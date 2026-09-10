"""
Budget Scenarios and Assumptions API endpoints
"""
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Body, Depends, HTTPException, status, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session, joinedload
from datetime import datetime
from decimal import Decimal
import logging
import sys
import os

logger = logging.getLogger(__name__)

# Add backend directory to Python path
backend_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from app.core.database import get_db
from app.core.auth import get_current_user_id
from app.core.ownership import validate_company_owned_by_user
from app.schemas import budget as budget_schemas
from app.schemas import forecast as forecast_schemas
from database import models
from calculations.forecast_engine import ForecastEngine

router = APIRouter()

_ASSUMPTION_JSON_FIELDS = {
    "financing_loans", "tax_temporary_differences", "sp_overrides",
}


def _json_safe_assumption_fields(values: Dict[str, Any]) -> Dict[str, Any]:
    """Convert nested Decimal-bearing assumption structures for JSON columns."""
    for field in _ASSUMPTION_JSON_FIELDS.intersection(values):
        values[field] = jsonable_encoder(values[field])
    return values


# ===== Validation Helper Functions =====

def validate_company_exists(company_id: int, user_id: str, db: Session) -> models.Company:
    """Validate company exists, belongs to user, and return it"""
    return validate_company_owned_by_user(db, company_id, user_id)


def validate_scenario_belongs_to_company(
    scenario_id: int,
    company_id: int,
    user_id: str,
    db: Session,
) -> models.BudgetScenario:
    """Validate company belongs to user and scenario belongs to company"""
    validate_company_owned_by_user(db, company_id, user_id)
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
    from database.queries import get_fy_prefer_full
    financial_year = get_fy_prefer_full(db, company_id, base_year)

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


def validate_scenario_input_data(
    company_id: int,
    base_year: int,
    scenario_type: str,
    db: Session,
    period_months: Optional[int] = None,
):
    """Validate the financial data a scenario needs to exist before use.

    Standard scenarios require the base year to have complete data.

    'infrannuale' scenarios are different: the base_year is the *reference*
    year, while the data actually imported is the *partial* year (base_year + 1).
    The reference year is OPTIONAL — when it is missing the engine falls back to
    pure annualization — so here we only require the *exact* partial period to
    exist.  A full year or a different partial period is never a substitute.
    """
    if scenario_type == "infrannuale":
        from database.queries import get_fy_full, get_fy_partial
        if period_months is None or not 1 <= period_months <= 12:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="An infrannuale scenario requires period_months between 1 and 12",
            )
        partial_year = base_year + 1
        if period_months == 12:
            # A 12-month infrannuale is a full year: it is stored as a full-year
            # record (period_months NULL/12), so validate against that.
            financial_year = get_fy_full(db, company_id, partial_year)
            missing_detail = (
                f"Full year {partial_year} not found for company {company_id}"
            )
        else:
            financial_year = get_fy_partial(
                db, company_id, partial_year, period_months
            )
            missing_detail = (
                f"Partial year {partial_year} ({period_months} months) not found "
                f"for company {company_id}"
            )
        if not financial_year:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=missing_detail,
            )
        if not financial_year.balance_sheet or not financial_year.income_statement:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Partial year {partial_year} is missing balance sheet or income statement data"
            )
        return

    validate_base_year_data(company_id, base_year, db)


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
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """
    List all budget scenarios for a company

    Optional filtering by is_active flag (0=inactive, 1=active)
    """
    # Validate company exists and belongs to user
    validate_company_exists(company_id, user_id, db)

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
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """
    Get a single budget scenario with optional details

    Set include_details=true to get nested assumptions and forecast years
    """
    # Validate company belongs to user
    validate_company_exists(company_id, user_id, db)

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
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """
    Create a new budget scenario

    Note: This creates the scenario metadata only.
    Use POST /scenarios/{id}/assumptions to add forecast assumptions.
    Use POST /scenarios/{id}/generate to generate forecasts.
    """
    # Validate company exists and belongs to user
    validate_company_exists(company_id, user_id, db)

    # Validate the data this scenario needs (base year, or partial year for infrannuale)
    validate_scenario_input_data(
        company_id,
        scenario_create.base_year,
        scenario_create.scenario_type,
        db,
        scenario_create.period_months,
    )

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
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """
    Update an existing budget scenario metadata

    Only provided fields will be updated
    """
    # Validate scenario belongs to company
    db_scenario = validate_scenario_belongs_to_company(scenario_id, company_id, user_id, db)

    # Validate the resolved scenario, not only a changed base year: changing the
    # period or switching to infrannuale changes which FinancialYear is required.
    supplied = scenario_update.model_fields_set
    resolved_base_year = (
        scenario_update.base_year if "base_year" in supplied else db_scenario.base_year
    )
    resolved_type = (
        scenario_update.scenario_type
        if "scenario_type" in supplied
        else db_scenario.scenario_type
    )
    resolved_period = (
        scenario_update.period_months
        if "period_months" in supplied
        else db_scenario.period_months
    )
    if supplied.intersection({"base_year", "scenario_type", "period_months"}):
        validate_scenario_input_data(
            company_id,
            resolved_base_year,
            resolved_type,
            db,
            resolved_period,
        )

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
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """
    Delete a budget scenario and all associated data

    This will cascade delete:
    - All budget assumptions
    - All forecast years
    - All forecasted balance sheets and income statements
    """
    # Validate scenario belongs to company
    db_scenario = validate_scenario_belongs_to_company(scenario_id, company_id, user_id, db)

    # Delete (cascade will handle related records)
    db.delete(db_scenario)
    db.commit()

    return None


