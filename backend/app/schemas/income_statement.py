"""
Pydantic schemas for IncomeStatement model
"""
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Optional
from decimal import Decimal


class IncomeStatementBase(BaseModel):
    """Base IncomeStatement schema with all line items"""
    # Revenue
    ce01_ricavi_vendite: Decimal = Field(default=Decimal("0"))
    ce02_variazioni_rimanenze: Decimal = Field(default=Decimal("0"))
    ce03_lavori_interni: Decimal = Field(default=Decimal("0"))
    ce04_altri_ricavi: Decimal = Field(default=Decimal("0"))

    # Costs
    ce05_materie_prime: Decimal = Field(default=Decimal("0"))
    ce06_servizi: Decimal = Field(default=Decimal("0"))
    ce07_godimento_beni: Decimal = Field(default=Decimal("0"))
    ce08_costi_personale: Decimal = Field(default=Decimal("0"))
    ce09_ammortamenti: Decimal = Field(default=Decimal("0"))
    ce10_var_rimanenze_mat_prime: Decimal = Field(default=Decimal("0"))
    ce11_accantonamenti: Decimal = Field(default=Decimal("0"))
    ce12_oneri_diversi: Decimal = Field(default=Decimal("0"))

    # Financial
    ce13_proventi_partecipazioni: Decimal = Field(default=Decimal("0"))
    ce14_altri_proventi_finanziari: Decimal = Field(default=Decimal("0"))
    ce15_oneri_finanziari: Decimal = Field(default=Decimal("0"))
    ce16_utili_perdite_cambi: Decimal = Field(default=Decimal("0"))

    # Extraordinary & Taxes
    ce17_rettifiche_attivita_fin: Decimal = Field(default=Decimal("0"))
    ce18_proventi_straordinari: Decimal = Field(default=Decimal("0"))
    ce19_oneri_straordinari: Decimal = Field(default=Decimal("0"))
    ce20_imposte: Decimal = Field(default=Decimal("0"))


class IncomeStatementCreate(IncomeStatementBase):
    """Schema for creating a new IncomeStatement"""
    financial_year_id: int


class IncomeStatementUpdate(BaseModel):
    """Schema for updating an IncomeStatement"""
    ce01_ricavi_vendite: Optional[Decimal] = None
    ce02_variazioni_rimanenze: Optional[Decimal] = None
    ce03_lavori_interni: Optional[Decimal] = None
    ce04_altri_ricavi: Optional[Decimal] = None
    ce05_materie_prime: Optional[Decimal] = None
    ce06_servizi: Optional[Decimal] = None
    ce07_godimento_beni: Optional[Decimal] = None
    ce08_costi_personale: Optional[Decimal] = None
    ce09_ammortamenti: Optional[Decimal] = None
    ce10_var_rimanenze_mat_prime: Optional[Decimal] = None
    ce11_accantonamenti: Optional[Decimal] = None
    ce12_oneri_diversi: Optional[Decimal] = None
    ce13_proventi_partecipazioni: Optional[Decimal] = None
    ce14_altri_proventi_finanziari: Optional[Decimal] = None
    ce15_oneri_finanziari: Optional[Decimal] = None
    ce16_utili_perdite_cambi: Optional[Decimal] = None
    ce17_rettifiche_attivita_fin: Optional[Decimal] = None
    ce18_proventi_straordinari: Optional[Decimal] = None
    ce19_oneri_straordinari: Optional[Decimal] = None
    ce20_imposte: Optional[Decimal] = None


class IncomeStatementInDB(IncomeStatementBase):
    """IncomeStatement schema with database fields"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    financial_year_id: int
    created_at: datetime
    updated_at: datetime


class IncomeStatement(IncomeStatementInDB):
    """Full IncomeStatement schema with computed fields"""
    production_value: float
    production_cost: float
    ebitda: float
    ebit: float
    financial_result: float
    extraordinary_result: float
    profit_before_tax: float
    net_profit: float
    revenue: float
