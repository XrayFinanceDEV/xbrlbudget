"""
Financial Year API endpoints
"""
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import sys
import os

# Add backend directory to Python path
backend_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from app.core.database import get_db
from app.schemas import financial_year as schemas
from app.schemas import balance_sheet as bs_schemas
from app.schemas import income_statement as is_schemas
from database import models

router = APIRouter()


@router.get("/companies/{company_id}/years/{year}", response_model=schemas.FinancialYear)
def get_financial_year(company_id: int, year: int, db: Session = Depends(get_db)):
    """Get financial year for a specific company and year"""
    fy = db.query(models.FinancialYear).filter(
        models.FinancialYear.company_id == company_id,
        models.FinancialYear.year == year
    ).first()

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
    db: Session = Depends(get_db)
):
    """Create a new financial year for a company"""
    # Verify company exists
    company = db.query(models.Company).filter(models.Company.id == company_id).first()
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company with id {company_id} not found"
        )

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
def delete_financial_year(company_id: int, year: int, db: Session = Depends(get_db)):
    """Delete a financial year and all associated financial statements"""
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
def get_balance_sheet(company_id: int, year: int, db: Session = Depends(get_db)):
    """Get balance sheet for a specific company and year"""
    fy = db.query(models.FinancialYear).filter(
        models.FinancialYear.company_id == company_id,
        models.FinancialYear.year == year
    ).first()

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
    db: Session = Depends(get_db)
):
    """Update balance sheet for a specific year"""
    fy = db.query(models.FinancialYear).filter(
        models.FinancialYear.company_id == company_id,
        models.FinancialYear.year == year
    ).first()

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
def get_income_statement(company_id: int, year: int, db: Session = Depends(get_db)):
    """Get income statement for a specific company and year"""
    fy = db.query(models.FinancialYear).filter(
        models.FinancialYear.company_id == company_id,
        models.FinancialYear.year == year
    ).first()

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
    db: Session = Depends(get_db)
):
    """Update income statement for a specific year"""
    fy = db.query(models.FinancialYear).filter(
        models.FinancialYear.company_id == company_id,
        models.FinancialYear.year == year
    ).first()

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
