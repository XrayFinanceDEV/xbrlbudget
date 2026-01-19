"""
CSV Importer for TEBE XBRL Conversions
Imports financial data from semicolon-delimited CSV files
"""
import csv
import re
import html
from decimal import Decimal
from typing import Dict, List, Tuple, Optional
from pathlib import Path
from database.models import BalanceSheet, IncomeStatement, Company, FinancialYear
from database.db import SessionLocal
from config import BalanceSheetType, TAXONOMY_ROW_COUNTS, CSV_DELIMITER, CSV_HTML_ENTITIES_TO_REPLACE


class CSVImportError(Exception):
    """Raised when CSV import fails"""
    pass


class CSVImporter:
    """
    Imports financial data from TEBE CSV format

    CSV Format:
    - Semicolon-delimited (;)
    - Columns: Description; Year1_Value; Year2_Value; Tag; Unit
    - First row: Balance sheet type (BILANCIO ESERCIZIO, BILANCIO ABBREVIATO, BILANCIO MICRO)
    - Contains HTML entities that need cleaning
    """

    def __init__(self, db_session=None):
        """
        Initialize CSV importer

        Args:
            db_session: Database session (optional, will create if not provided)
        """
        self.db = db_session or SessionLocal()
        self._own_session = db_session is None

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

        rows = []
        first_row_text = ""

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                # Read raw rows first
                reader = csv.reader(f, delimiter=CSV_DELIMITER)
                all_rows = list(reader)

                if len(all_rows) < 2:
                    raise CSVImportError("CSV file has insufficient data")

                # First row is balance sheet type
                first_row_text = all_rows[0][0] if all_rows[0] else ""

                # Process data rows (skip first row which is the header)
                for row_data in all_rows[1:]:  # Skip header row
                    if len(row_data) < 2:
                        continue

                    # Standardize to dictionary format
                    cleaned_row = {
                        'description': self.clean_html_entities(row_data[0]) if len(row_data) > 0 else '',
                        'value_year1': self.clean_html_entities(row_data[1]) if len(row_data) > 1 else '0',
                        'value_year2': self.clean_html_entities(row_data[2]) if len(row_data) > 2 else '0',
                        'tag': self.clean_html_entities(row_data[3]) if len(row_data) > 3 else '',
                        'unit': self.clean_html_entities(row_data[4]) if len(row_data) > 4 else ''
                    }
                    rows.append(cleaned_row)

        except Exception as e:
            raise CSVImportError(f"Error reading CSV file: {e}")

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
        # Read CSV
        bs_type, rows = self.read_csv_file(file_path)

        # Extract years if not provided
        if year1 is None or year2 is None:
            detected_year1, detected_year2 = self.extract_years_from_csv(rows)
            year1 = year1 or detected_year1
            year2 = year2 or detected_year2

        # Get or create financial years
        fy1 = self.db.query(FinancialYear).filter(
            FinancialYear.company_id == company_id,
            FinancialYear.year == year1
        ).first()

        if not fy1:
            fy1 = FinancialYear(company_id=company_id, year=year1)
            self.db.add(fy1)
            self.db.flush()

        fy2 = self.db.query(FinancialYear).filter(
            FinancialYear.company_id == company_id,
            FinancialYear.year == year2
        ).first()

        if not fy2:
            fy2 = FinancialYear(company_id=company_id, year=year2)
            self.db.add(fy2)
            self.db.flush()

        # Create balance sheets and income statements
        bs1 = BalanceSheet(financial_year_id=fy1.id)
        bs2 = BalanceSheet(financial_year_id=fy2.id)
        inc1 = IncomeStatement(financial_year_id=fy1.id)
        inc2 = IncomeStatement(financial_year_id=fy2.id)

        # Parse rows and populate data
        imported_bs_fields = 0
        imported_inc_fields = 0

        for row in rows:
            description = row.get('description', '')
            if not description or description == "Dati anagrafici":
                continue

            # Try balance sheet first
            field = self.map_row_to_field(description, is_balance_sheet=True)

            if field:
                # Balance sheet field
                try:
                    value1 = self.parse_monetary_value(row.get('value_year1', '0'))
                    value2 = self.parse_monetary_value(row.get('value_year2', '0'))

                    setattr(bs1, field, value1)
                    setattr(bs2, field, value2)
                    imported_bs_fields += 1
                except Exception as e:
                    print(f"Warning: Could not import balance sheet field {field}: {e}")
                    continue

            else:
                # Try income statement
                field = self.map_row_to_field(description, is_balance_sheet=False)

                if field:
                    try:
                        value1 = self.parse_monetary_value(row.get('value_year1', '0'))
                        value2 = self.parse_monetary_value(row.get('value_year2', '0'))

                        setattr(inc1, field, value1)
                        setattr(inc2, field, value2)
                        imported_inc_fields += 1
                    except Exception as e:
                        print(f"Warning: Could not import income statement field {field}: {e}")
                        continue

        # Save to database
        self.db.add(bs1)
        self.db.add(bs2)
        self.db.add(inc1)
        self.db.add(inc2)
        self.db.commit()

        return {
            'success': True,
            'balance_sheet_type': bs_type.value,
            'years': [year1, year2],
            'rows_processed': len(rows),
            'balance_sheet_fields_imported': imported_bs_fields,
            'income_statement_fields_imported': imported_inc_fields,
            'financial_year_ids': [fy1.id, fy2.id]
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
