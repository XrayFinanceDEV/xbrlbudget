"""La cassa non esce mai negativa: o solleva, o diventa scoperto di c/c dichiarato.

**Il difetto di partenza** (spec 2026-09-08 §11.1, misurato): un `sp_overrides`
che squilibra il foglio faceva persistere `sp09 = -4.829.777,78` sotto
`forecast_generated: True`. `_apply_sp_overrides` clampava a zero, e subito dopo
`_normalize_balance_sheet_cents(recompute_cash=True)` ricalcolava
`sp09 = passivo - attivo senza cassa` **senza clamp e senza sollevare**,
scavalcando il clamp. A valle quel numero aritmeticamente impossibile avvelena
current ratio, PFN, circolante di Altman e liquidita' FGPMI, senza un avviso.

**La regola nuova** (ruling del proprietario, 2026-09-09): la cassa plugga solo
verso l'alto, e un plug negativo e' un fabbisogno scoperto. Che cosa succede
allora dipende da una scelta ESPLICITA dell'utente, `overdraft_allowed`, spenta
di default:

- spenta: il motore solleva, `Fabbisogno finanziario scoperto di <importo>`, come
  ha sempre fatto — e ora lo fa **anche** sul percorso con override;
- accesa: il fabbisogno diventa `sp16a_debiti_banche_breve` generato dal piano,
  dichiarato in `details['scoperto_generato']`, con un tetto opzionale
  (`overdraft_limit`) oltre il quale il motore torna a sollevare.

Lo scoperto e' anche uno **strumento di misura**: accenderlo senza tetto serve a
far girare un piano stressato e leggere quanta finanza richiede — la risposta e'
`scoperto_generato` anno per anno, con il picco in `fabbisogno_picco`.
"""
import re
from decimal import Decimal as D

import pytest

from backend.app.services import assumptions_service
from backend.app.services import forecast_preview_service
from database.models import BudgetScenario, ForecastBalanceSheet
from tests.e2e_kit import memory_sessions, read_forecast_maps, seed_base_year

# L'override della spec §11.1: rimanenze gonfiate senza contropartita, cioe' un
# foglio che non quadra piu' se non a cassa negativa.
OVERRIDE_CHE_SQUILIBRA = {"sp05_rimanenze": 5000000}


def _scenario(db, user):
    company_id, _ = seed_base_year(db, user_id=user)
    sc = BudgetScenario(company_id=company_id, name=user, base_year=2026, scenario_type="budget")
    db.add(sc)
    db.commit()
    return company_id, sc.id


def _riga(anno, **extra):
    riga = {"forecast_year": anno, "revenue_growth_pct": 3.33, "tax_rate": 27.9}
    riga.update(extra)
    return riga


def _importo_scoperto(message):
    """L'importo dentro il messaggio del motore, con la regex del frontend."""
    m = re.search(r"Fabbisogno finanziario scoperto di ([\d.]+,\d{2})", message)
    return D(m.group(1).replace(".", "").replace(",", ".")) if m else None


def _dettagli(db, scenario_id, rows):
    """I `details` dichiarati anno per anno, dal percorso dell'anteprima."""
    res = forecast_preview_service.preview_forecast(db, scenario_id, rows)
    return {y["year"]: y["details"] for y in res["forecast_years"]}, res["error"]


def _eur(x):
    return round(float(x), 2)


# ── Step 1: il difetto di oggi, misurato ──────────────────────────────────────

def test_override_che_squilibra_non_persiste_una_cassa_negativa():
    """Senza concessione, l'override che squilibra il foglio RIFIUTA il piano.

    Prima di questa correzione la stessa chiamata rispondeva
    `forecast_generated: True` e persisteva una cassa di -4.829.777,78. Si legge
    `forecast_generated`, non l'HTTP 200: il bulk risponde 200 anche a un
    previsionale rifiutato (CLAUDE.md).
    """
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            _, sid = _scenario(db, "scoperto-spec-11-1")
            rows = [_riga(2027, sp_overrides=OVERRIDE_CHE_SQUILIBRA)]
            res = assumptions_service.bulk_upsert_assumptions(db, sid, rows, auto_generate=True)

        assert res["forecast_generated"] is False, res["message"]
        assert _importo_scoperto(res["message"]) is not None, res["message"]

        # Nessuna cassa negativa persistita: si guarda da una sessione NUOVA,
        # cosi' si legge cio' che e' stato committato e non cio' che e' rimasto
        # in sospeso nella sessione che ha fallito.
        with sessions() as db2:
            negative = (
                db2.query(ForecastBalanceSheet)
                .filter(ForecastBalanceSheet.sp09_disponibilita_liquide < 0)
                .all()
            )
            assert negative == [], [r.sp09_disponibilita_liquide for r in negative]
    finally:
        engine.dispose()


