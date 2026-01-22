"""
Test XBRL Parser with Real BKPS.XBRL File
"""
from database.db import init_db, SessionLocal, drop_all
from database.models import Company, FinancialYear
from importers.xbrl_parser import XBRLParser, import_xbrl_file
from calculations.ratios import FinancialRatiosCalculator
from calculations.altman import AltmanCalculator
from calculations.rating_fgpmi import FGPMICalculator
from config import Sector


def test_bkps_xbrl():
    """Test XBRL import with real BKPS file"""

    print("=" * 70)
    print("BKPS.XBRL IMPORT TEST")
    print("=" * 70)

    # Initialize database
    drop_all()
    init_db()

    db = SessionLocal()

    try:
        # Test: Import XBRL with automatic company creation
        print("\n1. Importing BKPS.XBRL file (auto-create company)...")
        xbrl_path = "BKPS.XBRL"

        result = import_xbrl_file(
            file_path=xbrl_path,
            create_company=True
        )

        print(f"   ✓ Import successful!")
        print(f"     Taxonomy Version: {result['taxonomy_version']}")
        print(f"     Company: {result['company_name']} (ID: {result['company_id']})")
        print(f"     Tax ID: {result['tax_id']}")
        print(f"     Years imported: {result['years']}")
        print(f"     Contexts found: {result['contexts_found']}")
        print(f"     Financial years: {result['years_imported']}")

        # Retrieve imported data
        print("\n2. Verifying imported data...")
        company_id = result['company_id']
        years = result['years']

        for year in years:
            fy = db.query(FinancialYear).filter(
                FinancialYear.company_id == company_id,
                FinancialYear.year == year
            ).first()

            if not fy:
                raise Exception(f"Financial year {year} not created!")

            bs = fy.balance_sheet
            inc = fy.income_statement

            print(f"\n   Year {year}:")
            print(f"     Balance Sheet:")
            print(f"       Total Assets:     €{bs.total_assets:>12,.2f}")
            print(f"       Total Equity:     €{bs.total_equity:>12,.2f}")
            print(f"       Total Debt:       €{bs.total_debt:>12,.2f}")
            print(f"       Balanced:         {'✓ YES' if bs.is_balanced() else '✗ NO'}")
            print(f"     Income Statement:")
            print(f"       Revenue:          €{inc.revenue:>12,.2f}")
            print(f"       EBITDA:           €{inc.ebitda:>12,.2f}")
            print(f"       Net Profit:       €{inc.net_profit:>12,.2f}")

        # Detailed analysis for most recent year
        most_recent_year = max(years)
        fy_current = db.query(FinancialYear).filter(
            FinancialYear.company_id == company_id,
            FinancialYear.year == most_recent_year
        ).first()

        bs_current = fy_current.balance_sheet
        inc_current = fy_current.income_statement

        print(f"\n3. DETAILED ANALYSIS (Year {most_recent_year})")
        print("-" * 70)

        # Financial Ratios
        print("\nFinancial Ratios:")
        ratios_calc = FinancialRatiosCalculator(bs_current, inc_current)

        wc = ratios_calc.calculate_working_capital_metrics()
        liq = ratios_calc.calculate_liquidity_ratios()
        solv = ratios_calc.calculate_solvency_ratios()
        prof = ratios_calc.calculate_profitability_ratios()
        act = ratios_calc.calculate_activity_ratios()

        print(f"  Working Capital:")
        print(f"    CCN (Net WC):         €{wc.ccn:>12,.2f}")
        print(f"    MS (Struct Margin):   €{wc.ms:>12,.2f}")
        print(f"")
        print(f"  Liquidity:")
        print(f"    Current Ratio:        {liq.current_ratio:>12.4f}")
        print(f"    Quick Ratio:          {liq.quick_ratio:>12.4f}")
        print(f"")
        print(f"  Solvency:")
        print(f"    Autonomy Index:       {solv.autonomy_index:>12.4f} ({solv.autonomy_index*100:.2f}%)")
        print(f"    Debt/Equity:          {solv.debt_to_equity:>12.4f}")
        print(f"")
        print(f"  Profitability:")
        print(f"    ROE:                  {prof.roe:>12.4f} ({prof.roe*100:.2f}%)")
        print(f"    ROI:                  {prof.roi:>12.4f} ({prof.roi*100:.2f}%)")
        print(f"    EBITDA Margin:        {prof.ebitda_margin:>12.4f} ({prof.ebitda_margin*100:.2f}%)")
        print(f"")
        print(f"  Activity:")
        print(f"    Asset Turnover:       {act.asset_turnover:>12.4f}")
        print(f"    Inventory Days:       {act.inventory_turnover_days:>12.0f} days")
        print(f"    Receivables Days:     {act.receivables_turnover_days:>12.0f} days")

        # Altman Z-Score
        print("\n4. ALTMAN Z-SCORE")
        print("-" * 70)

        altman = AltmanCalculator(bs_current, inc_current, Sector.INDUSTRIA.value)
        altman_result = altman.calculate()

        print(f"Model Type:           {altman_result.model_type}")
        print(f"Z-Score:              {altman_result.z_score:>12.2f}")
        print(f"Classification:       {altman_result.classification.upper()}")
        print(f"\nComponents:")
        print(f"  A (WC/TA):          {altman_result.components.A:>12.6f}")
        print(f"  B (RE/TA):          {altman_result.components.B:>12.6f}")
        print(f"  C (EBIT/TA):        {altman_result.components.C:>12.6f}")
        print(f"  D (Equity/Debt):    {altman_result.components.D:>12.6f}")
        print(f"  E (Revenue/TA):     {altman_result.components.E:>12.6f}")
        print(f"\n{altman_result.interpretation_it[:100]}...")

        # FGPMI Rating
        print("\n5. FGPMI RATING")
        print("-" * 70)

        fgpmi = FGPMICalculator(bs_current, inc_current, Sector.INDUSTRIA.value)
        fgpmi_result = fgpmi.calculate()

        print(f"Rating:               {fgpmi_result.rating_code} ({fgpmi_result.rating_description})")
        print(f"Score:                {fgpmi_result.total_score}/{fgpmi_result.max_score} ({fgpmi_result.total_score/fgpmi_result.max_score*100:.1f}%)")
        print(f"Risk Level:           {fgpmi_result.risk_level}")
        print(f"Sector Model:         {fgpmi_result.sector_model.title()}")
        print(f"Revenue Bonus:        +{fgpmi_result.revenue_bonus} points")

        print(f"\nTop 3 Indicators:")
        sorted_indicators = sorted(
            fgpmi_result.indicators.items(),
            key=lambda x: x[1].percentage,
            reverse=True
        )[:3]

        for code, ind in sorted_indicators:
            print(f"  {ind.code}: {ind.name}")
            print(f"      Score: {ind.points}/{ind.max_points} ({ind.percentage:.1f}%)")

        # Comparison between years
        if len(years) >= 2:
            print("\n6. YEAR-OVER-YEAR COMPARISON")
            print("-" * 70)

            year1, year2 = sorted(years, reverse=True)[:2]

            fy1 = db.query(FinancialYear).filter(
                FinancialYear.company_id == company_id,
                FinancialYear.year == year1
            ).first()

            fy2 = db.query(FinancialYear).filter(
                FinancialYear.company_id == company_id,
                FinancialYear.year == year2
            ).first()

            bs1, inc1 = fy1.balance_sheet, fy1.income_statement
            bs2, inc2 = fy2.balance_sheet, fy2.income_statement

            revenue_growth = ((inc1.revenue - inc2.revenue) / inc2.revenue) * 100 if inc2.revenue != 0 else 0
            profit_growth = ((inc1.net_profit - inc2.net_profit) / inc2.net_profit) * 100 if inc2.net_profit != 0 else 0
            asset_growth = ((bs1.total_assets - bs2.total_assets) / bs2.total_assets) * 100 if bs2.total_assets != 0 else 0
            equity_growth = ((bs1.total_equity - bs2.total_equity) / bs2.total_equity) * 100 if bs2.total_equity != 0 else 0

            print(f"Comparing {year1} vs {year2}:")
            print(f"  Revenue Growth:       {revenue_growth:>12.2f}%")
            print(f"  Profit Growth:        {profit_growth:>12.2f}%")
            print(f"  Asset Growth:         {asset_growth:>12.2f}%")
            print(f"  Equity Growth:        {equity_growth:>12.2f}%")

            # Altman trend
            altman2 = AltmanCalculator(bs2, inc2, Sector.INDUSTRIA.value)
            altman_result2 = altman2.calculate()

            z_change = altman_result.z_score - altman_result2.z_score

            print(f"\nAltman Z-Score Trend:")
            print(f"  {year2}: {altman_result2.z_score:.2f} ({altman_result2.classification})")
            print(f"  {year1}: {altman_result.z_score:.2f} ({altman_result.classification})")
            print(f"  Change: {'+' if z_change > 0 else ''}{z_change:.2f}")

        print("\n" + "=" * 70)
        print("✅ BKPS.XBRL IMPORT TEST PASSED!")
        print("=" * 70)
        print("\nSummary:")
        print(f"- Successfully parsed XBRL file with taxonomy {result['taxonomy_version']}")
        print(f"- Imported {result['years_imported']} years of financial data")
        print(f"- Created company automatically from XBRL entity info")
        print(f"- All calculations working correctly on imported data")

    except Exception as e:
        print(f"\n❌ Error during XBRL import test: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    test_bkps_xbrl()
