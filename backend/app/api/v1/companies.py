"""
Company API endpoints
"""
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
import sys
import os

# Add backend directory to Python path
backend_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from app.core.database import get_db
from app.core.auth import get_current_user_id
from app.core.ownership import validate_company_owned_by_user, check_company_limit
from app.schemas import company as schemas
from database import models

router = APIRouter()


@router.get("/companies", response_model=List[schemas.CompanyWithScenarios])
def list_companies(
    skip: int = 0,
    limit: int = 100,
    include: Optional[str] = None,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Get list of all companies for the current user.

    With ?include=scenarios each company also carries a lightweight list of its
    budget/infrannuale scenarios (one call replaces the per-company loop the
    Aziende & Pratiche home used to do). Plain calls return an empty scenarios
    list (backward compatible)."""
    if include == "scenarios":
        companies = (
            db.query(models.Company)
            .options(joinedload(models.Company.budget_scenarios)
                     .joinedload(models.BudgetScenario.forecast_years))
            .filter(models.Company.user_id == user_id)
            .offset(skip).limit(limit).all()
        )
        out = []
        for c in companies:
            item = schemas.CompanyWithScenarios.model_validate(c, from_attributes=True)
            item.scenarios = [
                schemas.ScenarioSummary(
                    id=s.id, name=s.name, scenario_type=s.scenario_type,
                    base_year=s.base_year, period_months=s.period_months,
                    is_active=s.is_active, has_forecast=len(s.forecast_years) > 0,
                    source_scenario_id=getattr(s, "source_scenario_id", None),
                    workflow_type=getattr(s, "workflow_type", None),
                    created_at=s.created_at,
                )
                for s in sorted(c.budget_scenarios,
                                key=lambda s: s.created_at or datetime.min, reverse=True)
            ]
            out.append(item)
        return out

    companies = db.query(models.Company).filter(
        models.Company.user_id == user_id
    ).offset(skip).limit(limit).all()
    return companies


@router.get("/companies/{company_id}", response_model=schemas.Company)
def get_company(
    company_id: int,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Get a specific company by ID"""
    return validate_company_owned_by_user(db, company_id, user_id)


@router.post("/companies", response_model=schemas.Company, status_code=status.HTTP_201_CREATED)
def create_company(
    company: schemas.CompanyCreate,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Create a new company"""
    check_company_limit(db, user_id)

    # Check if company with same tax_id already exists for this user
    if company.tax_id:
        existing = db.query(models.Company).filter(
            models.Company.tax_id == company.tax_id,
            models.Company.user_id == user_id,
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Company with tax_id {company.tax_id} already exists"
            )

    db_company = models.Company(**company.model_dump(), user_id=user_id)
    db.add(db_company)
    db.commit()
    db.refresh(db_company)
    return db_company


@router.put("/companies/{company_id}", response_model=schemas.Company)
def update_company(
    company_id: int,
    company_update: schemas.CompanyUpdate,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Update an existing company"""
    db_company = validate_company_owned_by_user(db, company_id, user_id)

    # Update only provided fields
    update_data = company_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_company, field, value)

    db.commit()
    db.refresh(db_company)
    return db_company


@router.delete("/companies/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_company(
    company_id: int,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Delete a company and all associated data"""
    db_company = validate_company_owned_by_user(db, company_id, user_id)
    db.delete(db_company)
    db.commit()
    return None


@router.get("/companies/{company_id}/years", response_model=List[int])
def get_company_years(
    company_id: int,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Get all years for which a company has financial data"""
    validate_company_owned_by_user(db, company_id, user_id)

    years = db.query(models.FinancialYear.year).filter(
        models.FinancialYear.company_id == company_id
    ).order_by(models.FinancialYear.year.desc()).all()

    # Deduplicate (partial + full-year records can coexist for same year)
    return sorted(set(year[0] for year in years), reverse=True)
