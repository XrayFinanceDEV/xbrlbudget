"""
Pydantic schemas for the Rettifiche (Adjustments) feature.
"""
from typing import Any, Optional, Dict, List
from pydantic import BaseModel


class RettificaEntry(BaseModel):
    """One per-edit double-entry rettifica, tracked for the log panel."""
    id: str
    edited_field: str
    edited_label: str
    edit_delta: float
    counterpart_field: str
    counterpart_label: str
    counterpart_delta: float
    explanation: Optional[str] = None
    created_at: str  # ISO timestamp


class AdjustableFinancialYear(BaseModel):
    """Response for GET /financial-years/{fy_id}/adjustable"""
    financial_year_id: int
    year: int
    period_months: Optional[int] = None
    balance_sheet: Dict[str, float]
    income_statement: Dict[str, float]
    original_balance_sheet: Optional[Dict[str, float]] = None
    original_income_statement: Optional[Dict[str, float]] = None
    rettifiche_log: List[RettificaEntry] = []
    validation_status: str = "legacy"
    validation_report: Optional[Dict[str, Any]] = None
    forecastable: bool = False

    model_config = {"from_attributes": True}


class AdjustmentsUpdate(BaseModel):
    """Request for PUT /financial-years/{fy_id}/adjustments"""
    balance_sheet: Dict[str, float]
    income_statement: Dict[str, float]
    rettifiche_log: Optional[List[RettificaEntry]] = None
