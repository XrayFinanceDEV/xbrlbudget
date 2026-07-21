"""Numeric stress across the full 5-year budget cycle."""
from decimal import Decimal

import pytest

from backend.app.api.v1 import budget_scenarios
from backend.app.schemas.budget import BudgetScenarioCreate
from tests.e2e_kit import memory_sessions, read_forecast_maps, seed_base_year

USER = "stress"

STRESS_CASES = [
    pytest.param(Decimal("0.0037"), Decimal("7.35"), id="micro-importi-con-centesimi"),
    # Lieve contrazione che GENERA per tutti i 5 anni (verificato: a -5%/anno i
    # ricavi restano sopra la soglia di cassa e la previsione si genera senza
    # fabbisogno scoperto), così la quadratura esatta e' testata anche sotto un
    # calo dei ricavi che quadra davvero — non solo sotto crescita (i casi -50%
    # sotto asseriscono invece il rifiuto onesto del motore).
    pytest.param(Decimal("1"), Decimal("-5"), id="lieve-contrazione-che-quadra"),
    pytest.param(Decimal("1"), Decimal("-50"), id="dimezzamento-ricavi"),
    pytest.param(Decimal("1"), Decimal("900"), id="crescita-esplosiva-900pct"),
    pytest.param(Decimal("2000000"), Decimal("7.35"), id="scala-miliardi"),
    pytest.param(Decimal("2000000"), Decimal("-50"), id="miliardi-in-contrazione"),
]


@pytest.mark.parametrize("scale,growth", STRESS_CASES)
def test_five_year_budget_stays_exact_to_the_cent(monkeypatch, scale, growth):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER, scale=scale)
            scenario = budget_scenarios.create_budget_scenario(
                company_id,
                BudgetScenarioCreate(company_id=company_id, name=f"stress {scale}x",
                                     base_year=2026, scenario_type="budget"),
                user_id=USER, db=db,
            )
            result = budget_scenarios.bulk_upsert_assumptions(
                company_id, scenario.id,
                request={"assumptions": [
                    {"forecast_year": y, "revenue_growth_pct": float(growth),
                     "tax_rate": 24}
                    for y in range(2027, 2032)
                ], "auto_generate": True},
                user_id=USER, db=db,
            )

            if growth == Decimal("-50"):
                # A -50%/yr revenue collapse does NOT free up cash the way one
                # might naively expect: personnel/depreciation/existing debt
                # service keep draining cash faster than the shrinking working
                # capital release can cover, and the shortfall COMPOUNDS every
                # year as revenue keeps halving (2027 = 50% of base, ...,
                # 2031 = 3.125% of base). Investigated empirically (see
                # task-5-report.md): no single flat financing_amount applied
                # uniformly across all 5 years resolves this — increasing it
                # fixes the earliest failing year but simply hands the binding
                # constraint to a LATER year (whose structural deficit is even
                # bigger, since costs don't shrink at all with revenue absent
                # an explicit cost-side assumption), producing a non-monotonic
                # "whack-a-mole" search with no fixed point at this uniform
                # growth rate. This is the SAME documented, deliberate refusal
                # exercised by tests/test_engine_accounting_invariants.py::
                # test_cash_plug_never_goes_negative (forecast_engine.py "CASH
                # PLUG": "Creating short-term bank debt here used to hide a
                # missing scenario choice") — a 5-year uniform 50%/yr revenue
                # collapse with unchanged cost structure is not, in fact, a
                # fundable going concern without an explicit per-year rescue
                # plan (financing AND cost cuts) that is out of scope for this
                # generic numeric-scale stress case. Assert the honest refusal
                # instead of engineering an artificial financing schedule that
                # would just mask the finding.
                assert result["forecast_generated"] is False
                assert "Unfunded financing requirement" in result["message"], result["message"]
                return

            assert result["forecast_generated"] is True, result["message"]
            rows = read_forecast_maps(db, scenario.id)
            assert len(rows) == 5
            for year, bs, ce in rows:
                # quadratura ESATTA sui Decimal riletti dal DB, anche al 5° anno
                assert bs["_total_assets"] == bs["_total_liabilities"], year
                assert bs["sp09_disponibilita_liquide"] >= 0, year
                # nessun campo fuori dal dominio Numeric(15,2)
                for name, value in {**bs, **ce}.items():
                    assert abs(value) < Decimal("10") ** 13, (year, name, value)
    finally:
        engine.dispose()


def test_zero_revenue_holding_survives_the_cycle(monkeypatch):
    """Ricavi = 0 (holding pura): la derivazione DSO/DIO/DPO non deve dividere
    per zero e la previsione deve comunque quadrare."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER, holding=True)
            scenario = budget_scenarios.create_budget_scenario(
                company_id,
                BudgetScenarioCreate(company_id=company_id, name="holding",
                                     base_year=2026, scenario_type="budget"),
                user_id=USER, db=db,
            )
            result = budget_scenarios.bulk_upsert_assumptions(
                company_id, scenario.id,
                request={"assumptions": [
                    {"forecast_year": 2027, "revenue_growth_pct": 0, "tax_rate": 24},
                    {"forecast_year": 2028, "revenue_growth_pct": 0, "tax_rate": 24},
                ], "auto_generate": True},
                user_id=USER, db=db,
            )
            assert result["forecast_generated"] is True, result["message"]
            for _, bs, ce in read_forecast_maps(db, scenario.id):
                assert bs["_total_assets"] == bs["_total_liabilities"]
                assert ce["ce01_ricavi_vendite"] == 0
    finally:
        engine.dispose()
