"""Un override di cella rifiutato dal motore non resta persistito.

Rilievo del giro di revisione 2 su task-10-fix1: `PUT /assumptions/{year}`
(SP Prev.) e `PATCH /ce-override` (CE Prev.) facevano `db.commit()`
dell'override **prima** di provare a rigenerare il previsionale — un
fallimento della generazione lasciava comunque il valore rifiutato scritto
in `BudgetAssumptions.sp_overrides`/`ce*_override`. Il client (giro 1 di
questo stesso task) scarta la modifica e mostra il previsionale vecchio, cosi'
lo scenario sembra intatto: in realta' ogni generazione successiva fallisce
con lo stesso errore, finche' l'utente non ritocca proprio quella cella — che
pero' a schermo non vede diversa dalle altre.

La regola (decisione del coordinatore, coerente con CLAUDE.md — "una
correzione che tocca piu' campi si applica tutta o niente"): salvataggio e
rigenerazione condividono la STESSA transazione
(`assumptions_service.update_single_year_assumptions`,
`assumptions_service.apply_ce_overrides`), e un fallimento fa `rollback()` di
tutto cio' che questa chiamata ha appena applicato. Il bulk
(`bulk_upsert_assumptions`, `PUT /assumptions`) NON cambia: salvare le ipotesi
anche a previsionale rifiutato resta il comportamento documentato del wizard.

Stesso stile di `tests/test_forecast_scoperto.py`: DB in-memory via
`tests.e2e_kit`, chiamate dirette al livello di servizio (non HTTP) — la
guardia server-side gia' esercitata li' e' la stessa che qui deve conservare
lo stato precedente, non solo rifiutare.
"""
from decimal import Decimal as D

import pytest

from backend.app.services import assumptions_service
from database.models import BudgetAssumptions, BudgetScenario
from tests.e2e_kit import memory_sessions, seed_base_year


def _scenario(db, user, overdraft_allowed=False):
    company_id, _ = seed_base_year(db, user_id=user)
    sc = BudgetScenario(company_id=company_id, name=user, base_year=2026, scenario_type="budget")
    db.add(sc)
    db.commit()
    return company_id, sc


def _riga(anno, **extra):
    riga = {"forecast_year": anno, "revenue_growth_pct": 3.33, "tax_rate": 27.9}
    riga.update(extra)
    return riga


def _stress(anno, **extra):
    """Lo stesso piano stressato di test_forecast_scoperto.py: 350.000,37
    investiti nel primo anno, cassa sotto pressione, scoperto concesso."""
    riga = _riga(anno, financing_interest_rate=6.13, overdraft_allowed=True)
    if anno == 2027:
        riga["tangible_investments"] = 350000.37
    riga.update(extra)
    return riga


def _assumptions_row(db, scenario_id, year):
    return (
        db.query(BudgetAssumptions)
        .filter(
            BudgetAssumptions.scenario_id == scenario_id,
            BudgetAssumptions.forecast_year == year,
        )
        .first()
    )


# ── SP Prev.: PUT /assumptions/{year} → update_single_year_assumptions ──────

def test_override_sp16a_incompatibile_rifiutato_non_persiste_su_get():
    """L'override di `sp16a` incompatibile con lo scoperto (lo stesso che il
    collaudo ha trovato in SP Prev., misurato anche in
    `tests/test_forecast_scoperto.py::test_i4_...`) fa fallire la
    rigenerazione — e una lettura successiva delle ipotesi deve vedere
    `sp_overrides` esattamente come prima del tentativo, non il valore
    rifiutato."""
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, scenario = _scenario(db, "override-rifiutato-sp16a")
            rows = [_stress(2027)]
            res = assumptions_service.bulk_upsert_assumptions(
                db, scenario.id, rows, auto_generate=True
            )
            assert res["forecast_generated"] is True, res["message"]

            prima = _assumptions_row(db, scenario.id, 2027)
            assert prima.sp_overrides is None, prima.sp_overrides

            # L'override rifiutato: 12.345,67 non basta a coprire il
            # fabbisogno di scoperto (227.113,48 misurato in
            # test_forecast_scoperto.py::test_i4).
            with pytest.raises(ValueError, match="incompatibile con sp16a_debiti_banche_breve forzato"):
                assumptions_service.update_single_year_assumptions(
                    db, scenario, 2027,
                    {"sp_overrides": {"sp16a_debiti_banche_breve": 12345.67}},
                )

            # STESSA sessione, appena dopo il rollback: l'ORM deve rileggere
            # dal DB, non restituire l'oggetto in memoria con l'override
            # ancora attaccato.
            db.expire_all()
            dopo = _assumptions_row(db, scenario.id, 2027)
            assert dopo.sp_overrides is None, dopo.sp_overrides

        # Sessione NUOVA: quello che e' davvero committato, non cio' che una
        # sessione fallita potrebbe ancora avere in sospeso.
        with sessions() as db2:
            verificata = _assumptions_row(db2, scenario.id, 2027)
            assert verificata.sp_overrides is None, verificata.sp_overrides
    finally:
        engine.dispose()


