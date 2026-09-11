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
            assert "non è ammesso" in res["message"] and campo in res["message"], res["message"]
            assert "piano di scadenziamento" in res["message"], res["message"]
            # Il rifiuto non lascia NESSUN previsionale: nessuna riga generata.
            assert read_forecast_maps(db, sc.id) == []
    finally:
        engine.dispose()


def test_override_lato_oltre_senza_piano_si_porta_avanti(monkeypatch):
    """Lo stesso override, senza piano su quel saldo, e' lecito come oggi:
    viene persistito e l'anno dopo la riga segue `_prev × (1 + crescita)`,
    quindi l'override si porta avanti da se'.

    NON e' piu' vero per `sp17e`, che il kernel fiscale governa anche senza
    piano: quello e' il test `test_sp17e_senza_piano_si_rifiuta` qui sotto.
    """
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


# ══ GIRO 2 (rilievi I-a…I-d, M-1, M-2, M-4 della revisione di `f330730`) ══
#
# Le quattro famiglie qui sotto sono lo stesso difetto visto da quattro righe
# diverse del patrimoniale: un'ipotesi salvata che L'ANNO DOPO il motore
# rigenera da un'altra fonte, e la cassa — che e' il plug — assorbe la
# differenza senza alcun flusso. Il foglio quadra, nessun controllo se ne
# accorge. La forma generale e' in `_rifiuto_override_governati`; qui ogni
# branch ha il suo rifiuto, la sua eccezione lecita, e la misura che li
# distingue.

ANNI_3 = (2027, 2028, 2029)


def _esito(db, user, rows, nome="giro2", base=None):
    """Salva e genera, e RESTITUISCE il verdetto (e la palestra per leggerlo).

    I test di questo blocco affermano un RIFIUTO, quindi non possono passare dal
    `_genera` di casa: quello asserisce `forecast_generated is True`, e
    diventerebbe verde proprio sull'assenza del rifiuto che stiamo provando.
    Restituisce `(res, azienda, scenario, righe)`: `righe` servono alla preview,
    che e' l'unica sede dove i `details` di uno scenario si leggono senza
    ri-generarlo (stessa strada della rete permanente).

    `base` e' l'anno base da costruire: di default `_base_tributi`, che pero' ha
    tutte le `sp07*` a zero — e su quelle proporzioni `_alloc` non distingue una
    riga governata da una che cresce da `prev` (vedi `_base_crediti`).
    """
    company_id = (base or _base_tributi)(db, user)
    sc = budget_scenarios.create_budget_scenario(
        company_id,
        BudgetScenarioCreate(company_id=company_id, name=nome, base_year=2026,
                             scenario_type="budget"),
        user_id=user, db=db)
    res = budget_scenarios.bulk_upsert_assumptions(
        company_id, sc.id, request={"assumptions": rows, "auto_generate": True},
        user_id=user, db=db)
    return res, company_id, sc.id, rows


def _dettagli(db, user, company_id, sid, rows):
    """`{anno: (persistito, details)}`: il persistito dal DB, i `details`
    dalla preview. Le due cose non si toccano, ed e' il punto."""
    prev = budget_scenarios.preview_forecast_route(
        company_id, sid, request={"assumptions": rows}, user_id=user, db=db)
    anni = {a["year"]: a["details"] for a in prev["forecast_years"]}
    return {y: (bs, anni.get(y) or {}) for y, bs, ce in read_forecast_maps(db, sid)}


def _righe_base(anni=ANNI_3, piano=None, manuale=False, overrides=None):
    """Tre anni di crescita piatta al 3,33 (il numero del file), con piano,
    via manuale e override PER ANNO — perche' un rifiuto che si controlla solo
    sulla prima riga e' un rifiuto a meta' (rilievo M-4: «la mutazione M8
    sopravvive, ogni test mette l'override anche nell'anno 1»)."""
    def riga(y):
        r = {"forecast_year": y, "revenue_growth_pct": 3.33}
        if manuale:
            r.update(sp06e_growth_pct=0, sp16e_growth_pct=0, sp17e_growth_pct=0)
        if overrides and y in overrides:
            r["sp_overrides"] = dict(overrides[y])
        return r
    rows = [riga(y) for y in anni]
    if piano:
        rows[0]["pregresso"] = piano
    return rows


def _letto(lette, y, campo):
    """Il valore PERSISTITO di una cella, dal prospetto dell'anno `y`. Use `_letto`
    (non `_figlia`, che qui sopra legge una terna diversa) sui dizionari di
    `_dettagli`."""
    return D(str(lette[y][0].get(campo) or 0))


def _riga_pregresso(det, saldo):
    return (det.get("pregresso") or {}).get(saldo) or {}


def _posizione(bs):
    """`sp16e + sp17e − sp06e`: la posizione tributaria della griglia revisione."""
    return (D(str(bs["sp16e_debiti_tributari_breve"]))
            + D(str(bs["sp17e_debiti_tributari_lungo"]))
            - D(str(bs["sp06e_crediti_tributari_breve"])))


def _scarto_di_flusso(lette, y):
    """Il «scarto di flusso dell'anno dopo» della revisione, al centesimo.

    `pos(N) − [pos(N−1) + imposta corrente − saldo − acconti − rate]`: se un
    debito e' comparso o sparito senza che un versamento lo dica, questo non e'
    zero. Il rifiuto da solo non dimostra che la via LECITA tenga: dimostra solo
    che la via rotta e' chiusa, e questa e' meta' del cerchio.
    """
    det = lette[y][1]
    i = det["imposte"]
    return _q(_posizione(lette[y][0]) - (_posizione(lette[y - 1][0])
             + D(str(i["current_tax"])) - D(str(i["saldo_paid"]))
             - D(str(i["acconti_paid"])) - D(str(i["rate_paid"]))))


# ─────────────────────────────── I-a ───────────────────────────────

