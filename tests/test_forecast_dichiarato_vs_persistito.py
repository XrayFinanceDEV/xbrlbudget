"""L'invariante: nessun numero persistito diverge da quello dichiarato.

**Perche' questo file esiste.** Il residuo di quadratura che riscrive una riga
gia' dichiarata e' stato trovato **cinque volte** in `forecast_engine.py`:

| # | Dove | Chiuso da |
|---|---|---|
| 1 | conto economico, righe con `*_override` (Task 11) | `_forced_ce_residual_fields` |
| 2 | `ce09d`, l'inesigibile scadenziato (Task 5) | `_engine_forced_ce_fields` |
| 3 | `sp16g`/`sp17g` scritti da un piano (Task 5 round 2) | `_pregresso_sp_forced_fields` |
| 4 | le voci indicizzate a un driver (Task 15) | `_indexed_sp_forced_fields` |
| 5 | `sp16e`/`sp16f`, il ripiego quando il secchio e' forzato (Task 15 round 1) | `_declared_sp_fields` |

Ogni volta da chi lo **cercava** con una sonda usa-e-getta, mai da chi leggeva; e
ogni sonda e' stata buttata dopo l'uso, cosi' la volta dopo si ripartiva da zero.
Tappare l'ennesimo caso significa garantirsi il successivo: questo file e' la
sonda che resta.

**Che cosa afferma.** Su ogni anno di ogni scenario della batteria, per ogni
numero che il motore **dichiara** — nei `details` o accettando un override —
il valore persistito e' quel numero arrotondato al centesimo. Non «vicino»: la
quantizzazione del motore e' `ROUND_HALF_UP`, quindi la coincidenza e' esatta e
un solo centesimo di scarto e' un difetto.

**Che cosa NON copre, e perche'.** `sp06`/`sp07` sono AGGREGATI che il piano dei
crediti commerciali scrive per intero e che `_alloc` ripartisce sulle proporzioni
dell'anno base: la loro somma di dettagli quantizzati non e' l'aggregato
quantizzato, e nessun `details` dichiara i singoli sotto-campi. E' la stessa
ragione per cui `_pregresso_sp_forced_fields` lascia fuori `crediti_commerciali`.

**Se questo test diventa rosso** il difetto e' quasi sempre nel motore, non qui:
qualcuno ha dichiarato un numero e ne ha persistito un altro. Allargare l'elenco
delle esenzioni per farlo tornare verde e' il modo di riaprire il caso numero sei.
"""
import itertools
from collections import Counter
from decimal import ROUND_HALF_UP, Decimal as D

import pytest

from backend.app.api.v1 import budget_scenarios
from backend.app.schemas.budget import BudgetScenarioCreate
from calculations.forecast_engine import SP_INDEXABLE_FIELDS
from database.models import BalanceSheet, FinancialYear
from tests.e2e_kit import memory_sessions, read_forecast_maps, seed_base_year

USER = "invariante"

# I quattro debiti che `details['pregresso']` descrive riga per riga. I crediti
# commerciali non ci sono: vedi il docstring del modulo.
SHORT_LONG = {
    "debiti_fornitori": ("sp16d_debiti_fornitori_breve", "sp17d_debiti_fornitori_lungo"),
    "debiti_tributari": ("sp16e_debiti_tributari_breve", "sp17e_debiti_tributari_lungo"),
    "debiti_previdenziali": ("sp16f_debiti_previdenza_breve", "sp17f_debiti_previdenza_lungo"),
    "altri_debiti": ("sp16g_altri_debiti_breve", "sp17g_altri_debiti_lungo"),
}

# Gli override di CE che cadono DENTRO un gruppo con un secchio di residuo
# (`ce08`, `ce09`): sono esattamente quelli del caso 1.
CE_OVERRIDES = {
    "ce09c_override": "ce09c_svalutazioni",
    "ce09d_override": "ce09d_svalutazione_crediti",
    "ce08d_override": "ce08d_altri_costi_personale",
    "ce08a_override": "ce08a_tfr_accrual",
}


def _q(x):
    """Al centesimo con la stessa regola del motore (`_quantize_values`)."""
    return D(str(x)).quantize(D("0.01"), rounding=ROUND_HALF_UP)


