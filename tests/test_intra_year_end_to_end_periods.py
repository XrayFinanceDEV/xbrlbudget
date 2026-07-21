from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.services.promote_service import promote_projection_to_financial_year
from calculations.intra_year_engine import IntraYearEngine
from database.db import Base
from database.models import (
    BalanceSheet,
    BudgetAssumptions,
    BudgetScenario,
    Company,
    FinancialYear,
    ForecastYear,
    IncomeStatement,
)


D = Decimal


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


def _add_year(db, company_id, year, period_months, profit):
    fy = FinancialYear(
        company_id=company_id,
        year=year,
        period_months=period_months,
        validation_status="verified",
        forecastable=True,
    )
    db.add(fy)
    db.flush()
    db.add(BalanceSheet(
        financial_year_id=fy.id,
        sp09_disponibilita_liquide=D("1000") + profit,
        sp11_capitale=D("1000"),
        sp13_utile_perdita=profit,
    ))
    db.add(IncomeStatement(
        financial_year_id=fy.id,
        ce01_ricavi_vendite=profit,
    ))
    db.flush()
    return fy


@pytest.mark.parametrize("period_months", [3, 6, 9, 12])
def test_generate_validate_and_promote_for_supported_periods(db_session, period_months):
    company = Company(name=f"E2E {period_months}M", tax_id=f"E2E-{period_months}", sector=1)
    db_session.add(company)
    db_session.flush()
    _add_year(db_session, company.id, 2024, None, D("0"))
    _add_year(
        db_session,
        company.id,
        2025,
        None if period_months == 12 else period_months,
        D("100"),
    )
    scenario = BudgetScenario(
        company_id=company.id,
        name=f"Infrannuale {period_months}M",
        base_year=2024,
        scenario_type="infrannuale",
        period_months=period_months,
    )
    db_session.add(scenario)
    db_session.flush()
    db_session.add(BudgetAssumptions(
        scenario_id=scenario.id,
        forecast_year=2025,
        tax_rate=D("0"),
        fixed_materials_percentage=D("0"),
        fixed_services_percentage=D("0"),
        ce01_override=D("555"),
        sp_overrides={"sp11_capitale": 1200},
    ))
    db_session.commit()

    generated = IntraYearEngine(db_session).generate_projection(scenario.id)
    assert generated["success"] is True
    forecast = db_session.query(ForecastYear).filter(
        ForecastYear.scenario_id == scenario.id
    ).one()
    assert forecast.balance_sheet.total_assets == forecast.balance_sheet.total_liabilities

    promoted = promote_projection_to_financial_year(db_session, scenario.id)
    assert promoted["verification"]["exact_match"] is True
    assert promoted["verification"]["semantic_valid"] is True
    copied = db_session.query(FinancialYear).filter(
        FinancialYear.id == promoted["financial_year_id"]
    ).one()
    assert copied.period_months is None
    assert copied.balance_sheet.sp09_disponibilita_liquide == forecast.balance_sheet.sp09_disponibilita_liquide
    assert copied.balance_sheet.sp11_capitale == D("1200")
    assert copied.income_statement.ce01_ricavi_vendite == forecast.income_statement.ce01_ricavi_vendite
    assert copied.income_statement.ce01_ricavi_vendite == D("555")
