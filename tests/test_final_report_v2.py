"""M2-00B: dossier sources, complete catalogs, exact values and version safety."""
import copy
import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.schemas.final_report import FinalReportModel
from app.schemas.final_report_v2 import FinalReportModelV2, StatementPeriod
from app.services.final_report_dossier import CATALOG, DossierSource, extend_dossier
from calculations.report_indicators import indicator_results
from tests.test_final_report_endpoint import client, _url

ROOT = Path(__file__).resolve().parents[1]


def fixture_report(name='bilancio', years=None):
    raw = json.loads((ROOT / 'tests/fixtures/final_report' / f'{name}.json').read_text())
    if years:
        raw['practice']['periods']['forecast_years'] = years
        raw['forecast']['years'] = [dict(copy.deepcopy(raw['forecast']['years'][0]), year=y) for y in years]
        for chart in raw['chart_series']:
            chart['categories'] = years
            for metric in chart['series']:
                metric['values'] = [metric['values'][0]] * len(years)
    report = FinalReportModel.model_validate(raw, context={'skip_hash_validation': True})
    from database.models import BalanceSheet, IncomeStatement
    sources = []
    for year in report.forecast.years:
        bs = {c.name: Decimal('0') for c in BalanceSheet.__table__.columns if c.name.startswith('sp')}
        inc = {c.name: Decimal('0') for c in IncomeStatement.__table__.columns if c.name.startswith('ce')}
        # The minimal M1 fixtures use presentation aliases. V2 fixtures declare
        # synthetic accounting zeros explicitly and map their known amounts.
        bs.update({('sp09_disponibilita_liquide' if l.code == 'cash' else l.code): l.value for l in year.balance_sheet})
        inc.update({('ce01_ricavi_vendite' if l.code == 'revenue' else l.code): l.value for l in year.income_statement})
        sources.append(DossierSource(StatementPeriod(id=f'forecast:{year.year}', year=year.year, label=str(year.year), basis='forecast', period_months=12, source='synthetic_fixture'), bs, inc))
    return extend_dossier(report, sources)


@pytest.mark.parametrize('workflow', ['infrannuale', 'bilancio', 'startup'])
@pytest.mark.parametrize('years', [[2027], [2027, 2028, 2029], list(range(2027, 2032))])
def test_shared_v2_workflows_neutral_titles_and_round_trip(workflow, years):
    report = fixture_report(workflow, years)
    title = 'Report Budget 2027' + (f' - {years[-1]}' if len(years) > 1 else '')
    assert report.document.title == title
    assert report.editorial_plan is None and report.editorial_readiness.status == 'pending'
    assert len(report.chart_series) > 6
    encoded = report.model_dump(mode='json')
    assert ('infrannual_closing' in encoded) == (workflow == 'infrannuale')
    assert FinalReportModelV2.model_validate_json(json.dumps(encoded)).model_dump(mode='json') == encoded
    for statement in report.detailed_statements:
        assert [r.id for r in statement.rows] == [r['id'] for r in CATALOG[statement.id]]
    for indicator in CATALOG['practice_indicators']:
        assert 'practice.' + indicator['key'] in {i.id for i in report.indicator_catalog}
    for indicator in CATALOG['analytical_indicators']:
        assert 'analytical.' + indicator['key'] in {i.id for i in report.indicator_catalog}


def test_live_api_negotiation_preserves_v1_and_exact_v2_source_values(client):
    from database.models import BudgetScenario, FinancialYear
    url = _url(client, client.ids['scenario'])
    before = client.get(url).json()
    v2 = client.get(url + '?schema_version=2')
    assert v2.status_code == 200, v2.text
    report = FinalReportModelV2.model_validate(v2.json())
    assert report.document.title == 'Report Budget 2027'
    assert report.source_hash != before['source_hash']
    assert client.get(url + '?schema_version=1').json()['model_hash'] == before['model_hash']
    assert client.get(url + '?schema_version=3').status_code == 422
    assert client.get(_url(client, client.ids['foreign']) + '?schema_version=2').status_code == 404
    with client.sessions() as db:
        scenario = db.get(BudgetScenario, client.ids['scenario'])
        scenario_stamp = scenario.updated_at
        historical_stamp = db.query(FinancialYear).filter_by(company_id=client.ids['company']).one().updated_at
    repeat = client.get(url + '?schema_version=2').json()
    assert (repeat['source_hash'], repeat['model_hash']) == (report.source_hash, report.model_hash)
    with client.sessions() as db:
        assert db.get(BudgetScenario, client.ids['scenario']).updated_at == scenario_stamp
        assert db.query(FinancialYear).filter_by(company_id=client.ids['company']).one().updated_at == historical_stamp
    forecast_column = next(i for i, p in enumerate(report.detailed_statements[0].periods) if p.basis == 'forecast')
    revenue = next(r for r in report.detailed_statements[0].rows if r.code == 'ce01_ricavi_vendite')
    assert revenue.values[forecast_column] == Decimal('110')
    ratio = next(i for i in report.indicator_catalog if i.id == 'analytical.profitability.ebitda_margin')
    assert ratio.values[forecast_column] == Decimal('100')  # points, not raw fraction 1
    from app.services.analysis_service import get_complete_analysis
    with client.sessions() as db:
        analysis = get_complete_analysis(db, client.ids['company'], client.ids['scenario'], exact_decimals=True)
    authoritative_cf = next(c for c in analysis['calculations']['cashflow']['years'] if c['year'] == 2027)
    cf_statement = report.detailed_statements[2]
    cf_column = next(i for i, p in enumerate(cf_statement.periods) if p.basis == 'forecast')
    for row in cf_statement.rows:
        if row.kind not in ('section', 'group'):
            expected = authoritative_cf
            for key in row.code.split('.'):
                expected = expected[key]
            assert row.values[cf_column] == expected


