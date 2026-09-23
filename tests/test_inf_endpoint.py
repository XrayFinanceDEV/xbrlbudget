"""Rotta del report infrannuale: ownership, scenario non infrannuale, contratto stretto, render reale, nessuna AI.

Gira su una copia del DB locale (regola del proprietario: niente bilanci inventati); senza DB si salta.
"""
import shutil
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

SRC = Path("/home/peter/DEV/budget/financial_analysis.db")
AMBIENTA, SCENARIO = 575, 17


@pytest.fixture(scope="module")
def client():
    if not SRC.is_file():
        pytest.skip("DB locale assente")
    from app.core.auth import get_current_user_id
    from app.core.database import get_db
    from app.main import app
    from database.models import BudgetScenario, Company

    tmp = Path(tempfile.mkdtemp()) / "db.sqlite"
    shutil.copyfile(SRC, tmp)
    Session = sessionmaker(bind=create_engine(f"sqlite:///{tmp}"))
    with Session() as s:
        owner = s.get(Company, AMBIENTA).user_id
        budget = s.query(BudgetScenario).filter(BudgetScenario.company_id == AMBIENTA,
                                                BudgetScenario.scenario_type != "infrannuale").first()
        ids = {"budget": budget.id if budget else None}

    def _db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user_id] = lambda: owner
    c = TestClient(app)
    c.ids = ids
    yield c
    app.dependency_overrides.clear()


def _url(company=AMBIENTA, scenario=SCENARIO):
    return f"/api/v1/companies/{company}/scenarios/{scenario}/infrannuale/pdf"


def test_render_reale_senza_ai(client, monkeypatch):
    import anthropic
    monkeypatch.setattr(anthropic.Anthropic, "__init__", lambda *a, **k: pytest.fail("il PDF non chiama l'AI"))
    r = client.post(_url(), json={})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf" and r.content.startswith(b"%PDF")
    cd = r.headers["content-disposition"]
    assert cd.startswith('attachment; filename="Report infrannuale AMBIENTA 6M 2026.pdf"')
    assert "filename*=UTF-8''" in cd
    assert r.headers["cache-control"] == "no-store"


def test_scenario_altrui_404(client):
    from app.core.auth import get_current_user_id
    from app.main import app
    owner = app.dependency_overrides[get_current_user_id]
    app.dependency_overrides[get_current_user_id] = lambda: "un-altro-utente"
    try:
        assert client.post(_url(), json={}).status_code == 404
    finally:
        app.dependency_overrides[get_current_user_id] = owner


def test_scenario_non_infrannuale_400(client):
    if client.ids["budget"] is None:
        pytest.skip("nessuno scenario budget per AMBIENTA")
    assert client.post(_url(scenario=client.ids["budget"]), json={}).status_code == 400


def test_contratto_stretto(client):
    assert client.post(_url(), json={"avviso_commenti": False}).status_code == 422


def test_nome_file_ascii():
    from app.services.infrannuale_pdf_service import filenames
    full, ascii_name = filenames("Società Ünicode — ČR", "6M 2026")
    assert full == "Report infrannuale Società Ünicode — ČR 6M 2026.pdf"
    assert ascii_name.isascii() and ascii_name.endswith(".pdf")
