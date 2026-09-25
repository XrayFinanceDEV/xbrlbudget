"""Banco di triage dei rilievi AMBIENTA (inbox/Verifica_piano_Ambienta_problemi.xlsx).

Spec: docs/superpowers/specs/2026-09-25-triage-rilievi-ambienta-design.md. Un test per rilievo software;
l'oracolo è il comportamento che il consulente si aspetta, quindi un test ROSSO vuol dire che il difetto
c'è. Nessun fix in questo file: il verdetto lo scrive tools/triage_rilievi.py.
"""
from decimal import Decimal as D

import pytest

from tests.rilievi_kit import BASE_BS, BASE_CE, base, genera, per_anno, piano, righe

SP = "sp"  # solo per leggibilità dei commenti


def test_kit_la_base_ambienta_genera_un_piano_a_crescita_zero():
    e = genera(righe())
    assert e.res["forecast_generated"] is True, e.res["message"]
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
    e = genera(rows)
    assert e.res["forecast_generated"] is True, e.res["message"]
    base = BASE_CE["ce05_materie_prime"]
    attese = [_q(base), _q(base * D("1.01")), _q(base * D("1.01") * D("1.02"))]
    assert [e.anni[y][1]["ce05_materie_prime"] for y in (2027, 2028, 2029)] == attese


def test_A03_acconto_manuale_maggiore_di_zero_vince_sulla_percentuale():
    """A03 · Passo 7 Imposte: acconti 50.000 / 10.000 / 20.000 ignorati, applicato il 100% dell'imposta
    dell'anno prima. Oracolo: l'acconto versato di ogni anno è l'importo digitato."""
    rows = per_anno(righe(), "tax_advances_paid", (50000, 10000, 20000))
    e = genera(rows)
    assert e.res["forecast_generated"] is True, e.res["message"]
    versati = [_q(e.det[y]["imposte"]["acconti_paid"]) for y in (2027, 2028, 2029)]
    assert versati == [D("50000.00"), D("10000.00"), D("20000.00")]


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
    lo SP tiene il saldo intero. Qui: oltre 45.000 → 44.000 nel 2027, e la generazione non è respinta."""
    rows = righe()
    rows[0]["pregresso"] = PREGRESSO_A04
    e = genera(rows)
    assert e.res["forecast_generated"] is True, e.res["message"]
    assert e.anni[2027][0]["sp07a_crediti_clienti_lungo"] == D("44000.00")


def test_A05_immobilizzazioni_finanziarie_senza_regola_non_seguono_i_ricavi():
    """A05 · Passo 6: regola «Manuale» sulle immobilizzazioni finanziarie con i campi 2027-2029 vuoti; l'output
    le fa crescere coi ricavi (52.550 → 55.178 / 58.488 / 62.582) con uscite di cassa per investimenti.
    Campi vuoti = nessun override e nessuna indicizzazione di sp04. Oracolo: sp04 resta 52.550 ogni anno."""
    rows = per_anno(righe(), "revenue_growth_pct", (5, 6, 7))
    e = genera(rows)
    assert e.res["forecast_generated"] is True, e.res["message"]
    assert [e.anni[y][0]["sp04_immob_finanziarie"] for y in (2027, 2028, 2029)] == [BASE_BS["sp04_immob_finanziarie"]] * 3


def test_A06_previdenziali_seguono_il_personale_se_la_tendina_lo_dice():
    """A06 · Passo 6: tendina «cresce con il costo del personale», casella non spuntata; l'output cresce coi
    ricavi. Oracolo: sp16f cresce come ce08 (personale +3/4/4, ricavi +5/6/7)."""
    rows = per_anno(righe(sp_indexing={"sp16f": "personale"}, previdenza_scales_with_personnel=False),
                    "revenue_growth_pct", (5, 6, 7))
    per_anno(rows, "personnel_growth_pct", (3, 4, 4))
    e = genera(rows)
    assert e.res["forecast_generated"] is True, e.res["message"]
    b16, b08 = BASE_BS["sp16f_debiti_previdenza_breve"], BASE_CE["ce08_costi_personale"]
    for y in (2027, 2028, 2029):
        sp, ce = e.anni[y]
        atteso = b16 * ce["ce08_costi_personale"] / b08
        assert abs(sp["sp16f_debiti_previdenza_breve"] - atteso) < D("1"), (y, sp["sp16f_debiti_previdenza_breve"], atteso)


@pytest.mark.xfail(strict=True, reason="B01 confermato dal triage 2026-09-25: nel CE la variazione "
                    "rimanenze resta ancorata al valore 2026, mentre nello SP le rimanenze seguono il DIO")
def test_B01_variazione_rimanenze_del_ce_segue_lo_sp():
    """B01 · Passo 4 / CE B11: nello SP le rimanenze seguono il DIO, nel CE la variazione resta al valore
    2026. Oracolo: ce10 di ogni anno = rimanenze di fine anno − rimanenze d'inizio (convenzione del CE:
    un aumento delle rimanenze di materie riduce il costo)."""
    rows = per_anno(righe(dio_days=22), "revenue_growth_pct", (5, 6, 7))
    e = genera(rows)
    assert e.res["forecast_generated"] is True, e.res["message"]
    prec = BASE_BS["sp05_rimanenze"]
    for y in (2027, 2028, 2029):
        sp, ce = e.anni[y]
        delta = sp["sp05_rimanenze"] - prec
        assert abs(abs(ce["ce10_var_rimanenze_mat_prime"]) - abs(delta)) < D("1"), (y, ce["ce10_var_rimanenze_mat_prime"], delta)
        prec = sp["sp05_rimanenze"]


@pytest.mark.xfail(strict=True, reason="B02 confermato dal triage 2026-09-25: l'ammortamento dei "
                    "cespiti materiali esistenti continua alla quota piena anche oltre il residuo netto")
def test_B02_ammortamento_dei_cespiti_esistenti_si_ferma_al_residuo():
    """B02 · Passo 6: materiali esistenti 72.797 netti ammortizzati 36.040/anno anche oltre il residuo.
    Con un investimento di 250.000 nel 2027 al 10%: 2027 = 36.040 + 25.000, 2028 = 36.040 + 25.000,
    2029 = residuo esistente (72.796,59 − 72.080 = 716,59) + 25.000."""
    rows = righe(depreciation_rate=10)
    rows[0]["tangible_investments"] = 250000
    e = genera(rows)
    assert e.res["forecast_generated"] is True, e.res["message"]
    assert e.anni[2029][1]["ce09b_ammort_materiali"] == D("25716.59")


@pytest.mark.xfail(strict=True, reason="B03 confermato dal triage 2026-09-25: l'accantonamento TFR "
                    "è il residuo del costo del personale, non retribuzioni/13,5 come dice l'interfaccia")
def test_B03_tfr_uguale_retribuzioni_diviso_13_5():
    """B03 · Passo 3/6: l'accantonamento è il residuo personale − salari − oneri, non retribuzioni/13,5
    come dice l'interfaccia. Oracolo: ce08a = ce08b / 13,5 in ogni anno."""
    e = genera(per_anno(righe(), "personnel_growth_pct", (3, 4, 4)))
    assert e.res["forecast_generated"] is True, e.res["message"]
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


