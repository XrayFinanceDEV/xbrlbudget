"""Rotta del Business plan: ownership, final solo se ready, render reale sul fixture minimo, nessuna AI."""
from types import SimpleNamespace

import pytest

from app.services import business_plan_pdf_service as bp_service
from tests.test_final_report_endpoint import client, _url  # noqa: F401  fixture condivisa


def _bp(client, scenario=None):  # noqa: F811
    sid = scenario if scenario is not None else client.ids["scenario"]
    return f"/api/v1/companies/{client.ids['company']}/scenarios/{sid}/business-plan/pdf"


def test_render_reale_sul_fixture_minimo(client, monkeypatch):  # noqa: F811
    from app.services import ai_comments_service

    monkeypatch.setattr(ai_comments_service, "generate_final_report_narrative",
                        lambda *a, **k: pytest.fail("il Business plan non chiama l'AI"))
    response = client.post(_bp(client), json={"document_state": "draft"})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    assert "attachment;" in response.headers["content-disposition"]
    assert response.headers["cache-control"] == "no-store"


def test_scenario_altrui_404(client):  # noqa: F811
    assert client.post(_bp(client, client.ids["foreign"]), json={}).status_code == 404


def test_final_richiede_ready(client, monkeypatch):  # noqa: F811
    report = SimpleNamespace(readiness=SimpleNamespace(status="draft"))
    monkeypatch.setattr(bp_service, "assemble_final_report", lambda *a, **k: report)
    response = client.post(_bp(client), json={"document_state": "final"})
    assert response.status_code == 409


def test_contratto_richiesta_stretto(client):  # noqa: F811
    assert client.post(_bp(client), json={"document_state": "final", "grayscale": True}).status_code == 422


def test_nome_file_ascii():
    full, ascii_name = bp_service.filenames("Società Ünicode Ltd — ČR", [2027, 2029])
    assert full == "Business plan Società Ünicode Ltd — ČR 2027-2029.pdf"
    assert ascii_name.isascii() and ascii_name.endswith(".pdf")
