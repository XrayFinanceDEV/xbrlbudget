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

    # (Ruling 57c) Un campo forzato da SP Prev. non si confronta piu' riga per
    # riga con le scomposizioni dei `details`: l'asserzione diventa
    # «persistito == override», e vince lei (precedente: il writeoff con
    # `ce09d_override`). Le righe di `details` che lo descrivevano restano
    # quelle che il motore ha riallineato al persistito (I1): il confronto
    # diretto con l'override e' quello che le tiene oneste.
    sp_ov = row.get("sp_overrides") or {}

    def confronta(campo, atteso, chi):
        letto = bs.get(campo) if campo.startswith("sp") else ce.get(campo)
        if _q(letto or 0) != _q(atteso):
            fuori.append((campo, f"{campo}: persistito {letto}, dichiarato {_q(atteso)} da {chi}"))

    for campo, val in sp_ov.items():
        if val is not None and campo in bs:
            confronta(campo, D(str(val)), "sp_overrides")

    def forzato(campo):
        return sp_ov.get(campo) is not None

    # ── casi 3 e 5: i quattro debiti, con o senza piano ──
    for saldo, (breve, oltre) in SHORT_LONG.items():
        if not forzato(breve):
            d = det["pregresso"][saldo]
            confronta(breve, D(str(d["generated"])) + D(str(d["residual_short"])),
                      f"details['pregresso']['{saldo}']")
            # Senza piano il lato oltre segue la propria percentuale e i `details`
            # non lo descrivono: dichiarare un confronto li' sarebbe inventarlo.
            if d["mode"] == "runoff" and not forzato(oltre):
                confronta(oltre, d["residual_long"], f"details['pregresso']['{saldo}'].residual_long")

    # ── la posizione tributaria scrive anche il CREDITO ──
    imposte = det["imposte"]
    if imposte["mode"] == "saldo_acconto" and not forzato("sp06e_crediti_tributari_breve"):
        confronta("sp06e_crediti_tributari_breve",
                  D(str(imposte["generated_credit"])) + D(str(imposte["opening_credit_left"])),
                  "details['imposte']")
    if imposte["mode"] == "saldo_acconto" and not forzato("sp16e_debiti_tributari_breve"):
        # I1: la posizione tributaria e' dichiarata in DUE sedi (`imposte` e la
        # riga `debiti_tributari` di `pregresso`). Il confronto con la riga
        # persistita lo fa gia' il ciclo qui sopra con `generated +
        # residual_short` (e con il rateizzato del piano non sarebbe corretto
        # ripeterlo qui: `generated_debt` e' solo la quota di saldo); cio' che
        # nessun altro confronto garantisce e' che le due sedi dicano LO STESSO
        # numero anche sotto un override (Ruling 57a: «dichiarato = persistito
        # vale per ogni chiave»).
        d_tax = det["pregresso"]["debiti_tributari"]
        if _q(D(str(imposte["generated_debt"]))) != _q(D(str(d_tax["generated"]))):
            fuori.append(("sp16e due sedi", f"details['imposte'] dice {imposte['generated_debt']}, "
                                            f"details['pregresso']['debiti_tributari'] dice "
                                            f"{d_tax['generated']}"))

    # ── caso 4: le voci indicizzate ──
    for code, voce in det["indicizzazione"].items():
        if not forzato(SP_INDEXABLE_FIELDS[code]):
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

    # ── lo scoperto di c/c (Task 12) e la quota a breve dei prestiti nuovi (Task 17) ──
    # Le otto chiavi si dichiarano sempre: a valle una chiave assente vale zero.
    for chiave in ("cassa_assorbita", "scoperto_generato", "scoperto_residuo", "oneri_scoperto",
                   "fabbisogno_picco", "fabbisogno_picco_anno", "cassa_sotto_minimo",
                   "prestiti_nuovi_quota_breve"):
        if chiave not in det:
            fuori.append((chiave, f"{chiave}: chiave non dichiarata"))
    cassa = bs["sp09_disponibilita_liquide"]
    residuo = D(str(det.get("scoperto_residuo") or 0))
    if cassa < 0:
        fuori.append(("sp09 negativa", f"cassa persistita {cassa}"))
    # I2: cassa libera e scoperto non convivono, neppure dopo un `sp_overrides`.
    if cassa > 0 and residuo > 0:
        fuori.append(("I2 cassa e scoperto", f"cassa {cassa} e scoperto {residuo} nello stesso anno"))
    # La quota a breve dei prestiti nuovi sta DENTRO la quota bancaria persistita di
    # `sp16a` (Task 17): dichiararne di piu' vorrebbe dire che l'anno dopo la si toglie
    # da un breve che non la contiene e la si rimette nel lungo — debito dal nulla.
    quota = D(str(det.get("prestiti_nuovi_quota_breve") or 0))
    if not D("0") <= quota <= bs["sp16a_debiti_banche_breve"] - residuo:
        fuori.append(("quota breve fuori da sp16a",
                      f"quota a breve {quota}, quota bancaria di sp16a {bs['sp16a_debiti_banche_breve'] - residuo}"))
    if bs["_total_assets"] != bs["_total_liabilities"]:
        fuori.append(("quadratura", f"attivo {bs['_total_assets']} != passivo {bs['_total_liabilities']}"))

    # Il residuo di quadratura non si posa MAI su un campo la cui dichiarazione
    # comanda il MOTORE. E' la stessa affermazione dei confronti qui sopra,
    # presa dall'altro capo: quelli guardano l'esito, questo guarda l'atto.
    # Ma "dichiarato" non vuol dire "elencato nei `details`": una riga in modo
    # legacy HA un `generated` che realign_ scrive eguale al persistito, quindi
    # un centesimo posato li' sopravvive dichiarato anche l'anno dopo (ed e' il
    # comportamento pre-lotto: il secchio libero lo riceveva). Inviolabili sono
    # le righe la cui memoria sta ALTROVE dal bilancio: il calendario del piano
    # (modo runoff), l'indicizzazione (che riporta alla BASE, non al prev), la
    # ripartizione bancaria, e cio' che un override dell'utente ha fissato.
    dichiarati = (
        {campo for saldo, coppia in SHORT_LONG.items()
         if det["pregresso"][saldo]["mode"] == "runoff" for campo in coppia}
        | {SP_INDEXABLE_FIELDS[code] for code in det["indicizzazione"]}
        # Task 16, giro di correzione 1 (rilievo 4): entrambi i lati della
        # ripartizione pregresso/prestito nuovo, non solo il breve.
        | {"sp16a_debiti_banche_breve", "sp17a_debiti_banche_lungo"}
        # Il secchio forzato da un piano/indice e' inviolabile anche se la sua
        # riga e' legacy: dove la batteria arriva, un centesimo su una riga che
        # l'utente ha forzato dalla schermata SP Prev. cancellere' l'override.
        | {c for c, v in sp_ov.items() if v is not None}
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

# I1-bis: quale riga a OLTRE ciascun saldo di piano governa (la stessa tabella
# del motore, `ForecastEngine._LATO_OLTRE_GOVERNATO_DA_PIANO`, qui duplicata
# deliberatamente: se le due copie divergono, un test rosso lo dice).
LATO_OLTRE_DEL_PIANO = {
    "debiti_fornitori": "sp17d_debiti_fornitori_lungo",
    "debiti_tributari": "sp17e_debiti_tributari_lungo",
    "debiti_previdenziali": "sp17f_debiti_previdenza_lungo",
    "altri_debiti": "sp17g_altri_debiti_lungo",
    "crediti_commerciali": "sp07_crediti_lungo",
}

# `sp_overrides` della famiglia I1: campi dichiarati dalla rete, parte breve.
SP_FAMIGLIA_BREVE = {
    "sp06e_crediti_tributari_breve": 5000.50,
    "sp16a_debiti_banche_breve": 25000.11,
    "sp16d_debiti_fornitori_breve": 80000.37,
    "sp16e_debiti_tributari_breve": 10000.71,
    "sp16f_debiti_previdenza_breve": 15000.13,
    "sp16g_altri_debiti_breve": 35000.19,
}
# La parte a oltre che un SENZA piano lascia libera, e che invece il motore
# deve rifiutare dove il piano e' attivo (Ruling 57b).
SP_FAMIGLIA_OLTRE = {
    "sp17d_debiti_fornitori_lungo": 20000.37,
    "sp17e_debiti_tributari_lungo": 7000.01,
    "sp17f_debiti_previdenza_lungo": 10000.71,
    "sp17g_altri_debiti_lungo": 20000.13,
}
SP_FAMIGLIA = {**SP_FAMIGLIA_BREVE, **SP_FAMIGLIA_OLTRE}


OVERRIDE = {
    "nessuno": {},
    "dentro ce08 e ce09": {"ce09c_override": 1234.56, "ce08d_override": 3333.33,
                           "ce08a_override": 777.77},
    # `ce09d` sopprime l'inesigibile del piano: l'override vince due volte.
    "anche ce09d": {"ce09d_override": 4321.99, "ce08d_override": 1111.11},
    # La famiglia di `sp_overrides` sui campi dichiarati (I1 della revisione
    # finale): finche' la batteria aveva SOLO override di CE, la rete non
    # poteva vedere che la posizione tributaria dichiarata divergeva dal
    # persistito sotto un override di cella. Gli importi stanno vicino alle
    # masse della base: mai sotto il naturale, perche' una voce di debito
    # forzata al ribasso sottrae cassa al plug e potrebbe alzare un fabbisogno
    # che non e' c'e' — la batteria deve generare, non collidere.
    # Il LATO OLTRE con un piano attivo, invece, collide per progetto (I1-bis):
    # quegli scenari si assertiscono sul RIFIUTO, vedi `_rifiuto_atteso`.
    "SP sui campi dichiarati": {"sp_overrides": SP_FAMIGLIA},
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


def _rifiuto_atteso(piano):
    """Il campo oltre che il motore deve rifiutare per questo piano, o None.

    Stesso ordine di scansione del motore (`_LATO_OLTRE_GOVERNATO_DA_PIANO`).
    """
    if not piano:
        return None
    for saldo, campo in LATO_OLTRE_DEL_PIANO.items():
        if piano.get(saldo) and SP_FAMIGLIA.get(campo) is not None:
            return campo
    return None


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
    fuori, scenari, anni, rifiutati = [], 0, 0, 0
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
                rifiutato = _rifiuto_atteso(piano) if "sp_overrides" in ov else None
                res = budget_scenarios.bulk_upsert_assumptions(
                    company_id, sc.id, request={"assumptions": rows, "auto_generate": True},
                    user_id=user, db=db)
                if rifiutato:
                    # I1-bis: con un piano attivo sul saldo, l'override sul suo
                    # lato oltre deve essere RIFIUTATO, non salvato per essere
                    # cancellato l'anno dopo. Il rifiuto si legge dal
                    # `forecast_generated`, non dall'HTTP 200 (CLAUDE.md).
                    rifiutati += 1
                    assert res["forecast_generated"] is False, \
                        f"[{nome_p} | {nome_i} | {nome_o}] {rifiutato} doveva essere rifiutato"
                    assert "non e' ammesso" in res["message"] and rifiutato in res["message"], \
                        f"[{nome_p} | {nome_i} | {nome_o}] messaggio sbagliato: {res['message']}"
                    continue
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
    # 96 scenari: 6 piani × 4 indicizzazioni × 4 OVERRIDE (la famiglia SP
    # sui campi dichiarati e' il quarto). I 16 rifiuti sono i 4 piani che
    # governano un lato oltre della famiglia (`altri debiti`,
    # `altri + previdenziali`, `fornitori + tributari`,
    # `tributari + previdenziali + altri`) × le 4 indicizzazioni: il piano
    # `crediti con inesigibile` non collide perche' la famiglia non tocca
    # `sp07` (rifiutato a parte, nel test dedicato), e `senza piano` non ha
    # alcun calendario da contraddire.
    assert scenari == 96 and anni == 240 and rifiutati == 16, \
        f"batteria incompleta: {scenari} scenari, {anni} anni, {rifiutati} rifiuti"
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


# ══ Lo scoperto ACCESO, dove i difetti vivevano (Task 12, giro di correzione 1) ══
#
# La prima stesura del Task 12 fu verificata da una sonda usa-e-getta, e i due
# difetti che la revisione trovo' stavano proprio fuori da quella sonda: i piani
# di rimborso (la rata del debito esistente e quella del nuovo finanziamento
# pagavano lo scoperto invece del proprio debito) e un `sp_overrides` dopo il
# plug (cassa e scoperto insieme, misura gonfiata fino al doppio). Qui entrano
# nella griglia.
#
# L'oracolo di I1 non ricalcola i piani di rimborso — sarebbe un secondo motore
# in un test: e' lo STESSO scenario senza lo stress ne' gli override, il
# «gemello». I debiti bancari non dipendono ne' dagli investimenti ne' dalla
# cassa, quindi quota bancaria di `sp16a` e `sp17a` devono coincidere con quelle
# del gemello, con o senza scoperto.

PRESTITO = {"financing_amount": 100000.37, "financing_duration_years": 4}

DEBITI = {
    "nessun piano": ({}, {}),
    # Rate al mezzo centesimo: (12.345,67 + 23.456,79) / 3 = 11.934,153…
    "rimborso esistente in 3 anni": ({}, {"existing_debt_repayment_years": 3}),
    # 100.000,37 / 4 = 25.000,0925 all'anno.
    "nuovo finanziamento": (PRESTITO, {}),
    # Task 16: pregresso a breve e oltre CON il suo piano, e un prestito nuovo nello
    # stesso scenario. Il piano in 2 anni si estingue nel 2028 e l'orizzonte arriva
    # al 2029: e' l'anno in cui la rata del pregresso, sopravvissuta al pregresso,
    # si mangiava il prestito nuovo. 35.802,46 / 2 = 17.901,23, al centesimo: il
    # mezzo centesimo sta nel prestito, e la somma di I1 esteso resta esatta.
    "rimborso in 2 anni + nuovo finanziamento": (PRESTITO, {"existing_debt_repayment_years": 2}),
}

# ══ I1 esteso (Task 16): il prestito nuovo non tocca il debito bancario pregresso ══
#
# Questa griglia conteneva gia' debito bancario pregresso e un prestito nuovo,
# ma il gemello di I1 AVEVA LO STESSO PRESTITO: lo scenario stressato e il suo
# gemello sbagliavano allo stesso modo, e la rata nuova che azzerava 12.345,67 di
# breve pregresso passava inosservata (Ruling 40). Il confronto giusto e' con lo
# stesso scenario SENZA prestito.
#
# Che cosa resta del prestito nuovo, da solo, persistito anno per anno (misurato:
# lo stesso prestito su un'azienda senza banca). Non dipende ne' dal pregresso ne'
# dalla crescita: e' la catena del kernel al centesimo.
SENZA_NUOVO = {
    "nuovo finanziamento": ("nessun piano", ({}, {})),
    "rimborso in 2 anni + nuovo finanziamento": (
        "rimborso esistente in 2 anni", ({}, {"existing_debt_repayment_years": 2})),
}
RESIDUO_PRESTITO = {2027: D("75000.28"), 2028: D("50000.19"), 2029: D("25000.10")}
# ══ Task 17: la parte di quel residuo che scade l'anno dopo sta a breve ══
#
# Rifatta a mano sulla catena, non sulla rata arrotondata: 75.000,28 → 50.000,19
# (75.000,28 − 25.000,0925 = 50.000,1875) toglie 25.000,09; 50.000,19 → 25.000,10
# (25.000,0975) toglie 25.000,09; 25.000,10 → 0,01 (0,0075) toglie 25.000,09. Il
# 2029 e' l'ultimo anno di orizzonte e la rata del 2030 conta lo stesso: il
# calendario del contratto non sa dove finisce il piano.
QUOTA_BREVE_PRESTITO = {2027: D("25000.09"), 2028: D("25000.09"), 2029: D("25000.09")}

SQUILIBRI = {
    "nessuno": None,
    # Il rilievo 1: un'attivita' forzata DOPO il plug, nel primo anno stressato.
    "crediti giu' nel 2027": (0, {"sp06a_crediti_clienti_breve": 1000.55}),
    "rimanenze su nel 2028": (1, {"sp05a_materie_prime": 91234.565}),
}

TASSO = 6.135
STRESS_2027 = 180123.455


def _base_year_con_banca(db, user):
    """La base della rete piu' debito bancario pregresso non tondo, a breve e oltre."""
    company_id = _base_year(db, user)
    fy = db.query(FinancialYear).filter(FinancialYear.company_id == company_id).one()
    b = db.query(BalanceSheet).filter(BalanceSheet.financial_year_id == fy.id).one()
    breve, lungo = D("12345.67"), D("23456.79")
    b.sp16a_debiti_banche_breve = breve
    b.sp16_debiti_breve += breve
    b.sp17a_debiti_banche_lungo = lungo
    b.sp17_debiti_lungo += lungo
    b.sp09_disponibilita_liquide += breve + lungo
    db.commit()
    return company_id


def _genera_e_leggi(db, user, rows):
    company_id = _base_year_con_banca(db, user)
    sc = budget_scenarios.create_budget_scenario(
        company_id,
        BudgetScenarioCreate(company_id=company_id, name="scoperto", base_year=2026, scenario_type="budget"),
        user_id=user, db=db)
    res = budget_scenarios.bulk_upsert_assumptions(
        company_id, sc.id, request={"assumptions": rows, "auto_generate": True}, user_id=user, db=db)
    if not res["forecast_generated"]:
        return res, None, None
    prev = budget_scenarios.preview_forecast_route(company_id, sc.id, request={"assumptions": rows},
                                                   user_id=user, db=db)
    return res, read_forecast_maps(db, sc.id), prev["forecast_years"]


@pytest.mark.parametrize("crescita", CRESCITE)
def test_lo_scoperto_acceso_resta_separato_dai_debiti_e_dichiarato_come_persistito(crescita, monkeypatch):
    """72 scenari per percentuale, 216 anni, piu' 30 gemelli: zero divergenze.

    Afferma, anno per anno: le famiglie di `_divergenze` (con I2 e cassa mai
    negativa); I1 (quota bancaria di `sp16a` e `sp17a` = gemello); I1 esteso
    (Task 16 e 17: sul gemello con prestito nuovo, quota bancaria di `sp16a` =
    gemello SENZA prestito + la rata dell'anno dopo, dichiarata identica nei
    `details`; `sp17a` = quel gemello + il residuo del prestito − quella rata);
    I4 (`scoperto_generato` = aumento del residuo, `oneri_scoperto` = residuo di
    apertura × tasso e addebitato in `ce15`, picco = massimo dei residui).
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    fuori, scenari, anni = [], 0, 0
    esercitati = Counter()

    def righe(piano, primo, tutti, squilibrio, stress):
        rows = [dict(forecast_year=y, revenue_growth_pct=crescita, **INVESTIMENTI_SOTTO_CENTESIMO,
                     overdraft_allowed=True, financing_interest_rate=TASSO, **tutti) for y in ANNI]
        rows[0].update(primo)
        if piano:
            rows[0]["pregresso"] = piano
        if stress:
            rows[0]["tangible_investments"] = STRESS_2027
            if squilibrio:
                rows[squilibrio[0]]["sp_overrides"] = squilibrio[1]
        return rows

    try:
        with sessions() as db:
            gemelli = {}

            def gemello(nome_p, piano, nome_d, primo, tutti):
                """Lo scenario senza stress ne' override, generato una volta per chiave."""
                chiave = (nome_p, nome_d)
                if chiave not in gemelli:
                    res_g, mappe_g, anni_g = _genera_e_leggi(
                        db, f"gemello-{crescita}-{nome_p}-{nome_d}", righe(piano, primo, tutti, None, False))
                    if mappe_g is None:
                        fuori.append(("non generato", f"[gemello {nome_p} | {nome_d}] {res_g['message']}"))
                        return None
                    gemelli[chiave] = {y: (bs, ce, a["details"]) for (y, bs, ce), a in zip(mappe_g, anni_g)}
                return gemelli[chiave]

            for (nome_p, piano), (nome_d, (primo, tutti)), (nome_s, squilibrio) in itertools.product(
                PIANI.items(), DEBITI.items(), SQUILIBRI.items()
            ):
                scenari += 1
                tag = f"{nome_p} | {nome_d} | {nome_s}"

                gem = gemello(nome_p, piano, nome_d, primo, tutti)
                if gem is None:
                    continue

                # I1 esteso, una volta per gemello: il prestito nuovo non muove la
                # quota bancaria pregressa di `sp16a`, e in `sp17a` si somma e basta.
                # Sul gemello e non sullo scenario stressato: lo stressato e' gia'
                # legato al suo gemello da I1 qui sotto, quindi lo e' anche a questo.
                if nome_d in SENZA_NUOVO and nome_s == next(iter(SQUILIBRI)):
                    nome_senza, (primo_s, tutti_s) = SENZA_NUOVO[nome_d]
                    senza = gemello(nome_p, piano, nome_senza, primo_s, tutti_s)
                    for anno in (ANNI if senza is not None else ()):
                        bs_c, _ce_c, det_c = gem[anno]
                        bs_s, _ce_s, det_s = senza[anno]
                        dove_g = f"[{nome_p} | {nome_d} | gemello | {anno}]"
                        esercitati["anni I1 esteso"] += 1
                        banca_c = bs_c["sp16a_debiti_banche_breve"] - D(str(det_c["scoperto_residuo"]))
                        banca_s = bs_s["sp16a_debiti_banche_breve"] - D(str(det_s["scoperto_residuo"]))
                        quota = QUOTA_BREVE_PRESTITO[anno]
                        # Task 17: la quota bancaria col prestito e' quella senza piu' la
                        # rata dell'anno dopo. Una differenza diversa vuol dire che la
                        # rata nuova ha pagato il pregresso, o che la quota a breve non e'
                        # stata riclassificata.
                        if banca_c - banca_s != quota:
                            fuori.append(("I1 esteso sp16a", f"{dove_g} quota bancaria {banca_c} col prestito, "
                                                             f"{banca_s} senza: differenza {banca_c - banca_s}, "
                                                             f"quota a breve del calendario {quota}"))
                        # Dichiarato = persistito: la chiave dice la stessa quota.
                        dichiarata = D(str(det_c.get("prestiti_nuovi_quota_breve") or 0))
                        if dichiarata != quota:
                            fuori.append(("quota breve dichiarata", f"{dove_g} dichiarata {dichiarata}, "
                                                                    f"calendario {quota}"))
                        atteso = bs_s["sp17a_debiti_banche_lungo"] + RESIDUO_PRESTITO[anno] - quota
                        if bs_c["sp17a_debiti_banche_lungo"] != atteso:
                            fuori.append(("I1 esteso sp17a", f"{dove_g} sp17a {bs_c['sp17a_debiti_banche_lungo']}, "
                                                             f"pregresso {bs_s['sp17a_debiti_banche_lungo']} + "
                                                             f"prestito {RESIDUO_PRESTITO[anno]} - quota a breve "
                                                             f"{quota} = {atteso}"))

                rows = righe(piano, primo, tutti, squilibrio, True)
                res, mappe, anni_prev = _genera_e_leggi(db, f"scoperto-{crescita}-{scenari}", rows)
                if mappe is None:
                    fuori.append(("non generato", f"[{tag}] {res['message']}"))
                    continue
                esercitati[nome_d] += 1
                residui = [D(str(a["details"]["scoperto_residuo"])) for a in anni_prev]
                picco = max(residui)
                residuo_prec = D("0")
                for (anno, bs, ce), prev_anno, row in zip(mappe, anni_prev, rows):
                    anni += 1
                    det = prev_anno["details"]
                    dove = f"[{tag} | {anno}]"
                    for campo, guasto in _divergenze(bs, ce, det, row):
                        fuori.append((campo, f"{dove} {guasto}"))
                    residuo = D(str(det["scoperto_residuo"]))
                    esercitati["anni con scoperto"] += residuo > 0
                    esercitati["anni che rimborsano"] += residuo < residuo_prec
                    bs_g, ce_g, det_g = gem[anno]
                    residuo_g = D(str(det_g["scoperto_residuo"]))
                    # I1: i piani di rimborso pagano il proprio debito, mai lo scoperto.
                    if bs["sp17a_debiti_banche_lungo"] != bs_g["sp17a_debiti_banche_lungo"]:
                        fuori.append(("I1 sp17a", f"{dove} sp17a {bs['sp17a_debiti_banche_lungo']}, "
                                                  f"il piano dice {bs_g['sp17a_debiti_banche_lungo']}"))
                    banca = bs["sp16a_debiti_banche_breve"] - residuo
                    banca_g = bs_g["sp16a_debiti_banche_breve"] - residuo_g
                    if banca != banca_g:
                        fuori.append(("I1 sp16a banca", f"{dove} quota bancaria {banca}, il piano dice {banca_g}"))
                    # I4: dichiarato = persistito.
                    generato = D(str(det["scoperto_generato"]))
                    if generato != max(D("0"), residuo - residuo_prec):
                        fuori.append(("I4 generato", f"{dove} generato {generato}, residuo {residuo_prec} -> {residuo}"))
                    oneri = D(str(det["oneri_scoperto"]))
                    if oneri != _q(residuo_prec * D(str(TASSO)) / D("100")):
                        fuori.append(("I4 oneri", f"{dove} oneri {oneri} sul residuo d'apertura {residuo_prec}"))
                    if ce["ce15_oneri_finanziari"] - oneri != ce_g["ce15_oneri_finanziari"] - D(str(det_g["oneri_scoperto"])):
                        fuori.append(("I4 ce15", f"{dove} ce15 {ce['ce15_oneri_finanziari']} con oneri {oneri}"))
                    if D(str(det["fabbisogno_picco"])) != picco:
                        fuori.append(("I4 picco", f"{dove} picco {det['fabbisogno_picco']}, massimo dei residui {picco}"))
                    anno_picco = ANNI[residui.index(picco)] if picco > 0 else None
                    if det["fabbisogno_picco_anno"] != anno_picco:
                        fuori.append(("I4 picco anno", f"{dove} anno {det['fabbisogno_picco_anno']} invece di {anno_picco}"))
                    residuo_prec = residuo
    finally:
        engine.dispose()
    per_campo = Counter(campo for campo, _ in fuori)
    assert not fuori, "\n".join(
        [f"{len(fuori)} divergenze su {anni} anni ({scenari} scenari)", "per campo:"]
        + [f"  {v:4d}  {k}" for k, v in per_campo.most_common()]
        + ["esempi:"] + [testo for _, testo in fuori[:15]]
    )
    assert scenari == 72 and anni == 216, f"batteria incompleta: {scenari} scenari, {anni} anni"
    # Una griglia che non accende scoperto, o non lo rimborsa, non prova I1 ne' I2.
    assert esercitati["anni con scoperto"] > 0 and esercitati["anni che rimborsano"] > 0, dict(esercitati)
    assert all(esercitati[nome] == 18 for nome in DEBITI), dict(esercitati)
    # 6 piani × 2 voci con prestito nuovo × 3 anni: I1 esteso non e' stato saltato.
    assert esercitati["anni I1 esteso"] == 36, dict(esercitati)
