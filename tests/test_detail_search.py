"""Long source coverage, partial failures, and honest no-detail outcomes."""
from decimal import Decimal as D
from dataclasses import replace
from pathlib import Path
import json
import threading
from types import SimpleNamespace

import fitz
import pytest

from importers import detail_enrichment as de, detail_search as ds
from tests.test_residual_finalization import import_fixture  # noqa: F401

INV = 'sp05_rimanenze'
RAW = 'sp05a_materie_prime'
GOODS = 'sp05d_prodotti_finiti'
CREDIT = 'sp06_crediti_breve'


def row(i, *, text=None, value='10', page=None, code=''):
    return de.SourceRow(f'r{i}', page or i + 1, 'T', text or ('Riga descrittiva ' + 'x' * 120),
                        (D(value),) if value is not None else (), code)


def reading_for(r, field=GOODS, column=0, period='current', aggregate=INV):
    return de.DetailReading(proposals=[de.DetailProposal(period=period, aggregate=aggregate, items=[
        de.DetailCell(field=field, row=r.id, column=column)])])


def test_chunk_plan_covers_every_row_once_and_never_truncates_notes():
    rows = [row(i) for i in range(60)]
    rows[-1] = row(59, text='Nota integrativa Rimanenze prodotti finiti 10,00')
    chunks = ds.plan_chunks(rows, max_chars=1200)
    assert len(chunks) > 1
    assert [r for chunk in chunks for r in chunk.primary] == rows
    for chunk in chunks:
        assert not chunk.error
        assert len('\n'.join(de.source_line(r) for r in chunk.context + chunk.primary)) <= 1200
        assert all(not r.amounts and r.id.startswith('context:') for r in chunk.context)
    assert rows[-1] in chunks[-1].primary


def test_headers_and_ancestors_survive_boundaries_as_non_spendable_context():
    rows = [row(0, text='CORRENTE 31/12/2025 PRECEDENTE 31/12/2024', value=None),
            row(1, text='DEBITI', code='31'), *[row(i) for i in range(2, 30)],
            row(30, text='Soci finanziamento', code='31.01')]
    chunks = ds.plan_chunks(rows, max_chars=1500)
    tail = chunks[-1]
    assert any('CORRENTE' in r.text for r in tail.context)
    assert any('DEBITI' in r.text for r in tail.context)
    assert all(not r.amounts for r in tail.context)


def test_long_document_above_old_limit_reaches_last_note(monkeypatch):
    rows = [row(i, text='Informazioni narrative ' + 'testo ' * 300) for i in range(100)]
    rows.append(row(100, text='NOTA INTEGRATIVA prodotti finiti', value='70'))
    assert sum(len(de.source_line(r)) for r in rows) > de.MAX_SOURCE_CHARS
    seen = set()
    lock = threading.Lock()
    def reader(batch, *args):
        with lock:
            seen.update(r.id for r in batch if not r.id.startswith('context:'))
        target = next((r for r in batch if r.id == 'r100'), None)
        return reading_for(target) if target else de.DetailReading()
    reading, audit = ds.search_details(rows, {'current': {INV: D(100)}}, 2025, reader=reader)
    assert seen == {r.id for r in rows}
    assert audit['status'] == 'complete' and audit['rows_completed'] == len(rows)
    bs, _ = de.apply_details({INV: D(100)}, reading.proposals, rows)
    assert bs[GOODS] == 70 and bs[RAW] == 30


def test_one_failed_chunk_preserves_other_proposals_and_reports_uncovered_rows():
    rows = [row(i) for i in range(20)]
    chunks = ds.plan_chunks(rows, max_chars=1000)
    failed = {r.id for r in chunks[1].primary}
    def reader(batch, *args):
        owned = [r for r in batch if not r.id.startswith('context:')]
        if any(r.id in failed for r in owned):
            raise TimeoutError('secret-must-not-be-persisted')
        return reading_for(owned[0])
    reading, audit = ds.search_details(rows, {'current': {INV: D(100)}}, 2025, reader=reader, max_chars=1000)
    assert audit['status'] == 'partial' and audit['rows_completed'] == len(rows) - len(failed)
    assert audit['chunks'][1]['reason'] == 'TimeoutError'
    assert 'secret-must-not-be-persisted' not in json.dumps(audit)
    assert reading.proposals and not any(c.row in failed for p in reading.proposals for c in p.items)


