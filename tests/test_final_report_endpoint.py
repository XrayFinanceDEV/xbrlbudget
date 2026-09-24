"""M1-06: final-report assembly, gates, and tenant-safe HTTP endpoint."""
import json
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


USER = "final-report-user"


@pytest.fixture()
def client(monkeypatch):
    from backend.app.main import app
    from app.core import database as core_db
    from app.core.config import settings
    from database.db import Base
    from database.models import (
        BalanceSheet, BudgetAssumptions, BudgetScenario, Company, FinancialYear,
        ForecastBalanceSheet, ForecastIncomeStatement, ForecastYear, IncomeStatement,
    )

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
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", None)
    monkeypatch.setattr(settings, "DEV_USER_ID", USER)
    with sessions() as db:
        mine, other = Company(name="Mine", sector=1, user_id=USER), Company(name="Other", sector=1, user_id="other")
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
        yield_ids = {"company": mine.id, "scenario": scenario.id, "foreign": foreign.id}
    with TestClient(app) as test_client:
        test_client.sessions, test_client.ids = sessions, yield_ids
        yield test_client
    app.dependency_overrides.pop(core_db.get_db, None)
    engine.dispose()


def _url(client, scenario):
    return f"/api/v1/companies/{client.ids['company']}/scenarios/{scenario}/final-report"


def _reason_codes(response):
    return {item["code"] for item in response.json()["diagnostics"]}


def test_get_is_read_only_and_foreign_scenario_or_source_is_404(client):
    from database.models import BudgetScenario, FinancialYear, ForecastYear
    with client.sessions() as db:
        before = {
            "forecast_count": db.query(ForecastYear).count(),
            "scenario": db.get(BudgetScenario, client.ids["scenario"]).updated_at,
            "historical": db.query(FinancialYear).filter_by(company_id=client.ids["company"], year=2026).one().updated_at,
        }
    baseline = client.get(_url(client, client.ids["scenario"]))
    assert baseline.status_code == 200, baseline.text
    assert baseline.json()["readiness"]["status"] == "ready"  # missing dossier prose is only info since 2026-09-24
    assert len(baseline.json()["chart_series"]) == 6
    repeat = client.get(_url(client, client.ids["scenario"]))
    assert (baseline.json()["source_hash"], baseline.json()["model_hash"]) == (repeat.json()["source_hash"], repeat.json()["model_hash"])
    with client.sessions() as db:
        assert db.query(ForecastYear).count() == before["forecast_count"]
        assert db.get(BudgetScenario, client.ids["scenario"]).updated_at == before["scenario"]
        assert db.query(FinancialYear).filter_by(company_id=client.ids["company"], year=2026).one().updated_at == before["historical"]
    assert client.get(_url(client, client.ids["foreign"])).status_code == 404
    with client.sessions() as db:
        row = db.get(BudgetScenario, client.ids["scenario"])
        row.workflow_type, row.source_scenario_id = "infrannuale", client.ids["foreign"]
        db.commit()
    assert client.get(_url(client, client.ids["scenario"])).status_code == 404
    with client.sessions() as db:
        row = db.get(BudgetScenario, client.ids["scenario"])
        row.source_scenario_id = None
        db.query(FinancialYear).filter_by(company_id=row.company_id, year=row.base_year).one().promoted_from_scenario_id = client.ids["foreign"]
        db.commit()
    assert client.get(_url(client, client.ids["scenario"])).status_code == 404


def test_stale_forecast_quadratura_and_adjustment_reconciliation_block_not_conflict(client):
    from database.models import BudgetAssumptions, BudgetScenario
    with client.sessions() as db:
        row = db.get(BudgetScenario, client.ids["scenario"])
        assumption = db.query(BudgetAssumptions).filter_by(scenario_id=row.id).one()
        assumption.updated_at = datetime.utcnow() + timedelta(minutes=2)
        db.commit()
    stale = client.get(_url(client, client.ids["scenario"]))
    assert stale.status_code == 200 and stale.json()["readiness"]["status"] == "blocked"
    assert "forecast_stale" in _reason_codes(stale)

    with client.sessions() as db:
        row = db.get(BudgetScenario, client.ids["scenario"])
        row.assumptions[0].updated_at = row.forecast_years[0].updated_at
        row.forecast_years[0].balance_sheet.sp09_disponibilita_liquide = Decimal("150")
        db.commit()
    unbalanced = client.get(_url(client, client.ids["scenario"]))
    assert unbalanced.status_code == 200 and "forecast_unbalanced" in _reason_codes(unbalanced)

    with client.sessions() as db:
        row = db.get(BudgetScenario, client.ids["scenario"])
        row.forecast_years[0].balance_sheet.sp09_disponibilita_liquide = Decimal("210")
        historical = db.query(__import__("database.models", fromlist=["FinancialYear"]).FinancialYear).filter_by(company_id=row.company_id, year=2026).one()
        historical.original_bs_snapshot = json.dumps({"sp09_disponibilita_liquide": "100", "sp11_capitale": "100"})
        historical.original_is_snapshot = json.dumps({"ce01_ricavi_vendite": "100"})
        historical.rettifiche_log = json.dumps([
            {"id": "r1", "edited_field": "sp09_disponibilita_liquide", "edited_label": "Cassa",
             "edit_delta": "10", "counterpart_field": "ce01_ricavi_vendite", "counterpart_label": "Ricavi",
             "counterpart_delta": "-10", "created_at": "2026-09-01T10:00:00"},
            {"id": "confirm", "entry_type": "confirm", "edited_field": "", "counterpart_field": "",
             "edited_label": "", "counterpart_label": "", "edit_delta": "0", "counterpart_delta": "0",
             "created_at": "2026-09-01T10:00:00"},
        ])
        db.commit()
    adjustments = client.get(_url(client, client.ids["scenario"]))
    assert adjustments.status_code == 200 and "adjustments_unreconciled" in _reason_codes(adjustments)


