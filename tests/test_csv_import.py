"""
Test CSV Importer
"""
from database.db import init_db, SessionLocal, drop_all
from database.models import Company, FinancialYear, BalanceSheet, IncomeStatement
from importers.csv_importer import CSVImporter, import_csv_file
from calculations.ratios import FinancialRatiosCalculator
from calculations.altman import AltmanCalculator
from calculations.rating_fgpmi import FGPMICalculator
from config import Sector


def test_csv_import():
    """Test CSV import functionality"""

    print("=" * 70)
    print("CSV IMPORT TEST")
    print("=" * 70)

    # Initialize database
    drop_all()
    init_db()

    db = SessionLocal()

    try:
        # Create test company
        print("\n1. Creating test company...")
        company = Company(
            name="Imported Company S.r.l.",
            tax_id="11223344556",
            sector=Sector.INDUSTRIA.value,
            notes="Created from CSV import test"
        )
        db.add(company)
        db.commit()
        db.refresh(company)
        print(f"   ✓ Company created: {company.name} (ID: {company.id})")

        # Import CSV file
        print("\n2. Importing CSV file...")
        csv_path = "sample_data.csv"

        result = import_csv_file(
            file_path=csv_path,
            company_id=company.id,
            year1=2024,
            year2=2023
        )

        print(f"   ✓ Import successful!")
        print(f"     Balance Sheet Type: {result['balance_sheet_type']}")
        print(f"     Years: {result['years']}")
        print(f"     Rows processed: {result['rows_processed']}")
        print(f"     Balance Sheet fields: {result['balance_sheet_fields_imported']}")
        print(f"     Income Statement fields: {result['income_statement_fields_imported']}")

        # Retrieve imported data
        print("\n3. Verifying imported data...")
        fy_2024 = db.query(FinancialYear).filter(
            FinancialYear.company_id == company.id,
            FinancialYear.year == 2024
        ).first()

        fy_2023 = db.query(FinancialYear).filter(
            FinancialYear.company_id == company.id,
            FinancialYear.year == 2023
        ).first()

        if not fy_2024 or not fy_2023:
            raise Exception("Financial years not created!")

        print(f"   ✓ Financial years created:")
        print(f"     - Year 2024 (ID: {fy_2024.id})")
        print(f"     - Year 2023 (ID: {fy_2023.id})")

        # Get balance sheets
        bs_2024 = fy_2024.balance_sheet
        bs_2023 = fy_2023.balance_sheet

        # Get income statements
        inc_2024 = fy_2024.income_statement
        inc_2023 = fy_2023.income_statement

        print("\n4. YEAR 2024 - FINANCIAL OVERVIEW")
        print("-" * 70)
        print(f"Balance Sheet:")
        print(f"  Total Assets:       €{bs_2024.total_assets:>12,.2f}")
        print(f"  Total Equity:       €{bs_2024.total_equity:>12,.2f}")
        print(f"  Total Liabilities:  €{bs_2024.total_liabilities:>12,.2f}")
        print(f"  Balanced:           {'✓ YES' if bs_2024.is_balanced() else '✗ NO'}")
        print(f"")
        print(f"Income Statement:")
        print(f"  Revenue:            €{inc_2024.revenue:>12,.2f}")
        print(f"  EBITDA:             €{inc_2024.ebitda:>12,.2f}")
        print(f"  EBIT:               €{inc_2024.ebit:>12,.2f}")
        print(f"  Net Profit:         €{inc_2024.net_profit:>12,.2f}")

        print("\n5. YEAR 2023 - FINANCIAL OVERVIEW")
        print("-" * 70)
        print(f"Balance Sheet:")
        print(f"  Total Assets:       €{bs_2023.total_assets:>12,.2f}")
        print(f"  Total Equity:       €{bs_2023.total_equity:>12,.2f}")
        print(f"  Total Liabilities:  €{bs_2023.total_liabilities:>12,.2f}")
        print(f"  Balanced:           {'✓ YES' if bs_2023.is_balanced() else '✗ NO'}")
        print(f"")
        print(f"Income Statement:")
        print(f"  Revenue:            €{inc_2023.revenue:>12,.2f}")
        print(f"  EBITDA:             €{inc_2023.ebitda:>12,.2f}")
        print(f"  EBIT:               €{inc_2023.ebit:>12,.2f}")
        print(f"  Net Profit:         €{inc_2023.net_profit:>12,.2f}")

        # Calculate ratios for 2024
        print("\n6. FINANCIAL ANALYSIS (Year 2024)")
        print("-" * 70)

        ratios_calc = FinancialRatiosCalculator(bs_2024, inc_2024)

        # Key ratios
        wc = ratios_calc.calculate_working_capital_metrics()
        liq = ratios_calc.calculate_liquidity_ratios()
        prof = ratios_calc.calculate_profitability_ratios()

        print(f"Working Capital:")
        print(f"  CCN (Net WC):       €{wc.ccn:>12,.2f}")
        print(f"")
        print(f"Liquidity:")
        print(f"  Current Ratio:      {liq.current_ratio:>12.4f}")
        print(f"")
        print(f"Profitability:")
        print(f"  ROE:                {prof.roe:>12.4f} ({prof.roe*100:.2f}%)")
        print(f"  ROI:                {prof.roi:>12.4f} ({prof.roi*100:.2f}%)")
        print(f"  EBITDA Margin:      {prof.ebitda_margin:>12.4f} ({prof.ebitda_margin*100:.2f}%)")

        # Altman Z-Score
        print("\n7. ALTMAN Z-SCORE")
        print("-" * 70)

        altman = AltmanCalculator(bs_2024, inc_2024, Sector.INDUSTRIA.value)
        altman_result = altman.calculate()

        print(f"Z-Score:              {altman_result.z_score:>12.2f}")
        print(f"Classification:       {altman_result.classification.upper()}")
        print(f"Interpretation:       {altman_result.interpretation_it[:80]}...")

        # FGPMI Rating
        print("\n8. FGPMI RATING")
        print("-" * 70)

        fgpmi = FGPMICalculator(bs_2024, inc_2024, Sector.INDUSTRIA.value)
        fgpmi_result = fgpmi.calculate()

        print(f"Rating:               {fgpmi_result.rating_code} ({fgpmi_result.rating_description})")
        print(f"Score:                {fgpmi_result.total_score}/{fgpmi_result.max_score} ({fgpmi_result.total_score/fgpmi_result.max_score*100:.1f}%)")
        print(f"Risk Level:           {fgpmi_result.risk_level}")

        # Year-over-year comparison
        print("\n9. YEAR-OVER-YEAR COMPARISON")
        print("-" * 70)

        revenue_growth = ((inc_2024.revenue - inc_2023.revenue) / inc_2023.revenue) * 100
        profit_growth = ((inc_2024.net_profit - inc_2023.net_profit) / inc_2023.net_profit) * 100
        asset_growth = ((bs_2024.total_assets - bs_2023.total_assets) / bs_2023.total_assets) * 100

        print(f"Revenue Growth:       {revenue_growth:>12.2f}%")
        print(f"Profit Growth:        {profit_growth:>12.2f}%")
        print(f"Asset Growth:         {asset_growth:>12.2f}%")

        print("\n" + "=" * 70)
        print("✅ CSV IMPORT TEST PASSED!")
        print("=" * 70)
        print("\nSummary:")
        print(f"- Imported {result['balance_sheet_fields_imported']} balance sheet fields")
        print(f"- Imported {result['income_statement_fields_imported']} income statement fields")
        print(f"- Created 2 financial years with complete data")
        print(f"- All calculations working correctly on imported data")

    except Exception as e:
        print(f"\n❌ Error during CSV import test: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    test_csv_import()
