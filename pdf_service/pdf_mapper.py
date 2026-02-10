"""
PDF to IV CEE Balance Sheet Mapper Service.

This module provides functionality to extract balance sheet data from
Italian PDF balance sheets using Docling and map them to the sp01-sp18 schema.
"""

from decimal import Decimal
from typing import Dict, List, Tuple
import re
import logging

logger = logging.getLogger(__name__)


class IVCEEMapper:
    """
    Mapper service to extract and validate Italian balance sheet data from PDF text.

    Supports:
    - Bilancio Micro (simplified format for small companies)
    - Bilancio Abbreviato (abbreviated format)
    - Bilancio Ordinario (full format)
    """

    # OIC 12 standard field mappings for table format (Docling markdown output)
    # Field names match database.models.BalanceSheet schema
    FIELD_PATTERNS = {
        # Assets (Attivo)
        'sp02_immob_immateriali': [
            r'\|\s*I\s*-\s*Immobilizzazioni\s+immateriali\s*\|\s*([\d\.,\-]+)\s*\|',
        ],
        'sp03_immob_materiali': [
            r'\|\s*II\s*-\s*Immobilizzazioni\s+materiali\s*\|\s*([\d\.,\-]+)\s*\|',
        ],
        'sp04_immob_finanziarie': [
            r'\|\s*III\s*-\s*Immobilizzazioni\s+finanziarie\s*\|\s*([\d\.,\-]+)\s*\|',
        ],
        'sp05_rimanenze': [
            r'\|\s*I\s*-\s*Rimanenze\s*\|\s*([\d\.,\-]+)\s*\|',
        ],
        # C.II) Crediti - In Bilancio Micro, typically all short-term
        'sp06_crediti_breve': [
            r'\|\s*II\s*-\s*Crediti\s*\|\s*([\d\.,\-]+)\s*\|',
        ],
        # C.III) Attività finanziarie
        'sp08_attivita_finanziarie': [
            r'\|\s*III\s*-\s*Attivita.*finanziarie.*non.*immobilizzazioni\s*\|\s*([\d\.,\-]+)\s*\|',
        ],
        # C.IV) Disponibilità liquide
        'sp09_disponibilita_liquide': [
            r'\|\s*IV\s*-\s*Disponibilita.*liquide\s*\|\s*([\d\.,\-]+)\s*\|',
        ],
        # D) Ratei e risconti attivi
        'sp10_ratei_risconti_attivi': [
            r'\|\s*D\)\s*Ratei\s+e\s+risconti\s*\|\s*([\d\.,\-]+)\s*\|',
        ],
        'totale_attivo': [
            r'\|\s*Totale\s+attivo\s*\|\s*([\d\.,\-]+)\s*\|',
        ],

        # Equity (Patrimonio Netto)
        # A.I) Capitale
        'sp11_capitale': [
            r'\|\s*I\s*-\s*Capitale\s*\|\s*([\d\.,\-]+)\s*\|',
        ],
        # A.IX) Utile/Perdita dell'esercizio
        'sp13_utile_perdita': [
            r'\|\s*IX\s*-\s*Utile.*perdita.*esercizio\s*\|\s*([\d\.,\-]+)\s*\|',
        ],

        # Liabilities (Passivo)
        # B) Fondi per rischi e oneri
        'sp14_fondi_rischi': [
            r'\|\s*B\)\s*Fondi.*rischi.*oneri\s*\|\s*([\d\.,\-]+)\s*\|',
        ],
        # C) TFR
        'sp15_tfr': [
            r'\|\s*C\)\s*Trattamento.*fine.*rapporto\s*\|\s*([\d\.,\-]+)\s*\|',
            r'\|\s*TFR\s*\|\s*([\d\.,\-]+)\s*\|',
        ],
        # D) Debiti - In Bilancio Micro, typically all short-term
        'sp16_debiti_breve': [
            r'\|\s*D\)\s*Debiti\s*\|\s*([\d\.,\-]+)\s*\|',
        ],
        # E) Ratei e risconti passivi
        'sp18_ratei_risconti_passivi': [
            r'\|\s*E\)\s*Ratei\s+e\s+risconti\s*\|\s*([\d\.,\-]+)\s*\|',
        ],
        'totale_passivo': [
            r'\|\s*Totale\s+passivo\s*\|\s*([\d\.,\-]+)\s*\|',
        ],
    }

    def parse_italian_number(self, value_str: str) -> Decimal:
        """
        Convert Italian number format to Decimal.

        Italian format: 1.234.567,89 (periods as thousand separators, comma as decimal)
        Standard format: 1234567.89

        Examples:
            "53.138" -> Decimal("53138")
            "205.686" -> Decimal("205686")
            "2.567,39" -> Decimal("2567.39")
            "-" -> Decimal("0")

        Args:
            value_str: Raw value from PDF cell (str, int, or float)

        Returns:
            Decimal representation
        """
        if not value_str or value_str.strip() in ['-', '', 'None', 'n/a', 'N/A']:
            return Decimal('0')

        # Remove spaces
        clean = value_str.strip()

        # Check if there's a comma (decimal separator)
        if ',' in clean:
            # Format: 1.234,56 or 234,56
            clean = clean.replace('.', '')  # Remove thousand separator
            clean = clean.replace(',', '.')  # Replace decimal comma with dot
        else:
            # Format: 53.138 (Italian thousand separator, no decimals)
            # Or: 53138 (no separators)
            if clean.count('.') == 1 and len(clean.split('.')[1]) == 3:
                # It's a thousand separator (e.g., 53.138)
                clean = clean.replace('.', '')
            # else: it's already a proper decimal
            # For safety, assume integers in balance sheets
            clean = clean.replace('.', '')

        try:
            return Decimal(clean)
        except Exception as e:
            logger.warning(f"Could not parse number '{value_str}': {e}, returning 0")
            return Decimal('0')

    def extract_balance_sheet(self, doc_text: str, year: int = None, company_name: str = None) -> Dict[str, Decimal]:
        """
        Extract balance sheet data from Docling-extracted markdown text.

        Args:
            doc_text: Markdown text from Docling document converter
            year: Fiscal year (optional, for metadata)
            company_name: Company name (optional, for metadata)

        Returns:
            Dictionary mapping field names (sp01-sp18) to Decimal values
        """
        lines = doc_text.split('\n')

        # Initialize result with all fields as zero (matches database.models.BalanceSheet)
        result = {}

        for field in ['sp01_crediti_soci', 'sp02_immob_immateriali', 'sp03_immob_materiali',
                      'sp04_immob_finanziarie', 'sp05_rimanenze', 'sp06_crediti_breve',
                      'sp07_crediti_lungo', 'sp08_attivita_finanziarie', 'sp09_disponibilita_liquide',
                      'sp10_ratei_risconti_attivi', 'sp11_capitale',
                      'sp12_riserve', 'sp13_utile_perdita', 'sp14_fondi_rischi',
                      'sp15_tfr', 'sp16_debiti_breve', 'sp17_debiti_lungo',
                      'sp18_ratei_risconti_passivi', 'totale_attivo', 'totale_passivo']:
            result[field] = Decimal('0')

        # Extract values using patterns
        for field, pattern_list in self.FIELD_PATTERNS.items():
            for pattern in pattern_list:
                for line in lines:
                    match = re.search(pattern, line, re.IGNORECASE)
                    if match:
                        value_str = match.group(1)
                        result[field] = self.parse_italian_number(value_str)
                        logger.debug(f"Found {field}: {value_str} -> {result[field]}")
                        break
                if result[field] != Decimal('0'):
                    break

        # Calculate sp12_riserve (reserves) by extracting components
        # In Bilancio Micro, reserves are often shown as a single aggregate line
        reserves_patterns = [
            r'\|\s*IV\s*-\s*Riserva\s+legale\s*\|\s*([\d\.,\-]+)\s*\|',
            r'\|\s*VI\s*-\s*Altre\s+riserve\s*\|\s*([\d\.,\-]+)\s*\|',
            r'\|\s*V\s*-\s*Riserv.*rivalutaz.*\|\s*([\d\.,\-]+)\s*\|',
            r'\|\s*VII\s*-\s*Riserv.*capitale\s*\|\s*([\d\.,\-]+)\s*\|',
            r'\|\s*VIII\s*-\s*Utili.*perdite.*portati\s*\|\s*([\d\.,\-]+)\s*\|',
            # Sometimes shown as aggregate II-VIII
            r'\|\s*II.*VIII\s*-\s*Riserve\s*\|\s*([\d\.,\-]+)\s*\|',
        ]

        reserves_total = Decimal('0')
        for pattern in reserves_patterns:
            for line in lines:
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    value_str = match.group(1)
                    reserves_total += self.parse_italian_number(value_str)
                    logger.debug(f"Found reserve component: {value_str}")

        result['sp12_riserve'] = reserves_total

        return result

    def validate_balance(self, data: Dict[str, Decimal]) -> bool:
        """
        Validate IV CEE fundamental equation:
        Total Assets = Total Liabilities + Equity

        Args:
            data: Extracted balance sheet dictionary

        Returns:
            True if balanced (within rounding tolerance)
        """
        total_attivo = data.get('totale_attivo', Decimal('0'))
        total_passivo = data.get('totale_passivo', Decimal('0'))

        difference = abs(total_attivo - total_passivo)

        # Allow small rounding differences (±€1)
        tolerance = Decimal('1.00')

        if difference <= tolerance:
            logger.info(f"✓ Balance verified: Assets={total_attivo}, Liabilities={total_passivo}")
            return True
        else:
            logger.error(
                f"✗ Balance FAILED: Assets={total_attivo} ≠ Liabilities={total_passivo} "
                f"(difference: {difference})"
            )
            return False

    def validate_hierarchy(self, data: Dict[str, Decimal]) -> List[str]:
        """
        Validate hierarchical consistency (subtotals = sum of components).

        Args:
            data: Extracted balance sheet dictionary

        Returns:
            List of validation warning messages (empty if all valid)
        """
        warnings = []

        # Validate immobilizzazioni (B)
        immob_sum = (
            data.get('sp02_immob_immateriali', Decimal('0')) +
            data.get('sp03_immob_materiali', Decimal('0')) +
            data.get('sp04_immob_finanziarie', Decimal('0'))
        )

        # Validate current assets (C)
        current_assets = (
            data.get('sp05_rimanenze', Decimal('0')) +
            data.get('sp06_crediti_breve', Decimal('0')) +
            data.get('sp07_crediti_lungo', Decimal('0')) +
            data.get('sp08_attivita_finanziarie', Decimal('0')) +
            data.get('sp09_disponibilita_liquide', Decimal('0'))
        )

        # Validate total assets
        calculated_total_assets = (
            immob_sum + current_assets +
            data.get('sp10_ratei_risconti_attivi', Decimal('0'))
        )

        stated_total_assets = data.get('totale_attivo', Decimal('0'))

        if abs(calculated_total_assets - stated_total_assets) > Decimal('1.00'):
            warnings.append(
                f"Total assets mismatch: calculated={calculated_total_assets}, "
                f"stated={stated_total_assets}"
            )

        return warnings

    def extract_income_statement(self, doc_text: str) -> Dict[str, Decimal]:
        """
        Extract income statement data from PDF text.

        Args:
            doc_text: Markdown text from Docling

        Returns:
            Dictionary with income statement fields
        """
        lines = doc_text.split('\n')

        result = {
            'ce01_ricavi_vendite': Decimal('0'),
            'ce20_utile_perdita': Decimal('0'),
        }

        # Revenue pattern (table format)
        revenue_pattern = r'\|\s*1\)\s*ricavi\s+delle\s+vendite.*prestazioni\s*\|\s*([\d\.,\-]+)\s*\|'

        for line in lines:
            match = re.search(revenue_pattern, line, re.IGNORECASE)
            if match:
                value_str = match.group(1)
                result['ce01_ricavi_vendite'] = self.parse_italian_number(value_str)
                logger.debug(f"Found ce01_ricavi_vendite: {value_str} -> {result['ce01_ricavi_vendite']}")
                break

        # Profit/loss pattern
        profit_pattern = r'\|\s*21\)\s*Utile.*perdita.*esercizio\s*\|\s*([\d\.,\-]+)\s*\|'

        for line in lines:
            match = re.search(profit_pattern, line, re.IGNORECASE)
            if match:
                value_str = match.group(1)
                result['ce20_utile_perdita'] = self.parse_italian_number(value_str)
                logger.debug(f"Found ce20_utile_perdita: {value_str} -> {result['ce20_utile_perdita']}")
                break

        return result
