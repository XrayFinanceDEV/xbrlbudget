"""
PDF to IV CEE Balance Sheet Mapper Service.

This module provides functionality to extract balance sheet and income statement
data from Italian PDF balance sheets using Docling table DataFrames,
and map them to the sp01-sp18 / ce01-ce20 schema.
"""

from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Any
import re
import logging

logger = logging.getLogger(__name__)


class IVCEEMapper:
    """
    Mapper service to extract and validate Italian balance sheet data from
    Docling-extracted tables (DataFrames).

    Supports:
    - Bilancio Micro (simplified format for small companies)
    - Bilancio Abbreviato (abbreviated format)
    - Bilancio Ordinario (full format)
    """

    def parse_italian_number(self, value_str: Any) -> Decimal:
        """
        Convert Italian number format to Decimal.

        Handles:
        - Italian format: 1.234.567,89 (periods as thousand separators, comma as decimal)
        - Parenthesized negatives: (347.117) -> -347117
        - Dash or empty -> 0
        - Merged columns: "32.129  (97.772)" -> takes first value only
        """
        if value_str is None:
            return Decimal('0')

        clean = str(value_str).strip()

        if not clean or clean in ['-', '', 'None', 'n/a', 'N/A']:
            return Decimal('0')

        # Handle merged columns from Docling: "32.129  (97.772)" or "(123)  456"
        # Two or more spaces separate current year from prior year - take first value
        multi_match = re.match(r'^(\([\d\.,]+\)|[\d\.,]+)\s{2,}(\([\d\.,]+\)|[\d\.,]+)', clean)
        if multi_match:
            logger.info(f"Multi-value cell detected, using first value: '{multi_match.group(1)}' from '{value_str}'")
            clean = multi_match.group(1)

        # Handle parenthesized negatives: (347.117) -> -347117
        negative = False
        if clean.startswith('(') and clean.endswith(')'):
            negative = True
            clean = clean[1:-1].strip()

        # Remove spaces
        clean = clean.replace(' ', '')

        # Check if there's a comma (decimal separator)
        if ',' in clean:
            clean = clean.replace('.', '')   # Remove thousand separators
            clean = clean.replace(',', '.')  # Replace decimal comma with dot
        else:
            # All dots are thousand separators (no decimal part)
            clean = clean.replace('.', '')

        try:
            result = Decimal(clean)
            return -result if negative else result
        except (InvalidOperation, ValueError) as e:
            logger.warning(f"Could not parse number '{value_str}': {e}, returning 0")
            return Decimal('0')

    # ------------------------------------------------------------------
    # DataFrame-based extraction (primary method)
    # ------------------------------------------------------------------

    def _find_table_containing(self, tables: list, keyword: str, doc=None) -> Optional[Any]:
        """Find the first table whose first column contains keyword."""
        for table in tables:
            try:
                df = table.export_to_dataframe(doc=doc) if doc else table.export_to_dataframe()
                col0_text = ' '.join(str(v) for v in df.iloc[:, 0].values)
                if keyword.lower() in col0_text.lower():
                    return df
            except Exception:
                continue
        return None

    def _find_tables_containing(self, tables: list, keywords: List[str], doc=None) -> List[Any]:
        """Find all tables whose first column contains any of the keywords."""
        result = []
        for table in tables:
            try:
                df = table.export_to_dataframe(doc=doc) if doc else table.export_to_dataframe()
                col0_text = ' '.join(str(v) for v in df.iloc[:, 0].values)
                col0_lower = col0_text.lower()
                if any(kw.lower() in col0_lower for kw in keywords):
                    result.append(df)
            except Exception:
                continue
        return result

    def _get_value(self, row, col_idx: int) -> Decimal:
        """Extract a Decimal value from a DataFrame row at the given column index."""
        try:
            val = row.iloc[col_idx]
            return self.parse_italian_number(val)
        except (IndexError, AttributeError):
            return Decimal('0')

    def _label_contains(self, label: str, keyword: str) -> bool:
        """Case-insensitive, accent-tolerant substring match."""
        # Normalize accented chars for matching
        label_norm = label.lower().replace('à', 'a').replace('è', 'e').replace('ò', 'o').replace('ù', 'u').replace('ì', 'i')
        keyword_norm = keyword.lower().replace('à', 'a').replace('è', 'e').replace('ò', 'o').replace('ù', 'u').replace('ì', 'i')
        return keyword_norm in label_norm

    def extract_from_tables(self, tables: list, fiscal_year: int = None, doc=None) -> Dict[str, Decimal]:
        """
        Extract balance sheet data from Docling table objects.

        Finds the Stato Patrimoniale table and parses all sp01-sp18 fields
        by matching row labels.

        Args:
            tables: List of Docling TableItem objects
            fiscal_year: Fiscal year (for metadata)
            doc: Docling Document object (pass to avoid deprecation warning)

        Returns:
            Dictionary mapping field names to Decimal values
        """
        # Initialize all fields to zero
        result: Dict[str, Decimal] = {}
        all_fields = [
            'sp01_crediti_soci', 'sp02_immob_immateriali', 'sp03_immob_materiali',
            'sp04_immob_finanziarie', 'sp05_rimanenze', 'sp06_crediti_breve',
            'sp07_crediti_lungo', 'sp08_attivita_finanziarie', 'sp09_disponibilita_liquide',
            'sp10_ratei_risconti_attivi', 'sp11_capitale', 'sp12_riserve',
            'sp13_utile_perdita', 'sp14_fondi_rischi', 'sp15_tfr',
            'sp16_debiti_breve', 'sp17_debiti_lungo', 'sp18_ratei_risconti_passivi',
            'totale_attivo', 'totale_passivo',
        ]
        for f in all_fields:
            result[f] = Decimal('0')

        # Find the SP table (contains "Totale attivo")
        sp_df = self._find_table_containing(tables, "Totale attivo", doc=doc)
        if sp_df is None:
            logger.warning("Could not find Stato Patrimoniale table in PDF")
            return result

        logger.info(f"Found SP table: {sp_df.shape[0]} rows x {sp_df.shape[1]} cols")

        # Current year values are in column 1 (col index 1)
        val_col = 1

        # Context tracking for "esigibili entro/oltre" under Crediti vs Debiti
        context = None  # 'crediti' or 'debiti'
        ratei_count = 0  # Track first (attivo) vs second (passivo) ratei e risconti
        reserves = Decimal('0')

        for idx in range(sp_df.shape[0]):
            label = str(sp_df.iloc[idx, 0]).strip()
            value = self._get_value(sp_df.iloc[idx], val_col)

            # --- Context tracking ---
            if self._label_contains(label, 'II - Crediti'):
                context = 'crediti'
                continue
            if self._label_contains(label, 'D) Debiti'):
                context = 'debiti'
                continue

            # --- Assets (Attivo) ---
            if self._label_contains(label, 'A) Crediti verso soci'):
                result['sp01_crediti_soci'] = value
            elif self._label_contains(label, 'I - Immobilizzazioni immateriali'):
                result['sp02_immob_immateriali'] = value
            elif self._label_contains(label, 'II - Immobilizzazioni materiali'):
                result['sp03_immob_materiali'] = value
            elif self._label_contains(label, 'III - Immobilizzazioni finanziarie'):
                result['sp04_immob_finanziarie'] = value
            elif self._label_contains(label, 'I - Rimanenze'):
                result['sp05_rimanenze'] = value

            # Crediti: esigibili entro/oltre
            elif self._label_contains(label, 'esigibili entro') and context == 'crediti':
                result['sp06_crediti_breve'] = value
            elif self._label_contains(label, 'esigibili oltre') and context == 'crediti':
                result['sp07_crediti_lungo'] = value
            elif self._label_contains(label, 'Totale crediti') and result['sp06_crediti_breve'] == 0:
                # Fallback: if esigibili not split, use total
                result['sp06_crediti_breve'] = value

            elif self._label_contains(label, 'finanziarie che non costituiscono'):
                result['sp08_attivita_finanziarie'] = value
            elif self._label_contains(label, 'Disponibilit') and self._label_contains(label, 'liquide'):
                result['sp09_disponibilita_liquide'] = value

            # Ratei e risconti - first occurrence = attivo (sp10), second = passivo (sp18)
            elif self._label_contains(label, 'Ratei e risconti') and not self._label_contains(label, 'Totale'):
                ratei_count += 1
                if ratei_count == 1:
                    result['sp10_ratei_risconti_attivi'] = value
                elif ratei_count == 2:
                    result['sp18_ratei_risconti_passivi'] = value

            elif self._label_contains(label, 'Totale attivo'):
                result['totale_attivo'] = value

            # --- Equity (Patrimonio Netto) ---
            elif self._label_contains(label, 'I - Capitale'):
                result['sp11_capitale'] = value

            # Reserve components → accumulate into sp12
            elif self._label_contains(label, 'II - Riserva da soprapprezzo'):
                reserves += value
            elif self._label_contains(label, 'III - Riserve di rivalutazione'):
                reserves += value
            elif self._label_contains(label, 'IV - Riserva legale'):
                reserves += value
            elif self._label_contains(label, 'V - Riserve statutarie'):
                reserves += value
            elif self._label_contains(label, 'VI - Altre riserve'):
                reserves += value
            elif self._label_contains(label, 'VII - Riserva per operazioni'):
                reserves += value
            elif self._label_contains(label, 'VIII - Utili') and self._label_contains(label, 'portati'):
                reserves += value

            elif self._label_contains(label, 'IX - Utile') or self._label_contains(label, 'IX - Perdita'):
                result['sp13_utile_perdita'] = value

            # --- Liabilities ---
            elif self._label_contains(label, 'B) Fondi per rischi'):
                result['sp14_fondi_rischi'] = value
            elif self._label_contains(label, 'C) Trattamento di fine rapporto'):
                result['sp15_tfr'] = value

            # Debiti: esigibili entro/oltre
            elif self._label_contains(label, 'esigibili entro') and context == 'debiti':
                result['sp16_debiti_breve'] = value
            elif self._label_contains(label, 'esigibili oltre') and context == 'debiti':
                result['sp17_debiti_lungo'] = value
            elif self._label_contains(label, 'Totale debiti') and result['sp16_debiti_breve'] == 0:
                # Fallback: if esigibili not split, put all in short-term
                result['sp16_debiti_breve'] = value

            elif self._label_contains(label, 'Totale passivo'):
                result['totale_passivo'] = value

        result['sp12_riserve'] = reserves

        # Log extracted values
        for field in all_fields:
            if result[field] != 0:
                logger.info(f"  SP {field} = {result[field]}")

        return result

    def extract_income_from_tables(self, tables: list, doc=None) -> Dict[str, Decimal]:
        """
        Extract income statement data from Docling table objects.

        Finds the Conto Economico tables and parses all ce01-ce20 fields.

        Args:
            tables: List of Docling TableItem objects
            doc: Docling Document object (pass to avoid deprecation warning)

        Returns:
            Dictionary mapping ce field names to Decimal values
        """
        result: Dict[str, Decimal] = {
            'ce01_ricavi_vendite': Decimal('0'),
            'ce02_variazioni_rimanenze': Decimal('0'),
            'ce03_lavori_interni': Decimal('0'),
            'ce04_altri_ricavi': Decimal('0'),
            'ce05_materie_prime': Decimal('0'),
            'ce06_servizi': Decimal('0'),
            'ce07_godimento_beni': Decimal('0'),
            'ce08_costi_personale': Decimal('0'),
            'ce08a_tfr_accrual': Decimal('0'),
            'ce09_ammortamenti': Decimal('0'),
            'ce09a_ammort_immateriali': Decimal('0'),
            'ce09b_ammort_materiali': Decimal('0'),
            'ce09c_svalutazioni': Decimal('0'),
            'ce09d_svalutazione_crediti': Decimal('0'),
            'ce10_var_rimanenze_mat_prime': Decimal('0'),
            'ce11_accantonamenti': Decimal('0'),
            'ce11b_altri_accantonamenti': Decimal('0'),
            'ce12_oneri_diversi': Decimal('0'),
            'ce13_proventi_partecipazioni': Decimal('0'),
            'ce14_altri_proventi_finanziari': Decimal('0'),
            'ce15_oneri_finanziari': Decimal('0'),
            'ce16_utili_perdite_cambi': Decimal('0'),
            'ce17_rettifiche_attivita_fin': Decimal('0'),
            'ce18_proventi_straordinari': Decimal('0'),
            'ce19_oneri_straordinari': Decimal('0'),
            'ce20_imposte': Decimal('0'),
        }

        # Find CE tables - they contain revenue/cost keywords
        ce_keywords = [
            'ricavi delle vendite',
            'Valore della produzione',
            'Costi della produzione',
            'Proventi e oneri finanziari',
            'Utile (perdita)',
        ]
        ce_dfs = self._find_tables_containing(tables, ce_keywords, doc=doc)

        if not ce_dfs:
            logger.warning("Could not find Conto Economico tables in PDF")
            return result

        logger.info(f"Found {len(ce_dfs)} CE tables")

        # Current year values are in column 1
        val_col = 1

        # Context tracking for financial income section ("altri" under 17)
        context = None  # 'oneri_finanziari'

        # Process all CE table rows
        for df in ce_dfs:
            for idx in range(df.shape[0]):
                label = str(df.iloc[idx, 0]).strip()
                value = self._get_value(df.iloc[idx], val_col)

                # Context tracking
                if self._label_contains(label, '17) interessi e altri oneri'):
                    context = 'oneri_finanziari'
                elif self._label_contains(label, '18)') or self._label_contains(label, 'Rettifiche di valore'):
                    context = None

                # --- A) Valore della produzione ---
                if self._label_contains(label, '1) ricavi delle vendite'):
                    result['ce01_ricavi_vendite'] = value

                elif (self._label_contains(label, '2) variazioni delle rimanenze di prodotti')
                      or self._label_contains(label, '2), 3) variazioni delle rimanenze')):
                    result['ce02_variazioni_rimanenze'] = value

                elif self._label_contains(label, '4) incrementi di immobilizzazioni'):
                    result['ce03_lavori_interni'] = value

                elif self._label_contains(label, 'Totale altri ricavi e proventi'):
                    result['ce04_altri_ricavi'] = value

                # --- B) Costi della produzione ---
                elif self._label_contains(label, '6) per materie prime'):
                    result['ce05_materie_prime'] = value

                elif self._label_contains(label, '7) per servizi'):
                    result['ce06_servizi'] = value

                elif self._label_contains(label, '8) per godimento di beni'):
                    result['ce07_godimento_beni'] = value

                elif self._label_contains(label, 'Totale costi per il personale'):
                    result['ce08_costi_personale'] = value

                elif (self._label_contains(label, 'c) trattamento di fine rapporto')
                      and not self._label_contains(label, 'd)')
                      and not self._label_contains(label, 'e)')
                      and self._label_contains(label, 'costi del personale')):
                    result['ce08a_tfr_accrual'] = value

                elif self._label_contains(label, 'a), b), c) ammortamento'):
                    result['ce09_ammortamenti'] = value

                elif self._label_contains(label, 'a) ammortamento delle immobilizzazioni imma'):
                    result['ce09a_ammort_immateriali'] = value

                elif self._label_contains(label, 'b) ammortamento delle immobilizzazioni mate'):
                    result['ce09b_ammort_materiali'] = value

                elif self._label_contains(label, 'c) altre svalutazioni delle immobilizzazioni'):
                    result['ce09c_svalutazioni'] = value

                elif self._label_contains(label, 'd) svalutazioni dei crediti'):
                    result['ce09d_svalutazione_crediti'] = value

                elif self._label_contains(label, '11) variazioni delle rimanenze di materie'):
                    # This line can be merged with "Totale ammortamenti" in the PDF
                    # Try to parse from a merged cell if needed
                    result['ce10_var_rimanenze_mat_prime'] = value

                elif self._label_contains(label, '12) accantonamenti per rischi'):
                    result['ce11_accantonamenti'] = value

                elif self._label_contains(label, '13) altri accantonamenti'):
                    result['ce11b_altri_accantonamenti'] = value

                elif self._label_contains(label, '14) oneri diversi di gestione'):
                    result['ce12_oneri_diversi'] = value

                # --- C) Proventi e oneri finanziari ---
                elif self._label_contains(label, '15) proventi da partecipazioni'):
                    result['ce13_proventi_partecipazioni'] = value

                elif self._label_contains(label, 'Totale altri proventi finanziari'):
                    result['ce14_altri_proventi_finanziari'] = value

                elif self._label_contains(label, 'Totale interessi e altri oneri'):
                    result['ce15_oneri_finanziari'] = value
                elif (context == 'oneri_finanziari'
                      and label.strip().lower() == 'altri'
                      and value != 0
                      and result['ce15_oneri_finanziari'] == 0):
                    # "altri" under "17) interessi e altri oneri finanziari"
                    result['ce15_oneri_finanziari'] = value

                elif self._label_contains(label, '17-bis') and self._label_contains(label, 'cambi'):
                    result['ce16_utili_perdite_cambi'] = value

                # --- D) Rettifiche ---
                elif self._label_contains(label, 'Totale delle rettifiche'):
                    result['ce17_rettifiche_attivita_fin'] = value

                # --- Imposte ---
                elif self._label_contains(label, 'Totale delle imposte'):
                    result['ce20_imposte'] = value

                # Handle the merged "Totale ammortamenti...11) variazioni" row
                elif (self._label_contains(label, 'Totale ammortamenti')
                      and self._label_contains(label, '11) variazioni')):
                    # This merged row has two values concatenated
                    # Try to extract the second value (ce10)
                    self._parse_merged_amm_var(df.iloc[idx], result, val_col)

        # Log extracted values
        for field, val in result.items():
            if val != 0:
                logger.info(f"  CE {field} = {val}")

        return result

    def _parse_merged_amm_var(self, row, result: Dict[str, Decimal], val_col: int):
        """
        Handle the merged row: "Totale ammortamenti e svalutazioni  11) variazioni..."
        which has two values concatenated in the value cell, e.g. "32.129  (97.772)".
        """
        try:
            raw = str(row.iloc[val_col]).strip()
            # Split on whitespace to find multiple numbers
            parts = re.findall(r'\([\d\.,]+\)|[\d\.,]+', raw)
            if len(parts) >= 2:
                # First = ammortamenti total, second = variazioni rimanenze
                amm_val = self.parse_italian_number(parts[0])
                var_val = self.parse_italian_number(parts[1])
                if result['ce09_ammortamenti'] == 0:
                    result['ce09_ammortamenti'] = amm_val
                if result['ce10_var_rimanenze_mat_prime'] == 0:
                    result['ce10_var_rimanenze_mat_prime'] = var_val
                logger.info(f"  Parsed merged amm/var row: ce09={amm_val}, ce10={var_val}")
        except Exception as e:
            logger.warning(f"Could not parse merged amm/var row: {e}")

    # ------------------------------------------------------------------
    # Validation methods (unchanged)
    # ------------------------------------------------------------------

    def validate_balance(self, data: Dict[str, Decimal]) -> bool:
        """
        Validate IV CEE fundamental equation:
        Total Assets = Total Liabilities + Equity
        """
        total_attivo = data.get('totale_attivo', Decimal('0'))
        total_passivo = data.get('totale_passivo', Decimal('0'))

        difference = abs(total_attivo - total_passivo)
        tolerance = Decimal('1.00')

        if difference <= tolerance:
            logger.info(f"Balance verified: Assets={total_attivo}, Liabilities={total_passivo}")
            return True
        else:
            logger.error(
                f"Balance FAILED: Assets={total_attivo} != Liabilities={total_passivo} "
                f"(difference: {difference})"
            )
            return False

    def validate_hierarchy(self, data: Dict[str, Decimal]) -> List[str]:
        """
        Validate hierarchical consistency (subtotals = sum of components).
        """
        warnings = []

        immob_sum = (
            data.get('sp02_immob_immateriali', Decimal('0')) +
            data.get('sp03_immob_materiali', Decimal('0')) +
            data.get('sp04_immob_finanziarie', Decimal('0'))
        )

        current_assets = (
            data.get('sp05_rimanenze', Decimal('0')) +
            data.get('sp06_crediti_breve', Decimal('0')) +
            data.get('sp07_crediti_lungo', Decimal('0')) +
            data.get('sp08_attivita_finanziarie', Decimal('0')) +
            data.get('sp09_disponibilita_liquide', Decimal('0'))
        )

        calculated_total_assets = (
            data.get('sp01_crediti_soci', Decimal('0')) +
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

    # ------------------------------------------------------------------
    # Legacy markdown-based extraction (fallback)
    # ------------------------------------------------------------------

    FIELD_PATTERNS = {
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
        'sp06_crediti_breve': [
            r'\|\s*Totale\s+crediti\s*\|\s*([\d\.,\-]+)\s*\|',
        ],
        'sp08_attivita_finanziarie': [
            r'\|\s*III\s*-\s*Attivit.*finanziarie.*non.*immobilizzazioni\s*\|\s*([\d\.,\-]+)\s*\|',
        ],
        'sp09_disponibilita_liquide': [
            r'\|\s*IV\s*-\s*Disponibilit.*liquide\s*\|\s*([\d\.,\-]+)\s*\|',
        ],
        'sp10_ratei_risconti_attivi': [
            r'\|\s*D\)\s*Ratei\s+e\s+risconti\s*\|\s*([\d\.,\-]+)\s*\|',
        ],
        'totale_attivo': [
            r'\|\s*Totale\s+attivo\s*\|\s*([\d\.,\-]+)\s*\|',
        ],
        'sp11_capitale': [
            r'\|\s*I\s*-\s*Capitale\s*\|\s*([\d\.,\-]+)\s*\|',
        ],
        'sp13_utile_perdita': [
            r'\|\s*IX\s*-\s*Utile.*perdita.*esercizio\s*\|\s*([\d\.,\-]+)\s*\|',
        ],
        'sp14_fondi_rischi': [
            r'\|\s*B\)\s*Fondi.*rischi.*oneri\s*\|\s*([\d\.,\-]+)\s*\|',
        ],
        'sp15_tfr': [
            r'\|\s*C\)\s*Trattamento.*fine.*rapporto.*\|\s*([\d\.,\-]+)\s*\|',
        ],
        'sp16_debiti_breve': [
            r'\|\s*Totale\s+debiti\s*\|\s*([\d\.,\-]+)\s*\|',
        ],
        'sp18_ratei_risconti_passivi': [
            r'\|\s*E\)\s*Ratei\s+e\s+risconti\s*\|\s*([\d\.,\-]+)\s*\|',
        ],
        'totale_passivo': [
            r'\|\s*Totale\s+passivo\s*\|\s*([\d\.,\-]+)\s*\|',
        ],
    }

    def extract_balance_sheet(self, doc_text: str, year: int = None, company_name: str = None) -> Dict[str, Decimal]:
        """Legacy markdown-based extraction (fallback)."""
        lines = doc_text.split('\n')

        result = {}
        for field in ['sp01_crediti_soci', 'sp02_immob_immateriali', 'sp03_immob_materiali',
                      'sp04_immob_finanziarie', 'sp05_rimanenze', 'sp06_crediti_breve',
                      'sp07_crediti_lungo', 'sp08_attivita_finanziarie', 'sp09_disponibilita_liquide',
                      'sp10_ratei_risconti_attivi', 'sp11_capitale',
                      'sp12_riserve', 'sp13_utile_perdita', 'sp14_fondi_rischi',
                      'sp15_tfr', 'sp16_debiti_breve', 'sp17_debiti_lungo',
                      'sp18_ratei_risconti_passivi', 'totale_attivo', 'totale_passivo']:
            result[field] = Decimal('0')

        for field, pattern_list in self.FIELD_PATTERNS.items():
            for pattern in pattern_list:
                for line in lines:
                    match = re.search(pattern, line, re.IGNORECASE)
                    if match:
                        result[field] = self.parse_italian_number(match.group(1))
                        break
                if result[field] != Decimal('0'):
                    break

        reserves_patterns = [
            r'\|\s*IV\s*-\s*Riserva\s+legale\s*\|\s*([\d\.,\-]+)\s*\|',
            r'\|\s*VI\s*-\s*Altre\s+riserve\s*\|\s*([\d\.,\-]+)\s*\|',
            r'\|\s*V\s*-\s*Riserv.*statutari.*\|\s*([\d\.,\-]+)\s*\|',
        ]

        reserves_total = Decimal('0')
        for pattern in reserves_patterns:
            for line in lines:
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    reserves_total += self.parse_italian_number(match.group(1))

        result['sp12_riserve'] = reserves_total
        return result

    def extract_income_statement(self, doc_text: str) -> Dict[str, Decimal]:
        """Legacy markdown-based extraction (fallback)."""
        lines = doc_text.split('\n')
        result = {'ce01_ricavi_vendite': Decimal('0')}

        revenue_pattern = r'\|\s*1\)\s*ricavi\s+delle\s+vendite.*prestazioni\s*\|\s*([\d\.,\-]+)\s*\|'
        for line in lines:
            match = re.search(revenue_pattern, line, re.IGNORECASE)
            if match:
                result['ce01_ricavi_vendite'] = self.parse_italian_number(match.group(1))
                break

        return result
