"""M1-07 unified narrative endpoints, freshness, and legacy compatibility."""
import asyncio
import json
from pathlib import Path
import sys
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


USER = "final-report-narrative-user"
BLOCKS = (
    "executive_summary", "adjustments_and_closing", "budget_assumptions",
    "economic_outlook", "financial_outlook", "risks_and_actions",
)


@pytest.fixture()
def narrative():
    from app.main import app
    from database.db import Base
    from database.models import (
        BalanceSheet, BudgetAssumptions, BudgetScenario, Company, FinancialYear,
        ForecastBalanceSheet, ForecastIncomeStatement, ForecastYear, IncomeStatement,
    )

    assert app is not None
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)

    with sessions() as db:
        mine = Company(name="Mine", sector=1, user_id=USER)
        other = Company(name="Other", sector=1, user_id="other")
        db.add_all([mine, other]); db.flush()
        historical = FinancialYear(company_id=mine.id, year=2026)
        historical.balance_sheet = BalanceSheet(sp09_disponibilita_liquide=Decimal("100"), sp11_capitale=Decimal("100"))
        historical.income_statement = IncomeStatement(ce01_ricavi_vendite=Decimal("100"))
        scenario = BudgetScenario(company_id=mine.id, name="Budget", base_year=2026, workflow_type="bilancio")
        scenario.assumptions = [BudgetAssumptions(forecast_year=2027, explicitly_supplied_fields=[])]
        forecast = ForecastYear(year=2027)
        forecast.balance_sheet = ForecastBalanceSheet(sp09_disponibilita_liquide=Decimal("210"), sp11_capitale=Decimal("100"), sp13_utile_perdita=Decimal("110"))
        forecast.income_statement = ForecastIncomeStatement(ce01_ricavi_vendite=Decimal("110"))
        scenario.forecast_years = [forecast]
        foreign = BudgetScenario(company_id=other.id, name="Foreign", base_year=2026)
        db.add_all([historical, scenario, foreign]); db.commit()
        ids = {"company": mine.id, "scenario": scenario.id, "foreign": foreign.id}
    yield SimpleNamespace(sessions=sessions, ids=ids)
    engine.dispose()


def _generated(prefix="ai"):
    return {block: f"{prefix} {block}" for block in BLOCKS}


def _asgi_get(app, path: str):
    """Exercise the actual route without TestClient's application lifespan."""
    async def request():
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.get(path)
    return asyncio.run(asyncio.wait_for(request(), timeout=5))


def test_get_is_pure_and_explicit_generation_uses_canonical_model(narrative, monkeypatch):
    from app.api.v1 import reports
    from database.models import BudgetScenario

    calls = []
    def fake_generate(report):
        calls.append(report)
        assert report.__class__.__name__ == "FinalReportModel"
        return _generated()

    monkeypatch.setattr(reports, "generate_final_report_narrative", fake_generate)
    with narrative.sessions() as db:
        before = reports.get_final_report(narrative.ids["company"], narrative.ids["scenario"], USER, db)
    assert calls == []
    with narrative.sessions() as db:
        assert db.get(BudgetScenario, narrative.ids["scenario"]).narrative_blocks is None

    with narrative.sessions() as db:
        generated = reports.generate_final_report_narrative_endpoint(
            narrative.ids["company"], narrative.ids["scenario"], USER, db,
        )
    assert len(calls) == 1
    blocks = {block.id: block for block in generated.narrative}
    assert blocks["economic_outlook"].text == "ai economic_outlook"
    assert all(block.provenance == "ai" and block.freshness == "fresh" for block in blocks.values())


def test_user_text_is_preserved_and_becomes_stale_after_source_change(narrative, monkeypatch):
    from app.api.v1 import reports
    from database.models import BudgetScenario
    from app.schemas.final_report import NarrativeSaveRequest

    monkeypatch.setattr(reports, "generate_final_report_narrative", lambda report: _generated("first"))
    with narrative.sessions() as db:
        reports.generate_final_report_narrative_endpoint(narrative.ids["company"], narrative.ids["scenario"], USER, db)
    with narrative.sessions() as db:
        reports.save_final_report_narrative(
            narrative.ids["company"], narrative.ids["scenario"],
            NarrativeSaveRequest.model_validate({"blocks": [{"id": "executive_summary", "text": "testo deciso dall'utente"}]}),
            USER, db,
        )

    monkeypatch.setattr(reports, "generate_final_report_narrative", lambda report: _generated("second"))
    with narrative.sessions() as db:
        regenerated = reports.generate_final_report_narrative_endpoint(narrative.ids["company"], narrative.ids["scenario"], USER, db)
    executive = next(item for item in regenerated.narrative if item.id == "executive_summary")
    assert (executive.text, executive.provenance) == ("testo deciso dall'utente", "user")

    with narrative.sessions() as db:
        scenario = db.get(BudgetScenario, narrative.ids["scenario"])
        scenario.forecast_years[0].income_statement.ce01_ricavi_vendite = Decimal("111")
        scenario.forecast_years[0].balance_sheet.sp09_disponibilita_liquide = Decimal("211")
        scenario.forecast_years[0].balance_sheet.sp13_utile_perdita = Decimal("111")
        db.commit()
    with narrative.sessions() as db:
        stale = reports.get_final_report(narrative.ids["company"], narrative.ids["scenario"], USER, db)
    assert all(item.freshness == "stale" for item in stale.narrative)


