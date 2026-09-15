"""M1-02: server-owned scenario lineage and startup provenance."""
from decimal import Decimal

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.api.v1.budget_scenarios import create_budget_scenario
from backend.app.schemas.budget import BudgetScenarioCreate, BudgetScenarioUpdate
from backend.app.services.promote_service import promote_projection_to_financial_year
from backend.app.services.scenario_provenance import (
    ScenarioProvenance, derive_scenario_provenance, find_active_reusable_scenario,
)
from database.db import Base
from database.models import (
    BalanceSheet, BudgetScenario, Company, FinancialYear, ForecastBalanceSheet,
    ForecastIncomeStatement, ForecastYear, IncomeStatement,
)


USER = "m1-02-user"


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


def _company(db, name="M1-02"):
    company = Company(name=name, sector=1, user_id=USER)
    db.add(company)
    db.flush()
    return company


def _full_year(db, company_id, year, *, promoted_from=None, origin=None, startup=False):
    financial_year = FinancialYear(
        company_id=company_id,
        year=year,
        period_months=None,
        promoted_from_scenario_id=promoted_from,
        workflow_origin=origin,
    )
    db.add(financial_year)
    db.flush()
    values = {}
    if startup:
        values = {
            "sp09_disponibilita_liquide": Decimal("1000"),
            "sp11_capitale": Decimal("1000"),
        }
    db.add(BalanceSheet(financial_year_id=financial_year.id, **values))
    db.add(IncomeStatement(financial_year_id=financial_year.id))
    db.flush()
    return financial_year


def _create(db, company_id, **values):
    request = BudgetScenarioCreate(
        company_id=company_id,
        name=values.pop("name", "Budget 2027"),
        base_year=values.pop("base_year", 2026),
        **values,
    )
    return create_budget_scenario(company_id, request, user_id=USER, db=db)


def test_forged_lineage_is_rejected_before_creation(db_session):
    company = _company(db_session)
    _full_year(db_session, company.id, 2026)
    with pytest.raises(HTTPException) as error:
        _create(db_session, company.id, source_scenario_id=99)
    assert error.value.status_code == 422
    assert db_session.query(BudgetScenario).count() == 0


def test_promoted_infrannuale_derives_exact_lineage_and_explicitly_reuses_it(db_session):
    company = _company(db_session)
    source = BudgetScenario(
        company_id=company.id, name="Infra 6M", base_year=2025,
        scenario_type="infrannuale", period_months=6,
    )
    db_session.add(source)
    db_session.flush()
    _full_year(
        db_session, company.id, 2026,
        promoted_from=source.id, origin="promoted_projection",
    )

    first = _create(db_session, company.id, name="  Budget   2027 ")
    second = _create(
        db_session, company.id, name="budget 2027", reuse_existing=True,
    )

    assert first.id == second.id
    assert first.workflow_type == "infrannuale"
    assert first.source_scenario_id == source.id


def test_same_name_creation_is_distinct_unless_reuse_is_explicit(db_session):
    company = _company(db_session)
    _full_year(db_session, company.id, 2026)

    first = _create(db_session, company.id, name="  Budget   2027 ")
    second = _create(db_session, company.id, name="budget 2027")
    reused = _create(
        db_session, company.id, name="BUDGET 2027", reuse_existing=True,
    )

    assert first.id != second.id
    assert reused.id == first.id


def test_explicit_reuse_identity_includes_scenario_period(db_session):
    company = _company(db_session)
    provenance = ScenarioProvenance("bilancio", None)
    six_month = BudgetScenario(
        company_id=company.id, name="Budget 2027", base_year=2026,
        scenario_type="budget", period_months=6, workflow_type="bilancio",
    )
    seven_month = BudgetScenario(
        company_id=company.id, name="Budget 2027", base_year=2026,
        scenario_type="budget", period_months=7, workflow_type="bilancio",
    )
    db_session.add_all([six_month, seven_month])
    db_session.commit()

    reused = find_active_reusable_scenario(
        db_session, company_id=company.id, base_year=2026, name=" budget 2027 ",
        scenario_type="budget", period_months=7, provenance=provenance,
    )
    assert reused.id == seven_month.id


@pytest.mark.parametrize(
    "immutable_field,value",
    [
        ("source_scenario_id", 12),
        ("workflow_type", "bilancio"),
        ("base_year", 2027),
        ("scenario_type", "infrannuale"),
        ("period_months", 6),
    ],
)
def test_update_rejects_lineage_and_topology_fields(immutable_field, value):
    with pytest.raises(ValidationError) as error:
        BudgetScenarioUpdate.model_validate({immutable_field: value})
    assert error.value.errors()[0]["type"] == "extra_forbidden"


