"""M2-05: endpoint PDF del dossier — cancello, mappa errori, header, parità, compile reale.

Le prove che non richiedono il compilatore girano con il renderer sostituito
(monkeypatch) e con il modello d'assemblaggio reale o in stub; la parità con
`GET /final-report?schema_version=2` e il watermark vero sono nel blocco nativo,
che si auto-salta senza `tools/typst/bin/typst` o senza `bwrap`.
"""
import re
import shutil
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import unquote

import pytest

from app.schemas.final_report import canonical_hash
from app.services import final_report_pdf_service as pdf_service
from tests.test_final_report_endpoint import client, _url  # fixture condivisa

ROOT = Path(__file__).resolve().parents[1]
NATIVE = pytest.mark.skipif(
    not (ROOT / "tools/typst/bin/typst").is_file() or shutil.which("bwrap") is None,
    reason="PDF nativo richiede il compiler pinnato e bubblewrap (bwrap)",
)
BLOCKS = ("executive_summary", "adjustments_and_closing", "budget_assumptions",
          "economic_outlook", "financial_outlook", "risks_and_actions")


def _pdf(client, scenario=None):
    return _url(client, scenario if scenario is not None else client.ids["scenario"]) + "/pdf"


def _stub_report(*, plan=True, readiness="draft", company_name="Ambienta"):
    """Il minimo contratto che il servizio e la rotta leggono dal modello."""
    return SimpleNamespace(
        editorial_plan=SimpleNamespace(plan_hash="b" * 64) if plan else None,
        readiness=SimpleNamespace(status=readiness),
        model_hash="a" * 64,
        document=SimpleNamespace(title="Report Budget 2027 - 2029"),
        company=SimpleNamespace(name=company_name),
    )


def _rendered(data=b"%PDF-1.7 stub\ntrailer\n%%EOF"):
    return SimpleNamespace(data=data, model_hash="a" * 64, template_version="dossier-final-1+editorial-4",
                           compiler_version="0.15.1", page_count=33, artifact_sha256="c" * 64)


def _patch(monkeypatch, report, render):
    """Sostituisce assemble e sonda: la rotta vede un modello pronto senza compilare."""
    assembled = []

    def fake_assemble(db, company_id, scenario_id, *, schema_version=1):
        assembled.append((company_id, scenario_id, schema_version))
        return report

    monkeypatch.setattr(pdf_service, "assemble_final_report", fake_assemble)
    monkeypatch.setattr(pdf_service, "get_dossier_probe", lambda: SimpleNamespace(render=render))
    return assembled


def _no_ai(monkeypatch):
    from app.services import ai_comments_service, editorial_notes_service

    def forbidden(*args, **kwargs):
        pytest.fail("Il download PDF non deve mai chiamare l'AI")
    for module, name in ((ai_comments_service, "generate_final_report_narrative"),
                         (ai_comments_service, "generate_report_comments"),
                         (editorial_notes_service, "_generate_with_provider")):
        monkeypatch.setattr(module, name, forbidden)


def test_missing_editorial_plan_is_409_before_any_render(client, monkeypatch):
    def forbidden():
        pytest.fail("Senza piano editoriale il renderer non deve nemmeno essere aperto")
    _no_ai(monkeypatch)
    monkeypatch.setattr(pdf_service, "get_dossier_probe", forbidden)
    response = client.post(_pdf(client), json={"document_state": "draft"})
    assert response.status_code == 409, response.text
    assert "Prepara piano editoriale" in response.json()["detail"]


