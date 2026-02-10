"""
Test Enhanced XBRL Parser with Reconciliation
"""
from database.db import init_db, SessionLocal, drop_all
from database.models import Company, FinancialYear
from importers.xbrl_parser_enhanced import import_xbrl_file_enhanced
import json


def test_enhanced_parser():
    """Test enhanced XBRL parser with BKPS file"""

    print("=" * 80)
    print("ENHANCED XBRL PARSER TEST - WITH RECONCILIATION")
    print("=" * 80)

    # Initialize database
    print("\n1. Initializing database...")
    drop_all()
    init_db()

    db = SessionLocal()

    try:
        # Import XBRL with enhanced parser
        print("\n2. Importing BKPS.XBRL with reconciliation...")
        xbrl_path = "BKPS.XBRL"

        result = import_xbrl_file_enhanced(
            file_path=xbrl_path,
            create_company=True
        )

        print(f"   ✓ Import successful!")
        print(f"     Company: {result['company_name']} (ID: {result['company_id']})")
        print(f"     Years imported: {result['years']}")

        # Display reconciliation info
        print("\n3. RECONCILIATION DETAILS:")
        print("=" * 80)

        for year, recon_info in result['reconciliation_info'].items():
            print(f"\n   Year {year}:")
            print(f"   {'-' * 76}")

            # Show aggregate totals captured
            if recon_info['aggregate_totals']:
                print(f"\n   Aggregate Totals Captured:")
                for tag, value in recon_info['aggregate_totals'].items():
                    print(f"     {tag:<40} €{value:>15,.2f}")

            # Show reconciliation adjustments
            if recon_info['reconciliation_adjustments']:
                print(f"\n   Reconciliation Adjustments Made:")
                for category, adj in recon_info['reconciliation_adjustments'].items():
                    print(f"\n     {category.upper()}:")
                    print(f"       XBRL Official Total:    €{adj['xbrl_total']:>15,.2f}")
                    print(f"       Sum of Imported Items:  €{adj['imported_sum']:>15,.2f}")
                    print(f"       Adjustment Applied:     €{adj['adjustment']:>15,.2f}")
                    print(f"       Added to field:         {adj['applied_to']}")

            # Show unmapped tags (if any)
            if recon_info['unmapped_tags']:
                print(f"\n   Unmapped Tags (not imported):")
                for unmapped in recon_info['unmapped_tags'][:10]:  # Show first 10
                    print(f"     {unmapped['tag']:<50} €{unmapped['value']:>12,.2f}")
                if len(recon_info['unmapped_tags']) > 10:
                    print(f"     ... and {len(recon_info['unmapped_tags']) - 10} more")

        # Verify imported data
        print("\n" + "=" * 80)
        print("4. VERIFICATION - Balance Sheet Check:")
        print("=" * 80)

        company_id = result['company_id']
        years = result['years']

        for year in years:
            fy = db.query(FinancialYear).filter(
                FinancialYear.company_id == company_id,
                FinancialYear.year == year
            ).first()

            if not fy:
                print(f"   ❌ ERROR: Financial year {year} not found!")
                continue

            bs = fy.balance_sheet

            print(f"\n   Year {year}:")
            print(f"     Total Assets:                  €{bs.total_assets:>15,.2f}")
            print(f"     Total Liabilities & Equity:    €{bs.total_liabilities:>15,.2f}")
            print(f"     {'-' * 60}")

            difference = bs.total_assets - bs.total_liabilities

            if abs(difference) < 0.01:
                print(f"     BALANCE CHECK:                 ✅ BALANCED!")
                print(f"     Difference:                    €{difference:>15,.2f}")
            else:
                print(f"     BALANCE CHECK:                 ❌ NOT BALANCED")
                print(f"     Difference:                    €{difference:>15,.2f}")

            print(f"\n     Breakdown:")
            print(f"       Fixed Assets:                €{bs.fixed_assets:>15,.2f}")
            print(f"       Current Assets:              €{bs.current_assets:>15,.2f}")
            print(f"       Credits (short):             €{bs.sp06_crediti_breve:>15,.2f}")
            print(f"       Credits (long):              €{bs.sp07_crediti_lungo:>15,.2f}")
            print(f"       Cash:                        €{bs.sp09_disponibilita_liquide:>15,.2f}")
            print()
            print(f"       Total Equity:                €{bs.total_equity:>15,.2f}")
            print(f"       Total Debt:                  €{bs.total_debt:>15,.2f}")
            print(f"       Debt (short):                €{bs.sp16_debiti_breve:>15,.2f}")
            print(f"       Debt (long):                 €{bs.sp17_debiti_lungo:>15,.2f}")

        print("\n" + "=" * 80)
        print("✅ TEST COMPLETED SUCCESSFULLY!")
        print("=" * 80)

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == '__main__':
    test_enhanced_parser()
