"""Full user journey over the REAL HTTP surface, with JWT multi-tenancy."""
import json
from decimal import Decimal

import jwt
import pytest
from fastapi.testclient import TestClient

from tests.test_standard_ivcee_parser import _write_compact_infrannual_pdf

SECRET = "http-cycle-test-secret"


def _auth(sub):
    token = jwt.encode({"sub": sub}, SECRET, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def client(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    # IMPORTANT: import the app via `backend.app.main` first. Its module body
    # inserts BOTH the project root AND the `backend/` directory onto
    # sys.path, which means `app.*` becomes importable as a package
    # *distinct* from `backend.app.*` even though they are the same files on
    # disk (Python caches modules by dotted name, not by path). Every route
    # inside backend/app/api/v1/*.py does `from app.core.database import
    # get_db` / `from app.core.config import settings` (the bare `app.*`
    # form) — so `Depends(get_db)` and the live `settings` object used at
    # request time are the `app.*` copies, NOT `backend.app.core.*`.
    # Patching the `backend.app.*` copies (as an earlier draft of this fixture
    # did, mirroring the brief verbatim) silently no-ops: dependency_overrides
    # keys on object identity and never matches, and settings.SUPABASE_JWT_SECRET
    # stays unset on the copy actually read by auth.py, so every request 500s
    # with "SUPABASE_JWT_SECRET not configured". Importing `app.*` only AFTER
    # `backend.app.main` guarantees sys.path already has `backend/` on it.
    from backend.app.main import app

    from app.core import database as core_db
    from app.core.config import settings
    from app.api.v1 import imports as imports_router
    from database.db import Base
    from importers import pdf_importer

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)

    def override_get_db():
        db = sessions()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[core_db.get_db] = override_get_db
    monkeypatch.setattr(pdf_importer, "SessionLocal", sessions)
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", SECRET)
    monkeypatch.setattr(settings, "DEV_USER_ID", None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    # imports.py does `from app.services.upload_tracker import save_upload,
    # mark_success, mark_error` (name-binding import), so it holds its own
    # local reference — patching the upload_tracker module's attributes
    # afterwards would not reach the calls made from imports.py. Patch the
    # names where they are actually called: on the imports router module
    # itself (writes to data/uploads + the tracker table are irrelevant here).
    monkeypatch.setattr(imports_router, "save_upload", lambda *a, **k: None)
    monkeypatch.setattr(imports_router, "mark_success", lambda *a, **k: None)
    monkeypatch.setattr(imports_router, "mark_error", lambda *a, **k: None)

    with TestClient(app) as test_client:
        test_client.sessions = sessions
        yield test_client
    app.dependency_overrides.pop(core_db.get_db, None)
    engine.dispose()


def _import_pdf(client, tmp_path, sub, name, **pdf_kwargs):
    pdf = tmp_path / f"{name}.pdf"
    _write_compact_infrannual_pdf(pdf, **pdf_kwargs)
    with pdf.open("rb") as fh:
        response = client.post(
            "/api/v1/import/pdf",
            params={
                "fiscal_year": 2026,
                "company_name": name,
                "create_company": True,
                "sector": 1,
                "period_months": 6,
            },
            files={"file": (pdf.name, fh, "application/pdf")},
            headers=_auth(sub),
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is True
    return body["company_id"]


def test_http_full_cycle_import_to_analysis(client, tmp_path):
    """Import → rettifica → scenario → ipotesi → analysis, tutto via HTTP/JSON."""
    company_id = _import_pdf(client, tmp_path, "user-a", "HTTP CYCLE SRL")

    adjustable = client.get(
        f"/api/v1/companies/{company_id}/years/2026/adjustable",
        params={"period_months": 6},
        headers=_auth("user-a"),
    )
    assert adjustable.status_code == 200
    bs = adjustable.json()["balance_sheet"]
    cash = Decimal(str(bs["sp09_disponibilita_liquide"]))
    bank = Decimal(str(bs["sp16a_debiti_banche_breve"]))
    debt = Decimal(str(bs["sp16_debiti_breve"]))

    put = client.put(
        f"/api/v1/companies/{company_id}/years/2026/adjustments",
        params={"period_months": 6},
        json={
            "balance_sheet": {
                "sp09_disponibilita_liquide": float(cash + 500),
                "sp16_debiti_breve": float(debt + 500),
                "sp16a_debiti_banche_breve": float(bank + 500),
            },
            "income_statement": {},
            "rettifiche_log": [
                {
                    "id": "http-1",
                    "edited_field": "sp09_disponibilita_liquide",
                    "edited_label": "Disponibilita liquide",
                    "edit_delta": 500,
                    "counterpart_field": "sp16a_debiti_banche_breve",
                    "counterpart_label": "Debiti verso banche entro 12 mesi",
                    "counterpart_delta": 500,
                    "explanation": "rettifica del test HTTP",
                    "created_at": "2026-07-21T09:00:00Z",
                }
            ],
        },
        headers=_auth("user-a"),
    )
    assert put.status_code == 200, put.text
    assert put.json()["forecastable"] is True

    created = client.post(
        f"/api/v1/companies/{company_id}/scenarios",
        json={
            "company_id": company_id,
            "name": "HTTP infrannuale",
            "base_year": 2025,
            "scenario_type": "infrannuale",
            "period_months": 6,
        },
        headers=_auth("user-a"),
    )
    assert created.status_code in (200, 201), created.text
    scenario_id = created.json()["id"]

    generated = client.put(
        f"/api/v1/companies/{company_id}/scenarios/{scenario_id}/assumptions",
        json={
            "assumptions": [{"forecast_year": 2026, "revenue_growth_pct": 4,
                             "tax_rate": 24}],
            "auto_generate": True,
        },
        headers=_auth("user-a"),
    )
    assert generated.status_code == 200, generated.text
    assert generated.json()["forecast_generated"] is True

    analysis = client.get(
        f"/api/v1/companies/{company_id}/scenarios/{scenario_id}/analysis",
        headers=_auth("user-a"),
    )
    assert analysis.status_code == 200, analysis.text
    payload = analysis.json()
    forecast = payload["forecast_years"]
    assert [f["year"] for f in forecast] == [2026]
    fb = forecast[0]["balance_sheet"]
    # La response schema (BalanceSheetData) non espone total_liabilities: lo
    # ricostruiamo dagli aggregati che SONO nella response (come fa la ORM
    # property total_liabilities in database/models.py), poi verifichiamo che
    # sui float serializzati la quadratura regga al centesimo.
    total_liabilities = (
        fb["total_equity"] + fb["total_debt"] + fb["sp14_fondi_rischi"]
        + fb["sp15_tfr"] + fb["sp18_ratei_risconti_passivi"]
    )
    assert abs(fb["total_assets"] - total_liabilities) < 0.005


def test_cross_user_isolation_is_a_404(client, tmp_path):
    """user-b non deve nemmeno sapere che l'azienda di user-a esiste."""
    company_id = _import_pdf(client, tmp_path, "user-a", "ISOLATA SRL")
    for path in (
        f"/api/v1/companies/{company_id}",
        f"/api/v1/companies/{company_id}/scenarios",
        f"/api/v1/companies/{company_id}/years/2026/adjustable?period_months=6",
    ):
        response = client.get(path, headers=_auth("user-b"))
        assert response.status_code == 404, f"{path} -> {response.status_code}"
    # e senza token: 401, non 500
    assert client.get(f"/api/v1/companies/{company_id}").status_code == 401


def test_rettifiche_log_cap_is_enforced_over_http(client, tmp_path):
    company_id = _import_pdf(client, tmp_path, "user-a", "CAP RETTIFICHE SRL")
    entries = [
        {
            "id": f"e{i}",
            "edited_field": "sp09_disponibilita_liquide",
            "edited_label": "Cassa",
            "edit_delta": 1,
            "counterpart_field": "sp16a_debiti_banche_breve",
            "counterpart_label": "Banche",
            "counterpart_delta": 1,
            "explanation": "x",
            "created_at": "2026-07-21T09:00:00Z",
        }
        for i in range(21)
    ]
    response = client.put(
        f"/api/v1/companies/{company_id}/years/2026/adjustments",
        params={"period_months": 6},
        json={"balance_sheet": {}, "income_statement": {}, "rettifiche_log": entries},
        headers=_auth("user-a"),
    )
    assert response.status_code == 400
    assert "20" in response.json()["detail"]


def test_delete_company_cascades_everything(client, tmp_path):
    from database.models import (
        BalanceSheet, BudgetScenario, Company, FinancialYear, IncomeStatement,
    )

    company_id = _import_pdf(client, tmp_path, "user-a", "DA CANCELLARE SRL")
    created = client.post(
        f"/api/v1/companies/{company_id}/scenarios",
        json={"company_id": company_id, "name": "temp", "base_year": 2025,
              "scenario_type": "infrannuale", "period_months": 6},
        headers=_auth("user-a"),
    )
    assert created.status_code in (200, 201)

    deleted = client.delete(
        f"/api/v1/companies/{company_id}", headers=_auth("user-a")
    )
    assert deleted.status_code == 204

    with client.sessions() as db:
        for model in (Company, FinancialYear, BalanceSheet, IncomeStatement,
                      BudgetScenario):
            assert db.query(model).count() == 0, model.__name__


def test_adjustments_preserves_critical_accounts_verdict(client, tmp_path):
    """PUT /adjustments used to rebuild validation_report from scratch, silently
    DESTROYING the critical_accounts verdict (importers/reliability.py) computed
    at import time. Confirms backend/app/api/v1/financial_years.py::save_adjustments
    now carries it over into the rebuilt payload."""
    from database.models import FinancialYear

    company_id = _import_pdf(client, tmp_path, "user-a", "CRITICAL ACCOUNTS SRL")

    with client.sessions() as db:
        year = db.query(FinancialYear).filter_by(company_id=company_id).one()
        stored_before = json.loads(year.validation_report)
        assert "critical_accounts" in stored_before, (
            "import must populate critical_accounts for this test to be meaningful")
        critical_before = stored_before["critical_accounts"]

    adjustable = client.get(
        f"/api/v1/companies/{company_id}/years/2026/adjustable",
        params={"period_months": 6},
        headers=_auth("user-a"),
    )
    assert adjustable.status_code == 200
    bs = adjustable.json()["balance_sheet"]
    cash = Decimal(str(bs["sp09_disponibilita_liquide"]))
    bank = Decimal(str(bs["sp16a_debiti_banche_breve"]))
    debt = Decimal(str(bs["sp16_debiti_breve"]))

    put = client.put(
        f"/api/v1/companies/{company_id}/years/2026/adjustments",
        params={"period_months": 6},
        json={
            "balance_sheet": {
                "sp09_disponibilita_liquide": float(cash + 10),
                "sp16_debiti_breve": float(debt + 10),
                "sp16a_debiti_banche_breve": float(bank + 10),
            },
            "income_statement": {},
        },
        headers=_auth("user-a"),
    )
    assert put.status_code == 200, put.text

    with client.sessions() as db:
        year = db.query(FinancialYear).filter_by(company_id=company_id).one()
        stored_after = json.loads(year.validation_report)
        assert "critical_accounts" in stored_after
        assert stored_after["critical_accounts"] == critical_before


def test_adjustments_survives_missing_or_malformed_stored_report(client, tmp_path):
    """A FinancialYear whose validation_report is NULL, empty, or not valid JSON
    (older records / edge cases) must never make PUT /adjustments raise - the
    critical_accounts preservation step reads the stored report defensively."""
    from database.models import FinancialYear

    company_id = _import_pdf(client, tmp_path, "user-a", "MALFORMED REPORT SRL")

    # Fetch valid edit values ONCE, before any corruption below - GET /adjustable
    # itself parses validation_report unconditionally (a separate, pre-existing
    # code path this task does not touch), so it must not be called again once
    # validation_report has been corrupted.
    adjustable = client.get(
        f"/api/v1/companies/{company_id}/years/2026/adjustable",
        params={"period_months": 6},
        headers=_auth("user-a"),
    )
    assert adjustable.status_code == 200
    bs = adjustable.json()["balance_sheet"]
    cash = Decimal(str(bs["sp09_disponibilita_liquide"]))
    bank = Decimal(str(bs["sp16a_debiti_banche_breve"]))
    debt = Decimal(str(bs["sp16_debiti_breve"]))

    for i, broken_report in enumerate((None, "", "not json {{{")):
        with client.sessions() as db:
            year = db.query(FinancialYear).filter_by(company_id=company_id).one()
            year.validation_report = broken_report
            db.commit()

        put = client.put(
            f"/api/v1/companies/{company_id}/years/2026/adjustments",
            params={"period_months": 6},
            json={
                "balance_sheet": {
                    "sp09_disponibilita_liquide": float(cash + i + 1),
                    "sp16_debiti_breve": float(debt + i + 1),
                    "sp16a_debiti_banche_breve": float(bank + i + 1),
                },
                "income_statement": {},
            },
            headers=_auth("user-a"),
        )
        assert put.status_code == 200, f"broken_report={broken_report!r}: {put.text}"

        with client.sessions() as db:
            year = db.query(FinancialYear).filter_by(company_id=company_id).one()
            # Must be valid JSON (the save always writes a fresh payload) and,
            # since there was nothing usable to carry over, no critical_accounts.
            rebuilt = json.loads(year.validation_report)
            assert "critical_accounts" not in rebuilt


def _stored_report(client, company_id):
    from database.models import FinancialYear
    with client.sessions() as db:
        year = db.query(FinancialYear).filter_by(company_id=company_id).one()
        return json.loads(year.validation_report)


def _set_stored_report(client, company_id, report):
    from database.models import FinancialYear
    with client.sessions() as db:
        year = db.query(FinancialYear).filter_by(company_id=company_id).one()
        year.validation_report = json.dumps(report)
        db.commit()


def _put_noop_adjustment(client, company_id, bump=1):
    """A double-entry rettifica that keeps the sheet balanced and touches
    nothing a critical-account verdict is about."""
    adjustable = client.get(
        f"/api/v1/companies/{company_id}/years/2026/adjustable",
        params={"period_months": 6},
        headers=_auth("user-a"),
    )
    assert adjustable.status_code == 200, adjustable.text
    bs = adjustable.json()["balance_sheet"]
    cash = Decimal(str(bs["sp09_disponibilita_liquide"]))
    bank = Decimal(str(bs["sp16a_debiti_banche_breve"]))
    debt = Decimal(str(bs["sp16_debiti_breve"]))
    return client.put(
        f"/api/v1/companies/{company_id}/years/2026/adjustments",
        params={"period_months": 6},
        json={
            "balance_sheet": {
                "sp09_disponibilita_liquide": float(cash + bump),
                "sp16_debiti_breve": float(debt + bump),
                "sp16a_debiti_banche_breve": float(bank + bump),
            },
            "income_statement": {},
        },
        headers=_auth("user-a"),
    )


def test_a_rettifica_cannot_restore_forecastable_over_a_false_verdict(client, tmp_path):
    """PUT /adjustments used to set validation_status='verified' /
    forecastable=True from semantic_valid alone, while the PRESERVED
    critical_accounts still said all_critical_ok=false: a self-contradictory
    record, and a gate any no-op edit could bypass."""
    from database.models import FinancialYear

    company_id = _import_pdf(client, tmp_path, "user-a", "VERDICT FALSE SRL")

    report = _stored_report(client, company_id)
    assert "critical_accounts" in report
    report["critical_accounts"]["all_critical_ok"] = False
    report["critical_accounts"]["immobilizzazioni"] = {
        "status": "unreliable", "reason": "forced for this test"}
    _set_stored_report(client, company_id, report)

    put = _put_noop_adjustment(client, company_id)
    assert put.status_code == 200, put.text

    with client.sessions() as db:
        year = db.query(FinancialYear).filter_by(company_id=company_id).one()
        stored = json.loads(year.validation_report)
        # the sheet itself is still balanced - only the verdict blocks it
        assert stored["semantic_valid"] is True
        assert stored["critical_accounts"]["all_critical_ok"] is False
        assert year.forecastable is False
        assert year.validation_status == "review_required"


def test_a_rettifica_keeps_forecastable_when_the_verdict_is_true(client, tmp_path):
    from database.models import FinancialYear

    company_id = _import_pdf(client, tmp_path, "user-a", "VERDICT TRUE SRL")
    report = _stored_report(client, company_id)
    assert report["critical_accounts"]["all_critical_ok"] is True

    put = _put_noop_adjustment(client, company_id)
    assert put.status_code == 200, put.text

    with client.sessions() as db:
        year = db.query(FinancialYear).filter_by(company_id=company_id).one()
        assert json.loads(year.validation_report)["semantic_valid"] is True
        assert year.forecastable is True
        assert year.validation_status == "verified"


def test_a_rettifica_without_a_stored_verdict_keeps_legacy_behaviour(client, tmp_path):
    """No preserved verdict means UNKNOWN, and unknown must never block:
    forecastable falls back to semantic_valid exactly as before this change."""
    from database.models import FinancialYear

    company_id = _import_pdf(client, tmp_path, "user-a", "NO VERDICT SRL")
    report = _stored_report(client, company_id)
    report.pop("critical_accounts", None)
    _set_stored_report(client, company_id, report)

    put = _put_noop_adjustment(client, company_id)
    assert put.status_code == 200, put.text

    with client.sessions() as db:
        year = db.query(FinancialYear).filter_by(company_id=company_id).one()
        stored = json.loads(year.validation_report)
        assert "critical_accounts" not in stored
        assert stored["semantic_valid"] is True
        assert year.forecastable is True
        assert year.validation_status == "verified"


@pytest.mark.parametrize("broken", [
    None, "", "not json {{{", "[]", '"a string"', '{"critical_accounts": null}',
    '{"critical_accounts": []}', '{"critical_accounts": {}}',
])
def test_a_malformed_stored_verdict_never_breaks_the_save(client, tmp_path, broken):
    """Absent / empty / malformed / non-dict / missing-key must never raise and
    never fail the adjustments save; they all mean UNKNOWN, which never blocks."""
    from database.models import FinancialYear

    company_id = _import_pdf(client, tmp_path, "user-a", f"BROKEN {abs(hash(broken)) % 9999} SRL")
    # read the edit values BEFORE corrupting: GET /adjustable itself parses
    # validation_report on a separate, pre-existing code path.
    adjustable = client.get(
        f"/api/v1/companies/{company_id}/years/2026/adjustable",
        params={"period_months": 6},
        headers=_auth("user-a"),
    )
    assert adjustable.status_code == 200
    bs = adjustable.json()["balance_sheet"]
    cash = Decimal(str(bs["sp09_disponibilita_liquide"]))
    bank = Decimal(str(bs["sp16a_debiti_banche_breve"]))
    debt = Decimal(str(bs["sp16_debiti_breve"]))

    with client.sessions() as db:
        year = db.query(FinancialYear).filter_by(company_id=company_id).one()
        year.validation_report = broken
        db.commit()

    put = client.put(
        f"/api/v1/companies/{company_id}/years/2026/adjustments",
        params={"period_months": 6},
        json={
            "balance_sheet": {
                "sp09_disponibilita_liquide": float(cash + 1),
                "sp16_debiti_breve": float(debt + 1),
                "sp16a_debiti_banche_breve": float(bank + 1),
            },
            "income_statement": {},
        },
        headers=_auth("user-a"),
    )
    assert put.status_code == 200, f"broken={broken!r}: {put.text}"

    with client.sessions() as db:
        year = db.query(FinancialYear).filter_by(company_id=company_id).one()
        assert year.forecastable is True          # unknown never blocks
        assert year.validation_status == "verified"


def test_forced_unreliable_verdict_blocks_forecastable_on_the_synthetic_pdf(
        client, tmp_path, monkeypatch):
    """Non-skipping CI guard for the wiring at importers/pdf_importer.py
    (`_critical_ok` / `_forecastable`). The equivalent test in
    tests/test_reliability_gating.py needs the untracked budget_615 corpus PDF,
    so it silently skips in a clean checkout; this one runs on the synthetic
    fixture every time. Reverting the wiring to `forecastable=_qd.semantic_valid`
    makes it fail, because the synthetic sheet balances on its own."""
    from database.models import FinancialYear
    from importers import reliability as reliability_module
    from importers.reliability import AccountStatus, ReliabilityReport

    monkeypatch.setattr(reliability_module, "assess", lambda *a, **k: ReliabilityReport(
        immobilizzazioni=AccountStatus.UNRELIABLE,
        immobilizzazioni_reason="forced unreliable for the CI wiring guard",
        patrimonio_netto=AccountStatus.DERIVED, patrimonio_netto_reason="n/a",
        debiti_banche=AccountStatus.DERIVED, debiti_banche_reason="n/a",
    ))

    company_id = _import_pdf(client, tmp_path, "user-a", "FORCED UNRELIABLE SRL")

    with client.sessions() as db:
        year = db.query(FinancialYear).filter_by(company_id=company_id).one()
        stored = json.loads(year.validation_report)
        # the verdict gates the FORECAST, never the SAVE
        assert year.balance_sheet is not None
        assert stored["semantic_valid"] is True
        assert stored["critical_accounts"]["all_critical_ok"] is False
        assert year.forecastable is False
        assert year.validation_status == "review_required"
