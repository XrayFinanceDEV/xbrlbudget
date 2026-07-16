#!/usr/bin/env python3
"""
Test script for hierarchical debt and depreciation import
"""
import sys
import os
from pathlib import Path

import pytest

# This file predates the current repository layout.  It is a manual integration
# diagnostic: it imports a real XBRL file and writes to the configured database.
# Never change process cwd during pytest collection and never run this diagnostic
# implicitly against the developer database.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
pytestmark = pytest.mark.skip(
    reason="legacy manual integration diagnostic; writes to the configured database"
)

from decimal import Decimal
from database.db import SessionLocal
from database.models import Company, FinancialYear, BalanceSheet, IncomeStatement
from importers.xbrl_parser import import_xbrl_file


def test_hierarchical_import():
    """Test XBRL import with hierarchical mapping"""
    print("=" * 80)
    print("TESTING: Hierarchical Debt and Depreciation Import")
    print("=" * 80)

    # Re-import the ISTANZA XBRL file
    xbrl_file = str(ROOT / "legacy" / "sample_data" / "ISTANZA02353550391.xbrl")

    if not os.path.exists(xbrl_file):
        print(f"\n❌ XBRL file not found: {xbrl_file}")
        return

    print(f"\n📥 Re-importing XBRL file: {xbrl_file}")
    print("   This will update existing data with hierarchical breakdown...")

    try:
        # Allow creating or finding existing company
        result = import_xbrl_file(xbrl_file, create_company=True)
        print(f"\n✅ Import successful!")
        print(f"   Company: {result['company_name']}")
        print(f"   Years imported: {result['years']}")
    except Exception as e:
        print(f"\n❌ Import failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return

    # Now verify the hierarchical data
    print("\n" + "=" * 80)
    print("VERIFICATION: Checking Hierarchical Fields")
    print("=" * 80)

    db = SessionLocal()

    try:
        # Find the ISTANZA company
        company = db.query(Company).filter(
            Company.tax_id == '02353550391'
        ).first()

        if not company:
            print("\n❌ Company not found with tax_id 02353550391")
            # Try finding by name
            company = db.query(Company).filter(
                Company.name.like('%PUCCI%')
            ).first()

            if company:
                print(f"✓ Found company by name: {company.name} (tax_id: {company.tax_id})")
            else:
                print("❌ Company not found by name either")
                companies = db.query(Company).all()
                print(f"Available companies: {[c.name for c in companies]}")
                return

        # Get 2023 and 2024 data
        fy_2023 = db.query(FinancialYear).filter(
            FinancialYear.company_id == company.id,
            FinancialYear.year == 2023
        ).first()

        fy_2024 = db.query(FinancialYear).filter(
            FinancialYear.company_id == company.id,
            FinancialYear.year == 2024
        ).first()

        if not fy_2023 or not fy_2024:
            print("\n❌ Financial years 2023 or 2024 not found")
            return

        bs_2023 = fy_2023.balance_sheet
        bs_2024 = fy_2024.balance_sheet
        inc_2024 = fy_2024.income_statement

        print("\n📊 BALANCE SHEET 2023 - Debt Breakdown:")
        print(f"   Total sp16 (short-term): €{bs_2023.sp16_debiti_breve:,.2f}")
        print(f"   Total sp17 (long-term):  €{bs_2023.sp17_debiti_lungo:,.2f}")

        print(f"\n   Financial Debts (Short-term):")
        print(f"      Banks (sp16a):           €{bs_2023.sp16a_debiti_banche_breve:,.2f}")
        print(f"      Other financiers (sp16b): €{bs_2023.sp16b_debiti_altri_finanz_breve:,.2f}")
        print(f"      Bonds (sp16c):           €{bs_2023.sp16c_debiti_obbligazioni_breve:,.2f}")
        fin_short_2023 = bs_2023.financial_debt_short
        print(f"      TOTAL Financial Short:   €{fin_short_2023:,.2f}")

        print(f"\n   Operating Debts (Short-term):")
        print(f"      Suppliers (sp16d):       €{bs_2023.sp16d_debiti_fornitori_breve:,.2f}")
        print(f"      Tax (sp16e):             €{bs_2023.sp16e_debiti_tributari_breve:,.2f}")
        print(f"      Social security (sp16f): €{bs_2023.sp16f_debiti_previdenza_breve:,.2f}")
        print(f"      Other (sp16g):           €{bs_2023.sp16g_altri_debiti_breve:,.2f}")
        op_short_2023 = bs_2023.operating_debt_short
        print(f"      TOTAL Operating Short:   €{op_short_2023:,.2f}")

        print(f"\n   Verification:")
        total_short_from_details_2023 = fin_short_2023 + op_short_2023
        match_2023 = abs(total_short_from_details_2023 - bs_2023.sp16_debiti_breve) < 1
        print(f"      Sum of details:          €{total_short_from_details_2023:,.2f}")
        print(f"      Aggregate sp16:          €{bs_2023.sp16_debiti_breve:,.2f}")
        print(f"      Match: {match_2023} {'✅' if match_2023 else '❌'}")

        print("\n" + "-" * 80)

        print("\n📊 BALANCE SHEET 2024 - Debt Breakdown:")
        print(f"   Total sp16 (short-term): €{bs_2024.sp16_debiti_breve:,.2f}")
        print(f"   Total sp17 (long-term):  €{bs_2024.sp17_debiti_lungo:,.2f}")

        print(f"\n   Financial Debts (Short-term):")
        print(f"      Banks (sp16a):           €{bs_2024.sp16a_debiti_banche_breve:,.2f}")
        print(f"      Other financiers (sp16b): €{bs_2024.sp16b_debiti_altri_finanz_breve:,.2f}")
        print(f"      Bonds (sp16c):           €{bs_2024.sp16c_debiti_obbligazioni_breve:,.2f}")
        fin_short_2024 = bs_2024.financial_debt_short
        print(f"      TOTAL Financial Short:   €{fin_short_2024:,.2f}")

        print(f"\n   Operating Debts (Short-term):")
        print(f"      Suppliers (sp16d):       €{bs_2024.sp16d_debiti_fornitori_breve:,.2f}")
        print(f"      Tax (sp16e):             €{bs_2024.sp16e_debiti_tributari_breve:,.2f}")
        print(f"      Social security (sp16f): €{bs_2024.sp16f_debiti_previdenza_breve:,.2f}")
        print(f"      Other (sp16g):           €{bs_2024.sp16g_altri_debiti_breve:,.2f}")
        op_short_2024 = bs_2024.operating_debt_short
        print(f"      TOTAL Operating Short:   €{op_short_2024:,.2f}")

        print(f"\n   Verification:")
        total_short_from_details_2024 = fin_short_2024 + op_short_2024
        match_2024 = abs(total_short_from_details_2024 - bs_2024.sp16_debiti_breve) < 1
        print(f"      Sum of details:          €{total_short_from_details_2024:,.2f}")
        print(f"      Aggregate sp16:          €{bs_2024.sp16_debiti_breve:,.2f}")
        print(f"      Match: {match_2024} {'✅' if match_2024 else '❌'}")

        print("\n" + "-" * 80)

        print("\n📊 DEBT CHANGES (for cashflow):")
        delta_fin_debt = bs_2024.financial_debt_total - bs_2023.financial_debt_total
        delta_op_debt = bs_2024.operating_debt_short - bs_2023.operating_debt_short

        print(f"\n   Financial Debt Change:")
        print(f"      2023: €{bs_2023.financial_debt_total:,.2f}")
        print(f"      2024: €{bs_2024.financial_debt_total:,.2f}")
        print(f"      Delta: €{delta_fin_debt:,.2f}")
        print(f"      Expected (from correct cashflow): €-411,301")
        match_fin = abs(delta_fin_debt - Decimal('-411301')) < 1000
        print(f"      Match: {match_fin} {'✅' if match_fin else '⚠️'}")

        print(f"\n   Operating Debt Change (short-term):")
        print(f"      2023: €{bs_2023.operating_debt_short:,.2f}")
        print(f"      2024: €{bs_2024.operating_debt_short:,.2f}")
        print(f"      Delta: €{delta_op_debt:,.2f}")
        print(f"      Expected (from correct cashflow): €628,975")
        match_op = abs(delta_op_debt - Decimal('628975')) < 1000
        print(f"      Match: {match_op} {'✅' if match_op else '⚠️'}")

        print("\n" + "=" * 80)

        print("\n📊 INCOME STATEMENT 2024 - Depreciation Breakdown:")
        print(f"   Total ce09 (depreciation): €{inc_2024.ce09_ammortamenti:,.2f}")

        print(f"\n   Details:")
        print(f"      Intangible (ce09a): €{inc_2024.ce09a_ammort_immateriali:,.2f}")
        print(f"      Tangible (ce09b):   €{inc_2024.ce09b_ammort_materiali:,.2f}")
        print(f"      Write-downs (ce09c): €{inc_2024.ce09c_svalutazioni:,.2f}")

        total_depn_from_details = (inc_2024.ce09a_ammort_immateriali +
                                   inc_2024.ce09b_ammort_materiali +
                                   inc_2024.ce09c_svalutazioni)

        print(f"\n   Verification:")
        print(f"      Sum of details: €{total_depn_from_details:,.2f}")
        print(f"      Aggregate ce09: €{inc_2024.ce09_ammortamenti:,.2f}")
        depn_match = abs(total_depn_from_details - inc_2024.ce09_ammortamenti) < 1
        print(f"      Match: {depn_match} {'✅' if depn_match else '❌'}")

        print(f"\n   Depreciation split ratio:")
        if inc_2024.ce09_ammortamenti > 0:
            intangible_ratio = inc_2024.ce09a_ammort_immateriali / inc_2024.ce09_ammortamenti * 100
            tangible_ratio = inc_2024.ce09b_ammort_materiali / inc_2024.ce09_ammortamenti * 100
            print(f"      Intangible: {intangible_ratio:.1f}%")
            print(f"      Tangible:   {tangible_ratio:.1f}%")

        print(f"\n   Asset split ratio (from balance sheet):")
        total_fixed = bs_2024.sp02_immob_immateriali + bs_2024.sp03_immob_materiali
        if total_fixed > 0:
            asset_intangible_ratio = bs_2024.sp02_immob_immateriali / total_fixed * 100
            asset_tangible_ratio = bs_2024.sp03_immob_materiali / total_fixed * 100
            print(f"      Intangible assets: {asset_intangible_ratio:.1f}%")
            print(f"      Tangible assets:   {asset_tangible_ratio:.1f}%")

        print("\n" + "=" * 80)
        print("✅ HIERARCHICAL IMPORT TEST COMPLETED")
        print("=" * 80)

        # Summary
        all_match = match_2023 and match_2024 and depn_match
        if all_match:
            print("\n🎉 SUCCESS: All hierarchical fields are correctly populated!")
        else:
            print("\n⚠️  WARNING: Some fields don't match aggregates")
            if not match_2023:
                print("   - 2023 debt details don't sum to aggregate")
            if not match_2024:
                print("   - 2024 debt details don't sum to aggregate")
            if not depn_match:
                print("   - Depreciation details don't sum to aggregate")

    finally:
        db.close()


if __name__ == "__main__":
    test_hierarchical_import()