def test_a_rate_sotto_il_centesimo_le_parti_dicono_la_cella(monkeypatch):
    """I-a dalla parte del numero: le due parti dichiarate di una posizione,
    prese AL CENTESIMO, devono sommare alla cella che descrivono.

    Fixture della revisione: rata 3252,815/3252,825 (di mezzo centesimo) sopra
    una base con massa tributaria 10.000, e nessun override. Su `b08a9a6` il
    riallineatore riscrive `generated_debt` (0 → 0.005) per una condizione resa
    vera da due numeri NON omogenei; ora il confronto e' fra quantizzati e la
    riga, al centesimo, dice il vero: 3252.825 + 0 = 3252.83 = `sp16e`.

    La coda grezza RESTA nei `details` (`residual_short` 3252.825,
    `generated_debt` 5760.04707000), e NON e' un dimenticatoio: quantizzarla
    vuol dire cambiare il `saldo_due` che l'anno dopo ci si paga sopra, e la
    misura dice quanto costa — un centesimo di cassa su otto scenari gia'
    fissati nei test (`test_forecast_scoperto`, `test_forecast_prestito_quota_
    breve`: 204440.71 invece di 204440.72). E' un nodo per l'owner, non una
    correzione da infilare in un giro di fix: vedi il rapporto del giro.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    piano = {"debiti_tributari": {"opening": 10000.00, "saldo": 3494.36,
                                  "rateizzato": 6505.64,
                                  "amounts": [3252.815, 3252.825]}}
    try:
        with sessions() as db:
            res, cid, sid, rows = _esito(db, "i-a-code", _righe_base(piano=piano))
            assert res["forecast_generated"] is True, res["message"]
            lette = _dettagli(db, "i-a-code", cid, sid, rows)
            for y in ANNI_3:
                riga = lette[y][0]
                d = _riga_pregresso(lette[y][1], "debiti_tributari")
                assert _q(d["generated"]) + _q(d["residual_short"]) == _q(
                    riga["sp16e_debiti_tributari_breve"]), (y, d)
                assert _q(D(str(lette[y][1]["imposte"]["generated_debt"]))) + _q(
                    d["residual_short"]) == _q(riga["sp16e_debiti_tributari_breve"]), (
                    y, lette[y][1]["imposte"], d)
                assert _q(D(str(lette[y][1]["imposte"]["generated_credit"]))) + _q(
                    lette[y][1]["imposte"]["opening_credit_left"]) == _q(
                    riga["sp06e_crediti_tributari_breve"]), (y, lette[y][1]["imposte"])
    finally:
        engine.dispose()


def test_a_senza_override_il_riallineamento_non_cambia_niente(monkeypatch, caplog):
    """Il rilievo I-a, preso dalla sua parte piu' forte: *quella* funzione, senza
    un `sp_overrides` e senza un residuo posato, DEVE ESSERE UN'IDENTITA'.

    La versione difettosa confrontava il persistito con una somma NON
    quantizzata: con una rata sotto il centesimo (1333.335) la condizione
    diventava vera da sola e riscriveva `generated_debt` (misurato dalla
    revisione: `0` → `0.005`, con `sp06g` a −0,01 e la cassa a +0,01
    nell'anno dopo) lontano da qualunque confronto, a ipotesi invariate. Due
    versioni del motore che si dividono per una coda di arrotondamento, a parita'
    di override assenti, passerebbero il banco come identiche: invece qui si
    misura.

    Affermazione di PROPRIETA' e non di numero: lo stesso scenario, una volta
    col riallineatore e una volta disattivandolo (`monkeypatch`), deve dare lo
    stesso identico previsionale. E' rosso su `b08a9a6` (il riallineatore
    spostava celle), verde qui.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    piano = {"debiti_tributari": {"opening": 10000.00, "saldo": 6000.00,
                                 "rateizzato": 4000.00,
                                 "amounts": [1333.335, 1333.335, 1333.33]}}

    def _esegui(tag):
        engine, sessions = memory_sessions()
        try:
            with sessions() as db:
                res, _cid, sid, _rows = _esito(db, f"i-a-{tag}", _righe_base(piano=piano),
                                               nome="i-a")
                assert res["forecast_generated"] is True, res["message"]
                return {y: dict(bs) for y, bs, ce in read_forecast_maps(db, sid)}
        finally:
            engine.dispose()

    con = _esegui("con-riallineamento")
    from calculations.forecast_engine import ForecastEngine
    monkeypatch.setattr(ForecastEngine, "_realign_sp_declarations",
                        classmethod(lambda cls, details, forecast_bs: None))
    senza = _esegui("senza-riallineamento")

    assert con.keys() == senza.keys()
    fuori = [(y, k) for y in con for k in con[y] if con[y][k] != senza[y][k]]
    assert fuori == [], (
        "il riallineamento ha mosso celle senza che nessuno abbia forzato niente: "
        f"{fuori}", {y: {k: (senza[y][k], con[y][k]) for k, _ in fuori if _ == y} for y in con})
    # E la coerenza che il riallineamento DEVE garantire, comunque: la riga
    # dichiarata somma al persistito, al centesimo.
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            res, cid, sid, rows = _esito(db, "i-a-dettagli", _righe_base(piano=piano))
            lette = _dettagli(db, "i-a-dettagli", cid, sid, rows)
            for y in ANNI_3:
                d = _riga_pregresso(lette[y][1], "debiti_tributari")
                assert (_q(d["generated"]) + _q(d["residual_short"])) == _q(
                    lette[y][0]["sp16e_debiti_tributari_breve"]), (y, d)
                assert lette[y][1].get("residuo_quadratura") in ([], None), (y, lette[y][1].get("residuo_quadratura"))
    finally:
        engine.dispose()


# ─────────────────────── I-b: `sp17e` senza piano ───────────────────────

