"""Full measured dossier: exact inventory, real reflow and per-page note capacity."""
from dataclasses import asdict, replace
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path

import fitz
import pytest

from app.renderers.typst import Compiler, RendererCompileError, RendererInputError, RendererLimits, RendererUnavailable
from app.renderers.typst.editorial_inventory import build_inventory, expected_content_inventory
from app.renderers.typst.editorial_plan import (
    DossierLayoutProbe, DossierTemplateBundle, build_editorial_plan,
    prepare_editorial_report, verify_editorial_layout,
)
from app.schemas.final_report_v2 import EditorialNote, FinalReportModelV2
from tests.test_final_report_v2 import fixture_report

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'backend/app/renderers/typst/templates/dossier-base'


def infrannual_period_report():
    """Synthetic distinct source bases assembled by the existing canonical service."""
    from app.schemas.final_report import FinalReportModel
    from app.schemas.final_report_v2 import StatementPeriod
    from app.services.final_report_dossier import DossierSource, extend_dossier
    from database.models import BalanceSheet, IncomeStatement
    v1 = FinalReportModel.model_validate_json((ROOT / 'tests/fixtures/final_report/infrannuale.json').read_bytes())
    bs = {column.name: Decimal(0) for column in BalanceSheet.__table__.columns if column.name.startswith('sp')}
    ce = {column.name: Decimal(0) for column in IncomeStatement.__table__.columns if column.name.startswith('ce')}
    sources = []
    for basis, year, months, amount in [('historical', 2025, 12, '850'), ('observed', 2026, 9, '900'),
                                       ('adjusted', 2026, 9, '1020'), ('closing', 2026, 12, '1200')]:
        period = StatementPeriod(id=f'{basis}:{year}', year=year, label=f'{year} · {basis}', basis=basis,
                                 period_months=months, source='synthetic_period_fixture')
        sources.append(DossierSource(period, {**bs, 'sp09_disponibilita_liquide': Decimal(80)},
                                     {**ce, 'ce01_ricavi_vendite': Decimal(amount)}))
    for forecast in v1.forecast.years:
        revenue = next(line.value for line in forecast.income_statement if line.code == 'revenue')
        cash = next(line.value for line in forecast.balance_sheet if line.code == 'cash')
        sources.append(DossierSource(StatementPeriod(id=f'forecast:{forecast.year}', year=forecast.year,
            label=str(forecast.year), basis='forecast', period_months=12, source='synthetic_period_fixture'),
            {**bs, 'sp09_disponibilita_liquide': cash}, {**ce, 'ce01_ricavi_vendite': revenue}))
    return extend_dossier(v1, sources)


@pytest.fixture
def probe(tmp_path):
    binary = Path(os.environ.get('TYPST_TEST_BINARY', ROOT / 'tools/typst/bin/typst'))
    if not binary.is_file():
        pytest.skip('Install pinned compiler for real editorial layout tests')
    return DossierLayoutProbe(Compiler.from_manifest(ROOT / 'tools/typst/manifest.json', binary),
                              DossierTemplateBundle(BASE), temp_root=tmp_path)


def signed(report):
    report.source_hash = report.calculate_source_hash()
    report.model_hash = report.calculate_model_hash()
    return FinalReportModelV2.model_validate_json(report.model_dump_json())


def with_notes(report, text='Commento breve di lettura.', provenance='automatic'):
    report = report.model_copy(deep=True)
    report.editorial_notes = [EditorialNote(id=page.note_id, content_ids=page.content_ids,
        text=text + f' Pagina {index + 1}.', provenance=provenance, updated_at=report.generated_at,
        source_hash=report.source_hash, plan_hash=report.editorial_plan.plan_hash,
        revision=1, freshness='fresh') for index, page in enumerate(report.editorial_plan.pages)]
    report.editorial_readiness.status = 'ready'
    report.editorial_readiness.reasons = []
    return signed(report)


