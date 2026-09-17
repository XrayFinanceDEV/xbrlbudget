"""Tenant-safe explicit commentary API and backwards-compatible report reads."""
import pytest

from tests.test_final_report_endpoint import client, _url


def _editorial(client):
    return _url(client, client.ids["scenario"]) + "/editorial"


def test_session_get_is_read_only_and_v1_unchanged(client, monkeypatch):
    from app.services import editorial_notes_service as service
    from database.report_editorial import ReportEditorialNote, ReportEditorialState

    def forbidden(*args, **kwargs):
        pytest.fail("GET must not prepare layout or invoke AI")
    monkeypatch.setattr(service, "get_dossier_probe", forbidden)
    monkeypatch.setattr(service, "get_note_fit_probe", forbidden)
    response = client.get(_editorial(client))
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["revision"] == 0 and payload["archived_notes"] == []
    assert payload["report"]["schema_version"] == 2
    assert payload["report"]["document"]["title"] == "Report Budget 2027"
    assert len(payload["report"]["chart_series"]) == 16
    assert payload["report"]["editorial_plan"] is None
    with client.sessions() as db:
        assert db.query(ReportEditorialState).count() == db.query(ReportEditorialNote).count() == 0
    v1 = client.get(_url(client, client.ids["scenario"]))
    assert v1.status_code == 200 and v1.json()["schema_version"] == 1
    assert "editorial_plan" not in v1.json()
    v2 = client.get(_url(client, client.ids["scenario"]) + "?schema_version=2")
    assert v2.status_code == 200 and v2.json()["source_hash"] == payload["report"]["source_hash"]


@pytest.mark.parametrize("suffix,method", [("", "get"), ("/prepare", "post"), ("/notes", "put"), ("/generate", "post")])
def test_all_editorial_operations_reject_foreign_scenario(client, suffix, method):
    url = _url(client, client.ids["foreign"]) + "/editorial" + suffix
    kwargs = {}
    if method != "get":
        payload = dict(source_hash="a" * 64, expected_revision=0)
        if suffix != "/prepare":
            payload.update(plan_hash="b" * 64, notes=[{"id": "note:x", "revision": 0}])
        if suffix == "/notes":
            payload["notes"][0]["text"] = "Nota"
        kwargs["json"] = payload
    response = getattr(client, method)(url, **kwargs)
    assert response.status_code == 404, response.text


def test_prepare_detects_stale_source_before_native_work(client, monkeypatch):
    from app.services import editorial_notes_service as service
    def forbidden():
        pytest.fail("Invalid source must be rejected before native work")
    monkeypatch.setattr(service, "get_dossier_probe", forbidden)
    response = client.post(_editorial(client) + "/prepare", json={"source_hash": "a" * 64, "expected_revision": 0})
    assert response.status_code == 409, response.text


def test_request_rejects_browser_context_and_coerced_revision(client):
    response = client.post(_editorial(client) + "/prepare", json={
        "source_hash": "a" * 64, "expected_revision": "0", "context": {"revenue": "invented"},
    })
    assert response.status_code == 422