def test_B05_ultimo_anno_la_rata_successiva_sta_a_breve():
    """B05 · Passo 5 → SP 2029: oltre l'orizzonte la rata 2030 del Finanziamento A non è classificata
    entro 12 mesi. Oracolo: banche a breve 2029 = fidi + rata 2030 scadenziata (53.409)."""
    banche = BASE_BS["sp16a_debiti_banche_breve"] + BASE_BS["sp17a_debiti_banche_lungo"]
    rows = righe()
    rows[0].update(_banche(300000, float(banche - D("300000"))))
    e = genera(rows)
    assert e.res["forecast_generated"] is True, e.res["message"]
    assert e.anni[2029][0]["sp16a_debiti_banche_breve"] == D("353409.00")


@pytest.mark.xfail(strict=True, reason="B05 confermato dal triage 2026-09-25: quando il piano scadenzia "
                    "solo 2027-2029 e resta un residuo, la rata dell'ultimo anno non finisce a breve")
def test_B05_bis_rata_oltre_orizzonte_non_scadenziata():
    """B05 · variante del foglio: il piano scadenzia solo 2027-2029 e a fine 2029 resta un residuo.
    Oracolo del consulente: a breve almeno la rata dell'ultimo anno (53.409)."""
    banche = BASE_BS["sp16a_debiti_banche_breve"] + BASE_BS["sp17a_debiti_banche_lungo"]
    rows = righe()
    rows[0].update(_banche(300000, float(banche - D("300000"))))
    rows[0]["financing_loans"][0]["repayments"] = [53409, 53409, 53409]
    e = genera(rows)
    assert e.res["forecast_generated"] is True, e.res["message"]
    assert e.anni[2029][0]["sp16a_debiti_banche_breve"] >= D("353409.00")


