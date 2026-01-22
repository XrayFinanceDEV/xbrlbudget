"""
Debug Detailed Cash Flow for ISTANZA02353550391
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from decimal import Decimal
from database.db import SessionLocal
from database.models import Company, FinancialYear, BalanceSheet, IncomeStatement
from app.calculations.cashflow_detailed import DetailedCashFlowCalculator


def debug_cashflow_istanza():
    """Debug cash flow for ISTANZA company"""
    print("=" * 80)
    print("DEBUG: Cash Flow for ISTANZA02353550391")
    print("=" * 80)

    db = SessionLocal()

    try:
        # Find the ISTANZA company (by tax_id)
        company = db.query(Company).filter(
            Company.tax_id == '02353550391'
        ).first()

        if not company:
            print("❌ ISTANZA company not found. Available companies:")
            companies = db.query(Company).all()
            for c in companies:
                print(f"  - {c.name} (Tax ID: {c.tax_id})")
            return

        print(f"\n✓ Company: {company.name}")
        print(f"  Tax ID: {company.tax_id}")

        # Get financial years
        fy_2023 = db.query(FinancialYear).filter(
            FinancialYear.company_id == company.id,
            FinancialYear.year == 2023
        ).first()

        fy_2024 = db.query(FinancialYear).filter(
            FinancialYear.company_id == company.id,
            FinancialYear.year == 2024
        ).first()

        if not fy_2023 or not fy_2024:
            print("❌ Financial years 2023 or 2024 not found")
            available_years = db.query(FinancialYear).filter(
                FinancialYear.company_id == company.id
            ).all()
            print("Available years:")
            for fy in available_years:
                print(f"  - {fy.year}")
            return

        # Get balance sheets
        bs_2023 = db.query(BalanceSheet).filter(
            BalanceSheet.financial_year_id == fy_2023.id
        ).first()

        bs_2024 = db.query(BalanceSheet).filter(
            BalanceSheet.financial_year_id == fy_2024.id
        ).first()

        # Get income statement
        inc_2024 = db.query(IncomeStatement).filter(
            IncomeStatement.financial_year_id == fy_2024.id
        ).first()

        if not bs_2023 or not bs_2024 or not inc_2024:
            print("❌ Missing financial statements")
            return

        print(f"\n✓ Found financial statements for 2023 and 2024")

        # Calculate cash flow
        print("\n" + "=" * 80)
        print("BALANCE SHEET VALUES")
        print("=" * 80)

        print(f"\n2023:")
        print(f"  Capitale: €{bs_2023.sp11_capitale:,.2f}")
        print(f"  Riserve: €{bs_2023.sp12_riserve:,.2f}")
        print(f"  Utile: €{bs_2023.sp13_utile_perdita:,.2f}")
        print(f"  Equity (without current profit): €{bs_2023.sp11_capitale + bs_2023.sp12_riserve:,.2f}")
        print(f"  Debiti breve: €{bs_2023.sp16_debiti_breve:,.2f}")
        print(f"  Debiti lungo: €{bs_2023.sp17_debiti_lungo:,.2f}")
        print(f"  Total debt: €{bs_2023.sp16_debiti_breve + bs_2023.sp17_debiti_lungo:,.2f}")

        print(f"\n2024:")
        print(f"  Capitale: €{bs_2024.sp11_capitale:,.2f}")
        print(f"  Riserve: €{bs_2024.sp12_riserve:,.2f}")
        print(f"  Utile: €{bs_2024.sp13_utile_perdita:,.2f}")
        print(f"  Equity (without current profit): €{bs_2024.sp11_capitale + bs_2024.sp12_riserve:,.2f}")
        print(f"  Debiti breve: €{bs_2024.sp16_debiti_breve:,.2f}")
        print(f"  Debiti lungo: €{bs_2024.sp17_debiti_lungo:,.2f}")
        print(f"  Total debt: €{bs_2024.sp16_debiti_breve + bs_2024.sp17_debiti_lungo:,.2f}")

        print(f"\n" + "=" * 80)
        print("CHANGES (Delta)")
        print("=" * 80)

        equity_2023 = bs_2023.sp11_capitale + bs_2023.sp12_riserve
        equity_2024 = bs_2024.sp11_capitale + bs_2024.sp12_riserve
        delta_equity = equity_2024 - equity_2023

        debt_2023 = bs_2023.sp16_debiti_breve + bs_2023.sp17_debiti_lungo
        debt_2024 = bs_2024.sp16_debiti_breve + bs_2024.sp17_debiti_lungo
        delta_debt = debt_2024 - debt_2023

        print(f"\n  Delta Equity (without profit): €{delta_equity:,.2f}")
        print(f"  Delta Debt: €{delta_debt:,.2f}")

        # Expected values
        print(f"\n" + "=" * 80)
        print("EXPECTED vs ACTUAL")
        print("=" * 80)

        print(f"\n📍 Financing Activities:")
        print(f"  Expected debt change: €-411,301")
        print(f"  Actual debt change: €{delta_debt:,.2f}")
        print(f"  Match: {abs(delta_debt - Decimal('-411301')) < 1}")

        print(f"\n  Expected equity change: €-9,856")
        print(f"  Actual equity change: €{delta_equity:,.2f}")
        print(f"  Match: {abs(delta_equity - Decimal('-9856')) < 1}")

        # Calculate cashflow
        cashflow = DetailedCashFlowCalculator.calculate(
            bs_current=bs_2024,
            bs_previous=bs_2023,
            inc_current=inc_2024,
            year=2024
        )

        print(f"\n" + "=" * 80)
        print("CALCULATED CASH FLOW")
        print("=" * 80)

        print(f"\n🔷 Operating Activities:")
        print(f"  Profit before adjustments: €{cashflow.operating_activities.start.profit_before_adjustments:,.2f}")
        print(f"  Expected: €1,765,725")

        print(f"\n  Non-cash adjustments: €{cashflow.operating_activities.non_cash_adjustments.total:,.2f}")
        print(f"  Expected: €3,386,580")

        print(f"\n  Cashflow before WC: €{cashflow.operating_activities.cashflow_before_wc:,.2f}")
        print(f"  Expected: €5,152,305")

        print(f"\n  WC changes total: €{cashflow.operating_activities.working_capital_changes.total:,.2f}")
        print(f"  Expected: €3,467,353")

        print(f"\n  Cashflow after WC: €{cashflow.operating_activities.cashflow_after_wc:,.2f}")
        print(f"  Expected: €8,619,658")

        print(f"\n  Cash adjustments: €{cashflow.operating_activities.cash_adjustments.total:,.2f}")
        print(f"  Expected: €-2,029,211")

        print(f"\n  ✅ Total Operating: €{cashflow.operating_activities.total_operating_cashflow:,.2f}")
        print(f"  Expected: €6,590,447")
        match = abs(cashflow.operating_activities.total_operating_cashflow - Decimal('6590447')) < 1000
        print(f"  Match: {match}")

        print(f"\n🔷 Investing Activities:")
        print(f"  Total Investing: €{cashflow.investing_activities.total_investing_cashflow:,.2f}")
        print(f"  Expected: €-6,787,084")
        match = abs(cashflow.investing_activities.total_investing_cashflow - Decimal('-6787084')) < 10000
        print(f"  Match: {match}")

        print(f"\n🔷 Financing Activities:")
        print(f"  Third-party funds: €{cashflow.financing_activities.third_party_funds.net:,.2f}")
        print(f"  Expected: €-411,301")
        match = abs(cashflow.financing_activities.third_party_funds.net - Decimal('-411301')) < 1000
        print(f"  Match: {match}")

        print(f"\n  Own funds: €{cashflow.financing_activities.own_funds.net:,.2f}")
        print(f"  Expected: €-9,856")
        match = abs(cashflow.financing_activities.own_funds.net - Decimal('-9856')) < 1000
        print(f"  Match: {match}")

        print(f"\n  ✅ Total Financing: €{cashflow.financing_activities.total_financing_cashflow:,.2f}")
        print(f"  Expected: €-421,157")
        match = abs(cashflow.financing_activities.total_financing_cashflow - Decimal('-421157')) < 1000
        print(f"  Match: {match}")

        print(f"\n🔷 Final Cash Flow:")
        print(f"  Total: €{cashflow.cash_reconciliation.total_cashflow:,.2f}")
        print(f"  Expected: €-617,794")
        match = abs(cashflow.cash_reconciliation.total_cashflow - Decimal('-617794')) < 1000
        print(f"  Match: {match}")

        # Check if there are issues
        if not match:
            print(f"\n❌ CASH FLOW MISMATCH!")
            print(f"   Difference: €{abs(cashflow.cash_reconciliation.total_cashflow - Decimal('-617794')):,.2f}")

    finally:
        db.close()


if __name__ == "__main__":
    debug_cashflow_istanza()
