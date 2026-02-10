"""
Analysis Service - Comprehensive financial analysis for scenarios

Provides complete analysis including historical data, forecasts, and all calculations
in a single response. This simplifies the API by consolidating multiple endpoints.
"""
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session, joinedload
from decimal import Decimal
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
from app.calculations.cashflow_detailed import DetailedCashFlowCalculator
from app.schemas import balance_sheet as bs_schemas
from app.schemas import income_statement as inc_schemas
from app.schemas import budget as budget_schemas
from pdf_service.em_score import calculate_em_score, get_em_score_description


def get_complete_analysis(
    db: Session,
    company_id: int,
    scenario_id: int,
    include_historical: bool = True,
    include_forecast: bool = True,
    include_calculations: bool = True
) -> Dict[str, Any]:
    """
    Get complete financial analysis for a scenario.

    Returns historical data, forecast data, and all calculations in one comprehensive response.
    This eliminates the need for multiple API calls.

    Args:
        db: Database session
        company_id: Company ID
        scenario_id: Budget scenario ID
        include_historical: Include historical years (base_year - 1 and base_year)
        include_forecast: Include forecast years
        include_calculations: Include all calculations (Altman, FGPMI, ratios, cashflow)

    Returns:
        Dictionary with complete analysis data

    Raises:
        ValueError: If scenario not found or data missing
    """
    # 1. Load scenario with all related data (eager loading for performance)
    scenario = db.query(models.BudgetScenario)\
        .options(
            joinedload(models.BudgetScenario.company),
            joinedload(models.BudgetScenario.assumptions),
            joinedload(models.BudgetScenario.forecast_years)
                .joinedload(models.ForecastYear.balance_sheet),
            joinedload(models.BudgetScenario.forecast_years)
                .joinedload(models.ForecastYear.income_statement)
        )\
        .filter(
            models.BudgetScenario.id == scenario_id,
            models.BudgetScenario.company_id == company_id
        )\
        .first()

    if not scenario:
        raise ValueError(f"Scenario {scenario_id} not found for company {company_id}")

    # Calculate projection_years dynamically from forecast years count
    projection_years = len(scenario.forecast_years) if scenario.forecast_years else 0

    # Build result structure
    result = {
        "scenario": {
            "id": scenario.id,
            "name": scenario.name,
            "base_year": scenario.base_year,
            "projection_years": projection_years,
            "is_active": scenario.is_active,
            "company": {
                "id": scenario.company.id,
                "name": scenario.company.name,
                "tax_id": scenario.company.tax_id or "",
                "sector": scenario.company.sector
            }
        },
        "historical_years": [],
        "forecast_years": [],
        "calculations": {}
    }

    # 2. Get historical years (base_year - 1 and base_year)
    historical_data_list = []
    if include_historical:
        historical_years_db = db.query(models.FinancialYear)\
            .options(
                joinedload(models.FinancialYear.balance_sheet),
                joinedload(models.FinancialYear.income_statement)
            )\
            .filter(
                models.FinancialYear.company_id == company_id,
                models.FinancialYear.year >= scenario.base_year - 1,
                models.FinancialYear.year <= scenario.base_year
            )\
            .order_by(models.FinancialYear.year)\
            .all()

        for fy in historical_years_db:
            if fy.balance_sheet and fy.income_statement:
                year_data = {
                    "year": fy.year,
                    "type": "historical",
                    "balance_sheet": _serialize_balance_sheet(fy.balance_sheet),
                    "income_statement": _serialize_income_statement(fy.income_statement)
                }
                result["historical_years"].append(year_data)
                historical_data_list.append({
                    "year": fy.year,
                    "balance_sheet": fy.balance_sheet,
                    "income_statement": fy.income_statement
                })

    # 3. Get forecast years
    forecast_data_list = []
    if include_forecast:
        # Sort forecast years by year
        forecast_years_sorted = sorted(scenario.forecast_years, key=lambda x: x.year)

        for forecast_year in forecast_years_sorted:
            if forecast_year.balance_sheet and forecast_year.income_statement:
                # Get assumptions for this year
                assumptions = next(
                    (a for a in scenario.assumptions if a.forecast_year == forecast_year.year),
                    None
                )

                year_data = {
                    "year": forecast_year.year,
                    "type": "forecast",
                    "assumptions": _serialize_assumptions(assumptions) if assumptions else None,
                    "balance_sheet": _serialize_balance_sheet(forecast_year.balance_sheet),
                    "income_statement": _serialize_income_statement(forecast_year.income_statement)
                }
                result["forecast_years"].append(year_data)
                forecast_data_list.append({
                    "year": forecast_year.year,
                    "balance_sheet": forecast_year.balance_sheet,
                    "income_statement": forecast_year.income_statement
                })

    # 4. Calculate all financial metrics for each year
    if include_calculations:
        all_years_data = historical_data_list + forecast_data_list
        calculations_by_year = {}

        # Calculate for each year
        for year_data in all_years_data:
            year = year_data["year"]
            bs = year_data["balance_sheet"]
            inc = year_data["income_statement"]
            sector = scenario.company.sector

            year_calculations = _calculate_year_metrics(bs, inc, sector)
            calculations_by_year[str(year)] = year_calculations

        result["calculations"]["by_year"] = calculations_by_year

        # Calculate cashflow (requires year-over-year comparisons)
        cashflow_years = []
        for i in range(1, len(all_years_data)):
            base_year_data = all_years_data[i - 1]
            current_year_data = all_years_data[i]

            try:
                cf_result = _calculate_cashflow(
                    base_year_data["balance_sheet"],
                    base_year_data["income_statement"],
                    current_year_data["balance_sheet"],
                    current_year_data["income_statement"],
                    current_year_data["year"]
                )
                cf_result["base_year"] = base_year_data["year"]
                cashflow_years.append(cf_result)
            except Exception as e:
                # If cashflow calculation fails for a year, continue with others
                print(f"Warning: Cashflow calculation failed for year {current_year_data['year']}: {str(e)}")

        result["calculations"]["cashflow"] = {"years": cashflow_years}

    return result


