"""Banco di triage dei rilievi AMBIENTA (inbox/Verifica_piano_Ambienta_problemi.xlsx).

Spec: docs/superpowers/specs/2026-09-25-triage-rilievi-ambienta-design.md. Un test per rilievo software;
l'oracolo è il comportamento che il consulente si aspetta, quindi un test ROSSO vuol dire che il difetto
c'è. Nessun fix in questo file: il verdetto lo scrive tools/triage_rilievi.py.
"""
from decimal import Decimal as D

import pytest

from tests.rilievi_kit import BASE_BS, BASE_CE, base, genera, generato, per_anno, piano, righe

def test_kit_la_base_ambienta_genera_un_piano_a_crescita_zero():
    e = generato(genera(righe()))
    assert sorted(e.anni) == [2027, 2028, 2029]
    assert e.anni[2027][1]["ce01_ricavi_vendite"] == BASE_CE["ce01_ricavi_vendite"]
    assert e.anni[2027][0]["_total_assets"] == e.anni[2027][0]["_total_liabilities"]


Q = D("0.01")


def _q(x) -> D:
    return D(str(x)).quantize(Q)


def test_A01_scostamento_materie_applicato_dal_motore():
    """A01 · Passo 3 Costi: scostamento −5 punti sulle materie dalla crescita ricavi (5/6/7 → 0/1/2).
    Il consulente: materie 2027 = 129.308 (base × 1,00), il report dava 135.773."""
    rows = per_anno(righe(fixed_materials_percentage=0, variable_materials_growth_auto=False),
                    "revenue_growth_pct", (5, 6, 7))
    per_anno(rows, "variable_materials_growth_pct", (0, 1, 2))
    e = generato(genera(rows))
    base = BASE_CE["ce05_materie_prime"]
    attese = [_q(base), _q(base * D("1.01")), _q(base * D("1.01") * D("1.02"))]
    assert [e.anni[y][1]["ce05_materie_prime"] for y in (2027, 2028, 2029)] == attese


def test_A03_acconto_manuale_maggiore_di_zero_vince_sulla_percentuale():
    """A03 · Passo 7 Imposte: acconti 50.000 / 10.000 / 20.000 ignorati, applicato il 100% dell'imposta
    dell'anno prima. Oracolo: l'acconto versato di ogni anno è l'importo digitato."""
    rows = per_anno(righe(), "tax_advances_paid", (50000, 10000, 20000))
    e = generato(genera(rows))
    versati = [_q(e.det[y]["imposte"]["acconti_paid"]) for y in (2027, 2028, 2029)]
    assert versati == [D("50000.00"), D("10000.00"), D("20000.00")]
    # Anche sul persistito, non solo nei details: la posizione tributaria netta 2027 (crediti − debiti
    # tributari a breve) si sposta esattamente della differenza fra l'acconto digitato e quello di default.
    # Netta, non il solo sp06e: se l'acconto di default supera l'imposta resta credito, altrimenti debito.
    d = generato(genera(righe()))
    default = d.det[2027]["imposte"]["acconti_paid"]
    netta = lambda x: x.anni[2027][0]["sp06e_crediti_tributari_breve"] - x.anni[2027][0]["sp16e_debiti_tributari_breve"]
    assert _q(netta(e) - netta(d)) == _q(D("50000") - D(str(default))), (netta(e), netta(d), default)


# Il piano che il wizard scrive per «incasso 1.000 nel 2027 sui crediti oltre 12 mesi»: prodotto da
# withOltreAmount(baseBs, {}, [2027, 2028, 2029], "crediti_commerciali", 0, 1000) sulla stessa base
# (breve 1.110.226,52 + oltre 45.000 = apertura 1.155.226,52; incasso 2027 = breve + 1.000).
PREGRESSO_A04 = {
    "crediti_commerciali": {"opening": 1155226.52, "amounts": [1111226.52, 0, 0], "writeoff": None,
                            "non_incassato": False},
    "crediti_tributari_breve": {"opening": 184140.58, "amounts": [184140.58, 0, 0], "writeoff": None},
    "crediti_tributari_lungo": {"opening": 17356.48, "amounts": [0, 0, 0], "writeoff": None},
    "debiti_fornitori": {"opening": 548578.07, "amounts": [548578.07, 0, 0], "writeoff": None},
}


