"""
Forecast Calculation Engine
Generates forecasted Income Statements and Balance Sheets based on budget assumptions
"""
from decimal import Decimal
from typing import Dict, Optional
from sqlalchemy.orm import Session
from database.models import (
    Company, FinancialYear, BalanceSheet, IncomeStatement,
    BudgetScenario, BudgetAssumptions, ForecastYear,
    ForecastBalanceSheet, ForecastIncomeStatement
)


class ForecastEngine:
    """
    Calculates forecasted financial statements based on budget assumptions
    """

    def __init__(self, db_session: Session):
        self.db = db_session

    def generate_forecast(self, scenario_id: int) -> Dict:
        """
        Generate complete forecast for a budget scenario

        Args:
            scenario_id: Budget scenario ID

        Returns:
            Dictionary with forecast results and statistics
        """
        # Get scenario
        scenario = self.db.query(BudgetScenario).filter(
            BudgetScenario.id == scenario_id
        ).first()

        if not scenario:
            raise ValueError(f"Budget scenario {scenario_id} not found")

        # Get base year data
        base_fy = self.db.query(FinancialYear).filter(
            FinancialYear.company_id == scenario.company_id,
            FinancialYear.year == scenario.base_year
        ).first()

        if not base_fy or not base_fy.balance_sheet or not base_fy.income_statement:
            raise ValueError(f"Base year {scenario.base_year} data not found or incomplete")

        base_bs = base_fy.balance_sheet
        base_inc = base_fy.income_statement

        # Get all assumptions for this scenario
        assumptions = self.db.query(BudgetAssumptions).filter(
            BudgetAssumptions.scenario_id == scenario_id
        ).order_by(BudgetAssumptions.forecast_year).all()

        if not assumptions:
            raise ValueError(f"No assumptions found for scenario {scenario_id}")

        forecast_years = []

        # Generate forecast for each year
        for assumption in assumptions:
            # Calculate forecasted income statement
            forecast_inc = self._calculate_income_statement(
                base_inc=base_inc,
                assumption=assumption,
                previous_inc=forecast_years[-1]['income_statement'] if forecast_years else base_inc
            )

            # Calculate forecasted balance sheet
            forecast_bs = self._calculate_balance_sheet(
                base_bs=base_bs,
                base_inc=base_inc,
                forecast_inc=forecast_inc,
                assumption=assumption,
                previous_bs=forecast_years[-1]['balance_sheet'] if forecast_years else base_bs
            )

            # Get or create forecast year
            fy = self.db.query(ForecastYear).filter(
                ForecastYear.scenario_id == scenario_id,
                ForecastYear.year == assumption.forecast_year
            ).first()

            if not fy:
                fy = ForecastYear(
                    scenario_id=scenario_id,
                    year=assumption.forecast_year
                )
                self.db.add(fy)
                self.db.flush()

            # Save or update forecast balance sheet
            existing_bs = self.db.query(ForecastBalanceSheet).filter(
                ForecastBalanceSheet.forecast_year_id == fy.id
            ).first()

            if existing_bs:
                # Update existing
                for field, value in forecast_bs.items():
                    setattr(existing_bs, field, value)
            else:
                # Create new
                new_bs = ForecastBalanceSheet(forecast_year_id=fy.id, **forecast_bs)
                self.db.add(new_bs)
                self.db.flush()
                existing_bs = new_bs

            # Save or update forecast income statement
            existing_inc = self.db.query(ForecastIncomeStatement).filter(
                ForecastIncomeStatement.forecast_year_id == fy.id
            ).first()

            if existing_inc:
                # Update existing
                for field, value in forecast_inc.items():
                    setattr(existing_inc, field, value)
            else:
                # Create new
                new_inc = ForecastIncomeStatement(forecast_year_id=fy.id, **forecast_inc)
                self.db.add(new_inc)
                self.db.flush()
                existing_inc = new_inc

            forecast_years.append({
                'year': assumption.forecast_year,
                'forecast_year_obj': fy,
                'balance_sheet': existing_bs,
                'income_statement': existing_inc
            })

        # Commit all changes
        self.db.commit()

        return {
            'success': True,
            'scenario_id': scenario_id,
            'scenario_name': scenario.name,
            'base_year': scenario.base_year,
            'forecast_years': [fy['year'] for fy in forecast_years],
            'years_generated': len(forecast_years)
        }

    def _calculate_income_statement(
        self,
        base_inc: IncomeStatement,
        assumption: BudgetAssumptions,
        previous_inc
    ) -> Dict:
        """
        Calculate forecasted income statement based on assumptions
        """
        # Apply growth rates to base year values
        ce01 = base_inc.ce01_ricavi_vendite * (Decimal('1') + assumption.revenue_growth_pct / Decimal('100'))
        ce04 = base_inc.ce04_altri_ricavi * (Decimal('1') + assumption.other_revenue_growth_pct / Decimal('100'))

        # Calculate costs - split between variable and fixed components based on user-defined percentages

        # Materials
        base_materials = base_inc.ce05_materie_prime
        fixed_pct_materials = assumption.fixed_materials_percentage / Decimal('100')
        variable_pct_materials = Decimal('1') - fixed_pct_materials
        variable_materials = base_materials * variable_pct_materials
        fixed_materials = base_materials * fixed_pct_materials
        ce05 = (
            variable_materials * (Decimal('1') + assumption.variable_materials_growth_pct / Decimal('100')) +
            fixed_materials * (Decimal('1') + assumption.fixed_materials_growth_pct / Decimal('100'))
        )

        # Services
        base_services = base_inc.ce06_servizi
        fixed_pct_services = assumption.fixed_services_percentage / Decimal('100')
        variable_pct_services = Decimal('1') - fixed_pct_services
        variable_services = base_services * variable_pct_services
        fixed_services = base_services * fixed_pct_services
        ce06 = (
            variable_services * (Decimal('1') + assumption.variable_services_growth_pct / Decimal('100')) +
            fixed_services * (Decimal('1') + assumption.fixed_services_growth_pct / Decimal('100'))
        )

        # Rent/Godimento beni
        ce07 = base_inc.ce07_godimento_beni * (Decimal('1') + assumption.rent_growth_pct / Decimal('100'))

        # Personnel
        ce08 = base_inc.ce08_costi_personale * (Decimal('1') + assumption.personnel_growth_pct / Decimal('100'))

        # Depreciation - calculated based on investments using user-defined depreciation rate
        base_depreciation = base_inc.ce09_ammortamenti
        depreciation_rate = assumption.depreciation_rate / Decimal('100')
        new_depreciation = assumption.investments * depreciation_rate if assumption.investments > 0 else Decimal('0')
        ce09 = base_depreciation + new_depreciation

        # Other costs
        ce12 = base_inc.ce12_oneri_diversi * (Decimal('1') + assumption.other_costs_growth_pct / Decimal('100'))

        # Keep other items constant or zero for simplicity
        ce02 = base_inc.ce02_variazioni_rimanenze
        ce03 = base_inc.ce03_lavori_interni
        ce10 = base_inc.ce10_var_rimanenze_mat_prime
        ce11 = base_inc.ce11_accantonamenti
        ce13 = base_inc.ce13_proventi_partecipazioni
        ce16 = base_inc.ce16_utili_perdite_cambi
        ce17 = base_inc.ce17_rettifiche_attivita_fin
        ce18 = base_inc.ce18_proventi_straordinari
        ce19 = base_inc.ce19_oneri_straordinari

        # Financial income on receivables
        # Will be calculated after balance sheet is projected
        ce14 = Decimal('0')  # Placeholder

        # Financial costs on payables
        # Will be calculated after balance sheet is projected
        ce15 = Decimal('0')  # Placeholder

        # Taxes - use user-defined tax rate (IRES/IRAP)
        production_value = ce01 + ce02 + ce03 + ce04
        production_cost = ce05 + ce06 + ce07 + ce08 + ce09 + ce10 + ce11 + ce12
        ebit = production_value - production_cost
        financial_result = ce13 + ce14 - ce15 + ce16
        profit_before_tax = ebit + financial_result + ce17 + (ce18 - ce19)
        tax_rate_decimal = assumption.tax_rate / Decimal('100')
        ce20 = max(Decimal('0'), profit_before_tax * tax_rate_decimal)

        return {
            'ce01_ricavi_vendite': ce01,
            'ce02_variazioni_rimanenze': ce02,
            'ce03_lavori_interni': ce03,
            'ce04_altri_ricavi': ce04,
            'ce05_materie_prime': ce05,
            'ce06_servizi': ce06,
            'ce07_godimento_beni': ce07,
            'ce08_costi_personale': ce08,
            'ce09_ammortamenti': ce09,
            'ce10_var_rimanenze_mat_prime': ce10,
            'ce11_accantonamenti': ce11,
            'ce12_oneri_diversi': ce12,
            'ce13_proventi_partecipazioni': ce13,
            'ce14_altri_proventi_finanziari': ce14,
            'ce15_oneri_finanziari': ce15,
            'ce16_utili_perdite_cambi': ce16,
            'ce17_rettifiche_attivita_fin': ce17,
            'ce18_proventi_straordinari': ce18,
            'ce19_oneri_straordinari': ce19,
            'ce20_imposte': ce20
        }

    def _calculate_balance_sheet(
        self,
        base_bs: BalanceSheet,
        base_inc: IncomeStatement,
        forecast_inc: Dict,
        assumption: BudgetAssumptions,
        previous_bs
    ) -> Dict:
        """
        Calculate forecasted balance sheet based on assumptions and forecast income statement
        """
        # ASSETS

        # Fixed assets - add investments and subtract depreciation
        base_fixed = (
            base_bs.sp02_immob_immateriali +
            base_bs.sp03_immob_materiali +
            base_bs.sp04_immob_finanziarie
        )
        new_investments = assumption.investments
        depreciation = forecast_inc['ce09_ammortamenti']

        # Distribute investments proportionally across fixed asset categories
        total_base_fixed = base_fixed if base_fixed > 0 else Decimal('1')
        sp02 = base_bs.sp02_immob_immateriali + (new_investments * base_bs.sp02_immob_immateriali / total_base_fixed) - (depreciation * Decimal('0.3'))
        sp03 = base_bs.sp03_immob_materiali + (new_investments * base_bs.sp03_immob_materiali / total_base_fixed) - (depreciation * Decimal('0.6'))
        sp04 = base_bs.sp04_immob_finanziarie + (new_investments * base_bs.sp04_immob_finanziarie / total_base_fixed) - (depreciation * Decimal('0.1'))

        # Ensure non-negative
        sp02 = max(Decimal('0'), sp02)
        sp03 = max(Decimal('0'), sp03)
        sp04 = max(Decimal('0'), sp04)

        # Receivables - apply growth rates
        sp06 = base_bs.sp06_crediti_breve * (Decimal('1') + assumption.receivables_short_growth_pct / Decimal('100'))
        sp07 = base_bs.sp07_crediti_lungo * (Decimal('1') + assumption.receivables_long_growth_pct / Decimal('100'))

        # Other current assets - keep proportional to revenue
        revenue_growth = Decimal('1') + assumption.revenue_growth_pct / Decimal('100')
        sp05 = base_bs.sp05_rimanenze * revenue_growth  # Inventory
        sp08 = base_bs.sp08_attivita_finanziarie  # Keep constant
        sp09 = base_bs.sp09_disponibilita_liquide  # Will be plug
        sp10 = base_bs.sp10_ratei_risconti_attivi

        # Other assets
        sp01 = base_bs.sp01_crediti_soci

        # LIABILITIES & EQUITY

        # Equity - add net profit from forecast
        net_profit = (
            forecast_inc['ce01_ricavi_vendite'] +
            forecast_inc['ce02_variazioni_rimanenze'] +
            forecast_inc['ce03_lavori_interni'] +
            forecast_inc['ce04_altri_ricavi'] -
            forecast_inc['ce05_materie_prime'] -
            forecast_inc['ce06_servizi'] -
            forecast_inc['ce07_godimento_beni'] -
            forecast_inc['ce08_costi_personale'] -
            forecast_inc['ce09_ammortamenti'] -
            forecast_inc['ce10_var_rimanenze_mat_prime'] -
            forecast_inc['ce11_accantonamenti'] -
            forecast_inc['ce12_oneri_diversi'] +
            forecast_inc['ce13_proventi_partecipazioni'] +
            forecast_inc['ce14_altri_proventi_finanziari'] -
            forecast_inc['ce15_oneri_finanziari'] +
            forecast_inc['ce16_utili_perdite_cambi'] +
            forecast_inc['ce17_rettifiche_attivita_fin'] +
            forecast_inc['ce18_proventi_straordinari'] -
            forecast_inc['ce19_oneri_straordinari'] -
            forecast_inc['ce20_imposte']
        )

        sp11 = base_bs.sp11_capitale  # Capital - keep constant
        sp12 = base_bs.sp12_riserve + (previous_bs.sp13_utile_perdita if hasattr(previous_bs, 'sp13_utile_perdita') else base_bs.sp13_utile_perdita)  # Add previous year's profit to reserves
        sp13 = net_profit  # Current year profit

        # Liabilities - apply growth rates
        sp16 = base_bs.sp16_debiti_breve * (Decimal('1') + assumption.payables_short_growth_pct / Decimal('100'))
        sp17 = base_bs.sp17_debiti_lungo  # Keep long-term debt constant for now

        # Other liabilities
        sp14 = base_bs.sp14_fondi_rischi
        sp15 = base_bs.sp15_tfr * (Decimal('1') + assumption.personnel_growth_pct / Decimal('100'))  # TFR grows with personnel
        sp18 = base_bs.sp18_ratei_risconti_passivi

        # Calculate total assets (excluding cash)
        total_assets_no_cash = (
            sp01 + sp02 + sp03 + sp04 + sp05 + sp06 + sp07 + sp08 + sp10
        )

        # Calculate total liabilities
        total_liabilities = (
            sp11 + sp12 + sp13 + sp14 + sp15 + sp16 + sp17 + sp18
        )

        # Cash is the plug to balance
        sp09 = total_liabilities - total_assets_no_cash

        # If cash is negative, increase short-term debt instead
        if sp09 < 0:
            sp16 = sp16 + abs(sp09)
            sp09 = Decimal('0')

        return {
            'sp01_crediti_soci': sp01,
            'sp02_immob_immateriali': sp02,
            'sp03_immob_materiali': sp03,
            'sp04_immob_finanziarie': sp04,
            'sp05_rimanenze': sp05,
            'sp06_crediti_breve': sp06,
            'sp07_crediti_lungo': sp07,
            'sp08_attivita_finanziarie': sp08,
            'sp09_disponibilita_liquide': sp09,
            'sp10_ratei_risconti_attivi': sp10,
            'sp11_capitale': sp11,
            'sp12_riserve': sp12,
            'sp13_utile_perdita': sp13,
            'sp14_fondi_rischi': sp14,
            'sp15_tfr': sp15,
            'sp16_debiti_breve': sp16,
            'sp17_debiti_lungo': sp17,
            'sp18_ratei_risconti_passivi': sp18
        }


def generate_forecast_for_scenario(scenario_id: int, db_session: Session) -> Dict:
    """
    Convenience function to generate forecast

    Args:
        scenario_id: Budget scenario ID
        db_session: Database session

    Returns:
        Forecast results
    """
    engine = ForecastEngine(db_session)
    return engine.generate_forecast(scenario_id)
