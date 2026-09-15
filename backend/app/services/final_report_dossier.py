"""Presentation-rich projection of authorized canonical report sources."""
from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from app.schemas.final_report import FinalReportModel
from app.schemas.final_report_v2 import (
    DetailedStatement, DetailedStatementRow, DocumentIdentity, DossierChartSeries,
    EditorialReadiness, FinalReportModelV2, IndicatorDefinition, StatementPeriod,
)
from calculations.ce_result import calculate_ce_result
from calculations.report_indicators import balance_aggregates, indicator_results, unavailable_details

CATALOG = json.loads((Path(__file__).resolve().parents[3] / 'contracts/final_report_dossier_catalog.json').read_text(encoding='utf-8'))
ZERO = Decimal('0')
UNITS = {'euro': 'eur', 'pct': 'percent', 'ratio': 'ratio', 'days': 'days'}


@dataclass(frozen=True)
class DossierSource:
    period: StatementPeriod
    balance_sheet: dict[str, Decimal] | None
    income_statement: dict[str, Decimal] | None
    calculations: dict | None = None
    cashflow: dict | None = None


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
    definitions += [('practice.' + key, {'label': label, 'format': 'pct'}, 'incidenze') for key, label in (('materials_revenue', 'Materie prime / Ricavi'), ('services_revenue', 'Servizi / Ricavi'))]
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
        detailed_statements=build_detailed_statements(sources), indicator_catalog=indicators, chart_series=charts,
        editorial_plan=None, editorial_notes=[],
        editorial_readiness=EditorialReadiness(status='pending', reasons=['Piano di impaginazione e commenti per pagina da preparare in M2-02A/M2-00C.']))
    draft = FinalReportModelV2.model_validate(payload, context={'skip_hash_validation': True})
    payload['source_hash'] = draft.calculate_source_hash()
    draft = FinalReportModelV2.model_validate(payload, context={'skip_hash_validation': True})
    payload['model_hash'] = draft.calculate_model_hash()
    return FinalReportModelV2.model_validate(payload)
