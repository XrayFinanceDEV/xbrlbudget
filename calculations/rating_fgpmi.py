"""
FGPMI Rating Calculator
Implements the complex SME credit rating model for Italian Guarantee Fund access
"""
import json
import os
from decimal import Decimal
from typing import NamedTuple, Dict, List, Optional
from database.models import BalanceSheet, IncomeStatement
from calculations.base import BaseCalculator
from calculations.ratios import FinancialRatiosCalculator


class IndicatorScore(NamedTuple):
    """Score for an individual indicator"""
    code: str
    name: str
    value: Decimal
    points: int
    max_points: int
    percentage: Decimal


class FGPMIResult(NamedTuple):
    """FGPMI Rating result"""
    total_score: int
    max_score: int
    rating_class: int
    rating_code: str
    rating_description: str
    risk_level: str
    sector_model: str
    revenue_bonus: int
    indicators: Dict[str, IndicatorScore]


class FGPMICalculator(BaseCalculator):
    """
    FGPMI (Fondo di Garanzia PMI) Rating Calculator

    Implements multi-indicator credit scoring model with sector-specific thresholds
    Used for Italian SME access to government-backed loan guarantees
    """

    def __init__(self,
                 balance_sheet: BalanceSheet,
                 income_statement: IncomeStatement,
                 sector: int):
        """
        Initialize FGPMI calculator

        Args:
            balance_sheet: Balance Sheet data
            income_statement: Income Statement data
            sector: Sector code (1-6)
        """
        self.bs = balance_sheet
        self.inc = income_statement
        self.sector = sector

        # Load configuration files
        self._load_configuration()

        # Get sector model
        self.sector_model = self._get_sector_model()

    def _load_configuration(self):
        """Load rating tables and sector configuration from JSON files"""
        base_path = os.path.join(os.path.dirname(__file__), '..', 'data')

        # Load rating tables
        rating_tables_path = os.path.join(base_path, 'rating_tables.json')
        with open(rating_tables_path, 'r', encoding='utf-8') as f:
            self.rating_tables = json.load(f)

        # Load sector configuration
        sectors_path = os.path.join(base_path, 'sectors.json')
        with open(sectors_path, 'r', encoding='utf-8') as f:
            sectors_config = json.load(f)
            self.sectors = sectors_config['sectors']

    def _get_sector_model(self) -> str:
        """Get FGPMI model type for the sector"""
        sector_info = self.sectors.get(str(self.sector))
        if not sector_info:
            raise ValueError(f"Invalid sector: {self.sector}")
        return sector_info['fgpmi_model']

    def _get_indicator_thresholds(self, indicator_code: str) -> List[Dict]:
        """
        Get thresholds for a specific indicator and sector

        Args:
            indicator_code: Indicator code (V1-V7)

        Returns:
            List of threshold dictionaries
        """
        indicator = self.rating_tables['indicators'][indicator_code]
        thresholds = indicator['thresholds'].get(self.sector_model, [])

        if not thresholds:
            # Fallback to industria if sector model not found
            thresholds = indicator['thresholds'].get('industria', [])

        return thresholds

    def _score_indicator(self, value: Decimal, thresholds: List[Dict]) -> int:
        """
        Score a value against threshold ranges

        Args:
            value: Value to score
            thresholds: List of threshold dictionaries

        Returns:
            Points earned
        """
        for threshold in thresholds:
            min_val = Decimal(str(threshold.get('min', '-999999')))
            max_val = Decimal(str(threshold.get('max', '999999')))

            # Check if value falls in this range
            if min_val <= value < max_val:
                return threshold['points']
            elif value >= min_val and 'max' not in threshold:
                # No upper bound (last threshold)
                return threshold['points']
            elif value < max_val and 'min' not in threshold:
                # No lower bound (first threshold)
                return threshold['points']

        # Default: return 0 if no threshold matched
        return 0

    def calculate_V1_autonomy(self) -> IndicatorScore:
        """
        V1: Indice di Autonomia Finanziaria
        Patrimonio Netto / Totale Attivo
        """
        value = self.safe_divide(self.bs.total_equity, self.bs.total_assets)
        thresholds = self._get_indicator_thresholds('V1')
        points = self._score_indicator(value, thresholds)
        max_points = self.rating_tables['indicators']['V1']['weight']

        return IndicatorScore(
            code='V1',
            name='Indice di Autonomia Finanziaria',
            value=self.round_decimal(value, 4),
            points=points,
            max_points=max_points,
            percentage=self.safe_divide(Decimal(points), Decimal(max_points)) * Decimal('100')
        )

    def calculate_V2_leverage(self) -> IndicatorScore:
        """
        V2: Indice di Indebitamento
        Immobilizzazioni / Patrimonio Netto
        """
        value = self.safe_divide(self.bs.fixed_assets, self.bs.total_equity)
        thresholds = self._get_indicator_thresholds('V2')
        points = self._score_indicator(value, thresholds)
        max_points = self.rating_tables['indicators']['V2']['weight']

        return IndicatorScore(
            code='V2',
            name='Indice di Indebitamento',
            value=self.round_decimal(value, 4),
            points=points,
            max_points=max_points,
            percentage=self.safe_divide(Decimal(points), Decimal(max_points)) * Decimal('100')
        )

    def calculate_V3_debt_to_production(self) -> IndicatorScore:
        """
        V3: Rapporto Debiti / Valore della Produzione
        Debiti Totali / Valore della Produzione
        """
        value = self.safe_divide(self.bs.total_debt, self.inc.production_value)
        thresholds = self._get_indicator_thresholds('V3')
        points = self._score_indicator(value, thresholds)
        max_points = self.rating_tables['indicators']['V3']['weight']

        return IndicatorScore(
            code='V3',
            name='Rapporto Debiti / Valore Produzione',
            value=self.round_decimal(value, 4),
            points=points,
            max_points=max_points,
            percentage=self.safe_divide(Decimal(points), Decimal(max_points)) * Decimal('100')
        )

    def calculate_V4_liquidity(self) -> IndicatorScore:
        """
        V4: Indice di Liquidità (Current Ratio)
        Attivo Corrente / Passivo Corrente
        """
        value = self.safe_divide(self.bs.current_assets, self.bs.current_liabilities)
        thresholds = self._get_indicator_thresholds('V4')
        points = self._score_indicator(value, thresholds)
        max_points = self.rating_tables['indicators']['V4']['weight']

        return IndicatorScore(
            code='V4',
            name='Indice di Liquidità (Current Ratio)',
            value=self.round_decimal(value, 4),
            points=points,
            max_points=max_points,
            percentage=self.safe_divide(Decimal(points), Decimal(max_points)) * Decimal('100')
        )

    def calculate_V5_roe(self) -> IndicatorScore:
        """
        V5: ROE (Return on Equity)
        Utile Netto / Patrimonio Netto
        """
        value = self.safe_divide(self.inc.net_profit, self.bs.total_equity)
        thresholds = self._get_indicator_thresholds('V5')
        points = self._score_indicator(value, thresholds)
        max_points = self.rating_tables['indicators']['V5']['weight']

        return IndicatorScore(
            code='V5',
            name='ROE (Return on Equity)',
            value=self.round_decimal(value, 4),
            points=points,
            max_points=max_points,
            percentage=self.safe_divide(Decimal(points), Decimal(max_points)) * Decimal('100')
        )

    def calculate_V6_working_capital(self) -> IndicatorScore:
        """
        V6: Capitale Circolante Netto / Totale Attivo
        CCN / TA
        """
        value = self.safe_divide(self.bs.working_capital_net, self.bs.total_assets)
        thresholds = self._get_indicator_thresholds('V6')
        points = self._score_indicator(value, thresholds)
        max_points = self.rating_tables['indicators']['V6']['weight']

        return IndicatorScore(
            code='V6',
            name='Capitale Circolante Netto / Totale Attivo',
            value=self.round_decimal(value, 4),
            points=points,
            max_points=max_points,
            percentage=self.safe_divide(Decimal(points), Decimal(max_points)) * Decimal('100')
        )

    def calculate_V7_ebitda_margin(self) -> IndicatorScore:
        """
        V7: EBITDA Margin
        EBITDA / Fatturato
        """
        value = self.safe_divide(self.inc.ebitda, self.inc.revenue)
        thresholds = self._get_indicator_thresholds('V7')
        points = self._score_indicator(value, thresholds)
        max_points = self.rating_tables['indicators']['V7']['weight']

        return IndicatorScore(
            code='V7',
            name='EBITDA Margin',
            value=self.round_decimal(value, 4),
            points=points,
            max_points=max_points,
            percentage=self.safe_divide(Decimal(points), Decimal(max_points)) * Decimal('100')
        )

    def calculate_revenue_bonus(self) -> int:
        """
        Calculate bonus points based on revenue size

        Returns:
            Bonus points (0 or 5)
        """
        revenue_config = self.rating_tables['revenue_adjustments']
        threshold = Decimal(str(revenue_config['threshold']))

        if self.inc.revenue >= threshold:
            return revenue_config['bonus_points']['above_threshold']
        else:
            return revenue_config['bonus_points']['below_threshold']

    def get_rating_class_info(self, rating_class: int) -> Dict[str, str]:
        """
        Get rating class information

        Args:
            rating_class: Rating class code (1-13)

        Returns:
            Dictionary with rating details
        """
        rating_info = self.rating_tables['rating_classes'].get(str(rating_class))
        if not rating_info:
            # Default to worst rating if not found
            rating_info = self.rating_tables['rating_classes']['13']

        return rating_info

    def score_to_rating_class(self, total_score: int) -> int:
        """
        Map total score to rating class

        Args:
            total_score: Total points earned

        Returns:
            Rating class code
        """
        # Calculate percentage score
        max_possible = 105  # 15+10+15+15+20+15+10+5
        score_percentage = (total_score / max_possible) * 100

        # Map percentage to rating class
        if score_percentage >= 90:
            return 1  # AAA
        elif score_percentage >= 85:
            return 2  # AA+
        elif score_percentage >= 80:
            return 3  # AA
        elif score_percentage >= 75:
            return 4  # AA-
        elif score_percentage >= 70:
            return 5  # A+
        elif score_percentage >= 65:
            return 6  # A
        elif score_percentage >= 60:
            return 7  # A-
        elif score_percentage >= 55:
            return 8  # BBB+
        elif score_percentage >= 50:
            return 9  # BBB
        elif score_percentage >= 45:
            return 10  # BBB-
        elif score_percentage >= 40:
            return 11  # BB+
        elif score_percentage >= 30:
            return 12  # BB
        else:
            return 13  # BB-

    def calculate(self) -> FGPMIResult:
        """
        Calculate complete FGPMI Rating

        Returns:
            FGPMIResult with rating and detailed breakdown
        """
        # Calculate all indicators
        indicators = {
            'V1': self.calculate_V1_autonomy(),
            'V2': self.calculate_V2_leverage(),
            'V3': self.calculate_V3_debt_to_production(),
            'V4': self.calculate_V4_liquidity(),
            'V5': self.calculate_V5_roe(),
            'V6': self.calculate_V6_working_capital(),
            'V7': self.calculate_V7_ebitda_margin()
        }

        # Calculate total score
        indicator_score = sum(ind.points for ind in indicators.values())
        revenue_bonus = self.calculate_revenue_bonus()
        total_score = indicator_score + revenue_bonus

        # Calculate max possible score
        max_score = sum(ind.max_points for ind in indicators.values()) + 5  # +5 for revenue bonus

        # Determine rating class
        rating_class = self.score_to_rating_class(total_score)
        rating_info = self.get_rating_class_info(rating_class)

        return FGPMIResult(
            total_score=total_score,
            max_score=max_score,
            rating_class=rating_class,
            rating_code=rating_info['rating'],
            rating_description=rating_info['description'],
            risk_level=rating_info['risk_level'],
            sector_model=self.sector_model,
            revenue_bonus=revenue_bonus,
            indicators=indicators
        )

    def get_interpretation_it(self, result: FGPMIResult) -> str:
        """
        Get Italian interpretation of rating

        Args:
            result: FGPMI Rating result

        Returns:
            Italian text interpretation
        """
        score_pct = (result.total_score / result.max_score) * 100

        interpretation = f"""
RATING FGPMI: {result.rating_code} ({result.rating_description})
Livello di Rischio: {result.risk_level}
Punteggio: {result.total_score}/{result.max_score} ({score_pct:.1f}%)
Settore: {self.sector_model.title()}

VALUTAZIONE:
"""

        if result.rating_class <= 6:
            interpretation += "L'azienda presenta un profilo creditizio solido con elevata capacità di accesso al credito."
        elif result.rating_class <= 9:
            interpretation += "L'azienda presenta un profilo creditizio adeguato con buona capacità di accesso al credito."
        elif result.rating_class <= 10:
            interpretation += "L'azienda presenta un profilo creditizio appena sufficiente. Richiede monitoraggio."
        else:
            interpretation += "L'azienda presenta un profilo creditizio inadeguato con difficoltà di accesso al credito."

        # Add revenue bonus note
        if result.revenue_bonus > 0:
            interpretation += f"\n\nBonus Fatturato: +{result.revenue_bonus} punti (Fatturato > €500.000)"

        return interpretation

    def get_detailed_breakdown(self, result: FGPMIResult) -> str:
        """
        Get detailed breakdown of rating calculation

        Args:
            result: FGPMI Rating result

        Returns:
            Formatted string with detailed breakdown
        """
        output = []
        output.append("=" * 70)
        output.append(f"RATING FGPMI: {result.rating_code} - {result.rating_description}")
        output.append("=" * 70)
        output.append(f"Punteggio Totale: {result.total_score}/{result.max_score}")
        output.append(f"Livello di Rischio: {result.risk_level}")
        output.append(f"Modello Settore: {result.sector_model.title()}")
        output.append("")
        output.append("DETTAGLIO INDICATORI:")
        output.append("-" * 70)

        for code in ['V1', 'V2', 'V3', 'V4', 'V5', 'V6', 'V7']:
            ind = result.indicators[code]
            output.append(f"\n{ind.code}: {ind.name}")
            output.append(f"  Valore:    {ind.value:.4f}")
            output.append(f"  Punteggio: {ind.points}/{ind.max_points} ({ind.percentage:.1f}%)")

        output.append("")
        output.append("-" * 70)
        output.append(f"Bonus Fatturato: {result.revenue_bonus} punti")
        output.append("=" * 70)

        return "\n".join(output)