def test_A04_incasso_scadenziato_sui_crediti_oltre_12_mesi_arriva_allo_sp():
    """A04 · Passo 5: incasso di 1.000 nel 2027 sui crediti oltre 12 mesi; l'interfaccia dice «resta 8.769»,
    lo SP tiene il saldo intero. Qui sulla base com'è (oltre tutto su sp07a, clienti): 45.000 → 44.000 nel 2027.
    La riga del consulente è però sp07g: vedi test_A04_incasso_scadenziato_arriva_agli_altri_crediti_oltre_12_mesi."""
    rows = righe()
    rows[0]["pregresso"] = PREGRESSO_A04
    e = generato(genera(rows))
    assert e.anni[2027][0]["sp07a_crediti_clienti_lungo"] == D("44000.00")


def _a04_base(sp07a, sp07g) -> dict:
    """Base AMBIENTA con i crediti oltre 12 mesi ridistribuiti fra clienti (sp07a) e altri (sp07g): l'aggregato
    sp07 e ogni totale restano quelli del bilancio (sp07a + sp07g = 45.000)."""
    assert D(str(sp07a)) + D(str(sp07g)) == BASE_BS["sp07a_crediti_clienti_lungo"]
    return {"sp07a_crediti_clienti_lungo": D(str(sp07a)), "sp07g_crediti_altri_lungo": D(str(sp07g))}


# Per le due varianti il piano del wizard è lo STESSO PREGRESSO_A04: withOltreAmount(base modificata, {}, [2027,
# 2028, 2029], "crediti_commerciali", 0, 1000) dà lo stesso JSON, perché massaOltre dei crediti commerciali è
# creditiComponents(bs).long, che comprende sp07g (misurato con un Vitest usa e getta, 2026-09-25).


@pytest.mark.parametrize("sp07a, sp07g", [
    pytest.param(0, 45000, id="tutto_su_sp07g"),
    pytest.param(35231, 9769, id="mix_del_consulente", marks=pytest.mark.xfail(
        strict=True, raises=AssertionError,
        reason="A04 confermato dal triage 2026-09-25: con clienti e altri crediti oltre 12 mesi insieme, "
               "l'incasso scadenziato si ripartisce per proporzione (sp07g 2027 = 9.551,91, non 8.769) "
               "— togli il marcatore quando il fix lo fa passare")),
])
def test_A04_incasso_scadenziato_arriva_agli_altri_crediti_oltre_12_mesi(sp07a, sp07g):
    """A04 · la riga del consulente è «Altri crediti oltre 12 mesi» = sp07g (9.769, «resta 8.769»), non sp07a.
    Il motore scrive il residuo del piano sull'aggregato sp07 e lo ripartisce per proporzione fra
    sp07a/b/c/d/g (forecast_engine.py, blocco crediti_commerciali). Oracolo del consulente: la riga su cui
    ha scadenziato l'incasso scende di esattamente 1.000 nel 2027 — tutto_su_sp07g: 45.000 → 44.000;
    mix_del_consulente: sp07g 9.769 → 8.769."""
    rows = righe()
    rows[0]["pregresso"] = PREGRESSO_A04
    e = generato(genera(rows, bs=_a04_base(sp07a, sp07g)))
    assert e.anni[2027][0]["sp07g_crediti_altri_lungo"] == D(str(sp07g)) - D("1000"), e.anni[2027][0]


def test_A05_immobilizzazioni_finanziarie_senza_regola_non_seguono_i_ricavi():
    """A05 · Passo 6: regola «Manuale» sulle immobilizzazioni finanziarie con i campi 2027-2029 vuoti; l'output
    le fa crescere coi ricavi (52.550 → 55.178 / 58.488 / 62.582) con uscite di cassa per investimenti.
    Campi vuoti = nessun override e nessuna indicizzazione di sp04. Oracolo: sp04 resta 52.550 ogni anno."""
    rows = per_anno(righe(), "revenue_growth_pct", (5, 6, 7))
    e = generato(genera(rows))
    assert [e.anni[y][0]["sp04_immob_finanziarie"] for y in (2027, 2028, 2029)] == [BASE_BS["sp04_immob_finanziarie"]] * 3


