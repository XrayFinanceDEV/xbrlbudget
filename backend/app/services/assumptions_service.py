"""
Assumptions Service - Bulk operations for budget assumptions

Handles bulk insert/update of forecast assumptions with automatic forecast generation.
"""
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime
import sys
import os

# Add backend directory to Python path
backend_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from database import models
from calculations.forecast_engine import ForecastEngine


def bulk_upsert_assumptions(
    db: Session,
    scenario_id: int,
    assumptions_list: List[Dict[str, Any]],
    auto_generate: bool = True
) -> Dict[str, Any]:
    """
    Bulk insert or update budget assumptions for a scenario.

    This replaces all existing assumptions with the new ones provided.
    Optionally triggers automatic forecast generation.

    Args:
        db: Database session
        scenario_id: Budget scenario ID
        assumptions_list: List of assumption dicts with fields:
            - forecast_year: int (required)
            - revenue_growth_pct: float
            - material_cost_growth_pct: float
            - service_cost_growth_pct: float
            - personnel_cost_growth_pct: float
            - other_revenue_growth_pct: float
            - depreciation_rate_tangible_pct: float
            - depreciation_rate_intangible_pct: float
            - capex_tangible: Decimal
            - capex_intangible: Decimal
            - new_debt: Decimal
            - debt_repayment: Decimal
            - interest_rate_pct: float
            - tax_rate_pct: float
            - dividend_payout_pct: float
        auto_generate: If True, automatically generate forecasts after saving

    Returns:
        Dictionary with operation results:
            - success: bool
            - scenario_id: int
            - assumptions_saved: int
            - forecast_generated: bool
            - forecast_years: List[int]
            - message: str

    Raises:
        ValueError: If scenario not found or validation fails
    """
    # 1. Validate scenario exists
    scenario = db.query(models.BudgetScenario).filter(
        models.BudgetScenario.id == scenario_id
    ).first()

    if not scenario:
        raise ValueError(f"Scenario {scenario_id} not found")

    # 2. Validate assumptions list
    if not assumptions_list or len(assumptions_list) == 0:
        raise ValueError("At least one assumption record is required")

    # 3. Validate all years are after base year
    for assumption in assumptions_list:
        if "forecast_year" not in assumption:
            raise ValueError("Each assumption must have a forecast_year")

        forecast_year = assumption["forecast_year"]
        if forecast_year <= scenario.base_year:
            raise ValueError(
                f"Forecast year {forecast_year} must be greater than base year {scenario.base_year}"
            )

    # 4. Check for duplicate years in input
    years = [a["forecast_year"] for a in assumptions_list]
    if len(years) != len(set(years)):
        raise ValueError("Duplicate forecast years found in assumptions list")

    # 5. Delete existing assumptions for this scenario
    db.query(models.BudgetAssumptions).filter(
        models.BudgetAssumptions.scenario_id == scenario_id
    ).delete()

    # 6. Insert new assumptions
    assumptions_saved = 0
    forecast_years_list = []

    for assumption_data in assumptions_list:
        # Create new assumption record
        db_assumption = models.BudgetAssumptions(
            scenario_id=scenario_id,
            forecast_year=assumption_data.get("forecast_year"),
            revenue_growth_pct=assumption_data.get("revenue_growth_pct", 0.0),
            other_revenue_growth_pct=assumption_data.get("other_revenue_growth_pct", 0.0),
            variable_materials_growth_pct=assumption_data.get("variable_materials_growth_pct", 0.0),
            fixed_materials_growth_pct=assumption_data.get("fixed_materials_growth_pct", 0.0),
            variable_services_growth_pct=assumption_data.get("variable_services_growth_pct", 0.0),
            fixed_services_growth_pct=assumption_data.get("fixed_services_growth_pct", 0.0),
            rent_growth_pct=assumption_data.get("rent_growth_pct", 0.0),
            personnel_growth_pct=assumption_data.get("personnel_growth_pct", 0.0),
            other_costs_growth_pct=assumption_data.get("other_costs_growth_pct", 0.0),
            investments=assumption_data.get("investments", 0.0),
            receivables_short_growth_pct=assumption_data.get("receivables_short_growth_pct", 0.0),
            receivables_long_growth_pct=assumption_data.get("receivables_long_growth_pct", 0.0),
            payables_short_growth_pct=assumption_data.get("payables_short_growth_pct", 0.0),
            interest_rate_receivables=assumption_data.get("interest_rate_receivables", 0.0),
            interest_rate_payables=assumption_data.get("interest_rate_payables", 0.0),
            tax_rate=assumption_data.get("tax_rate", 27.9),
            fixed_materials_percentage=assumption_data.get("fixed_materials_percentage", 40.0),
            fixed_services_percentage=assumption_data.get("fixed_services_percentage", 40.0),
            depreciation_rate=assumption_data.get("depreciation_rate", 20.0),
            financing_amount=assumption_data.get("financing_amount", 0.0),
            financing_duration_years=assumption_data.get("financing_duration_years", 0.0),
            financing_interest_rate=assumption_data.get("financing_interest_rate", 0.0),
        )
        db.add(db_assumption)
        assumptions_saved += 1
        forecast_years_list.append(assumption_data["forecast_year"])

    # 7. Commit assumptions
    db.commit()

    # 8. Generate forecasts if requested
    forecast_generated = False
    if auto_generate:
        try:
            if scenario.scenario_type == "infrannuale":
                from calculations.intra_year_engine import IntraYearEngine
                engine = IntraYearEngine(db)
                engine.generate_projection(scenario_id)
            else:
                engine = ForecastEngine(db)
                engine.generate_forecast(scenario_id)
            forecast_generated = True
        except Exception as e:
            # If forecast generation fails, return success for assumptions but note failure
            return {
                "success": True,
                "scenario_id": scenario_id,
                "assumptions_saved": assumptions_saved,
                "forecast_generated": False,
                "forecast_years": forecast_years_list,
                "message": f"Assumptions saved successfully, but forecast generation failed: {str(e)}"
            }

    return {
        "success": True,
        "scenario_id": scenario_id,
        "assumptions_saved": assumptions_saved,
        "forecast_generated": forecast_generated,
        "forecast_years": sorted(forecast_years_list),
        "message": "Assumptions saved and forecast generated successfully" if forecast_generated
                   else "Assumptions saved successfully"
    }


