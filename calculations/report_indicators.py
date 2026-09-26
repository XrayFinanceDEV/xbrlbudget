"""Exact dossier indicator conventions and availability, shared by renderers.

Practice ratios retain their distinct balance-sheet perimeter. Economic results
come from the canonical CE engine, including detail-first D-section netting.
Analytical ratios retain the existing calculator's values and rounding, with
availability checked before its legacy safe_divide zero can reach the report.
"""
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Mapping

from calculations.ce_result import calculate_ce_result
from importers.iv_cee_hierarchy import detail_fields

ZERO = Decimal('0')
HUNDRED = Decimal('100')


def unavailable_details(raw: Mapping[str, Decimal]) -> set[str]:
    """Zero default subaccounts cannot explain an unallocated aggregate.

    Reuse the legal hierarchy. Nonzero details stay available; zero siblings
    are unknown when the declared aggregate is not fully allocated. A fully
    reconciled zero family remains a financial zero.
    """
    missing = set()
    for aggregate in raw:
        children = detail_fields(aggregate)
        if children and abs(raw[aggregate] - sum((raw.get(c, ZERO) for c in children), ZERO)) > Decimal('0.01'):
            missing.update(c for c in children if raw.get(c, ZERO) == ZERO)
    return missing


@dataclass(frozen=True)
class IndicatorResult:
    value: Decimal | None
    reason: str | None
    methodology: str
    convention: str


def balance_aggregates(bs: Mapping[str, Decimal]) -> dict[str, Decimal]:
    def total(*fields):
        return sum((bs.get(f, ZERO) for f in fields), ZERO)
    fixed = total('sp02_immob_immateriali', 'sp03_immob_materiali', 'sp04_immob_finanziarie')
    equity = total('sp11_capitale', 'sp12_riserve', 'sp13_utile_perdita')
    current = total('sp05_rimanenze', 'sp06_crediti_breve', 'sp07_crediti_lungo', 'sp08_attivita_finanziarie', 'sp09_disponibilita_liquide')
    debt = total('sp16_debiti_breve', 'sp17_debiti_lungo')
    assets = fixed + current + total('sp01_crediti_soci', 'sp10_ratei_risconti_attivi')
    liabilities = equity + debt + total('sp14_fondi_rischi', 'sp15_tfr', 'sp18_ratei_risconti_passivi')
    return {'fixed_assets': fixed, 'current_assets': current, 'total_assets': assets,
            'total_equity': equity, 'total_debt': debt, 'total_liabilities': liabilities}


def attivo_corrente(field_value: Callable[[str], Decimal]) -> Decimal:
    """Attivo corrente (C05, lotto 2 fix rilievi 2026-09-26): rimanenze + crediti a breve +
    attività finanziarie a breve + liquidità + ratei attivi. I crediti oltre 12 mesi (sp07) restano
    fuori: non sono correnti. Un solo calcolo condiviso da sezione 8 e Allegato E — prima ognuno
    portava una perimetrazione diversa e lo stesso bilancio dava due current ratio nello stesso
    documento.
    """
    fields = ('sp05_rimanenze', 'sp06_crediti_breve', 'sp08_attivita_finanziarie',
              'sp09_disponibilita_liquide', 'sp10_ratei_risconti_attivi')
    return sum((field_value(f) for f in fields), ZERO)


def passivo_corrente(field_value: Callable[[str], Decimal]) -> Decimal:
    """Passivo corrente (C05): debiti a breve + ratei passivi — simmetrico sull'attivo corrente,
    che include i ratei attivi (sp10). Senza sp18 il passivo corrente sarebbe sbilanciato sui ratei
    rispetto all'attivo che li conta già.
    """
    fields = ('sp16_debiti_breve', 'sp18_ratei_risconti_passivi')
    return sum((field_value(f) for f in fields), ZERO)