def test_E05_caratterizzazione_ammortamento_primo_anno_e_straordinari():
    """E05 · caratterizzazione, non verdetto (spec §4): registra lo stato. Investimento 2027 di 100.000 al 10%:
    quota 2027 del nuovo = 10.000 (aliquota piena). Oneri diversi 2026 ripetuti ogni anno."""
    rows = righe(depreciation_rate=10)
    rows[0]["tangible_investments"] = 100000
    e = genera(rows)
    assert e.res["forecast_generated"] is True, e.res["message"]
    quota_nuovo = e.anni[2027][1]["ce09b_ammort_materiali"] - BASE_CE["ce09b_ammort_materiali"]
    assert quota_nuovo == D("10000.00")  # aliquota piena nel primo anno: stato di oggi


def _bp():
    pytest.importorskip("app.renderers.business_plan.data")
    pytest.importorskip("backend.app.renderers.business_plan.data")


@pytest.mark.xfail(strict=True, reason="A01-bis confermato dal triage 2026-09-25: il PDF in bozza "
                    "tace sul previsionale vecchio dopo un salvataggio respinto")
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
    assert e.res["forecast_generated"] is False
    assert e.rep is not None, "il report non si costruisce sul previsionale vecchio"
    assert e.rep.readiness.status == "blocked", e.rep.readiness
    import fitz
    pdf = render_business_plan(e.data)
    testo = "".join(p.get_text() for p in fitz.open(stream=pdf, filetype="pdf")).lower()
    assert "non aggiornat" in testo or "ipotesi salvate" in testo, "il PDF in bozza tace sul previsionale vecchio"


@pytest.mark.xfail(strict=True, reason="A02 confermato dal triage 2026-09-25: il BEP del report usa "
                    "la ripartizione fissi/variabili degli slider di default, non quella del motore")
def test_A02_bep_del_report_usa_la_ripartizione_del_motore():
    """A02 · Report sez. 4: il BEP del report non usa la ripartizione fissi/variabili degli slider (60/40 di
    default). Oracolo: costi variabili e fatturato di pareggio del report = details['pareggio'] del motore."""
    _bp()
    rows = righe(fixed_materials_percentage=0, fixed_services_percentage=50)
    e = genera(rows, report=True)
    assert e.res["forecast_generated"] is True, e.res["message"]
    for i, y in enumerate((2027, 2028, 2029)):
        par = e.det[y]["pareggio"]
        assert abs(D(str(piano(e.data, "costi_variabili")[i])) - par["costi_variabili"]) < D("1"), y
        assert abs(D(str(piano(e.data, "bep")[i])) - par["fatturato_pareggio"]) < D("1"), y


def _con_rimborsi():
    banche = BASE_BS["sp16a_debiti_banche_breve"] + BASE_BS["sp17a_debiti_banche_lungo"]
    rows = righe()
    rows[0].update(_banche(300000, float(banche - D("300000"))))
    return rows


@pytest.mark.xfail(strict=True, reason="C01 confermato dal triage 2026-09-25: il DSCR del report è "
                    "(MOL-imposte)/oneri, senza la quota capitale al denominatore")
def test_C01_il_dscr_del_report_comprende_la_quota_capitale():
    """C01 · Report sez. 1, 6, All. D: «DSCR proxy» = (EBITDA − imposte) / oneri, senza quota capitale.
    Oracolo: DSCR = (MOL − imposte) / (oneri + quota capitale); con rimborsi 53.409 è molto sotto il proxy."""
    _bp()
    e = genera(_con_rimborsi(), report=True)
    assert e.res["forecast_generated"] is True, e.res["message"]
    ce = e.anni[2027][1]
    mol = e.data.v("ebitda")[e.data.plan_idx[0]]
    atteso = (D(str(mol)) - ce["ce20_imposte"]) / (ce["ce15_oneri_finanziari"] + D("53409"))
    assert abs(D(str(piano(e.data, "dscr")[0])) - atteso) < D("0.01"), (piano(e.data, "dscr")[0], atteso)


