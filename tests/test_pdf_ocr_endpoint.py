"""Endpoint tests for POST /import/pdf-ocr (MinerU mocked — no Docker)."""
import jwt
import pytest
from fastapi.testclient import TestClient

SECRET = "ocr-endpoint-test-secret"
PDF_BYTES = b"%PDF-1.4\n%mock scanned bilancio\n"


def _auth(sub):
    return {"Authorization": f"Bearer {jwt.encode({'sub': sub}, SECRET, algorithm='HS256')}"}


@pytest.fixture()
def ctx(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from backend.app.main import app
    from app.core import database as core_db
    from app.core.config import settings
    from app.api.v1 import imports as imports_router
    from app.services import mineru_client as mc
    from database.db import Base

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)

    def override_get_db():
        db = sessions()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[core_db.get_db] = override_get_db
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", SECRET)
    monkeypatch.setattr(settings, "DEV_USER_ID", None)
    monkeypatch.setattr(settings, "MINERU_OCR_ENABLED", True)
    # tracking writes are irrelevant here
    monkeypatch.setattr(imports_router, "save_upload", lambda *a, **k: object())
    monkeypatch.setattr(imports_router, "mark_success", lambda *a, **k: None)
    monkeypatch.setattr(imports_router, "mark_error", lambda *a, **k: None)

    client = TestClient(app)
    try:
        yield client, settings, imports_router, mc, monkeypatch
    finally:
        app.dependency_overrides.clear()


def _fake_client_cls(*, health_exc=None, parse_exc=None, md="Stato Patrimoniale Attivo 100"):
    from app.services.mineru_client import MinerURawResult

    class _Fake:
        def __init__(self, *a, **k):
            pass

        @classmethod
        def from_settings(cls, *a, **k):
            return cls()

        async def health(self):
            if health_exc:
                raise health_exc
            return object()

        async def parse_pdf(self, *, content, filename):
            if parse_exc:
                raise parse_exc
            return MinerURawResult(
                version="3.2.0", status="completed", file_stem="x",
                md_content=md, middle_json="", content_list="", raw={},
            )

    return _Fake


def test_ocr_disabled_returns_503(ctx):
    client, settings, imports_router, mc, mp = ctx
    mp.setattr(settings, "MINERU_OCR_ENABLED", False)
    r = client.post(
        "/api/v1/import/pdf-ocr?fiscal_year=2024&company_name=Acme&create_company=true",
        files={"file": ("b.pdf", PDF_BYTES, "application/pdf")}, headers=_auth("u1"),
    )
    assert r.status_code == 503
    assert r.json()["detail"]["error_code"] == "MINERU_DISABLED"


def test_ocr_requires_auth(ctx):
    client, *_ = ctx
    r = client.post(
        "/api/v1/import/pdf-ocr?fiscal_year=2024&company_name=Acme",
        files={"file": ("b.pdf", PDF_BYTES, "application/pdf")},
    )
    assert r.status_code == 401


def test_ocr_rejects_non_pdf_signature(ctx):
    client, *_ = ctx
    r = client.post(
        "/api/v1/import/pdf-ocr?fiscal_year=2024&company_name=Acme",
        files={"file": ("b.pdf", b"not a pdf", "application/pdf")}, headers=_auth("u1"),
    )
    assert r.status_code == 400


def test_capabilities_reflects_flag(ctx):
    client, settings, imports_router, mc, mp = ctx
    r = client.get("/api/v1/import/capabilities", headers=_auth("u1"))
    assert r.status_code == 200 and r.json()["ocr_available"] is True
    mp.setattr(settings, "MINERU_OCR_ENABLED", False)
    r = client.get("/api/v1/import/capabilities", headers=_auth("u1"))
    assert r.json()["ocr_available"] is False


def test_ocr_mineru_unavailable_503(ctx):
    client, settings, imports_router, mc, mp = ctx
    from app.services.mineru_client import MinerUUnavailableError
    mp.setattr(mc, "MinerUClient", _fake_client_cls(health_exc=MinerUUnavailableError("down")))
    r = client.post(
        "/api/v1/import/pdf-ocr?fiscal_year=2024&company_name=Acme",
        files={"file": ("b.pdf", PDF_BYTES, "application/pdf")}, headers=_auth("u1"),
    )
    assert r.status_code == 503
    assert r.json()["detail"]["error_code"] == "MINERU_UNAVAILABLE"


