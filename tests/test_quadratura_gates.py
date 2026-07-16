"""Tests for the quadratura gates added by the 2026-07-15 audit:

- backend PUT /adjustments server-side balance validation (_bs_imbalance + rule)
- promote_service quadratura gate (_forecast_bs_imbalance)
- CSV / XBRL import quadratura warnings (check_quadratura plumbing on dicts)

Run: python -m pytest tests/test_quadratura_gates.py -v
"""
import os
import sys
from decimal import Decimal

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "backend"))

D = Decimal


# ------------------------------------------------------------- _bs_imbalance

def _bal(att_cash, capitale):
    return {"sp09_disponibilita_liquide": att_cash, "sp11_capitale": capitale}


def test_bs_imbalance_zero_on_balanced_dict():
    from app.api.v1.financial_years import _bs_imbalance
    assert _bs_imbalance(_bal(1000, 1000)) == D("0")


def test_bs_imbalance_measures_gap_and_ignores_missing_fields():
    from app.api.v1.financial_years import _bs_imbalance
    assert _bs_imbalance(_bal(1500, 1000)) == D("500")
    assert _bs_imbalance({}) == D("0")
    # None fields count as 0, not crash
    assert _bs_imbalance({"sp09_disponibilita_liquide": None,
                          "sp11_capitale": 100}) == D("100")


def test_adjustments_rule_rejects_worsening_allows_preexisting():
    # the endpoint rule: reject when new > cur + TOL. Reproduce it here on the
    # helper so the arithmetic contract is pinned.
    from app.api.v1.financial_years import _bs_imbalance, ADJUSTMENTS_BALANCE_TOL
    current = _bal(1000, 1000)              # balanced record
    unbalanced_edit = _bal(2000, 1000)      # +1000 only on the attivo side
    assert _bs_imbalance(unbalanced_edit) > _bs_imbalance(current) + ADJUSTMENTS_BALANCE_TOL
    # a record ALREADY unbalanced at import: a double-entry edit keeps the gap
    # constant -> allowed (new == cur, not worse)
    cur_unbal = _bal(1300, 1000)
    edited = {"sp09_disponibilita_liquide": 1200, "sp06_crediti_breve": 100,
              "sp11_capitale": 1000}
    assert _bs_imbalance(edited) <= _bs_imbalance(cur_unbal) + ADJUSTMENTS_BALANCE_TOL


# ----------------------------------------------------- promote quadratura gate

def test_forecast_bs_imbalance_balanced_and_unbalanced():
    from app.services.promote_service import _forecast_bs_imbalance
    from database.models import ForecastBalanceSheet
    ok = ForecastBalanceSheet(sp09_disponibilita_liquide=D("500"),
                              sp11_capitale=D("300"), sp13_utile_perdita=D("200"))
    assert _forecast_bs_imbalance(ok) == D("0")
    bad = ForecastBalanceSheet(sp09_disponibilita_liquide=D("500"),
                               sp11_capitale=D("300"))
    assert _forecast_bs_imbalance(bad) == D("200")


def test_promote_raises_on_unbalanced_projection(monkeypatch):
    # exercise the gate through promote_projection_to_financial_year with stubbed
    # DB queries: scenario + forecast year present, BS unbalanced by 200.
    from app.services import promote_service as ps
    from database.models import ForecastBalanceSheet, ForecastIncomeStatement

    class _FY:
        year = 2026
        balance_sheet = ForecastBalanceSheet(sp09_disponibilita_liquide=D("500"),
                                             sp11_capitale=D("300"))
        income_statement = ForecastIncomeStatement()

    class _Scenario:
        id = 1
        scenario_type = "infrannuale"
        company_id = 7

    class _Query:
        def __init__(self, obj):
            self._obj = obj
        def filter(self, *a, **k):
            return self
        def first(self):
            return self._obj

    class _DB:
        def query(self, model):
            name = getattr(model, "__name__", "")
            if name == "BudgetScenario":
                return _Query(_Scenario())
            if name == "ForecastYear":
                return _Query(_FY())
            return _Query(None)

    with pytest.raises(ValueError, match="non quadra"):
        ps.promote_projection_to_financial_year(_DB(), 1)


# --------------------------------------------- check_quadratura on import dicts

def test_check_quadratura_flags_unbalanced_dict():
    # the exact call now made by the XBRL/CSV import paths
    from importers.iv_cee_hierarchy import check_quadratura
    bs = {"sp09_disponibilita_liquide": D("1000"), "sp11_capitale": D("400")}
    q = check_quadratura(bs, None)
    assert not q.quadra
    assert any("BILANCIO NON QUADRATO" in w for w in q.warnings)


def test_check_quadratura_passes_balanced_dict():
    from importers.iv_cee_hierarchy import check_quadratura
    bs = {"sp09_disponibilita_liquide": D("1000"), "sp11_capitale": D("1000")}
    q = check_quadratura(bs, None)
    assert q.quadra and not q.warnings
