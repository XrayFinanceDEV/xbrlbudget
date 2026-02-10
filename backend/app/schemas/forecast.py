"""
Pydantic schemas for Forecast models (Balance Sheet, Income Statement)
"""
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Optional, List, Dict, Any
from decimal import Decimal


# ForecastBalanceSheet Schemas
class ForecastBalanceSheetBase(BaseModel):
    """Base ForecastBalanceSheet schema with all balance sheet line items"""
    # Assets - Fixed Assets
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

    # Assets - Current Assets
    sp05_rimanenze: Decimal = Field(default=Decimal("0"))
    sp06_crediti_breve: Decimal = Field(default=Decimal("0"))
    sp07_crediti_lungo: Decimal = Field(default=Decimal("0"))
    sp08_attivita_finanziarie: Decimal = Field(default=Decimal("0"))
    sp09_disponibilita_liquide: Decimal = Field(default=Decimal("0"))
    sp10_ratei_risconti_attivi: Decimal = Field(default=Decimal("0"))

    # Liabilities - Equity
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

    # Liabilities - Provisions and Debts
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


class ForecastBalanceSheetInDB(ForecastBalanceSheetBase):
    """ForecastBalanceSheet schema with database fields"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    forecast_year_id: int
    created_at: datetime
    updated_at: datetime

    # Calculated properties
    total_assets: Optional[Decimal] = Field(default=None, description="Total Assets (computed)")
    total_equity: Optional[Decimal] = Field(default=None, description="Total Equity (computed)")
    total_liabilities: Optional[Decimal] = Field(default=None, description="Total Liabilities (computed)")
    fixed_assets: Optional[Decimal] = Field(default=None, description="Fixed Assets (computed)")
    current_assets: Optional[Decimal] = Field(default=None, description="Current Assets (computed)")
    current_liabilities: Optional[Decimal] = Field(default=None, description="Current Liabilities (computed)")
    total_debt: Optional[Decimal] = Field(default=None, description="Total Debt (computed)")
    working_capital_net: Optional[Decimal] = Field(default=None, description="Net Working Capital (computed)")


class ForecastBalanceSheet(ForecastBalanceSheetInDB):
    """Full ForecastBalanceSheet schema for API responses"""
    pass


# ForecastIncomeStatement Schemas
class ForecastIncomeStatementBase(BaseModel):
    """Base ForecastIncomeStatement schema with all income statement line items"""
    # A) Production Value
    ce01_ricavi_vendite: Decimal = Field(default=Decimal("0"))
    ce02_variazioni_rimanenze: Decimal = Field(default=Decimal("0"))
    ce03_lavori_interni: Decimal = Field(default=Decimal("0"))
    ce04_altri_ricavi: Decimal = Field(default=Decimal("0"))

    # B) Production Costs
    ce05_materie_prime: Decimal = Field(default=Decimal("0"))
    ce06_servizi: Decimal = Field(default=Decimal("0"))
    ce07_godimento_beni: Decimal = Field(default=Decimal("0"))
    ce08_costi_personale: Decimal = Field(default=Decimal("0"))
    ce09_ammortamenti: Decimal = Field(default=Decimal("0"))
    ce10_var_rimanenze_mat_prime: Decimal = Field(default=Decimal("0"))
    ce11_accantonamenti: Decimal = Field(default=Decimal("0"))
    ce12_oneri_diversi: Decimal = Field(default=Decimal("0"))

    # C) Financial Items
    ce13_proventi_partecipazioni: Decimal = Field(default=Decimal("0"))
    ce14_altri_proventi_finanziari: Decimal = Field(default=Decimal("0"))
    ce15_oneri_finanziari: Decimal = Field(default=Decimal("0"))
    ce16_utili_perdite_cambi: Decimal = Field(default=Decimal("0"))

    # D) Financial Assets Adjustments
    ce17_rettifiche_attivita_fin: Decimal = Field(default=Decimal("0"))

    # E) Extraordinary Items
    ce18_proventi_straordinari: Decimal = Field(default=Decimal("0"))
    ce19_oneri_straordinari: Decimal = Field(default=Decimal("0"))

    # Taxes
    ce20_imposte: Decimal = Field(default=Decimal("0"))


class ForecastIncomeStatementInDB(ForecastIncomeStatementBase):
    """ForecastIncomeStatement schema with database fields"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    forecast_year_id: int
    created_at: datetime
    updated_at: datetime

    # Calculated properties
    production_value: Optional[Decimal] = Field(default=None, description="Production Value (computed)")
    production_cost: Optional[Decimal] = Field(default=None, description="Production Cost (computed)")
    ebitda: Optional[Decimal] = Field(default=None, description="EBITDA (computed)")
    ebit: Optional[Decimal] = Field(default=None, description="EBIT (computed)")
    financial_result: Optional[Decimal] = Field(default=None, description="Financial Result (computed)")
    extraordinary_result: Optional[Decimal] = Field(default=None, description="Extraordinary Result (computed)")
    profit_before_tax: Optional[Decimal] = Field(default=None, description="Profit Before Tax (computed)")
    net_profit: Optional[Decimal] = Field(default=None, description="Net Profit (computed)")
    revenue: Optional[Decimal] = Field(default=None, description="Revenue (computed)")


class ForecastIncomeStatement(ForecastIncomeStatementInDB):
    """Full ForecastIncomeStatement schema for API responses"""
    pass


# Nested Response Schemas
class BudgetScenarioWithDetails(BaseModel):
    """Budget scenario with nested assumptions and forecast years"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    name: str
    base_year: int
    description: Optional[str] = None
    is_active: int
    created_at: datetime
    updated_at: datetime

    # Nested relationships (populated via eager loading)
    assumptions: List[Any] = Field(default_factory=list, description="Budget assumptions for forecast years")
    forecast_years: List[Any] = Field(default_factory=list, description="Generated forecast years")


class ForecastYearSummary(BaseModel):
    """Summary information for a forecast year"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    scenario_id: int
    year: int
    created_at: datetime
    updated_at: datetime


class ForecastGenerationResult(BaseModel):
    """Result of forecast generation with summary statistics"""
    scenario_id: int
    scenario_name: str
    base_year: int
    forecast_years: List[int] = Field(description="List of forecast years generated")
    summary: Dict[str, Any] = Field(
        description="Summary statistics per year (net_profit, total_assets, working_capital, etc.)"
    )
    generated_at: datetime = Field(default_factory=datetime.utcnow)
