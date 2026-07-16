"""Regression for the image-only by-sign trial-balance import route."""

import importlib.util
from decimal import Decimal
from pathlib import Path
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "Test" / "sez-contrapposte" / "Bilancino 31-5-26.pdf"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database.db import Base
from database.models import BalanceSheet, FinancialYear, IncomeStatement
from importers import pdf_importer


def test_scanned_verifica_segno_imports_without_anthropic(monkeypatch):
    if importlib.util.find_spec("rapidocr_onnxruntime") is None:
        pytest.skip("RapidOCR optional dependency is not installed")
    if not SOURCE.exists():
        pytest.skip("local scanned corpus PDF is unavailable")

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr(pdf_importer, "SessionLocal", session_factory)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    try:
        result = pdf_importer.import_pdf_balance_sheet(
            file_path=str(SOURCE),
            fiscal_year=2026,
            company_name="OCR REGRESSION",
            create_company=True,
            sector=1,
            user_id="ocr-regression",
        )

        assert result["validation_status"] == "review_required"
        assert result["forecastable"] is False

        with session_factory() as db:
            year = db.query(FinancialYear).one()
            balance = db.query(BalanceSheet).filter_by(financial_year_id=year.id).one()
            income = db.query(IncomeStatement).filter_by(financial_year_id=year.id).one()

            assert balance.total_assets == Decimal("1913698.44")
            assert balance.total_liabilities == Decimal("1913698.44")
            assert balance.sp02_immob_immateriali == Decimal("18931.18")
            assert balance.sp03_immob_materiali == Decimal("1232809.55")
            assert balance.sp06_crediti_breve == Decimal("374966.41")
            assert balance.sp12_riserve == Decimal("98464.87")
            assert balance.sp13_utile_perdita == Decimal("17872.66")
            assert income.net_profit == Decimal("17872.66")
    finally:
        engine.dispose()
