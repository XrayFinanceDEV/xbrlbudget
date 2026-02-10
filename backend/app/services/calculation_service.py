"""
Calculation Service - Business logic layer for financial calculations
"""
from typing import Optional
from sqlalchemy.orm import Session
import sys
import os

# Add backend directory to Python path
backend_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from database import models
from calculations.ratios import FinancialRatiosCalculator
from calculations.altman import AltmanCalculator
from calculations.rating_fgpmi import FGPMICalculator
from app.calculations.cashflow import CashFlowCalculator
from app.calculations.cashflow_detailed import DetailedCashFlowCalculator
from app.schemas import calculations as calc_schemas
from app.schemas.cashflow_detailed import DetailedCashFlowStatement, MultiYearDetailedCashFlow
from decimal import Decimal


def _convert_namedtuple_to_dict(nt):
    """Convert NamedTuple to dictionary with appropriate types"""
    if nt is None:
        return None
    result = {}
    for key, value in nt._asdict().items():
        if hasattr(value, '_asdict'):  # Nested NamedTuple
            result[key] = _convert_namedtuple_to_dict(value)
        elif isinstance(value, (int, str, bool)):  # Keep as-is
            result[key] = value
        elif value is not None:  # Convert Decimal to float
            try:
                result[key] = float(value)
            except (ValueError, TypeError):
                result[key] = value  # Keep original if conversion fails
        else:
            result[key] = 0.0
    return result


def get_financial_year_with_statements(
    db: Session,
    company_id: int,
    year: int
) -> tuple[models.Company, models.FinancialYear, models.BalanceSheet, models.IncomeStatement]:
    """
    Get company, financial year, and both financial statements

    Returns:
        Tuple of (Company, FinancialYear, BalanceSheet, IncomeStatement)

    Raises:
        ValueError: If any required data is missing
    """
    # Get financial year with company
    fy = db.query(models.FinancialYear).filter(
        models.FinancialYear.company_id == company_id,
        models.FinancialYear.year == year
    ).first()

    if not fy:
        raise ValueError(f"Financial year {year} for company {company_id} not found")

    # Get company
    company = fy.company
    if not company:
        raise ValueError(f"Company {company_id} not found")

    # Check balance sheet exists
    if not fy.balance_sheet:
        raise ValueError(f"Balance sheet for year {year} not found")

    # Check income statement exists
    if not fy.income_statement:
        raise ValueError(f"Income statement for year {year} not found")

    return company, fy, fy.balance_sheet, fy.income_statement


def calculate_all_ratios(
    db: Session,
    company_id: int,
    year: int
) -> calc_schemas.AllRatios:
    """
    Calculate all financial ratios for a specific year

    Args:
        db: Database session
        company_id: Company ID
        year: Financial year

    Returns:
        AllRatios schema with all ratio categories
    """
    company, fy, bs, inc = get_financial_year_with_statements(db, company_id, year)

    # Initialize calculator
    calc = FinancialRatiosCalculator(bs, inc)

    # Calculate each category
    wc = calc.calculate_working_capital_metrics()
    liquidity = calc.calculate_liquidity_ratios()
    solvency = calc.calculate_solvency_ratios()
    profitability = calc.calculate_profitability_ratios()
    activity = calc.calculate_activity_ratios()
    coverage = calc.calculate_coverage_ratios()
    turnover = calc.calculate_turnover_ratios()
    extended_profitability = calc.calculate_extended_profitability_ratios()
    efficiency = calc.calculate_efficiency_ratios()
    break_even = calc.calculate_break_even_analysis()

    # Convert to Pydantic models
    return calc_schemas.AllRatios(
        working_capital=calc_schemas.WorkingCapitalMetrics(**_convert_namedtuple_to_dict(wc)),
        liquidity=calc_schemas.LiquidityRatios(**_convert_namedtuple_to_dict(liquidity)),
        solvency=calc_schemas.SolvencyRatios(**_convert_namedtuple_to_dict(solvency)),
        profitability=calc_schemas.ProfitabilityRatios(**_convert_namedtuple_to_dict(profitability)),
        activity=calc_schemas.ActivityRatios(**_convert_namedtuple_to_dict(activity)),
        coverage=calc_schemas.CoverageRatios(**_convert_namedtuple_to_dict(coverage)),
        turnover=calc_schemas.TurnoverRatios(**_convert_namedtuple_to_dict(turnover)),
        extended_profitability=calc_schemas.ExtendedProfitabilityRatios(**_convert_namedtuple_to_dict(extended_profitability)),
        efficiency=calc_schemas.EfficiencyRatios(**_convert_namedtuple_to_dict(efficiency)),
        break_even=calc_schemas.BreakEvenAnalysis(**_convert_namedtuple_to_dict(break_even))
    )


