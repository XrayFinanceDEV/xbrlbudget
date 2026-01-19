"""
XBRL Parser for Italian GAAP Files
Imports financial data directly from XBRL instance documents
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


class XBRLParser:
    """
    Parses Italian GAAP XBRL instance documents

    Supports taxonomies:
    - 2018-11-04, 2017-07-06, 2016-11-14, 2015-12-14, 2014-11-17, 2011-01-04
    """

    # XBRL namespace
    XBRL_NAMESPACES = {
        'xbrli': 'http://www.xbrl.org/2003/instance',
        'link': 'http://www.xbrl.org/2003/linkbase',
        'xlink': 'http://www.w3.org/1999/xlink',
        'iso4217': 'http://www.xbrl.org/2003/iso4217'
    }

    def __init__(self, db_session=None):
        """
        Initialize XBRL parser

        Args:
            db_session: Database session (optional)
        """
        self.db = db_session or SessionLocal()
        self._own_session = db_session is None

        # Load taxonomy mapping
        self._load_taxonomy_mapping()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._own_session:
            self.db.close()

    def _load_taxonomy_mapping(self):
        """Load taxonomy mapping from JSON file"""
        mapping_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'taxonomy_mapping.json')
        with open(mapping_path, 'r', encoding='utf-8') as f:
            taxonomy = json.load(f)
            self.bs_mapping = taxonomy['balance_sheet_mapping']
            self.inc_mapping = taxonomy['income_statement_mapping']

    def clean_xbrl_text(self, text: str) -> str:
        """
        Clean special characters from XBRL text

        Args:
            text: Text to clean

        Returns:
            Cleaned text
        """
        if not text:
            return text

        cleaned = text
        for entity, replacement in CSV_HTML_ENTITIES_TO_REPLACE.items():
            cleaned = cleaned.replace(entity, replacement)

        return cleaned.strip()

    def parse_file(self, file_path: str) -> etree._Element:
        """
        Parse XBRL file and return root element

        Args:
            file_path: Path to XBRL file

        Returns:
            XML root element
        """
        if not Path(file_path).exists():
            raise XBRLParseError(f"File not found: {file_path}")

        try:
            # Parse XML
            parser = etree.XMLParser(remove_blank_text=True, encoding='utf-8')
            tree = etree.parse(file_path, parser)
            root = tree.getroot()

            return root

        except etree.XMLSyntaxError as e:
            raise XBRLParseError(f"Invalid XML syntax: {e}")
        except Exception as e:
            raise XBRLParseError(f"Error parsing XBRL file: {e}")

    def extract_taxonomy_version(self, root: etree._Element) -> str:
        """
        Extract taxonomy version from XBRL file

        Args:
            root: XML root element

        Returns:
            Taxonomy version (e.g., "2018-11-04")
        """
        # Look for schemaRef element
        schema_ref = root.find('.//link:schemaRef', namespaces=self.XBRL_NAMESPACES)

        if schema_ref is not None:
            href = schema_ref.get('{http://www.w3.org/1999/xlink}href', '')
            # Extract version from href (e.g., "http://.../2018-11-04/...")
            for taxonomy in SUPPORTED_TAXONOMIES:
                if taxonomy in href:
                    return taxonomy

        # Try to infer from namespace declarations
        for prefix, uri in root.nsmap.items():
            if 'itcc-ci' in str(uri):
                for taxonomy in SUPPORTED_TAXONOMIES:
                    if taxonomy in str(uri):
                        return taxonomy

        # Default to latest
        return SUPPORTED_TAXONOMIES[0]

    def extract_contexts(self, root: etree._Element) -> Dict[str, Dict]:
        """
        Extract context information (periods) from XBRL

        Args:
            root: XML root element

        Returns:
            Dictionary mapping context ID to context info
        """
        contexts = {}

        # Find all context elements
        context_elements = root.findall('.//xbrli:context', namespaces=self.XBRL_NAMESPACES)

        for ctx in context_elements:
            ctx_id = ctx.get('id')
            if not ctx_id:
                continue

            # Extract period information
            period = ctx.find('.//xbrli:period', namespaces=self.XBRL_NAMESPACES)

            if period is not None:
                # Try instant period
                instant = period.find('.//xbrli:instant', namespaces=self.XBRL_NAMESPACES)
                if instant is not None:
                    date_str = instant.text
                    try:
                        date = datetime.strptime(date_str, '%Y-%m-%d')
                        year = date.year
                    except:
                        year = None
                else:
                    # Try duration period (use end date)
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
        """
        Extract entity (company) information from XBRL

        Args:
            root: XML root element

        Returns:
            Dictionary with entity information
        """
        entity_info = {}

        # Look for entity element in first context
        context = root.find('.//xbrli:context', namespaces=self.XBRL_NAMESPACES)

        if context is not None:
            entity = context.find('.//xbrli:entity', namespaces=self.XBRL_NAMESPACES)

            if entity is not None:
                # Extract identifier (typically tax code)
                identifier = entity.find('.//xbrli:identifier', namespaces=self.XBRL_NAMESPACES)
                if identifier is not None:
                    entity_info['tax_id'] = identifier.text

                # Extract entity name from facts (if present)
                # Look for common entity name elements
                for elem in root.iter():
                    # Safely get tag as string
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
        """
        Extract financial facts from XBRL

        Args:
            root: XML root element
            contexts: Context information

        Returns:
            Dictionary mapping year to facts dictionary
        """
        # Group facts by year
        facts_by_year = {}

        # Get all namespaces from root
        namespaces = dict(root.nsmap)

        # Iterate through all elements
        for elem in root.iter():
            # Skip if no context reference
            context_ref = elem.get('contextRef')
            if not context_ref or context_ref not in contexts:
                continue

            # Get year from context
            year = contexts[context_ref]['year']
            if not year:
                continue

            # Initialize year dictionary if needed
            if year not in facts_by_year:
                facts_by_year[year] = {}

            # Get element local name (without namespace)
            tag = etree.QName(elem).localname

            # Get full qualified name for mapping
            full_tag = elem.tag

            # Try to get value
            value_text = elem.text
            if value_text:
                try:
                    # Clean and parse value
                    cleaned = self.clean_xbrl_text(value_text)
                    value = Decimal(cleaned.replace(',', '.'))

                    # Store with full tag name for later mapping
                    facts_by_year[year][full_tag] = value

                except:
                    # Not a numeric value, skip
                    continue

        return facts_by_year

    def map_facts_to_fields(self, facts: Dict[str, Decimal]) -> Tuple[Dict[str, Decimal], Dict[str, Decimal]]:
        """
        Map XBRL facts to database fields

        Args:
            facts: Dictionary of XBRL tag -> value

        Returns:
            Tuple of (balance_sheet_data, income_statement_data)
        """
        bs_data = {}
        inc_data = {}

        for tag, value in facts.items():
            # Get local name from tag (strip namespace)
            local_name = etree.QName(tag).localname if tag.startswith('{') else tag.split(':')[-1]

            # Try balance sheet mapping
            matched = False
            for xbrl_tag, field in self.bs_mapping.items():
                expected_local = xbrl_tag.split(':')[-1]

                # Priority 1: Exact match
                if local_name == expected_local:
                    # Accumulate if field already exists (for multiple items mapping to same field)
                    bs_data[field] = bs_data.get(field, Decimal('0')) + value
                    matched = True
                    break

                # Priority 2: Match with "Totale" prefix (prefer totals over detail items)
                if local_name.startswith('Totale') and expected_local in local_name:
                    bs_data[field] = bs_data.get(field, Decimal('0')) + value
                    matched = True
                    break

            # Only try income statement if not matched in balance sheet
            if not matched:
                for xbrl_tag, field in self.inc_mapping.items():
                    expected_local = xbrl_tag.split(':')[-1]

                    # Priority 1: Exact match
                    if local_name == expected_local:
                        inc_data[field] = inc_data.get(field, Decimal('0')) + value
                        break

                    # Priority 2: Match with "Totale" prefix
                    if local_name.startswith('Totale') and expected_local in local_name:
                        inc_data[field] = inc_data.get(field, Decimal('0')) + value
                        break

        return bs_data, inc_data

    def import_to_database(self,
                          file_path: str,
                          company_id: Optional[int] = None,
                          create_company: bool = True) -> Dict[str, any]:
        """
        Import XBRL file to database

        Args:
            file_path: Path to XBRL file
            company_id: Company ID (optional, will create if None and create_company=True)
            create_company: Whether to create company if not found

        Returns:
            Dictionary with import results
        """
        # Parse XBRL file
        root = self.parse_file(file_path)

        # Extract taxonomy version
        taxonomy_version = self.extract_taxonomy_version(root)

        # Extract contexts (periods/years)
        contexts = self.extract_contexts(root)

        if not contexts:
            raise XBRLParseError("No contexts found in XBRL file")

        # Extract entity information
        entity_info = self.extract_entity_info(root)

        # Get or create company
        company_created = False
        if company_id is None:
            if create_company:
                # Check if company with this tax_id already exists
                tax_id = entity_info.get('tax_id')
                existing_company = None

                if tax_id:
                    existing_company = self.db.query(Company).filter(
                        Company.tax_id == tax_id
                    ).first()

                if existing_company:
                    # Use existing company
                    company = existing_company
                    company_id = company.id
                    company_created = False
                else:
                    # Create new company
                    company = Company(
                        name=entity_info.get('name', 'Imported Company'),
                        tax_id=tax_id,
                        sector=1  # Default to Industria
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

        # Extract financial facts
        facts_by_year = self.extract_facts(root, contexts)

        if not facts_by_year:
            raise XBRLParseError("No financial facts found in XBRL file")

        # Sort years (most recent first)
        years = sorted(facts_by_year.keys(), reverse=True)

        imported_years = []
        financial_year_ids = []

        # Import each year
        for year in years:
            # Get or create financial year
            fy = self.db.query(FinancialYear).filter(
                FinancialYear.company_id == company_id,
                FinancialYear.year == year
            ).first()

            if not fy:
                fy = FinancialYear(company_id=company_id, year=year)
                self.db.add(fy)
                self.db.flush()

            # Map facts to fields
            bs_data, inc_data = self.map_facts_to_fields(facts_by_year[year])

            # Get or create balance sheet
            bs = self.db.query(BalanceSheet).filter(
                BalanceSheet.financial_year_id == fy.id
            ).first()

            if bs:
                # Update existing balance sheet
                for field, value in bs_data.items():
                    setattr(bs, field, value)
                bs.updated_at = datetime.utcnow()
            else:
                # Create new balance sheet
                bs = BalanceSheet(financial_year_id=fy.id)
                for field, value in bs_data.items():
                    setattr(bs, field, value)
                self.db.add(bs)

            # Get or create income statement
            inc = self.db.query(IncomeStatement).filter(
                IncomeStatement.financial_year_id == fy.id
            ).first()

            if inc:
                # Update existing income statement
                for field, value in inc_data.items():
                    setattr(inc, field, value)
                inc.updated_at = datetime.utcnow()
            else:
                # Create new income statement
                inc = IncomeStatement(financial_year_id=fy.id)
                for field, value in inc_data.items():
                    setattr(inc, field, value)
                self.db.add(inc)

            imported_years.append(year)
            financial_year_ids.append(fy.id)

        # Commit all changes
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
            'company_created': company_created
        }


def import_xbrl_file(file_path: str,
                    company_id: Optional[int] = None,
                    create_company: bool = True) -> Dict[str, any]:
    """
    Convenience function to import XBRL file

    Args:
        file_path: Path to XBRL file
        company_id: Company ID (optional)
        create_company: Whether to create company if not exists

    Returns:
        Import results dictionary
    """
    with XBRLParser() as parser:
        return parser.import_to_database(file_path, company_id, create_company)