def _calculate_year_metrics(
    bs: models.BalanceSheet,
    inc: models.IncomeStatement,
    sector: int
) -> Dict[str, Any]:
    """
    Calculate all financial metrics for a single year.

    Returns:
        Dictionary with Altman, FGPMI, and all ratio categories
    """
    # Calculate ratios
    ratios_calc = FinancialRatiosCalculator(bs, inc)
    wc = ratios_calc.calculate_working_capital_metrics()
    liquidity = ratios_calc.calculate_liquidity_ratios()
    solvency = ratios_calc.calculate_solvency_ratios()
    profitability = ratios_calc.calculate_profitability_ratios()
    activity = ratios_calc.calculate_activity_ratios()
    coverage = ratios_calc.calculate_coverage_ratios()
    turnover = ratios_calc.calculate_turnover_ratios()
    extended_profitability = ratios_calc.calculate_extended_profitability_ratios()
    efficiency = ratios_calc.calculate_efficiency_ratios()
    break_even = ratios_calc.calculate_break_even_analysis()

    # Calculate Altman Z-Score
    altman_calc = AltmanCalculator(bs, inc, sector)
    altman = altman_calc.calculate()

    # Calculate FGPMI Rating
    fgpmi_calc = FGPMICalculator(bs, inc, sector)
    fgpmi = fgpmi_calc.calculate()

    # Calculate EM-Score from Altman Z-Score
    em_rating, em_z_used = calculate_em_score(altman.z_score, sector)
    em_description = get_em_score_description(em_rating)

    return {
        "altman": _serialize_altman(altman),
        "fgpmi": _serialize_fgpmi(fgpmi),
        "em_score": {
            "rating": em_rating,
            "z_score_used": float(em_z_used),
            "description": em_description,
        },
        "ratios": {
            "working_capital": _serialize_working_capital(wc),
            "liquidity": _serialize_liquidity(liquidity),
            "solvency": _serialize_solvency(solvency),
            "profitability": _serialize_profitability(profitability),
            "activity": _serialize_activity(activity),
            "coverage": _namedtuple_to_dict(coverage),
            "turnover": _namedtuple_to_dict(turnover),
            "extended_profitability": _namedtuple_to_dict(extended_profitability),
            "efficiency": _namedtuple_to_dict(efficiency),
            "break_even": _namedtuple_to_dict(break_even),
        }
    }


def _calculate_cashflow(
    base_bs: models.BalanceSheet,
    base_inc: models.IncomeStatement,
    current_bs: models.BalanceSheet,
    current_inc: models.IncomeStatement,
    year: int
) -> Dict[str, Any]:
    """
    Calculate detailed cashflow for one year.

    Returns:
        Dictionary with operating, investing, financing cashflows and ratios
    """
    # Call static method with correct parameters
    cf_result = DetailedCashFlowCalculator.calculate(
        bs_current=current_bs,
        bs_previous=base_bs,
        inc_current=current_inc,
        year=year
    )

    return {
        "operating": _serialize_operating_activities(cf_result.operating_activities),
        "investing": _serialize_investing_activities(cf_result.investing_activities),
        "financing": _serialize_financing_activities(cf_result.financing_activities),
        "cash_reconciliation": _serialize_cash_reconciliation(cf_result.cash_reconciliation),
        "year": cf_result.year
    }


