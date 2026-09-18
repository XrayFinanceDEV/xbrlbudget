"""Presentation-rich projection of authorized canonical report sources."""
from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from app.schemas.final_report import FinalReportModel
from app.schemas.final_report_v2 import (
    DetailedStatement, DetailedStatementRow, DocumentIdentity, DossierChartSeries,
    EditorialReadiness, FinalReportModelV2, IndicatorDefinition, ReportSeries,
    ReportSeriesGroup, StatementPeriod,
)
from calculations.ce_result import calculate_ce_result
from calculations.ratios import FinancialRatiosCalculator
from calculations.report_indicators import (
    balance_aggregates, financial_debt_total, indicator_results, unavailable_details,
)

CATALOG = json.loads((Path(__file__).resolve().parents[3] / 'contracts/final_report_dossier_catalog.json').read_text(encoding='utf-8'))
ZERO = Decimal('0')
HUNDRED = Decimal('100')
# La quota fissa di default di `calculate_break_even_analysis`: è quella che
# vale per i costi che non hanno un'ipotesi per categoria.
DEFAULT_FIXED_SHARE = Decimal('0.40')
BREAK_EVEN_COST_FIELDS = ('ce05_materie_prime', 'ce06_servizi', 'ce07_godimento_beni', 'ce08_costi_personale', 'ce12_oneri_diversi')
EQUITY_DEPS = ('sp11_capitale', 'sp12_riserve', 'sp13_utile_perdita')
LIABILITIES_DEPS = EQUITY_DEPS + ('sp16_debiti_breve', 'sp17_debiti_lungo', 'sp14_fondi_rischi', 'sp15_tfr', 'sp18_ratei_risconti_passivi')
UNITS = {'euro': 'eur', 'pct': 'percent', 'ratio': 'ratio', 'days': 'days'}


@dataclass(frozen=True)
class DossierSource:
    period: StatementPeriod
    balance_sheet: dict[str, Decimal] | None
    income_statement: dict[str, Decimal] | None
    calculations: dict | None = None
    cashflow: dict | None = None
    # Quota fissa per categoria delle ipotesi dello scenario (materie, servizi),
    # in punti percentuali. `None` su un anno di piano = nessuna ipotesi.
    fixed_split: tuple[Decimal, Decimal] | None = None


def _path(data, key):
    for part in key.split('.'):
        if not isinstance(data, dict) or part not in data:
            return None
        data = data[part]
    return data


def build_detailed_statements(sources: list[DossierSource]) -> list[DetailedStatement]:
    statements = []
    titles = {'income_statement': 'Conto economico completo', 'balance_sheet': 'Stato patrimoniale completo', 'cashflow': 'Rendiconto finanziario completo — metodo indiretto'}
    for key, title in titles.items():
        rows = []
        for definition in CATALOG[key]:
            values, reasons = [], []
            header = definition['kind'] in ('section', 'group')
            applicable = header or bool(definition['field'] or definition['dependencies'])
            for source in sources:
                value, reason = None, None
                raw = getattr(source, key)
                if header:
                    reason = 'presentation_header'
                elif not applicable:
                    reason = 'model_field_unavailable'
                elif raw is None:
                    reason = 'source_period_unavailable'
                elif key == 'cashflow':
                    value = _path(raw, definition['field'])
                else:
                    enriched = dict(raw)
                    missing_details = unavailable_details(raw)
                    if key == 'income_statement':
                        ce = calculate_ce_result(raw)
                        enriched.update({field: getattr(ce, field) for field in ('production_value', 'production_cost', 'ebitda', 'ebit', 'financial_result', 'extraordinary_result', 'profit_before_tax', 'net_profit')})
                        # The D-section subtotal follows canonical detail-first netting,
                        # even when a legacy aggregate is also stored.
                        enriched['ce17_rettifiche_attivita_fin'] = ce.value_adjustments
                    else:
                        enriched.update(balance_aggregates(raw))
                    if definition['field'] in missing_details or any(k in missing_details for k in definition['dependencies']):
                        reason = 'detail_not_declared'
                    elif definition['difference']:
                        value = enriched['total_assets'] - enriched['total_liabilities']
                    elif definition['dependencies']:
                        dependencies = [enriched.get(k) for k in definition['dependencies']]
                        if all(v is not None for v in dependencies):
                            value = sum(dependencies, ZERO)
                    else:
                        value = enriched.get(definition['field'])
                if value is None and reason is None:
                    reason = 'source_field_unavailable'
                values.append(value)
                reasons.append(reason)
            rows.append(DetailedStatementRow(
                **{k: definition[k] for k in ('id', 'code', 'label', 'parent_id', 'level', 'kind')},
                applicable=applicable, values=values, unavailable_reasons=reasons,
                source='DetailedCashFlowCalculator' if key == 'cashflow' else 'persisted_statement; calculate_ce_result' if key == 'income_statement' else 'persisted_statement; balance_aggregates',
            ))
        statements.append(DetailedStatement(id=key, title=title, catalog_version=CATALOG['catalog_version'], periods=[s.period for s in sources], rows=rows))
    return statements


