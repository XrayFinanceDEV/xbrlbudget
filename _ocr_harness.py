"""Ad-hoc harness: compare STANDARD (/import/pdf, native text) vs OCR (/import/pdf-ocr,
MinerU 3.2.0 live) import for every PDF in Test/prova_tets, in an isolated SQLite DB.
Answers: do they balance, and does OCR help or hurt vs the native-text path?"""
import asyncio
import glob
import os

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
FOLDER = "Test/prova_tets"


def euro(v):
    try:
        return f"{Decimal(str(v)):,.2f}".replace(",", "#").replace(".", ",").replace("#", ".")
    except Exception:
        return str(v)


async def main():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    pdf_importer.SessionLocal = sessions

    client = MinerUClient(base_url=BRIDGE, timeout_seconds=550, language="latin",
                          backend="pipeline", parse_method="ocr")
    h = await client.health()
    print(f"MinerU {h.version} status={h.status}\n")

    def run_import(path, tag, ctx):
        cname = f"{tag}_{os.path.basename(path)[:18]}"
        try:
            pdf_importer.import_pdf_balance_sheet(
                file_path=path, company_id=None, fiscal_year=2025,
                company_name=cname, create_company=True, sector=1,
                period_months=None, user_id="harness", extraction_context=ctx,
            )
        except Exception as e:
            return ("FAIL", "-", f"{type(e).__name__}: {str(e)[:45]}")
        db = sessions()
        try:
            comp = db.query(Company).filter(Company.name == cname).first()
            fy = db.query(FinancialYear).filter(FinancialYear.company_id == comp.id).first() if comp else None
            bs = db.query(BalanceSheet).filter(BalanceSheet.financial_year_id == fy.id).first() if fy else None
            if not bs:
                return ("FAIL", "-", "no BS")
            att, pas = bs.total_assets, bs.total_liabilities
            quad = "OK" if abs(Decimal(str(att)) - Decimal(str(pas))) <= Decimal("1") else f"SBIL({euro(att - pas)})"
            return ("IMPORT", quad, euro(att))
        finally:
            db.close()

    files = sorted(glob.glob(os.path.join(FOLDER, "*.pdf")))
    rows = []
    for i, path in enumerate(files, 1):
        name = os.path.basename(path)[:44]
        std = run_import(path, f"STD{i}", None)
        try:
            with open(path, "rb") as fh:
                raw = await client.parse_pdf(content=fh.read(), filename=os.path.basename(path))
            ctx = build_extraction_context(raw)
            ocr = run_import(path, f"OCR{i}", ctx)
        except Exception as e:
            ocr = ("MINERU_ERR", "-", type(e).__name__)
        rows.append((name, std, ocr))
        so = "quadra" if std[0] == "IMPORT" and std[1] == "OK" else (std[1] if std[0] == "IMPORT" else "FAIL")
        oo = "quadra" if ocr[0] == "IMPORT" and ocr[1] == "OK" else (ocr[1] if ocr[0] == "IMPORT" else ocr[0])
        print(f"[{i}/{len(files)}] {name}\n     STD={so:14} OCR={oo}")

    print("\n===== RIEPILOGO  STANDARD vs OCR =====")
    print(f"{'FILE':46}{'STD':>12}{'OCR':>12}")
    print("-" * 72)
    std_ok = ocr_ok = 0
    for name, std, ocr in rows:
        s = "quadra" if std[0] == "IMPORT" and std[1] == "OK" else (std[0] if std[0] != "IMPORT" else std[1])
        o = "quadra" if ocr[0] == "IMPORT" and ocr[1] == "OK" else (ocr[0] if ocr[0] != "IMPORT" else ocr[1])
        std_ok += s == "quadra"
        ocr_ok += o == "quadra"
        print(f"{name:46}{s:>12}{o:>12}")
    print(f"\nStandard quadrati: {std_ok}/{len(files)}   |   OCR quadrati: {ocr_ok}/{len(files)}")


asyncio.run(main())