@pytest.mark.xfail(strict=True, reason="C02 confermato dal triage 2026-09-25: il DSO del report include "
                    "crediti tributari e oltre 12 mesi, non i soli crediti commerciali")
def test_C02_dso_sui_soli_crediti_commerciali():
    """C02 · Report sez. 1, 7, All. E: «DSO» su tutti i crediti (tributari e oltre 12 mesi compresi).
    Oracolo: DSO 2026 = clienti (sp06a + sp07a) / ricavi × 360."""
    _bp()
    e = genera(righe(), report=True)
    assert e.res["forecast_generated"] is True, e.res["message"]
    atteso = (BASE_BS["sp06a_crediti_clienti_breve"] + BASE_BS["sp07a_crediti_clienti_lungo"]) \
        / BASE_CE["ce01_ricavi_vendite"] * 360
    assert abs(D(str(base(e.data, "dso"))) - atteso) < D("1"), (base(e.data, "dso"), atteso)


@pytest.mark.xfail(strict=True, reason="C03 confermato dal triage 2026-09-25: il ROD del report divide "
                    "per il totale debiti (fornitori compresi), non per i soli debiti finanziari")
def test_C03_rod_sui_debiti_finanziari():
    """C03 · ROD = oneri finanziari / totale debiti (fornitori compresi). Oracolo: oneri / debiti finanziari
    (banche + altri finanziatori), in percentuale."""
    _bp()
    e = genera(righe(), report=True)
    assert e.res["forecast_generated"] is True, e.res["message"]
    fin = BASE_BS["sp16a_debiti_banche_breve"] + BASE_BS["sp17a_debiti_banche_lungo"] \
        + BASE_BS["sp17b_debiti_altri_finanz_lungo"]
    atteso = BASE_CE["ce15_oneri_finanziari"] / fin * 100
    assert abs(D(str(base(e.data, "rod"))) - atteso) < D("0.05"), (base(e.data, "rod"), atteso)


@pytest.mark.xfail(strict=True, reason="C04 confermato dal triage 2026-09-25: la PFN del report esclude "
                    "gli altri finanziatori a lungo, che l'interfaccia (finDebt) include")
def test_C04_pfn_del_report_comprende_gli_altri_finanziatori():
    """C04 · PFN del report esclude gli altri finanziatori, l'interfaccia (budget-piano-step.ts, finDebt)
    li include. Oracolo: PFN 2026 = banche + altri finanziatori + obbligazioni − cassa."""
    _bp()
    e = genera(righe(), report=True)
    assert e.res["forecast_generated"] is True, e.res["message"]
    atteso = BASE_BS["sp16a_debiti_banche_breve"] + BASE_BS["sp17a_debiti_banche_lungo"] \
        + BASE_BS["sp17b_debiti_altri_finanz_lungo"] - BASE_BS["sp09_disponibilita_liquide"]
    assert abs(D(str(base(e.data, "pfn"))) - atteso) < D("1"), (base(e.data, "pfn"), atteso)


def _analitico(data, etichetta: str):
    for r in data.indicators_analytical:
        if r.label.strip().lower() == etichetta.lower():
            return r
    raise AssertionError(f"indicatore «{etichetta}» assente dall'Allegato E: "
                         f"{[r.label for r in data.indicators_analytical]}")


@pytest.mark.xfail(strict=True, reason="C05 confermato dal triage 2026-09-25: liquidità corrente sez. 8 "
                    "e Current Ratio (ILC) dell'All. E danno due valori diversi nello stesso documento")
def test_C05_un_solo_current_ratio_nel_documento():
    """C05 · Liquidità corrente sez. 8 = 1,43×, Current Ratio All. E = 1,29×. Oracolo: stesso valore.
    Ruling: l'etichetta esatta nel catalogo è «Current Ratio (ILC)», non «Current Ratio»
    (contracts/final_report_dossier_catalog.json:2130)."""
    _bp()
    e = genera(righe(), report=True)
    assert e.res["forecast_generated"] is True, e.res["message"]
    sez8 = D(str(base(e.data, "liquidita_corrente")))
    all_e = D(str(_analitico(e.data, "Current Ratio (ILC)").values[0]))
    assert abs(sez8 - all_e) < D("0.01"), (sez8, all_e)


