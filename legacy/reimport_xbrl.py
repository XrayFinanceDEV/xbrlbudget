"""
Re-import ISTANZA XBRL file to database
"""
from importers.xbrl_parser_enhanced import import_xbrl_file_enhanced
import json


def main():
    print("=" * 80)
    print("RE-IMPORTING ISTANZA02353550391.xbrl")
    print("=" * 80)

    xbrl_file = "ISTANZA02353550391.xbrl"

    try:
        print(f"\n✓ Importing {xbrl_file}...")

        result = import_xbrl_file_enhanced(
            file_path=xbrl_file,
            company_id=None,  # Will find by tax_id or create new
            create_company=True
        )

        print(f"\n✅ IMPORT SUCCESSFUL!")
        print(f"\n📊 Results:")
        print(f"   Company: {result['company_name']}")
        print(f"   Tax ID: {result['tax_id']}")
        print(f"   Company ID: {result['company_id']}")
        print(f"   Taxonomy: {result['taxonomy_version']}")
        print(f"   Years imported: {result['years']}")
        print(f"   Company created: {result.get('company_created', False)}")

        # Show reconciliation info
        if 'reconciliation_info' in result:
            for year, info in result['reconciliation_info'].items():
                print(f"\n   Year {year}:")
                print(f"     Priority matches: {len(info.get('priority_matches', {}))}")

                if info.get('reconciliation_adjustments'):
                    print(f"     Reconciliation adjustments:")
                    for category, adj in info['reconciliation_adjustments'].items():
                        print(f"       {category}: {adj}")

        print(f"\n✅ Database updated with correct ISTANZA data!")
        print(f"\n⚠️ NEXT STEPS:")
        print(f"   1. Restart the backend server (FastAPI)")
        print(f"   2. Refresh the frontend")
        print(f"   3. Check the cashflow statement")

    except Exception as e:
        print(f"\n❌ IMPORT FAILED: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
