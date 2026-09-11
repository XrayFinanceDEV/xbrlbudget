"""SP Prev. salva una modifica multi-anno in UNA transazione, non N in corsa.

Rilievo Important del giro di ri-revisione 2 su task-10-fix1
(`task-10-fix1-rereview.md`, "New Breakage in the Fix Diff"): dopo il giro 2,
`handleSaveOverrides` di SP Prev. lanciava ancora N `PUT /assumptions/{year}`
**in parallelo** (`Promise.all`, un anno per chiamata) per una modifica che
tocca piu' anni. Dal giro 2 ciascun PUT rigenera l'INTERO scenario nella
propria transazione: N rigenerazioni pesanti in corsa su SQLite rischiano
`database is locked`, e un anno puo' essere validato senza vedere ancora la
modifica dell'altro anno (non ancora committata) — un rifiuto spurio anche
quando la combinazione sarebbe valida.

La correzione (giro 3): `PATCH /sp-override` (`assumptions_service.
apply_sp_overrides`) applica TUTTE le modifiche di TUTTI gli anni del lotto
PRIMA di una rigenerazione sola — stessa architettura di
`apply_ce_overrides` (CE Prev., giro 2). Questo file prova il contratto con
un caso reale in cui un anno da solo (con l'altro al suo stato corrente,
esattamente cio' che una PUT-per-anno in corsa vedrebbe) viene rifiutato, ma
la combinazione dei due e' valida.

Costruzione della sonda (derivata eseguendo il motore reale, non a mano):
due anni consecutivi (2027, 2028), il 2027 con un investimento che genera un
vero fabbisogno di scoperto, il 2028 con `overdraft_allowed=False` (cosi'
qualunque fabbisogno residuo che eredita da solo lo rifiuta invece di
diventare scoperto silenzioso). Un override di `sp16a` forzato sul 2027 basta
a coprire il SUO fabbisogno (lo stesso meccanismo di
`tests/test_forecast_scoperto.py::test_i4_...`), ma lascia il 2028 senza
copertura per il proprio; un override forzato sul 2028 da solo non basta
perche' eredita ancora il fabbisogno pieno del 2027 non toccato. Solo
applicando ENTRAMBI insieme, nella stessa rigenerazione, il 2028 eredita lo
stato gia' risanato del 2027 e il suo proprio override lo copre.

Stesso stile di `tests/test_override_rejection_not_persisted.py` e di
`tests/test_forecast_scoperto.py`: DB in-memory via `tests.e2e_kit`, chiamata
diretta al livello di servizio (non HTTP).
"""
from decimal import Decimal as D

import pytest

from backend.app.services import assumptions_service
from database.models import BudgetAssumptions, BudgetScenario
from tests.e2e_kit import memory_sessions, read_forecast_maps, seed_base_year


def _scenario(db, user):
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
    """Investimento reale nel 2027 (finanziamento a tasso 6,13%, come
    `tests/test_forecast_scoperto.py::_stress`); il 2028 di default eredita
    `overdraft_allowed=True` a meno che il chiamante non lo tolga."""
    riga = _riga(
        anno, financing_interest_rate=6.13, overdraft_allowed=True,
        tangible_investments=350000.37,
    )
    riga.update(extra)
    return riga


def _build(db, user):
    """Il fixture dei due anni: 2027 stressato, 2028 SENZA scoperto concesso
    -- cosi' un fabbisogno ereditato senza copertura si rifiuta sempre,
    invece di diventare uno scoperto silenzioso che nasconderebbe la prova."""
    company_id, scenario = _scenario(db, user)
    rows = [_stress(2027), _stress(2028, overdraft_allowed=False)]
    assumptions_service.bulk_upsert_assumptions(db, scenario.id, rows, auto_generate=False)
    return company_id, scenario


def _sp_overrides(db, scenario_id, year):
    row = (
        db.query(BudgetAssumptions)
        .filter(
            BudgetAssumptions.scenario_id == scenario_id,
            BudgetAssumptions.forecast_year == year,
        )
        .first()
    )
    return row.sp_overrides


# I due importi della sonda: derivati eseguendo il motore reale (non a mano),
# gli unici per cui questo fixture produce esattamente "un anno solo fallisce,
# insieme riescono" -- vedi il docstring del modulo.
OVERRIDE_2027 = 300000.0
OVERRIDE_2028 = 450000.0


