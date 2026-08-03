"""Production-faithful import probe on a THROWAWAY in-memory DB.

Calls the real `importers.pdf_importer.import_pdf_balance_sheet` (the same
function the `/import/pdf` endpoint calls) but binds `SessionLocal` to a fresh
in-memory SQLite engine, so the real `financial_analysis.db` is never touched.

Answers the only question that matters for the audit: *does this PDF import, and
are the stored numbers right?* — unlike `Test/_quadratura_harness.py`, which
stops at `extract -> check_quadratura` and is therefore pessimistic on route A/B
and optimistic on route C.

CLI (needs the local, gitignored `Test/` corpus):
    python tests/_import_probe.py "<file.pdf>" [standard|ocr]
    python tests/_import_probe.py --dir "<folder>" [standard|ocr] [--json out.jsonl]
"""
import argparse
import glob
import json
import os
import sys
import traceback
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _load_env():
    """Make ANTHROPIC_API_KEY available exactly like the running backend does."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return
    for cand in (os.path.join(ROOT, "backend", ".env"), os.path.join(ROOT, ".env")):
        if not os.path.exists(cand):
            continue
        for line in open(cand, encoding="utf-8", errors="ignore"):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import database.db as dbmod  # noqa: E402
from database.models import Base  # noqa: E402


def _install_memory_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    dbmod.engine = engine
    dbmod.SessionLocal = Session
    import importers.pdf_importer as pi
    pi.SessionLocal = Session
    return Session


_install_memory_db()

from importers.pdf_importer import import_pdf_balance_sheet  # noqa: E402


def _mineru_context(file_path: str):
    """Build the MinerU extraction context the /import/pdf-ocr endpoint injects."""
    from backend.app.services.mineru_client import MinerUClient  # noqa: WPS433
    from importers.mineru_adapter import build_extraction_context  # noqa: WPS433
    import asyncio

    client = MinerUClient(
        base_url=os.environ.get("MINERU_BASE_URL", "http://127.0.0.1:8002"),
        expected_version="3.2.0", language="latin",
        backend="pipeline", parse_method="ocr", timeout_seconds=600.0,
    )
    content = open(file_path, "rb").read()

    async def _go():
        await client.health()
        return await client.parse_pdf(content=content,
                                      filename=os.path.basename(file_path))

    return build_extraction_context(asyncio.run(_go()))


def probe(file_path: str, method: str = "standard") -> dict:
    """Import one file; never raises. Returns a flat result record."""
    rec = {
        "file": os.path.basename(file_path),
        "sha256": sha256_of(file_path),
        "method": method,
        "ok": False,
        "error": None,
        "route": None,
        "macro_area": None,
        "macro_subcategory": None,
        "extraction_method": None,
        "validation_status": None,
        "forecastable": None,
        "totale_attivo": None,
        "totale_passivo": None,
        "sbilancio": None,
        "utile_ce": None,
        "sp13": None,
        "plug_residual": None,
        "netted_contra": None,
        "prior_year_imported": None,
        "warnings": [],
        "masked": None,
        # {colonna_db: str(Decimal)} per ogni sp*/ce* non nullo. Stringhe, mai float:
        # i confronti di baseline su float producono falsi diff da arrotondamento.
        "fields": {},
    }
    ctx = None
    try:
        if method == "ocr":
            ctx = _mineru_context(file_path)
    except Exception as exc:  # MinerU unavailable -> record honestly
        rec["error"] = f"MINERU_UNAVAILABLE: {type(exc).__name__}: {exc}"
        return rec

    try:
        res = import_pdf_balance_sheet(
            file_path=file_path,
            company_id=None,
            fiscal_year=None,
            company_name=os.path.splitext(os.path.basename(file_path))[0][:60],
            create_company=True,
            sector=1,
            user_id="probe-user",
            extraction_context=ctx,
        )
        rec["ok"] = bool(res.get("success", True))
        rec["macro_area"] = res.get("macro_area")
        rec["macro_subcategory"] = res.get("macro_subcategory")
        rec["extraction_method"] = res.get("extraction_method")
        rec["route"] = res.get("extraction_method")
        rec["validation_status"] = res.get("validation_status")
        rec["forecastable"] = res.get("forecastable")
        rec["prior_year_imported"] = res.get("prior_year_imported")
        vr = res.get("validation_report") or {}
        _q = vr.get("quadratura") or {}
        rec["masked"] = _q.get("masked", vr.get("masked"))
        rec["plug_residual"] = _str_dec(_q.get("plug_residual", vr.get("plug_residual")))
        rec["netted_contra"] = _str_dec(vr.get("netted_contra"))
        w = list(res.get("warnings") or []) + list(vr.get("warnings") or [])
        rec["warnings"] = [str(x)[:220] for x in w][:10]

        # Read back what was actually STORED (the numbers the user sees).
        from database.models import BalanceSheet, IncomeStatement
        s = dbmod.SessionLocal()
        try:
            bs = s.get(BalanceSheet, res.get("balance_sheet_id"))
            ce = s.get(IncomeStatement, res.get("income_statement_id"))
            bsd = _as_dict(bs)
            ced = _as_dict(ce)
            if bsd:
                from importers.iv_cee_hierarchy import check_quadratura
                q = check_quadratura(bsd, ced or None, tol=Decimal("2"))
                rec["totale_attivo"] = _num(q.totale_attivo)
                rec["totale_passivo"] = _num(q.totale_passivo)
                rec["sbilancio"] = _num(q.sbilancio)
                rec["utile_ce"] = _num(q.utile_ce)
                rec["quadra"] = bool(q.quadra)
                rec["sp13"] = _num(bsd.get("sp13_utile_perdita"))
                for wmsg in q.warnings:
                    if str(wmsg) not in rec["warnings"]:
                        rec["warnings"].append(str(wmsg)[:220])
            # tutti i campi contabili non nulli, come stringhe Decimal
            for src in (bsd, ced):
                for name, value in (src or {}).items():
                    if not (name.startswith("sp") or name.startswith("ce")):
                        continue
                    # NB: mai riusare `s` qui — e' la sessione DB chiusa nel
                    # finally; sovrascriverla faceva fallire ogni import RIUSCITO
                    # con "AttributeError: 'str' object has no attribute 'close'".
                    amount = _str_dec(value)
                    if amount is not None and amount != "0":
                        rec["fields"][name] = amount
        finally:
            s.close()
    except Exception as exc:
        rec["error"] = f"{type(exc).__name__}: {exc}"
        rec["traceback"] = traceback.format_exc()[-1200:]
    return rec


def sha256_of(path: str) -> str:
    """Hash del documento: la baseline e' indicizzata per contenuto, non per nome
    (gli stessi PDF ricorrono con nomi diversi in piu' cartelle del corpus)."""
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _as_dict(obj):
    if obj is None:
        return {}
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns
            if c.name not in ("id", "financial_year_id", "created_at", "updated_at")}