def test_fragments_of_same_family_merge_once_before_reduction_for_both_years(monkeypatch):
    rows = [replace(row(i), amounts=(D(1), D(2))) for i in range(20)]
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'test')
    monkeypatch.setattr(ds, 'CHUNK_CHARS', 1000)
    monkeypatch.setattr(de, 'collect_source_rows', lambda *a, **kw: rows)
    def reader(batch, *args):
        owned = [r for r in batch if not r.id.startswith('context:')]
        return de.DetailReading(proposals=[de.DetailProposal(period=period, aggregate=INV, items=[
            de.DetailCell(field=GOODS, row=r.id, column=column) for r in owned])
            for period, column in [('current', 0), ('prior', 1)]])
    monkeypatch.setattr(de, 'read_details', reader)
    current, prior, report = de.enrich_pdf_details('unused', {INV: D(100)}, {INV: D(100)})
    assert current[GOODS] == 20 and current[RAW] == 80
    assert prior[GOODS] == 40 and prior[RAW] == 60
    assert report['search']['chunks_planned'] > 1
    assert report['periods']['current']['search_families'][INV]['outcome'] == 'details_accepted'


def test_context_and_foreign_chunk_cells_cannot_be_spent_again():
    rows = [row(i) for i in range(20)]
    def reader(batch, *args):
        # Every chunk attempts to spend the first row, even when not owned.
        return reading_for(rows[0])
    reading, audit = ds.search_details(rows, {'current': {INV: D(100)}}, 2025, reader=reader, max_chars=1000)
    assert sum(len(p.items) for p in reading.proposals) == 1
    assert audit['status'] == 'partial'
    assert sum(a.get('invalid_references', 0) for a in audit['chunks']) == len(audit['chunks']) - 1


def test_duplicate_proposals_are_deduplicated_and_parent_child_overlap_stays_rejected():
    rows = [row(0, code='10', value='70'), row(1, code='10.01', value='70')]
    def reader(batch, *args):
        return de.DetailReading(proposals=reading_for(rows[0]).proposals * 2 + reading_for(rows[1]).proposals)
    reading, _ = ds.search_details(rows, {'current': {INV: D(100)}}, 2025, reader=reader)
    assert sum(len(p.items) for p in reading.proposals) == 2
    bs, audit = de.apply_details({INV: D(100)}, reading.proposals, rows)
    assert bs[GOODS] == 70 and bs[RAW] == 30 and audit['rejected']


def test_oversized_single_row_does_not_discard_later_note():
    rows = [row(0, text='x' * 3000), row(1, text='Nota integrativa merci 70', value='70')]
    reading, audit = ds.search_details(rows, {'current': {INV: D(100)}}, 2025,
                                       reader=lambda batch, *a: reading_for(rows[1]), max_chars=1000)
    assert audit['status'] == 'partial' and audit['chunks'][0]['reason'] == 'source_row_too_large'
    assert reading.proposals[0].items[0].row == 'r1'


def test_deadline_reports_every_unattempted_chunk_without_network(monkeypatch):
    ticks = iter([0, *([10] * 100)])
    monkeypatch.setattr(ds.time, 'monotonic', lambda: next(ticks))
    _, audit = ds.search_details([row(i) for i in range(20)], {'current': {INV: D(100)}}, 2025,
                                 reader=lambda *a: pytest.fail('expired deadline called reader'), max_chars=1000, max_seconds=1)
    assert audit['status'] == 'not_searched'
    assert all(a['reason'] == 'time_budget_exhausted' for a in audit['chunks'])
    assert sum(a['rows'] for a in audit['chunks']) == 20