# ── Step 2: lo scoperto concesso ──────────────────────────────────────────────

def test_scoperto_concesso_diventa_debito_bancario_a_breve_dichiarato():
    """Concesso: `sp09 = 0`, `sp16a` cresce dell'importo che prima era negativo.

    L'importo atteso e' quello che il motore stesso dichiara nel rifiuto (il
    test sopra), non un numero copiato a mano: se il piano cambia, i due lati
    del confronto si muovono insieme.
    """
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            _, sid_no = _scenario(db, "scoperto-negato")
            rows_no = [_riga(2027, sp_overrides=OVERRIDE_CHE_SQUILIBRA)]
            rifiuto = assumptions_service.bulk_upsert_assumptions(db, sid_no, rows_no, auto_generate=True)
            fabbisogno = _importo_scoperto(rifiuto["message"])
            assert fabbisogno is not None and fabbisogno > 0, rifiuto["message"]

            # Lo stesso piano SENZA override: da' il `sp16a` di riferimento,
            # cioe' quello che l'override non tocca.
            _, sid_base = _scenario(db, "scoperto-senza-override")
            base = assumptions_service.bulk_upsert_assumptions(
                db, sid_base, [_riga(2027)], auto_generate=True)
            assert base["forecast_generated"] is True, base["message"]
            _, sp_base, _ce = read_forecast_maps(db, sid_base)[0]

            _, sid_ok = _scenario(db, "scoperto-concesso")
            rows_ok = [_riga(2027, sp_overrides=OVERRIDE_CHE_SQUILIBRA, overdraft_allowed=True)]
            res = assumptions_service.bulk_upsert_assumptions(db, sid_ok, rows_ok, auto_generate=True)
            assert res["forecast_generated"] is True, res["message"]

            _, sp, _ce = read_forecast_maps(db, sid_ok)[0]
            assert sp["sp09_disponibilita_liquide"] == D("0.00")
            assert sp["sp16a_debiti_banche_breve"] == sp_base["sp16a_debiti_banche_breve"] + fabbisogno
            # Il foglio quadra ancora: lo scoperto e' una contropartita vera,
            # non un tappo sulla sola riga della cassa.
            assert sp["_total_assets"] == sp["_total_liabilities"]

            dettagli, errore = _dettagli(db, sid_ok, rows_ok)
            assert errore is None, errore
            assert _eur(dettagli[2027]["scoperto_generato"]) == _eur(fabbisogno)
            assert _eur(dettagli[2027]["scoperto_residuo"]) == _eur(fabbisogno)
            assert _eur(dettagli[2027]["fabbisogno_picco"]) == _eur(fabbisogno)
            assert dettagli[2027]["fabbisogno_picco_anno"] == 2027
    finally:
        engine.dispose()


def test_tetto_dello_scoperto_solleva_e_nomina_i_due_importi():
    """`overdraft_limit` sotto il fabbisogno: il motore torna a sollevare."""
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            _, sid = _scenario(db, "scoperto-tetto")
            rows = [_riga(2027, sp_overrides=OVERRIDE_CHE_SQUILIBRA,
                          overdraft_allowed=True, overdraft_limit=100000)]
            res = assumptions_service.bulk_upsert_assumptions(db, sid, rows, auto_generate=True)

        assert res["forecast_generated"] is False, res["message"]
        # I due importi nel messaggio: il tetto concesso e quello richiesto.
        assert "il tetto concesso e' 100.000,00" in res["message"], res["message"]
        richiesto = re.search(r"servono ([\d.]+,\d{2})", res["message"])
        assert richiesto, res["message"]
        # Il richiesto e' il fabbisogno intero, non la sola eccedenza sul tetto.
        assert D(richiesto.group(1).replace(".", "").replace(",", ".")) > D("100000"), res["message"]

        with sessions() as db2:
            assert db2.query(ForecastBalanceSheet).count() == 0
    finally:
        engine.dispose()


