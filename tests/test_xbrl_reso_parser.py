"""Task 25: il PDF reso dal bilancio XBRL depositato, letto dal solo testo.

PDF sintetici costruiti qui (niente dati reali): ogni riga di prospetto e' un blocco di testo con
la didascalia e, sotto, un importo per colonna-anno; il piede di ogni pagina porta la tassonomia.
Nessuna chiamata a un modello: i test che passano da ``importa()`` vietano vision e gx10.
"""
from __future__ import annotations

import fitz
import pytest
from decimal import Decimal as D

from importers import xbrl_reso_parser as X

PIEDE = "Generato automaticamente - Conforme alla tassonomia itcc-ci-2018-11-04"


def _altezza(riga):
    if isinstance(riga, tuple):
        return 14.0 * len(riga[1]) * 1.6 + 24
    return 12.0 * len(riga.split("\n")) + 14


def _pdf(tmp_path, pagine, nome="reso.pdf", piede=True):
    """``pagine``: per pagina logica, un elenco di righe; una riga e' una stringa con le sue righe di
    testo separate da ``\n`` (didascalia, poi gli importi), oppure ``("tabella", righe_di_celle)``.
    Una pagina logica che non sta in una pagina fisica prosegue sulla successiva, col suo piede."""
    fisiche: list[list] = []
    for righe in pagine:
        corrente, y = [], 50.0
        for riga in righe:
            if y + _altezza(riga) > 690:
                fisiche.append(corrente)
                corrente, y = [], 50.0
            corrente.append(riga)
            y += _altezza(riga)
        fisiche.append(corrente)
    doc = fitz.open()
    totale = len(fisiche)
    for numero, righe in enumerate(fisiche, start=1):
        pagina = doc.new_page(width=595, height=842)
        y = 50.0
        for riga in righe:
            if isinstance(riga, tuple) and riga[0] == "tabella":
                y = _tabella(pagina, y, riga[1]) + 24
                continue
            for linea in riga.split("\n"):
                pagina.insert_text((40, y), linea, fontname="helv", fontsize=9)
                y += 12
            y += 14
        if piede == "pagina":
            # altro generatore, senza tassonomia: "Bilancio di esercizio / Pagina N di M" in fondo
            pagina.insert_text((57, 700), "Bilancio di esercizio ", fontname="helv", fontsize=7)
            pagina.insert_text((57, 712), f"Pagina {numero} di {totale} ", fontname="helv", fontsize=7)
        elif piede:
            # il piede e' una pila di blocchi in fondo alla pagina, come nel documento reale
            for dy, linea in ((0, "v.2.14.5\nAZIENDA SRL"), (24, "Bilancio di esercizio al 31-12-2025\n"
                                                              f"Pag. {numero} di {totale}"),
                              (48, PIEDE)):
                for k, parte in enumerate(linea.split("\n")):
                    pagina.insert_text((40, 700 + dy + 12 * k), parte, fontname="helv", fontsize=7)
    path = str(tmp_path / nome)
    doc.save(path)
    doc.close()
    return path


def _tabella(pagina, y, righe, larghezza_prima=190, larghezza=70):
    """Tabella con bordi (``find_tables`` li cerca): ``righe`` = elenco di elenchi di celle."""
    colonne = len(righe[0])
    x = [40.0, 40.0 + larghezza_prima]
    for _ in range(colonne - 1):
        x.append(x[-1] + larghezza)
    for riga in righe:
        altezza = 14.0 * max(len(str(c).split("\n")) for c in riga) + 6
        for i, cella in enumerate(riga):
            pagina.draw_rect(fitz.Rect(x[i], y, x[i + 1], y + altezza), color=(0, 0, 0), width=0.6)
            for k, linea in enumerate(str(cella).split("\n")):
                pagina.insert_text((x[i] + 3, y + 11 + 12 * k), linea, fontname="helv", fontsize=7)
        y += altezza
    return y


# ---- il prospetto abbreviato, con le cifre del caso reale che ha motivato il task -----------

DATE = "31-12-2025\n31-12-2024"

SP_ABBREVIATO = [
    "Stato patrimoniale", DATE, "Stato patrimoniale", "Attivo", "B) Immobilizzazioni",
    "I - Immobilizzazioni immateriali\n21.798\n22.776",
    "II - Immobilizzazioni materiali\n379.283\n201.732",
    "III - Immobilizzazioni finanziarie\n4.395\n139.412",
    "Totale immobilizzazioni (B)\n405.476\n363.920",
    "C) Attivo circolante", "II - Crediti",
    "esigibili entro l'esercizio successivo\n1.252.972\n1.185.768",
    "Totale crediti\n1.252.972\n1.185.768",
    "III - Attività finanziarie che non costituiscono immobilizzazioni\n12.502\n12.502",
    "IV - Disponibilità liquide\n1.758\n55.886",
    "Totale attivo circolante (C)\n1.267.232\n1.254.156",
    "D) Ratei e risconti\n9\n9",
    "Totale attivo\n1.672.717\n1.618.085",
    "Passivo", "A) Patrimonio netto",
    "I - Capitale\n52.500\n52.500",
    "IV - Riserva legale\n50.547\n10.500",
    "VI - Altre riserve\n669.472\n857.531",
    "IX - Utile (perdita) dell'esercizio\n100.419\n40.047",
    "Totale patrimonio netto\n872.938\n960.578",
    "C) Trattamento di fine rapporto di lavoro subordinato\n6.633\n6.870",
    "D) Debiti",
    "esigibili entro l'esercizio successivo\n782.871\n650.637",
    "esigibili oltre l'esercizio successivo\n10.275\n0",
    "Totale debiti\n793.146\n650.637",
    "E) Ratei e risconti\n-\n0",
    "Totale passivo\n1.672.717\n1.618.085",
]