@pytest.mark.parametrize('mode,coverage,outcome', [
    ('empty', 'complete', 'no_details_found'), ('timeout', 'not_searched', 'unknown'),
    ('disabled', 'not_searched', 'unknown'), ('no_key', 'not_searched', 'unknown'),
    ('no_cells', 'not_searched', 'unknown'), ('rejected', 'complete', 'proposals_not_accepted'),
])
def test_family_outcomes_distinguish_not_found_from_not_searched(monkeypatch, mode, coverage, outcome):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'test')
    monkeypatch.setattr(de, 'collect_source_rows', lambda *a, **kw: [] if mode == 'no_cells' else [row(0, value='200')])
    if mode == 'disabled':
        monkeypatch.setenv('PDF_DETAIL_ENRICHMENT', '0')
    if mode == 'no_key':
        monkeypatch.delenv('ANTHROPIC_API_KEY')
    def reader(*args):
        if mode == 'timeout':
            raise TimeoutError()
        return reading_for(row(0)) if mode == 'rejected' else de.DetailReading()
    monkeypatch.setattr(de, 'read_details', reader)
    _, _, report = de.enrich_pdf_details('unused', {INV: D(100)})
    family = report['periods']['current']['search_families'][INV]
    assert family['status'] == coverage and family['outcome'] == outcome
    assert bool(report['warnings']) is (mode != 'empty')


def test_blank_scan_page_does_not_count_as_searched_when_other_pages_have_text(monkeypatch, tmp_path):
    path = tmp_path / 'mixed.pdf'
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((40, 40), 'Rimanenze 100,00')
        doc.new_page()
        doc.save(path)
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'test')
    monkeypatch.setattr(de, 'read_details', lambda *a: de.DetailReading())
    _, _, report = de.enrich_pdf_details(path, {INV: D(100)})
    assert report['search']['status'] == 'partial' and report['search']['unreadable_pages'] == [2]
    assert report['periods']['current']['search_families'][INV]['outcome'] == 'unknown'
    assert report['warnings']


def test_truncated_response_is_explicit_and_never_called_complete(monkeypatch):
    import anthropic
    monkeypatch.setattr(anthropic, 'Anthropic', lambda **kw: SimpleNamespace(messages=SimpleNamespace(
        create=lambda **kw: SimpleNamespace(stop_reason='max_tokens', content=[]))))
    _, report = ds.search_details([row(0)], {'current': {INV: D(100)}}, 2025)
    assert report['status'] == 'not_searched' and report['chunks'][0]['reason'] == 'output_truncated'


def test_local_note_details_survive_when_every_llm_chunk_fails(monkeypatch):
    note = replace(row(0, text='Prodotti finiti e merci', value='70'), kinds=('closing',))
    monkeypatch.setattr(de, 'collect_source_rows', lambda *a, **kw: [note])
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'test')
    def fail(*args):
        raise TimeoutError()
    monkeypatch.setattr(de, 'read_details', fail)
    bs, _, report = de.enrich_pdf_details('unused', {INV: D(100)})
    assert bs[GOODS] == 70 and bs[RAW] == 30
    assert report['search']['status'] == 'not_searched'
    assert report['periods']['current']['search_families'][INV]['outcome'] == 'details_accepted'
    assert report['warnings']


def test_no_active_family_needs_no_search_or_warning(monkeypatch):
    monkeypatch.setattr(de, 'collect_source_rows', lambda *a, **kw: pytest.fail('unnecessary read'))
    bs, prior, report = de.enrich_pdf_details('unused', {INV: D(0)})
    assert bs == {INV: D(0)} and prior is None
    assert report['search']['status'] == 'not_applicable' and report['warnings'] == []


def test_reader_schema_excludes_context_from_citable_cells(monkeypatch):
    import anthropic
    primary = row(0)
    context = replace(row(1), id='context:r1', amounts=())
    def create(**kwargs):
        schema = kwargs['tools'][0]['input_schema']
        assert schema['$defs']['DetailCell']['properties']['row']['enum'] == ['r0']
        assert schema['$defs']['DetailProposal']['properties']['aggregate']['enum'] == [INV]
        return SimpleNamespace(stop_reason='tool_use', content=[SimpleNamespace(
            type='tool_use', name='dettagli_documentati', input={'proposals': []})])
    monkeypatch.setattr(anthropic, 'Anthropic', lambda **kw: SimpleNamespace(messages=SimpleNamespace(create=create)))
    assert de.read_details([context, primary], {'current': {INV: D(100)}}, 2025).proposals == []


