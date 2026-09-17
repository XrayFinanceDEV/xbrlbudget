"""Freeze physical pages measured from the complete authorized canonical dossier."""
from __future__ import annotations

from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass, replace
from decimal import Decimal
import hashlib
import json
from pathlib import Path

from app.schemas.final_report import canonical_hash
from app.schemas.final_report_v2 import (
    EditorialNoteSlot, EditorialPage, EditorialPlan, EditorialReadiness,
    EditorialTablePart, FinalReportModelV2,
)
from .chart_components import ChartTemplateBundle
from .editorial_inventory import (build_inventory, chart_marker_width_mm, chart_view, expected_content_inventory)
from .layout_probe import LayoutMeasurement, TypstLayoutProbe
from .runtime import RendererCompileError, RendererInputError, RendererLimits, RendererUnavailable, _regular

_INVENTORY = 'editorial-inventory.json'
_PT_PER_MM = Decimal(72) / Decimal('25.4')
_GENERATOR_PATH = Path(__file__).with_name('editorial_inventory.py').absolute()
_GENERATOR_HASH = hashlib.sha256(_regular(_GENERATOR_PATH, 256 * 1024)).hexdigest()


class DossierTemplateBundle(ChartTemplateBundle):
    """Fixed internal entrypoint; presentation data are derived, never caller assets."""
    def read(self, limits: RendererLimits):
        version, _, files = super().read(limits)
        if 'editorial.typ' not in files or _INVENTORY in files:
            raise RendererUnavailable()
        return version + '+editorial-3', 'editorial.typ', files


@dataclass(frozen=True)
class DossierRecord:
    kind: str
    page: int
    content_id: str
    width_pt: str | None = None
    height_pt: str | None = None
    font_size_pt: str | None = None
    max_lines: int | None = None


class DossierLayoutProbe(TypstLayoutProbe):
    """Same fixed query, process limits and sandbox as the base layout probe."""
    def measure_layout(self, report):
        measurement = super().measure_layout(report)
        # The Python inventory definition affects composition as much as Typst
        # assets. Economic input remains bound by source_hash, not an asset hash.
        return replace(measurement,
            layout_hash=canonical_hash({'bundle': measurement.layout_hash, 'inventory': _GENERATOR_HASH}),
            asset_hash=canonical_hash({'bundle': measurement.asset_hash, 'inventory': _GENERATOR_HASH}))

    @contextmanager
    def _private_job(self, serialized, files, binary, options):
        if hashlib.sha256(_regular(_GENERATOR_PATH, 256 * 1024)).hexdigest() != _GENERATOR_HASH:
            raise RendererUnavailable()
        report = FinalReportModelV2.model_validate_json(serialized)
        inventory = json.dumps(build_inventory(report), ensure_ascii=False, allow_nan=False,
                               separators=(',', ':')).encode('utf-8')
        if (len(inventory) > self.limits.max_input_bytes or _INVENTORY in files
                or len(files) + 1 > self.limits.max_assets
                or sum(map(len, files.values())) + len(inventory) > self.limits.max_asset_bytes):
            raise RendererInputError()
        with super()._private_job(serialized, {**files, _INVENTORY: inventory}, binary, options) as job:
            yield job

    @staticmethod
    def _validate_records(raw, report, *, max_pages=200):
        try:
            values = json.loads(raw)
            expected = expected_content_inventory(report)
            if not isinstance(values, list) or not values:
                raise ValueError()
            records = []
            charts = {'chart:' + chart.id: chart for chart in report.chart_series}
            for value in values:
                if not isinstance(value, dict) or type(value.get('page')) is not int or not 1 <= value['page'] <= max_pages:
                    raise ValueError()
                kind, content_id, page = value.get('kind'), value.get('content_id'), value['page']
                if kind in ('content', 'page'):
                    if (set(value) != {'kind', 'content_id', 'page'}
                            or (kind == 'page' and content_id != 'page-shell')
                            or (kind == 'content' and (content_id not in expected or content_id in charts))):
                        raise ValueError()
                    records.append(DossierRecord(kind, page, content_id))
                elif kind == 'chart':
                    # La serie disegnata è la vista dell'inventario (`chart_view`),
                    # non `chart.series` del modello v1: il modello resta fermo
                    # agli anni di piano, la vista espone tutto il timeline.
                    chart_id = content_id[len('chart:'):] if content_id.startswith('chart:') else ''
                    view = chart_view(report, chart_id) if chart_id else None
                    # Rilievo 1: il grafico con colonna KPI si dichiara largo 118 mm
                    # (grid a due colonne in typst), gli altri restano a 178.
                    declared = Decimal(chart_marker_width_mm(report, chart_id)) if chart_id else Decimal(-1)
                    if (view is None or set(value) != {'kind', 'content_id', 'page', 'width_mm', 'height_mm',
                            'measured_width_mm', 'measured_height_mm', 'unit', 'categories', 'series', 'thresholds'}
                            or value['unit'] != view['unit'] or value['categories'] != view['categories']
                            or value['series'] != view['series'] or value['thresholds'] != view['thresholds']
                            or any(not isinstance(value[k], str) or not Decimal(value[k]).is_finite()
                                   or Decimal(value[k]) != literal for k, literal in (
                                ('width_mm', declared), ('measured_width_mm', declared),
                                ('height_mm', Decimal(94)), ('measured_height_mm', Decimal(94))))):
                        raise ValueError()
                    # Store the validated marker; the inventory view is canonical.
                    records.append(DossierRecord('content', page, content_id))
                elif kind == 'slot':
                    if (set(value) != {'kind', 'content_id', 'page', 'width_pt', 'height_pt', 'font_size_pt', 'max_lines'}
                            or content_id != 'note-slot' or value['font_size_pt'] != '9'
                            or type(value['max_lines']) is not int or value['max_lines'] != 4):
                        raise ValueError()
                    for key, mm in (('width_pt', 178), ('height_pt', 18)):
                        if (not isinstance(value[key], str) or not Decimal(value[key]).is_finite()
                                or abs(Decimal(value[key]) - Decimal(mm) * _PT_PER_MM) > Decimal('0.001')):
                            raise ValueError()
                    records.append(DossierRecord(kind, page, content_id, value['width_pt'],
                                                 value['height_pt'], value['font_size_pt'], value['max_lines']))
                else:
                    raise ValueError()
            _validate_inventory(records, expected, max_pages)
            return tuple(records)
        except (KeyError, TypeError, ValueError, ArithmeticError):
            raise RendererCompileError() from None


