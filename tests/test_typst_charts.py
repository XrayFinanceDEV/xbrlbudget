"""M2-03 real native charts: source fidelity, geometry, holes and printed styles."""
import json
import os
import time
from decimal import Decimal, ROUND_HALF_UP, localcontext
from pathlib import Path

import fitz
import pytest

from app.renderers.typst import Compiler, RendererCompileError, RendererLimits, RendererUnavailable, TypstRenderer
from app.renderers.typst.chart_components import ChartTemplateBundle
from app.schemas.final_report import ChartMetric
from app.schemas.final_report_v2 import FinalReportModelV2, IndicatorThreshold
from tests.test_final_report_v2 import fixture_report

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'backend/app/renderers/typst/templates/dossier-base'


@pytest.fixture
def renderer(tmp_path):
    binary = Path(os.environ.get('TYPST_TEST_BINARY', ROOT / 'tools/typst/bin/typst'))
    if not binary.is_file():
        pytest.skip('Install pinned compiler for native chart integration tests')
    return TypstRenderer(Compiler.from_manifest(ROOT / 'tools/typst/manifest.json', binary),
                         ChartTemplateBundle(BASE), temp_root=tmp_path)


def signed(report):
    report.source_hash = report.calculate_source_hash()
    report.model_hash = report.calculate_model_hash()
    return FinalReportModelV2.model_validate_json(report.model_dump_json())


def displayed(value, unit):
    if value is None:
        return 'n.d.'
    places = 3 if unit == 'ratio' else 1 if unit == 'days' else 2
    with localcontext() as ctx:
        ctx.prec = max(100, len(value.as_tuple().digits) + places + abs(value.adjusted()) + 10)
        rounded = value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
        number = format(abs(rounded), f',.{places}f').translate(str.maketrans({',': '.', '.': ','}))
    return ('−' if rounded < 0 else '') + number


def metadata(renderer, report):
    """Test-only fixed query in the real namespace; never capture diagnostics."""
    serialized = report.model_dump_json().encode()
    _, entry, files = renderer.bundle.read(renderer.limits)
    binary = renderer.compiler.verified_bytes()
    with renderer._private_job(serialized, files, binary,
                              b'{"document_state":"draft","grayscale":false}') as job:
        command = ['/report/compiler', 'eval', 'query(metadata).map(x => x.value)',
                   '--in', '/report/' + entry, '--root', '/report', '--format', 'json',
                   '--jobs', '1', '--ignore-system-fonts', '--font-path', '/report/fonts',
                   '--package-path', '/report/packages', '--package-cache-path', '/report/cache']
        output = job / 'output/layout.json'
        renderer._run(renderer._sandbox_command(job, command), job,
                      stdout_path=output, deadline=time.monotonic() + 30)
        return [v for v in json.loads(output.read_bytes()) if v['kind'] == 'chart']


@pytest.mark.parametrize('workflow', ['infrannuale', 'bilancio', 'startup'])
@pytest.mark.parametrize('years', [[2027], [2027, 2028, 2029], list(range(2027, 2032))])
@pytest.mark.parametrize('draft,gray', [(True, False), (False, False), (True, True), (False, True)])
def test_real_graph_matrix_extracts_canonical_values_without_overflow(renderer, tmp_path, workflow, years, draft, gray):
    report = fixture_report(workflow, years)
    before = report.model_dump_json()
    artifact = renderer.render(report, document_state='draft' if draft else 'final', grayscale=gray)
    assert artifact.template_version.endswith('+native-charts-1')
    with fitz.open(stream=artifact.data, filetype='pdf') as pdf:
        assert pdf.page_count == 1 + len(report.chart_series)
        for index, chart in enumerate(report.chart_series, 1):
            page = pdf[index]
            text = ' '.join(page.get_text().split())
            assert chart.title in text
            assert ('BOZZA' in text) == draft
            assert 'Lettura del consulente' in text
            assert not page.get_images()
            for metric in chart.series:
                assert metric.label in text
                for value in metric.values:
                    assert displayed(value, chart.unit) in text
            assert all(pdf.extract_font(f[0])[3] for f in page.get_fonts())
            for block in page.get_text('dict')['blocks']:
                for line in block.get('lines', []):
                    for span in line['spans']:
                        rect = fitz.Rect(span['bbox'])
                        assert rect.x0 >= -0.5 and rect.x1 <= page.rect.width + 0.5
                        assert rect.y0 >= -0.5 and rect.y1 <= page.rect.height + 0.5
            if gray:
                for drawing in page.get_drawings():
                    for color in (drawing['color'], drawing['fill']):
                        if color is not None:
                            assert max(color) - min(color) < 0.002
    assert report.model_dump_json() == before
    assert not list(tmp_path.iterdir())


