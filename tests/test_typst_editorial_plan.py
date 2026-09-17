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


def infrannual_period_report(amounts=('850', '900', '1020', '1200')):
    """Synthetic distinct source bases assembled by the existing canonical service."""
    from app.schemas.final_report import FinalReportModel
    from app.schemas.final_report_v2 import StatementPeriod
    from app.services.final_report_dossier import DossierSource, extend_dossier
    from database.models import BalanceSheet, IncomeStatement
    v1 = FinalReportModel.model_validate_json((ROOT / 'tests/fixtures/final_report/infrannuale.json').read_bytes())
    bs = {column.name: Decimal(0) for column in BalanceSheet.__table__.columns if column.name.startswith('sp')}
    ce = {column.name: Decimal(0) for column in IncomeStatement.__table__.columns if column.name.startswith('ce')}
    sources = []
    for (basis, year, months), amount in zip([('historical', 2025, 12), ('observed', 2026, 9),
                                              ('adjusted', 2026, 9), ('closing', 2026, 12)], amounts):
        period = StatementPeriod(id=f'{basis}:{year}', year=year, label={'historical': '2025 storico', 'observed': '2026 osservato',
                                                                         'adjusted': '2026 rettificato', 'closing': '2026 chiusura'}[basis],
                                 basis=basis, period_months=months, source='synthetic_period_fixture')
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
    report = with_notes(report)
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
        page_texts = [' '.join(page.get_text().split()) for page in pdf]
        full_text = ' '.join(page_texts)
        assert report.document.title in page_texts[0]
        assert report.company.name in page_texts[0]
        assert 'PERIMETRO DEL DOCUMENTO' in page_texts[0]
        assert 'CONTENUTI DEL DOSSIER' in page_texts[0]
        assert 'Base editoriale in sviluppo' not in full_text
        for statement in report.detailed_statements:
            numbers = [number for number, page in enumerate(plan.pages, 1)
                       if any(part.statement_id == statement.id for part in page.table_parts)]
            expected_reference = f'{statement.title} · pagina {numbers[0]}'
            if numbers[0] != numbers[-1]:
                expected_reference += f'–{numbers[-1]}'
            assert expected_reference in full_text
            assert all(statement.title in page_texts[number - 1] for number in numbers)
        for page, note in zip(pdf, report.editorial_notes):
            text = page_texts[page.number]
            assert page.rect.width < page.rect.height
            assert 'BOZZA' in text and 'Lettura del consulente' in text
            assert 'Riservato e confidenziale' in text
            assert f'{page.number + 1} / {pdf.page_count}' in text
            if page.number:
                assert report.company.name in text and report.document.title in text
            assert note.text in text
            assert not page.get_images()
            assert all(pdf.extract_font(font[0])[3] for font in page.get_fonts())
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
    with pytest.raises(RendererCompileError) as error:
        verify_editorial_layout(report, probe)
    # Il codice del template arriva fino a chi deve spiegarlo: prima finiva in DEVNULL e l'endpoint
    # diceva «verificare il renderer» anche quando il renderer funzionava (AMBIENTA, 2026-09-17).
    assert 'editorial-note-does-not-fit' in error.value.panics
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
    assert production['cells'][1:5] == ['850', '900', '1020', '1200']
    assert '2026 osservato (9 mesi)' in comparison['columns']
    assert '2026 rettificato (9 mesi)' in comparison['columns']
    assert '2026 chiusura (12 mesi)' in comparison['columns']
    report = prepare_editorial_report(original, probe)
    verify_editorial_layout(report, probe)
    with fitz.open(stream=probe.render(report).data, filetype='pdf') as pdf:
        text = ' '.join(' '.join(page.get_text().split()) for page in pdf)
        assert 'non annualizza gli importi infrannuali' in text
        # Euro interi nelle tabelle (decisione del proprietario, 2026-09-17): i centesimi non entrano
        # in una colonna di un periodo su sei o sette, e in un dossier non dicono nulla.
        assert '900' in text and '1.020' in text and '1.200' in text
        assert '900,00' not in text and '1.020,00' not in text and '1.200,00' not in text
    assert all(len(statement.periods) == 7 for statement in report.detailed_statements)


def test_changed_narrative_reflow_invalidates_existing_page_bindings(probe):
    report = prepare_editorial_report(fixture_report(), probe)
    changed = report.model_copy(deep=True)
    # I grafici canonici occupano ormai una pagina propria (M2-02B): un testo
    # entro capacità non sposta più nulla — il piano resta valido, ed è ciò che
    # si vuole. Il reflow che conta è quello che eccede la pagina fissa: il
    # template paniccia e la verifica deve rifiutare il drift, non riassociare
    # le note.
    changed.narrative[0].text = 'Il piano richiede una lettura dei valori e delle ipotesi. ' * 130
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