@pytest.mark.parametrize('workflow', ['infrannuale', 'bilancio', 'startup'])
@pytest.mark.parametrize('years', [[2027], [2027, 2028, 2029], list(range(2027, 2032))])
def test_full_real_composition_has_exact_rows_indicators_charts_and_slots(probe, workflow, years, tmp_path):
    original = fixture_report(workflow, years)
    before = original.model_dump_json()
    report = prepare_editorial_report(original, probe)
    assert original.model_dump_json() == before
    assert report.source_hash == original.source_hash
    assert report.editorial_readiness.status == 'pending' and not report.editorial_notes
    measurement = verify_editorial_layout(report, probe)
    plan = report.editorial_plan
    assert plan.plan_hash == plan.calculate_plan_hash()
    assert len(plan.pages) == measurement.page_count
    contents = [content for page in plan.pages for content in page.content_ids]
    assert contents == list(expected_content_inventory(original))
    assert len(set(contents)) == len(contents)
    rows = [(part.statement_id, row) for page in plan.pages for part in page.table_parts for row in part.row_ids]
    assert rows == [(s.id, r.id) for s in report.detailed_statements for r in s.rows]
    assert all(page.note_slot.max_lines == 4 and page.note_slot.font_size_pt == 9 for page in plan.pages)
    assert len({page.note_id for page in plan.pages}) == len(plan.pages)
    assert ('infrannual_closing' in {page.section_id for page in plan.pages}) == (workflow == 'infrannuale')
    artifact = probe.render(report)
    with fitz.open(stream=artifact.data, filetype='pdf') as pdf:
        assert pdf.page_count == measurement.page_count
        assert pdf.metadata['title'] == report.document.title
        full_text = ' '.join(' '.join(page.get_text().split()) for page in pdf)
        for statement in report.detailed_statements:
            numbers = [number for number, page in enumerate(plan.pages, 1)
                       if any(part.statement_id == statement.id for part in page.table_parts)]
            expected_reference = f'{statement.title} · pagina {numbers[0]}'
            if numbers[0] != numbers[-1]:
                expected_reference += f'–{numbers[-1]}'
            assert expected_reference in full_text
        for page in pdf:
            assert page.rect.width < page.rect.height
            assert 'BOZZA' in page.get_text() and 'Commento di pagina' in page.get_text()
            assert not page.get_images()
            for block in page.get_text('dict')['blocks']:
                for line in block.get('lines', []):
                    for span in line['spans']:
                        x0, y0, x1, y1 = span['bbox']
                        assert x0 >= -1 and y0 >= -1 and x1 <= page.rect.width + 1 and y1 <= page.rect.height + 1
    assert not list(tmp_path.iterdir())


def test_fitting_notes_do_not_reflow_and_manual_notes_survive_read_only_preparation(probe):
    prepared = prepare_editorial_report(fixture_report(), probe)
    report = with_notes(prepared, provenance='user')
    before = report.model_dump_json()
    measurement = verify_editorial_layout(report, probe)
    refreshed = prepare_editorial_report(report, probe)
    assert refreshed.editorial_plan == report.editorial_plan
    assert refreshed.editorial_notes == report.editorial_notes
    assert report.model_dump_json() == before
    with fitz.open(stream=probe.render(report).data, filetype='pdf') as pdf:
        assert pdf.page_count == measurement.page_count
        for page, note in zip(pdf, report.editorial_notes):
            assert note.text in ' '.join(page.get_text().split())


def test_overlong_notes_and_overlong_narrative_fail_without_truncation(probe):
    prepared = prepare_editorial_report(fixture_report(), probe)
    report = with_notes(prepared, text='Commento molto lungo. ' * 120)
    with pytest.raises(RendererCompileError):
        verify_editorial_layout(report, probe)
    huge = fixture_report()
    huge.narrative[0].text = 'Una narrazione troppo lunga per il blocco. ' * 2000
    with pytest.raises(RendererCompileError):
        prepare_editorial_report(signed(huge), probe)


def test_single_unbreakable_manual_note_cannot_escape_its_width(probe):
    prepared = prepare_editorial_report(fixture_report(), probe)
    report = with_notes(prepared, text='W' * 300, provenance='user')
    with pytest.raises(RendererCompileError):
        verify_editorial_layout(report, probe)
    with pytest.raises(RendererCompileError):
        prepare_editorial_report(report, probe)


@pytest.mark.parametrize('geometry', [178, 178.0])
def test_chart_measurements_reject_numeric_json_geometry(probe, geometry):
    report = fixture_report()
    measured = probe.measure_layout(report)
    charts = {'chart:' + chart.id: chart for chart in report.chart_series}
    values = []
    for record in measured.records:
        value = {key: item for key, item in asdict(record).items() if item is not None}
        if record.content_id in charts:
            chart = charts[record.content_id]
            value.update(kind='chart', width_mm='178', height_mm='94', measured_width_mm='178',
                         measured_height_mm='94', unit=chart.unit, categories=chart.categories,
                         series=chart.model_dump(mode='json')['series'], thresholds=[])
        values.append(value)
    assert probe._validate_records(json.dumps(values).encode(), report) == measured.records
    chart_value = next(value for value in values if value['kind'] == 'chart')
    chart_value['width_mm'] = geometry
    with pytest.raises(RendererCompileError):
        probe._validate_records(json.dumps(values).encode(), report)


def test_actual_infrannual_bases_keep_unannualized_values_and_all_appendix_periods(probe):
    original = infrannual_period_report()
    inventory = build_inventory(original)
    comparison = next(item for section in inventory for item in section['items']
                      if item['id'] == 'comparison:income_statement')
    production = next(row for row in comparison['rows'] if row['id'].endswith(':production_value'))
    assert production['cells'][2:6] == ['850', '900', '1020', '1200']
    assert '2026 · observed (9 mesi)' in comparison['columns']
    assert '2026 · adjusted (9 mesi)' in comparison['columns']
    assert '2026 · closing (12 mesi)' in comparison['columns']
    report = prepare_editorial_report(original, probe)
    verify_editorial_layout(report, probe)
    with fitz.open(stream=probe.render(report).data, filetype='pdf') as pdf:
        text = ' '.join(' '.join(page.get_text().split()) for page in pdf)
        assert 'non annualizza gli importi infrannuali' in text
        assert '900,00' in text and '1.020,00' in text and '1.200,00' in text
    assert all(len(statement.periods) == 7 for statement in report.detailed_statements)