def test_sp17e_senza_piano_si_rifiuta_quando_l_anno_dopo_lo_legge(monkeypatch):
    """Rilievo I-b: in `saldo_acconto` il lato lungo tributario lo scrive il
    runoff, NON il persistito — e senza piano il runoff di uno zero vale zero.

    L'override quindi non viene "portato avanti": viene CANCELLATO, e la cassa
    dell'anno dopo torna esattamente quella del gemello (sonde `E0`, `K4` della
    revisione: 2028 identica, scarto di flusso −7.000,01 / −3.000). E' I1 sulla
    quarta riga, e il motore lo RIFIUTA con lo stesso ragionamento di I1-bis.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            res, cid, sid, rows = _esito(db, "i-b-rifiuto", _righe_base(
                overrides={2027: {"sp17e_debiti_tributari_lungo": 7000.01}}))
            assert res["forecast_generated"] is False, res["message"]
            assert "sp17e_debiti_tributari_lungo" in res["message"], res["message"]
            assert "non è ammesso" in res["message"], res["message"]
            # Ruling 63: qui il piano NON c'e' (il ramo lo pretende), quindi
            # il messaggio deve CHIEDERE di metterlo, non di modificare ciò
            # che non esiste: «Modifica il piano» era la strada verso un
            # nulla che l'utente avrebbe cercato al passo 6 senza trovarlo.
            assert "Imposta un piano" in res["message"], res["message"]
            assert "Modifica il piano" not in res["message"], res["message"]
            assert "«Imposte»" in res["message"], res["message"]
            assert read_forecast_maps(db, sid) == []
            # E l'ultimo anno NO: nessuno lo legge dopo, quindi la stessa cifra
            # e' una forzatura legittima (il confine del rifiuto e' "l'anno che
            # lo leggerebbe", non "la riga").
            res2, cid2, sid2, rows2 = _esito(db, "i-b-ultimo-anno", _righe_base(
                overrides={ANNI_3[-1]: {"sp17e_debiti_tributari_lungo": 7000.01}}))
            assert res2["forecast_generated"] is True, res2["message"]
            lette = _dettagli(db, "i-b-ultimo-anno", cid2, sid2, rows2)
            assert _letto(lette, ANNI_3[-1], "sp17e_debiti_tributari_lungo") == D("7000.01")
    finally:
        engine.dispose()


def test_sp17e_in_via_manuale_non_si_rifiuta_e_si_porta_avanti(monkeypatch):
    """Rilievo M-1: in via manuale `sp17e` segue `_prev × (1 + crescita)`, quindi
    l'override SUPERVIVE all'anno dopo — rifiutarlo vorrebbe dire togliere una
    liberta' che il motore onora (sonda `X2`: il base porta avanti 250,25 dal
    2027 al 2030; `test_via_manuale_porta_avanti_lo_stesso_override` e' la
    guardia controllore sullo stesso punto lato `sp16e`).
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    piano = {"debiti_tributari": {"opening": 10000.00, "saldo": 6000.00,
                                  "rateizzato": 4000.00, "amounts": [2000.00, 2000.00]}}
    try:
        with sessions() as db:
            res, cid, sid, rows = _esito(db, "m-1-manuale", _righe_base(
                piano=piano, manuale=True,
                overrides={2027: {"sp17e_debiti_tributari_lungo": 250.25}}))
            assert res["forecast_generated"] is True, res["message"]
            lette = _dettagli(db, "m-1-manuale", cid, sid, rows)
            for y in ANNI_3:
                assert _letto(lette, y, "sp17e_debiti_tributari_lungo") >= D("250.25"), y
    finally:
        engine.dispose()


# ─────────────── I-c: il lato BREVE sotto il rateizzato dovuto ───────────────

PIANO_ALTRI_CENT = {"altri_debiti": {"opening": 55000.00, "amounts": [18333.34, 18333.33]}}
PIANO_TRIB_CENT = {"debiti_tributari": {"opening": 10000.00, "saldo": 6000.00,
                                        "rateizzato": 4000.00,
                                        "amounts": [1333.34, 1333.33, 1333.33]}}


@pytest.mark.parametrize("piano,campo,sotto,sopra", [
    (PIANO_ALTRI_CENT, "sp16g_altri_debiti_breve", D("0"), D("36666.68")),
    (PIANO_TRIB_CENT, "sp16e_debiti_tributari_breve", D("500.25"), D("4000.00")),
])
def test_override_breve_sotto_il_rateizzato_si_rifiuta_sopra_no(monkeypatch, piano, campo,
                                                                sotto, sopra):
    """Rilievo I-c: sotto la quota che il calendario deve pagare l'anno dopo,
    l'override non e' una scelta — e' una rata che viene pagata DUE volte.

    Il motore la sottrae dal rateizzato in N (sonda `P1`: cassa 2027 −1.333,34),
    poi in N+1 riparte dal calendario e la ripaga (`rate_paid` dichiarato su una
    rata che l'override aveva gia' tolto, scarto di flusso +1.333,34). Sopra
    quella quota invece l'override e' la parte GENERATA, e si porta avanti: la
    stessa cella, due destini, e il confine e' il `residual_short` del piano.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            res, _cid, sid, _rows = _esito(db, f"i-c-sotto-{campo}",
                                           _righe_base(piano=piano,
                                                       overrides={2027: {campo: sotto}}))
            assert res["forecast_generated"] is False, res["message"]
            assert campo in res["message"] and "non è ammesso" in res["message"], res["message"]
            assert "deve pagare" in res["message"], res["message"]
            assert read_forecast_maps(db, sid) == []

        with sessions() as db:
            res2, cid2, sid2, rows2 = _esito(db, f"i-c-sopra-{campo}",
                                             _righe_base(piano=piano,
                                                         overrides={2027: {campo: sopra}}))
            assert res2["forecast_generated"] is True, res2["message"]
            lette = _dettagli(db, f"i-c-sopra-{campo}", cid2, sid2, rows2)
            assert _letto(lette, 2027, campo) == _q(sopra)
            # Rilievo m-E, punto 1: l'altra meta' del cerchio. Il rifiuto
            # (ramo `sotto`) chiude la via rotta; qui si deve vedere che la via
            # lecita TENGA, e il numero che lo dice non e' la cella del 2027
            # (quella e' l'override stesso) bensi' lo scarto di flusso
            # dell'anno dopo: un debito che si e' spostato senza un versamento
            # che lo dice vive li', non nell'anno dell'override.
            assert _scarto_di_flusso(lette, 2028) == D("0.00"), (
                campo, _scarto_di_flusso(lette, 2028))
    finally:
        engine.dispose()


@pytest.mark.parametrize("forzato,si_genera", [
    (D("1333.33"), True),    # la rata che il piano deve pagare nel 2028, ESATTA
    (D("1333.32"), False),   # un centesimo sotto: e' la rata pagata due volte
])
def test_i_c_confine_la_rata_dovuta_esatta_si_genera_un_centesimo_sotto_no(
        monkeypatch, forzato, si_genera):
    """Rilievo m-E, punto 2: il confine di I-c e' il `residual_short` del
    piano, NON meta' di qualcosa, e la confronto e' `<` (sotto), non `<=`.

    Misure della revisione (B5/B6): con piano tributario 6.000 + 4.000 e rate
    1.333,34/1.333,33/1.333,33, forzare la rata DOVUTA l'anno dopo (1.333,33)
    genera, con scarto di flusso 0,00; forzare 1.333,32 si rifiuta. Un `<` in
    `<=` si vede solo qui: e' la mutazione 3 della lista del giro.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            res, cid, sid, rows = _esito(db, f"i-c-confine-{forzato}", _righe_base(
                piano=PIANO_TRIB_CENT,
                overrides={2027: {"sp16e_debiti_tributari_breve": forzato}}))
            if si_genera:
                assert res["forecast_generated"] is True, res["message"]
                lette = _dettagli(db, f"i-c-confine-{forzato}", cid, sid, rows)
                assert _letto(lette, 2027, "sp16e_debiti_tributari_breve") == forzato
                assert _scarto_di_flusso(lette, 2028) == D("0.00"), (
                    _scarto_di_flusso(lette, 2028))
                # La riga lo dichiara: quota generata 0, tutta la cella e'
                # la rata che il calendario doveva pagare.
                d = _riga_pregresso(lette[2027][1], "debiti_tributari")
                assert _q(d["generated"]) == D("0.00"), d
            else:
                assert res["forecast_generated"] is False, res["message"]
                assert "deve pagare" in res["message"], res["message"]
                assert read_forecast_maps(db, sid) == []
    finally:
        engine.dispose()


