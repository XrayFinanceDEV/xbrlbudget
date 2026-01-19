"""
Pydantic schemas for BalanceSheet model
"""
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Optional
from decimal import Decimal


class BalanceSheetBase(BaseModel):
    """Base BalanceSheet schema with all line items"""
    # Assets
    sp01_crediti_soci: Decimal = Field(default=Decimal("0"), ge=0)
    sp02_immob_immateriali: Decimal = Field(default=Decimal("0"), ge=0)
    sp03_immob_materiali: Decimal = Field(default=Decimal("0"), ge=0)
    sp04_immob_finanziarie: Decimal = Field(default=Decimal("0"), ge=0)
    sp05_rimanenze: Decimal = Field(default=Decimal("0"), ge=0)
    sp06_crediti_breve: Decimal = Field(default=Decimal("0"), ge=0)
    sp07_crediti_lungo: Decimal = Field(default=Decimal("0"), ge=0)
    sp08_attivita_finanziarie: Decimal = Field(default=Decimal("0"), ge=0)
    sp09_disponibilita_liquide: Decimal = Field(default=Decimal("0"), ge=0)
    sp10_ratei_risconti_attivi: Decimal = Field(default=Decimal("0"), ge=0)

    # Liabilities & Equity
    sp11_capitale: Decimal = Field(default=Decimal("0"))
    sp12_riserve: Decimal = Field(default=Decimal("0"))
    sp13_utile_perdita: Decimal = Field(default=Decimal("0"))
    sp14_fondi_rischi: Decimal = Field(default=Decimal("0"), ge=0)
    sp15_tfr: Decimal = Field(default=Decimal("0"), ge=0)
    sp16_debiti_breve: Decimal = Field(default=Decimal("0"), ge=0)
    sp17_debiti_lungo: Decimal = Field(default=Decimal("0"), ge=0)
    sp18_ratei_risconti_passivi: Decimal = Field(default=Decimal("0"), ge=0)


class BalanceSheetCreate(BalanceSheetBase):
    """Schema for creating a new BalanceSheet"""
    financial_year_id: int


class BalanceSheetUpdate(BaseModel):
    """Schema for updating a BalanceSheet"""
    sp01_crediti_soci: Optional[Decimal] = None
    sp02_immob_immateriali: Optional[Decimal] = None
    sp03_immob_materiali: Optional[Decimal] = None
    sp04_immob_finanziarie: Optional[Decimal] = None
    sp05_rimanenze: Optional[Decimal] = None
    sp06_crediti_breve: Optional[Decimal] = None
    sp07_crediti_lungo: Optional[Decimal] = None
    sp08_attivita_finanziarie: Optional[Decimal] = None
    sp09_disponibilita_liquide: Optional[Decimal] = None
    sp10_ratei_risconti_attivi: Optional[Decimal] = None
    sp11_capitale: Optional[Decimal] = None
    sp12_riserve: Optional[Decimal] = None
    sp13_utile_perdita: Optional[Decimal] = None
    sp14_fondi_rischi: Optional[Decimal] = None
    sp15_tfr: Optional[Decimal] = None
    sp16_debiti_breve: Optional[Decimal] = None
    sp17_debiti_lungo: Optional[Decimal] = None
    sp18_ratei_risconti_passivi: Optional[Decimal] = None


class BalanceSheetInDB(BalanceSheetBase):
    """BalanceSheet schema with database fields"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    financial_year_id: int
    created_at: datetime
    updated_at: datetime


class BalanceSheet(BalanceSheetInDB):
    """Full BalanceSheet schema with computed fields"""
    total_assets: float
    total_equity: float
    total_liabilities: float
    fixed_assets: float
    current_assets: float
    current_liabilities: float
    total_debt: float
    working_capital_net: float
