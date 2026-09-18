"""Catalogo fisso del dossier v4 (M2-02D): esatto per pagina, reflow reale e
capacita' della nota per pagina. Sostituisce la vecchia suite scritta contro
l'inventario generico (editorial_inventory.py, rimosso): alcuni test del giro
precedente non hanno più un contenuto a cui riferirsi — comparazione dei
periodi, catalogo indicatori a blocchi, blocchi narrativi — perché quelle
pagine non sono ancora implementate (dati.py e indicatori.py hanno registro
vuoto in questa fase). Restano commentati dove rimossi, non silenziosamente
sparsi."""
from dataclasses import asdict, replace
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path

import fitz
import pytest

from app.renderers.typst import Compiler, RendererCompileError, RendererInputError, RendererLimits, RendererUnavailable
from app.renderers.typst.dossier_catalog import (build_inventory, chart_declarations, chart_marker_width_mm, expected_content_inventory)
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
def test_full_real_composition_has_exact_pages_appendix_rows_and_slots(probe, workflow, years, tmp_path):
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
    # Le righe degli Allegati restano lossless anche se le colonne mostrate sono
    # solo chiusura/storico + anni di piano (vincolo del proprietario): ogni
    # riga dei tre prospetti compare esattamente una volta, in ordine.
    rows = [(part.statement_id, row) for page in plan.pages for part in page.table_parts for row in part.row_ids]
    assert rows == [(s.id, r.id) for s in report.detailed_statements for r in s.rows]
    assert all(page.note_slot.max_lines == 4 and page.note_slot.font_size_pt == 9 for page in plan.pages)
    assert len({page.note_id for page in plan.pages}) == len(plan.pages)
    # Un catalogo fisso: ogni voce del catalogo Python è esattamente una
    # pagina fisica (nessuna voce del catalogo si spezza fuori dagli Allegati,
    # che dichiarano da sé le proprie parti come voci separate) — già
    # garantito da `_validate_inventory` dentro `build_editorial_plan`
    # ("physical pages cannot mix logical sections"), qui solo il conteggio.
    assert len(plan.pages) == len(build_inventory(original))
    artifact = probe.render(report)
    with fitz.open(stream=artifact.data, filetype='pdf') as pdf:
        assert pdf.page_count == measurement.page_count
        assert pdf.metadata['title'] == report.document.title
        page_texts = [' '.join(page.get_text().split()) for page in pdf]
        full_text = ' '.join(page_texts)
        assert report.document.title in page_texts[0]
        assert report.company.name in page_texts[0]
        # Copertina come la v4 (M2-02G): occhiello, messaggio, striscia KPI e
        # indice delle sezioni col numero di pagina. I due blocchi precedenti
        # («Perimetro del documento», «Contenuti del dossier» a sei voci senza
        # numeri) non esistono più.
        assert 'REPORT FINALE DELLA PRATICA' in page_texts[0]
        assert 'PERIMETRO DEL DOCUMENTO' not in page_texts[0]
        catalog = build_inventory(original)
        cover_toc = catalog[0]['toc']
        assert cover_toc, 'la copertina deve elencare le sezioni'
        for entry in cover_toc:
            assert entry['label'] in page_texts[0], entry
            # Il numero stampato è la posizione reale della pagina nel
            # documento compilato, non una promessa di Python.
            assert catalog[entry['page'] - 1]['title'] == entry['label'], entry
            assert entry['label'] in page_texts[entry['page'] - 1], entry
        for statement in report.detailed_statements:
            numbers = [number for number, page in enumerate(plan.pages, 1)
                       if any(part.statement_id == statement.id for part in page.table_parts)]
            assert numbers, statement.id
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


