"""Batch OCR-import harness over a slice of _uniq_pdfs.txt.
Usage: python _ocr_batch.py <start_line> <end_line>   (1-indexed, inclusive)
Runs each file through the OCR path (MinerU 3.2.0 -> import_pdf_balance_sheet) into an
isolated DB and appends one JSON line per file to _ocr_res_<start>_<end>.jsonl."""
import asyncio
import json
import os
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


async def main():
    start, end = int(sys.argv[1]), int(sys.argv[2])
    files = [l.strip() for l in open("_uniq_pdfs.txt", encoding="utf-8") if l.strip()]
    slice_files = files[start - 1:end]
    out_path = f"_ocr_res_{start}_{end}.jsonl"
    sessions = _setup()
    client = MinerUClient(base_url=BRIDGE, timeout_seconds=550, language="latin",
                          backend="pipeline", parse_method="ocr")

    with open(out_path, "w", encoding="utf-8") as out:
        for idx, path in enumerate(slice_files, start):
            rec = {"line": idx, "file": os.path.basename(path)}
            try:
                with open(path, "rb") as fh:
                    raw = await client.parse_pdf(content=fh.read(), filename=os.path.basename(path))
                ctx = build_extraction_context(raw)
                rec["mineru"] = {"ver": ctx.mineru_version, "pages": ctx.page_count, "tables": ctx.table_count}
            except Exception as e:
                rec["ocr"] = "MINERU_ERR"
                rec["err"] = f"{type(e).__name__}: {str(e)[:80]}"
                out.write(json.dumps(rec, ensure_ascii=False) + "\n"); out.flush()
                print(f"[{idx}] {rec['file'][:40]}: MINERU_ERR")
                continue
            try:
                res = pdf_importer.import_pdf_balance_sheet(
                    file_path=path, company_id=None, fiscal_year=2025,
                    company_name=f"B{idx}", create_company=True, sector=1,
                    period_months=None, user_id="h", extraction_context=ctx,
                )
                db = sessions()
                comp = db.query(Company).filter(Company.name == f"B{idx}").first()
                fy = db.query(FinancialYear).filter(FinancialYear.company_id == comp.id).first() if comp else None
                bs = db.query(BalanceSheet).filter(BalanceSheet.financial_year_id == fy.id).first() if fy else None
                if bs:
                    att, pas = Decimal(str(bs.total_assets)), Decimal(str(bs.total_liabilities))
                    rec["ocr"] = "IMPORT"
                    rec["quadra"] = abs(att - pas) <= Decimal("1")
                    rec["attivo"] = float(att)
                    rec["vstatus"] = getattr(fy, "validation_status", None)
                else:
                    rec["ocr"] = "IMPORT"; rec["quadra"] = None; rec["note"] = "no BS"
                db.close()
                print(f"[{idx}] {rec['file'][:40]}: IMPORT quadra={rec.get('quadra')}")
            except Exception as e:
                rec["ocr"] = "FAIL"
                rec["err"] = f"{type(e).__name__}: {str(e)[:90]}"
                print(f"[{idx}] {rec['file'][:40]}: FAIL {type(e).__name__}")
            out.write(json.dumps(rec, ensure_ascii=False) + "\n"); out.flush()

    print(f"DONE slice {start}-{end} -> {out_path}")


asyncio.run(main())