def test_A06_previdenziali_seguono_il_personale_se_la_tendina_lo_dice():
    """A06 · Passo 6: tendina «cresce con il costo del personale», casella non spuntata; l'output cresce coi
    ricavi. Oracolo: sp16f cresce come ce08 (personale +3/4/4, ricavi +5/6/7)."""
    rows = per_anno(righe(sp_indexing={"sp16f": "personale"}, previdenza_scales_with_personnel=False),
                    "revenue_growth_pct", (5, 6, 7))
    per_anno(rows, "personnel_growth_pct", (3, 4, 4))
    e = generato(genera(rows))
    b16, b08 = BASE_BS["sp16f_debiti_previdenza_breve"], BASE_CE["ce08_costi_personale"]
    for y in (2027, 2028, 2029):
        sp, ce = e.anni[y]
        atteso = b16 * ce["ce08_costi_personale"] / b08
        assert abs(sp["sp16f_debiti_previdenza_breve"] - atteso) < D("1"), (y, sp["sp16f_debiti_previdenza_breve"], atteso)


def test_B01_variazione_rimanenze_del_ce_segue_lo_sp():
    """B01 · Passo 4 / CE B11, fix: le materie prime (sp05a) si calcolano nel CE dal consumo
    dell'anno (ce05 + apertura − chiusura), prima delle imposte, e lo SP legge la chiusura da
    li' — mai il contrario. Su questa base AMBIENTA (senza dettaglio sp05b–e) l'intero
    aggregato sp05 coincide con le materie, quindi la Δ dello SP e ce10 devono coincidere
    esattamente anno per anno. Oracolo: ce10 di ogni anno = rimanenze di fine anno − rimanenze
    d'inizio (convenzione OIC B11: un aumento delle rimanenze di materie riduce il costo)."""
    rows = per_anno(righe(dio_days=22), "revenue_growth_pct", (5, 6, 7))
    e = generato(genera(rows))
    prec = BASE_BS["sp05_rimanenze"]
    for y in (2027, 2028, 2029):
        sp, ce = e.anni[y]
        delta = sp["sp05_rimanenze"] - prec
        # abs() su entrambi: il segno di ce10 dipende dalla convenzione del campo (variazione come costo o come
        # rettifica), che non è il rilievo. Il rilievo è l'importo: ce10 non segue la Δ rimanenze dello SP.
        assert abs(abs(ce["ce10_var_rimanenze_mat_prime"]) - abs(delta)) < D("1"), (y, ce["ce10_var_rimanenze_mat_prime"], delta)
        prec = sp["sp05_rimanenze"]


def test_B02_ammortamento_dei_cespiti_esistenti_si_ferma_al_residuo():
    """B02 · Passo 6, fix 2026-09-26: materiali esistenti 72.797 netti, quota base 36.040/anno, ora si
    ferma al residuo invece di continuare alla quota piena. Con un investimento di 250.000 nel 2027 al
    10% (meta' aliquota nell'anno d'ingresso, E05): il nuovo cespite ammortizza 12.500 nel 2027 e 25.000
    pieni dal 2028; l'esistente si esaurisce nel 2029 (residuo 716,59 invece dei 36.040 di prima),
    quindi 2029 = 716,59 + 25.000 = 25.716,59. L'oracolo non cambia con la meta' aliquota: la meta'
    riguarda solo l'anno d'ingresso del nuovo cespite (2027), non il 2029."""
    rows = righe(depreciation_rate=10)
    rows[0]["tangible_investments"] = 250000
    e = generato(genera(rows))
    assert e.anni[2029][1]["ce09b_ammort_materiali"] == D("25716.59")


def test_B03_tfr_uguale_retribuzioni_diviso_13_5():
    """B03 · Passo 3/6: l'accantonamento è il residuo personale − salari − oneri, non retribuzioni/13,5
    come dice l'interfaccia. Oracolo: ce08a = ce08b / 13,5 in ogni anno."""
    e = generato(genera(per_anno(righe(), "personnel_growth_pct", (3, 4, 4))))
    for y in (2027, 2028, 2029):
        ce = e.anni[y][1]
        assert abs(ce["ce08a_tfr_accrual"] - ce["ce08b_salari_stipendi"] / D("13.5")) < D("1"), (y, ce["ce08a_tfr_accrual"])