# ===== Serialization Helpers =====

def _namedtuple_to_dict(nt) -> Dict[str, Any]:
    """Convert NamedTuple to dictionary with float conversion"""
    if nt is None:
        return {}
    result = {}
    for key, value in nt._asdict().items():
        if hasattr(value, '_asdict'):  # Nested NamedTuple
            result[key] = _namedtuple_to_dict(value)
        elif isinstance(value, (int, str, bool)):
            result[key] = value
        elif isinstance(value, Decimal):
            result[key] = float(value)
        elif value is not None:
            try:
                result[key] = float(value)
            except (ValueError, TypeError):
                result[key] = value
        else:
            result[key] = None
    return result


def _serialize_balance_sheet(bs) -> Dict[str, Any]:
    """Serialize balance sheet to dictionary (works for both historical and forecast)"""
    # Manually construct dictionary to work with both BalanceSheet and ForecastBalanceSheet
    data = {}

    # Get all sp## fields
    for attr in dir(bs):
        if attr.startswith('sp') and not attr.startswith('_'):
            value = getattr(bs, attr, Decimal("0"))
            data[attr] = float(value) if isinstance(value, Decimal) else float(value or 0)

    # Add calculated properties
    data["total_assets"] = float(bs.total_assets)
    data["total_equity"] = float(bs.total_equity)
    data["total_debt"] = float(bs.total_debt)
    data["fixed_assets"] = float(bs.fixed_assets)
    data["current_assets"] = float(bs.current_assets)
    data["current_liabilities"] = float(bs.current_liabilities)
    data["working_capital_net"] = float(bs.working_capital_net)

    return data


def _serialize_income_statement(inc) -> Dict[str, Any]:
    """Serialize income statement to dictionary (works for both historical and forecast)"""
    # Manually construct dictionary to work with both IncomeStatement and ForecastIncomeStatement
    data = {}

    # Get all ce## fields
    for attr in dir(inc):
        if attr.startswith('ce') and not attr.startswith('_'):
            value = getattr(inc, attr, Decimal("0"))
            data[attr] = float(value) if isinstance(value, Decimal) else float(value or 0)

    # Add calculated properties
    data["revenue"] = float(inc.revenue)
    data["production_value"] = float(inc.production_value)
    data["production_cost"] = float(inc.production_cost)
    data["ebitda"] = float(inc.ebitda)
    data["ebit"] = float(inc.ebit)
    data["financial_result"] = float(inc.financial_result)
    data["extraordinary_result"] = float(inc.extraordinary_result)
    data["profit_before_tax"] = float(inc.profit_before_tax)
    data["net_profit"] = float(inc.net_profit)

    return data


def _serialize_assumptions(assumptions) -> Dict[str, Any]:
    """Serialize budget assumptions to dictionary using Pydantic schema"""
    if not assumptions:
        return None

    # Use the existing BudgetAssumptions Pydantic schema
    schema = budget_schemas.BudgetAssumptions.model_validate(assumptions)
    data = schema.model_dump()

    # Convert all Decimal to float
    for key, value in data.items():
        if isinstance(value, Decimal):
            data[key] = float(value)

    return data


def _serialize_altman(altman) -> Dict[str, Any]:
    """Serialize Altman Z-Score result to dictionary"""
    return {
        "z_score": float(altman.z_score),
        "classification": altman.classification,
        "interpretation_it": altman.interpretation_it,
        "sector": altman.sector,
        "model_type": altman.model_type,
        "components": {
            "A": float(altman.components.A),
            "B": float(altman.components.B),
            "C": float(altman.components.C),
            "D": float(altman.components.D),
            "E": float(altman.components.E) if altman.components.E is not None else None
        }
    }


def _serialize_fgpmi(fgpmi) -> Dict[str, Any]:
    """Serialize FGPMI rating result to dictionary"""
    # Serialize indicators dictionary
    indicators_dict = {}
    for key, indicator in fgpmi.indicators.items():
        indicators_dict[key] = _namedtuple_to_dict(indicator)

    return {
        "total_score": fgpmi.total_score,
        "max_score": fgpmi.max_score,
        "rating_class": fgpmi.rating_class,
        "rating_code": fgpmi.rating_code,
        "rating_description": fgpmi.rating_description,
        "risk_level": fgpmi.risk_level,
        "sector_model": fgpmi.sector_model,
        "revenue_bonus": fgpmi.revenue_bonus,
        "indicators": indicators_dict
    }


def _serialize_working_capital(wc) -> Dict[str, Any]:
    """Serialize working capital metrics to dictionary"""
    return _namedtuple_to_dict(wc)


