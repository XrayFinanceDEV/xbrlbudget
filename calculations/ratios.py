"""
Financial Ratios Calculator (INDICI)
Implements all financial ratios from the Excel INDICI sheet
"""
from decimal import Decimal
from typing import Dict, Optional, NamedTuple
from database.models import BalanceSheet, IncomeStatement
from calculations.base import BaseCalculator


class WorkingCapitalMetrics(NamedTuple):
    """Working Capital related metrics"""
    ccln: Decimal  # Capitale Circolante Lordo Netto
    ccn: Decimal   # Capitale Circolante Netto
    ms: Decimal    # Margine di Struttura
    mt: Decimal    # Margine di Tesoreria


class LiquidityRatios(NamedTuple):
    """Liquidity ratios"""
    current_ratio: Decimal      # ILC - Indice Liquidità Corrente
    quick_ratio: Decimal        # ISL - Indice di Solvibilità Liquida
    acid_test: Decimal          # Acid Test Ratio


class SolvencyRatios(NamedTuple):
    """Solvency/Leverage ratios"""
    autonomy_index: Decimal           # Indice di Autonomia Finanziaria
    leverage_ratio: Decimal           # Indice di Indebitamento
    debt_to_equity: Decimal           # Rapporto Debiti/Patrimonio Netto
    debt_to_production: Decimal       # Debiti/Valore della Produzione


class ProfitabilityRatios(NamedTuple):
    """Profitability ratios"""
    roe: Decimal    # Return on Equity
    roi: Decimal    # Return on Investment
    ros: Decimal    # Return on Sales
    rod: Decimal    # Costo del Denaro (Return on Debt)
    ebitda_margin: Decimal  # EBITDA / Revenue
    ebit_margin: Decimal    # EBIT / Revenue
    net_margin: Decimal     # Net Profit / Revenue


class ActivityRatios(NamedTuple):
    """Activity/Efficiency ratios"""
    asset_turnover: Decimal         # Fatturato / Totale Attivo
    inventory_turnover_days: Decimal  # DMAG - Giorni di Magazzino
    receivables_turnover_days: Decimal  # DCRED - Giorni di Credito
    payables_turnover_days: Decimal  # DDEB - Giorni di Debito
    working_capital_days: Decimal    # DCCN - Giorni CCN
    cash_conversion_cycle: Decimal   # Ciclo di conversione del denaro


class CoverageRatios(NamedTuple):
    """Coverage/Solidity ratios (Indici di Solidità)"""
    fixed_assets_coverage_with_equity_and_ltdebt: Decimal  # (CN+PF)/AF
    fixed_assets_coverage_with_equity: Decimal              # CN/AF
    independence_from_third_parties: Decimal                # CN/(PC+PF)


class TurnoverRatios(NamedTuple):
    """Turnover ratios (actual turnover, not days)"""
    inventory_turnover: Decimal        # TdM = CO/RD
    receivables_turnover: Decimal      # TdC = RIC/LD
    payables_turnover: Decimal         # TdD = (CO+AC+ODG)/PC
    working_capital_turnover: Decimal  # TdCCN = RIC/CCN
    total_assets_turnover: Decimal     # TdAT = RIC/TA


class ExtendedProfitabilityRatios(NamedTuple):
    """Extended profitability indices"""
    spread: Decimal                      # ROI - ROD
    financial_leverage_effect: Decimal   # (PC+PF)/CN
    ebitda_on_sales: Decimal            # MOL/RIC
    financial_charges_on_revenue: Decimal  # OF/RIC


class EfficiencyRatios(NamedTuple):
    """Efficiency ratios (Indici di Efficienza)"""
    revenue_per_employee_cost: Decimal   # RIC/CL (Rendimento dipendenti)
    revenue_per_materials_cost: Decimal  # RIC/CO (Rendimento materie)


class BreakEvenAnalysis(NamedTuple):
    """Break Even Point analysis"""
    fixed_costs: Decimal                  # Costi Fissi
    variable_costs: Decimal               # Costi Variabili
    contribution_margin: Decimal          # Margine di Contribuzione = RIC - CV
    contribution_margin_percentage: Decimal  # %MdC = MdC/RIC
    break_even_revenue: Decimal           # Ricavi BEP = CF/%MdC
    safety_margin: Decimal                # Margine di Sicurezza = 1 - (BEP/RIC)
    operating_leverage: Decimal           # Leva Operativa = MdC/MON
    fixed_cost_multiplier: Decimal        # Moltiplicatore CF = 1/%MdC


