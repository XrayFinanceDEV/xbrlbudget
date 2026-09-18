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


BANK_FIELDS = ('sp16a_debiti_banche_breve', 'sp17a_debiti_banche_lungo', 'sp16c_debiti_obbligazioni_breve', 'sp17c_debiti_obbligazioni_lungo')
NONBANK_FINANCIAL_FIELDS = ('sp16b_debiti_altri_finanz_breve', 'sp17b_debiti_altri_finanz_lungo',
                            'sp16d_debiti_fornitori_breve', 'sp17d_debiti_fornitori_lungo',
                            'sp16e_debiti_tributari_breve', 'sp17e_debiti_tributari_lungo',
                            'sp16f_debiti_previdenza_breve', 'sp17f_debiti_previdenza_lungo')


def financial_debt_total(field_value: Callable[[str], Decimal]) -> Decimal:
    """Debito finanziario con un'unica convenzione, quella della PFN.

    Banche e obbligazioni se positive; altrimenti debito totale meno i dettagli
    non bancari noti; altrimenti il debito totale. Usata dalla PFN e dalla
    composizione delle fonti: un solo numero, una sola convenzione.
    """
    bank = sum((field_value(field) for field in BANK_FIELDS), ZERO)
    if bank > 0:
        return bank
    nonbank = sum((field_value(field) for field in NONBANK_FINANCIAL_FIELDS), ZERO)
    debt = field_value('sp16_debiti_breve') + field_value('sp17_debiti_lungo')
    return debt - nonbank if nonbank > 0 else debt