def test_null_zero_negative_and_proxy_dscr_availability():
    bs = {'sp09_disponibilita_liquide': Decimal('100'), 'sp11_capitale': Decimal('100')}
    inc = {'ce01_ricavi_vendite': Decimal('100'), 'ce05_materie_prime': Decimal('100')}
    values = indicator_results(bs, inc)
    assert values['practice.ebitda_margin'].value == Decimal('0')
    assert values['practice.dscr'].value is None
    assert values['practice.dscr'].reason == 'zero_denominator'
    assert values['practice.pfn'].value == Decimal('-100')
    assert values['practice.pfn_ebitda'].value is None
    bs['sp11_capitale'] = Decimal('-100')
    assert indicator_results(bs, inc)['practice.roe'].reason == 'non_positive_denominator'


def test_missing_model_field_is_preserved_as_unavailable_and_not_a_header():
    report = fixture_report()
    row = next(r for r in report.detailed_statements[0].rows if 'quiescenza' in r.label)
    assert row.kind == 'detail' and not row.applicable
    assert row.values == [None] * len(row.values)
    assert set(row.unavailable_reasons) == {'model_field_unavailable'}


def test_ce_subtotal_uses_canonical_detail_first_netting_and_decimal_precision():
    from app.services.final_report_dossier import build_detailed_statements
    amount = Decimal('9007199254740993.01')
    source = DossierSource(StatementPeriod(id='forecast:2027', year=2027, label='2027', basis='forecast', source='fixture'),
        {}, {'ce01_ricavi_vendite': amount, 'ce17_rettifiche_attivita_fin': Decimal('999'), 'ce17a_rivalutazioni': Decimal('20'), 'ce17b_svalutazioni': Decimal('3')})
    statement = build_detailed_statements([source])[0]
    subtotal = next(r for r in statement.rows if r.code == 'ce17_rettifiche_attivita_fin')
    assert subtotal.values == [Decimal('17')]
    revenue = next(r for r in statement.rows if r.code == 'ce01_ricavi_vendite')
    assert revenue.model_dump(mode='json')['values'] == ['9007199254740993.01']


@pytest.mark.parametrize('mutation, error', [
    (lambda r: r['document'].update(title='Margini in crescita'), 'neutral'),
    (lambda r: r['detailed_statements'][0]['rows'][1].update(parent_id='missing'), 'parent'),
    (lambda r: r['detailed_statements'][0]['rows'][1].update(values=[1.25]), 'exact JSON strings'),
    (lambda r: r['detailed_statements'][0]['rows'][1].update(values=[None] * len(r['document']['budget_years']), unavailable_reasons=[None] * len(r['document']['budget_years'])), 'unavailability'),
    (lambda r: r['editorial_readiness'].update(status='ready'), 'pending'),
    (lambda r: r['chart_series'][-1]['series'][0].update(values=['999'] * len(r['document']['budget_years'])), 'match referenced'),
])
def test_contract_rejects_invalid_dossier_extensions(mutation, error):
    raw = fixture_report().model_dump(mode='json')
    mutation(raw)
    with pytest.raises(ValueError, match=error):
        FinalReportModelV2.model_validate(raw, context={'skip_hash_validation': True})