@pytest.mark.parametrize("forzato,apertura,generato", [
    (D("5000.00"),  D("5000.00"), D("0.00")),       # sotto il credito d'apertura
    (D("20000.00"), D("10000.00"), D("10000.00")),  # sopra il credito d'apertura
])
def test_override_sp06e_riempie_prima_il_credito_d_apertura(
        monkeypatch, forzato, apertura, generato):
    """Rilievo m-E, punto 5: la regola dichiarata della ripartizione forzata.

    `test_override_sp06e_...` (in cima a questo file) asseriva gia' la SOMMA
    delle due chiavi pari alla cella; qui si asserisce l'ORDINE, che e' la
    meta' mancante: prima si esaurisce `opening_credit_left` (il credito
    portato dall'anno prima), il resto va a `generated_credit`. Il gemello
    senza override dichiara 10.000,00 + 24.895,58 = 34.895,58: sotto 10.000
    tutta la cella e' credito d'apertura, sopra la eccedenza e' generata.
    E' la mutazione 1 (ripartizione invertita) che questa riga uccide.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            res, cid, sid, rows = _esito(db, f"split-{forzato}", _righe_base(
                overrides={2027: {"sp06e_crediti_tributari_breve": forzato}}))
            assert res["forecast_generated"] is True, res["message"]
            lette = _dettagli(db, f"split-{forzato}", cid, sid, rows)
            imp = lette[2027][1]["imposte"]
            assert _q(D(str(imp["opening_credit_left"]))) == _q(apertura), imp
            assert _q(D(str(imp["generated_credit"]))) == _q(generato), imp
            assert _q(apertura) + _q(generato) == _letto(lette, 2027, "sp06e_crediti_tributari_breve")
    finally:
        engine.dispose()


# ─────────────── I-d: le sotto-voci che il piano dei crediti rigenera ───────────────

# Le sei chiavi che il piano dei crediti COMMERCIALI rigenera: l'aggregato
# `sp07` (il calendario lo scrive come `residual_long` + la quota fiscale
# cresciuta, `:2745-2763`) e le cinque sotto-voci che `_alloc` ritaglia da
# quell'aggregato sulle proporzioni dell'anno base (`:3351-3366`). Non `sp07e`
# /`sp07f`: quelle il piano non le tocca, e stanno nel test qui sotto.
PIANO_CREDITI_LUNGHI = {"crediti_commerciali": {"opening": 133000.00,
                                                "amounts": [66500.00, 66500.00]}}
GOVERNATE = ("sp07_crediti_lungo", "sp07a_crediti_clienti_lungo",
             "sp07b_crediti_controllate_lungo", "sp07c_crediti_collegate_lungo",
             "sp07d_crediti_controllanti_lungo", "sp07g_crediti_altri_lungo")


def _base_crediti(db, user):
    """L'anno base con un creditorio LUNGO commerciale davvero popolato.

    Serve una fixture cosi' per misurare I-d: su `_base_tributi` ogni `sp07*` e'
    zero, e `_alloc` di un aggregato su proporzioni tutte zero mette tutto nella
    bottega primaria — quindi la distinzione fra una sotto-voce governata e una
    che cresce da `prev` non si vede (misurato: `sp07e` a 0,00 con e senza
    override, perche' l'importo finiva tutto in `sp07g`). Qui le proporzioni
    esistono, e il calendario le calpesta solo dove le calpesta davvero.
    """
    company_id = _base_tributi(db, user)
    fy = db.query(FinancialYear).filter(FinancialYear.company_id == company_id).one()
    b = db.query(BalanceSheet).filter(BalanceSheet.financial_year_id == fy.id).one()
    for campo, val in (
        ("sp07_crediti_lungo", "40000.00"), ("sp07a_crediti_clienti_lungo", "20000.00"),
        ("sp07b_crediti_controllate_lungo", "5000.00"), ("sp07c_crediti_collegate_lungo", "5000.00"),
        ("sp07e_crediti_tributari_lungo", "5000.00"), ("sp07f_imposte_anticipate_lungo", "2000.00"),
        ("sp07g_crediti_altri_lungo", "3000.00"),
        # Il passivo segue: il foglio deve pareggiare, o il test misura un fabbisogno
        # invece di misurare un calendario.
        ("sp17_debiti_lungo", "90000.00"), ("sp17g_altri_debiti_lungo", "60000.00"),
    ):
        setattr(b, campo, D(val))
    db.commit()
    return company_id


@pytest.mark.parametrize("campo", GOVERNATE)
def test_sp07_governate_dal_piano_crediti_si_rifiutano(monkeypatch, campo):
    """Rilievo I-d: il rifiuto su `sp07` da solo non chiudevava niente, perche'
    `sp07` NON e' una cella di SP Prev. — quelle che l'utente tocca sono
    `sp07a`…`sp07g`, e il piano le rigenera dall'aggregato.

    Misura su QUESTA fixture (`_base_crediti`, piano 133.000 in due rate,
    override 250,25 nel 2027, valore del 2028 col rifiuto disattivato per
    vedere che cosa succederebbe): tutti e sei tornano ESATTI al gemello —
    `sp07` 1225.00 == 1225.00, `sp07a` 612.50 == 612.50, `sp07b`/`sp07c`
    153.13 == 153.13, `sp07d` 0 == 0, `sp07g` 91.86 == 91.86 — e con loro la
    CASSA, identica a 277.564,02: l'override e' sparito, la differenza se
    l'e' presa la cassa senza un solo flusso. Sono le sei chiavi di `GOVERNATE`.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()

    try:
        with sessions() as db:
            res, _cid, sid, _rows = _esito(db, f"i-d-{campo}",
                                          _righe_base(piano=PIANO_CREDITI_LUNGHI,
                                                      overrides={2027: {campo: 250.25}}),
                                          base=_base_crediti)
            assert res["forecast_generated"] is False, f"{campo}: doveva essere rifiutato"
            assert campo in res["message"], res["message"]
            assert "piano di scadenziamento" in res["message"], res["message"]
            assert read_forecast_maps(db, sid) == []
    finally:
        engine.dispose()