def _divergenze(bs, ce, det, row):
    """Ogni numero dichiarato che il persistito non conferma.

    Restituisce coppie `(campo, spiegazione)`: il campo separato serve a
    raggruppare il fallimento per FAMIGLIA invece che per ordine di scenario
    (vedi il messaggio in coda al test).
    """
    fuori = []

    def confronta(campo, atteso, chi):
        letto = bs.get(campo) if campo.startswith("sp") else ce.get(campo)
        if _q(letto or 0) != _q(atteso):
            fuori.append((campo, f"{campo}: persistito {letto}, dichiarato {_q(atteso)} da {chi}"))

    # ── casi 3 e 5: i quattro debiti, con o senza piano ──
    for saldo, (breve, oltre) in SHORT_LONG.items():
        d = det["pregresso"][saldo]
        confronta(breve, D(str(d["generated"])) + D(str(d["residual_short"])),
                  f"details['pregresso']['{saldo}']")
        # Senza piano il lato oltre segue la propria percentuale e i `details`
        # non lo descrivono: dichiarare un confronto li' sarebbe inventarlo.
        if d["mode"] == "runoff":
            confronta(oltre, d["residual_long"], f"details['pregresso']['{saldo}'].residual_long")

    # ── la posizione tributaria scrive anche il CREDITO ──
    imposte = det["imposte"]
    if imposte["mode"] == "saldo_acconto":
        confronta("sp06e_crediti_tributari_breve",
                  D(str(imposte["generated_credit"])) + D(str(imposte["opening_credit_left"])),
                  "details['imposte']")

    # ── caso 4: le voci indicizzate ──
    for code, voce in det["indicizzazione"].items():
        confronta(SP_INDEXABLE_FIELDS[code], voce["valore"], f"details['indicizzazione']['{code}']")

    # ── caso 1: un override vince, e vince fino in fondo ──
    for attr, riga in CE_OVERRIDES.items():
        if row.get(attr) is not None:
            confronta(riga, row[attr], attr)

    # ── caso 2: l'inesigibile scadenziato finisce in `ce09d` per intero ──
    # Solo quando c'e' davvero un inesigibile: senza, `ce09d` e' il dettaglio di
    # CHIUSURA del gruppo `ce09` e prendersi il residuo e' il suo mestiere, non un
    # difetto (`_engine_forced_ce_fields` lo forza con la stessa condizione).
    # Preteserlo comunque e' un'asserzione sbagliata, non una rete piu' fitta: la
    # prima stesura lo faceva e dichiarava 112 divergenze inesistenti.
    # E con un override della riga (o del suo aggregato) l'inesigibile e'
    # soppresso e vince l'override, che il ciclo qui sopra ha gia' confrontato.
    writeoff = D(str(det["pregresso"]["crediti_commerciali"]["writeoff"]))
    if writeoff > 0 and row.get("ce09d_override") is None and row.get("ce09_override") is None:
        confronta("ce09d_svalutazione_crediti", writeoff,
                  "details['pregresso']['crediti_commerciali'].writeoff")

    # Il residuo di quadratura non si posa MAI su un campo dichiarato. E' la
    # stessa affermazione dei confronti qui sopra, presa dall'altro capo: quelli
    # guardano l'esito, questo guarda l'atto — e un residuo posato su un campo
    # dichiarato e' un difetto anche nell'anno fortunato in cui vale zero.
    dichiarati = (
        {campo for coppia in SHORT_LONG.values() for campo in coppia}
        | {SP_INDEXABLE_FIELDS[code] for code in det["indicizzazione"]}
    )
    for posa in det["residuo_quadratura"]:
        if posa["campo"] in dichiarati:
            fuori.append((posa["campo"],
                          f"residuo di {posa['importo']} posato su {posa['campo']}, che e' dichiarato"))
    return fuori


def _base_year(db, user):
    """Un anno base con massa su OGNI voce che la batteria mette alla prova.

    Il fixture del kit tiene tutto il passivo su `sp16d`/`sp17a` e lascia a zero
    le voci minori: un fattore che moltiplica zero, e un residuo che si posa su
    una riga vuota, passerebbero qualunque asserzione.
    """
    company_id, _ = seed_base_year(db, user_id=user)
    fy = db.query(FinancialYear).filter(FinancialYear.company_id == company_id).one()
    b = db.query(BalanceSheet).filter(BalanceSheet.financial_year_id == fy.id).one()
    b.sp16_debiti_breve = D("145000.00")
    # `sp16b` non e' un riempitivo: dopo che i quattro debiti dichiarati sono
    # tutti forzati, e' li' (o su `sp16c`) che il residuo di quadratura si posa.
    # A zero non si vedrebbe la differenza fra «posato» e «non posato».
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
    # Attivo 40+140+50+120+31+3+20+4+5 = 413 · Passivo 100+60+20+30+145+50+6+2 = 413
    b.sp09_disponibilita_liquide = D("31000.00")
    db.commit()
    return company_id