def test_editorial_content_does_not_change_economic_hash_but_changes_model_hash():
    report = fixture_report()
    changed = report.model_copy(deep=True)
    changed.editorial_readiness.reasons = ['Preparing layout']
    assert changed.calculate_source_hash() == report.source_hash
    assert changed.calculate_model_hash() != report.model_hash
    changed.indicator_catalog[0].methodology += ' Changed convention.'
    assert changed.calculate_source_hash() != report.source_hash


def test_unallocated_aggregate_details_remain_null_but_reconciled_zero_is_zero():
    from app.services.final_report_dossier import build_detailed_statements
    p = StatementPeriod(id='historical:2026', year=2026, label='2026', basis='historical', source='fixture')
    raw = {'sp05_rimanenze': Decimal('100'), 'sp05a_materie_prime': Decimal('0'), 'sp05d_prodotti_finiti': Decimal('0')}
    statement = build_detailed_statements([DossierSource(p, raw, {})])[1]
    row = next(r for r in statement.rows if r.code == 'sp05a_materie_prime')
    assert row.values == [None] and row.unavailable_reasons == ['detail_not_declared']
    raw['sp05d_prodotti_finiti'] = Decimal('100')
    statement = build_detailed_statements([DossierSource(p, raw, {})])[1]
    row = next(r for r in statement.rows if r.code == 'sp05a_materie_prime')
    assert row.values == [Decimal('0')]


@pytest.mark.parametrize('snapshot_available', [True, False])
def test_intra_api_has_distinct_observed_adjusted_and_closing_bases(client, snapshot_available):
    from database.models import (BalanceSheet, BudgetScenario, FinancialYear, ForecastBalanceSheet, ForecastIncomeStatement, ForecastYear, IncomeStatement)
    with client.sessions() as db:
        budget = db.get(BudgetScenario, client.ids['scenario'])
        source = BudgetScenario(company_id=budget.company_id, name='9M', base_year=2025, period_months=9, scenario_type='infrannuale', workflow_type='infrannuale')
        closing = ForecastYear(year=2026)
        closing.balance_sheet = ForecastBalanceSheet(sp09_disponibilita_liquide=Decimal('130'))
        closing.income_statement = ForecastIncomeStatement(ce01_ricavi_vendite=Decimal('125'))
        source.forecast_years = [closing]
        db.add(source); db.flush()
        partial = FinancialYear(company_id=budget.company_id, year=2026, period_months=9,
            original_bs_snapshot=json.dumps({'sp09_disponibilita_liquide': '80'}) if snapshot_available else None,
            original_is_snapshot=json.dumps({'ce01_ricavi_vendite': '80'}) if snapshot_available else None,
            rettifiche_log=json.dumps([{'id': 'r1', 'edited_field': 'ce01_ricavi_vendite', 'edit_delta': '10', 'counterpart_field': 'sp09_disponibilita_liquide', 'counterpart_delta': '10', 'created_at': '2026-09-30T10:00:00'}]))
        partial.balance_sheet = BalanceSheet(sp09_disponibilita_liquide=Decimal('90'))
        partial.income_statement = IncomeStatement(ce01_ricavi_vendite=Decimal('90'))
        budget.workflow_type, budget.source_scenario_id = 'infrannuale', source.id
        db.add(partial); db.commit()
    response = client.get(_url(client, client.ids['scenario']) + '?schema_version=2')
    assert response.status_code == 200, response.text
    report = FinalReportModelV2.model_validate(response.json())
    statement = report.detailed_statements[0]
    columns = {p.basis: i for i, p in enumerate(statement.periods)}
    assert set(columns) >= {'observed', 'adjusted', 'closing', 'forecast'}
    revenue = next(r for r in statement.rows if r.code == 'ce01_ricavi_vendite')
    assert revenue.values[columns['observed']] == (Decimal('80') if snapshot_available else None)
    assert revenue.values[columns['adjusted']] == Decimal('90')
    assert revenue.values[columns['closing']] == Decimal('125')
    assert statement.periods[columns['observed']].period_months == 9
    analytical = next(i for i in report.indicator_catalog if i.id == 'analytical.profitability.roi')
    assert analytical.values[columns['closing']] is None  # Old promoted-record metrics are not this source closing.


def test_v2_requires_auth_and_company_ownership(client, monkeypatch):
    from app.core.config import settings
    from database.models import Company
    url = _url(client, client.ids['scenario']) + '?schema_version=2'
    monkeypatch.setattr(settings, 'DEV_USER_ID', None)
    assert client.get(url).status_code == 401
    monkeypatch.setattr(settings, 'DEV_USER_ID', 'final-report-user')
    with client.sessions() as db:
        db.get(Company, client.ids['company']).user_id = 'other-user'
        db.commit()
    assert client.get(url).status_code == 404


