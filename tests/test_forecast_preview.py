from decimal import Decimal

import pytest
from fastapi import HTTPException

from backend.app.api.v1 import budget_scenarios
from backend.app.schemas.budget import BudgetScenarioCreate
from database import models
from tests.e2e_kit import memory_sessions, read_forecast_maps, seed_base_year

USER = "preview"


def _saved_scenario(db, company_id):
    sc = budget_scenarios.create_budget_scenario(
        company_id, BudgetScenarioCreate(company_id=company_id, name="p", base_year=2026, scenario_type="budget"),
        user_id=USER, db=db)
    rows = [{"forecast_year": y, "revenue_growth_pct": 5} for y in (2027, 2028)]
    res = budget_scenarios.bulk_upsert_assumptions(
        company_id, sc.id, request={"assumptions": rows, "auto_generate": True}, user_id=USER, db=db)
    assert res["forecast_generated"] is True
    return sc, rows


def _counts(db):
    return tuple(db.query(m).count() for m in (
        models.BudgetAssumptions, models.ForecastYear, models.ForecastBalanceSheet, models.ForecastIncomeStatement))


def test_preview_of_saved_rows_equals_persisted_and_writes_nothing(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            sc, rows = _saved_scenario(db, company_id)
            before = _counts(db)
            saved_pct = [a.revenue_growth_pct for a in db.query(models.BudgetAssumptions).order_by(models.BudgetAssumptions.forecast_year)]
            out = budget_scenarios.preview_forecast_route(
                company_id, sc.id, request={"assumptions": [dict(r, revenue_growth_pct=40) for r in rows]},
                user_id=USER, db=db)
            assert out["error"] is None
            assert [y["year"] for y in out["forecast_years"]] == [2027, 2028]
            assert _counts(db) == before
            assert [a.revenue_growth_pct for a in db.query(models.BudgetAssumptions).order_by(models.BudgetAssumptions.forecast_year)] == saved_pct
            # con le righe salvate, l'anteprima coincide col persistito
            same = budget_scenarios.preview_forecast_route(
                company_id, sc.id, request={"assumptions": rows}, user_id=USER, db=db)
            for y, (_, bs, ce) in zip(same["forecast_years"], read_forecast_maps(db, sc.id)):
                assert Decimal(str(y["balance_sheet"]["sp09_disponibilita_liquide"])) == bs["sp09_disponibilita_liquide"]
                assert Decimal(str(y["income_statement"]["ce01_ricavi_vendite"])) == ce["ce01_ricavi_vendite"]
            for key in ("ce05_fixed", "ce05_variable", "ce06_fixed", "ce06_variable", "dso_applied", "dio_applied", "dpo_applied"):
                assert key in same["forecast_years"][0]["details"]
    finally:
        engine.dispose()


def test_unfunded_requirement_returns_200_with_partial_years(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            sc, rows = _saved_scenario(db, company_id)
            rows[1]["tangible_investments"] = 5_000_000
            out = budget_scenarios.preview_forecast_route(
                company_id, sc.id, request={"assumptions": rows}, user_id=USER, db=db)
            assert [y["year"] for y in out["forecast_years"]] == [2027]
            assert out["error"]["year"] == 2028
            assert "Unfunded financing requirement" in out["error"]["message"]
    finally:
        engine.dispose()


def test_bad_input_is_400_and_foreign_scenario_is_404(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            sc, rows = _saved_scenario(db, company_id)
            with pytest.raises(HTTPException) as e:
                budget_scenarios.preview_forecast_route(
                    company_id, sc.id, request={"assumptions": [{"forecast_year": 2026}]}, user_id=USER, db=db)
            assert e.value.status_code == 400
            with pytest.raises(HTTPException) as e:
                budget_scenarios.preview_forecast_route(
                    company_id, sc.id, request={"assumptions": rows}, user_id="someone-else", db=db)
            assert e.value.status_code == 404
    finally:
        engine.dispose()
