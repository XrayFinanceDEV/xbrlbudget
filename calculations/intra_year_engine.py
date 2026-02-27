"""
Intra-Year Projection Engine
Projects partial-year financials (e.g., 9 months) to a full 12-month year.

Default method: Simple annualization (value * 12 / period_months)
User can override via assumptions (growth % vs reference full year).
The frontend converts user overrides to growth % before saving.
"""
from decimal import Decimal
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from database.models import (
    FinancialYear, BalanceSheet, IncomeStatement,
    BudgetScenario, BudgetAssumptions, ForecastYear,
    ForecastBalanceSheet, ForecastIncomeStatement
)


# P&L line item codes for comparison
CE_FIELDS = [
    ('ce01_ricavi_vendite', 'Ricavi delle vendite'),
    ('ce02_variazioni_rimanenze', 'Variazioni rimanenze prodotti'),
    ('ce03_lavori_interni', 'Lavori interni capitalizzati'),
    ('ce04_altri_ricavi', 'Altri ricavi e proventi'),
    ('ce05_materie_prime', 'Materie prime e consumo'),
    ('ce06_servizi', 'Costi per servizi'),
    ('ce07_godimento_beni', 'Godimento beni di terzi'),
    ('ce08_costi_personale', 'Costi del personale'),
    ('ce09_ammortamenti', 'Ammortamenti e svalutazioni'),
    ('ce10_var_rimanenze_mat_prime', 'Variazioni rimanenze materie prime'),
    ('ce11_accantonamenti', 'Accantonamenti per rischi'),
    ('ce12_oneri_diversi', 'Oneri diversi di gestione'),
    ('ce13_proventi_partecipazioni', 'Proventi da partecipazioni'),
    ('ce14_altri_proventi_finanziari', 'Altri proventi finanziari'),
    ('ce15_oneri_finanziari', 'Oneri finanziari'),
    ('ce16_utili_perdite_cambi', 'Utili/perdite su cambi'),
    ('ce17_rettifiche_attivita_fin', 'Rettifiche attivita finanziarie'),
    ('ce18_proventi_straordinari', 'Proventi straordinari'),
    ('ce19_oneri_straordinari', 'Oneri straordinari'),
    ('ce20_imposte', 'Imposte sul reddito'),
]

# BS line item codes for comparison
SP_FIELDS = [
    ('sp01_crediti_soci', 'Crediti verso soci'),
    ('sp02_immob_immateriali', 'Immobilizzazioni immateriali'),
    ('sp03_immob_materiali', 'Immobilizzazioni materiali'),
    ('sp04_immob_finanziarie', 'Immobilizzazioni finanziarie'),
    ('sp05_rimanenze', 'Rimanenze'),
    ('sp06_crediti_breve', 'Crediti esigibili entro 12 mesi'),
    ('sp07_crediti_lungo', 'Crediti esigibili oltre 12 mesi'),
    ('sp08_attivita_finanziarie', 'Attivita finanziarie'),
    ('sp09_disponibilita_liquide', 'Disponibilita liquide'),
    ('sp10_ratei_risconti_attivi', 'Ratei e risconti attivi'),
    ('sp11_capitale', 'Capitale sociale'),
    ('sp12_riserve', 'Riserve'),
    ('sp13_utile_perdita', 'Utile/Perdita di esercizio'),
    ('sp14_fondi_rischi', 'Fondi per rischi e oneri'),
    ('sp15_tfr', 'TFR'),
    ('sp16_debiti_breve', 'Debiti esigibili entro 12 mesi'),
    ('sp17_debiti_lungo', 'Debiti esigibili oltre 12 mesi'),
    ('sp18_ratei_risconti_passivi', 'Ratei e risconti passivi'),
]


def _safe_divide(numerator, denominator, default=Decimal('0')):
    """Safe division returning default if denominator is zero."""
    if denominator == 0 or denominator is None:
        return default
    return numerator / denominator