MUTUO_A = {"name": "Finanziamento A", "amount": 0, "opening_residual": 467528.52, "interest_rate": 4,
           "grace_years": 0, "balloon_pct": 0, "duration_years": None,
           "repayments": [53409, 53409, 53409, 53409]}


def _banche(fidi: float, residuo: float) -> dict:
    return {"financing_loans": [{**MUTUO_A, "opening_residual": residuo}], "bank_lines_amount": fidi,
            "bank_lines_rule": "costante", "bank_lines_rate": 6}


def test_B04_fidi_e_residui_che_non_quadrano_col_bilancio_si_rifiutano():
    """B04 · Passo 5: fidi 311.000 + residuo ≠ debito bancario di bilancio (scarto 11.000), avviso rosso ma
    il motore calcola coi fidi ridotti in silenzio. Oracolo: generazione respinta e scarto nel messaggio."""
    banche = BASE_BS["sp16a_debiti_banche_breve"] + BASE_BS["sp17a_debiti_banche_lungo"]  # 960.937,42
    residuo = float(banche - D("300000"))  # il residuo quadra coi fidi a 300.000: lo scarto sono i fidi a 311.000
    rows = righe()
    rows[0].update(_banche(311000, residuo))
    e = genera(rows)
    assert e.res["forecast_generated"] is False
    assert "11.000" in e.res["message"], e.res["message"]


def test_B05_rata_oltre_orizzonte_non_scadenziata_sta_a_breve():
    """B05 · lo scenario del consulente: il piano del Finanziamento A scadenzia solo 2027-2029 e a fine 2029 resta
    un residuo (360.710 nel foglio). Oracolo del consulente: a breve almeno la rata dell'ultimo anno (53.409),
    cioè banche a breve 2029 ≥ fidi 300.000 + 53.409."""
    banche = BASE_BS["sp16a_debiti_banche_breve"] + BASE_BS["sp17a_debiti_banche_lungo"]
    rows = righe()
    rows[0].update(_banche(300000, float(banche - D("300000"))))
    rows[0]["financing_loans"][0]["repayments"] = [53409, 53409, 53409]
    e = generato(genera(rows))
    assert e.anni[2029][0]["sp16a_debiti_banche_breve"] >= D("353409.00")


def test_B05_bis_rata_2030_scadenziata_sta_a_breve():
    """B05 · variante: il piano scadenzia anche la rata 2030. Oracolo: banche a breve 2029 = fidi + rata 2030
    scadenziata (53.409)."""
    banche = BASE_BS["sp16a_debiti_banche_breve"] + BASE_BS["sp17a_debiti_banche_lungo"]
    rows = righe()
    rows[0].update(_banche(300000, float(banche - D("300000"))))
    e = generato(genera(rows))
    assert e.anni[2029][0]["sp16a_debiti_banche_breve"] == D("353409.00")


def test_E05_ammortamento_a_meta_aliquota_nel_primo_anno():
    """E05 · decisione del proprietario (2026-09-26): un investimento si ammortizza a metà aliquota
    nell'anno in cui entra. Investimento 2027 di 100.000 al 10%: quota 2027 del nuovo = 5.000."""
    rows = righe(depreciation_rate=10)
    rows[0]["tangible_investments"] = 100000
    e = generato(genera(rows))
    quota_nuovo = e.anni[2027][1]["ce09b_ammort_materiali"] - BASE_CE["ce09b_ammort_materiali"]
    assert quota_nuovo == D("5000.00")


def test_E05_straordinari_a_zero_nel_piano():
    """E05 · decisione del proprietario (2026-09-26): proventi e oneri straordinari della base non si
    proiettano; valgono zero in ogni anno di piano, salvo override."""
    straord = {"ce18_proventi_straordinari": D("1234.00"), "ce19_oneri_straordinari": D("1234.00")}
    e = generato(genera(righe(), ce=straord))
    for y in (2027, 2028, 2029):
        ce = e.anni[y][1]
        assert (ce["ce18_proventi_straordinari"], ce["ce19_oneri_straordinari"]) == (D("0.00"), D("0.00")), y


