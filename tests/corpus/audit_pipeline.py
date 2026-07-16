"""Offline semantic audit of the paid/local import corpus.

The runner never calls OCR, vision or an LLM.  It audits:

* every unique source listed in ``manifest.json``;
* route-C PDFs through the deterministic production replica;
* native XBRL and CSV through an isolated in-memory database;
* historical batch databases through the current immutable validator.

IV-CEE PDFs whose only extractor is external are deliberately reported as
``NOT_REEXECUTED_NO_API``.  Existing database rows are still revalidated, but a
cached result is never presented as a fresh extraction from the source.

Run from the repository root::

    python tests/corpus/audit_pipeline.py
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterable, List

import fitz
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = ROOT / "Test"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tests") not in sys.path:
    sys.path.insert(0, str(ROOT / "tests"))

from database.db import Base  # noqa: E402
from database.models import Company, FinancialYear  # noqa: E402
from importers.bilancio_classifier import (  # noqa: E402
    ROUTE_IVCEE,
    ROUTE_TRIAL,
    ROUTE_UNSUPPORTED,
    ROUTE_XBRL,
    classify_bilancio,
)
from importers.csv_importer import CSVImporter  # noqa: E402
from importers.iv_cee_hierarchy import check_quadratura  # noqa: E402
from importers.xbrl_parser_enhanced import EnhancedXBRLParser  # noqa: E402
from _prod_route_c_runner import run_prod_route_c  # noqa: E402


logging.getLogger("importers").setLevel(logging.ERROR)


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _pdf_text(path: Path) -> str:
    try:
        with fitz.open(path) as document:
            return "".join(page.get_text() for page in document[:14])
    except Exception:
        return ""


def _validation_payload(q) -> Dict[str, Any]:
    return {
        "quadra": q.quadra,
        "semantic_valid": q.semantic_valid,
        "empty": q.is_empty,
        "masked": q.masked,
        "sp_difference": q.sbilancio,
        "ce_sp_match": q.utile_match,
        "plug_residual": q.plug_residual,
        "hierarchy_consistent": q.hierarchy_consistent,
        "hierarchy_differences": q.hierarchy_differences,
        "warnings": q.warnings,
    }


def _audit_trial(path: Path) -> Dict[str, Any]:
    try:
        result = run_prod_route_c(str(path))
    except ValueError as exc:
        scanned = not bool(_pdf_text(path).strip())
        return {
            "status": "UNSUPPORTED_LOCAL_OCR" if scanned else "REJECTED",
            "error": str(exc),
        }
    q = check_quadratura(result["bs"], result["ce"])
    status = (
        "PASS_VERIFIED"
        if q.semantic_valid
        else "PASS_STRUCTURAL"
        if q.quadra
        else "REVIEW_REQUIRED"
        if not q.is_empty
        else "REJECTED"
    )
    return {
        "status": status,
        "validation": _validation_payload(q),
        "sp02": result["sp02"],
        "sp03": result["sp03"],
        "sp13": result["sp13"],
        "total_assets": result["totale_attivo"],
        "netted_contra": result["contra"],
    }


def _memory_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine)()


def _audit_native(path: Path, file_format: str) -> Dict[str, Any]:
    engine, db = _memory_session()
    try:
        if file_format == "xbrl":
            imported = EnhancedXBRLParser(db_session=db).import_to_database(
                str(path), create_company=True
            )
        else:
            company = Company(name="Corpus CSV", tax_id=None, sector=1)
            db.add(company)
            db.flush()
            imported = CSVImporter(db_session=db).import_to_database(str(path), company.id)
        periods = []
        for fy in db.query(FinancialYear).order_by(FinancialYear.year, FinancialYear.id):
            periods.append(
                {
                    "year": fy.year,
                    "period_months": fy.period_months,
                    "validation_status": fy.validation_status,
                    "forecastable": bool(fy.forecastable),
                }
            )
        status = (
            "PASS_VERIFIED"
            if periods and all(item["forecastable"] for item in periods)
            else "REVIEW_REQUIRED"
        )
        return {"status": status, "periods": periods, "import": imported}
    except Exception as exc:
        db.rollback()
        return {"status": "REJECTED", "error": f"{type(exc).__name__}: {exc}"}
    finally:
        db.close()
        engine.dispose()


def audit_sources(manifest_path: Path) -> List[Dict[str, Any]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    records: List[Dict[str, Any]] = []
    for item in manifest["files"]:
        path = TEST_ROOT / item["paths"][0]
        record: Dict[str, Any] = {
            "sha256": item["sha256"],
            "path": str(path.relative_to(ROOT)),
            "format": item["format"],
        }
        if item["format"] in {"xbrl", "csv"}:
            record.update(_audit_native(path, item["format"]))
            record["route"] = "XBRL_NATIVE" if item["format"] == "xbrl" else "CSV_NATIVE"
            records.append(record)
            continue

        text = _pdf_text(path)
        try:
            classification = classify_bilancio(file_path=str(path), text=text)
            record.update(
                route=classification.route,
                macro_area=classification.macro_area,
                confidence=classification.confidence,
                reason=classification.reason,
                text_characters=len(text),
            )
        except Exception as exc:
            record.update(status="REJECTED", route="CLASSIFIER_ERROR", error=str(exc))
            records.append(record)
            continue

        if classification.route == ROUTE_TRIAL:
            record.update(_audit_trial(path))
        elif classification.route == ROUTE_IVCEE:
            record["status"] = "NOT_REEXECUTED_NO_API"
        elif classification.route == ROUTE_XBRL:
            record.update(_audit_native(path, "xbrl"))
        elif classification.route == ROUTE_UNSUPPORTED:
            record["status"] = (
                "UNSUPPORTED_LOCAL_OCR" if not text.strip() else "UNSUPPORTED"
            )
        else:
            record["status"] = "UNSUPPORTED"
        records.append(record)
    return records


def _row_dict(cursor: sqlite3.Cursor, row: sqlite3.Row) -> Dict[str, Decimal]:
    return {
        key: Decimal(str(row[key] or 0))
        for key in row.keys()
        if key.startswith(("sp", "ce"))
    }


def _batch_rows(db_path: Path) -> Iterable[Dict[str, Any]]:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        query = """
            SELECT fy.id AS fy_id, fy.year, fy.period_months,
                   fy.original_bs_snapshot, c.name AS company_name,
                   bs.*, inc.*
            FROM financial_years fy
            JOIN companies c ON c.id = fy.company_id
            JOIN balance_sheets bs ON bs.financial_year_id = fy.id
            JOIN income_statements inc ON inc.financial_year_id = fy.id
            ORDER BY fy.id
        """
        for row in connection.execute(query):
            values = _row_dict(connection.cursor(), row)
            bs = {key: value for key, value in values.items() if key.startswith("sp")}
            ce = {key: value for key, value in values.items() if key.startswith("ce")}
            raw_snapshot = row["original_bs_snapshot"]
            if raw_snapshot:
                try:
                    snapshot = json.loads(raw_snapshot)
                    for key in ("_plug_residual", "_unexplained_balance_difference"):
                        if key in snapshot:
                            bs[key] = Decimal(str(snapshot[key]))
                except (TypeError, ValueError, json.JSONDecodeError):
                    bs["_plug_residual"] = Decimal("Infinity")
            q = check_quadratura(bs, ce)
            yield {
                "database": db_path.name,
                "financial_year_id": row["fy_id"],
                "company": row["company_name"],
                "year": row["year"],
                "period_months": row["period_months"],
                "status": "PASS_VERIFIED" if q.semantic_valid else "REVIEW_REQUIRED",
                "validation": _validation_payload(q),
            }
    finally:
        connection.close()


def audit_batch_databases(folder: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for db_path in sorted(folder.glob("*.db")):
        rows.extend(_batch_rows(db_path))
    return rows


def _summary(records: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    return dict(sorted(Counter(record["status"] for record in records).items()))


def _markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# Audit corrente della logica di import",
        "",
        "Esecuzione interamente locale: nessuna chiamata OCR, vision o LLM.",
        "",
        "## Sorgenti uniche",
        "",
        "| Stato | Numero |",
        "|---|---:|",
    ]
    lines.extend(f"| {key} | {value} |" for key, value in report["source_summary"].items())
    lines.extend(
        [
            "",
            "## Record dei database batch riesaminati",
            "",
            "| Stato | Numero |",
            "|---|---:|",
        ]
    )
    lines.extend(f"| {key} | {value} |" for key, value in report["batch_summary"].items())
    lines.extend(
        [
            "",
            "`NOT_REEXECUTED_NO_API` non è un successo: indica PDF IV-CEE per cui "
            "non è stata ripetuta l'estrazione esterna. I record già presenti nei "
            "database batch sono comunque stati rivalidati con le regole correnti.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--json",
        type=Path,
        default=TEST_ROOT / "_analysis" / "current_logic_audit.json",
    )
    parser.add_argument(
        "--md",
        type=Path,
        default=TEST_ROOT / "_analysis" / "current_logic_audit.md",
    )
    args = parser.parse_args()

    sources = audit_sources(Path(__file__).with_name("manifest.json"))
    batch = audit_batch_databases(TEST_ROOT / "_batch_dbs")
    report = {
        "policy": "offline_no_api",
        "source_summary": _summary(sources),
        "batch_summary": _summary(batch),
        "sources": sources,
        "batch_financial_years": batch,
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(
        json.dumps(_json_value(report), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    args.md.write_text(_markdown(report), encoding="utf-8")
    print(json.dumps({"sources": report["source_summary"], "batch": report["batch_summary"]}, indent=2))
    print(f"JSON: {args.json}")
    print(f"Markdown: {args.md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
