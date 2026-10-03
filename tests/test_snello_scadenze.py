"""Scadenze entro/oltre nel modo "legge" del percorso snello (spike Qwen diretto, 2026-10-03).

budget_597 stampa «4) debiti verso banche / esigibili entro 580.481 / esigibili oltre 641.999»:
il prompt diceva di usare '.E'/'.O' solo per voci SENZA numero arabo, e Qwen restituiva il
totale 'SPP.D.4' -> tutto in sp16a. CCN e current ratio sbagliati, foglio quadrato: nessun
controllo lo vedeva.
"""
from decimal import Decimal

from importers.import_snello.conti import da_coppie
from importers.import_snello.lettura import PROMPT_VOCI


def test_il_prompt_chiede_le_scadenze_anche_sotto_una_voce_numerata():
    assert "'SPP.D.4.E'" in PROMPT_VOCI and "'SPP.D.4.O'" in PROMPT_VOCI
    assert "non il totale della voce" in PROMPT_VOCI


def test_entro_e_oltre_di_una_voce_numerata_vanno_su_breve_e_lungo():
    bs, _, _ = da_coppie([("SPP.D.4.E", "580481"), ("SPP.D.4.O", "641999"),
                          ("SPP.D.5.E", "77500"), ("SPP.D.5.O", "175500"),
                          ("SPA.C.II.1.E", "1000"), ("SPA.C.II.1.O", "500")])
    assert bs["sp16a_debiti_banche_breve"] == Decimal("580481")
    assert bs["sp17a_debiti_banche_lungo"] == Decimal("641999")
    assert bs["sp16b_debiti_altri_finanz_breve"] == Decimal("77500")
    assert bs["sp17b_debiti_altri_finanz_lungo"] == Decimal("175500")
    assert bs["sp06a_crediti_clienti_breve"] == Decimal("1000")
    assert bs["sp07a_crediti_clienti_lungo"] == Decimal("500")


def test_il_totale_della_voce_insieme_alle_scadenze_non_si_somma_due_volte():
    bs, _, diag = da_coppie([("SPP.D.4", "1222480"), ("SPP.D.4.E", "580481"), ("SPP.D.4.O", "641999")])
    assert bs["sp16a_debiti_banche_breve"] == Decimal("580481")
    assert bs["sp17a_debiti_banche_lungo"] == Decimal("641999")


def test_piu_voci_sotto_lo_stesso_percorso_si_sommano_un_doppione_identico_no():
    """budget_597: B.III.2 ha sotto-lettere (controllate, collegate, altri) che la legenda non
    distingue, e Qwen restituisce tre 'SPA.B.III.2.O' con importi diversi. Tenere solo la prima
    perdeva 26.268 e il foglio non quadrava; la stessa coppia letta due volte resta una."""
    bs, _, _ = da_coppie([("SPA.B.III.2.O", "645000"), ("SPA.B.III.2.O", "6000"),
                          ("SPA.B.III.2.O", "20268"), ("SPA.B.III.2.E", "41857"),
                          ("SPP.D.7.E", "2305814"), ("SPP.D.7.E", "2305814")])
    assert bs["sp04c_crediti_immob_lungo"] == Decimal("671268")
    assert bs["sp04b_crediti_immob_breve"] == Decimal("41857")
    assert bs["sp16d_debiti_fornitori_breve"] == Decimal("2305814")