CE_ABBREVIATO = [
    "Conto economico", "31-12-2025 31-12-2024", "Conto economico", "A) Valore della produzione",
    "1) ricavi delle vendite e delle prestazioni\n382.549\n346.310",
    "2), 3) variazioni delle rimanenze di prodotti in corso di lavorazione, semilavorati e finiti e \n"
    "dei lavori in corso su ordinazione\n-\n(1.500)",
    "3) variazioni dei lavori in corso su ordinazione\n-\n(1.500)",
    "5) altri ricavi e proventi", "altri\n49.439\n236.177",
    "Totale altri ricavi e proventi\n49.439\n236.177",
    "Totale valore della produzione\n431.988\n580.987",
    "B) Costi della produzione",
    "6) per materie prime, sussidiarie, di consumo e di merci\n9.583\n31.709",
    "7) per servizi\n226.212\n236.952",
    "8) per godimento di beni di terzi\n1.300\n21.346",
    "9) per il personale",
    "a) salari e stipendi\n30.910\n58.975",
    "b) oneri sociali\n11.067\n15.502",
    "c), d), e) trattamento di fine rapporto, trattamento di quiescenza, altri costi del personale\n-\n6.308",
    "c) trattamento di fine rapporto\n-\n6.308",
    "Totale costi per il personale\n41.977\n80.785",
    "10) ammortamenti e svalutazioni",
    "a), b), c) ammortamento delle immobilizzazioni immateriali e materiali, altre svalutazioni \n"
    "delle immobilizzazioni\n35.592\n35.529",
    "a) ammortamento delle immobilizzazioni immateriali\n978\n978",
    "b) ammortamento delle immobilizzazioni materiali\n34.614\n34.551",
    "Totale ammortamenti e svalutazioni\n35.592\n35.529",
    "14) oneri diversi di gestione\n8.638\n128.844",
    "Totale costi della produzione\n323.302\n535.165",
    "Differenza tra valore e costi della produzione (A - B)\n108.686\n45.822",
    "C) Proventi e oneri finanziari",
    "16) altri proventi finanziari", "d) proventi diversi dai precedenti", "altri\n-\n81",
    "Totale proventi diversi dai precedenti\n-\n81",
    "Totale altri proventi finanziari\n-\n81",
    "17) interessi e altri oneri finanziari", "altri\n777\n1.775",
    "Totale interessi e altri oneri finanziari\n777\n1.775",
    "Totale proventi e oneri finanziari (15 + 16 - 17 + - 17-bis)\n(777)\n(1.694)",
    "Risultato prima delle imposte (A - B + - C + - D)\n107.909\n44.128",
    "20) Imposte sul reddito dell'esercizio, correnti, differite e anticipate",
    "imposte correnti\n7.486\n3.851", "imposte relative a esercizi precedenti\n4\n230",
    "Totale delle imposte sul reddito dell'esercizio, correnti, differite e anticipate\n7.490\n4.081",
    "21) Utile (perdita) dell'esercizio\n100.419\n40.047",
]


def _abbreviato(tmp_path, sp=None, ce=None, extra=(), nome="reso.pdf"):
    return _pdf(tmp_path, [sp or SP_ABBREVIATO, ce or CE_ABBREVIATO, *extra], nome=nome)


def _sostituisci(righe, prima, dopo):
    assert prima in righe, prima
    return [dopo if r == prima else r for r in righe]


# ---- riconoscimento --------------------------------------------------------------------------

def test_riconosci_dal_piede_di_tassonomia(tmp_path):
    assert X.riconosci(_abbreviato(tmp_path)) is True


def test_riconosci_da_testo():
    testo = "Stato patrimoniale\n31-12-2025\n" + PIEDE
    assert X.riconosci(testo) is True
    assert X.riconosci("Stato patrimoniale\nAttivo\nTotale attivo 100") is False
    assert X.riconosci("") is False


def test_non_xbrl_non_riconosciuto_e_estrai_none(tmp_path):
    path = _pdf(tmp_path, [SP_ABBREVIATO], piede=False)     # un solo prospetto, nessun piede
    assert X.riconosci(path) is False
    assert X.estrai(path) is None


# ---- il caso 392: "-" e' uno zero nella SUA colonna ------------------------------------------

def test_trattino_e_uno_zero_nella_sua_colonna_e_il_bilancio_quadra(tmp_path):
    r = X.estrai(_abbreviato(tmp_path))
    assert r["adottabile"] is True and r["rifiuto"] is None
    bs, ce = r["bs"], r["ce"]
    assert ce["ce03_lavori_interni"] == D("0")                     # 2025 stampa "-"
    assert r["prior_ce"]["ce03_lavori_interni"] == D("-1500")      # 2024 stampa (1.500)
    assert ce["ce06_servizi"] == D("226212")                       # mai tappata a 224.712
    assert bs["sp16_debiti_breve"] == D("782871")
    assert bs["sp17_debiti_lungo"] == D("10275")
    assert bs["sp13_utile_perdita"] == D("100419")
    attivo = sum(bs.get(k, 0) for k in ("sp02_immob_immateriali", "sp03_immob_materiali",
                                        "sp04_immob_finanziarie", "sp06_crediti_breve",
                                        "sp08_attivita_finanziarie", "sp09_disponibilita_liquide",
                                        "sp10_ratei_risconti_attivi"))
    assert attivo == D("1672717")
    assert r["stampati"]["totale_attivo"] == D("1672717") == r["stampati"]["totale_passivo"]


def test_anno_precedente_letto_e_chiude_anche_lui(tmp_path):
    r = X.estrai(_abbreviato(tmp_path))
    assert r["prior_stato"] == "letto"
    assert r["prior_bs"]["sp13_utile_perdita"] == D("40047")
    assert r["prior_bs"]["sp16_debiti_breve"] == D("650637")
    assert r["prior_bs"].get("sp17_debiti_lungo", 0) == D("0")
    assert r["anni"] == [2025, 2024]


def test_chiavi_diagnostiche_sempre_dichiarate_anche_a_zero(tmp_path):
    r = X.estrai(_abbreviato(tmp_path))
    assert r["bs"]["_unclassified_mass"] == D("0")
    assert r["bs"]["_plug_residual"] == D("0")
    assert r["prior_bs"]["_unclassified_mass"] == D("0")
    assert r["prior_bs"]["_plug_residual"] == D("0")