def test_tetto_negativo_rifiutato_dal_bulk_e_dichiarato_dal_motore_in_anteprima():
    """Dal lotto 3A (Task 7a) il bulk valida le righe con lo schema tipizzato: un tetto negativo non arriva piu' al
    motore per quella porta. L'anteprima non valida lo schema, e li' il motore continua a dire il difetto vero."""
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            _, sid = _scenario(db, "scoperto-tetto-negativo")
            rows = [_riga(2027, overdraft_allowed=True, overdraft_limit=-1000)]
            with pytest.raises(assumptions_service.AssumptionsValidationError) as e:
                assumptions_service.bulk_upsert_assumptions(db, sid, [dict(r) for r in rows], auto_generate=True)
            assert e.value.errori == [{"forecast_year": 2027, "campo": "overdraft_limit",
                                       "messaggio": "deve essere maggiore o uguale a 0 (ricevuto: -1000)"}]
            _dettagli_anni, errore = _dettagli(db, sid, rows)
        assert "Il limite di scoperto non puo' essere negativo" in errore["message"], errore
        assert "ricevuto -1.000,00" in errore["message"], errore
        assert "tetto concesso" not in errore["message"], errore
        with sessions() as db2:
            assert db2.query(ForecastBalanceSheet).count() == 0
    finally:
        engine.dispose()


# ── Step 3: il giro d'anno ────────────────────────────────────────────────────

def _piano_due_anni(**extra):
    """Anno 1 investe 200k e va sotto; anno 2 non investe e genera cassa."""
    return [
        _riga(2027, tangible_investments=200000, financing_interest_rate=6.0, **extra),
        _riga(2028, financing_interest_rate=6.0, **extra),
    ]


def test_il_giro_danno_riduce_lo_scoperto_e_gli_oneri_stanno_sullapertura():
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            _, sid = _scenario(db, "scoperto-giro-anno")
            rows = _piano_due_anni(overdraft_allowed=True)
            res = assumptions_service.bulk_upsert_assumptions(db, sid, rows, auto_generate=True)
            assert res["forecast_generated"] is True, res["message"]

            mappe = {y: sp for y, sp, _ce in read_forecast_maps(db, sid)}
            ce = {y: c for y, _sp, c in read_forecast_maps(db, sid)}
            dettagli, errore = _dettagli(db, sid, rows)
            assert errore is None, errore

            residuo_27 = D(str(dettagli[2027]["scoperto_residuo"]))
            residuo_28 = D(str(dettagli[2028]["scoperto_residuo"]))
            assert residuo_27 > 0, dettagli[2027]
            # L'anno 2 non ne accende di nuovo e ne rimborsa una parte con la
            # cassa generata: lo scoperto non e' eterno.
            assert _eur(dettagli[2028]["scoperto_generato"]) == 0.0
            assert residuo_28 < residuo_27
            assert mappe[2028]["sp16a_debiti_banche_breve"] < mappe[2027]["sp16a_debiti_banche_breve"]

            # Gli oneri stanno sul saldo di APERTURA, mai su quello che l'anno
            # stesso genera: altrimenti l'interesse cambia la cassa che
            # determina l'interesse.
            assert _eur(dettagli[2027]["oneri_scoperto"]) == 0.0
            assert _eur(dettagli[2028]["oneri_scoperto"]) == _eur(residuo_27 * D("6") / D("100"))
            # E confluiscono in ce15, sopra l'onere finanziario di sempre.
            assert ce[2028]["ce15_oneri_finanziari"] == (
                ce[2027]["ce15_oneri_finanziari"]
                + D(str(_eur(dettagli[2028]["oneri_scoperto"]))).quantize(D("0.01"))
            )

            # Il picco e l'anno in cui cade: il numero che si porta in banca.
            assert _eur(dettagli[2027]["fabbisogno_picco"]) == _eur(residuo_27)
            assert dettagli[2027]["fabbisogno_picco_anno"] == 2027
            assert dettagli[2028]["fabbisogno_picco_anno"] == 2027
    finally:
        engine.dispose()


def test_senza_concessione_lo_stesso_piano_si_ferma_come_sempre():
    """Il default e' SPENTO: lo stesso piano stressato solleva, come oggi."""
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            _, sid = _scenario(db, "scoperto-spento")
            res = assumptions_service.bulk_upsert_assumptions(
                db, sid, _piano_due_anni(), auto_generate=True)
        assert res["forecast_generated"] is False, res["message"]
        assert _importo_scoperto(res["message"]) is not None, res["message"]
    finally:
        engine.dispose()


