"""La quota del prestito nuovo che scade l'anno dopo sta a breve (Task 17).

**Il difetto** (confermato con una sonda dalla revisione del Task 16, rilievo
«preesistente (a)»): il motore metteva TUTTO il residuo del prestito nuovo in
`sp17a_debiti_banche_lungo`, anche la rata che scade entro i dodici mesi
successivi. Sulla base del kit con 12.345,67 di breve e 23.456,79 di lungo
pregresso e un prestito di 100.000,38 in 4 anni, il current ratio 2027 valeva
2,4206 invece di 2,0794. `sp16` e `sp17` stanno entrambi nel passivo: il pareggio
non se ne accorge, se ne accorgono CCN, current ratio e circolante di Altman.

**Il contratto.** La quota di ogni prestito nuovo che il calendario del kernel
rimborsa nell'anno dopo sta in `sp16a`, il resto in `sp17a`: zero finche' l'anno
dopo e' ancora di preammortamento, la maxirata nell'anno prima che scada, e
l'ultimo anno di orizzonte non si azzera. Debito bancario pregresso, cassa, conto
economico e totale del debito non cambiano, anno per anno.

**Gli oracoli, e da dove vengono.**
- La quota a breve e' rifatta A MANO sulla catena del prestito (caso per caso,
  qui sotto): e' cio' che la catena persistita toglie al residuo l'anno dopo.
- La componente pregressa viene dal gemello «senza prestito», quella nuova dal
  gemello «solo prestito» su un'azienda senza banca: e' l'I1 esteso del Task 16,
  ora anche sul lato breve.
- «Invariato rispetto a prima» e' letterale: debito bancario totale, cassa,
  risultato, oneri finanziari e imposte sono i numeri che `5197929` (l'HEAD di
  partenza del Task 17) persisteva per gli STESSI scenari, misurati su uno
  snapshot `git archive`. Una riclassifica che li muove non e' una riclassifica.

**Il campionamento e' parte della rete**: rata al mezzo centesimo (100.000,38 / 4
= 25.000,095), preammortamento con quota al mezzo centesimo, maxirata con code di
millesimi, debito pregresso non tondo a breve E a lungo accanto, un piano del
pregresso, lo scoperto concesso, lo sweep e un override di `sp16a`.
"""
from decimal import Decimal as D

import pytest

from backend.app.services import assumptions_service, forecast_preview_service
from database.models import BalanceSheet, BudgetScenario, FinancialYear
from tests.e2e_kit import memory_sessions, read_forecast_maps, seed_base_year

BREVE, LUNGO = D("12345.67"), D("23456.79")
ZERO = D("0")
SP16A, SP17A, SP09 = "sp16a_debiti_banche_breve", "sp17a_debiti_banche_lungo", "sp09_disponibilita_liquide"
A3 = (2027, 2028, 2029)
A4 = (2027, 2028, 2029, 2030)
A5 = (2027, 2028, 2029, 2030, 2031)

# 100.000,38 in 4 anni: rata 25.000,095, il mezzo centesimo esatto.
PRESTITO = {"financing_amount": 100000.38, "financing_duration_years": 4, "financing_interest_rate": 4.35}
# Un secondo prestito erogato l'anno dopo: 55.555,55 in 3 anni, rata 18.518,51666…
SECONDO_PRESTITO = {"financing_amount": 55555.55, "financing_duration_years": 3, "financing_interest_rate": 3.1}
# 60.000,01 in 4 anni, i primi 2 di solo interessi: poi 30.000,005 all'anno.
PREAMMORTAMENTO = [{"name": "Preammortamento", "amount": 60000.01, "duration_years": 4,
                    "grace_years": 2, "interest_rate": 3.3}]
# 80.000,03 in 3 anni con maxirata del 40%: maxirata 32.000,012, quota capitale 16.000,006.
MAXIRATA = [{"name": "Maxirata", "amount": 80000.03, "duration_years": 3,
             "balloon_pct": 40, "interest_rate": 5}]
SCOPERTO = {"overdraft_allowed": True, "financing_interest_rate": 6.13}
STRESS = {"tangible_investments": 350000.37}


