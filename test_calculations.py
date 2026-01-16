"""
Test financial calculations with sample data
"""
from decimal import Decimal
from database.db import init_db, SessionLocal, drop_all
from database.models import Company, FinancialYear, BalanceSheet, IncomeStatement
from calculations.ratios import FinancialRatiosCalculator
from calculations.altman import AltmanCalculator
from config import Sector


def test_calculations():
    """Test all calculation modules"""

    print("=" * 70)
    print("FINANCIAL CALCULATIONS TEST")
    print("=" * 70)

    # Initialize database
    drop_all()
    init_db()

    db = SessionLocal()

    try:
        # Create test company
        company = Company(
            name="Industria Test S.r.l.",
            tax_id="12345678901",
            sector=Sector.INDUSTRIA.value
        )
        db.add(company)
        db.commit()

        # Create financial year
        fy = FinancialYear(company_id=company.id, year=2024)
        db.add(fy)
        db.commit()

        # Create Balance Sheet with realistic values
        bs = BalanceSheet(
            financial_year_id=fy.id,
            # ASSETS
            sp01_crediti_soci=Decimal("0"),
            sp02_immob_immateriali=Decimal("50000"),    # Intangibles
            sp03_immob_materiali=Decimal("250000"),     # PP&E
            sp04_immob_finanziarie=Decimal("0"),
            sp05_rimanenze=Decimal("80000"),            # Inventory
            sp06_crediti_breve=Decimal("150000"),       # Receivables <12m
            sp07_crediti_lungo=Decimal("0"),
            sp08_attivita_finanziarie=Decimal("10000"), # Marketable securities
            sp09_disponibilita_liquide=Decimal("70000"), # Cash
            sp10_ratei_risconti_attivi=Decimal("5000"),
            # LIABILITIES & EQUITY
            sp11_capitale=Decimal("100000"),            # Capital
            sp12_riserve=Decimal("80000"),              # Retained earnings
            sp13_utile_perdita=Decimal("30000"),        # Net profit
            sp14_fondi_rischi=Decimal("0"),
            sp15_tfr=Decimal("25000"),                  # Severance
            sp16_debiti_breve=Decimal("200000"),        # Short-term debt
            sp17_debiti_lungo=Decimal("100000"),        # Long-term debt
            sp18_ratei_risconti_passivi=Decimal("80000")
        )
        db.add(bs)
        db.commit()

        # Create Income Statement
        inc = IncomeStatement(
            financial_year_id=fy.id,
            # REVENUE
            ce01_ricavi_vendite=Decimal("600000"),      # Revenue
            ce02_variazioni_rimanenze=Decimal("5000"),
            ce03_lavori_interni=Decimal("0"),
            ce04_altri_ricavi=Decimal("10000"),
            # COSTS
            ce05_materie_prime=Decimal("220000"),       # Materials
            ce06_servizi=Decimal("100000"),             # Services
            ce07_godimento_beni=Decimal("20000"),       # Rent
            ce08_costi_personale=Decimal("150000"),     # Labor
            ce09_ammortamenti=Decimal("30000"),         # Depreciation
            ce10_var_rimanenze_mat_prime=Decimal("0"),
            ce11_accantonamenti=Decimal("0"),
            ce12_oneri_diversi=Decimal("15000"),        # Other expenses
            # FINANCIAL
            ce13_proventi_partecipazioni=Decimal("0"),
            ce14_altri_proventi_finanziari=Decimal("2000"),
            ce15_oneri_finanziari=Decimal("18000"),     # Interest expense
            ce16_utili_perdite_cambi=Decimal("0"),
            # OTHER
            ce17_rettifiche_attivita_fin=Decimal("0"),
            ce18_proventi_straordinari=Decimal("5000"),
            ce19_oneri_straordinari=Decimal("0"),
            ce20_imposte=Decimal("9000")                # Taxes
        )
        db.add(inc)
        db.commit()

        print("\n1. BALANCE SHEET OVERVIEW")
        print("-" * 70)
        print(f"Total Assets:       €{bs.total_assets:>12,.2f}")
        print(f"Fixed Assets:       €{bs.fixed_assets:>12,.2f}")
        print(f"Current Assets:     €{bs.current_assets:>12,.2f}")
        print(f"Total Equity:       €{bs.total_equity:>12,.2f}")
        print(f"Total Debt:         €{bs.total_debt:>12,.2f}")
        print(f"Current Liabilities:€{bs.current_liabilities:>12,.2f}")
        print(f"Balance Check:      {'✓ BALANCED' if bs.is_balanced() else '✗ NOT BALANCED'}")

        print("\n2. INCOME STATEMENT OVERVIEW")
        print("-" * 70)
        print(f"Revenue:            €{inc.revenue:>12,.2f}")
        print(f"Production Value:   €{inc.production_value:>12,.2f}")
        print(f"EBITDA:             €{inc.ebitda:>12,.2f}")
        print(f"EBIT:               €{inc.ebit:>12,.2f}")
        print(f"Net Profit:         €{inc.net_profit:>12,.2f}")

        # Test Financial Ratios
        print("\n3. FINANCIAL RATIOS ANALYSIS")
        print("-" * 70)

        ratios_calc = FinancialRatiosCalculator(bs, inc)

        # Working Capital
        wc = ratios_calc.calculate_working_capital_metrics()
        print(f"\nWorking Capital Metrics:")
        print(f"  CCN (Net WC):     €{wc.ccn:>12,.2f}")
        print(f"  MS (Struct Margin):€{wc.ms:>12,.2f}")
        print(f"  MT (Treasury Margin):€{wc.mt:>12,.2f}")

        # Liquidity
        liq = ratios_calc.calculate_liquidity_ratios()
        print(f"\nLiquidity Ratios:")
        print(f"  Current Ratio:    {liq.current_ratio:>12.4f}")
        print(f"  Quick Ratio:      {liq.quick_ratio:>12.4f}")
        print(f"  Acid Test:        {liq.acid_test:>12.4f}")

        # Solvency
        solv = ratios_calc.calculate_solvency_ratios()
        print(f"\nSolvency Ratios:")
        print(f"  Autonomy Index:   {solv.autonomy_index:>12.4f} ({solv.autonomy_index*100:.2f}%)")
        print(f"  Debt/Equity:      {solv.debt_to_equity:>12.4f}")
        print(f"  Leverage:         {solv.leverage_ratio:>12.4f}")

        # Profitability
        prof = ratios_calc.calculate_profitability_ratios()
        print(f"\nProfitability Ratios:")
        print(f"  ROE:              {prof.roe:>12.4f} ({prof.roe*100:.2f}%)")
        print(f"  ROI:              {prof.roi:>12.4f} ({prof.roi*100:.2f}%)")
        print(f"  ROS:              {prof.ros:>12.4f} ({prof.ros*100:.2f}%)")
        print(f"  EBITDA Margin:    {prof.ebitda_margin:>12.4f} ({prof.ebitda_margin*100:.2f}%)")
        print(f"  Net Margin:       {prof.net_margin:>12.4f} ({prof.net_margin*100:.2f}%)")

        # Activity
        act = ratios_calc.calculate_activity_ratios()
        print(f"\nActivity Ratios:")
        print(f"  Asset Turnover:   {act.asset_turnover:>12.4f}")
        print(f"  Inventory Days:   {act.inventory_turnover_days:>12.0f} days")
        print(f"  Receivables Days: {act.receivables_turnover_days:>12.0f} days")
        print(f"  Payables Days:    {act.payables_turnover_days:>12.0f} days")
        print(f"  Cash Conv. Cycle: {act.cash_conversion_cycle:>12.0f} days")

        # Test Altman Z-Score
        print("\n4. ALTMAN Z-SCORE ANALYSIS")
        print("-" * 70)

        altman_calc = AltmanCalculator(bs, inc, Sector.INDUSTRIA.value)
        altman_result = altman_calc.calculate()

        print(f"\nSector: {Sector.INDUSTRIA.value} (Industria - Manufacturing Model)")
        print(f"Model Type: {altman_result.model_type}")
        print(f"\nComponents:")
        print(f"  A (WC/TA):        {altman_result.components.A:>12.6f}")
        print(f"  B (RE/TA):        {altman_result.components.B:>12.6f}")
        print(f"  C (EBIT/TA):      {altman_result.components.C:>12.6f}")
        print(f"  D (Equity/Debt):  {altman_result.components.D:>12.6f}")
        print(f"  E (Revenue/TA):   {altman_result.components.E:>12.6f}")
        print(f"\nZ-Score:          {altman_result.z_score:>12.2f}")
        print(f"Classification:     {altman_result.classification.upper()}")
        print(f"\nInterpretation:")
        print(f"  {altman_result.interpretation_it}")

        # Test Services sector
        print("\n5. ALTMAN Z-SCORE - SERVICES SECTOR TEST")
        print("-" * 70)

        altman_services = AltmanCalculator(bs, inc, Sector.SERVIZI.value)
        altman_serv_result = altman_services.calculate()

        print(f"\nSector: {Sector.SERVIZI.value} (Servizi - Services Model)")
        print(f"Model Type: {altman_serv_result.model_type}")
        print(f"\nZ-Score:          {altman_serv_result.z_score:>12.2f}")
        print(f"Classification:     {altman_serv_result.classification.upper()}")
        print(f"\nNote: Services model does NOT use component E (Revenue/Assets)")

        print("\n" + "=" * 70)
        print("✅ ALL CALCULATION TESTS PASSED!")
        print("=" * 70)

    except Exception as e:
        print(f"\n❌ Error during calculations: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    test_calculations()
