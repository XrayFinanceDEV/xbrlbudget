"""R11 / #63 — un piano pregresso `crediti_tributari_breve` che non incassa tutto.

`runoff_schedule` dichiara `residual_long` per la parte che il calendario non
incassa entro l'anno dopo; lo SP persistito deve dire la stessa cosa: la parte
breve in `sp06e`, la parte oltre 12 mesi in `sp07e`. Prima restava tutto in
`sp06e` e `sp07e` non si muoveva, contro ciò che `details['pregresso']` dichiara.
È una riclassifica breve -> lungo: totale attivo e cassa non cambiano.
"""
from decimal import Decimal as D

import pytest

from backend.app.api.v1 import budget_scenarios
from backend.app.schemas.budget import BudgetScenarioCreate
from database import models
from tests.e2e_kit import memory_sessions, read_forecast_maps, seed_base_year

USER = "riclass-tributari"
ANNI = (2027, 2028, 2029)
MANUALE = {"sp16e_growth_pct": 0, "sp06e_growth_pct": 0}


def _genera(db, company_id, rows):
    sc = budget_scenarios.create_budget_scenario(
        company_id, BudgetScenarioCreate(company_id=company_id, name="r11", base_year=2026,
                                         scenario_type="budget"),
        user_id=USER, db=db)
    res = budget_scenarios.bulk_upsert_assumptions(
        company_id, sc.id, request={"assumptions": rows, "auto_generate": True}, user_id=USER, db=db)
    assert res["forecast_generated"] is True, res["message"]
    prev = budget_scenarios.preview_forecast_route(
        company_id, sc.id, request={"assumptions": rows}, user_id=USER, db=db)
    return sc, read_forecast_maps(db, sc.id), prev["forecast_years"]


def _base(db, company_id):
    fy = db.query(models.FinancialYear).filter_by(company_id=company_id).one()
    bs = db.query(models.BalanceSheet).filter_by(financial_year_id=fy.id).one()
    bs.sp06a_crediti_clienti_breve = D("100000")
    bs.sp06e_crediti_tributari_breve = D("20000")
    bs.sp07_crediti_lungo = D("10000")
    bs.sp07e_crediti_tributari_lungo = D("10000")
    bs.sp09_disponibilita_liquide = D("20000")
    db.commit()


@pytest.mark.parametrize("manuale", [True, False], ids=["via_manuale", "saldo_acconto"])
def test_residuo_non_incassato_va_oltre_12_mesi_in_sp07e(monkeypatch, manuale):
    """Apertura 15.000, incasso 12.000 nel primo anno e nulla dopo: restano 3.000
    senza incasso previsto -> `residual_short` 0, `residual_long` 3.000. Lo SP li
    mette in `sp07e` (10.000 + 3.000, in OGNI anno: la quota non si ri-somma), e
    `sp06e` non li porta più."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            _base(db, company_id)
            extra = MANUALE if manuale else {}
            rows = [dict(forecast_year=y, revenue_growth_pct=0, **extra) for y in ANNI]
            rows[0]["pregresso"] = {
                "acconti_tributari_storici": 5000,
                "crediti_tributari_breve": {"opening": 15000, "amounts": [12000, 0, 0]},
            }
            _, anni, dettagli = _genera(db, company_id, rows)
            # Riclassifica pura: la cassa (plug) è quella misurata PRIMA della correzione (R11).
            cassa = ["128692.22", "225384.44", "322076.66"] if manuale else ["103222.22", "219444.44", "324726.66"]
            assert [b["sp09_disponibilita_liquide"] for _, b, _ in anni] == [D(c) for c in cassa]
            for (anno, bs, _ce), fy in zip(anni, dettagli):
                d = fy["details"]["pregresso"]["crediti_tributari_breve"]
                assert D(str(d["residual_short"])) == D("0")
                assert D(str(d["residual_long"])) == D("3000")
                assert bs["sp07e_crediti_tributari_lungo"] == D("13000.00"), anno
                assert bs["sp07_crediti_lungo"] == D("13000.00"), anno
                if manuale:
                    # sp06e = solo credito da acconti storici (5.000), senza i 3.000 non incassati
                    assert bs["sp06e_crediti_tributari_breve"] == D("5000.00"), anno
                else:
                    # sp06e = (consuntivo - 3.000 oltre) + credito generato dalle imposte, e la riga
                    # `imposte` dichiarata (dopo `_realign_sp_declarations`) torna con la cella persistita (realign)
                    im = fy["details"]["imposte"]
                    assert D(str(im["crediti_riclassificati_lungo"])) == D("3000")
                    attesa = (D(str(im["crediti_tributari_consuntivo"])) - D("3000")
                              + D(str(im["generated_credit"])))
                    assert bs["sp06e_crediti_tributari_breve"] == attesa.quantize(D("0.01")), (anno, im, bs["sp06e_crediti_tributari_breve"])
                assert bs["_total_assets"] == bs["_total_liabilities"], anno
    finally:
        engine.dispose()


def test_residuo_con_incasso_l_anno_dopo_resta_a_breve(monkeypatch):
    """Il caso già coperto non si muove: se il calendario incassa l'anno dopo,
    il residuo è `residual_short` e resta in `sp06e`; `sp07e` invariato."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            _base(db, company_id)
            rows = [dict(forecast_year=y, revenue_growth_pct=0, **MANUALE) for y in ANNI]
            rows[0]["pregresso"] = {
                "acconti_tributari_storici": 5000,
                "crediti_tributari_breve": {"opening": 15000, "amounts": [5000, 10000, 0]},
            }
            _, anni, _ = _genera(db, company_id, rows)
            assert [b["sp07e_crediti_tributari_lungo"] for _, b, _ in anni] == [D("10000")] * 3
            assert [b["sp06e_crediti_tributari_breve"] for _, b, _ in anni] == [D("15000"), D("5000"), D("5000")]
    finally:
        engine.dispose()
