"""Offline macro gate tests: no API, no production database writes."""
from dataclasses import replace
from contextlib import nullcontext
from decimal import Decimal as D
import json
from pathlib import Path
from types import SimpleNamespace

import fitz
import pytest

from importers import macro_analysis as ma
from importers.detail_enrichment import SourceRow, collect_source_rows


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import anthropic
    monkeypatch.setattr(anthropic, 'Anthropic', lambda **kw: pytest.fail('unexpected API call'))


def fixture_rows():
    data = {
        'sp09_disponibilita_liquide': '100.00', 'sp11_capitale': '60.00',
        'sp13_utile_perdita': '10.00', 'totale_patrimonio_netto': '70.00',
        'totale_debiti': '30.00', 'totale_attivo': '100.00', 'totale_passivo': '100.00',
        'ce01_ricavi_vendite': '50.00', 'ce06_servizi': '40.00',
        'valore_produzione': '50.00', 'costi_produzione': '40.00', 'risultato_ce': '10.00',
    }
    return [SourceRow(k, i + 1, 'T', k, (D(v),), positions=(400,), kinds=('current',),
                      statement='ce' if k.startswith('ce') or k in {
                          'valore_produzione', 'costi_produzione', 'risultato_ce'} else 'bs')
            for i, (k, v) in enumerate(data.items())]


def fixture_reader(rows, periods, feedback=()):
    facts = [ma.MacroFact(field=r.id, cells=[ma.MacroCell(row=r.id, column=0)])
             for r in rows if r.id in ma.FIELDS and r.amounts]
    return ma.MacroReading(facts=facts, absent=[ma.MacroAbsence(
        fields=sorted(set(ma.FIELDS) - {f.field for f in facts}))], unresolved=[])


def test_every_row_and_page_is_read_even_after_old_page_limits():
    rows = fixture_rows()
    calls = []
    def reader(batch, periods, feedback):
        calls.extend(r.id for r in batch if not r.id.startswith('context:'))
        return fixture_reader(batch, periods, feedback)
    bs, ce, _, _, report = ma.analyze_pdf_macros('unused', rows=rows, reader=reader, max_chars=900)
    assert sorted(calls) == sorted(r.id for r in rows)
    assert report['rows_completed'] == report['rows_total'] == len(rows)
    assert report['pages_read'] == list(range(1, 13))
    assert len(report['passes'][0]['chunks']) > 1
    assert bs['sp16_debiti_breve'] == 30 and bs['sp17_debiti_lungo'] == 0
    assert ce['ce06_servizi'] == 40 and report['status'] == 'verified'


def test_missing_is_not_zero_and_one_corrective_pass_is_allowed():
    rows = fixture_rows()
    calls = []
    def reader(batch, periods, feedback):
        calls.append(feedback)
        result = fixture_reader(batch, periods)
        if not feedback:
            # Omitted completely, not even explicitly declared absent.
            result.facts = [f for f in result.facts if f.field != 'ce06_servizi']
        return result
    *_, report = ma.analyze_pdf_macros('unused', rows=rows, reader=reader)
    assert len(calls) == 2 and 'ce06_servizi' in str(calls[1])
    assert report['status'] == 'verified'


def test_invalid_structured_answer_can_be_corrected_without_accepting_empty_cells():
    calls = []
    def reader(batch, periods, feedback):
        calls.append(feedback)
        if not feedback:
            return ma.MacroReading.model_validate({
                'facts': [{'field': 'ce06_servizi', 'cells': []}],
                'absent': [], 'unresolved': [],
            })
        return fixture_reader(batch, periods)
    *_, report = ma.analyze_pdf_macros('unused', rows=fixture_rows(), reader=reader)
    assert len(calls) == 2
    assert any('facts.0.cells: too_short' in error for error in calls[1])
    assert report['status'] == 'verified'


def test_repeated_invalid_structured_answers_remain_incomplete():
    def reader(*args):
        return ma.MacroReading.model_validate({
            'facts': [{'field': 'ce06_servizi', 'cells': []}],
            'absent': [], 'unresolved': [],
        })
    with pytest.raises(ma.MacroAnalysisError) as exc:
        ma.analyze_pdf_macros('unused', rows=fixture_rows(), reader=reader)
    assert len(exc.value.report['passes']) == 2
    assert exc.value.report['status'] == 'incomplete'