# ── Step 4: la parita' ────────────────────────────────────────────────────────

# I numeri di PRIMA della correzione, misurati sul percorso persistito
# (`bulk_upsert_assumptions` + `read_forecast_maps`) e congelati qui.
#
# Perche' questi otto campi e non l'intero prospetto: sono le sole superfici che
# la correzione tocca — il plug (`sp09`), la voce in cui lo scoperto atterra
# (`sp16a`, col suo aggregato `sp16`), il debito bancario che il rimborso
# potrebbe erodere (`sp17a`), gli oneri finanziari che l'interesse dello
# scoperto alimenta (`ce15`), e i tre numeri che qualunque spostamento di quelli
# muoverebbe a valle (`sp13`, `ce20`, il totale attivo). Una riga di costo non
# puo' muoversi per questa correzione, e congelarla direbbe di piu' di quanto
# questo test sa.
PARITA = {
    2027: {"sp09_disponibilita_liquide": "94586.93", "sp16a_debiti_banche_breve": "0.00",
           "sp16_debiti_breve": "140000.00", "sp17a_debiti_banche_lungo": "50000.00",
           "sp13_utile_perdita": "61796.71", "ce15_oneri_finanziari": "5000.00",
           "ce20_imposte": "23913.02", "_total_assets": "468088.00"},
    2028: {"sp09_disponibilita_liquide": "204440.72", "sp16a_debiti_banche_breve": "0.00",
           "sp16_debiti_breve": "144564.52", "sp17a_debiti_banche_lungo": "50000.00",
           "sp13_utile_perdita": "73592.47", "ce15_oneri_finanziari": "5000.00",
           "ce20_imposte": "28477.54", "_total_assets": "552606.11"},
    2029: {"sp09_disponibilita_liquide": "329576.89", "sp16a_debiti_banche_breve": "0.00",
           "sp16_debiti_breve": "144752.16", "sp17a_debiti_banche_lungo": "50000.00",
           "sp13_utile_perdita": "85873.15", "ce15_oneri_finanziari": "5000.00",
           "ce20_imposte": "33229.69", "_total_assets": "645098.63"},
}

RIGHE_PARITA = [
    {"forecast_year": y, "revenue_growth_pct": 3.33, "personnel_growth_pct": 1.11,
     "tangible_investments": 12345.67, "intangible_investments": 2345.67,
     "financing_interest_rate": 5.5, "tax_rate": 27.9}
    for y in (2027, 2028, 2029)
]


def test_uno_scenario_senza_scoperto_da_gli_stessi_numeri_di_prima():
    """Nessuna concessione, nessun override: gli stessi numeri, al centesimo.

    Le crescite non sono tonde di proposito: il residuo di quadratura nasce
    dall'arrotondamento, e una batteria di numeri tondi non lo produce mai.
    """
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            _, sid = _scenario(db, "scoperto-parita")
            res = assumptions_service.bulk_upsert_assumptions(
                db, sid, RIGHE_PARITA, auto_generate=True)
            assert res["forecast_generated"] is True, res["message"]

            fuori = []
            for anno, sp, ce in read_forecast_maps(db, sid):
                for campo, atteso in PARITA[anno].items():
                    letto = sp.get(campo) if campo.startswith(("sp", "_")) else ce.get(campo)
                    if D(str(letto)) != D(atteso):
                        fuori.append(f"{anno} {campo}: {letto} invece di {atteso}")
            assert not fuori, "\n".join(fuori)

            # `cassa_assorbita` si dichiara SEMPRE, anche quando la cassa resta
            # positiva: e' la cosa di cui l'utente va avvertito PRIMA che
            # diventi uno scoperto (a valle una chiave assente vale zero,
            # quindi tacere equivarrebbe a dichiararsi puliti).
            dettagli, errore = _dettagli(db, sid, RIGHE_PARITA)
            assert errore is None, errore
            for anno in (2027, 2028, 2029):
                for chiave in ("cassa_assorbita", "scoperto_generato", "scoperto_residuo",
                               "oneri_scoperto", "fabbisogno_picco", "fabbisogno_picco_anno"):
                    assert chiave in dettagli[anno], f"{anno}: manca {chiave}"
                assert _eur(dettagli[anno]["scoperto_generato"]) == 0.0
                assert _eur(dettagli[anno]["fabbisogno_picco"]) == 0.0
                assert dettagli[anno]["fabbisogno_picco_anno"] is None
    finally:
        engine.dispose()