def test_real_metadata_keeps_wire_decimals_and_declared_measured_footprint(renderer):
    report = fixture_report('bilancio', list(range(2027, 2032)))
    records = metadata(renderer, report)
    dimensions = renderer.bundle.dimensions()
    assert dimensions.version == 'native-charts-1'
    assert dimensions.width_mm == Decimal('178') and dimensions.height_mm == Decimal('94')
    assert dimensions.plot_height_mm == Decimal('62') and dimensions.legend_height_mm == Decimal('32')
    assert len(records) == len(report.chart_series)
    for record, chart in zip(records, report.chart_series):
        assert record['content_id'] == 'chart:' + chart.id
        assert record['categories'] == chart.categories and record['unit'] == chart.unit
        assert record['series'] == chart.model_dump(mode='json')['series']
        assert record['thresholds'] == []  # No implicit DSCR 1 or invented class.
        assert Decimal(record['width_mm']) == Decimal(record['measured_width_mm']) == Decimal('178')
        assert Decimal(record['height_mm']) == Decimal(record['measured_height_mm']) == Decimal('94')


def test_nulls_split_lines_and_isolated_points_remain_visible(renderer):
    report = fixture_report(years=list(range(2027, 2032)))
    report.chart_series[1].series[0].values = [Decimal('2'), None, Decimal('4'), Decimal('0'), Decimal('-2')]
    report = signed(report)
    artifact = renderer.render(report, document_state='final')
    with fitz.open(stream=artifact.data, filetype='pdf') as pdf:
        page = pdf[2]
        joins = [d for d in page.get_drawings() if abs(d['width'] - 1.5) < 0.01 and d['rect'].width > 30]
        assert len(joins) == 2  # Only 4→0 and 0→−2; no segment bridging the hole.
        assert 'n.d.' in page.get_text() and '−2,00' in page.get_text()


def test_negative_bars_and_true_zero_do_not_create_fake_rectangles(renderer):
    report = fixture_report(years=list(range(2027, 2032)))
    report.chart_series[0].series[0].values = [Decimal('-2'), Decimal('0'), None, Decimal('3'), Decimal('0')]
    report = signed(report)
    artifact = renderer.render(report, document_state='final')
    with fitz.open(stream=artifact.data, filetype='pdf') as pdf:
        drawings = pdf[1].get_drawings()
        bars = [d for d in drawings if d['fill'] is not None and d['type'] == 'fs']
        zero = next(d['rect'].y0 for d in drawings if abs(d['width'] - 0.8) < 0.01)
        assert len(bars) == 2
        assert any(abs(d['rect'].y0 - zero) < 0.01 for d in bars)
        assert any(abs(d['rect'].y1 - zero) < 0.01 for d in bars)


def test_decimal_rounding_never_uses_float_in_text_and_handles_carry(renderer):
    report = fixture_report(years=list(range(2027, 2032)))
    values = [Decimal('9007199254740993.01'), Decimal('999999999999999.995'),
              Decimal('-999.995'), Decimal('-0.004'), Decimal('0')]
    report.chart_series[0].series[0].values = values
    report = signed(report)
    artifact = renderer.render(report, document_state='final')
    with fitz.open(stream=artifact.data, filetype='pdf') as pdf:
        text = pdf[1].get_text()
        assert all(displayed(v, 'eur') in text for v in values)
    assert metadata(renderer, report)[0]['series'][0]['values'] == [format(v, 'f') for v in values]


def test_amount_axis_under_10000_stays_euro_interi_with_integer_ticks(renderer):
    """Rilievo 5: un asse di importi resta in euro interi sotto i 10.000 €,
    e i tick sono sempre interi (mai un tick come «0,997»)."""
    report = fixture_report(years=[2027, 2028, 2029])
    report.chart_series[0].series[0].values = [Decimal('1200'), Decimal('600'), Decimal('0')]
    report = signed(report)
    artifact = renderer.render(report, document_state='final')
    with fitz.open(stream=artifact.data, filetype='pdf') as pdf:
        text = pdf[1].get_text()
        assert 'euro' in text and 'migliaia' not in text
        for tick in ('−96', '252', '600', '948', '1.296'):
            assert tick in text
        assert '0,997' not in text and '1,36' not in text