def _genera(db, user, rows, breve=BREVE, lungo=LUNGO):
    """`{anno: (sp, ce, details)}` dal percorso persistito, o fallisce parlando."""
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
    prev = forecast_preview_service.preview_forecast(db, sc.id, [dict(r) for r in rows])
    assert prev["error"] is None, f"{user}: {prev['error']}"
    det = {a["year"]: a["details"] for a in prev["forecast_years"]}
    return {anno: (sp, ce, det[anno]) for anno, sp, ce in read_forecast_maps(db, sc.id)}


def _righe(anni, tutti=None, per_anno=None):
    rows = [dict(forecast_year=y, revenue_growth_pct=3.33, tax_rate=27.9, **(tutti or {})) for y in anni]
    for i, extra in (per_anno or {}).items():
        rows[i].update(extra)
    return rows


def _scoperto(det):
    return D(str(det.get("scoperto_residuo") or 0))


def _quota(det):
    """La quota a breve dei prestiti NUOVI dichiarata: somma dei `breve` dei contratti senza residuo iniziale in
    `details['debito_bancario']` (lotto 3A, Task 2). Assente vale zero — ed e' l'asserzione a dirlo, non un KeyError."""
    contratti = (det.get("debito_bancario") or {}).get("contratti") or []
    return sum((D(str(c["breve"])) for c in contratti if D(str(c.get("residuo_iniziale") or 0)) == 0), D("0"))


def _al_centesimo(fuori, dove, sp, det):
    """Quadratura, cassa mai negativa, I2, e nessun residuo di quadratura sulla ripartizione."""
    if sp["_total_assets"] != sp["_total_liabilities"]:
        fuori.append(f"{dove} quadratura: attivo {sp['_total_assets']} != passivo {sp['_total_liabilities']}")
    if sp[SP09] < 0:
        fuori.append(f"{dove} cassa negativa {sp[SP09]}")
    if sp[SP09] > 0 and _scoperto(det) > 0:
        fuori.append(f"{dove} I2: cassa {sp[SP09]} e scoperto {_scoperto(det)} insieme")
    for posa in det.get("residuo_quadratura") or []:
        if posa["campo"] in (SP16A, SP17A):
            fuori.append(f"{dove} residuo di quadratura {posa['importo']} posato su {posa['campo']}")


PRIMA_ETICHETTE = ("debito bancario sp16a+sp17a", "cassa sp09", "risultato sp13",
                   "oneri finanziari ce15", "imposte ce20")


def _prima(fuori, dove, sp, ce, attesi):
    """Gli stessi cinque numeri che `5197929` persisteva per lo stesso scenario."""
    ora = (sp[SP16A] + sp[SP17A], sp[SP09], sp["sp13_utile_perdita"],
           ce["ce15_oneri_finanziari"], ce["ce20_imposte"])
    for etichetta, valore, atteso in zip(PRIMA_ETICHETTE, ora, attesi):
        if valore != D(atteso):
            fuori.append(f"{dove} {etichetta}: {valore}, su 5197929 era {atteso}")


