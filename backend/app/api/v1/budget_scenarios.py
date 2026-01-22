"""
Budget Scenarios and Assumptions API endpoints
"""
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload
from datetime import datetime
import sys
import os

# Add backend directory to Python path
backend_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from app.core.database import get_db
from app.schemas import budget as budget_schemas
from app.schemas import forecast as forecast_schemas
from database import models
from calculations.forecast_engine import ForecastEngine

router = APIRouter()


# ===== Validation Helper Functions =====

def validate_company_exists(company_id: int, db: Session) -> models.Company:
    """Validate company exists and return it"""
    company = db.query(models.Company).filter(models.Company.id == company_id).first()
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company with id {company_id} not found"
        )
    return company


def validate_scenario_belongs_to_company(
    scenario_id: int,
    company_id: int,
    db: Session
) -> models.BudgetScenario:
    """Validate scenario exists and belongs to company"""
    scenario = db.query(models.BudgetScenario).filter(
        models.BudgetScenario.id == scenario_id,
        models.BudgetScenario.company_id == company_id
    ).first()

    if not scenario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Budget scenario {scenario_id} not found for company {company_id}"
        )
    return scenario


def validate_base_year_data(company_id: int, base_year: int, db: Session):
    """Validate that base year has complete financial data"""
    financial_year = db.query(models.FinancialYear).filter(
        models.FinancialYear.company_id == company_id,
        models.FinancialYear.year == base_year
    ).first()

    if not financial_year:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Base year {base_year} not found for company {company_id}"
        )

    if not financial_year.balance_sheet or not financial_year.income_statement:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Base year {base_year} is missing balance sheet or income statement data"
        )


def validate_forecast_year_exists(
    scenario_id: int,
    year: int,
    db: Session
) -> models.ForecastYear:
    """Validate forecast year exists for scenario"""
    forecast_year = db.query(models.ForecastYear).filter(
        models.ForecastYear.scenario_id == scenario_id,
        models.ForecastYear.year == year
    ).first()

    if not forecast_year:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Forecast for year {year} not found in scenario {scenario_id}"
        )
    return forecast_year


# ===== Budget Scenario Endpoints =====

@router.get(
    "/companies/{company_id}/scenarios",
    response_model=List[budget_schemas.BudgetScenario]
)
def list_budget_scenarios(
    company_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    is_active: Optional[int] = Query(None, ge=0, le=1),
    db: Session = Depends(get_db)
):
    """
    List all budget scenarios for a company

    Optional filtering by is_active flag (0=inactive, 1=active)
    """
    # Validate company exists
    validate_company_exists(company_id, db)

    # Build query
    query = db.query(models.BudgetScenario).filter(
        models.BudgetScenario.company_id == company_id
    )

    # Apply optional filter
    if is_active is not None:
        query = query.filter(models.BudgetScenario.is_active == is_active)

    # Order by updated_at descending (most recent first)
    scenarios = query.order_by(
        models.BudgetScenario.updated_at.desc()
    ).offset(skip).limit(limit).all()

    return scenarios


@router.get(
    "/companies/{company_id}/scenarios/{scenario_id}",
    response_model=budget_schemas.BudgetScenario
)
def get_budget_scenario(
    company_id: int,
    scenario_id: int,
    include_details: bool = Query(False, description="Include nested assumptions and forecast years"),
    db: Session = Depends(get_db)
):
    """
    Get a single budget scenario with optional details

    Set include_details=true to get nested assumptions and forecast years
    """
    # Build query with optional eager loading
    query = db.query(models.BudgetScenario).filter(
        models.BudgetScenario.id == scenario_id,
        models.BudgetScenario.company_id == company_id
    )

    if include_details:
        query = query.options(
            joinedload(models.BudgetScenario.assumptions),
            joinedload(models.BudgetScenario.forecast_years)
        )

    scenario = query.first()

    if not scenario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Budget scenario {scenario_id} not found for company {company_id}"
        )

    return scenario


