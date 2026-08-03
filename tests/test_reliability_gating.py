"""The reliability verdict gates the FORECAST, never the SAVE.

An unreliable file must still be persisted: Rettifiche operates on a saved
FinancialYear, so refusing to save would make the file uncorrectable.
"""
import os
import sys
from decimal import Decimal

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from importers.pdf_importer import _validation_report_payload  # noqa: E402
from importers.reliability import assess                       # noqa: E402

D = Decimal

# Local corpus fixture (not shipped in the repo - skip cleanly when absent,
# matching the rest of tests/, e.g. test_budget_615_semantic_classification.py).
PDF_615 = os.path.join(
    ROOT, "tests", "debug", "budget_615_2024 Lavori di meccanica generale.pdf")


class _FakeQ:
    """Minimal stand-in for the check_quadratura result."""
    sbilancio = D("0")
    utile_match = True
    hierarchy_consistent = True
    semantic_valid = True
    masked = False
    is_empty = False
    totale_attivo = D("2000000")
    totale_passivo = D("2000000")
    utile_ce = D("100000")
    sp13 = D("100000")
    plug_residual = D("0")
    hierarchy_differences: dict = {}
    warnings: list = []


def test_payload_carries_critical_accounts_when_a_report_is_given():
    bs = {"_contra_detected": D("2247715.70"), "_contra_applied": D("0"),
          "_contra_reason": "non applicati", "totale_attivo": D("2000000")}
    report = assess(bs, {})
    payload = _validation_report_payload(_FakeQ(), reliability=report)
    assert payload["critical_accounts"]["immobilizzazioni"]["status"] == "unreliable"
    assert payload["critical_accounts"]["all_critical_ok"] is False


def test_payload_omits_critical_accounts_when_no_report_is_given():
    payload = _validation_report_payload(_FakeQ())
    assert "critical_accounts" not in payload


def test_unreliable_immobilizzazioni_blocks_forecastable():
    bs = {"_contra_detected": D("2247715.70"), "_contra_applied": D("0"),
          "_contra_reason": "non applicati", "totale_attivo": D("2000000")}
    report = assess(bs, {})
    forecastable = _FakeQ.semantic_valid and report.all_critical_ok
    assert forecastable is False


def test_clean_sheet_stays_forecastable():
    bs = {"_contra_detected": D("1000"), "_contra_applied": D("1000"),
          "totale_attivo": D("2000000")}
    report = assess(bs, {})
    assert report.all_critical_ok is True
    assert (_FakeQ.semantic_valid and report.all_critical_ok) is True


@pytest.mark.skipif(not os.path.exists(PDF_615), reason="budget_615 corpus PDF not present")
def test_forced_unreliable_verdict_blocks_forecastable_via_the_real_import_path(monkeypatch):
    """Exercises the ACTUAL wiring in importers/pdf_importer.py (the
    `_reliability` / `_critical_ok` / `_forecastable` block that computes and
    persists `FinancialYear.forecastable`), not just the standalone `assess()`
    combination logic the tests above check. Forces reliability.assess to
    return an UNRELIABLE verdict and asserts the real import path (a) still
    saves the record (verdict gates the forecast, never the save) and (b)
    the persisted `forecastable`/`validation_status` reflect the forced verdict.

    Deleting the wiring at importers/pdf_importer.py and reverting to
    `forecastable=_qd.semantic_valid` makes this test fail, because budget_615
    balances cleanly on its own (semantic_valid is True) - see task-5-report.md
    "Fix round 1" for the verbatim before/after run.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from database.db import Base
    from database.models import FinancialYear
    from importers import pdf_importer
    from importers import reliability as reliability_module
    from importers.reliability import AccountStatus, ReliabilityReport

    fake_report = ReliabilityReport(
        immobilizzazioni=AccountStatus.UNRELIABLE,
        immobilizzazioni_reason="forced unreliable for wiring test",
        patrimonio_netto=AccountStatus.DERIVED, patrimonio_netto_reason="n/a",
        debiti_banche=AccountStatus.DERIVED, debiti_banche_reason="n/a",
    )
    monkeypatch.setattr(reliability_module, "assess", lambda *a, **k: fake_report)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr(pdf_importer, "SessionLocal", session_factory)

    result = pdf_importer.import_pdf_balance_sheet(
        file_path=PDF_615, fiscal_year=2024,
        company_name="Wiring test forced-unreliable",
        create_company=True, sector=1, user_id="test-wiring", period_months=12,
    )

    # The verdict never blocks the SAVE - the record must still exist.
    assert result["company_id"] is not None

    # budget_615 balances on its own (semantic_valid would be True); the ONLY
    # thing that can have flipped this to False/review_required is the
    # reliability gate under test.
    assert result["validation_status"] == "review_required"
    assert result["forecastable"] is False
    assert result["validation_report"]["critical_accounts"]["all_critical_ok"] is False

    with session_factory() as db:
        year = db.query(FinancialYear).filter_by(company_id=result["company_id"]).one()
        assert year.forecastable is False
        assert year.validation_status == "review_required"