def test_legacy_mapping_is_conservative_and_foreign_narrative_is_hidden(narrative):
    from app.services.ai_comments_service import read_narrative_blocks
    from app.api.v1 import reports
    from database.models import BudgetScenario

    with narrative.sessions() as db:
        scenario = db.get(BudgetScenario, narrative.ids["scenario"])
        scenario.ai_comment_overall = "Sintesi legacy"
        scenario.ai_comment_dashboard = "Da recuperare"
        scenario.ai_comments_infrannuale = json.dumps({
            "overall": "Seconda sintesi", "ce_proiezione": "Outlook CE", "ce_confronto": "Confronto CE",
        })
        db.commit()
        blocks, recovered = read_narrative_blocks(scenario)
    assert blocks["executive_summary"]["text"] == "Sintesi legacy"
    assert blocks["economic_outlook"]["text"] == "Outlook CE"
    assert recovered["budget"]["dashboard_comment"] == "Da recuperare"
    assert recovered["infrannuale"]["overall"] == "Seconda sintesi"
    assert recovered["infrannuale"]["ce_confronto"] == "Confronto CE"
    with narrative.sessions() as db:
        legacy_report = reports.get_final_report(
            narrative.ids["company"], narrative.ids["scenario"], USER, db,
        )
    legacy_blocks = {block.id: block for block in legacy_report.narrative}
    assert legacy_blocks["executive_summary"].text == "Sintesi legacy"
    assert legacy_blocks["economic_outlook"].text == "Outlook CE"
    with narrative.sessions() as db, pytest.raises(HTTPException) as error:
        reports.generate_final_report_narrative_endpoint(
            narrative.ids["company"], narrative.ids["foreign"], USER, db,
        )
    assert error.value.status_code == 404


@pytest.mark.parametrize(
    ("raw_blocks", "expected_user_text"),
    [
        (None, None),
        ([
            {
                "id": "executive_summary", "text": "Testo utente integro",
                "origin": "user", "source_hash": "UPPERCASE", "updated_at": "not-a-timestamp",
            },
            {
                "id": "economic_outlook", "text": "Testo con origine corrotta",
                "origin": [], "source_hash": 12, "updated_at": [],
            },
        ], "Testo utente integro"),
    ],
    ids=("blocks-none", "origin-list"),
)
def test_route_normalizes_malformed_persisted_narrative_without_losing_user_text(
    narrative, monkeypatch, raw_blocks, expected_user_text,
):
    """Malformed JSON is storage input, never a reason for the report GET to 500."""
    import fastapi.routing
    from app.main import app
    from app.core.auth import get_current_user_id
    from app.core import database as core_db
    from app.core.config import settings
    from database.models import BudgetScenario

    async def override_get_db():
        db = narrative.sessions()
        try:
            yield db
        finally:
            db.close()

    async def override_user_id():
        return USER

    async def run_sync_inline(function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", None)
    monkeypatch.setattr(settings, "DEV_USER_ID", USER)
    # The sandbox cannot start AnyIO's worker threads reliably.  Keep the real
    # ASGI route, routing dependencies and response-model validation in play,
    # but run its synchronous handler inline under the transport timeout.
    monkeypatch.setattr(fastapi.routing, "run_in_threadpool", run_sync_inline)
    app.dependency_overrides[core_db.get_db] = override_get_db
    app.dependency_overrides[get_current_user_id] = override_user_id
    try:
        with narrative.sessions() as db:
            scenario = db.get(BudgetScenario, narrative.ids["scenario"])
            scenario.narrative_source_hash = "not-a-sha256"
            scenario.narrative_blocks = {
                "blocks": raw_blocks,
            }
            db.commit()

        path = f"/api/v1/companies/{narrative.ids['company']}/scenarios/{narrative.ids['scenario']}/final-report"
        first, second = _asgi_get(app, path), _asgi_get(app, path)
        assert first.status_code == second.status_code == 200, first.text
        blocks = {item["id"]: item for item in first.json()["narrative"]}
        if expected_user_text is not None:
            assert (blocks["executive_summary"]["text"], blocks["executive_summary"]["provenance"]) == (
                expected_user_text, "user",
            )
            assert blocks["economic_outlook"]["provenance"] == "migrated"
            assert all(blocks[ident]["source_hash"] == "0" * 64 for ident in ("executive_summary", "economic_outlook"))
            assert all(blocks[ident]["updated_at"] == "1970-01-01T00:00:00Z" for ident in ("executive_summary", "economic_outlook"))
        assert (first.json()["source_hash"], first.json()["model_hash"]) == (
            second.json()["source_hash"], second.json()["model_hash"],
        )
        with narrative.sessions() as db:
            persisted = db.get(BudgetScenario, narrative.ids["scenario"])
            assert persisted.narrative_source_hash == "not-a-sha256"
            assert persisted.narrative_blocks["blocks"] == raw_blocks
        assert _asgi_get(
            app,
            f"/api/v1/companies/{narrative.ids['company']}/scenarios/{narrative.ids['foreign']}/final-report",
        ).status_code == 404
    finally:
        app.dependency_overrides.pop(core_db.get_db, None)
        app.dependency_overrides.pop(get_current_user_id, None)
