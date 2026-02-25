"""
Promote Service — copies an infrannuale projection (ForecastYear)
into a proper FinancialYear so it can serve as base year for budget scenarios.
"""
from decimal import Decimal
from sqlalchemy.orm import Session

from database.models import (
    BudgetScenario, ForecastYear,
    FinancialYear, BalanceSheet, IncomeStatement,
    ForecastBalanceSheet, ForecastIncomeStatement,
)


def promote_projection_to_financial_year(db: Session, scenario_id: int) -> dict:
    """
    Copy the single ForecastYear of an infrannuale scenario into a new
    FinancialYear(period_months=None) record.

    Returns dict with {success, financial_year_id, year, company_id, message}.
    Raises ValueError on validation errors.
    """
    # 1. Validate scenario
    scenario = db.query(BudgetScenario).filter(
        BudgetScenario.id == scenario_id
    ).first()
    if not scenario:
        raise ValueError(f"Scenario {scenario_id} not found")

    if scenario.scenario_type != "infrannuale":
        raise ValueError("Only infrannuale scenarios can be promoted")

    # 2. Find the ForecastYear
    forecast_year = db.query(ForecastYear).filter(
        ForecastYear.scenario_id == scenario_id
    ).first()
    if not forecast_year:
        raise ValueError("No projection found — run the projection first")
    if not forecast_year.balance_sheet or not forecast_year.income_statement:
        raise ValueError("Projection is incomplete (missing BS or IS)")

    target_year = forecast_year.year
    company_id = scenario.company_id

    # 3. Replace existing full-year FinancialYear if present (re-promote)
    existing = db.query(FinancialYear).filter(
        FinancialYear.company_id == company_id,
        FinancialYear.year == target_year,
        FinancialYear.period_months.is_(None),
    ).first()
    if existing:
        db.delete(existing)  # cascade removes BS + IS
        db.flush()

    # 4. Create new FinancialYear (full-year)
    new_fy = FinancialYear(
        company_id=company_id,
        year=target_year,
        period_months=None,
    )
    db.add(new_fy)
    db.flush()  # get new_fy.id

    # 5. Copy balance sheet columns
    new_bs = _copy_columns(
        forecast_year.balance_sheet,
        ForecastBalanceSheet, BalanceSheet,
        id_field="financial_year_id", id_value=new_fy.id,
    )
    db.add(new_bs)

    # 6. Copy income statement columns
    new_is = _copy_columns(
        forecast_year.income_statement,
        ForecastIncomeStatement, IncomeStatement,
        id_field="financial_year_id", id_value=new_fy.id,
    )
    db.add(new_is)

    db.commit()

    return {
        "success": True,
        "financial_year_id": new_fy.id,
        "year": target_year,
        "company_id": company_id,
        "message": f"Projection {target_year} promoted to full-year financial data",
    }


def _copy_columns(source, source_model, target_model, *, id_field: str, id_value: int):
    """
    Copy all shared Numeric columns from source ORM object to a new target ORM instance.
    Uses column intersection so missing columns (e.g. ce09d only in IS) default to 0.
    """
    source_cols = {c.name for c in source_model.__table__.columns}
    target_cols = {c.name for c in target_model.__table__.columns}
    shared = source_cols & target_cols

    # Exclude metadata / pk / fk columns
    skip = {"id", "created_at", "updated_at", "financial_year_id", "forecast_year_id"}
    kwargs = {id_field: id_value}

    for col_name in shared - skip:
        value = getattr(source, col_name, None)
        if value is not None:
            kwargs[col_name] = value

    return target_model(**kwargs)