def _bp():
    pytest.importorskip("backend.app.renderers.business_plan.data")


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="A01-bis confermato dal triage 2026-09-25: il PDF in bozza "
                    "tace sul previsionale vecchio dopo un salvataggio respinto"
                    " — togli il marcatore quando il fix lo fa passare")
def test_A01_bis_salvataggio_respinto_non_stampa_il_previsionale_vecchio_come_buono():
    """A01/A04/B04 · ipotesi della verifica sul codice: un salvataggio respinto risponde 200, a schermo resta il
    previsionale vecchio e il report lo stampa. Oracolo: il report è bloccato E il PDF in bozza dice che il
    previsionale non corrisponde alle ipotesi salvate."""
    _bp()
    from backend.app.renderers.business_plan.document import render_business_plan
    buone = righe()
    respinte = righe()
    banche = BASE_BS["sp16a_debiti_banche_breve"] + BASE_BS["sp17a_debiti_banche_lungo"]
    respinte[0].update(_banche(311000, float(banche - D("300000"))))
    e = genera(respinte, prima=buone, report=True)
    if e.res["forecast_generated"] is not False:
        pytest.fail("precondizione: il salvataggio doveva essere respinto")
    if e.rep is None:
        pytest.fail("precondizione: il report non si costruisce sul previsionale vecchio")
    assert e.rep.readiness.status == "blocked", e.rep.readiness
    import fitz
    pdf = render_business_plan(e.data)
    testo = "".join(p.get_text() for p in fitz.open(stream=pdf, filetype="pdf")).lower()
    frasi = ("non aggiornat", "ipotesi salvate", "da rigenerare", "precedente alle ipotesi")
    assert any(f in testo for f in frasi), "il PDF in bozza tace sul previsionale vecchio"


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="A02 confermato dal triage 2026-09-25: il BEP del report usa "
                    "la ripartizione fissi/variabili degli slider di default, non quella del motore"
                    " — togli il marcatore quando il fix lo fa passare")
def test_A02_bep_del_report_usa_la_ripartizione_del_motore():
    """A02 · Report sez. 4: il BEP del report non usa la ripartizione fissi/variabili degli slider (60/40 di
    default). Oracolo: costi variabili e fatturato di pareggio del report = details['pareggio'] del motore."""
    _bp()
    rows = righe(fixed_materials_percentage=0, fixed_services_percentage=50)
    e = generato(genera(rows, report=True))
    for i, y in enumerate((2027, 2028, 2029)):
        par = e.det[y]["pareggio"]
        assert abs(D(str(piano(e.data, "costi_variabili")[i])) - par["costi_variabili"]) < D("1"), y
        assert abs(D(str(piano(e.data, "bep")[i])) - par["fatturato_pareggio"]) < D("1"), y


def _con_rimborsi():
    banche = BASE_BS["sp16a_debiti_banche_breve"] + BASE_BS["sp17a_debiti_banche_lungo"]
    rows = righe()
    rows[0].update(_banche(300000, float(banche - D("300000"))))
    return rows


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="C01 confermato dal triage 2026-09-25: il DSCR del report è "
                    "(MOL-imposte)/oneri, senza la quota capitale al denominatore"
                    " — togli il marcatore quando il fix lo fa passare")
def test_C01_il_dscr_del_report_comprende_la_quota_capitale():
    """C01 · Report sez. 1, 6, All. D: «DSCR proxy» = (EBITDA − imposte) / oneri, senza quota capitale.
    Oracolo: DSCR = (MOL − imposte) / (oneri + quota capitale); con rimborsi 53.409 è molto sotto il proxy.
    Il numeratore (MOL − imposte) è la formula del consulente, non una scelta del banco: un fix che adottasse
    un altro numeratore (es. flusso di cassa operativo) va confrontato con lui, non con questo test."""
    _bp()
    e = generato(genera(_con_rimborsi(), report=True))
    ce = e.anni[2027][1]
    mol = e.data.v("ebitda")[e.data.plan_idx[0]]
    atteso = (D(str(mol)) - ce["ce20_imposte"]) / (ce["ce15_oneri_finanziari"] + D("53409"))
    assert abs(D(str(piano(e.data, "dscr")[0])) - atteso) < D("0.01"), (piano(e.data, "dscr")[0], atteso)


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="C02 confermato dal triage 2026-09-25: il DSO del report include "
                    "crediti tributari e oltre 12 mesi, non i soli crediti commerciali"
                    " — togli il marcatore quando il fix lo fa passare")
