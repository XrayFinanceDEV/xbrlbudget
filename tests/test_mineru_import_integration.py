"""MinerU structured evidence -> real accounting importer -> persisted years.

MinerU transport is outside this test; unlike the endpoint contract test, the
accounting importer itself is not mocked.
"""
import json
from decimal import Decimal
from pathlib import Path

import fitz
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.db import Base
from database.models import FinancialYear
from importers.mineru_adapter import build_extraction_context


FIXTURE = Path(__file__).parent / "fixtures" / "mineru" / "file_parse_response.json"


def _context():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    block = payload["results"]["sample"]
    return build_extraction_context({**block, "version": payload["version"]})


def test_structured_mineru_tables_persist_verified_current_and_prior(tmp_path, monkeypatch):
    from importers import pdf_importer

    # A scanned PDF may have no text layer. The accounting evidence comes from
    # MinerU's structured context, not from this original file.
    pdf_path = tmp_path / "scanned-source.pdf"
    document = fitz.open()
    document.new_page()
    document.save(pdf_path)
    document.close()

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    monkeypatch.setattr(pdf_importer, "SessionLocal", sessions)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    try:
        result = pdf_importer.import_pdf_balance_sheet(
            file_path=str(pdf_path),
            fiscal_year=2024,
            company_name="SYNTHETIC OCR COMPANY",
            create_company=True,
            sector=1,
            user_id="mineru-integration-user",
            extraction_context=_context(),
        )

        assert result["success"] is True
        assert result["extraction_method"] == "mineru+ivcee_deterministic"
        assert result["prior_year_imported"] is True
        assert result["ocr_engine"] == "mineru"
        assert result["ocr_version"] == "3.2.0"
        assert result["source_detail_fields"] >= 8
        assert result["detail_level"] == "standard"
        assert result["forecastable"] is True

        with sessions() as db:
            years = (
                db.query(FinancialYear)
                .filter(FinancialYear.company_id == result["company_id"])
                .order_by(FinancialYear.year.desc())
                .all()
            )
            assert [year.year for year in years] == [2024, 2023]
            current, prior = years
            assert current.validation_status == "verified"
            assert current.forecastable is True
            assert current.parser_version.endswith("+mineru-3.2.0")
            report = json.loads(current.validation_report)
            assert report["ocr"]["accounting_method"] == "ivcee_deterministic"
            assert report["ocr"]["source_detail_fields"] >= 8
            assert current.balance_sheet.total_assets == Decimal("100")
            assert current.balance_sheet.total_liabilities == Decimal("100")
            assert current.income_statement.net_profit == Decimal("20")
            assert prior.balance_sheet.total_assets == Decimal("90")
            assert prior.income_statement.net_profit == Decimal("15")
    finally:
        engine.dispose()


def test_route_c_deterministic_parser_receives_mineru_text_override(tmp_path, monkeypatch):
    from importers import situazione_contabile_parser as parser

    pdf_path = tmp_path / "blank.pdf"
    document = fitz.open()
    document.new_page()
    document.save(pdf_path)
    document.close()

    seen = []
    monkeypatch.setattr(parser, "parse_entries", lambda text: seen.append(text) or [])
    monkeypatch.setattr(parser, "build_iv_cee", lambda entries, default_ce=False: ({}, {}))

    result = parser.extract_situazione_contabile(
        str(pdf_path),
        return_prior=False,
        text_override="OCR_ONLY_ACCOUNTING_TEXT",
    )

    assert seen == ["OCR_ONLY_ACCOUNTING_TEXT"]
    assert result == ({}, {})
