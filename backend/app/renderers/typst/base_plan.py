"""Provisional base-only grouping of metadata measured by the pinned Typst runtime."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Literal

from app.schemas.final_report import canonical_hash
from app.schemas.final_report_v2 import FinalReportModelV2

from .layout_probe import LayoutMeasurement, LayoutProbeRecord, TypstLayoutProbe
from .runtime import RendererCompileError

_SHA_LENGTH = 64


@dataclass(frozen=True)
class BaseTablePart:
    statement_id: str
    row_ids: tuple[str, ...]


@dataclass(frozen=True)
class BasePagePlan:
    """One measured physical page; it deliberately has no final editorial note binding."""
    id: str
    anchor: str
    section_id: str
    content_ids: tuple[str, ...]
    table_parts: tuple[BaseTablePart, ...]
    note_id: str


@dataclass(frozen=True)
class MeasuredBasePlan:
    """A reproducible base composition, pending M2-03 assets and final editorial planning."""
    scope: Literal['base']
    finalized: Literal[False]
    source_hash: str
    model_hash: str
    layout_version: str
    font_hash: str
    layout_hash: str
    asset_hash: str
    page_count: int
    pages: tuple[BasePagePlan, ...]
    plan_hash: str

    def hash_payload(self) -> dict:
        return {
            'scope': self.scope,
            'finalized': self.finalized,
            'source_hash': self.source_hash,
            'layout_version': self.layout_version,
            'font_hash': self.font_hash,
            'layout_hash': self.layout_hash,
            'asset_hash': self.asset_hash,
            'page_count': self.page_count,
            'pages': [
                {
                    'id': page.id,
                    'anchor': page.anchor,
                    'section_id': page.section_id,
                    'content_ids': list(page.content_ids),
                    'table_parts': [
                        {'statement_id': part.statement_id, 'row_ids': list(part.row_ids)}
                        for part in page.table_parts
                    ],
                    'note_id': page.note_id,
                }
                for page in self.pages
            ],
        }

    def calculate_plan_hash(self) -> str:
        return canonical_hash(self.hash_payload(), exclude_volatile=False)


def build_measured_base_plan(report: FinalReportModelV2, measurement: LayoutMeasurement) -> MeasuredBasePlan:
    """Group only exact Typst metadata; never estimate text dimensions in Python."""
    _validate_measurement_binding(report, measurement)
    expected_rows = [(statement.id, row.id) for statement in report.detailed_statements for row in statement.rows]
    rows = [record for record in measurement.records if record.kind == 'row']
    if [(record.statement_id, record.row_id) for record in rows] != expected_rows:
        raise ValueError('measurement row inventory does not exactly match source order')

    records_by_page: dict[int, list[LayoutProbeRecord]] = {page: [] for page in range(1, measurement.page_count + 1)}
    shells: dict[int, int] = {page: 0 for page in records_by_page}
    for record in measurement.records:
        if record.page not in records_by_page:
            raise ValueError('measurement page is outside declared page count')
        if record.kind == 'page':
            shells[record.page] += 1
        else:
            records_by_page[record.page].append(record)
    if any(count != 1 for count in shells.values()) or any(not records for records in records_by_page.values()):
        raise ValueError('measurement lacks exactly one page shell and body inventory per physical page')

    pages = tuple(_page_from_records(page, records) for page, records in records_by_page.items())
    if len({page.id for page in pages}) != len(pages) or len({page.note_id for page in pages}) != len(pages):
        raise ValueError('measurement produces duplicate semantic page anchors')
    provisional = MeasuredBasePlan(
        scope='base', finalized=False, source_hash=measurement.source_hash, model_hash=measurement.model_hash,
        layout_version=measurement.layout_version, font_hash=measurement.font_hash,
        layout_hash=measurement.layout_hash, asset_hash=measurement.asset_hash,
        page_count=measurement.page_count, pages=pages, plan_hash='',
    )
    return MeasuredBasePlan(**{**provisional.__dict__, 'plan_hash': provisional.calculate_plan_hash()})


def _page_from_records(page_number: int, records: list[LayoutProbeRecord]) -> BasePagePlan:
    content_ids = tuple(record.content_id for record in records)
    if len(content_ids) != len(set(content_ids)):
        raise ValueError('measurement duplicates content marker on a physical page')
    first = records[0]
    if first.kind == 'content':
        if page_number != 1 or first.content_id != 'cover' or len(records) != 1:
            raise ValueError('cover must be the only base content marker on page one')
        anchor, section_id, table_parts = 'cover', 'cover', ()
    else:
        if any(record.kind != 'row' for record in records):
            raise ValueError('unexpected non-row base content marker')
        statement_ids = {record.statement_id for record in records}
        if len(statement_ids) != 1:
            raise ValueError('a base physical page cannot mix statement tables')
        statement_id = first.statement_id
        if statement_id is None or any(record.row_id is None for record in records):
            raise ValueError('row marker is incomplete')
        anchor, section_id = first.content_id, statement_id
        table_parts = (BaseTablePart(statement_id, tuple(record.row_id for record in records if record.row_id is not None)),)
    return BasePagePlan(
        id=f'page:{anchor}', anchor=anchor, section_id=section_id, content_ids=content_ids,
        table_parts=table_parts, note_id=f'note:{anchor}',
    )


def _validate_measurement_binding(report: FinalReportModelV2, measurement: LayoutMeasurement) -> None:
    if not isinstance(report, FinalReportModelV2) or not isinstance(measurement, LayoutMeasurement):
        raise ValueError('report and verified layout measurement are required')
    if (measurement.source_hash != report.source_hash or measurement.source_hash != report.calculate_source_hash()
            or measurement.model_hash != report.model_hash or measurement.model_hash != report.calculate_model_hash()):
        raise ValueError('measurement hashes do not bind to the supplied report')
    hashes = (measurement.source_hash, measurement.model_hash, measurement.font_hash,
              measurement.layout_hash, measurement.asset_hash)
    if (not isinstance(measurement.layout_version, str) or not measurement.layout_version
            or any(not isinstance(value, str) or len(value) != _SHA_LENGTH
                   or any(char not in '0123456789abcdef' for char in value) for value in hashes)
            or type(measurement.page_count) is not int or not 1 <= measurement.page_count <= 200):
        raise ValueError('measurement identity is invalid')
    if type(measurement.records) is not tuple or any(type(record) is not LayoutProbeRecord for record in measurement.records):
        raise ValueError('measurement records are not trusted probe records')
    values = []
    for record in measurement.records:
        value = {key: value for key, value in asdict(record).items() if value is not None}
        values.append(value)
    try:
        verified = TypstLayoutProbe._validate_records(
            json.dumps(values, separators=(',', ':')).encode('utf-8'), report, max_pages=200,
        )
    except (RendererCompileError, TypeError, ValueError):
        raise ValueError('measurement metadata inventory is invalid') from None
    if verified != measurement.records:
        raise ValueError('measurement metadata changed after probe validation')
    expected_pages = list(range(1, measurement.page_count + 1))
    observed_pages = sorted({record.page for record in measurement.records})
    if observed_pages != expected_pages or measurement.page_count != max(observed_pages):
        raise ValueError('measurement physical pages are not contiguous')