def test_override_sp16a_accettato_persiste_normalmente():
    """Controprova: un override che il motore accetta (il totale forzato
    copre il fabbisogno, con un tetto di scoperto sopra — stessi valori di
    test_forecast_scoperto.py::test_i4) resta scritto e si rilegge."""
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, scenario = _scenario(db, "override-accettato-sp16a")
            rows = [_stress(2027)]
            res = assumptions_service.bulk_upsert_assumptions(
                db, scenario.id, rows, auto_generate=True
            )
            assert res["forecast_generated"] is True, res["message"]

            aggiornata = assumptions_service.update_single_year_assumptions(
                db, scenario, 2027,
                {"sp_overrides": {"sp16a_debiti_banche_breve": 400000.55}},
            )
            assert aggiornata.sp_overrides == {"sp16a_debiti_banche_breve": 400000.55}

        with sessions() as db2:
            verificata = _assumptions_row(db2, scenario.id, 2027)
            assert verificata.sp_overrides == {"sp16a_debiti_banche_breve": 400000.55}
    finally:
        engine.dispose()


# ── CE Prev.: PATCH /ce-override → apply_ce_overrides ───────────────────────

def test_ce_override_che_sbilancia_la_cassa_rifiutato_non_persiste_su_get():
    """Senza scoperto concesso, un costo di materie prime forzato a un
    valore enorme sbilancia la cassa: il motore solleva "Fabbisogno finanziario
    scoperto" e NESSUNO dei due `ce*_override` del lotto deve restare
    scritto — l'atomicita' vale sul lotto intero, non voce per voce."""
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, scenario = _scenario(db, "ce-override-rifiutato")
            rows = [_riga(2027)]
            res = assumptions_service.bulk_upsert_assumptions(
                db, scenario.id, rows, auto_generate=True
            )
            assert res["forecast_generated"] is True, res["message"]

            prima = _assumptions_row(db, scenario.id, 2027)
            assert prima.ce05_override is None
            assert prima.ce07_override is None

            with pytest.raises(ValueError, match="Fabbisogno finanziario scoperto"):
                assumptions_service.apply_ce_overrides(
                    db, scenario,
                    [
                        {"forecast_year": 2027, "field": "ce05_override", "value": 9000000.0},
                        {"forecast_year": 2027, "field": "ce07_override", "value": 12345.0},
                    ],
                )

            db.expire_all()
            dopo = _assumptions_row(db, scenario.id, 2027)
            assert dopo.ce05_override is None, dopo.ce05_override
            assert dopo.ce07_override is None, dopo.ce07_override

        with sessions() as db2:
            verificata = _assumptions_row(db2, scenario.id, 2027)
            assert verificata.ce05_override is None
            assert verificata.ce07_override is None
    finally:
        engine.dispose()


def test_ce_override_accettato_persiste_normalmente():
    """Controprova: un lotto di override che il motore accetta resta
    scritto e si rilegge, esattamente come prima di questa correzione."""
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, scenario = _scenario(db, "ce-override-accettato")
            rows = [_riga(2027)]
            res = assumptions_service.bulk_upsert_assumptions(
                db, scenario.id, rows, auto_generate=True
            )
            assert res["forecast_generated"] is True, res["message"]

            applied = assumptions_service.apply_ce_overrides(
                db, scenario,
                [{"forecast_year": 2027, "field": "ce07_override", "value": 12345.0}],
            )
            assert applied == 1

        with sessions() as db2:
            verificata = _assumptions_row(db2, scenario.id, 2027)
            assert verificata.ce07_override == D("12345.00")
    finally:
        engine.dispose()