def _num(v):
    if v is None:
        return None
    try:
        return float(Decimal(str(v)))
    except Exception:
        return None


def _str_dec(v):
    """Importo come stringa Decimal normalizzata (mai float): '1234.50' -> '1234.5'.

    La baseline confronta stringhe; senza normalizzazione '1234.50' e '1234.5'
    sarebbero un falso diff, e con i float lo sarebbero 0.1+0.2 e 0.3.
    """
    if v is None:
        return None
    try:
        return str(Decimal(str(v)).normalize())
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target")
    ap.add_argument("method", nargs="?", default="standard", choices=["standard", "ocr"])
    ap.add_argument("--dir", action="store_true", help="target is a folder")
    ap.add_argument("--json", default=None, help="write JSONL results here")
    ap.add_argument("--only", default=None, help="substring filter on filename")
    args = ap.parse_args()

    if args.dir or os.path.isdir(args.target):
        files = [p for p in sorted(glob.glob(os.path.join(args.target, "*")))
                 if os.path.splitext(p)[1].lower() in (".pdf",)]
    else:
        files = [args.target]
    if args.only:
        files = [f for f in files if args.only.lower() in os.path.basename(f).lower()]

    out = open(args.json, "w", encoding="utf-8") if args.json else None
    for p in files:
        rec = probe(p, args.method)
        status = "OK  " if rec["ok"] and not rec["error"] else "FAIL"
        extra = ""
        if rec["ok"]:
            extra = (f"attivo={rec['totale_attivo']:,.0f} sbil={rec['sbilancio']:,.2f} "
                     f"sp13={rec['sp13']} masked={rec['masked']}") if rec['totale_attivo'] is not None else ""
        else:
            extra = (rec["error"] or "")[:160]
        print(f"{status} [{rec.get('macro_area') or '?'}] {rec['file'][:58]:<58} {extra}", flush=True)
        if out:
            out.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
            out.flush()
    if out:
        out.close()


if __name__ == "__main__":
    main()