def test_cassa_assorbita_si_dichiara_anche_quando_la_cassa_resta_positiva():
    """L'avviso e' il punto: un anno che consuma cassa lo dice, senza scoperto.

    L'anno 1 investe 100k con la cassa base di 30k: la cassa scende senza mai
    andare sotto zero, perche' il circolante e l'utile la rialzano — e' proprio
    il caso in cui nessun errore comparirebbe e l'utente non saprebbe nulla.
    """
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            _, sid = _scenario(db, "scoperto-avviso")
            rows = [_riga(2027, tangible_investments=100000)]
            res = assumptions_service.bulk_upsert_assumptions(db, sid, rows, auto_generate=True)
            assert res["forecast_generated"] is True, res["message"]

            _, sp, _ce = read_forecast_maps(db, sid)[0]
            assert sp["sp09_disponibilita_liquide"] > 0
            dettagli, errore = _dettagli(db, sid, rows)
            assert errore is None, errore
            assorbita = D(str(dettagli[2027]["cassa_assorbita"]))
            assert assorbita > 0, dettagli[2027]
            # Apertura (l'anno base) meno chiusura, al centesimo.
            assert _eur(assorbita) == _eur(D("30000.00") - sp["sp09_disponibilita_liquide"])
            assert _eur(dettagli[2027]["scoperto_generato"]) == 0.0
    finally:
        engine.dispose()


def test_gli_oneri_maturano_sul_residuo_di_apertura_non_su_quanto_acceso_prima():
    """Il terzo anno distingue due saldi che nel secondo coincidono.

    Nel 2028 lo scoperto acceso nel 2027 e quello residuo a fine 2027 sono lo
    stesso numero: un motore che calcolasse gli oneri sul GENERATO invece che
    sul RESIDUO passerebbe il test del giro d'anno (misurato con una mutazione).
    Nel 2029 non piu': il 2028 ha rimborsato una parte, non ne ha acceso di
    nuovo, e gli oneri devono stare su quel che resta.
    """
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            _, sid = _scenario(db, "scoperto-terzo-anno")
            rows = [
                _riga(2027, tangible_investments=350000.37, financing_interest_rate=6.0, overdraft_allowed=True),
                _riga(2028, financing_interest_rate=6.0, overdraft_allowed=True),
                _riga(2029, financing_interest_rate=6.0, overdraft_allowed=True),
            ]
            res = assumptions_service.bulk_upsert_assumptions(db, sid, rows, auto_generate=True)
            assert res["forecast_generated"] is True, res["message"]
            dettagli, errore = _dettagli(db, sid, rows)
            assert errore is None, errore

            residuo_28 = D(str(dettagli[2028]["scoperto_residuo"]))
            generato_28 = D(str(dettagli[2028]["scoperto_generato"]))
            # Le precondizioni che rendono il caso discriminante: nel 2028 c'e'
            # ancora scoperto, e non coincide con quanto acceso nell'anno.
            assert residuo_28 > 0, dettagli[2028]
            assert residuo_28 != generato_28, dettagli[2028]
            assert _eur(dettagli[2029]["oneri_scoperto"]) == _eur(residuo_28 * D("6") / D("100"))
    finally:
        engine.dispose()


# ══ Giro di correzione 1 ══════════════════════════════════════════════════════
#
# Lo scoperto e' una voce GENERATA dal piano: «bisogna dividere le voci
# patrimoniali generate dal previsionale dallo scadenziamento del pregresso» (il
# proprietario). Il commit 2641305 lo separava nei `details` ma lo mescolava
# nell'aritmetica di `sp16a`: le rate dei debiti lo pagavano al posto del proprio
# debito (I1), e un override applicato dopo il plug lasciava convivere cassa e
# scoperto gonfiando la misura (I2). Ogni test qui sotto e' rosso su 2641305.

from database.models import BalanceSheet, FinancialYear  # noqa: E402


