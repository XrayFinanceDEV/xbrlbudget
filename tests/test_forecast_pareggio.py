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


def test_pareggio_porta_dentro_lavori_interni_rimanenze_e_accantonamenti():
    """Collaudo di fine lotto, R1: il pareggio si calcola sul MOL del CE, non su ricavi + altri ricavi.

    Kit di sopra piu' lavori interni 50.000 (ce03) e variazione rimanenze materie 10.000 (ce10):
    fissi operativi = 275.000 + 10.000 - 50.000 = 235.000; pareggio = 235.000 / 0,65 = 361.538,46;
    MOL del CE = 600.000 + 50.000 - 210.000 - 275.000 - 10.000 = 155.000 = (600.000 - 361.538,46) x 0,65.
    """
    out = _preview("bep-ce03", [{"forecast_year": 2027, "tax_rate": 27.9,
                                 "ce03_override": 50000, "ce10_override": 10000}])
    anno = out["forecast_years"][0]
    p = anno["details"]["pareggio"]
    assert D(str(p["costi_fissi_operativi"])) == D("235000.00")
    assert D(str(p["fatturato_pareggio"])) == D("361538.46")
    ce = anno["income_statement"]
    mol = (D(str(ce["ce01_ricavi_vendite"])) + D(str(ce["ce03_lavori_interni"])) + D(str(ce["ce04_altri_ricavi"]))
           - D(str(ce["ce05_materie_prime"])) - D(str(ce["ce06_servizi"])) - D(str(ce["ce07_godimento_beni"]))
           - D(str(ce["ce08_costi_personale"])) - D(str(ce["ce10_var_rimanenze_mat_prime"]))
           - D(str(ce["ce12_oneri_diversi"])))
    assert mol == D("155000")
    assert abs((D("600000") - D(str(p["fatturato_pareggio"]))) * D(str(p["margine_contribuzione_pct"])) / 100 - mol) < D("0.01")


def test_pareggio_nullo_con_override_di_ce05():
    out = _preview("bep-override", [{"forecast_year": 2027, "tax_rate": 27.9, "ce05_override": 100000}])
    p = out["forecast_years"][0]["details"]["pareggio"]
    assert all(v is None for v in p.values())


def test_non_incassato_dichiarato():
    piano = {"crediti_commerciali": {"opening": 120000, "amounts": [120000], "non_incassato": True}}
    out = _preview("non-incassato", [{"forecast_year": 2027, "tax_rate": 27.9, "pregresso": piano}])
    assert out["error"] is None
    assert out["forecast_years"][0]["details"]["pregresso"]["crediti_commerciali"]["non_incassato"] is True