def calculate_summary_metrics(
    db: Session,
    company_id: int,
    year: int
) -> calc_schemas.SummaryMetrics:
    """
    Calculate summary financial metrics

    Args:
        db: Database session
        company_id: Company ID
        year: Financial year

    Returns:
        SummaryMetrics schema
    """
    company, fy, bs, inc = get_financial_year_with_statements(db, company_id, year)

    # Initialize calculator
    calc = FinancialRatiosCalculator(bs, inc)

    # Get summary dict
    summary = calc.get_summary_metrics()

    # Convert Decimals to floats
    summary_dict = {k: float(v) if v is not None else 0.0 for k, v in summary.items()}

    return calc_schemas.SummaryMetrics(**summary_dict)


def calculate_altman_zscore(
    db: Session,
    company_id: int,
    year: int
) -> calc_schemas.AltmanResult:
    """
    Calculate Altman Z-Score for bankruptcy prediction

    Args:
        db: Database session
        company_id: Company ID
        year: Financial year

    Returns:
        AltmanResult schema
    """
    company, fy, bs, inc = get_financial_year_with_statements(db, company_id, year)

    # Initialize calculator with sector
    calc = AltmanCalculator(bs, inc, company.sector)

    # Calculate Z-Score
    result = calc.calculate()

    # Convert NamedTuple to dict
    result_dict = _convert_namedtuple_to_dict(result)

    return calc_schemas.AltmanResult(**result_dict)


def calculate_fgpmi_rating(
    db: Session,
    company_id: int,
    year: int
) -> calc_schemas.FGPMIResult:
    """
    Calculate FGPMI credit rating

    Args:
        db: Database session
        company_id: Company ID
        year: Financial year

    Returns:
        FGPMIResult schema
    """
    company, fy, bs, inc = get_financial_year_with_statements(db, company_id, year)

    # Initialize calculator with sector
    calc = FGPMICalculator(bs, inc, company.sector)

    # Calculate rating
    result = calc.calculate()

    # Convert NamedTuple to dict
    result_dict = _convert_namedtuple_to_dict(result)

    # Convert indicator scores
    if 'indicators' in result_dict and result_dict['indicators']:
        indicators_dict = {}
        for key, indicator in result_dict['indicators'].items():
            indicators_dict[key] = calc_schemas.IndicatorScore(**_convert_namedtuple_to_dict(indicator))
        result_dict['indicators'] = indicators_dict

    return calc_schemas.FGPMIResult(**result_dict)


def calculate_complete_analysis(
    db: Session,
    company_id: int,
    year: int
) -> calc_schemas.FinancialAnalysis:
    """
    Calculate complete financial analysis (ratios + Altman + FGPMI)

    Args:
        db: Database session
        company_id: Company ID
        year: Financial year

    Returns:
        FinancialAnalysis schema with all calculations
    """
    company, fy, bs, inc = get_financial_year_with_statements(db, company_id, year)

    # Calculate all components
    ratios = calculate_all_ratios(db, company_id, year)
    summary = calculate_summary_metrics(db, company_id, year)
    altman = calculate_altman_zscore(db, company_id, year)
    fgpmi = calculate_fgpmi_rating(db, company_id, year)

    return calc_schemas.FinancialAnalysis(
        company_id=company_id,
        year=year,
        sector=company.sector,
        ratios=ratios,
        altman=altman,
        fgpmi=fgpmi,
        summary=summary
    )


def calculate_cashflow(
    db: Session,
    company_id: int,
    year: int
) -> calc_schemas.CashFlowResult:
    """
    Calculate cash flow statement for a specific year using indirect method

    Args:
        db: Database session
        company_id: Company ID
        year: Financial year

    Returns:
        CashFlowResult schema with all components and ratios
    """
    # Get current year data
    company, fy, bs_current, inc_current = get_financial_year_with_statements(db, company_id, year)

    # Try to get previous year
    fy_previous = db.query(models.FinancialYear).filter(
        models.FinancialYear.company_id == company_id,
        models.FinancialYear.year == year - 1
    ).first()

    bs_previous = fy_previous.balance_sheet if fy_previous else None

    # Calculate EBITDA from income statement
    ebitda = Decimal(str(inc_current.ebitda))

    # Calculate cash flow
    result = CashFlowCalculator.calculate(bs_current, bs_previous, inc_current, ebitda)

    # Convert NamedTuple to dict
    result_dict = _convert_namedtuple_to_dict(result)

    return calc_schemas.CashFlowResult(**result_dict)