def build_indicator_catalog(sources: list[DossierSource]) -> list[IndicatorDefinition]:
    results = [indicator_results(s.balance_sheet, s.income_statement, (s.calculations or {}).get('ratios')) for s in sources]
    definitions = [('practice.' + row['key'], row, 'pratica') for row in CATALOG['practice_indicators']]
    definitions += [('practice.' + key, {'label': label, 'format': 'pct'}, 'incidenze') for key, label in (('materials_revenue', 'Materie prime / Ricavi'), ('services_revenue', 'Servizi / Ricavi'), ('personnel_revenue', 'Personale / Ricavi'))]
    # M2-02E: quattro indicatori canonici mancanti (pagine 7, 8, 12 del dossier v4). Come
    # `materials_revenue`/`services_revenue`/`personnel_revenue` sopra, non stanno nel catalogo
    # TS-generato (`contracts/final_report_dossier_catalog.json`, esportato da
    # `frontend/lib/pratica-indicators.ts` per la scheda Indicatori della pratica, un perimetro
    # diverso): entrano qui perché sono voci del solo modello v2 del report finale.
    definitions += [
        ('practice.opex_revenue', {'label': 'Costi Operativi / Ricavi', 'format': 'pct'}, 'incidenze'),
        ('practice.effective_tax_rate', {'label': 'Aliquota Effettiva', 'format': 'pct'}, 'fiscalità'),
        ('practice.ebit_margin', {'label': 'Margine EBIT', 'format': 'pct'}, 'redditività'),
        ('practice.quick_ratio', {'label': 'Liquidità Immediata', 'format': 'ratio'}, 'liquidità'),
    ]
    definitions += [('analytical.' + row['key'], row, row['category']) for row in CATALOG['analytical_indicators']]
    indicators = []
    for identifier, row, family in definitions:
        unit = UNITS[row['format']]
        prototype = next((r[identifier] for r in results if identifier in r), None)
        values, reasons = [], []
        for result in results:
            entry = result.get(identifier)
            value = entry.value if entry else None
            reason = entry.reason if entry else 'source_period_unavailable'
            if identifier.startswith('analytical.') and unit == 'percent' and value is not None:
                value *= Decimal('100')
            values.append(value)
            reasons.append(reason)
        label = 'DSCR — proxy della pratica' if identifier == 'practice.dscr' else row['label']
        indicators.append(IndicatorDefinition(id=identifier, label=label, family=family, unit=unit,
            methodology=prototype.methodology if prototype else 'Fonte di calcolo non disponibile; nessuna formula applicata dal renderer.',
            convention=prototype.convention if prototype else 'Periodo e unità dichiarati; valori indisponibili distinti dallo zero.',
            periods=[s.period for s in sources], values=values, unavailable_reasons=reasons,
            source='calculations.report_indicators' if identifier.startswith('practice.') else 'FinancialRatiosCalculator',
        ))
    return indicators


def _share(value: Decimal | None, total: Decimal | None) -> tuple[Decimal | None, str | None]:
    """Quota percentuale sull'aggregato, con il proprio motivo quando manca."""
    if value is None:
        return None, 'source_field_unavailable'
    if total is None:
        return None, 'source_period_unavailable'
    if total == ZERO:
        return None, 'zero_denominator'
    if total < ZERO:
        return None, 'non_positive_denominator'
    return value / total * HUNDRED, None


def _deps_sum(data: dict[str, Decimal], keys: tuple[str, ...]) -> Decimal | None:
    """Somma gli aggregati come fa la riga del prospetto: campo assente ⇒ None."""
    return None if any(key not in data for key in keys) else sum((data[key] for key in keys), ZERO)


