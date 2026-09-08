"""compute_forecast: parita' col previsionale persistito, e `details` dichiarati.

Il motore budget e' separato in lettura (`load_forecast_source`), calcolo puro
(`ForecastEngine.compute_forecast`) e persistenza (`generate_forecast`). Queste
prove fissano le due cose che la separazione non deve rompere: il previsionale
salvato resta identico al centesimo, e ogni anno calcolato porta i sette
`details` dichiarati.
"""
from decimal import Decimal

from backend.app.api.v1 import budget_scenarios
from backend.app.schemas.budget import BudgetScenarioCreate
from calculations.forecast_engine import ForecastEngine, load_forecast_source
from database import models
from tests.e2e_kit import memory_sessions, read_forecast_maps, seed_base_year

USER = "compute"


def _scenario(db, company_id, extra):
    sc = budget_scenarios.create_budget_scenario(
        company_id,
        BudgetScenarioCreate(company_id=company_id, name="c", base_year=2026, scenario_type="budget"),
        user_id=USER, db=db,
    )
    rows = [dict(forecast_year=y, **extra) for y in (2027, 2028, 2029)]
    res = budget_scenarios.bulk_upsert_assumptions(
        company_id, sc.id, request={"assumptions": rows, "auto_generate": True}, user_id=USER, db=db,
    )
    assert res["forecast_generated"] is True, res["message"]
    return sc


def test_compute_matches_persisted_forecast_to_the_cent(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            sc = _scenario(db, company_id, {"revenue_growth_pct": 5, "tangible_investments": 10000})
            persisted = read_forecast_maps(db, sc.id)
            source = load_forecast_source(db, sc.id)
            rows = (db.query(models.BudgetAssumptions)
                      .filter(models.BudgetAssumptions.scenario_id == sc.id)
                      .order_by(models.BudgetAssumptions.forecast_year).all())
            comp = ForecastEngine(db).compute_forecast(source, rows)
            assert comp.error is None
            assert [y.year for y in comp.years] == [y for y, _, _ in persisted]
            for computed, (_, bs, ce) in zip(comp.years, persisted):
                for k, v in computed.balance_sheet.items():
                    assert Decimal(str(v)).quantize(Decimal("0.01")) == bs[k], k
                for k, v in computed.income_statement.items():
                    assert Decimal(str(v)).quantize(Decimal("0.01")) == ce[k], k
    finally:
        engine.dispose()


def test_details_are_declared_and_sum_to_the_line(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            sc = _scenario(db, company_id, {"fixed_materials_percentage": 30,
                                            "variable_materials_growth_pct": 10,
                                            "fixed_materials_growth_pct": 2})
            source = load_forecast_source(db, sc.id)
            rows = (db.query(models.BudgetAssumptions)
                      .filter(models.BudgetAssumptions.scenario_id == sc.id)
                      .order_by(models.BudgetAssumptions.forecast_year).all())
            comp = ForecastEngine(db).compute_forecast(source, rows)
            for y in comp.years:
                d = y.details
                for key in ("ce05_fixed", "ce05_variable", "ce06_fixed", "ce06_variable",
                            "dso_applied", "dio_applied", "dpo_applied"):
                    assert key in d, key
                assert (d["ce05_fixed"] + d["ce05_variable"]).quantize(Decimal("0.01")) == \
                    y.income_statement["ce05_materie_prime"].quantize(Decimal("0.01"))
            # anno 1: 200.000 base -> 30% fisso +2%, 70% variabile +10%
            assert comp.years[0].details["ce05_fixed"] == Decimal("61200.00")
            assert comp.years[0].details["ce05_variable"] == Decimal("154000.00")
    finally:
        engine.dispose()


def test_override_blanks_the_split_and_stop_on_error_false_keeps_partial_years(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            sc = _scenario(db, company_id, {"ce05_override": 150000})
            source = load_forecast_source(db, sc.id)
            rows = (db.query(models.BudgetAssumptions)
                      .filter(models.BudgetAssumptions.scenario_id == sc.id)
                      .order_by(models.BudgetAssumptions.forecast_year).all())
            comp = ForecastEngine(db).compute_forecast(source, rows)
            assert comp.years[0].details["ce05_fixed"] is None
            assert comp.years[0].details["ce05_variable"] is None
            # investimenti fuori scala nel 2028: l'anno 2027 resta, 2028 e' l'errore
            rows[1].tangible_investments = Decimal("5000000")
            partial = ForecastEngine(db).compute_forecast(source, rows, stop_on_error=False)
            assert [y.year for y in partial.years] == [2027]
            assert partial.error.year == 2028
            assert "Unfunded financing requirement" in partial.error.message
    finally:
        engine.dispose()
