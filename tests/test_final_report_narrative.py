"""M1-07 unified narrative endpoints, freshness, and legacy compatibility."""
import json
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


USER = "final-report-narrative-user"
BLOCKS = (
    "executive_summary", "adjustments_and_closing", "budget_assumptions",
    "economic_outlook", "financial_outlook", "risks_and_actions",
)


@pytest.fixture()
def narrative():
    # The application bootstrap installs backend/ on sys.path.  It must happen
    # before app.* imports, otherwise the same module can be loaded twice.
    from backend.app.main import app
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
    with narrative.sessions() as db, pytest.raises(HTTPException) as error:
        reports.generate_final_report_narrative_endpoint(
            narrative.ids["company"], narrative.ids["foreign"], USER, db,
        )
    assert error.value.status_code == 404