def _column(series: dict[str, tuple[list, list]], key: str, value: Decimal | None, reason: str | None) -> None:
    series[key][0].append(value)
    series[key][1].append(value is None and (reason or 'source_field_unavailable') or None)


def _columns(keys: tuple[str, ...]) -> dict[str, tuple[list, list]]:
    return {key: ([], []) for key in keys}


def _finish(series: dict[str, tuple[list, list]], labels: dict[str, str], unit: dict[str, str]) -> list[ReportSeries]:
    return [ReportSeries(id=key, label=labels[key], unit=unit[key], values=values, unavailable_reasons=reasons)
            for key, (values, reasons) in series.items()]


def build_structure_series(sources: list[DossierSource], indicators: list[IndicatorDefinition]) -> list[ReportSeriesGroup]:
    """Le serie delle pagine «Composizioni» e «Pareggio», dagli stessi numeri dei prospetti.

    Nulla qua ricalcola una formula: importi e quote vengono dagli aggregati
    canonici (`balance_aggregates`, `financial_debt_total`) e il pareggio da
    `FinancialRatiosCalculator.calculate_break_even_analysis` chiamato con la
    quota fissa blended delle ipotesi dello scenario. Un valore che non c'è è
    null con il proprio motivo, mai zero.
    """
    periods = [source.period for source in sources]

    uses = _columns(('fixed_assets', 'fixed_assets_share', 'current_other', 'current_other_share', 'cash', 'cash_share'))
    for source in sources:
        bs = source.balance_sheet
        if bs is None:
            for key in uses:
                _column(uses, key, None, 'source_period_unavailable')
            continue
        aggregates = balance_aggregates(bs)
        fixed, total, cash = aggregates['fixed_assets'], aggregates['total_assets'], bs.get('sp09_disponibilita_liquide')
        other = None if (cash is None or fixed is None) else total - fixed - cash
        for key, value in (('fixed_assets', fixed), ('current_other', other), ('cash', cash)):
            _column(uses, key, value, None if value is not None else 'source_field_unavailable')
            share, share_reason = _share(value, total)
            _column(uses, key + '_share', share, share_reason)

    sources_group = _columns(('equity', 'equity_share', 'financial_debt', 'financial_debt_share', 'other_liabilities', 'other_liabilities_share'))
    for source in sources:
        bs = source.balance_sheet
        if bs is None:
            for key in sources_group:
                _column(sources_group, key, None, 'source_period_unavailable')
            continue
        equity = _deps_sum(bs, EQUITY_DEPS)
        financial = financial_debt_total(lambda field: bs.get(field, ZERO))
        liabilities = _deps_sum(bs, LIABILITIES_DEPS)
        other = None if (equity is None or liabilities is None) else liabilities - equity - financial
        for key, value in (('equity', equity), ('financial_debt', financial), ('other_liabilities', other)):
            _column(sources_group, key, value, None if value is not None else 'source_field_unavailable')
            share, share_reason = _share(value, liabilities)
            _column(sources_group, key + '_share', share, share_reason)

    by_indicator = {indicator.id: indicator for indicator in indicators}
    incidence_specs = (('materials', 'Materie prime / Ricavi', 'practice.materials_revenue'),
                       ('services', 'Servizi / Ricavi', 'practice.services_revenue'),
                       ('personnel', 'Personale / Ricavi', 'practice.personnel_revenue'),
                       ('financial_charges', 'Oneri finanziari / Ricavi', 'practice.of_revenue'))
    incidence = [ReportSeries(id=key, label=label, unit='percent',
                              values=list(by_indicator[identifier].values),
                              unavailable_reasons=list(by_indicator[identifier].unavailable_reasons))
                 for key, label, identifier in incidence_specs]

    pareggio = _columns(('fixed_costs', 'variable_costs', 'contribution_margin', 'break_even_revenue', 'safety_margin_pct'))
    for source in sources:
        bs, inc = source.balance_sheet, source.income_statement
        if bs is None or inc is None:
            for key in pareggio:
                _column(pareggio, key, None, 'source_period_unavailable')
            continue
        if source.period.basis == 'forecast' and source.fixed_split is None:
            for key in pareggio:
                _column(pareggio, key, None, 'assumptions_missing')
            continue
        costs = [inc.get(key) for key in BREAK_EVEN_COST_FIELDS]
        if any(cost is None for cost in costs):
            for key in pareggio:
                _column(pareggio, key, None, 'source_field_unavailable')
            continue
        total_costs = sum(costs, ZERO)
        if source.fixed_split is None or total_costs == ZERO:
            fixed_share = DEFAULT_FIXED_SHARE
        else:
            materials_pct, services_pct = (percentage / HUNDRED for percentage in source.fixed_split)
            fixed_share = (costs[0] * materials_pct + costs[1] * services_pct
                           + sum(costs[2:], ZERO) * DEFAULT_FIXED_SHARE) / total_costs
        revenue = inc.get('ce01_ricavi_vendite')
        view = SimpleNamespace(revenue=ZERO if revenue is None else revenue,
                               ebit=calculate_ce_result(inc).ebit,
                               **{key: cost for key, cost in zip(BREAK_EVEN_COST_FIELDS, costs)})
        analysis = FinancialRatiosCalculator(None, view).calculate_break_even_analysis(fixed_cost_percentage=fixed_share)
        _column(pareggio, 'fixed_costs', analysis.fixed_costs, None)
        _column(pareggio, 'variable_costs', analysis.variable_costs, None)
        # Stessa guardia del blocco `pareggio` del motore budget: il ricavo di
        # pareggio esiste solo con ricavi e margine di contribuzione positivi.
        margin_raw = view.revenue - total_costs * (Decimal('1') - fixed_share)
        if revenue is None:
            reason = 'source_field_unavailable'
        elif view.revenue == ZERO:
            reason = 'zero_denominator'
        elif view.revenue < 0 or margin_raw <= 0:
            reason = 'non_positive_denominator'
        else:
            reason = None
        _column(pareggio, 'contribution_margin', None if revenue is None else analysis.contribution_margin,
                'source_field_unavailable')
        if reason is None:
            _column(pareggio, 'break_even_revenue', analysis.break_even_revenue, None)
            _column(pareggio, 'safety_margin_pct', analysis.safety_margin * HUNDRED, None)
        else:
            for key in ('break_even_revenue', 'safety_margin_pct'):
                _column(pareggio, key, None, reason)

    labels = {
        'fixed_assets': 'Immobilizzazioni nette', 'fixed_assets_share': 'Immobilizzazioni nette · quota %',
        'current_other': 'Circolante e altro', 'current_other_share': 'Circolante e altro · quota %',
        'cash': 'Disponibilità liquide', 'cash_share': 'Disponibilità liquide · quota %',
        'equity': 'Patrimonio netto', 'equity_share': 'Patrimonio netto · quota %',
        'financial_debt': 'Debiti finanziari', 'financial_debt_share': 'Debiti finanziari · quota %',
        'other_liabilities': 'Altre passività', 'other_liabilities_share': 'Altre passività · quota %',
        'fixed_costs': 'Costi fissi', 'variable_costs': 'Costi variabili',
        'contribution_margin': 'Margine di contribuzione', 'break_even_revenue': 'Ricavi di pareggio',
        'safety_margin_pct': 'Margine di sicurezza %',
    }
    eur = {key: 'eur' for key in labels}
    units = {**eur, **{key: 'percent' for key in labels if key.endswith('_share') or key == 'safety_margin_pct'}}
    return [
        ReportSeriesGroup(id='composition_uses', title='Composizione degli impieghi', periods=periods,
                          series=_finish(uses, labels, units), source='persisted_statement; balance_aggregates',
                          methodology="Immobilizzazioni nette e disponibilità liquide dagli aggregati di bilancio; il circolante e altro è il residuo sul totale dell'attivo. Quote percentuali sullo stesso totale."),
        ReportSeriesGroup(id='composition_sources', title='Composizione delle fonti', periods=periods,
                          series=_finish(sources_group, labels, units), source='persisted_statement; balance_aggregates; financial_debt_total',
                          methodology='Patrimonio netto dagli aggregati; debiti finanziari con la convenzione della PFN (banche'
                                      ' e obbligazioni se positive, altrimenti debito meno i dettagli non bancari noti, altrimenti'
                                      ' il debito totale); altre passività come residuo sul totale del passivo.'),
        ReportSeriesGroup(id='cost_incidence', title='Incidenza dei costi sui ricavi', periods=periods,
                          series=incidence, source='calculations.report_indicators',
                          methodology="Valori del catalogo indicatori (practice.*): rapporto sull'articolo CE 1 × 100, con i flussi del periodo senza annualizzazione."),
        ReportSeriesGroup(id='break_even', title='Pareggio e margine di sicurezza', periods=periods,
                          series=_finish(pareggio, labels, units), source='FinancialRatiosCalculator.calculate_break_even_analysis; BudgetAssumptions',
                          methodology='calculate_break_even_analysis chiamato con la quota fissa desunta dalle ipotesi per'
                                      ' categoria (materie e servizi) e con il 40% di default sugli altri costi operativi; i'
                                      ' periodi non di piano usano il default. Ricavi di pareggio e margine di sicurezza solo'
                                      ' con ricavi e margine di contribuzione positivi.'),
    ]


