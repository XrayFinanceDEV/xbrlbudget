from decimal import Decimal
from pathlib import Path

import pytest

from importers.pdf_extractor_llm import _declared_control_totals
from importers.iv_cee_hierarchy import check_quadratura
from importers.pdf_mapper import IVCEEMapper
from importers.standard_ivcee_parser import (
    extract_standard_ivcee_balances,
    extract_standard_ivcee_income,
    overlay_standard_ivcee_balance,
)


ROOT = Path(__file__).resolve().parents[1]
PDF_328 = (
    ROOT
    / "Test"
    / "successTerzo"
    / "success"
    / "budget_328_2025- ELLE ERRE BIL.pdf"
)


def test_declared_controls_accept_whole_euro_thousands_totals():
    text = """
    Stato patrimoniale attivo
    Totale attivo
    6.474.612
    Stato patrimoniale passivo
    Totale passivo
    6.474.612
    Utile d'esercizio
    30.440
    Conto economico
    """

    controls = _declared_control_totals("unused.pdf", text=text)

    assert controls["attivo"] == Decimal("6474612")
    assert controls["passivo"] == Decimal("6474612")
    assert controls["utile"] == Decimal("30440")


def test_source_overlay_preserves_typed_llm_details():
    extracted = {
        "sp06_crediti_breve": Decimal("1"),
        "sp06a_crediti_clienti_breve": Decimal("2790956"),
    }
    source = {
        "sp06_crediti_breve": Decimal("2926403"),
        "totale_attivo": Decimal("6474612"),
    }

    result = overlay_standard_ivcee_balance(extracted, source)

    assert result["sp06_crediti_breve"] == Decimal("2926403")
    assert result["totale_attivo"] == Decimal("6474612")
    assert result["sp06a_crediti_clienti_breve"] == Decimal("2790956")


@pytest.mark.skipif(not PDF_328.exists(), reason="local PDF corpus not available")
def test_budget_328_source_balances_are_exact_and_self_validating():
    current, prior = extract_standard_ivcee_balances(str(PDF_328))
    current_ce, prior_ce = extract_standard_ivcee_income(str(PDF_328))

    assert current is not None
    assert current["totale_attivo"] == Decimal("6474612")
    assert current["totale_passivo"] == Decimal("6474612")
    assert current["sp13_utile_perdita"] == Decimal("30440")
    assert current["sp06_crediti_breve"] == Decimal("2926403")
    assert current["sp07_crediti_lungo"] == Decimal("73019")
    assert current["sp16_debiti_breve"] == Decimal("2683274")
    assert current["sp17_debiti_lungo"] == Decimal("303510")
    assert IVCEEMapper().validate_balance(current)
    assert current_ce is not None
    assert current_ce["ce10_var_rimanenze_mat_prime"] == Decimal("0")
    assert current_ce["ce11_accantonamenti"] == Decimal("12586")
    current_q = check_quadratura(current, current_ce, tol=Decimal("2"))
    assert current_q.quadra
    assert current_q.utile_ce == Decimal("30440")

    assert prior is not None
    assert prior["totale_attivo"] == Decimal("6783434")
    assert prior["totale_passivo"] == Decimal("6783434")
    assert IVCEEMapper().validate_balance(prior)
    assert prior_ce is not None
    assert prior_ce["ce10_var_rimanenze_mat_prime"] == Decimal("-300567")
    prior_q = check_quadratura(prior, prior_ce, tol=Decimal("2"))
    assert prior_q.quadra
    assert prior_q.utile_ce == Decimal("283549")


@pytest.mark.skipif(not PDF_328.exists(), reason="local PDF corpus not available")
def test_budget_328_imports_end_to_end_without_an_api_key(monkeypatch):
    """The production import must use verified source rows, not LLM luck."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from database.db import Base
    from database.models import FinancialYear
    from importers import pdf_importer

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    monkeypatch.setattr(pdf_importer, "SessionLocal", sessions)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    try:
        result = pdf_importer.import_pdf_balance_sheet(
            file_path=str(PDF_328),
            fiscal_year=2025,
            company_name="ELLE ERRE SOURCE TEST",
            create_company=True,
            sector=1,
            user_id="source-test",
        )

        assert result["success"] is True
        assert result["extraction_method"] == "ivcee_source"
        assert result["prior_year_imported"] is True

        with sessions() as db:
            current = db.query(FinancialYear).filter_by(year=2025).one()
            prior = db.query(FinancialYear).filter_by(year=2024).one()
            assert current.balance_sheet.total_assets == Decimal("6474612")
            assert current.balance_sheet.total_liabilities == Decimal("6474612")
            assert current.balance_sheet.sp13_utile_perdita == Decimal("30440")
            assert current.income_statement.net_profit == Decimal("30440")
            assert prior.balance_sheet.total_assets == Decimal("6783434")
            assert prior.balance_sheet.total_liabilities == Decimal("6783434")
            assert prior.income_statement.net_profit == Decimal("283549")
    finally:
        engine.dispose()