CASI = [
    dict(
        nome="rata al mezzo centesimo, e l'orizzonte taglia l'ultima rata",
        anni=A3,
        con=_righe(A3, None, {0: PRESTITO}),
        senza=_righe(A3),
        solo=_righe(A3, None, {0: PRESTITO}),
        # 100.000,38 − 25.000,095 = 75.000,285 → 75.000,29; → 50.000,20 (50.000,195);
        # → 25.000,11 (25.000,105); nel 2030, oltre l'orizzonte, → 0,02 (0,015).
        catena={2027: "75000.29", 2028: "50000.20", 2029: "25000.11"},
        # Cio' che la catena toglie l'anno dopo: 25.000,09 ogni anno, ANCHE nel 2029,
        # perche' la rata del 2030 sta nel contratto anche se non nel piano.
        quota={2027: "25000.09", 2028: "25000.09", 2029: "25000.09"},
        prima={
            2027: ("110802.75", "166993.94", "61739.21", "9350.02", "23890.77"),
            2028: ("85802.66", "265838.62", "77408.59", "8262.51", "29954.23"),
            2029: ("60802.57", "380845.36", "93573.64", "7175.01", "36209.50"),
        },
    ),
    dict(
        nome="preammortamento",
        anni=A4,
        con=_righe(A4, None, {0: {"financing_loans": PREAMMORTAMENTO}}),
        senza=_righe(A4),
        solo=_righe(A4, None, {0: {"financing_loans": PREAMMORTAMENTO}}),
        # 2027-2028 solo interessi: 60.000,01; 2029 → 30.000,01 (30.000,005); 2030 →
        # 0,01 (0,005), che resta: il contratto e' finito.
        catena={2027: "60000.01", 2028: "60000.01", 2029: "30000.01", 2030: "0.01"},
        # Fine 2027: il 2028 e' ancora preammortamento, niente a breve. Fine 2028:
        # 60.000,01 − 30.000,01 = 30.000,00. Fine 2029: 30.000,01 − 0,01 = 30.000,00.
        # Fine 2030: nessuna rata nel 2031.
        quota={2027: "0", 2028: "30000.00", 2029: "30000.00", 2030: "0"},
        prima={
            2027: ("95802.47", "154363.69", "63448.00", "6980.00", "24552.00"),
            2028: ("95802.47", "278829.73", "78333.28", "6980.00", "30312.05"),
            2029: ("65802.47", "388673.76", "93714.25", "6980.00", "36263.90"),
            2030: ("35802.47", "515397.86", "110321.19", "5990.00", "42690.17"),
        },
    ),
    dict(
        nome="maxirata accanto a un piano del pregresso",
        anni=A3,
        # 35.802,46 / 2 = 17.901,23 al centesimo: il mezzo centesimo sta nel prestito.
        con=_righe(A3, {"existing_debt_repayment_years": 2}, {0: {"financing_loans": MAXIRATA}}),
        senza=_righe(A3, {"existing_debt_repayment_years": 2}),
        solo=_righe(A3, None, {0: {"financing_loans": MAXIRATA}}),
        # 80.000,03 − 16.000,006 = 64.000,024 → 64.000,02; → 48.000,01 (48.000,014);
        # 2029 rata + maxirata 48.000,018 → zero.
        catena={2027: "64000.02", 2028: "48000.01", 2029: "0"},
        # Fine 2027: 64.000,02 − 48.000,01 = 16.000,01. Fine 2028: la maxirata scade nel
        # 2029, e con lei tutto il residuo: 48.000,01 a breve, zero oltre.
        quota={2027: "16000.01", 2028: "48000.01", 2029: "0"},
        prima={
            2027: ("81901.25", "138442.47", "61991.58", "9000.00", "23988.42"),
            2028: ("48000.01", "228350.85", "77453.66", "8200.00", "29971.67"),
            2029: ("0", "320115.25", "93411.43", "7400.00", "36146.72"),
        },
    ),
    dict(
        nome="due prestiti erogati in anni diversi",
        anni=A3,
        # Il secondo nasce nel 2028: a fine 2027 non e' debito, e la sua prima rata
        # (nel 2028) non entra nella quota a breve del 2027.
        con=_righe(A3, None, {0: PRESTITO, 1: SECONDO_PRESTITO}),
        senza=_righe(A3),
        solo=_righe(A3, None, {0: PRESTITO, 1: SECONDO_PRESTITO}),
        # Rate 25.000,095 e 55.555,55 / 3 = 18.518,51666…: 2027 → 75.000,29; 2028 →
        # 75.000,29 + 55.555,55 − 43.518,61166… = 87.037,228… → 87.037,23; 2029 →
        # 43.518,618… → 43.518,62; nel 2030, oltre l'orizzonte, 0,008… → 0,01.
        catena={2027: "75000.29", 2028: "87037.23", 2029: "43518.62"},
        # Fine 2027: la sola rata 2028 del PRIMO prestito, 75.000,29 − 50.000,20 =
        # 25.000,09 (con anche quella del secondo sarebbe 43.518,61). Fine 2028:
        # 87.037,23 − 43.518,62 = 43.518,61. Fine 2029: 43.518,62 − 0,01 = 43.518,61.
        quota={2027: "25000.09", 2028: "43518.61", 2029: "43518.61"},
        prima={
            2027: ("110802.75", "166993.94", "61739.21", "9350.02", "23890.77"),
            2028: ("122839.69", "301153.43", "76166.87", "9984.73", "29473.73"),
            2029: ("79321.08", "396974.00", "92745.83", "8323.16", "35889.16"),
        },
    ),
    dict(
        nome="scoperto concesso sopra la quota a breve",
        anni=A3,
        con=_righe(A3, SCOPERTO, {0: {**PRESTITO, **SCOPERTO, **STRESS}}),
        senza=_righe(A3, SCOPERTO, {0: STRESS}),
        solo=_righe(A3, None, {0: PRESTITO}),
        catena={2027: "75000.29", 2028: "50000.20", 2029: "25000.11"},
        quota={2027: "25000.09", 2028: "25000.09", 2029: "25000.09"},
        esercita_scoperto=True,
        # Il debito bancario qui comprende lo scoperto in essere (184.786,42 nel 2027).
        prima={
            2027: ("295589.17", "0", "9985.79", "11130.02", "3864.12"),
            2028: ("164380.17", "0", "17808.94", "20924.93", "6891.39"),
            2029: ("60802.57", "53785.26", "38988.99", "12881.81", "15087.28"),
        },
    ),
]