def test_scadenze_stampate_vanno_sul_breve_e_sul_lungo_mai_appiattite(tmp_path):
    r = X.estrai(_abbreviato(tmp_path))
    assert r["bs"]["_source_maturity_read"] == D("1")
    assert "_source_maturity_unspecified" not in r["bs"]
    # senza dettaglio per voce l'aggregato sta sul sotto-campo esplicito, non sull'aggregato
    assert r["bs"]["sp16g_altri_debiti_breve"] == D("782871")
    assert r["bs"]["sp17g_altri_debiti_lungo"] == D("10275")
    assert r["bs"]["sp06g_crediti_altri_breve"] == D("1252972")


def test_scadenza_non_stampata_resta_a_breve_e_si_dichiara(tmp_path):
    sp = list(SP_ABBREVIATO)
    i = sp.index("D) Debiti")
    sp[i + 1:i + 3] = ["debiti diversi\n793.146\n650.637"]      # nessuna scadenza stampata
    r = X.estrai(_abbreviato(tmp_path, sp=sp))
    assert r["adottabile"] is True
    assert r["bs"].get("sp17_debiti_lungo", 0) == D("0")
    assert r["bs"]["_source_maturity_unspecified"] == D("1")


# ---- raggruppamento e componenti: mai entrambi ------------------------------------------------

def test_riga_di_raggruppamento_e_componenti_non_si_contano_due_volte(tmp_path):
    r = X.estrai(_abbreviato(tmp_path))
    ce = r["ce"]
    assert ce["ce09_ammortamenti"] == D("35592")                   # non 71.184
    assert ce["ce09a_ammort_immateriali"] == D("978")
    assert ce["ce09b_ammort_materiali"] == D("34614")
    assert ce["ce08_costi_personale"] == D("41977")
    assert r["prior_ce"]["ce08a_tfr_accrual"] == D("6308")         # c) trattamento di fine rapporto
    assert r["prior_ce"]["ce08_costi_personale"] == D("80785")


def test_raggruppamento_senza_componenti_va_sull_aggregato_della_voce(tmp_path):
    ce = [r for r in CE_ABBREVIATO if not r.startswith(("a) ammortamento", "b) ammortamento"))]
    r = X.estrai(_abbreviato(tmp_path, ce=ce))
    assert r["adottabile"] is True
    assert r["ce"]["ce09_ammortamenti"] == D("35592")
    assert r["ce"].get("ce09a_ammort_immateriali", 0) == D("0")


# ---- un totale stampato che le righe non riproducono: rifiuto, mai un tappo -------------------

def test_totale_non_riprodotto_rifiuta_il_candidato_e_nomina_il_controllo(tmp_path):
    sp = _sostituisci(SP_ABBREVIATO, "Totale immobilizzazioni (B)\n405.476\n363.920",
                      "Totale immobilizzazioni (B)\n405.477\n363.920")
    r = X.estrai(_abbreviato(tmp_path, sp=sp))
    assert r["adottabile"] is False
    assert r["rifiuto"]["controllo"] == "totale"
    assert "immobilizzazioni" in r["rifiuto"]["didascalia"].lower()
    assert r["rifiuto"]["stampato"] == "405477" and r["rifiuto"]["letto"] == "405476"
    assert r["bs"] == {} and r["ce"] == {}                          # niente di adottabile


def test_attivo_diverso_da_passivo_rifiuta(tmp_path):
    sp = _sostituisci(SP_ABBREVIATO, "Totale passivo\n1.672.717\n1.618.085",
                      "Totale passivo\n1.672.718\n1.618.085")
    r = X.estrai(_abbreviato(tmp_path, sp=sp))
    assert r["adottabile"] is False
    assert r["rifiuto"]["controllo"] == "totale"


def test_utile_ce_diverso_da_sp13_rifiuta(tmp_path):
    ce = _sostituisci(CE_ABBREVIATO, "21) Utile (perdita) dell'esercizio\n100.419\n40.047",
                      "21) Utile (perdita) dell'esercizio\n100.420\n40.047")
    r = X.estrai(_abbreviato(tmp_path, ce=ce))
    assert r["adottabile"] is False
    assert r["rifiuto"]["controllo"] in ("stampato_utile", "utile_ce", "ce_diverso_da_sp13")


def test_anno_precedente_che_non_chiude_non_trascina_il_corrente(tmp_path):
    sp = _sostituisci(SP_ABBREVIATO, "Totale crediti\n1.252.972\n1.185.768",
                      "Totale crediti\n1.252.972\n1.185.769")
    r = X.estrai(_abbreviato(tmp_path, sp=sp))
    assert r["adottabile"] is True
    assert r["prior_bs"] is None and r["prior_stato"] == "scartato"
    assert r["prior_rifiuto"]["anno"] == 2024


def test_estrazione_vuota_non_e_una_quadratura(tmp_path):
    sp = ["Stato patrimoniale", DATE, "Attivo", "Totale attivo\n-\n-", "Passivo", "Totale passivo\n-\n-"]
    ce = ["Conto economico", "31-12-2025 31-12-2024", "21) Utile (perdita) dell'esercizio\n-\n-"]
    r = X.estrai(_abbreviato(tmp_path, sp=sp, ce=ce))
    assert r["adottabile"] is False


# ---- didascalia sconosciuta: sul secchio della sua sezione, contata -------------------------

def test_didascalia_sconosciuta_nei_costi_va_su_ce06_ed_e_contata(tmp_path):
    ce = list(CE_ABBREVIATO)
    # 500 euro letti sotto una didascalia che non conosciamo, tolti dai servizi: i totali non cambiano
    ce = _sostituisci(ce, "7) per servizi\n226.212\n236.952", "7) per servizi\n225.712\n236.952")
    ce.insert(ce.index("14) oneri diversi di gestione\n8.638\n128.844"), "costo mai visto\n500\n0")
    r = X.estrai(_abbreviato(tmp_path, ce=ce))
    assert r["adottabile"] is True, r["rifiuto"]
    assert r["ce"]["ce06_servizi"] == D("226212")                  # 225.712 letti + 500 sul secchio
    assert r["bs"]["_unclassified_mass"] == D("500")
    assert r["ignoti"][0][0] == "costo mai visto" and r["ignoti"][0][1] == "ce06"


