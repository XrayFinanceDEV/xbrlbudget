"""Base print composition: real fonts, continuation headers and usable margins."""
import hashlib
import json
import os
from pathlib import Path

import fitz
import pytest

from app.renderers.typst import Compiler, RendererCompileError, TemplateBundle, TypstRenderer
from tests.test_final_report_v2 import fixture_report

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'backend/app/renderers/typst/templates/dossier-base'


@pytest.fixture
def renderer(tmp_path):
    binary = Path(os.environ.get('TYPST_TEST_BINARY', ROOT / 'tools/typst/bin/typst'))
    if not binary.exists():
        pytest.skip('Install pinned Typst to run print composition tests')
    return TypstRenderer(Compiler.from_manifest(ROOT / 'tools/typst/manifest.json', binary),
                         TemplateBundle(BASE), temp_root=tmp_path)


def test_all_assets_verified_and_reference_font_variants_bundled():
    manifest = json.loads((BASE / 'manifest.json').read_text())
    expected = {
        'Regular': '975dcda37d80f038dcd143c22e33ca2d97a0cc5a929aace1c749153b0fe1afa5',
        'Medium': '331c8639d7598b2cde62a911a71db195e30cb655cd6bdf2e324a7e984955f907',
        'SemiBold': 'a20caf8286023a6a7a85e40b1d2a4ae9fc3e3b1f9eda8f4c542dd4986af67bb1',
        'Italic': 'a9c6ef9942c49e49d11e11a6dacc0b3a087978757e9b22a06b8ac22a6400fb15',
    }
    for variant, digest in expected.items():
        name = f'fonts/IBMPlexSans-{variant}.ttf'
        assert manifest['files'][name] == hashlib.sha256((BASE / name).read_bytes()).hexdigest() == digest
    assert 'SIL OPEN FONT LICENSE Version 1.1' in (BASE / 'OFL-1.1.txt').read_text()
    assert '242c4cccd37e87985a5337815c99b960ef13c65c' in (BASE / 'PROVENANCE.md').read_text()


@pytest.mark.parametrize('workflow', ['bilancio', 'infrannuale', 'startup'])
@pytest.mark.parametrize('years', [[2027], [2027, 2028, 2029], list(range(2027, 2032))])
def test_real_base_has_complete_appendices_notes_fonts_and_no_overflow(renderer, tmp_path, workflow, years):
    report = fixture_report(workflow, years)
    artifact = renderer.render(report)
    fonts = set()
    titles = {s.title for s in report.detailed_statements}
    with fitz.open(stream=artifact.data, filetype='pdf') as pdf:
        assert pdf.metadata['title'] == report.document.title
        assert pdf.page_count > 4
        for page in pdf:
            text = page.get_text()
            assert 'Lettura del consulente' in text and 'Spazio riservato' in text
            assert 'BOZZA' in text and 'Riservato e confidenziale' in text
            if page.number:
                assert any(title in text for title in titles), 'Continuation lacks statement header'
            assert not page.get_images()
            for font in page.get_fonts():
                assert 'IBMPlexSans' in font[3]
                assert pdf.extract_font(font[0])[3], 'Font not embedded'
                fonts.add(font[3].split('+')[-1])
            for block in page.get_text('dict')['blocks']:
                for line in block.get('lines', []):
                    for span in line['spans']:
                        bounds = fitz.Rect(span['bbox'])
                        assert bounds.x0 >= -0.5 and bounds.x1 <= page.rect.width + 0.5
                        assert bounds.y0 >= -0.5 and bounds.y1 <= page.rect.height + 0.5
        assert any('Medium' in f or 'Medm' in f for f in fonts)
        assert any('SemiBold' in f or 'SmBld' in f for f in fonts)
        assert all(any(s.title in p.get_text() for p in pdf) for s in report.detailed_statements)
    assert not list(tmp_path.iterdir())


def test_long_company_and_literal_markup_fit_without_truncation(renderer):
    report = fixture_report()
    report.company.name = ('Officine Industriali Toscane e Servizi di Progettazione ' * 10) + '#panic("LITERAL-COMPANY")'
    report.source_hash = report.calculate_source_hash()
    report.model_hash = report.calculate_model_hash()
    artifact = renderer.render(report)
    with fitz.open(stream=artifact.data, filetype='pdf') as pdf:
        text = ' '.join(pdf[0].get_text().split())
        assert 'LITERAL-COMPANY' in text
        assert ' '.join(report.company.name.split()) in text
        # All white cover text remains inside the 108mm blue band.
        for b in pdf[0].get_text('dict')['blocks']:
            for line in b.get('lines', []):
                for span in line['spans']:
                    if span['color'] == 0xffffff:
                        assert span['bbox'][3] <= 108 * 72 / 25.4 + 0.5


def test_final_gray_state_is_literal_and_repeatable(renderer):
    report = fixture_report('startup')
    first = renderer.render(report, document_state='final', grayscale=True)
    second = renderer.render(report, document_state='final', grayscale=True)
    assert first.data == second.data
    with fitz.open(stream=first.data, filetype='pdf') as pdf:
        assert all('BOZZA' not in p.get_text() for p in pdf)
        # The full width, 108mm cover rectangle remains vector and gray.
        rectangles = [d for d in pdf[0].get_drawings() if d['fill'] is not None
                      and d['rect'].width > 590 and d['rect'].height > 300]
        assert rectangles
        assert any(max(d['fill']) - min(d['fill']) < 0.001 for d in rectangles)


def test_amount_that_cannot_fit_base_is_rejected_without_clipping(renderer):
    from decimal import Decimal
    report = fixture_report(years=list(range(2027, 2032)))
    row = next(r for r in report.detailed_statements[0].rows if r.code == 'ce01_ricavi_vendite')
    row.values = [Decimal('9007199254740993.01')] * 5
    # M2-02C tied `structure_series.break_even.contribution_margin` to this
    # same row (revenue - variable costs): keep it consistent so the huge
    # amount is rejected for not fitting the page, not for a stale margin.
    break_even = next(g for g in report.structure_series if g.id == 'break_even')
    variable_costs = next(s for s in break_even.series if s.id == 'variable_costs')
    margin = next(s for s in break_even.series if s.id == 'contribution_margin')
    margin.values = [None if variable is None else (row.values[0] - variable) for variable in variable_costs.values]
    report.source_hash = report.calculate_source_hash()
    report.model_hash = report.calculate_model_hash()
    with pytest.raises(RendererCompileError):
        renderer.render(report)