@pytest.mark.parametrize("campo", ["sp07e_crediti_tributari_lungo",
                                   "sp07f_imposte_anticipate_lungo"])
def test_sp07e_ed_sp07f_non_si_rifiutano_perche_sopravvivono(monkeypatch, campo):
    """Le due che il piano NON rigenera, e la guardia che lo verifica.

    L'altra meta' del rilievo I-d: `sp07e` entra nell'aggregato come
    `_prev × crescita` (`:2757`), `sp07f` dal kernel del deferred. Rifiutarle
    sarebbe una restrizione inventata — `CLAUDE.md` vuole che ogni rifiuto abbia
    una misura dietro, non una simmetria. Misura su QUESTA fixture, override
    250,25 nel 2027: nel 2028 `sp07e` 75.03 contro 153.13 del gemello, `sp07f`
    56.26 contro 61.25 — DIVERSI, quindi l'override ha attraversato l'anno e
    non e' stato calpestato. La prova e' doppia: il previsionale si genera, e
    il valore dell'anno dopo non coincide col gemello (se un domani il
    calendario le cancellasse, il rifiuto dovrebbe scattare: questo test e' il
    campanello che lo dira').
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()

    try:
        with sessions() as db:
            res, cid, sid, rows = _esito(db, f"i-d-ok-{campo}",
                                        _righe_base(piano=PIANO_CREDITI_LUNGHI,
                                                    overrides={2027: {campo: 250.25}}),
                                        base=_base_crediti)
            assert res["forecast_generated"] is True, res["message"]
            lette = _dettagli(db, f"i-d-ok-{campo}", cid, sid, rows)
        with sessions() as db:
            res2, cid2, sid2, rows2 = _esito(db, f"i-d-gemello-{campo}",
                                            _righe_base(piano=PIANO_CREDITI_LUNGHI), base=_base_crediti)
            gemelle = _dettagli(db, f"i-d-gemello-{campo}", cid2, sid2, rows2)
        assert _letto(lette, 2027, campo) == D("250.25")
        assert _letto(lette, 2028, campo) != _letto(gemelle, 2028, campo), \
            f"{campo}: l'override e' tornato al gemello ({_letto(gemelle, 2028, campo)}), il rifiuto qui sarebbe dovuto scattare"
    finally:
        engine.dispose()


def test_senza_piano_crediti_nessuna_sottovoce_si_rifiuta(monkeypatch):
    """Il confine del rifiuto e' il PIANO, non il campo: senza scadenziamento
    dei crediti le sei chiavi di `GOVERNATE` sono forzabili come sempre (la
    riga segue `_prev × (1 + crescita)`, e l'override si porta avanti).
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        for campo in GOVERNATE:
            with sessions() as db:
                res, cid, sid, rows = _esito(db, f"i-d-senza-piano-{campo}",
                                             _righe_base(overrides={2027: {campo: 250.25}}),
                                             base=_base_crediti)
                assert res["forecast_generated"] is True, f"{campo}: {res['message']}"
                lette = _dettagli(db, f"i-d-senza-piano-{campo}", cid, sid, rows)
                assert _letto(lette, 2027, campo) == D("250.25"), campo
    finally:
        engine.dispose()


# ─────────────── M-4: l'override sull'ANNO DUE, e le due sedi ───────────────

@pytest.mark.parametrize("campo,piano", [
    ("sp17d_debiti_fornitori_lungo",
     {"debiti_fornitori": {"opening": 100000.00, "amounts": [50000.00, 50000.00]}}),
    ("sp07a_crediti_clienti_lungo",
     {"crediti_commerciali": {"opening": 100000.00, "amounts": [50000.00, 50000.00]}}),
])
def test_il_rifiuto_vale_anche_se_l_override_e_solamente_sull_ultimo_anno(monkeypatch, campo, piano):
    """Rilievo M-4 (mutazione M8): controllare il rifiuto solo sulla PRIMA riga
    non prova niente, perche' il calendario governa la riga in OGNI anno del
    piano, l'ultimo compreso (e' il caso `R1` della revisione: fornitori +
    `sp17d` nel 2029, dopo l'ultima rata).
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            res, _cid, sid, _rows = _esito(db, f"m-8-{campo}", _righe_base(
                piano=piano, overrides={ANNI_3[-1]: {campo: 250.25}}))
            assert res["forecast_generated"] is False, res["message"]
            assert campo in res["message"], res["message"]
    finally:
        engine.dispose()


def test_le_due_sedi_di_generated_debt_dicono_lo_stesso_numero_sotto_override(monkeypatch):
    """Rilievo M-4 (mutazione M4, che la rete non vedeva): `details['imposte']`
    e la riga `debiti_tributari` di `details['pregresso']` dichiarano LO STESSO
    debito generato anche quando `sp16e` e' forzato.

    Il confronto che la rete saltava `if forzato(...)` e' proprio quello che
    tiene oneste le due sedi: qui corre sempre, e sui campi forzati.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    piano = {"debiti_tributari": {"opening": 10000.00, "saldo": 6000.00,
                                 "rateizzato": 4000.00,
                                 "amounts": [1333.34, 1333.33, 1333.33]}}
    try:
        with sessions() as db:
            res, cid, sid, rows = _esito(db, "m-4-due-sedi", _righe_base(
                piano=piano, overrides={2028: {"sp16e_debiti_tributari_breve": 8000.00}}))
            assert res["forecast_generated"] is True, res["message"]
            lette = _dettagli(db, "m-4-due-sedi", cid, sid, rows)
            for y in ANNI_3:
                det = lette[y][1]
                assert _q(D(str(det["imposte"]["generated_debt"]))) == _q(
                    D(str(_riga_pregresso(det, "debiti_tributari")["generated"]))), (y, det)
                assert _q(D(str(det["imposte"]["generated_debt"]))) + _q(
                    _riga_pregresso(det, "debiti_tributari")["residual_short"]) == _q(
                    lette[y][0]["sp16e_debiti_tributari_breve"]), y
    finally:
        engine.dispose()


def test_lo_scarto_di_flusso_dell_anno_dopo_e_zero_sulla_via_lecita(monkeypatch):
    """Meta' mancante di I1: il rifiuto chiude la via rotta, ma serve che la via
    lecita tenga — e il numero che lo dice e' lo scarto di flusso dell'anno DOPO
    (la griglia della revisione: `pos(N) − [pos(N−1) + imposta − saldo − acconti
    − rate]`), non la cella dell'anno dell'override, che e' l'override stesso.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            for nome, ov in (("senza-override", None),
                             ("sp16e-forzato", {2027: {"sp16e_debiti_tributari_breve": 40000.33}}),
                             ("sp06e-forzato", {2027: {"sp06e_crediti_tributari_breve": 60000.55}})):
                res, cid, sid, rows = _esito(db, f"flusso-{nome}", _righe_base(overrides=ov))
                assert res["forecast_generated"] is True, f"{nome}: {res['message']}"
                lette = _dettagli(db, f"flusso-{nome}", cid, sid, rows)
                for y in ANNI_3[1:]:
                    assert _scarto_di_flusso(lette, y) == D("0.00"), (nome, y, _scarto_di_flusso(lette, y))
    finally:
        engine.dispose()


# ─────────────── M-2: il messaggio deve essere una strada, non un muro ───────────────

def test_il_messaggio_del_rifiuto_indica_passo_ed_etichetta(monkeypatch):
    """Rilievo M-2 (sonda `S2`): l'override proibito resta nel sacco, e da li'
    ogni `PATCH` su UNA CELLA DIVERSA risponde 400 con lo stesso messaggio fino
    a che quella cella non torna a `null`. Se il messaggio non dice quale saldo
    e' e dove si scadenzia, l'utente ha un errore che non si puo' togliere.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            res, _cid, _sid, _rows = _esito(db, "m-2-msg", _righe_base(
                piano={"debiti_fornitori": {"opening": 100000.00, "amounts": [50000.00, 50000.00]}},
                overrides={2027: {"sp17d_debiti_fornitori_lungo": 250.25}}))
            msg = res["message"]
            assert "debiti verso fornitori" in msg, msg          # l'etichetta, non la chiave tecnica
            assert "'debiti_fornitori'" not in msg, msg
            assert "Pregresso e nuovo" in msg, msg               # il passo che lo scadenzia
            assert "value: null" in msg, msg                     # la via d'uscita
            assert "non è ammesso" in msg, msg                   # e l'accento, come `validate_pregresso`

        with sessions() as db:
            res2, _c2, _s2, _r2 = _esito(db, "m-2-msg-trib", _righe_base(
                piano={"debiti_tributari": {"opening": 10000.00, "saldo": 6000.00,
                                            "rateizzato": 4000.00,
                                            "amounts": [1333.34, 1333.33, 1333.33]}},
                overrides={2027: {"sp17e_debiti_tributari_lungo": 250.25}}))
            # I tributari NON stanno al passo 6: li scadenzia il passo Imposte.
            assert "Imposte" in res2["message"], res2["message"]
            assert "debiti tributari" in res2["message"], res2["message"]
    finally:
        engine.dispose()


