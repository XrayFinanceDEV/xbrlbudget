"""
Test script to verify database models and basic functionality
"""
from decimal import Decimal
from database.db import init_db, SessionLocal, drop_all
from database.models import Company, FinancialYear, BalanceSheet, IncomeStatement
from config import Sector

def test_database():
    """Test database creation and basic operations"""

    print("1. Dropping existing tables...")
    drop_all()

    print("2. Creating database tables...")
    init_db()
    print("   ✓ Tables created successfully")

    # Create a session
    db = SessionLocal()

    try:
        print("\n3. Creating test company...")
        company = Company(
            name="Test S.r.l.",
            tax_id="12345678901",
            sector=Sector.INDUSTRIA.value,
            notes="Test company for development"
        )
        db.add(company)
        db.commit()
        db.refresh(company)
        print(f"   ✓ Company created: {company}")

        print("\n4. Creating financial year 2024...")
        fy = FinancialYear(
            company_id=company.id,
            year=2024
        )
        db.add(fy)
        db.commit()
        db.refresh(fy)
        print(f"   ✓ Financial Year created: {fy}")

        print("\n5. Creating balance sheet...")
        bs = BalanceSheet(
            financial_year_id=fy.id,
            # Assets
            sp01_crediti_soci=Decimal("0"),
            sp02_immob_immateriali=Decimal("50000"),
            sp03_immob_materiali=Decimal("250000"),
            sp04_immob_finanziarie=Decimal("0"),
            sp05_rimanenze=Decimal("80000"),
            sp06_crediti_breve=Decimal("150000"),
            sp07_crediti_lungo=Decimal("0"),
            sp08_attivita_finanziarie=Decimal("0"),
            sp09_disponibilita_liquide=Decimal("70000"),
            sp10_ratei_risconti_attivi=Decimal("5000"),
            # Liabilities & Equity
            sp11_capitale=Decimal("100000"),
            sp12_riserve=Decimal("50000"),
            sp13_utile_perdita=Decimal("30000"),
            sp14_fondi_rischi=Decimal("0"),
            sp15_tfr=Decimal("25000"),
            sp16_debiti_breve=Decimal("300000"),
            sp17_debiti_lungo=Decimal("100000"),
            sp18_ratei_risconti_passivi=Decimal("0")
        )
        db.add(bs)
        db.commit()
        db.refresh(bs)
        print(f"   ✓ Balance Sheet created")
        print(f"      Total Assets: €{bs.total_assets:,.2f}")
        print(f"      Total Equity: €{bs.total_equity:,.2f}")
        print(f"      Total Liabilities: €{bs.total_liabilities:,.2f}")
        print(f"      Balanced: {bs.is_balanced()}")

        print("\n6. Creating income statement...")
        inc = IncomeStatement(
            financial_year_id=fy.id,
            # Revenue
            ce01_ricavi_vendite=Decimal("500000"),
            ce02_variazioni_rimanenze=Decimal("0"),
            ce03_lavori_interni=Decimal("0"),
            ce04_altri_ricavi=Decimal("10000"),
            # Costs
            ce05_materie_prime=Decimal("200000"),
            ce06_servizi=Decimal("100000"),
            ce07_godimento_beni=Decimal("20000"),
            ce08_costi_personale=Decimal("120000"),
            ce09_ammortamenti=Decimal("30000"),
            ce10_var_rimanenze_mat_prime=Decimal("0"),
            ce11_accantonamenti=Decimal("0"),
            ce12_oneri_diversi=Decimal("10000"),
            # Financial
            ce13_proventi_partecipazioni=Decimal("0"),
            ce14_altri_proventi_finanziari=Decimal("1000"),
            ce15_oneri_finanziari=Decimal("15000"),
            ce16_utili_perdite_cambi=Decimal("0"),
            # Other
            ce17_rettifiche_attivita_fin=Decimal("0"),
            ce18_proventi_straordinari=Decimal("0"),
            ce19_oneri_straordinari=Decimal("0"),
            ce20_imposte=Decimal("6000")
        )
        db.add(inc)
        db.commit()
        db.refresh(inc)
        print(f"   ✓ Income Statement created")
        print(f"      Revenue: €{inc.revenue:,.2f}")
        print(f"      EBITDA: €{inc.ebitda:,.2f}")
        print(f"      EBIT: €{inc.ebit:,.2f}")
        print(f"      Net Profit: €{inc.net_profit:,.2f}")

        print("\n7. Testing relationships...")
        # Test relationships
        company_from_db = db.query(Company).filter(Company.id == company.id).first()
        print(f"   Company: {company_from_db.name}")
        print(f"   Financial Years: {len(company_from_db.financial_years)}")
        if company_from_db.financial_years:
            fy_from_db = company_from_db.financial_years[0]
            print(f"   Year: {fy_from_db.year}")
            print(f"   Has Balance Sheet: {fy_from_db.balance_sheet is not None}")
            print(f"   Has Income Statement: {fy_from_db.income_statement is not None}")

        print("\n✅ All database tests passed!")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    test_database()
