"""
Debug Cash Flow Calculation Issues
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from decimal import Decimal
from database.db import SessionLocal
from database.models import Company, FinancialYear, BalanceSheet, IncomeStatement
from app.calculations.cashflow_detailed import DetailedCashFlowCalculator


def debug_cashflow_2024():
    """Debug cash flow calculation for 2024"""
    print("=" * 80)
    print("DEBUG: Cash Flow Calculation for 2024")
    print("=" * 80)

    db = SessionLocal()

    try:
        # Find company
        company = db.query(Company).first()
        if not company:
            print("❌ No company found")
            return

        print(f"\n✓ Company: {company.name}")

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

        print(f"✓ Found financial statements for 2023 and 2024")

        # Check key values
        print("\n" + "=" * 80)
        print("KEY VALUES FROM DATABASE")
        print("=" * 80)

        print(f"\n📊 Income Statement 2024:")
        print(f"  ce11_accantonamenti: €{inc_2024.ce11_accantonamenti:,.2f}")
        print(f"  ce09_ammortamenti: €{inc_2024.ce09_ammortamenti:,.2f}")
        print(f"  ce15_oneri_finanziari: €{inc_2024.ce15_oneri_finanziari:,.2f}")
        print(f"  ce14_altri_proventi_finanziari: €{inc_2024.ce14_altri_proventi_finanziari:,.2f}")
        print(f"  ce20_imposte: €{inc_2024.ce20_imposte:,.2f}")

        print(f"\n📊 Balance Sheet - Fondi per Rischi:")
        print(f"  2023 sp14_fondi_rischi: €{bs_2023.sp14_fondi_rischi:,.2f}")
        print(f"  2024 sp14_fondi_rischi: €{bs_2024.sp14_fondi_rischi:,.2f}")

        print(f"\n📊 Balance Sheet - Ratei e Risconti:")
        print(f"  2023 sp10_ratei_risconti_attivi: €{bs_2023.sp10_ratei_risconti_attivi:,.2f}")
        print(f"  2024 sp10_ratei_risconti_attivi: €{bs_2024.sp10_ratei_risconti_attivi:,.2f}")
        print(f"  2023 sp18_ratei_risconti_passivi: €{bs_2023.sp18_ratei_risconti_passivi:,.2f}")
        print(f"  2024 sp18_ratei_risconti_passivi: €{bs_2024.sp18_ratei_risconti_passivi:,.2f}")

        print(f"\n📊 Balance Sheet - Equity:")
        print(f"  2023 sp11_capitale: €{bs_2023.sp11_capitale:,.2f}")
        print(f"  2024 sp11_capitale: €{bs_2024.sp11_capitale:,.2f}")
        print(f"  2023 sp12_riserve: €{bs_2023.sp12_riserve:,.2f}")
        print(f"  2024 sp12_riserve: €{bs_2024.sp12_riserve:,.2f}")

        print(f"\n📊 Balance Sheet - Debts:")
        print(f"  2023 total debiti: €{bs_2023.sp16_debiti_breve + bs_2023.sp17_debiti_lungo:,.2f}")
        print(f"  2024 total debiti: €{bs_2024.sp16_debiti_breve + bs_2024.sp17_debiti_lungo:,.2f}")

        # Calculate cash flow
        print("\n" + "=" * 80)
        print("CALCULATING CASH FLOW")
        print("=" * 80)

        cashflow = DetailedCashFlowCalculator.calculate(
            bs_current=bs_2024,
            bs_previous=bs_2023,
            inc_current=inc_2024,
            year=2024
        )

        # Check specific issues
        print("\n" + "=" * 80)
        print("CHECKING SPECIFIC ISSUES")
        print("=" * 80)

        # Issue 1: Provisions
        provisions = cashflow.operating_activities.non_cash_adjustments.provisions
        expected_provisions = Decimal('189973')

        print(f"\n1️⃣ Accantonamenti ai fondi (Provisions):")
        print(f"   Current: €{provisions:,.2f}")
        print(f"   Expected: €{expected_provisions:,.2f}")
        if provisions == expected_provisions:
            print(f"   ✅ CORRECT")
        else:
            print(f"   ❌ WRONG! Difference: €{abs(provisions - expected_provisions):,.2f}")

        # Issue 2: Use of provisions
        use_provisions = cashflow.operating_activities.cash_adjustments.use_of_provisions
        expected_use = Decimal('-274232')

        print(f"\n2️⃣ (Utilizzo dei fondi) [Use of provisions]:")
        print(f"   Current: €{use_provisions:,.2f}")
        print(f"   Expected: €{expected_use:,.2f}")
        if use_provisions == expected_use:
            print(f"   ✅ CORRECT")
        else:
            print(f"   ❌ WRONG! Difference: €{abs(use_provisions - expected_use):,.2f}")

        # Issue 3: Other cash changes
        other_changes = cashflow.operating_activities.cash_adjustments.other_cash_changes
        expected_other = Decimal('0')

        print(f"\n3️⃣ Altri incassi/(pagamenti) [Other cash changes]:")
        print(f"   Current: €{other_changes:,.2f}")
        print(f"   Expected: €{expected_other:,.2f}")
        if other_changes == expected_other:
            print(f"   ✅ CORRECT")
        else:
            print(f"   ❌ WRONG! Difference: €{abs(other_changes - expected_other):,.2f}")

            # Debug accruals
            delta_accruals_active = bs_2023.sp10_ratei_risconti_attivi - bs_2024.sp10_ratei_risconti_attivi
            delta_accruals_passive = bs_2024.sp18_ratei_risconti_passivi - bs_2023.sp18_ratei_risconti_passivi
            print(f"   → Delta ratei attivi: €{delta_accruals_active:,.2f}")
            print(f"   → Delta ratei passivi: €{delta_accruals_passive:,.2f}")
            print(f"   → Sum (causing issue): €{delta_accruals_active + delta_accruals_passive:,.2f}")

        # Issue 4: Interest expense
        interest = cashflow.operating_activities.start.interest_expense_income
        expected_interest = Decimal('1653112')

        print(f"\n4️⃣ Interessi passivi/(interessi attivi):")
        print(f"   Current: €{interest:,.2f}")
        print(f"   Expected: €{expected_interest:,.2f}")
        if abs(interest - expected_interest) < 10:
            print(f"   ✅ CORRECT")
        else:
            print(f"   ❌ WRONG! Difference: €{abs(interest - expected_interest):,.2f}")

        # Issue 5: Financing activities
        debt_net = cashflow.financing_activities.third_party_funds.net
        expected_debt = Decimal('-411301')

        print(f"\n5️⃣ Mezzi di terzi (Third-party funds):")
        print(f"   Current: €{debt_net:,.2f}")
        print(f"   Expected: €{expected_debt:,.2f}")
        if debt_net == expected_debt:
            print(f"   ✅ CORRECT")
        else:
            print(f"   ❌ WRONG! Difference: €{abs(debt_net - expected_debt):,.2f}")

        equity_net = cashflow.financing_activities.own_funds.net
        expected_equity = Decimal('-9856')

        print(f"\n6️⃣ Mezzi propri (Own funds):")
        print(f"   Current: €{equity_net:,.2f}")
        print(f"   Expected: €{expected_equity:,.2f}")
        if equity_net == expected_equity:
            print(f"   ✅ CORRECT")
        else:
            print(f"   ❌ WRONG! Difference: €{abs(equity_net - expected_equity):,.2f}")

        # Final total
        total_cf = cashflow.cash_reconciliation.total_cashflow
        expected_total = Decimal('-617794')

        print(f"\n" + "=" * 80)
        print(f"FINAL CASH FLOW")
        print(f"=" * 80)
        print(f"\n   Current: €{total_cf:,.2f}")
        print(f"   Expected: €{expected_total:,.2f}")
        if abs(total_cf - expected_total) < 1:
            print(f"   ✅ CORRECT")
        else:
            print(f"   ❌ WRONG! Difference: €{abs(total_cf - expected_total):,.2f}")

    finally:
        db.close()


if __name__ == "__main__":
    debug_cashflow_2024()
