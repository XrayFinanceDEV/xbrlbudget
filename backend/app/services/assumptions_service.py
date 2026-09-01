"""
Assumptions Service - Bulk operations for budget assumptions

Handles bulk insert/update of forecast assumptions with automatic forecast generation.
"""
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime
from fastapi.encoders import jsonable_encoder
import sys
import os

# Add backend directory to Python path
backend_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from database import models
from calculations.forecast_engine import ForecastEngine, prune_out_of_plan_forecast_years


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
            intangible_investments=assumption_data.get("intangible_investments", 0.0),
            tangible_investments=assumption_data.get("tangible_investments", 0.0),
            asset_disposal_nbv=assumption_data.get("asset_disposal_nbv", None),
            asset_disposal_proceeds=assumption_data.get("asset_disposal_proceeds", None),
            receivables_short_growth_pct=assumption_data.get("receivables_short_growth_pct", 0.0),
            receivables_long_growth_pct=assumption_data.get("receivables_long_growth_pct", 0.0),
            payables_short_growth_pct=assumption_data.get("payables_short_growth_pct", 0.0),
            dso_days=assumption_data.get("dso_days", None),
            dio_days=assumption_data.get("dio_days", None),
            dpo_days=assumption_data.get("dpo_days", None),
            existing_debt_repayment_years=assumption_data.get("existing_debt_repayment_years", None),
            altri_finanz_repayment_years=assumption_data.get("altri_finanz_repayment_years", None),
            cash_sweep_enabled=assumption_data.get("cash_sweep_enabled", False) or False,
            cash_sweep_min_cash=assumption_data.get("cash_sweep_min_cash", None),
            tfr_accrual_suspended=assumption_data.get("tfr_accrual_suspended", False) or False,
            previdenza_scales_with_personnel=assumption_data.get("previdenza_scales_with_personnel", False) or False,
            interest_rate_receivables=assumption_data.get("interest_rate_receivables", 0.0),
            interest_rate_payables=assumption_data.get("interest_rate_payables", 0.0),
            tax_rate=assumption_data.get("tax_rate", 27.9),
            tax_advances_paid=assumption_data.get("tax_advances_paid", 0.0) or 0.0,
            tax_temporary_differences=jsonable_encoder(
                assumption_data.get("tax_temporary_differences", None)
            ),
            fixed_materials_percentage=assumption_data.get("fixed_materials_percentage", 40.0),
            fixed_services_percentage=assumption_data.get("fixed_services_percentage", 40.0),
            depreciation_rate=assumption_data.get("depreciation_rate", 20.0),
            depreciation_rate_intangible=assumption_data.get("depreciation_rate_intangible", 20.0),
            # Coalesce null -> 0: the UI now allows clearing these fields (sends null),
            # but the columns are NOT NULL. 0 == "no financing", the existing default
            # semantics. (.get(key, 0.0) only defaults on a MISSING key, not an explicit null.)
            financing_amount=assumption_data.get("financing_amount") or 0.0,
            financing_duration_years=assumption_data.get("financing_duration_years") or 0.0,
            financing_interest_rate=assumption_data.get("financing_interest_rate") or 0.0,
            financing_loans=jsonable_encoder(assumption_data.get("financing_loans", None)),
            sp01_growth_pct=assumption_data.get("sp01_growth_pct", None),
            sp04_growth_pct=assumption_data.get("sp04_growth_pct", None),
            sp06e_growth_pct=assumption_data.get("sp06e_growth_pct", None),
            sp06f_growth_pct=assumption_data.get("sp06f_growth_pct", None),
            sp08_growth_pct=assumption_data.get("sp08_growth_pct", None),
            sp10_growth_pct=assumption_data.get("sp10_growth_pct", None),
            sp14_growth_pct=assumption_data.get("sp14_growth_pct", None),
            sp16e_growth_pct=assumption_data.get("sp16e_growth_pct", None),
            sp16f_growth_pct=assumption_data.get("sp16f_growth_pct", None),
            sp16g_growth_pct=assumption_data.get("sp16g_growth_pct", None),
            sp17d_growth_pct=assumption_data.get("sp17d_growth_pct", None),
            sp17e_growth_pct=assumption_data.get("sp17e_growth_pct", None),
            sp17f_growth_pct=assumption_data.get("sp17f_growth_pct", None),
            sp17g_growth_pct=assumption_data.get("sp17g_growth_pct", None),
            sp18_growth_pct=assumption_data.get("sp18_growth_pct", None),
            sp_overrides=jsonable_encoder(assumption_data.get("sp_overrides", None)),
            ce02_override=assumption_data.get("ce02_override", None),
            ce03_override=assumption_data.get("ce03_override", None),
            ce03a_override=assumption_data.get("ce03a_override", None),
            ce10_override=assumption_data.get("ce10_override", None),
            ce11_override=assumption_data.get("ce11_override", None),
            ce13_override=assumption_data.get("ce13_override", None),
            ce14_override=assumption_data.get("ce14_override", None),
            ce15_override=assumption_data.get("ce15_override", None),
            ce16_override=assumption_data.get("ce16_override", None),
            ce17_override=assumption_data.get("ce17_override", None),
            ce18_override=assumption_data.get("ce18_override", None),
            ce19_override=assumption_data.get("ce19_override", None),
            ce01_override=assumption_data.get("ce01_override", None),
            ce04_override=assumption_data.get("ce04_override", None),
            ce05_override=assumption_data.get("ce05_override", None),
            ce06_override=assumption_data.get("ce06_override", None),
            ce07_override=assumption_data.get("ce07_override", None),
            ce08_override=assumption_data.get("ce08_override", None),
            ce08a_override=assumption_data.get("ce08a_override", None),
            ce08b_override=assumption_data.get("ce08b_override", None),
            ce08c_override=assumption_data.get("ce08c_override", None),
            ce08d_override=assumption_data.get("ce08d_override", None),
            ce09_override=assumption_data.get("ce09_override", None),
            ce09a_override=assumption_data.get("ce09a_override", None),
            ce09b_override=assumption_data.get("ce09b_override", None),
            ce09c_override=assumption_data.get("ce09c_override", None),
            ce09d_override=assumption_data.get("ce09d_override", None),
            ce11b_override=assumption_data.get("ce11b_override", None),
            ce12_override=assumption_data.get("ce12_override", None),
            ce17a_override=assumption_data.get("ce17a_override", None),
            ce17b_override=assumption_data.get("ce17b_override", None),
            ce20_override=assumption_data.get("ce20_override", None),
        )
        db.add(db_assumption)
        assumptions_saved += 1
        forecast_years_list.append(assumption_data["forecast_year"])

    # 7. Gli anni fuori piano si potano QUI, non solo dentro il motore: le
    # ipotesi vengono committate qui sotto, mentre il motore puo' non girare
    # affatto (`auto_generate=false`) o fallire — e in quel caso la sua
    # transazione, potatura compresa, viene annullata mentre le ipotesi salvate
    # restano. In entrambi i casi /analysis conterebbe ancora gli anni in piu'
    # coi numeri del salvataggio precedente, sotto un avviso che parla solo di
    # generazione.
    #
    # Sta PRIMA del commit, non dopo: cosi' e' atomica col salvataggio delle
    # ipotesi (una DELETE che fallisce annulla tutto e l'errore e' onesto),
    # mentre dopo il commit avrebbe potuto restituire 500 «errore nel
    # salvataggio» su ipotesi gia' persistite e previsionale non rigenerato.
    # L'infrannuale e' escluso: la sua proiezione e' un anno solo e non segue
    # gli anni delle ipotesi.
    if scenario.scenario_type != "infrannuale":
        prune_out_of_plan_forecast_years(db, scenario_id, forecast_years_list)

    # 7-bis. Commit assumptions
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
