"""
Pydantic schemas for calculation results
"""
from pydantic import BaseModel, ConfigDict
from typing import Dict, Literal
from decimal import Decimal


# ============= WORKING CAPITAL & RATIOS =============

class WorkingCapitalMetrics(BaseModel):
    """Working Capital related metrics"""
    model_config = ConfigDict(from_attributes=True)

    ccln: float  # Capitale Circolante Lordo Netto
    ccn: float   # Capitale Circolante Netto
    ms: float    # Margine di Struttura
    mt: float    # Margine di Tesoreria


class LiquidityRatios(BaseModel):
    """Liquidity ratios"""
    model_config = ConfigDict(from_attributes=True)

    current_ratio: float      # ILC - Indice Liquidità Corrente
    quick_ratio: float        # ISL - Indice di Solvibilità Liquida
    acid_test: float          # Acid Test Ratio


class SolvencyRatios(BaseModel):
    """Solvency/Leverage ratios"""
    model_config = ConfigDict(from_attributes=True)

    autonomy_index: float           # Indice di Autonomia Finanziaria
    leverage_ratio: float           # Indice di Indebitamento
    debt_to_equity: float           # Rapporto Debiti/Patrimonio Netto
    debt_to_production: float       # Debiti/Valore della Produzione


class ProfitabilityRatios(BaseModel):
    """Profitability ratios"""
    model_config = ConfigDict(from_attributes=True)

    roe: float    # Return on Equity
    roi: float    # Return on Investment
    ros: float    # Return on Sales
    rod: float    # Costo del Denaro (Return on Debt)
    ebitda_margin: float  # EBITDA / Revenue
    ebit_margin: float    # EBIT / Revenue
    net_margin: float     # Net Profit / Revenue


class ActivityRatios(BaseModel):
    """Activity/Efficiency ratios"""
    model_config = ConfigDict(from_attributes=True)

    asset_turnover: float         # Fatturato / Totale Attivo
    inventory_turnover_days: float  # DMAG - Giorni di Magazzino
    receivables_turnover_days: float  # DCRED - Giorni di Credito
    payables_turnover_days: float  # DDEB - Giorni di Debito
    working_capital_days: float    # DCCN - Giorni CCN
    cash_conversion_cycle: float   # Ciclo di conversione del denaro


class AllRatios(BaseModel):
    """All financial ratios combined"""
    working_capital: WorkingCapitalMetrics
    liquidity: LiquidityRatios
    solvency: SolvencyRatios
    profitability: ProfitabilityRatios
    activity: ActivityRatios


class SummaryMetrics(BaseModel):
    """Summary financial metrics"""
    revenue: float
    ebitda: float
    ebit: float
    net_profit: float
    total_assets: float
    total_equity: float
    total_debt: float
    working_capital: float
    current_ratio: float
    roe: float
    roi: float
    debt_to_equity: float
    ebitda_margin: float


# ============= ALTMAN Z-SCORE =============

class AltmanComponents(BaseModel):
    """Individual components of Altman Z-Score"""
    model_config = ConfigDict(from_attributes=True)

    A: float  # Working Capital / Total Assets
    B: float  # Retained Earnings / Total Assets
    C: float  # EBIT / Total Assets
    D: float  # Market Value Equity / Total Debt
    E: float  # Revenue / Total Assets (Manufacturing only)


class AltmanResult(BaseModel):
    """Altman Z-Score calculation result"""
    model_config = ConfigDict(from_attributes=True)

    z_score: float
    components: AltmanComponents
    classification: Literal["safe", "gray_zone", "distress"]
    interpretation_it: str
    sector: int
    model_type: Literal["manufacturing", "services"]


# ============= FGPMI RATING =============

class IndicatorScore(BaseModel):
    """Score for an individual indicator"""
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
    value: float
    points: int
    max_points: int
    percentage: float


class FGPMIResult(BaseModel):
    """FGPMI Rating result"""
    model_config = ConfigDict(from_attributes=True)

    total_score: int
    max_score: int
    rating_class: int
    rating_code: str
    rating_description: str
    risk_level: str
    sector_model: str
    revenue_bonus: int
    indicators: Dict[str, IndicatorScore]


# ============= COMBINED RESPONSE =============

class FinancialAnalysis(BaseModel):
    """Complete financial analysis for a year"""
    company_id: int
    year: int
    sector: int
    ratios: AllRatios
    altman: AltmanResult
    fgpmi: FGPMIResult
    summary: SummaryMetrics