@router.post(
    "/companies/{company_id}/scenarios",
    response_model=budget_schemas.BudgetScenario,
    status_code=status.HTTP_201_CREATED
)
def create_budget_scenario(
    company_id: int,
    scenario_create: budget_schemas.BudgetScenarioCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new budget scenario

    Note: This creates the scenario metadata only.
    Use POST /scenarios/{id}/assumptions to add forecast assumptions.
    Use POST /scenarios/{id}/generate to generate forecasts.
    """
    # Validate company exists
    validate_company_exists(company_id, db)

    # Validate base year has complete data
    validate_base_year_data(company_id, scenario_create.base_year, db)

    # Ensure company_id matches
    if scenario_create.company_id != company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Company ID in URL must match company_id in request body"
        )

    # Create scenario
    db_scenario = models.BudgetScenario(**scenario_create.model_dump())
    db.add(db_scenario)
    db.commit()
    db.refresh(db_scenario)

    return db_scenario


@router.put(
    "/companies/{company_id}/scenarios/{scenario_id}",
    response_model=budget_schemas.BudgetScenario
)
def update_budget_scenario(
    company_id: int,
    scenario_id: int,
    scenario_update: budget_schemas.BudgetScenarioUpdate,
    db: Session = Depends(get_db)
):
    """
    Update an existing budget scenario metadata

    Only provided fields will be updated
    """
    # Validate scenario belongs to company
    db_scenario = validate_scenario_belongs_to_company(scenario_id, company_id, db)

    # If base_year is being updated, validate new base year data
    if scenario_update.base_year is not None and scenario_update.base_year != db_scenario.base_year:
        validate_base_year_data(company_id, scenario_update.base_year, db)

    # Update only provided fields
    update_data = scenario_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_scenario, field, value)

    db.commit()
    db.refresh(db_scenario)

    return db_scenario


@router.delete(
    "/companies/{company_id}/scenarios/{scenario_id}",
    status_code=status.HTTP_204_NO_CONTENT
)
def delete_budget_scenario(
    company_id: int,
    scenario_id: int,
    db: Session = Depends(get_db)
):
    """
    Delete a budget scenario and all associated data

    This will cascade delete:
    - All budget assumptions
    - All forecast years
    - All forecasted balance sheets and income statements
    """
    # Validate scenario belongs to company
    db_scenario = validate_scenario_belongs_to_company(scenario_id, company_id, db)

    # Delete (cascade will handle related records)
    db.delete(db_scenario)
    db.commit()

    return None


# ===== Budget Assumptions Endpoints =====

@router.get(
    "/companies/{company_id}/scenarios/{scenario_id}/assumptions",
    response_model=List[budget_schemas.BudgetAssumptions]
)
def list_budget_assumptions(
    company_id: int,
    scenario_id: int,
    db: Session = Depends(get_db)
):
    """
    Get all budget assumptions for a scenario

    Returns assumptions ordered by forecast year (ascending)
    """
    # Validate scenario belongs to company
    validate_scenario_belongs_to_company(scenario_id, company_id, db)

    # Get assumptions ordered by year
    assumptions = db.query(models.BudgetAssumptions).filter(
        models.BudgetAssumptions.scenario_id == scenario_id
    ).order_by(models.BudgetAssumptions.forecast_year.asc()).all()

    return assumptions


@router.post(
    "/companies/{company_id}/scenarios/{scenario_id}/assumptions",
    response_model=budget_schemas.BudgetAssumptions,
    status_code=status.HTTP_201_CREATED
)
def create_budget_assumptions(
    company_id: int,
    scenario_id: int,
    assumptions_create: budget_schemas.BudgetAssumptionsCreate,
    db: Session = Depends(get_db)
):
    """
    Create budget assumptions for a forecast year

    Each scenario can have multiple assumption records (one per forecast year)
    """
    # Validate scenario belongs to company
    scenario = validate_scenario_belongs_to_company(scenario_id, company_id, db)

    # Ensure scenario_id matches
    if assumptions_create.scenario_id != scenario_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Scenario ID in URL must match scenario_id in request body"
        )

    # Validate forecast year is after base year
    if assumptions_create.forecast_year <= scenario.base_year:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Forecast year {assumptions_create.forecast_year} must be greater than base year {scenario.base_year}"
        )

    # Check for duplicate (scenario_id, forecast_year)
    existing = db.query(models.BudgetAssumptions).filter(
        models.BudgetAssumptions.scenario_id == scenario_id,
        models.BudgetAssumptions.forecast_year == assumptions_create.forecast_year
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Assumptions for year {assumptions_create.forecast_year} already exist in scenario {scenario_id}"
        )

    # Create assumptions
    db_assumptions = models.BudgetAssumptions(**assumptions_create.model_dump())
    db.add(db_assumptions)
    db.commit()
    db.refresh(db_assumptions)

    return db_assumptions


@router.put(
    "/companies/{company_id}/scenarios/{scenario_id}/assumptions/{year}",
    response_model=budget_schemas.BudgetAssumptions
)
def update_budget_assumptions(
    company_id: int,
    scenario_id: int,
    year: int,
    assumptions_update: budget_schemas.BudgetAssumptionsUpdate,
    db: Session = Depends(get_db)
):
    """
    Update budget assumptions for a specific forecast year

    Only provided fields will be updated
    """
    # Validate scenario belongs to company
    validate_scenario_belongs_to_company(scenario_id, company_id, db)

    # Find assumptions for this year
    db_assumptions = db.query(models.BudgetAssumptions).filter(
        models.BudgetAssumptions.scenario_id == scenario_id,
        models.BudgetAssumptions.forecast_year == year
    ).first()

    if not db_assumptions:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assumptions for year {year} not found in scenario {scenario_id}"
        )

    # Update only provided fields
    update_data = assumptions_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_assumptions, field, value)

    db.commit()
    db.refresh(db_assumptions)

    return db_assumptions


@router.delete(
    "/companies/{company_id}/scenarios/{scenario_id}/assumptions/{year}",
    status_code=status.HTTP_204_NO_CONTENT
)
def delete_budget_assumptions(
    company_id: int,
    scenario_id: int,
    year: int,
    db: Session = Depends(get_db)
):
    """
    Delete budget assumptions for a specific forecast year

    This will also delete the associated forecast year and forecasted statements (cascade)
    """
    # Validate scenario belongs to company
    validate_scenario_belongs_to_company(scenario_id, company_id, db)

    # Find assumptions for this year
    db_assumptions = db.query(models.BudgetAssumptions).filter(
        models.BudgetAssumptions.scenario_id == scenario_id,
        models.BudgetAssumptions.forecast_year == year
    ).first()

    if not db_assumptions:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assumptions for year {year} not found in scenario {scenario_id}"
        )

    # Delete assumptions
    db.delete(db_assumptions)
    db.commit()

    return None


# ===== Forecast Generation Endpoint =====

@router.post(
    "/companies/{company_id}/scenarios/{scenario_id}/generate",
    response_model=forecast_schemas.ForecastGenerationResult
)
def generate_forecasts(
    company_id: int,
    scenario_id: int,
    db: Session = Depends(get_db)
):
    """
    Generate (or regenerate) forecasts for all years in the scenario

    This will:
    1. Validate base year data exists
    2. Validate at least one assumption exists
    3. Call ForecastEngine to generate forecasted balance sheets and income statements
    4. Create/update ForecastYear, ForecastBalanceSheet, and ForecastIncomeStatement records
    5. Return summary statistics
    """
    # Validate scenario belongs to company
    scenario = validate_scenario_belongs_to_company(scenario_id, company_id, db)

    # Validate base year data
    validate_base_year_data(company_id, scenario.base_year, db)

    # Validate at least one assumption exists
    assumptions_count = db.query(models.BudgetAssumptions).filter(
        models.BudgetAssumptions.scenario_id == scenario_id
    ).count()

    if assumptions_count == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot generate forecast: no assumptions found for scenario {scenario_id}. Add assumptions first."
        )

    # Generate forecast using ForecastEngine
    try:
        engine = ForecastEngine(db)
        result = engine.generate_forecast(scenario_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Forecast generation failed: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error during forecast generation: {str(e)}"
        )

    # Build response with summary
    forecast_years = db.query(models.ForecastYear).filter(
        models.ForecastYear.scenario_id == scenario_id
    ).order_by(models.ForecastYear.year.asc()).all()

    # Extract summary statistics per year
    summary = {}
    for fy in forecast_years:
        if fy.balance_sheet and fy.income_statement:
            summary[str(fy.year)] = {
                "total_assets": float(fy.balance_sheet.total_assets),
                "total_equity": float(fy.balance_sheet.total_equity),
                "total_debt": float(fy.balance_sheet.total_debt),
                "working_capital_net": float(fy.balance_sheet.working_capital_net),
                "revenue": float(fy.income_statement.revenue),
                "ebitda": float(fy.income_statement.ebitda),
                "ebit": float(fy.income_statement.ebit),
                "net_profit": float(fy.income_statement.net_profit)
            }

    return forecast_schemas.ForecastGenerationResult(
        scenario_id=scenario.id,
        scenario_name=scenario.name,
        base_year=scenario.base_year,
        forecast_years=[fy.year for fy in forecast_years],
        summary=summary,
        generated_at=datetime.utcnow()
    )


# ===== Forecast Data Access Endpoints =====

@router.get(
    "/companies/{company_id}/scenarios/{scenario_id}/forecasts",
    response_model=List[forecast_schemas.ForecastYearSummary]
)
def list_forecast_years(
    company_id: int,
    scenario_id: int,
    db: Session = Depends(get_db)
):
    """
    List all forecast years for a scenario

    Returns forecast year metadata (id, year, timestamps)
    """
    # Validate scenario belongs to company
    validate_scenario_belongs_to_company(scenario_id, company_id, db)

    # Get forecast years ordered by year
    forecast_years = db.query(models.ForecastYear).filter(
        models.ForecastYear.scenario_id == scenario_id
    ).order_by(models.ForecastYear.year.asc()).all()

    return forecast_years


@router.get(
    "/companies/{company_id}/scenarios/{scenario_id}/forecasts/{year}/balance-sheet",
    response_model=forecast_schemas.ForecastBalanceSheet
)
def get_forecast_balance_sheet(
    company_id: int,
    scenario_id: int,
    year: int,
    db: Session = Depends(get_db)
):
    """
    Get forecasted balance sheet for a specific year

    Returns all balance sheet line items and calculated properties
    """
    # Validate scenario belongs to company
    validate_scenario_belongs_to_company(scenario_id, company_id, db)

    # Validate forecast year exists
    forecast_year = validate_forecast_year_exists(scenario_id, year, db)

    # Check balance sheet exists
    if not forecast_year.balance_sheet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Balance sheet not found for forecast year {year}"
        )

    return forecast_year.balance_sheet


@router.get(
    "/companies/{company_id}/scenarios/{scenario_id}/forecasts/{year}/income-statement",
    response_model=forecast_schemas.ForecastIncomeStatement
)
def get_forecast_income_statement(
    company_id: int,
    scenario_id: int,
    year: int,
    db: Session = Depends(get_db)
):
    """
    Get forecasted income statement for a specific year

    Returns all income statement line items and calculated properties
    """
    # Validate scenario belongs to company
    validate_scenario_belongs_to_company(scenario_id, company_id, db)

    # Validate forecast year exists
    forecast_year = validate_forecast_year_exists(scenario_id, year, db)

    # Check income statement exists
    if not forecast_year.income_statement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Income statement not found for forecast year {year}"
        )

    return forecast_year.income_statement


@router.get(
    "/companies/{company_id}/scenarios/{scenario_id}/reclassified",
    response_model=Dict[str, Any],
    summary="Get reclassified financial data for forecast scenario"
)
def get_forecast_reclassified_data(
    company_id: int,
    scenario_id: int,
    db: Session = Depends(get_db)
):
    """
    Get reclassified financial indicators for both historical and forecast years.

    Returns comprehensive metrics for charting and analysis:
    - Historical data (up to base year)
    - Forecast data (projection years)
    - Income Statement reclassified (Revenue, EBITDA, EBIT, Net Profit)
    - Balance Sheet reclassified (Assets, Equity, Debt, Working Capital)
    - Key financial ratios (Liquidity, Profitability, Solvency)

    This endpoint is designed for the "Previsionale Riclassificato" page.
    """
    from calculations.ratios import FinancialRatiosCalculator

    # Validate scenario belongs to company
    scenario = validate_scenario_belongs_to_company(scenario_id, company_id, db)

    # Get base year
    base_year = scenario.base_year

    # Get company
    company = validate_company_exists(company_id, db)

    # Get all forecast years for this scenario
    forecast_years = db.query(models.ForecastYear).filter(
        models.ForecastYear.scenario_id == scenario_id
    ).order_by(models.ForecastYear.year).all()

    if not forecast_years:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No forecast data found for scenario {scenario_id}"
        )

    # Get historical data (all years up to and including base year)
    historical_years = db.query(models.FinancialYear).filter(
        models.FinancialYear.company_id == company_id,
        models.FinancialYear.year <= base_year
    ).order_by(models.FinancialYear.year).all()

    # Build result structure
    result = {
        "scenario": {
            "id": scenario.id,
            "name": scenario.name,
            "base_year": scenario.base_year,
            "projection_years": len(forecast_years)
        },
        "years": [],
        "historical_data": [],
        "forecast_data": []
    }

    # Process historical data
    for fy in historical_years:
        if not fy.balance_sheet or not fy.income_statement:
            continue

        bs = fy.balance_sheet
        inc = fy.income_statement

        # Calculate ratios
        calc = FinancialRatiosCalculator(bs, inc)
        wc_metrics = calc.calculate_working_capital_metrics()
        liquidity = calc.calculate_liquidity_ratios()
        profitability = calc.calculate_profitability_ratios()
        solvency = calc.calculate_solvency_ratios()

        year_data = {
            "year": fy.year,
            "type": "historical",
            # Income Statement Reclassified
            "income_statement": {
                "revenue": float(inc.revenue),
                "production_value": float(inc.production_value),
                "production_cost": float(inc.production_cost),
                "ebitda": float(inc.ebitda),
                "ebit": float(inc.ebit),
                "financial_result": float(inc.financial_result),
                "extraordinary_result": float(inc.extraordinary_result),
                "profit_before_tax": float(inc.profit_before_tax),
                "net_profit": float(inc.net_profit)
            },
            # Balance Sheet Reclassified
            "balance_sheet": {
                "total_assets": float(bs.total_assets),
                "fixed_assets": float(bs.fixed_assets),
                "current_assets": float(bs.current_assets),
                "total_equity": float(bs.total_equity),
                "total_debt": float(bs.total_debt),
                "current_liabilities": float(bs.current_liabilities),
                "long_term_debt": float(bs.sp17_debiti_lungo),
                "working_capital": float(bs.working_capital_net)
            },
            # Key Ratios
            "ratios": {
                "current_ratio": float(liquidity.current_ratio),
                "quick_ratio": float(liquidity.quick_ratio),
                "roe": float(profitability.roe),
                "roi": float(profitability.roi),
                "ros": float(profitability.ros),
                "ebitda_margin": float(profitability.ebitda_margin),
                "ebit_margin": float(profitability.ebit_margin),
                "net_margin": float(profitability.net_margin),
                "debt_to_equity": float(solvency.debt_to_equity),
                "autonomy_index": float(solvency.autonomy_index)
            }
        }

        result["years"].append(fy.year)
        result["historical_data"].append(year_data)

    # Process forecast data
    for forecast_year in forecast_years:
        if not forecast_year.balance_sheet or not forecast_year.income_statement:
            continue

        bs = forecast_year.balance_sheet
        inc = forecast_year.income_statement

        # Calculate ratios
        calc = FinancialRatiosCalculator(bs, inc)
        wc_metrics = calc.calculate_working_capital_metrics()
        liquidity = calc.calculate_liquidity_ratios()
        profitability = calc.calculate_profitability_ratios()
        solvency = calc.calculate_solvency_ratios()

        year_data = {
            "year": forecast_year.year,
            "type": "forecast",
            # Income Statement Reclassified
            "income_statement": {
                "revenue": float(inc.revenue),
                "production_value": float(inc.production_value),
                "production_cost": float(inc.production_cost),
                "ebitda": float(inc.ebitda),
                "ebit": float(inc.ebit),
                "financial_result": float(inc.financial_result),
                "extraordinary_result": float(inc.extraordinary_result),
                "profit_before_tax": float(inc.profit_before_tax),
                "net_profit": float(inc.net_profit)
            },
            # Balance Sheet Reclassified
            "balance_sheet": {
                "total_assets": float(bs.total_assets),
                "fixed_assets": float(bs.fixed_assets),
                "current_assets": float(bs.current_assets),
                "total_equity": float(bs.total_equity),
                "total_debt": float(bs.total_debt),
                "current_liabilities": float(bs.current_liabilities),
                "long_term_debt": float(bs.sp17_debiti_lungo),
                "working_capital": float(bs.working_capital_net)
            },
            # Key Ratios
            "ratios": {
                "current_ratio": float(liquidity.current_ratio),
                "quick_ratio": float(liquidity.quick_ratio),
                "roe": float(profitability.roe),
                "roi": float(profitability.roi),
                "ros": float(profitability.ros),
                "ebitda_margin": float(profitability.ebitda_margin),
                "ebit_margin": float(profitability.ebit_margin),
                "net_margin": float(profitability.net_margin),
                "debt_to_equity": float(solvency.debt_to_equity),
                "autonomy_index": float(solvency.autonomy_index)
            }
        }

        result["years"].append(forecast_year.year)
        result["forecast_data"].append(year_data)

    return result


# ===== Detailed Cash Flow Endpoints =====

@router.get(
    "/companies/{company_id}/scenarios/{scenario_id}/detailed-cashflow",
    response_model=Any,
    summary="Get detailed cash flow statement for scenario (historical + forecast)"
)
def get_detailed_cashflow_scenario(
    company_id: int,
    scenario_id: int,
    db: Session = Depends(get_db)
):
    """
    Get detailed cash flow statement (Italian GAAP - Indirect Method)

    Timeline: base_year (2023) → historical (2024) → forecasts (2025, 2026, 2027)

    Returns comprehensive cash flow with:
    - Operating activities (detailed breakdown with WC changes, provisions, etc.)
    - Investing activities (by asset type: tangible, intangible, financial)
    - Financing activities (debt and equity sources)
    - Cash reconciliation with verification

    Matches VBA RENDICONTO_FINANZIARIO structure.
    """
    from app.services import calculation_service

    # Validate scenario
    scenario = validate_scenario_belongs_to_company(scenario_id, company_id, db)

    try:
        result = calculation_service.calculate_detailed_cashflow_historical_and_forecast(
            db=db,
            company_id=company_id,
            scenario_id=scenario_id,
            base_year=scenario.base_year
        )
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error calculating detailed cashflow: {str(e)}"
        )


@router.get(
    "/companies/{company_id}/detailed-cashflow",
    response_model=Any,
    summary="Get detailed cash flow statement for historical years only"
)
def get_detailed_cashflow_historical(
    company_id: int,
    start_year: int = Query(..., description="First year to calculate cashflow for"),
    end_year: int = Query(..., description="Last year to calculate cashflow for"),
    db: Session = Depends(get_db)
):
    """
    Get detailed cash flow statement for historical years only (no scenario)

    Returns comprehensive cash flow with all components for specified year range.
    Requires at least 2 years of data (start_year and start_year-1 as base).
    """
    from app.services import calculation_service

    # Validate company
    validate_company_exists(company_id, db)

    try:
        result = calculation_service.calculate_detailed_cashflow_historical_only(
            db=db,
            company_id=company_id,
            start_year=start_year,
            end_year=end_year
        )
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error calculating detailed cashflow: {str(e)}"
        )
