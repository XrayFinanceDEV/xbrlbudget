"""
Check XBRL Mapping Completeness
This script analyzes an XBRL file to identify unmapped tags
"""
from lxml import etree
from pathlib import Path
import json
import sys

def load_taxonomy_mapping():
    """Load taxonomy mapping from JSON"""
    mapping_path = Path(__file__).parent / 'data' / 'taxonomy_mapping.json'
    with open(mapping_path, 'r', encoding='utf-8') as f:
        taxonomy = json.load(f)
        return taxonomy['balance_sheet_mapping'], taxonomy['income_statement_mapping']

def analyze_xbrl_file(xbrl_path):
    """Analyze XBRL file and report on mapping coverage"""

    # Parse XBRL
    parser = etree.XMLParser(remove_blank_text=True, encoding='utf-8')
    tree = etree.parse(xbrl_path, parser)
    root = tree.getroot()

    # Load mappings
    bs_mapping, inc_mapping = load_taxonomy_mapping()

    # Combine all mapped tags (get local names)
    mapped_tags = set()
    for xbrl_tag in list(bs_mapping.keys()) + list(inc_mapping.keys()):
        local_name = xbrl_tag.split(':')[-1]
        mapped_tags.add(local_name)

    # Find all numeric facts in XBRL
    numeric_facts = {}
    all_tags = set()

    for elem in root.iter():
        # Skip if no contextRef (not a fact)
        if elem.get('contextRef') is None:
            continue

        # Get local name
        try:
            local_name = etree.QName(elem).localname
        except:
            continue

        # Try to parse as number
        if elem.text:
            try:
                value = float(elem.text.replace(',', '.'))
                all_tags.add(local_name)

                # Check if mapped
                is_mapped = local_name in mapped_tags

                if local_name not in numeric_facts:
                    numeric_facts[local_name] = {
                        'count': 0,
                        'sample_value': value,
                        'mapped': is_mapped,
                        'contexts': []
                    }

                numeric_facts[local_name]['count'] += 1
                numeric_facts[local_name]['contexts'].append(elem.get('contextRef'))
            except:
                pass

    # Report results
    print("=" * 80)
    print("XBRL MAPPING ANALYSIS")
    print("=" * 80)
    print(f"\nFile: {xbrl_path}")
    print(f"Total numeric tags found: {len(numeric_facts)}")
    print(f"Mapped tags in taxonomy: {len(mapped_tags)}")

    # Find unmapped tags
    unmapped = []
    mapped = []

    for tag, info in numeric_facts.items():
        if info['mapped']:
            mapped.append((tag, info))
        else:
            unmapped.append((tag, info))

    print(f"\n✓ Mapped tags found: {len(mapped)}")
    print(f"✗ Unmapped tags found: {len(unmapped)}")

    if unmapped:
        print("\n" + "=" * 80)
        print("UNMAPPED TAGS (these values are NOT being imported):")
        print("=" * 80)
        for tag, info in sorted(unmapped):
            print(f"\n  Tag: {tag}")
            print(f"  Occurrences: {info['count']}")
            print(f"  Sample value: {info['sample_value']:,.2f}")
            print(f"  Contexts: {', '.join(info['contexts'][:3])}")

    if mapped:
        print("\n" + "=" * 80)
        print("MAPPED TAGS (these values ARE being imported):")
        print("=" * 80)
        for tag, info in sorted(mapped):
            print(f"\n  Tag: {tag}")
            print(f"  Occurrences: {info['count']}")
            print(f"  Sample value: {info['sample_value']:,.2f}")

    # Check for potential aggregation issues
    print("\n" + "=" * 80)
    print("AGGREGATION CHECK:")
    print("=" * 80)

    # Calculate totals from sample_data.xbrl if that's what we're analyzing
    contexts = root.findall('.//{http://www.xbrl.org/2003/instance}context')

    for ctx in contexts[:1]:  # Just check first context
        ctx_id = ctx.get('id')
        print(f"\nContext: {ctx_id}")

        # Calculate asset total
        asset_total = 0
        liability_total = 0

        # Assets (sp01-sp10)
        asset_fields = [
            'CreditiVersoSociPerVersAmDoControllate',
            'ImmobilizzazioniImmateriali',
            'ImmobilizzazioniMateriali',
            'ImmobilizzazioniFinanziarie',
            'Rimanenze',
            'CreditiEsigibiliEntroEsSucc',
            'CreditiEsigibiliOltreEsSucc',
            'AttivitaFinanziarieNonImmob',
            'DisponibilitaLiquide',
            'RateiERiscontiAttivi'
        ]

        # Liabilities (sp11-sp18)
        liability_fields = [
            'Capitale',
            'Riserve',
            'UtilePerdita',
            'FondiPerRischiEOneri',
            'TFR',
            'DebitiEsigibiliEntroEsSucc',
            'DebitiEsigibiliOltreEsSucc',
            'RateiERiscontiPassivi'
        ]

        print("\n  Assets:")
        for field in asset_fields:
            if field in numeric_facts:
                # Find value for this context
                for elem in root.iter():
                    try:
                        if etree.QName(elem).localname == field and elem.get('contextRef') == ctx_id:
                            value = float(elem.text)
                            asset_total += value
                            status = "✓" if field in mapped_tags else "✗"
                            print(f"    {status} {field}: {value:,.0f}")
                            break
                    except:
                        pass

        print(f"\n  Total Assets: {asset_total:,.0f}")

        print("\n  Liabilities & Equity:")
        for field in liability_fields:
            if field in numeric_facts:
                for elem in root.iter():
                    try:
                        if etree.QName(elem).localname == field and elem.get('contextRef') == ctx_id:
                            value = float(elem.text)
                            liability_total += value
                            status = "✓" if field in mapped_tags else "✗"
                            print(f"    {status} {field}: {value:,.0f}")
                            break
                    except:
                        pass

        print(f"\n  Total Liabilities & Equity: {liability_total:,.0f}")
        print(f"\n  DIFFERENCE (Asset - Liability): {asset_total - liability_total:,.0f}")

        if abs(asset_total - liability_total) > 0.01:
            print("  ⚠️  WARNING: Balance sheet does not balance!")
        else:
            print("  ✓ Balance sheet balances correctly")

if __name__ == '__main__':
    if len(sys.argv) > 1:
        xbrl_path = sys.argv[1]
    else:
        xbrl_path = 'sample_data.xbrl'

    if not Path(xbrl_path).exists():
        print(f"Error: File {xbrl_path} not found")
        sys.exit(1)

    analyze_xbrl_file(xbrl_path)
