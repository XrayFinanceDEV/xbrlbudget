"""M2-02A provisional plan: group only metadata measured by real Typst pages."""
from dataclasses import replace
import os
from pathlib import Path

import pytest

from app.renderers.typst.base_plan import build_measured_base_plan
from tests.test_final_report_v2 import fixture_report
from tests.test_typst_layout_probe import ROOT
from app.renderers.typst import Compiler, TemplateBundle
from app.renderers.typst.layout_probe import TypstLayoutProbe


@pytest.fixture
def measured_base(tmp_path):
    binary = Path(os.environ.get('TYPST_TEST_BINARY', ROOT / 'tools/typst/bin/typst'))
    if not binary.is_file():
        pytest.skip('Install pinned Typst to run measured planner integration tests')
    report = fixture_report('bilancio', [2027, 2028, 2029])
    renderer = TypstLayoutProbe(
        Compiler.from_manifest(ROOT / 'tools/typst/manifest.json', binary),
        TemplateBundle(ROOT / 'backend/app/renderers/typst/templates/dossier-base'), temp_root=tmp_path,
    )
    return report, renderer.measure_layout(report)


def test_base_plan_uses_actual_page_groups_with_stable_semantic_ids(measured_base):
    report, measurement = measured_base
    plan = build_measured_base_plan(report, measurement)
    assert plan.scope == 'base' and plan.finalized is False
    assert plan.page_count == len(plan.pages) == measurement.page_count
    assert plan.plan_hash == plan.calculate_plan_hash()
    assert all(page.id == f'page:{page.anchor}' and page.note_id == f'note:{page.anchor}'
               for page in plan.pages)
    assert plan.pages[0].anchor == 'cover'
    assert plan.pages[0].section_id == 'cover' and plan.pages[0].table_parts == ()
    assert all(page.content_ids for page in plan.pages)

    expected = [(statement.id, row.id) for statement in report.detailed_statements for row in statement.rows]
    actual = [(part.statement_id, row_id) for page in plan.pages for part in page.table_parts
              for row_id in part.row_ids]
    assert actual == expected
    for page in plan.pages[1:]:
        assert len(page.table_parts) == 1
        assert page.section_id == page.table_parts[0].statement_id
        assert page.anchor == page.content_ids[0]


@pytest.mark.parametrize('field,value', [
    ('font_hash', 'f' * 64), ('layout_hash', 'e' * 64), ('asset_hash', 'd' * 64),
])
def test_base_plan_hash_binds_all_measured_asset_identities(measured_base, field, value):
    report, measurement = measured_base
    original = build_measured_base_plan(report, measurement)
    changed = build_measured_base_plan(report, replace(measurement, **{field: value}))
    assert changed.plan_hash != original.plan_hash


def test_base_plan_hash_binds_source_but_not_narrative_model_identity(measured_base):
    report, measurement = measured_base
    changed = report.model_copy(deep=True)
    changed.company.name += ' S.r.l.'
    changed.source_hash = changed.calculate_source_hash()
    changed.model_hash = changed.calculate_model_hash()
    original = build_measured_base_plan(report, measurement)
    rebound = replace(measurement, source_hash=changed.source_hash, model_hash=changed.model_hash)
    assert build_measured_base_plan(changed, rebound).plan_hash != original.plan_hash
    with pytest.raises(ValueError, match='do not bind'):
        build_measured_base_plan(changed, measurement)

    narrative_only = report.model_copy(deep=True)
    narrative_only.narrative[0].text = 'Una nuova nota narrativa non cambia la geometria di base.'
    narrative_only.model_hash = narrative_only.calculate_model_hash()
    assert narrative_only.calculate_source_hash() == report.source_hash
    refreshed = replace(measurement, model_hash=narrative_only.model_hash)
    narrative_plan = build_measured_base_plan(narrative_only, refreshed)
    assert narrative_plan.model_hash != original.model_hash
    assert narrative_plan.plan_hash == original.plan_hash


@pytest.mark.parametrize('forge', ['missing_row', 'missing_shell', 'duplicate_content', 'wrong_page_count'])
def test_base_plan_rejects_forged_measurement_inventory(measured_base, forge):
    report, measurement = measured_base
    records = measurement.records
    if forge == 'missing_row':
        first_row = next(record for record in records if record.kind == 'row')
        records = tuple(record for record in records if record is not first_row)
    elif forge == 'missing_shell':
        records = tuple(record for record in records if record.kind != 'page' or record.page != 1)
    elif forge == 'duplicate_content':
        records = records + (next(record for record in records if record.kind == 'content'),)
    else:
        measurement = replace(measurement, page_count=measurement.page_count + 1)
    with pytest.raises(ValueError):
        build_measured_base_plan(report, replace(measurement, records=records))


def test_valid_cross_statement_duplicate_row_ids_have_distinct_page_and_note_anchors(tmp_path):
    from app.schemas.final_report_v2 import FinalReportModelV2
    binary = Path(os.environ.get('TYPST_TEST_BINARY', ROOT / 'tools/typst/bin/typst'))
    if not binary.is_file():
        pytest.skip('Install pinned Typst to run measured planner integration tests')
    report = fixture_report()
    income, balance = report.detailed_statements[:2]
    old_root = income.rows[0].id
    shared_root = balance.rows[0].id
    income.rows[0].id = shared_root
    for row in income.rows:
        if row.parent_id == old_root:
            row.parent_id = shared_root
    report.source_hash = report.calculate_source_hash()
    report.model_hash = report.calculate_model_hash()
    # The shared ID is legal: uniqueness belongs to each statement, not the report.
    report = FinalReportModelV2.model_validate_json(report.model_dump_json())
    renderer = TypstLayoutProbe(
        Compiler.from_manifest(ROOT / 'tools/typst/manifest.json', binary),
        TemplateBundle(ROOT / 'backend/app/renderers/typst/templates/dossier-base'), temp_root=tmp_path,
    )
    measurement = renderer.measure_layout(report)
    plan = build_measured_base_plan(report, measurement)
    assert len({p.id for p in plan.pages}) == len({p.note_id for p in plan.pages}) == plan.page_count
    assert any(p.anchor == f'row:income_statement:{shared_root}' for p in plan.pages)
    assert any(p.anchor == f'row:balance_sheet:{shared_root}' for p in plan.pages)
    shared = [r for r in measurement.records if r.row_id == shared_root]
    assert len(shared) == 2 and shared[0].content_id != shared[1].content_id