def test_C02_dso_sui_soli_crediti_commerciali():
    """C02 · Report sez. 1, 7, All. E: «DSO» su tutti i crediti (tributari e oltre 12 mesi compresi).
    Oracolo: DSO 2026 = clienti (sp06a + sp07a) / ricavi × 360."""
    _bp()
    e = generato(genera(righe(), report=True))
    atteso = (BASE_BS["sp06a_crediti_clienti_breve"] + BASE_BS["sp07a_crediti_clienti_lungo"]) \
        / BASE_CE["ce01_ricavi_vendite"] * 360
    assert abs(D(str(base(e.data, "dso"))) - atteso) < D("1"), (base(e.data, "dso"), atteso)


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="C03 confermato dal triage 2026-09-25: il ROD del report divide "
                    "per il totale debiti (fornitori compresi), non per i soli debiti finanziari"
                    " — togli il marcatore quando il fix lo fa passare")
def test_C03_rod_sui_debiti_finanziari():
    """C03 · ROD = oneri finanziari / totale debiti (fornitori compresi). Oracolo: oneri / debiti finanziari
    (banche + altri finanziatori), in percentuale."""
    _bp()
    e = generato(genera(righe(), report=True))
    fin = BASE_BS["sp16a_debiti_banche_breve"] + BASE_BS["sp17a_debiti_banche_lungo"] \
        + BASE_BS["sp17b_debiti_altri_finanz_lungo"]
    atteso = BASE_CE["ce15_oneri_finanziari"] / fin * 100
    assert abs(D(str(base(e.data, "rod"))) - atteso) < D("0.05"), (base(e.data, "rod"), atteso)


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="C04 confermato dal triage 2026-09-25: la PFN del report esclude "
                    "gli altri finanziatori a lungo, che l'interfaccia (finDebt) include"
                    " — togli il marcatore quando il fix lo fa passare")
def test_C04_pfn_del_report_comprende_gli_altri_finanziatori():
    """C04 · PFN del report esclude gli altri finanziatori, l'interfaccia (budget-piano-step.ts, finDebt)
    li include. Oracolo: PFN 2026 = banche + altri finanziatori + obbligazioni − cassa."""
    _bp()
    e = generato(genera(righe(), report=True))
    atteso = BASE_BS["sp16a_debiti_banche_breve"] + BASE_BS["sp17a_debiti_banche_lungo"] \
        + BASE_BS["sp17b_debiti_altri_finanz_lungo"] - BASE_BS["sp09_disponibilita_liquide"]
    assert abs(D(str(base(e.data, "pfn"))) - atteso) < D("1"), (base(e.data, "pfn"), atteso)


def _analitico(data, etichetta: str):
    for r in data.indicators_analytical:
        if r.label.strip().lower() == etichetta.lower():
            return r
    raise AssertionError(f"indicatore «{etichetta}» assente dall'Allegato E: "
                         f"{[r.label for r in data.indicators_analytical]}")


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="C05 confermato dal triage 2026-09-25: liquidità corrente sez. 8 "
                    "e Current Ratio (ILC) dell'All. E danno due valori diversi nello stesso documento"
                    " — togli il marcatore quando il fix lo fa passare")
def test_C05_un_solo_current_ratio_nel_documento():
    """C05 · Liquidità corrente sez. 8 = 1,43×, Current Ratio All. E = 1,29×. Oracolo: stesso valore.
    Ruling: l'etichetta esatta nel catalogo è «Current Ratio (ILC)», non «Current Ratio»
    (contracts/final_report_dossier_catalog.json:2130)."""
    _bp()
    e = generato(genera(righe(), report=True))
    sez8 = D(str(base(e.data, "liquidita_corrente")))
    all_e = D(str(_analitico(e.data, "Current Ratio (ILC)").values[0]))
    assert abs(sez8 - all_e) < D("0.01"), (sez8, all_e)


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="C06 confermato dal triage 2026-09-25: «Indice di Indebitamento» "
                    "nell'All. E è immobilizzazioni/PN, non debiti totali/PN"
                    " — togli il marcatore quando il fix lo fa passare")
