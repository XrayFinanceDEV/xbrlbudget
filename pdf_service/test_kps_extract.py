#!/usr/bin/env python3
"""
Test script to extract balance sheet data from KPS PDF using Docling.

Usage:
    cd /home/peter/DEV/budget/pdf_service
    source venv/bin/activate
    python test_kps_extract.py
"""

import sys
from pathlib import Path
from decimal import Decimal
from docling.document_converter import DocumentConverter
import json
import re

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

PDF_PATH = project_root / "docs" / "kps - Bilancio XBRL 2024.pdf"


def parse_italian_number(value_str: str) -> Decimal:
    """
    Convert Italian number format to Decimal.

    Examples:
        "53.138" -> Decimal("53138")
        "205.686" -> Decimal("205686")
        "2.567,39" -> Decimal("2567.39")
        "-" -> Decimal("0")
    """
    if not value_str or value_str.strip() in ['-', '', 'None']:
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
    except:
        print(f"Warning: Could not parse number '{value_str}', returning 0")
        return Decimal('0')


def extract_balance_sheet_micro(doc_text: str) -> dict:
    """
    Extract balance sheet data from Micro format PDF text.

    Strategy:
    1. Split text into lines
    2. Find balance sheet section (Stato Patrimoniale)
    3. Extract values using pattern matching
    4. Map to sp01-sp18 schema
    """

    lines = doc_text.split('\n')

    # Initialize result with all fields as zero
    result = {
        'company_name': 'KPS FINANCIAL LAB S.R.L.',
        'tax_id': '11793470961',
        'year': 2024,
        'format': 'micro',
        'balance_sheet': {
            'sp01_crediti_soci': Decimal('0'),
            'sp02_immob_immateriali': Decimal('0'),
            'sp03_immob_materiali': Decimal('0'),
            'sp04_immob_finanziarie': Decimal('0'),
            'sp05_rimanenze': Decimal('0'),
            'sp06_crediti': Decimal('0'),
            'sp07_attivita_finanziarie': Decimal('0'),
            'sp08_disponibilita_liquide': Decimal('0'),
            'sp09_ratei_risconti_attivi': Decimal('0'),
            'sp10_capitale_sociale': Decimal('0'),
            'sp11_riserve': Decimal('0'),
            'sp12_utile_perdita': Decimal('0'),
            'sp13_fondi_rischi': Decimal('0'),
            'sp14_tfr': Decimal('0'),
            'sp15_debiti_lungo': Decimal('0'),
            'sp16_debiti_breve': Decimal('0'),
            'sp17_ratei_risconti_passivi': Decimal('0'),
            'sp18_totale_attivo': Decimal('0'),
            'sp18_totale_passivo': Decimal('0'),
        },
        'income_statement': {
            'ce01_ricavi_vendite': Decimal('0'),
            'ce20_utile_perdita': Decimal('0'),
        }
    }

    # Pattern matching for balance sheet items (table format from markdown)
    patterns = {
        # Assets - matches table rows like "| I - Immobilizzazioni immateriali | 53.138 | 72.256 |"
        'sp02_immob_immateriali': [
            r'\|\s*I\s*-\s*Immobilizzazioni\s+immateriali\s*\|\s*([\d\.,\-]+)\s*\|',
        ],
        'sp03_immob_materiali': [
            r'\|\s*II\s*-\s*Immobilizzazioni\s+materiali\s*\|\s*([\d\.,\-]+)\s*\|',
        ],
        'sp04_immob_finanziarie': [
            r'\|\s*III\s*-\s*Immobilizzazioni\s+finanziarie\s*\|\s*([\d\.,\-]+)\s*\|',
        ],
        'sp06_crediti': [
            r'\|\s*II\s*-\s*Crediti\s*\|\s*([\d\.,\-]+)\s*\|',
        ],
        'sp07_attivita_finanziarie': [
            r'\|\s*III\s*-\s*Attivita.*finanziarie.*non.*immobilizzazioni\s*\|\s*([\d\.,\-]+)\s*\|',
        ],
        'sp08_disponibilita_liquide': [
            r'\|\s*IV\s*-\s*Disponibilita.*liquide\s*\|\s*([\d\.,\-]+)\s*\|',
        ],
        'sp09_ratei_risconti_attivi': [
            r'\|\s*D\)\s*Ratei\s+e\s+risconti\s*\|\s*([\d\.,\-]+)\s*\|',
        ],
        'sp18_totale_attivo': [
            r'\|\s*Totale\s+attivo\s*\|\s*([\d\.,\-]+)\s*\|',
        ],
        # Liabilities
        'sp10_capitale_sociale': [
            r'\|\s*I\s*-\s*Capitale\s*\|\s*([\d\.,\-]+)\s*\|',
        ],
        'sp12_utile_perdita': [
            r'\|\s*IX\s*-\s*Utile.*perdita.*esercizio\s*\|\s*([\d\.,\-]+)\s*\|',
        ],
        'sp16_debiti_breve': [
            r'\|\s*D\)\s*Debiti\s*\|\s*([\d\.,\-]+)\s*\|',
        ],
        'sp17_ratei_risconti_passivi': [
            r'\|\s*E\)\s*Ratei\s+e\s+risconti\s*\|\s*([\d\.,\-]+)\s*\|',
        ],
        'sp18_totale_passivo': [
            r'\|\s*Totale\s+passivo\s*\|\s*([\d\.,\-]+)\s*\|',
        ],
    }

    # Extract values using patterns
    for field, pattern_list in patterns.items():
        for pattern in pattern_list:
            for line in lines:
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    value_str = match.group(1)
                    result['balance_sheet'][field] = parse_italian_number(value_str)
                    print(f"✓ Found {field}: {value_str} -> {result['balance_sheet'][field]}")
                    break
            if result['balance_sheet'][field] != Decimal('0'):
                break

    # Calculate sp11_riserve (reserves) = Total equity - Capital - Profit
    # We need to extract reserves explicitly (table format)
    reserves_patterns = [
        r'\|\s*IV\s*-\s*Riserva\s+legale\s*\|\s*([\d\.,\-]+)\s*\|',
        r'\|\s*VI\s*-\s*Altre\s+riserve\s*\|\s*([\d\.,\-]+)\s*\|',
    ]

    reserves_total = Decimal('0')
    for pattern in reserves_patterns:
        for line in lines:
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                value_str = match.group(1)
                reserves_total += parse_italian_number(value_str)
                print(f"✓ Found reserve component: {value_str}")

    result['balance_sheet']['sp11_riserve'] = reserves_total

    # Extract income statement items (table format)
    income_patterns = {
        'ce01_ricavi_vendite': [
            r'\|\s*1\)\s*ricavi\s+delle\s+vendite.*prestazioni\s*\|\s*([\d\.,\-]+)\s*\|',
        ],
    }

    for field, pattern_list in income_patterns.items():
        for pattern in pattern_list:
            for line in lines:
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    value_str = match.group(1)
                    result['income_statement'][field] = parse_italian_number(value_str)
                    print(f"✓ Found {field}: {value_str} -> {result['income_statement'][field]}")
                    break
            if result['income_statement'][field] != Decimal('0'):
                break

    # Copy profit to income statement
    result['income_statement']['ce20_utile_perdita'] = result['balance_sheet']['sp12_utile_perdita']

    return result


