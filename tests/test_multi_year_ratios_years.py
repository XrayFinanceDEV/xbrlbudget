"""La colonna di un anno compare una volta sola nella tabella indici.

Un anno promosso (proiezione infrannuale copiata su FinancialYear) esiste sia
come anno storico sia come anno di previsione dello scenario che lo ha
generato. `calculate_ratios_historical_and_forecast` prendeva TUTTI gli anni
storici a pieno periodo, ignorando il `base_year` che pure riceve: il 2026
finiva due volte nella lista `years` e il frontend rendeva due colonne con la
stessa chiave React.
"""
import os
import sys
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import backend.app.main  # noqa: F401,E402  — inserisce la project root in sys.path
from database.db import Base  # noqa: E402
from database.models import (  # noqa: E402
    BalanceSheet,
    BudgetScenario,
    Company,
    FinancialYear,
    ForecastBalanceSheet,
    ForecastIncomeStatement,
    ForecastYear,
    IncomeStatement,
)
from backend.app.services import calculation_service  # noqa: E402

D = Decimal


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _bs(**kw):
    return BalanceSheet(
        sp09_disponibilita_liquide=D("1000"),
        sp11_capitale=D("1000"),
        **kw,
    )


def _is(**kw):
    return IncomeStatement(ce01_ricavi_vendite=D("5000"), **kw)


def _forecast_bs(**kw):
    return ForecastBalanceSheet(
        sp09_disponibilita_liquide=D("1000"),
        sp11_capitale=D("1000"),
        **kw,
    )


def _forecast_is(**kw):
    return ForecastIncomeStatement(ce01_ricavi_vendite=D("5000"), **kw)


def _company_with_promoted_year(db):
    """2023-2025 storici, 2026 promosso, scenario base 2025 con previsione 2026-2028."""
    company = Company(name="Promossa S.r.l.", tax_id="00000000001", sector=1,
                      user_id="test-user")
    db.add(company)
    db.flush()

    for year in (2023, 2024, 2025, 2026):
        fy = FinancialYear(company_id=company.id, year=year, period_months=None)
        fy.balance_sheet = _bs()
        fy.income_statement = _is()
        db.add(fy)

    scenario = BudgetScenario(company_id=company.id, name="Budget 2026-2028",
                              base_year=2025, scenario_type="budget")
    db.add(scenario)
    db.flush()

    for year in (2026, 2027, 2028):
        fcy = ForecastYear(scenario_id=scenario.id, year=year)
        fcy.balance_sheet = _forecast_bs()
        fcy.income_statement = _forecast_is()
        db.add(fcy)

    db.commit()
    return company, scenario


def test_no_duplicate_year_columns(db):
    company, scenario = _company_with_promoted_year(db)

    result = calculation_service.calculate_ratios_historical_and_forecast(
        db=db, company_id=company.id, scenario_id=scenario.id,
        base_year=scenario.base_year,
    )

    years = result["years"]
    assert len(years) == len(set(years)), f"anni duplicati: {years}"


def test_historical_stops_at_base_year_and_forecast_continues(db):
    company, scenario = _company_with_promoted_year(db)

    result = calculation_service.calculate_ratios_historical_and_forecast(
        db=db, company_id=company.id, scenario_id=scenario.id,
        base_year=scenario.base_year,
    )

    # Il 2026 c'è, ma è quello dello SCENARIO: l'anno promosso non lo raddoppia.
    assert result["years"] == [2023, 2024, 2025, 2026, 2027, 2028]
    assert len(result["ratios"]) == len(result["years"])
