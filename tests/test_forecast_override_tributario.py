"""Rilievo I1 (revisione finale del branch `feat/scadenziamento-pregresso`).

**Che cosa prova.** In modo `saldo_acconto` l'anno N+1 legge `saldo_due` e il
credito d'apertura dai `details['imposte']` dell'anno N, NON dal patrimoniale
persistito; gli `sp_overrides` si applicano dopo le dichiarazioni. Prima della
correzione un override di cella su `sp06e`/`sp16e` quindi **si annullava da
solo l'anno dopo**: l'anno N+1 tornava esattamente ai numeri del piano senza
override, e la cassa — che e' il plug — assorbiva l'intera differenza senza
alcun flusso. Il foglio quadrava e nessun controllo se ne accorgeva. E' la
forma di danno silenzioso che `CLAUDE.md` teme, ed e' una regressione del
Task 6: la via manuale, che legge il patrimoniale, l'override lo portava
avanti (ultimo caso qui sotto, tenuto come guardia per non rompere anche
quella).

**I numeri.** La sonda della revisione (scratchpad, perduta) e' ricostruita
qui sull'anno base ricco del kit con credito tributario 20.000 e crescita
3,33 su un solo anno di piano: `tests/test_forecast_dichiarato_vs_persistito
._base_year` con `sp06a`/`sp06e` = 100.000/20.000. Le cifre «piane» sono
pinzate perche' il test affermi una VOLTA SOLA che cosa deve cambiare:
l'anno con l'override deve DIFFERIRE dal gemello senza override.

**Che cosa NON copre.** La coincidenza dichiarato=persistito su tutta la
griglia: sta nella rete permanente (`test_forecast_dichiarato_vs_persistito`),
che da questo giro include anche una famiglia di `sp_overrides` sui campi
dichiarati.
"""
from decimal import Decimal as D

import pytest

from backend.app.api.v1 import budget_scenarios
from backend.app.schemas.budget import BudgetScenarioCreate
from database.models import BalanceSheet, FinancialYear
from tests.e2e_kit import memory_sessions, read_forecast_maps, seed_base_year

CREDITO_BASE = D("20000.00")

# I numeri del gemello PIANO (nessun override), misurati su questa base.
PIANO_CREDITO = {
    2027: {"sp06e": D("34895.58"), "cassa": D("112207.22")},
    2028: {"sp06e": D("34895.58"), "cassa": D("238789.02")},
}
PIANO_DEBITO = {
    2027: {"sp16e": D("24104.42"), "cassa": D("161207.22")},
    2028: {"sp16e": D("29864.47"), "cassa": D("297789.02")},
}


def _base_tributi(db, user):
    """L'anno base ricco della rete, con credito tributario 20.000 in `sp06e`."""
    company_id, _ = seed_base_year(db, user_id=user)
    fy = db.query(FinancialYear).filter(FinancialYear.company_id == company_id).one()
    b = db.query(BalanceSheet).filter(BalanceSheet.financial_year_id == fy.id).one()
    b.sp16_debiti_breve = D("145000.00")
    b.sp16b_debiti_altri_finanz_breve = D("5000.00")
    b.sp16d_debiti_fornitori_breve = D("80000.00")
    b.sp16e_debiti_tributari_breve = D("10000.00")
    b.sp16f_debiti_previdenza_breve = D("15000.00")
    b.sp16g_altri_debiti_breve = D("35000.00")
    b.sp17a_debiti_banche_lungo = D("0.00")
    b.sp17d_debiti_fornitori_lungo = D("20000.00")
    b.sp17f_debiti_previdenza_lungo = D("10000.00")
    b.sp17g_altri_debiti_lungo = D("20000.00")
    b.sp03_immob_materiali = D("140000.00")
    b.sp04_immob_finanziarie = D("20000.00")
    b.sp04a_partecipazioni = D("20000.00")
    b.sp01_crediti_soci = D("3000.00")
    b.sp01b_parte_da_richiamare = D("3000.00")
    b.sp08_attivita_finanziarie = D("4000.00")
    b.sp10_ratei_risconti_attivi = D("5000.00")
    b.sp14_fondi_rischi = D("6000.00")
    b.sp14d_altri_fondi = D("6000.00")
    b.sp18_ratei_risconti_passivi = D("2000.00")
    # Il credito tributario della sonda: 20.000 scolpiti dentro `sp06a`, aggregato
    # e bilancio invariati (attivo 413 = passivo 413, cassa 31.000).
    b.sp06a_crediti_clienti_breve = D("100000.00")
    b.sp06e_crediti_tributari_breve = CREDITO_BASE
    b.sp09_disponibilita_liquide = D("31000.00")
    db.commit()
    return company_id