@pytest.mark.parametrize('complete', [True, False])
def test_note_representation_is_not_added_twice_but_partial_note_stays_open(monkeypatch, complete):
    note = replace(row(0, text='Prodotti finiti e merci', value='100' if complete else '30'), kinds=('closing',))
    alternative = row(1, text='Prodotti finiti e merci nel prospetto', value='100' if complete else '20')
    rows = [note, *[row(i, value=None) for i in range(2, 20)], alternative]
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'test')
    monkeypatch.setattr(ds, 'CHUNK_CHARS', 1000)
    monkeypatch.setattr(de, 'collect_source_rows', lambda *a, **kw: rows)
    monkeypatch.setattr(de, 'read_details', lambda batch, *a: reading_for(alternative)
                        if any(r.id == alternative.id for r in batch) else de.DetailReading())
    bs, _, report = de.enrich_pdf_details('unused', {INV: D(100)})
    assert bs[GOODS] == (100 if complete else 50)
    assert bs[RAW] == (0 if complete else 50)
    audit = report['periods']['current']
    assert audit['reconciled_note_families'] == ([INV] if complete else [])
    assert any('rappresentazione alternativa' in r['reason'] for r in audit['rejected']) is complete


def test_formetal_complete_notes_survive_repeated_statement_values(monkeypatch):
    path = Path(__file__).resolve().parents[1] / 'inbox/import-test/FORMETAL_701_Bilancio xbrl 31-12-2025.pdf'
    if not path.exists():
        pytest.skip('private source PDF absent')
    original = de.collect_source_rows(path)
    repeated = replace(row(10000, text='Imposte anticipate', value='5042'), page=1)
    monkeypatch.setattr(de, 'collect_source_rows', lambda *a, **kw: [repeated, *original])
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'test')
    monkeypatch.setattr(de, 'read_details', lambda batch, *a: reading_for(
        repeated, field='sp06f_imposte_anticipate_breve', aggregate=CREDIT)
        if any(r.id == repeated.id for r in batch) else de.DetailReading())
    initial = {INV: D(79135), CREDIT: D(579879), 'sp07_crediti_lungo': D(95428),
               'sp16_debiti_breve': D(1255656), 'sp17_debiti_lungo': D(459080)}
    bs, _, report = de.enrich_pdf_details(str(path), initial)
    assert all(bs[k] == v for k, v in initial.items())
    assert bs['sp06a_crediti_clienti_breve'] == 455145
    assert bs['sp06e_crediti_tributari_breve'] == 97048
    assert bs['sp06f_imposte_anticipate_breve'] == 5042
    assert bs['sp06g_crediti_altri_breve'] == 22644
    assert bs['sp16a_debiti_banche_breve'] == 710247
    assert bs['sp17a_debiti_banche_lungo'] == 459080
    assert report['search']['status'] == 'complete'


def test_failed_search_warnings_and_coverage_persist_through_import_and_adjustments(import_fixture, monkeypatch):
    from database.models import FinancialYear
    importer, sessions, path, current, prior = import_fixture
    def fail(*args):
        raise TimeoutError()
    monkeypatch.setattr(de, 'read_details', fail)
    result = importer.import_pdf_balance_sheet(str(path), fiscal_year=2025, company_name='Search coverage')
    assert result['success'] and any('RICERCA DETTAGLI NON COMPLETA' in w for w in result['warnings'])
    with sessions() as db:
        years = db.query(FinancialYear).order_by(FinancialYear.year.desc()).all()
        for fy in years:
            audit = json.loads(fy.validation_report)
            assert audit['detail_enrichment']['search']['status'] == 'not_searched'
            assert audit['detail_enrichment']['search_families'][INV]['outcome'] == 'unknown'
            assert any('RICERCA DETTAGLI NON COMPLETA' in w for w in audit['warnings'])
            # Mandatory residual closure is unaffected by search availability.
            assert fy.balance_sheet.sp05a_materie_prime == fy.balance_sheet.sp05_rimanenze
        monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'backend'))
        from app.api.v1 import financial_years as endpoint
        from app.schemas.adjustments import AdjustmentsUpdate
        monkeypatch.setattr(endpoint, 'validate_company_owned_by_user', lambda *a: None)
        endpoint.save_adjustments(company_id=result['company_id'], year=2025, period_months=None,
                                  payload=AdjustmentsUpdate(balance_sheet={}, income_statement={}), user_id='test', db=db)
        db.refresh(years[0])
        audit = json.loads(years[0].validation_report)
        assert audit['detail_enrichment']['search']['status'] == 'not_searched'
        assert any('RICERCA DETTAGLI NON COMPLETA' in w for w in audit['warnings'])
