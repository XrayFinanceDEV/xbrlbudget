"""
Altman Z-Score Calculator
Implements sector-specific bankruptcy prediction models
"""
from decimal import Decimal
from typing import NamedTuple, Literal, Dict
from database.models import BalanceSheet, IncomeStatement
from calculations.base import BaseCalculator
from config import (
    Sector,
    ALTMAN_COEFFICIENTS_MANUFACTURING,
    ALTMAN_COEFFICIENTS_SERVICES,
    ALTMAN_THRESHOLDS_MANUFACTURING,
    ALTMAN_THRESHOLDS_SERVICES
)


class AltmanComponents(NamedTuple):
    """Individual components of Altman Z-Score"""
    A: Decimal  # Working Capital / Total Assets
    B: Decimal  # Retained Earnings / Total Assets
    C: Decimal  # EBIT / Total Assets
    D: Decimal  # Market Value Equity / Total Debt
    E: Decimal  # Revenue / Total Assets (Manufacturing only)


class AltmanResult(NamedTuple):
    """Altman Z-Score calculation result"""
    z_score: Decimal
    components: AltmanComponents
    classification: Literal["safe", "gray_zone", "distress"]
    interpretation_it: str
    sector: int
    model_type: Literal["manufacturing", "services"]


class AltmanCalculator(BaseCalculator):
    """
    Altman Z-Score Calculator with sector-specific formulas

    Two models:
    1. Manufacturing (Sector 1): 5-component model
    2. Services/Other (Sectors 2-6): 4-component model
    """

    def __init__(self,
                 balance_sheet: BalanceSheet,
                 income_statement: IncomeStatement,
                 sector: int):
        """
        Initialize Altman calculator

        Args:
            balance_sheet: Balance Sheet data
            income_statement: Income Statement data
            sector: Sector code (1-6)
        """
        self.bs = balance_sheet
        self.inc = income_statement
        self.sector = sector

    def _is_manufacturing_sector(self) -> bool:
        """Check if sector uses manufacturing model"""
        return self.sector == Sector.INDUSTRIA.value

    def calculate_components(self) -> AltmanComponents:
        """
        Calculate individual Altman components

        Returns:
            AltmanComponents with all component values
        """
        # Component A: Working Capital / Total Assets
        # Working Capital = Current Assets - Current Liabilities
        working_capital = self.bs.working_capital_net
        A = self.safe_divide(working_capital, self.bs.total_assets)

        # Component B: Retained Earnings / Total Assets
        # Retained Earnings = Reserves (Riserve)
        # In Italian accounting, this is "Riserve" which includes retained earnings
        B = self.safe_divide(self.bs.sp12_riserve, self.bs.total_assets)

        # Component C: EBIT / Total Assets
        # EBIT = Risultato Operativo
        C = self.safe_divide(self.inc.ebit, self.bs.total_assets)

        # Component D: Market Value of Equity / Total Debt
        # For private companies, use Book Value of Equity
        # Market Value ≈ Book Value = Patrimonio Netto
        D = self.safe_divide(self.bs.total_equity, self.bs.total_debt)

        # Component E: Revenue / Total Assets (Manufacturing only)
        E = self.safe_divide(self.inc.revenue, self.bs.total_assets)

        return AltmanComponents(
            A=self.round_decimal(A, 6),
            B=self.round_decimal(B, 6),
            C=self.round_decimal(C, 6),
            D=self.round_decimal(D, 6),
            E=self.round_decimal(E, 6)
        )

    def calculate_z_score_manufacturing(self, components: AltmanComponents) -> Decimal:
        """
        Calculate Z-Score for Manufacturing sector

        Formula:
        Z = 0.717*A + 0.847*B + 3.107*C + 0.42*D + 0.998*E

        Args:
            components: Calculated Altman components

        Returns:
            Z-Score as Decimal
        """
        coef = ALTMAN_COEFFICIENTS_MANUFACTURING

        z_score = (
            Decimal(str(coef["A"])) * components.A +
            Decimal(str(coef["B"])) * components.B +
            Decimal(str(coef["C"])) * components.C +
            Decimal(str(coef["D"])) * components.D +
            Decimal(str(coef["E"])) * components.E
        )

        return self.round_decimal(z_score, 2)

    def calculate_z_score_services(self, components: AltmanComponents) -> Decimal:
        """
        Calculate Z-Score for Services/Commerce/Other sectors

        Formula:
        Z = 3.25 + 6.56*A + 3.26*B + 6.72*C + 1.05*D

        Note: Component E (Revenue/Assets) is NOT used for services

        Args:
            components: Calculated Altman components

        Returns:
            Z-Score as Decimal
        """
        coef = ALTMAN_COEFFICIENTS_SERVICES

        z_score = (
            Decimal(str(coef["constant"])) +
            Decimal(str(coef["A"])) * components.A +
            Decimal(str(coef["B"])) * components.B +
            Decimal(str(coef["C"])) * components.C +
            Decimal(str(coef["D"])) * components.D
        )

        return self.round_decimal(z_score, 2)

    def classify_z_score(self, z_score: Decimal, is_manufacturing: bool) -> Literal["safe", "gray_zone", "distress"]:
        """
        Classify Z-Score into risk category

        Args:
            z_score: Calculated Z-Score
            is_manufacturing: Whether manufacturing sector thresholds apply

        Returns:
            Classification: "safe", "gray_zone", or "distress"
        """
        thresholds = (ALTMAN_THRESHOLDS_MANUFACTURING if is_manufacturing
                     else ALTMAN_THRESHOLDS_SERVICES)

        if z_score >= Decimal(str(thresholds["safe"])):
            return "safe"
        elif z_score >= Decimal(str(thresholds["gray_zone_low"])):
            return "gray_zone"
        else:
            return "distress"

    def get_interpretation_it(self, classification: str, is_manufacturing: bool) -> str:
        """
        Get Italian interpretation of Z-Score classification

        Args:
            classification: Risk classification
            is_manufacturing: Whether manufacturing thresholds used

        Returns:
            Italian text interpretation
        """
        thresholds = (ALTMAN_THRESHOLDS_MANUFACTURING if is_manufacturing
                     else ALTMAN_THRESHOLDS_SERVICES)

        interpretations = {
            "safe": f"Buono - Zona di Sicurezza (Z > {thresholds['safe']}). "
                   "L'azienda presenta bassissimo rischio di insolvenza.",

            "gray_zone": f"Zona d'Ombra ({thresholds['gray_zone_low']} < Z < {thresholds['safe']}). "
                        "L'azienda richiede monitoraggio. Situazione incerta con possibile rischio futuro.",

            "distress": f"Rischio Fallimento (Z < {thresholds['distress']}). "
                       "L'azienda presenta elevato rischio di insolvenza nei prossimi 2 anni."
        }

        return interpretations.get(classification, "Classificazione non disponibile")

    def calculate(self) -> AltmanResult:
        """
        Calculate complete Altman Z-Score analysis

        Returns:
            AltmanResult with Z-Score, components, and interpretation
        """
        # Calculate components
        components = self.calculate_components()

        # Determine model type and calculate Z-Score
        is_manufacturing = self._is_manufacturing_sector()

        if is_manufacturing:
            z_score = self.calculate_z_score_manufacturing(components)
            model_type = "manufacturing"
        else:
            z_score = self.calculate_z_score_services(components)
            model_type = "services"

        # Classify result
        classification = self.classify_z_score(z_score, is_manufacturing)

        # Get interpretation
        interpretation = self.get_interpretation_it(classification, is_manufacturing)

        return AltmanResult(
            z_score=z_score,
            components=components,
            classification=classification,
            interpretation_it=interpretation,
            sector=self.sector,
            model_type=model_type
        )

    def calculate_multi_year(self,
                            balance_sheets: list[BalanceSheet],
                            income_statements: list[IncomeStatement]) -> list[AltmanResult]:
        """
        Calculate Altman Z-Score for multiple years

        Args:
            balance_sheets: List of balance sheets (chronological order)
            income_statements: List of income statements (chronological order)

        Returns:
            List of AltmanResult, one per year
        """
        if len(balance_sheets) != len(income_statements):
            raise ValueError("Balance sheets and income statements must have same length")

        results = []
        for bs, inc in zip(balance_sheets, income_statements):
            calculator = AltmanCalculator(bs, inc, self.sector)
            results.append(calculator.calculate())

        return results

    def get_trend_analysis(self, results: list[AltmanResult]) -> Dict[str, any]:
        """
        Analyze trend across multiple years

        Args:
            results: List of AltmanResult for multiple years

        Returns:
            Dictionary with trend analysis
        """
        if len(results) < 2:
            return {"trend": "insufficient_data", "change": Decimal('0')}

        # Calculate change from first to last year
        first_z = results[0].z_score
        last_z = results[-1].z_score
        change = last_z - first_z
        pct_change = self.safe_divide(change, first_z) * Decimal('100')

        # Determine trend
        if change > Decimal('0.5'):
            trend = "improving"
        elif change < Decimal('-0.5'):
            trend = "deteriorating"
        else:
            trend = "stable"

        # Count classifications
        classifications = [r.classification for r in results]
        safe_count = classifications.count("safe")
        gray_count = classifications.count("gray_zone")
        distress_count = classifications.count("distress")

        return {
            "trend": trend,
            "change": self.round_decimal(change, 2),
            "pct_change": self.round_decimal(pct_change, 2),
            "first_z": first_z,
            "last_z": last_z,
            "safe_years": safe_count,
            "gray_years": gray_count,
            "distress_years": distress_count,
            "total_years": len(results)
        }