# Le masse dei piani sono quelle del bilancio base qui sopra: `validate_pregresso`
# impone che coincidano, e un piano che non le rispetta non arriva al motore.
#
# **Le rate sono TERZI, non numeri tondi, e non e' un vezzo.** Il residuo di
# quadratura nasce per definizione dall'arrotondamento: una batteria fatta di
# 100.000 e 40.000 non lo produce mai, e una sonda cosi' campionata conclude
# «zero occorrenze» mentre il difetto e' li'. Terzi arrotondati al centesimo non
# bastano: `runoff_schedule` li restituisce esatti, e il residuo resta zero
# (misurato). Servono rate con il MEZZO centesimo, che e' la coda che la
# quantizzazione deve spezzare. E' successo davvero — la sesta
# occorrenza della trappola (residuo su `sp16d` con piu' piani insieme) era
# sfuggita a una sonda giusta ma campionata su rate tonde. Terzi e code decimali
# sono quindi parte della rete quanto le asserzioni.
PIANI = {
    "senza piano": None,
    "altri debiti": {"altri_debiti": {"opening": 55000,
                                      "amounts": [18333.335, 18333.335, 18333.33]}},
    "altri + previdenziali": {
        "altri_debiti": {"opening": 55000, "amounts": [18333.335, 18333.335, 18333.33]},
        "debiti_previdenziali": {"opening": 25000, "amounts": [8333.335, 8333.335, 8333.33]},
    },
    "fornitori + tributari": {
        "debiti_fornitori": {"opening": 100000, "amounts": [33333.335, 33333.335, 33333.33]},
        "debiti_tributari": {"opening": 10000, "saldo": 6000, "rateizzato": 4000,
                             "amounts": [1333.335, 1333.335, 1333.33]},
    },
    # La forma esatta della SESTA occorrenza: `sp16e`, `sp16f` e `sp16g` tutti e
    # tre forzati da un piano, e `sp16d` — il campo che la guardia dei giorni
    # degeneri scrive — lasciato libero, quindi primo bersaglio del cammino a
    # ritroso. E' il caso che una sonda campionata su rate tonde non vede.
    "tributari + previdenziali + altri": {
        "debiti_tributari": {"opening": 10000, "saldo": 6000, "rateizzato": 4000,
                             "amounts": [1333.335, 1333.335, 1333.33]},
        "debiti_previdenziali": {"opening": 25000, "amounts": [8333.335, 8333.335, 8333.33]},
        "altri_debiti": {"opening": 55000, "amounts": [18333.335, 18333.335, 18333.33]},
    },
    # Con inesigibile: e' il piano che fa scrivere `ce09d` al motore (caso 2).
    "crediti con inesigibile": {
        "crediti_commerciali": {"opening": 120000, "amounts": [38333.335, 38333.335, 38333.33],
                                "writeoff": [1666.67, 0, 0]},
    },
}

INDICIZZAZIONE = {
    "nessuna": None,
    "solo g": {"sp16g": "ricavi", "sp17g": "ricavi"},
    # Due righe dello stesso gruppo: e' la combinazione che spinge il residuo
    # oltre il secchio e oltre `sp16f`, fino ai tributari (caso 5).
    "f + g": {"sp16f": "ricavi", "sp17f": "ricavi",
              "sp16g": "acquisti", "sp17g": "acquisti"},
    "tutte e undici": {"sp01": "ricavi", "sp04": "ricavi", "sp08": "ricavi",
                       "sp10": "acquisti", "sp14": "personale", "sp16f": "personale",
                       "sp16g": "ricavi", "sp17d": "acquisti", "sp17f": "personale",
                       "sp17g": "ricavi", "sp18": "ricavi"},
}

OVERRIDE = {
    "nessuno": {},
    "dentro ce08 e ce09": {"ce09c_override": 1234.56, "ce08d_override": 3333.33,
                           "ce08a_override": 777.77},
    # `ce09d` sopprime l'inesigibile del piano: l'override vince due volte.
    "anche ce09d": {"ce09d_override": 4321.99, "ce08d_override": 1111.11},
}