def _genera(db, user, overrides=None, extra_per_anno=None, manual_tax=False,
            per_anno=None):
    company_id = _base_tributi(db, user)
    rows = []
    for y in (2027, 2028):
        r = {"forecast_year": y, "revenue_growth_pct": 3.33}
        if manual_tax:
            r.update(sp06e_growth_pct=0, sp16e_growth_pct=0, sp17e_growth_pct=0)
        r.update((extra_per_anno or {}).get(y, {}) or (extra_per_anno or {}).get("tutti", {}))
        if (overrides or {}).get(y):
            r["sp_overrides"] = overrides[y]
        if (per_anno or {}).get(y):
            r.update(per_anno[y])
        rows.append(r)
    sc = budget_scenarios.create_budget_scenario(
        company_id,
        BudgetScenarioCreate(company_id=company_id, name="i1", base_year=2026,
                             scenario_type="budget"),
        user_id=user, db=db)
    res = budget_scenarios.bulk_upsert_assumptions(
        company_id, sc.id, request={"assumptions": rows, "auto_generate": True},
        user_id=user, db=db)
    assert res["forecast_generated"] is True, res["message"]
    prev = budget_scenarios.preview_forecast_route(
        company_id, sc.id, request={"assumptions": rows}, user_id=user, db=db)
    det = {a["year"]: a["details"] for a in prev["forecast_years"]}
    return {y: (bs, ce, det[y]) for y, bs, ce in read_forecast_maps(db, sc.id)}


def _figlia(righe, y, campo):
    return righe[y][0].get(campo, D("0"))


def _q(x):
    """Al centesimo con la regola del motore (come `_divergenze` nella rete)."""
    from decimal import ROUND_HALF_UP
    return D(str(x)).quantize(D("0.01"), rounding=ROUND_HALF_UP)


def test_gemello_piano_credito(monkeypatch):
    """Il gemello senza override: i numeri pinzati su cui si misura il resto."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            righe = _genera(db, "i1-piano-credito")
        for y, atteso in PIANO_CREDITO.items():
            assert _figlia(righe, y, "sp06e_crediti_tributari_breve") == atteso["sp06e"], y
            assert _figlia(righe, y, "sp09_disponibilita_liquide") == atteso["cassa"], y
    finally:
        engine.dispose()


def test_override_sp06e_non_si_annulla_l_anno_dopo(monkeypatch):
    """Override 2027 `sp06e = 0`: il 2028 deve DIFFERIRE dal gemello piano.

    Prima della correzione il 2028 tornava a `sp06e` 34.895,58 e cassa
    238.789,02 ESATTI come nel piano senza override: l'intero credito
    annullato a mano ricompariva l'anno dopo e la cassa lo riassorbiva senza
    alcun flusso.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            righe = _genera(db, "i1-ov-sp06e",
                            overrides={2027: {"sp06e_crediti_tributari_breve": 0}})
        assert _figlia(righe, 2027, "sp06e_crediti_tributari_breve") == D("0")
        assert _figlia(righe, 2027, "sp09_disponibilita_liquide") \
            == PIANO_CREDITO[2027]["cassa"] + PIANO_CREDITO[2027]["sp06e"], \
            "la cassa 2027 assorbe il credito annullato (questo gia' funzionava)"
        assert _figlia(righe, 2028, "sp06e_crediti_tributari_breve") \
            != PIANO_CREDITO[2028]["sp06e"], \
            "il 2028 e' identico al gemello: l'override si e' annullato da solo"
        assert _figlia(righe, 2028, "sp09_disponibilita_liquide") \
            != PIANO_CREDITO[2028]["cassa"]
        # Dichiarato = persistito, in entrambe le sedi che dichiarano il credito.
        # Al centesimo: `current_tax` viaggia grezza sopra il centesimo e la
        # quantizzazione della riga è quella che viene persistita (stessa
        # regola di `_divergenze` nella rete permanente).
        for y in (2027, 2028):
            imp = righe[y][2]["imposte"]
            assert imp["mode"] == "saldo_acconto"
            assert _q(D(str(imp["generated_credit"])) + D(str(imp["opening_credit_left"]))) \
                == _figlia(righe, y, "sp06e_crediti_tributari_breve"), \
                (y, imp, "details['imposte'] non coincide col persistito")
    finally:
        engine.dispose()


