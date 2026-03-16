"""
Pydantic schemas for the Rettifiche (Adjustments) feature.
"""
from typing import Optional, Dict
from pydantic import BaseModel


class AdjustableFinancialYear(BaseModel):
    """Response for GET /financial-years/{fy_id}/adjustable"""
    financial_year_id: int
    year: int
    period_months: Optional[int] = None
    balance_sheet: Dict[str, float]
    income_statement: Dict[str, float]
    original_balance_sheet: Optional[Dict[str, float]] = None
    original_income_statement: Optional[Dict[str, float]] = None

    model_config = {"from_attributes": True}


class AdjustmentsUpdate(BaseModel):
    """Request for PUT /financial-years/{fy_id}/adjustments"""
    balance_sheet: Dict[str, float]
    income_statement: Dict[str, float]
