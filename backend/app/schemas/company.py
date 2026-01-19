"""
Pydantic schemas for Company model
"""
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Optional


class CompanyBase(BaseModel):
    """Base Company schema"""
    name: str = Field(..., min_length=1, max_length=255)
    tax_id: Optional[str] = Field(None, max_length=20)
    sector: int = Field(..., ge=1, le=6)
    notes: Optional[str] = None


class CompanyCreate(CompanyBase):
    """Schema for creating a new Company"""
    pass


class CompanyUpdate(BaseModel):
    """Schema for updating a Company"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    tax_id: Optional[str] = Field(None, max_length=20)
    sector: Optional[int] = Field(None, ge=1, le=6)
    notes: Optional[str] = None


class CompanyInDB(CompanyBase):
    """Company schema with database fields"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class Company(CompanyInDB):
    """Full Company schema for API responses"""
    pass