def test_archived_or_wrong_lineage_is_never_reused(db_session):
    company = _company(db_session)
    source = BudgetScenario(
        company_id=company.id, name="Infra 9M", base_year=2025,
        scenario_type="infrannuale", period_months=9,
    )
    db_session.add(source)
    db_session.flush()
    _full_year(db_session, company.id, 2026, promoted_from=source.id, origin="promoted_projection")
    db_session.add_all([
        BudgetScenario(
            company_id=company.id, name="Budget 2027", base_year=2026,
            workflow_type="bilancio", is_active=1,
        ),
        BudgetScenario(
            company_id=company.id, name="Budget 2027", base_year=2026,
            workflow_type="infrannuale", source_scenario_id=source.id, is_active=0,
        ),
    ])
    db_session.commit()

    created = _create(db_session, company.id)
    assert created.is_active == 1
    assert created.workflow_type == "infrannuale"
    assert created.source_scenario_id == source.id
    assert db_session.query(BudgetScenario).filter(
        BudgetScenario.workflow_type == "infrannuale",
        BudgetScenario.source_scenario_id == source.id,
        BudgetScenario.is_active == 1,
    ).count() == 1


def test_cross_company_or_missing_promoted_source_is_not_disclosed_as_lineage(db_session):
    company = _company(db_session, "Owner")
    foreign = _company(db_session, "Foreign")
    foreign_source = BudgetScenario(
        company_id=foreign.id, name="Foreign 6M", base_year=2025,
        scenario_type="infrannuale", period_months=6,
    )
    db_session.add(foreign_source)
    db_session.flush()
    _full_year(
        db_session, company.id, 2026,
        promoted_from=foreign_source.id, origin="promoted_projection",
    )
    with pytest.raises(HTTPException) as cross_company:
        _create(db_session, company.id)
    assert cross_company.value.status_code == 404

    company_two = _company(db_session, "Missing")
    _full_year(db_session, company_two.id, 2026, promoted_from=9999, origin="promoted_projection")
    with pytest.raises(HTTPException) as missing:
        _create(db_session, company_two.id)
    assert missing.value.status_code == 404


def test_12_month_source_and_regular_year_are_not_promoted_lineage(db_session):
    company = _company(db_session)
    source = BudgetScenario(
        company_id=company.id, name="Infra 12M", base_year=2025,
        scenario_type="infrannuale", period_months=12,
    )
    db_session.add(source)
    db_session.flush()
    _full_year(db_session, company.id, 2026, promoted_from=source.id, origin="promoted_projection")

    derived = derive_scenario_provenance(
        db_session, company_id=company.id, base_year=2026, scenario_type="budget",
        period_months=None, workflow_intent=None,
    )
    assert derived.workflow_type == "bilancio"
    assert derived.source_scenario_id is None


def test_startup_intent_requires_and_recognizes_the_opening_balance(db_session):
    company = _company(db_session)
    _full_year(db_session, company.id, 2026, startup=True)
    startup = _create(db_session, company.id, workflow_intent="startup")
    assert startup.workflow_type == "startup"
    assert startup.source_scenario_id is None

    invalid_company = _company(db_session, "Invalid startup")
    invalid = _full_year(db_session, invalid_company.id, 2026, startup=True)
    invalid.balance_sheet.sp06_crediti_breve = Decimal("1")
    db_session.commit()
    with pytest.raises(HTTPException) as error:
        _create(db_session, invalid_company.id, workflow_intent="startup")
    assert error.value.status_code == 400


def _forecast(db, scenario, year=2026):
    forecast = ForecastYear(scenario_id=scenario.id, year=year)
    db.add(forecast)
    db.flush()
    db.add(ForecastBalanceSheet(
        forecast_year_id=forecast.id, sp09_disponibilita_liquide=Decimal("100"),
        sp11_capitale=Decimal("100"),
    ))
    db.add(ForecastIncomeStatement(forecast_year_id=forecast.id))
    db.commit()


