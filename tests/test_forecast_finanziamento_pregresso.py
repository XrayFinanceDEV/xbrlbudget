"""La rata del nuovo finanziamento paga il proprio debito, non il debito bancario pregresso.

**Il difetto** (Ruling 40, confermato con una sonda dal ri-revisore del Task 12):
`sp16a` pregresso di 12.345,67 senza alcun piano di rimborso restava 12.345,67
ogni anno senza nuovo prestito, e andava a **zero nel primo anno** con un nuovo
finanziamento. La rata del prestito NUOVO si prendeva «prima dal breve», e il
breve era tutto debito bancario pregresso.

**La stessa famiglia, all'altro capo** (misurata da questa rete, non dal Ruling
40): la rata del piano del pregresso (`existing_debt_repayment_years`) non si
ferma quando il pregresso e' estinto — e' una rata fissa sull'esposizione
dell'anno base, tenuta a bada dal solo `max(0, …)` — e, finche' `sp17a` conteneva
anche il prestito nuovo, si mangiava quello: con un piano a 2 anni su un orizzonte
di 3, `sp17a` del 2029 valeva 7.098,88 invece dei 25.000,11 del prestito da solo
(misurato su 5ad6112 con il prestito di questo file).

**Il principio** (il proprietario): «bisogna dividere le voci patrimoniali
generate dal previsionale dallo scadenziamento del pregresso». Invariante I1
esteso: ogni debito si riduce solo con il proprio rimborso, quindi la
componente pregressa di `sp16a`/`sp17a` e' identica, anno per anno, con e senza
il nuovo finanziamento.

**L'oracolo non ricalcola i piani** (sarebbe un secondo motore in un test): sono
due GEMELLI generati dallo stesso motore. Il gemello «senza prestito» dice che
cosa fanno il pregresso e il suo piano da soli; il gemello «solo prestito», su
un'azienda senza banca, dice che cosa fa il prestito da solo. Il nuovo prestito
non sta mai in `sp16a`, quindi `sp16a` deve coincidere col primo gemello; e
`sp17a` deve valere la SOMMA dei due.

**Perche' la somma e' esatta, e perche' i piani sono scelti cosi'.** Il motore
persiste al centesimo anno per anno, e l'arrotondamento di una somma non e' la
somma degli arrotondamenti. La somma torna esatta quando uno dei due addendi si
muove di centesimi interi: ROUND_HALF_UP e' invariante per traslazione di un
multiplo di 0,01. Per questo il pregresso ha passi al centesimo (35.802,46 / 2 =
17.901,23; contratti dettagliati da 6.000,00 e 2.901,23) e il MEZZO centesimo sta
tutto nel prestito: 100.000,38 / 4 = 25.000,095, una rata che cade esattamente
sul confine di arrotondamento — e' li' che una sonda con importi tondi dichiara
«zero occorrenze».
"""
from decimal import Decimal as D

import pytest

from backend.app.services import assumptions_service
from database.models import BalanceSheet, BudgetScenario, FinancialYear
from tests.e2e_kit import memory_sessions, read_forecast_maps, seed_base_year

ANNI = (2027, 2028, 2029)
BREVE, LUNGO = D("12345.67"), D("23456.79")

# Rata al mezzo centesimo: 100.000,38 / 4 = 25.000,095.
PRESTITO = {"financing_amount": 100000.38, "financing_duration_years": 4, "financing_interest_rate": 4.35}

# Il prestito da solo, persistito anno per anno (misurato sul gemello, e rifatto a
# mano: 100.000,38 − 25.000,095 = 75.000,285 → 75.000,29; − 25.000,095 = 50.000,195
# → 50.000,20; − 25.000,095 = 25.000,105 → 25.000,11). Tre mezzi centesimi, tre
# arrotondamenti per eccesso: e' la catena che il motore persiste per un prestito.
SOLO_PRESTITO = {2027: D("75000.29"), 2028: D("50000.20"), 2029: D("25000.11")}