def get_assumptions_for_scenario(
    db: Session,
    scenario_id: int
) -> List[models.BudgetAssumptions]:
    """
    Get all assumptions for a scenario, ordered by year.

    Args:
        db: Database session
        scenario_id: Budget scenario ID

    Returns:
        List of BudgetAssumptions ordered by forecast_year

    Raises:
        ValueError: If scenario not found
    """
    # Validate scenario exists
    scenario = db.query(models.BudgetScenario).filter(
        models.BudgetScenario.id == scenario_id
    ).first()

    if not scenario:
        raise ValueError(f"Scenario {scenario_id} not found")

    # Get assumptions ordered by year
    assumptions = db.query(models.BudgetAssumptions).filter(
        models.BudgetAssumptions.scenario_id == scenario_id
    ).order_by(models.BudgetAssumptions.forecast_year).all()

    return assumptions


def delete_assumptions_for_scenario(
    db: Session,
    scenario_id: int
) -> int:
    """
    Delete all assumptions for a scenario.

    Args:
        db: Database session
        scenario_id: Budget scenario ID

    Returns:
        Number of assumptions deleted

    Raises:
        ValueError: If scenario not found
    """
    # Validate scenario exists
    scenario = db.query(models.BudgetScenario).filter(
        models.BudgetScenario.id == scenario_id
    ).first()

    if not scenario:
        raise ValueError(f"Scenario {scenario_id} not found")

    # Delete assumptions
    count = db.query(models.BudgetAssumptions).filter(
        models.BudgetAssumptions.scenario_id == scenario_id
    ).delete()

    db.commit()

    return count
