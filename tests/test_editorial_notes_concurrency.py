"""Real measured plans: partial AI, concurrency, and recoverable manual notes."""
from decimal import Decimal
from pathlib import Path

import pytest

from tests.test_final_report_endpoint import client, _url


@pytest.fixture
def prepared(client):
    if not (Path(__file__).resolve().parents[1] / "tools/typst/bin/typst").is_file():
        pytest.skip("Install pinned Typst for editorial workflow tests")
    path = _url(client, client.ids["scenario"]) + "/editorial"
    baseline = client.get(path).json()
    response = client.post(path + "/prepare", json={"source_hash": baseline["report"]["source_hash"], "expected_revision": 0})
    assert response.status_code == 200, response.text
    return path, response.json()


def request(session, notes):
    report = session["report"]
    return {"source_hash": report["source_hash"], "plan_hash": report["editorial_plan"]["plan_hash"],
        "expected_revision": session["revision"], "notes": notes}


def test_partial_ai_keeps_prior_comments_and_persists_only_fitting_known_results(client, prepared, monkeypatch):
    from app.services import editorial_notes_service as service
    from database.report_editorial import ReportEditorialNote
    path, session = prepared
    chosen = session["report"]["editorial_notes"][:3]
    monkeypatch.setattr(service, "_generate_with_provider", lambda contexts: {
        chosen[0]["id"]: "Nota AI breve sui contenuti disponibili.", chosen[1]["id"]: "W" * 300,
    })
    response = client.post(path + "/generate", json=request(session, [{"id": note["id"], "revision": 0} for note in chosen]))
    assert response.status_code == 200, response.text
    latest = response.json()
    notes = {note["id"]: note for note in latest["report"]["editorial_notes"]}
    assert (notes[chosen[0]["id"]]["provenance"], notes[chosen[0]["id"]]["revision"]) == ("ai", 1)
    assert {key: value for key, value in notes[chosen[1]["id"]].items() if key != "updated_at"} == {key: value for key, value in chosen[1].items() if key != "updated_at"}
    assert {key: value for key, value in notes[chosen[2]["id"]].items() if key != "updated_at"} == {key: value for key, value in chosen[2].items() if key != "updated_at"}
    assert {warning["note_id"] for warning in latest["generation_warnings"]} == {chosen[1]["id"], chosen[2]["id"]}
    with client.sessions() as db:
        assert db.query(ReportEditorialNote).count() == 1
    repeated = client.post(path + "/prepare", json={"source_hash": latest["report"]["source_hash"], "expected_revision": latest["revision"]})
    assert repeated.status_code == 200, repeated.text
    assert next(note for note in repeated.json()["report"]["editorial_notes"] if note["id"] == chosen[0]["id"]) == notes[chosen[0]["id"]]


def test_unknown_provider_id_rejects_whole_batch_without_writing(client, prepared, monkeypatch):
    from app.services import editorial_notes_service as service
    from database.report_editorial import ReportEditorialNote
    path, session = prepared
    chosen = session["report"]["editorial_notes"][:2]
    monkeypatch.setattr(service, "_generate_with_provider", lambda contexts: {chosen[0]["id"]: "Nota", "unknown": "Fuori contesto"})
    response = client.post(path + "/generate", json=request(session, [{"id": note["id"], "revision": 0} for note in chosen]))
    assert response.status_code == 200, response.text
    assert response.json()["revision"] == session["revision"]
    assert len(response.json()["generation_warnings"]) == 2
    with client.sessions() as db:
        assert db.query(ReportEditorialNote).count() == 0


def test_manual_save_during_provider_call_wins_and_stale_ai_is_rejected(client, prepared, monkeypatch):
    from app.services import editorial_notes_service as service
    path, session = prepared
    chosen = session["report"]["editorial_notes"][0]
    def provider(contexts):
        saved = client.put(path + "/notes", json=request(session, [{"id": chosen["id"], "revision": 0, "text": "Modifica manuale concorrente."}]))
        assert saved.status_code == 200, saved.text
        return {chosen["id"]: "Risposta AI ormai superata."}
    monkeypatch.setattr(service, "_generate_with_provider", provider)
    response = client.post(path + "/generate", json=request(session, [{"id": chosen["id"], "revision": 0}]))
    assert response.status_code == 409, response.text
    latest = client.get(path).json()
    note = next(note for note in latest["report"]["editorial_notes"] if note["id"] == chosen["id"])
    assert (note["text"], note["provenance"]) == ("Modifica manuale concorrente.", "user")


def test_economic_change_during_provider_call_is_rejected_even_without_editorial_revision_change(client, prepared, monkeypatch):
    from app.services import editorial_notes_service as service
    from database.models import FinancialYear
    from database.report_editorial import ReportEditorialNote
    path, session = prepared
    chosen = session["report"]["editorial_notes"][0]
    def provider(contexts):
        with client.sessions() as db:
            base = db.query(FinancialYear).filter_by(company_id=client.ids["company"], year=2026).one()
            base.income_statement.ce01_ricavi_vendite = Decimal("123")
            db.commit()
        return {chosen["id"]: "Risposta sulla base precedente."}
    monkeypatch.setattr(service, "_generate_with_provider", provider)
    response = client.post(path + "/generate", json=request(session, [{"id": chosen["id"], "revision": 0}]))
    assert response.status_code == 409, response.text
    with client.sessions() as db:
        assert db.query(ReportEditorialNote).count() == 0


def test_manual_archive_survives_source_change_and_explicit_reassociation(client, prepared):
    from database.models import FinancialYear
    from database.report_editorial import ReportEditorialNote
    path, session = prepared
    chosen = session["report"]["editorial_notes"][0]
    saved = client.put(path + "/notes", json=request(session, [{"id": chosen["id"], "revision": 0, "text": "Testo manuale da conservare."}]))
    assert saved.status_code == 200, saved.text
    manual = next(note for note in saved.json()["report"]["editorial_notes"] if note["id"] == chosen["id"])
    current_reference = request(saved.json(), [{"id": chosen["id"], "revision": 1, "text": "Copia", "from_note": {"id": manual["id"], "plan_hash": manual["plan_hash"], "revision": 1}}])
    assert client.put(path + "/notes", json=current_reference).status_code == 422
    with client.sessions() as db:
        base = db.query(FinancialYear).filter_by(company_id=client.ids["company"], year=2026).one()
        base.income_statement.ce01_ricavi_vendite = Decimal("124")
        db.commit()
    stale = client.get(path).json()
    assert stale["report"]["editorial_plan"] is None
    assert stale["archived_notes"][0]["text"] == manual["text"]
    refreshed = client.post(path + "/prepare", json={"source_hash": stale["report"]["source_hash"], "expected_revision": stale["revision"]})
    assert refreshed.status_code == 200, refreshed.text
    latest = refreshed.json()
    current = latest["report"]["editorial_notes"][0]
    assert current["provenance"] == "automatic"
    associated = client.put(path + "/notes", json=request(latest, [{"id": current["id"], "revision": 0, "text": manual["text"],
        "from_note": {"id": manual["id"], "plan_hash": manual["plan_hash"], "revision": manual["revision"]}}]))
    assert associated.status_code == 200, associated.text
    assert associated.json()["archived_notes"][0]["text"] == manual["text"]
    with client.sessions() as db:
        assert db.query(ReportEditorialNote).count() == 2