def _serialize_liquidity(liquidity) -> Dict[str, Any]:
    """Serialize liquidity ratios to dictionary"""
    return _namedtuple_to_dict(liquidity)


def _serialize_solvency(solvency) -> Dict[str, Any]:
    """Serialize solvency ratios to dictionary"""
    return _namedtuple_to_dict(solvency)


def _serialize_profitability(profitability) -> Dict[str, Any]:
    """Serialize profitability ratios to dictionary"""
    return _namedtuple_to_dict(profitability)


def _serialize_activity(activity) -> Dict[str, Any]:
    """Serialize activity ratios to dictionary"""
    return _namedtuple_to_dict(activity)


def _serialize_operating_activities(operating) -> Dict[str, Any]:
    """Serialize operating activities section of cashflow"""
    return {
        "start": {
            "net_profit": float(operating.start.net_profit),
            "income_taxes": float(operating.start.income_taxes),
            "interest_expense_income": float(operating.start.interest_expense_income),
            "dividends": float(operating.start.dividends),
            "capital_gains_losses": float(operating.start.capital_gains_losses),
            "profit_before_adjustments": float(operating.start.profit_before_adjustments)
        },
        "non_cash_adjustments": {
            "provisions": float(operating.non_cash_adjustments.provisions),
            "depreciation_amortization": float(operating.non_cash_adjustments.depreciation_amortization),
            "write_downs": float(operating.non_cash_adjustments.write_downs),
            "total": float(operating.non_cash_adjustments.total)
        },
        "cashflow_before_wc": float(operating.cashflow_before_wc),
        "working_capital_changes": {
            "delta_inventory": float(operating.working_capital_changes.delta_inventory),
            "delta_receivables": float(operating.working_capital_changes.delta_receivables),
            "delta_payables": float(operating.working_capital_changes.delta_payables),
            "delta_accruals_deferrals_active": float(operating.working_capital_changes.delta_accruals_deferrals_active),
            "delta_accruals_deferrals_passive": float(operating.working_capital_changes.delta_accruals_deferrals_passive),
            "other_wc_changes": float(operating.working_capital_changes.other_wc_changes),
            "total": float(operating.working_capital_changes.total)
        },
        "cashflow_after_wc": float(operating.cashflow_after_wc),
        "cash_adjustments": {
            "interest_paid_received": float(operating.cash_adjustments.interest_paid_received),
            "taxes_paid": float(operating.cash_adjustments.taxes_paid),
            "dividends_received": float(operating.cash_adjustments.dividends_received),
            "use_of_provisions": float(operating.cash_adjustments.use_of_provisions),
            "other_cash_changes": float(operating.cash_adjustments.other_cash_changes),
            "total": float(operating.cash_adjustments.total)
        },
        "total_operating_cashflow": float(operating.total_operating_cashflow)
    }


def _serialize_investing_activities(investing) -> Dict[str, Any]:
    """Serialize investing activities section of cashflow"""
    return {
        "tangible_assets": {
            "investments": float(investing.tangible_assets.investments),
            "disinvestments": float(investing.tangible_assets.disinvestments),
            "net": float(investing.tangible_assets.net)
        },
        "intangible_assets": {
            "investments": float(investing.intangible_assets.investments),
            "disinvestments": float(investing.intangible_assets.disinvestments),
            "net": float(investing.intangible_assets.net)
        },
        "financial_assets": {
            "investments": float(investing.financial_assets.investments),
            "disinvestments": float(investing.financial_assets.disinvestments),
            "net": float(investing.financial_assets.net)
        },
        "total_investing_cashflow": float(investing.total_investing_cashflow)
    }


def _serialize_financing_activities(financing) -> Dict[str, Any]:
    """Serialize financing activities section of cashflow"""
    return {
        "third_party_funds": {
            "increases": float(financing.third_party_funds.increases),
            "decreases": float(financing.third_party_funds.decreases),
            "net": float(financing.third_party_funds.net)
        },
        "own_funds": {
            "increases": float(financing.own_funds.increases),
            "decreases": float(financing.own_funds.decreases),
            "net": float(financing.own_funds.net)
        },
        "total_financing_cashflow": float(financing.total_financing_cashflow)
    }


def _serialize_cash_reconciliation(reconciliation) -> Dict[str, Any]:
    """Serialize cash reconciliation section of cashflow"""
    return {
        "total_cashflow": float(reconciliation.total_cashflow),
        "cash_beginning": float(reconciliation.cash_beginning),
        "cash_ending": float(reconciliation.cash_ending),
        "difference": float(reconciliation.difference),
        "verification_ok": reconciliation.verification_ok
    }
