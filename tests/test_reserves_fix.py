"""
Test Reserves Accumulation Fix

Tests that sp12_riserve correctly accumulates ALL reserve types
instead of stopping at first match.
"""
from importers.xbrl_parser_enhanced import EnhancedXBRLParser
from decimal import Decimal


def test_reserves_accumulation():
    """Test that all reserve types are accumulated"""
    print("=" * 80)
    print("TEST: Reserves Accumulation")
    print("=" * 80)

    parser = EnhancedXBRLParser()

    # Mock facts with multiple reserve types (from real XBRL)
    test_facts = {
        # Different reserve types
        '{http://www.xbrl.org/italy/itcc-ci}PatrimonioNettoRiservaSoprapprezzo': Decimal('3180324'),
        '{http://www.xbrl.org/italy/itcc-ci}PatrimonioNettoRiservaLegale': Decimal('19365'),
        '{http://www.xbrl.org/italy/itcc-ci}PatrimonioNettoAltreRiserve': Decimal('30222'),
        '{http://www.xbrl.org/italy/itcc-ci}PatrimonioNettoUtiliPerditePortatiNuovo': Decimal('-68533'),
    }

    # Test sp12_riserve accumulation
    if 'sp12_riserve' in parser.bs_mapping_v2:
        value, matched_tag = parser._extract_value_by_priority(
            test_facts,
            parser.bs_mapping_v2['sp12_riserve']
        )

        print(f"\n✓ sp12_riserve configuration:")
        config = parser.bs_mapping_v2['sp12_riserve']
        if 'accumulate_all' in config:
            print(f"  accumulate_all: {config['accumulate_all']}")
        if 'detail_tags' in config:
            print(f"  detail_tags: {len(config['detail_tags'])} tags")

        print(f"\n✓ Extracted value: €{value:,.2f}" if value else "  Value: None")
        print(f"✓ Matched: {matched_tag}")

        # Expected total: 3,180,324 + 19,365 + 30,222 - 68,533 = 3,161,378
        expected = Decimal('3161378')

        print(f"\n✓ Expected total: €{expected:,.2f}")
        print(f"✓ Actual total: €{value:,.2f}" if value else "  Actual: None")

        if value == expected:
            print("\n✅ PASS: All reserves accumulated correctly!")
            return True
        else:
            print(f"\n❌ FAIL: Expected €{expected:,.2f}, got €{value:,.2f}" if value else "  Got: None")
            print(f"   Difference: €{abs(expected - value):,.2f}" if value else "  No value")
            return False
    else:
        print("❌ FAIL: sp12_riserve not found in v2 mappings")
        return False

    parser.db.close()


def test_full_xbrl_import():
    """Test importing real XBRL file with reserves fix"""
    print("\n" + "=" * 80)
    print("TEST: Full XBRL Import with Reserves")
    print("=" * 80)

    import os
    xbrl_file = "ISTANZA02353550391.xbrl"

    if not os.path.exists(xbrl_file):
        print(f"\n⚠ Skipping: XBRL file '{xbrl_file}' not found")
        return True

    parser = EnhancedXBRLParser()

    try:
        root = parser.parse_file(xbrl_file)
        contexts = parser.extract_contexts(root)
        facts_by_year = parser.extract_facts(root, contexts)

        year = 2024  # Use 2024 data
        if year not in facts_by_year:
            print(f"❌ FAIL: Year {year} not found in XBRL")
            return False

        facts = facts_by_year[year]

        # Map with priority-based system
        bs_data, inc_data, reconciliation_info = parser.map_facts_to_fields_with_reconciliation(facts)

        print(f"\n✓ Year: {year}")
        print(f"✓ Balance sheet fields mapped: {len(bs_data)}")

        # Check equity section
        print(f"\n✓ Patrimonio Netto (Equity) Section:")
        capitale = bs_data.get('sp11_capitale', Decimal('0'))
        riserve = bs_data.get('sp12_riserve', Decimal('0'))
        utile = bs_data.get('sp13_utile_perdita', Decimal('0'))

        print(f"  sp11_capitale: €{capitale:,.2f}")
        print(f"  sp12_riserve: €{riserve:,.2f}")
        print(f"  sp13_utile_perdita: €{utile:,.2f}")

        patrimonio_netto = capitale + riserve + utile
        print(f"  Total Patrimonio Netto: €{patrimonio_netto:,.2f}")

        # Expected values from XBRL
        expected_capitale = Decimal('1100000')
        expected_riserve = Decimal('3161378')  # Sum of all reserves
        expected_utile = Decimal('10746')
        expected_patrimonio = expected_capitale + expected_riserve + expected_utile  # 4,272,124

        print(f"\n✓ Expected values:")
        print(f"  Capitale: €{expected_capitale:,.2f}")
        print(f"  Riserve: €{expected_riserve:,.2f}")
        print(f"  Utile: €{expected_utile:,.2f}")
        print(f"  Total: €{expected_patrimonio:,.2f}")

        # Check if values match
        success = True
        if capitale != expected_capitale:
            print(f"\n❌ Capitale mismatch: expected €{expected_capitale:,.2f}, got €{capitale:,.2f}")
            success = False
        else:
            print(f"\n✅ Capitale correct")

        if riserve != expected_riserve:
            print(f"❌ Riserve mismatch: expected €{expected_riserve:,.2f}, got €{riserve:,.2f}")
            print(f"   Difference: €{abs(expected_riserve - riserve):,.2f}")
            success = False
        else:
            print(f"✅ Riserve correct (accumulated all types)")

        if utile != expected_utile:
            print(f"❌ Utile mismatch: expected €{expected_utile:,.2f}, got €{utile:,.2f}")
            success = False
        else:
            print(f"✅ Utile correct")

        if patrimonio_netto != expected_patrimonio:
            print(f"\n❌ Total Patrimonio Netto mismatch:")
            print(f"   Expected: €{expected_patrimonio:,.2f}")
            print(f"   Got: €{patrimonio_netto:,.2f}")
            print(f"   Difference: €{abs(expected_patrimonio - patrimonio_netto):,.2f}")
            success = False
        else:
            print(f"\n✅ Total Patrimonio Netto correct: €{patrimonio_netto:,.2f}")

        # Show which tag was matched for reserves
        if 'priority_matches' in reconciliation_info:
            reserves_match = reconciliation_info['priority_matches'].get('sp12_riserve')
            if reserves_match:
                print(f"\n✓ sp12_riserve matched via: {reserves_match}")

        return success

    except Exception as e:
        print(f"\n❌ FAIL: Error during import: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        parser.db.close()


def main():
    """Run all tests"""
    print("\n" + "=" * 80)
    print("RESERVES ACCUMULATION FIX - TESTS")
    print("=" * 80)

    results = []

    try:
        results.append(("Reserves Accumulation Test", test_reserves_accumulation()))
    except Exception as e:
        print(f"❌ Reserves Accumulation Test FAILED: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Reserves Accumulation Test", False))

    try:
        results.append(("Full XBRL Import Test", test_full_xbrl_import()))
    except Exception as e:
        print(f"❌ Full XBRL Import Test FAILED: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Full XBRL Import Test", False))

    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed! Reserves fix working correctly.")
        print("\nPatrimonio Netto should now show:")
        print("  - Capitale: €1,100,000")
        print("  - Riserve: €3,161,378 (accumulated from all reserve types)")
        print("  - Utile: €10,746")
        print("  - TOTAL: €4,272,124 ✓")
    else:
        print(f"\n⚠ {total - passed} test(s) failed. Review implementation.")


if __name__ == "__main__":
    main()
