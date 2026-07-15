"""
Financial Year API endpoints
"""
import json
from typing import List, Dict, Any, Optional
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
import sys
import os

# Add backend directory to Python path
backend_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from app.core.database import get_db
from app.core.auth import get_current_user_id
from app.core.ownership import validate_company_owned_by_user
from app.schemas import financial_year as schemas
from app.schemas import balance_sheet as bs_schemas
from app.schemas import income_statement as is_schemas
from app.schemas.adjustments import AdjustableFinancialYear, AdjustmentsUpdate
from database import models
from database.queries import get_fy_prefer_full

router = APIRouter()


@router.get("/companies/{company_id}/years/{year}", response_model=schemas.FinancialYear)
def get_financial_year(
    company_id: int,
    year: int,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Get financial year for a specific company and year"""
    validate_company_owned_by_user(db, company_id, user_id)
    fy = get_fy_prefer_full(db, company_id, year)

    if not fy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Financial year {year} for company {company_id} not found"
        )

    return fy


@router.post("/companies/{company_id}/years", response_model=schemas.FinancialYear, status_code=status.HTTP_201_CREATED)
def create_financial_year(
    company_id: int,
    year_data: schemas.FinancialYearCreate,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Create a new financial year for a company"""
    validate_company_owned_by_user(db, company_id, user_id)

    # Check if year already exists for this company
    existing = db.query(models.FinancialYear).filter(
        models.FinancialYear.company_id == company_id,
        models.FinancialYear.year == year_data.year
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Year {year_data.year} already exists for company {company_id}"
        )

    # Create financial year
    db_year = models.FinancialYear(company_id=company_id, year=year_data.year)
    db.add(db_year)
    db.commit()
    db.refresh(db_year)

    # Create empty balance sheet and income statement
    db_bs = models.BalanceSheet(financial_year_id=db_year.id)
    db_is = models.IncomeStatement(financial_year_id=db_year.id)

    db.add(db_bs)
    db.add(db_is)
    db.commit()

    return db_year


@router.delete("/companies/{company_id}/years/{year}", status_code=status.HTTP_204_NO_CONTENT)
def delete_financial_year(
    company_id: int,
    year: int,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Delete a financial year and all associated financial statements"""
    validate_company_owned_by_user(db, company_id, user_id)

    fy = db.query(models.FinancialYear).filter(
        models.FinancialYear.company_id == company_id,
        models.FinancialYear.year == year
    ).first()

    if not fy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Financial year {year} for company {company_id} not found"
        )

    db.delete(fy)
    db.commit()
    return None


@router.get("/companies/{company_id}/years/{year}/balance-sheet", response_model=bs_schemas.BalanceSheet)
def get_balance_sheet(
    company_id: int,
    year: int,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Get balance sheet for a specific company and year"""
    validate_company_owned_by_user(db, company_id, user_id)
    fy = get_fy_prefer_full(db, company_id, year)

    if not fy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Financial year {year} for company {company_id} not found"
        )

    if not fy.balance_sheet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Balance sheet for year {year} not found"
        )

    return fy.balance_sheet


@router.put("/companies/{company_id}/years/{year}/balance-sheet", response_model=bs_schemas.BalanceSheet)
def update_balance_sheet(
    company_id: int,
    year: int,
    bs_update: bs_schemas.BalanceSheetUpdate,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Update balance sheet for a specific year"""
    validate_company_owned_by_user(db, company_id, user_id)
    fy = get_fy_prefer_full(db, company_id, year)

    if not fy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Financial year {year} for company {company_id} not found"
        )

    if not fy.balance_sheet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Balance sheet for year {year} not found"
        )

    # Update only provided fields
    update_data = bs_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(fy.balance_sheet, field, value)

    db.commit()
    db.refresh(fy.balance_sheet)
    return fy.balance_sheet


@router.get("/companies/{company_id}/years/{year}/income-statement", response_model=is_schemas.IncomeStatement)
def get_income_statement(
    company_id: int,
    year: int,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Get income statement for a specific company and year"""
    validate_company_owned_by_user(db, company_id, user_id)
    fy = get_fy_prefer_full(db, company_id, year)

    if not fy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Financial year {year} for company {company_id} not found"
        )

    if not fy.income_statement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Income statement for year {year} not found"
        )

    return fy.income_statement