# Il pregresso descritto da contratti (`opening_residual`): 30.000,00 in 5 anni e
# 5.802,46 in 2, cioe' 8.901,23 di rata il primo anno — MENO della quota a breve.
# E' la forma in cui la rata del prestito nuovo trova ancora breve da mangiare.
CONTRATTI_PREGRESSO = [
    {"name": "Mutuo A", "amount": 0, "opening_residual": 30000.00, "duration_years": 5, "interest_rate": 3.1},
    {"name": "Mutuo B", "amount": 0, "opening_residual": 5802.46, "duration_years": 2, "interest_rate": 2.7},
]


def _genera(db, user, rows, breve, lungo):
    """Genera sul percorso persistito e restituisce `{anno: sp}`, o fallisce parlando."""
    company_id, _ = seed_base_year(db, user_id=user)
    fy = db.query(FinancialYear).filter(FinancialYear.company_id == company_id).one()
    b = db.query(BalanceSheet).filter(BalanceSheet.financial_year_id == fy.id).one()
    # Il kit tiene 50.000 su `sp17a`: lo si sostituisce, non lo si somma.
    delta_lungo = lungo - b.sp17a_debiti_banche_lungo
    b.sp16a_debiti_banche_breve = breve
    b.sp16_debiti_breve += breve
    b.sp17a_debiti_banche_lungo = lungo
    b.sp17_debiti_lungo += delta_lungo
    b.sp09_disponibilita_liquide += breve + delta_lungo
    db.commit()
    sc = BudgetScenario(company_id=company_id, name=user, base_year=2026, scenario_type="budget")
    db.add(sc)
    db.commit()
    res = assumptions_service.bulk_upsert_assumptions(db, sc.id, [dict(r) for r in rows], auto_generate=True)
    # `forecast_generated`, non l'HTTP 200: il bulk risponde 200 anche a un
    # previsionale rifiutato (CLAUDE.md).
    assert res["forecast_generated"] is True, f"{user}: {res['message']}"
    return {anno: sp for anno, sp, _ce in read_forecast_maps(db, sc.id)}


def _righe(primo=None, tutti=None):
    rows = [dict(forecast_year=y, revenue_growth_pct=3.33, tax_rate=27.9, **(tutti or {})) for y in ANNI]
    rows[0].update(primo or {})
    return rows


CASI = [
    # (nome, breve, lungo, ipotesi del primo anno, ipotesi di tutti gli anni)
    ("breve senza piano", BREVE, LUNGO, {}, {}),
    # 35.802,46 / 2 = 17.901,23: il piano si estingue nel 2028, l'orizzonte arriva al 2029.
    ("breve e lungo con piano in 2 anni", BREVE, LUNGO, {}, {"existing_debt_repayment_years": 2}),
    ("breve e lungo con contratti dettagliati", BREVE, LUNGO, {"financing_loans": CONTRATTI_PREGRESSO}, {}),
    # Solo lungo: senza piano il codice di prima era gia' giusto (il breve non
    # c'era); con il piano no, perche' la rata del pregresso sopravvive al pregresso.
    ("solo lungo senza piano", D("0"), LUNGO, {}, {}),
    # 23.456,78 e non 23.456,79: da solo il lungo e' TUTTA la base del piano, e
    # 23.456,79 / 2 = 11.728,395 metterebbe il mezzo centesimo anche sul pregresso —
    # misurato: la somma dei gemelli sbaglia allora di un centesimo senza alcun difetto.
    ("solo lungo con piano in 2 anni", D("0"), D("23456.78"), {}, {"existing_debt_repayment_years": 2}),
]


