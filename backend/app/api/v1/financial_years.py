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

    # A calendar year may contain several exact partial periods and one full
    # year.  Treat 12 and NULL as the same full-year identity; never let a six-
    # month record block a nine-month or annual import.
    normalized_period = None if year_data.period_months in (None, 12) else year_data.period_months
    existing_query = db.query(models.FinancialYear).filter(
        models.FinancialYear.company_id == company_id,
        models.FinancialYear.year == year_data.year,
    )
    if normalized_period is None:
        existing_query = existing_query.filter(
            (models.FinancialYear.period_months == None)
            | (models.FinancialYear.period_months == 12)
        )
    else:
        existing_query = existing_query.filter(
            models.FinancialYear.period_months == normalized_period
        )
    existing = existing_query.first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(f"Period {year_data.year}/{normalized_period or 12}M already "
                    f"exists for company {company_id}")
        )

    # Create financial year
    db_year = models.FinancialYear(
        company_id=company_id,
        year=year_data.year,
        period_months=normalized_period,
        validation_status="draft",
        forecastable=False,
    )
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
        validation_status=fy.validation_status or "legacy",
        validation_report=(json.loads(fy.validation_report) if fy.validation_report else None),
        forecastable=bool(fy.forecastable),
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


def _validation_magnitudes(bs_fields: Dict[str, Any], ce_fields: Dict[str, Any]):
    """Comparable SP, CE/SP and hierarchy error magnitudes for adjustments."""
    from importers.iv_cee_hierarchy import check_quadratura

    q = check_quadratura(bs_fields, ce_fields, tol=Decimal("0.01"))
    ce_gap = (
        abs((q.utile_ce or Decimal("0")) - q.sp13)
        if q.utile_ce is not None else Decimal("0")
    )
    hierarchy_gap = sum(
        (abs(value) for value in q.hierarchy_differences.values()), Decimal("0")
    )
    return q, abs(q.sbilancio), ce_gap, hierarchy_gap


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
    is_columns = {col.name for col in models.IncomeStatement.__table__.columns} - _IS_SKIP
    current_is = _is_to_dict(fy.income_statement)
    merged_is = dict(current_is)
    merged_is.update({f: v for f, v in payload.income_statement.items() if f in is_columns})

    current_q, cur_imb, cur_ce_gap, cur_hierarchy_gap = _validation_magnitudes(
        current_bs, current_is
    )
    new_q, new_imb, new_ce_gap, new_hierarchy_gap = _validation_magnitudes(
        merged_bs, merged_is
    )
    worsened = []
    if new_imb > cur_imb + ADJUSTMENTS_BALANCE_TOL:
        worsened.append(f"Attivo−Passivo {cur_imb:,.2f}→{new_imb:,.2f}")
    if new_ce_gap > cur_ce_gap + ADJUSTMENTS_BALANCE_TOL:
        worsened.append(f"CE−SP13 {cur_ce_gap:,.2f}→{new_ce_gap:,.2f}")
    if new_hierarchy_gap > cur_hierarchy_gap + ADJUSTMENTS_BALANCE_TOL:
        worsened.append(
            f"aggregati−dettagli {cur_hierarchy_gap:,.2f}→{new_hierarchy_gap:,.2f}"
        )
    if worsened:
        raise HTTPException(
            status_code=400,
            detail=(
                "Rettifiche contabilmente incoerenti: " + "; ".join(worsened) +
                ". La modifica non può peggiorare quadratura, risultato CE↔SP o "
                "coerenza aggregati/dettagli."
            ),
        )
    for field, value in payload.balance_sheet.items():
        if field in bs_columns:
            setattr(fy.balance_sheet, field, Decimal(str(value)))

    # Update IS fields
    for field, value in payload.income_statement.items():
        if field in is_columns:
            setattr(fy.income_statement, field, Decimal(str(value)))

    validation_payload = {
        "arithmetic_balanced": abs(new_q.sbilancio) <= Decimal("0.01"),
        "income_result_consistent": new_q.utile_match,
        "hierarchy_consistent": new_q.hierarchy_consistent,
        "semantic_valid": new_q.semantic_valid,
        "masked": new_q.masked,
        "sbilancio": str(new_q.sbilancio),
        "utile_ce": None if new_q.utile_ce is None else str(new_q.utile_ce),
        "sp13": str(new_q.sp13),
        "hierarchy_differences": {
            key: str(value) for key, value in new_q.hierarchy_differences.items()
        },
        "warnings": list(new_q.warnings),
    }
    # Preserve the import-time reliability verdict (importers/reliability.py):
    # this endpoint used to rebuild validation_report from scratch, silently
    # DESTROYING critical_accounts the first time a user touched Rettifiche.
    # Read the CURRENTLY STORED report defensively — it may be absent, empty,
    # or (older records) fail to parse — and never let that raise or block
    # the save; a missing/bad prior report just means nothing to carry over.
    try:
        _prior_report = json.loads(fy.validation_report) if fy.validation_report else {}
        if isinstance(_prior_report, dict) and "critical_accounts" in _prior_report:
            validation_payload["critical_accounts"] = _prior_report["critical_accounts"]
    except Exception:
        pass
    # RULE: a rettifica may NOT restore forecastable while the preserved
    # verdict still says a critical account is unreliable. Setting
    # forecastable/validation_status from semantic_valid alone produced a
    # self-contradictory record (all_critical_ok=false next to
    # validation_status="verified") and let ANY no-op edit bypass the gate.
    # So the two AND in the preserved verdict, mirroring the import-time
    # expression in importers/pdf_importer.py.
    #
    # Re-running reliability.assess here is NOT an option: the `_contra_*`
    # diagnostics it reads are import-time metadata that never reach the
    # database, so on an ORM sheet it would always return DERIVED and
    # auto-clear the very flag being protected.
    #
    # Read the verdict defensively — absent, empty, non-dict or missing the
    # key all mean UNKNOWN, and unknown must never block (exactly the legacy
    # behaviour) nor make the save raise.
    _preserved = validation_payload.get("critical_accounts")
    _critical_ok = True
    if isinstance(_preserved, dict) and "all_critical_ok" in _preserved:
        _critical_ok = bool(_preserved["all_critical_ok"])
    _forecastable = bool(new_q.semantic_valid) and _critical_ok
    # Stato a tre vie identico a quello dell'import: senza questo, la PRIMA
    # rettifica salvata degraderebbe "unbalanced" a "review_required" pur
    # restando il bilancio sbilanciato, perdendo il segnale per la UI.
    from importers.pdf_importer import _resolve_validation_status
    fy.validation_status = _resolve_validation_status(
        abs(new_q.sbilancio) <= Decimal("0.01"), _forecastable
    )
    fy.validation_report = json.dumps(validation_payload, ensure_ascii=False)
    fy.parser_version = "manual-adjustments-semantic-v2"
    fy.forecastable = _forecastable

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
        validation_status=fy.validation_status or "legacy",
        validation_report=(json.loads(fy.validation_report) if fy.validation_report else None),
        forecastable=bool(fy.forecastable),
    )