def test_didascalia_sconosciuta_senza_secchio_rifiuta(tmp_path):
    ce = list(CE_ABBREVIATO)
    ce.insert(ce.index("Totale proventi e oneri finanziari (15 + 16 - 17 + - 17-bis)\n(777)\n(1.694)"),
              "voce finanziaria mai vista\n5\n0")
    r = X.estrai(_abbreviato(tmp_path, ce=ce))
    assert r["adottabile"] is False
    assert r["rifiuto"]["controllo"] == "didascalia_non_collocabile"


# ---- tabelle di nota: "Variazioni e scadenza" ----------------------------------------------

INTESTAZIONE = ["", "Valore di inizio\nesercizio", "Variazione\nnell'esercizio",
                "Valore di fine\nesercizio", "Quota scadente entro\nl'esercizio",
                "Quota scadente oltre\nl'esercizio"]

TABELLA_DEBITI = [
    INTESTAZIONE,
    ["Debiti verso banche", "500.000", "(50.000)", "450.000", "350.000", "100.000"],
    ["Debiti verso fornitori", "200.000", "100.000", "300.000", "300.000", "-"],
    ["Debiti tributari", "10.000", "5.000", "15.000", "15.000", "-"],
    ["Altri debiti", "28.000", "0", "28.000", "28.000", "-"],
]
# totali che chiudono sul prospetto 1.672.717: usiamo un abbreviato con debiti 793.000
TOTALE_RIGA = ["Totale debiti", "738.000", "55.000", "793.000", "693.000", "100.000"]


def _sp_con_debiti(entro, oltre):
    sp = list(SP_ABBREVIATO)
    sp = _sostituisci(sp, "esigibili entro l'esercizio successivo\n782.871\n650.637",
                      f"esigibili entro l'esercizio successivo\n{entro}\n650.637")
    sp = _sostituisci(sp, "esigibili oltre l'esercizio successivo\n10.275\n0",
                      f"esigibili oltre l'esercizio successivo\n{oltre}\n0")
    tot = int(entro.replace(".", "")) + int(oltre.replace(".", ""))
    def f(n):
        return f"{n:,}".replace(",", ".")
    sp = _sostituisci(sp, "Totale debiti\n793.146\n650.637", f"Totale debiti\n{f(tot)}\n650.637")
    delta = tot - 793146
    sp = _sostituisci(sp, "Totale passivo\n1.672.717\n1.618.085", f"Totale passivo\n{f(1672717 + delta)}\n1.618.085")
    sp = _sostituisci(sp, "IV - Disponibilità liquide\n1.758\n55.886", f"IV - Disponibilità liquide\n{f(1758 + delta)}\n55.886")
    sp = _sostituisci(sp, "Totale attivo circolante (C)\n1.267.232\n1.254.156",
                      f"Totale attivo circolante (C)\n{f(1267232 + delta)}\n1.254.156")
    sp = _sostituisci(sp, "Totale attivo\n1.672.717\n1.618.085", f"Totale attivo\n{f(1672717 + delta)}\n1.618.085")
    return sp


def _nota(righe_tabella):
    return ["Variazioni e scadenza dei debiti", ("tabella", righe_tabella)]


def test_tabella_debiti_applicata_quando_le_quote_chiudono_sul_prospetto(tmp_path):
    sp = _sp_con_debiti("693.000", "100.000")
    path = _abbreviato(tmp_path, sp=sp, extra=[_nota(TABELLA_DEBITI + [TOTALE_RIGA])])
    r = X.estrai(path)
    assert r["adottabile"] is True, r["rifiuto"]
    assert r["dettagli"]["debiti"]["applicata"] is True
    bs = r["bs"]
    assert bs["sp16a_debiti_banche_breve"] == D("350000")
    assert bs["sp17a_debiti_banche_lungo"] == D("100000")
    assert bs["sp16d_debiti_fornitori_breve"] == D("300000")
    assert bs["sp16e_debiti_tributari_breve"] == D("15000")
    assert bs["sp16g_altri_debiti_breve"] == D("28000")
    assert bs["sp16_debiti_breve"] == D("693000") and bs["sp17_debiti_lungo"] == D("100000")
    # l'anno precedente non ha tabella: resta sul sotto-campo esplicito
    assert r["prior_bs"]["sp16g_altri_debiti_breve"] == D("650637")


def test_tabella_debiti_non_applicata_se_differisce_di_un_euro_e_lo_dichiara(tmp_path):
    sp = _sp_con_debiti("693.001", "100.000")           # il prospetto stampa 1 euro in piu'
    path = _abbreviato(tmp_path, sp=sp, extra=[_nota(TABELLA_DEBITI + [TOTALE_RIGA])])
    r = X.estrai(path)
    assert r["adottabile"] is True
    assert r["dettagli"]["debiti"]["applicata"] is False
    assert r["dettagli"]["debiti"]["motivo"] == "non_riconcilia_col_prospetto"
    assert r["dettagli"]["debiti"]["tabella"] == ["693000", "100000"]
    assert r["dettagli"]["debiti"]["prospetto"] == ["693001", "100000"]
    bs = r["bs"]                                          # tutto o niente: nessun campo toccato
    assert bs.get("sp16a_debiti_banche_breve", 0) == D("0")
    assert bs["sp16g_altri_debiti_breve"] == D("693001")
    assert bs["sp17g_altri_debiti_lungo"] == D("100000")


def test_tabella_che_prosegue_sulla_pagina_dopo(tmp_path):
    sp = _sp_con_debiti("693.000", "100.000")
    prima = _nota(TABELLA_DEBITI[:3])
    dopo = [("tabella", [INTESTAZIONE] + TABELLA_DEBITI[3:] + [TOTALE_RIGA])]
    path = _pdf(tmp_path, [sp, CE_ABBREVIATO, prima, dopo])
    r = X.estrai(path)
    assert r["dettagli"]["debiti"]["applicata"] is True, r["dettagli"]
    pagine = r["dettagli"]["debiti"]["pagine"]
    assert len(pagine) == 2 and pagine[1] == pagine[0] + 1
    assert r["bs"]["sp16g_altri_debiti_breve"] == D("28000")