def test_appendix_index_lists_every_part_with_its_own_resolved_page(probe):
    report = with_notes(prepare_editorial_report(fixture_report('bilancio', [2027, 2028, 2029]), probe))
    plan = report.editorial_plan
    page_of = {content_id: number for number, page in enumerate(plan.pages, 1) for content_id in page.content_ids}
    with fitz.open(stream=probe.render(report).data, filetype='pdf') as pdf:
        page_texts = [' '.join(page.get_text().split()) for page in pdf]
    index_page = next(page for page in plan.pages if 'appendix-index' in page.content_ids)
    index_text = page_texts[plan.pages.index(index_page)]
    for section in build_inventory(report):
        for item in section['items']:
            if item['kind'] != 'index':
                continue
            for entry in item['entries']:
                number = page_of[entry['target']]
                assert entry['label'] in index_text
                assert str(number) in index_text


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


def test_overlong_manual_note_fails_without_truncation(probe):
    # La metà "narrativa troppo lunga" del vecchio test non ha più un
    # contenuto a cui riferirsi: nessuna pagina del catalogo di questa fase
    # rende un blocco narrativo (`report.narrative`) — copertina, sintesi,
    # CE previsionale e Allegati non lo usano. Resta la metà sul commento per
    # pagina, che ogni pagina porta sempre.
    prepared = prepare_editorial_report(fixture_report(), probe)
    report = with_notes(prepared, text='Commento molto lungo. ' * 120)
    with pytest.raises(RendererCompileError):
        verify_editorial_layout(report, probe)


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
    charts = chart_declarations(report)
    values = []
    for record in measured.records:
        value = {key: item for key, item in asdict(record).items() if item is not None}
        if record.content_id.startswith('chart:'):
            item = charts[record.content_id]
            view = item['chart']
            width = chart_marker_width_mm(item)
            value.update(kind='chart', width_mm=width, height_mm='94', measured_width_mm=width,
                         measured_height_mm='94', unit=view['unit'], categories=view['categories'],
                         series=view['series'], thresholds=view['thresholds'])
        values.append(value)
    assert probe._validate_records(json.dumps(values).encode(), report) == measured.records
    chart_value = next(value for value in values if value['kind'] == 'chart')
    chart_value['width_mm'] = geometry
    with pytest.raises(RendererCompileError):
        probe._validate_records(json.dumps(values).encode(), report)


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