class FinancialRatiosCalculator(BaseCalculator):
    """
    Calculator for all financial ratios and indices
    Matches Excel INDICI sheet functionality
    """

    def __init__(self, balance_sheet: BalanceSheet, income_statement: IncomeStatement):
        """
        Initialize calculator with financial statements

        Args:
            balance_sheet: Balance Sheet data
            income_statement: Income Statement data
        """
        self.bs = balance_sheet
        self.inc = income_statement

    # ============= WORKING CAPITAL METRICS =============

    def calculate_working_capital_metrics(self) -> WorkingCapitalMetrics:
        """
        Calculate Working Capital related metrics

        Returns:
            WorkingCapitalMetrics with CCLN, CCN, MS, MT
        """
        # CCLN = Capital Circolante Lordo Netto = Attivo Corrente
        ccln = self.bs.current_assets

        # CCN = Capitale Circolante Netto = Attivo Corrente - Passivo Corrente
        ccn = self.bs.working_capital_net

        # MS = Margine di Struttura = Patrimonio Netto - Immobilizzazioni
        ms = self.bs.total_equity - self.bs.fixed_assets

        # MT = Margine di Tesoreria = (Liquidità + Crediti) - Passivo Corrente
        # MT = Attivo Corrente - Rimanenze - Passivo Corrente
        mt = (
            self.bs.sp06_crediti_breve +
            self.bs.sp07_crediti_lungo +
            self.bs.sp09_disponibilita_liquide -
            self.bs.current_liabilities
        )

        return WorkingCapitalMetrics(
            ccln=self.round_decimal(ccln),
            ccn=self.round_decimal(ccn),
            ms=self.round_decimal(ms),
            mt=self.round_decimal(mt)
        )

    # ============= LIQUIDITY RATIOS =============

    def calculate_liquidity_ratios(self) -> LiquidityRatios:
        """
        Calculate Liquidity ratios

        Returns:
            LiquidityRatios with Current Ratio, Quick Ratio, Acid Test
        """
        # ILC = Current Ratio = Attivo Corrente / Passivo Corrente
        current_ratio = self.safe_divide(
            self.bs.current_assets,
            self.bs.current_liabilities
        )

        # Quick Ratio = (Liquidità + Crediti) / Passivo Corrente
        liquid_assets = (
            self.bs.sp06_crediti_breve +
            self.bs.sp07_crediti_lungo +
            self.bs.sp09_disponibilita_liquide
        )
        quick_ratio = self.safe_divide(
            liquid_assets,
            self.bs.current_liabilities
        )

        # Acid Test = (Liquidità + Crediti + Attività Finanziarie) / Passivo Corrente
        most_liquid = (
            self.bs.sp06_crediti_breve +
            self.bs.sp07_crediti_lungo +
            self.bs.sp08_attivita_finanziarie +
            self.bs.sp09_disponibilita_liquide
        )
        acid_test = self.safe_divide(
            most_liquid,
            self.bs.current_liabilities
        )

        return LiquidityRatios(
            current_ratio=self.round_decimal(current_ratio, 4),
            quick_ratio=self.round_decimal(quick_ratio, 4),
            acid_test=self.round_decimal(acid_test, 4)
        )

    # ============= SOLVENCY RATIOS =============

    def calculate_solvency_ratios(self) -> SolvencyRatios:
        """
        Calculate Solvency/Leverage ratios

        Returns:
            SolvencyRatios with autonomy, leverage, debt ratios
        """
        # Indice di Autonomia = Patrimonio Netto / Totale Attivo
        autonomy_index = self.safe_divide(
            self.bs.total_equity,
            self.bs.total_assets
        )

        # Indice di Indebitamento = Immobilizzazioni / Patrimonio Netto
        leverage_ratio = self.safe_divide(
            self.bs.fixed_assets,
            self.bs.total_equity
        )

        # Debt to Equity = Debiti Totali / Patrimonio Netto
        debt_to_equity = self.safe_divide(
            self.bs.total_debt,
            self.bs.total_equity
        )

        # Debt to Production Value = Debiti Totali / Valore della Produzione
        debt_to_production = self.safe_divide(
            self.bs.total_debt,
            self.inc.production_value
        )

        return SolvencyRatios(
            autonomy_index=self.round_decimal(autonomy_index, 4),
            leverage_ratio=self.round_decimal(leverage_ratio, 4),
            debt_to_equity=self.round_decimal(debt_to_equity, 4),
            debt_to_production=self.round_decimal(debt_to_production, 4)
        )

    # ============= PROFITABILITY RATIOS =============

    def calculate_profitability_ratios(self) -> ProfitabilityRatios:
        """
        Calculate Profitability ratios

        Returns:
            ProfitabilityRatios with ROE, ROI, ROS, ROD, margins
        """
        # ROE = Return on Equity = Utile Netto / Patrimonio Netto
        roe = self.safe_divide(
            self.inc.net_profit,
            self.bs.total_equity
        )

        # ROI = Return on Investment = EBIT / Totale Attivo
        roi = self.safe_divide(
            self.inc.ebit,
            self.bs.total_assets
        )

        # ROS = Return on Sales = Utile Netto / Fatturato
        ros = self.safe_divide(
            self.inc.net_profit,
            self.inc.revenue
        )

        # ROD = Costo del Denaro = Oneri Finanziari / Debiti Totali
        rod = self.safe_divide(
            self.inc.ce15_oneri_finanziari,
            self.bs.total_debt
        )

        # EBITDA Margin = EBITDA / Fatturato
        ebitda_margin = self.safe_divide(
            self.inc.ebitda,
            self.inc.revenue
        )

        # EBIT Margin = EBIT / Fatturato
        ebit_margin = self.safe_divide(
            self.inc.ebit,
            self.inc.revenue
        )

        # Net Margin = Utile Netto / Fatturato
        net_margin = self.safe_divide(
            self.inc.net_profit,
            self.inc.revenue
        )

        return ProfitabilityRatios(
            roe=self.round_decimal(roe, 4),
            roi=self.round_decimal(roi, 4),
            ros=self.round_decimal(ros, 4),
            rod=self.round_decimal(rod, 4),
            ebitda_margin=self.round_decimal(ebitda_margin, 4),
            ebit_margin=self.round_decimal(ebit_margin, 4),
            net_margin=self.round_decimal(net_margin, 4)
        )

    # ============= ACTIVITY RATIOS =============

    def calculate_activity_ratios(self, days_in_year: int = 360) -> ActivityRatios:
        """
        Calculate Activity/Efficiency ratios

        Args:
            days_in_year: Days to use for calculations (default: 360)

        Returns:
            ActivityRatios with turnover and days calculations
        """
        # Asset Turnover = Fatturato / Totale Attivo
        asset_turnover = self.safe_divide(
            self.inc.revenue,
            self.bs.total_assets
        )

        # DMAG = Giorni di Magazzino = 360 * Rimanenze / Fatturato
        inventory_turnover_days = self.safe_divide(
            Decimal(days_in_year) * self.bs.sp05_rimanenze,
            self.inc.revenue
        )

        # DCRED = Giorni di Credito = 360 * Crediti / Fatturato
        total_receivables = self.bs.sp06_crediti_breve + self.bs.sp07_crediti_lungo
        receivables_turnover_days = self.safe_divide(
            Decimal(days_in_year) * total_receivables,
            self.inc.revenue
        )

        # DDEB = Giorni di Debito = 360 * Debiti / Fatturato
        payables_turnover_days = self.safe_divide(
            Decimal(days_in_year) * self.bs.total_debt,
            self.inc.revenue
        )

        # DCCN = Giorni CCN = 360 * CCN / Fatturato
        working_capital_days = self.safe_divide(
            Decimal(days_in_year) * self.bs.working_capital_net,
            self.inc.revenue
        )

        # Cash Conversion Cycle = DMAG + DCRED - DDEB
        cash_conversion_cycle = (
            inventory_turnover_days +
            receivables_turnover_days -
            payables_turnover_days
        )

        return ActivityRatios(
            asset_turnover=self.round_decimal(asset_turnover, 4),
            inventory_turnover_days=self.round_decimal(inventory_turnover_days, 0),
            receivables_turnover_days=self.round_decimal(receivables_turnover_days, 0),
            payables_turnover_days=self.round_decimal(payables_turnover_days, 0),
            working_capital_days=self.round_decimal(working_capital_days, 0),
            cash_conversion_cycle=self.round_decimal(cash_conversion_cycle, 0)
        )

    # ============= COVERAGE RATIOS =============

    def calculate_coverage_ratios(self) -> CoverageRatios:
        """
        Calculate Coverage/Solidity ratios (Indici di Solidità)

        Returns:
            CoverageRatios with fixed assets coverage indices
        """
        # (CN+PF)/AF - Coverage of Fixed Assets with Equity and LT Debt
        equity_plus_ltdebt = self.bs.total_equity + self.bs.sp17_debiti_lungo
        fixed_assets_coverage_with_equity_and_ltdebt = self.safe_divide(
            equity_plus_ltdebt,
            self.bs.fixed_assets
        )

        # CN/AF - Coverage of Fixed Assets with Equity only
        fixed_assets_coverage_with_equity = self.safe_divide(
            self.bs.total_equity,
            self.bs.fixed_assets
        )

        # CN/(PC+PF) - Independence from Third Parties
        total_liabilities = self.bs.current_liabilities + self.bs.sp17_debiti_lungo
        independence_from_third_parties = self.safe_divide(
            self.bs.total_equity,
            total_liabilities
        )

        return CoverageRatios(
            fixed_assets_coverage_with_equity_and_ltdebt=self.round_decimal(fixed_assets_coverage_with_equity_and_ltdebt, 4),
            fixed_assets_coverage_with_equity=self.round_decimal(fixed_assets_coverage_with_equity, 4),
            independence_from_third_parties=self.round_decimal(independence_from_third_parties, 4)
        )

    # ============= TURNOVER RATIOS =============

    def calculate_turnover_ratios(self) -> TurnoverRatios:
        """
        Calculate Turnover ratios (actual ratios, not days)

        Returns:
            TurnoverRatios with all turnover calculations
        """
        # TdM = CO/RD (Cost of Goods Sold / Inventory)
        inventory_turnover = self.safe_divide(
            self.inc.ce05_materie_prime,
            self.bs.sp05_rimanenze
        )

        # TdC = RIC/LD (Revenue / Receivables)
        total_receivables = self.bs.sp06_crediti_breve + self.bs.sp07_crediti_lungo
        receivables_turnover = self.safe_divide(
            self.inc.revenue,
            total_receivables
        )

        # TdD = (CO+AC+ODG)/PC (Operating Costs / Current Liabilities)
        operating_costs = (
            self.inc.ce05_materie_prime +
            self.inc.ce06_servizi +
            self.inc.ce07_godimento_beni
        )
        payables_turnover = self.safe_divide(
            operating_costs,
            self.bs.current_liabilities
        )

        # TdCCN = RIC/CCN (Revenue / Working Capital)
        working_capital_turnover = self.safe_divide(
            self.inc.revenue,
            self.bs.working_capital_net
        )

        # TdAT = RIC/TA (Revenue / Total Assets)
        total_assets_turnover = self.safe_divide(
            self.inc.revenue,
            self.bs.total_assets
        )

        return TurnoverRatios(
            inventory_turnover=self.round_decimal(inventory_turnover, 4),
            receivables_turnover=self.round_decimal(receivables_turnover, 4),
            payables_turnover=self.round_decimal(payables_turnover, 4),
            working_capital_turnover=self.round_decimal(working_capital_turnover, 4),
            total_assets_turnover=self.round_decimal(total_assets_turnover, 4)
        )

    # ============= EXTENDED PROFITABILITY RATIOS =============

    def calculate_extended_profitability_ratios(self) -> ExtendedProfitabilityRatios:
        """
        Calculate Extended profitability indices

        Returns:
            ExtendedProfitabilityRatios with spread, leverage, etc.
        """
        # Calculate base ratios first
        profitability = self.calculate_profitability_ratios()

        # Spread = ROI - ROD
        spread = profitability.roi - profitability.rod

        # Financial Leverage Effect = (PC+PF)/CN
        total_liabilities = self.bs.current_liabilities + self.bs.sp17_debiti_lungo
        financial_leverage_effect = self.safe_divide(
            total_liabilities,
            self.bs.total_equity
        )

        # MOL/RIC - EBITDA on Sales
        ebitda_on_sales = self.safe_divide(
            self.inc.ebitda,
            self.inc.revenue
        )

        # OF/RIC - Financial Charges on Revenue
        financial_charges_on_revenue = self.safe_divide(
            self.inc.ce15_oneri_finanziari,
            self.inc.revenue
        )

        return ExtendedProfitabilityRatios(
            spread=self.round_decimal(spread, 4),
            financial_leverage_effect=self.round_decimal(financial_leverage_effect, 4),
            ebitda_on_sales=self.round_decimal(ebitda_on_sales, 4),
            financial_charges_on_revenue=self.round_decimal(financial_charges_on_revenue, 4)
        )

    # ============= EFFICIENCY RATIOS =============

    def calculate_efficiency_ratios(self) -> EfficiencyRatios:
        """
        Calculate Efficiency ratios (Indici di Efficienza)

        Returns:
            EfficiencyRatios with revenue per cost ratios
        """
        # RIC/CL - Revenue per Employee Cost (Rendimento dipendenti)
        revenue_per_employee_cost = self.safe_divide(
            self.inc.revenue,
            self.inc.ce08_costi_personale
        )

        # RIC/CO - Revenue per Materials Cost (Rendimento materie)
        revenue_per_materials_cost = self.safe_divide(
            self.inc.revenue,
            self.inc.ce05_materie_prime
        )

        return EfficiencyRatios(
            revenue_per_employee_cost=self.round_decimal(revenue_per_employee_cost, 4),
            revenue_per_materials_cost=self.round_decimal(revenue_per_materials_cost, 4)
        )

    # ============= BREAK EVEN ANALYSIS =============

    def calculate_break_even_analysis(self, fixed_cost_percentage: Decimal = Decimal("0.40")) -> BreakEvenAnalysis:
        """
        Calculate Break Even Point analysis

        Args:
            fixed_cost_percentage: Percentage of costs that are fixed (default: 40%)

        Returns:
            BreakEvenAnalysis with BEP calculations
        """
        # Total operating costs
        total_operating_costs = (
            self.inc.ce05_materie_prime +
            self.inc.ce06_servizi +
            self.inc.ce07_godimento_beni +
            self.inc.ce08_costi_personale +
            self.inc.ce12_oneri_diversi
        )

        # Split into fixed and variable costs
        fixed_costs = total_operating_costs * fixed_cost_percentage
        variable_costs = total_operating_costs * (Decimal("1") - fixed_cost_percentage)

        # Contribution Margin = Revenue - Variable Costs
        contribution_margin = self.inc.revenue - variable_costs

        # Contribution Margin Percentage = MdC/Revenue
        contribution_margin_percentage = self.safe_divide(
            contribution_margin,
            self.inc.revenue
        )

        # Break Even Revenue = Fixed Costs / Contribution Margin %
        break_even_revenue = self.safe_divide(
            fixed_costs,
            contribution_margin_percentage
        )

        # Safety Margin = 1 - (BEP/Revenue)
        safety_margin = Decimal("1") - self.safe_divide(
            break_even_revenue,
            self.inc.revenue
        )

        # Operating Leverage = Contribution Margin / EBIT
        operating_leverage = self.safe_divide(
            contribution_margin,
            self.inc.ebit
        )

        # Fixed Cost Multiplier = 1 / Contribution Margin %
        fixed_cost_multiplier = self.safe_divide(
            Decimal("1"),
            contribution_margin_percentage
        )

        return BreakEvenAnalysis(
            fixed_costs=self.round_decimal(fixed_costs),
            variable_costs=self.round_decimal(variable_costs),
            contribution_margin=self.round_decimal(contribution_margin),
            contribution_margin_percentage=self.round_decimal(contribution_margin_percentage, 4),
            break_even_revenue=self.round_decimal(break_even_revenue),
            safety_margin=self.round_decimal(safety_margin, 4),
            operating_leverage=self.round_decimal(operating_leverage, 4),
            fixed_cost_multiplier=self.round_decimal(fixed_cost_multiplier, 4)
        )

    # ============= COMPREHENSIVE ANALYSIS =============

    def calculate_all_ratios(self) -> Dict[str, any]:
        """
        Calculate all financial ratios

        Returns:
            Dictionary with all ratio categories
        """
        return {
            "working_capital": self.calculate_working_capital_metrics(),
            "liquidity": self.calculate_liquidity_ratios(),
            "solvency": self.calculate_solvency_ratios(),
            "profitability": self.calculate_profitability_ratios(),
            "activity": self.calculate_activity_ratios(),
            "coverage": self.calculate_coverage_ratios(),
            "turnover": self.calculate_turnover_ratios(),
            "extended_profitability": self.calculate_extended_profitability_ratios(),
            "efficiency": self.calculate_efficiency_ratios(),
            "break_even": self.calculate_break_even_analysis()
        }

    def get_summary_metrics(self) -> Dict[str, Decimal]:
        """
        Get key summary metrics for dashboard

        Returns:
            Dictionary with key financial metrics
        """
        liquidity = self.calculate_liquidity_ratios()
        solvency = self.calculate_solvency_ratios()
        profitability = self.calculate_profitability_ratios()
        wc = self.calculate_working_capital_metrics()

        return {
            "revenue": self.round_decimal(self.inc.revenue),
            "ebitda": self.round_decimal(self.inc.ebitda),
            "ebit": self.round_decimal(self.inc.ebit),
            "net_profit": self.round_decimal(self.inc.net_profit),
            "total_assets": self.round_decimal(self.bs.total_assets),
            "total_equity": self.round_decimal(self.bs.total_equity),
            "total_debt": self.round_decimal(self.bs.total_debt),
            "working_capital": self.round_decimal(wc.ccn),
            "current_ratio": liquidity.current_ratio,
            "roe": profitability.roe,
            "roi": profitability.roi,
            "debt_to_equity": solvency.debt_to_equity,
            "ebitda_margin": profitability.ebitda_margin
        }