# ===== Intra-Year Comparison Endpoint =====

@router.get(
    "/companies/{company_id}/scenarios/{scenario_id}/comparison",
    response_model=budget_schemas.IntraYearComparison,
    summary="Get intra-year comparison (partial year vs reference full year)"
)
def get_intra_year_comparison(
    company_id: int,
    scenario_id: int,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """
    Compare partial-year financial data with reference full year.

    Only valid for scenarios with scenario_type="infrannuale".
    Returns line-by-line comparison with percentages and annualized values.
    """
    scenario = validate_scenario_belongs_to_company(scenario_id, company_id, user_id, db)

    if scenario.scenario_type != "infrannuale":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Comparison is only available for infrannuale scenarios"
        )

    try:
        from calculations.intra_year_engine import IntraYearEngine
        engine = IntraYearEngine(db)
        return engine.get_comparison(scenario_id)
    except ValueError as e:
        logger.error(
            f"[COMPARISON] Failed for company={company_id} scenario={scenario_id} "
            f"base_year={scenario.base_year} period_months={scenario.period_months}: {e}"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# ===== Infrannuale AI Comments (Stampa tab) =====

@router.get(
    "/companies/{company_id}/scenarios/{scenario_id}/infrannuale/ai-comments",
    summary="Get stored infrannuale AI comments (Stampa tab)",
)
def get_infrannuale_ai_comments(
    company_id: int,
    scenario_id: int,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    validate_scenario_belongs_to_company(scenario_id, company_id, user_id, db)
    from app.services.ai_comments_service import get_infrannuale_comments
    return get_infrannuale_comments(db, scenario_id)


@router.post(
    "/companies/{company_id}/scenarios/{scenario_id}/infrannuale/ai-comments",
    summary="Generate infrannuale AI comments via Haiku and persist them",
)
def generate_infrannuale_ai_comments(
    company_id: int,
    scenario_id: int,
    ctx: Dict[str, Any] = Body(..., description="Pre-built context: scenario, income_map, balance_map, indicators, ratings"),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    validate_scenario_belongs_to_company(scenario_id, company_id, user_id, db)
    from app.services.ai_comments_service import (
        generate_infrannuale_comments,
        save_infrannuale_comments,
    )
    comments = generate_infrannuale_comments(ctx)
    if comments:
        save_infrannuale_comments(db, scenario_id, comments)
    return comments


@router.put(
    "/companies/{company_id}/scenarios/{scenario_id}/infrannuale/ai-comments",
    summary="Save user-edited infrannuale AI comments (no LLM call)",
)
def save_infrannuale_ai_comments(
    company_id: int,
    scenario_id: int,
    comments: Dict[str, str] = Body(...),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    validate_scenario_belongs_to_company(scenario_id, company_id, user_id, db)
    from app.services.ai_comments_service import save_infrannuale_comments
    save_infrannuale_comments(db, scenario_id, comments)
    return {"success": True}


# ===== Promote Infrannuale Projection =====

@router.post(
    "/companies/{company_id}/scenarios/{scenario_id}/promote",
    response_model=Any,
    summary="Promote infrannuale projection to full-year FinancialYear"
)
def promote_projection(
    company_id: int,
    scenario_id: int,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """
    Copy the infrannuale projection into a proper FinancialYear record
    so it can be used as base year for budget scenarios.

    Only valid for scenarios with scenario_type="infrannuale" that have
    a generated projection (ForecastYear).
    """
    scenario = validate_scenario_belongs_to_company(scenario_id, company_id, user_id, db)

    if scenario.scenario_type != "infrannuale":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only infrannuale scenarios can be promoted"
        )

    try:
        from app.services.promote_service import promote_projection_to_financial_year
        result = promote_projection_to_financial_year(db, scenario_id)
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# ===== Budget Assumptions Endpoints =====

@router.get(
    "/companies/{company_id}/scenarios/{scenario_id}/assumptions",
    response_model=List[budget_schemas.BudgetAssumptions]
)
def list_budget_assumptions(
    company_id: int,
    scenario_id: int,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """
    Get all budget assumptions for a scenario

    Returns assumptions ordered by forecast year (ascending)
    """
    # Validate scenario belongs to company
    validate_scenario_belongs_to_company(scenario_id, company_id, user_id, db)

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
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """
    Create budget assumptions for a forecast year

    Each scenario can have multiple assumption records (one per forecast year)
    """
    # Validate scenario belongs to company
    scenario = validate_scenario_belongs_to_company(scenario_id, company_id, user_id, db)

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
    db_assumptions = models.BudgetAssumptions(**_json_safe_assumption_fields(
        assumptions_create.model_dump()
    ))
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
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """
    Update budget assumptions for a specific forecast year, then regenerate
    the forecast in the SAME transaction.

    Only provided fields will be updated. A rejected regeneration rolls back
    the update: a GET afterward reads the assumptions exactly as they were
    before this call (CLAUDE.md § Previsionale/Frontend -- an override the
    engine rejects is never persisted, only applied-and-reflected or neither).
    """
    from app.services import assumptions_service

    # Validate scenario belongs to company
    scenario = validate_scenario_belongs_to_company(scenario_id, company_id, user_id, db)

    # Update only provided fields
    update_data = _json_safe_assumption_fields(
        assumptions_update.model_dump(exclude_unset=True)
    )

    try:
        db_assumptions = assumptions_service.update_single_year_assumptions(
            db, scenario, year, update_data
        )
    except LookupError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Forecast generation failed: {str(e)}"
        )
    except Exception as e:
        logger.exception(
            "Forecast regeneration failed after assumptions update, scenario=%s year=%s",
            scenario_id, year,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error during forecast generation: {str(e)}"
        )

    return db_assumptions


@router.delete(
    "/companies/{company_id}/scenarios/{scenario_id}/assumptions/{year}",
    status_code=status.HTTP_204_NO_CONTENT
)
def delete_budget_assumptions(
    company_id: int,
    scenario_id: int,
    year: int,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """
    Delete budget assumptions for a specific forecast year

    This will also delete the associated forecast year and forecasted statements (cascade)
    """
    # Validate scenario belongs to company
    validate_scenario_belongs_to_company(scenario_id, company_id, user_id, db)

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


@router.put(
    "/companies/{company_id}/scenarios/{scenario_id}/assumptions",
    response_model=Any,
    summary="Bulk upsert assumptions for all forecast years"
)
def bulk_upsert_assumptions(
    company_id: int,
    scenario_id: int,
    request: Any = Body(...),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """
    Bulk insert or update assumptions for all forecast years at once.

    **Simplified workflow:**
    1. User sets assumptions for all years (3 or 5) in one call
    2. API automatically generates forecast (if auto_generate=true)
    3. Done!

    **Request body:**
    ```json
    {
        "assumptions": [
            {
                "forecast_year": 2025,
                "revenue_growth_pct": 5.0,
                "material_cost_growth_pct": 3.0,
                "service_cost_growth_pct": 2.5,
                "personnel_cost_growth_pct": 2.0,
                "capex_tangible": 50000.00,
                "capex_intangible": 10000.00,
                ...
            },
            { "forecast_year": 2026, ... },
            { "forecast_year": 2027, ... }
        ],
        "auto_generate": true
    }
    ```

    **This replaces:**
    - Individual POST /assumptions (per year)
    - Individual PUT /assumptions/{year} (per year)
    - Separate POST /generate call

    **Result:**
    - All assumptions saved in one transaction
    - Forecast automatically generated
    - Frontend needs only ONE API call instead of 4+
    """
    from app.services import assumptions_service
    from app.schemas import analysis as analysis_schemas

    # Validate scenario belongs to company
    validate_scenario_belongs_to_company(scenario_id, company_id, user_id, db)

    try:
        # Parse request body
        if isinstance(request, dict):
            request_data = request
        else:
            request_data = request.model_dump() if hasattr(request, 'model_dump') else request

        assumptions_list = request_data.get("assumptions", [])
        auto_generate = request_data.get("auto_generate", True)

        # Call service layer
        result = assumptions_service.bulk_upsert_assumptions(
            db=db,
            scenario_id=scenario_id,
            assumptions_list=assumptions_list,
            auto_generate=auto_generate
        )

        return result

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.exception("Error saving assumptions for scenario=%s", scenario_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error saving assumptions: {str(e)}"
        )


# ===== CE Override (direct forecast editing) =====

@router.patch(
    "/companies/{company_id}/scenarios/{scenario_id}/ce-override",
    response_model=Any,
    summary="Batch-patch CE overrides and regenerate forecast"
)
def patch_ce_override(
    company_id: int,
    scenario_id: int,
    request: Any = Body(...),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """
    Update one or more CE overrides, then regenerate the forecast once, in
    the SAME transaction: a rejected regeneration rolls back the WHOLE
    batch, not just the last entry (CLAUDE.md § Previsionale/Frontend -- an
    override the engine rejects is never persisted).

    **Request body:**
    ```json
    {
        "overrides": [
            { "forecast_year": 2025, "field": "ce01_override", "value": 1200000.00 },
            { "forecast_year": 2025, "field": "ce05_override", "value": null },
            { "forecast_year": 2026, "field": "ce01_override", "value": 1300000.00 }
        ]
    }
    ```

    Set `value` to `null` to clear an override and revert to engine calculation.
    """
    from app.services import assumptions_service

    scenario = validate_scenario_belongs_to_company(scenario_id, company_id, user_id, db)

    if isinstance(request, dict):
        request_data = request
    else:
        request_data = request.model_dump() if hasattr(request, 'model_dump') else request

    overrides = request_data.get("overrides", [])

    try:
        applied = assumptions_service.apply_ce_overrides(db, scenario, overrides)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Forecast regeneration failed after CE override patch")
        raise HTTPException(
            status_code=500,
            detail=f"Forecast regeneration failed, no override was applied: {str(e)}"
        )

    return {"success": True, "applied": applied}


# Una sola copia: alla rotta CE equivalente non serve, perche' lei scrive nelle
# colonne `ce*_override` (Numeric), dove un Decimal non cambia forma;
# qui invece il valore finisce dentro un sacco JSON, e la forma e' contenuto.
def _sp_override_json_value(value: Optional[Decimal]) -> Any:
    """Rida' al valore validato da Pydantic la forma numerica del corpo.

    `apply_sp_overrides` scrive il valore com'e' nel sacco JSON `sp_overrides`,
    e quel sacco finora conteneva i numeri usciti da `json.loads` della
    richiesta. Passare un Decimal cambierebbe la forma salvata:
    `model_dump(mode="json")` (Pydantic 2) lo gira in STRINGA, `jsonable_encoder`
    in float anche dove il corpo ne portava uno intero (`1000` -> `1000.0`). Un
    integrale resta `int`, il resto e' `float` -- identico a oggi, e il motore
    rilegge comunque con `Decimal(str(...))`, quindi il previsionale non si
    muove di un centesimo (M2).
    """
    if value is None:
        return None
    if value == value.to_integral_value():
        return int(value)
    return float(value)


@router.patch(
    "/companies/{company_id}/scenarios/{scenario_id}/sp-override",
    response_model=Any,
    summary="Batch-patch SP overrides across one or more years and regenerate forecast once"
)
def patch_sp_override(
    company_id: int,
    scenario_id: int,
    request: budget_schemas.SpOverrideRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """
    Update one or more SP overrides, possibly across MULTIPLE forecast
    years, then regenerate the forecast once, in the SAME transaction: a
    rejected regeneration rolls back the WHOLE batch -- every year touched
    by this call, not just one (CLAUDE.md § Previsionale/Frontend -- an
    override the engine rejects is never persisted; "una correzione che
    tocca piu' campi si applica tutta o niente").

    Replaces looping N `PUT /assumptions/{year}` calls in parallel for a
    multi-year edit (SP Prev., giro di correzione 3): after giro 2 each PUT
    regenerates the WHOLE scenario in its own transaction, and N of those in
    parallel on SQLite risked "database is locked" plus spurious rejections
    (a year validated without yet seeing the sibling year's uncommitted
    edit). This route applies every edit first, then regenerates once.

    **Request body:**
    ```json
    {
        "overrides": [
            { "forecast_year": 2025, "field": "sp16a_debiti_banche_breve", "value": 400000.55 },
            { "forecast_year": 2026, "field": "sp16a_debiti_banche_breve", "value": 350000.00 },
            { "forecast_year": 2025, "field": "sp06a_crediti_clienti_breve", "value": null }
        ]
    }
    ```

    `field` is the key inside that year's `sp_overrides` JSON bag -- there is
    no fixed allowlist (unlike CE's `CE_OVERRIDE_FIELDS`): a key the engine's
    result does not recognize is ignored in silence, same as every other
    `sp_overrides` write (CLAUDE.md § Previsionale). Set `value` to `null` to
    clear that key and revert to engine calculation. Multiple entries for the
    same year merge into that year's SAME bag.

    **Validation:** the body is checked by `budget_schemas.SpOverrideRequest`
    before anything is written or regenerated, so a non-numeric `value`, a
    NaN/Infinity, a missing `forecast_year` or an `overrides` that is not a
    list answers **422**. Before that they reached `Decimal(str(raw_value))`
    inside the engine, whose `decimal.InvalidOperation` is an `ArithmeticError`
    and not a `ValueError`, and the only answer this route could give was a
    500 (M2). Nothing was ever left written in either case -- the rollback was
    already correct, only the status code was not.
    """
    from app.services import assumptions_service

    scenario = validate_scenario_belongs_to_company(scenario_id, company_id, user_id, db)

    # Il corpo e' gia' valido qui: Pydantic ha rifiutato un 422 prima che si
    # scrivesse e si rigenerasse qualunque cosa (M2). `value` torna numero
    # nella forma che aveva nel corpo, perche' il sacco salvato non cambi.
    overrides = [
        {
            "forecast_year": entry.forecast_year,
            "field": entry.field,
            "value": _sp_override_json_value(entry.value),
        }
        for entry in request.overrides
    ]

    try:
        years_touched = assumptions_service.apply_sp_overrides(db, scenario, overrides)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Forecast regeneration failed after SP override patch")
        raise HTTPException(
            status_code=500,
            detail=f"Forecast regeneration failed, no override was applied: {str(e)}"
        )

    return {"success": True, "years": years_touched}


# ===== Forecast Generation Endpoint =====

@router.post(
    "/companies/{company_id}/scenarios/{scenario_id}/generate",
    response_model=forecast_schemas.ForecastGenerationResult
)
def generate_forecasts(
    company_id: int,
    scenario_id: int,
    clear_overrides: bool = Query(False, description="Clear all CE overrides before regenerating"),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """
    Generate (or regenerate) forecasts for all years in the scenario

    This will:
    1. Validate base year data exists
    2. Validate at least one assumption exists
    3. Call ForecastEngine to generate forecasted balance sheets and income statements
    4. Create/update ForecastYear, ForecastBalanceSheet, and ForecastIncomeStatement records
    5. Return summary statistics

    Pass ?clear_overrides=true to reset all manual CE overrides before regenerating.
    """
    # Validate scenario belongs to company
    scenario = validate_scenario_belongs_to_company(scenario_id, company_id, user_id, db)

    # Validate the data this scenario needs (base year, or partial year for infrannuale)
    validate_scenario_input_data(
        company_id,
        scenario.base_year,
        scenario.scenario_type,
        db,
        scenario.period_months,
    )

    # Validate at least one assumption exists
    assumptions = db.query(models.BudgetAssumptions).filter(
        models.BudgetAssumptions.scenario_id == scenario_id
    ).all()

    if not assumptions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot generate forecast: no assumptions found for scenario {scenario_id}. Add assumptions first."
        )

    # Clear all CE overrides if requested
    if clear_overrides:
        for assumption in assumptions:
            for col in assumption.__table__.columns:
                if col.name.endswith("_override"):
                    setattr(assumption, col.name, None)
        db.commit()

    # Generate forecast using appropriate engine
    try:
        if scenario.scenario_type == "infrannuale":
            from calculations.intra_year_engine import IntraYearEngine
            engine = IntraYearEngine(db)
            result = engine.generate_projection(scenario_id)
        else:
            engine = ForecastEngine(db)
            result = engine.generate_forecast(scenario_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Forecast generation failed: {str(e)}"
        )
    except Exception as e:
        logger.exception("Forecast generation error for scenario=%s", scenario_id)
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
        diagnostics=result.get("diagnostics", []),
        generated_at=datetime.utcnow()
    )


@router.post(
    "/companies/{company_id}/scenarios/{scenario_id}/preview",
    response_model=forecast_schemas.ForecastPreviewResponse,
    summary="Anteprima del previsionale dalle ipotesi nel corpo, senza salvare",
)
def preview_forecast_route(
    company_id: int,
    scenario_id: int,
    request: Any = Body(...),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Stesso corpo del bulk (`{"assumptions": [...]}`), nessuna scrittura.
    Risponde 200 anche se il motore si ferma: leggere `error`, non lo status."""
    from app.services import forecast_preview_service
    validate_scenario_belongs_to_company(scenario_id, company_id, user_id, db)
    request_data = request if isinstance(request, dict) else request.model_dump()
    try:
        return forecast_preview_service.preview_forecast(
            db, scenario_id, request_data.get("assumptions", []))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        # Stessa rete del bulk (generate_forecasts sopra): un guasto inatteso
        # nel motore non deve mai uscire come 500 anonimo. Non e' una scusa per
        # non chiudere le cause vere (coalescenza dei null, forecast_year non
        # numerico) dentro il servizio -- quelle restano ValueError -> 400.
        logger.exception("Forecast preview failed for scenario=%s", scenario_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error during forecast preview: {str(e)}"
        )


# ===== Forecast Data Access Endpoints =====

@router.get(
    "/companies/{company_id}/scenarios/{scenario_id}/forecasts",
    response_model=List[forecast_schemas.ForecastYearSummary]
)
def list_forecast_years(
    company_id: int,
    scenario_id: int,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """
    List all forecast years for a scenario

    Returns forecast year metadata (id, year, timestamps)
    """
    # Validate scenario belongs to company
    validate_scenario_belongs_to_company(scenario_id, company_id, user_id, db)

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
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """
    Get forecasted balance sheet for a specific year

    Returns all balance sheet line items and calculated properties
    """
    # Validate scenario belongs to company
    validate_scenario_belongs_to_company(scenario_id, company_id, user_id, db)

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
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """
    Get forecasted income statement for a specific year

    Returns all income statement line items and calculated properties
    """
    # Validate scenario belongs to company
    validate_scenario_belongs_to_company(scenario_id, company_id, user_id, db)

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
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
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
    scenario = validate_scenario_belongs_to_company(scenario_id, company_id, user_id, db)

    # Get base year
    base_year = scenario.base_year

    # Get company
    company = validate_company_exists(company_id, user_id, db)

    # Get all forecast years for this scenario
    forecast_years = db.query(models.ForecastYear).filter(
        models.ForecastYear.scenario_id == scenario_id
    ).order_by(models.ForecastYear.year).all()

    if not forecast_years:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No forecast data found for scenario {scenario_id}"
        )

    # Get historical data (full-year records up to and including base year)
    historical_years = db.query(models.FinancialYear).filter(
        models.FinancialYear.company_id == company_id,
        models.FinancialYear.year <= base_year,
        (models.FinancialYear.period_months == None) | (models.FinancialYear.period_months == 12),
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
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
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
    scenario = validate_scenario_belongs_to_company(scenario_id, company_id, user_id, db)

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
        logger.exception("Error calculating detailed cashflow for scenario=%s", scenario_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error calculating detailed cashflow: {str(e)}"
        )


@router.get(
    "/companies/{company_id}/scenarios/{scenario_id}/ratios",
    response_model=Any,
    summary="Get all financial ratios for scenario (historical + forecast)"
)
def get_ratios_scenario(
    company_id: int,
    scenario_id: int,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """
    Get all financial ratios for historical and forecast years

    Timeline: historical years → forecast years

    Returns comprehensive ratios including:
    - Working capital metrics
    - Liquidity, solvency, profitability ratios
    - Activity, coverage, turnover ratios
    - Extended profitability, efficiency, break-even analysis
    """
    from app.services import calculation_service

    # Validate scenario
    scenario = validate_scenario_belongs_to_company(scenario_id, company_id, user_id, db)

    try:
        result = calculation_service.calculate_ratios_historical_and_forecast(
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
        logger.exception("Error calculating ratios for scenario=%s", scenario_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error calculating ratios: {str(e)}"
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
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """
    Get detailed cash flow statement for historical years only (no scenario)

    Returns comprehensive cash flow with all components for specified year range.
    Requires at least 2 years of data (start_year and start_year-1 as base).
    """
    from app.services import calculation_service

    # Validate company
    validate_company_exists(company_id, user_id, db)

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
        logger.exception("Error calculating detailed cashflow for scenario=%s", scenario_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error calculating detailed cashflow: {str(e)}"
        )