@pytest.mark.parametrize("caso", CASI, ids=[c["nome"] for c in CASI])
def test_la_rata_dell_anno_dopo_sta_a_breve_e_nient_altro_si_muove(caso):
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            con = _genera(db, "con", caso["con"])
            senza = _genera(db, "senza", caso["senza"])
            solo = _genera(db, "solo", caso["solo"], ZERO, ZERO)
        fuori = []
        for anno in caso["anni"]:
            (c, ce_c, det_c), (s, _ce_s, det_s), (p, _ce_p, det_p) = con[anno], senza[anno], solo[anno]
            dove = f"[{caso['nome']} | {anno}]"
            quota = D(caso["quota"][anno])

            # 1. La quota a breve: persistita, del prestito da solo, e dichiarata.
            persistita = (c[SP16A] - _scoperto(det_c)) - (s[SP16A] - _scoperto(det_s))
            if persistita != quota:
                fuori.append(f"{dove} quota bancaria di sp16a col prestito − senza = {persistita}, "
                             f"il calendario dice {quota}")
            if p[SP16A] != quota:
                fuori.append(f"{dove} sp16a del prestito da solo {p[SP16A]}, il calendario dice {quota}")
            if _quota(det_c) != quota:
                fuori.append(f"{dove} quota dichiarata {_quota(det_c)}, il calendario dice {quota}")

            # 2. Il resto sta oltre, e il pregresso non si accorge del prestito (I1 esteso).
            if c[SP17A] != s[SP17A] + p[SP17A]:
                fuori.append(f"{dove} sp17a {c[SP17A]}, atteso pregresso {s[SP17A]} + oltre del prestito {p[SP17A]}")
            if p[SP16A] + p[SP17A] != D(caso["catena"][anno]):
                fuori.append(f"{dove} prestito da solo {p[SP16A] + p[SP17A]}, catena {caso['catena'][anno]}")

            # 3. Invariato rispetto a prima: e' una riclassifica, non un flusso.
            _prima(fuori, dove, c, ce_c, caso["prima"][anno])

            # 4. Al centesimo.
            _al_centesimo(fuori, dove, c, det_c)
        if caso.get("esercita_scoperto"):
            assert any(_scoperto(con[a][2]) > 0 for a in caso["anni"]), "lo scoperto non e' mai stato acceso"
        assert not fuori, "\n".join(fuori)
    finally:
        engine.dispose()


