"""
Analyze XBRL Balance Sheet Balance
Check if ATTIVO = PASSIVO in the XBRL file itself
"""
from lxml import etree
from pathlib import Path
from decimal import Decimal
import sys

def analyze_xbrl_balance(xbrl_path):
    """Analyze if XBRL file has balanced balance sheet"""

    # Parse XBRL
    parser = etree.XMLParser(remove_blank_text=True, encoding='utf-8')
    tree = etree.parse(xbrl_path, parser)
    root = tree.getroot()

    print("=" * 80)
    print("XBRL BALANCE SHEET BALANCE ANALYSIS")
    print("=" * 80)
    print(f"\nFile: {xbrl_path}")

    # Find all contexts
    contexts = {}
    for ctx in root.findall('.//{http://www.xbrl.org/2003/instance}context'):
        ctx_id = ctx.get('id')
        period = ctx.find('.//{http://www.xbrl.org/2003/instance}period')

        if period is not None:
            instant = period.find('.//{http://www.xbrl.org/2003/instance}instant')
            if instant is not None:
                contexts[ctx_id] = {
                    'id': ctx_id,
                    'date': instant.text,
                    'type': 'instant'
                }
            else:
                end_date = period.find('.//{http://www.xbrl.org/2003/instance}endDate')
                if end_date is not None:
                    contexts[ctx_id] = {
                        'id': ctx_id,
                        'date': end_date.text,
                        'type': 'duration'
                    }

    print(f"\nContexts found: {len(contexts)}")

    # Analyze each context
    for ctx_id, ctx_info in contexts.items():
        if ctx_info['type'] != 'instant':
            continue  # Skip duration contexts (income statement)

        print(f"\n{'=' * 80}")
        print(f"Context: {ctx_id} - Date: {ctx_info['date']}")
        print('=' * 80)

        # Extract all balance sheet related tags
        attivo_tags = []
        passivo_tags = []
        total_attivo = None
        total_passivo = None

        for elem in root.iter():
            if elem.get('contextRef') != ctx_id:
                continue

            try:
                local_name = etree.QName(elem).localname
                if not elem.text:
                    continue

                value = Decimal(elem.text.replace(',', '.'))

                # Look for total tags
                if local_name == 'TotaleAttivo':
                    total_attivo = value
                    print(f"\n✓ Found TotaleAttivo: €{value:,.2f}")
                elif local_name == 'TotalePassivo':
                    total_passivo = value
                    print(f"✓ Found TotalePassivo: €{value:,.2f}")

                # Categorize as Attivo or Passivo based on tag name
                if any(x in local_name for x in ['Immobilizzazioni', 'Crediti', 'Rimanenze',
                                                   'Disponibilita', 'Attiv', 'Circolante']):
                    if 'Passiv' not in local_name:
                        attivo_tags.append((local_name, value))

                if any(x in local_name for x in ['Patrimonio', 'Capital', 'Riserv', 'Utile',
                                                   'Debiti', 'TFR', 'Fondi', 'PassivRatei']):
                    passivo_tags.append((local_name, value))

            except Exception as e:
                continue

        # Display results
        if total_attivo is not None and total_passivo is not None:
            print(f"\n{'─' * 80}")
            print("OFFICIAL TOTALS FROM XBRL:")
            print(f"{'─' * 80}")
            print(f"  Totale Attivo:   €{total_attivo:>15,.2f}")
            print(f"  Totale Passivo:  €{total_passivo:>15,.2f}")
            print(f"  {'─' * 50}")
            difference = total_attivo - total_passivo
            print(f"  DIFFERENCE:      €{difference:>15,.2f}")

            if abs(difference) < 0.01:
                print(f"\n  ✅ BALANCE SHEET IS BALANCED IN XBRL FILE!")
            else:
                print(f"\n  ❌ BALANCE SHEET IS NOT BALANCED IN XBRL FILE!")
                print(f"     Discrepancy: €{difference:,.2f}")
        else:
            print(f"\n⚠️  Warning: Could not find TotaleAttivo and/or TotalePassivo tags")
            print(f"   This may be an abbreviated schema or missing aggregate totals")

        # Show detailed breakdown
        print(f"\n{'─' * 80}")
        print("DETAILED BREAKDOWN OF TAGS:")
        print(f"{'─' * 80}")

        print(f"\nATTIVO (Assets) - {len(attivo_tags)} tags found:")
        print(f"{'─' * 80}")
        attivo_sum = Decimal('0')
        for tag, value in sorted(attivo_tags, key=lambda x: x[1], reverse=True):
            if 'Totale' in tag:
                print(f"  {tag:<55} €{value:>15,.2f} [TOTAL]")
            else:
                print(f"  {tag:<55} €{value:>15,.2f}")
                if 'Totale' not in tag:
                    attivo_sum += value

        print(f"\nPASSIVO (Liabilities & Equity) - {len(passivo_tags)} tags found:")
        print(f"{'─' * 80}")
        passivo_sum = Decimal('0')
        for tag, value in sorted(passivo_tags, key=lambda x: x[1], reverse=True):
            if 'Totale' in tag:
                print(f"  {tag:<55} €{value:>15,.2f} [TOTAL]")
            else:
                print(f"  {tag:<55} €{value:>15,.2f}")
                if 'Totale' not in tag:
                    passivo_sum += value

        print(f"\n{'─' * 80}")
        print("SUMMARY OF DETAIL ITEMS (excluding aggregate totals):")
        print(f"{'─' * 80}")
        print(f"  Sum of Attivo detail items:   €{attivo_sum:>15,.2f}")
        print(f"  Sum of Passivo detail items:  €{passivo_sum:>15,.2f}")
        print(f"  {'─' * 50}")
        detail_diff = attivo_sum - passivo_sum
        print(f"  Difference in details:        €{detail_diff:>15,.2f}")

        if total_attivo is not None:
            print(f"\n{'─' * 80}")
            print("COMPARISON: Official Totals vs. Sum of Details:")
            print(f"{'─' * 80}")
            print(f"  Official TotaleAttivo:        €{total_attivo:>15,.2f}")
            print(f"  Sum of Attivo details:        €{attivo_sum:>15,.2f}")
            print(f"  Missing from details:         €{total_attivo - attivo_sum:>15,.2f}")
            print()
            print(f"  Official TotalePassivo:       €{total_passivo:>15,.2f}")
            print(f"  Sum of Passivo details:       €{passivo_sum:>15,.2f}")
            print(f"  Missing from details:         €{total_passivo - passivo_sum:>15,.2f}")

        print(f"\n{'=' * 80}\n")

if __name__ == '__main__':
    if len(sys.argv) > 1:
        xbrl_path = sys.argv[1]
    else:
        xbrl_path = 'BKPS.XBRL'

    if not Path(xbrl_path).exists():
        print(f"Error: File {xbrl_path} not found")
        sys.exit(1)

    analyze_xbrl_balance(xbrl_path)