# Che cosa fa il pregresso DA SOLO, `(sp16a, sp17a)` anno per anno, rifatto a mano.
# Serve perche' i due gemelli condividono il motore: un difetto che sbaglia il piano
# del pregresso in ENTRAMBI (per esempio i contratti `opening_residual` presi per
# prestiti nuovi, e mai rimborsati) lascia la somma esatta e passerebbe inosservato.
#   piano in 2 anni: 35.802,46 / 2 = 17.901,23 — il breve 12.345,67 per primo, poi
#     5.555,56 dal lungo (17.901,23); nel 2028 il resto; nel 2029 il `max` a zero.
#   contratti: 6.000,00 + 2.901,23 = 8.901,23 nel 2027 (breve a 3.444,44), 8.901,23
#     nel 2028 (breve a zero, 5.456,79 dal lungo: 18.000,00), 6.000,00 nel 2029.
#   solo lungo in 2 anni: 23.456,78 / 2 = 11.728,39.
PREGRESSO_DA_SOLO = {
    "breve senza piano": [(BREVE, LUNGO)] * 3,
    "breve e lungo con piano in 2 anni": [(D("0"), D("17901.23")), (D("0"), D("0")), (D("0"), D("0"))],
    "breve e lungo con contratti dettagliati": [
        (D("3444.44"), LUNGO), (D("0"), D("18000.00")), (D("0"), D("12000.00"))],
    "solo lungo senza piano": [(D("0"), LUNGO)] * 3,
    "solo lungo con piano in 2 anni": [(D("0"), D("11728.39")), (D("0"), D("0")), (D("0"), D("0"))],
}


def _con_prestito(primo):
    """Il primo anno col prestito aggiunto. Con i contratti dettagliati il prestito
    nuovo e' la legacy `financing_amount` accanto a loro: `assemble_financing`
    li mette nello stesso elenco, ed e' li' che il motore deve separarli."""
    out = dict(primo)
    out.update(PRESTITO)
    return out


def test_il_prestito_da_solo_e_la_catena_attesa():
    """L'oracolo della somma, tenuto fermo a mano: se questo cambia, cambia il kernel
    del prestito o la quantizzazione — non il confine col pregresso."""
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            solo = _genera(db, "solo-prestito", _righe(PRESTITO), D("0"), D("0"))
        assert {y: sp["sp17a_debiti_banche_lungo"] for y, sp in solo.items()} == SOLO_PRESTITO
        assert all(sp["sp16a_debiti_banche_breve"] == D("0") for sp in solo.values())
    finally:
        engine.dispose()


@pytest.mark.parametrize("nome, breve, lungo, primo, tutti", CASI, ids=[c[0] for c in CASI])
def test_i1_esteso_la_componente_pregressa_non_si_accorge_del_prestito(nome, breve, lungo, primo, tutti):
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            con = _genera(db, f"con-{nome}", _righe(_con_prestito(primo), tutti), breve, lungo)
            senza = _genera(db, f"senza-{nome}", _righe(primo, tutti), breve, lungo)
            # Il prestito da solo, con le STESSE ipotesi fuorche' il pregresso: su
            # un'azienda senza banca non c'e' piano ne' contratto da applicare.
            solo = _genera(db, f"solo-{nome}", _righe(PRESTITO), D("0"), D("0"))

        fuori = []
        for anno, (breve_atteso, lungo_atteso) in zip(ANNI, PREGRESSO_DA_SOLO[nome]):
            c, s, p = con[anno], senza[anno], solo[anno]
            if (s["sp16a_debiti_banche_breve"], s["sp17a_debiti_banche_lungo"]) != (breve_atteso, lungo_atteso):
                fuori.append(f"{anno} pregresso da solo: ({s['sp16a_debiti_banche_breve']}, "
                             f"{s['sp17a_debiti_banche_lungo']}), rifatto a mano ({breve_atteso}, {lungo_atteso})")
            if c["sp16a_debiti_banche_breve"] != s["sp16a_debiti_banche_breve"]:
                fuori.append(f"{anno} sp16a: {c['sp16a_debiti_banche_breve']} col prestito, "
                             f"{s['sp16a_debiti_banche_breve']} senza — la rata nuova ha pagato il pregresso")
            atteso = s["sp17a_debiti_banche_lungo"] + p["sp17a_debiti_banche_lungo"]
            if c["sp17a_debiti_banche_lungo"] != atteso:
                fuori.append(f"{anno} sp17a: {c['sp17a_debiti_banche_lungo']}, atteso {atteso} = "
                             f"pregresso {s['sp17a_debiti_banche_lungo']} + prestito {p['sp17a_debiti_banche_lungo']}")
            # Nessun denaro dal nulla: il foglio quadra al centesimo ogni anno.
            if c["_total_assets"] != c["_total_liabilities"]:
                fuori.append(f"{anno} quadratura: attivo {c['_total_assets']} != passivo {c['_total_liabilities']}")
            if c["sp09_disponibilita_liquide"] < 0:
                fuori.append(f"{anno} cassa negativa {c['sp09_disponibilita_liquide']}")
        assert not fuori, f"[{nome}]\n" + "\n".join(fuori)
    finally:
        engine.dispose()