# ══ Il cash sweep: rimborsa il pregresso SENZA piano ══
#
# La sonda 6a della revisione del Task 16: cassa 2027 senza sweep 166.993,94,
# minimo scelto perche' lo sweep rimborsi esattamente il breve pregresso
# piu' 10.000,55. L'eccedenza (22.346,22) non supera il pregresso (35.802,46),
# quindi dal lotto 3A i numeri restano quelli di prima: il breve si chiude, i
# 10.000,55 cadono sul lungo pregresso (23.456,79 → 13.456,24) e ci restano; il
# prestito nuovo tiene il proprio calendario. Con l'ordine opposto il prestito
# perderebbe 10.000,55 e il pregresso resterebbe intatto: il 2030 varrebbe
# 23.456,79 invece di 13.456,26 (misurato dalla revisione).
MINIMO_SWEEP = D("144647.72")
CATENA_SWEEP = {2027: "75000.29", 2028: "50000.20", 2029: "25000.11", 2030: "0.02", 2031: "0.02"}
PREGRESSO_DOPO_SWEEP = D("13456.24")
QUOTA_SWEEP = {2027: "25000.09", 2028: "25000.09", 2029: "25000.09", 2030: "0", 2031: "0"}
PRIMA_SWEEP = {
    2027: ("88456.53", "144647.72", "61739.21", "9350.02", "23890.77"),
    2028: ("63456.44", "243492.40", "77408.59", "8262.51", "29954.23"),
    2029: ("38456.35", "358499.14", "93573.64", "7175.01", "36209.50"),
    2030: ("13456.26", "490180.06", "110250.90", "6087.50", "42662.96"),
    2031: ("13456.26", "664064.37", "156297.38", "5000.00", "60481.23"),
}


def test_lo_sweep_rimborsa_solo_il_pregresso_senza_piano():
    """L'asserzione e' sui TOTALI e sulla componente pregressa, non su `sp17a` da
    sola: dal Task 17 una parte del prestito sta a breve, e un test su `sp17a`
    misurerebbe la riclassifica invece dell'ordine. Dal lotto 3A lo sweep non
    tocca il prestito per nulla: qui l'eccedenza del 2027 (22.346,22) non supera
    il pregresso (35.802,46), quindi i numeri restano quelli — misurato:
    identici, cella per cella, a prima della decisione 3 del proprietario."""
    engine, sessions = memory_sessions()
    try:
        rows = _righe(A5, None, {0: {**PRESTITO, "cash_sweep_enabled": True,
                                     "cash_sweep_min_cash": float(MINIMO_SWEEP)}})
        with sessions() as db:
            run = _genera(db, "sweep-ordine", rows)
        # Precondizione: lo sweep del 2027 ha girato fino al minimo, non oltre.
        assert run[2027][0][SP09] == MINIMO_SWEEP, run[2027][0][SP09]
        fuori = []
        for anno in A5:
            c, ce, det = run[anno]
            dove = f"[sweep | {anno}]"
            totale = c[SP16A] - _scoperto(det) + c[SP17A]
            pregresso = totale - D(CATENA_SWEEP[anno])
            if pregresso != PREGRESSO_DOPO_SWEEP:
                fuori.append(f"{dove} pregresso {pregresso} = debito bancario {totale} − catena del prestito "
                             f"{CATENA_SWEEP[anno]}, atteso {PREGRESSO_DOPO_SWEEP}: lo sweep non ha rimborsato "
                             "prima il pregresso")
            _prima(fuori, dove, c, ce, PRIMA_SWEEP[anno])
            # Il breve pregresso l'ha chiuso lo sweep: in `sp16a` c'e' solo la quota nuova.
            quota = D(QUOTA_SWEEP[anno])
            if c[SP16A] - _scoperto(det) != quota or _quota(det) != quota:
                fuori.append(f"{dove} sp16a {c[SP16A]}, quota dichiarata {_quota(det)}, calendario {quota}")
            _al_centesimo(fuori, dove, c, det)
        assert not fuori, "\n".join(fuori)
    finally:
        engine.dispose()


# ══ Uno sweep che oltre il pregresso non va ══
#
# Stessa base e stessi due minimi della sonda 6b della revisione del Task 16: la cassa del 2027 sopra il minimo supera il
# pregresso (35.802,46). Dal lotto 3A (decisione 3 del proprietario) il prestito segue il suo piano, lo sweep si ferma al
# pregresso e la cassa resta: i due minimi danno gli stessi numeri. Oracolo: gemello senza sweep meno il pregresso,
# sullo snapshot `452112d`.
OLTRE_IL_PREGRESSO = dict(
    totale=("75000.29", "50000.20", "25000.11", "0.02", "0.02"),
    cassa=("131191.48", "230036.16", "345042.90", "476723.82", "650608.13"),
    quota=("25000.09", "25000.09", "25000.09", "0", "0"),
    oltre=("50000.20", "25000.11", "0.02", "0.02", "0.02"),
)


