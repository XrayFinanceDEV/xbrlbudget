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
    sp01_crediti_soci: Decimal = Field(default=Decimal("0"))
    sp02_immob_immateriali: Decimal = Field(default=Decimal("0"))
    sp03_immob_materiali: Decimal = Field(default=Decimal("0"))
    sp04_immob_finanziarie: Decimal = Field(default=Decimal("0"))

    # Detailed breakdown - Immobilizzazioni finanziarie
    sp04a_partecipazioni: Decimal = Field(default=Decimal("0"))
    sp04b_crediti_immob_breve: Decimal = Field(default=Decimal("0"))
    sp04c_crediti_immob_lungo: Decimal = Field(default=Decimal("0"))
    sp04d_altri_titoli: Decimal = Field(default=Decimal("0"))
    sp04e_strumenti_derivati_attivi: Decimal = Field(default=Decimal("0"))

    sp05_rimanenze: Decimal = Field(default=Decimal("0"))
    sp06_crediti_breve: Decimal = Field(default=Decimal("0"))
    sp07_crediti_lungo: Decimal = Field(default=Decimal("0"))
    sp08_attivita_finanziarie: Decimal = Field(default=Decimal("0"))
    sp09_disponibilita_liquide: Decimal = Field(default=Decimal("0"))
    sp10_ratei_risconti_attivi: Decimal = Field(default=Decimal("0"))

    # Liabilities & Equity
    sp11_capitale: Decimal = Field(default=Decimal("0"))
    sp12_riserve: Decimal = Field(default=Decimal("0"))

    # Detailed breakdown - Patrimonio Netto (Riserve)
    sp12a_riserva_sovrapprezzo: Decimal = Field(default=Decimal("0"))
    sp12b_riserve_rivalutazione: Decimal = Field(default=Decimal("0"))
    sp12c_riserva_legale: Decimal = Field(default=Decimal("0"))
    sp12d_riserve_statutarie: Decimal = Field(default=Decimal("0"))
    sp12e_altre_riserve: Decimal = Field(default=Decimal("0"))
    sp12f_riserva_copertura_flussi: Decimal = Field(default=Decimal("0"))
    sp12g_utili_perdite_portati: Decimal = Field(default=Decimal("0"))
    sp12h_riserva_neg_azioni_proprie: Decimal = Field(default=Decimal("0"))

    sp13_utile_perdita: Decimal = Field(default=Decimal("0"))
    sp14_fondi_rischi: Decimal = Field(default=Decimal("0"))
    sp15_tfr: Decimal = Field(default=Decimal("0"))
    sp16_debiti_breve: Decimal = Field(default=Decimal("0"))
    sp17_debiti_lungo: Decimal = Field(default=Decimal("0"))

    # Detailed breakdown - Financial debts
    sp16a_debiti_banche_breve: Decimal = Field(default=Decimal("0"))
    sp17a_debiti_banche_lungo: Decimal = Field(default=Decimal("0"))
    sp16b_debiti_altri_finanz_breve: Decimal = Field(default=Decimal("0"))
    sp17b_debiti_altri_finanz_lungo: Decimal = Field(default=Decimal("0"))
    sp16c_debiti_obbligazioni_breve: Decimal = Field(default=Decimal("0"))
    sp17c_debiti_obbligazioni_lungo: Decimal = Field(default=Decimal("0"))

    # Detailed breakdown - Operating debts
    sp16d_debiti_fornitori_breve: Decimal = Field(default=Decimal("0"))
    sp17d_debiti_fornitori_lungo: Decimal = Field(default=Decimal("0"))
    sp16e_debiti_tributari_breve: Decimal = Field(default=Decimal("0"))
    sp17e_debiti_tributari_lungo: Decimal = Field(default=Decimal("0"))
    sp16f_debiti_previdenza_breve: Decimal = Field(default=Decimal("0"))
    sp17f_debiti_previdenza_lungo: Decimal = Field(default=Decimal("0"))
    sp16g_altri_debiti_breve: Decimal = Field(default=Decimal("0"))
    sp17g_altri_debiti_lungo: Decimal = Field(default=Decimal("0"))

    sp18_ratei_risconti_passivi: Decimal = Field(default=Decimal("0"))


class BalanceSheetCreate(BalanceSheetBase):
    """Schema for creating a new BalanceSheet"""
    financial_year_id: int


class BalanceSheetUpdate(BaseModel):
    """Schema for updating a BalanceSheet"""
    sp01_crediti_soci: Optional[Decimal] = None
    sp02_immob_immateriali: Optional[Decimal] = None
    sp03_immob_materiali: Optional[Decimal] = None
    sp04_immob_finanziarie: Optional[Decimal] = None

    # Detailed breakdown - Immobilizzazioni finanziarie
    sp04a_partecipazioni: Optional[Decimal] = None
    sp04b_crediti_immob_breve: Optional[Decimal] = None
    sp04c_crediti_immob_lungo: Optional[Decimal] = None
    sp04d_altri_titoli: Optional[Decimal] = None
    sp04e_strumenti_derivati_attivi: Optional[Decimal] = None

    sp05_rimanenze: Optional[Decimal] = None
    sp06_crediti_breve: Optional[Decimal] = None
    sp07_crediti_lungo: Optional[Decimal] = None
    sp08_attivita_finanziarie: Optional[Decimal] = None
    sp09_disponibilita_liquide: Optional[Decimal] = None
    sp10_ratei_risconti_attivi: Optional[Decimal] = None
    sp11_capitale: Optional[Decimal] = None
    sp12_riserve: Optional[Decimal] = None

    # Detailed breakdown - Patrimonio Netto (Riserve)
    sp12a_riserva_sovrapprezzo: Optional[Decimal] = None
    sp12b_riserve_rivalutazione: Optional[Decimal] = None
    sp12c_riserva_legale: Optional[Decimal] = None
    sp12d_riserve_statutarie: Optional[Decimal] = None
    sp12e_altre_riserve: Optional[Decimal] = None
    sp12f_riserva_copertura_flussi: Optional[Decimal] = None
    sp12g_utili_perdite_portati: Optional[Decimal] = None
    sp12h_riserva_neg_azioni_proprie: Optional[Decimal] = None

    sp13_utile_perdita: Optional[Decimal] = None
    sp14_fondi_rischi: Optional[Decimal] = None
    sp15_tfr: Optional[Decimal] = None
    sp16_debiti_breve: Optional[Decimal] = None
    sp17_debiti_lungo: Optional[Decimal] = None

    # Detailed breakdown - Financial debts
    sp16a_debiti_banche_breve: Optional[Decimal] = None
    sp17a_debiti_banche_lungo: Optional[Decimal] = None
    sp16b_debiti_altri_finanz_breve: Optional[Decimal] = None
    sp17b_debiti_altri_finanz_lungo: Optional[Decimal] = None
    sp16c_debiti_obbligazioni_breve: Optional[Decimal] = None
    sp17c_debiti_obbligazioni_lungo: Optional[Decimal] = None

    # Detailed breakdown - Operating debts
    sp16d_debiti_fornitori_breve: Optional[Decimal] = None
    sp17d_debiti_fornitori_lungo: Optional[Decimal] = None
    sp16e_debiti_tributari_breve: Optional[Decimal] = None
    sp17e_debiti_tributari_lungo: Optional[Decimal] = None
    sp16f_debiti_previdenza_breve: Optional[Decimal] = None
    sp17f_debiti_previdenza_lungo: Optional[Decimal] = None
    sp16g_altri_debiti_breve: Optional[Decimal] = None
    sp17g_altri_debiti_lungo: Optional[Decimal] = None

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
