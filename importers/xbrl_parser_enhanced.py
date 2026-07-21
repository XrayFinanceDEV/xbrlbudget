"""
Enhanced XBRL Parser with Aggregate Total Reconciliation
Ensures balance sheet always balances by using aggregate totals
"""
from lxml import etree
from decimal import Decimal
from typing import Dict, List, Tuple, Optional
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from database.models import BalanceSheet, IncomeStatement, Company, FinancialYear
from database.db import SessionLocal
from config import SUPPORTED_TAXONOMIES, CSV_HTML_ENTITIES_TO_REPLACE
import json
import os
import logging
import hashlib

logger = logging.getLogger(__name__)


class XBRLParseError(Exception):
    """Raised when XBRL parsing fails"""
    pass


@dataclass(frozen=True)
class XBRLPeriodKey:
    """Identity of one coherent accounting period in an XBRL instance.

    ``year`` alone is not a period identity: an instance may legitimately contain
    both a full year and a nine-month statement ending in the same calendar year.
    Entity and dimensions are part of the key so facts from different reporting
    scopes can never be merged accidentally.
    """

    entity_scheme: str
    entity_identifier: str
    end_date: str
    period_months: Optional[int]
    start_date: str = ''
    dimensions: Tuple[str, ...] = ()

    @property
    def year(self) -> int:
        return int(self.end_date[:4])

    @property
    def is_full_year(self) -> bool:
        return self.period_months in (None, 12)

    @property
    def label(self) -> str:
        months = self.period_months or 12
        return f"{self.year}-{months}M@{self.end_date}"

    def sort_key(self) -> Tuple[str, str, str, int, str, Tuple[str, ...]]:
        return (
            self.entity_scheme,
            self.entity_identifier,
            self.end_date,
            self.period_months or 12,
            self.start_date,
            self.dimensions,
        )


