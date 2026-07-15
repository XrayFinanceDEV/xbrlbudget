"""
Enhanced XBRL Parser with Aggregate Total Reconciliation
Ensures balance sheet always balances by using aggregate totals
"""
from lxml import etree
from decimal import Decimal
from typing import Dict, List, Tuple, Optional
from pathlib import Path
from datetime import datetime
from database.models import BalanceSheet, IncomeStatement, Company, FinancialYear
from database.db import SessionLocal
from config import SUPPORTED_TAXONOMIES, CSV_HTML_ENTITIES_TO_REPLACE
import json
import os
import logging

logger = logging.getLogger(__name__)


class XBRLParseError(Exception):
    """Raised when XBRL parsing fails"""
    pass


class EnhancedXBRLParser:
    """
    Enhanced XBRL Parser with reconciliation logic

    Features:
    - Imports detail items
    - Captures aggregate totals
    - Reconciles differences into fallback fields
    """

    # XBRL namespace
    XBRL_NAMESPACES = {
        'xbrli': 'http://www.xbrl.org/2003/instance',
        'link': 'http://www.xbrl.org/2003/linkbase',
        'xlink': 'http://www.w3.org/1999/xlink',
        'iso4217': 'http://www.xbrl.org/2003/iso4217'
    }

    # Aggregate total tags that we should capture
    AGGREGATE_TAGS = {
        'TotaleAttivo': 'total_assets',
        'TotalePassivo': 'total_passivo',
        'TotaleCrediti': 'total_crediti',
        'TotaleDebiti': 'total_debiti',
        'TotalePatrimonioNetto': 'total_patrimonio',
        'TotaleImmobilizzazioni': 'total_immobilizzazioni',
        'TotaleAttivoCircolante': 'total_attivo_circolante',
    }

    # Per-creditor "Totale*" tags (full-debt total for a group, no entro/oltre split).
    # These are typically present for the COMPARATIVE year in Wolters Kluwer bilanci
    # when the detail entro/oltre tags are not republished. Used as fallback to
    # populate sp16x/sp17x when per-creditor entro/oltre sub-fields are missing.
    # Key = XBRL local name, value = target "creditor bucket" (maps to sp16x/sp17x).
    CREDITOR_TOTAL_TAGS = {
        'DebitiDebitiVersoBancheTotaleDebitiVersoBanche': 'banche',
        'DebitiDebitiVersoAltriFinanziatoriTotaleDebitiVersoAltriFinanziatori': 'altri_finanz',
        'DebitiDebitiVersoSociFinanziamentiTotaleDebitiVersoSociFinanziamenti': 'altri_finanz',
        'DebitiObbligazioniTotaleObbligazioni': 'obbligazioni',
        'DebitiObbligazioniConvertibiliTotaleObbligazioniConvertibili': 'obbligazioni',
        'DebitiDebitiVersoFornitoriTotaleDebitiVersoFornitori': 'fornitori',
        'DebitiDebitiTributariTotaleDebitiTributari': 'tributari',
        'DebitiDebitiVersoIstitutiPrevidenzaSicurezzaSocialeTotaleDebitiVersoIstitutiPrevidenzaSicurezzaSociale': 'previdenza',
        'DebitiAltriDebitiTotaleAltriDebiti': 'altri',
        'DebitiAccontiTotaleAcconti': 'altri',
    }

    # Mapping of creditor bucket -> (sp16x field, sp17x field).
    CREDITOR_FIELDS = {
        'banche': ('sp16a_debiti_banche_breve', 'sp17a_debiti_banche_lungo'),
        'altri_finanz': ('sp16b_debiti_altri_finanz_breve', 'sp17b_debiti_altri_finanz_lungo'),
        'obbligazioni': ('sp16c_debiti_obbligazioni_breve', 'sp17c_debiti_obbligazioni_lungo'),
        'fornitori': ('sp16d_debiti_fornitori_breve', 'sp17d_debiti_fornitori_lungo'),
        'tributari': ('sp16e_debiti_tributari_breve', 'sp17e_debiti_tributari_lungo'),
        'previdenza': ('sp16f_debiti_previdenza_breve', 'sp17f_debiti_previdenza_lungo'),
        'altri': ('sp16g_altri_debiti_breve', 'sp17g_altri_debiti_lungo'),
    }

    # Per-debtor "Totale*" tags for C.II) Crediti (operating receivables, NOT
    # B.III.2 Crediti Immobilizzati which map to sp04*). Same fallback pattern
    # as CREDITOR_TOTAL_TAGS: used when per-type Entro/Oltre tags are missing
    # from the comparative year. Note: tag naming is inconsistent — items whose
    # taxonomy name starts with "Crediti" (e.g. "Crediti tributari") get the
    # doubled prefix `CreditiCrediti*`; items named "Verso X" get `CreditiVerso*`.
    CREDIT_TOTAL_TAGS = {
        'CreditiVersoClientiTotaleCreditiVersoClienti': 'clienti',
        'CreditiVersoImpreseControllateTotaleCreditiVersoImpreseControllate': 'controllate',
        'CreditiVersoImpreseCollegateTotaleCreditiVersoImpreseCollegate': 'collegate',
        'CreditiVersoControllantiTotaleCreditiVersoControllanti': 'controllanti',
        'CreditiCreditiTributariTotaleCreditiTributari': 'tributari',
        'CreditiImposteAnticipateTotaleImposteAnticipate': 'imposte_anticipate',
        'CreditiVersoAltriTotaleCreditiVersoAltri': 'altri',
    }

    # Mapping of debtor bucket -> (sp06x field, sp07x field).
    CREDIT_FIELDS = {
        'clienti': ('sp06a_crediti_clienti_breve', 'sp07a_crediti_clienti_lungo'),
        'controllate': ('sp06b_crediti_controllate_breve', 'sp07b_crediti_controllate_lungo'),
        'collegate': ('sp06c_crediti_collegate_breve', 'sp07c_crediti_collegate_lungo'),
        'controllanti': ('sp06d_crediti_controllanti_breve', 'sp07d_crediti_controllanti_lungo'),
        'tributari': ('sp06e_crediti_tributari_breve', 'sp07e_crediti_tributari_lungo'),
        'imposte_anticipate': ('sp06f_imposte_anticipate_breve', 'sp07f_imposte_anticipate_lungo'),
        'altri': ('sp06g_crediti_altri_breve', 'sp07g_crediti_altri_lungo'),
    }

    def __init__(self, db_session=None):
        """Initialize enhanced parser"""
        self.db = db_session or SessionLocal()
        self._own_session = db_session is None
        self._load_taxonomy_mapping()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._own_session:
            self.db.close()

    def _load_taxonomy_mapping(self):
        """Load taxonomy mapping from JSON files (v1 and v2)"""
        # Load v1 mapping (backward compatibility)
        mapping_path_v1 = os.path.join(os.path.dirname(__file__), '..', 'data', 'taxonomy_mapping.json')
        with open(mapping_path_v1, 'r', encoding='utf-8') as f:
            taxonomy_v1 = json.load(f)
            self.bs_mapping_v1 = taxonomy_v1['balance_sheet_mapping']
            self.inc_mapping_v1 = taxonomy_v1['income_statement_mapping']

        # Load v2 mapping (priority-based)
        mapping_path_v2 = os.path.join(os.path.dirname(__file__), '..', 'data', 'taxonomy_mapping_v2.json')
        try:
            with open(mapping_path_v2, 'r', encoding='utf-8') as f:
                taxonomy_v2 = json.load(f)
                self.bs_mapping_v2 = taxonomy_v2.get('balance_sheet_mapping_v2', {})
                self.inc_mapping_v2 = taxonomy_v2.get('income_statement_mapping_v2', {})
                self.aggregate_tags_reconciliation = taxonomy_v2.get('aggregate_tags_for_reconciliation', {})
        except FileNotFoundError:
            # Fallback to v1 only if v2 doesn't exist
            self.bs_mapping_v2 = {}
            self.inc_mapping_v2 = {}
            self.aggregate_tags_reconciliation = {}

    def clean_xbrl_text(self, text: str) -> str:
        """Clean special characters from XBRL text"""
        if not text:
            return text

        cleaned = text
        for entity, replacement in CSV_HTML_ENTITIES_TO_REPLACE.items():
            cleaned = cleaned.replace(entity, replacement)

        return cleaned.strip()

    # HTML entities not defined in XML that may appear in XBRL files
    # (e.g. in Nota Integrativa sections embedded as HTML-encoded text)
    HTML_ENTITIES_REPLACE = {
        '&rsquo;': '&#x2019;',
        '&lsquo;': '&#x2018;',
        '&rdquo;': '&#x201D;',
        '&ldquo;': '&#x201C;',
        '&nbsp;': '&#xA0;',
        '&hellip;': '&#x2026;',
        '&euro;': '&#x20AC;',
        '&mdash;': '&#x2014;',
        '&ndash;': '&#x2013;',
        '&bull;': '&#x2022;',
        '&copy;': '&#xA9;',
        '&reg;': '&#xAE;',
        '&trade;': '&#x2122;',
        '&agrave;': '&#xE0;',
        '&egrave;': '&#xE8;',
        '&igrave;': '&#xEC;',
        '&ograve;': '&#xF2;',
        '&ugrave;': '&#xF9;',
        '&eacute;': '&#xE9;',
    }

    def parse_file(self, file_path: str) -> etree._Element:
        """Parse XBRL file and return root element"""
        if not Path(file_path).exists():
            raise XBRLParseError(f"File not found: {file_path}")

        try:
            parser = etree.XMLParser(remove_blank_text=True, encoding='utf-8')
            tree = etree.parse(file_path, parser)
            root = tree.getroot()
            return root
        except etree.XMLSyntaxError:
            # Retry: read raw content, fix encoding and replace HTML entities
            try:
                raw = Path(file_path).read_bytes()
                text = raw.decode('utf-8', errors='replace')
                # Replace HTML entities not valid in XML with numeric equivalents
                for entity, replacement in self.HTML_ENTITIES_REPLACE.items():
                    text = text.replace(entity, replacement)
                parser = etree.XMLParser(remove_blank_text=True, recover=True)
                root = etree.fromstring(text.encode('utf-8'), parser)
                return root
            except Exception as e2:
                raise XBRLParseError(f"Invalid XML syntax: {e2}")
        except Exception as e:
            raise XBRLParseError(f"Error parsing XBRL file: {e}")

    def extract_taxonomy_version(self, root: etree._Element) -> str:
        """Extract taxonomy version from XBRL file"""
        schema_ref = root.find('.//link:schemaRef', namespaces=self.XBRL_NAMESPACES)

        if schema_ref is not None:
            href = schema_ref.get('{http://www.w3.org/1999/xlink}href', '')
            for taxonomy in SUPPORTED_TAXONOMIES:
                if taxonomy in href:
                    return taxonomy

        for prefix, uri in root.nsmap.items():
            if 'itcc-ci' in str(uri):
                for taxonomy in SUPPORTED_TAXONOMIES:
                    if taxonomy in str(uri):
                        return taxonomy

        return SUPPORTED_TAXONOMIES[0]

    def extract_contexts(self, root: etree._Element) -> Dict[str, Dict]:
        """Extract context information (periods) from XBRL"""
        contexts = {}

        context_elements = root.findall('.//xbrli:context', namespaces=self.XBRL_NAMESPACES)

        for ctx in context_elements:
            ctx_id = ctx.get('id')
            if not ctx_id:
                continue

            period = ctx.find('.//xbrli:period', namespaces=self.XBRL_NAMESPACES)

            if period is not None:
                period_months = None
                instant = period.find('.//xbrli:instant', namespaces=self.XBRL_NAMESPACES)
                if instant is not None:
                    date_str = instant.text
                    try:
                        date = datetime.strptime(date_str, '%Y-%m-%d')
                        year = date.year
                    except:
                        year = None
                else:
                    start_date_el = period.find('.//xbrli:startDate', namespaces=self.XBRL_NAMESPACES)
                    end_date = period.find('.//xbrli:endDate', namespaces=self.XBRL_NAMESPACES)
                    if end_date is not None:
                        date_str = end_date.text
                        try:
                            date = datetime.strptime(date_str, '%Y-%m-%d')
                            year = date.year
                            # Detect period_months from startDate..endDate
                            if start_date_el is not None:
                                start = datetime.strptime(start_date_el.text, '%Y-%m-%d')
                                # Calculate months: Jan 1 to Jun 30 = 6 months, Jan 1 to Dec 31 = 12
                                months = (date.year - start.year) * 12 + (date.month - start.month + 1)
                                if months >= 1 and months <= 11:
                                    period_months = months
                        except:
                            year = None
                    else:
                        year = None

                contexts[ctx_id] = {
                    'id': ctx_id,
                    'year': year,
                    'date': date_str if 'date_str' in locals() else None,
                    'period_months': period_months,
                }

        return contexts

    def extract_entity_info(self, root: etree._Element) -> Dict[str, str]:
        """Extract entity (company) information from XBRL"""
        entity_info = {}
        partita_iva = None
        codice_fiscale = None

        context = root.find('.//xbrli:context', namespaces=self.XBRL_NAMESPACES)

        if context is not None:
            entity = context.find('.//xbrli:entity', namespaces=self.XBRL_NAMESPACES)

            if entity is not None:
                # Use entity identifier as fallback tax_id
                identifier = entity.find('.//xbrli:identifier', namespaces=self.XBRL_NAMESPACES)
                if identifier is not None:
                    entity_info['tax_id'] = identifier.text

                for elem in root.iter():
                    try:
                        local_name = etree.QName(elem).localname if hasattr(elem, 'tag') else ''
                    except:
                        local_name = str(elem.tag) if elem.tag else ''

                    tag_lower = local_name.lower()

                    if not entity_info.get('name') and ('denominazione' in tag_lower or 'ragionesociale' in tag_lower or 'name' in tag_lower):
                        if elem.text:
                            entity_info['name'] = self.clean_xbrl_text(elem.text)

                    # Extract P.IVA and CF from DatiAnagrafici section
                    if local_name == 'DatiAnagraficiPartitaIva' and elem.text and elem.text.strip():
                        partita_iva = elem.text.strip()
                    elif local_name == 'DatiAnagraficiCodiceFiscale' and elem.text and elem.text.strip():
                        codice_fiscale = elem.text.strip()

        # Prefer CF > P.IVA > entity identifier as tax_id
        # CF is the permanent unique identifier; P.IVA can change (mergers etc.)
        # Entity identifier can be a software vendor code (e.g. Wolters Kluwer COMPCODE)
        if codice_fiscale:
            entity_info['tax_id'] = codice_fiscale
        elif partita_iva:
            entity_info['tax_id'] = partita_iva

        return entity_info

    def extract_facts(self, root: etree._Element, contexts: Dict[str, Dict]) -> Dict[int, Dict[str, Decimal]]:
        """Extract financial facts from XBRL"""
        facts_by_year = {}

        for elem in root.iter():
            context_ref = elem.get('contextRef')
            if not context_ref or context_ref not in contexts:
                continue

            year = contexts[context_ref]['year']
            if not year:
                continue

            if year not in facts_by_year:
                facts_by_year[year] = {}

            tag = etree.QName(elem).localname
            full_tag = elem.tag

            value_text = elem.text
            if value_text:
                try:
                    cleaned = self.clean_xbrl_text(value_text)
                    value = Decimal(cleaned.replace(',', '.'))
                    facts_by_year[year][full_tag] = value
                except:
                    continue

        return facts_by_year

    def _extract_value_by_priority(
        self,
        facts: Dict[str, Decimal],
        field_config: Dict[str, str]
    ) -> Tuple[Optional[Decimal], Optional[str]]:
        """
        Extract value using priority-based matching

        Args:
            facts: Dictionary of XBRL tag -> value
            field_config: Configuration with priority_1, priority_2, etc.

        Returns:
            Tuple of (value, matched_tag) or (None, None) if not found
        """
        # Special handling for accumulate_all fields (like reserves)
        # Try detail_tags FIRST if accumulate_all is set
        if field_config.get('accumulate_all', False) and 'detail_tags' in field_config:
            accumulated = Decimal('0')
            found_any = False
            matched_tags = []

            for detail_tag in field_config['detail_tags']:
                expected_local = detail_tag.split(':')[-1]

                for fact_tag, value in facts.items():
                    local_name = etree.QName(fact_tag).localname if fact_tag.startswith('{') else fact_tag.split(':')[-1]

                    if local_name == expected_local:
                        accumulated += value
                        found_any = True
                        matched_tags.append(expected_local)

            if found_any:
                return accumulated, f'detail_tags_accumulated ({len(matched_tags)} items)'

        # Try priorities in order (for non-accumulate_all or if detail_tags didn't match)
        for priority_key in ['priority_1', 'priority_2', 'priority_3', 'priority_4', 'priority_5']:
            if priority_key not in field_config:
                continue

            xbrl_tag = field_config[priority_key]
            expected_local = xbrl_tag.split(':')[-1]

            # Try to find matching tag in facts
            for fact_tag, value in facts.items():
                local_name = etree.QName(fact_tag).localname if fact_tag.startswith('{') else fact_tag.split(':')[-1]

                # Exact match
                if local_name == expected_local:
                    return value, xbrl_tag

                # Match with "Totale" prefix (e.g., TotaleImmobilizzazioniImmateriali == Totale + ImmobilizzazioniImmateriali)
                if local_name == 'Totale' + expected_local:
                    return value, xbrl_tag

        # Fuzzy fallback: match minor spelling variations (e.g., Incremento vs Incrementi)
        # Only when lengths are within 10% of each other (prevents short-substring-of-long matches)
        for priority_key in ['priority_1', 'priority_2', 'priority_3', 'priority_4', 'priority_5']:
            if priority_key not in field_config:
                continue

            xbrl_tag = field_config[priority_key]
            expected_local = xbrl_tag.split(':')[-1]

            for fact_tag, value in facts.items():
                local_name = etree.QName(fact_tag).localname if fact_tag.startswith('{') else fact_tag.split(':')[-1]

                # Only consider near-equal length strings (within 10%)
                len_ratio = len(local_name) / max(len(expected_local), 1)
                if len(expected_local) > 15 and 0.9 <= len_ratio <= 1.1:
                    if local_name.lower() == expected_local.lower():
                        logger.info(f"[XBRL] Fuzzy case match: {local_name} ~ {xbrl_tag}")
                        return value, xbrl_tag
                    # Check if only 1-2 chars differ (e.g., Incremento vs Incrementi)
                    if expected_local in local_name or local_name in expected_local:
                        logger.info(f"[XBRL] Fuzzy near-match: {local_name} ~ {xbrl_tag}")
                        return value, xbrl_tag

        # Try detail_tags if present and not already tried (for non-accumulate_all)
        if not field_config.get('accumulate_all', False) and 'detail_tags' in field_config:
            accumulated = Decimal('0')
            found_any = False

            for detail_tag in field_config['detail_tags']:
                expected_local = detail_tag.split(':')[-1]

                for fact_tag, value in facts.items():
                    local_name = etree.QName(fact_tag).localname if fact_tag.startswith('{') else fact_tag.split(':')[-1]

                    if local_name == expected_local:
                        accumulated += value
                        found_any = True

            if found_any:
                return accumulated, 'detail_tags_accumulated'

        return None, None

    def map_facts_to_fields_with_reconciliation(
        self,
        facts: Dict[str, Decimal]
    ) -> Tuple[Dict[str, Decimal], Dict[str, Decimal], Dict[str, any]]:
        """
        Map XBRL facts to database fields WITH priority-based matching and reconciliation

        Returns:
            Tuple of (balance_sheet_data, income_statement_data, reconciliation_info)
        """
        bs_data = {}
        inc_data = {}
        aggregates = {}
        # Per-creditor full-debt totals (bucket -> amount). Populated from
        # "DebitiDebitiVersoXTotaleDebitiVersoX" tags when present; used as
        # fallback for prior years that only publish totals without entro/oltre.
        creditor_totals: Dict[str, Decimal] = {}
        # Per-debtor full-credit totals (bucket -> amount). Same fallback role
        # for C.II Crediti when comparative year only publishes group totals.
        credit_totals: Dict[str, Decimal] = {}
        reconciliation_info = {
            'unmapped_tags': [],
            'aggregate_totals': {},
            'reconciliation_adjustments': {},
            'priority_matches': {}
        }

        # First pass: Extract aggregate totals for reconciliation
        for tag, value in facts.items():
            local_name = etree.QName(tag).localname if tag.startswith('{') else tag.split(':')[-1]

            if local_name in self.AGGREGATE_TAGS:
                aggregate_key = self.AGGREGATE_TAGS[local_name]
                aggregates[aggregate_key] = value
                reconciliation_info['aggregate_totals'][local_name] = float(value)

            # Collect per-creditor full-debt totals (fallback for years w/o entro/oltre detail)
            if local_name in self.CREDITOR_TOTAL_TAGS:
                bucket = self.CREDITOR_TOTAL_TAGS[local_name]
                creditor_totals[bucket] = creditor_totals.get(bucket, Decimal('0')) + value

            # Collect per-debtor full-credit totals (same fallback role for C.II Crediti)
            if local_name in self.CREDIT_TOTAL_TAGS:
                bucket = self.CREDIT_TOTAL_TAGS[local_name]
                credit_totals[bucket] = credit_totals.get(bucket, Decimal('0')) + value

            # Also check v2 reconciliation aggregates
            if hasattr(self, 'aggregate_tags_reconciliation'):
                bs_agg = self.aggregate_tags_reconciliation.get('balance_sheet', {})
                inc_agg = self.aggregate_tags_reconciliation.get('income_statement', {})

                if local_name in bs_agg:
                    aggregate_key = bs_agg[local_name]
                    aggregates[aggregate_key] = value
                    reconciliation_info['aggregate_totals'][local_name] = float(value)

                if local_name in inc_agg:
                    aggregate_key = inc_agg[local_name]
                    aggregates[aggregate_key] = value
                    reconciliation_info['aggregate_totals'][local_name] = float(value)

        # Second pass: Use priority-based mapping (v2)
        v2_mapped_fields_bs = set()
        v2_mapped_fields_inc = set()

        if self.bs_mapping_v2:
            # Map balance sheet fields using priority system
            for field, field_config in self.bs_mapping_v2.items():
                if isinstance(field_config, dict):
                    value, matched_tag = self._extract_value_by_priority(facts, field_config)
                    if value is not None:
                        bs_data[field] = bs_data.get(field, Decimal('0')) + value
                        reconciliation_info['priority_matches'][field] = matched_tag
                        v2_mapped_fields_bs.add(field)  # Track successfully mapped fields

        if self.inc_mapping_v2:
            # Map income statement fields using priority system
            for field, field_config in self.inc_mapping_v2.items():
                if isinstance(field_config, dict):
                    value, matched_tag = self._extract_value_by_priority(facts, field_config)
                    if value is not None:
                        inc_data[field] = inc_data.get(field, Decimal('0')) + value
                        reconciliation_info['priority_matches'][field] = matched_tag
                        v2_mapped_fields_inc.add(field)  # Track successfully mapped fields

        # Fallback to v1 mapping for any unmatched fields
        matched_tags = set()
        for tag, value in facts.items():
            local_name = etree.QName(tag).localname if tag.startswith('{') else tag.split(':')[-1]

            # Skip aggregate totals in detail mapping
            if local_name in self.AGGREGATE_TAGS:
                continue

            # Skip if already matched via v2 (exact local name match, not substring)
            already_matched = False
            for matched_tag in reconciliation_info.get('priority_matches', {}).values():
                if matched_tag:
                    matched_local = matched_tag.split(':')[-1] if ':' in matched_tag else matched_tag
                    if local_name == matched_local:
                        already_matched = True
                        break

            if already_matched:
                continue

            matched = False

            # Try balance sheet mapping (v1)
            for xbrl_tag, field in self.bs_mapping_v1.items():
                expected_local = xbrl_tag.split(':')[-1]

                if local_name == expected_local:
                    # Skip if this field was already successfully mapped by v2
                    if field in v2_mapped_fields_bs:
                        matched = True  # Mark as matched to avoid "unmapped" warning
                        break

                    # Detail fields accumulate (multiple XBRL categories may map to same field,
                    # e.g. AltriDebiti + Acconti both → sp16g/sp17g)
                    ACCUMULATE_FIELDS = {
                        'sp06a_crediti_clienti_breve', 'sp06b_crediti_controllate_breve',
                        'sp06c_crediti_collegate_breve', 'sp06d_crediti_controllanti_breve',
                        'sp06e_crediti_tributari_breve', 'sp06f_imposte_anticipate_breve',
                        'sp06g_crediti_altri_breve',
                        'sp07a_crediti_clienti_lungo', 'sp07b_crediti_controllate_lungo',
                        'sp07c_crediti_collegate_lungo', 'sp07d_crediti_controllanti_lungo',
                        'sp07e_crediti_tributari_lungo', 'sp07f_imposte_anticipate_lungo',
                        'sp07g_crediti_altri_lungo',
                        'sp16a_debiti_banche_breve', 'sp16b_debiti_altri_finanz_breve',
                        'sp16c_debiti_obbligazioni_breve', 'sp16d_debiti_fornitori_breve',
                        'sp16e_debiti_tributari_breve', 'sp16f_debiti_previdenza_breve',
                        'sp16g_altri_debiti_breve',
                        'sp17a_debiti_banche_lungo', 'sp17b_debiti_altri_finanz_lungo',
                        'sp17c_debiti_obbligazioni_lungo', 'sp17d_debiti_fornitori_lungo',
                        'sp17e_debiti_tributari_lungo', 'sp17f_debiti_previdenza_lungo',
                        'sp17g_altri_debiti_lungo',
                    }
                    if field in ACCUMULATE_FIELDS:
                        bs_data[field] = bs_data.get(field, Decimal('0')) + value
                    elif field not in bs_data or bs_data[field] == Decimal('0'):
                        bs_data[field] = bs_data.get(field, Decimal('0')) + value
                    matched = True
                    matched_tags.add(local_name)
                    break

                if local_name.startswith('Totale') and expected_local in local_name:
                    # Skip if this field was already successfully mapped by v2
                    if field in v2_mapped_fields_bs:
                        matched = True
                        break

                    if field not in bs_data or bs_data[field] == Decimal('0'):
                        bs_data[field] = bs_data.get(field, Decimal('0')) + value
                    matched = True
                    matched_tags.add(local_name)
                    break

            # Try income statement if not matched (v1)
            if not matched:
                for xbrl_tag, field in self.inc_mapping_v1.items():
                    expected_local = xbrl_tag.split(':')[-1]

                    if local_name == expected_local:
                        # Skip if this field was already successfully mapped by v2
                        if field in v2_mapped_fields_inc:
                            matched = True
                            break

                        if field not in inc_data or inc_data[field] == Decimal('0'):
                            inc_data[field] = inc_data.get(field, Decimal('0')) + value
                        matched = True
                        matched_tags.add(local_name)
                        break

                    if local_name.startswith('Totale') and expected_local in local_name:
                        # Skip if this field was already successfully mapped by v2
                        if field in v2_mapped_fields_inc:
                            matched = True
                            break

                        if field not in inc_data or inc_data[field] == Decimal('0'):
                            inc_data[field] = inc_data.get(field, Decimal('0')) + value
                        matched = True
                        matched_tags.add(local_name)
                        break

            if not matched and value != 0:
                reconciliation_info['unmapped_tags'].append({
                    'tag': local_name,
                    'value': float(value)
                })

        # Third pass: Sum detail fields into aggregates when aggregate is missing
        # Many XBRL files provide only detail-level Entro/Oltre tags (e.g.
        # DebitiDebitiVersoBancheEsigibiliEntroEsercizioSuccessivo) without the
        # aggregate tags (e.g. DebitiEsigibiliEntroEsercizioSuccessivo).
        # Without this step, sp06/sp07/sp16/sp17 stay at 0 and reconciliation
        # incorrectly dumps the grand total into the short-term aggregate.
        DETAIL_TO_AGGREGATE = {
            'sp06_crediti_breve': [
                'sp06a_crediti_clienti_breve', 'sp06b_crediti_controllate_breve',
                'sp06c_crediti_collegate_breve', 'sp06d_crediti_controllanti_breve',
                'sp06e_crediti_tributari_breve', 'sp06f_imposte_anticipate_breve',
                'sp06g_crediti_altri_breve',
            ],
            'sp07_crediti_lungo': [
                'sp07a_crediti_clienti_lungo', 'sp07b_crediti_controllate_lungo',
                'sp07c_crediti_collegate_lungo', 'sp07d_crediti_controllanti_lungo',
                'sp07e_crediti_tributari_lungo', 'sp07f_imposte_anticipate_lungo',
                'sp07g_crediti_altri_lungo',
            ],
            'sp16_debiti_breve': [
                'sp16a_debiti_banche_breve', 'sp16b_debiti_altri_finanz_breve',
                'sp16c_debiti_obbligazioni_breve', 'sp16d_debiti_fornitori_breve',
                'sp16e_debiti_tributari_breve', 'sp16f_debiti_previdenza_breve',
                'sp16g_altri_debiti_breve',
            ],
            'sp17_debiti_lungo': [
                'sp17a_debiti_banche_lungo', 'sp17b_debiti_altri_finanz_lungo',
                'sp17c_debiti_obbligazioni_lungo', 'sp17d_debiti_fornitori_lungo',
                'sp17e_debiti_tributari_lungo', 'sp17f_debiti_previdenza_lungo',
                'sp17g_altri_debiti_lungo',
            ],
        }
        for agg_field, detail_fields in DETAIL_TO_AGGREGATE.items():
            if bs_data.get(agg_field, Decimal('0')) == Decimal('0'):
                detail_sum = sum(bs_data.get(f, Decimal('0')) for f in detail_fields)
                if detail_sum != Decimal('0'):
                    bs_data[agg_field] = detail_sum

        # 3b: Fill per-creditor debt breakdown from "Totale*" fallback tags.
        # Runs when the per-creditor Entro/Oltre tags are missing from the XBRL
        # (typical for COMPARATIVE years in Wolters Kluwer bilanci — the full
        # detail only gets republished for the current year). Uses the
        # "DebitiDebitiVerso*Totale*" tags collected in the first pass to seed
        # sp16x_breve, then redistributes the overall sp17 aggregate into sp17x
        # (banche priority by default — Italian SMEs usually hold mutuos there).
        sp16_agg = bs_data.get('sp16_debiti_breve', Decimal('0'))
        sp17_agg = bs_data.get('sp17_debiti_lungo', Decimal('0'))
        entro_detail_sum = sum(bs_data.get(f, Decimal('0'))
                               for (f, _) in self.CREDITOR_FIELDS.values())
        oltre_detail_sum = sum(bs_data.get(f, Decimal('0'))
                               for (_, f) in self.CREDITOR_FIELDS.values())

        if creditor_totals and entro_detail_sum == Decimal('0') and oltre_detail_sum == Decimal('0') \
                and (sp16_agg + sp17_agg) > Decimal('0'):
            # Seed sp16x with each creditor's total (treat as short-term initially).
            for bucket, total in creditor_totals.items():
                if total == Decimal('0'):
                    continue
                breve_field, _ = self.CREDITOR_FIELDS[bucket]
                bs_data[breve_field] = bs_data.get(breve_field, Decimal('0')) + total

            # Move the overall oltre aggregate into sp17a (banche lungo) by default,
            # spilling to other groups in priority order if banche has less than sp17.
            priority = ['banche', 'altri_finanz', 'obbligazioni', 'fornitori', 'altri', 'tributari', 'previdenza']
            remaining_oltre = sp17_agg
            for bucket in priority:
                if remaining_oltre <= Decimal('0'):
                    break
                breve_field, lungo_field = self.CREDITOR_FIELDS[bucket]
                available = bs_data.get(breve_field, Decimal('0'))
                if available <= Decimal('0'):
                    continue
                move = min(available, remaining_oltre)
                bs_data[breve_field] = available - move
                bs_data[lungo_field] = bs_data.get(lungo_field, Decimal('0')) + move
                remaining_oltre -= move

            reconciliation_info['reconciliation_adjustments']['debt_creditor_fallback'] = {
                'source': 'per-creditor Totale* tags (no entro/oltre detail in XBRL)',
                'sp17_distributed': float(sp17_agg - remaining_oltre),
                'sp17_unallocated': float(remaining_oltre),
            }

        # 3c: Same fallback for C.II Crediti — seed sp06x_breve from per-debtor
        # Totale tags, then redistribute the overall sp07 aggregate into sp07x
        # (clienti priority by default, since long-term receivables most often
        # sit under Verso clienti).
        sp06_agg = bs_data.get('sp06_crediti_breve', Decimal('0'))
        sp07_agg = bs_data.get('sp07_crediti_lungo', Decimal('0'))
        cr_entro_detail_sum = sum(bs_data.get(f, Decimal('0'))
                                  for (f, _) in self.CREDIT_FIELDS.values())
        cr_oltre_detail_sum = sum(bs_data.get(f, Decimal('0'))
                                  for (_, f) in self.CREDIT_FIELDS.values())

        if credit_totals and cr_entro_detail_sum == Decimal('0') and cr_oltre_detail_sum == Decimal('0') \
                and (sp06_agg + sp07_agg) > Decimal('0'):
            # Seed sp06x with each debtor's total (treat as short-term initially).
            for bucket, total in credit_totals.items():
                if total == Decimal('0'):
                    continue
                breve_field, _ = self.CREDIT_FIELDS[bucket]
                bs_data[breve_field] = bs_data.get(breve_field, Decimal('0')) + total

            # Move the overall oltre aggregate into sp07a (clienti lungo) by default,
            # spilling to other groups in priority order when clienti total is smaller.
            priority = ['clienti', 'altri', 'tributari', 'imposte_anticipate',
                        'controllate', 'collegate', 'controllanti']
            remaining_oltre = sp07_agg
            for bucket in priority:
                if remaining_oltre <= Decimal('0'):
                    break
                breve_field, lungo_field = self.CREDIT_FIELDS[bucket]
                available = bs_data.get(breve_field, Decimal('0'))
                if available <= Decimal('0'):
                    continue
                move = min(available, remaining_oltre)
                bs_data[breve_field] = available - move
                bs_data[lungo_field] = bs_data.get(lungo_field, Decimal('0')) + move
                remaining_oltre -= move

            reconciliation_info['reconciliation_adjustments']['credit_debtor_fallback'] = {
                'source': 'per-debtor Totale* tags (no entro/oltre detail in XBRL)',
                'sp07_distributed': float(sp07_agg - remaining_oltre),
                'sp07_unallocated': float(remaining_oltre),
            }

        # Fourth pass: Reconciliation
        # Reconcile credits if we have TotaleCrediti
        if 'total_crediti' in aggregates:
            total_crediti_xbrl = aggregates['total_crediti']

            # Sum all credit fields we imported
            imported_crediti = (
                bs_data.get('sp06_crediti_breve', Decimal('0')) +
                bs_data.get('sp07_crediti_lungo', Decimal('0'))
            )

            diff_crediti = total_crediti_xbrl - imported_crediti

            if abs(diff_crediti) > Decimal('0.01'):
                # Add difference to short-term credits (catch-all)
                bs_data['sp06_crediti_breve'] = bs_data.get('sp06_crediti_breve', Decimal('0')) + diff_crediti
                reconciliation_info['reconciliation_adjustments']['crediti'] = {
                    'xbrl_total': float(total_crediti_xbrl),
                    'imported_sum': float(imported_crediti),
                    'adjustment': float(diff_crediti),
                    'applied_to': 'sp06_crediti_breve'
                }

        # Reconcile debts if we have TotaleDebiti
        if 'total_debiti' in aggregates:
            total_debiti_xbrl = aggregates['total_debiti']

            imported_debiti = (
                bs_data.get('sp16_debiti_breve', Decimal('0')) +
                bs_data.get('sp17_debiti_lungo', Decimal('0'))
            )

            diff_debiti = total_debiti_xbrl - imported_debiti

            if abs(diff_debiti) > Decimal('0.01'):
                bs_data['sp16_debiti_breve'] = bs_data.get('sp16_debiti_breve', Decimal('0')) + diff_debiti
                reconciliation_info['reconciliation_adjustments']['debiti'] = {
                    'xbrl_total': float(total_debiti_xbrl),
                    'imported_sum': float(imported_debiti),
                    'adjustment': float(diff_debiti),
                    'applied_to': 'sp16_debiti_breve'
                }

        return bs_data, inc_data, reconciliation_info

    def import_to_database(
        self,
        file_path: str,
        company_id: Optional[int] = None,
        create_company: bool = True,
        sector: Optional[int] = None,
        user_id: Optional[str] = None,
        period_months: Optional[int] = None,
    ) -> Dict[str, any]:
        """Import XBRL file to database with reconciliation"""

        root = self.parse_file(file_path)
        taxonomy_version = self.extract_taxonomy_version(root)
        contexts = self.extract_contexts(root)

        if not contexts:
            raise XBRLParseError("No contexts found in XBRL file")

        entity_info = self.extract_entity_info(root)

        # Get or create company
        company_created = False
        if company_id is None:
            if create_company:
                tax_id = entity_info.get('tax_id')
                existing_company = None

                if tax_id:
                    query = self.db.query(Company).filter(Company.tax_id == tax_id)
                    if user_id:
                        query = query.filter(Company.user_id == user_id)
                    existing_company = query.first()

                if existing_company:
                    company = existing_company
                    company_id = company.id
                else:
                    company = Company(
                        name=entity_info.get('name', 'Imported Company'),
                        tax_id=tax_id,
                        sector=sector or 1,
                        user_id=user_id,
                    )
                    self.db.add(company)
                    self.db.commit()
                    self.db.refresh(company)
                    company_id = company.id
                    company_created = True
            else:
                raise XBRLParseError("No company_id provided and create_company=False")
        else:
            company = self.db.query(Company).filter(Company.id == company_id).first()
            if not company:
                raise XBRLParseError(f"Company with ID {company_id} not found")
            if user_id and company.user_id != user_id:
                raise XBRLParseError(f"Company with ID {company_id} not found")

        facts_by_year = self.extract_facts(root, contexts)

        if not facts_by_year:
            raise XBRLParseError("No financial facts found in XBRL file")

        # Detect period_months per year from duration contexts
        year_period_months = {}
        for ctx in contexts.values():
            yr = ctx.get('year')
            pm = ctx.get('period_months')
            if yr and pm:
                # Keep the period_months (partial year detected)
                year_period_months[yr] = pm

        logger.info(f"[XBRL] Auto-detected period_months: {year_period_months}")

        years = sorted(facts_by_year.keys(), reverse=True)
        imported_years = []
        financial_year_ids = []
        all_reconciliation_info = {}
        quadratura_warnings = []  # user-visible, non-blocking (per-year, "[year] msg")

        # Apply user-specified period_months to the most recent year if not auto-detected
        if period_months and period_months < 12:
            most_recent = years[0]
            if most_recent not in year_period_months:
                year_period_months[most_recent] = period_months
                logger.info(f"[XBRL] User override: year {most_recent} → period_months={period_months}")

        for year in years:
            detected_pm = year_period_months.get(year)  # None = full year, 1-11 = partial

            if detected_pm:
                # Partial year: match existing partial record or create new one.
                # period_months == 12 is a FULL year by convention (see CLAUDE.md
                # "NULL or 12") — exclude it, or an incoming partial import would
                # overwrite a historical full-year record saved with 12.
                fy = self.db.query(FinancialYear).filter(
                    FinancialYear.company_id == company_id,
                    FinancialYear.year == year,
                    FinancialYear.period_months.isnot(None),
                    FinancialYear.period_months != 12,
                ).first()

                if not fy:
                    fy = FinancialYear(company_id=company_id, year=year, period_months=detected_pm)
                    self.db.add(fy)
                    self.db.flush()
                else:
                    fy.period_months = detected_pm
            else:
                # Full year: match existing full-year record
                fy = self.db.query(FinancialYear).filter(
                    FinancialYear.company_id == company_id,
                    FinancialYear.year == year,
                    FinancialYear.period_months.is_(None),
                ).first()

                if not fy:
                    fy = FinancialYear(company_id=company_id, year=year)
                    self.db.add(fy)
                    self.db.flush()

            # Map facts with reconciliation
            bs_data, inc_data, reconciliation_info = self.map_facts_to_fields_with_reconciliation(
                facts_by_year[year]
            )

            # GENERAL rule (same as the PDF routes): enforce the CE↔SP identity
            # utile_CE == sp13 so the app's "Verifica CE ↔ SP" passes on XBRL imports too.
            # sp13 comes from a dedicated XBRL tag (authoritative), so prefer="sp13" and align
            # the CE to it (plug a CE line). No-op when already consistent.
            try:
                from importers.iv_cee_hierarchy import enforce_ce_sp_identity
                inc_data = enforce_ce_sp_identity(bs_data, inc_data, f"xbrl-{year}", prefer="sp13")
            except Exception as _ce_sp_err:
                logger.warning(f"[XBRL] CE↔SP enforcement skipped for year {year}: {_ce_sp_err}")

            # GENERAL: check the balance-sheet identity too (attivo == passivo). Unlike
            # the PDF routes, XBRL has no validate_balance gate nor a reconcile/plug
            # stage, so an unbalanced instance (or one unbalanced by the debt/credit
            # reconciliation above, which adjusts sp06/sp16 to the declared totals) was
            # imported SILENTLY. Non-blocking by design (a tagged official filing should
            # still open, and the user corrects in Rettifiche) — but it must be flagged.
            try:
                from importers.iv_cee_hierarchy import check_quadratura
                _q = check_quadratura(bs_data, inc_data)
                if not _q.quadra or not _q.utile_match:
                    for _w in _q.warnings:
                        quadratura_warnings.append(f"[{year}] {_w}")
                        logger.warning(f"[XBRL] {year}: {_w}")
            except Exception as _q_err:
                logger.warning(f"[XBRL] quadratura check skipped for year {year}: {_q_err}")

            logger.info(
                f"[XBRL] Year {year} (pm={detected_pm}): "
                f"ce08={inc_data.get('ce08_costi_personale', 'MISSING')}, "
                f"sp13={bs_data.get('sp13_utile_perdita', 'MISSING')}"
            )

            all_reconciliation_info[year] = reconciliation_info

            # Update or create balance sheet
            bs = self.db.query(BalanceSheet).filter(
                BalanceSheet.financial_year_id == fy.id
            ).first()

            if bs:
                for field, value in bs_data.items():
                    setattr(bs, field, value)
                bs.updated_at = datetime.utcnow()
            else:
                bs = BalanceSheet(financial_year_id=fy.id)
                for field, value in bs_data.items():
                    setattr(bs, field, value)
                self.db.add(bs)

            # Update or create income statement
            inc = self.db.query(IncomeStatement).filter(
                IncomeStatement.financial_year_id == fy.id
            ).first()

            if inc:
                for field, value in inc_data.items():
                    setattr(inc, field, value)
                inc.updated_at = datetime.utcnow()
            else:
                inc = IncomeStatement(financial_year_id=fy.id)
                for field, value in inc_data.items():
                    setattr(inc, field, value)
                self.db.add(inc)

            imported_years.append(year)
            financial_year_ids.append(fy.id)

        self.db.commit()

        return {
            'success': True,
            'taxonomy_version': taxonomy_version,
            'years': imported_years,
            'company_id': company_id,
            'company_name': company.name,
            'tax_id': entity_info.get('tax_id'),
            'financial_year_ids': financial_year_ids,
            'contexts_found': len(contexts),
            'years_imported': len(imported_years),
            'company_created': company_created,
            'reconciliation_info': all_reconciliation_info,
            'year_period_months': year_period_months,  # {year: months} for partial years
            'warnings': quadratura_warnings,           # non-blocking quadratura flags
        }


def import_xbrl_file_enhanced(
    file_path: str,
    company_id: Optional[int] = None,
    create_company: bool = True,
    sector: Optional[int] = None,
    user_id: Optional[str] = None,
    period_months: Optional[int] = None,
) -> Dict[str, any]:
    """
    Convenience function to import XBRL file with reconciliation
    """
    with EnhancedXBRLParser() as parser:
        return parser.import_to_database(file_path, company_id, create_company, sector=sector, user_id=user_id, period_months=period_months)