def test_catalog_definition_revision_invalidates_plan_even_without_page_changes(probe, tmp_path, monkeypatch):
    """`_GENERATOR_FILES` copre l'intero pacchetto `dossier_catalog/`, non più
    un solo file: la stessa garanzia di prima (una revisione del generatore
    invalida i piani già misurati) ora vale modificando uno qualunque dei
    suoi moduli, qui `shared.py` — usato da ogni gruppo."""
    import app.renderers.typst.editorial_plan as module
    real_dir = Path(module._GENERATOR_DIR)
    copies = []
    for path in real_dir.glob('*.py'):
        target = tmp_path / path.name
        target.write_bytes(path.read_bytes())
        copies.append(target)
    monkeypatch.setattr(module, '_GENERATOR_FILES', tuple(sorted(copies)))
    report = fixture_report()
    first = prepare_editorial_report(report, probe)
    shared_copy = tmp_path / 'shared.py'
    shared_copy.write_bytes(shared_copy.read_bytes() + b'\n# Layout definition revision.\n')
    with pytest.raises(RendererUnavailable):
        probe.measure_layout(report)
    # Simulate a restarted worker loading the revised definition; semantics and
    # page geometry remain identical, but layout/asset identity must differ.
    monkeypatch.setattr(module, '_GENERATOR_HASH', module._generator_hash())
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
    più. Le fixture usavano importi da tre cifre, un'azienda vera ha milioni al centesimo. Il
    catalogo di questa fase mostra osservato e rettificato solo nelle pagine 3-6 (non ancora
    implementate): qui si verifica solo la chiusura, l'unica delle quattro cifre che compare
    davvero negli Allegati di questa fase (chiusura + anni di piano, vincolo del proprietario).
    """
    original = infrannual_period_report(('3761087.73', '4006984.18', '4146966.26', '8013968.36'))
    report = prepare_editorial_report(original, probe)
    verify_editorial_layout(report, probe)
    with fitz.open(stream=probe.render(report).data, filetype='pdf') as pdf:
        text = ' '.join(' '.join(page.get_text().split()) for page in pdf)
    assert '8.013.968' in text
    assert '8.013.968,36' not in text


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
    assert 'SINTESI · ' in text and 'Sintesi esecutiva' in text
    assert 'PIANO E RISULTATI · ' in text
    assert 'ALLEGATI · ' in text


@pytest.mark.parametrize('workflow', ['infrannuale', 'bilancio', 'startup'])
def test_kpi_cassa_letto_al_centesimo_dal_modello_con_periodo_giusto(probe, workflow):
    """M2-02B difetto 4, ristretto al catalogo di questa fase: la colonna KPI
    legge valori dal modello v2, non reinventa nulla. «cassa» è l'unico KPI
    con una regola di periodo fissa e verificabile riga per riga (l'ultimo
    anno di piano); «ricavi» ha più fonti possibili (chiusura, primo anno,
    ultimo anno a seconda del workflow) e non si presta allo stesso confronto
    diretto — resta verificato solo per presenza, sotto."""
    report = prepare_editorial_report(fixture_report(workflow, [2027, 2028, 2029]), probe)
    inventory = build_inventory(report)
    last = report.forecast.years[-1]
    cash_rows = {line.code: line.value for line in last.balance_sheet if line.code in ('cash', 'sp09_disponibilita_liquide')}
    checked = 0
    for section in inventory:
        # I KPI stanno sul singolo blocco oppure, nelle pagine con una forma
        # dichiarata, nel rail di pagina (M2-02G traccia A): la regola di
        # periodo è la stessa, cambia solo dove il catalogo li appende.
        candidates = [kpi for item in section['items'] for kpi in item.get('kpis') or ()]
        candidates += list(section.get('rail') or ())
        for kpi in candidates:
                if kpi['label'] == f'cassa · {last.year}':
                    value = next(v for code, v in cash_rows.items() if v is not None)
                    assert kpi['value'] == format(value, 'f'), kpi
                    checked += 1
    if not cash_rows or all(v is None for v in cash_rows.values()):
        pytest.skip('fixture senza riga di cassa: niente KPI da allineare')
    assert checked >= 1
    with fitz.open(stream=probe.render(report).data, filetype='pdf') as pdf:
        text = ' '.join(' '.join(page.get_text().split()) for page in pdf)
    for label in ('EBITDA margin ·', 'PFN ·', 'orizzonte di piano', 'cassa ·', 'ricavi ·'):
        assert label in text, label
    # Un KPI che il modello non fornisce è omesso, mai un «n.d.» in colonna.
    for section in inventory:
        for kpi in section.get('kpis') or ():
            assert kpi['value'] is not None or kpi['series'] or kpi['to'] is not None, kpi
        for item in section['items']:
            for kpi in item.get('kpis') or ():
                assert kpi['value'] is not None or kpi['series'] or kpi['to'] is not None, kpi


@pytest.mark.parametrize('workflow', ['infrannuale', 'bilancio', 'startup'])
def test_grafici_multi_serie_senza_mille_punte_e_senza_pagine_nd(probe, workflow):
    """M2-02B difetti 5 e 6: via «×10^3» dagli assi (parola italiana o nessuna
    scala), grafici multi-serie, e nessun grafico vuoto sprecato su una pagina
    intera — un grafico senza alcun valore semplicemente non compare."""
    report = prepare_editorial_report(fixture_report(workflow, [2027, 2028, 2029]), probe)
    with fitz.open(stream=probe.render(report).data, filetype='pdf') as pdf:
        text = ' '.join(' '.join(page.get_text().split()) for page in pdf)
    assert '×10' not in text
    chart_items = [item for section in build_inventory(report) for item in section['items'] if item['kind'] == 'chart']
    assert any(len(item['chart']['series']) > 1 for item in chart_items), 'nessun grafico multi-serie'
    for item in chart_items:
        assert any(value is not None for series in item['chart']['series'] for value in series['values']), item['chart_id']
