"""Deduplicated production PDF-import audit for the local corpus.

The runner exercises ``import_pdf_balance_sheet`` against an isolated in-memory
database for every unique IV-CEE PDF under ``Test``.  ``Test/july_budget`` and
``Test/_analysis`` are always excluded.  SHA-256 aliases are retained in the
report, but the external extractor is called once per unique content.

Results are checkpointed after every file, so an interrupted paid run resumes
without repeating completed API calls.

Run from the repository root::

    python tests/corpus/api_pdf_import_audit.py --workers 3
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import time
import traceback
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import fitz


ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = ROOT / "Test"
DEFAULT_OUTPUT = TEST_ROOT / "_analysis" / "api_pdf_import_excluding_july.json"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_pdfs() -> dict[str, list[Path]]:
    by_hash: dict[str, list[Path]] = defaultdict(list)
    for path in sorted(TEST_ROOT.rglob("*"), key=lambda item: item.as_posix().casefold()):
        if not path.is_file() or path.suffix.lower() != ".pdf":
            continue
        relative_parts = tuple(part.casefold() for part in path.relative_to(TEST_ROOT).parts)
        if "july_budget" in relative_parts or "_analysis" in relative_parts:
            continue
        by_hash[_sha256(path)].append(path)
    return by_hash


def _pdf_text(path: Path) -> str:
    with fitz.open(path) as document:
        return "".join(page.get_text() for page in document[:14])


def _inventory(include_scanned: bool) -> list[dict[str, Any]]:
    from importers.bilancio_classifier import ROUTE_IVCEE, classify_bilancio

    records: list[dict[str, Any]] = []
    for digest, paths in sorted(_source_pdfs().items()):
        canonical = paths[0]
        text = _pdf_text(canonical)
        classification = classify_bilancio(file_path=str(canonical), text=text)
        is_scanned = len(text.strip()) < 50
        if classification.route != ROUTE_IVCEE and not (include_scanned and is_scanned):
            continue
        records.append(
            {
                "sha256": digest,
                "canonical_path": str(canonical.relative_to(ROOT)),
                "aliases": [str(path.relative_to(ROOT)) for path in paths],
                "route_before_ocr": classification.route,
                "macro_area_before_ocr": classification.macro_area,
                "classification_reason": classification.reason,
                "scanned": is_scanned,
            }
        )
    return records


def _load_environment() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / "backend" / ".env", override=False)
    except ImportError:
        env_path = ROOT / "backend" / ".env"
        if env_path.exists():
            for raw_line in env_path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip())


def _audit_one(item: dict[str, Any]) -> dict[str, Any]:
    """Run one production import in a private process and private database."""
    started = time.monotonic()
    _load_environment()
    logging.getLogger().setLevel(logging.ERROR)
    logging.getLogger("importers").setLevel(logging.ERROR)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from database.db import Base
    from importers import pdf_importer

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    pdf_importer.SessionLocal = sessionmaker(bind=engine)
    source = ROOT / item["canonical_path"]

    record = dict(item)
    try:
        result = pdf_importer.import_pdf_balance_sheet(
            file_path=str(source),
            fiscal_year=2025,
            company_name=f"CORPUS AUDIT {item['sha256'][:12]}",
            create_company=True,
            sector=1,
            user_id="corpus-audit",
        )
        record.update(
            status="PASS",
            validation_status=result.get("validation_status"),
            forecastable=bool(result.get("forecastable")),
            prior_year_imported=bool(result.get("prior_year_imported")),
            warnings=result.get("warnings") or [],
            result=result,
        )
    except Exception as exc:  # each failure must remain isolated and reportable
        record.update(
            status="FAIL",
            error_type=type(exc).__name__,
            error=str(exc),
            traceback="".join(traceback.format_exception(exc))[-8000:],
        )
    finally:
        engine.dispose()
    record["elapsed_seconds"] = round(time.monotonic() - started, 3)
    record["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    return record


def _read_report(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"records": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"records": []}


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _write_report(path: Path, inventory: list[dict[str, Any]], records: dict[str, dict[str, Any]]) -> None:
    statuses = Counter(record.get("status", "PENDING") for record in records.values())
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "unique IVCEE PDFs under Test, excluding Test/july_budget and Test/_analysis",
        "unique_inventory": len(inventory),
        "physical_aliases": sum(len(item["aliases"]) for item in inventory),
        "summary": dict(sorted(statuses.items())),
        "records": [records[key] for key in sorted(records)],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(_json_safe(report), ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--retry-failures", action="store_true")
    parser.add_argument(
        "--path-pattern",
        action="append",
        default=[],
        help="only execute canonical paths containing one of these substrings",
    )
    parser.add_argument(
        "--include-scanned",
        action="store_true",
        help="also try image-only PDFs whose pre-OCR route is unsupported",
    )
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    inventory = _inventory(include_scanned=args.include_scanned)
    previous = _read_report(args.output)
    records = {
        record["sha256"]: record
        for record in previous.get("records", [])
        if record.get("sha256")
    }
    completed_before_run = sum(item["sha256"] in records for item in inventory)
    pending = [
        item
        for item in inventory
        if item["sha256"] not in records
        or (args.retry_failures and records[item["sha256"]].get("status") == "FAIL")
    ]
    if args.path_pattern:
        patterns = [pattern.casefold() for pattern in args.path_pattern]
        pending = [
            item for item in pending
            if any(pattern in item["canonical_path"].casefold() for pattern in patterns)
        ]
    if args.limit is not None:
        pending = pending[: max(args.limit, 0)]

    print(
        f"IVCEE unici={len(inventory)} alias={sum(len(item['aliases']) for item in inventory)} "
        f"gia_completati={completed_before_run} da_eseguire={len(pending)}",
        flush=True,
    )
    _write_report(args.output, inventory, records)
    if not pending:
        print(f"Report: {args.output}", flush=True)
        return 0

    workers = max(1, min(args.workers, 4))
    with ProcessPoolExecutor(max_workers=workers) as executor:
        future_items = {executor.submit(_audit_one, item): item for item in pending}
        completed = 0
        for future in as_completed(future_items):
            item = future_items[future]
            try:
                record = future.result()
            except Exception as exc:
                record = dict(item)
                record.update(
                    status="FAIL",
                    error_type=type(exc).__name__,
                    error=str(exc),
                    traceback="".join(traceback.format_exception(exc))[-8000:],
                    completed_at_utc=datetime.now(timezone.utc).isoformat(),
                )
            records[item["sha256"]] = record
            completed += 1
            _write_report(args.output, inventory, records)
            print(
                f"[{completed}/{len(pending)}] {record['status']:4s} "
                f"{record['canonical_path']} ({record.get('elapsed_seconds', 0)}s) "
                f"{record.get('error', '')[:180]}",
                flush=True,
            )

    print(f"Riepilogo: {dict(Counter(record['status'] for record in records.values()))}")
    print(f"Report: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