# ══ N-I1 (Ruling 61, giro 3): la transizione «via manuale → automatico» ══
#
# Il ramo `else` del calcolatore tributario (primo anno di piano OPPURE anno
# preceduto dalla via manuale) fa `saldo_due = max(0, opening - rate_aperto)`.
# Se il debito tributario lasciato dall'anno manuale e' INFERIORE al rateizzato
# ancora aperto, il `max` taglia il deficit in silenzio: il calendario riparte
# intero, la cassa assorbe la differenza, e lo scarto di flusso dell'anno dopo
# e' +2.666,66 anche senza override (sonda `sonda_trans.py` della revisione).
# Il motore ora RIFIUTA (a) nel kernel, e (b) in `_rifiuto_override_governati`
# esenta la via manuale solo se anche l'anno dopo e' manuale.

PIANO_TRANS = {"debiti_tributari": {"opening": 10000.00, "saldo": 6000.00,
                                    "rateizzato": 4000.00,
                                    "amounts": [1333.34, 1333.33, 1333.33]}}
# Il piano della sonda `sonda_ni1_lungo.py` del coordinatore: quattro rate
# tonde su quattro anni, per misurare la transizione 2028→2029.
PIANO_SONDA = {"debiti_tributari": {"opening": 10000.00, "saldo": 6000.00,
                                    "rateizzato": 4000.00,
                                    "amounts": [1000.00] * 4}}
ANNI_4 = (2027, 2028, 2029, 2030)


def _righe_trans(manuale_anni, overrides=None, growth=-100, anni=ANNI_3,
                 piano=None, g17=None):
    """Anni di piano (default 3); `manuale_anni` = insieme di anni in via manuale.

    L'anno in via manuale porta `sp16e_growth_pct = growth` (default −100:
    azzera il debito, che e' il caso che apre il buco) e, se `g17` e' dato,
    anche `sp17e_growth_pct = g17`; gli altri restano automatici. `overrides`
    e' PER ANNO, come in `_righe_base`.
    """
    rows = []
    for y in anni:
        r = {"forecast_year": y, "revenue_growth_pct": 3.33}
        if y in manuale_anni:
            r["sp16e_growth_pct"] = growth
            if g17 is not None:
                r["sp17e_growth_pct"] = g17
        if overrides and y in overrides:
            r["sp_overrides"] = dict(overrides[y])
        rows.append(r)
    rows[0]["pregresso"] = piano or PIANO_TRANS
    return rows