def calculate_cashflow_multi_year(
    db: Session,
    company_id: int
) -> list[calc_schemas.CashFlowResult]:
    """
    Calculate cash flow statements for all available years

    Args:
        db: Database session
        company_id: Company ID

    Returns:
        List of CashFlowResult schemas, one per year (sorted by year)
    """
    # Get all financial years for company
    financial_years = db.query(models.FinancialYear).filter(
        models.FinancialYear.company_id == company_id
    ).order_by(models.FinancialYear.year).all()

    if len(financial_years) < 2:
        raise ValueError("At least 2 years of data required for cash flow analysis")

    results = []

    for i, fy in enumerate(financial_years):
        # Skip if missing statements
        if not fy.balance_sheet or not fy.income_statement:
            continue

        # Get previous year (None for first year)
        bs_previous = None
        if i > 0:
            fy_prev = financial_years[i-1]
            if fy_prev.balance_sheet:
                bs_previous = fy_prev.balance_sheet

        # Calculate cash flow
        ebitda = Decimal(str(fy.income_statement.ebitda))
        result = CashFlowCalculator.calculate(
            fy.balance_sheet,
            bs_previous,
            fy.income_statement,
            ebitda
        )

        # Convert to schema
        result_dict = _convert_namedtuple_to_dict(result)
        results.append(calc_schemas.CashFlowResult(**result_dict))

    return results


def calculate_detailed_cashflow_historical_and_forecast(
    db: Session,
    company_id: int,
    scenario_id: int,
    base_year: int
) -> MultiYearDetailedCashFlow:
    """
    Calculate detailed cash flow for base year (historical) and forecast years

    Timeline: (base_year-1) & base_year -> cashflow for base_year (2024)
              base_year & forecast_years -> cashflows for forecasts (2025, 2026, 2027)

    Example: base_year=2024
        - Calculates cashflow FOR 2024 using (2023, 2024) balance sheets
        - Calculates cashflow FOR 2025 using (2024, 2025_forecast) balance sheets
        - Calculates cashflow FOR 2026 using (2025_forecast, 2026_forecast) balance sheets
        - Calculates cashflow FOR 2027 using (2026_forecast, 2027_forecast) balance sheets

    Args:
        db: Database session
        company_id: Company ID
        scenario_id: Budget scenario ID
        base_year: Last historical year (e.g., 2024)

    Returns:
        MultiYearDetailedCashFlow with base year + forecast cashflows
    """
    from database.models import BudgetScenario, ForecastYear

    # Get scenario
    scenario = db.query(BudgetScenario).filter(
        BudgetScenario.id == scenario_id,
        BudgetScenario.company_id == company_id
    ).first()

    if not scenario:
        raise ValueError(f"Scenario {scenario_id} not found for company {company_id}")

    if scenario.base_year != base_year:
        raise ValueError(f"Scenario base year {scenario.base_year} does not match requested base year {base_year}")

    # Get base year financial statements (last historical year)
    fy_base = db.query(models.FinancialYear).filter(
        models.FinancialYear.company_id == company_id,
        models.FinancialYear.year == base_year
    ).first()

    if not fy_base or not fy_base.balance_sheet or not fy_base.income_statement:
        raise ValueError(f"Base year {base_year} missing financial statements")

    # Get previous year (base_year - 1) for calculating base year cashflow
    fy_previous = db.query(models.FinancialYear).filter(
        models.FinancialYear.company_id == company_id,
        models.FinancialYear.year == base_year - 1
    ).first()

    cashflows = []

    # Calculate cashflow FOR base year (using base_year-1 and base_year)
    if fy_previous and fy_previous.balance_sheet:
        base_year_cf = DetailedCashFlowCalculator.calculate(
            bs_current=fy_base.balance_sheet,
            bs_previous=fy_previous.balance_sheet,
            inc_current=fy_base.income_statement,
            year=base_year
        )
        cashflows.append(base_year_cf)

    # Get forecast years
    forecast_years = db.query(ForecastYear).filter(
        ForecastYear.scenario_id == scenario_id
    ).order_by(ForecastYear.year).all()

    if not forecast_years:
        raise ValueError(f"No forecast years found for scenario {scenario_id}")

    # Calculate forecast cashflows (using base year as starting point)
    previous_bs = fy_base.balance_sheet

    for forecast_year in forecast_years:
        if not forecast_year.balance_sheet or not forecast_year.income_statement:
            continue

        forecast_cf = DetailedCashFlowCalculator.calculate(
            bs_current=forecast_year.balance_sheet,
            bs_previous=previous_bs,
            inc_current=forecast_year.income_statement,
            year=forecast_year.year
        )
        cashflows.append(forecast_cf)

        # Update previous for next iteration
        previous_bs = forecast_year.balance_sheet

    return MultiYearDetailedCashFlow(
        company_id=company_id,
        scenario_id=scenario_id,
        base_year=base_year,
        cashflows=cashflows
    )


