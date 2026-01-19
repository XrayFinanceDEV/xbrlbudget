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
from app.schemas import calculations as calc_schemas


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

    # Convert to Pydantic models
    return calc_schemas.AllRatios(
        working_capital=calc_schemas.WorkingCapitalMetrics(**_convert_namedtuple_to_dict(wc)),
        liquidity=calc_schemas.LiquidityRatios(**_convert_namedtuple_to_dict(liquidity)),
        solvency=calc_schemas.SolvencyRatios(**_convert_namedtuple_to_dict(solvency)),
        profitability=calc_schemas.ProfitabilityRatios(**_convert_namedtuple_to_dict(profitability)),
        activity=calc_schemas.ActivityRatios(**_convert_namedtuple_to_dict(activity))
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