def validate_balance_sheet(data: dict) -> bool:
    """
    Validate that balance sheet balances.

    Assets = Liabilities + Equity
    """
    bs = data['balance_sheet']

    total_attivo = bs['sp18_totale_attivo']
    total_passivo = bs['sp18_totale_passivo']

    print("\n" + "="*60)
    print("VALIDATION")
    print("="*60)

    print(f"Total Attivo:  {total_attivo:>15,.2f}")
    print(f"Total Passivo: {total_passivo:>15,.2f}")
    print(f"Difference:    {abs(total_attivo - total_passivo):>15,.2f}")

    tolerance = Decimal('0.01')
    balanced = abs(total_attivo - total_passivo) <= tolerance

    if balanced:
        print("✓ Balance sheet BALANCES")
    else:
        print("✗ Balance sheet DOES NOT BALANCE")

    return balanced


def display_results(data: dict):
    """Pretty print extracted data."""

    print("\n" + "="*60)
    print("EXTRACTED DATA")
    print("="*60)

    print(f"\nCompany: {data['company_name']}")
    print(f"Tax ID:  {data['tax_id']}")
    print(f"Year:    {data['year']}")
    print(f"Format:  {data['format'].upper()}")

    print("\n" + "-"*60)
    print("BALANCE SHEET (Stato Patrimoniale)")
    print("-"*60)

    bs = data['balance_sheet']

    print("\nASSETS (ATTIVO):")
    print(f"  sp02 Immob. immateriali:    {bs['sp02_immob_immateriali']:>15,.2f}")
    print(f"  sp03 Immob. materiali:      {bs['sp03_immob_materiali']:>15,.2f}")
    print(f"  sp04 Immob. finanziarie:    {bs['sp04_immob_finanziarie']:>15,.2f}")
    print(f"  sp06 Crediti:               {bs['sp06_crediti']:>15,.2f}")
    print(f"  sp07 Attività finanziarie:  {bs['sp07_attivita_finanziarie']:>15,.2f}")
    print(f"  sp08 Disponibilità liquide: {bs['sp08_disponibilita_liquide']:>15,.2f}")
    print(f"  sp09 Ratei/risconti attivi: {bs['sp09_ratei_risconti_attivi']:>15,.2f}")
    print(f"  " + "-"*50)
    print(f"  sp18 TOTALE ATTIVO:         {bs['sp18_totale_attivo']:>15,.2f}")

    print("\nLIABILITIES & EQUITY (PASSIVO):")
    print(f"  sp10 Capitale sociale:      {bs['sp10_capitale_sociale']:>15,.2f}")
    print(f"  sp11 Riserve:               {bs['sp11_riserve']:>15,.2f}")
    print(f"  sp12 Utile/perdita:         {bs['sp12_utile_perdita']:>15,.2f}")
    print(f"  sp16 Debiti breve termine:  {bs['sp16_debiti_breve']:>15,.2f}")
    print(f"  sp17 Ratei/risconti passivi:{bs['sp17_ratei_risconti_passivi']:>15,.2f}")
    print(f"  " + "-"*50)
    print(f"  sp18 TOTALE PASSIVO:        {bs['sp18_totale_passivo']:>15,.2f}")

    print("\n" + "-"*60)
    print("INCOME STATEMENT (Conto Economico)")
    print("-"*60)

    inc = data['income_statement']
    print(f"  ce01 Ricavi vendite:        {inc['ce01_ricavi_vendite']:>15,.2f}")
    print(f"  ce20 Utile/perdita:         {inc['ce20_utile_perdita']:>15,.2f}")

    print("\n" + "-"*60)
    print("MISSING FIELDS (Micro Format Limitation)")
    print("-"*60)
    print("  sp01 Crediti verso soci:      Not in Micro format")
    print("  sp05 Rimanenze:               Not in Micro format")
    print("  sp13 Fondi rischi:            Not in Micro format")
    print("  sp14 TFR:                     Not in Micro format")
    print("  sp15 Debiti lungo termine:    Not in Micro format")
    print("  sp16a-g Hierarchical debts:   Not in Micro format")