def test_tabella_con_riga_sconosciuta_non_si_applica(tmp_path):
    sp = _sp_con_debiti("693.000", "100.000")
    tabella = [TABELLA_DEBITI[0], ["Debiti per cose nuove", "1", "1", "2", "2", "-"]] + TABELLA_DEBITI[1:]
    r = X.estrai(_abbreviato(tmp_path, sp=sp, extra=[_nota(tabella + [TOTALE_RIGA])]))
    assert r["dettagli"]["debiti"]["applicata"] is False
    assert r["dettagli"]["debiti"]["motivo"].startswith("riga_non_riconosciuta")


TABELLA_CREDITI = [
    INTESTAZIONE,
    ["Crediti verso clienti iscritti nell'attivo circolante", "1.000.000", "100.000", "1.100.000",
     "1.100.000", "-"],
    ["Crediti tributari iscritti nell'attivo circolante", "100.000", "52.972", "152.972", "152.972", "-"],
    ["Totale crediti iscritti nell'attivo circolante", "1.100.000", "152.972", "1.252.972",
     "1.252.972", "-"],
]


def test_tabella_crediti_applicata_sulle_voci(tmp_path):
    r = X.estrai(_abbreviato(tmp_path, extra=[
        ["Variazioni e scadenza dei crediti iscritti nell'attivo circolante", ("tabella", TABELLA_CREDITI)]]))
    assert r["dettagli"]["crediti"]["applicata"] is True
    assert r["bs"]["sp06a_crediti_clienti_breve"] == D("1100000")
    assert r["bs"]["sp06e_crediti_tributari_breve"] == D("152972")
    assert r["bs"]["sp06_crediti_breve"] == D("1252972")


# ---- ordinario con le voci stampate nel prospetto: vince il prospetto -------------------------

def test_prospetto_ordinario_con_sotto_voci_vince_sulla_tabella(tmp_path):
    sp = list(SP_ABBREVIATO)
    i = sp.index("D) Debiti")
    j = sp.index("Totale debiti\n793.146\n650.637")
    sp[i + 1:j] = [
        "4) debiti verso banche", "esigibili entro l'esercizio successivo\n350.000\n300.000",
        "esigibili oltre l'esercizio successivo\n100.000\n0", "Totale debiti verso banche\n450.000\n300.000",
        "7) debiti verso fornitori", "esigibili entro l'esercizio successivo\n332.871\n350.637",
        "Totale debiti verso fornitori\n332.871\n350.637",
        "14) altri debiti", "esigibili oltre l'esercizio successivo\n10.275\n0",
        "Totale altri debiti\n10.275\n0",
    ]
    tabella = [INTESTAZIONE,
               ["Debiti verso banche", "0", "0", "450.000", "400.000", "50.000"],
               ["Debiti verso fornitori", "0", "0", "332.871", "332.871", "-"],
               ["Altri debiti", "0", "0", "10.275", "10.275", "-"],
               ["Totale debiti", "0", "0", "793.146", "743.146", "50.000"]]
    r = X.estrai(_abbreviato(tmp_path, sp=sp, extra=[_nota(tabella)]))
    assert r["adottabile"] is True, r["rifiuto"]
    assert r["dettagli"]["debiti"]["applicata"] is False
    assert r["dettagli"]["debiti"]["motivo"] == "prospetto_con_dettaglio"
    assert r["dettagli"]["debiti"]["discordanze"]                  # dichiarato, nulla cambiato
    assert r["bs"]["sp16a_debiti_banche_breve"] == D("350000")     # il prospetto stampa 350.000
    assert r["bs"]["sp17a_debiti_banche_lungo"] == D("100000")
    assert r["bs"]["sp16d_debiti_fornitori_breve"] == D("332871")
    assert r["bs"]["sp17g_altri_debiti_lungo"] == D("10275")


# ---- note a pie di tabella e rimandi --------------------------------------------------------

def test_importo_con_rimando_a_nota_non_e_un_secondo_importo(tmp_path):
    sp = _sostituisci(SP_ABBREVIATO, "VI - Altre riserve\n669.472\n857.531",
                      "VI - Altre riserve\n669.472 (1)\n857.531")
    r = X.estrai(_abbreviato(tmp_path, sp=sp))
    assert r["adottabile"] is True
    assert r["bs"]["sp12e_altre_riserve"] == D("669472")


def test_voce_di_patrimonio_senza_enumeratore_a_zero(tmp_path):
    sp = list(SP_ABBREVIATO)
    sp.insert(sp.index("Totale patrimonio netto\n872.938\n960.578"), "Perdita ripianata nell'esercizio\n0\n0")
    r = X.estrai(_abbreviato(tmp_path, sp=sp))
    assert r["adottabile"] is True
    assert r["bs"]["_unclassified_mass"] == D("0")


# ---- wiring in deterministico.py ------------------------------------------------------------

def test_deterministico_adotta_il_reso_xbrl_per_primo(tmp_path):
    from importers.import_snello import deterministico as DET
    esito = DET.tentativo(_abbreviato(tmp_path))
    assert esito["adottato"] is True
    assert esito["parser"] == "xbrl_reso_parser"
    assert esito["esito"] == "ok"
    assert esito["ce"]["ce06_servizi"] == D("226212")
    assert esito["prior_ce"]["ce03_lavori_interni"] == D("-1500")


def test_deterministico_candidato_rifiutato_non_si_adotta_e_porta_il_perche(tmp_path):
    from importers.import_snello import deterministico as DET
    sp = _sostituisci(SP_ABBREVIATO, "Totale immobilizzazioni (B)\n405.476\n363.920",
                      "Totale immobilizzazioni (B)\n405.477\n363.920")
    esito = DET.tentativo(_abbreviato(tmp_path, sp=sp))
    assert esito["adottato"] is False
    assert esito["xbrl_reso"]["rifiuto"]["controllo"] == "totale"


