"""
Create test data for calculations API testing
"""
import sys
import os

backend_path = os.path.dirname(os.path.abspath(__file__))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from app.core.database import SessionLocal
from database import models
from decimal import Decimal

def create_test_data():
    """Create a company with realistic financial data"""
    db = SessionLocal()

    try:
        # Create company
        company = models.Company(
            name="Test Manufacturing Company",
            tax_id="IT12345678901",
            sector=1,  # INDUSTRIA (Manufacturing)
            notes="Test company for calculations"
        )
        db.add(company)
        db.flush()

        # Create financial year
        fy = models.FinancialYear(
            company_id=company.id,
            year=2024
        )
        db.add(fy)
        db.flush()

        # Create Balance Sheet with realistic values (in euros)
        bs = models.BalanceSheet(
            financial_year_id=fy.id,
            # ASSETS
            sp01_crediti_soci=Decimal("0.00"),
            sp02_immob_immateriali=Decimal("50000.00"),
            sp03_immob_materiali=Decimal("450000.00"),
            sp04_immob_finanziarie=Decimal("0.00"),
            sp05_rimanenze=Decimal("180000.00"),
            sp06_crediti_breve=Decimal("320000.00"),
            sp07_crediti_lungo=Decimal("0.00"),
            sp08_attivita_finanziarie=Decimal("0.00"),
            sp09_disponibilita_liquide=Decimal("150000.00"),
            sp10_ratei_risconti_attivi=Decimal("10000.00"),
            # LIABILITIES & EQUITY
            sp11_capitale=Decimal("100000.00"),
            sp12_riserve=Decimal("250000.00"),
            sp13_utile_perdita=Decimal("80000.00"),
            sp14_fondi_rischi=Decimal("20000.00"),
            sp15_tfr=Decimal("90000.00"),
            sp16_debiti_breve=Decimal("400000.00"),
            sp17_debiti_lungo=Decimal("250000.00"),
            sp18_ratei_risconti_passivi=Decimal("10000.00")
        )
        db.add(bs)

        # Verify balance sheet balances
        print(f"Total Assets: €{bs.total_assets:,.2f}")
        print(f"Total Liabilities: €{bs.total_liabilities:,.2f}")
        print(f"Balanced: {bs.is_balanced()}")

        # Create Income Statement with realistic values
        inc = models.IncomeStatement(
            financial_year_id=fy.id,
            # REVENUE
            ce01_ricavi_vendite=Decimal("1500000.00"),
            ce02_variazioni_rimanenze=Decimal("0.00"),
            ce03_lavori_interni=Decimal("0.00"),
            ce04_altri_ricavi=Decimal("20000.00"),
            # COSTS
            ce05_materie_prime=Decimal("600000.00"),
            ce06_servizi=Decimal("250000.00"),
            ce07_godimento_beni=Decimal("30000.00"),
            ce08_costi_personale=Decimal("380000.00"),
            ce09_ammortamenti=Decimal("90000.00"),
            ce10_var_rimanenze_mat_prime=Decimal("0.00"),
            ce11_accantonamenti=Decimal("10000.00"),
            ce12_oneri_diversi=Decimal("20000.00"),
            # FINANCIAL
            ce13_proventi_partecipazioni=Decimal("0.00"),
            ce14_altri_proventi_finanziari=Decimal("5000.00"),
            ce15_oneri_finanziari=Decimal("35000.00"),
            ce16_utili_perdite_cambi=Decimal("0.00"),
            # EXTRAORDINARY & TAXES
            ce17_rettifiche_attivita_fin=Decimal("0.00"),
            ce18_proventi_straordinari=Decimal("0.00"),
            ce19_oneri_straordinari=Decimal("0.00"),
            ce20_imposte=Decimal("30000.00")
        )
        db.add(inc)

        # Print key metrics
        print(f"\nRevenue: €{inc.revenue:,.2f}")
        print(f"EBITDA: €{inc.ebitda:,.2f}")
        print(f"EBIT: €{inc.ebit:,.2f}")
        print(f"Net Profit: €{inc.net_profit:,.2f}")

        db.commit()

        print(f"\n✓ Created company ID {company.id} with financial data for year {fy.year}")
        print(f"Use these values to test: company_id={company.id}, year={fy.year}")

        return company.id, fy.year

    except Exception as e:
        db.rollback()
        print(f"Error creating test data: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    create_test_data()
