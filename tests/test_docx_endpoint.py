"""Rotta Word del report infrannuale: gemella della PDF (ownership, 400, 422), file che si apre, nessuna AI."""
import io

import pytest
from docx import Document

from tests.test_inf_endpoint import AMBIENTA, SCENARIO, client  # noqa: F401  fixture condivisa

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _url(company=AMBIENTA, scenario=SCENARIO):
    return f"/api/v1/companies/{company}/scenarios/{scenario}/infrannuale/docx"


def test_word_reale_senza_ai(client, monkeypatch):  # noqa: F811
    import anthropic
    monkeypatch.setattr(anthropic.Anthropic, "__init__", lambda *a, **k: pytest.fail("il Word non chiama l'AI"))
    r = client.post(_url(), json={})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == DOCX and r.content.startswith(b"PK")
    assert r.headers["content-disposition"].startswith('attachment; filename="Report infrannuale AMBIENTA 6M 2026.docx"')
    assert "filename*=UTF-8''" in r.headers["content-disposition"] and r.headers["cache-control"] == "no-store"
    Document(io.BytesIO(r.content))


def test_scenario_altrui_404(client):  # noqa: F811
    from app.core.auth import get_current_user_id
    from app.main import app
    owner = app.dependency_overrides[get_current_user_id]
    app.dependency_overrides[get_current_user_id] = lambda: "un-altro-utente"
    try:
        assert client.post(_url(), json={}).status_code == 404
    finally:
        app.dependency_overrides[get_current_user_id] = owner


def test_scenario_non_infrannuale_400(client):  # noqa: F811
    if client.ids["budget"] is None:
        pytest.skip("nessuno scenario budget per AMBIENTA")
    assert client.post(_url(scenario=client.ids["budget"]), json={}).status_code == 400


def test_contratto_stretto(client):  # noqa: F811
    assert client.post(_url(), json={"avviso_commenti": False}).status_code == 422
