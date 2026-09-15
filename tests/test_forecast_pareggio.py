"""Il punto di pareggio sul MOL lo dichiara il motore (spec 2026-09-15 §4.3, decisione 4).

Kit a crescita zero e quota fissa 40%: ricavi 600.000; variabili = 0,6 × (200.000 + 150.000) =
210.000; fissi = 140.000 + 120.000 + 10.000 + 5.000 = 275.000; altri ricavi 0 → fissi operativi
275.000; margine di contribuzione 65% → pareggio 423.076,92; margine di sicurezza 176.923,08 (29,49%).
"""
from decimal import Decimal as D

from backend.app.services import assumptions_service, forecast_preview_service  # noqa: F401 (assumptions_service import order puts backend/ on sys.path)
from database.models import BudgetScenario
from tests.e2e_kit import memory_sessions, seed_base_year


def _preview(user, rows):
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=user)
            sc = BudgetScenario(company_id=company_id, name=user, base_year=2026, scenario_type="budget")
            db.add(sc); db.commit()
            return forecast_preview_service.preview_forecast(db, sc.id, rows)
    finally:
        engine.dispose()


def test_pareggio_dichiarato():
    out = _preview("bep", [{"forecast_year": 2027, "tax_rate": 27.9}])
    p = out["forecast_years"][0]["details"]["pareggio"]
    assert p == {"costi_variabili": D("210000.00"), "costi_fissi": D("275000.00"),
                 "costi_fissi_operativi": D("275000.00"), "margine_contribuzione_pct": D("65.00"),
                 "fatturato_pareggio": D("423076.92"), "margine_sicurezza": D("176923.08"),
                 "margine_sicurezza_pct": D("29.49")}


def test_pareggio_nullo_con_override_di_ce05():
    out = _preview("bep-override", [{"forecast_year": 2027, "tax_rate": 27.9, "ce05_override": 100000}])
    p = out["forecast_years"][0]["details"]["pareggio"]
    assert all(v is None for v in p.values())


def test_non_incassato_dichiarato():
    piano = {"crediti_commerciali": {"opening": 120000, "amounts": [120000], "non_incassato": True}}
    out = _preview("non-incassato", [{"forecast_year": 2027, "tax_rate": 27.9, "pregresso": piano}])
    assert out["error"] is None
    assert out["forecast_years"][0]["details"]["pregresso"]["crediti_commerciali"]["non_incassato"] is True