def test_v2_does_not_invent_budget_years_for_an_undeclared_plan(client):
    from database.models import BudgetScenario
    with client.sessions() as db:
        scenario = db.get(BudgetScenario, client.ids['scenario'])
        scenario.forecast_years.clear()
        scenario.assumptions.clear()
        db.commit()
    url = _url(client, client.ids['scenario'])
    assert client.get(url).status_code == 200  # Existing v1 blocked-report behavior.
    response = client.get(url + '?schema_version=2')
    assert response.status_code == 409
    assert 'Orizzonte budget' in response.json()['detail']


def test_wire_decimal_lists_never_emit_exponents():
    from app.schemas.final_report import ChartMetric
    metric = ChartMetric(key='zero', label='Zero', values=[Decimal('0E+2'), Decimal('1E+5')])
    assert metric.model_dump(mode='json')['values'] == ['0', '100000']


def test_catalog_has_economic_parents_for_totals_and_preserves_occurrences():
    ce = {r['code']: r for r in CATALOG['income_statement']}
    sp = {r['code']: r for r in CATALOG['balance_sheet']}
    cf = {r['code']: r for r in CATALOG['cashflow']}
    assert ce['ce09_ammortamenti']['parent_id'] == ce['10_ammortamenti_e_svalutazioni']['id']
    assert ce['net_profit']['parent_id'] is None
    assert ce['profit_before_tax']['parent_id'] is None
    assert sp['total_assets']['parent_id'] == sp['attivo']['id']
    difference = next(r for r in CATALOG['balance_sheet'] if r['difference'])
    assert difference['parent_id'] is None
    assert cf['cash_reconciliation.total_cashflow']['parent_id'] is None


def planned_report():
    from app.schemas.final_report_v2 import EditorialPlan
    report = fixture_report()
    plan = EditorialPlan.model_validate(dict(layout_version='test-1', font_version='font-1', asset_version='asset-1',
        source_hash=report.source_hash, plan_hash='0' * 64, pages=[dict(id='cover', section_id='cover', content_ids=['document'],
            note_id='cover-note', note_slot=dict(width_pt='400', height_pt='60', font_size_pt='9', max_lines=4))]), context={'skip_hash_validation': True})
    plan.plan_hash = plan.calculate_plan_hash()
    raw = report.model_dump(mode='json')
    raw['editorial_plan'] = plan.model_dump(mode='json')
    raw['editorial_notes'] = [dict(id='cover-note', content_ids=['document'], text='Nota neutrale sul perimetro del piano.', provenance='automatic',
        updated_at=raw['generated_at'], source_hash=report.source_hash, plan_hash=plan.plan_hash, revision=0, freshness='fresh')]
    raw['editorial_readiness'] = dict(status='ready', reasons=[])
    validated = FinalReportModelV2.model_validate(raw, context={'skip_hash_validation': True})
    raw['model_hash'] = validated.calculate_model_hash()
    return FinalReportModelV2.model_validate(raw)


def test_editorial_text_changes_model_hash_without_invalidating_its_plan():
    report = planned_report()
    changed = report.model_copy(deep=True)
    changed.editorial_notes[0].text = 'Nuova nota manuale sul medesimo perimetro.'
    changed.editorial_notes[0].provenance = 'user'
    assert changed.calculate_source_hash() == report.source_hash
    assert changed.editorial_plan.calculate_plan_hash() == report.editorial_plan.plan_hash
    assert changed.calculate_model_hash() != report.model_hash


@pytest.mark.parametrize('mutation, error', [
    (lambda r: r['editorial_notes'].clear(), 'fresh note'),
    (lambda r: r['editorial_notes'][0].update(content_ids=['wrong-section']), 'planned page contents'),
    (lambda r: r['editorial_notes'][0].update(freshness='stale'), 'fresh note'),
    (lambda r: r['editorial_plan'].update(source_hash='1' * 64), 'current report sources'),
])
def test_editorial_finalization_contract_rejects_missing_or_misassociated_notes(mutation, error):
    raw = planned_report().model_dump(mode='json')
    mutation(raw)
    with pytest.raises(ValueError, match=error):
        FinalReportModelV2.model_validate(raw, context={'skip_hash_validation': True})


def test_layout_change_requires_a_new_plan_hash():
    from app.schemas.final_report_v2 import EditorialPlan
    plan = planned_report().editorial_plan.model_dump(mode='json')
    plan['font_version'] = 'different-font'
    with pytest.raises(ValueError, match='plan_hash'):
        EditorialPlan.model_validate(plan)