def test_false_absence_cannot_pass_production_cost_crossfoot():
    rows = fixture_rows()
    def reader(batch, periods, feedback):
        result = fixture_reader(batch, periods)
        result.facts = [f for f in result.facts if f.field != 'ce06_servizi']
        result.absent[0].fields.append('ce06_servizi')
        return result
    with pytest.raises(ma.MacroAnalysisError) as exc:
        ma.analyze_pdf_macros('unused', rows=rows, reader=reader)
    assert len(exc.value.report['passes']) == 2
    assert any(e.startswith('costs:') for e in exc.value.report['errors'])


def test_documented_zero_differs_from_not_reported():
    rows = fixture_rows() + [SourceRow('sp05_rimanenze', 1, 'T', 'Rimanenze', (D('0.00'),))]
    *_, report = ma.analyze_pdf_macros('unused', rows=rows, reader=fixture_reader)
    assert report['inventory']['sp05_rimanenze']['status'] == 'observed_zero'
    assert report['inventory']['sp02_immob_immateriali']['status'] == 'not_reported'


def test_same_cell_cannot_be_spent_twice_by_sibling_macros():
    rows = fixture_rows()
    reading = fixture_reader(rows, ['current'])
    reading.facts.append(ma.MacroFact(field='ce05_materie_prime', cells=[
        ma.MacroCell(row='ce06_servizi', column=0)]))
    _, _, report = ma.reduce_macros(rows, [({r.id for r in rows}, reading)])
    assert any('shared by macro siblings' in e for e in report['errors'])


def test_repeated_total_is_an_alternative_not_an_additive_amount():
    rows = fixture_rows()
    reading = fixture_reader(rows, ['current'])
    reading.facts.append(reading.facts[0].model_copy(deep=True))
    bs, _, report = ma.reduce_macros(rows, [({r.id for r in rows}, reading)])
    assert report['status'] == 'verified' and bs['sp09_disponibilita_liquide'] == 100


def test_conflicting_totals_never_choose_one_silently():
    rows = fixture_rows() + [SourceRow('conflict', 1, 'T', 'Cassa', (D('101.00'),))]
    reading = fixture_reader(rows, ['current'])
    reading.facts.append(ma.MacroFact(field='sp09_disponibilita_liquide', cells=[
        ma.MacroCell(row='conflict', column=0)]))
    _, _, report = ma.reduce_macros(rows, [({r.id for r in rows}, reading)])
    assert 'conflicting totals: sp09_disponibilita_liquide' in report['errors']


def test_unresolved_comparative_does_not_invalidate_current():
    rows = fixture_rows()
    def reader(batch, *args):
        reading = fixture_reader(batch, ['current'])
        reading.unresolved.append(ma.MacroUnresolved(period='prior', field='ce20_imposte', reason='illeggibile'))
        return reading
    *_, report = ma.analyze_pdf_macros('unused', rows=rows, reader=reader, include_prior=True)
    assert report['status'] == 'verified' and report['prior']['status'] == 'incomplete'


@pytest.mark.parametrize('role', ['prior', 'difference', 'percentage', 'identifier', 'opening'])
def test_wrong_column_is_never_spendable(role):
    rows = fixture_rows()
    rows[0] = replace(rows[0], kinds=(role,))
    with pytest.raises(ma.MacroAnalysisError, match='wrong source role'):
        ma.analyze_pdf_macros('unused', rows=rows, reader=fixture_reader, max_passes=1)


@pytest.mark.parametrize('section', ['notes', 'unassigned', 'ce'])
def test_notes_unassigned_and_wrong_statement_do_not_supply_sp_macros(section):
    rows = fixture_rows()
    rows[0] = replace(rows[0], statement=section)
    with pytest.raises(ma.MacroAnalysisError, match='wrong source role'):
        ma.analyze_pdf_macros('unused', rows=rows, reader=fixture_reader, max_passes=1)