def indicator_results(bs, inc, analytical_ratios=None) -> dict[str, IndicatorResult]:
    """No annualization: flows retain the duration identified by their period."""
    if bs is None or inc is None:
        return {}
    v = lambda field: bs.get(field, inc.get(field, ZERO))
    ce = calculate_ce_result(inc)
    b = balance_aggregates(bs)
    fixed, equity, assets = b['fixed_assets'], b['total_equity'], b['total_assets']
    short, long, debt = v('sp16_debiti_breve'), v('sp17_debiti_lungo'), b['total_debt']
    current = b['current_assets'] - v('sp07_crediti_lungo') + v('sp10_ratei_risconti_attivi')
    financial_debt = financial_debt_total(v)
    pfn = financial_debt - v('sp09_disponibilita_liquide') - v('sp08_attivita_finanziarie')
    revenue, interest = v('ce01_ricavi_vendite'), v('ce15_oneri_finanziari')
    result = {}
    practice_convention = ('pratica-v1: attivo corrente senza crediti oltre 12 mesi, con ratei attivi; '
                           'CE canonico; flussi del periodo non annualizzati; nessun punteggio implicito.')
    def ratio(key, numerator, denominator, formula, *, percentage=False, positive=False):
        reason = 'zero_denominator' if denominator == 0 else 'non_positive_denominator' if positive and denominator < 0 else None
        value = None if reason else numerator / denominator * (HUNDRED if percentage else Decimal('1'))
        result['practice.' + key] = IndicatorResult(value, reason, formula, practice_convention)
    def amount(key, value, formula):
        result['practice.' + key] = IndicatorResult(value, None, formula, practice_convention)
    ratio('dscr', ce.ebitda - ce.taxes, interest, '(EBITDA - imposte) / oneri finanziari: proxy della pratica, non servizio completo del debito.', positive=True)
    ratio('ebitda_margin', ce.ebitda, revenue, 'EBITDA / ricavi × 100', percentage=True)
    amount('mt', current - v('sp05_rimanenze') - short, 'Attivo corrente pratica - rimanenze - debiti entro 12 mesi')
    amount('ccn', current - short, 'Attivo corrente pratica - debiti entro 12 mesi')
    ratio('current_ratio', current, short, 'Attivo corrente pratica / debiti entro 12 mesi')
    ratio('quick_ratio', current - v('sp05_rimanenze'), short, 'Attivo corrente pratica - rimanenze / debiti entro 12 mesi')
    amount('ms', equity - fixed, 'Patrimonio netto - immobilizzazioni')
    ratio('copertura_immob', equity + long, fixed, '(Patrimonio netto + debiti oltre 12 mesi) / immobilizzazioni × 100', percentage=True)
    ratio('indipendenza', equity, assets, 'Patrimonio netto / totale attivo × 100', percentage=True)
    amount('pfn', pfn, 'Banche e obbligazioni se dettaglio positivo; altrimenti debito al netto dei dettagli non bancari noti; altrimenti debito totale; meno cassa e attività finanziarie.')
    ratio('pfn_ebitda', pfn, ce.ebitda, 'PFN pratica / EBITDA del periodo')
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
        'liquidity.current_ratio': short, 'liquidity.quick_ratio': short, 'liquidity.acid_test': short,
        'solvency.autonomy_index': assets, 'solvency.leverage_ratio': equity, 'solvency.debt_to_equity': equity,
        'solvency.debt_to_production': ce.production_value,
        'profitability.roe': equity, 'profitability.roi': assets, 'profitability.ros': revenue,
        'profitability.rod': debt, 'profitability.ebitda_margin': revenue,
        'coverage.fixed_assets_coverage_with_equity_and_ltdebt': fixed,
        'coverage.fixed_assets_coverage_with_equity': fixed, 'coverage.independence_from_third_parties': debt,
        'activity.inventory_turnover_days': revenue, 'activity.receivables_turnover_days': revenue,
        'activity.payables_turnover_days': dpo_base, 'activity.asset_turnover': assets,
        'extended_profitability.financial_leverage_effect': equity,
        'extended_profitability.ebitda_on_sales': revenue, 'extended_profitability.financial_charges_on_revenue': revenue,
        'efficiency.revenue_per_employee_cost': v('ce08_costi_personale'), 'efficiency.revenue_per_materials_cost': v('ce05_materie_prime'),
    }
    formulas = {
        'liquidity.current_ratio': 'Attivo corrente del modello / debiti entro 12 mesi',
        'liquidity.quick_ratio': '(Crediti entro e oltre 12 mesi + cassa) / debiti entro 12 mesi',
        'liquidity.acid_test': '(Crediti entro e oltre 12 mesi + attività finanziarie + cassa) / debiti entro 12 mesi',
        'solvency.autonomy_index': 'Patrimonio netto / totale attivo',
        'solvency.leverage_ratio': 'Immobilizzazioni / patrimonio netto',
        'solvency.debt_to_equity': 'Debiti totali / patrimonio netto',
        'solvency.debt_to_production': 'Debiti totali / valore della produzione',
        'profitability.roe': 'Utile netto / patrimonio netto', 'profitability.roi': 'EBIT / totale attivo',
        'profitability.ros': 'Utile netto / ricavi: convenzione analitica distinta dal ROS operativo della pratica',
        'profitability.rod': 'Oneri finanziari / debiti totali', 'profitability.ebitda_margin': 'EBITDA / ricavi',
        'coverage.fixed_assets_coverage_with_equity_and_ltdebt': '(Patrimonio netto + debiti oltre 12 mesi) / immobilizzazioni',
        'coverage.fixed_assets_coverage_with_equity': 'Patrimonio netto / immobilizzazioni',
        'coverage.independence_from_third_parties': 'Patrimonio netto / debiti totali',
        'activity.inventory_turnover_days': '360 × rimanenze / ricavi',
        'activity.receivables_turnover_days': '360 × crediti entro e oltre 12 mesi / ricavi',
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
        reason = 'source_calculation_unavailable' if value is None else 'zero_denominator' if any(d == 0 for d in bases) else 'non_positive_denominator' if key == 'profitability.roe' and equity < 0 else None
        if key in ('activity.payables_turnover_days', 'activity.cash_conversion_cycle') and any(f in detail_missing for f in ('sp16d_debiti_fornitori_breve', 'sp17d_debiti_fornitori_lungo')):
            reason = 'trade_payables_detail_unavailable'
        result['analytical.' + key] = IndicatorResult(None if reason else value, reason, formula,
            'Motore FinancialRatiosCalculator: stock finali, anno commerciale 360 giorni, rapporti arrotondati a 4 decimali, giorni interi. Percentuali convertite in punti percentuali dal backend; flussi non annualizzati.')
    return result