def test_un_cash_sweep_che_rimborsa_oltre_il_pregresso_non_fa_rinascere_debito():
    """La regola che la separazione introduce, tenuta ferma.

    Il residuo del prestito nuovo all'apertura e' la catena del kernel, ma non puo'
    superare `sp17a`: un cash sweep che l'anno prima ha rimborsato tutto il debito
    bancario lo ha tolto prima al pregresso e poi al prestito nuovo. Nel 2028 lo
    sweep chiude ogni debito bancario; nel 2029 la rata del kernel cade su un
    prestito gia' estinto e deve restare a zero. Senza quel limite il pregresso
    diventerebbe negativo e `sp17a` persisterebbe un debito negativo: denaro dal
    nulla, e un foglio che quadra lo stesso.

    Lo sweep sta SOLO nel 2028, e non per comodita': uno sweep acceso anche nel
    2029 «rimborsa» un `sp17a` negativo (`min(eccesso, negativo)` e' negativo), lo
    riporta a zero e gonfia la cassa. Misurato: con lo sweep in entrambi gli anni
    la mutazione «senza limite» passava questo test.
    """
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            sweep = {"cash_sweep_enabled": True, "cash_sweep_min_cash": 1000.55}
            rows = [
                dict(forecast_year=2027, revenue_growth_pct=3.33, tax_rate=27.9, **PRESTITO),
                dict(forecast_year=2028, revenue_growth_pct=3.33, tax_rate=27.9, **sweep),
                dict(forecast_year=2029, revenue_growth_pct=3.33, tax_rate=27.9),
            ]
            sp = _genera(db, "sweep-oltre", rows, BREVE, LUNGO)
        # Precondizioni: nel 2027 c'e' debito bancario pregresso e nuovo, e lo sweep
        # del 2028 ha cassa per chiuderli entrambi.
        assert sp[2027]["sp16a_debiti_banche_breve"] == BREVE
        assert sp[2027]["sp17a_debiti_banche_lungo"] > LUNGO
        assert sp[2028]["sp09_disponibilita_liquide"] > D("1000.55")
        for anno in (2028, 2029):
            assert sp[anno]["sp16a_debiti_banche_breve"] == D("0"), anno
            assert sp[anno]["sp17a_debiti_banche_lungo"] == D("0"), anno
            assert sp[anno]["_total_assets"] == sp[anno]["_total_liabilities"], anno
    finally:
        engine.dispose()


def test_la_sonda_del_ruling_40_con_i_suoi_numeri():
    """La sonda del ri-revisore, a scoperto spento: 12.345,67 di breve pregresso,
    nessun piano, un prestito nuovo. Su 5ad6112 il breve andava a zero nel 2027."""
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            con = _genera(db, "r40-con", _righe(_con_prestito({})), BREVE, LUNGO)
        assert [con[y]["sp16a_debiti_banche_breve"] for y in ANNI] == [BREVE] * 3
        # 23.456,79 di lungo pregresso fermo + la catena del prestito.
        assert [con[y]["sp17a_debiti_banche_lungo"] for y in ANNI] == [
            D("98457.08"), D("73456.99"), D("48456.90")]
    finally:
        engine.dispose()
