"""Rotta Word del Business plan: gemella della PDF (ownership, final solo se ready), file che si apre, nessuna AI."""
import io

import pytest
from docx import Document

from tests.test_final_report_endpoint import client, _url  # noqa: F401  fixture condivisa

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _bp(client, scenario=None):  # noqa: F811
    sid = scenario if scenario is not None else client.ids["scenario"]
    return f"/api/v1/companies/{client.ids['company']}/scenarios/{sid}/business-plan/docx"


def test_word_reale_sul_fixture_minimo(client, monkeypatch):  # noqa: F811
    from app.services import ai_comments_service
    monkeypatch.setattr(ai_comments_service, "generate_final_report_narrative",
                        lambda *a, **k: pytest.fail("il Business plan non chiama l'AI"))
    r = client.post(_bp(client), json={"document_state": "draft"})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == DOCX and r.content.startswith(b"PK")
    assert '.docx"' in r.headers["content-disposition"] and r.headers["cache-control"] == "no-store"
    assert "BOZZA" in Document(io.BytesIO(r.content)).sections[0].header.paragraphs[0].text


def test_scenario_altrui_404(client):  # noqa: F811
    assert client.post(_bp(client, client.ids["foreign"]), json={}).status_code == 404


def test_campo_in_piu_422(client):  # noqa: F811
    assert client.post(_bp(client), json={"document_state": "draft", "grayscale": True}).status_code == 422


def test_final_richiede_ready(client, monkeypatch):  # noqa: F811
    from types import SimpleNamespace
    from app.services import business_plan_pdf_service as bp_service
    report = SimpleNamespace(readiness=SimpleNamespace(status="draft"))
    monkeypatch.setattr(bp_service, "assemble_final_report", lambda *a, **k: report)
    assert client.post(_bp(client), json={"document_state": "final"}).status_code == 409


def test_nome_file_word():
    from app.services import business_plan_pdf_service as bp_service
    from app.services import infrannuale_pdf_service as inf_service
    assert bp_service.filenames("X", [2027, 2029], ext="docx")[0] == "Business plan X 2027-2029.docx"
    assert inf_service.filenames("X", "6M 2026", ext="docx")[1] == "Report infrannuale X 6M 2026.docx"