def test_ni1_t1_transizione_manuale_auto_sotto_il_rateizzato_si_rifiuta(monkeypatch):
    """T1: 2027 manuale con `sp16e_growth_pct = −100`, 2028 automatico, nessun
    override. Il debito lasciato (0) e' sotto il rateizzato aperto (2.666,66):
    il kernel (a) RIFIUTA, con l'anno 2028 nel messaggio.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            res, _cid, sid, _rows = _esito(db, "ni1-t1", _righe_trans({2027}))
            assert res["forecast_generated"] is False, res["message"]
            assert "2028" in res["message"], res["message"]
            assert "rateizz" in res["message"], res["message"]
            assert read_forecast_maps(db, sid) == []
    finally:
        engine.dispose()


def test_ni1_t3_override_sotto_il_rateizzato_in_anno_manuale_si_rifiuta(monkeypatch):
    """T3 (percorso di servizio, bulk): override `sp16e` 2027 = 2.000 in un anno
    manuale seguito da un anno automatico → RIFIUTATO (400 via kernel).

    Con Ruling 62 lo ferma il kernel (a), non piu' il controllo (b) sull'anno
    manuale: l'unica guardia della transizione e' lei, perche' misura il totale
    `sp16e + sp17e` che l'anno dopo legge davvero. Il messaggio e' quello del
    kernel e nomina l'anno manuale (2027) e quello che riparte (2028).
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            res, _cid, sid, _rows = _esito(
                db, "ni1-t3", _righe_trans({2027}, overrides={2027: {
                    "sp16e_debiti_tributari_breve": 2000.00}}))
            assert res["forecast_generated"] is False, res["message"]
            assert "non può ripartire" in res["message"], res["message"]
            assert "2027" in res["message"] and "2028" in res["message"], res["message"]
            assert read_forecast_maps(db, sid) == []
    finally:
        engine.dispose()


def test_ni1_t3_patch_sp_override_rifiuta_e_rollback(monkeypatch):
    """T3 sul percorso `PATCH /sp-override`: 400 e `sp_overrides` non persistito.

    L'override proibito dal rifiuto (b) non deve restare nel sacco JSON, perche'
    un override proibito avvelena ogni `PATCH` successivo sullo stesso scenario
    (`patch_400_loop`, CLAUDE.md).
    """
    from backend.app.api.v1 import budget_scenarios as bs
    from backend.app.schemas import budget as schemas
    from database.models import BudgetAssumptions
    import fastapi
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id = _base_tributi(db, "ni1-t3-patch")
            sc = bs.create_budget_scenario(
                company_id,
                schemas.BudgetScenarioCreate(company_id=company_id, name="t3p",
                                             base_year=2026, scenario_type="budget"),
                user_id="ni1-t3-patch", db=db)
            rows = _righe_trans({2027})
            res = bs.bulk_upsert_assumptions(
                company_id, sc.id, request={"assumptions": rows, "auto_generate": False},
                user_id="ni1-t3-patch", db=db)
            assert res["success"] is True
            req = schemas.SpOverrideRequest(overrides=[{
                "forecast_year": 2027, "field": "sp16e_debiti_tributari_breve",
                "value": 2000.00}])
            with pytest.raises(fastapi.HTTPException) as exc:
                bs.patch_sp_override(company_id, sc.id, req,
                                     user_id="ni1-t3-patch", db=db)
            assert exc.value.status_code == 400, exc.value.detail
            # Ruling 62: lo ferma il kernel (a), e il 400 porta il SUO messaggio.
            assert "non può ripartire" in str(exc.value.detail), exc.value.detail
            bag = db.query(BudgetAssumptions).filter(
                BudgetAssumptions.scenario_id == sc.id,
                BudgetAssumptions.forecast_year == 2027).first().sp_overrides
            assert not (bag or {}).get("sp16e_debiti_tributari_breve"), bag
    finally:
        engine.dispose()


def test_ni1_t2_override_sopra_il_rateizzato_genera_e_scarto_zero(monkeypatch):
    """T2: override `sp16e` 2027 = 5.000 (sopra il rateizzato aperto 2.666,66),
    2028 automatico. Si genera, e lo scarto di flusso tributario del 2028 e'
    0,00: la via lecita tiene.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            res, cid, sid, rows = _esito(
                db, "ni1-t2", _righe_trans({2027}, overrides={2027: {
                    "sp16e_debiti_tributari_breve": 5000.00}}))
            assert res["forecast_generated"] is True, res["message"]
            lette = _dettagli(db, "ni1-t2", cid, sid, rows)
            assert _letto(lette, 2027, "sp16e_debiti_tributari_breve") == D("5000.00")
            assert _scarto_di_flusso(lette, 2028) == D("0.00"), _scarto_di_flusso(lette, 2028)
    finally:
        engine.dispose()


def test_ni1_t4_tutti_manuali_override_zero_genera(monkeypatch):
    """T4: tutti gli anni in via manuale, override `sp16e` 2027 = 0. Nessun anno
    automatico riparte dal calendario, quindi (a)/(b) non scattano: si genera.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            res, cid, sid, rows = _esito(
                db, "ni1-t4", _righe_trans(set(ANNI_3), overrides={2027: {
                    "sp16e_debiti_tributari_breve": 0}}))
            assert res["forecast_generated"] is True, res["message"]
            lette = _dettagli(db, "ni1-t4", cid, sid, rows)
            assert _letto(lette, 2027, "sp16e_debiti_tributari_breve") == D("0.00")
    finally:
        engine.dispose()


# ══ Ruling 62: l'esenzione (b) di Ruling 61 rifiutava override leciti ══
#
# Misura del coordinatore (`sonda_ni1_lungo.py`, piano 4 x 1000 su 4 anni,
# 2028 manuale, 2029-2030 automatici): la soglia `_rateizzato_aperto_dopo`
# confrontava il SOLO `sp16e` forzato (1000) con TUTTO il rateizzato aperto
# (2000), ma in via manuale `sp17e` porta ancora il lato lungo (2000 in
# `sp17e` dal runoff del 2027): il totale che il 2029 legge e' 3000, e
# l'override del valore IDENTICO a quello del motore veniva RIFIUTATO. Con
# (b) speso negli anni manuali (`sonda_ni1_senza_b.py`) le via lecite generano
# con scarto 0,00 e il kernel (a) ferma da solo il buco vero. I tre casi della
# sonda diventano test: i primi due sono ROSSI su 25a5357 (il rifiuto (b)
# li ferma) e verdi qui.