def test_esito_di_un_candidato_vuoto_e_vuoto_non_oltre_soglia():
    from importers.import_snello import deterministico as DET
    assert DET._esito("x", {}, {}, None)["esito"] == "vuoto"
    assert DET._esito("x", {"sp09_disponibilita_liquide": D("0")},
                      {"ce01_ricavi_vendite": D("0")}, None)["esito"] == "vuoto"


# ---- importa(): zero vision, zero gx10 --------------------------------------------------------

def _vieta_modelli(monkeypatch):
    from importers import llm_provider
    from importers.struttura_documento import analisi

    def vietato(nome):
        def f(*a, **k):
            raise AssertionError(f"{nome} chiamato su un reso XBRL adottato")
        return f
    monkeypatch.setattr(analisi, "analizza_struttura", vietato("analizza_struttura (vision)"))
    for nome in dir(llm_provider):
        if nome.startswith(("leggi_", "chiama_", "gx10", "coge_", "lettore_")) and callable(
                getattr(llm_provider, nome)):
            monkeypatch.setattr(llm_provider, nome, vietato(f"llm_provider.{nome}"))


def test_un_reso_adottato_non_chiama_ne_vision_ne_gx10(tmp_path, monkeypatch):
    from importers import import_snello
    _vieta_modelli(monkeypatch)

    def vietata(*a, **k):
        raise AssertionError("modello chiamato")
    ris = import_snello.importa(_abbreviato(tmp_path), analizza=vietata, leggi_conti=vietata,
                                leggi_voci=vietata, trascrivi=vietata)
    assert ris.report["fonte"] == "deterministico:xbrl_reso_parser"
    assert ris.report["esito"] == "ok"
    assert ris.report["letture"]["chiamate"] == 0
    assert ris.struttura.chiamate_vision == 0
    assert ris.report["struttura"]["stato"] == "non_richiesta"
    assert ris.bs["sp16_debiti_breve"] == D("782871")
    assert ris.prior_bs is not None and ris.prior_ce["ce03_lavori_interni"] == D("-1500")
    assert ris.report["deterministico"]["parser"] == "xbrl_reso_parser"


def test_un_reso_adottato_salta_il_passaggio_dei_dettagli_e_dice_da_dove_vengono(tmp_path, monkeypatch):
    """Dal percorso di import vero: ``enrich_pdf_details`` (che poteva chiamare Qwen) non gira per
    questa fonte; i dettagli sono quelli del prospetto e della nota, e il report lo dice."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from database.db import Base
    from importers import detail_enrichment, pdf_importer

    monkeypatch.setenv("IMPORT_MOTORE", "snello")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _vieta_modelli(monkeypatch)
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(pdf_importer, "SessionLocal", sessionmaker(bind=engine))

    def vietata(*a, **k):
        raise AssertionError("enrich_pdf_details chiamata su un reso XBRL adottato")
    monkeypatch.setattr(detail_enrichment, "enrich_pdf_details", vietata)

    sp = _sp_con_debiti("693.000", "100.000")
    path = _abbreviato(tmp_path, sp=sp, extra=[_nota(TABELLA_DEBITI + [TOTALE_RIGA])])
    result = pdf_importer.import_pdf_balance_sheet(
        file_path=path, fiscal_year=2025, company_name="Reso XBRL", create_company=True, sector=1,
        user_id="reso-xbrl", period_months=12)
    rapporto = result["validation_report"]["import_snello"]
    assert rapporto["fonte"] == "deterministico:xbrl_reso_parser"
    assert rapporto["dettagli"]["debiti"]["applicata"] is True
    assert result["extraction_method"] == "import_snello"


# ---- casi di layout visti sul corpus -----------------------------------------------------------

def test_una_sola_colonna_anno_nessun_precedente(tmp_path):
    def una(righe):
        out = []
        for r in righe:
            linee = r.split("\n")
            amounts = [l for l in linee if X._IMPORTO.match(l.strip())]
            out.append("\n".join(linee[:-1]) if len(amounts) == 2 else r)
        return out
    sp = _sostituisci(una(SP_ABBREVIATO), DATE, "31-12-2025")
    ce = _sostituisci(una(CE_ABBREVIATO), "31-12-2025 31-12-2024", "31-12-2025")
    r = X.estrai(_abbreviato(tmp_path, sp=sp, ce=ce))
    assert r["adottabile"] is True, r["rifiuto"]
    assert r["prior_bs"] is None and r["prior_stato"] == "assente"
    assert r["anni"] == [2025]


def test_pagina_che_si_spezza_dentro_un_raggruppamento(tmp_path):
    """Il piede di pagina fra la riga di raggruppamento e il suo ultimo componente non deve
    far perdere il raggruppamento (budget 202: il componente b) apre la pagina dopo)."""
    ce_a = CE_ABBREVIATO[:CE_ABBREVIATO.index("b) ammortamento delle immobilizzazioni materiali\n34.614\n34.551")]
    ce_b = CE_ABBREVIATO[len(ce_a):]
    r = X.estrai(_pdf(tmp_path, [SP_ABBREVIATO, ce_a, ce_b]))
    assert r["adottabile"] is True, r["rifiuto"]
    assert r["ce"]["ce09_ammortamenti"] == D("35592")


def test_nota_a_pie_di_tabella_non_entra_nel_prospetto(tmp_path):
    sp = list(SP_ABBREVIATO)
    sp += ["(1)", "Altre riserve\n31/12/2025 31/12/2024", "Riserva straordinaria\n669.472\n857.531",
           "Differenza da arrotondamento all'unità di Euro\n(1)"]
    sp = _sostituisci(sp, "VI - Altre riserve\n669.472\n857.531", "VI - Altre riserve\n669.472 (1)\n857.531")
    r = X.estrai(_abbreviato(tmp_path, sp=sp))
    assert r["adottabile"] is True, r["rifiuto"]
    assert r["bs"]["sp12e_altre_riserve"] == D("669472")


def test_totale_a_zero_di_una_sezione_senza_righe(tmp_path):
    ce = list(CE_ABBREVIATO)
    i = ce.index("Risultato prima delle imposte (A - B + - C + - D)\n107.909\n44.128")
    ce[i:i] = ["D) Rettifiche di valore di attività e passività finanziarie",
               "Totale delle rettifiche di valore di attività e passività finanziarie (18 - 19)\n-\n-"]
    r = X.estrai(_abbreviato(tmp_path, ce=ce))
    assert r["adottabile"] is True, r["rifiuto"]
    assert r["ce"]["ce20_imposte"] == D("7490")


def test_riga_di_dettaglio_negativa_resta_col_suo_segno(tmp_path):
    """Un importo stampato tra parentesi e' negativo: mai assolutizzato (la quadratura decide)."""
    sp = _sostituisci(SP_ABBREVIATO, "VI - Altre riserve\n669.472\n857.531",
                      "VI - Altre riserve\n669.472\n857.531")
    sp = _sostituisci(sp, "IX - Utile (perdita) dell'esercizio\n100.419\n40.047",
                      "IX - Utile (perdita) dell'esercizio\n100.419\n40.047")
    r = X.estrai(_abbreviato(tmp_path, sp=sp))
    assert r["prior_ce"]["ce03_lavori_interni"] == D("-1500")
    assert r["prior_bs"]["sp13_utile_perdita"] == D("40047")