@pytest.fixture()
def valid_promote(monkeypatch):
    from types import SimpleNamespace
    from backend.app.services import promote_service
    from importers import iv_cee_hierarchy

    validation = SimpleNamespace(
        semantic_valid=True, quadra=True, totale_attivo=Decimal("100"),
        totale_passivo=Decimal("100"), utile_ce=Decimal("0"), sp13=Decimal("0"),
        warnings=[],
    )
    monkeypatch.setattr(promote_service, "forecast_staleness", lambda scenario: (None, None, False))
    monkeypatch.setattr(iv_cee_hierarchy, "check_quadratura", lambda *_: validation)


def test_promote_sets_lineage_for_1_to_11_month_sources(db_session, valid_promote):
    company = _company(db_session)
    source = BudgetScenario(
        company_id=company.id, name="Infra", base_year=2025,
        scenario_type="infrannuale", period_months=6,
    )
    db_session.add(source)
    db_session.flush()
    _forecast(db_session, source)

    result = promote_projection_to_financial_year(db_session, source.id)
    promoted = db_session.get(FinancialYear, result["financial_year_id"])
    assert promoted.promoted_from_scenario_id == source.id
    assert promoted.workflow_origin == "promoted_projection"


def test_promote_12_month_copy_is_not_a_lineage_source(db_session, valid_promote):
    company = _company(db_session)
    source = BudgetScenario(
        company_id=company.id, name="Infra 12", base_year=2025,
        scenario_type="infrannuale", period_months=12,
    )
    db_session.add(source)
    db_session.flush()
    _forecast(db_session, source)

    result = promote_projection_to_financial_year(db_session, source.id)
    promoted = db_session.get(FinancialYear, result["financial_year_id"])
    assert promoted.promoted_from_scenario_id is None
    assert promoted.workflow_origin is None


def test_repromotion_preserves_same_source_and_archives_different_lineage(db_session, valid_promote):
    company = _company(db_session)
    old_source = BudgetScenario(
        company_id=company.id, name="Old 6M", base_year=2025,
        scenario_type="infrannuale", period_months=6,
    )
    new_source = BudgetScenario(
        company_id=company.id, name="New 9M", base_year=2025,
        scenario_type="infrannuale", period_months=9,
    )
    db_session.add_all([old_source, new_source])
    db_session.flush()
    _forecast(db_session, new_source)
    _full_year(
        db_session, company.id, 2026,
        promoted_from=old_source.id, origin="promoted_projection",
    )
    stale = BudgetScenario(
        company_id=company.id, name="Budget stale", base_year=2026,
        workflow_type="infrannuale", source_scenario_id=old_source.id, is_active=1,
    )
    matching = BudgetScenario(
        company_id=company.id, name="Budget matching", base_year=2026,
        workflow_type="infrannuale", source_scenario_id=new_source.id, is_active=1,
    )
    db_session.add_all([stale, matching])
    db_session.commit()

    promote_projection_to_financial_year(db_session, new_source.id)
    assert db_session.get(BudgetScenario, stale.id).is_active == 0
    assert db_session.get(BudgetScenario, matching.id).is_active == 1

    # A second promote from the same source must leave its active budget alone.
    promote_projection_to_financial_year(db_session, new_source.id)
    assert db_session.get(BudgetScenario, matching.id).is_active == 1


def test_12_month_replacement_archives_old_lineage_but_keeps_bilancio(db_session, valid_promote):
    company = _company(db_session)
    old_source = BudgetScenario(
        company_id=company.id, name="Old 6M", base_year=2025,
        scenario_type="infrannuale", period_months=6,
    )
    full_year_source = BudgetScenario(
        company_id=company.id, name="New 12M", base_year=2025,
        scenario_type="infrannuale", period_months=12,
    )
    db_session.add_all([old_source, full_year_source])
    db_session.flush()
    _forecast(db_session, full_year_source)
    _full_year(
        db_session, company.id, 2026,
        promoted_from=old_source.id, origin="promoted_projection",
    )
    old_lineage = BudgetScenario(
        company_id=company.id, name="Budget old lineage", base_year=2026,
        workflow_type="infrannuale", source_scenario_id=old_source.id, is_active=1,
    )
    ordinary_budget = BudgetScenario(
        company_id=company.id, name="Budget ordinary", base_year=2026,
        workflow_type="bilancio", source_scenario_id=None, is_active=1,
    )
    db_session.add_all([old_lineage, ordinary_budget])
    db_session.commit()

    promote_projection_to_financial_year(db_session, full_year_source.id)

    assert db_session.get(BudgetScenario, old_lineage.id).is_active == 0
    assert db_session.get(BudgetScenario, ordinary_budget.id).is_active == 1
