"""AI uses exact server content and rejects invented or duplicate note IDs."""
from collections import defaultdict
from types import SimpleNamespace

import pytest

from app.renderers.typst.editorial_inventory import expected_content_inventory
from app.services import editorial_notes_service as service
from tests.test_final_report_v2 import fixture_report


@pytest.mark.parametrize("workflow", ["infrannuale", "bilancio", "startup"])
def test_every_canonical_content_id_can_be_projected_without_client_context(workflow):
    report = fixture_report(workflow)
    original = report.model_dump_json()
    sections = defaultdict(list)
    for content_id, section_id in expected_content_inventory(report).items():
        sections[section_id].append(content_id)
    for section_id, content_ids in sections.items():
        page = SimpleNamespace(note_id="note:authorized", section_id=section_id, content_ids=content_ids)
        context = service._page_context(report, page)
        assert [item["id"] for item in context["content"]] == content_ids
        assert context["source_hash"] == report.source_hash
        assert "archived_notes" not in context and "editorial_notes" not in context
    assert report.model_dump_json() == original


def test_page_context_rejects_unknown_content():
    page = SimpleNamespace(note_id="note:x", section_id="unknown", content_ids=["other-company"])
    with pytest.raises(service.EditorialInputError):
        service._page_context(fixture_report(), page)


@pytest.mark.parametrize("notes,expected", [
    ([{"id": "note:a", "text": "Commento valido."}], {"note:a": "Commento valido."}),
    ([{"id": "note:a", "text": "Uno"}, {"id": "note:a", "text": "Due"}], {}),
    ([{"id": "other", "text": "Inventato"}], {}),
])
def test_structured_provider_binds_ids_and_keeps_short_literal_text(monkeypatch, notes, expected):
    import anthropic
    calls = []
    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(type="tool_use", name="editorial_notes", input={"notes": notes})])
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-only")
    monkeypatch.setattr(anthropic, "Anthropic", lambda **kwargs: SimpleNamespace(messages=SimpleNamespace(create=create)))
    contexts = [{"note_id": "note:a", "content": [{"value": "9007199254740993.12"}]}]
    assert service._generate_with_provider(contexts) == expected
    assert len(calls) == 1
    assert "9007199254740993.12" in calls[0]["messages"][0]["content"]
    assert calls[0]["tool_choice"] == {"type": "tool", "name": "editorial_notes"}


def test_provider_absent_does_not_import_or_generate(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert service._generate_with_provider([{"note_id": "note:a"}]) == {}