@router.put("/companies/{company_id}/years/{year}/income-statement", response_model=is_schemas.IncomeStatement)
def update_income_statement(
    company_id: int,
    year: int,
    is_update: is_schemas.IncomeStatementUpdate,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Update income statement for a specific year"""
    validate_company_owned_by_user(db, company_id, user_id)
    fy = get_fy_prefer_full(db, company_id, year)

    if not fy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Financial year {year} for company {company_id} not found"
        )

    if not fy.income_statement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Income statement for year {year} not found"
        )

    # Update only provided fields
    update_data = is_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(fy.income_statement, field, value)

    db.commit()
    db.refresh(fy.income_statement)
    return fy.income_statement


# ===== Rettifiche (Adjustments) Endpoints =====

# Helper: list of SP/CE column names from the ORM model (exclude non-financial columns)
_BS_SKIP = {"id", "financial_year_id", "created_at", "updated_at"}
_IS_SKIP = {"id", "financial_year_id", "created_at", "updated_at"}


def _bs_to_dict(bs: models.BalanceSheet) -> Dict[str, float]:
    """Convert BalanceSheet ORM object to dict of {column: float}."""
    result = {}
    for col in models.BalanceSheet.__table__.columns:
        if col.name in _BS_SKIP:
            continue
        val = getattr(bs, col.name)
        result[col.name] = float(val) if val is not None else 0.0
    return result


def _is_to_dict(is_obj: models.IncomeStatement) -> Dict[str, float]:
    """Convert IncomeStatement ORM object to dict of {column: float}."""
    result = {}
    for col in models.IncomeStatement.__table__.columns:
        if col.name in _IS_SKIP:
            continue
        val = getattr(is_obj, col.name)
        result[col.name] = float(val) if val is not None else 0.0
    return result


def _find_fy(db: Session, company_id: int, year: int, period_months: Optional[int] = None) -> Optional[models.FinancialYear]:
    """Find a FinancialYear by company, year, and optionally period_months."""
    query = db.query(models.FinancialYear).filter(
        models.FinancialYear.company_id == company_id,
        models.FinancialYear.year == year,
    )
    if period_months is not None and period_months < 12:
        query = query.filter(models.FinancialYear.period_months == period_months)
    else:
        query = query.filter(
            (models.FinancialYear.period_months == None) | (models.FinancialYear.period_months == 12)
        )
    return query.first()


@router.get(
    "/companies/{company_id}/years/{year}/adjustable",
    response_model=AdjustableFinancialYear,
)
def get_adjustable_financial_year(
    company_id: int,
    year: int,
    period_months: Optional[int] = Query(None),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """
    Get BS + IS data for the Rettifiche tab.
    On first call (no snapshot), saves current BS/IS as the original snapshot.
    Uses year + period_months to find the correct FinancialYear.
    """
    validate_company_owned_by_user(db, company_id, user_id)

    fy = _find_fy(db, company_id, year, period_months)
    if not fy:
        raise HTTPException(status_code=404, detail="Financial year not found")
    if not fy.balance_sheet or not fy.income_statement:
        raise HTTPException(status_code=404, detail="Balance sheet or income statement not found")

    bs_dict = _bs_to_dict(fy.balance_sheet)
    is_dict = _is_to_dict(fy.income_statement)

    # Create snapshot on first access (if not already saved)
    if fy.original_bs_snapshot is None:
        fy.original_bs_snapshot = json.dumps(bs_dict)
        fy.original_is_snapshot = json.dumps(is_dict)
        db.commit()

    original_bs = json.loads(fy.original_bs_snapshot) if fy.original_bs_snapshot else None
    original_is = json.loads(fy.original_is_snapshot) if fy.original_is_snapshot else None
    rettifiche_log = json.loads(fy.rettifiche_log) if fy.rettifiche_log else []

    return AdjustableFinancialYear(
        financial_year_id=fy.id,
        year=fy.year,
        period_months=fy.period_months,
        balance_sheet=bs_dict,
        income_statement=is_dict,
        original_balance_sheet=original_bs,
        original_income_statement=original_is,
        rettifiche_log=rettifiche_log,
    )


RETTIFICHE_LOG_MAX = 20

# Tolerance for the server-side balance check on PUT /adjustments: the legit
# frontend keeps edits balanced by double-entry and plugs ≤ €5 import-rounding
# gaps into sp09 (reconcileSubfields), so €5 of drift per save is normal noise.
ADJUSTMENTS_BALANCE_TOL = Decimal("5")


def _bs_imbalance(bs_fields: Dict[str, Any]) -> Decimal:
    """|attivo − passivo| of a balance-sheet field dict (full DB field names).

    Uses the shared IV-CEE aggregate field lists so this stays consistent with
    check_quadratura. Missing/None fields count as 0.
    """
    from importers.iv_cee_hierarchy import _ATTIVO_FIELDS, _PASSIVO_FIELDS
    att = sum((Decimal(str(bs_fields.get(f) or 0)) for f in _ATTIVO_FIELDS), Decimal("0"))
    pas = sum((Decimal(str(bs_fields.get(f) or 0)) for f in _PASSIVO_FIELDS), Decimal("0"))
    return abs(att - pas)


@router.put(
    "/companies/{company_id}/years/{year}/adjustments",
    response_model=AdjustableFinancialYear,
)
def save_adjustments(
    company_id: int,
    year: int,
    payload: AdjustmentsUpdate,
    period_months: Optional[int] = Query(None),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """
    Save corrected BS + IS values from the Rettifiche tab.
    Only updates columns that exist on the ORM model.
    """
    validate_company_owned_by_user(db, company_id, user_id)

    fy = _find_fy(db, company_id, year, period_months)
    if not fy:
        raise HTTPException(status_code=404, detail="Financial year not found")
    if not fy.balance_sheet or not fy.income_statement:
        raise HTTPException(status_code=404, detail="Balance sheet or income statement not found")

    # Ensure snapshot exists before overwriting
    if fy.original_bs_snapshot is None:
        fy.original_bs_snapshot = json.dumps(_bs_to_dict(fy.balance_sheet))
        fy.original_is_snapshot = json.dumps(_is_to_dict(fy.income_statement))

    # Server-side balance validation: the frontend keeps rettifiche balanced by
    # double-entry, but a direct API client could persist an arbitrarily unbalanced
    # sheet with no check at all. Merge the payload over the CURRENT record (robust
    # to partial payloads) and reject a save that WORSENS the imbalance beyond the
    # tolerance — while still allowing saves on a record that was already unbalanced
    # at import (the user must be able to work on it, and double-entry edits keep
    # the gap constant).
    bs_columns = {col.name for col in models.BalanceSheet.__table__.columns} - _BS_SKIP
    current_bs = _bs_to_dict(fy.balance_sheet)
    merged_bs = dict(current_bs)
    merged_bs.update({f: v for f, v in payload.balance_sheet.items() if f in bs_columns})
    new_imb = _bs_imbalance(merged_bs)
    cur_imb = _bs_imbalance(current_bs)
    if new_imb > max(cur_imb, Decimal("0")) + ADJUSTMENTS_BALANCE_TOL:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Rettifiche sbilanciate: attivo−passivo = {new_imb:,.2f} € "
                f"(prima del salvataggio era {cur_imb:,.2f} €). Ogni rettifica deve "
                f"essere in partita doppia."
            ),
        )
    for field, value in payload.balance_sheet.items():
        if field in bs_columns:
            setattr(fy.balance_sheet, field, Decimal(str(value)))

    # Update IS fields
    is_columns = {col.name for col in models.IncomeStatement.__table__.columns} - _IS_SKIP
    for field, value in payload.income_statement.items():
        if field in is_columns:
            setattr(fy.income_statement, field, Decimal(str(value)))

    # Persist rettifiche log if provided (max RETTIFICHE_LOG_MAX entries)
    if payload.rettifiche_log is not None:
        if len(payload.rettifiche_log) > RETTIFICHE_LOG_MAX:
            raise HTTPException(
                status_code=400,
                detail=f"Massimo {RETTIFICHE_LOG_MAX} rettifiche consentite",
            )
        fy.rettifiche_log = json.dumps([e.model_dump() for e in payload.rettifiche_log])

    db.commit()
    db.refresh(fy.balance_sheet)
    db.refresh(fy.income_statement)

    bs_dict = _bs_to_dict(fy.balance_sheet)
    is_dict = _is_to_dict(fy.income_statement)
    original_bs = json.loads(fy.original_bs_snapshot) if fy.original_bs_snapshot else None
    original_is = json.loads(fy.original_is_snapshot) if fy.original_is_snapshot else None
    rettifiche_log = json.loads(fy.rettifiche_log) if fy.rettifiche_log else []

    return AdjustableFinancialYear(
        financial_year_id=fy.id,
        year=fy.year,
        period_months=fy.period_months,
        balance_sheet=bs_dict,
        income_statement=is_dict,
        original_balance_sheet=original_bs,
        original_income_statement=original_is,
        rettifiche_log=rettifiche_log,
    )