def test_credit_error_stops_immediately_and_is_not_exposed_verbatim():
    calls = []
    def reader(*args):
        calls.append(1)
        raise RuntimeError('Your credit balance is too low; secret request body')
    with pytest.raises(ma.MacroAnalysisError, match='credito API insufficiente') as exc:
        ma.analyze_pdf_macros('unused', rows=fixture_rows(), reader=reader, max_chars=900)
    assert len(calls) == 1 and 'secret' not in str(exc.value)


@pytest.mark.parametrize('truncated', [False, True])
def test_provider_contract_has_no_sdk_retries_and_excludes_context_citations(monkeypatch, truncated):
    import anthropic
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'offline-only')
    primary = fixture_rows()[0]
    context = replace(primary, id='context:header', amounts=())
    def create(**kwargs):
        schema = kwargs['tools'][0]['input_schema']
        assert schema['$defs']['MacroCell']['properties']['row']['enum'] == [primary.id]
        assert schema['$defs']['MacroFact']['properties']['field']['enum'] == list(ma.FIELDS)
        assert 'statement=bs' in kwargs['messages'][0]['content']
        return SimpleNamespace(stop_reason='max_tokens' if truncated else 'tool_use', content=[
            SimpleNamespace(type='tool_use', name='macros', input=fixture_reader([primary], ['current']).model_dump())])
    def client(**kwargs):
        assert kwargs['max_retries'] == 0 and kwargs['timeout'] == 60
        return nullcontext(SimpleNamespace(messages=SimpleNamespace(create=create)))
    monkeypatch.setattr(anthropic, 'Anthropic', client)
    if truncated:
        with pytest.raises(RuntimeError, match='macro_response_truncated'):
            ma.read_macros([context, primary], ['current'])
    else:
        assert ma.read_macros([context, primary], ['current']).facts[0].field == primary.id


def test_time_budget_never_looks_like_a_complete_read():
    with pytest.raises(ma.MacroAnalysisError, match='time_budget_exhausted'):
        ma.analyze_pdf_macros('unused', rows=fixture_rows(), reader=fixture_reader, max_seconds=0)


def test_textless_page_requires_ocr_instead_of_being_silently_omitted(tmp_path):
    path = tmp_path / 'mixed.pdf'
    with fitz.open() as doc:
        doc.new_page().insert_text((40, 50), 'Stato patrimoniale')
        doc.new_page()
        doc.save(path)
    with pytest.raises(ma.MacroAnalysisError, match='OCR/vision necessario sulle pagine: 2'):
        ma.analyze_pdf_macros(path)


SAP = Path(__file__).resolve().parents[1] / 'inbox/check-budget1/budget_524_Test maggio 2026.pdf'


