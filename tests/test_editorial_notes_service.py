"""Pure persistence-service guards that do not require a native Typst run."""
from datetime import timedelta
import hashlib
import pytest

from app.renderers.typst.dossier_catalog import expected_content_inventory
from app.schemas.final_report import canonical_hash
from app.schemas.final_report_v2 import EditorialNoteSlot, EditorialPage, EditorialPlan, EditorialTablePart
from app.services import editorial_notes_service as service
from tests.test_final_report_v2 import fixture_report


def _inventory_plan(report):
    inventory = expected_content_inventory(report)
    detail_rows = {
        "row:" + statement.id + ":" + row.id: (statement.id, row.id)
        for statement in report.detailed_statements for row in statement.rows
    }
    pages = []
    for content_id, section_id in inventory.items():
        identity = canonical_hash(content_id, exclude_volatile=False)
        parts = []
        if content_id in detail_rows:
            statement_id, row_id = detail_rows[content_id]
            parts = [EditorialTablePart(statement_id=statement_id, row_ids=[row_id])]
        pages.append(EditorialPage(
            id="page:" + identity, note_id="note:" + identity, section_id=section_id,
            content_ids=[content_id], table_parts=parts,
            note_slot=EditorialNoteSlot(width_pt="504.57", height_pt="51.02", font_size_pt="9", max_lines=4),
        ))
    payload = dict(layout_version="layout", font_version="font", asset_version="asset",
                   source_hash=report.source_hash, plan_hash="0" * 64, pages=pages)
    draft = EditorialPlan.model_validate(payload, context={"skip_hash_validation": True})
    payload["plan_hash"] = draft.calculate_plan_hash()
    return EditorialPlan.model_validate(payload)


def test_body_hash_ignores_assembly_timestamp_but_binds_narrative():
    report = fixture_report()
    rebuilt = report.model_copy(update={"generated_at": report.generated_at + timedelta(seconds=1)})
    assert service._body_hash(rebuilt) == service._body_hash(report)
    changed = report.model_copy(update={"narrative": [*report.narrative[:-1], report.narrative[-1].model_copy(update={"text": "Testo modificato"})]})
    assert service._body_hash(changed) != service._body_hash(report)


def test_plan_inventory_binds_table_parts_to_their_physical_page():
    report = fixture_report()
    plan = _inventory_plan(report)
    assert service._valid_plan_inventory(report, plan)
    detailed_pages = [page for page in plan.pages if page.table_parts]
    source, target = detailed_pages[:2]
    moved = plan.model_dump(mode="python")
    moved["pages"][plan.pages.index(target)]["table_parts"] = source.table_parts
    moved["pages"][plan.pages.index(source)]["table_parts"] = []
    moved["plan_hash"] = "0" * 64
    draft = EditorialPlan.model_validate(moved, context={"skip_hash_validation": True})
    moved["plan_hash"] = draft.calculate_plan_hash()
    assert not service._valid_plan_inventory(report, EditorialPlan.model_validate(moved))


def test_layout_and_fit_probes_share_the_single_renderer_worker_budget():
    layout = service.get_dossier_probe()
    fit = service.get_note_fit_probe()
    assert service.get_dossier_probe() is layout
    assert service.get_note_fit_probe() is fit
    assert fit._slots is layout._slots


def test_automatic_prose_definition_changes_invalidate_fit_signature_and_require_worker_reload(tmp_path, monkeypatch):
    from app.renderers.typst.runtime import RendererUnavailable
    original = service.current_render_signature()
    changed = tmp_path / "commentary.py"
    changed.write_bytes(service._COMMENTARY_SOURCE.read_bytes() + b"\n# new generator revision\n")
    monkeypatch.setattr(service, "_COMMENTARY_SOURCE", changed)
    with pytest.raises(RendererUnavailable):
        service.current_render_signature()
    monkeypatch.setattr(service, "_COMMENTARY_HASH", hashlib.sha256(changed.read_bytes()).hexdigest())
    assert service.current_render_signature() != original
