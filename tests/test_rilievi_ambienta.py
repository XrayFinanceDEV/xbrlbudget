"""Banco di triage dei rilievi AMBIENTA (inbox/Verifica_piano_Ambienta_problemi.xlsx).

Spec: docs/superpowers/specs/2026-09-25-triage-rilievi-ambienta-design.md. Un test per rilievo software;
l'oracolo è il comportamento che il consulente si aspetta, quindi un test ROSSO vuol dire che il difetto
c'è. Nessun fix in questo file: il verdetto lo scrive tools/triage_rilievi.py.
"""
from decimal import Decimal as D

import pytest

from tests.rilievi_kit import BASE_BS, BASE_CE, genera, per_anno, righe

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


def test_B02_ammortamento_dei_cespiti_esistenti_si_ferma_al_residuo():
    """B02 · Passo 6: materiali esistenti 72.797 netti ammortizzati 36.040/anno anche oltre il residuo.
    Con un investimento di 250.000 nel 2027 al 10%: 2027 = 36.040 + 25.000, 2028 = 36.040 + 25.000,
    2029 = residuo esistente (72.796,59 − 72.080 = 716,59) + 25.000."""
    rows = righe(depreciation_rate=10)
    rows[0]["tangible_investments"] = 250000
    e = genera(rows)
    assert e.res["forecast_generated"] is True, e.res["message"]
    assert e.anni[2029][1]["ce09b_ammort_materiali"] == D("25716.59")


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