def sap_reader(rows, periods, feedback=()):
    # Independent transcription of LABELS/signs only. Amounts come exclusively
    # from the real PDF cells; this is a fixture, NOT a production SAP parser.
    specs = {
        '17 TOT IMMOBILIZZAZIONI IMMATERIALI': ('sp02_immob_immateriali', 1),
        '18 TOT IMMOBILIZZAZIONI MATERIALI': ('sp03_immob_materiali', 1),
        '19 TOT IMMOBILIZZAZIONI FINANZIARIE': ('sp04_immob_finanziarie', 1),
        '36 TOT RIMANENZE': ('sp05_rimanenze', 1),
        '37 TOT CREDITI': ('totale_crediti', 1),
        '39 TOT DISPONIBILITA': ('sp09_disponibilita_liquide', 1),
        '11 TOT RATEI': ('sp10_ratei_risconti_attivi', 1),
        '7 TOT ATTIVO': ('totale_attivo', 1),
        '69 TOT CAPITALE': ('sp11_capitale', -1),
        "4 PERDITA DELL'ESERCIZIO": ('sp13_utile_perdita', -1),
        '12 TOT PATRIMONIO NETTO': ('totale_patrimonio_netto', -1),
        '13 TOT FONDI': ('sp14_fondi_rischi', -1),
        '14 TOT TRATTAMENTO': ('sp15_tfr', -1),
        '15 TOT DEBITI': ('totale_debiti', -1),
        '16 TOT RATEI': ('sp18_ratei_risconti_passivi', -1),
        '6 TOT PASSIVO': ('totale_passivo', -1),
        '101 TOT RICAVI': ('ce01_ricavi_vendite', -1),
        '102 TOT VARIAZIONI': ('ce02_variazioni_rimanenze', -1),
        '105 TOT ALTRI RICAVI': ('ce04_altri_ricavi', -1),
        '96 TOT VALORE': ('valore_produzione', -1),
        '106 TOT PER MATERIE': ('ce05_materie_prime', 1),
        '107 TOT PER SERVIZI': ('ce06_servizi', 1),
        '108 TOT PER GODIMENTO': ('ce07_godimento_beni', 1),
        '109 TOT PER IL PERSONALE': ('ce08_costi_personale', 1),
        '115 TOT AMMORTORTAMENTI': ('ce09_ammortamenti', 1),
        '130 TOT VARIAZIONE': ('ce10_var_rimanenze_mat_prime', 1),
        '133 TOT ONERI DIVERSI': ('ce12_oneri_diversi', 1),
        '97 TOT COSTI DELLA': ('costi_produzione', 1),
        '135 TOT ALTRI PROVENTI': ('ce14_altri_proventi_finanziari', -1),
        '136 TOT INTERESSI': ('ce15_oneri_finanziari', 1),
        '146 TOT UTILI E PERDITE': ('ce16_utili_perdite_cambi', -1),
        '3 TOT UTILE (PERDITE)': ('risultato_ce', 1),
    }
    facts = []
    for row in rows:
        if row.id.startswith('context:'):
            continue
        spec = next((v for k, v in specs.items() if row.text.startswith(k)), None)
        if 'CRED. IMPOSTE ANTIC. OLTRE 12 M' in row.text:
            spec = ('crediti_lungo', 1)
        if spec:
            for period in periods:
                cells = [i for i, kind in enumerate(row.kinds) if kind == period]
                if cells:
                    assert len(cells) == 1
                    facts.append(ma.MacroFact(field=spec[0], period=period,
                        cells=[ma.MacroCell(row=row.id, column=cells[0], sign=spec[1])]))
    return ma.MacroReading(facts=facts, absent=[ma.MacroAbsence(period=p,
        fields=sorted(set(ma.FIELDS) - {f.field for f in facts if f.period == p}))
        for p in periods], unresolved=[])


@pytest.mark.skipif(not SAP.exists(), reason='private PDF unavailable')
def test_524_all_twenty_pages_and_source_amounts_reconcile_with_offline_reader():
    bs, ce, _, _, report = ma.analyze_pdf_macros(SAP, reader=sap_reader)
    assert report['pages_read'] == list(range(1, 21))
    assert report['rows_completed'] == report['rows_total'] == 1128
    assert bs['sp02_immob_immateriali'] == D('615829.08')
    assert bs['sp05_rimanenze'] == D('-230106.59')
    assert bs['sp06_crediti_breve'] == D('20817262.93')
    assert bs['sp07_crediti_lungo'] == D('184391.00')
    assert bs['sp12_riserve'] == D('31028339.94')
    assert bs['totale_attivo'] == bs['totale_passivo'] == D('55117048.16')
    assert ce['ce09_ammortamenti'] == D('977681.20')
    assert ce['ce10_var_rimanenze_mat_prime'] == D('6036705.98')
    assert ma.calculate_ce_result(ce).net_profit == bs['sp13_utile_perdita'] == D('-7674851.79')
    assert report['status'] == 'verified'


@pytest.mark.skipif(not SAP.exists(), reason='private PDF unavailable')
def test_524_prior_source_error_is_not_a_reason_to_retry_or_corrupt_current():
    *_, prior_bs, prior_ce, report = ma.analyze_pdf_macros(SAP, reader=sap_reader, include_prior=True)
    assert prior_bs is prior_ce is None
    assert report['status'] == 'verified' and len(report['passes']) == 1
    assert report['prior']['status'] == 'incomplete'
    assert any('ce_sp:' in e for e in report['prior']['errors'])


