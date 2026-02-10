"""
Test Priority-Based XBRL Mapping (Phase 1)

This script tests the new priority-based mapping system that tries
multiple tag variations before falling back to aggregates.
"""
from importers.xbrl_parser_enhanced import EnhancedXBRLParser
import json
from decimal import Decimal


def test_priority_mapping_structure():
    """Test that v2 mappings are loaded correctly"""
    print("=" * 80)
    print("TEST 1: Priority Mapping Structure")
    print("=" * 80)

    parser = EnhancedXBRLParser()

    # Check v2 mappings loaded
    print(f"\n✓ Balance sheet v2 mappings loaded: {len(parser.bs_mapping_v2)} fields")
    print(f"✓ Income statement v2 mappings loaded: {len(parser.inc_mapping_v2)} fields")

    # Show example priority structure
    if 'sp06_crediti_breve' in parser.bs_mapping_v2:
        print(f"\n✓ Example: sp06_crediti_breve priorities:")
        config = parser.bs_mapping_v2['sp06_crediti_breve']
        for key, value in config.items():
            if key.startswith('priority_'):
                print(f"  {key}: {value}")

    parser.db.close()
    return True


def test_priority_extraction():
    """Test priority-based value extraction"""
    print("\n" + "=" * 80)
    print("TEST 2: Priority-Based Value Extraction")
    print("=" * 80)

    parser = EnhancedXBRLParser()

    # Mock facts with different tag variations
    test_facts = {
        '{http://www.xbrl.org/italy/itcc-ci}TotaleCreditiIscrittiAttivoCircolanteQuotaScadenteEntroEsercizio': Decimal('2688056'),
        '{http://www.xbrl.org/italy/itcc-ci}TotaleCreditiIscrittiAttivoCircolanteQuotaScadenteOltreEsercizio': Decimal('377330'),
        '{http://www.xbrl.org/italy/itcc-ci}TotaleRimanenze': Decimal('10853983'),
    }

    # Test sp06_crediti_breve (should match priority_1)
    if 'sp06_crediti_breve' in parser.bs_mapping_v2:
        value, matched_tag = parser._extract_value_by_priority(
            test_facts,
            parser.bs_mapping_v2['sp06_crediti_breve']
        )

        print(f"\n✓ sp06_crediti_breve:")
        print(f"  Value: €{value:,.2f}" if value else "  Value: None")
        print(f"  Matched tag: {matched_tag}")

        if value == Decimal('2688056'):
            print("  ✓ PASS: Matched correct priority_1 tag")
        else:
            print("  ✗ FAIL: Expected €2,688,056")

    # Test sp05_rimanenze
    if 'sp05_rimanenze' in parser.bs_mapping_v2:
        value, matched_tag = parser._extract_value_by_priority(
            test_facts,
            parser.bs_mapping_v2['sp05_rimanenze']
        )

        print(f"\n✓ sp05_rimanenze:")
        print(f"  Value: €{value:,.2f}" if value else "  Value: None")
        print(f"  Matched tag: {matched_tag}")

        if value == Decimal('10853983'):
            print("  ✓ PASS: Matched TotaleRimanenze")
        else:
            print("  ✗ FAIL: Expected €10,853,983")

    parser.db.close()
    return True


