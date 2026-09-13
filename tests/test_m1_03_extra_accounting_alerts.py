"""M1-03 HTTP contract for persisted infrannuale extra-accounting alerts."""
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


USER = "m1-03-user"
KEYS = ("retribuzioni", "fornitori", "banche", "inps", "inail", "riscossione", "iva")


def _alerts(**enabled):
    return {key: enabled.get(key, False) for key in KEYS}


@pytest.fixture()
def client(monkeypatch):
    # Importing backend.app.main first keeps the dependency override bound to
    # the same `app.*` modules that the live router imports.
    from backend.app.main import app

    from app.core import database as core_db
    from app.core.config import settings
    from database.db import Base
    from database.models import BudgetScenario, Company

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
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
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", None)
    monkeypatch.setattr(settings, "DEV_USER_ID", USER)

    with sessions() as db:
        company = Company(name="M1-03", sector=1, user_id=USER)
        other_company = Company(name="Other", sector=1, user_id="other-user")
        db.add_all([company, other_company])
        db.flush()
        infra = BudgetScenario(
            company_id=company.id, name="Infra", base_year=2025,
            scenario_type="infrannuale", period_months=6,
        )
        budget = BudgetScenario(
            company_id=company.id, name="Budget", base_year=2025, scenario_type="budget",
        )
        foreign = BudgetScenario(
            company_id=other_company.id, name="Foreign", base_year=2025,
            scenario_type="infrannuale", period_months=6,
        )
        twelve_month = BudgetScenario(
            company_id=company.id, name="Infra 12M", base_year=2025,
            scenario_type="infrannuale", period_months=12,
        )
        legacy_sparse = BudgetScenario(
            company_id=company.id, name="Legacy sparse", base_year=2025,
            scenario_type="infrannuale", period_months=6,
            extra_accounting_alerts={"banche": True, "iva": "not a bool"},
            extra_accounting_alerts_updated_at=datetime.utcnow(),
        )
        db.add_all([infra, budget, foreign, twelve_month, legacy_sparse])
        db.commit()
        ids = {
            "company": company.id, "infra": infra.id, "budget": budget.id,
            "foreign_company": other_company.id, "foreign": foreign.id,
            "twelve_month": twelve_month.id, "legacy_sparse": legacy_sparse.id,
        }

    with TestClient(app) as test_client:
        test_client.ids = ids
        test_client.sessions = sessions
        yield test_client

    app.dependency_overrides.pop(core_db.get_db, None)
    engine.dispose()


def _url(client, scenario_id):
    return (
        f"/api/v1/companies/{client.ids['company']}/scenarios/{scenario_id}"
        "/extra-accounting-alerts"
    )


def test_get_defaults_null_and_put_round_trips_all_keys_including_false(client):
    default = client.get(_url(client, client.ids["infra"]))
    assert default.status_code == 200, default.text
    assert default.json() == {"alerts": _alerts(), "updated_at": None}

    payload = _alerts(banche=True, inps=True)
    saved = client.put(_url(client, client.ids["infra"]), json=payload)
    assert saved.status_code == 200, saved.text
    assert saved.json()["alerts"] == payload
    assert saved.json()["updated_at"] is not None
    assert saved.json()["updated_at"].endswith(("Z", "+00:00"))

    generic = client.get(
        f"/api/v1/companies/{client.ids['company']}/scenarios/{client.ids['infra']}"
    )
    assert generic.status_code == 200, generic.text
    assert generic.json()["extra_accounting_alerts_updated_at"].endswith(("Z", "+00:00"))

    from database.models import BudgetScenario
    with client.sessions() as db:
        row = db.get(BudgetScenario, client.ids["infra"])
        assert row.extra_accounting_alerts_updated_at.tzinfo is None

    # A separate request/session reads the JSON stored by the PUT transaction.
    reloaded = client.get(_url(client, client.ids["infra"]))
    assert reloaded.status_code == 200
    assert reloaded.json()["alerts"] == payload
    assert reloaded.json()["updated_at"] is not None
    assert reloaded.json()["updated_at"].endswith(("Z", "+00:00"))


def test_get_normalizes_legacy_sparse_json_and_allows_infrannuale_12_months(client):
    legacy = client.get(_url(client, client.ids["legacy_sparse"]))
    assert legacy.status_code == 200, legacy.text
    assert legacy.json()["alerts"] == _alerts(banche=True)
    assert legacy.json()["updated_at"].endswith(("Z", "+00:00"))

    twelve_month = client.get(_url(client, client.ids["twelve_month"]))
    assert twelve_month.status_code == 200, twelve_month.text
    assert twelve_month.json()["alerts"] == _alerts()


def test_foreign_scenario_is_not_visible(client):
    get_response = client.get(_url(client, client.ids["foreign"]))
    put_response = client.put(_url(client, client.ids["foreign"]), json=_alerts())
    assert get_response.status_code == 404
    assert put_response.status_code == 404


def test_budget_scenario_rejects_alert_resource(client):
    get_response = client.get(_url(client, client.ids["budget"]))
    put_response = client.put(_url(client, client.ids["budget"]), json=_alerts())
    assert get_response.status_code == 422
    assert put_response.status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {"banche": True},
        {**_alerts(), "inventata": True},
        {**_alerts(), "banche": "true"},
    ],
)
def test_put_requires_exact_strict_boolean_map(client, payload):
    response = client.put(_url(client, client.ids["infra"]), json=payload)
    assert response.status_code == 422


@pytest.mark.parametrize(
    "field,value",
    [
        ("extra_accounting_alerts", _alerts()),
        ("extra_accounting_alerts_updated_at", "2026-09-14T00:00:00Z"),
    ],
)
def test_generic_scenario_writes_and_create_time_fields_are_rejected(client, field, value):
    generic = client.put(
        f"/api/v1/companies/{client.ids['company']}/scenarios/{client.ids['infra']}",
        json={field: value},
    )
    assert generic.status_code == 422

    create = client.post(
        f"/api/v1/companies/{client.ids['company']}/scenarios",
        json={
            "company_id": client.ids["company"], "name": "forged", "base_year": 2025,
            field: value,
        },
    )
    assert create.status_code == 422