def test_estrai_che_solleva_non_impedisce_il_percorso_di_sempre(tmp_path, monkeypatch):
    from importers.import_snello import deterministico as DET

    def rotto(path):
        raise RuntimeError("lettore rotto")
    monkeypatch.setattr(X, "estrai", rotto)
    esito = DET.tentativo(_abbreviato(tmp_path))
    assert esito["adottato"] is False                       # il percorso classico non legge questo file
    assert esito["xbrl_reso"] == {"esito": "errore", "errore": "RuntimeError: lettore rotto"}


def test_massa_non_classificata_sopra_soglia_non_si_adotta_e_si_dichiara(tmp_path):
    from importers.import_snello import deterministico as DET
    ce = list(CE_ABBREVIATO)
    # 5.000 euro su una didascalia mai vista (sopra max(100 euro, 0,1% dell'attivo) = 1.672,72)
    ce = _sostituisci(ce, "7) per servizi\n226.212\n236.952", "7) per servizi\n221.212\n236.952")
    ce.insert(ce.index("14) oneri diversi di gestione\n8.638\n128.844"), "costo mai visto\n5.000\n0")
    esito = DET.tentativo(_abbreviato(tmp_path, ce=ce))
    assert esito["adottato"] is False
    assert esito["xbrl_reso"]["esito"] == "massa_non_classificata"
    assert esito["xbrl_reso"]["unclassified_mass"] == "5000.00"


def test_riconosci_un_file_senza_estensione_pdf(tmp_path):
    path = _abbreviato(tmp_path)
    import shutil
    shutil.copy(path, str(tmp_path / "caricato"))
    assert X.riconosci(str(tmp_path / "caricato")) is True


# ---- fix round 1: un flag di scadenza per lato -----------------------------------------------

def test_flag_scadenza_per_lato(tmp_path):
    r = X.estrai(_abbreviato(tmp_path))                       # entrambe le scadenze stampate
    assert "_source_maturity_unspecified" not in r["bs"]
    assert "_source_credit_maturity_unspecified" not in r["bs"]
    assert r["bs"]["_source_maturity_read"] == D("1")
    sp = list(SP_ABBREVIATO)                                  # solo i debiti senza scadenza
    i = sp.index("D) Debiti")
    sp[i + 1:i + 3] = ["debiti diversi\n793.146\n650.637"]
    r = X.estrai(_abbreviato(tmp_path, sp=sp, nome="a.pdf"))
    assert r["bs"]["_source_maturity_unspecified"] == D("1")
    assert "_source_credit_maturity_unspecified" not in r["bs"]
    sp = _sostituisci(SP_ABBREVIATO, "esigibili entro l'esercizio successivo\n1.252.972\n1.185.768",
                      "crediti diversi\n1.252.972\n1.185.768")   # solo i crediti senza scadenza
    r = X.estrai(_abbreviato(tmp_path, sp=sp, nome="b.pdf"))
    assert r["adottabile"] is True, r["rifiuto"]
    assert r["bs"]["_source_credit_maturity_unspecified"] == D("1")
    assert "_source_maturity_unspecified" not in r["bs"]


# ---- fix round 1: l'anno precedente si usa solo se l'intestazione e' esattamente corrente - 1 ----

def test_colonna_precedente_con_anno_non_consecutivo_e_scartata_e_dichiarata(tmp_path):
    sp = _sostituisci(SP_ABBREVIATO, DATE, "31-12-2025\n31-12-2023")
    ce = _sostituisci(CE_ABBREVIATO, "31-12-2025 31-12-2024", "31-12-2025 31-12-2023")
    r = X.estrai(_abbreviato(tmp_path, sp=sp, ce=ce))
    assert r["adottabile"] is True
    assert r["anni"] == [2025, 2023]
    assert r["prior_bs"] is None and r["prior_ce"] is None
    assert r["prior_stato"] == "scartato"
    assert r["prior_rifiuto"]["controllo"] == "anno_non_consecutivo"
    assert r["prior_rifiuto"]["anni"] == [2025, 2023]


def test_intestazioni_illeggibili_o_incomplete_nessun_precedente():
    assert X._anno_precedente_valido([2025, 2024], 2) is True
    assert X._anno_precedente_valido([2025, 2023], 2) is False
    assert X._anno_precedente_valido([2025], 2) is False
    assert X._anno_precedente_valido([], 2) is False


def test_precedente_scartato_arriva_nel_report_snello(tmp_path, monkeypatch):
    from importers import import_snello
    sp = _sostituisci(SP_ABBREVIATO, DATE, "31-12-2025\n31-12-2023")
    ce = _sostituisci(CE_ABBREVIATO, "31-12-2025 31-12-2024", "31-12-2025 31-12-2023")
    _vieta_modelli(monkeypatch)
    ris = import_snello.importa(_abbreviato(tmp_path, sp=sp, ce=ce))
    assert ris.prior_bs is None
    det = ris.report["deterministico"]
    assert det["prior_stato"] == "scartato"
    assert det["prior_rifiuto"]["anni"] == [2025, 2023]


