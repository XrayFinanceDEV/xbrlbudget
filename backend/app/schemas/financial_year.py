"""
Pydantic schemas for FinancialYear model
"""
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Any, Dict, Optional


class FinancialYearBase(BaseModel):
    """Base FinancialYear schema"""
    company_id: int
    year: int = Field(..., ge=2000, le=2100)


class FinancialYearCreate(FinancialYearBase):
    """Schema for creating a new FinancialYear"""
    period_months: Optional[int] = Field(None, ge=1, le=12)


class FinancialYearUpdate(BaseModel):
    """Schema for updating a FinancialYear"""
    year: Optional[int] = Field(None, ge=2000, le=2100)
    period_months: Optional[int] = Field(None, ge=1, le=12)


class FinancialYearInDB(FinancialYearBase):
    """FinancialYear schema with database fields"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    period_months: Optional[int] = None
    validation_status: str = "legacy"
    validation_report: Optional[str] = None
    source_sha256: Optional[str] = None
    parser_version: Optional[str] = None
    forecastable: bool = False
    created_at: datetime
    updated_at: datetime


class FinancialYear(FinancialYearInDB):
    """Full FinancialYear schema for API responses"""
    pass
