import json
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.services.ai_comments_service import (
    get_infrannuale_comments,
    save_infrannuale_comments,
)
from database.db import Base
from database.models import BudgetScenario, Company, ForecastYear


def _status(*, comments_at, forecast_at, with_comments=True):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    company = Company(name="Commenti", tax_id="COMMENTS", sector=1)
    db.add(company)
    db.flush()
    scenario = BudgetScenario(
        company_id=company.id,
        name="infra",
        base_year=2025,
        scenario_type="infrannuale",
        ai_comments_infrannuale=json.dumps({"overall": "test"}) if with_comments else None,
        ai_comments_infrannuale_updated_at=comments_at,
    )
    db.add(scenario)
    db.flush()
    if forecast_at is not None:
        forecast = ForecastYear(scenario_id=scenario.id, year=2026)
        db.add(forecast)
        db.flush()
        forecast.created_at = forecast_at
        forecast.updated_at = forecast_at
    db.commit()
    out = get_infrannuale_comments(db, scenario.id)
    db.close()
    engine.dispose()
    return out


def test_commenti_piu_vecchi_della_proiezione_sono_stantii():
    old = datetime(2026, 9, 12, 8, 0)
    out = _status(comments_at=old, forecast_at=old + timedelta(minutes=1))
    assert out["comments_stale"] is True
    assert out["comments"] == {"overall": "test"}


def test_commenti_salvati_dopo_la_proiezione_sono_allineati():
    old = datetime(2026, 9, 12, 8, 0)
    out = _status(comments_at=old + timedelta(minutes=1), forecast_at=old)
    assert out["comments_stale"] is False


def test_commenti_legacy_senza_timestamp_non_si_dichiarano_aggiornati():
    out = _status(
        comments_at=None,
        forecast_at=datetime(2026, 9, 12, 8, 0),
    )
    assert out["comments_stale"] is True
    assert out["comments_updated_at"] is None


def test_senza_commenti_non_ce_un_avviso_da_mostrare():
    out = _status(
        comments_at=None,
        forecast_at=datetime(2026, 9, 12, 8, 0),
        with_comments=False,
    )
    assert out["comments_stale"] is False


def test_senza_proiezione_non_ce_un_confronto_di_freschezza():
    out = _status(comments_at=None, forecast_at=None)
    assert out["comments_stale"] is False
    assert out["forecast_updated_at"] is None


def test_salvare_i_commenti_registra_la_data_e_li_rende_allineati():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    company = Company(name="Salva commenti", tax_id="SAVE-COMMENTS", sector=1)
    db.add(company)
    db.flush()
    scenario = BudgetScenario(
        company_id=company.id,
        name="infra",
        base_year=2025,
        scenario_type="infrannuale",
    )
    db.add(scenario)
    db.flush()
    db.add(ForecastYear(scenario_id=scenario.id, year=2026))
    db.commit()

    save_infrannuale_comments(db, scenario.id, {"overall": "aggiornato"})
    out = get_infrannuale_comments(db, scenario.id)

    assert out["comments"] == {"overall": "aggiornato"}
    assert out["comments_updated_at"].endswith("Z")
    assert out["comments_stale"] is False
    db.close()
    engine.dispose()
