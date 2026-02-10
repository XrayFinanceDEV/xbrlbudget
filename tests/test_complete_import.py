"""
Complete XBRL Import Test - Verify Both Balance Sheet and Income Statement
"""
from importers.xbrl_parser_enhanced import EnhancedXBRLParser
from decimal import Decimal


def test_complete_xbrl_import():
    """Test complete XBRL import with all fixes"""
    print("=" * 80)
    print("COMPLETE XBRL IMPORT TEST")
    print("=" * 80)

    import os
    xbrl_file = "ISTANZA02353550391.xbrl"

    if not os.path.exists(xbrl_file):
        print(f"\n❌ XBRL file '{xbrl_file}' not found")
        return False

    parser = EnhancedXBRLParser()

    try:
        root = parser.parse_file(xbrl_file)
        contexts = parser.extract_contexts(root)
        facts_by_year = parser.extract_facts(root, contexts)

        year = 2024
        if year not in facts_by_year:
            print(f"❌ Year {year} not found")
            return False

        facts = facts_by_year[year]

        # Map with priority-based system
        bs_data, inc_data, reconciliation_info = parser.map_facts_to_fields_with_reconciliation(facts)

        print(f"\n✓ Year: {year}")
        print(f"✓ Balance sheet fields mapped: {len(bs_data)}")
        print(f"✓ Income statement fields mapped: {len(inc_data)}")

        # Test Balance Sheet - Patrimonio Netto (Equity)
        print("\n" + "=" * 80)
        print("BALANCE SHEET - PATRIMONIO NETTO (EQUITY)")
        print("=" * 80)

        capitale = bs_data.get('sp11_capitale', Decimal('0'))
        riserve = bs_data.get('sp12_riserve', Decimal('0'))
        utile = bs_data.get('sp13_utile_perdita', Decimal('0'))
        patrimonio_netto = capitale + riserve + utile

        print(f"\n  Capitale: €{capitale:,.2f}")
        print(f"  Riserve: €{riserve:,.2f}")
        print(f"  Utile (perdita): €{utile:,.2f}")
        print(f"  TOTAL Patrimonio Netto: €{patrimonio_netto:,.2f}")

        # Expected values
        expected_capitale = Decimal('1100000')
        expected_riserve = Decimal('3161378')
        expected_utile = Decimal('10746')
        expected_patrimonio = expected_capitale + expected_riserve + expected_utile

        success_bs = True

        if capitale != expected_capitale:
            print(f"\n❌ Capitale wrong: expected €{expected_capitale:,.2f}, got €{capitale:,.2f}")
            success_bs = False
        else:
            print(f"\n✅ Capitale correct")

        if riserve != expected_riserve:
            print(f"❌ Riserve wrong: expected €{expected_riserve:,.2f}, got €{riserve:,.2f}")
            success_bs = False
        else:
            print(f"✅ Riserve correct (accumulated all types)")

        if utile != expected_utile:
            print(f"❌ Utile wrong: expected €{expected_utile:,.2f}, got €{utile:,.2f}")
            success_bs = False
        else:
            print(f"✅ Utile correct")

        if patrimonio_netto != expected_patrimonio:
            print(f"❌ Total Patrimonio Netto wrong: expected €{expected_patrimonio:,.2f}, got €{patrimonio_netto:,.2f}")
            success_bs = False
        else:
            print(f"✅ Total Patrimonio Netto correct: €{patrimonio_netto:,.2f}")

        # Test Income Statement - Imposte sul reddito
        print("\n" + "=" * 80)
        print("INCOME STATEMENT - IMPOSTE SUL REDDITO (TAXES)")
        print("=" * 80)

        imposte = inc_data.get('ce20_imposte', Decimal('0'))
        expected_imposte = Decimal('101867')

        print(f"\n  Imposte sul reddito: €{imposte:,.2f}")
        print(f"  Expected: €{expected_imposte:,.2f}")

        success_inc = True

        if imposte != expected_imposte:
            print(f"\n❌ Imposte wrong: expected €{expected_imposte:,.2f}, got €{imposte:,.2f}")
            print(f"   Difference: €{abs(expected_imposte - imposte):,.2f}")
            success_inc = False
        else:
            print(f"\n✅ Imposte correct: €{imposte:,.2f}")

        # Show other key income statement values
        print("\n" + "=" * 80)
        print("OTHER KEY INCOME STATEMENT VALUES")
        print("=" * 80)

        key_inc_fields = [
            ('ce01_ricavi_vendite', 'Ricavi vendite'),
            ('ce05_materie_prime', 'Materie prime'),
            ('ce06_servizi', 'Servizi'),
            ('ce08_costi_personale', 'Costi personale'),
            ('ce09_ammortamenti', 'Ammortamenti'),
            ('ce15_oneri_finanziari', 'Oneri finanziari'),
            ('ce20_imposte', 'Imposte sul reddito'),
        ]

        print()
        for field, label in key_inc_fields:
            value = inc_data.get(field, Decimal('0'))
            print(f"  {label}: €{value:,.2f}")

        # Show priority matches
        print("\n" + "=" * 80)
        print("PRIORITY MATCHES")
        print("=" * 80)

        if 'priority_matches' in reconciliation_info:
            print(f"\n✓ Total priority-based matches: {len(reconciliation_info['priority_matches'])}")

            # Show key matches
            key_matches = ['sp12_riserve', 'ce20_imposte']
            for field in key_matches:
                if field in reconciliation_info['priority_matches']:
                    matched = reconciliation_info['priority_matches'][field]
                    print(f"  {field}: {matched}")

        # Final result
        print("\n" + "=" * 80)
        print("TEST RESULT")
        print("=" * 80)

        if success_bs and success_inc:
            print("\n✅ ALL TESTS PASSED!")
            print("\n✓ Balance Sheet correct:")
            print(f"  - Capitale: €{capitale:,.2f}")
            print(f"  - Riserve: €{riserve:,.2f} (accumulated 6 types)")
            print(f"  - Utile: €{utile:,.2f}")
            print(f"  - TOTAL: €{patrimonio_netto:,.2f}")
            print("\n✓ Income Statement correct:")
            print(f"  - Imposte sul reddito: €{imposte:,.2f}")
            return True
        else:
            print("\n❌ SOME TESTS FAILED!")
            if not success_bs:
                print("  - Balance Sheet (Patrimonio Netto) has errors")
            if not success_inc:
                print("  - Income Statement (Imposte) has errors")
            return False

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        parser.db.close()


if __name__ == "__main__":
    success = test_complete_xbrl_import()
    exit(0 if success else 1)
