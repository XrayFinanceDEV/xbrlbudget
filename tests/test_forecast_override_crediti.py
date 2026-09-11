"""Rilievo m-3 (revisione del terzo giro, `final-fix-3-review.md`) — corretto
nel quinto e ultimo giro del lotto 2 (spec `spec-giro5-motore.md`).

**Il difetto.** Con un piano dei crediti commerciali attivo, N-I3
(`_realign_sp_declarations`) riscrive `details['pregresso']['crediti_
commerciali']['generated']` come `parte_commerciale_persistita −
residual_short`, SENZA limite inferiore: un `sp_overrides` che porta la parte
commerciale sotto il `residual_short` che il calendario deve incassare l'anno
dopo fa dichiarare un `generated` negativo — un credito nuovo negativo, che
economicamente sarebbe un debito (anticipi da clienti). Per i quattro debiti
il caso analogo e' gia' rifiutato (I-c); per i crediti non c'era ne' limite ne'
rifiuto.

**La correzione.** Decisione del proprietario (2026-09-11): «new receivables
can not go negative, they can become new payables if negative but it's an
edge case» — si RIFIUTA, come I-c, non si clampa e non si riclassifica in
debito (un clamp romperebbe l'identita' di riga che la rete M-4 asserisce).

**Fixture.** La base della rete M-4 (`test_forecast_dichiarato_vs_persistito.
_base_year`: crediti commerciali 120.000, kit di default), piano
30.000 + 30.000 sul solo primo anno (`validate_pregresso` impone che la
massa coincida con la base). Il `residual_short` dell'anno 0 (2027) e' quindi
esattamente 30.000,00 (`runoff_schedule(120000, [30000, 30000], [], 0, 3)
.residual_short`).
"""
from decimal import Decimal as D

import pytest

from backend.app.api.v1 import budget_scenarios
from backend.app.schemas.budget import BudgetScenarioCreate
from backend.app.services import assumptions_service
from database.models import BudgetAssumptions, BudgetScenario
from tests.e2e_kit import memory_sessions, read_forecast_maps
from tests.test_forecast_dichiarato_vs_persistito import _base_year

ANNI = (2027, 2028, 2029)
PIANO = {"crediti_commerciali": {"opening": 120000.00, "amounts": [30000.00, 30000.00]}}
RESIDUO_2027 = D("30000.00")


def _righe(anni=ANNI, piano=PIANO, overrides=None):
    """Crescita piatta al 3,33 su tutti gli anni, piano (se dato) e override
    (se dati) sul primo anno soltanto — lo stesso schema di
    `test_ni3_sotto_la_riga_debiti_anche_i_crediti_seguono_il_persistito`."""
    rows = [dict(forecast_year=y, revenue_growth_pct=3.33) for y in anni]
    if piano is not None:
        rows[0]["pregresso"] = piano
    if overrides:
        rows[0]["sp_overrides"] = overrides
    return rows


def _esito(db, user, rows):
    company_id = _base_year(db, user)
    sc = budget_scenarios.create_budget_scenario(
        company_id,
        BudgetScenarioCreate(company_id=company_id, name="crediti-m3", base_year=2026,
                             scenario_type="budget"),
        user_id=user, db=db)
    res = budget_scenarios.bulk_upsert_assumptions(
        company_id, sc.id, request={"assumptions": rows, "auto_generate": True},
        user_id=user, db=db)
    return res, company_id, sc.id


def _dettagli(db, user, company_id, sid, rows):
    """`{anno: (persistito, details)}`, come nei test gemelli di
    `test_forecast_override_tributario.py`."""
    prev = budget_scenarios.preview_forecast_route(
        company_id, sid, request={"assumptions": rows}, user_id=user, db=db)
    anni = {a["year"]: a["details"] for a in prev["forecast_years"]}
    return {y: (bs, anni.get(y) or {}) for y, bs, ce in read_forecast_maps(db, sid)}


def test_override_sotto_il_residuo_si_rifiuta_col_messaggio_giusto(monkeypatch):
    """`sp06a` 2027 = 20.000, sotto i 30.000,00 dovuti l'anno dopo: rifiutato,
    col residuo in formato italiano, l'articolo giusto e nessun importo grezzo
    col punto decimale."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            rows = _righe(overrides={"sp06a_crediti_clienti_breve": 20000.00})
            res, _cid, sid = _esito(db, "m3-rifiuto", rows)
            assert res["forecast_generated"] is False, res["message"]
            msg = res["message"]
            assert "Pregresso e nuovo" in msg, msg
            assert "30.000,00" in msg, msg
            assert "crediti commerciali" in msg, msg
            # Nessun importo grezzo col punto decimale: solo la forma italiana.
            assert "20000.00" not in msg and "30000.00" not in msg, msg
            assert read_forecast_maps(db, sid) == []
    finally:
        engine.dispose()


@pytest.mark.parametrize("forzato,si_genera", [
    (RESIDUO_2027, True),           # esattamente il residuo: genera, generated 0,00
    (D("29999.99"), False),         # un centesimo sotto: rifiutato
])
def test_confine_residuo_esatto_genera_un_centesimo_sotto_rifiuta(monkeypatch, forzato, si_genera):
    """Il confine e' il `residual_short` del piano, ESATTO, e il confronto e'
    `<` (sotto), non `<=` — come per il confine gemello dei debiti (I-c,
    rilievo m-E punto 2)."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            user = f"m3-confine-{forzato}"
            rows = _righe(overrides={"sp06a_crediti_clienti_breve": forzato})
            res, cid, sid = _esito(db, user, rows)
            if si_genera:
                assert res["forecast_generated"] is True, res["message"]
                lette = _dettagli(db, user, cid, sid, rows)
                bs2027, det2027 = lette[2027]
                assert bs2027["sp06a_crediti_clienti_breve"] == forzato
                d = det2027["pregresso"]["crediti_commerciali"]
                assert D(str(d["generated"])).quantize(D("0.01")) == D("0.00"), d
            else:
                assert res["forecast_generated"] is False, res["message"]
                assert "30.000,00" in res["message"], res["message"]
                assert read_forecast_maps(db, sid) == []
    finally:
        engine.dispose()