def test_ambiguous_legacy_chain_is_the_only_chain_conflict(client):
    from database.models import BudgetScenario
    with client.sessions() as db:
        row = db.get(BudgetScenario, client.ids["scenario"])
        row.workflow_type = None
        row.base_year = 2027
        db.add_all([
            BudgetScenario(company_id=row.company_id, name="I1", base_year=2026, scenario_type="infrannuale", period_months=6),
            BudgetScenario(company_id=row.company_id, name="I2", base_year=2026, scenario_type="infrannuale", period_months=9),
        ])
        db.commit()
    response = client.get(_url(client, client.ids["scenario"]))
    assert response.status_code == 409


def test_incomplete_forecast_is_blocked_and_non_infrannual_closing_is_omitted(client):
    from database.models import BudgetScenario
    with client.sessions() as db:
        row = db.get(BudgetScenario, client.ids["scenario"])
        row.forecast_years[0].income_statement = None
        db.commit()
    incomplete = client.get(_url(client, client.ids["scenario"]))
    assert incomplete.status_code == 200
    assert incomplete.json()["readiness"]["status"] == "blocked"
    assert "forecast_statements_incomplete" in _reason_codes(incomplete)
    assert "forecast_cashflow_missing" in _reason_codes(incomplete)

    with client.sessions() as db:
        db.get(BudgetScenario, client.ids["scenario"]).workflow_type = "startup"
        db.commit()
    startup = client.get(_url(client, client.ids["scenario"]))
    assert startup.status_code == 200
    assert "infrannual_closing" not in startup.json()


def test_linked_infrannuale_uses_source_progressivo_and_closing_provenance(client):
    from database.models import (
        BalanceSheet, BudgetAssumptions, BudgetScenario, FinancialYear, ForecastBalanceSheet,
        ForecastIncomeStatement, ForecastYear, IncomeStatement,
    )
    with client.sessions() as db:
        budget = db.get(BudgetScenario, client.ids["scenario"])
        source = BudgetScenario(company_id=budget.company_id, name="9M source", base_year=2026,
                                scenario_type="infrannuale", period_months=9,
                                workflow_type="infrannuale", extra_accounting_alerts={"banche": True})
        source_forecast = ForecastYear(year=2027)
        source_forecast.balance_sheet = ForecastBalanceSheet(sp09_disponibilita_liquide=Decimal("130"))
        source_forecast.income_statement = ForecastIncomeStatement(
            ce01_ricavi_vendite=Decimal("125"),
            ce02_variazioni_rimanenze=Decimal("30"),
        )
        source.forecast_years = [source_forecast]
        source.assumptions = [BudgetAssumptions(
            forecast_year=2027,
            ce01_override=Decimal("125"),
            sp_overrides={"sp09_disponibilita_liquide": "130.00"},
            explicitly_supplied_fields=["ce01_override", "sp_overrides"],
        )]
        db.add(source); db.flush()
        partial = FinancialYear(company_id=budget.company_id, year=2027, period_months=9,
                                original_bs_snapshot=json.dumps({"sp09_disponibilita_liquide": "80"}),
                                original_is_snapshot=json.dumps({"ce01_ricavi_vendite": "80"}),
                                rettifiche_log=json.dumps([{ "id": "partial-r1", "edited_field": "ce01_ricavi_vendite",
                                    "edited_label": "Ricavi", "edit_delta": "10", "counterpart_field": "sp09_disponibilita_liquide",
                                    "counterpart_label": "Cassa", "counterpart_delta": "10", "created_at": "2027-09-30T10:00:00" },
                                    {"id": "confirm", "entry_type": "confirm", "edited_field": "", "edited_label": "",
                                     "edit_delta": "0", "counterpart_field": "", "counterpart_label": "", "counterpart_delta": "0",
                                     "created_at": "2027-09-30T10:00:00"}]))
        partial.balance_sheet = BalanceSheet(sp09_disponibilita_liquide=Decimal("90"))
        partial.income_statement = IncomeStatement(ce01_ricavi_vendite=Decimal("90"))
        db.add(partial)
        db.flush()
        partial_id = partial.id
        budget.base_year, budget.workflow_type, budget.source_scenario_id = 2027, "infrannuale", source.id
        db.commit()
    response = client.get(_url(client, client.ids["scenario"]))
    assert response.status_code == 200, response.text
    report = response.json()
    revenue = next(value for value in report["infrannual_closing"]["values"] if value["code"] == "ce01_ricavi_vendite")
    assert report["infrannual_closing"]["period_end"] == "2027-09-30"
    assert (revenue["observed"], revenue["comparable"], revenue["automatic"], revenue["override"], revenue["closing_used"]) == (
        "90.00", "100.00", None, "125.00", "125.00",
    )
    automatic = next(value for value in report["infrannual_closing"]["values"] if value["code"] == "ce02_variazioni_rimanenze")
    assert automatic["automatic"] == "30.00" and automatic["override"] is None
    cash = next(value for value in report["infrannual_closing"]["values"] if value["code"] == "sp09_disponibilita_liquide")
    assert (cash["observed"], cash["automatic"], cash["override"], cash["closing_used"]) == (
        "90.00", None, "130.00", "130.00",
    )
    assert report["adjustments"]["entries"][0]["id"] == "partial-r1"
    assert report["infrannual_closing"]["extra_accounting_alerts"]["banche"] is True
    adjustment_revision = next(item for item in report["source_revisions"] if item["source"] == "adjustments")
    assert adjustment_revision["identifier"] == str(partial_id)
    assert adjustment_revision["revision"] is None
    assert adjustment_revision["revision_at"] is not None


