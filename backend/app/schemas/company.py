"""
Pydantic schemas for Company model
"""
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import List, Optional


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


class CompanyInDB(BaseModel):
    """Company schema with database fields.

    Schema di LETTURA: non riapplica i vincoli dell'input (`CompanyBase`) alle
    righe già salvate. SQLite non fa rispettare `String(255)`/`String(20)`, e un
    importer ha scritto nomi di 590 caratteri (un paragrafo HTML della nota
    integrativa): con i vincoli qui, quella riga sola faceva rispondere 500 a
    `GET /companies` e l'utente non vedeva più nessuna delle sue aziende — e
    ricreandole riceveva 400 per P.IVA già usata. Una riga anomala si mostra e si
    rinomina; i vincoli restano su `CompanyCreate`/`CompanyUpdate`."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    tax_id: Optional[str] = None
    sector: int
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class Company(CompanyInDB):
    """Full Company schema for API responses"""
    pass


class ScenarioSummary(BaseModel):
    """Lightweight scenario summary for the Aziende & Pratiche home."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    scenario_type: str
    base_year: int
    period_months: Optional[int] = None
    is_active: int
    has_forecast: bool
    source_scenario_id: Optional[int] = None
    workflow_type: Optional[str] = None
    created_at: Optional[datetime] = None


class CompanyWithScenarios(Company):
    """Company plus its budget/infrannuale scenarios (include=scenarios)."""
    scenarios: List[ScenarioSummary] = []


class ExistingBalanceOption(BaseModel):
    """A complete imported balance available as the source of a new practice."""
    id: int
    year: int
    period_months: Optional[int] = None
