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
            "activity": self.calculate_activity_ratios()
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