def test_required_infrannual_chain_missing_is_a_blocked_report(client):
    from database.models import BudgetScenario

    with client.sessions() as db:
        scenario = db.get(BudgetScenario, client.ids["scenario"])
        scenario.workflow_type = "infrannuale"
        scenario.source_scenario_id = None
        db.commit()

    response = client.get(_url(client, client.ids["scenario"]))
    assert response.status_code == 200
    assert response.json()["readiness"]["status"] == "blocked"
    assert "chain_blocked" in _reason_codes(response)


def test_forecast_order_parity_and_material_mutation_change_hashes(client):
    from app.services.analysis_service import get_complete_analysis
    from database.models import BudgetAssumptions, BudgetScenario, ForecastBalanceSheet, ForecastIncomeStatement, ForecastYear
    with client.sessions() as db:
        scenario = db.get(BudgetScenario, client.ids["scenario"])
        # Persist 2028 first, then insert 2027: relationship order is deliberately
        # not the report contract order.
        original = scenario.forecast_years[0]
        original.year = 2028
        scenario.assumptions[0].forecast_year = 2028
        earlier = ForecastYear(year=2027)
        earlier.balance_sheet = ForecastBalanceSheet(sp09_disponibilita_liquide=Decimal("210"), sp11_capitale=Decimal("100"), sp13_utile_perdita=Decimal("110"))
        earlier.income_statement = ForecastIncomeStatement(ce01_ricavi_vendite=Decimal("110"))
        scenario.forecast_years.append(earlier)
        scenario.assumptions.append(BudgetAssumptions(forecast_year=2027, explicitly_supplied_fields=[]))
        db.commit()
        analysis = get_complete_analysis(db, scenario.company_id, scenario.id)
    first = client.get(_url(client, client.ids["scenario"]))
    assert first.status_code == 200, first.text
    report = first.json()
    assert [year["year"] for year in report["forecast"]["years"]] == [2027, 2028]
    assert report["chart_series"][0]["categories"] == [2027, 2028]
    report_revenue = next(line["value"] for line in report["forecast"]["years"][0]["income_statement"] if line["code"] == "ce01_ricavi_vendite")
    assert Decimal(report_revenue) == Decimal(str(analysis["forecast_years"][0]["income_statement"]["ce01_ricavi_vendite"]))

    with client.sessions() as db:
        row = db.get(BudgetScenario, client.ids["scenario"])
        changed = next(item for item in row.forecast_years if item.year == 2027)
        changed.income_statement.ce01_ricavi_vendite = Decimal("111")
        changed.balance_sheet.sp09_disponibilita_liquide = Decimal("211")
        changed.balance_sheet.sp13_utile_perdita = Decimal("111")
        db.commit()
    second = client.get(_url(client, client.ids["scenario"]))
    assert second.status_code == 200
    assert first.json()["source_hash"] != second.json()["source_hash"]
    assert first.json()["model_hash"] != second.json()["model_hash"]
