"""
Pydantic schemas for IncomeStatement model
"""
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Optional
from decimal import Decimal


class IncomeStatementBase(BaseModel):
    """Base IncomeStatement schema with all line items"""
    # === A) VALORE DELLA PRODUZIONE ===
    # A.1) Ricavi delle vendite e delle prestazioni
    ce01_ricavi_vendite: Decimal = Field(default=Decimal("0"))
    # A.2) Variazioni delle rimanenze di prodotti in lavorazione, semilavorati e finiti
    ce02_variazioni_rimanenze: Decimal = Field(default=Decimal("0"))
    # A.3) Variazioni dei lavori in corso su ordinazione
    ce03_lavori_interni: Decimal = Field(default=Decimal("0"))
    # A.4) Incrementi di immobilizzazioni per lavori interni (included in ce04)
    # A.5) Altri ricavi e proventi
    ce04_altri_ricavi: Decimal = Field(default=Decimal("0"))

    # === B) COSTI DELLA PRODUZIONE ===
    # B.6) Per materie prime, sussidiarie, di consumo e di merci
    ce05_materie_prime: Decimal = Field(default=Decimal("0"))
    # B.7) Per servizi
    ce06_servizi: Decimal = Field(default=Decimal("0"))
    # B.8) Per godimento di beni di terzi
    ce07_godimento_beni: Decimal = Field(default=Decimal("0"))
    # B.9) Per il personale
    ce08_costi_personale: Decimal = Field(default=Decimal("0"))
    ce08a_tfr_accrual: Decimal = Field(default=Decimal("0"))  # TFR accrual detail

    # B.10) Ammortamenti e svalutazioni
    ce09_ammortamenti: Decimal = Field(default=Decimal("0"))  # Total
    ce09a_ammort_immateriali: Decimal = Field(default=Decimal("0"))  # Intangible
    ce09b_ammort_materiali: Decimal = Field(default=Decimal("0"))  # Tangible
    ce09c_svalutazioni: Decimal = Field(default=Decimal("0"))  # Other write-downs of fixed assets (c)
    ce09d_svalutazione_crediti: Decimal = Field(default=Decimal("0"))  # Write-downs of receivables (d)

    # B.11) Variazioni delle rimanenze di materie prime
    ce10_var_rimanenze_mat_prime: Decimal = Field(default=Decimal("0"))
    # B.12) Accantonamenti per rischi
    ce11_accantonamenti: Decimal = Field(default=Decimal("0"))
    # B.13) Altri accantonamenti
    ce11b_altri_accantonamenti: Decimal = Field(default=Decimal("0"))
    # B.14) Oneri diversi di gestione
    ce12_oneri_diversi: Decimal = Field(default=Decimal("0"))

    # === C) PROVENTI E ONERI FINANZIARI ===
    # C.15) Proventi da partecipazioni
    ce13_proventi_partecipazioni: Decimal = Field(default=Decimal("0"))
    # C.16) Altri proventi finanziari
    ce14_altri_proventi_finanziari: Decimal = Field(default=Decimal("0"))
    # C.17) Interessi e altri oneri finanziari
    ce15_oneri_finanziari: Decimal = Field(default=Decimal("0"))
    # C.17-bis) Utili e perdite su cambi
    ce16_utili_perdite_cambi: Decimal = Field(default=Decimal("0"))

    # === D) RETTIFICHE DI VALORE DI ATTIVITÀ FINANZIARIE ===
    ce17_rettifiche_attivita_fin: Decimal = Field(default=Decimal("0"))

    # === E) PROVENTI E ONERI STRAORDINARI ===
    ce18_proventi_straordinari: Decimal = Field(default=Decimal("0"))
    ce19_oneri_straordinari: Decimal = Field(default=Decimal("0"))

    # === IMPOSTE ===
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
    ce08a_tfr_accrual: Optional[Decimal] = None
    ce09_ammortamenti: Optional[Decimal] = None
    ce09a_ammort_immateriali: Optional[Decimal] = None
    ce09b_ammort_materiali: Optional[Decimal] = None
    ce09c_svalutazioni: Optional[Decimal] = None
    ce09d_svalutazione_crediti: Optional[Decimal] = None
    ce10_var_rimanenze_mat_prime: Optional[Decimal] = None
    ce11_accantonamenti: Optional[Decimal] = None
    ce11b_altri_accantonamenti: Optional[Decimal] = None
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
