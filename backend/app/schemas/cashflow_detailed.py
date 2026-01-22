"""
Pydantic schemas for Detailed Cash Flow Statement (Italian GAAP - Indirect Method)
Based on VBA implementation structure
"""
from pydantic import BaseModel, Field
from decimal import Decimal
from typing import Optional


# ===== Operating Activities Components =====

class OperatingActivitiesStart(BaseModel):
    """Starting point for operating activities - profit adjustments"""
    net_profit: Decimal = Field(description="Utile (perdita) dell'esercizio")
    income_taxes: Decimal = Field(description="Imposte sul reddito")
    interest_expense_income: Decimal = Field(description="Interessi passivi/(interessi attivi)")
    dividends: Decimal = Field(default=Decimal("0"), description="(Dividendi)")
    capital_gains_losses: Decimal = Field(default=Decimal("0"), description="(Plusvalenze)/minusvalenze")
    profit_before_adjustments: Decimal = Field(
        description="1. Utile dell'esercizio prima d'imposte, interessi, dividendi e plus/minusvalenze"
    )


class NonCashAdjustments(BaseModel):
    """Non-cash items that don't affect working capital"""
    provisions: Decimal = Field(description="Accantonamenti ai fondi")
    depreciation_amortization: Decimal = Field(description="Ammortamenti delle immobilizzazioni")
    write_downs: Decimal = Field(default=Decimal("0"), description="Svalutazioni per perdite durevoli di valore")
    total: Decimal = Field(
        description="Totale rettifiche per elementi non monetari"
    )


class WorkingCapitalChanges(BaseModel):
    """Changes in working capital components"""
    delta_inventory: Decimal = Field(description="Decremento/(incremento) delle rimanenze")
    delta_receivables: Decimal = Field(description="Decremento/(incremento) dei crediti entro esercizio")
    delta_payables: Decimal = Field(description="Incremento/(decremento) dei debiti entro esercizio")
    delta_accruals_deferrals_active: Decimal = Field(
        default=Decimal("0"),
        description="Decremento/(incremento) ratei e risconti attivi"
    )
    delta_accruals_deferrals_passive: Decimal = Field(
        default=Decimal("0"),
        description="Incremento/(decremento) ratei e risconti passivi"
    )
    other_wc_changes: Decimal = Field(
        default=Decimal("0"),
        description="Altri incrementi/(decrementi) del capitale circolante netto"
    )
    total: Decimal = Field(description="Totale variazioni del capitale circolante netto")


class CashAdjustments(BaseModel):
    """Cash-related adjustments"""
    interest_paid_received: Decimal = Field(description="Interessi incassati/(pagati)")
    taxes_paid: Decimal = Field(description="(Imposte sul reddito pagate)")
    dividends_received: Decimal = Field(default=Decimal("0"), description="Dividendi incassati")
    use_of_provisions: Decimal = Field(default=Decimal("0"), description="(Utilizzo dei fondi)")
    other_cash_changes: Decimal = Field(default=Decimal("0"), description="Altri incassi/(pagamenti)")
    total: Decimal = Field(description="Totale altre rettifiche")


class OperatingActivities(BaseModel):
    """Complete operating activities section"""
    start: OperatingActivitiesStart
    non_cash_adjustments: NonCashAdjustments
    cashflow_before_wc: Decimal = Field(description="2. Flusso finanziario prima delle variazioni del ccn")
    working_capital_changes: WorkingCapitalChanges
    cashflow_after_wc: Decimal = Field(description="3. Flusso finanziario dopo le variazioni del ccn")
    cash_adjustments: CashAdjustments
    total_operating_cashflow: Decimal = Field(description="Flusso finanziario dell'attività operativa (A)")


# ===== Investing Activities Components =====

class AssetInvestments(BaseModel):
    """Investment/disinvestment for a specific asset category"""
    investments: Decimal = Field(description="(Investimenti)")
    disinvestments: Decimal = Field(default=Decimal("0"), description="Disinvestimenti")
    net: Decimal = Field(description="Net cashflow for this asset category")


class InvestingActivities(BaseModel):
    """Complete investing activities section"""
    tangible_assets: AssetInvestments = Field(description="Immobilizzazioni materiali")
    intangible_assets: AssetInvestments = Field(description="Immobilizzazioni immateriali")
    financial_assets: AssetInvestments = Field(description="Attività finanziarie (immobilizzate e circolanti)")
    total_investing_cashflow: Decimal = Field(description="Flusso finanziario dell'attività di investimento (B)")


# ===== Financing Activities Components =====

class FinancingSource(BaseModel):
    """Financing from a specific source (debt or equity)"""
    increases: Decimal = Field(description="Incrementi")
    decreases: Decimal = Field(description="(Decrementi)")
    net: Decimal = Field(description="Net change")


class FinancingActivities(BaseModel):
    """Complete financing activities section"""
    third_party_funds: FinancingSource = Field(description="Mezzi di terzi (debt)")
    own_funds: FinancingSource = Field(description="Mezzi propri (equity)")
    total_financing_cashflow: Decimal = Field(description="Flusso finanziario dell'attività di finanziamento (C)")


# ===== Cash Reconciliation =====

class CashReconciliation(BaseModel):
    """Cash balance reconciliation"""
    total_cashflow: Decimal = Field(description="Incremento (decremento) delle disponibilità liquide (A±B±C)")
    cash_beginning: Decimal = Field(description="Disponibilità liquide all'inizio dell'esercizio")
    cash_ending: Decimal = Field(description="Disponibilità liquide alla fine dell'esercizio")
    difference: Decimal = Field(description="Differenza")
    verification_ok: bool = Field(description="VERIFICA: difference matches total_cashflow")


# ===== Complete Detailed Cash Flow Statement =====

class DetailedCashFlowStatement(BaseModel):
    """Complete detailed cash flow statement (Italian GAAP - Indirect Method)"""
    year: int
    operating_activities: OperatingActivities
    investing_activities: InvestingActivities
    financing_activities: FinancingActivities
    cash_reconciliation: CashReconciliation


class MultiYearDetailedCashFlow(BaseModel):
    """Multi-year detailed cash flow statement"""
    company_id: int
    scenario_id: Optional[int] = Field(
        default=None,
        description="Budget scenario ID (null for historical data only)"
    )
    base_year: int = Field(description="Base year for comparisons (e.g., 2023)")
    cashflows: list[DetailedCashFlowStatement] = Field(
        description="Cash flow statements for each year (2024, 2025, 2026, 2027)"
    )