DOSSIER_CHARTS = (
    ('structural_balance', 'Equilibrio finanziario e strutturale', ('practice.ccn', 'practice.mt', 'practice.ms')),
    ('practice_liquidity', 'Liquidità corrente della pratica', ('practice.current_ratio',)),
    ('practice_profitability', 'Redditività operativa della pratica', ('practice.roi', 'practice.roe', 'practice.ros')),
    ('practice_asset_coverage', 'Autonomia e copertura immobilizzazioni', ('practice.indipendenza', 'practice.copertura_immob')),
    ('practice_net_debt', 'Posizione finanziaria netta della pratica', ('practice.pfn',)),
    ('practice_net_debt_ebitda', 'PFN / EBITDA della pratica', ('practice.pfn_ebitda',)),
    ('practice_dscr_proxy', 'Copertura degli oneri finanziari — proxy DSCR', ('practice.dscr',)),
    ('economic_incidence', 'Incidenze economiche sui ricavi', ('practice.ebitda_margin', 'practice.materials_revenue', 'practice.services_revenue')),
    ('financial_charges', 'Incidenza degli oneri finanziari', ('practice.of_revenue', 'practice.of_mol')),
    ('analytical_liquidity', 'Liquidità — convenzione analitica', ('analytical.liquidity.current_ratio', 'analytical.liquidity.quick_ratio', 'analytical.liquidity.acid_test')),
)


