"""M2-02A: resolved Typst metadata is measured inside the renderer sandbox."""
import hashlib
import json
import os
from pathlib import Path

import pytest

from app.renderers.typst import Compiler, RendererCompileError, RendererUnavailable, TemplateBundle
from app.renderers.typst.layout_probe import TypstLayoutProbe
from tests.test_final_report_v2 import fixture_report

ROOT = Path(__file__).resolve().parents[1]


def _bundle(tmp_path, source):
    folder = tmp_path / f'template-{len(list(tmp_path.glob("template-*")))}'
    folder.mkdir()
    (folder / 'template.typ').write_text(source, encoding='utf-8')
    digest = hashlib.sha256(source.encode()).hexdigest()
    (folder / 'manifest.json').write_text(json.dumps({
        'version': 'layout-test-1', 'entrypoint': 'template.typ',
        'files': {'template.typ': digest},
    }), encoding='utf-8')
    return TemplateBundle(folder)


def _source(report, *, omit=None):
    parts = ['#set page(footer: context metadata((kind: "page", content_id: "page-shell", page: here().page())))',
             '#context [#metadata((kind: "content", content_id: "cover", page: here().page()))]']
    for statement in report.detailed_statements:
        for row in statement.rows:
            if (statement.id, row.id) == omit:
                continue
            parts.extend((
                '#pagebreak()',
                '#context [#metadata((kind: "row", content_id: "row:' + statement.id + ':' + row.id
                + '", statement_id: "' + statement.id + '", row_id: "' + row.id
                + '", page: here().page()))]',
                '[x]',
            ))
    return '\n'.join(parts)


@pytest.fixture
def probe(tmp_path):
    binary = Path(os.environ.get('TYPST_TEST_BINARY', ROOT / 'tools/typst/bin/typst'))
    if not binary.is_file():
        pytest.skip('Install pinned tools/typst compiler for runtime integration tests')
    compiler = Compiler.from_manifest(ROOT / 'tools/typst/manifest.json', binary)
    report = fixture_report()
    return TypstLayoutProbe(compiler, _bundle(tmp_path, _source(report)), temp_root=tmp_path), report


def test_layout_probe_reads_resolved_pages_and_cleans_private_job(probe, tmp_path):
    renderer, report = probe
    records = renderer.inspect_layout(report)
    cover = next(r for r in records if r.kind == 'content')
    assert cover.content_id == 'cover' and cover.page == 1
    rows = [record for record in records if record.kind == 'row']
    assert [(record.statement_id, record.row_id) for record in rows] == [
        (statement.id, row.id) for statement in report.detailed_statements for row in statement.rows
    ]
    content = [r for r in records if r.kind != 'page']
    assert [record.page for record in content] == list(range(1, len(content) + 1))
    assert not list(tmp_path.glob('budget-typst-*'))


def test_layout_probe_rejects_missing_or_reordered_requested_rows(probe, tmp_path):
    renderer, report = probe
    first = report.detailed_statements[0].rows[0]
    renderer.bundle = _bundle(tmp_path, _source(report, omit=(report.detailed_statements[0].id, first.id)))
    with pytest.raises(RendererCompileError):
        renderer.inspect_layout(report)
    assert not list(tmp_path.glob('budget-typst-*'))


def test_real_base_measurement_matches_pdf_pages_and_exact_source_binding(probe):
    from app.renderers.typst import TypstRenderer
    renderer, report = probe
    renderer.bundle = TemplateBundle(ROOT / 'backend/app/renderers/typst/templates/dossier-base')
    measured = renderer.measure_layout(report)
    pdf = TypstRenderer(renderer.compiler, renderer.bundle).render(report)
    assert measured.page_count == pdf.page_count
    assert measured.source_hash == report.source_hash and measured.model_hash == report.model_hash
    assert measured.layout_version == 'dossier-base-1'
    assert len(measured.font_hash) == len(measured.layout_hash) == len(measured.asset_hash) == 64
    assert renderer.measure_layout(report) == measured
    assert len([r for r in measured.records if r.kind == 'page']) == pdf.page_count


@pytest.mark.parametrize('fault', ['missing', 'duplicate', 'reorder', 'unknown_content',
                                  'blank_page', 'missing_shell', 'page_limit', 'bad_type'])
def test_metadata_inventory_rejects_invalid_or_uncovered_pages(fault):
    report = fixture_report()
    values = [{'kind': 'content', 'content_id': 'cover', 'page': 1},
              {'kind': 'page', 'content_id': 'page-shell', 'page': 1},
              {'kind': 'page', 'content_id': 'page-shell', 'page': 2}]
    values += [{'kind': 'row', 'content_id': 'row:' + s.id + ':' + row.id, 'page': 2,
                'statement_id': s.id, 'row_id': row.id}
               for s in report.detailed_statements for row in s.rows]
    max_pages = 200
    if fault == 'missing':
        values.pop()
    elif fault == 'duplicate':
        values.append(values[-1])
    elif fault == 'reorder':
        values[-1], values[-2] = values[-2], values[-1]
    elif fault == 'unknown_content':
        values[0]['content_id'] = 'not-in-inventory'
    elif fault == 'blank_page':
        values.append({'kind': 'page', 'content_id': 'page-shell', 'page': 3})
    elif fault == 'missing_shell':
        values.pop(2)
    elif fault == 'page_limit':
        max_pages = 1
    else:
        values[0]['page'] = True
    with pytest.raises(RendererCompileError):
        TypstLayoutProbe._validate_records(json.dumps(values).encode(), report, max_pages=max_pages)


def test_staging_os_error_is_sanitized(probe, monkeypatch):
    renderer, report = probe
    def failed(*args):
        raise OSError('PRIVATE-PATH-CONTENT')
    monkeypatch.setattr(renderer, '_private_job', failed)
    with pytest.raises(RendererUnavailable) as caught:
        renderer.inspect_layout(report)
    assert 'PRIVATE' not in str(caught.value)
