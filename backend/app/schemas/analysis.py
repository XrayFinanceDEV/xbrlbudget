"""
Pydantic schemas for Complete Analysis API responses

Simplified schemas for the comprehensive analysis endpoint that returns
historical data, forecasts, and all calculations in one response.
"""
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from decimal import Decimal


# ===== Company Info Schema =====

class CompanyInfo(BaseModel):
    """Company information embedded in analysis response"""
    id: int
    name: str
    tax_id: str
    sector: int


# ===== Scenario Info Schema =====

class ScenarioInfo(BaseModel):
    """Scenario information"""
    id: int
    name: str
    base_year: int
    projection_years: int
    is_active: int
    company: CompanyInfo


# ===== Financial Statement Schemas =====

class BalanceSheetData(BaseModel):
    """Balance sheet data (historical or forecast)"""
    # All sp01-sp18 fields as floats
    sp01_crediti_soci: float
    sp02_immob_immateriali: float
    sp03_immob_materiali: float
    sp04_immob_finanziarie: float
    sp05_rimanenze: float
    sp06_crediti_breve: float
    sp07_crediti_lungo: float
    sp08_attivita_finanziarie: float
    sp09_disponibilita_liquide: float
    sp10_ratei_risconti_attivi: float
    sp11_capitale: float
    sp12_riserve: float
    sp13_utile_perdita: float
    sp14_fondi_rischi: float
    sp15_tfr: float
    sp16_debiti_breve: float
    sp17_debiti_lungo: float
    sp16a_debiti_banche_breve: float
    sp16b_debiti_altri_finanz_breve: float
    sp16c_debiti_obbligazioni_breve: float
    sp16d_debiti_fornitori_breve: float
    sp16e_debiti_tributari_breve: float
    sp16f_debiti_previdenza_breve: float
    sp16g_altri_debiti_breve: float
    sp17a_debiti_banche_lungo: float
    sp17b_debiti_altri_finanz_lungo: float
    sp17c_debiti_obbligazioni_lungo: float
    sp17d_debiti_fornitori_lungo: float
    sp17e_debiti_tributari_lungo: float
    sp17f_debiti_previdenza_lungo: float
    sp17g_altri_debiti_lungo: float
    sp18_ratei_risconti_passivi: float

    # Calculated properties
    total_assets: float
    total_equity: float
    total_debt: float
    fixed_assets: float
    current_assets: float
    current_liabilities: float
    working_capital_net: float


class IncomeStatementData(BaseModel):
    """Income statement data (historical or forecast)"""
    # All ce01-ce20 fields as floats
    ce01_ricavi_vendite: float
    ce02_var_rimanenze: float
    ce03_var_lavori: float
    ce04_incrementi: float
    ce05_altri_ricavi: float
    ce06_materie_prime: float
    ce07_servizi: float
    ce08_godimento_beni: float
    ce09_personale: float
    ce10_ammortamenti: float
    ce11_svalutazioni: float
    ce12_accantonamenti: float
    ce13_oneri_diversi: float
    ce14_proventi_finanziari: float
    ce15_oneri_finanziari: float
    ce16_rettifiche_attivita_finanziarie: float
    ce17_proventi_straordinari: float
    ce18_oneri_straordinari: float
    ce19_imposte: float
    ce20_utile_perdita: float

    # Calculated properties
    revenue: float
    production_value: float
    production_cost: float
    ebitda: float
    ebit: float
    financial_result: float
    extraordinary_result: float
    profit_before_tax: float
    net_profit: float


class AssumptionsData(BaseModel):
    """Budget assumptions for a forecast year"""
    forecast_year: int
    revenue_growth_pct: float
    material_cost_growth_pct: float
    service_cost_growth_pct: float
    personnel_cost_growth_pct: float
    other_revenue_growth_pct: float
    depreciation_rate_tangible_pct: float
    depreciation_rate_intangible_pct: float
    capex_tangible: float
    capex_intangible: float
    new_debt: float
    debt_repayment: float
    interest_rate_pct: float
    tax_rate_pct: float
    dividend_payout_pct: float


# ===== Year Data Schemas =====

class HistoricalYearData(BaseModel):
    """Data for one historical year"""
    year: int
    type: str = "historical"
    balance_sheet: BalanceSheetData
    income_statement: IncomeStatementData


class ForecastYearData(BaseModel):
    """Data for one forecast year"""
    year: int
    type: str = "forecast"
    assumptions: Optional[AssumptionsData]
    balance_sheet: BalanceSheetData
    income_statement: IncomeStatementData


# ===== Calculations Schemas =====
# Using Dict[str, Any] for flexibility since calculation structures are complex

class CompleteAnalysisResponse(BaseModel):
    """
    Complete analysis response schema.

    This is the main response from GET /companies/{id}/scenarios/{sid}/analysis
    Returns everything needed for all frontend pages in one call.
    """
    scenario: ScenarioInfo
    historical_years: List[HistoricalYearData]
    forecast_years: List[ForecastYearData]
    calculations: Dict[str, Any] = Field(
        description="""
        All calculations structured as:
        {
            "by_year": {
                "2023": { "altman": {...}, "fgpmi": {...}, "ratios": {...} },
                "2024": { ... },
                "2025": { ... },
                ...
            },
            "cashflow": {
                "years": [
                    { "year": 2024, "base_year": 2023, "operating": {...}, ... },
                    ...
                ]
            }
        }
        """
    )


# ===== Bulk Assumptions Request/Response Schemas =====

class BulkAssumptionInput(BaseModel):
    """Single assumption input for bulk upsert"""
    forecast_year: int = Field(..., ge=2000, le=2100)
    revenue_growth_pct: float = Field(default=0.0)
    material_cost_growth_pct: float = Field(default=0.0)
    service_cost_growth_pct: float = Field(default=0.0)
    personnel_cost_growth_pct: float = Field(default=0.0)
    other_revenue_growth_pct: float = Field(default=0.0)
    depreciation_rate_tangible_pct: float = Field(default=0.0)
    depreciation_rate_intangible_pct: float = Field(default=0.0)
    capex_tangible: float = Field(default=0.0)
    capex_intangible: float = Field(default=0.0)
    new_debt: float = Field(default=0.0)
    debt_repayment: float = Field(default=0.0)
    interest_rate_pct: float = Field(default=0.0)
    tax_rate_pct: float = Field(default=24.0)  # Italian IRES rate
    dividend_payout_pct: float = Field(default=0.0)


class BulkAssumptionsRequest(BaseModel):
    """Request schema for bulk assumptions upsert"""
    assumptions: List[BulkAssumptionInput] = Field(
        ...,
        min_length=1,
        description="List of assumptions for each forecast year"
    )
    auto_generate: bool = Field(
        default=True,
        description="Automatically generate forecast after saving assumptions"
    )


class BulkAssumptionsResponse(BaseModel):
    """Response schema for bulk assumptions upsert"""
    success: bool
    scenario_id: int
    assumptions_saved: int
    forecast_generated: bool
    forecast_years: List[int]
    message: str