@dataclass(frozen=True)
class _FactCandidate:
    value: Decimal
    context_ref: str
    unit_ref: str
    unit_signature: Tuple[str, ...]
    context_kind: str
    decimals: str


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

    @staticmethod
    def _expanded_qname(value: str, element: etree._Element) -> str:
        """Return a stable Clark-name for a QName stored in an attribute."""
        if not value or ':' not in value:
            return value or ''
        prefix, local = value.split(':', 1)
        namespace = element.nsmap.get(prefix)
        return f'{{{namespace}}}{local}' if namespace else value

    def _context_dimensions(self, ctx: etree._Element) -> Tuple[str, ...]:
        dimensions = []
        for node in ctx.iter():
            try:
                local = etree.QName(node).localname
            except (TypeError, ValueError):
                continue
            if local == 'explicitMember':
                dimension = self._expanded_qname(node.get('dimension', ''), node)
                member = self._expanded_qname((node.text or '').strip(), node)
                dimensions.append(f'{dimension}={member}')
            elif local == 'typedMember':
                dimension = self._expanded_qname(node.get('dimension', ''), node)
                payload = ''.join(
                    etree.tostring(child, method='c14n').decode('utf-8')
                    for child in node
                )
                dimensions.append(f'{dimension}={payload}')
        return tuple(sorted(dimensions))

    def extract_contexts(self, root: etree._Element) -> Dict[str, Dict]:
        """Extract complete context identities without collapsing them by year."""
        contexts: Dict[str, Dict] = {}

        for ctx in root.findall('.//xbrli:context', namespaces=self.XBRL_NAMESPACES):
            ctx_id = ctx.get('id')
            if not ctx_id:
                continue

            identifier = ctx.find('.//xbrli:identifier', namespaces=self.XBRL_NAMESPACES)
            entity_identifier = (identifier.text or '').strip() if identifier is not None else ''
            entity_scheme = identifier.get('scheme', '') if identifier is not None else ''
            period = ctx.find('./xbrli:period', namespaces=self.XBRL_NAMESPACES)
            if period is None:
                continue

            instant = period.find('./xbrli:instant', namespaces=self.XBRL_NAMESPACES)
            start_el = period.find('./xbrli:startDate', namespaces=self.XBRL_NAMESPACES)
            end_el = period.find('./xbrli:endDate', namespaces=self.XBRL_NAMESPACES)
            forever = period.find('./xbrli:forever', namespaces=self.XBRL_NAMESPACES)
            if forever is not None:
                continue

            kind = 'instant' if instant is not None else 'duration'
            start_date = (start_el.text or '').strip() if start_el is not None else ''
            end_date = (
                (instant.text or '').strip() if instant is not None
                else (end_el.text or '').strip() if end_el is not None else ''
            )
            try:
                end = datetime.strptime(end_date, '%Y-%m-%d')
                year = end.year
            except (TypeError, ValueError):
                continue

            period_months = None
            if kind == 'duration' and start_date:
                try:
                    start = datetime.strptime(start_date, '%Y-%m-%d')
                    months = (end.year - start.year) * 12 + end.month - start.month + 1
                    if 1 <= months <= 12:
                        period_months = months
                except ValueError:
                    pass

            contexts[ctx_id] = {
                'id': ctx_id,
                'year': year,
                'date': end_date,
                'end_date': end_date,
                'start_date': start_date,
                'period_months': period_months,
                'kind': kind,
                'entity_identifier': entity_identifier,
                'entity_scheme': entity_scheme,
                'dimensions': self._context_dimensions(ctx),
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

    def _extract_units(self, root: etree._Element) -> Dict[str, Tuple[str, ...]]:
        units: Dict[str, Tuple[str, ...]] = {}
        for unit in root.findall('.//xbrli:unit', namespaces=self.XBRL_NAMESPACES):
            unit_id = unit.get('id')
            if not unit_id:
                continue
            measures = []
            for measure in unit.findall('.//xbrli:measure', namespaces=self.XBRL_NAMESPACES):
                measures.append(self._expanded_qname((measure.text or '').strip(), measure))
            units[unit_id] = tuple(sorted(measures))
        return units

    @staticmethod
    def _unit_rank(signature: Tuple[str, ...]) -> int:
        local_measures = {m.rsplit('}', 1)[-1].upper() for m in signature}
        if 'EUR' in local_measures:
            return 0
        if not signature:
            return 1
        if 'PURE' in local_measures:
            return 2
        return 3

    @staticmethod
    def _precision_rank(decimals: str) -> int:
        if (decimals or '').upper() == 'INF':
            return -10_000
        try:
            return -int(decimals)
        except (TypeError, ValueError):
            return 10_000

    def _statement_kind_for_tag(self, full_tag: str) -> Optional[str]:
        local = etree.QName(full_tag).localname if full_tag.startswith('{') else full_tag.split(':')[-1]
        bs_locals = {
            tag.split(':')[-1] for tag in self.bs_mapping_v1
        }
        inc_locals = {
            tag.split(':')[-1] for tag in self.inc_mapping_v1
        }
        for config in self.bs_mapping_v2.values():
            if isinstance(config, dict):
                bs_locals.update(
                    str(value).split(':')[-1]
                    for key, value in config.items()
                    if key.startswith('priority_')
                )
        for config in self.inc_mapping_v2.values():
            if isinstance(config, dict):
                inc_locals.update(
                    str(value).split(':')[-1]
                    for key, value in config.items()
                    if key.startswith('priority_')
                )
        if local in bs_locals or local in self.AGGREGATE_TAGS:
            return 'instant'
        if local in inc_locals:
            return 'duration'
        return None

    def _select_fact_candidate(
        self, full_tag: str, candidates: List[_FactCandidate], period: XBRLPeriodKey
    ) -> _FactCandidate:
        expected_kind = self._statement_kind_for_tag(full_tag)

        def rank(candidate: _FactCandidate) -> Tuple[int, int, int, str, str]:
            kind_rank = 0 if not expected_kind or candidate.context_kind == expected_kind else 1
            return (
                self._unit_rank(candidate.unit_signature),
                kind_rank,
                self._precision_rank(candidate.decimals),
                candidate.context_ref,
                candidate.unit_ref,
            )

        selected = min(candidates, key=rank)
        distinct_values = {candidate.value for candidate in candidates}
        if len(distinct_values) > 1:
            local = etree.QName(full_tag).localname if full_tag.startswith('{') else full_tag
            warning = (
                f"[{period.label}] fact XBRL duplicato {local}: selezionato "
                f"{selected.value} ({selected.context_ref}/{selected.unit_ref}); "
                f"scartati {len(candidates) - 1} candidati incompatibili"
            )
            self._fact_selection_warnings.append(warning)
            logger.warning(warning)
        return selected

    def extract_facts(
        self, root: etree._Element, contexts: Dict[str, Dict]
    ) -> Dict[XBRLPeriodKey, Dict[str, Decimal]]:
        """Extract facts by coherent entity/dimension/period cohorts.

        Instant contexts are attached to duration cohorts with the same entity,
        dimensions and end date.  This joins the SP at period end to the matching CE
        duration while keeping annual and interim statements in separate buckets.
        """
        self._fact_selection_warnings: List[str] = []
        units = self._extract_units(root)

        numeric_elements = []
        context_fact_counts: Dict[str, int] = {}
        for elem in root.iter():
            context_ref = elem.get('contextRef')
            if not context_ref or context_ref not in contexts or not elem.text:
                continue
            try:
                value = Decimal(self.clean_xbrl_text(elem.text).replace(',', '.'))
            except Exception:
                continue
            numeric_elements.append((elem, context_ref, value))
            context_fact_counts[context_ref] = context_fact_counts.get(context_ref, 0) + 1

        if not numeric_elements:
            return {}

        # One import must have one reporting entity and one dimensional scope.  Prefer
        # the dimensionless primary statement; otherwise choose the most populated
        # scope, with lexical ties for order independence.
        entity_counts: Dict[Tuple[str, str], int] = {}
        for context_ref, count in context_fact_counts.items():
            ctx = contexts[context_ref]
            entity = (ctx['entity_scheme'], ctx['entity_identifier'])
            entity_counts[entity] = entity_counts.get(entity, 0) + count
        primary_entity = min(entity_counts, key=lambda key: (-entity_counts[key], key))

        dimension_counts: Dict[Tuple[str, ...], int] = {}
        for context_ref, count in context_fact_counts.items():
            ctx = contexts[context_ref]
            if (ctx['entity_scheme'], ctx['entity_identifier']) != primary_entity:
                continue
            dims = ctx['dimensions']
            dimension_counts[dims] = dimension_counts.get(dims, 0) + count
        primary_dimensions = (
            () if () in dimension_counts
            else min(dimension_counts, key=lambda key: (-dimension_counts[key], key))
        )

        duration_keys: Dict[str, XBRLPeriodKey] = {}
        for context_ref, ctx in contexts.items():
            if ctx['kind'] != 'duration':
                continue
            if (ctx['entity_scheme'], ctx['entity_identifier']) != primary_entity:
                continue
            if ctx['dimensions'] != primary_dimensions:
                continue
            duration_keys[context_ref] = XBRLPeriodKey(
                entity_scheme=ctx['entity_scheme'],
                entity_identifier=ctx['entity_identifier'],
                end_date=ctx['end_date'],
                period_months=ctx['period_months'],
                start_date=ctx['start_date'],
                dimensions=ctx['dimensions'],
            )

        candidates: Dict[Tuple[XBRLPeriodKey, str], List[_FactCandidate]] = {}
        for elem, context_ref, value in numeric_elements:
            ctx = contexts[context_ref]
            if (ctx['entity_scheme'], ctx['entity_identifier']) != primary_entity:
                continue
            if ctx['dimensions'] != primary_dimensions:
                continue

            if ctx['kind'] == 'duration':
                period_keys = [duration_keys[context_ref]]
            else:
                period_keys = [
                    key for key in duration_keys.values()
                    if key.end_date == ctx['end_date']
                ]
                if not period_keys:
                    period_keys = [XBRLPeriodKey(
                        entity_scheme=ctx['entity_scheme'],
                        entity_identifier=ctx['entity_identifier'],
                        end_date=ctx['end_date'],
                        period_months=None,
                        dimensions=ctx['dimensions'],
                    )]

            unit_ref = elem.get('unitRef', '')
            candidate = _FactCandidate(
                value=value,
                context_ref=context_ref,
                unit_ref=unit_ref,
                unit_signature=units.get(unit_ref, ()),
                context_kind=ctx['kind'],
                decimals=elem.get('decimals', ''),
            )
            for period_key in period_keys:
                candidates.setdefault((period_key, elem.tag), []).append(candidate)

        facts_by_period: Dict[XBRLPeriodKey, Dict[str, Decimal]] = {}
        for (period_key, full_tag), fact_candidates in sorted(
            candidates.items(), key=lambda item: (item[0][0].sort_key(), str(item[0][1]))
        ):
            selected = self._select_fact_candidate(full_tag, fact_candidates, period_key)
            facts_by_period.setdefault(period_key, {})[full_tag] = selected.value

        return facts_by_period

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
            'priority_matches': {},
            'derived_aggregates': {},
            'source_derivations': {},
            'aggregate_conflicts': {},
            'missing_breakdowns': {},
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

        # Resolve maturity aggregates only from a closed, source-backed identity.
        # Some XBRL producers publish C.II/D totals plus one maturity subtotal and
        # all typed details, while their generic "detail_tags" subtotal omits one
        # taxonomy variant.  In that case the missing maturity amount is
        # mathematically determined by published total - published other maturity,
        # and is corroborated by the typed rows.  This is not a balance plug: both
        # operands and the corroborating detail live in the instance.
        def _derive_maturity_pair(total_key, short_field, long_field, short_details, long_details):
            if total_key not in aggregates:
                return
            published = aggregates[total_key]
            short_value = bs_data.get(short_field, Decimal('0'))
            long_value = bs_data.get(long_field, Decimal('0'))
            if abs((short_value + long_value) - published) <= Decimal('0.01'):
                return
            short_detail = sum(bs_data.get(field, Decimal('0')) for field in short_details)
            long_detail = sum(bs_data.get(field, Decimal('0')) for field in long_details)
            rounding_tol = max(Decimal('1'), abs(published) * Decimal('0.000001'))

            candidates = []
            # A published maturity subtotal can exclude one separately printed
            # debtor/creditor row (most often deferred-tax receivables).  When the
            # exact grand-total residual is independently present in the typed
            # short/long details, add it to that maturity bucket.  This recovers the
            # source identity used by budget_041/399/421/431 without treating the
            # balance-sheet gap itself as evidence.
            residual = published - short_value - long_value
            if residual != 0:
                if short_detail != 0 and abs(residual - short_detail) <= rounding_tol:
                    candidates.append(
                        (short_field, short_value + residual, long_field, long_value)
                    )
                if long_detail != 0 and abs(residual - long_detail) <= rounding_tol:
                    candidates.append(
                        (long_field, long_value + residual, short_field, short_value)
                    )
            implied_short = published - long_value
            if short_detail != 0 and abs(implied_short - short_detail) <= rounding_tol:
                candidates.append((short_field, implied_short, long_field, long_value))
            implied_long = published - short_value
            if long_detail != 0 and abs(implied_long - long_detail) <= rounding_tol:
                candidates.append((long_field, implied_long, short_field, short_value))

            # If neither mapped maturity subtotal is trustworthy but the complete
            # typed rows close to the published total, retain the long typed amount
            # and derive the short amount.  Maturity is still fully source-backed.
            if not candidates and short_detail != 0 and long_detail != 0:
                if abs((short_detail + long_detail) - published) <= rounding_tol:
                    candidates.append(
                        (short_field, published - long_detail, long_field, long_detail)
                    )
            if not candidates:
                return

            # The source identity must also improve the independent SP invariant.
            # This rejects comparative/tag variants whose apparent "Totale" belongs
            # to a different presentation scope.  Quadratura is only a validation
            # gate here: every candidate amount was already determined above from
            # explicit source facts.
            from importers.iv_cee_hierarchy import _ATTIVO_FIELDS, _PASSIVO_FIELDS

            def _gap(values):
                return (
                    sum(values.get(field, Decimal('0')) for field in _ATTIVO_FIELDS)
                    - sum(values.get(field, Decimal('0')) for field in _PASSIVO_FIELDS)
                )

            before_gap = abs(_gap(bs_data))
            improving = []
            for candidate in candidates:
                target, value, retained_field, retained_value = candidate
                trial = dict(bs_data)
                trial[target] = value
                trial[retained_field] = retained_value
                after_gap = abs(_gap(trial))
                if after_gap + Decimal('0.01') < before_gap:
                    improving.append((after_gap, candidate))
            if not improving:
                return

            _, (target, value, retained_field, retained_value) = min(
                improving,
                key=lambda item: (
                    item[0],
                    abs(bs_data.get(item[1][0], Decimal('0')) - item[1][1]),
                    item[1][0],
                ),
            )
            bs_data[target] = value
            bs_data[retained_field] = retained_value
            reconciliation_info['source_derivations'][target] = {
                'formula': f"{total_key} - {retained_field}",
                'published_total': float(published),
                'retained_amount': float(retained_value),
                'derived_amount': float(value),
            }

        _derive_maturity_pair(
            'total_crediti', 'sp06_crediti_breve', 'sp07_crediti_lungo',
            tuple(fields[0] for fields in self.CREDIT_FIELDS.values()),
            tuple(fields[1] for fields in self.CREDIT_FIELDS.values()),
        )
        _derive_maturity_pair(
            'total_debiti', 'sp16_debiti_breve', 'sp17_debiti_lungo',
            tuple(fields[0] for fields in self.CREDITOR_FIELDS.values()),
            tuple(fields[1] for fields in self.CREDITOR_FIELDS.values()),
        )

        # Third pass: derive an aggregate only when the source did not publish it.
        # Never alter a published aggregate and never scale/invent detail buckets.
        DETAIL_TO_AGGREGATE = {
            'sp01_crediti_soci': [
                'sp01a_parte_richiamata', 'sp01b_parte_da_richiamare',
            ],
            'sp02_immob_immateriali': [
                'sp02a_costi_impianto', 'sp02b_costi_sviluppo', 'sp02c_brevetti',
                'sp02d_concessioni', 'sp02e_avviamento', 'sp02f_immob_in_corso',
                'sp02g_altre_immob_imm',
            ],
            'sp03_immob_materiali': [
                'sp03a_terreni_fabbricati', 'sp03b_impianti_macchinari',
                'sp03c_attrezzature', 'sp03d_altri_beni', 'sp03e_immob_in_corso',
            ],
            'sp04_immob_finanziarie': [
                'sp04a_partecipazioni', 'sp04b_crediti_immob_breve',
                'sp04c_crediti_immob_lungo', 'sp04d_altri_titoli',
                'sp04e_strumenti_derivati_attivi',
            ],
            'sp05_rimanenze': [
                'sp05a_materie_prime', 'sp05b_prodotti_in_corso',
                'sp05c_lavori_in_corso', 'sp05d_prodotti_finiti', 'sp05e_acconti',
            ],
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
            'sp12_riserve': [
                'sp12a_riserva_sovrapprezzo', 'sp12b_riserve_rivalutazione',
                'sp12c_riserva_legale', 'sp12d_riserve_statutarie',
                'sp12e_altre_riserve', 'sp12f_riserva_copertura_flussi',
                'sp12g_utili_perdite_portati', 'sp12h_riserva_neg_azioni_proprie',
            ],
            'sp14_fondi_rischi': [
                'sp14a_fondi_trattamento_quiescenza', 'sp14b_fondi_imposte',
                'sp14c_strumenti_derivati_passivi', 'sp14d_altri_fondi',
            ],
        }
        for agg_field, detail_fields in DETAIL_TO_AGGREGATE.items():
            detail_sum = sum(bs_data.get(f, Decimal('0')) for f in detail_fields)
            if agg_field not in bs_data:
                if detail_sum != Decimal('0'):
                    bs_data[agg_field] = detail_sum
                    reconciliation_info['derived_aggregates'][agg_field] = float(detail_sum)
                continue
            aggregate_value = bs_data[agg_field]
            if detail_sum == Decimal('0') and aggregate_value != Decimal('0'):
                reconciliation_info['missing_breakdowns'][agg_field] = {
                    'aggregate': float(aggregate_value),
                    'detail_sum': 0.0,
                }
            elif abs(aggregate_value - detail_sum) > Decimal('0.01'):
                reconciliation_info['aggregate_conflicts'][agg_field] = {
                    'aggregate': float(aggregate_value),
                    'detail_sum': float(detail_sum),
                    'difference': float(aggregate_value - detail_sum),
                }

        for agg_field, detail_fields in {
            'ce08_costi_personale': [
                'ce08a_tfr_accrual', 'ce08b_salari_stipendi',
                'ce08c_oneri_sociali', 'ce08d_altri_costi_personale',
            ],
            'ce09_ammortamenti': [
                'ce09a_ammort_immateriali', 'ce09b_ammort_materiali',
                'ce09c_svalutazioni', 'ce09d_svalutazione_crediti',
            ],
        }.items():
            detail_sum = sum(inc_data.get(f, Decimal('0')) for f in detail_fields)
            if agg_field not in inc_data:
                if detail_sum != Decimal('0'):
                    inc_data[agg_field] = detail_sum
                    reconciliation_info['derived_aggregates'][agg_field] = float(detail_sum)
                continue
            aggregate_value = inc_data[agg_field]
            if detail_sum == Decimal('0') and aggregate_value != Decimal('0'):
                reconciliation_info['missing_breakdowns'][agg_field] = {
                    'aggregate': float(aggregate_value),
                    'detail_sum': 0.0,
                }
            elif abs(aggregate_value - detail_sum) > Decimal('0.01'):
                reconciliation_info['aggregate_conflicts'][agg_field] = {
                    'aggregate': float(aggregate_value),
                    'detail_sum': float(detail_sum),
                    'difference': float(aggregate_value - detail_sum),
                }

        ce17_detail = (
            inc_data.get('ce17a_rivalutazioni', Decimal('0'))
            - inc_data.get('ce17b_svalutazioni', Decimal('0'))
        )
        if 'ce17_rettifiche_attivita_fin' not in inc_data and ce17_detail != Decimal('0'):
            inc_data['ce17_rettifiche_attivita_fin'] = ce17_detail
            reconciliation_info['derived_aggregates']['ce17_rettifiche_attivita_fin'] = float(ce17_detail)
        elif 'ce17_rettifiche_attivita_fin' in inc_data and abs(
            inc_data['ce17_rettifiche_attivita_fin'] - ce17_detail
        ) > Decimal('0.01'):
            reconciliation_info['aggregate_conflicts']['ce17_rettifiche_attivita_fin'] = {
                'aggregate': float(inc_data['ce17_rettifiche_attivita_fin']),
                'detail_sum': float(ce17_detail),
                'difference': float(inc_data['ce17_rettifiche_attivita_fin'] - ce17_detail),
            }

        # Per-counterparty totals without maturity detail are retained as evidence
        # only.  Allocating them to short/long buckets would create facts not present
        # in the instance.
        for bucket, total in creditor_totals.items():
            breve_field, lungo_field = self.CREDITOR_FIELDS[bucket]
            typed_sum = bs_data.get(breve_field, Decimal('0')) + bs_data.get(lungo_field, Decimal('0'))
            if abs(total - typed_sum) > Decimal('0.01'):
                reconciliation_info['aggregate_conflicts'][f'debiti_{bucket}'] = {
                    'aggregate': float(total),
                    'detail_sum': float(typed_sum),
                    'difference': float(total - typed_sum),
                }
        for bucket, total in credit_totals.items():
            breve_field, lungo_field = self.CREDIT_FIELDS[bucket]
            typed_sum = bs_data.get(breve_field, Decimal('0')) + bs_data.get(lungo_field, Decimal('0'))
            if abs(total - typed_sum) > Decimal('0.01'):
                reconciliation_info['aggregate_conflicts'][f'crediti_{bucket}'] = {
                    'aggregate': float(total),
                    'detail_sum': float(typed_sum),
                    'difference': float(total - typed_sum),
                }

        # Grand totals are controls, not destinations for a balancing difference.
        for aggregate_key, fields in {
            'total_crediti': ('sp06_crediti_breve', 'sp07_crediti_lungo'),
            'total_debiti': ('sp16_debiti_breve', 'sp17_debiti_lungo'),
        }.items():
            if aggregate_key not in aggregates:
                continue
            published = aggregates[aggregate_key]
            mapped = sum(bs_data.get(field, Decimal('0')) for field in fields)
            if abs(published - mapped) > Decimal('0.01'):
                reconciliation_info['aggregate_conflicts'][aggregate_key] = {
                    'aggregate': float(published),
                    'detail_sum': float(mapped),
                    'difference': float(published - mapped),
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
                    self.db.flush()
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

        facts_by_period = self.extract_facts(root, contexts)

        if not facts_by_period:
            raise XBRLParseError("No financial facts found in XBRL file")

        periods = sorted(
            facts_by_period,
            key=lambda key: (key.end_date, key.period_months or 12, key.start_date),
            reverse=True,
        )
        year_period_months = {
            key.year: key.period_months
            for key in periods if key.period_months and key.period_months < 12
        }
        logger.info(
            "[XBRL] Periods detected: %s",
            [key.label for key in periods],
        )

        imported_years = []
        imported_periods = []
        financial_year_ids = []
        all_reconciliation_info = {}
        quadratura_warnings = list(getattr(self, '_fact_selection_warnings', []))
        source_sha256 = hashlib.sha256(Path(file_path).read_bytes()).hexdigest()
        bs_columns = {column.name for column in BalanceSheet.__table__.columns}
        inc_columns = {column.name for column in IncomeStatement.__table__.columns}

        for index, period_key in enumerate(periods):
            year = period_key.year
            detected_pm = period_key.period_months
            if detected_pm == 12:
                detected_pm = None
            # A manual period is only a fallback for an instant-only instance.  It
            # must never relabel an explicit annual duration as an interim period.
            if (
                index == 0 and period_months and period_months < 12
                and period_key.period_months is None
            ):
                detected_pm = period_months

            if detected_pm:
                # Match the exact interim duration.  A 6M import must not overwrite
                # an existing 9M statement from the same calendar year.
                fy = self.db.query(FinancialYear).filter(
                    FinancialYear.company_id == company_id,
                    FinancialYear.year == year,
                    FinancialYear.period_months == detected_pm,
                ).first()

                if not fy:
                    fy = FinancialYear(company_id=company_id, year=year, period_months=detected_pm)
                    self.db.add(fy)
                    self.db.flush()
            else:
                # Full year: match existing full-year record
                fy = self.db.query(FinancialYear).filter(
                    FinancialYear.company_id == company_id,
                    FinancialYear.year == year,
                    (FinancialYear.period_months.is_(None)) |
                    (FinancialYear.period_months == 12),
                ).first()

                if not fy:
                    fy = FinancialYear(company_id=company_id, year=year)
                    self.db.add(fy)
                    self.db.flush()

            # Map facts, but do not reconcile by changing accounting values.
            bs_data, inc_data, reconciliation_info = self.map_facts_to_fields_with_reconciliation(
                facts_by_period[period_key]
            )

            # Bilancio abbreviato XBRL publishes legal aggregates (sp04/sp14/…)
            # without their typed sub-details. Book the unexplained remainder into
            # each family's "altri" bucket so the aggregate equals the sum of its
            # detail — the aggregate and the balance are untouched — otherwise the
            # forecast engine rejects the year as "aggregate/detail mismatch" and
            # the company can never be forecast. (This does NOT alter any
            # accounting value: it only fills detail that reconstructs the
            # already-published aggregate.)
            from importers.iv_cee_hierarchy import (
                check_quadratura,
                reconcile_source_detail,
            )
            reconcile_source_detail(bs_data, inc_data)
            q = check_quadratura(bs_data, inc_data)
            period_label = f"{year}-{detected_pm or 12}M"
            for warning in q.warnings:
                quadratura_warnings.append(f"[{period_label}] {warning}")
                logger.warning("[XBRL] %s: %s", period_label, warning)
            for field, conflict in reconciliation_info['aggregate_conflicts'].items():
                warning = (
                    f"[{period_label}] CONFLITTO AGGREGATO XBRL {field}: "
                    f"aggregato {conflict['aggregate']:,.2f}, dettagli "
                    f"{conflict['detail_sum']:,.2f}"
                )
                quadratura_warnings.append(warning)
                logger.warning(warning)

            # Without a persisted rejected/review staging object, a core-invalid
            # statement must fail atomically.  It is never committed merely because
            # a caller wants to inspect it in Rettifiche.
            if not q.quadra:
                self.db.rollback()
                raise XBRLParseError(
                    f"XBRL {period_label} non valido: " + "; ".join(q.warnings)
                )

            semantic_valid = (
                q.semantic_valid
                and not reconciliation_info['aggregate_conflicts']
                and not reconciliation_info['missing_breakdowns']
            )
            validation_report = {
                'period': period_label,
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
                'aggregate_conflicts': reconciliation_info['aggregate_conflicts'],
                'missing_breakdowns': reconciliation_info['missing_breakdowns'],
                'fact_selection_warnings': getattr(self, '_fact_selection_warnings', []),
            }
            fy.validation_status = 'verified' if semantic_valid else 'review_required'
            fy.validation_report = json.dumps(validation_report, ensure_ascii=False)
            fy.source_sha256 = source_sha256
            fy.parser_version = 'xbrl-context-period-v3'
            fy.forecastable = semantic_valid

            logger.info(
                f"[XBRL] Year {year} (pm={detected_pm}): "
                f"ce08={inc_data.get('ce08_costi_personale', 'MISSING')}, "
                f"sp13={bs_data.get('sp13_utile_perdita', 'MISSING')}"
            )

            # The public response schema is historically keyed by year.  Preserve it
            # while exposing every imported period separately in ``periods_imported``.
            all_reconciliation_info.setdefault(year, reconciliation_info)

            # Update or create balance sheet
            bs = self.db.query(BalanceSheet).filter(
                BalanceSheet.financial_year_id == fy.id
            ).first()

            if bs:
                for field, value in bs_data.items():
                    if field not in bs_columns:
                        continue
                    setattr(bs, field, value)
                bs.updated_at = datetime.utcnow()
            else:
                bs = BalanceSheet(financial_year_id=fy.id)
                for field, value in bs_data.items():
                    if field not in bs_columns:
                        continue
                    setattr(bs, field, value)
                self.db.add(bs)

            # Update or create income statement
            inc = self.db.query(IncomeStatement).filter(
                IncomeStatement.financial_year_id == fy.id
            ).first()

            if inc:
                for field, value in inc_data.items():
                    if field not in inc_columns:
                        continue
                    setattr(inc, field, value)
                inc.updated_at = datetime.utcnow()
            else:
                inc = IncomeStatement(financial_year_id=fy.id)
                for field, value in inc_data.items():
                    if field not in inc_columns:
                        continue
                    setattr(inc, field, value)
                self.db.add(inc)

            imported_years.append(year)
            imported_periods.append({
                'year': year,
                'period_months': detected_pm or 12,
                'end_date': period_key.end_date,
                'financial_year_id': fy.id,
            })
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
            'periods_imported': imported_periods,
            'warnings': quadratura_warnings,
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