def extend_dossier(report: FinalReportModel, sources: list[DossierSource]) -> FinalReportModelV2:
    """Freeze exact sources in v2; pagination and AI remain subsequent steps."""
    payload = report.model_dump(mode='python')
    # model_dump omits closing for annual/startup via the inherited wire shape.
    payload.update(schema_version=2, source_hash='0' * 64, model_hash='0' * 64)
    years = report.practice.periods.forecast_years
    title = f'Report Budget {years[0]}' + (f' - {years[-1]}' if len(years) > 1 else '')
    indicators = build_indicator_catalog(sources)
    structure = build_structure_series(sources, indicators)
    by_id = {i.id: i for i in indicators}
    charts = list(report.chart_series)
    for identifier, chart_title, refs in DOSSIER_CHARTS:
        metrics = []
        for ref in refs:
            indicator = by_id[ref]
            by_year = {p.year: v for p, v in zip(indicator.periods, indicator.values) if p.basis == 'forecast'}
            metrics.append({'key': ref, 'label': indicator.label, 'values': [by_year.get(y) for y in years]})
        charts.append(DossierChartSeries(id=identifier, title=chart_title, unit=by_id[refs[0]].unit, categories=years,
            series=metrics, indicator_ids=list(refs), methodology='Valori del catalogo canonico; unità e convenzioni disponibili per ciascun indicatore.'))
    payload.update(document=DocumentIdentity(title=title, budget_years=years),
        detailed_statements=build_detailed_statements(sources), indicator_catalog=indicators,
        structure_series=structure, chart_series=charts,
        editorial_plan=None, editorial_notes=[],
        editorial_readiness=EditorialReadiness(status='pending', reasons=['Piano di impaginazione e commenti per pagina da preparare in M2-02A/M2-00C.']))
    draft = FinalReportModelV2.model_validate(payload, context={'skip_hash_validation': True})
    payload['source_hash'] = draft.calculate_source_hash()
    draft = FinalReportModelV2.model_validate(payload, context={'skip_hash_validation': True})
    payload['model_hash'] = draft.calculate_model_hash()
    return FinalReportModelV2.model_validate(payload)
