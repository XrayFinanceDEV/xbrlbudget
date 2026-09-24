from fastapi import HTTPException
import pytest

from backend.app.api.v1.companies import get_existing_balances
from backend.app.api.v1.budget_scenarios import create_budget_scenario
from backend.app.schemas.budget import BudgetScenarioCreate
from database.models import BalanceSheet, FinancialYear, IncomeStatement
from tests.e2e_kit import memory_sessions, seed_base_year


def test_existing_balances_lists_exact_complete_periods_and_scopes_company():
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id="home-balances", year=2026)
            partial = FinancialYear(company_id=company_id, year=2026, period_months=6)
            incomplete = FinancialYear(company_id=company_id, year=2024, period_months=None)
            db.add_all([partial, incomplete])
            db.flush()
            db.add(BalanceSheet(financial_year_id=partial.id))
            db.add(IncomeStatement(financial_year_id=partial.id))
            db.add(BalanceSheet(financial_year_id=incomplete.id))
            db.commit()

            options = get_existing_balances(company_id, user_id="home-balances", db=db)
            assert {(o.year, o.period_months) for o in options} == {(2026, None), (2026, 6)}
            first = create_budget_scenario(company_id, BudgetScenarioCreate(
                company_id=company_id, name="Proiezione 1", base_year=2025,
                scenario_type="infrannuale", period_months=6,
            ), user_id="home-balances", db=db)
            second = create_budget_scenario(company_id, BudgetScenarioCreate(
                company_id=company_id, name="Proiezione 2", base_year=2025,
                scenario_type="infrannuale", period_months=6,
            ), user_id="home-balances", db=db)
            assert first.id != second.id
            with pytest.raises(HTTPException) as denied:
                get_existing_balances(company_id, user_id="someone-else", db=db)
            assert denied.value.status_code == 404
    finally:
        engine.dispose()