def _get_field(obj, field_name, default=Decimal('0')):
    """Get a Decimal field from an ORM object, defaulting to 0."""
    val = getattr(obj, field_name, None)
    if val is None:
        return default
    return Decimal(str(val))


class IntraYearEngine:
    """
    Projects partial-year financials to a full 12-month year.

    Workflow:
    1. Load partial-year data (e.g., 9 months of 2025) and reference full year (2024)
    2. For P&L: apply growth rates from assumptions to reference year values
       (frontend pre-calculates growth rates from annualized defaults + user overrides)
    3. For BS: use partial year actuals for fixed assets, turnover ratios for working capital
    4. Recalculate taxes on projected pre-tax profit
    5. Store result as ForecastYear (compatible with existing /analysis endpoint)
    """

    def __init__(self, db_session: Session):
        self.db = db_session

    def get_comparison(self, scenario_id: int) -> Dict:
        """
        Returns comparison data between partial year and reference full year.

        For each P&L and BS line item: partial value, reference value,
        percentage of reference, and annualized value.
        """
        scenario = self._load_scenario(scenario_id)
        partial_fy, ref_fy = self._load_financial_years(scenario)

        period_months = scenario.period_months
        factor = Decimal('12') / Decimal(str(period_months))

        income_items = []
        for field_name, label in CE_FIELDS:
            partial_val = _get_field(partial_fy.income_statement, field_name)
            ref_val = _get_field(ref_fy.income_statement, field_name)
            annualized = partial_val * factor
            pct = float(_safe_divide(partial_val * Decimal('100'), ref_val)) if ref_val != 0 else 0.0

            income_items.append({
                'code': field_name,
                'label': label,
                'partial_value': float(partial_val),
                'reference_value': float(ref_val),
                'pct_of_reference': round(pct, 2),
                'annualized_value': float(annualized.quantize(Decimal('0.01'))),
            })

        balance_items = []
        for field_name, label in SP_FIELDS:
            partial_val = _get_field(partial_fy.balance_sheet, field_name)
            ref_val = _get_field(ref_fy.balance_sheet, field_name)
            # BS items are stock (point-in-time), annualization doesn't apply
            # Show partial value as "annualized" for consistency
            pct = float(_safe_divide(partial_val * Decimal('100'), ref_val)) if ref_val != 0 else 0.0

            balance_items.append({
                'code': field_name,
                'label': label,
                'partial_value': float(partial_val),
                'reference_value': float(ref_val),
                'pct_of_reference': round(pct, 2),
                'annualized_value': float(partial_val),  # BS = point-in-time, no annualization
            })

        return {
            'partial_year': scenario.base_year + 1,  # e.g., 2025
            'reference_year': scenario.base_year,     # e.g., 2024
            'period_months': period_months,
            'income_items': income_items,
            'balance_items': balance_items,
        }

    def generate_projection(self, scenario_id: int) -> Dict:
        """
        Generate projected 12-month financials from partial-year data.

        Returns summary dict compatible with ForecastEngine.generate_forecast().
        """
        scenario = self._load_scenario(scenario_id)
        partial_fy, ref_fy = self._load_financial_years(scenario)

        # Load assumptions (single year for infrannuale)
        assumption = self.db.query(BudgetAssumptions).filter(
            BudgetAssumptions.scenario_id == scenario_id
        ).first()

        if not assumption:
            raise ValueError(f"No assumptions found for scenario {scenario_id}")

        period_months = scenario.period_months
        projection_year = assumption.forecast_year

        # Project income statement
        projected_inc = self._project_income_statement(
            partial_inc=partial_fy.income_statement,
            ref_inc=ref_fy.income_statement,
            assumption=assumption,
            period_months=period_months
        )

        # Project balance sheet
        projected_bs = self._project_balance_sheet(
            partial_bs=partial_fy.balance_sheet,
            ref_bs=ref_fy.balance_sheet,
            projected_inc=projected_inc,
            ref_inc=ref_fy.income_statement,
            assumption=assumption,
            period_months=period_months
        )

        # Store as ForecastYear
        self._save_forecast(scenario_id, projection_year, projected_bs, projected_inc)
        self.db.commit()

        return {
            'success': True,
            'scenario_id': scenario_id,
            'scenario_name': scenario.name,
            'base_year': scenario.base_year,
            'forecast_years': [projection_year],
            'years_generated': 1,
        }

    def _load_scenario(self, scenario_id: int) -> BudgetScenario:
        scenario = self.db.query(BudgetScenario).filter(
            BudgetScenario.id == scenario_id
        ).first()
        if not scenario:
            raise ValueError(f"Scenario {scenario_id} not found")
        if scenario.scenario_type != 'infrannuale':
            raise ValueError(f"Scenario {scenario_id} is not infrannuale type")
        if not scenario.period_months:
            raise ValueError(f"Scenario {scenario_id} has no period_months set")
        return scenario

    def _load_financial_years(self, scenario: BudgetScenario):
        """Load partial year and reference full year data."""
        company_id = scenario.company_id
        partial_year_num = scenario.base_year + 1  # e.g., 2025
        ref_year_num = scenario.base_year           # e.g., 2024

        # Load partial year (the imported partial-year data)
        from database.queries import get_fy_partial, get_fy_prefer_full
        partial_fy = get_fy_partial(self.db, company_id, partial_year_num)

        if not partial_fy or not partial_fy.balance_sheet or not partial_fy.income_statement:
            raise ValueError(
                f"Partial year {partial_year_num} data not found or incomplete for company {company_id}"
            )

        # Load reference full year (must be full-year record)
        ref_fy = get_fy_prefer_full(self.db, company_id, ref_year_num)

        if not ref_fy or not ref_fy.balance_sheet or not ref_fy.income_statement:
            raise ValueError(
                f"Reference year {ref_year_num} data not found or incomplete for company {company_id}"
            )

        return partial_fy, ref_fy

    def _project_income_statement(
        self,
        partial_inc: IncomeStatement,
        ref_inc: IncomeStatement,
        assumption: BudgetAssumptions,
        period_months: int
    ) -> Dict:
        """
        Project P&L to full 12 months.

        Uses growth rates from assumptions applied to reference year.
        The frontend pre-calculates these rates:
        - Default: growth_pct = (annualized / reference - 1) * 100
        - Override: growth_pct = (user_value / reference - 1) * 100
        """
        factor = Decimal('12') / Decimal(str(period_months))

        # Revenue and other income: apply growth rates to reference year
        ref_ce01 = _get_field(ref_inc, 'ce01_ricavi_vendite')
        ce01 = ref_ce01 * (Decimal('1') + assumption.revenue_growth_pct / Decimal('100'))

        ref_ce04 = _get_field(ref_inc, 'ce04_altri_ricavi')
        ce04 = ref_ce04 * (Decimal('1') + assumption.other_revenue_growth_pct / Decimal('100'))

        # Costs: apply growth rates or annualize
        # Materials - use combined variable/fixed approach
        ref_ce05 = _get_field(ref_inc, 'ce05_materie_prime')
        fixed_pct = assumption.fixed_materials_percentage / Decimal('100')
        variable_pct = Decimal('1') - fixed_pct
        ce05 = (
            ref_ce05 * variable_pct * (Decimal('1') + assumption.variable_materials_growth_pct / Decimal('100')) +
            ref_ce05 * fixed_pct * (Decimal('1') + assumption.fixed_materials_growth_pct / Decimal('100'))
        )

        # Services
        ref_ce06 = _get_field(ref_inc, 'ce06_servizi')
        fixed_pct_svc = assumption.fixed_services_percentage / Decimal('100')
        variable_pct_svc = Decimal('1') - fixed_pct_svc
        ce06 = (
            ref_ce06 * variable_pct_svc * (Decimal('1') + assumption.variable_services_growth_pct / Decimal('100')) +
            ref_ce06 * fixed_pct_svc * (Decimal('1') + assumption.fixed_services_growth_pct / Decimal('100'))
        )

        # Rent
        ref_ce07 = _get_field(ref_inc, 'ce07_godimento_beni')
        ce07 = ref_ce07 * (Decimal('1') + assumption.rent_growth_pct / Decimal('100'))

        # Personnel
        ref_ce08 = _get_field(ref_inc, 'ce08_costi_personale')
        ce08 = ref_ce08 * (Decimal('1') + assumption.personnel_growth_pct / Decimal('100'))

        # TFR accrual - maintain same % of personnel as reference
        ref_ce08a = _get_field(ref_inc, 'ce08a_tfr_accrual')
        if ref_ce08 > 0 and ref_ce08a > 0:
            tfr_rate = ref_ce08a / ref_ce08
            ce08a = ce08 * tfr_rate
        else:
            ce08a = Decimal('0')

        # Depreciation - annualize (linear accrual) + new investments
        partial_ce09 = _get_field(partial_inc, 'ce09_ammortamenti')
        ce09 = partial_ce09 * factor
        # Add depreciation on new investments if any
        if assumption.investments > 0:
            depreciation_rate = assumption.depreciation_rate / Decimal('100')
            remaining_months = Decimal('12') - Decimal(str(period_months))
            new_dep = assumption.investments * depreciation_rate * remaining_months / Decimal('12')
            ce09 = ce09 + new_dep

        # Other costs
        ref_ce12 = _get_field(ref_inc, 'ce12_oneri_diversi')
        ce12 = ref_ce12 * (Decimal('1') + assumption.other_costs_growth_pct / Decimal('100'))

        # Items kept from annualization of partial year (less subject to user control)
        ce02 = _get_field(partial_inc, 'ce02_variazioni_rimanenze') * factor
        ce03 = _get_field(partial_inc, 'ce03_lavori_interni') * factor
        ce10 = _get_field(partial_inc, 'ce10_var_rimanenze_mat_prime') * factor
        ce11 = _get_field(partial_inc, 'ce11_accantonamenti') * factor
        ce13 = _get_field(partial_inc, 'ce13_proventi_partecipazioni') * factor
        ce14 = assumption.ce14_override if assumption.ce14_override is not None else _get_field(partial_inc, 'ce14_altri_proventi_finanziari') * factor
        ce15 = assumption.ce15_override if assumption.ce15_override is not None else _get_field(partial_inc, 'ce15_oneri_finanziari') * factor
        ce16 = _get_field(partial_inc, 'ce16_utili_perdite_cambi') * factor
        ce17 = _get_field(partial_inc, 'ce17_rettifiche_attivita_fin') * factor
        ce18 = _get_field(partial_inc, 'ce18_proventi_straordinari') * factor
        ce19 = _get_field(partial_inc, 'ce19_oneri_straordinari') * factor

        # Taxes - recalculate on projected pre-tax profit
        production_value = ce01 + ce02 + ce03 + ce04
        production_cost = ce05 + ce06 + ce07 + ce08 + ce09 + ce10 + ce11 + ce12
        ebit = production_value - production_cost
        financial_result = ce13 + ce14 - ce15 + ce16
        profit_before_tax = ebit + financial_result + ce17 + (ce18 - ce19)
        tax_rate = assumption.tax_rate / Decimal('100')
        ce20 = max(Decimal('0'), profit_before_tax * tax_rate)

        return {
            'ce01_ricavi_vendite': ce01,
            'ce02_variazioni_rimanenze': ce02,
            'ce03_lavori_interni': ce03,
            'ce04_altri_ricavi': ce04,
            'ce05_materie_prime': ce05,
            'ce06_servizi': ce06,
            'ce07_godimento_beni': ce07,
            'ce08_costi_personale': ce08,
            'ce08a_tfr_accrual': ce08a,
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
            'ce20_imposte': ce20,
        }

    def _project_balance_sheet(
        self,
        partial_bs: BalanceSheet,
        ref_bs: BalanceSheet,
        projected_inc: Dict,
        ref_inc: IncomeStatement,
        assumption: BudgetAssumptions,
        period_months: int
    ) -> Dict:
        """
        Project balance sheet to year-end.

        Fixed assets: partial year values adjusted for remaining depreciation.
        Working capital: turnover ratios from reference year applied to projected P&L.
        Equity: capital constant, reserves + previous profit, current profit from projection.
        Cash: plug variable.
        """
        remaining_months = Decimal('12') - Decimal(str(period_months))

        # FIXED ASSETS - keep partial year values, adjust for remaining depreciation
        partial_sp02 = _get_field(partial_bs, 'sp02_immob_immateriali')
        partial_sp03 = _get_field(partial_bs, 'sp03_immob_materiali')
        partial_sp04 = _get_field(partial_bs, 'sp04_immob_finanziarie')

        # Distribute remaining depreciation proportionally
        total_dep = projected_inc['ce09_ammortamenti']
        partial_dep = _get_field(partial_bs, 'sp02_immob_immateriali')  # not really, need partial year dep
        # Use: remaining depreciation = total_annual_dep * (remaining_months / 12)
        remaining_dep = total_dep * remaining_months / Decimal('12')

        total_fixed = partial_sp02 + partial_sp03 + partial_sp04
        if total_fixed > 0:
            sp02 = max(Decimal('0'), partial_sp02 - remaining_dep * partial_sp02 / total_fixed)
            sp03 = max(Decimal('0'), partial_sp03 - remaining_dep * partial_sp03 / total_fixed)
            sp04 = max(Decimal('0'), partial_sp04 - remaining_dep * partial_sp04 / total_fixed)
        else:
            sp02 = partial_sp02
            sp03 = partial_sp03
            sp04 = partial_sp04

        # Add new investments if any
        if assumption.investments > 0:
            inv = assumption.investments
            if total_fixed > 0:
                sp02 = sp02 + inv * partial_sp02 / total_fixed
                sp03 = sp03 + inv * partial_sp03 / total_fixed
                sp04 = sp04 + inv * partial_sp04 / total_fixed
            else:
                sp03 = sp03 + inv  # Default to tangible

        # WORKING CAPITAL - use turnover ratios from reference year
        projected_revenue = projected_inc['ce01_ricavi_vendite']
        projected_costs = (
            projected_inc['ce05_materie_prime'] +
            projected_inc['ce06_servizi'] +
            projected_inc['ce07_godimento_beni']
        )

        ref_revenue = _get_field(ref_inc, 'ce01_ricavi_vendite')
        ref_sp05 = _get_field(ref_bs, 'sp05_rimanenze')
        ref_sp06 = _get_field(ref_bs, 'sp06_crediti_breve')
        ref_sp07 = _get_field(ref_bs, 'sp07_crediti_lungo')
        ref_sp16 = _get_field(ref_bs, 'sp16_debiti_breve')
        ref_costs = (
            _get_field(ref_inc, 'ce05_materie_prime') +
            _get_field(ref_inc, 'ce06_servizi') +
            _get_field(ref_inc, 'ce07_godimento_beni')
        )

        # Inventory: proportional to cost of materials
        ref_ce05 = _get_field(ref_inc, 'ce05_materie_prime')
        sp05 = projected_inc['ce05_materie_prime'] * _safe_divide(ref_sp05, ref_ce05, Decimal('0'))

        # Short-term receivables: proportional to revenue
        sp06 = projected_revenue * _safe_divide(ref_sp06, ref_revenue, Decimal('0'))

        # Long-term receivables: keep from partial year (stable)
        sp07 = _get_field(partial_bs, 'sp07_crediti_lungo')

        # Other current assets: keep from partial year
        sp01 = _get_field(partial_bs, 'sp01_crediti_soci')
        sp08 = _get_field(partial_bs, 'sp08_attivita_finanziarie')
        sp10 = _get_field(partial_bs, 'sp10_ratei_risconti_attivi')

        # EQUITY
        sp11 = _get_field(ref_bs, 'sp11_capitale')  # Capital - keep from reference
        # Reserves: reference reserves + reference year profit (moved to reserves at year-end)
        ref_profit = _get_field(ref_bs, 'sp13_utile_perdita')
        sp12 = _get_field(ref_bs, 'sp12_riserve') + ref_profit

        # Current year projected net profit
        net_profit = (
            projected_inc['ce01_ricavi_vendite'] +
            projected_inc['ce02_variazioni_rimanenze'] +
            projected_inc['ce03_lavori_interni'] +
            projected_inc['ce04_altri_ricavi'] -
            projected_inc['ce05_materie_prime'] -
            projected_inc['ce06_servizi'] -
            projected_inc['ce07_godimento_beni'] -
            projected_inc['ce08_costi_personale'] -
            projected_inc['ce09_ammortamenti'] -
            projected_inc['ce10_var_rimanenze_mat_prime'] -
            projected_inc['ce11_accantonamenti'] -
            projected_inc['ce12_oneri_diversi'] +
            projected_inc['ce13_proventi_partecipazioni'] +
            projected_inc['ce14_altri_proventi_finanziari'] -
            projected_inc['ce15_oneri_finanziari'] +
            projected_inc['ce16_utili_perdite_cambi'] +
            projected_inc['ce17_rettifiche_attivita_fin'] +
            projected_inc['ce18_proventi_straordinari'] -
            projected_inc['ce19_oneri_straordinari'] -
            projected_inc['ce20_imposte']
        )
        sp13 = net_profit

        # Reserve details
        sp12a = _get_field(ref_bs, 'sp12a_riserva_sovrapprezzo')
        sp12b = _get_field(ref_bs, 'sp12b_riserve_rivalutazione')
        sp12c = _get_field(ref_bs, 'sp12c_riserva_legale')
        sp12d = _get_field(ref_bs, 'sp12d_riserve_statutarie')
        sp12e = _get_field(ref_bs, 'sp12e_altre_riserve')
        sp12f = _get_field(ref_bs, 'sp12f_riserva_copertura_flussi')
        sp12g = _get_field(ref_bs, 'sp12g_utili_perdite_portati') + ref_profit
        sp12h = _get_field(ref_bs, 'sp12h_riserva_neg_azioni_proprie')

        # LIABILITIES
        sp14 = _get_field(ref_bs, 'sp14_fondi_rischi')
        # TFR: reference TFR + annual accrual
        sp15 = _get_field(ref_bs, 'sp15_tfr') + projected_inc.get('ce08a_tfr_accrual', Decimal('0'))

        # Short-term debt: proportional to operating costs (turnover ratio)
        sp16 = projected_costs * _safe_divide(ref_sp16, ref_costs, Decimal('0'))

        # Long-term debt: keep from reference (stable)
        sp17 = _get_field(ref_bs, 'sp17_debiti_lungo')

        # Add new financing if any
        if assumption.financing_amount > 0:
            sp17 = sp17 + assumption.financing_amount

        sp18 = _get_field(ref_bs, 'sp18_ratei_risconti_passivi')

        # CASH PLUG - balance the sheet
        total_assets_no_cash = sp01 + sp02 + sp03 + sp04 + sp05 + sp06 + sp07 + sp08 + sp10
        total_liabilities = sp11 + sp12 + sp13 + sp14 + sp15 + sp16 + sp17 + sp18
        sp09 = total_liabilities - total_assets_no_cash

        # If cash negative, increase short-term debt
        if sp09 < 0:
            sp16 = sp16 + abs(sp09)
            sp09 = Decimal('0')

        # Debt detail breakdowns (proportional from reference)
        sp04a, sp04b, sp04c, sp04d, sp04e = self._distribute_sp04(ref_bs, sp04)
        sp16a, sp16b, sp16c, sp16d, sp16e, sp16f, sp16g = self._distribute_sp16(ref_bs, sp16)
        sp17a, sp17b, sp17c, sp17d, sp17e, sp17f, sp17g = self._distribute_sp17(ref_bs, sp17)

        return {
            'sp01_crediti_soci': sp01,
            'sp02_immob_immateriali': sp02,
            'sp03_immob_materiali': sp03,
            'sp04_immob_finanziarie': sp04,
            'sp04a_partecipazioni': sp04a,
            'sp04b_crediti_immob_breve': sp04b,
            'sp04c_crediti_immob_lungo': sp04c,
            'sp04d_altri_titoli': sp04d,
            'sp04e_strumenti_derivati_attivi': sp04e,
            'sp05_rimanenze': sp05,
            'sp06_crediti_breve': sp06,
            'sp07_crediti_lungo': sp07,
            'sp08_attivita_finanziarie': sp08,
            'sp09_disponibilita_liquide': sp09,
            'sp10_ratei_risconti_attivi': sp10,
            'sp11_capitale': sp11,
            'sp12_riserve': sp12,
            'sp12a_riserva_sovrapprezzo': sp12a,
            'sp12b_riserve_rivalutazione': sp12b,
            'sp12c_riserva_legale': sp12c,
            'sp12d_riserve_statutarie': sp12d,
            'sp12e_altre_riserve': sp12e,
            'sp12f_riserva_copertura_flussi': sp12f,
            'sp12g_utili_perdite_portati': sp12g,
            'sp12h_riserva_neg_azioni_proprie': sp12h,
            'sp13_utile_perdita': sp13,
            'sp14_fondi_rischi': sp14,
            'sp15_tfr': sp15,
            'sp16_debiti_breve': sp16,
            'sp17_debiti_lungo': sp17,
            'sp16a_debiti_banche_breve': sp16a,
            'sp17a_debiti_banche_lungo': sp17a,
            'sp16b_debiti_altri_finanz_breve': sp16b,
            'sp17b_debiti_altri_finanz_lungo': sp17b,
            'sp16c_debiti_obbligazioni_breve': sp16c,
            'sp17c_debiti_obbligazioni_lungo': sp17c,
            'sp16d_debiti_fornitori_breve': sp16d,
            'sp17d_debiti_fornitori_lungo': sp17d,
            'sp16e_debiti_tributari_breve': sp16e,
            'sp17e_debiti_tributari_lungo': sp17e,
            'sp16f_debiti_previdenza_breve': sp16f,
            'sp17f_debiti_previdenza_lungo': sp17f,
            'sp16g_altri_debiti_breve': sp16g,
            'sp17g_altri_debiti_lungo': sp17g,
            'sp18_ratei_risconti_passivi': sp18,
        }

    def _distribute_sp04(self, ref_bs, sp04_total):
        """Distribute sp04 into sub-categories proportionally from reference."""
        total = (
            _get_field(ref_bs, 'sp04a_partecipazioni') +
            _get_field(ref_bs, 'sp04b_crediti_immob_breve') +
            _get_field(ref_bs, 'sp04c_crediti_immob_lungo') +
            _get_field(ref_bs, 'sp04d_altri_titoli') +
            _get_field(ref_bs, 'sp04e_strumenti_derivati_attivi')
        )
        if total > 0:
            r = sp04_total / total
            return (
                _get_field(ref_bs, 'sp04a_partecipazioni') * r,
                _get_field(ref_bs, 'sp04b_crediti_immob_breve') * r,
                _get_field(ref_bs, 'sp04c_crediti_immob_lungo') * r,
                _get_field(ref_bs, 'sp04d_altri_titoli') * r,
                _get_field(ref_bs, 'sp04e_strumenti_derivati_attivi') * r,
            )
        return (Decimal('0'),) * 5

    def _distribute_sp16(self, ref_bs, sp16_total):
        """Distribute sp16 into sub-categories proportionally from reference."""
        total = (
            _get_field(ref_bs, 'sp16a_debiti_banche_breve') +
            _get_field(ref_bs, 'sp16b_debiti_altri_finanz_breve') +
            _get_field(ref_bs, 'sp16c_debiti_obbligazioni_breve') +
            _get_field(ref_bs, 'sp16d_debiti_fornitori_breve') +
            _get_field(ref_bs, 'sp16e_debiti_tributari_breve') +
            _get_field(ref_bs, 'sp16f_debiti_previdenza_breve') +
            _get_field(ref_bs, 'sp16g_altri_debiti_breve')
        )
        if total > 0:
            r = sp16_total / total
            return (
                _get_field(ref_bs, 'sp16a_debiti_banche_breve') * r,
                _get_field(ref_bs, 'sp16b_debiti_altri_finanz_breve') * r,
                _get_field(ref_bs, 'sp16c_debiti_obbligazioni_breve') * r,
                _get_field(ref_bs, 'sp16d_debiti_fornitori_breve') * r,
                _get_field(ref_bs, 'sp16e_debiti_tributari_breve') * r,
                _get_field(ref_bs, 'sp16f_debiti_previdenza_breve') * r,
                _get_field(ref_bs, 'sp16g_altri_debiti_breve') * r,
            )
        # Default distribution
        fin = sp16_total * Decimal('0.4')
        ops = sp16_total * Decimal('0.6')
        return (
            fin * Decimal('0.7'), fin * Decimal('0.2'), fin * Decimal('0.1'),
            ops * Decimal('0.6'), ops * Decimal('0.2'), ops * Decimal('0.1'), ops * Decimal('0.1'),
        )

    def _distribute_sp17(self, ref_bs, sp17_total):
        """Distribute sp17 into sub-categories proportionally from reference."""
        total = (
            _get_field(ref_bs, 'sp17a_debiti_banche_lungo') +
            _get_field(ref_bs, 'sp17b_debiti_altri_finanz_lungo') +
            _get_field(ref_bs, 'sp17c_debiti_obbligazioni_lungo') +
            _get_field(ref_bs, 'sp17d_debiti_fornitori_lungo') +
            _get_field(ref_bs, 'sp17e_debiti_tributari_lungo') +
            _get_field(ref_bs, 'sp17f_debiti_previdenza_lungo') +
            _get_field(ref_bs, 'sp17g_altri_debiti_lungo')
        )
        if total > 0:
            r = sp17_total / total
            return (
                _get_field(ref_bs, 'sp17a_debiti_banche_lungo') * r,
                _get_field(ref_bs, 'sp17b_debiti_altri_finanz_lungo') * r,
                _get_field(ref_bs, 'sp17c_debiti_obbligazioni_lungo') * r,
                _get_field(ref_bs, 'sp17d_debiti_fornitori_lungo') * r,
                _get_field(ref_bs, 'sp17e_debiti_tributari_lungo') * r,
                _get_field(ref_bs, 'sp17f_debiti_previdenza_lungo') * r,
                _get_field(ref_bs, 'sp17g_altri_debiti_lungo') * r,
            )
        return (Decimal('0'),) * 7

    def _save_forecast(self, scenario_id: int, year: int, bs_data: Dict, inc_data: Dict):
        """Save projected data as ForecastYear + ForecastBalanceSheet + ForecastIncomeStatement."""
        fy = self.db.query(ForecastYear).filter(
            ForecastYear.scenario_id == scenario_id,
            ForecastYear.year == year
        ).first()

        if not fy:
            fy = ForecastYear(scenario_id=scenario_id, year=year)
            self.db.add(fy)
            self.db.flush()

        # Save/update balance sheet
        existing_bs = self.db.query(ForecastBalanceSheet).filter(
            ForecastBalanceSheet.forecast_year_id == fy.id
        ).first()

        if existing_bs:
            for field, value in bs_data.items():
                setattr(existing_bs, field, value)
        else:
            new_bs = ForecastBalanceSheet(forecast_year_id=fy.id, **bs_data)
            self.db.add(new_bs)

        # Save/update income statement
        existing_inc = self.db.query(ForecastIncomeStatement).filter(
            ForecastIncomeStatement.forecast_year_id == fy.id
        ).first()

        if existing_inc:
            for field, value in inc_data.items():
                setattr(existing_inc, field, value)
        else:
            new_inc = ForecastIncomeStatement(forecast_year_id=fy.id, **inc_data)
            self.db.add(new_inc)