def test_changed_narrative_reflow_invalidates_existing_page_bindings(probe):
    report = prepare_editorial_report(fixture_report(), probe)
    changed = report.model_copy(deep=True)
    # Add enough within-capacity text to move subsequent items across real pages.
    changed.narrative[0].text = 'Il piano richiede una lettura dei valori e delle ipotesi. ' * 65
    changed = signed(changed)
    assert changed.source_hash == report.source_hash
    with pytest.raises((ValueError, RendererCompileError)):
        verify_editorial_layout(changed, probe)


@pytest.mark.parametrize('fault', ['missing', 'duplicate', 'unknown', 'slot', 'blank_page', 'page_count', 'source', 'asset'])
def test_forged_measurements_cannot_freeze_a_complete_editorial_plan(probe, fault):
    report = fixture_report()
    measurement = probe.measure_layout(report)
    records = list(measurement.records)
    if fault == 'missing':
        records.pop(next(i for i, record in enumerate(records) if record.kind == 'content' and record.content_id != 'cover'))
    elif fault == 'duplicate':
        records.append(next(record for record in records if record.kind == 'content'))
    elif fault == 'unknown':
        i = next(i for i, record in enumerate(records) if record.kind == 'content')
        records[i] = replace(records[i], content_id='unknown-content')
    elif fault == 'slot':
        i = next(i for i, record in enumerate(records) if record.kind == 'slot')
        records[i] = replace(records[i], height_pt='100')
    elif fault == 'blank_page':
        records = [record for record in records if not (record.page == 1 and record.kind == 'content')]
    elif fault == 'page_count':
        measurement = replace(measurement, page_count=measurement.page_count + 1)
    elif fault == 'source':
        measurement = replace(measurement, source_hash='f' * 64)
    else:
        measurement = replace(measurement, asset_hash='invalid')
    with pytest.raises(ValueError):
        build_editorial_plan(report, replace(measurement, records=tuple(records)))


def test_asset_revision_changes_plan_hash_and_repreparation_blocks_manual_reassociation(probe):
    report = fixture_report()
    measurement = probe.measure_layout(report)
    original = build_editorial_plan(report, measurement)
    changed = build_editorial_plan(report, replace(measurement, font_hash='f' * 64))
    assert original.plan_hash != changed.plan_hash
    prepared = with_notes(prepare_editorial_report(report, probe), provenance='user')
    prepared.editorial_plan.font_version = 'f' * 64
    prepared.editorial_plan.plan_hash = prepared.editorial_plan.calculate_plan_hash()
    for note in prepared.editorial_notes:
        note.plan_hash = prepared.editorial_plan.plan_hash
    with pytest.raises(ValueError, match='manual notes'):
        prepare_editorial_report(signed(prepared), probe)


def test_inventory_definition_revision_invalidates_plan_even_without_page_changes(probe, tmp_path, monkeypatch):
    import app.renderers.typst.editorial_plan as module
    definition = tmp_path / 'inventory-definition.py'
    definition.write_bytes(module._GENERATOR_PATH.read_bytes())
    monkeypatch.setattr(module, '_GENERATOR_PATH', definition)
    report = fixture_report()
    first = prepare_editorial_report(report, probe)
    definition.write_bytes(definition.read_bytes() + b'\n# Layout definition revision.\n')
    with pytest.raises(RendererUnavailable):
        probe.measure_layout(report)
    # Simulate a restarted worker loading the revised definition; semantics and
    # page geometry remain identical, but layout/asset identity must differ.
    monkeypatch.setattr(module, '_GENERATOR_HASH', hashlib.sha256(definition.read_bytes()).hexdigest())
    second = prepare_editorial_report(report, probe)
    assert [page.content_ids for page in first.editorial_plan.pages] == [page.content_ids for page in second.editorial_plan.pages]
    assert first.editorial_plan.asset_version != second.editorial_plan.asset_version
    assert first.editorial_plan.plan_hash != second.editorial_plan.plan_hash


@pytest.mark.parametrize('limit', ['bytes', 'files'])
def test_derived_inventory_obeys_verified_asset_budget_before_staging(probe, limit, tmp_path):
    report = fixture_report()
    _, _, files = probe.bundle.read(probe.limits)
    if limit == 'bytes':
        probe.limits = RendererLimits(max_asset_bytes=sum(map(len, files.values())) + 1)
    else:
        probe.limits = RendererLimits(max_assets=len(files))
    with pytest.raises(RendererInputError):
        with probe._private_job(report.model_dump_json().encode(), files,
                                probe.compiler.verified_bytes(), b'{"document_state":"draft","grayscale":false}'):
            pytest.fail('oversized derived inventory reached the private job')
    assert not list(tmp_path.iterdir())