@pytest.mark.parametrize("minimo", ["71191.48", "91190.93"])
def test_uno_sweep_oltre_il_pregresso_lascia_il_prestito_al_suo_piano(minimo):
    engine, sessions = memory_sessions()
    try:
        rows = _righe(A5, None, {0: {**PRESTITO, "cash_sweep_enabled": True, "cash_sweep_min_cash": float(D(minimo))}})
        with sessions() as db:
            run = _genera(db, "oltre-pregresso", rows)
        fuori = []
        for i, anno in enumerate(A5):
            c, _ce, det = run[anno]
            dove = f"[minimo {minimo} | {anno}]"
            confronti = {
                "debito bancario sp16a+sp17a": (c[SP16A] + c[SP17A], OLTRE_IL_PREGRESSO["totale"][i]),
                "cassa sp09": (c[SP09], OLTRE_IL_PREGRESSO["cassa"][i]),
                "quota a breve in sp16a": (c[SP16A] - _scoperto(det), OLTRE_IL_PREGRESSO["quota"][i]),
                "quota dichiarata": (_quota(det), OLTRE_IL_PREGRESSO["quota"][i]),
                "oltre in sp17a": (c[SP17A], OLTRE_IL_PREGRESSO["oltre"][i]),
            }
            for etichetta, (valore, atteso) in confronti.items():
                if valore != D(atteso):
                    fuori.append(f"{dove} {etichetta}: {valore}, atteso {atteso}")
            _al_centesimo(fuori, dove, c, det)
        assert not fuori, "\n".join(fuori)
    finally:
        engine.dispose()


@pytest.mark.parametrize("lungo, attesa", [
    # Tutto in scadenza l'anno dopo, lungo grezzo sul mezzo centesimo: senza il
    # limite la quota sarebbe 5.000,01 e `sp17a` persisterebbe -0,01.
    ("5000.005", "5000.00"),
    ("4999.997", "4999.99"),
    ("5000.004", "5000.00"),
    ("0.005", "0"),
    ("7500.0025", "7500.00"),
    # Pregresso accanto: la quota e' la rata, il resto e' pregresso oltre.
    ("23456.79", "10000.00"),
    ("10000.00", "10000.00"),
])
def test_la_quota_non_supera_mai_il_lungo_e_la_riclassifica_resta_al_centesimo(lungo, attesa):
    """Il limite della quota a breve, su una funzione pura.

    La sonda del Task 17 non lo raggiunge dal percorso persistito sul kit: morde
    solo quando lo sweep erode un prestito tutto in scadenza l'anno dopo e il lungo
    grezzo resta sotto il centesimo, e sul kit la cassa grezza e' sempre al
    centesimo (12 crescite provate, zero celle diverse con il limite tolto). Qui la
    condizione si scrive direttamente: `lungo - quota` non negativo e
    `Q(lungo - quota) + quota = Q(lungo)`, cioe' la riclassifica non crea e non
    toglie un centesimo. Import locale: su un motore senza la funzione fallisce
    questo test, non la raccolta del file.
    """
    from decimal import ROUND_HALF_UP

    from calculations.forecast_engine import _quota_breve_prestiti_nuovi

    q = lambda x: x.quantize(D("0.01"), rounding=ROUND_HALF_UP)
    # 20.000,00 in 2 anni, erogato nel 2027: catena 10.000,00, rata 2028 10.000,00.
    prestito = [{"year": 2027, "amount": D("20000.00"), "duration": D("2"), "rate": D("0")}]
    lungo = D(lungo)
    quota = _quota_breve_prestiti_nuovi(prestito, 2027, lungo)
    assert quota == D(attesa), quota
    assert lungo - quota >= 0, f"sp17a grezzo negativo: {lungo - quota}"
    assert q(lungo - quota) + quota == q(lungo), f"{q(lungo - quota)} + {quota} != {q(lungo)}"


