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

    def parse_file(self, file_path: str) -> etree._Element:
        """Parse XBRL file and return root element"""
        if not Path(file_path).exists():
            raise XBRLParseError(f"File not found: {file_path}")

        try:
            parser = etree.XMLParser(remove_blank_text=True, encoding='utf-8')
            tree = etree.parse(file_path, parser)
            root = tree.getroot()
            return root
        except etree.XMLSyntaxError as e:
            raise XBRLParseError(f"Invalid XML syntax: {e}")
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
                instant = period.find('.//xbrli:instant', namespaces=self.XBRL_NAMESPACES)
                if instant is not None:
                    date_str = instant.text
                    try:
                        date = datetime.strptime(date_str, '%Y-%m-%d')
                        year = date.year
                    except:
                        year = None
                else:
                    end_date = period.find('.//xbrli:endDate', namespaces=self.XBRL_NAMESPACES)
                    if end_date is not None:
                        date_str = end_date.text
                        try:
                            date = datetime.strptime(date_str, '%Y-%m-%d')
                            year = date.year
                        except:
                            year = None
                    else:
                        year = None

                contexts[ctx_id] = {
                    'id': ctx_id,
                    'year': year,
                    'date': date_str if 'date_str' in locals() else None
                }

        return contexts

    def extract_entity_info(self, root: etree._Element) -> Dict[str, str]:
        """Extract entity (company) information from XBRL"""
        entity_info = {}

        context = root.find('.//xbrli:context', namespaces=self.XBRL_NAMESPACES)

        if context is not None:
            entity = context.find('.//xbrli:entity', namespaces=self.XBRL_NAMESPACES)

            if entity is not None:
                identifier = entity.find('.//xbrli:identifier', namespaces=self.XBRL_NAMESPACES)
                if identifier is not None:
                    entity_info['tax_id'] = identifier.text

                for elem in root.iter():
                    try:
                        tag_str = etree.QName(elem).localname.lower() if hasattr(elem, 'tag') else ''
                    except:
                        tag_str = str(elem.tag).lower() if elem.tag else ''

                    if 'denominazione' in tag_str or 'ragionesociale' in tag_str or 'name' in tag_str:
                        if elem.text:
                            entity_info['name'] = self.clean_xbrl_text(elem.text)
                            break

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

                # Match with "Totale" prefix
                if local_name.startswith('Totale') and expected_local in local_name:
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

            # Skip if already matched via v2
            already_matched = False
            for matched_tag in reconciliation_info.get('priority_matches', {}).values():
                if matched_tag and local_name in matched_tag:
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

                    # Only add if not already added via v2
                    if field not in bs_data or bs_data[field] == Decimal('0'):
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

        # Third pass: Reconciliation
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
        create_company: bool = True
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
                    existing_company = self.db.query(Company).filter(
                        Company.tax_id == tax_id
                    ).first()

                if existing_company:
                    company = existing_company
                    company_id = company.id
                else:
                    company = Company(
                        name=entity_info.get('name', 'Imported Company'),
                        tax_id=tax_id,
                        sector=1
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

        facts_by_year = self.extract_facts(root, contexts)

        if not facts_by_year:
            raise XBRLParseError("No financial facts found in XBRL file")

        years = sorted(facts_by_year.keys(), reverse=True)
        imported_years = []
        financial_year_ids = []
        all_reconciliation_info = {}

        for year in years:
            fy = self.db.query(FinancialYear).filter(
                FinancialYear.company_id == company_id,
                FinancialYear.year == year
            ).first()

            if not fy:
                fy = FinancialYear(company_id=company_id, year=year)
                self.db.add(fy)
                self.db.flush()

            # Map facts with reconciliation
            bs_data, inc_data, reconciliation_info = self.map_facts_to_fields_with_reconciliation(
                facts_by_year[year]
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
            'reconciliation_info': all_reconciliation_info
        }


def import_xbrl_file_enhanced(
    file_path: str,
    company_id: Optional[int] = None,
    create_company: bool = True
) -> Dict[str, any]:
    """
    Convenience function to import XBRL file with reconciliation
    """
    with EnhancedXBRLParser() as parser:
        return parser.import_to_database(file_path, company_id, create_company)
