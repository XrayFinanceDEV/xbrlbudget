"""
Detailed Cash Flow Statement Calculator (Italian GAAP - Indirect Method)
Based on VBA implementation - matches RENDICONTO_FINANZIARIO structure
"""
from decimal import Decimal
from typing import Optional
import sys
import os

# Add backend directory to Python path
backend_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from database.models import BalanceSheet, IncomeStatement
from app.schemas.cashflow_detailed import (
    DetailedCashFlowStatement,
    OperatingActivities,
    OperatingActivitiesStart,
    NonCashAdjustments,
    WorkingCapitalChanges,
    CashAdjustments,
    InvestingActivities,
    AssetInvestments,
    FinancingActivities,
    FinancingSource,
    CashReconciliation,
)


class DetailedCashFlowCalculator:
    """
    Calculate detailed cash flow statement using indirect method

    Matches VBA RENDICONTO_FINANZIARIO structure with all line items:
    - Operating activities with detailed breakdowns
    - Investing activities by asset type
    - Financing activities by source
    - Cash reconciliation with verification
    """

    @staticmethod
    def _safe_decimal(value) -> Decimal:
        """Convert value to Decimal safely"""
        if value is None:
            return Decimal("0")
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))

    @staticmethod
    def _round(value: Decimal, places: int = 2) -> Decimal:
        """Round decimal to specified places"""
        from decimal import ROUND_HALF_UP
        quantizer = Decimal('0.1') ** places
        return value.quantize(quantizer, rounding=ROUND_HALF_UP)

    @staticmethod
    def calculate(
        bs_current: BalanceSheet,
        bs_previous: BalanceSheet,
        inc_current: IncomeStatement,
        year: int
    ) -> DetailedCashFlowStatement:
        """
        Calculate detailed cash flow statement for a year

        Args:
            bs_current: Current year balance sheet
            bs_previous: Previous year balance sheet (required for cashflow)
            inc_current: Current year income statement
            year: The year for this cashflow statement

        Returns:
            DetailedCashFlowStatement with all components
        """
        D = DetailedCashFlowCalculator._safe_decimal
        R = DetailedCashFlowCalculator._round

        # ===== A. OPERATING ACTIVITIES =====

        # 1. Starting point - Net profit adjustments
        # IMPORTANT: Use balance sheet profit (sp13) not income statement calculated profit
        # because income statement might have missing data
        net_profit = D(bs_current.sp13_utile_perdita)

        # Income taxes - use detail field if available, otherwise calculate from aggregates
        income_taxes = D(inc_current.ce20_imposte)
        if income_taxes == Decimal("0"):
            # Fallback: calculate from profit_before_tax - net_profit
            profit_before_tax = D(inc_current.profit_before_tax)
            inc_net_profit = D(inc_current.net_profit)
            if profit_before_tax != Decimal("0") or inc_net_profit != Decimal("0"):
                income_taxes = profit_before_tax - inc_net_profit

        # Interest expense (oneri finanziari - other financial income)
        # Use detail fields if available
        interest_expense = D(inc_current.ce15_oneri_finanziari)
        other_financial_income = D(inc_current.ce14_altri_proventi_finanziari)

        # If detail fields are zero, use financial_result aggregate (but negate it)
        # financial_result = income - expense, so we want -(financial_result) = expense - income
        if interest_expense == Decimal("0") and other_financial_income == Decimal("0"):
            financial_result = D(inc_current.financial_result)
            interest_expense_income = -financial_result
        else:
            interest_expense_income = interest_expense - other_financial_income

        # Dividends (if any)
        dividends = D(inc_current.ce13_proventi_partecipazioni)

        # Capital gains/losses (from extraordinary items if any)
        capital_gains_losses = Decimal("0")  # Could be derived from ce18/ce19 if needed

        # Profit before adjustments
        profit_before_adjustments = (
            net_profit + income_taxes + interest_expense_income - dividends + capital_gains_losses
        )

        start = OperatingActivitiesStart(
            net_profit=R(net_profit),
            income_taxes=R(income_taxes),
            interest_expense_income=R(interest_expense_income),
            dividends=R(dividends),
            capital_gains_losses=R(capital_gains_losses),
            profit_before_adjustments=R(profit_before_adjustments)
        )

        # 2. Non-cash adjustments
        depreciation_amortization = D(inc_current.ce09_ammortamenti)
        provisions = D(inc_current.ce11_accantonamenti)
        write_downs = Decimal("0")  # Could be in ce09 or ce17 if needed

        non_cash_total = depreciation_amortization + provisions + write_downs

        non_cash_adjustments = NonCashAdjustments(
            provisions=R(provisions),
            depreciation_amortization=R(depreciation_amortization),
            write_downs=R(write_downs),
            total=R(non_cash_total)
        )

        # Cashflow before working capital changes
        cashflow_before_wc = profit_before_adjustments + non_cash_total

        # 3. Working capital changes
        # Note: In cashflow, increases in assets are negative (use cash), increases in liabilities are positive (provide cash)

        # Inventory: decrease is positive (releases cash)
        delta_inventory = D(bs_previous.sp05_rimanenze) - D(bs_current.sp05_rimanenze)

        # Receivables - short term: decrease is positive (collect cash)
        delta_receivables = D(bs_previous.sp06_crediti_breve) - D(bs_current.sp06_crediti_breve)

        # Payables: increase is positive (defer payment)
        delta_payables = D(bs_current.sp16_debiti_breve) - D(bs_previous.sp16_debiti_breve)

        # Accruals/deferrals - active
        delta_accruals_active = D(bs_previous.sp10_ratei_risconti_attivi) - D(bs_current.sp10_ratei_risconti_attivi)

        # Accruals/deferrals - passive
        delta_accruals_passive = D(bs_current.sp18_ratei_risconti_passivi) - D(bs_previous.sp18_ratei_risconti_passivi)

        # Other WC changes - includes long-term receivables and other balance sheet movements
        # Long-term receivables (sp07) - decrease is positive (converts to short-term or collected)
        delta_long_receivables = D(bs_previous.sp07_crediti_lungo) - D(bs_current.sp07_crediti_lungo)

        # Include long-term receivables in "altri" working capital changes
        other_wc_changes = delta_long_receivables

        # In Italian GAAP cashflow, working capital total INCLUDES accruals/deferrals
        # They are shown as separate line items but included in the total
        wc_total = (delta_inventory + delta_receivables + delta_payables +
                   delta_accruals_active + delta_accruals_passive + other_wc_changes)

        working_capital_changes = WorkingCapitalChanges(
            delta_inventory=R(delta_inventory),
            delta_receivables=R(delta_receivables),
            delta_payables=R(delta_payables),
            delta_accruals_deferrals_active=R(delta_accruals_active),
            delta_accruals_deferrals_passive=R(delta_accruals_passive),
            other_wc_changes=R(other_wc_changes),
            total=R(wc_total)
        )

        # Cashflow after working capital (now includes accruals)
        cashflow_after_wc = cashflow_before_wc + wc_total

        # 4. Cash adjustments (other adjustments to arrive at net operating cashflow)
        # Interest paid (negative because it's an outflow)
        interest_paid_received = -interest_expense_income

        # Taxes paid (negative because it's an outflow)
        taxes_paid = -income_taxes

        # Dividends received (already in profit)
        dividends_received = Decimal("0")

        # Use of provisions (negative because it's a cash outflow when provisions are used)
        # Estimate: provisions used = previous provisions + new provisions - current provisions
        use_of_provisions = -(D(bs_previous.sp14_fondi_rischi) + provisions - D(bs_current.sp14_fondi_rischi))

        # Other cash changes - set to 0 because accruals are already in WC section
        # In Italian GAAP cashflow, accruals/deferrals are part of working capital changes,
        # not separate "other cash changes"
        other_cash_changes = Decimal("0")

        cash_adjustments_total = (interest_paid_received + taxes_paid + dividends_received +
                                 use_of_provisions + other_cash_changes)

        cash_adjustments = CashAdjustments(
            interest_paid_received=R(interest_paid_received),
            taxes_paid=R(taxes_paid),
            dividends_received=R(dividends_received),
            use_of_provisions=R(use_of_provisions),
            other_cash_changes=R(other_cash_changes),
            total=R(cash_adjustments_total)
        )

        # Total operating cashflow
        total_operating_cashflow = cashflow_after_wc + cash_adjustments_total

        operating_activities = OperatingActivities(
            start=start,
            non_cash_adjustments=non_cash_adjustments,
            cashflow_before_wc=R(cashflow_before_wc),
            working_capital_changes=working_capital_changes,
            cashflow_after_wc=R(cashflow_after_wc),
            cash_adjustments=cash_adjustments,
            total_operating_cashflow=R(total_operating_cashflow)
        )

        # ===== B. INVESTING ACTIVITIES =====

        # Tangible assets (immobilizzazioni materiali)
        # CAPEX = -(Change in fixed assets + Depreciation)
        # This is because: Ending = Beginning + CAPEX - Depreciation
        # So: CAPEX = Ending - Beginning + Depreciation
        # Negative sign because it's a cash outflow
        delta_tangible = D(bs_current.sp03_immob_materiali) - D(bs_previous.sp03_immob_materiali)

        # Split total depreciation between tangible and intangible based on asset proportions
        total_fixed_assets_previous = D(bs_previous.sp02_immob_immateriali) + D(bs_previous.sp03_immob_materiali)
        if total_fixed_assets_previous > 0:
            tangible_ratio = D(bs_previous.sp03_immob_materiali) / total_fixed_assets_previous
        else:
            tangible_ratio = Decimal("0.8")  # Default assumption if no prior assets

        depreciation_tangible = depreciation_amortization * tangible_ratio
        depreciation_intangible = depreciation_amortization * (Decimal("1") - tangible_ratio)

        # Tangible CAPEX (negative = cash outflow)
        tangible_investments = -(delta_tangible + depreciation_tangible)
        tangible_disinvestments = Decimal("0")  # Would need disposal data
        tangible_net = tangible_investments + tangible_disinvestments

        tangible_assets = AssetInvestments(
            investments=R(tangible_investments),
            disinvestments=R(tangible_disinvestments),
            net=R(tangible_net)
        )

        # Intangible assets (immobilizzazioni immateriali)
        delta_intangible = D(bs_current.sp02_immob_immateriali) - D(bs_previous.sp02_immob_immateriali)

        # Intangible CAPEX (negative = cash outflow)
        intangible_investments = -(delta_intangible + depreciation_intangible)
        intangible_disinvestments = Decimal("0")
        intangible_net = intangible_investments + intangible_disinvestments

        intangible_assets = AssetInvestments(
            investments=R(intangible_investments),
            disinvestments=R(intangible_disinvestments),
            net=R(intangible_net)
        )

        # Financial assets
        delta_financial = (
            (D(bs_current.sp04_immob_finanziarie) + D(bs_current.sp08_attivita_finanziarie)) -
            (D(bs_previous.sp04_immob_finanziarie) + D(bs_previous.sp08_attivita_finanziarie))
        )
        financial_investments = -delta_financial if delta_financial > 0 else Decimal("0")
        financial_disinvestments = delta_financial if delta_financial < 0 else Decimal("0")
        financial_net = financial_disinvestments - financial_investments

        financial_assets = AssetInvestments(
            investments=R(financial_investments),
            disinvestments=R(financial_disinvestments),
            net=R(financial_net)
        )

        # Total investing cashflow
        total_investing_cashflow = tangible_net + intangible_net + financial_net

        investing_activities = InvestingActivities(
            tangible_assets=tangible_assets,
            intangible_assets=intangible_assets,
            financial_assets=financial_assets,
            total_investing_cashflow=R(total_investing_cashflow)
        )

        # ===== C. FINANCING ACTIVITIES =====

        # Third-party funds (debt)
        current_debt = D(bs_current.sp16_debiti_breve) + D(bs_current.sp17_debiti_lungo)
        previous_debt = D(bs_previous.sp16_debiti_breve) + D(bs_previous.sp17_debiti_lungo)
        delta_debt = current_debt - previous_debt

        debt_increases = delta_debt if delta_debt > 0 else Decimal("0")
        debt_decreases = -delta_debt if delta_debt < 0 else Decimal("0")
        debt_net = delta_debt

        third_party_funds = FinancingSource(
            increases=R(debt_increases),
            decreases=R(debt_decreases),
            net=R(debt_net)
        )

        # Own funds (equity - excluding current year profit)
        current_equity_base = D(bs_current.sp11_capitale) + D(bs_current.sp12_riserve)
        previous_equity_base = D(bs_previous.sp11_capitale) + D(bs_previous.sp12_riserve)
        delta_equity = current_equity_base - previous_equity_base

        equity_increases = delta_equity if delta_equity > 0 else Decimal("0")
        equity_decreases = -delta_equity if delta_equity < 0 else Decimal("0")
        equity_net = delta_equity

        own_funds = FinancingSource(
            increases=R(equity_increases),
            decreases=R(equity_decreases),
            net=R(equity_net)
        )

        # Total financing cashflow
        total_financing_cashflow = debt_net + equity_net

        financing_activities = FinancingActivities(
            third_party_funds=third_party_funds,
            own_funds=own_funds,
            total_financing_cashflow=R(total_financing_cashflow)
        )

        # ===== CASH RECONCILIATION =====

        # Total cashflow from all activities
        total_cashflow = total_operating_cashflow + total_investing_cashflow + total_financing_cashflow

        # Cash balances
        cash_beginning = D(bs_previous.sp09_disponibilita_liquide)
        cash_ending = D(bs_current.sp09_disponibilita_liquide)
        actual_cash_change = cash_ending - cash_beginning

        # Verification: total cashflow should equal actual cash change
        verification_ok = abs(total_cashflow - actual_cash_change) < Decimal("1.0")  # Allow 1 euro tolerance

        cash_reconciliation = CashReconciliation(
            total_cashflow=R(total_cashflow),
            cash_beginning=R(cash_beginning),
            cash_ending=R(cash_ending),
            difference=R(actual_cash_change),
            verification_ok=verification_ok
        )

        # Return complete statement
        return DetailedCashFlowStatement(
            year=year,
            operating_activities=operating_activities,
            investing_activities=investing_activities,
            financing_activities=financing_activities,
            cash_reconciliation=cash_reconciliation
        )