FINANCIAL_DEBT_FIELDS = ('sp16a_debiti_banche_breve', 'sp17a_debiti_banche_lungo',
                         'sp16b_debiti_altri_finanz_breve', 'sp17b_debiti_altri_finanz_lungo',
                         'sp16c_debiti_obbligazioni_breve', 'sp17c_debiti_obbligazioni_lungo')


def financial_debt_total(field_value: Callable[[str], Decimal]) -> Decimal:
    """Debito finanziario: banche, altri finanziatori e obbligazioni, breve e lungo (C03/C04,
    lotto 2 fix rilievi 2026-09-26). Somma incondizionata — mai un ramo "banche positive altrimenti
    fallback" che tagliava fuori gli altri finanziatori quando le banche c'erano già: stessa
    convenzione di `BalanceSheet.financial_debt_total` (database/models.py) e di `finDebt` in
    `frontend/lib/budget-piano-step.ts`. Fornitori, tributari e previdenziali non sono debito
    finanziario. Usata dalla PFN, dal ROD e dalla composizione delle fonti: un solo numero.
    """
    return sum((field_value(field) for field in FINANCIAL_DEBT_FIELDS), ZERO)


def _dscr_capital_quota(cashflow, *, is_forecast_year: bool = False,
                         rimborsi_piano: Decimal | None = None) -> tuple[Decimal | None, str | None]:
    """Quota capitale rimborsata nell'anno (C01, lotto 2 fix rilievi 2026-09-26; F2, decisione del
    proprietario 2026-09-26).

    Su un anno di PIANO (`is_forecast_year`) la quota viene esclusivamente da
    `engine_meta['rimborsi_piano']` del motore (`calculations/forecast_engine.py`): le sole rate
    di uno scadenziamento vero — contratti bancari, pregresso bancario su piano anni, altri
    finanziatori — mai il rimborso di uno scoperto, di un fido o dello sweep di cassa. Prima di
    questa correzione la quota veniva dal rendiconto (`financing.third_party_funds.decreases`,
    Task 5/C08), che mischia nella stessa riga il vero servizio del debito con la liquidità libera
    che rientra: su uno scenario con crescita −40/+80/0 e scoperto concesso il DSCR crollava da
    3,29 a 0,90 nell'anno in cui l'unico movimento era il rimborso dello scoperto, non un impegno
    contrattuale. Senza `rimborsi_piano` dichiarato (nessun `engine_meta` persistito, o un motore
    più vecchio di questa correzione): `rimborsi_piano_non_disponibile`, mai un fallback silenzioso.

    Sulla colonna BASE/storica (`is_forecast_year=False`, invariata dal Task 6) la quota resta
    quella letta dal rendiconto finanziario dettagliato dello stesso anno,
    `financing.third_party_funds.decreases` — il rimborso vero quando le erogazioni dell'anno sono
    note, la diminuzione netta del debito finanziario altrimenti. Un anno senza rendiconto (prima
    colonna storica del dossier, periodi infrannuali `observed`/`adjusted`, che non ne calcolano
    uno proprio) rende il DSCR indefinito allo stesso modo: mai un fallback silenzioso alla vecchia
    formula (EBITDA - imposte)/oneri, senza la quota capitale. Quando le erogazioni note dell'anno
    (motore di previsione) non bastano a spiegare l'aumento del debito rilevato
    (`erogazioni_incoerenti`), la quota capitale non è determinabile allo stesso modo — il
    rendiconto in quel caso è tornato al solo netto storico, che non è la quota capitale.
    """
    if is_forecast_year:
        if rimborsi_piano is None:
            return None, 'rimborsi_piano_non_disponibile'
        return rimborsi_piano, None
    if not cashflow:
        return None, 'cashflow_unavailable'
    financing = cashflow.get('financing') or {}
    if financing.get('erogazioni_incoerenti'):
        return None, 'rimborsi_non_determinabili'
    quota = (financing.get('third_party_funds') or {}).get('decreases')
    if quota is None:
        return None, 'cashflow_unavailable'
    return quota, None


