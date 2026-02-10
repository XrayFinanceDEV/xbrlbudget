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


class CoverageRatios(BaseModel):
    """Coverage/Solidity ratios (Indici di Solidità)"""
    model_config = ConfigDict(from_attributes=True)

    fixed_assets_coverage_with_equity_and_ltdebt: float  # (CN+PF)/AF
    fixed_assets_coverage_with_equity: float              # CN/AF
    independence_from_third_parties: float                # CN/(PC+PF)


class TurnoverRatios(BaseModel):
    """Turnover ratios (actual turnover, not days)"""
    model_config = ConfigDict(from_attributes=True)

    inventory_turnover: float        # TdM = CO/RD
    receivables_turnover: float      # TdC = RIC/LD
    payables_turnover: float         # TdD = (CO+AC+ODG)/PC
    working_capital_turnover: float  # TdCCN = RIC/CCN
    total_assets_turnover: float     # TdAT = RIC/TA


class ExtendedProfitabilityRatios(BaseModel):
    """Extended profitability indices"""
    model_config = ConfigDict(from_attributes=True)

    spread: float                      # ROI - ROD
    financial_leverage_effect: float   # (PC+PF)/CN
    ebitda_on_sales: float            # MOL/RIC
    financial_charges_on_revenue: float  # OF/RIC


class EfficiencyRatios(BaseModel):
    """Efficiency ratios (Indici di Efficienza)"""
    model_config = ConfigDict(from_attributes=True)

    revenue_per_employee_cost: float   # RIC/CL (Rendimento dipendenti)
    revenue_per_materials_cost: float  # RIC/CO (Rendimento materie)


class BreakEvenAnalysis(BaseModel):
    """Break Even Point analysis"""
    model_config = ConfigDict(from_attributes=True)

    fixed_costs: float                  # Costi Fissi
    variable_costs: float               # Costi Variabili
    contribution_margin: float          # Margine di Contribuzione
    contribution_margin_percentage: float  # %MdC
    break_even_revenue: float           # Ricavi BEP
    safety_margin: float                # Margine di Sicurezza
    operating_leverage: float           # Leva Operativa
    fixed_cost_multiplier: float        # Moltiplicatore CF


class AllRatios(BaseModel):
    """All financial ratios combined"""
    working_capital: WorkingCapitalMetrics
    liquidity: LiquidityRatios
    solvency: SolvencyRatios
    profitability: ProfitabilityRatios
    activity: ActivityRatios
    coverage: CoverageRatios
    turnover: TurnoverRatios
    extended_profitability: ExtendedProfitabilityRatios
    efficiency: EfficiencyRatios
    break_even: BreakEvenAnalysis


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


# ============= CASH FLOW STATEMENT =============

class CashFlowComponents(BaseModel):
    """Components of cash flow statement (indirect method)"""
    model_config = ConfigDict(from_attributes=True)

    # Operating activities
    net_profit: float
    depreciation: float
    delta_receivables: float
    delta_inventory: float
    delta_payables: float
    operating_cf: float

    # Investing activities
    capex: float
    investing_cf: float

    # Financing activities
    delta_debt: float
    delta_equity: float
    financing_cf: float

    # Total
    total_cf: float
    actual_cash_change: float
    cash_beginning: float
    cash_ending: float


class CashFlowRatios(BaseModel):
    """Cash flow related ratios"""
    model_config = ConfigDict(from_attributes=True)

    ocf_margin: float  # Operating CF / EBITDA
    free_cash_flow: float  # Operating CF + Investing CF
    cash_conversion: float  # Operating CF / Net Profit
    capex_to_operating_cf: float  # CAPEX / Operating CF


class CashFlowResult(BaseModel):
    """Complete cash flow statement result"""
    model_config = ConfigDict(from_attributes=True)

    year: int
    components: CashFlowComponents
    ratios: CashFlowRatios