def main():
    """Main test function."""

    print("="*60)
    print("DOCLING PDF EXTRACTION TEST - KPS Balance Sheet")
    print("="*60)
    print(f"\nPDF File: {PDF_PATH}")
    print(f"Exists: {PDF_PATH.exists()}")

    if not PDF_PATH.exists():
        print(f"\n✗ ERROR: PDF file not found at {PDF_PATH}")
        return 1

    print("\n" + "-"*60)
    print("STEP 1: Initialize Docling Converter")
    print("-"*60)
    print("Note: First run will download models (~2GB) from HuggingFace")
    print("This can take 2-10 minutes depending on connection speed.")
    print("Subsequent runs will be much faster (<5 seconds).\n")

    converter = DocumentConverter()
    print("✓ Converter initialized")

    print("\n" + "-"*60)
    print("STEP 2: Convert PDF to Structured Format")
    print("-"*60)

    result = converter.convert(str(PDF_PATH))
    print(f"✓ PDF converted successfully")
    print(f"  Pages: {len(result.document.pages)}")

    # Get full text
    doc_text = result.document.export_to_markdown()
    print(f"  Text length: {len(doc_text)} characters")

    # Save markdown for inspection
    markdown_path = PDF_PATH.parent / "kps_extracted.md"
    with open(markdown_path, 'w', encoding='utf-8') as f:
        f.write(doc_text)
    print(f"✓ Markdown saved to: {markdown_path}")

    print("\n" + "-"*60)
    print("STEP 3: Extract Balance Sheet Data")
    print("-"*60)

    extracted_data = extract_balance_sheet_micro(doc_text)

    print("\n" + "-"*60)
    print("STEP 4: Display Results")
    print("-"*60)

    display_results(extracted_data)

    print("\n" + "-"*60)
    print("STEP 5: Validate Balance Sheet")
    print("-"*60)

    is_valid = validate_balance_sheet(extracted_data)

    # Save JSON
    json_path = PDF_PATH.parent / "kps_extracted.json"

    # Convert Decimal to float for JSON
    def decimal_to_float(obj):
        if isinstance(obj, Decimal):
            return float(obj)
        raise TypeError

    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(extracted_data, f, indent=2, ensure_ascii=False, default=decimal_to_float)
    print(f"\n✓ JSON saved to: {json_path}")

    print("\n" + "="*60)
    print("TEST COMPLETE")
    print("="*60)

    return 0 if is_valid else 1


if __name__ == '__main__':
    sys.exit(main())