def test_importi_milionari_al_centesimo_si_impaginano_in_euro_interi(probe):
    """AMBIENTA, 2026-09-17: «Prepara piano editoriale» rispondeva 503 «verificare il renderer».

    Il renderer funzionava: il template si fermava su ``editorial-amount-does-not-fit``, perché
    «4.006.984,18» misura 49,7 pt in una colonna di 39,8 pt quando i periodi affiancati sono sei o
    più. Le fixture usavano importi da tre cifre, un'azienda vera ha milioni al centesimo.
    """
    original = infrannual_period_report(('3761087.73', '4006984.18', '4146966.26', '8013968.36'))
    report = prepare_editorial_report(original, probe)
    verify_editorial_layout(report, probe)
    with fitz.open(stream=probe.render(report).data, filetype='pdf') as pdf:
        text = ' '.join(' '.join(page.get_text().split()) for page in pdf)
    assert '4.006.984' in text and '8.013.968' in text
    assert '4.006.984,18' not in text
    # Arrotondamento al mezzo euro, non troncamento: 4.146.966,26 → 4.146.966; 3.761.087,73 → 3.761.088.
    assert '3.761.088' in text

@pytest.mark.parametrize('workflow', ['infrannuale', 'bilancio', 'startup'])
def test_nessun_metadato_tecnico_e_nessun_titolo_inglese_nel_document(probe, workflow):
    """M2-02B difetti 2 e 3: il PDF di M2-02 stampava gli ID canonici come contenuto
    («ID: historical:2025», «Fonte: synthetic_period_fixture», blocchi «practice.pfn»,
    «Unità: ratio») e sei titoli narrativi in inglese. Nel dossier editoriale nulla di
    tutto questo compare: le etichette sono italiane, gli ID restano nei marcatori."""
    report = prepare_editorial_report(fixture_report(workflow, [2027, 2028, 2029]), probe)
    with fitz.open(stream=probe.render(report).data, filetype='pdf') as pdf:
        text = ' '.join(' '.join(page.get_text().split()) for page in pdf)
    for forbidden in ('historical:', 'forecast:', 'practice.', 'synthetic_', 'Unità: ratio',
                      'Executive summary', 'Adjustments and closing', 'Budget assumptions',
                      'Economic outlook', 'Financial outlook', 'Risks and actions'):
        assert forbidden not in text, forbidden
    # Occhiello e titolo neutro in italiano per ogni sezione resa.
    assert 'SINTESI · ' in text and 'Sintesi esecutiva' in text
    assert 'PIANO E RISULTATI · ' in text


@pytest.mark.parametrize('workflow', ['infrannuale', 'bilancio', 'startup'])
def test_colonna_kpi_letta_al_centesimo_dal_modello_col_periodo_giusto(probe, workflow):
    """M2-02B difetto 4: la colonna KPI della pagina tipo legge valori dal
    modello v2, non reinventa nulla. Ogni KPI è controllato riga per riga
    contro il Decimal da cui è preso (l'anno sbagliato fa fallire il test), e
    le etichette dei periodi resa sono quelle dell'ultimo anno di piano."""
    report = prepare_editorial_report(fixture_report(workflow, [2027, 2028, 2029]), probe)
    inventory = build_inventory(report)
    last = report.forecast.years[-1]
    checks = {'cassa': ('balance_sheet', 'cash'), 'ricavi': ('income_statement', 'revenue')}
    rows = {line.code for line in last.balance_sheet + last.income_statement if line.value is not None}
    checked = 0
    for section in inventory:
        for item in section['items']:
            for kpi in item.get('kpis') or ():
                for prefix, (attribute, code) in checks.items():
                    if kpi['label'] == f"{prefix} · {last.year}":
                        value = next(line.value for line in getattr(last, attribute) if line.code == code)
                        assert kpi['value'] == format(value, 'f'), kpi
                        checked += 1
    if not {'cash', 'revenue'} <= rows:
        pytest.skip("fixture senza righe di previsione: niente KPI da allineare")
    assert checked >= len(checks)
    with fitz.open(stream=probe.render(report).data, filetype='pdf') as pdf:
        text = ' '.join(' '.join(page.get_text().split()) for page in pdf)
    for label in ('EBITDA margin ·', 'PFN ·', 'orizzonte di piano', 'cassa · 2029', 'ricavi ·'):
        assert label in text, label
    # Un KPI che il modello non fornisce è omesso, mai un «n.d.» in colonna.
    for section in inventory:
        for kpi in section.get('kpis') or ():
            assert kpi['value'] is not None or kpi['series'] or kpi['to'] is not None, kpi
        for item in section['items']:
            for kpi in item.get('kpis') or ():
                assert kpi['value'] is not None or kpi['series'] or kpi['to'] is not None, kpi