def _con_banca(db, company_id, breve=D("12345.67")):
    """Debito bancario PREGRESSO a breve, non tondo: il confine che gli oneri e i
    rimborsi dello scoperto non devono attraversare."""
    fy = db.query(FinancialYear).filter(FinancialYear.company_id == company_id).one()
    b = db.query(BalanceSheet).filter(BalanceSheet.financial_year_id == fy.id).one()
    b.sp16a_debiti_banche_breve = breve
    b.sp16_debiti_breve = b.sp16_debiti_breve + breve
    b.sp09_disponibilita_liquide = b.sp09_disponibilita_liquide + breve
    db.commit()


def _genera(db, user, rows, banca=None):
    company_id, sid = _scenario(db, user)
    if banca is not None:
        _con_banca(db, company_id, banca)
    res = assumptions_service.bulk_upsert_assumptions(db, sid, rows, auto_generate=True)
    return sid, res


def _stress(anno, **extra):
    """Il piano stressato delle sonde di revisione: 350.000,37 investiti nel primo anno."""
    riga = _riga(anno, financing_interest_rate=6.13, overdraft_allowed=True)
    if anno == 2027:
        riga["tangible_investments"] = 350000.37
    riga.update(extra)
    return riga


def _gemello(rows):
    """Lo stesso piano SENZA lo stress e senza override: cio' che dicono i piani di
    rimborso da soli. I debiti non dipendono ne' dagli investimenti ne' dalla cassa."""
    out = []
    for r in rows:
        g = {k: v for k, v in r.items() if k not in ("tangible_investments", "sp_overrides")}
        out.append(g)
    return out


@pytest.mark.parametrize("nome, extra_primo, extra_tutti, sp17a_atteso", [
    ("debito esistente in 3 anni", {}, {"existing_debt_repayment_years": 3},
     [D("33333.33"), D("16666.66"), D("0")]),
    # Il lungo e' il kit (50.000,00) piu' il residuo del prestito MENO la rata
    # dell'anno dopo, che dal Task 17 sta a breve: catena 75.000,28 / 50.000,19 /
    # 25.000,10 / 0,01, quindi 25.000,09 a breve ogni anno (anche nel 2029: la rata
    # del 2030 cade oltre l'orizzonte, ma il calendario del contratto la conosce).
    # 50.000 + 75.000,28 − 25.000,09 = 100.000,19, poi 75.000,10 e 50.000,01.
    ("nuovo finanziamento in 4 anni", {"financing_amount": 100000.37, "financing_duration_years": 4}, {},
     [D("100000.19"), D("75000.10"), D("50000.01")]),
])
def test_i1_le_rate_pagano_il_proprio_debito_non_lo_scoperto(nome, extra_primo, extra_tutti, sp17a_atteso):
    """Su 2641305 `sp17a` restava fermo (33.333,33 tre anni di fila; 125.000,28 per
    sempre): la rata, che prende prima dal breve, pagava lo scoperto."""
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            rows = [_stress(2027, **extra_primo, **extra_tutti)] + [
                _stress(y, **extra_tutti) for y in (2028, 2029)]
            sid, res = _genera(db, f"i1-{nome}", rows)
            assert res["forecast_generated"] is True, res["message"]
            sid_g, res_g = _genera(db, f"i1-gemello-{nome}", _gemello(rows))
            assert res_g["forecast_generated"] is True, res_g["message"]
            det, _ = _dettagli(db, sid, rows)
            det_g, _ = _dettagli(db, sid_g, _gemello(rows))
            mappe = read_forecast_maps(db, sid)
            gemello = {y: sp for y, sp, _ce in read_forecast_maps(db, sid_g)}

            assert [sp["sp17a_debiti_banche_lungo"] for _y, sp, _ce in mappe] == sp17a_atteso
            assert any(D(str(det[y]["scoperto_residuo"])) > 0 for y in (2027, 2028)), det
            for y, sp, _ce in mappe:
                assert sp["sp17a_debiti_banche_lungo"] == gemello[y]["sp17a_debiti_banche_lungo"], y
                # La quota bancaria di `sp16a` e' quella del piano, con o senza scoperto.
                assert (sp["sp16a_debiti_banche_breve"] - D(str(det[y]["scoperto_residuo"]))
                        == gemello[y]["sp16a_debiti_banche_breve"] - D(str(det_g[y]["scoperto_residuo"]))), y
    finally:
        engine.dispose()