def test_foreign_scenario_is_404(client, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Un'azienda di un altro utente non deve nemmeno arrivare al modello")
    _no_ai(monkeypatch)
    monkeypatch.setattr(pdf_service, "assemble_final_report", forbidden)
    monkeypatch.setattr(pdf_service, "get_dossier_probe", forbidden)
    response = client.post(_pdf(client, client.ids["foreign"]), json={"document_state": "draft"})
    assert response.status_code == 404, response.text


@pytest.mark.parametrize("body", [
    {}, {"document_state": "draft"}, {"document_state": "final", "grayscale": True},
])
def test_plan_present_renders_with_the_requested_options(client, monkeypatch, body):
    calls = []
    _patch(monkeypatch, _stub_report(readiness="ready"),
           lambda report, *, document_state, grayscale: calls.append((document_state, grayscale)) or _rendered())
    response = client.post(_pdf(client), json=body)
    assert response.status_code == 200, response.text
    assert response.content.startswith(b"%PDF-")
    assert calls and calls[0][0] == body.get("document_state", "draft")
    assert calls[0][1] == body.get("grayscale", False)


@pytest.mark.parametrize("readiness,status_code", [("draft", 409), ("blocked", 409), ("ready", 200)])
def test_final_only_on_ready_report(client, monkeypatch, readiness, status_code):
    calls = []
    _patch(monkeypatch, _stub_report(readiness=readiness),
           lambda report, *, document_state, grayscale: calls.append(document_state) or _rendered())
    response = client.post(_pdf(client), json={"document_state": "final"})
    assert response.status_code == status_code, response.text
    if status_code == 409:
        assert "non è pronto" in response.json()["detail"] and calls == []
        # La bozza è sempre ammessa, con il watermark: il cancello blocca solo il finale.
        assert client.post(_pdf(client), json={"document_state": "draft"}).status_code == 200
        assert calls == ["draft"]
    else:
        assert calls == ["final"]


def test_request_contract_is_strict(client, monkeypatch):
    _patch(monkeypatch, _stub_report(), lambda *a, **k: _rendered())
    assert client.post(_pdf(client), json={"document_state": "published"}).status_code == 422
    assert client.post(_pdf(client), json={"document_state": "draft", "context": {}}).status_code == 422
    assert client.post(_pdf(client), json={"document_state": True}).status_code == 422
    assert client.post(_pdf(client)).status_code == 422  # il corpo è richiesto


def test_pdf_renders_the_same_report_the_service_assembled(client, monkeypatch):
    report = _stub_report()
    seen = []
    assembled = _patch(monkeypatch, report,
                       lambda model, *, document_state, grayscale: seen.append(model) or _rendered())
    response = client.post(_pdf(client), json={"document_state": "draft"})
    assert response.status_code == 200, response.text
    assert assembled == [(client.ids["company"], client.ids["scenario"], 2)]
    assert seen == [report]  # nessun doppio assemblaggio, nessuna mutazione


@pytest.mark.parametrize("state", ["draft", "final"])
def test_no_writes_and_no_ai(client, monkeypatch, state):
    from database.models import BudgetScenario
    from database.report_editorial import ReportEditorialNote, ReportEditorialState

    _no_ai(monkeypatch)
    _patch(monkeypatch, _stub_report(readiness="ready"), lambda *a, **k: _rendered())
    with client.sessions() as db:
        before = (db.query(ReportEditorialState).count(), db.query(ReportEditorialNote).count(),
                  db.get(BudgetScenario, client.ids["scenario"]).updated_at)
    response = client.post(_pdf(client), json={"document_state": state, "grayscale": True})
    assert response.status_code == 200, response.text
    with client.sessions() as db:
        after = (db.query(ReportEditorialState).count(), db.query(ReportEditorialNote).count(),
                 db.get(BudgetScenario, client.ids["scenario"]).updated_at)
    assert after == before


def _renderer_error_case(name):
    from app.renderers.typst.runtime import (
        RendererBusy, RendererCompileError, RendererError, RendererInputError,
        RendererInvalidPdf, RendererTimeout, RendererUnavailable,
    )
    return {
        "busy": RendererBusy(),
        "unavailable": RendererUnavailable(),
        "timeout": RendererTimeout(),
        "panic-known": RendererCompileError(("editorial-amount-does-not-fit",)),
        "panic-unknown": RendererCompileError(("qualcosaltro",)),
        "compile-bare": RendererCompileError(),
        "invalid-pdf": RendererInvalidPdf(),
        "input": RendererInputError(),
        "generic": RendererError(),
    }[name]


@pytest.mark.parametrize("name,status_code,needle", [
    ("busy", 503, "occupata"),
    ("unavailable", 503, "non disponibile"),
    ("timeout", 504, "Tempo massimo"),
    ("panic-known", 422, "un importo è più largo della sua colonna"),
    ("panic-unknown", 500, "Compilazione"),
    ("compile-bare", 500, "Compilazione"),
    ("invalid-pdf", 500, "validazione"),
    ("input", 500, "Modello o opzioni"),
    ("generic", 500, "non riuscita"),
])
def test_renderer_errors_map_without_paths_or_data(client, monkeypatch, name, status_code, needle):
    error = _renderer_error_case(name)

    def render(report, *, document_state, grayscale):
        raise error
    _patch(monkeypatch, _stub_report(readiness="ready"), render)
    response = client.post(_pdf(client), json={"document_state": "final"})
    assert response.status_code == status_code, response.text
    detail = response.json()["detail"]
    assert needle in detail
    assert "/" not in detail  # nessun percorso, nessun dato: solo italiano
    assert "a" * 64 not in detail and str(client.ids["company"]) not in str(detail)


def test_headers_and_filename(client, monkeypatch):
    _patch(monkeypatch, _stub_report(company_name='Acme / "Banca" <Milano> \\ Corso: Cosenza'),
           lambda *a, **k: _rendered())
    response = client.post(_pdf(client), json={"document_state": "draft"})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    disposition = response.headers["content-disposition"]
    name = disposition.split('filename="')[1].split('"')[0]
    assert name == "Report Budget 2027 - 2029 - Acme Banca Milano Corso Cosenza.pdf"
    assert not re.search(r'[/\\:<>?*"]', name)
    assert "filename*=UTF-8''" in disposition
    expected_etag = canonical_hash({"model": "a" * 64, "plan": "b" * 64,
                                    "document_state": "draft", "grayscale": False}, exclude_volatile=False)
    assert response.headers["etag"] == f'"{expected_etag}"'
    assert response.headers["x-report-model-hash"] == "a" * 64
    assert response.headers["x-report-template-version"] == "dossier-final-1+editorial-4"
    assert response.headers["x-report-compiler-version"] == "0.15.1"
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("company,expected,expected_ascii", [
    ("Ambienta", "Report Budget 2027 - 2029 - Ambienta.pdf",
     "Report Budget 2027 - 2029 - Ambienta.pdf"),
    ('P & P "Srl"', "Report Budget 2027 - 2029 - P & P Srl.pdf",
     "Report Budget 2027 - 2029 - P & P Srl.pdf"),
    ("/// <<< >>> ???", "Report Budget 2027 - 2029.pdf", "Report Budget 2027 - 2029.pdf"),
    ("::", "Report Budget 2027 - 2029.pdf", "Report Budget 2027 - 2029.pdf"),
    ("Ambienta\tNuova\nSrl", "Report Budget 2027 - 2029 - Ambienta Nuova Srl.pdf",
     "Report Budget 2027 - 2029 - Ambienta Nuova Srl.pdf"),
    # Starlette codifica gli header in latin-1: ’ € – non sono latini e crackerebbero la risposta.
    ("Caffè D’Italia – Srl €", "Report Budget 2027 - 2029 - Caffè D’Italia – Srl €.pdf",
     "Report Budget 2027 - 2029 - Caffe DItalia Srl.pdf"),
    ("☺ ☹", "Report Budget 2027 - 2029 - ☺ ☹.pdf", "Report Budget 2027 - 2029.pdf"),
])
def test_artifact_filename_pure(company, expected, expected_ascii):
    report = _stub_report(company_name=company)
    assert pdf_service.artifact_filename(report) == expected
    ascii_name = pdf_service.artifact_ascii_filename(report)
    assert ascii_name == expected_ascii
    assert ascii_name.isascii()


def test_etag_identifies_the_representation(client, monkeypatch):
    """Quattro rappresentazioni diverse, quattro ETag; la ripetizione è stabile."""
    _patch(monkeypatch, _stub_report(readiness="ready"), lambda *a, **k: _rendered())
    etags = {}
    for state in ("draft", "final"):
        for gray in (False, True):
            response = client.post(_pdf(client), json={"document_state": state, "grayscale": gray})
            assert response.status_code == 200, response.text
            etags[(state, gray)] = response.headers["etag"]
    assert len(set(etags.values())) == 4, etags
    repeat = client.post(_pdf(client), json={"document_state": "final", "grayscale": True})
    assert repeat.headers["etag"] == etags[("final", True)]


def test_content_disposition_survives_a_non_latin1_company(client, monkeypatch):
    """HTTP reale: con l'azienda «Caffè D’Italia – Srl €» la risposta non deve crackare.

    Prima della correzione l'header portava il nome UTF-8 anche in `filename=`:
    Starlette lo codifica in latin-1 e un’azienda con ’, € o – sollevava
    `UnicodeEncodeError` a PDF già compilato (500 sull'errore di nessuno).
    """
    _patch(monkeypatch, _stub_report(company_name="Caffè D’Italia – Srl €"),
           lambda *a, **k: _rendered())
    response = client.post(_pdf(client), json={"document_state": "draft"})
    assert response.status_code == 200, response.text
    assert response.content.startswith(b"%PDF-")
    disposition = response.headers["content-disposition"]
    disposition.encode("latin-1")  # è così che lo codifica Starlette: dev'essere puro ASCII
    assert disposition.isascii()
    fallback = re.search(r'filename="([^"]*)"', disposition).group(1)
    assert fallback == "Report Budget 2027 - 2029 - Caffe DItalia Srl.pdf"
    extended = re.search(r"filename\*=UTF-8''([^;]+)", disposition).group(1)
    assert unquote(extended, encoding="utf-8") == "Report Budget 2027 - 2029 - Caffè D’Italia – Srl €.pdf"


@NATIVE
def test_native_pdf_matches_get_v2_and_watermarks(client):
    import fitz

    def prepare(session):
        response = client.post(_url(client, client.ids["scenario"]) + "/editorial/prepare", json={
            "source_hash": session["report"]["source_hash"], "expected_revision": session["revision"],
        })
        assert response.status_code == 200, response.text
        return response.json()

    def etag_of(report, state="draft", gray=False):
        return '"{}"'.format(canonical_hash(
            {"model": report["model_hash"], "plan": report["editorial_plan"]["plan_hash"],
             "document_state": state, "grayscale": gray}, exclude_volatile=False))

    prepare(client.get(_url(client, client.ids["scenario"]) + "/editorial").json())
    v2 = client.get(_url(client, client.ids["scenario"]) + "?schema_version=2").json()
    assert v2["editorial_readiness"]["status"] == "ready"

    draft = client.post(_pdf(client), json={"document_state": "draft"})
    assert draft.status_code == 200, draft.text
    assert draft.content.startswith(b"%PDF-")
    with fitz.open(stream=draft.content, filetype="pdf") as pdf:
        assert pdf.metadata["title"] == v2["document"]["title"]
        assert pdf.page_count == len(v2["editorial_plan"]["pages"]) > 0
        assert all("BOZZA" in page.get_text() for page in pdf)
    assert draft.headers["etag"] == etag_of(v2, "draft", False)
    assert draft.headers["x-report-model-hash"] == v2["model_hash"]
    assert draft.headers["x-report-template-version"].endswith("+editorial-4")
    assert v2["document"]["title"] in draft.headers["content-disposition"]

    # Piano pronto non basta: «final» su report la cui readiness non è ready è 409,
    # e il renderer non deve essere stato invocato (nessun PDF in risposta).
    blocked = client.post(_pdf(client), json={"document_state": "final"})
    assert blocked.status_code == 409
    assert b"%PDF" not in blocked.content[:8]
    assert "non è pronto" in blocked.json()["detail"]

    # Rende il report ready la narrativa esplicita; il body_hash cambia, il piano
    # va preparato di nuovo, e solo allora il finale esce senza watermark.
    saved = client.put(_url(client, client.ids["scenario"]) + "/narrative", json={"blocks": [
        {"id": key, "text": f"Commento distensivo per la sezione {key}."} for key in BLOCKS]})
    assert saved.status_code == 200, saved.text
    intermediate = client.get(_url(client, client.ids["scenario"]) + "?schema_version=2").json()
    assert intermediate["readiness"]["status"] == "ready", intermediate["readiness"]
    assert client.post(_pdf(client), json={"document_state": "final"}).status_code == 409  # piano now stale
    prepare(client.get(_url(client, client.ids["scenario"]) + "/editorial").json())
    ready_v2 = client.get(_url(client, client.ids["scenario"]) + "?schema_version=2").json()
    assert ready_v2["editorial_readiness"]["status"] == "ready"
    final = client.post(_pdf(client), json={"document_state": "final"})
    assert final.status_code == 200, final.text
    assert final.headers["etag"] == etag_of(ready_v2, "final", False) != draft.headers["etag"]  # piano nuovo e stato
    with fitz.open(stream=final.content, filetype="pdf") as pdf:
        assert pdf.metadata["title"] == ready_v2["document"]["title"]
        assert all("BOZZA" not in page.get_text() for page in pdf)