def _validate_inventory(records, expected, max_pages):
    contents = [record for record in records if record.kind == 'content']
    pages = sorted({record.page for record in records})
    if (not pages or pages[-1] > max_pages or pages != list(range(1, pages[-1] + 1))
            or [record.content_id for record in contents] != list(expected)
            or not contents or contents[0].content_id != 'cover' or contents[0].page != 1
            or [r.page for r in contents] != sorted(r.page for r in contents)
            or sorted({r.page for r in contents}) != pages):
        raise ValueError('measured contents do not exactly cover the canonical inventory')
    for kind in ('page', 'slot'):
        if sorted(record.page for record in records if record.kind == kind) != pages:
            raise ValueError('each physical page requires one shell and one comment slot')
    for page in pages:
        sections = {expected[record.content_id] for record in contents if record.page == page}
        if len(sections) != 1:
            raise ValueError('physical pages cannot mix logical sections')


def build_editorial_plan(report: FinalReportModelV2, measurement: LayoutMeasurement) -> EditorialPlan:
    """Bind semantic content anchors to actual pages, including appendix continuations."""
    if (not isinstance(report, FinalReportModelV2) or type(measurement) is not LayoutMeasurement
            or measurement.source_hash != report.source_hash or report.source_hash != report.calculate_source_hash()
            or measurement.model_hash != report.model_hash or report.model_hash != report.calculate_model_hash()
            or type(measurement.page_count) is not int or not 1 <= measurement.page_count <= 200
            or type(measurement.records) is not tuple
            or any(type(record) is not DossierRecord for record in measurement.records)
            or not isinstance(measurement.layout_version, str)
            or not measurement.layout_version.endswith('+native-charts-1+editorial-3')):
        raise ValueError('measurement does not bind to the complete dossier')
    for digest in (measurement.font_hash, measurement.layout_hash, measurement.asset_hash):
        if not isinstance(digest, str) or len(digest) != 64 or any(char not in '0123456789abcdef' for char in digest):
            raise ValueError('invalid measured asset identity')
    expected = expected_content_inventory(report)
    records = measurement.records
    # Revalidate immutable records: callers cannot forge a new slot or remove content.
    for record in records:
        if type(record.page) is not int or not 1 <= record.page <= measurement.page_count:
            raise ValueError('invalid measured page')
        if record.kind == 'slot':
            try:
                slot = EditorialNoteSlot(width_pt=record.width_pt, height_pt=record.height_pt,
                                         font_size_pt=record.font_size_pt, max_lines=record.max_lines)
                if (abs(slot.width_pt - Decimal(178) * _PT_PER_MM) > Decimal('0.001')
                        or abs(slot.height_pt - Decimal(18) * _PT_PER_MM) > Decimal('0.001')
                        or slot.font_size_pt != 9 or slot.max_lines != 4 or record.content_id != 'note-slot'):
                    raise ValueError()
            except (TypeError, ValueError, ArithmeticError):
                raise ValueError('invalid measured note slot') from None
        elif (record.kind not in ('content', 'page')
                or record.kind == 'page' and record.content_id != 'page-shell'
                or any(getattr(record, field) is not None for field in ('width_pt', 'height_pt', 'font_size_pt', 'max_lines'))):
            raise ValueError('invalid measured content marker')
    _validate_inventory(records, expected, measurement.page_count)
    if max(record.page for record in records) != measurement.page_count:
        raise ValueError('declared page count differs from actual layout')
    row_lookup = {'row:' + statement.id + ':' + row.id: (statement.id, row.id)
                  for statement in report.detailed_statements for row in statement.rows}
    pages = []
    for number in range(1, measurement.page_count + 1):
        content_ids = [record.content_id for record in records if record.kind == 'content' and record.page == number]
        slot_record = next(record for record in records if record.kind == 'slot' and record.page == number)
        parts = OrderedDict()
        for content_id in content_ids:
            if content_id in row_lookup:
                statement_id, row_id = row_lookup[content_id]
                parts.setdefault(statement_id, []).append(row_id)
        anchor = content_ids[0]
        identity = canonical_hash(anchor, exclude_volatile=False)
        pages.append(EditorialPage(id='page:' + identity, section_id=expected[anchor], content_ids=content_ids,
            table_parts=[EditorialTablePart(statement_id=key, row_ids=ids) for key, ids in parts.items()],
            note_id='note:' + identity, note_slot=EditorialNoteSlot(width_pt=slot_record.width_pt,
                height_pt=slot_record.height_pt, font_size_pt=slot_record.font_size_pt, max_lines=slot_record.max_lines)))
    expected_rows = [(s.id, row.id) for s in report.detailed_statements for row in s.rows]
    actual_rows = [(part.statement_id, row_id) for page in pages for part in page.table_parts for row_id in part.row_ids]
    if actual_rows != expected_rows:
        raise ValueError('full appendix row inventory must be preserved exactly once')
    payload = dict(layout_version=measurement.layout_version + ':' + measurement.layout_hash,
                   font_version=measurement.font_hash, asset_version=measurement.asset_hash,
                   source_hash=measurement.source_hash, plan_hash='0' * 64, pages=pages)
    provisional = EditorialPlan.model_validate(payload, context={'skip_hash_validation': True})
    payload['plan_hash'] = provisional.calculate_plan_hash()
    return EditorialPlan.model_validate(payload)