def test_i2_un_override_dopo_il_plug_non_lascia_cassa_e_scoperto_insieme():
    """Crediti forzati a 1.000,55 nel primo anno stressato.

    Su 2641305: cassa 122.995,45 E scoperto 239.459,15 insieme, e
    `cassa_assorbita` zero. Il fabbisogno vero e' lo scoperto senza override meno
    i crediti liberati: 116.463,70, con la cassa a zero.
    """
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            base_rows = [_stress(2027)]
            sid_b, res_b = _genera(db, "i2-senza", base_rows)
            assert res_b["forecast_generated"] is True, res_b["message"]
            _, sp_b, _ = read_forecast_maps(db, sid_b)[0]
            det_b, _ = _dettagli(db, sid_b, base_rows)

            rows = [_stress(2027, sp_overrides={"sp06a_crediti_clienti_breve": 1000.55})]
            sid, res = _genera(db, "i2-override", rows)
            assert res["forecast_generated"] is True, res["message"]
            _, sp, _ = read_forecast_maps(db, sid)[0]
            det, _ = _dettagli(db, sid, rows)

            liberati = sp_b["sp06a_crediti_clienti_breve"] - D("1000.55")
            atteso = D(str(det_b[2027]["scoperto_residuo"])) - liberati
            assert atteso == D("116463.70")
            assert sp["sp09_disponibilita_liquide"] == D("0.00")
            assert sp["sp16a_debiti_banche_breve"] == atteso
            assert D(str(det[2027]["scoperto_residuo"])) == atteso
            assert D(str(det[2027]["scoperto_generato"])) == atteso
            assert D(str(det[2027]["fabbisogno_picco"])) == atteso
            assert _eur(det[2027]["cassa_assorbita"]) == 30000.0
    finally:
        engine.dispose()


def test_i3_il_tetto_si_misura_sullo_scoperto_in_essere_a_fine_anno():
    """Il piano di I2 sta sotto un tetto di 120.000: genera. Su 2641305 no, perche'
    il plug aveva gia' contato 239.459,15 prima dell'override."""
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            ov = {"sp06a_crediti_clienti_breve": 1000.55}
            _sid, res = _genera(db, "i3-sotto", [_stress(2027, sp_overrides=ov, overdraft_limit=120000)])
            assert res["forecast_generated"] is True, res["message"]
            _sid2, res2 = _genera(db, "i3-sopra", [_stress(2027, sp_overrides=ov, overdraft_limit=116463.69)])
        assert res2["forecast_generated"] is False
        assert "servono 116.463,70, il tetto concesso e' 116.463,69" in res2["message"], res2["message"]
    finally:
        engine.dispose()


def test_i4_override_di_sp16a_il_totale_forzato_vince_o_la_combinazione_si_rifiuta():
    """Il totale di `sp16a` fissato da un override vince, e lo scoperto ne discende.

    Perche' a volte si rifiuta, invece di superare il totale: con `sp16a` forzato a X
    il passivo e' fissato qualunque sia la divisione di X fra banca e scoperto,
    quindi la cassa vale `passivo − attivo` comunque la si divida. Se e' negativa,
    nessuna ripartizione di X la rende non negativa: l'unica via sarebbe superare X,
    cioe' smentire l'override. Su 2641305 lo stesso caso generava con
    `scoperto_generato` 466.572,63 contro uno scoperto in essere di 239.459,15.
    """
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            _sid, rifiuto = _genera(
                db, "i4-poco", [_stress(2027, sp_overrides={"sp16a_debiti_banche_breve": 12345.67})])
            assert rifiuto["forecast_generated"] is False
            assert "incompatibile con sp16a_debiti_banche_breve forzato" in rifiuto["message"], rifiuto["message"]
            assert "servono 227.113,48 di scoperto" in rifiuto["message"], rifiuto["message"]

            rows = [_stress(2027, sp_overrides={"sp16a_debiti_banche_breve": 400000.55}, overdraft_limit=300000)]
            sid, res = _genera(db, "i4-abbastanza", rows)
            assert res["forecast_generated"] is True, res["message"]
            _, sp, _ = read_forecast_maps(db, sid)[0]
            det, _ = _dettagli(db, sid, rows)
            assert sp["sp16a_debiti_banche_breve"] == D("400000.55")
            # Senza override il fabbisogno era 239.459,15: il totale forzato lo copre e avanza.
            assert sp["sp09_disponibilita_liquide"] == D("400000.55") - D("239459.15")
            assert _eur(det[2027]["scoperto_residuo"]) == 0.0
            assert _eur(det[2027]["scoperto_generato"]) == 0.0
    finally:
        engine.dispose()


