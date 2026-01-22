"""
Cash Flow Statement Calculator
Implements indirect method for cash flow calculation
"""
from decimal import Decimal
from typing import NamedTuple, Optional
from database.models import BalanceSheet, IncomeStatement


class CashFlowComponents(NamedTuple):
    """Components of cash flow calculation"""
    # Operating activities
    net_profit: Decimal
    depreciation: Decimal
    delta_receivables: Decimal
    delta_inventory: Decimal
    delta_payables: Decimal
    operating_cf: Decimal

    # Investing activities
    capex: Decimal
    investing_cf: Decimal

    # Financing activities
    delta_debt: Decimal
    delta_equity: Decimal
    financing_cf: Decimal

    # Total
    total_cf: Decimal
    actual_cash_change: Decimal
    cash_beginning: Decimal
    cash_ending: Decimal


class CashFlowRatios(NamedTuple):
    """Cash flow related ratios"""
    ocf_margin: Decimal  # Operating CF / EBITDA
    free_cash_flow: Decimal  # Operating CF + Investing CF
    cash_conversion: Decimal  # Operating CF / Net Profit
    capex_to_operating_cf: Decimal  # CAPEX / Operating CF


class CashFlowResult(NamedTuple):
    """Complete cash flow statement result"""
    year: int
    components: CashFlowComponents
    ratios: CashFlowRatios


