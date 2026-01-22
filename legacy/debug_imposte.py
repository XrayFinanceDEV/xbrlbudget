"""
Debug Imposte sul reddito - Find the correct XBRL tag
"""
from importers.xbrl_parser_enhanced import EnhancedXBRLParser
from lxml import etree
from decimal import Decimal


def debug_imposte_in_xbrl():
    """Extract and show all tax-related tags from XBRL"""
    print("=" * 80)
    print("DEBUG: Imposte (Tax) Tags in XBRL File")
    print("=" * 80)

    import os
    xbrl_file = "ISTANZA02353550391.xbrl"

    if not os.path.exists(xbrl_file):
        print(f"\n❌ XBRL file '{xbrl_file}' not found")
        return

    parser = EnhancedXBRLParser()

    try:
        root = parser.parse_file(xbrl_file)
        contexts = parser.extract_contexts(root)
        facts_by_year = parser.extract_facts(root, contexts)

        year = 2024
        if year not in facts_by_year:
            print(f"❌ Year {year} not found")
            return

        facts = facts_by_year[year]

        print(f"\n✓ Total facts for {year}: {len(facts)}")

        # Find all tax-related tags
        tax_keywords = ['Impost', 'Tass', 'Fiscal']
        tax_facts = {}

        for tag, value in facts.items():
            local_name = etree.QName(tag).localname if tag.startswith('{') else tag.split(':')[-1]

            # Check if tag contains tax keywords
            for keyword in tax_keywords:
                if keyword in local_name:
                    tax_facts[local_name] = value
                    break

        print(f"\n✓ Found {len(tax_facts)} tax-related tags:")
        print("\n" + "-" * 80)

        # Sort by value (descending)
        sorted_taxes = sorted(tax_facts.items(), key=lambda x: abs(x[1]), reverse=True)

        for tag_name, value in sorted_taxes:
            print(f"{tag_name:70s} €{value:>15,.2f}")

        print("-" * 80)
        print("=" * 80)

        # Look specifically for tags around 101,867
        print("\n" + "=" * 80)
        print("LOOKING FOR €101,867 VALUE")
        print("=" * 80)

        target = Decimal('101867')
        tolerance = Decimal('100')

        for tag, value in facts.items():
            local_name = etree.QName(tag).localname if tag.startswith('{') else tag.split(':')[-1]

            if abs(value - target) <= tolerance:
                print(f"\n✓ FOUND MATCH!")
                print(f"  Tag: {local_name}")
                print(f"  Value: €{value:,.2f}")
                print(f"  Full tag: {tag}")

        # Check current mapping
        print("\n" + "=" * 80)
        print("CURRENT V2 MAPPING FOR ce20_imposte")
        print("=" * 80)

        if 'ce20_imposte' in parser.inc_mapping_v2:
            config = parser.inc_mapping_v2['ce20_imposte']
            print(f"\n✓ ce20_imposte configuration:")
            for key, value in config.items():
                if key.startswith('priority_'):
                    print(f"  {key}: {value}")

        # Test extraction
        print("\n" + "=" * 80)
        print("TESTING _extract_value_by_priority() FOR ce20_imposte")
        print("=" * 80)

        if 'ce20_imposte' in parser.inc_mapping_v2:
            value, matched_tag = parser._extract_value_by_priority(
                facts,
                parser.inc_mapping_v2['ce20_imposte']
            )

            print(f"\n✓ Method returned:")
            print(f"  Value: €{value:,.2f}" if value else "  Value: None")
            print(f"  Matched: {matched_tag}")

            if value == target:
                print(f"\n✅ Correct value extracted!")
            else:
                print(f"\n❌ WRONG VALUE!")
                print(f"   Expected: €{target:,.2f}")
                print(f"   Got: €{value:,.2f}" if value else "   Got: None")

        # Test full mapping
        print("\n" + "=" * 80)
        print("TESTING FULL MAPPING")
        print("=" * 80)

        bs_data, inc_data, reconciliation_info = parser.map_facts_to_fields_with_reconciliation(facts)

        ce20_value = inc_data.get('ce20_imposte', Decimal('0'))
        print(f"\n✓ ce20_imposte in inc_data: €{ce20_value:,.2f}")
        print(f"✓ Expected: €{target:,.2f}")

        if ce20_value == target:
            print(f"\n✅ Full mapping correct!")
        else:
            print(f"\n❌ Full mapping wrong!")
            print(f"   Difference: €{abs(target - ce20_value):,.2f}")

            # Check priority matches
            if 'priority_matches' in reconciliation_info:
                if 'ce20_imposte' in reconciliation_info['priority_matches']:
                    print(f"\n✓ ce20_imposte matched via: {reconciliation_info['priority_matches']['ce20_imposte']}")
                else:
                    print(f"\n⚠ ce20_imposte NOT in priority_matches!")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        parser.db.close()


if __name__ == "__main__":
    debug_imposte_in_xbrl()
