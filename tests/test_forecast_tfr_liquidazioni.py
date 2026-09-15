"""Il fondo TFR si scarica con le liquidazioni (spec 2026-09-15 §5.4).

Kit: sp15 30.000, ce08 120.000 con ce08b 0 → accantonamento = 120.000 × 0,70 / 13,5 = 6.222,22
(personale a crescita zero). Oracolo: 2027 fondo 36.222,22 senza liquidazioni; con 20.000 di
liquidazioni 16.222,22 e la cassa scende di 20.000 rispetto al gemello.
"""
from decimal import Decimal as D

from backend.app.services import assumptions_service, forecast_preview_service
from database.models import BudgetScenario
from tests.e2e_kit import memory_sessions, read_forecast_maps, seed_base_year

SP15, SP09 = "sp15_tfr", "sp09_disponibilita_liquide"


def _genera(user, rows):
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=user)
            sc = BudgetScenario(company_id=company_id, name=user, base_year=2026, scenario_type="budget")
            db.add(sc); db.commit()
            res = assumptions_service.bulk_upsert_assumptions(db, sc.id, [dict(r) for r in rows], auto_generate=True)
            prev = forecast_preview_service.preview_forecast(db, sc.id, [dict(r) for r in rows])
            anni = {anno: (sp, ce) for anno, sp, ce in read_forecast_maps(db, sc.id)} if res["forecast_generated"] else {}
            det = {y["year"]: y["details"] for y in prev["forecast_years"]}
            return res, anni, det
    finally:
        engine.dispose()


def _rows(**primo):
    r1 = {"forecast_year": 2027, "tax_rate": 27.9, "personnel_growth_pct": 0}
    r1.update(primo)
    return [r1, {"forecast_year": 2028, "tax_rate": 27.9, "personnel_growth_pct": 0}]


def test_liquidazione_scarica_il_fondo_e_la_cassa():
    senza = _genera("tfr-no", _rows())
    con = _genera("tfr-si", _rows(tfr_payments=20000))
    assert con[0]["forecast_generated"] is True, con[0]["message"]
    assert senza[1][2027][0][SP15] == D("36222.22") and con[1][2027][0][SP15] == D("16222.22")
    assert con[1][2027][0][SP09] == senza[1][2027][0][SP09] - D("20000.00")
    tfr = con[2][2027]["tfr"]
    assert {k: (v if k == "sospeso" else D(str(v))) for k, v in tfr.items()} == {
        "apertura": D("30000.00"), "accantonamento": D("6222.22"), "liquidazioni": D("20000.00"), "chiusura": D("16222.22"), "sospeso": False}
    assert D(str(senza[2][2027]["tfr"]["liquidazioni"])) == D("0.00")


def test_liquidazione_oltre_il_fondo_si_rifiuta():
    res, *_ = _genera("tfr-troppo", _rows(tfr_payments=40000))
    assert res["forecast_generated"] is False
    assert "Liquidazioni TFR 2027" in res["message"] and "Patrimoniale piano" in res["message"]


def test_sospeso_con_liquidazione():
    res, anni, det = _genera("tfr-sospeso", _rows(tfr_accrual_suspended=True, tfr_payments=10000))
    assert res["forecast_generated"] is True, res["message"]
    assert anni[2027][0][SP15] == D("20000.00") and det[2027]["tfr"]["sospeso"] is True