def prepare_editorial_report(report: FinalReportModelV2, probe: DossierLayoutProbe) -> FinalReportModelV2:
    """Read-only preparation; no AI, persistence, or reuse of notes from a changed plan."""
    payload = report.model_dump(mode='python')
    payload.update(editorial_plan=None, editorial_notes=[],
                   editorial_readiness=EditorialReadiness(status='pending', reasons=['Commenti per pagina da preparare.']))
    provisional = FinalReportModelV2.model_validate(payload, context={'skip_hash_validation': True})
    payload['model_hash'] = provisional.calculate_model_hash()
    clean = FinalReportModelV2.model_validate(payload)
    plan = build_editorial_plan(clean, probe.measure_layout(clean))
    payload['editorial_plan'] = plan
    if report.editorial_plan is not None:
        if report.editorial_plan.plan_hash == plan.plan_hash:
            payload['editorial_notes'] = list(report.editorial_notes)
            payload['editorial_readiness'] = report.editorial_readiness
        elif any(note.provenance == 'user' for note in report.editorial_notes):
            raise ValueError('layout changed; manual notes require explicit reassociation')
    provisional = FinalReportModelV2.model_validate(payload, context={'skip_hash_validation': True})
    payload['model_hash'] = provisional.calculate_model_hash()
    prepared = FinalReportModelV2.model_validate(payload)
    if prepared.editorial_notes:
        verify_editorial_layout(prepared, probe)
    return prepared


def verify_editorial_layout(report: FinalReportModelV2, probe: DossierLayoutProbe) -> LayoutMeasurement:
    """Controlled reflow check before snapshot/export: reject drift rather than reassociate notes."""
    if report.editorial_plan is None:
        raise ValueError('editorial plan is required')
    measurement = probe.measure_layout(report)
    actual = build_editorial_plan(report, measurement)
    if actual.plan_hash != report.editorial_plan.plan_hash:
        raise ValueError('editorial layout changed; prepare a new plan before regenerating page notes')
    return measurement