DSCR_FORMULA = ('(MOL - imposte) / (oneri finanziari + quota capitale delle rate dei piani): sugli anni di piano '
                'la quota viene da engine_meta[\'rimborsi_piano\'] del motore — le sole rate di uno '
                'scadenziamento vero (contratti bancari, pregresso bancario su piano anni, altri finanziatori), '
                'mai il rimborso di uno scoperto, di un fido o dello sweep di cassa. Sulla colonna base/storica la '
                'quota resta la diminuzione netta del debito finanziario dell\'anno, dal rendiconto finanziario '
                'dettagliato (financing.third_party_funds.decreases) — il rimborso vero quando le erogazioni '
                'dell\'anno sono note. Indefinito senza un rendiconto per l\'anno (base/storica), con erogazioni '
                'note ma incoerenti col debito rilevato (base/storica), o senza rimborsi_piano dichiarato dal '
                'motore (piano): mai la vecchia formula senza quota capitale '
                '((EBITDA - imposte) / oneri finanziari).')


def indicator_results(bs, inc, analytical_ratios=None, cashflow=None, *, is_forecast_year: bool = False,
                       rimborsi_piano: Decimal | None = None) -> dict[str, IndicatorResult]:
    """No annualization: flows retain the duration identified by their period."""
    if bs is None or inc is None:
        return {}
    v = lambda field: bs.get(field, inc.get(field, ZERO))
    ce = calculate_ce_result(inc)
    b = balance_aggregates(bs)
    fixed, equity, assets = b['fixed_assets'], b['total_equity'], b['total_assets']
    short, long, debt = v('sp16_debiti_breve'), v('sp17_debiti_lungo'), b['total_debt']
    current = attivo_corrente(v)
    passivo = passivo_corrente(v)
    financial_debt = financial_debt_total(v)
    pfn = financial_debt - v('sp09_disponibilita_liquide') - v('sp08_attivita_finanziarie')
    # F1 (Critico, revisione finale lotto 2, 2026-09-26): le sei sotto-voci finanziarie
    # (sp16a/b/c, sp17a/b/c) tutte a zero mentre l'aggregato sp16+sp17 resta positivo non
    # significa "nessun debito finanziario" — significa che l'import non ha classificato
    # quel debito. Dichiarare PFN = -cassa in quel caso sarebbe falso: "non lo so", non
    # zero. `financial_debt_unavailable` guida PFN, PFN/EBITDA e il ROD analitico.
    financial_debt_unavailable = financial_debt == 0 and debt > 0
    revenue, interest = v('ce01_ricavi_vendite'), v('ce15_oneri_finanziari')
    # C02 (lotto 2 fix rilievi, 2026-09-26): il consumo di materie che governa il DIO, stessa
    # convenzione di `calculations/forecast_engine.py::consumo_base_materie` — un consumo non
    # positivo rende il DIO indefinito, mai zero né negativo.
    consumo_materie = v('ce05_materie_prime') + v('ce10_var_rimanenze_mat_prime')
    # F1: sp06a+sp07a a zero mentre l'aggregato sp06+sp07 resta positivo — stessa diagnosi del
    # debito finanziario, sui crediti commerciali. Guida il DSO analitico.
    trade_receivables = v('sp06a_crediti_clienti_breve') + v('sp07a_crediti_clienti_lungo')
    receivables_total = v('sp06_crediti_breve') + v('sp07_crediti_lungo')
    trade_receivables_unavailable = trade_receivables == 0 and receivables_total > 0
    result = {}
    practice_convention = ('pratica-v1: attivo corrente senza crediti oltre 12 mesi, con ratei attivi; '
                           'CE canonico; flussi del periodo non annualizzati; nessun punteggio implicito.')
    def ratio(key, numerator, denominator, formula, *, percentage=False, positive=False):
        reason = 'zero_denominator' if denominator == 0 else 'non_positive_denominator' if positive and denominator < 0 else None
        value = None if reason else numerator / denominator * (HUNDRED if percentage else Decimal('1'))
        result['practice.' + key] = IndicatorResult(value, reason, formula, practice_convention)
    def amount(key, value, formula):
        result['practice.' + key] = IndicatorResult(value, None, formula, practice_convention)
    quota_capitale, dscr_reason = _dscr_capital_quota(
        cashflow, is_forecast_year=is_forecast_year, rimborsi_piano=rimborsi_piano)
    if dscr_reason:
        result['practice.dscr'] = IndicatorResult(None, dscr_reason, DSCR_FORMULA, practice_convention)
    else:
        ratio('dscr', ce.ebitda - ce.taxes, interest + quota_capitale, DSCR_FORMULA, positive=True)
    ratio('ebitda_margin', ce.ebitda, revenue, 'EBITDA / ricavi × 100', percentage=True)
    # F6 (Importante, revisione finale lotto 2, 2026-09-26): MT allineato sul passivo corrente
    # simmetrico di C05 (debiti a breve + ratei passivi), non più i soli debiti a breve — altrimenti
    # il CCN (che invece li include già) e il MT dello stesso bilancio non tornano fra loro.
    amount('mt', current - v('sp05_rimanenze') - passivo, 'Attivo corrente pratica - rimanenze - passivo corrente (debiti entro 12 mesi + ratei passivi)')
    # C05 (lotto 2 fix rilievi, 2026-09-26): CCN, current ratio e quick ratio sul passivo corrente
    # simmetrico sui ratei (debiti a breve + ratei passivi) — stessa formula usata dall'Allegato E,
    # cosicché sezione 8 e Allegato E non pubblichino più due current ratio diversi sullo stesso
    # bilancio.
    amount('ccn', current - passivo, 'Attivo corrente pratica - passivo corrente (debiti entro 12 mesi + ratei passivi)')
    ratio('current_ratio', current, passivo, 'Attivo corrente pratica / passivo corrente (debiti entro 12 mesi + ratei passivi)')
    ratio('quick_ratio', current - v('sp05_rimanenze'), passivo, 'Attivo corrente pratica - rimanenze / passivo corrente (debiti entro 12 mesi + ratei passivi)')
    amount('ms', equity - fixed, 'Patrimonio netto - immobilizzazioni')
    # C07: il TFR è una fonte consolidata al pari del debito oltre 12 mesi, non fuori dal computo.
    ratio('copertura_immob', equity + long + v('sp15_tfr'), fixed, '(Patrimonio netto + debiti oltre 12 mesi + TFR) / immobilizzazioni × 100', percentage=True)
    ratio('indipendenza', equity, assets, 'Patrimonio netto / totale attivo × 100', percentage=True)
    # C04: debito finanziario (banche, altri finanziatori, obbligazioni) meno cassa e attività
    # finanziarie. F1: indefinita, non -cassa, quando il debito finanziario non è dettagliato.
    pfn_formula = 'Banche, altri finanziatori e obbligazioni (breve e lungo) meno cassa e attività finanziarie.'
    if financial_debt_unavailable:
        result['practice.pfn'] = IndicatorResult(None, 'financial_debt_detail_unavailable', pfn_formula, practice_convention)
        result['practice.pfn_ebitda'] = IndicatorResult(None, 'financial_debt_detail_unavailable', 'PFN pratica / EBITDA del periodo', practice_convention)
    else:
        amount('pfn', pfn, pfn_formula)
        ratio('pfn_ebitda', pfn, ce.ebitda, 'PFN pratica / EBITDA del periodo', positive=True)
    ratio('roi', ce.ebit, assets, 'EBIT / totale attivo × 100', percentage=True)
    ratio('roe', ce.net_profit, equity, 'Utile netto CE canonico / patrimonio netto × 100', percentage=True, positive=True)
    ratio('ros', ce.ebit, revenue, 'EBIT / ricavi × 100', percentage=True)
    ratio('ebit_margin', ce.ebit, revenue, 'EBIT / ricavi × 100', percentage=True)
    ratio('of_mol', interest, ce.ebitda, 'Oneri finanziari / EBITDA × 100', percentage=True)
    ratio('of_revenue', interest, revenue, 'Oneri finanziari / ricavi × 100', percentage=True)
    ratio('materials_revenue', v('ce05_materie_prime'), revenue, 'Materie prime / ricavi × 100', percentage=True)
    ratio('personnel_revenue', v('ce08_costi_personale'), revenue, 'Personale / ricavi × 100', percentage=True)
    ratio('services_revenue', v('ce06_servizi'), revenue, 'Servizi / ricavi × 100', percentage=True)
    ratio('opex_revenue', ce.production_cost - v('ce09_ammortamenti'), revenue,
          'Costi della produzione al netto degli ammortamenti (ce09) / ricavi × 100', percentage=True)

    # Aliquota effettiva: stessa convenzione del motore di previsione
    # (`calculations/forecast_engine.py::_tax_components`), ricalcolata qui sulle
    # voci canoniche del periodo perché il motore lavora su base_inc/projected_inc,
    # non su un singolo periodo del dossier. Stesso scarto oltre il 60%: un'aliquota
    # implausibile non è "zero", è "non lo so" (mappatura-v4-pagine-1-11.md §Driver).
    pbt = ce.profit_before_tax
    tax_reason = 'zero_denominator' if pbt == 0 else 'non_positive_denominator' if pbt < 0 else None
    tax_rate = None
    if tax_reason is None:
        tax_rate = ce.taxes / pbt
        if tax_rate > Decimal('0.6'):
            tax_reason = 'aliquota_fuori_intervallo_plausibile'
    tax_value = None if tax_reason else tax_rate * HUNDRED
    result['practice.effective_tax_rate'] = IndicatorResult(
        tax_value, tax_reason,
        'Imposte correnti (ce20_imposte) / risultato ante imposte × 100; scartata oltre il 60%, '
        'stessa soglia usata da _tax_components per derivare l\'aliquota effettiva del motore.',
        practice_convention)

    purchases = v('ce05_materie_prime') + v('ce06_servizi')
    dpo_base = purchases if purchases > 0 else revenue
    denominators = {
        'liquidity.current_ratio': passivo, 'liquidity.quick_ratio': passivo, 'liquidity.acid_test': short,
        'solvency.autonomy_index': assets, 'solvency.leverage_ratio': equity, 'solvency.debt_to_equity': equity,
        'solvency.debt_to_production': ce.production_value,
        'profitability.roe': equity, 'profitability.roi': assets, 'profitability.ros': revenue,
        'profitability.rod': financial_debt, 'profitability.ebitda_margin': revenue,
        'coverage.fixed_assets_coverage_with_equity_and_ltdebt': fixed,
        'coverage.fixed_assets_coverage_with_equity': fixed, 'coverage.independence_from_third_parties': debt,
        'activity.inventory_turnover_days': consumo_materie, 'activity.receivables_turnover_days': revenue,
        'activity.payables_turnover_days': dpo_base, 'activity.asset_turnover': assets,
        'extended_profitability.financial_leverage_effect': equity,
        'extended_profitability.ebitda_on_sales': revenue, 'extended_profitability.financial_charges_on_revenue': revenue,
        'efficiency.revenue_per_employee_cost': v('ce08_costi_personale'), 'efficiency.revenue_per_materials_cost': v('ce05_materie_prime'),
    }
    formulas = {
        'liquidity.current_ratio': '(Rimanenze + crediti a breve + attività finanziarie a breve + liquidità + ratei attivi) '
                                    '/ (debiti entro 12 mesi + ratei passivi) — stessa formula della sezione 8',
        'liquidity.quick_ratio': '(Crediti a breve + attività finanziarie a breve + liquidità + ratei attivi) '
                                  '/ (debiti entro 12 mesi + ratei passivi)',
        'liquidity.acid_test': '(Crediti entro e oltre 12 mesi + attività finanziarie + cassa) / debiti entro 12 mesi',
        'solvency.autonomy_index': 'Patrimonio netto / totale attivo',
        'solvency.leverage_ratio': 'Debiti totali / patrimonio netto',
        'solvency.debt_to_equity': 'Debiti totali / patrimonio netto',
        'solvency.debt_to_production': 'Debiti totali / valore della produzione',
        'profitability.roe': 'Utile netto / patrimonio netto', 'profitability.roi': 'EBIT / totale attivo',
        'profitability.ros': 'Utile netto / ricavi: convenzione analitica distinta dal ROS operativo della pratica',
        'profitability.rod': 'Oneri finanziari / debito finanziario (banche, altri finanziatori, obbligazioni)',
        'profitability.ebitda_margin': 'EBITDA / ricavi',
        'coverage.fixed_assets_coverage_with_equity_and_ltdebt': '(Patrimonio netto + debiti oltre 12 mesi + TFR) / immobilizzazioni',
        'coverage.fixed_assets_coverage_with_equity': 'Patrimonio netto / immobilizzazioni',
        'coverage.independence_from_third_parties': 'Patrimonio netto / debiti totali',
        'activity.inventory_turnover_days': '360 × rimanenze / (materie prime + variazione rimanenze materie prime); indefinito con consumo non positivo',
        'activity.receivables_turnover_days': '360 × crediti verso clienti entro e oltre 12 mesi / ricavi',
        'activity.payables_turnover_days': '360 × debiti verso fornitori entro e oltre 12 mesi / (materie + servizi); base ricavi se acquisti non positivi',
        'activity.cash_conversion_cycle': 'Giorni magazzino + giorni credito - giorni debito, prima degli arrotondamenti individuali',
        'activity.asset_turnover': 'Ricavi / totale attivo',
        'extended_profitability.spread': 'ROI - ROD, già arrotondati dal motore',
        'extended_profitability.financial_leverage_effect': 'Debiti totali / patrimonio netto',
        'extended_profitability.ebitda_on_sales': 'EBITDA / ricavi',
        'extended_profitability.financial_charges_on_revenue': 'Oneri finanziari / ricavi',
        'efficiency.revenue_per_employee_cost': 'Ricavi / costo del personale',
        'efficiency.revenue_per_materials_cost': 'Ricavi / materie prime',
    }
    detail_missing = unavailable_details(bs)
    for key, formula in formulas.items():
        category, name = key.split('.')
        value = (analytical_ratios or {}).get(category, {}).get(name)
        bases = [revenue, dpo_base] if key == 'activity.cash_conversion_cycle' else [assets, debt] if key == 'extended_profitability.spread' else [denominators[key]]
        non_positive = (key == 'profitability.roe' and equity < 0) or (key == 'activity.inventory_turnover_days' and consumo_materie < 0)
        reason = 'source_calculation_unavailable' if value is None else 'zero_denominator' if any(d == 0 for d in bases) else 'non_positive_denominator' if non_positive else None
        if key in ('activity.payables_turnover_days', 'activity.cash_conversion_cycle') and any(f in detail_missing for f in ('sp16d_debiti_fornitori_breve', 'sp17d_debiti_fornitori_lungo')):
            reason = 'trade_payables_detail_unavailable'
        # F1: stessa dichiarazione esplicita di trade_payables_detail_unavailable, sui crediti
        # commerciali (DSO, e il ciclo di conversione che lo somma) e sul debito finanziario (ROD).
        if key in ('activity.receivables_turnover_days', 'activity.cash_conversion_cycle') and trade_receivables_unavailable:
            reason = 'trade_receivables_detail_unavailable'
        if key == 'profitability.rod' and financial_debt_unavailable:
            reason = 'financial_debt_detail_unavailable'
        result['analytical.' + key] = IndicatorResult(None if reason else value, reason, formula,
            'Motore FinancialRatiosCalculator: stock finali, anno commerciale 360 giorni, rapporti arrotondati a 4 decimali, giorni interi. Percentuali convertite in punti percentuali dal backend; flussi non annualizzati.')
    return result
