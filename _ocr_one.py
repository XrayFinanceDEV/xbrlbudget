"""Single-file STD vs OCR import diagnostic. Usage: python _ocr_one.py "<pdf path>"
Prints a compact JSON line plus, on OCR failure, the MinerU totals-region text so the
cause (garbled OCR total, wrong routing, hierarchy mismatch) is visible."""
import asyncio
import json
import os
import re
import sys

os.environ.setdefault("ANTHROPIC_API_KEY", open("_akey.tmp").read().strip())

from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import importers.pdf_importer as pdf_importer
from database.db import Base
from database.models import BalanceSheet, Company, FinancialYear
from backend.app.services.mineru_client import MinerUClient
from importers.mineru_adapter import build_extraction_context

BRIDGE = "http://127.0.0.1:8002"


def _setup():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)
    pdf_importer.SessionLocal = s
    return s


def _imp(sessions, path, tag, ctx):
    cname = f"{tag}"
    try:
        res = pdf_importer.import_pdf_balance_sheet(
            file_path=path, company_id=None, fiscal_year=2025, company_name=cname,
            create_company=True, sector=1, period_months=None, user_id="h", extraction_context=ctx,
        )
    except Exception as e:
        return {"outcome": "FAIL", "error": f"{type(e).__name__}: {str(e)[:140]}"}
    db = sessions()
    try:
        comp = db.query(Company).filter(Company.name == cname).first()
        fy = db.query(FinancialYear).filter(FinancialYear.company_id == comp.id).first() if comp else None
        bs = db.query(BalanceSheet).filter(BalanceSheet.financial_year_id == fy.id).first() if fy else None
        if not bs:
            return {"outcome": "FAIL", "error": "no BS created"}
        att, pas = Decimal(str(bs.total_assets)), Decimal(str(bs.total_liabilities))
        diff = att - pas
        return {
            "outcome": "IMPORT",
            "attivo": float(att), "passivo": float(pas), "diff": float(diff),
            "quadra": abs(diff) <= Decimal("1"),
            "validation_status": getattr(fy, "validation_status", None),
            "warnings": [str(w)[:80] for w in (res.get("warnings") or [])][:4],
            "extraction_method": res.get("extraction_method"),
        }
    finally:
        db.close()


async def main():
    path = sys.argv[1]
    sessions = _setup()
    out = {"file": os.path.basename(path)}

    out["std"] = _imp(sessions, path, "STD", None)

    client = MinerUClient(base_url=BRIDGE, timeout_seconds=550, language="latin",
                          backend="pipeline", parse_method="ocr")
    with open(path, "rb") as fh:
        raw = await client.parse_pdf(content=fh.read(), filename=os.path.basename(path))
    ctx = build_extraction_context(raw)
    out["mineru"] = {"version": ctx.mineru_version, "pages": ctx.page_count, "tables": ctx.table_count, "rows": len(ctx.rows)}
    out["ocr"] = _imp(sessions, path, "OCR", ctx)

    # If OCR failed or didn't balance, surface the MinerU totals region for diagnosis
    if out["ocr"]["outcome"] == "FAIL" or not out["ocr"].get("quadra", False):
        txt = ctx.full_text
        snips = []
        for kw in ["totale attiv", "totale passiv", "pareggio", "totale general"]:
            for m in re.finditer(re.escape(kw), txt, re.I):
                s = txt[max(0, m.start() - 30):m.start() + 70].replace("\n", " ")
                snips.append(s)
        out["mineru_totals_region"] = snips[:6]

    print("JSONRESULT " + json.dumps(out, ensure_ascii=False))


asyncio.run(main())