def test_ocr_mineru_timeout_504(ctx):
    client, settings, imports_router, mc, mp = ctx
    from app.services.mineru_client import MinerUTimeoutError
    mp.setattr(mc, "MinerUClient", _fake_client_cls(parse_exc=MinerUTimeoutError("slow")))
    r = client.post(
        "/api/v1/import/pdf-ocr?fiscal_year=2024&company_name=Acme",
        files={"file": ("b.pdf", PDF_BYTES, "application/pdf")}, headers=_auth("u1"),
    )
    assert r.status_code == 504
    assert r.json()["detail"]["error_code"] == "MINERU_TIMEOUT"


def test_ocr_empty_text_422(ctx):
    client, settings, imports_router, mc, mp = ctx
    mp.setattr(mc, "MinerUClient", _fake_client_cls(md="   "))  # whitespace only → empty context
    r = client.post(
        "/api/v1/import/pdf-ocr?fiscal_year=2024&company_name=Acme",
        files={"file": ("b.pdf", PDF_BYTES, "application/pdf")}, headers=_auth("u1"),
    )
    assert r.status_code == 422
    assert r.json()["detail"]["error_code"] == "MINERU_EMPTY"


def test_ocr_empty_text_marks_tracked_upload_as_error(ctx):
    client, settings, imports_router, mc, mp = ctx
    record = object()
    marked = []
    mp.setattr(imports_router, "save_upload", lambda *a, **k: record)
    mp.setattr(imports_router, "mark_error", lambda db, upload, error: marked.append((upload, error)))
    mp.setattr(mc, "MinerUClient", _fake_client_cls(md="   "))

    r = client.post(
        "/api/v1/import/pdf-ocr?fiscal_year=2024&company_name=Acme",
        files={"file": ("b.pdf", PDF_BYTES, "application/pdf")}, headers=_auth("u1"),
    )

    assert r.status_code == 422
    assert len(marked) == 1
    assert marked[0][0] is record


def test_ownership_gate_runs_before_upload_tracking(ctx):
    from fastapi import HTTPException

    client, settings, imports_router, mc, mp = ctx
    saved = []

    def reject_ownership(*args, **kwargs):
        raise HTTPException(status_code=404, detail="not found")

    mp.setattr(imports_router, "validate_company_owned_by_user", reject_ownership)
    mp.setattr(imports_router, "save_upload", lambda *a, **k: saved.append(True))
    r = client.post(
        "/api/v1/import/pdf-ocr?fiscal_year=2024&company_id=99&create_company=false",
        files={"file": ("b.pdf", PDF_BYTES, "application/pdf")}, headers=_auth("u1"),
    )

    assert r.status_code == 404
    assert saved == []


def test_ocr_contract_mismatch_returns_503(ctx):
    client, settings, imports_router, mc, mp = ctx
    from app.services.mineru_client import MinerUContractError

    mp.setattr(
        mc,
        "MinerUClient",
        _fake_client_cls(health_exc=MinerUContractError("expected 3.2.0, got 3.3.0")),
    )
    r = client.post(
        "/api/v1/import/pdf-ocr?fiscal_year=2024&company_name=Acme",
        files={"file": ("b.pdf", PDF_BYTES, "application/pdf")}, headers=_auth("u1"),
    )

    assert r.status_code == 503
    assert r.json()["detail"]["error_code"] == "MINERU_CONTRACT_MISMATCH"


def test_ocr_success_passes_context_to_importer(ctx):
    client, settings, imports_router, mc, mp = ctx
    mp.setattr(mc, "MinerUClient", _fake_client_cls(md="Stato Patrimoniale Attivo 100"))

    captured = {}

    def fake_import(**kwargs):
        captured.update(kwargs)
        return {"success": True, "company_id": 1, "company_name": "Acme", "fiscal_year": 2024,
                "extraction_method": "mineru+deterministico", "ocr_engine": "mineru"}

    mp.setattr(imports_router, "import_pdf_balance_sheet", fake_import)
    r = client.post(
        "/api/v1/import/pdf-ocr?fiscal_year=2024&company_name=Acme&create_company=true",
        files={"file": ("b.pdf", PDF_BYTES, "application/pdf")}, headers=_auth("u1"),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    # the MinerU context reached the accounting pipeline
    assert captured.get("extraction_context") is not None
    assert captured["extraction_context"].full_text.strip() != ""
    assert captured["fiscal_year"] == 2024