class CashFlowCalculator:
    """
    Calculate cash flow statement using indirect method

    The indirect method starts with net profit and adjusts for:
    - Non-cash expenses (depreciation)
    - Changes in working capital
    - Investing activities (CAPEX)
    - Financing activities (debt and equity changes)
    """

    @staticmethod
    def _safe_divide(numerator: Decimal, denominator: Decimal, default: Decimal = Decimal('0')) -> Decimal:
        """Safe division with zero protection"""
        try:
            if denominator == 0:
                return default
            return numerator / denominator
        except (ValueError, TypeError, ArithmeticError):
            return default

    @staticmethod
    def _round_decimal(value: Decimal, places: int = 2) -> Decimal:
        """Round decimal to specified places"""
        from decimal import ROUND_HALF_UP
        quantizer = Decimal('0.1') ** places
        return value.quantize(quantizer, rounding=ROUND_HALF_UP)

    @staticmethod
    def calculate(
        bs_current: BalanceSheet,
        bs_previous: Optional[BalanceSheet],
        inc_current: IncomeStatement,
        ebitda: Decimal
    ) -> CashFlowResult:
        """
        Calculate cash flow statement for a year

        Args:
            bs_current: Current year balance sheet
            bs_previous: Previous year balance sheet (None if first year)
            inc_current: Current year income statement
            ebitda: Current year EBITDA (from income statement calculated field)

        Returns:
            CashFlowResult with all components and ratios
        """
        round_decimal = CashFlowCalculator._round_decimal

        # 1. OPERATING ACTIVITIES
        net_profit = Decimal(str(inc_current.net_profit))
        depreciation = Decimal(str(inc_current.ce09_ammortamenti))

        # Start with net profit
        operating_cf = net_profit

        # Add back depreciation (non-cash expense)
        operating_cf += depreciation

        # Adjust for changes in working capital
        if bs_previous:
            # Increase in receivables reduces cash (cash tied up)
            delta_receivables = (
                Decimal(str(bs_current.sp06_crediti_breve)) -
                Decimal(str(bs_previous.sp06_crediti_breve))
            )
            operating_cf -= delta_receivables

            # Increase in inventory reduces cash
            delta_inventory = (
                Decimal(str(bs_current.sp05_rimanenze)) -
                Decimal(str(bs_previous.sp05_rimanenze))
            )
            operating_cf -= delta_inventory

            # Increase in payables increases cash (we keep cash longer)
            delta_payables = (
                Decimal(str(bs_current.sp16_debiti_breve)) -
                Decimal(str(bs_previous.sp16_debiti_breve))
            )
            operating_cf += delta_payables
        else:
            # First year - no comparison possible
            delta_receivables = Decimal('0')
            delta_inventory = Decimal('0')
            delta_payables = Decimal('0')

        # 2. INVESTING ACTIVITIES
        if bs_previous:
            # CAPEX = Increase in fixed assets + depreciation
            # (depreciation represents the decline in assets, so actual investment is higher)
            delta_fixed_assets = (
                Decimal(str(bs_current.fixed_assets)) -
                Decimal(str(bs_previous.fixed_assets))
            )
            capex = delta_fixed_assets + depreciation
        else:
            # First year - assume depreciation as minimum CAPEX
            capex = depreciation

        # Negative because it's cash outflow
        investing_cf = -capex

        # 3. FINANCING ACTIVITIES
        if bs_previous:
            # Change in total debt
            delta_debt = (
                Decimal(str(bs_current.total_debt)) -
                Decimal(str(bs_previous.total_debt))
            )

            # Change in equity (excluding current year profit)
            # We look at capital + reserves only (profit is in operating)
            current_equity_base = (
                Decimal(str(bs_current.sp11_capitale)) +
                Decimal(str(bs_current.sp12_riserve))
            )
            previous_equity_base = (
                Decimal(str(bs_previous.sp11_capitale)) +
                Decimal(str(bs_previous.sp12_riserve))
            )
            delta_equity = current_equity_base - previous_equity_base

            # Financing CF = debt changes + equity changes (excluding profit)
            financing_cf = delta_debt + delta_equity
        else:
            delta_debt = Decimal('0')
            delta_equity = Decimal('0')
            financing_cf = Decimal('0')

        # 4. TOTAL CASH FLOW
        total_cf = operating_cf + investing_cf + financing_cf

        # 5. VERIFY WITH ACTUAL CASH CHANGE
        cash_ending = Decimal(str(bs_current.sp09_disponibilita_liquide))

        if bs_previous:
            cash_beginning = Decimal(str(bs_previous.sp09_disponibilita_liquide))
            actual_cash_change = cash_ending - cash_beginning
        else:
            cash_beginning = Decimal('0')
            actual_cash_change = cash_ending

        # Create components
        components = CashFlowComponents(
            net_profit=round_decimal(net_profit),
            depreciation=round_decimal(depreciation),
            delta_receivables=round_decimal(delta_receivables),
            delta_inventory=round_decimal(delta_inventory),
            delta_payables=round_decimal(delta_payables),
            operating_cf=round_decimal(operating_cf),
            capex=round_decimal(capex),
            investing_cf=round_decimal(investing_cf),
            delta_debt=round_decimal(delta_debt),
            delta_equity=round_decimal(delta_equity),
            financing_cf=round_decimal(financing_cf),
            total_cf=round_decimal(total_cf),
            actual_cash_change=round_decimal(actual_cash_change),
            cash_beginning=round_decimal(cash_beginning),
            cash_ending=round_decimal(cash_ending)
        )

        # Calculate ratios
        ebitda_decimal = Decimal(str(ebitda))

        ocf_margin = CashFlowCalculator._safe_divide(operating_cf, ebitda_decimal) * Decimal('100')
        free_cash_flow = operating_cf + investing_cf
        cash_conversion = CashFlowCalculator._safe_divide(operating_cf, net_profit) * Decimal('100') if net_profit != 0 else Decimal('0')
        capex_to_operating_cf = CashFlowCalculator._safe_divide(capex, operating_cf) * Decimal('100') if operating_cf > 0 else Decimal('0')

        ratios = CashFlowRatios(
            ocf_margin=round_decimal(ocf_margin, 2),
            free_cash_flow=round_decimal(free_cash_flow),
            cash_conversion=round_decimal(cash_conversion, 2),
            capex_to_operating_cf=round_decimal(capex_to_operating_cf, 2)
        )

        return CashFlowResult(
            year=bs_current.financial_year.year,
            components=components,
            ratios=ratios
        )

    @staticmethod
    def calculate_multi_year(
        balance_sheets: list[tuple[BalanceSheet, BalanceSheet | None]],
        income_statements: list[IncomeStatement],
        ebitdas: list[Decimal]
    ) -> list[CashFlowResult]:
        """
        Calculate cash flow for multiple years

        Args:
            balance_sheets: List of (current, previous) balance sheet tuples
            income_statements: List of income statements
            ebitdas: List of EBITDA values

        Returns:
            List of CashFlowResult, one per year
        """
        if len(balance_sheets) != len(income_statements) or len(balance_sheets) != len(ebitdas):
            raise ValueError("All input lists must have the same length")

        results = []
        for (bs_current, bs_previous), inc_current, ebitda in zip(balance_sheets, income_statements, ebitdas):
            result = CashFlowCalculator.calculate(bs_current, bs_previous, inc_current, ebitda)
            results.append(result)

        return results
