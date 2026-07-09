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
from calculations.projection_common import (
    financial_repayment_instalment, altri_finanz_repayment_instalment,
    tfr_accrual_quota, new_financing_schedule,
)


class ForecastEngine:
    """
    Calculates forecasted financial statements based on budget assumptions
    """

    def __init__(self, db_session: Session):
        self.db = db_session

    @staticmethod
    def _get_total_investments(assumption) -> Decimal:
        """Get total investments from split fields or legacy field."""
        intangible = getattr(assumption, 'intangible_investments', None) or Decimal('0')
        tangible = getattr(assumption, 'tangible_investments', None) or Decimal('0')
        if intangible > 0 or tangible > 0:
            return intangible + tangible
        return assumption.investments if assumption.investments else Decimal('0')

    @staticmethod
    def _get_split_investments(assumption):
        """Return (intangible, tangible) investment amounts."""
        intangible = getattr(assumption, 'intangible_investments', None) or Decimal('0')
        tangible = getattr(assumption, 'tangible_investments', None) or Decimal('0')
        if intangible > 0 or tangible > 0:
            return intangible, tangible
        # Legacy fallback: distribute proportionally (50/50)
        total = assumption.investments if assumption.investments else Decimal('0')
        return total / 2, total / 2

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

        # Get base year data (prefer full-year record)
        from database.queries import get_fy_prefer_full
        base_fy = get_fy_prefer_full(self.db, scenario.company_id, scenario.base_year)

        if not base_fy or not base_fy.balance_sheet or not base_fy.income_statement:
            raise ValueError(f"Base year {scenario.base_year} data not found or incomplete")

        base_bs = base_fy.balance_sheet
        base_inc = base_fy.income_statement

        # Guard: a base year with NEGATIVE sales revenue is a broken extraction
        # (ricavi delle vendite, OIC A.1, can never be < 0). Projecting it produces
        # garbage — applying a growth % to a negative base inverts the direction
        # (e.g. +15% makes it MORE negative). Refuse with an honest error pointing to
        # Rettifiche instead of generating a misleading forecast.
        if (base_inc.ce01_ricavi_vendite or Decimal('0')) < 0:
            raise ValueError(
                f"Anno base {scenario.base_year}: ricavi delle vendite negativi "
                f"({base_inc.ce01_ricavi_vendite:.0f} €) — estrazione del bilancio non valida. "
                f"Correggi i ricavi in Rettifiche (o re-importa il bilancio) prima di generare il previsionale."
            )

        # Get all assumptions for this scenario
        assumptions = self.db.query(BudgetAssumptions).filter(
            BudgetAssumptions.scenario_id == scenario_id
        ).order_by(BudgetAssumptions.forecast_year).all()

        if not assumptions:
            raise ValueError(f"No assumptions found for scenario {scenario_id}")

        forecast_years = []

        # NEW financing raised during the plan: each assumption's financing_amount
        # is a loan taken THAT year, amortised over its durata with interest on the
        # residual (shared kernel `new_financing_schedule`). Assembled ONCE from all
        # years because a single per-year assumption can't see a loan raised earlier
        # that is still being repaid. Keeps the SP debt (sp17a) and the P&L oneri
        # finanziari (ce15) in sync — the previous code added the debt but only
        # charged interest in the year of erogazione.
        financing_loans = []
        for a in assumptions:
            amt = a.financing_amount or Decimal('0')
            dur = a.financing_duration_years or Decimal('0')
            rate = (a.financing_interest_rate or Decimal('0')) / Decimal('100')
            if amt > 0 and dur > 0:
                financing_loans.append({
                    'year': a.forecast_year, 'amount': amt, 'duration': dur, 'rate': rate,
                })

        # Generate forecast for each year
        for idx, assumption in enumerate(assumptions):
            year_offset = assumption.forecast_year - scenario.base_year

            # Calculate forecasted income statement
            forecast_inc = self._calculate_income_statement(
                base_inc=base_inc,
                assumption=assumption,
                previous_inc=forecast_years[-1]['income_statement'] if forecast_years else base_inc,
                previous_bs=forecast_years[-1]['balance_sheet'] if forecast_years else base_bs,
                financing_loans=financing_loans
            )

            # Calculate forecasted balance sheet
            forecast_bs = self._calculate_balance_sheet(
                base_bs=base_bs,
                base_inc=base_inc,
                forecast_inc=forecast_inc,
                assumption=assumption,
                previous_bs=forecast_years[-1]['balance_sheet'] if forecast_years else base_bs,
                year_offset=year_offset,
                financing_loans=financing_loans
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

    @staticmethod
    def _pbt_from_income(inc) -> Decimal:
        """Pre-tax profit from an IncomeStatement-like object (same formula as the forecast)."""
        g = lambda k: getattr(inc, k, None) or Decimal('0')
        vp = (g('ce01_ricavi_vendite') + g('ce02_variazioni_rimanenze') + g('ce03_lavori_interni')
              + g('ce03a_incrementi_immobilizzazioni') + g('ce04_altri_ricavi'))
        co = (g('ce05_materie_prime') + g('ce06_servizi') + g('ce07_godimento_beni') + g('ce08_costi_personale')
              + g('ce09_ammortamenti') + g('ce10_var_rimanenze_mat_prime') + g('ce11_accantonamenti')
              + g('ce11b_altri_accantonamenti') + g('ce12_oneri_diversi'))
        fin = (g('ce13_proventi_partecipazioni') + g('ce14_altri_proventi_finanziari') - g('ce15_oneri_finanziari')
               + g('ce16_utili_perdite_cambi') + g('ce17_rettifiche_attivita_fin')
               + g('ce18_proventi_straordinari') - g('ce19_oneri_straordinari'))
        return vp - co + fin

    def _calculate_income_statement(
        self,
        base_inc: IncomeStatement,
        assumption: BudgetAssumptions,
        previous_inc,
        previous_bs=None,
        financing_loans=None
    ) -> Dict:
        """
        Calculate forecasted income statement based on assumptions
        """
        # Growth rates apply YEAR OVER YEAR: each forecast year grows from the
        # PREVIOUS year, not from the consuntivo base year. So +5/+5/+5 compounds
        # (100 → 105 → 110,25 → 115,76) instead of being flat vs base (105 each
        # year). For the first forecast year previous_inc IS base_inc, so nothing
        # changes there. Flat carry-forward lines (ce02/03/10/11/13-19) keep
        # reading base_inc — with no growth % the two are identical.
        def _pinc(field):
            v = getattr(previous_inc, field, None) if previous_inc is not None else None
            return v if v is not None else Decimal('0')

        # Apply growth rates to the previous year values (overrides take precedence)
        if assumption.ce01_override is not None:
            ce01 = assumption.ce01_override
        else:
            ce01 = _pinc('ce01_ricavi_vendite') * (Decimal('1') + assumption.revenue_growth_pct / Decimal('100'))
        if assumption.ce04_override is not None:
            ce04 = assumption.ce04_override
        else:
            ce04 = _pinc('ce04_altri_ricavi') * (Decimal('1') + assumption.other_revenue_growth_pct / Decimal('100'))

        # Calculate costs - split between variable and fixed components based on user-defined percentages

        # Materials
        if assumption.ce05_override is not None:
            ce05 = assumption.ce05_override
        else:
            base_materials = _pinc('ce05_materie_prime')
            fixed_pct_materials = assumption.fixed_materials_percentage / Decimal('100')
            variable_pct_materials = Decimal('1') - fixed_pct_materials
            variable_materials = base_materials * variable_pct_materials
            fixed_materials = base_materials * fixed_pct_materials
            ce05 = (
                variable_materials * (Decimal('1') + assumption.variable_materials_growth_pct / Decimal('100')) +
                fixed_materials * (Decimal('1') + assumption.fixed_materials_growth_pct / Decimal('100'))
            )

        # Services
        if assumption.ce06_override is not None:
            ce06 = assumption.ce06_override
        else:
            base_services = _pinc('ce06_servizi')
            fixed_pct_services = assumption.fixed_services_percentage / Decimal('100')
            variable_pct_services = Decimal('1') - fixed_pct_services
            variable_services = base_services * variable_pct_services
            fixed_services = base_services * fixed_pct_services
            ce06 = (
                variable_services * (Decimal('1') + assumption.variable_services_growth_pct / Decimal('100')) +
                fixed_services * (Decimal('1') + assumption.fixed_services_growth_pct / Decimal('100'))
            )

        # Rent/Godimento beni
        if assumption.ce07_override is not None:
            ce07 = assumption.ce07_override
        else:
            ce07 = _pinc('ce07_godimento_beni') * (Decimal('1') + assumption.rent_growth_pct / Decimal('100'))

        # Personnel
        if assumption.ce08_override is not None:
            ce08 = assumption.ce08_override
        else:
            ce08 = _pinc('ce08_costi_personale') * (Decimal('1') + assumption.personnel_growth_pct / Decimal('100'))

        # Personnel sub-items — override or maintain same proportions as the previous year.
        # Salari/oneri scale with the personnel total; TFR (ce08a) is instead the statutory
        # accrual salari/13,5 (so the sp15 fund — which reads ce08a — grows every year even
        # when the base import only carried the aggregate personnel cost); ce08d absorbs the
        # remainder so the four sub-items still sum to the personnel total.
        prev_ce08 = _pinc('ce08_costi_personale')
        if prev_ce08 > 0:
            growth_factor = ce08 / prev_ce08
        else:
            growth_factor = Decimal('1')
        ce08b = assumption.ce08b_override if assumption.ce08b_override is not None else _pinc('ce08b_salari_stipendi') * growth_factor
        ce08c = assumption.ce08c_override if assumption.ce08c_override is not None else _pinc('ce08c_oneri_sociali') * growth_factor
        # Cap the derived TFR quota at the remainder left by salari+oneri so the four
        # sub-items never sum to more than the personnel total (an explicit override is
        # trusted as-is). ce08d then absorbs the exact remainder.
        ce08a = assumption.ce08a_override if assumption.ce08a_override is not None else min(tfr_accrual_quota(ce08b, ce08), max(Decimal('0'), ce08 - ce08b - ce08c))
        ce08d = assumption.ce08d_override if assumption.ce08d_override is not None else max(Decimal('0'), ce08 - ce08a - ce08b - ce08c)

        # Depreciation — override total or calculate from investments
        depreciation_rate_tangible = assumption.depreciation_rate / Decimal('100')
        depreciation_rate_intangible = (getattr(assumption, 'depreciation_rate_intangible', None) or assumption.depreciation_rate) / Decimal('100')
        intangible_inv, tangible_inv = self._get_split_investments(assumption)
        new_depr_intangible = intangible_inv * depreciation_rate_intangible if intangible_inv > 0 else Decimal('0')
        new_depr_tangible = tangible_inv * depreciation_rate_tangible if tangible_inv > 0 else Decimal('0')

        # Depreciation sub-items: override, else carry the PREVIOUS year's charge forward
        # (it already includes prior investments' depreciation) plus this year's new
        # investment depreciation — so a one-off investment keeps being depreciated in
        # later years instead of reverting to the base-year charge (#7). The charge is
        # then capped at the available net book value (previous NBV + this year's
        # investment) so depreciation stops once the asset is fully written down (#5).
        base_ce09a = getattr(base_inc, 'ce09a_ammort_immateriali', None) or Decimal('0')
        base_ce09b = getattr(base_inc, 'ce09b_ammort_materiali', None) or Decimal('0')
        base_ce09c = getattr(base_inc, 'ce09c_svalutazioni', None) or Decimal('0')
        base_ce09d = getattr(base_inc, 'ce09d_svalutazione_crediti', None) or Decimal('0')

        def _prev_inc_val(field, fallback):
            v = getattr(previous_inc, field, None) if previous_inc is not None else None
            return v if v is not None else fallback

        def _prev_bs_val(field):
            if previous_bs is None:
                return Decimal('0')
            if isinstance(previous_bs, dict):
                return previous_bs.get(field, Decimal('0')) or Decimal('0')
            return getattr(previous_bs, field, Decimal('0')) or Decimal('0')

        prev_ce09a = _prev_inc_val('ce09a_ammort_immateriali', base_ce09a)
        prev_ce09b = _prev_inc_val('ce09b_ammort_materiali', base_ce09b)
        avail_intangible = max(Decimal('0'), _prev_bs_val('sp02_immob_immateriali') + intangible_inv)
        avail_tangible = max(Decimal('0'), _prev_bs_val('sp03_immob_materiali') + tangible_inv)

        if assumption.ce09a_override is not None:
            ce09a = assumption.ce09a_override
        else:
            ce09a = min(prev_ce09a + new_depr_intangible, avail_intangible)
        if assumption.ce09b_override is not None:
            ce09b = assumption.ce09b_override
        else:
            ce09b = min(prev_ce09b + new_depr_tangible, avail_tangible)
        ce09c = assumption.ce09c_override if assumption.ce09c_override is not None else base_ce09c
        ce09d = assumption.ce09d_override if assumption.ce09d_override is not None else base_ce09d

        # Total depreciation: override or sum of sub-items
        if assumption.ce09_override is not None:
            ce09 = assumption.ce09_override
        else:
            ce09 = ce09a + ce09b + ce09c + ce09d

        # Other costs
        if assumption.ce12_override is not None:
            ce12 = assumption.ce12_override
        else:
            ce12 = _pinc('ce12_oneri_diversi') * (Decimal('1') + assumption.other_costs_growth_pct / Decimal('100'))

        # Asset disposal (dismissione/vendita cespite): proceeds - net book value = gain/loss.
        # Post-2016 OIC: plusvalenza ordinaria → A.5 altri ricavi (ce04); minusvalenza → B.14
        # oneri diversi (ce12). The disposed asset's NBV is removed from sp03 in the balance
        # sheet and the sale proceeds flow in through the cash plug.
        disposal_nbv = getattr(assumption, 'asset_disposal_nbv', None) or Decimal('0')
        disposal_proceeds = getattr(assumption, 'asset_disposal_proceeds', None) or Decimal('0')
        if disposal_nbv > 0 or disposal_proceeds > 0:
            disposal_gain = disposal_proceeds - disposal_nbv
            if disposal_gain >= 0:
                ce04 = ce04 + disposal_gain
            else:
                ce12 = ce12 + (-disposal_gain)

        # CE line items: use override if set, otherwise fall back to base year
        ce02 = assumption.ce02_override if assumption.ce02_override is not None else base_inc.ce02_variazioni_rimanenze
        ce03 = assumption.ce03_override if assumption.ce03_override is not None else base_inc.ce03_lavori_interni
        # A.4 "Incrementi di immobilizzazioni per lavori interni" — carried as its own line.
        # Without this the engine silently dropped it from the production value (the client's
        # "380.423 che sparisce / non si azzera" issue) and it had no override.
        _base_ce03a = getattr(base_inc, 'ce03a_incrementi_immobilizzazioni', None) or Decimal('0')
        ce03a = assumption.ce03a_override if getattr(assumption, 'ce03a_override', None) is not None else _base_ce03a
        ce10 = assumption.ce10_override if assumption.ce10_override is not None else base_inc.ce10_var_rimanenze_mat_prime
        ce11 = assumption.ce11_override if assumption.ce11_override is not None else base_inc.ce11_accantonamenti
        ce11b = assumption.ce11b_override if assumption.ce11b_override is not None else base_inc.ce11b_altri_accantonamenti
        ce13 = assumption.ce13_override if assumption.ce13_override is not None else base_inc.ce13_proventi_partecipazioni
        ce16 = assumption.ce16_override if assumption.ce16_override is not None else base_inc.ce16_utili_perdite_cambi
        ce17a = assumption.ce17a_override if assumption.ce17a_override is not None else (getattr(base_inc, 'ce17a_rivalutazioni', None) or Decimal('0'))
        ce17b = assumption.ce17b_override if assumption.ce17b_override is not None else (getattr(base_inc, 'ce17b_svalutazioni', None) or Decimal('0'))
        ce17 = assumption.ce17_override if assumption.ce17_override is not None else (ce17a - ce17b)
        ce18 = assumption.ce18_override if assumption.ce18_override is not None else base_inc.ce18_proventi_straordinari
        ce19 = assumption.ce19_override if assumption.ce19_override is not None else base_inc.ce19_oneri_straordinari

        # Financial income/costs: use override if set, otherwise carry forward from base year
        ce14 = assumption.ce14_override if assumption.ce14_override is not None else base_inc.ce14_altri_proventi_finanziari
        ce15 = assumption.ce15_override if assumption.ce15_override is not None else base_inc.ce15_oneri_finanziari

        # Add interest on NEW financing raised during the plan. Charged on the
        # OUTSTANDING balance at the start of each year (shared kernel), so a loan
        # raised once keeps generating interest — decreasing as it amortises —
        # across every year it is on the balance sheet, not only in the year of
        # erogazione. Interest is 0 automatically once the loan is fully repaid or
        # when the rate is 0.
        _, _, financing_interest = new_financing_schedule(financing_loans, assumption.forecast_year)
        ce15 = ce15 + financing_interest

        # Taxes - use override if set, otherwise use tax rate
        production_value = ce01 + ce02 + ce03 + ce03a + ce04
        production_cost = ce05 + ce06 + ce07 + ce08 + ce09 + ce10 + ce11 + ce11b + ce12
        ebit = production_value - production_cost
        financial_result = ce13 + ce14 - ce15 + ce16
        profit_before_tax = ebit + financial_result + ce17 + (ce18 - ce19)
        if assumption.ce20_override is not None:
            ce20 = assumption.ce20_override
        else:
            # Use the company's EFFECTIVE tax rate derived from the base year (captures
            # the IRES + IRAP blend on their different bases). A flat IRES-only rate
            # understates tax and overstates the forecast utile. Fall back to the
            # explicit assumption.tax_rate when the base year has no usable signal or
            # the derived rate is implausible (losses, tax credits, deferred taxes).
            base_pbt = self._pbt_from_income(base_inc)
            eff_rate = None
            base_tax = getattr(base_inc, 'ce20_imposte', None) or Decimal('0')
            if base_tax > 0 and base_pbt > 0:
                eff_rate = base_tax / base_pbt
                if eff_rate <= 0 or eff_rate > Decimal('0.6'):
                    eff_rate = None
            tax_rate_decimal = eff_rate if eff_rate is not None else (assumption.tax_rate / Decimal('100'))
            ce20 = max(Decimal('0'), profit_before_tax * tax_rate_decimal)

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
            'ce17a_rivalutazioni': ce17a,
            'ce17b_svalutazioni': ce17b,
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
        previous_bs,
        year_offset: int = 1,
        financing_loans=None
    ) -> Dict:
        """
        Calculate forecasted balance sheet based on assumptions and forecast income statement.
        Builds debt detail bottom-up: financial debts from repayment schedule,
        trade payables from DPO, other operating debts carried forward.
        """
        D = Decimal
        ZERO = D('0')
        DAYS = D('360')

        # Helper to read fields from previous_bs (could be ORM object or dict)
        def _prev(field, default=ZERO):
            if isinstance(previous_bs, dict):
                return previous_bs.get(field, default)
            return getattr(previous_bs, field, default) or default

        def _base(field, default=ZERO):
            return getattr(base_bs, field, default) or default

        # ── ASSETS ──

        # Fixed assets - previous year + investments - depreciation
        ce09a = forecast_inc.get('ce09a_ammort_immateriali', ZERO)
        ce09b = forecast_inc.get('ce09b_ammort_materiali', ZERO)
        ce09c = forecast_inc.get('ce09c_svalutazioni', ZERO)

        intangible_inv, tangible_inv = self._get_split_investments(assumption)

        # Asset disposal: remove the disposed cespite's net book value from sp03 (tangible
        # fixed assets). The proceeds/gain are booked in the P&L; the cash plug brings in
        # the sale cash automatically, keeping the balance sheet balanced.
        disposal_nbv = getattr(assumption, 'asset_disposal_nbv', None) or ZERO
        sp02 = max(ZERO, _prev('sp02_immob_immateriali') + intangible_inv - ce09a)
        sp03 = max(ZERO, _prev('sp03_immob_materiali') + tangible_inv - ce09b - disposal_nbv)

        # Helper for SP growth % fields (nullable → 0% = carry forward)
        def _sp_growth(field_name):
            val = getattr(assumption, field_name, None)
            if val is None:
                return ZERO
            return D(str(val)) / D('100')

        sp04 = max(ZERO, _prev('sp04_immob_finanziarie') * (D('1') + _sp_growth('sp04_growth_pct')) - ce09c)

        # Working capital via turnover days
        # When turnover days are not explicitly set, derive them from the base year
        # so that working capital scales proportionally with revenue/purchases.
        forecast_revenue = forecast_inc['ce01_ricavi_vendite']
        forecast_purchases = forecast_inc['ce05_materie_prime'] + forecast_inc['ce06_servizi']
        base_revenue = base_inc.ce01_ricavi_vendite or D('1')
        base_purchases = (base_inc.ce05_materie_prime + base_inc.ce06_servizi) or D('1')

        # Crediti tributari (sp06e) and imposte anticipate (sp06f) are NOT commercial
        # receivables and must NOT scale with revenue via DSO (the client's "crediti
        # tributari / imposte anticipate che salgono coi ricavi — non è corretto"): they
        # depend on the fiscal position, not on turnover. Carry them forward from the
        # previous year, with an optional manual % (sp06e_growth_pct / sp06f_growth_pct)
        # — mirroring the tax/other debts on the passivo (sp16e_growth_pct). Default
        # (no %) → constant. Only the TRADE buckets (clienti/controllate/collegate/
        # controllanti/altri) are driven by DSO below.
        sp06e = _prev('sp06e_crediti_tributari_breve') * (D('1') + _sp_growth('sp06e_growth_pct'))
        sp06f = _prev('sp06f_imposte_anticipate_breve') * (D('1') + _sp_growth('sp06f_growth_pct'))

        # DSO → sp06 TRADE receivables (short-term). Auto-derive DSO from the base year
        # TRADE receivables only (sp06 aggregate minus tax credits and deferred taxes),
        # so carving those out above does not distort the ratio.
        dso = getattr(assumption, 'dso_days', None)
        if dso is not None:
            dso = D(str(dso))
        else:
            base_sp06_trade = max(
                ZERO,
                _base('sp06_crediti_breve')
                - _base('sp06e_crediti_tributari_breve')
                - _base('sp06f_imposte_anticipate_breve'),
            )
            dso = (base_sp06_trade / base_revenue * DAYS) if base_revenue > 0 else ZERO
        sp06_trade = forecast_revenue * dso / DAYS
        sp06 = sp06_trade + sp06e + sp06f

        # DIO → sp05 (inventory)
        dio = getattr(assumption, 'dio_days', None)
        if dio is not None:
            dio = D(str(dio))
        else:
            # Auto-derive DIO from base year: base_sp05 / base_revenue * 360
            base_sp05 = _base('sp05_rimanenze')
            dio = (base_sp05 / base_revenue * DAYS) if base_revenue > 0 else ZERO
        sp05 = forecast_revenue * dio / DAYS

        # Long-term receivables, other current assets
        sp07 = _prev('sp07_crediti_lungo') * (D('1') + assumption.receivables_long_growth_pct / D('100'))
        sp08 = _prev('sp08_attivita_finanziarie') * (D('1') + _sp_growth('sp08_growth_pct'))
        sp10 = _prev('sp10_ratei_risconti_attivi') * (D('1') + _sp_growth('sp10_growth_pct'))
        sp01 = _prev('sp01_crediti_soci') * (D('1') + _sp_growth('sp01_growth_pct'))

        # ── EQUITY ──

        net_profit = (
            forecast_inc['ce01_ricavi_vendite'] +
            forecast_inc['ce02_variazioni_rimanenze'] +
            forecast_inc['ce03_lavori_interni'] +
            forecast_inc.get('ce03a_incrementi_immobilizzazioni', Decimal('0')) +
            forecast_inc['ce04_altri_ricavi'] -
            forecast_inc['ce05_materie_prime'] -
            forecast_inc['ce06_servizi'] -
            forecast_inc['ce07_godimento_beni'] -
            forecast_inc['ce08_costi_personale'] -
            forecast_inc['ce09_ammortamenti'] -
            forecast_inc['ce10_var_rimanenze_mat_prime'] -
            forecast_inc['ce11_accantonamenti'] -
            forecast_inc['ce11b_altri_accantonamenti'] -
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

        sp11 = _base('sp11_capitale')
        previous_profit = _prev('sp13_utile_perdita')
        sp12 = _prev('sp12_riserve') + previous_profit
        sp13 = net_profit

        # Reserve detail
        sp12a = _base('sp12a_riserva_sovrapprezzo')
        sp12b = _base('sp12b_riserve_rivalutazione')
        sp12c = _base('sp12c_riserva_legale')
        sp12d = _base('sp12d_riserve_statutarie')
        sp12e = _base('sp12e_altre_riserve')
        sp12f = _base('sp12f_riserva_copertura_flussi')
        sp12g = _prev('sp12g_utili_perdite_portati') + previous_profit
        sp12h = _base('sp12h_riserva_neg_azioni_proprie')

        # ── LIABILITIES (bottom-up from components) ──

        # Other liabilities (non-debt)
        sp14 = _prev('sp14_fondi_rischi') * (D('1') + _sp_growth('sp14_growth_pct'))
        # TFR fund: previous fund + accrual. When the accrual is suspended (companies
        # with >60 employees pay the maturing TFR to the INPS treasury fund from a given
        # year rather than accruing it internally), the fund stops growing. The ce08a
        # cost stays in the P&L (it is paid out, not retained), so the outflow is reflected
        # through equity/cash — no internal liability is created.
        tfr_suspended = bool(getattr(assumption, 'tfr_accrual_suspended', False))
        if tfr_suspended:
            sp15 = _prev('sp15_tfr')
        else:
            sp15 = _prev('sp15_tfr') + forecast_inc.get('ce08a_tfr_accrual', ZERO)
        sp18 = _prev('sp18_ratei_risconti_passivi') * (D('1') + _sp_growth('sp18_growth_pct'))

        # --- FINANCIAL DEBTS: repayment schedule ---
        existing_repay_years = getattr(assumption, 'existing_debt_repayment_years', None)

        # Carry forward financial sub-fields from previous year
        sp16a = _prev('sp16a_debiti_banche_breve')
        sp16b = _prev('sp16b_debiti_altri_finanz_breve')
        sp16c = _prev('sp16c_debiti_obbligazioni_breve')
        sp17a = _prev('sp17a_debiti_banche_lungo')
        sp17b = _prev('sp17b_debiti_altri_finanz_lungo')
        sp17c = _prev('sp17c_debiti_obbligazioni_lungo')

        # Handle abbreviato gap: if previous year has aggregate but no sub-field
        # detail, allocate the unaccounted portion to banche (bank debt).
        prev_sp16_agg = _prev('sp16_debiti_breve')
        prev_sp17_agg = _prev('sp17_debiti_lungo')

        # --- TRADE PAYABLES: DPO ---
        dpo = getattr(assumption, 'dpo_days', None)
        if dpo is not None:
            dpo = D(str(dpo))
        else:
            # Auto-derive DPO from base year: base_sp16d / base_purchases * 360
            base_sp16d = _base('sp16d_debiti_fornitori_breve')
            dpo = (base_sp16d / base_purchases * DAYS) if base_purchases > 0 else ZERO
        sp16d = forecast_purchases * dpo / DAYS

        # Long-term trade payables
        sp17d = _prev('sp17d_debiti_fornitori_lungo') * (D('1') + _sp_growth('sp17d_growth_pct'))

        # --- OTHER OPERATING DEBTS: carry forward with optional growth % ---
        sp16e = _prev('sp16e_debiti_tributari_breve') * (D('1') + _sp_growth('sp16e_growth_pct'))
        sp16g = _prev('sp16g_altri_debiti_breve') * (D('1') + _sp_growth('sp16g_growth_pct'))
        sp17e = _prev('sp17e_debiti_tributari_lungo') * (D('1') + _sp_growth('sp17e_growth_pct'))
        sp17g = _prev('sp17g_altri_debiti_lungo') * (D('1') + _sp_growth('sp17g_growth_pct'))

        # Previdenza (sp16f/sp17f): opt-in scaling with the personnel cost (P5).
        # When enabled, social-security payables move in proportion to ce08 vs the BASE
        # year (e.g. personnel 100k→200k ⇒ previdenza 20k→40k), anchored on the base-year
        # amount so multi-year chains stay consistent. Default OFF → carry forward with
        # the manual sp16f/sp17f_growth_pct, exactly as before (zero regression).
        if getattr(assumption, 'previdenza_scales_with_personnel', False):
            base_ce08 = (getattr(base_inc, 'ce08_costi_personale', ZERO) or ZERO)
            fc_ce08 = (forecast_inc.get('ce08_costi_personale', ZERO) or ZERO)
            pers_factor = (fc_ce08 / base_ce08) if base_ce08 > 0 else D('1')
            sp16f = _base('sp16f_debiti_previdenza_breve') * pers_factor
            sp17f = _base('sp17f_debiti_previdenza_lungo') * pers_factor
        else:
            sp16f = _prev('sp16f_debiti_previdenza_breve') * (D('1') + _sp_growth('sp16f_growth_pct'))
            sp17f = _prev('sp17f_debiti_previdenza_lungo') * (D('1') + _sp_growth('sp17f_growth_pct'))

        # Detect abbreviato gap: difference between aggregate and sum of sub-fields.
        # This happens when imported data only has sp16/sp17 totals (abbreviato format)
        # but no detail breakdown — sub-fields are all 0 while aggregate is > 0.
        # Allocate the gap to banche (sp16a/sp17a) as the default financial debt bucket.
        prev_sp16_detail = sp16a + sp16b + sp16c + sp16d + sp16e + sp16f + sp16g
        gap_short = prev_sp16_agg - prev_sp16_detail
        if gap_short > ZERO:
            sp16a = sp16a + gap_short

        prev_sp17_detail = sp17a + sp17b + sp17c + sp17d + sp17e + sp17f + sp17g
        gap_long = prev_sp17_agg - prev_sp17_detail
        if gap_long > ZERO:
            sp17a = sp17a + gap_long

        # Apply repayment schedule to existing financial debt (reduces long-term).
        # The instalment is FIXED on the ORIGINAL (base-year) financial long-term debt
        # so the debt fully amortises to zero after `existing_repay_years`. (Recomputing
        # the instalment on the shrinking residual each year — the previous behaviour —
        # is a decreasing instalment that never reaches zero: e.g. over 3 years it leaves
        # 8/27 ≈ 30% outstanding, the "residuo" the user reported.)
        if existing_repay_years is not None and D(str(existing_repay_years)) > 0:
            # Fixed instalment on the ORIGINAL (base-year) BANK + BONDS long-term debt,
            # including the abbreviato gap allocated to banks when only the aggregate sp17
            # is imported. The instalment FORMULA lives in the shared kernel so it is
            # identical to the intra-year engine by construction (P2); here it is
            # apportioned across the current residual bank/bond sub-fields. NB: sp17b
            # (altri finanziatori) is repaid on its OWN schedule below, not here.
            annual_repayment = financial_repayment_instalment(_base, existing_repay_years)
            total_bank_bonds = sp17a + sp17c   # current residual, for apportioning
            if total_bank_bonds > 0:
                bank_share = sp17a / total_bank_bonds
                bonds_share = sp17c / total_bank_bonds
                sp17a = max(ZERO, sp17a - annual_repayment * bank_share)
                sp17c = max(ZERO, sp17c - annual_repayment * bonds_share)

        # Altri finanziatori (sp17b) — e.g. an intra-group loan — repaid on its OWN fixed
        # schedule, independent of the bank debt (shared kernel: fixed instalment on the
        # base-year amount, amortises fully to zero after `altri_finanz_repayment_years`).
        altri_repay_years = getattr(assumption, 'altri_finanz_repayment_years', None)
        if altri_repay_years is not None and D(str(altri_repay_years)) > 0:
            annual_altri = altri_finanz_repayment_instalment(_base, altri_repay_years)
            sp17b = max(ZERO, sp17b - annual_altri)

        # New financing raised during the plan: add what is raised THIS year to
        # long-term bank debt, then subtract this year's straight-line instalment
        # so the loan amortises over its durata (shared kernel, mirrors the
        # existing-debt plan above). Because sp17a is carried forward via `_prev`,
        # a loan raised once (e.g. 150k in year 1, then 0) stays on the sheet and
        # shrinks by its rata each year instead of persisting flat forever.
        fin_raised, fin_repayment, _ = new_financing_schedule(financing_loans, assumption.forecast_year)
        sp17a = sp17a + fin_raised
        sp17a = max(ZERO, sp17a - fin_repayment)

        # --- AGGREGATE sp16/sp17 from components ---
        sp16 = sp16a + sp16b + sp16c + sp16d + sp16e + sp16f + sp16g
        sp17 = sp17a + sp17b + sp17c + sp17d + sp17e + sp17f + sp17g

        # ── CASH PLUG ──
        total_assets_no_cash = sp01 + sp02 + sp03 + sp04 + sp05 + sp06 + sp07 + sp08 + sp10
        total_liabilities = sp11 + sp12 + sp13 + sp14 + sp15 + sp16 + sp17 + sp18

        sp09 = total_liabilities - total_assets_no_cash

        # If cash is negative, increase short-term bank debt instead
        if sp09 < 0:
            sp16a = sp16a + abs(sp09)
            sp16 = sp16 + abs(sp09)
            sp09 = ZERO
        elif bool(getattr(assumption, 'cash_sweep_enabled', False)):
            # ── CASH SWEEP (opt-in) ── Use cash generated above the minimum floor to pay
            # down BANK debt — short-term first (sp16a), then long-term (sp17a) — instead
            # of letting idle cash accumulate while the debt stays flat (the client's
            # "la cassa cresce ma il debito v/banche resta invariato"). Cash and debt are
            # reduced by the same amount, so the balance sheet stays balanced.
            floor = getattr(assumption, 'cash_sweep_min_cash', None)
            floor = D(str(floor)) if floor is not None else ZERO
            excess = sp09 - floor
            if excess > ZERO:
                pay_short = min(excess, sp16a)
                sp16a -= pay_short; sp16 -= pay_short; sp09 -= pay_short; excess -= pay_short
                pay_long = min(excess, sp17a)
                sp17a -= pay_long; sp17 -= pay_long; sp09 -= pay_long; excess -= pay_long

        # ── DETAIL BREAKDOWNS ──

        # Immobilizzazioni finanziarie (sp04 sub-fields)
        total_base_sp04 = (
            _base('sp04a_partecipazioni') + _base('sp04b_crediti_immob_breve') +
            _base('sp04c_crediti_immob_lungo') + _base('sp04d_altri_titoli') +
            _base('sp04e_strumenti_derivati_attivi')
        )
        if total_base_sp04 > 0:
            ratio = sp04 / total_base_sp04
            sp04a = _base('sp04a_partecipazioni') * ratio
            sp04b = _base('sp04b_crediti_immob_breve') * ratio
            sp04c = _base('sp04c_crediti_immob_lungo') * ratio
            sp04d = _base('sp04d_altri_titoli') * ratio
            sp04e = _base('sp04e_strumenti_derivati_attivi') * ratio
        else:
            sp04a = sp04b = sp04c = sp04d = sp04e = ZERO

        # Trade receivables / inventory detail (sp06*, sp05*): the engine drives only the
        # aggregates (sp06 from DSO, sp05 from DIO), but the forecast BS renders the IV-CEE
        # sub-rows (e.g. "1) verso clienti" = sp06a). Without writing them the rows stay
        # blank. Allocate the aggregate proportionally to the base-year detail; when the
        # base has no detail, put it all in the primary bucket (clienti / materie).
        def _alloc(aggregate, base_fields, primary_idx=0):
            base_vals = [_base(f) for f in base_fields]
            tot = sum(base_vals, ZERO)
            if tot > 0:
                return [aggregate * (v / tot) for v in base_vals]
            out = [ZERO] * len(base_fields)
            out[primary_idx] = aggregate
            return out

        # Allocate the DSO-driven TRADE total across the commercial buckets only
        # (a/b/c/d/g). Crediti tributari (sp06e) and imposte anticipate (sp06f) keep the
        # carried-forward values computed in the working-capital section above — they do
        # not scale with revenue.
        sp06_trade_fields = ['sp06a_crediti_clienti_breve', 'sp06b_crediti_controllate_breve',
                             'sp06c_crediti_collegate_breve', 'sp06d_crediti_controllanti_breve',
                             'sp06g_crediti_altri_breve']
        sp06a, sp06b, sp06c, sp06d, sp06g = _alloc(sp06_trade, sp06_trade_fields)

        sp05_fields = ['sp05a_materie_prime', 'sp05b_prodotti_in_corso', 'sp05c_lavori_in_corso',
                       'sp05d_prodotti_finiti', 'sp05e_acconti']
        sp05a, sp05b, sp05c, sp05d, sp05e = _alloc(sp05, sp05_fields)

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
            'sp05a_materie_prime': sp05a,
            'sp05b_prodotti_in_corso': sp05b,
            'sp05c_lavori_in_corso': sp05c,
            'sp05d_prodotti_finiti': sp05d,
            'sp05e_acconti': sp05e,
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