def test_ruling_37_un_fabbisogno_che_vale_zero_centesimi_non_alza():
    """Il fabbisogno si quantizza PRIMA del confronto, senza tolleranza.

    L'attivita' finanziaria forzata alla cassa del piano piu' 4 millesimi porta la
    cassa esatta a -0,004: al centesimo vale 0,00 e il piano genera (su 2641305:
    «Fabbisogno finanziario scoperto di 0,00»). Piu' 6 millesimi il centesimo e' vero,
    e il motore alza per 0,01.
    """
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            sid0, res0 = _genera(db, "r37-base", [_riga(2027)])
            assert res0["forecast_generated"] is True, res0["message"]
            _, sp0, _ = read_forecast_maps(db, sid0)[0]
            cassa = sp0["sp09_disponibilita_liquide"]
            assert cassa > 0

            sid, res = _genera(db, "r37-zero", [_riga(2027, sp_overrides={
                "sp08_attivita_finanziarie": float(cassa + D("0.004"))})])
            assert res["forecast_generated"] is True, res["message"]
            _, sp, _ = read_forecast_maps(db, sid)[0]
            assert sp["sp09_disponibilita_liquide"] == D("0.00")

            _sid, res2 = _genera(db, "r37-centesimo", [_riga(2027, sp_overrides={
                "sp08_attivita_finanziarie": float(cassa + D("0.006"))})])
        assert res2["forecast_generated"] is False
        assert _importo_scoperto(res2["message"]) == D("0.01"), res2["message"]
    finally:
        engine.dispose()


def test_ruling_38_lo_scoperto_si_rimborsa_per_primo_anche_sotto_la_cassa_minima():
    """Decisione del proprietario: «annulliamo la cassa per compensare lo scoperto».

    Cash sweep con cassa minima 20.000,55 nel 2028 e nel 2029: nel 2028 la cassa
    chiude a zero con lo scoperto ancora aperto, e `cassa_sotto_minimo` lo dice;
    nel 2029 lo scoperto e' chiuso e la cassa torna esattamente al minimo.
    """
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            sweep = {"cash_sweep_enabled": True, "cash_sweep_min_cash": 20000.55}
            rows = [_stress(2027), _stress(2028, **sweep), _stress(2029, **sweep)]
            sid, res = _genera(db, "r38", rows)
            assert res["forecast_generated"] is True, res["message"]
            mappe = {y: sp for y, sp, _ce in read_forecast_maps(db, sid)}
            det, _ = _dettagli(db, sid, rows)
        assert _eur(det[2027]["cassa_sotto_minimo"]) == 0.0       # sweep spento: nessun minimo
        assert mappe[2028]["sp09_disponibilita_liquide"] == D("0.00")
        assert D(str(det[2028]["scoperto_residuo"])) == D("108714.36")
        assert D(str(det[2028]["cassa_sotto_minimo"])) == D("20000.55")
        assert mappe[2029]["sp09_disponibilita_liquide"] == D("20000.55")
        assert _eur(det[2029]["scoperto_residuo"]) == 0.0
        assert _eur(det[2029]["cassa_sotto_minimo"]) == 0.0
    finally:
        engine.dispose()


def test_gli_oneri_stanno_sullo_scoperto_non_sul_debito_bancario_pregresso():
    """Debito bancario pregresso a breve di 12.345,67: gli oneri dello scoperto non lo
    toccano, e la quota bancaria di `sp16a` resta quella. Uccide la mutazione «oneri
    su tutto `sp16a` di apertura», che il fixture senza banca lasciava vivere."""
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            rows = [_stress(2027), _stress(2028)]
            sid, res = _genera(db, "oneri-banca", rows, banca=D("12345.67"))
            assert res["forecast_generated"] is True, res["message"]
            mappe = {y: sp for y, sp, _ce in read_forecast_maps(db, sid)}
            det, _ = _dettagli(db, sid, rows)
        residuo_27 = D(str(det[2027]["scoperto_residuo"]))
        assert residuo_27 > 0
        assert mappe[2027]["sp16a_debiti_banche_breve"] - residuo_27 == D("12345.67")
        assert D(str(det[2028]["oneri_scoperto"])) == (residuo_27 * D("6.13") / D("100")).quantize(D("0.01"))
    finally:
        engine.dispose()