def test_real_prepare_save_and_reprepare_preserve_manual_note_and_all_page_coverage(client, monkeypatch):
    from pathlib import Path
    from database.report_editorial import ReportEditorialNote
    from database.models import BudgetScenario
    if not (Path(__file__).resolve().parents[1] / "tools/typst/bin/typst").is_file():
        pytest.skip("Install the pinned compiler for native editorial HTTP workflow")
    baseline = client.get(_editorial(client)).json()
    with client.sessions() as db:
        timestamp = db.get(BudgetScenario, client.ids["scenario"]).updated_at
    response = client.post(_editorial(client) + "/prepare", json={
        "source_hash": baseline["report"]["source_hash"], "expected_revision": baseline["revision"],
    })
    assert response.status_code == 200, response.text
    prepared = response.json()
    report = prepared["report"]
    assert report["editorial_readiness"]["status"] == "ready"
    assert {page["note_id"] for page in report["editorial_plan"]["pages"]} == {note["id"] for note in report["editorial_notes"]}
    assert all(note["provenance"] == "automatic" and note["revision"] == 0 for note in report["editorial_notes"])
    assert len({note["text"] for note in report["editorial_notes"]}) == len(report["editorial_notes"])
    with client.sessions() as db:
        assert db.query(ReportEditorialNote).count() == 0
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    missing_provider = client.post(_editorial(client) + "/generate", json={
        "source_hash": report["source_hash"], "plan_hash": report["editorial_plan"]["plan_hash"],
        "expected_revision": prepared["revision"], "notes": [{"id": item["id"], "revision": 0} for item in report["editorial_notes"][:2]],
    })
    assert missing_provider.status_code == 200, missing_provider.text
    assert len(missing_provider.json()["generation_warnings"]) == 2
    assert missing_provider.json()["revision"] == prepared["revision"]
    note = report["editorial_notes"][0]
    payload = dict(source_hash=report["source_hash"], plan_hash=report["editorial_plan"]["plan_hash"],
        expected_revision=prepared["revision"], notes=[{"id": note["id"], "revision": 0, "text": "Commento manuale verificato."}])
    saved = client.put(_editorial(client) + "/notes", json=payload)
    assert saved.status_code == 200, saved.text
    assert client.put(_editorial(client) + "/notes", json=payload).status_code == 409
    latest = saved.json()
    manual = next(item for item in latest["report"]["editorial_notes"] if item["id"] == note["id"])
    assert (manual["text"], manual["provenance"], manual["revision"]) == ("Commento manuale verificato.", "user", 1)
    protected = client.post(_editorial(client) + "/generate", json={
        "source_hash": report["source_hash"], "plan_hash": report["editorial_plan"]["plan_hash"],
        "expected_revision": latest["revision"], "notes": [{"id": manual["id"], "revision": manual["revision"]}],
    })
    assert protected.status_code == 409, protected.text
    oversized = {**payload, "expected_revision": latest["revision"], "notes": [{"id": note["id"], "revision": 1, "text": "W" * 300}]}
    assert client.put(_editorial(client) + "/notes", json=oversized).status_code == 422
    repeat = client.post(_editorial(client) + "/prepare", json={"source_hash": report["source_hash"], "expected_revision": latest["revision"]})
    assert repeat.status_code == 200, repeat.text
    after = next(item for item in repeat.json()["report"]["editorial_notes"] if item["id"] == note["id"])
    assert after == manual
    with client.sessions() as db:
        assert db.query(ReportEditorialNote).count() == 1
        assert db.get(BudgetScenario, client.ids["scenario"]).updated_at == timestamp


@pytest.mark.parametrize(("panics", "status", "frase"), [
    (("editorial-amount-does-not-fit",), 422, "importo"),
    (("editorial-cell-token-does-not-fit", "appendix-index-without-source-rows"), 422, "cella"),
    (("editorial-note-does-not-fit",), 422, "commento"),
    ((), 503, "Compilazione del report non riuscita"),
])
def test_un_contenuto_che_non_entra_non_si_spaccia_per_un_renderer_guasto(panics, status, frase):
    """AMBIENTA, 2026-09-17: 503 «Riprovare dopo aver verificato il renderer» mentre il renderer
    funzionava e a non entrare era un importo da 4.006.984,18 in una colonna da 39,8 pt."""
    from fastapi import HTTPException
    from app.api.v1 import editorial_notes
    from app.renderers.typst.runtime import RendererCompileError

    class _Db:
        def rollback(self):
            pass

    def action(db, company_id, scenario_id):
        raise RendererCompileError(panics=panics)

    with pytest.raises(HTTPException) as error:
        editorial_notes._run(action, _Db(), 1, 1)
    assert error.value.status_code == status
    assert frase in error.value.detail
    assert "verificato il renderer" not in error.value.detail