def test_override_sp16e_non_si_annulla_l_anno_dopo(monkeypatch):
    """Override 2027 `sp16e = 0` con acconti espliciti: la cassa 2028 deve
    differire dal gemello piano, e il 2028 NON deve dichiarare un `saldo_paid`
    su un debito che l'override ha tolto."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            piano = _genera(db, "i1-piano-debito",
                            extra_per_anno={"tutti": {"tax_advances_paid": 1000}})
            for y, atteso in PIANO_DEBITO.items():
                assert _figlia(piano, y, "sp16e_debiti_tributari_breve") == atteso["sp16e"], y
                assert _figlia(piano, y, "sp09_disponibilita_liquide") == atteso["cassa"], y
            righe = _genera(db, "i1-ov-sp16e",
                            extra_per_anno={"tutti": {"tax_advances_paid": 1000}},
                            overrides={2027: {"sp16e_debiti_tributari_breve": 0}})
        assert _figlia(righe, 2027, "sp16e_debiti_tributari_breve") == D("0")
        assert _figlia(righe, 2028, "sp09_disponibilita_liquide") \
            != PIANO_DEBITO[2028]["cassa"], \
            "la cassa 2028 e' identica al gemello: l'override si e' annullato da solo"
        imp28 = righe[2028][2]["imposte"]
        assert D(str(imp28["saldo_paid"])) == D("0"), \
            f"saldo_paid {imp28['saldo_paid']} dichiarato su un debito tolto dall'override"
        for y in (2027, 2028):
            imp = righe[y][2]["imposte"]
            assert _q(imp["generated_debt"]) \
                == _figlia(righe, y, "sp16e_debiti_tributari_breve"), \
                (y, imp, "details['imposte'] non coincide col persistito")
    finally:
        engine.dispose()


def test_via_manuale_porta_avanti_lo_stesso_override(monkeypatch):
    """Guardia controllore: sulla via MANUALE l'override di `sp16e` si portava
    avanti anche prima (il motore legge il patrimoniale). Non deve rompersi."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            righe = _genera(db, "i1-manuale-ov",
                            overrides={2027: {"sp16e_debiti_tributari_breve": 0}},
                            manual_tax=True)
        assert _figlia(righe, 2027, "sp16e_debiti_tributari_breve") == D("0")
        assert _figlia(righe, 2028, "sp16e_debiti_tributari_breve") == D("0")
    finally:
        engine.dispose()


# ══ I1-bis (Ruling 57b): l'override sul lato oltre di un saldo con piano ══
#
# Un piano di scadenziamento scrive il lato oltre dalla propria formula
# di calendario, non dal persistito: un override salvato su quella riga
# viene CANCELLATO IN SILENZIO l'anno dopo (misurato dalla sonda della
# revisione: piano fornitori, override `sp17d = 250,25`, la riga torna
# quella del runoff e la cassa assorbe la differenza — e la cassa assorbe
# sempre, perche' e' il plug). Il motore quindi lo RIFIUTA, e il rifiuto
# vuole una contraddizione: qui la contraddizione e' fra due ipotesi che
# affermano due destini diversi per la stessa riga.

PIANO_FORNITORI = {"debiti_fornitori": {"opening": 100000, "amounts": [50000, 50000]}}
PIANO_CREDITI = {"crediti_commerciali": {"opening": 100000, "amounts": [50000, 50000]}}


@pytest.mark.parametrize("piano,campo", [
    (PIANO_FORNITORI, "sp17d_debiti_fornitori_lungo"),
    (PIANO_CREDITI, "sp07_crediti_lungo"),
])
def test_override_lato_oltre_con_piano_attivo_si_rifiuta(monkeypatch, piano, campo):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id = _base_tributi(db, f"i1bis-{campo}")
            rows = [
                {"forecast_year": 2027, "revenue_growth_pct": 3.33,
                 "pregresso": piano, "sp_overrides": {campo: 250.25}},
                {"forecast_year": 2028, "revenue_growth_pct": 3.33,
                 "sp_overrides": {campo: 250.25}},
            ]
            sc = budget_scenarios.create_budget_scenario(
                company_id,
                BudgetScenarioCreate(company_id=company_id, name="i1bis", base_year=2026,
                                     scenario_type="budget"),
                user_id=f"i1bis-{campo}", db=db)
            res = budget_scenarios.bulk_upsert_assumptions(
                company_id, sc.id, request={"assumptions": rows, "auto_generate": True},
                user_id=f"i1bis-{campo}", db=db)
            # Non l'HTTP 200: il rifiuto vive nel `forecast_generated` (CLAUDE.md).
            assert res["forecast_generated"] is False, res["message"]
            assert "non e' ammesso" in res["message"] and campo in res["message"], res["message"]
            assert "piano di scadenziamento" in res["message"], res["message"]
            # Il rifiuto non lascia nửa un previsionale: nessuna riga generata.
            assert read_forecast_maps(db, sc.id) == []
    finally:
        engine.dispose()


def test_override_lato_oltre_senza_piano_si_porta_avanti(monkeypatch):
    """Lo stesso override, senza piano su quel saldo, e' lecito come oggi:
    viene persistito e l'anno dopo la riga segue `_prev × (1 + crescita)`,
    quindi l'override si porta avanti da se'."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            righe = _genera(db, "i1bis-senza-piano",
                            overrides={2027: {"sp17d_debiti_fornitori_lungo": 250.25}})
        assert _figlia(righe, 2027, "sp17d_debiti_fornitori_lungo") == D("250.25")
        assert _figlia(righe, 2028, "sp17d_debiti_fornitori_lungo") == D("250.25")
    finally:
        engine.dispose()