def calculate_ratios_historical_and_forecast(
    db: Session,
    company_id: int,
    scenario_id: int,
    base_year: int
) -> dict:
    """
    Calculate all financial ratios for historical and forecast years

    Args:
        db: Database session
        company_id: Company ID
        scenario_id: Budget scenario ID
        base_year: Last historical year

    Returns:
        Dictionary with years and ratios for each year
    """
    from database.models import BudgetScenario, ForecastYear

    # Get scenario
    scenario = db.query(BudgetScenario).filter(
        BudgetScenario.id == scenario_id,
        BudgetScenario.company_id == company_id
    ).first()

    if not scenario:
        raise ValueError(f"Scenario {scenario_id} not found for company {company_id}")

    # Get all historical years
    historical_years = db.query(models.FinancialYear).filter(
        models.FinancialYear.company_id == company_id
    ).order_by(models.FinancialYear.year).all()

    # Get all forecast years
    forecast_years = db.query(ForecastYear).filter(
        ForecastYear.scenario_id == scenario_id
    ).order_by(ForecastYear.year).all()

    result = {
        "company_id": company_id,
        "scenario_id": scenario_id,
        "base_year": base_year,
        "years": [],
        "ratios": []
    }

    # Calculate ratios for historical years
    for fy in historical_years:
        if not fy.balance_sheet or not fy.income_statement:
            continue

        calc = FinancialRatiosCalculator(fy.balance_sheet, fy.income_statement)
        all_ratios = calc.calculate_all_ratios()

        # Convert NamedTuples to dicts
        ratios_dict = {}
        for category, ratios in all_ratios.items():
            ratios_dict[category] = _convert_namedtuple_to_dict(ratios)

        result["years"].append(fy.year)
        result["ratios"].append(ratios_dict)

    # Calculate ratios for forecast years
    for fy in forecast_years:
        if not fy.balance_sheet or not fy.income_statement:
            continue

        calc = FinancialRatiosCalculator(fy.balance_sheet, fy.income_statement)
        all_ratios = calc.calculate_all_ratios()

        # Convert NamedTuples to dicts
        ratios_dict = {}
        for category, ratios in all_ratios.items():
            ratios_dict[category] = _convert_namedtuple_to_dict(ratios)

        result["years"].append(fy.year)
        result["ratios"].append(ratios_dict)

    return result


def calculate_detailed_cashflow_historical_only(
    db: Session,
    company_id: int,
    start_year: int,
    end_year: int
) -> MultiYearDetailedCashFlow:
    """
    Calculate detailed cash flow for historical years only (no scenario)

    Args:
        db: Database session
        company_id: Company ID
        start_year: First year to calculate cashflow for
        end_year: Last year to calculate cashflow for

    Returns:
        MultiYearDetailedCashFlow with historical cashflows only
    """
    # Get all financial years in range
    financial_years = db.query(models.FinancialYear).filter(
        models.FinancialYear.company_id == company_id,
        models.FinancialYear.year >= start_year - 1,  # Need previous year as base
        models.FinancialYear.year <= end_year
    ).order_by(models.FinancialYear.year).all()

    if len(financial_years) < 2:
        raise ValueError("At least 2 years of historical data required for cashflow calculation")

    cashflows = []
    base_year = start_year - 1

    # Calculate cashflow for each year starting from start_year
    for i in range(1, len(financial_years)):
        current = financial_years[i]
        previous = financial_years[i-1]

        if current.year < start_year:
            continue

        if not current.balance_sheet or not current.income_statement:
            continue
        if not previous.balance_sheet:
            continue

        cf = DetailedCashFlowCalculator.calculate(
            bs_current=current.balance_sheet,
            bs_previous=previous.balance_sheet,
            inc_current=current.income_statement,
            year=current.year
        )
        cashflows.append(cf)

    if not cashflows:
        raise ValueError("No cashflows could be calculated for the specified period")

    return MultiYearDetailedCashFlow(
        company_id=company_id,
        scenario_id=None,
        base_year=base_year,
        cashflows=cashflows
    )