def test_ruling62_override_identico_al_motore_genera(monkeypatch):
    """Sonda A/B: override `sp16e` 2028 = 1000, il valore che il motore produce
    da sé in via manuale con crescita 0: genera, scarto 2029 e 2030 = 0,00.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            res, cid, sid, rows = _esito(db, "r62-1000", _righe_trans(
                {2028}, overrides={2028: {"sp16e_debiti_tributari_breve": 1000.00}},
                growth=0, anni=ANNI_4, piano=PIANO_SONDA))
            assert res["forecast_generated"] is True, res["message"]
            lette = _dettagli(db, "r62-1000", cid, sid, rows)
            assert _letto(lette, 2028, "sp16e_debiti_tributari_breve") == D("1000.00")
            for y in (2029, 2030):
                assert _scarto_di_flusso(lette, y) == D("0.00"), (y, _scarto_di_flusso(lette, y))
    finally:
        engine.dispose()


def test_ruling62_override_zero_lato_lungo_in_sp17e_genera(monkeypatch):
    """Sonda G: override `sp16e` 2028 = 0 con il lato lungo ancora in `sp17e`
    (2000 dal runoff): il totale 2000 NON è sotto il rateizzato aperto (2000),
    la transizione è sana, genera con scarto 0,00 negli anni automatici.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            res, cid, sid, rows = _esito(db, "r62-0", _righe_trans(
                {2028}, overrides={2028: {"sp16e_debiti_tributari_breve": 0}},
                growth=0, anni=ANNI_4, piano=PIANO_SONDA))
            assert res["forecast_generated"] is True, res["message"]
            lette = _dettagli(db, "r62-0", cid, sid, rows)
            assert _letto(lette, 2028, "sp16e_debiti_tributari_breve") == D("0.00")
            assert _letto(lette, 2028, "sp17e_debiti_tributari_lungo") == D("2000.00")
            for y in (2029, 2030):
                assert _scarto_di_flusso(lette, y) == D("0.00"), (y, _scarto_di_flusso(lette, y))
    finally:
        engine.dispose()


def test_ruling62_buco_vero_lato_lungo_sotto_si_rifiuta(monkeypatch):
    """Sonda H: override `sp16e` 2028 = 0 E `sp17e_growth_pct = −60`: il totale
    lasciato (800) è sotto il rateizzato aperto (2000). Lo ferma il kernel (a),
    e il messaggio nomina l'anno manuale (2028) e quello che riparte (2029).
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            res, _cid, sid, _rows = _esito(db, "r62-buco", _righe_trans(
                {2028}, overrides={2028: {"sp16e_debiti_tributari_breve": 0}},
                growth=0, g17=-60, anni=ANNI_4, piano=PIANO_SONDA))
            assert res["forecast_generated"] is False, res["message"]
            assert "non può ripartire" in res["message"], res["message"]
            assert "2028" in res["message"] and "2029" in res["message"], res["message"]
            assert read_forecast_maps(db, sid) == []
    finally:
        engine.dispose()


# ══ m-A (giro 3): articoli, importi e registro nei messaggi di rifiuto ══

def test_ma_articoli_corretti_nei_messaggi(monkeypatch):
    """«i altri debiti» e «dei altri debiti» (misura della revisione): le forme
    con articolo vanno nel dizionario, non fissate nei message f-string.

    Afferma le due forme corrette (`gli altri debiti` al nominale nel rifiuto
    I1-bis/I-d, `degli altri debiti` al genitivo nel rifiuto I-c) e che la
    forma mozza non ricompaia mai.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    import re
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            res, _c, _s, _r = _esito(db, "ma-oltre", _righe_base(
                piano=PIANO_ALTRI_CENT,
                overrides={2027: {"sp17g_altri_debiti_lungo": 250.25}}))
            assert res["forecast_generated"] is False, res["message"]
            assert "gli altri debiti hanno un piano" in res["message"], res["message"]
            # «gl[i altri debiti]» contiene la stringa mozza: il guard-behind
            # distingue «i altri» isolato da «i altri» dentro «gli altri».
            assert not re.search(r"(?<![A-Za-z])i altri debiti", res["message"]), res["message"]
        with sessions() as db:
            res2, _c2, _s2, _r2 = _esito(db, "ma-breve", _righe_base(
                piano=PIANO_ALTRI_CENT,
                overrides={2027: {"sp16g_altri_debiti_breve": D("0")}}))
            assert res2["forecast_generated"] is False, res2["message"]
            assert "il piano di scadenziamento degli altri debiti" in res2["message"], res2["message"]
            assert "dei altri debiti" not in res2["message"], res2["message"]
    finally:
        engine.dispose()


def test_ma_importi_in_formato_italiano(monkeypatch):
    """«deve pagare 1333.335» (misura della revisione): gli importi dei rifiuti
    escono al centesimo in formato italiano, `1.333,33`, non grezzi col punto.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            res, _c, _s, _r = _esito(db, "ma-importi", _righe_base(
                piano=PIANO_TRIB_CENT,
                overrides={2027: {"sp16e_debiti_tributari_breve": D("500.25")}}))
            assert res["forecast_generated"] is False, res["message"]
            assert "vale 500,25" in res["message"], res["message"]
            assert "deve pagare 1.333,33" in res["message"], res["message"]
            assert "1333.33" not in res["message"] and "500.25" not in res["message"], res["message"]
    finally:
        engine.dispose()


# ══ m-1 (giro 4): il rifiuto del kernel N-I1 vuole un piano tributario ══

def _righe_senza_piano(anno_manuale, growth=-150, anni=ANNI_3):
    """Anni automatici con UN solo anno in via manuale e NESSUN `pregresso`.

    E' il caso D della sonda `sonda_p1.py`: senza piano il rateizzato aperto
    vale 0, quindi il kernel non ha nulla da ripartire. Il buco che N-I1
    chiude e' quello di UN CALENDARIO che riparte da sotto le rate ancora
    aperte: senza calendario quel buco non esiste, e il `max` di riga clampa a
    zero come prima del lotto.
    """
    rows = []
    for y in anni:
        r = {"forecast_year": y, "revenue_growth_pct": 3.33}
        if y == anno_manuale:
            r["sp16e_growth_pct"] = growth
        rows.append(r)
    return rows


def test_m1_senza_piano_l_anno_manuale_sotto_zero_non_si_rifiuta(monkeypatch):
    """Nessun piano, 2027 manuale a −150%, 2028-2029 automatici: SI GENERA.

    Su `2b643ef` il kernel rifiutava nominando un «passo Imposte» che
    l'utente non ha mai compilato, e dicendo «0,00 da rateizzare»: un criterio
    del lotto (senza piano un saldo si comporta come prima) trasformato in
    regressione silenziosa dall'API diretta, perche' li' lo schema non pone il
    limite −100 che il wizard mette (`budget-field-rules.ts`).

    Non afferma IL valore negativo residuo in `sp16e`: quello e' un nodo di
    prodotto (issue agenda, m-1 punto 3), non di questo test.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            res, cid, sid, rows = _esito(db, "m1-no-plan", _righe_senza_piano(2027))
            assert res["forecast_generated"] is True, res["message"]
            assert "non può ripartire" not in res.get("message", ""), res["message"]
            assert len(read_forecast_maps(db, sid)) == len(rows)
    finally:
        engine.dispose()