def test_C06_indice_di_indebitamento_e_debiti_su_patrimonio():
    """C06 · All. E: «Indice di indebitamento» = immobilizzazioni / PN. Oracolo: debiti totali / PN oppure totale
    attivo / PN — il consulente accetta l'una o l'altra definizione; immobilizzazioni / PN no."""
    _bp()
    e = generato(genera(righe(), report=True))
    pn = BASE_BS["sp11_capitale"] + BASE_BS["sp12_riserve"] + BASE_BS["sp13_utile_perdita"]
    debiti_pn = (BASE_BS["sp16_debiti_breve"] + BASE_BS["sp17_debiti_lungo"]) / pn
    attivo = sum(BASE_BS[k] for k in BASE_BS if k[:4] in {f"sp{i:02d}" for i in range(1, 11)} and len(k) > 5
                 and k[4] == "_")
    attivo_pn = attivo / pn
    val = D(str(_analitico(e.data, "Indice di Indebitamento").values[0]))
    assert abs(val - debiti_pn) < D("0.01") or abs(val - attivo_pn) < D("0.01"), (val, debiti_pn, attivo_pn)


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="C07 confermato dal triage 2026-09-25: il TFR non è incluso fra "
                    "le fonti consolidate della copertura immobilizzazioni"
                    " — togli il marcatore quando il fix lo fa passare")
def test_C07_copertura_immobilizzazioni_con_il_tfr():
    """C07 · Sez. 8, All. D: il TFR non è fra le fonti consolidate. Oracolo (in %):
    (PN + debiti a lungo + TFR) / immobilizzazioni × 100."""
    _bp()
    e = generato(genera(righe(), report=True))
    pn = BASE_BS["sp11_capitale"] + BASE_BS["sp12_riserve"] + BASE_BS["sp13_utile_perdita"]
    immob = BASE_BS["sp02_immob_immateriali"] + BASE_BS["sp03_immob_materiali"] + BASE_BS["sp04_immob_finanziarie"]
    atteso = (pn + BASE_BS["sp17_debiti_lungo"] + BASE_BS["sp15_tfr"]) / immob * 100
    assert abs(D(str(base(e.data, "copertura_immob"))) - atteso) < D("0.1"), (base(e.data, "copertura_immob"), atteso)


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="C08 confermato dal triage 2026-09-25: erogazione e rimborsi "
                    "escono compensati sulla stessa riga del rendiconto, non su righe separate"
                    " — togli il marcatore quando il fix lo fa passare")
def test_C08_erogazioni_e_rimborsi_su_righe_separate():
    """C08 · Sez. 1, 5, All. C: nel 2027 erogazione 280.000 e rimborsi 88.409 compensati (191.591).
    Oracolo: il rendiconto 2027 porta nuovo debito = 280.000 e rimborsi ≥ 53.409, non il netto."""
    _bp()
    rows = _con_rimborsi()
    rows[0]["financing_loans"].append({"name": "Nuovo", "amount": 280000, "opening_residual": 0,
                                       "duration_years": 8, "interest_rate": 4.5, "grace_years": 0,
                                       "balloon_pct": 0})
    e = generato(genera(rows, report=True))
    nuovo, rimb = piano(e.data, "cf_nuovo_debito")[0], piano(e.data, "cf_rimborsi")[0]
    assert abs(D(str(nuovo)) - D("280000")) < D("1"), (nuovo, rimb)
    assert D(str(rimb)) >= D("53409"), (nuovo, rimb)


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="C09 confermato dal triage 2026-09-25: il testo narrativo non cita "
                    "la percentuale oneri/MOL della colonna base — togli il marcatore quando il fix lo fa passare")
def test_C09_oneri_su_mol_parte_dalla_colonna_base():
    """C09 · Sez. 1: «dal 24,54% al 10,71%» ma il 2026 F è 30,73%. Oracolo: il testo cita il valore della
    colonna base."""
    _bp()
    from backend.app.renderers.business_plan import fmt
    from backend.app.renderers.business_plan.narrative import key_points
    e = generato(genera(_con_rimborsi(), report=True))
    testo = " ".join(t for _, t in key_points(e.data))
    assert fmt.pct(base(e.data, "of_mol")) in testo, (fmt.pct(base(e.data, "of_mol")), testo)
