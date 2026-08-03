"""The reliability verdict gates the FORECAST, never the SAVE.

An unreliable file must still be persisted: Rettifiche operates on a saved
FinancialYear, so refusing to save would make the file uncorrectable.
"""
import os
import sys
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from importers.pdf_importer import _validation_report_payload  # noqa: E402
from importers.reliability import AccountStatus, assess        # noqa: E402

D = Decimal


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