# Due investimenti da 0,02 al 20%: due quote da 0,004 che i dettagli arrotondano
# in giu' e l'aggregato in su, cioe' un residuo di +0,01 su `ce09` — la stessa
# costruzione con cui il Task 5 dimostro' il caso 2. Senza, il gruppo `ce09` non
# ha alcun residuo da posare e disattivare `_engine_forced_ce_fields` non produce
# nulla che si possa misurare (verificato: la rete lo lasciava sfuggire).
INVESTIMENTI_SOTTO_CENTESIMO = {
    "intangible_investments": 0.02, "tangible_investments": 0.02,
    "depreciation_rate": 20, "depreciation_rate_intangible": 20,
}

# Percentuali scelte perche' producono frazioni di centesimo su piu' righe: e'
# li' che il residuo di quadratura nasce.
CRESCITE = (1.11, 3.33, 7.77, 0.37)
ANNI = (2027, 2028, 2029)


@pytest.mark.parametrize("crescita", CRESCITE)
def test_nessun_numero_persistito_diverge_da_quello_dichiarato(crescita, monkeypatch):
    """La rete permanente: 72 scenari per percentuale, 216 anni, zero divergenze.

    Parametrizzato sulla crescita per avere quattro esiti distinti invece di uno
    solo: quando si rompe, il messaggio dice su quale percentuale — e un difetto
    che dipende dall'arrotondamento dipende quasi sempre da quella.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    fuori, scenari, anni = [], 0, 0
    try:
        with sessions() as db:
            for (nome_p, piano), (nome_i, idx), (nome_o, ov) in itertools.product(
                PIANI.items(), INDICIZZAZIONE.items(), OVERRIDE.items()
            ):
                scenari += 1
                user = f"{USER}-{crescita}-{scenari}"
                company_id = _base_year(db, user)
                rows = [dict(forecast_year=y, revenue_growth_pct=crescita,
                             **INVESTIMENTI_SOTTO_CENTESIMO, **ov) for y in ANNI]
                if piano:
                    rows[0]["pregresso"] = piano
                if idx:
                    for r in rows:
                        r["sp_indexing"] = idx
                sc = budget_scenarios.create_budget_scenario(
                    company_id,
                    BudgetScenarioCreate(company_id=company_id, name="inv", base_year=2026,
                                         scenario_type="budget"),
                    user_id=user, db=db)
                res = budget_scenarios.bulk_upsert_assumptions(
                    company_id, sc.id, request={"assumptions": rows, "auto_generate": True},
                    user_id=user, db=db)
                # `forecast_generated`, non l'HTTP 200: il bulk risponde 200 anche
                # a un previsionale rifiutato (CLAUDE.md). Uno scenario che non
                # genera non e' un caso in meno da controllare: e' la batteria che
                # ha smesso di provare quello che dice di provare.
                assert res["forecast_generated"] is True, f"{nome_p}/{nome_i}/{nome_o}: {res['message']}"
                prev = budget_scenarios.preview_forecast_route(
                    company_id, sc.id, request={"assumptions": rows}, user_id=user, db=db)
                for (_, bs, ce), anno, row in zip(
                    read_forecast_maps(db, sc.id), prev["forecast_years"], rows
                ):
                    anni += 1
                    for campo, guasto in _divergenze(bs, ce, anno["details"], row):
                        fuori.append((campo, f"[{nome_p} | {nome_i} | {nome_o} | {anno['year']}] {guasto}"))
    finally:
        engine.dispose()
    assert scenari == 72 and anni == 216, f"batteria incompleta: {scenari} scenari, {anni} anni"
    # Il riepilogo PER CAMPO prima degli esempi, e non e' cosmesi: la prima
    # stesura elencava solo i primi 25 casi in ordine di scenario, e cosi'
    # facendo NASCONDEVA che il residuo finiva anche su `sp16d` — cioe' proprio
    # la sesta occorrenza che si stava cercando. Un messaggio troncato per
    # posizione dice quale scenario e' andato per primo, non quale famiglia si e'
    # rotta.
    per_campo = Counter(campo for campo, _ in fuori)
    assert not fuori, "\n".join(
        [f"{len(fuori)} divergenze su {anni} anni", "per campo:"]
        + [f"  {v:4d}  {k}" for k, v in per_campo.most_common()]
        + ["esempi:"] + [testo for _, testo in fuori[:15]]
    )