def test_solo_la_combinazione_e_valida_il_salvataggio_riesce():
    """2027 da solo fallisce (il 2028, intatto, eredita un fabbisogno che
    l'override del 2027 non ha coperto); il 2028 da solo fallisce (eredita
    ancora l'intero fabbisogno del 2027, non risanato); insieme riescono
    entrambi, in una rigenerazione sola."""
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            _, scenario = _build(db, "solo-combinazione-riesce")

            # 2027 da solo: il 2028 resta intatto e il suo fabbisogno emerge
            # comunque -- rifiutato.
            with pytest.raises(ValueError, match="Fabbisogno finanziario scoperto"):
                assumptions_service.apply_sp_overrides(
                    db, scenario,
                    [{"forecast_year": 2027, "field": "sp16a_debiti_banche_breve",
                      "value": OVERRIDE_2027}],
                )
            db.expire_all()
            assert _sp_overrides(db, scenario.id, 2027) is None
            assert _sp_overrides(db, scenario.id, 2028) is None

        with sessions() as db:
            _, scenario = _build(db, "solo-combinazione-riesce-2")

            # 2028 da solo: eredita l'intero fabbisogno del 2027 non toccato
            # -- rifiutato.
            with pytest.raises(ValueError, match="incompatibile con sp16a_debiti_banche_breve forzato"):
                assumptions_service.apply_sp_overrides(
                    db, scenario,
                    [{"forecast_year": 2028, "field": "sp16a_debiti_banche_breve",
                      "value": OVERRIDE_2028}],
                )
            db.expire_all()
            assert _sp_overrides(db, scenario.id, 2027) is None
            assert _sp_overrides(db, scenario.id, 2028) is None

        with sessions() as db:
            _, scenario = _build(db, "solo-combinazione-riesce-3")

            # ENTRAMBI insieme, in una rigenerazione sola: riescono.
            years_touched = assumptions_service.apply_sp_overrides(
                db, scenario,
                [
                    {"forecast_year": 2027, "field": "sp16a_debiti_banche_breve",
                     "value": OVERRIDE_2027},
                    {"forecast_year": 2028, "field": "sp16a_debiti_banche_breve",
                     "value": OVERRIDE_2028},
                ],
            )
            assert years_touched == 2
            assert _sp_overrides(db, scenario.id, 2027) == {"sp16a_debiti_banche_breve": OVERRIDE_2027}
            assert _sp_overrides(db, scenario.id, 2028) == {"sp16a_debiti_banche_breve": OVERRIDE_2028}

            maps = {y: sp for y, sp, _ce in read_forecast_maps(db, scenario.id)}
            assert maps[2027]["sp16a_debiti_banche_breve"] == D(str(OVERRIDE_2027))
            assert maps[2028]["sp16a_debiti_banche_breve"] == D(str(OVERRIDE_2028))
            assert maps[2027]["sp09_disponibilita_liquide"] >= 0
            assert maps[2028]["sp09_disponibilita_liquide"] >= 0
        with sessions() as db2:
            # Sessione NUOVA: quello che e' davvero committato.
            row27 = _sp_overrides(db2, scenario.id, 2027)
            row28 = _sp_overrides(db2, scenario.id, 2028)
            assert row27 == {"sp16a_debiti_banche_breve": OVERRIDE_2027}
            assert row28 == {"sp16a_debiti_banche_breve": OVERRIDE_2028}
    finally:
        engine.dispose()


def test_combinazione_invalida_nessuno_dei_due_resta_salvato():
    """Una combinazione che NON copre il fabbisogno nemmeno insieme (gli
    stessi due importi del test sopra, scambiati -- il 2027 sotto-coperto
    e il 2028 con lo stesso importo insufficiente del 2027 da solo) rifiuta
    l'intero lotto: ne' il 2027 ne' il 2028 restano scritti."""
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            _, scenario = _build(db, "combinazione-invalida")

            with pytest.raises(ValueError):
                assumptions_service.apply_sp_overrides(
                    db, scenario,
                    [
                        {"forecast_year": 2027, "field": "sp16a_debiti_banche_breve",
                         "value": OVERRIDE_2027},
                        {"forecast_year": 2028, "field": "sp16a_debiti_banche_breve",
                         "value": OVERRIDE_2027},  # troppo poco per il 2028
                    ],
                )
            db.expire_all()
            assert _sp_overrides(db, scenario.id, 2027) is None, "il 2027 non deve restare scritto"
            assert _sp_overrides(db, scenario.id, 2028) is None, "il 2028 non deve restare scritto"

        with sessions() as db2:
            assert _sp_overrides(db2, scenario.id, 2027) is None
            assert _sp_overrides(db2, scenario.id, 2028) is None
    finally:
        engine.dispose()