def test_sopra_il_residuo_genera_col_valore_della_sonda(monkeypatch):
    """Sopra il residuo l'override e' la quota GENERATA, e si porta avanti:
    riproduce la sonda della revisione (`sonda_ni3.py`), `sp06a` 2027 =
    106.770,89 -> `generated` 76.770,89."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            user = "m3-sopra"
            rows = _righe(overrides={"sp06a_crediti_clienti_breve": D("106770.89")})
            res, cid, sid = _esito(db, user, rows)
            assert res["forecast_generated"] is True, res["message"]
            lette = _dettagli(db, user, cid, sid, rows)
            bs2027, det2027 = lette[2027]
            assert bs2027["sp06a_crediti_clienti_breve"] == D("106770.89")
            d = det2027["pregresso"]["crediti_commerciali"]
            assert D(str(d["generated"])).quantize(D("0.01")) == D("76770.89"), d
    finally:
        engine.dispose()


def test_senza_piano_lo_stesso_override_genera(monkeypatch):
    """Senza piano dei crediti il rifiuto non scatta mai: la riga `legacy`
    non ha calendario da contraddire."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            user = "m3-senza-piano"
            rows = _righe(piano=None, overrides={"sp06a_crediti_clienti_breve": D("20000.00")})
            res, cid, sid = _esito(db, user, rows)
            assert res["forecast_generated"] is True, res["message"]
            lette = _dettagli(db, user, cid, sid, rows)
            bs2027, det2027 = lette[2027]
            assert bs2027["sp06a_crediti_clienti_breve"] == D("20000.00")
            d = det2027["pregresso"]["crediti_commerciali"]
            assert d["mode"] == "legacy"
    finally:
        engine.dispose()


def test_override_sull_aggregato_sotto_il_residuo_si_rifiuta(monkeypatch):
    """Vale anche per un override sull'AGGREGATO `sp06`, non solo su una sua
    sotto-voce commerciale: e' la stessa parte commerciale che si muove."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            rows = _righe(overrides={"sp06_crediti_breve": D("20000.00")})
            res, _cid, sid = _esito(db, "m3-aggregato", rows)
            assert res["forecast_generated"] is False, res["message"]
            assert "30.000,00" in res["message"], res["message"]
            assert read_forecast_maps(db, sid) == []
    finally:
        engine.dispose()


# ── Servizio: bulk (`forecast_generated`) e PATCH /sp-override (4xx + rollback) ──

def test_bulk_rifiuta_con_forecast_generated_false_non_l_http(monkeypatch):
    """Il bulk (`PUT /scenarios/{id}/assumptions`) risponde 200 anche a un
    rifiuto: chi chiama deve leggere `forecast_generated`, non lo status
    (CLAUDE.md, «Un verdetto di inaffidabilita' blocca...» /
    «chi chiama l'endpoint bulk...»)."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            rows = _righe(overrides={"sp06a_crediti_clienti_breve": 20000.00})
            res, _cid, sid = _esito(db, "m3-bulk", rows)
            assert res["forecast_generated"] is False
            assert "message" in res and res["message"]
            assert read_forecast_maps(db, sid) == []
    finally:
        engine.dispose()


def test_patch_sp_override_rifiutato_non_persiste_su_get(monkeypatch):
    """`PATCH /sp-override` (`assumptions_service.apply_sp_overrides`) risponde
    4xx (un `ValueError` che il router traduce) e fa `rollback()`: una `GET`
    successiva sulle ipotesi non vede l'override rifiutato, come per i quattro
    debiti (`tests/test_override_rejection_not_persisted.py`)."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            rows = _righe()
            res, _cid, sid = _esito(db, "m3-patch", rows)
            assert res["forecast_generated"] is True, res["message"]

            scenario = db.query(BudgetScenario).filter(BudgetScenario.id == sid).one()
            prima = db.query(BudgetAssumptions).filter(
                BudgetAssumptions.scenario_id == sid,
                BudgetAssumptions.forecast_year == 2027,
            ).one()
            assert prima.sp_overrides is None, prima.sp_overrides

            with pytest.raises(ValueError, match="non è ammesso"):
                assumptions_service.apply_sp_overrides(
                    db, scenario,
                    [{"forecast_year": 2027, "field": "sp06a_crediti_clienti_breve",
                      "value": 20000.00}],
                )

            db.expire_all()
            dopo = db.query(BudgetAssumptions).filter(
                BudgetAssumptions.scenario_id == sid,
                BudgetAssumptions.forecast_year == 2027,
            ).one()
            assert dopo.sp_overrides is None, dopo.sp_overrides

        with sessions() as db2:
            verificata = db2.query(BudgetAssumptions).filter(
                BudgetAssumptions.scenario_id == sid,
                BudgetAssumptions.forecast_year == 2027,
            ).one()
            assert verificata.sp_overrides is None, verificata.sp_overrides
    finally:
        engine.dispose()