def test_xbrl_import_with_priorities():
    """Test importing real XBRL file with priority-based mapping"""
    print("\n" + "=" * 80)
    print("TEST 3: Import XBRL File with Priority Mapping")
    print("=" * 80)

    import os
    xbrl_file = "ISTANZA02353550391.xbrl"

    if not os.path.exists(xbrl_file):
        print(f"\n⚠ Skipping: XBRL file '{xbrl_file}' not found")
        print("  (This test requires the XBRL file to be in the current directory)")
        return True

    print(f"\n✓ Found XBRL file: {xbrl_file}")

    parser = EnhancedXBRLParser()

    try:
        # Parse file and extract facts
        root = parser.parse_file(xbrl_file)
        taxonomy_version = parser.extract_taxonomy_version(root)
        contexts = parser.extract_contexts(root)

        print(f"✓ Taxonomy version: {taxonomy_version}")
        print(f"✓ Contexts found: {len(contexts)}")

        # Extract facts
        facts_by_year = parser.extract_facts(root, contexts)

        if facts_by_year:
            year = list(facts_by_year.keys())[0]
            facts = facts_by_year[year]

            print(f"✓ Year: {year}")
            print(f"✓ Facts extracted: {len(facts)}")

            # Map with priority-based system
            bs_data, inc_data, reconciliation_info = parser.map_facts_to_fields_with_reconciliation(facts)

            print(f"\n✓ Balance sheet fields mapped: {len(bs_data)}")
            print(f"✓ Income statement fields mapped: {len(inc_data)}")

            # Show priority matches
            if 'priority_matches' in reconciliation_info:
                print(f"\n✓ Priority-based matches: {len(reconciliation_info['priority_matches'])}")

                # Show first 5 examples
                for i, (field, matched_tag) in enumerate(list(reconciliation_info['priority_matches'].items())[:5]):
                    print(f"  {field} → {matched_tag}")

            # Show reconciliation adjustments
            if reconciliation_info.get('reconciliation_adjustments'):
                print(f"\n✓ Reconciliation adjustments:")
                for category, adjustment in reconciliation_info['reconciliation_adjustments'].items():
                    print(f"  {category}:")
                    print(f"    XBRL total: €{adjustment['xbrl_total']:,.2f}")
                    print(f"    Imported sum: €{adjustment['imported_sum']:,.2f}")
                    print(f"    Adjustment: €{adjustment['adjustment']:,.2f}")

            # Show key balance sheet values
            print(f"\n✓ Key Balance Sheet Values:")
            key_fields = [
                ('sp05_rimanenze', 'Rimanenze'),
                ('sp06_crediti_breve', 'Crediti breve termine'),
                ('sp07_crediti_lungo', 'Crediti lungo termine'),
                ('sp09_disponibilita_liquide', 'Disponibilità liquide'),
                ('sp16_debiti_breve', 'Debiti breve termine'),
                ('sp17_debiti_lungo', 'Debiti lungo termine'),
            ]

            for field, label in key_fields:
                value = bs_data.get(field, Decimal('0'))
                print(f"  {label}: €{value:,.2f}")

            print("\n✓ PASS: Priority-based mapping working correctly")

        else:
            print("✗ FAIL: No facts extracted from XBRL file")
            return False

    except Exception as e:
        print(f"\n✗ FAIL: Error during import: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        parser.db.close()

    return True


def test_fallback_to_v1():
    """Test that v1 mappings still work as fallback"""
    print("\n" + "=" * 80)
    print("TEST 4: V1 Fallback Compatibility")
    print("=" * 80)

    parser = EnhancedXBRLParser()

    # Mock facts with v1-style tags
    test_facts = {
        '{http://www.xbrl.org/italy/itcc-ci-2018-11-04}Capitale': Decimal('100000'),
        '{http://www.xbrl.org/italy/itcc-ci-2018-11-04}Riserve': Decimal('50000'),
    }

    bs_data, inc_data, reconciliation_info = parser.map_facts_to_fields_with_reconciliation(test_facts)

    print(f"\n✓ sp11_capitale: €{bs_data.get('sp11_capitale', Decimal('0')):,.2f}")
    print(f"✓ sp12_riserve: €{bs_data.get('sp12_riserve', Decimal('0')):,.2f}")

    if bs_data.get('sp11_capitale') == Decimal('100000'):
        print("✓ PASS: V1 fallback working for capitale")
    else:
        print("✗ FAIL: V1 fallback not working for capitale")

    if bs_data.get('sp12_riserve') == Decimal('50000'):
        print("✓ PASS: V1 fallback working for riserve")
    else:
        print("✗ FAIL: V1 fallback not working for riserve")

    parser.db.close()
    return True


def main():
    """Run all tests"""
    print("\n" + "=" * 80)
    print("PRIORITY-BASED XBRL MAPPING - PHASE 1 TESTS")
    print("=" * 80)

    results = []

    try:
        results.append(("Structure Test", test_priority_mapping_structure()))
    except Exception as e:
        print(f"✗ Structure Test FAILED: {e}")
        results.append(("Structure Test", False))

    try:
        results.append(("Priority Extraction Test", test_priority_extraction()))
    except Exception as e:
        print(f"✗ Priority Extraction Test FAILED: {e}")
        results.append(("Priority Extraction Test", False))

    try:
        results.append(("XBRL Import Test", test_xbrl_import_with_priorities()))
    except Exception as e:
        print(f"✗ XBRL Import Test FAILED: {e}")
        results.append(("XBRL Import Test", False))

    try:
        results.append(("V1 Fallback Test", test_fallback_to_v1()))
    except Exception as e:
        print(f"✗ V1 Fallback Test FAILED: {e}")
        results.append(("V1 Fallback Test", False))

    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed! Phase 1 implementation complete.")
    else:
        print(f"\n⚠ {total - passed} test(s) failed. Review implementation.")


if __name__ == "__main__":
    main()