@pytest.mark.xfail(strict=True, reason="C06 confermato dal triage 2026-09-25: «Indice di Indebitamento» "
                    "nell'All. E è immobilizzazioni/PN, non debiti totali/PN")
def test_C06_indice_di_indebitamento_e_debiti_su_patrimonio():
    """C06 · All. E: «Indice di indebitamento» = immobilizzazioni / PN. Oracolo: debiti totali / PN."""
    _bp()
    e = genera(righe(), report=True)
    assert e.res["forecast_generated"] is True, e.res["message"]
    pn = BASE_BS["sp11_capitale"] + BASE_BS["sp12_riserve"] + BASE_BS["sp13_utile_perdita"]
    atteso = (BASE_BS["sp16_debiti_breve"] + BASE_BS["sp17_debiti_lungo"]) / pn
    val = D(str(_analitico(e.data, "Indice di Indebitamento").values[0]))
    assert abs(val - atteso) < D("0.01"), (val, atteso)


@pytest.mark.xfail(strict=True, reason="C07 confermato dal triage 2026-09-25: il TFR non è incluso fra "
                    "le fonti consolidate della copertura immobilizzazioni")
def test_C07_copertura_immobilizzazioni_con_il_tfr():
    """C07 · Sez. 8, All. D: il TFR non è fra le fonti consolidate. Oracolo (in %):
    (PN + debiti a lungo + TFR) / immobilizzazioni × 100."""
    _bp()
    e = genera(righe(), report=True)
    assert e.res["forecast_generated"] is True, e.res["message"]
    pn = BASE_BS["sp11_capitale"] + BASE_BS["sp12_riserve"] + BASE_BS["sp13_utile_perdita"]
    immob = BASE_BS["sp02_immob_immateriali"] + BASE_BS["sp03_immob_materiali"] + BASE_BS["sp04_immob_finanziarie"]
    atteso = (pn + BASE_BS["sp17_debiti_lungo"] + BASE_BS["sp15_tfr"]) / immob * 100
    assert abs(D(str(base(e.data, "copertura_immob"))) - atteso) < D("0.1"), (base(e.data, "copertura_immob"), atteso)


@pytest.mark.xfail(strict=True, reason="C08 confermato dal triage 2026-09-25: erogazione e rimborsi "
                    "escono compensati sulla stessa riga del rendiconto, non su righe separate")
def test_C08_erogazioni_e_rimborsi_su_righe_separate():
    """C08 · Sez. 1, 5, All. C: nel 2027 erogazione 280.000 e rimborsi 88.409 compensati (191.591).
    Oracolo: il rendiconto 2027 porta nuovo debito = 280.000 e rimborsi ≥ 53.409, non il netto."""
    _bp()
    rows = _con_rimborsi()
    rows[0]["financing_loans"].append({"name": "Nuovo", "amount": 280000, "opening_residual": 0,
                                       "duration_years": 8, "interest_rate": 4.5, "grace_years": 0,
                                       "balloon_pct": 0})
    e = genera(rows, report=True)
    assert e.res["forecast_generated"] is True, e.res["message"]
    nuovo, rimb = piano(e.data, "cf_nuovo_debito")[0], piano(e.data, "cf_rimborsi")[0]
    assert abs(D(str(nuovo)) - D("280000")) < D("1"), (nuovo, rimb)
    assert D(str(rimb)) >= D("53409"), (nuovo, rimb)


@pytest.mark.xfail(strict=True, reason="C09 confermato dal triage 2026-09-25: il testo narrativo non cita "
                    "la percentuale oneri/MOL della colonna base")
def test_C09_oneri_su_mol_parte_dalla_colonna_base():
    """C09 · Sez. 1: «dal 24,54% al 10,71%» ma il 2026 F è 30,73%. Oracolo: il testo cita il valore della
    colonna base."""
    _bp()
    from backend.app.renderers.business_plan import fmt
    from backend.app.renderers.business_plan.narrative import key_points
    e = genera(_con_rimborsi(), report=True)
    assert e.res["forecast_generated"] is True, e.res["message"]
    testo = " ".join(t for _, t in key_points(e.data))
    assert fmt.pct(base(e.data, "of_mol")) in testo, (fmt.pct(base(e.data, "of_mol")), testo)
