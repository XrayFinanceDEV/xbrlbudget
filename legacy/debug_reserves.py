"""
Debug Reserves - See exactly what's in the XBRL file
"""
from importers.xbrl_parser_enhanced import EnhancedXBRLParser
from lxml import etree
from decimal import Decimal


def debug_reserves_in_xbrl():
    """Extract and show all reserve-related tags from XBRL"""
    print("=" * 80)
    print("DEBUG: Reserve Tags in XBRL File")
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

        # Find all reserve-related tags
        reserve_keywords = ['Patrimonio', 'Riserv', 'Capitale', 'Utili', 'Perdite']
        reserve_facts = {}

        for tag, value in facts.items():
            local_name = etree.QName(tag).localname if tag.startswith('{') else tag.split(':')[-1]

            # Check if tag contains reserve keywords
            for keyword in reserve_keywords:
                if keyword in local_name:
                    reserve_facts[local_name] = value
                    break

        print(f"\n✓ Found {len(reserve_facts)} reserve-related tags:")
        print("\n" + "-" * 80)

        # Sort by value (descending)
        sorted_reserves = sorted(reserve_facts.items(), key=lambda x: x[1], reverse=True)

        total = Decimal('0')
        for tag_name, value in sorted_reserves:
            print(f"{tag_name:70s} €{value:>15,.2f}")
            total += value

        print("-" * 80)
        print(f"{'TOTAL':70s} €{total:>15,.2f}")
        print("=" * 80)

        # Check which tags match our detail_tags
        print("\n" + "=" * 80)
        print("MATCHING AGAINST V2 DETAIL_TAGS")
        print("=" * 80)

        detail_tags_config = [
            "itcc-ci:PatrimonioNettoRiservaLegale",
            "itcc-ci:PatrimonioNettoRiservaSoprapprezzo",
            "itcc-ci:PatrimonioNettoRiservaSoprapprezzoAzioni",
            "itcc-ci:PatrimonioNettoRiservaRivalutazione",
            "itcc-ci:PatrimonioNettoRiserveStatutarie",
            "itcc-ci:PatrimonioNettoAltreRiserve",
            "itcc-ci:PatrimonioNettoAltreRiserveDistintamenteIndicateTotaleAltreRiserve",
            "itcc-ci:PatrimonioNettoRiservaOperazioniCoperturaFlussiFinanziariAttesi",
            "itcc-ci:PatrimonioNettoUtiliPerditePortatiNuovo"
        ]

        matched = []
        matched_total = Decimal('0')

        for detail_tag in detail_tags_config:
            expected_local = detail_tag.split(':')[-1]

            for tag, value in facts.items():
                local_name = etree.QName(tag).localname if tag.startswith('{') else tag.split(':')[-1]

                if local_name == expected_local:
                    matched.append((expected_local, value))
                    matched_total += value
                    print(f"✓ {expected_local:70s} €{value:>15,.2f}")
                    break
            else:
                print(f"  {expected_local:70s} (not found)")

        print("-" * 80)
        print(f"{'MATCHED TOTAL':70s} €{matched_total:>15,.2f}")
        print("=" * 80)

        print(f"\n✓ Expected total: €3,161,378.00")
        print(f"✓ Matched total: €{matched_total:,.2f}")

        if matched_total == Decimal('3161378'):
            print("\n✅ Matched total is correct!")
        else:
            print(f"\n❌ Mismatch! Difference: €{abs(Decimal('3161378') - matched_total):,.2f}")

        # Now test the actual _extract_value_by_priority method
        print("\n" + "=" * 80)
        print("TESTING _extract_value_by_priority() METHOD")
        print("=" * 80)

        if 'sp12_riserve' in parser.bs_mapping_v2:
            value, matched_tag = parser._extract_value_by_priority(
                facts,
                parser.bs_mapping_v2['sp12_riserve']
            )

            print(f"\n✓ Method returned:")
            print(f"  Value: €{value:,.2f}" if value else "  Value: None")
            print(f"  Matched: {matched_tag}")

            if value != matched_total:
                print(f"\n❌ METHOD RETURNED WRONG VALUE!")
                print(f"   Expected: €{matched_total:,.2f}")
                print(f"   Got: €{value:,.2f}")
                print(f"   Difference: €{abs(matched_total - value):,.2f}")
            else:
                print(f"\n✅ Method returned correct value!")

        # Test the full mapping
        print("\n" + "=" * 80)
        print("TESTING FULL map_facts_to_fields_with_reconciliation()")
        print("=" * 80)

        bs_data, inc_data, reconciliation_info = parser.map_facts_to_fields_with_reconciliation(facts)

        sp12_value = bs_data.get('sp12_riserve', Decimal('0'))
        print(f"\n✓ sp12_riserve in bs_data: €{sp12_value:,.2f}")
        print(f"✓ Expected: €{matched_total:,.2f}")

        if sp12_value != matched_total:
            print(f"\n❌ FULL MAPPING RETURNED WRONG VALUE!")
            print(f"   Difference: €{abs(matched_total - sp12_value):,.2f}")

            # Check if v1 interfered
            print(f"\n✓ Checking priority_matches:")
            if 'sp12_riserve' in reconciliation_info.get('priority_matches', {}):
                print(f"   sp12_riserve matched via: {reconciliation_info['priority_matches']['sp12_riserve']}")
            else:
                print(f"   sp12_riserve NOT in priority_matches!")

            # Check reconciliation adjustments
            if reconciliation_info.get('reconciliation_adjustments'):
                print(f"\n✓ Reconciliation adjustments:")
                for key, adj in reconciliation_info['reconciliation_adjustments'].items():
                    print(f"   {key}: {adj}")

        else:
            print(f"\n✅ Full mapping returned correct value!")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        parser.db.close()


if __name__ == "__main__":
    debug_reserves_in_xbrl()