def test_il_reale_162_non_scrive_il_2023_sul_2024():
    import glob, os
    trovati = glob.glob("/home/peter/DEV/budget/Test/**/budget_162_*.pdf", recursive=True)
    if not trovati:
        pytest.skip("corpus locale assente")
    r = X.estrai(trovati[0])
    assert r["anni"] == [2025, 2023] and r["prior_bs"] is None


# ---- fix round 1: il resto di un raggruppamento va sul sotto-campo esplicito, dichiarato -------

def _ce_con_resto(gruppo_personale=None, gruppo_amm=None):
    """Raggruppamento piu' grande dei suoi componenti stampati; il resto e' tolto da una riga
    non toccata cosi' i totali restano quelli del documento."""
    ce = list(CE_ABBREVIATO)
    if gruppo_personale is not None:
        # c), d), e) = 500 con componente c) = 0: il resto (500) e' stampato solo nel raggruppamento
        ce = _sostituisci(ce, "c), d), e) trattamento di fine rapporto, trattamento di quiescenza, altri costi del personale\n-\n6.308",
                          "c), d), e) trattamento di fine rapporto, trattamento di quiescenza, altri costi del personale\n500\n6.308")
        ce = _sostituisci(ce, "c) trattamento di fine rapporto\n-\n6.308", "c) trattamento di fine rapporto\n-\n6.308")
        ce = _sostituisci(ce, "Totale costi per il personale\n41.977\n80.785", "Totale costi per il personale\n42.477\n80.785")
        ce = _sostituisci(ce, "7) per servizi\n226.212\n236.952", "7) per servizi\n225.712\n236.952")
    return ce


def test_resto_di_un_raggruppamento_va_su_ce08d_ed_e_dichiarato(tmp_path):
    r = X.estrai(_abbreviato(tmp_path, ce=_ce_con_resto(gruppo_personale=True)))
    assert r["adottabile"] is True, r["rifiuto"]
    assert r["ce"]["ce08_costi_personale"] == D("42477")
    assert r["ce"]["ce08d_altri_costi_personale"] == D("500")      # mai solo sull'aggregato
    assert r["bs"]["_unclassified_mass"] == D("500")
    assert r["ignoti"][0][1] == "ce08d"


def test_resto_degli_ammortamenti_va_su_ce09c_non_su_un_confine_di_kpi(tmp_path):
    ce = _sostituisci(CE_ABBREVIATO, "b) ammortamento delle immobilizzazioni materiali\n34.614\n34.551",
                      "b) ammortamento delle immobilizzazioni materiali\n34.114\n34.551")
    r = X.estrai(_abbreviato(tmp_path, ce=ce))
    assert r["adottabile"] is True, r["rifiuto"]
    assert r["ce"]["ce09_ammortamenti"] == D("35592")
    assert r["ce"]["ce09c_svalutazioni"] == D("500")
    assert r["ce"]["ce09b_ammort_materiali"] == D("34114")
    assert r["ignoti"][0][1] == "ce09c"


# ---- fix round 1: gli importi negativi stampati fuori dalle immobilizzazioni si dichiarano -----

def test_importo_negativo_stampato_e_dichiarato_nelle_anomalie(tmp_path, monkeypatch):
    from importers import import_snello
    _vieta_modelli(monkeypatch)
    # attivita' finanziarie negative stampate (come 247): il valore si tiene, l'utente lo vede
    sp = _sostituisci(SP_ABBREVIATO,
                      "III - Attività finanziarie che non costituiscono immobilizzazioni\n12.502\n12.502",
                      "III - Attività finanziarie che non costituiscono immobilizzazioni\n(55.000)\n12.502")
    sp = _sostituisci(sp, "IV - Disponibilità liquide\n1.758\n55.886", "IV - Disponibilità liquide\n69.260\n55.886")
    ris = import_snello.importa(_abbreviato(tmp_path, sp=sp))
    assert ris.bs["sp08_attivita_finanziarie"] == D("-55000")
    assert ["sp08_attivita_finanziarie", "-55000.00"] in ris.report["anomalie"]


def test_nessuna_anomalia_senza_negativi(tmp_path, monkeypatch):
    from importers import import_snello
    _vieta_modelli(monkeypatch)
    ris = import_snello.importa(_abbreviato(tmp_path))
    assert ris.report["anomalie"] == []


# ---- fix round 1, addizione A: stessa famiglia senza piede di tassonomia ----------------------

def test_riconosciuto_per_struttura_senza_piede(tmp_path):
    path = _pdf(tmp_path, [SP_ABBREVIATO, CE_ABBREVIATO], piede="pagina")
    assert X.riconosci(path) is True
    r = X.estrai(path)
    assert r["adottabile"] is True, r["rifiuto"]
    assert r["bs"]["sp13_utile_perdita"] == D("100419")
    assert r["ce"]["ce06_servizi"] == D("226212")


def test_intestazione_di_pagina_in_mezzo_a_un_raggruppamento_non_lo_spezza(tmp_path):
    ce_a = CE_ABBREVIATO[:CE_ABBREVIATO.index("b) ammortamento delle immobilizzazioni materiali\n34.614\n34.551")]
    ce_b = CE_ABBREVIATO[len(ce_a):]
    r = X.estrai(_pdf(tmp_path, [SP_ABBREVIATO, ce_a, ce_b], piede="pagina"))
    assert r["adottabile"] is True, r["rifiuto"]
    assert r["ce"]["ce09_ammortamenti"] == D("35592")


def test_testo_senza_piede_e_senza_la_struttura_non_e_riconosciuto(tmp_path):
    assert X.riconosci("Stato patrimoniale\nAttivo\nTotale attivo\n100\n") is False
    # un prospetto qualunque (importi sulla stessa riga della didascalia) non e' questa famiglia
    solo_sp = _pdf(tmp_path, [SP_ABBREVIATO], piede="pagina")
    assert X.riconosci(solo_sp) is False
