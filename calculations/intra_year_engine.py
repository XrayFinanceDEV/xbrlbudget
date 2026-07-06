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
from calculations.projection_common import (
    financial_repayment_instalment, altri_finanz_repayment_instalment,
    tfr_accrual_quota,
)


# P&L line item codes for comparison
CE_FIELDS = [
    ('ce01_ricavi_vendite', 'Ricavi delle vendite'),
    ('ce02_variazioni_rimanenze', 'Variazioni rimanenze prodotti'),
    ('ce03_lavori_interni', 'Lavori interni capitalizzati'),
    ('ce03a_incrementi_immobilizzazioni', 'Incrementi di immobilizzazioni per lavori interni'),
    ('ce04_altri_ricavi', 'Altri ricavi e proventi'),
    ('ce05_materie_prime', 'Materie prime e consumo'),
    ('ce06_servizi', 'Costi per servizi'),
    ('ce07_godimento_beni', 'Godimento beni di terzi'),
    ('ce08_costi_personale', 'Costi del personale'),
    ('ce08b_salari_stipendi', 'Salari e stipendi'),
    ('ce08c_oneri_sociali', 'Oneri sociali'),
    ('ce08a_tfr_accrual', 'TFR accantonamento'),
    ('ce08d_altri_costi_personale', 'Altri costi del personale'),
    ('ce09_ammortamenti', 'Ammortamenti e svalutazioni'),
    ('ce09a_ammort_immateriali', 'Ammortamento immobilizzazioni immateriali'),
    ('ce09b_ammort_materiali', 'Ammortamento immobilizzazioni materiali'),
    ('ce09c_svalutazioni', 'Svalutazioni immobilizzazioni'),
    ('ce09d_svalutazione_crediti', 'Svalutazione crediti'),
    ('ce10_var_rimanenze_mat_prime', 'Variazioni rimanenze materie prime'),
    ('ce11_accantonamenti', 'Accantonamenti per rischi'),
    ('ce11b_altri_accantonamenti', 'Altri accantonamenti'),
    ('ce12_oneri_diversi', 'Oneri diversi di gestione'),
    ('ce13_proventi_partecipazioni', 'Proventi da partecipazioni'),
    ('ce14_altri_proventi_finanziari', 'Altri proventi finanziari'),
    ('ce15_oneri_finanziari', 'Oneri finanziari'),
    ('ce16_utili_perdite_cambi', 'Utili/perdite su cambi'),
    ('ce17_rettifiche_attivita_fin', 'Rettifiche attivita finanziarie'),
    ('ce17a_rivalutazioni', 'Rivalutazioni'),
    ('ce17b_svalutazioni', 'Svalutazioni'),
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
    ('sp06a_crediti_clienti_breve', 'Verso clienti'),
    ('sp06b_crediti_controllate_breve', 'Verso imprese controllate'),
    ('sp06c_crediti_collegate_breve', 'Verso imprese collegate'),
    ('sp06d_crediti_controllanti_breve', 'Verso controllanti'),
    ('sp06e_crediti_tributari_breve', 'Crediti tributari'),
    ('sp06f_imposte_anticipate_breve', 'Imposte anticipate'),
    ('sp06g_crediti_altri_breve', 'Verso altri'),
    ('sp07_crediti_lungo', 'Crediti esigibili oltre 12 mesi'),
    ('sp07a_crediti_clienti_lungo', 'Verso clienti'),
    ('sp07b_crediti_controllate_lungo', 'Verso imprese controllate'),
    ('sp07c_crediti_collegate_lungo', 'Verso imprese collegate'),
    ('sp07d_crediti_controllanti_lungo', 'Verso controllanti'),
    ('sp07e_crediti_tributari_lungo', 'Crediti tributari'),
    ('sp07f_imposte_anticipate_lungo', 'Imposte anticipate'),
    ('sp07g_crediti_altri_lungo', 'Verso altri'),
    ('sp08_attivita_finanziarie', 'Attivita finanziarie'),
    ('sp09_disponibilita_liquide', 'Disponibilita liquide'),
    ('sp10_ratei_risconti_attivi', 'Ratei e risconti attivi'),
    ('sp11_capitale', 'Capitale sociale'),
    ('sp12_riserve', 'Riserve'),
    ('sp13_utile_perdita', 'Utile/Perdita di esercizio'),
    ('sp14_fondi_rischi', 'Fondi per rischi e oneri'),
    ('sp15_tfr', 'TFR'),
    ('sp16_debiti_breve', 'Debiti esigibili entro 12 mesi'),
    ('sp16a_debiti_banche_breve', 'Debiti verso banche'),
    ('sp16b_debiti_altri_finanz_breve', 'Debiti verso altri finanziatori'),
    ('sp16c_debiti_obbligazioni_breve', 'Debiti obbligazionari'),
    ('sp16d_debiti_fornitori_breve', 'Debiti verso fornitori'),
    ('sp16e_debiti_tributari_breve', 'Debiti tributari'),
    ('sp16f_debiti_previdenza_breve', 'Debiti previdenziali'),
    ('sp16g_altri_debiti_breve', 'Altri debiti'),
    ('sp17_debiti_lungo', 'Debiti esigibili oltre 12 mesi'),
    ('sp17a_debiti_banche_lungo', 'Debiti verso banche'),
    ('sp17b_debiti_altri_finanz_lungo', 'Debiti verso altri finanziatori'),
    ('sp17c_debiti_obbligazioni_lungo', 'Debiti obbligazionari'),
    ('sp17d_debiti_fornitori_lungo', 'Debiti verso fornitori'),
    ('sp17e_debiti_tributari_lungo', 'Debiti tributari'),
    ('sp17f_debiti_previdenza_lungo', 'Debiti previdenziali'),
    ('sp17g_altri_debiti_lungo', 'Altri debiti'),
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


def _get_total_investments(assumption) -> Decimal:
    """Get total investments from split fields or legacy field."""
    intangible = getattr(assumption, 'intangible_investments', None) or Decimal('0')
    tangible = getattr(assumption, 'tangible_investments', None) or Decimal('0')
    if intangible > 0 or tangible > 0:
        return Decimal(str(intangible)) + Decimal(str(tangible))
    inv = assumption.investments if assumption.investments else Decimal('0')
    return Decimal(str(inv))


def _get_split_investments(assumption):
    """Return (intangible, tangible) investment amounts."""
    intangible = getattr(assumption, 'intangible_investments', None) or Decimal('0')
    tangible = getattr(assumption, 'tangible_investments', None) or Decimal('0')
    intangible = Decimal(str(intangible))
    tangible = Decimal(str(tangible))
    if intangible > 0 or tangible > 0:
        return intangible, tangible
    # Legacy fallback
    total = Decimal(str(assumption.investments)) if assumption.investments else Decimal('0')
    return total / 2, total / 2


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
        prior year value (year before reference), percentage of reference,
        and annualized value.
        """
        scenario = self._load_scenario(scenario_id)
        partial_fy, ref_fy = self._load_financial_years(scenario)

        # Try to load prior year (year before reference) for additional context
        from database.queries import get_fy_prefer_full
        prior_year_num = scenario.base_year - 1  # e.g., 2023
        prior_fy = get_fy_prefer_full(self.db, scenario.company_id, prior_year_num)

        period_months = scenario.period_months
        factor = Decimal('12') / Decimal(str(period_months))

        has_reference = ref_fy is not None
        ref_inc = ref_fy.income_statement if ref_fy else None
        ref_bs = ref_fy.balance_sheet if ref_fy else None

        income_items = []
        for field_name, label in CE_FIELDS:
            partial_val = _get_field(partial_fy.income_statement, field_name)
            ref_val = _get_field(ref_inc, field_name) if ref_inc else Decimal('0')
            prior_val = _get_field(prior_fy.income_statement, field_name) if prior_fy and prior_fy.income_statement else Decimal('0')
            annualized = partial_val * factor
            pct = float(_safe_divide(partial_val * Decimal('100'), ref_val)) if ref_val != 0 else 0.0

            income_items.append({
                'code': field_name,
                'label': label,
                'partial_value': float(partial_val),
                'reference_value': float(ref_val),
                'prior_value': float(prior_val),
                'pct_of_reference': round(pct, 2),
                'annualized_value': float(annualized.quantize(Decimal('0.01'))),
            })

        balance_items = []
        for field_name, label in SP_FIELDS:
            partial_val = _get_field(partial_fy.balance_sheet, field_name)
            ref_val = _get_field(ref_bs, field_name) if ref_bs else Decimal('0')
            prior_val = _get_field(prior_fy.balance_sheet, field_name) if prior_fy and prior_fy.balance_sheet else Decimal('0')
            # BS items are stock (point-in-time), annualization doesn't apply
            # Show partial value as "annualized" for consistency
            pct = float(_safe_divide(partial_val * Decimal('100'), ref_val)) if ref_val != 0 else 0.0

            balance_items.append({
                'code': field_name,
                'label': label,
                'partial_value': float(partial_val),
                'reference_value': float(ref_val),
                'prior_value': float(prior_val),
                'pct_of_reference': round(pct, 2),
                'annualized_value': float(partial_val),  # BS = point-in-time, no annualization
            })

        return {
            'partial_year': scenario.base_year + 1,  # e.g., 2025
            'reference_year': scenario.base_year,     # e.g., 2024
            'prior_year': prior_year_num if prior_fy else None,  # e.g., 2023 or None
            'has_reference': has_reference,           # False = pure-annualization mode
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

        # Reference year may be absent (user chose to proceed without it).
        ref_inc = ref_fy.income_statement if ref_fy else None
        ref_bs = ref_fy.balance_sheet if ref_fy else None

        # Project income statement
        projected_inc = self._project_income_statement(
            partial_inc=partial_fy.income_statement,
            ref_inc=ref_inc,
            assumption=assumption,
            period_months=period_months
        )

        # Project balance sheet
        projected_bs = self._project_balance_sheet(
            partial_bs=partial_fy.balance_sheet,
            ref_bs=ref_bs,
            projected_inc=projected_inc,
            ref_inc=ref_inc,
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

        from database.queries import get_fy_partial, get_fy_prefer_full

        # Load partial year: prefer partial-year record, fall back to full-year
        # (full-year record may exist if the same year was also imported for budget)
        partial_fy = get_fy_partial(self.db, company_id, partial_year_num)
        if not partial_fy:
            partial_fy = get_fy_prefer_full(self.db, company_id, partial_year_num)

        if not partial_fy or not partial_fy.balance_sheet or not partial_fy.income_statement:
            raise ValueError(
                f"Dati anno {partial_year_num} non trovati o incompleti per l'azienda {company_id}. "
                f"Importare il bilancio {partial_year_num} prima di procedere."
            )

        # Load reference full year. This is OPTIONAL: when the prior-year balance
        # sheet was never imported (e.g. single-column PDF, first year of activity),
        # the user can choose to proceed anyway. In that case ref_fy is None and the
        # engine falls back to pure annualization (partial * 12 / period_months).
        ref_fy = get_fy_prefer_full(self.db, company_id, ref_year_num)
        if ref_fy and (not ref_fy.balance_sheet or not ref_fy.income_statement):
            ref_fy = None

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

        When the reference year is absent (ref_inc is None) the growth-based
        formulas have no base, so we fall back to pure annualization.
        """
        if ref_inc is None:
            return self._project_income_statement_annualized(
                partial_inc, assumption, period_months
            )

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

        # Personnel sub-items - salari/oneri scale with the personnel total; TFR (ce08a)
        # is the statutory accrual salari/13,5 so the sp15 fund grows even when only the
        # aggregate personnel cost is available; ce08d absorbs the remainder so the four
        # sub-items still sum to the personnel total.
        if ref_ce08 > 0:
            growth_factor = ce08 / ref_ce08
            ce08b = _get_field(ref_inc, 'ce08b_salari_stipendi') * growth_factor
            ce08c = _get_field(ref_inc, 'ce08c_oneri_sociali') * growth_factor
        else:
            ce08b = Decimal('0')
            ce08c = Decimal('0')
        # Cap the derived TFR quota at the remainder left by salari+oneri so the four
        # sub-items never sum to more than the personnel total.
        ce08a = min(tfr_accrual_quota(ce08b, ce08), max(Decimal('0'), ce08 - ce08b - ce08c))
        ce08d = max(Decimal('0'), ce08 - ce08a - ce08b - ce08c)

        # Depreciation - annualize (linear accrual) + new investments
        partial_ce09 = _get_field(partial_inc, 'ce09_ammortamenti')
        ce09 = partial_ce09 * factor
        # Sub-items: annualize partial year values
        partial_ce09a = _get_field(partial_inc, 'ce09a_ammort_immateriali')
        partial_ce09b = _get_field(partial_inc, 'ce09b_ammort_materiali')
        ce09a = partial_ce09a * factor
        ce09b = partial_ce09b * factor
        ce09c = _get_field(partial_inc, 'ce09c_svalutazioni') * factor
        ce09d = _get_field(partial_inc, 'ce09d_svalutazione_crediti') * factor
        # Add depreciation on new investments if any
        intangible_inv, tangible_inv = _get_split_investments(assumption)
        total_investments = intangible_inv + tangible_inv
        if total_investments > 0:
            depreciation_rate_tangible = assumption.depreciation_rate / Decimal('100')
            depreciation_rate_intangible = (getattr(assumption, 'depreciation_rate_intangible', None) or assumption.depreciation_rate) / Decimal('100')
            remaining_months = Decimal('12') - Decimal(str(period_months))
            new_dep_intangible = intangible_inv * depreciation_rate_intangible * remaining_months / Decimal('12')
            new_dep_tangible = tangible_inv * depreciation_rate_tangible * remaining_months / Decimal('12')
            ce09a = ce09a + new_dep_intangible
            ce09b = ce09b + new_dep_tangible
            ce09 = ce09 + new_dep_intangible + new_dep_tangible

        # Other costs
        ref_ce12 = _get_field(ref_inc, 'ce12_oneri_diversi')
        ce12 = ref_ce12 * (Decimal('1') + assumption.other_costs_growth_pct / Decimal('100'))

        # Items kept from annualization of partial year (less subject to user control)
        ce02 = _get_field(partial_inc, 'ce02_variazioni_rimanenze') * factor
        ce03 = _get_field(partial_inc, 'ce03_lavori_interni') * factor
        # Incrementi di immobilizzazioni per lavori interni (A.4) — part of the value of
        # production; must be included so the projected CE utile reconciles with the SP
        # (which carries the booked profit including this item), avoiding a false sbilancio.
        ce03a = _get_field(partial_inc, 'ce03a_incrementi_immobilizzazioni') * factor
        ce10 = _get_field(partial_inc, 'ce10_var_rimanenze_mat_prime') * factor
        ce11 = _get_field(partial_inc, 'ce11_accantonamenti') * factor
        ce11b = _get_field(partial_inc, 'ce11b_altri_accantonamenti') * factor
        ce13 = _get_field(partial_inc, 'ce13_proventi_partecipazioni') * factor
        ce14 = assumption.ce14_override if assumption.ce14_override is not None else _get_field(partial_inc, 'ce14_altri_proventi_finanziari') * factor
        ce15 = assumption.ce15_override if assumption.ce15_override is not None else _get_field(partial_inc, 'ce15_oneri_finanziari') * factor
        ce16 = _get_field(partial_inc, 'ce16_utili_perdite_cambi') * factor
        ce17 = _get_field(partial_inc, 'ce17_rettifiche_attivita_fin') * factor
        ce18 = _get_field(partial_inc, 'ce18_proventi_straordinari') * factor
        ce19 = _get_field(partial_inc, 'ce19_oneri_straordinari') * factor

        # Taxes - recalculate on projected pre-tax profit
        production_value = ce01 + ce02 + ce03 + ce03a + ce04
        production_cost = ce05 + ce06 + ce07 + ce08 + ce09 + ce10 + ce11 + ce11b + ce12
        ebit = production_value - production_cost
        financial_result = ce13 + ce14 - ce15 + ce16
        profit_before_tax = ebit + financial_result + ce17 + (ce18 - ce19)
        tax_rate = assumption.tax_rate / Decimal('100')
        ce20 = max(Decimal('0'), profit_before_tax * tax_rate)

        return {
            'ce01_ricavi_vendite': ce01,
            'ce02_variazioni_rimanenze': ce02,
            'ce03_lavori_interni': ce03,
            'ce03a_incrementi_immobilizzazioni': ce03a,
            'ce04_altri_ricavi': ce04,
            'ce05_materie_prime': ce05,
            'ce06_servizi': ce06,
            'ce07_godimento_beni': ce07,
            'ce08_costi_personale': ce08,
            'ce08a_tfr_accrual': ce08a,
            'ce08b_salari_stipendi': ce08b,
            'ce08c_oneri_sociali': ce08c,
            'ce08d_altri_costi_personale': ce08d,
            'ce09_ammortamenti': ce09,
            'ce09a_ammort_immateriali': ce09a,
            'ce09b_ammort_materiali': ce09b,
            'ce09c_svalutazioni': ce09c,
            'ce09d_svalutazione_crediti': ce09d,
            'ce10_var_rimanenze_mat_prime': ce10,
            'ce11_accantonamenti': ce11,
            'ce11b_altri_accantonamenti': ce11b,
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

    def _project_income_statement_annualized(
        self,
        partial_inc: IncomeStatement,
        assumption: BudgetAssumptions,
        period_months: int
    ) -> Dict:
        """
        Project P&L to 12 months by pure annualization (partial * 12 / period).

        Used when there is no reference year. Growth assumptions cannot apply
        (they are relative to the reference), but explicit financial overrides
        (ce14/ce15), new-investment depreciation and financing still take effect,
        and taxes are recomputed on the projected pre-tax profit.
        """
        factor = Decimal('12') / Decimal(str(period_months))

        def ann(code):
            return _get_field(partial_inc, code) * factor

        ce01 = ann('ce01_ricavi_vendite')
        ce02 = ann('ce02_variazioni_rimanenze')
        ce03 = ann('ce03_lavori_interni')
        ce03a = ann('ce03a_incrementi_immobilizzazioni')
        ce04 = ann('ce04_altri_ricavi')
        ce05 = ann('ce05_materie_prime')
        ce06 = ann('ce06_servizi')
        ce07 = ann('ce07_godimento_beni')
        ce08 = ann('ce08_costi_personale')
        # TFR (ce08a) is the statutory accrual salari/13,5 so the sp15 fund grows even when
        # only the aggregate personnel cost is available; ce08d absorbs the remainder so the
        # four sub-items still sum to the personnel total.
        ce08b = ann('ce08b_salari_stipendi')
        ce08c = ann('ce08c_oneri_sociali')
        # Cap the derived TFR quota at the remainder left by salari+oneri so the four
        # sub-items never sum to more than the personnel total.
        ce08a = min(tfr_accrual_quota(ce08b, ce08), max(Decimal('0'), ce08 - ce08b - ce08c))
        ce08d = max(Decimal('0'), ce08 - ce08a - ce08b - ce08c)

        # Depreciation: annualize partial year + depreciation on new investments
        ce09 = ann('ce09_ammortamenti')
        ce09a = ann('ce09a_ammort_immateriali')
        ce09b = ann('ce09b_ammort_materiali')
        ce09c = ann('ce09c_svalutazioni')
        ce09d = ann('ce09d_svalutazione_crediti')
        intangible_inv, tangible_inv = _get_split_investments(assumption)
        total_investments = intangible_inv + tangible_inv
        if total_investments > 0:
            depreciation_rate_tangible = assumption.depreciation_rate / Decimal('100')
            depreciation_rate_intangible = (getattr(assumption, 'depreciation_rate_intangible', None) or assumption.depreciation_rate) / Decimal('100')
            remaining_months = Decimal('12') - Decimal(str(period_months))
            new_dep_intangible = intangible_inv * depreciation_rate_intangible * remaining_months / Decimal('12')
            new_dep_tangible = tangible_inv * depreciation_rate_tangible * remaining_months / Decimal('12')
            ce09a = ce09a + new_dep_intangible
            ce09b = ce09b + new_dep_tangible
            ce09 = ce09 + new_dep_intangible + new_dep_tangible

        ce10 = ann('ce10_var_rimanenze_mat_prime')
        ce11 = ann('ce11_accantonamenti')
        ce11b = ann('ce11b_altri_accantonamenti')
        ce12 = ann('ce12_oneri_diversi')
        ce13 = ann('ce13_proventi_partecipazioni')
        ce14 = assumption.ce14_override if assumption.ce14_override is not None else ann('ce14_altri_proventi_finanziari')
        ce15 = assumption.ce15_override if assumption.ce15_override is not None else ann('ce15_oneri_finanziari')
        ce16 = ann('ce16_utili_perdite_cambi')
        ce17 = ann('ce17_rettifiche_attivita_fin')
        ce18 = ann('ce18_proventi_straordinari')
        ce19 = ann('ce19_oneri_straordinari')

        # Taxes - recalculate on projected pre-tax profit
        production_value = ce01 + ce02 + ce03 + ce03a + ce04
        production_cost = ce05 + ce06 + ce07 + ce08 + ce09 + ce10 + ce11 + ce11b + ce12
        ebit = production_value - production_cost
        financial_result = ce13 + ce14 - ce15 + ce16
        profit_before_tax = ebit + financial_result + ce17 + (ce18 - ce19)
        tax_rate = assumption.tax_rate / Decimal('100')
        ce20 = max(Decimal('0'), profit_before_tax * tax_rate)

        return {
            'ce01_ricavi_vendite': ce01,
            'ce02_variazioni_rimanenze': ce02,
            'ce03_lavori_interni': ce03,
            'ce03a_incrementi_immobilizzazioni': ce03a,
            'ce04_altri_ricavi': ce04,
            'ce05_materie_prime': ce05,
            'ce06_servizi': ce06,
            'ce07_godimento_beni': ce07,
            'ce08_costi_personale': ce08,
            'ce08a_tfr_accrual': ce08a,
            'ce08b_salari_stipendi': ce08b,
            'ce08c_oneri_sociali': ce08c,
            'ce08d_altri_costi_personale': ce08d,
            'ce09_ammortamenti': ce09,
            'ce09a_ammort_immateriali': ce09a,
            'ce09b_ammort_materiali': ce09b,
            'ce09c_svalutazioni': ce09c,
            'ce09d_svalutazione_crediti': ce09d,
            'ce10_var_rimanenze_mat_prime': ce10,
            'ce11_accantonamenti': ce11,
            'ce11b_altri_accantonamenti': ce11b,
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

        When the reference year is absent (ref_bs is None) we cannot derive
        turnover ratios, so we fall back to using the partial-year stocks as the
        year-end basis (see _project_balance_sheet_annualized).
        """
        if ref_bs is None:
            return self._project_balance_sheet_annualized(
                partial_bs, projected_inc, assumption, period_months
            )

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
        intangible_inv, tangible_inv = _get_split_investments(assumption)
        if intangible_inv > 0 or tangible_inv > 0:
            sp02 = sp02 + intangible_inv
            sp03 = sp03 + tangible_inv

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
        sp13 = self._net_profit_from_projection(projected_inc)

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

        # Long-term debt: keep from reference, then amortise per repayment plan (P2)
        sp17 = _get_field(ref_bs, 'sp17_debiti_lungo')
        sp17 = self._apply_debt_repayment(ref_bs, sp17, assumption)

        # Add new financing if any
        if (assumption.financing_amount or Decimal('0')) > 0:
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
        sp06a, sp06b, sp06c, sp06d, sp06e, sp06f, sp06g = self._distribute_sp06(ref_bs, sp06)
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
            'sp06a_crediti_clienti_breve': sp06a,
            'sp06b_crediti_controllate_breve': sp06b,
            'sp06c_crediti_collegate_breve': sp06c,
            'sp06d_crediti_controllanti_breve': sp06d,
            'sp06e_crediti_tributari_breve': sp06e,
            'sp06f_imposte_anticipate_breve': sp06f,
            'sp06g_crediti_altri_breve': sp06g,
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

    def _net_profit_from_projection(self, projected_inc: Dict) -> Decimal:
        """Net profit = value of production - costs +/- financial/extraordinary - taxes."""
        return (
            projected_inc['ce01_ricavi_vendite'] +
            projected_inc['ce02_variazioni_rimanenze'] +
            projected_inc['ce03_lavori_interni'] +
            projected_inc.get('ce03a_incrementi_immobilizzazioni', Decimal('0')) +
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

    def _project_balance_sheet_annualized(
        self,
        partial_bs: BalanceSheet,
        projected_inc: Dict,
        assumption: BudgetAssumptions,
        period_months: int
    ) -> Dict:
        """
        Project BS to year-end when there is no reference year.

        Without a reference year we cannot apply turnover ratios, so the
        partial-year stocks are carried to year-end as-is, except:
        - fixed assets are reduced by the remaining-months depreciation,
        - new investments / financing are added,
        - current-year profit is the projected (annualized) net profit,
        - TFR adds the remaining-months accrual,
        - cash is the balancing plug.
        Sub-item breakdowns are distributed proportionally from the partial year.
        """
        remaining_months = Decimal('12') - Decimal(str(period_months))

        # FIXED ASSETS - partial values reduced by remaining depreciation
        partial_sp02 = _get_field(partial_bs, 'sp02_immob_immateriali')
        partial_sp03 = _get_field(partial_bs, 'sp03_immob_materiali')
        partial_sp04 = _get_field(partial_bs, 'sp04_immob_finanziarie')

        total_dep = projected_inc['ce09_ammortamenti']
        remaining_dep = total_dep * remaining_months / Decimal('12')
        total_fixed = partial_sp02 + partial_sp03 + partial_sp04
        if total_fixed > 0:
            sp02 = max(Decimal('0'), partial_sp02 - remaining_dep * partial_sp02 / total_fixed)
            sp03 = max(Decimal('0'), partial_sp03 - remaining_dep * partial_sp03 / total_fixed)
            sp04 = max(Decimal('0'), partial_sp04 - remaining_dep * partial_sp04 / total_fixed)
        else:
            sp02, sp03, sp04 = partial_sp02, partial_sp03, partial_sp04

        intangible_inv, tangible_inv = _get_split_investments(assumption)
        if intangible_inv > 0 or tangible_inv > 0:
            sp02 = sp02 + intangible_inv
            sp03 = sp03 + tangible_inv

        # WORKING CAPITAL and other current assets - carry partial year stocks
        sp01 = _get_field(partial_bs, 'sp01_crediti_soci')
        sp05 = _get_field(partial_bs, 'sp05_rimanenze')
        sp06 = _get_field(partial_bs, 'sp06_crediti_breve')
        sp07 = _get_field(partial_bs, 'sp07_crediti_lungo')
        sp08 = _get_field(partial_bs, 'sp08_attivita_finanziarie')
        sp10 = _get_field(partial_bs, 'sp10_ratei_risconti_attivi')

        # EQUITY - capital and reserves from partial year, profit from projection
        sp11 = _get_field(partial_bs, 'sp11_capitale')
        sp12 = _get_field(partial_bs, 'sp12_riserve')
        sp13 = self._net_profit_from_projection(projected_inc)
        sp12a = _get_field(partial_bs, 'sp12a_riserva_sovrapprezzo')
        sp12b = _get_field(partial_bs, 'sp12b_riserve_rivalutazione')
        sp12c = _get_field(partial_bs, 'sp12c_riserva_legale')
        sp12d = _get_field(partial_bs, 'sp12d_riserve_statutarie')
        sp12e = _get_field(partial_bs, 'sp12e_altre_riserve')
        sp12f = _get_field(partial_bs, 'sp12f_riserva_copertura_flussi')
        sp12g = _get_field(partial_bs, 'sp12g_utili_perdite_portati')
        sp12h = _get_field(partial_bs, 'sp12h_riserva_neg_azioni_proprie')

        # LIABILITIES - carry partial year, add remaining TFR accrual / financing
        sp14 = _get_field(partial_bs, 'sp14_fondi_rischi')
        sp15 = _get_field(partial_bs, 'sp15_tfr') + projected_inc.get('ce08a_tfr_accrual', Decimal('0')) * remaining_months / Decimal('12')
        sp16 = _get_field(partial_bs, 'sp16_debiti_breve')
        sp17 = _get_field(partial_bs, 'sp17_debiti_lungo')
        sp17 = self._apply_debt_repayment(partial_bs, sp17, assumption)
        if (assumption.financing_amount or Decimal('0')) > 0:
            sp17 = sp17 + assumption.financing_amount
        sp18 = _get_field(partial_bs, 'sp18_ratei_risconti_passivi')

        # CASH PLUG - balance the sheet
        total_assets_no_cash = sp01 + sp02 + sp03 + sp04 + sp05 + sp06 + sp07 + sp08 + sp10
        total_liabilities = sp11 + sp12 + sp13 + sp14 + sp15 + sp16 + sp17 + sp18
        sp09 = total_liabilities - total_assets_no_cash
        if sp09 < 0:
            sp16 = sp16 + abs(sp09)
            sp09 = Decimal('0')

        # Sub-item breakdowns proportional to the partial year
        sp04a, sp04b, sp04c, sp04d, sp04e = self._distribute_sp04(partial_bs, sp04)
        sp06a, sp06b, sp06c, sp06d, sp06e, sp06f, sp06g = self._distribute_sp06(partial_bs, sp06)
        sp16a, sp16b, sp16c, sp16d, sp16e, sp16f, sp16g = self._distribute_sp16(partial_bs, sp16)
        sp17a, sp17b, sp17c, sp17d, sp17e, sp17f, sp17g = self._distribute_sp17(partial_bs, sp17)

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
            'sp06a_crediti_clienti_breve': sp06a,
            'sp06b_crediti_controllate_breve': sp06b,
            'sp06c_crediti_collegate_breve': sp06c,
            'sp06d_crediti_controllanti_breve': sp06d,
            'sp06e_crediti_tributari_breve': sp06e,
            'sp06f_imposte_anticipate_breve': sp06f,
            'sp06g_crediti_altri_breve': sp06g,
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

    def _apply_debt_repayment(self, base_bs, sp17_long: Decimal, assumption) -> Decimal:
        """Reduce projected long-term debt by one annual repayment instalment (P2).

        Mirrors the budget engine: a FIXED instalment computed on the base-year
        financial long-term debt (banks + bonds), so e.g. a 100k loan on a 5-year
        plan drops to 80k in the projected year (the repayment then surfaces as a
        financing outflow in the rendiconto finanziario) instead of staying flat.
        'Altri finanziatori' (sp17b) amortise on their own plan. No-op when the
        repayment-years assumptions are not set (zero regression on existing files).
        """
        # The repayment RULE (fixed instalment on the base-year financial long-term
        # debt, excluding 'altri finanziatori' and non-financial debts) lives in the
        # shared kernel so it is identical to the budget engine by construction (P2).
        # This engine APPLIES it to the aggregate sp17_long; the budget engine
        # apportions the same instalment across the sp17a/sp17c sub-fields — that
        # difference is orchestration, the instalment formula is the same.
        getter = lambda f: _get_field(base_bs, f)

        instalment = financial_repayment_instalment(
            getter, getattr(assumption, 'existing_debt_repayment_years', None))
        if instalment > 0:
            sp17_long = max(Decimal('0'), sp17_long - instalment)

        altri_years = getattr(assumption, 'altri_finanz_repayment_years', None)
        if altri_years is not None and Decimal(str(altri_years)) > 0:
            altri_instalment = altri_finanz_repayment_instalment(getter, altri_years)
            sp17_long = max(Decimal('0'), sp17_long - altri_instalment)

        return sp17_long

    def _distribute_sp06(self, ref_bs, sp06_total):
        """Distribute sp06 (current receivables) into sub-categories proportionally
        from the base year, so detail lines — notably 'crediti tributari' (sp06e) —
        move WITH the projected aggregate instead of staying frozen (P3). Mirrors
        _distribute_sp16. When the base year has no sub-detail (abbreviato: only the
        aggregate populated) it returns zeros and the frontend reconciler plugs the
        gap into 'altri', same as the debiti side."""
        fields = (
            'sp06a_crediti_clienti_breve', 'sp06b_crediti_controllate_breve',
            'sp06c_crediti_collegate_breve', 'sp06d_crediti_controllanti_breve',
            'sp06e_crediti_tributari_breve', 'sp06f_imposte_anticipate_breve',
            'sp06g_crediti_altri_breve',
        )
        total = sum((_get_field(ref_bs, f) for f in fields), Decimal('0'))
        if total > 0:
            r = sp06_total / total
            return tuple(_get_field(ref_bs, f) * r for f in fields)
        return (Decimal('0'),) * 7

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
