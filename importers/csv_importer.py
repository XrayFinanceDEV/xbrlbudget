"""
CSV Importer for TEBE XBRL Conversions
Imports financial data from semicolon-delimited CSV files
"""
import csv
import re
import html
import json
import hashlib
import logging
import unicodedata
from decimal import Decimal
from typing import Dict, List, Tuple, Optional
from pathlib import Path
from datetime import datetime
from database.models import BalanceSheet, IncomeStatement, Company, FinancialYear
from database.db import SessionLocal
from config import BalanceSheetType, TAXONOMY_ROW_COUNTS, CSV_DELIMITER, CSV_HTML_ENTITIES_TO_REPLACE


logger = logging.getLogger(__name__)


class CSVImportError(Exception):
    """Raised when CSV import fails"""
    pass


class CSVImporter:
    """
    Imports financial data from TEBE and BILAQ CSV formats.
    """
    TEBE_TAG_FIELDS = {
        **{f'SP{i:02d}': field for i, field in enumerate((
            'sp01_crediti_soci', 'sp02_immob_immateriali', 'sp03_immob_materiali',
            'sp04_immob_finanziarie', 'sp05_rimanenze', 'sp06_crediti_breve',
            'sp07_crediti_lungo', 'sp08_attivita_finanziarie',
            'sp09_disponibilita_liquide', 'sp10_ratei_risconti_attivi',
            'sp11_capitale', 'sp12_riserve', 'sp13_utile_perdita',
            'sp14_fondi_rischi', 'sp15_tfr', 'sp16_debiti_breve',
            'sp17_debiti_lungo', 'sp18_ratei_risconti_passivi',
        ), start=1)},
        **{f'CE{i:02d}': field for i, field in enumerate((
            'ce01_ricavi_vendite', 'ce02_variazioni_rimanenze',
            'ce03a_incrementi_immobilizzazioni', 'ce04_altri_ricavi',
            'ce05_materie_prime', 'ce06_servizi', 'ce07_godimento_beni',
            'ce08_costi_personale', 'ce09_ammortamenti',
            'ce10_var_rimanenze_mat_prime', 'ce11_accantonamenti',
            'ce12_oneri_diversi', 'ce13_proventi_partecipazioni',
            'ce14_altri_proventi_finanziari', 'ce15_oneri_finanziari',
            'ce16_utili_perdite_cambi', 'ce17_rettifiche_attivita_fin',
            'ce18_proventi_straordinari', 'ce19_oneri_straordinari',
            'ce20_imposte',
        ), start=1)},
    }

    def __init__(self, db_session=None):
        """
        Initialize CSV importer

        Args:
            db_session: Database session (optional, will create if not provided)
        """
        self.db = db_session or SessionLocal()
        self._own_session = db_session is None
        self.csv_metadata: Dict[str, object] = {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._own_session:
            self.db.close()

    def clean_html_entities(self, text: str) -> str:
        """
        Clean HTML entities from text

        Args:
            text: Text to clean

        Returns:
            Cleaned text
        """
        if not text:
            return text

        # Replace configured entities
        cleaned = text
        for entity, replacement in CSV_HTML_ENTITIES_TO_REPLACE.items():
            # Literal accented letters are valid data, not HTML entities.  The old
            # table also contains transliteration rules; applying those here hid an
            # encoding error and damaged descriptions such as "Disponibilità".
            if entity.startswith('&'):
                cleaned = cleaned.replace(entity, replacement)

        # Decode any remaining HTML entities
        cleaned = html.unescape(cleaned)

        return cleaned.strip()

    def parse_monetary_value(self, value_str: str) -> Decimal:
        """
        Parse monetary value from CSV string

        Handles formats like:
        - "1.234.567,89" (Italian format)
        - "1234567.89" (Standard format)
        - "1 234 567" (with spaces, from TEBE CSV)

        Args:
            value_str: String representation of monetary value

        Returns:
            Decimal value
        """
        if not value_str or value_str.strip() == "":
            return Decimal('0')

        # Clean the string
        cleaned = value_str.strip()

        # Remove HTML entities
        cleaned = self.clean_html_entities(cleaned)

        # Remove currency symbols
        cleaned = re.sub(r'[€$]', '', cleaned)

        # Handle Italian format (1.234.567,89 -> 1234567.89)
        if ',' in cleaned and '.' in cleaned:
            # Italian format: remove dots (thousands), replace comma with dot
            cleaned = cleaned.replace('.', '').replace(',', '.')
        elif ',' in cleaned and '.' not in cleaned:
            # Only comma: replace with dot
            cleaned = cleaned.replace(',', '.')

        # Remove spaces (TEBE format: "1 234 567")
        cleaned = cleaned.replace(' ', '')

        # Remove any remaining non-numeric characters except dot and minus
        cleaned = re.sub(r'[^\d.-]', '', cleaned)

        try:
            return Decimal(cleaned)
        except Exception as e:
            raise CSVImportError(f"Cannot parse monetary value '{value_str}': {e}")

    def detect_balance_sheet_type(self, first_row: str, row_count: int) -> BalanceSheetType:
        """
        Detect balance sheet type from CSV

        Args:
            first_row: First row text
            row_count: Number of data rows

        Returns:
            BalanceSheetType
        """
        # Check first row text
        first_row_upper = first_row.upper()

        if "BILANCIO MICRO" in first_row_upper or "MICRO" in first_row_upper:
            return BalanceSheetType.MICRO
        elif "BILANCIO ABBREVIATO" in first_row_upper or "ABBREVIATO" in first_row_upper:
            return BalanceSheetType.ABBREVIATO
        elif "BILANCIO ESERCIZIO" in first_row_upper or "ORDINARIO" in first_row_upper:
            return BalanceSheetType.ORDINARIO

        # Fallback: detect by row count
        for bs_type, valid_counts in TAXONOMY_ROW_COUNTS.items():
            if row_count in valid_counts:
                return bs_type

        # Default to ORDINARIO
        return BalanceSheetType.ORDINARIO

    @staticmethod
    def _normalise_header(value: str) -> str:
        value = unicodedata.normalize('NFKD', value or '')
        value = ''.join(char for char in value if not unicodedata.combining(char))
        return re.sub(r'[^a-z0-9]+', ' ', value.lower()).strip()

    def _decode_csv(self, file_path: str) -> Tuple[str, str]:
        raw = Path(file_path).read_bytes()
        if raw.startswith(b'\xef\xbb\xbf'):
            return raw.decode('utf-8-sig'), 'utf-8-sig'
        if raw.startswith(b'\xff\xfe'):
            return raw.decode('utf-16'), 'utf-16-le'
        if raw.startswith(b'\xfe\xff'):
            return raw.decode('utf-16'), 'utf-16-be'
        for encoding in ('utf-8', 'cp1252'):
            try:
                return raw.decode(encoding), encoding
            except UnicodeDecodeError:
                continue
        raise CSVImportError('Encoding CSV non supportato (attesi UTF-8, UTF-16 o Windows-1252)')

    def _detect_schema(self, first_row: List[str]) -> str:
        headers = {self._normalise_header(cell) for cell in first_row}
        if {'ragione sociale', 'data bilancio', 'descrizione item', 'valore corrente'} <= headers:
            return 'BILAQ'
        first_cell = self._normalise_header(first_row[0] if first_row else '')
        if (
            first_cell.startswith('bilancio')
            and any(re.search(r'\b(?:19|20)\d{2}\b', cell or '') for cell in first_row)
        ):
            return 'TEBE'
        raise CSVImportError(
            'Schema CSV non riconosciuto: attesa intestazione TEBE o BILAQ'
        )

    def read_csv_file(self, file_path: str) -> Tuple[BalanceSheetType, List[Dict]]:
        """
        Read and parse CSV file

        Args:
            file_path: Path to CSV file

        Returns:
            Tuple of (BalanceSheetType, list of row dictionaries)
        """
        if not Path(file_path).exists():
            raise CSVImportError(f"File not found: {file_path}")

        rows: List[Dict] = []
        try:
            text, encoding = self._decode_csv(file_path)
            all_rows = list(csv.reader(text.splitlines(), delimiter=CSV_DELIMITER))
            if len(all_rows) < 2:
                raise CSVImportError("CSV file has insufficient data")
            schema = self._detect_schema(all_rows[0])
            first_row_text = all_rows[0][0] if all_rows[0] else ''

            if schema == 'TEBE':
                headers = [self._normalise_header(cell) for cell in all_rows[0]]
                year_columns = [
                    (index, int(match.group(0)))
                    for index, cell in enumerate(all_rows[0])
                    if (match := re.search(r'\b(?:19|20)\d{2}\b', cell or ''))
                ]
                if not year_columns:
                    raise CSVImportError('TEBE senza colonne anno riconoscibili')
                tag_index = headers.index('tag') if 'tag' in headers else None
                unit_index = next(
                    (index for index, header in enumerate(headers) if header in ('euro', 'unita', 'unit')),
                    None,
                )
                for row_data in all_rows[1:]:
                    if not row_data or not any(cell.strip() for cell in row_data):
                        continue
                    values = [
                        row_data[index] if index < len(row_data) else '0'
                        for index, _ in year_columns
                    ]
                    rows.append({
                        'schema': schema,
                        'description': self.clean_html_entities(row_data[0]),
                        'values': values,
                        'value_year1': values[0] if values else '0',
                        'value_year2': values[1] if len(values) > 1 else '0',
                        'tag': self.clean_html_entities(row_data[tag_index])
                               if tag_index is not None and tag_index < len(row_data) else '',
                        'unit': self.clean_html_entities(row_data[unit_index])
                                if unit_index is not None and unit_index < len(row_data) else '',
                        'statement': '',
                        'section': '',
                    })
                detected_years = [year for _, year in year_columns]
            else:
                header_index = {
                    self._normalise_header(header): index
                    for index, header in enumerate(all_rows[0])
                }

                def cell(row_data: List[str], header: str) -> str:
                    index = header_index[header]
                    return row_data[index] if index < len(row_data) else ''

                statement = ''
                seen = set()
                detected_years = []
                for row_data in all_rows[1:]:
                    description = self.clean_html_entities(cell(row_data, 'descrizione item'))
                    description_normalised = self._normalise_header(description)
                    if description_normalised == 'stato patrimoniale attivo':
                        statement = 'sp_attivo'
                    elif description_normalised == 'stato patrimoniale passivo':
                        statement = 'sp_passivo'
                    elif description_normalised == 'conto economico':
                        statement = 'ce'

                    raw_date = cell(row_data, 'data bilancio').strip()
                    match = re.search(r'(?:19|20)\d{2}', raw_date)
                    if match and int(match.group(0)) not in detected_years:
                        detected_years.append(int(match.group(0)))
                    section = self.clean_html_entities(cell(row_data, 'sezione item'))
                    value = self.clean_html_entities(cell(row_data, 'valore corrente'))
                    source_code = self.clean_html_entities(cell(row_data, 'codnew'))
                    dedupe_key = (statement, source_code, section, description, value)
                    if dedupe_key in seen:
                        continue
                    seen.add(dedupe_key)
                    rows.append({
                        'schema': schema,
                        'description': description,
                        'values': [value],
                        'value_year1': value,
                        'value_year2': '0',
                        'tag': section,
                        'unit': 'EUR',
                        'statement': statement,
                        'section': section,
                        'level': int(cell(row_data, 'livello') or 0),
                        'is_total': self._normalise_header(cell(row_data, 'somma figli')) == 'true',
                        'source_code': source_code,
                    })

            self.csv_metadata = {
                'schema': schema,
                'encoding': encoding,
                'detected_years': detected_years,
            }
        except CSVImportError:
            raise
        except Exception as e:
            raise CSVImportError(f"Error reading CSV file: {e}") from e

        # Detect balance sheet type
        bs_type = self.detect_balance_sheet_type(first_row_text, len(rows))

        return bs_type, rows

    def map_row_to_field(self, description: str, is_balance_sheet: bool = True) -> Optional[str]:
        """
        Map row description to database field

        Args:
            description: Row description from CSV
            is_balance_sheet: True for balance sheet, False for income statement

        Returns:
            Database field name or None
        """
        # Load taxonomy mapping (simplified for now - could cache this)
        import json
        import os
        mapping_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'taxonomy_mapping.json')

        with open(mapping_path, 'r', encoding='utf-8') as f:
            taxonomy = json.load(f)

        csv_mapping = taxonomy['csv_simplified_mapping']
        section = 'balance_sheet' if is_balance_sheet else 'income_statement'

        # Fuzzy match description
        desc_clean = description.lower().strip()

        for key, field in csv_mapping[section].items():
            key_clean = key.lower().strip()
            if key_clean in desc_clean or desc_clean in key_clean:
                return field

        return None

    @staticmethod
    def _normalise_section(section: str) -> str:
        return re.sub(r'\s+', '', (section or '').upper()).replace('QUATER', 'QUATER')

    def _map_bilaq_row_to_fields(self, row: Dict) -> List[Tuple[str, str]]:
        """Map a BILAQ row by its semantic IV-CEE section, not column position."""
        statement = row.get('statement')
        section = self._normalise_section(row.get('section', ''))
        level = int(row.get('level') or 0)
        description = self._normalise_header(row.get('description', ''))
        result: List[Tuple[str, str]] = []

        if statement == 'sp_attivo':
            direct = {
                'A': 'sp01_crediti_soci',
                'B.I': 'sp02_immob_immateriali',
                'B.II': 'sp03_immob_materiali',
                'B.III': 'sp04_immob_finanziarie',
                'C.I': 'sp05_rimanenze',
                'C.III': 'sp08_attivita_finanziarie',
                'C.IV': 'sp09_disponibilita_liquide',
                'D': 'sp10_ratei_risconti_attivi',
            }
            detail = {
                'B.I.1': 'sp02a_costi_impianto', 'B.I.2': 'sp02b_costi_sviluppo',
                'B.I.3': 'sp02c_brevetti', 'B.I.4': 'sp02d_concessioni',
                'B.I.5': 'sp02e_avviamento', 'B.I.6': 'sp02f_immob_in_corso',
                'B.I.7': 'sp02g_altre_immob_imm',
                'B.II.1': 'sp03a_terreni_fabbricati',
                'B.II.2': 'sp03b_impianti_macchinari',
                'B.II.3': 'sp03c_attrezzature', 'B.II.4': 'sp03d_altri_beni',
                'B.II.5': 'sp03e_immob_in_corso',
                'B.III.1': 'sp04a_partecipazioni', 'B.III.3': 'sp04d_altri_titoli',
                'B.III.4': 'sp04e_strumenti_derivati_attivi',
                'C.I.1': 'sp05a_materie_prime', 'C.I.2': 'sp05b_prodotti_in_corso',
                'C.I.3': 'sp05c_lavori_in_corso', 'C.I.4': 'sp05d_prodotti_finiti',
                'C.I.5': 'sp05e_acconti',
            }
            if section in direct:
                result.append((direct[section], 'set'))
            if section in detail:
                result.append((detail[section], 'set'))

            maturity = None
            if description.startswith('esigibili entro l esercizio successivo'):
                maturity = 'breve'
            elif description.startswith('esigibili oltre l esercizio successivo'):
                maturity = 'lungo'
            if section.startswith('C.II.') and maturity:
                category = None
                category_fields = {
                    '.1.': ('sp06a_crediti_clienti_breve', 'sp07a_crediti_clienti_lungo'),
                    '.2.': ('sp06b_crediti_controllate_breve', 'sp07b_crediti_controllate_lungo'),
                    '.3.': ('sp06c_crediti_collegate_breve', 'sp07c_crediti_collegate_lungo'),
                    '.4.': ('sp06d_crediti_controllanti_breve', 'sp07d_crediti_controllanti_lungo'),
                    '.5BIS.': ('sp06e_crediti_tributari_breve', 'sp07e_crediti_tributari_lungo'),
                    '.5TER.': ('sp06f_imposte_anticipate_breve', 'sp07f_imposte_anticipate_lungo'),
                    '.5QUATER.': ('sp06g_crediti_altri_breve', 'sp07g_crediti_altri_lungo'),
                }
                for marker, fields in category_fields.items():
                    if marker in section:
                        category = fields[0 if maturity == 'breve' else 1]
                        break
                if category:
                    result.append((category, 'add'))
                    result.append((
                        'sp06_crediti_breve' if maturity == 'breve' else 'sp07_crediti_lungo',
                        'add',
                    ))

        elif statement == 'sp_passivo':
            if section == 'A.I':
                result.append(('sp11_capitale', 'set'))
            reserve_fields = {
                'A.II': 'sp12a_riserva_sovrapprezzo',
                'A.III': 'sp12b_riserve_rivalutazione',
                'A.IV': 'sp12c_riserva_legale',
                'A.V': 'sp12d_riserve_statutarie',
                'A.VI': 'sp12e_altre_riserve',
                'A.VII': 'sp12f_riserva_copertura_flussi',
                'A.VIII': 'sp12g_utili_perdite_portati',
                'A.X': 'sp12h_riserva_neg_azioni_proprie',
            }
            if section in reserve_fields and level == 3:
                result.extend(((reserve_fields[section], 'set'), ('sp12_riserve', 'add')))
            if section == 'A.IX' and level == 3:
                result.append(('sp13_utile_perdita', 'set'))
            if section == 'B' and level == 2:
                result.append(('sp14_fondi_rischi', 'set'))
            fund_fields = {
                'B.1': 'sp14a_fondi_trattamento_quiescenza',
                'B.2': 'sp14b_fondi_imposte',
                'B.3': 'sp14c_strumenti_derivati_passivi',
                'B.4': 'sp14d_altri_fondi',
            }
            if section in fund_fields and level == 3:
                result.append((fund_fields[section], 'set'))
            if section == 'C' and level == 2:
                result.append(('sp15_tfr', 'set'))
            if section == 'E' and level == 2:
                result.append(('sp18_ratei_risconti_passivi', 'set'))

            maturity = None
            if description.startswith('esigibili entro l esercizio successivo'):
                maturity = 'breve'
            elif description.startswith('esigibili oltre l esercizio successivo'):
                maturity = 'lungo'
            debt_match = re.match(r'D\.(\d+)\.(1|2)$', section)
            if debt_match and maturity:
                debt_number = int(debt_match.group(1))
                if debt_number in (1, 2):
                    bucket = 'obbligazioni'
                elif debt_number in (3, 5):
                    bucket = 'altri_finanz'
                elif debt_number == 4:
                    bucket = 'banche'
                elif debt_number == 7:
                    bucket = 'fornitori'
                elif debt_number == 12:
                    bucket = 'tributari'
                elif debt_number == 13:
                    bucket = 'previdenza'
                else:
                    bucket = 'altri'
                typed = {
                    'banche': ('sp16a_debiti_banche_breve', 'sp17a_debiti_banche_lungo'),
                    'altri_finanz': ('sp16b_debiti_altri_finanz_breve', 'sp17b_debiti_altri_finanz_lungo'),
                    'obbligazioni': ('sp16c_debiti_obbligazioni_breve', 'sp17c_debiti_obbligazioni_lungo'),
                    'fornitori': ('sp16d_debiti_fornitori_breve', 'sp17d_debiti_fornitori_lungo'),
                    'tributari': ('sp16e_debiti_tributari_breve', 'sp17e_debiti_tributari_lungo'),
                    'previdenza': ('sp16f_debiti_previdenza_breve', 'sp17f_debiti_previdenza_lungo'),
                    'altri': ('sp16g_altri_debiti_breve', 'sp17g_altri_debiti_lungo'),
                }[bucket][0 if maturity == 'breve' else 1]
                result.extend((
                    (typed, 'add'),
                    ('sp16_debiti_breve' if maturity == 'breve' else 'sp17_debiti_lungo', 'add'),
                ))

        elif statement == 'ce':
            direct = {
                'A.1': 'ce01_ricavi_vendite', 'A.2': 'ce02_variazioni_rimanenze',
                'A.3': 'ce03_lavori_interni', 'A.4': 'ce03a_incrementi_immobilizzazioni',
                'A.5': 'ce04_altri_ricavi', 'B.6': 'ce05_materie_prime',
                'B.7': 'ce06_servizi', 'B.8': 'ce07_godimento_beni',
                'B.9': 'ce08_costi_personale', 'B.10': 'ce09_ammortamenti',
                'B.11': 'ce10_var_rimanenze_mat_prime', 'B.12': 'ce11_accantonamenti',
                'B.13': 'ce11b_altri_accantonamenti', 'B.14': 'ce12_oneri_diversi',
                'C.15': 'ce13_proventi_partecipazioni',
                'C.16': 'ce14_altri_proventi_finanziari',
                'C.17': 'ce15_oneri_finanziari', 'C.17BIS': 'ce16_utili_perdite_cambi',
                'D.18': 'ce17a_rivalutazioni', 'D.19': 'ce17b_svalutazioni',
                'E.20': 'ce20_imposte', '20': 'ce20_imposte',
            }
            if section in direct and level <= 3:
                result.append((direct[section], 'set'))
            ce_details = {
                'B.9.A': 'ce08b_salari_stipendi', 'B.9.B': 'ce08c_oneri_sociali',
                'B.9.C': 'ce08a_tfr_accrual', 'B.9.E': 'ce08d_altri_costi_personale',
                'B.10.A': 'ce09a_ammort_immateriali',
                'B.10.B': 'ce09b_ammort_materiali',
                'B.10.C': 'ce09c_svalutazioni', 'B.10.D': 'ce09d_svalutazione_crediti',
            }
            if section in ce_details and level == 4:
                result.append((ce_details[section], 'set'))

        return result

    def map_row_to_fields(self, row: Dict) -> List[Tuple[str, str]]:
        if row.get('schema') == 'BILAQ':
            return self._map_bilaq_row_to_fields(row)
        tag = re.sub(r'[^A-Z0-9]', '', (row.get('tag') or '').upper())
        field = self.TEBE_TAG_FIELDS.get(tag)
        if tag == 'CE03' and 'variazioni' in self._normalise_header(row.get('description', '')):
            field = 'ce03_lavori_interni'
        if field:
            return [(field, 'set')]
        description = row.get('description', '')
        field = self.map_row_to_field(description, is_balance_sheet=True)
        if field:
            return [(field, 'set')]
        field = self.map_row_to_field(description, is_balance_sheet=False)
        return [(field, 'set')] if field else []

    def extract_years_from_csv(self, rows: List[Dict]) -> Tuple[int, int]:
        """
        Extract year information from CSV

        Args:
            rows: List of CSV row dictionaries

        Returns:
            Tuple of (year1, year2) - most recent first
        """
        # Look for year in column headers or first data row
        # Typically: "Anno Corrente", "Anno Precedente" or actual years

        # Try to find year columns
        for row in rows[:5]:  # Check first 5 rows
            for key, value in row.items():
                if 'anno' in key.lower() or re.match(r'20\d{2}', str(value)):
                    # Found potential year
                    try:
                        year_match = re.search(r'(20\d{2})', str(value))
                        if year_match:
                            year = int(year_match.group(1))
                            # Assume second year is previous
                            return (year, year - 1)
                    except:
                        continue

        # Default: current year and previous
        from datetime import datetime
        current_year = datetime.now().year
        return (current_year, current_year - 1)

    def import_to_database(self,
                          file_path: str,
                          company_id: int,
                          year1: Optional[int] = None,
                          year2: Optional[int] = None) -> Dict[str, any]:
        """
        Import CSV file to database

        Args:
            file_path: Path to CSV file
            company_id: Company ID to import for
            year1: First year (most recent) - auto-detect if None
            year2: Second year (previous) - auto-detect if None

        Returns:
            Dictionary with import results
        """
        bs_type, rows = self.read_csv_file(file_path)
        schema = str(self.csv_metadata.get('schema'))
        detected_years = list(self.csv_metadata.get('detected_years') or [])
        slot_count = max((len(row.get('values', [])) for row in rows), default=0)
        if schema == 'BILAQ':
            years = [year1 or (detected_years[0] if detected_years else datetime.now().year)]
        else:
            fallback1, fallback2 = self.extract_years_from_csv(rows)
            years = []
            for index in range(slot_count):
                detected = detected_years[index] if index < len(detected_years) else None
                override = year1 if index == 0 else year2 if index == 1 else None
                years.append(override or detected or (fallback1 if index == 0 else fallback2))

        if not years:
            raise CSVImportError('Nessun esercizio rilevato nel CSV')

        data_by_year = {
            year: {'bs': {}, 'ce': {}, 'bs_fields': set(), 'ce_fields': set()}
            for year in years
        }
        for row in rows:
            if not row.get('description') or self._normalise_header(row['description']) == 'dati anagrafici':
                continue
            mappings = self.map_row_to_fields(row)
            if not mappings:
                continue
            for index, year in enumerate(years):
                values = row.get('values', [])
                raw_value = values[index] if index < len(values) else '0'
                value = self.parse_monetary_value(raw_value)
                for field, mode in mappings:
                    target_name = 'bs' if field.startswith('sp') else 'ce'
                    target = data_by_year[year][target_name]
                    target[field] = target.get(field, Decimal('0')) + value if mode == 'add' else value
                    data_by_year[year][f'{target_name}_fields'].add(field)

        from importers.iv_cee_hierarchy import check_quadratura
        source_sha256 = hashlib.sha256(Path(file_path).read_bytes()).hexdigest()
        bs_columns = {column.name for column in BalanceSheet.__table__.columns}
        ce_columns = {column.name for column in IncomeStatement.__table__.columns}
        warnings: List[str] = []
        financial_year_ids: List[int] = []
        imported_bs_fields = set()
        imported_ce_fields = set()

        for year in years:
            bs_data = data_by_year[year]['bs']
            ce_data = data_by_year[year]['ce']
            if 'ce17_rettifiche_attivita_fin' not in ce_data and (
                'ce17a_rivalutazioni' in ce_data or 'ce17b_svalutazioni' in ce_data
            ):
                ce_data['ce17_rettifiche_attivita_fin'] = (
                    ce_data.get('ce17a_rivalutazioni', Decimal('0'))
                    - ce_data.get('ce17b_svalutazioni', Decimal('0'))
                )
            q = check_quadratura(bs_data, ce_data)
            warnings.extend(f'[{year}] {warning}' for warning in q.warnings)
            if not q.quadra:
                self.db.rollback()
                raise CSVImportError(
                    f'CSV {schema} {year} non valido: ' + '; '.join(q.warnings)
                )

            fy = self.db.query(FinancialYear).filter(
                FinancialYear.company_id == company_id,
                FinancialYear.year == year,
                (FinancialYear.period_months.is_(None)) | (FinancialYear.period_months == 12),
            ).first()
            if not fy:
                fy = FinancialYear(company_id=company_id, year=year)
                self.db.add(fy)
                self.db.flush()

            semantic_valid = q.semantic_valid
            validation_report = {
                'schema': schema,
                'encoding': self.csv_metadata.get('encoding'),
                'totale_attivo': str(q.totale_attivo),
                'totale_passivo': str(q.totale_passivo),
                'sbilancio': str(q.sbilancio),
                'utile_ce': str(q.utile_ce) if q.utile_ce is not None else None,
                'sp13': str(q.sp13),
                'quadra': q.quadra,
                'utile_match': q.utile_match,
                'hierarchy_consistent': q.hierarchy_consistent,
                'semantic_valid': semantic_valid,
                'warnings': q.warnings,
            }
            fy.validation_status = 'verified' if semantic_valid else 'review_required'
            fy.validation_report = json.dumps(validation_report, ensure_ascii=False)
            fy.source_sha256 = source_sha256
            fy.parser_version = 'csv-header-schema-v2'
            fy.forecastable = semantic_valid

            bs = fy.balance_sheet or BalanceSheet(financial_year_id=fy.id)
            inc = fy.income_statement or IncomeStatement(financial_year_id=fy.id)
            for field, value in bs_data.items():
                if field in bs_columns:
                    setattr(bs, field, value)
            for field, value in ce_data.items():
                if field in ce_columns:
                    setattr(inc, field, value)
            if bs.id is None:
                self.db.add(bs)
            if inc.id is None:
                self.db.add(inc)

            imported_bs_fields.update(data_by_year[year]['bs_fields'])
            imported_ce_fields.update(data_by_year[year]['ce_fields'])
            financial_year_ids.append(fy.id)

        self.db.commit()
        return {
            'success': True,
            'balance_sheet_type': bs_type.value,
            'years': years,
            'rows_processed': len(rows),
            'balance_sheet_fields_imported': len(imported_bs_fields),
            'income_statement_fields_imported': len(imported_ce_fields),
            'financial_year_ids': financial_year_ids,
            'warnings': warnings,
            'csv_schema': schema,
            'encoding': self.csv_metadata.get('encoding'),
        }


def import_csv_file(file_path: str, company_id: int, year1: Optional[int] = None, year2: Optional[int] = None) -> Dict[str, any]:
    """
    Convenience function to import CSV file

    Args:
        file_path: Path to CSV file
        company_id: Company ID
        year1: First year (optional)
        year2: Second year (optional)

    Returns:
        Import results dictionary
    """
    with CSVImporter() as importer:
        return importer.import_to_database(file_path, company_id, year1, year2)