def test_un_override_di_sp16a_sotto_la_quota_la_riduce_e_non_crea_debito():
    """`sp_overrides` fissa `sp16a` a 5.000,55 nel 2027, sotto il breve pregresso
    (12.345,67) piu' la quota a breve (25.000,09).

    L'override vince sul totale, e dal Task 17 quel totale CONTIENE la quota del
    prestito: rispetto a `5197929` il debito del 2027 e' quindi 25.000,09 piu' basso.
    E' cambiato il contenuto del campo, non l'aritmetica. Il taglio cade prima sul
    breve pregresso (la precedenza dello sweep): la quota dichiarata e' cio' che ne
    resta, 5.000,55, cioe' quanto `sp16a` persiste davvero. L'anno dopo non nasce
    debito: il debito bancario del 2028 e' quello persistito nel 2027 meno la sola
    rata 2028 del prestito (il pregresso non ha piano), e cosi' il 2029.
    """
    engine, sessions = memory_sessions()
    try:
        rows = _righe(A3, None, {0: {**PRESTITO, "sp_overrides": {SP16A: 5000.55}}})
        with sessions() as db:
            run = _genera(db, "override-sp16a", rows)
        fuori = []
        sp27, _ce27, det27 = run[2027]
        assert sp27[SP16A] == D("5000.55"), sp27[SP16A]
        if _quota(det27) != D("5000.55"):
            fuori.append(f"[2027] quota dichiarata {_quota(det27)}, sp16a persiste 5000.55 senza scoperto")
        precedente = sp27[SP16A] + sp27[SP17A]
        for anno in (2028, 2029):
            sp, _ce, det = run[anno]
            totale = sp[SP16A] + sp[SP17A]
            if totale != precedente - D("25000.09"):
                fuori.append(f"[{anno}] debito bancario {totale}, atteso {precedente} − rata del prestito 25000.09")
            if _quota(det) != D("25000.09"):
                fuori.append(f"[{anno}] quota dichiarata {_quota(det)}, calendario 25000.09")
            precedente = totale
        for anno in A3:
            _al_centesimo(fuori, f"[override | {anno}]", run[anno][0], run[anno][2])
        assert not fuori, "\n".join(fuori)
    finally:
        engine.dispose()


def test_un_override_di_sp17a_fissa_solo_l_oltre_e_aggiunge_la_quota_al_debito():
    """`sp_overrides` fissa `sp17a` a 60.000,00 nel 2027 (rilievo Important I2 della
    revisione: un override di `sp17a`, non solo di `sp16a`, cambia significato).

    La riclassifica (`_quota_breve_prestiti_nuovi`) avviene PRIMA che gli override
    vengano applicati: l'override di `sp17a` fissa quindi solo la parte OLTRE la
    quota, e `sp16a` resta quello che era senza override (breve pregresso 12.345,67
    piu' la quota a breve 25.000,09 = 37.345,76). Rispetto a un override salvato
    quando il prestito stava tutto in `sp17a` (prima del Task 17), il debito del
    2027 e' quindi 25.000,09 PIU' alto (il contrario del caso `sp16a`, dove era piu'
    basso): il segno dipende da quale lato dello split l'utente ha fissato.
    """
    engine, sessions = memory_sessions()
    try:
        rows = _righe(A3, None, {0: {**PRESTITO, "sp_overrides": {SP17A: 60000.00}}})
        with sessions() as db:
            run = _genera(db, "override-sp17a", rows)
        fuori = []
        sp27, _ce27, det27 = run[2027]
        assert sp27[SP17A] == D("60000.00"), sp27[SP17A]
        if sp27[SP16A] != D("37345.76"):
            fuori.append(f"[2027] sp16a {sp27[SP16A]}, atteso 37345.76 (breve pregresso + quota, override non lo tocca)")
        if _quota(det27) != D("25000.09"):
            fuori.append(f"[2027] quota dichiarata {_quota(det27)}, attesa 25000.09 (sp16a non e' vincolato dall'override)")
        precedente = sp27[SP16A] + sp27[SP17A]
        for anno in (2028, 2029):
            sp, _ce, det = run[anno]
            totale = sp[SP16A] + sp[SP17A]
            if totale != precedente - D("25000.09"):
                fuori.append(f"[{anno}] debito bancario {totale}, atteso {precedente} − rata del prestito 25000.09")
            if _quota(det) != D("25000.09"):
                fuori.append(f"[{anno}] quota dichiarata {_quota(det)}, calendario 25000.09")
            precedente = totale
        for anno in A3:
            _al_centesimo(fuori, f"[override-sp17a | {anno}]", run[anno][0], run[anno][2])
        assert not fuori, "\n".join(fuori)
    finally:
        engine.dispose()