def test_amount_axis_over_10000_switches_to_migliaia_with_integer_ticks(renderer):
    """Rilievo 5: oltre i 10.000 € l'asse passa a € migliaia, e i tick
    restano interi — mai una frazione tipo «0,997» al posto di «997»."""
    report = fixture_report(years=[2027, 2028, 2029])
    report.chart_series[0].series[0].values = [Decimal('12000'), Decimal('6000'), Decimal('0')]
    report = signed(report)
    artifact = renderer.render(report, document_state='final')
    with fitz.open(stream=artifact.data, filetype='pdf') as pdf:
        text = pdf[1].get_text()
        assert 'euro · valori in migliaia' in text
        for tick in ('−1', '3', '6', '9', '13'):
            assert tick in text
        assert '0,997' not in text and '2,52' not in text and '9,48' not in text


def test_supplied_authoritative_thresholds_only(renderer):
    report = fixture_report(years=[2027, 2028, 2029])
    chart = next(c for c in report.chart_series if c.id == 'practice_liquidity')
    indicator = next(i for i in report.indicator_catalog if i.id == chart.indicator_ids[0])
    values = [Decimal('1'), Decimal('2'), Decimal('3')]
    chart.series[0].values = values
    for index, period in enumerate(indicator.periods):
        if period.basis == 'forecast':
            indicator.values[index] = values[chart.categories.index(period.year)]
            indicator.unavailable_reasons[index] = None
    indicator.thresholds = [IndicatorThreshold(label='Soglia dimostrativa', value=Decimal('1.5'), source='Fonte canonica della fixture')]
    report = signed(report)
    artifact = renderer.render(report, document_state='final')
    with fitz.open(stream=artifact.data, filetype='pdf') as pdf:
        assert 'Fonte canonica della fixture' in pdf[8].get_text()
        assert '1,500' in pdf[8].get_text()
    record = next(r for r in metadata(renderer, report) if r['content_id'] == 'chart:practice_liquidity')
    assert record['thresholds'][0]['value'] == '1.5'
    assert record['thresholds'][0]['source'] == 'Fonte canonica della fixture'


def test_four_canonical_cashflow_series_have_distinct_gray_styles(renderer):
    report = fixture_report(years=[2027, 2028, 2029])
    chart = report.chart_series[2]
    chart.series = [ChartMetric(key=str(i), label='Flusso ' + str(i), values=[Decimal(i + 1)] * 3) for i in range(4)]
    report = signed(report)
    artifact = renderer.render(report, document_state='final', grayscale=True)
    with fitz.open(stream=artifact.data, filetype='pdf') as pdf:
        fills = {d['fill'] for d in pdf[3].get_drawings() if d['type'] == 'fs' and d['fill'] is not None}
        assert len(fills) == 4
        assert 'Flusso 3' in pdf[3].get_text()


def test_identical_report_options_reproduce_pdf_bytes(renderer):
    report = fixture_report()
    assert renderer.render(report).data == renderer.render(report).data


def test_oversized_legend_fails_without_clipping(renderer):
    report = fixture_report()
    report.chart_series[0].series[0].label = 'Etichetta molto lunga ' * 100
    report = signed(report)
    with pytest.raises(RendererCompileError):
        renderer.render(report)


@pytest.mark.parametrize('value', ['1e400', '1e-400'])
def test_unrepresentable_coordinates_fail_without_false_zero(renderer, value):
    report = fixture_report(years=[2027])
    report.chart_series[0].series[0].values = [Decimal(value)]
    report = signed(report)
    with pytest.raises(RendererCompileError):
        renderer.render(report)


@pytest.mark.parametrize('mutation', ['negative', 'sum', 'too_wide', 'bool', 'styles', 'float_json', 'legal_but_changed'])
def test_dimension_contract_rejects_invalid_verified_config(mutation):
    _, _, files = ChartTemplateBundle(BASE).read(RendererLimits())
    config = json.loads(files['chart-layout.json'])
    if mutation == 'negative':
        config['height_mm'] = '-1'
    elif mutation == 'sum':
        config['height_mm'] = '93'
    elif mutation == 'too_wide':
        config['width_mm'] = '300'
    elif mutation == 'bool':
        config['height_mm'] = True
    elif mutation == 'styles':
        config['max_series'] = 5
    elif mutation == 'legal_but_changed':
        config.update(width_mm='177', height_mm='93', plot_height_mm='61', legend_height_mm='32')
    else:
        config['height_mm'] = 94.0
    files['chart-layout.json'] = json.dumps(config).encode()
    with pytest.raises(RendererUnavailable):
        ChartTemplateBundle._dimensions(files)