@pytest.mark.skipif(not SAP.exists(), reason='private PDF unavailable')
def test_sap_identifier_92_is_not_a_money_cell():
    row = next(r for r in collect_source_rows(SAP) if r.text.startswith('92 TOT DEBITI VS'))
    assert D(92) not in row.amounts
    assert row.amounts[0] == D('-752474.43')
    assert row.kinds == ('current', 'prior', 'difference', 'percentage')


@pytest.fixture
def memory_import(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from database.models import Base
    from importers import pdf_importer
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    monkeypatch.setattr(pdf_importer, 'SessionLocal', sessions)
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'test-not-used')
    monkeypatch.setenv('PDF_DETAIL_ENRICHMENT', '0')
    yield pdf_importer, sessions
    engine.dispose()


@pytest.mark.skipif(not SAP.exists(), reason='private PDF unavailable')
def test_524_offline_macro_reader_through_real_import_and_persistence(memory_import, monkeypatch):
    from database.models import FinancialYear
    importer, sessions = memory_import
    monkeypatch.setattr(ma, 'read_macros', sap_reader)
    result = importer.import_pdf_balance_sheet(str(SAP), fiscal_year=2026,
        period_months=5, company_name='Offline macro 524')
    assert result['success'] and not result['prior_year_imported']
    with sessions() as db:
        year = db.query(FinancialYear).one()
        report = json.loads(year.validation_report)
        assert report['macro_analysis']['status'] == 'verified'
        assert report['macro_analysis']['pages_read'] == list(range(1, 21))
        assert year.period_months == 5
        assert year.balance_sheet.sp02_immob_immateriali == D('615829.08')
        assert year.balance_sheet.sp13_utile_perdita == D('-7674851.79')
        assert year.income_statement.ce09_ammortamenti == D('977681.20')
        assert year.income_statement.net_profit == D('-7674851.79')
        assert year.balance_sheet.total_assets == D('55117048.16')
        assert not year.forecastable  # Unassigned source stock is still a real source warning.
        assert any('CONTI NON ASSEGNATI' in w for w in report['warnings'])
        # Historical coverage survives a no-op manual correction.
        monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'backend'))
        from app.api.v1 import financial_years as endpoint
        from app.schemas.adjustments import AdjustmentsUpdate
        monkeypatch.setattr(endpoint, 'validate_company_owned_by_user', lambda *a: None)
        endpoint.save_adjustments(company_id=result['company_id'], year=2026, period_months=5,
            payload=AdjustmentsUpdate(balance_sheet={}, income_statement={}), user_id='test', db=db)
        db.refresh(year)
        assert json.loads(year.validation_report)['macro_analysis'] == report['macro_analysis']


@pytest.mark.skipif(not SAP.exists(), reason='private PDF unavailable')
def test_incomplete_macro_analysis_uses_fallback_and_persists(memory_import, monkeypatch):
    from database.models import FinancialYear
    from importers import pdf_extractor_llm as llm
    importer, sessions = memory_import
    bs, ce, *_ = ma.analyze_pdf_macros(SAP, reader=sap_reader)
    def incomplete(rows, periods, feedback):
        reading = sap_reader(rows, periods, feedback)
        reading.facts = [f for f in reading.facts if f.field != 'ce09_ammortamenti']
        return reading
    monkeypatch.setattr(ma, 'read_macros', incomplete)
    monkeypatch.setattr(llm, 'extract_pdf_with_llm', lambda *a, **kw: (dict(bs), dict(ce)))
    monkeypatch.setattr(llm, 'extract_pdf_both_years_with_llm',
                        lambda *a, **kw: (dict(bs), dict(ce), None, None))
    result = importer.import_pdf_balance_sheet(str(SAP), fiscal_year=2026,
        period_months=5, company_name='Incomplete macros with fallback')
    assert result['success']
    with sessions() as db:
        year = db.query(FinancialYear).one()
        report = json.loads(year.validation_report)
        assert report['macro_analysis']['status'] == 'incomplete'
        assert report['macro_analysis']['fallback_used']
        assert year.income_statement.ce09_ammortamenti == D('977681.20')
