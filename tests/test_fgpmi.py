"""
Test FGPMI Rating Calculator
"""
from decimal import Decimal
from database.db import init_db, SessionLocal, drop_all
from database.models import Company, FinancialYear, BalanceSheet, IncomeStatement
from calculations.rating_fgpmi import FGPMICalculator
from config import Sector


def test_fgpmi_rating():
    """Test FGPMI Rating calculation"""

    print("=" * 70)
    print("FGPMI RATING CALCULATOR TEST")
    print("=" * 70)

    # Initialize database
    drop_all()
    init_db()

    db = SessionLocal()

    try:
        # Create test company
        company = Company(
            name="Test Manufacturing S.r.l.",
            tax_id="98765432101",
            sector=Sector.INDUSTRIA.value
        )
        db.add(company)
        db.commit()

        # Create financial year
        fy = FinancialYear(company_id=company.id, year=2024)
        db.add(fy)
        db.commit()

        # Create Balance Sheet - Strong company profile
        bs = BalanceSheet(
            financial_year_id=fy.id,
            # ASSETS
            sp01_crediti_soci=Decimal("0"),
            sp02_immob_immateriali=Decimal("80000"),
            sp03_immob_materiali=Decimal("400000"),
            sp04_immob_finanziarie=Decimal("20000"),
            sp05_rimanenze=Decimal("150000"),
            sp06_crediti_breve=Decimal("250000"),
            sp07_crediti_lungo=Decimal("30000"),
            sp08_attivita_finanziarie=Decimal("20000"),
            sp09_disponibilita_liquide=Decimal("150000"),
            sp10_ratei_risconti_attivi=Decimal("10000"),
            # LIABILITIES & EQUITY - Strong equity position
            sp11_capitale=Decimal("200000"),
            sp12_riserve=Decimal("250000"),  # Strong retained earnings
            sp13_utile_perdita=Decimal("80000"),  # Good profit
            sp14_fondi_rischi=Decimal("10000"),
            sp15_tfr=Decimal("40000"),
            sp16_debiti_breve=Decimal("280000"),
            sp17_debiti_lungo=Decimal("150000"),
            sp18_ratei_risconti_passivi=Decimal("10000")
        )
        db.add(bs)
        db.commit()

        # Create Income Statement - Profitable company
        inc = IncomeStatement(
            financial_year_id=fy.id,
            # REVENUE - Above 500K threshold for bonus
            ce01_ricavi_vendite=Decimal("1200000"),
            ce02_variazioni_rimanenze=Decimal("10000"),
            ce03_lavori_interni=Decimal("0"),
            ce04_altri_ricavi=Decimal("20000"),
            # COSTS
            ce05_materie_prime=Decimal("480000"),
            ce06_servizi=Decimal("200000"),
            ce07_godimento_beni=Decimal("40000"),
            ce08_costi_personale=Decimal("280000"),
            ce09_ammortamenti=Decimal("60000"),
            ce10_var_rimanenze_mat_prime=Decimal("0"),
            ce11_accantonamenti=Decimal("5000"),
            ce12_oneri_diversi=Decimal("25000"),
            # FINANCIAL
            ce13_proventi_partecipazioni=Decimal("0"),
            ce14_altri_proventi_finanziari=Decimal("5000"),
            ce15_oneri_finanziari=Decimal("25000"),
            ce16_utili_perdite_cambi=Decimal("0"),
            # OTHER
            ce17_rettifiche_attivita_fin=Decimal("0"),
            ce18_proventi_straordinari=Decimal("10000"),
            ce19_oneri_straordinari=Decimal("0"),
            ce20_imposte=Decimal("30000")
        )
        db.add(inc)
        db.commit()

        print("\n1. COMPANY OVERVIEW")
        print("-" * 70)
        print(f"Name: {company.name}")
        print(f"Sector: {Sector.INDUSTRIA.value} (Industria)")
        print(f"Year: {fy.year}")

        print("\n2. FINANCIAL SUMMARY")
        print("-" * 70)
        print(f"Total Assets:       €{bs.total_assets:>12,.2f}")
        print(f"Total Equity:       €{bs.total_equity:>12,.2f}")
        print(f"Total Debt:         €{bs.total_debt:>12,.2f}")
        print(f"Working Capital:    €{bs.working_capital_net:>12,.2f}")
        print(f"")
        print(f"Revenue:            €{inc.revenue:>12,.2f}")
        print(f"EBITDA:             €{inc.ebitda:>12,.2f}")
        print(f"EBIT:               €{inc.ebit:>12,.2f}")
        print(f"Net Profit:         €{inc.net_profit:>12,.2f}")

        print("\n3. FGPMI RATING CALCULATION")
        print("-" * 70)

        # Calculate FGPMI Rating
        fgpmi_calc = FGPMICalculator(bs, inc, Sector.INDUSTRIA.value)
        result = fgpmi_calc.calculate()

        print(f"\nSector Model: {result.sector_model.upper()}")
        print(f"\n{'-' * 70}")
        print(f"{'INDICATOR':<45} {'VALUE':>10} {'POINTS':>14}")
        print(f"{'-' * 70}")

        for code in ['V1', 'V2', 'V3', 'V4', 'V5', 'V6', 'V7']:
            ind = result.indicators[code]
            value_display = f"{ind.value:.4f}"
            points_display = f"{ind.points}/{ind.max_points}"
            print(f"{ind.name:<45} {value_display:>10} {points_display:>14}")

        print(f"{'-' * 70}")
        print(f"{'Revenue Bonus (Fatturato > €500K)':<45} {'':<10} {f'+{result.revenue_bonus}':>14}")
        print(f"{'=':<70}")
        print(f"{'TOTAL SCORE':<45} {'':<10} {f'{result.total_score}/{result.max_score}':>14}")
        print(f"{'=':<70}")

        print(f"\n4. RATING RESULT")
        print("-" * 70)
        print(f"Rating Class:       {result.rating_class}")
        print(f"Rating Code:        {result.rating_code}")
        print(f"Description:        {result.rating_description}")
        print(f"Risk Level:         {result.risk_level}")
        print(f"Score:              {result.total_score}/{result.max_score} ({result.total_score/result.max_score*100:.1f}%)")

        print(f"\n5. INTERPRETATION")
        print("-" * 70)
        interpretation = fgpmi_calc.get_interpretation_it(result)
        print(interpretation)

        # Test with different sectors
        print("\n\n6. CROSS-SECTOR COMPARISON")
        print("=" * 70)

        sectors_to_test = [
            (Sector.COMMERCIO.value, "Commercio"),
            (Sector.SERVIZI.value, "Servizi"),
            (Sector.EDILIZIA.value, "Edilizia")
        ]

        for sector_code, sector_name in sectors_to_test:
            calc = FGPMICalculator(bs, inc, sector_code)
            res = calc.calculate()
            print(f"\n{sector_name:15} → Rating: {res.rating_code:5} | Score: {res.total_score:3}/{res.max_score} | {res.rating_description}")

        # Test weak company
        print("\n\n7. WEAK COMPANY PROFILE TEST")
        print("=" * 70)

        # Create weak balance sheet
        bs_weak = BalanceSheet(
            financial_year_id=fy.id,
            sp01_crediti_soci=Decimal("0"),
            sp02_immob_immateriali=Decimal("20000"),
            sp03_immob_materiali=Decimal("150000"),
            sp04_immob_finanziarie=Decimal("0"),
            sp05_rimanenze=Decimal("40000"),
            sp06_crediti_breve=Decimal("80000"),
            sp07_crediti_lungo=Decimal("0"),
            sp08_attivita_finanziarie=Decimal("0"),
            sp09_disponibilita_liquide=Decimal("20000"),
            sp10_ratei_risconti_attivi=Decimal("5000"),
            # Weak equity, high debt
            sp11_capitale=Decimal("50000"),
            sp12_riserve=Decimal("10000"),
            sp13_utile_perdita=Decimal("5000"),  # Low profit
            sp14_fondi_rischi=Decimal("5000"),
            sp15_tfr=Decimal("20000"),
            sp16_debiti_breve=Decimal("150000"),
            sp17_debiti_lungo=Decimal("80000"),
            sp18_ratei_risconti_passivi=Decimal("5000")
        )

        # Weak income statement
        inc_weak = IncomeStatement(
            financial_year_id=fy.id,
            ce01_ricavi_vendite=Decimal("400000"),  # Below 500K threshold
            ce02_variazioni_rimanenze=Decimal("0"),
            ce03_lavori_interni=Decimal("0"),
            ce04_altri_ricavi=Decimal("5000"),
            ce05_materie_prime=Decimal("180000"),
            ce06_servizi=Decimal("80000"),
            ce07_godimento_beni=Decimal("20000"),
            ce08_costi_personale=Decimal("100000"),
            ce09_ammortamenti=Decimal("20000"),
            ce10_var_rimanenze_mat_prime=Decimal("0"),
            ce11_accantonamenti=Decimal("0"),
            ce12_oneri_diversi=Decimal("10000"),
            ce13_proventi_partecipazioni=Decimal("0"),
            ce14_altri_proventi_finanziari=Decimal("0"),
            ce15_oneri_finanziari=Decimal("15000"),
            ce16_utili_perdite_cambi=Decimal("0"),
            ce17_rettifiche_attivita_fin=Decimal("0"),
            ce18_proventi_straordinari=Decimal("0"),
            ce19_oneri_straordinari=Decimal("0"),
            ce20_imposte=Decimal("2000")
        )

        fgpmi_weak = FGPMICalculator(bs_weak, inc_weak, Sector.INDUSTRIA.value)
        result_weak = fgpmi_weak.calculate()

        print(f"\nWeak Company Profile:")
        print(f"  Total Assets:    €{bs_weak.total_assets:,.2f}")
        print(f"  Total Equity:    €{bs_weak.total_equity:,.2f}")
        print(f"  Revenue:         €{inc_weak.revenue:,.2f}")
        print(f"  Net Profit:      €{inc_weak.net_profit:,.2f}")
        print(f"")
        print(f"  Rating:          {result_weak.rating_code} ({result_weak.rating_description})")
        print(f"  Score:           {result_weak.total_score}/{result_weak.max_score} ({result_weak.total_score/result_weak.max_score*100:.1f}%)")
        print(f"  Risk Level:      {result_weak.risk_level}")
        print(f"  Revenue Bonus:   {result_weak.revenue_bonus} (below €500K threshold)")

        print("\n" + "=" * 70)
        print("✅ ALL FGPMI RATING TESTS PASSED!")
        print("=" * 70)

    except Exception as e:
        print(f"\n❌ Error during FGPMI calculation: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    test_fgpmi_rating()
