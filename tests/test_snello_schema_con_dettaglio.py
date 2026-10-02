"""Task 24: «schema di legge con dettaglio conti» (budget_313, budget_352).

Una famiglia di bilanci che e' uno schema di legge IV-CEE le cui didascalie portano il valore
(netto) stampato, con sotto le righe-conto (codice + descrizione + lordo, e i fondi a parte). Le
macro voci si leggono dalle sole didascalie; le righe con codice conto non entrano nella lettura.

PDF sintetici (niente dati reali), modellati sui due file veri:
- budget_313: colonne ESERCIZIO 2025 | ESERCIZIO 2024 | DIFFERENZA | SCOST., conti "03/15/015",
  negativi col meno in coda, totali come "B TOTALE IMMOBILIZZAZIONI";
- budget_352: colonna singola, conti "050101010", colonna-flag "A", righe "Totale X" dopo i figli,
  piede "Pagina N di M".
"""
from __future__ import annotations

from decimal import Decimal as D

import fitz
import pytest

from importers import import_snello
from importers.import_snello import deterministico as DET
from importers.standard_ivcee_parser import (
    extract_ivcee_didascalie,
    extract_standard_ivcee_balances,
    riconosci_schema_con_dettaglio,
)

FONT = "helv"


def _dest(page, x_right, y, testo, fontsize=8):
    larghezza = fitz.get_text_length(testo, fontname=FONT, fontsize=fontsize)
    page.insert_text((x_right - larghezza, y), testo, fontname=FONT, fontsize=fontsize)


def _sx(page, x, y, testo, fontsize=8):
    page.insert_text((x, y), testo, fontname=FONT, fontsize=fontsize)


# --------------------------------------------------------------------------- budget_313
# (etichetta, [corrente, precedente, differenza, scostamento] oppure None). Un'etichetta che
# comincia col codice conto e' una riga-conto: stampa il LORDO e, per i fondi, il segno meno in coda.
_RIGHE_313_SP = [
    ("STATO PATRIMONIALE - ATTIVO", None),
    ("A) CREDITI VERSO SOCI P/VERS.TI ANCORA DOVUTI", ["0,00", "0,00", "0,00", ""]),
    ("B) IMMOBILIZZAZIONI", None),
    ("I) IMMOBILIZZAZIONI IMMATERIALI", ["500,00", "800,00", "300,00-", "37,500-"]),
    ("03/15/015 SPESE DI COSTITUZIONE", ["600,00", "900,00", "300,00-", "33,333-"]),
    ("03/15/016 F/AMM.SPESE DI COSTITUZIONE", ["100,00-", "100,00-", "0,00", ""]),
    ("II) IMMOBILIZZAZIONI MATERIALI", ["0,00", "0,00", "0,00", ""]),
    ("III) IMMOBILIZZAZIONI FINANZIARIE", ["0,00", "0,00", "0,00", ""]),
    ("B TOTALE IMMOBILIZZAZIONI", ["500,00", "800,00", "300,00-", "37,500-"]),
    ("C) ATTIVO CIRCOLANTE", None),
    ("I) RIMANENZE", ["0,00", "0,00", "0,00", ""]),
    ("II) CREDITI :", None),
    ("1) Esigibili entro l'esercizio successivo", ["300,00", "250,00", "50,00", "20,000"]),
    ("14/00000 CREDITI V/CLIENTI", ["300,00", "250,00", "50,00", "20,000"]),
    ("II TOTALE CREDITI :", ["300,00", "250,00", "50,00", "20,000"]),
    ("III) ATTIVITA' FINANZIARIE (non immobilizz.)", ["0,00", "0,00", "0,00", ""]),
    ("IV) DISPONIBILITA' LIQUIDE", ["200,00", "100,00", "100,00", "100,000"]),
    ("24/15/005 DENARO IN CASSA", ["200,00", "100,00", "100,00", "100,000"]),
    ("C TOTALE ATTIVO CIRCOLANTE", ["500,00", "350,00", "150,00", "42,857"]),
    ("D) RATEI E RISCONTI", ["0,00", "0,00", "0,00", ""]),
    ("TOTALE STATO PATRIMONIALE - ATTIVO", ["1.000,00", "1.150,00", "150,00-", "13,043-"]),
    ("STATO PATRIMONIALE - PASSIVO", None),
    ("A) PATRIMONIO NETTO", None),
    ("I) Capitale", ["0,00", "0,00", "0,00", ""]),
    ("IX) Utile (perdita) dell' esercizio", ["150,00", "120,00", "30,00", "25,000"]),
    ("Perdita ripianata nell'esercizio", ["0,00", "0,00", "0,00", ""]),
    ("A TOTALE PATRIMONIO NETTO", ["150,00", "120,00", "30,00", "25,000"]),
    ("B) FONDI PER RISCHI E ONERI", ["0,00", "0,00", "0,00", ""]),
    ("C) TRATTAMENTO FINE RAPPORTO LAVORO SUBORDINATO", ["0,00", "0,00", "0,00", ""]),
    ("D) DEBITI", None),
    ("1) Esigibili entro l'esercizio successivo", ["850,00", "1.030,00", "180,00-", "17,476-"]),
    ("40/00000 DEBITI V/FORNITORI", ["850,00", "1.030,00", "180,00-", "17,476-"]),
    ("D TOTALE DEBITI", ["850,00", "1.030,00", "180,00-", "17,476-"]),
    ("E) RATEI E RISCONTI", ["0,00", "0,00", "0,00", ""]),
    ("TOTALE STATO PATRIMONIALE - PASSIVO", ["1.000,00", "1.150,00", "150,00-", "13,043-"]),
]

_RIGHE_313_CE = [
    ("CONTO ECONOMICO", None),
    ("A) VALORE DELLA PRODUZIONE", None),
    ("1) Ricavi delle vendite e delle prestazioni", ["2.000,00", "1.800,00", "200,00", "11,111"]),
    ("58/15/005 COMP. PROFESS. PERCEPITI", ["2.100,00-", "1.900,00-", "200,00-", "10,526"]),
    ("5) Altri ricavi e proventi", ["0,00", "0,00", "0,00", ""]),
    ("A TOTALE VALORE DELLA PRODUZIONE", ["2.000,00", "1.800,00", "200,00", "11,111"]),
    ("B) COSTI DELLA PRODUZIONE", None),
    ("6) per materie prime,suss.,di cons.e merci", ["100,00", "90,00", "10,00", "11,111"]),
    ("66/30/025 CANCELLERIA", ["100,00", "90,00", "10,00", "11,111"]),
    ("7) per servizi", ["1.200,00", "1.000,00", "200,00", "20,000"]),
    ("8) per godimento di beni di terzi", ["0,00", "0,00", "0,00", ""]),
    ("9) per il personale:", None),
    ("a) salari e stipendi", ["300,00", "250,00", "50,00", "20,000"]),
    ("9 totale per il personale:", ["300,00", "250,00", "50,00", "20,000"]),
    ("10) ammortamenti e svalutazioni:", None),
    ("b) ammort. immobilizz. materiali", ["100,00", "100,00", "0,00", ""]),
    ("10 totale ammortamenti e svalutazioni:", ["100,00", "100,00", "0,00", ""]),
    ("14) oneri diversi di gestione", ["0,00", "0,00", "0,00", ""]),
    ("B TOTALE COSTI DELLA PRODUZIONE", ["1.700,00", "1.440,00", "260,00", "18,055"]),
    ("A-B TOTALE DIFF. TRA VALORE E COSTI DI PRODUZIONE", ["300,00", "360,00", "60,00-", "16,666-"]),
    ("C) PROVENTI E ONERI FINANZIARI", None),
    ("17) interessi e altri oneri finanziari da:", None),
    ("e) altri debiti", ["50,00", "40,00", "10,00", "25,000"]),
    ("17 totale interessi e altri oneri finanziari da:", ["50,00", "40,00", "10,00", "25,000"]),
    ("15+16-17+-17B TOTALE DIFF. PROVENTI E ONERI FINANZIARI", ["50,00-", "40,00-", "10,00-", "25,000"]),
    ("D) RETTIFICHE DI VAL. DI ATTIV. E PASSIV. FINANZIARIE", None),
    ("A-B+-C+-D TOTALE RIS. PRIMA DELLE IMPOSTE", ["250,00", "320,00", "70,00-", "21,875-"]),
    ("20) IMPOSTE REDD.EERC.,CORRENTI,DIFFERITE,ANTICIPATE", None),
    ("20 TOTALE IMPOSTE REDD.EERC.,CORRENTI,DIFFERITE,ANTICIPATE", ["100,00", "200,00", "100,00-", "50,000-"]),
    ("21) UTILE (PERDITE) DELL'ESERCIZIO", ["150,00", "120,00", "30,00", "25,000"]),
]


def _scrivi_pagina_313(doc, righe):
    page = doc.new_page(width=595, height=842)
    _dest(page, 366, 100, "ESERCIZIO")
    _dest(page, 438, 100, "ESERCIZIO")
    _dest(page, 513, 100, "DIFFERENZA")
    _dest(page, 566, 100, "SCOST.")
    _dest(page, 350, 110, "2025")
    _dest(page, 422, 110, "2024")
    y = 140
    for label, valori in righe:
        _sx(page, 74, y, label)
        if valori:
            for x, v in zip((373, 445, 519, 574), valori):
                if v:
                    _dest(page, x, y, v)
        y += 10
    return page


def _pdf_313(path, *, righe_sp=None, righe_ce=None) -> str:
    doc = fitz.open()
    _scrivi_pagina_313(doc, righe_sp or _RIGHE_313_SP)
    _scrivi_pagina_313(doc, righe_ce or _RIGHE_313_CE)
    doc.save(str(path))
    return str(path)


# --------------------------------------------------------------------------- budget_352
def _pdf_352(path, *, utile_ce="200,00", scadenze=False) -> str:
    """Colonna singola, conti "050101010" con flag "A", «Totale X» dopo i figli."""
    righe = [
        ("BILANCIO AL 31/12/2025", None, False),
        ("31/12/2025", None, False),
        ("STATO PATRIMONIALE ATTIVO", None, False),
        ("A) Crediti verso soci per versamenti ancora dovuti", None, False),
        ("B) Immobilizzazioni", None, False),
        (" I) Immobilizzazioni immateriali", None, False),
        ("   1) Costi di impianto e di ampliamento", "100,00", False),
        ("050101010 Spese di costituzione e modifica societa", "2.100,00", True),
        ("050101510 F.do amm. spese di costituzione", "-2.000,00", True),
        ("   Totale Immobilizzazioni immateriali", "100,00", False),
        (" II) Immobilizzazioni materiali", None, False),
        ("   2) Impianti e macchinario", "400,00", False),
        ("06015101510 Impianti specifici", "1.000,00", True),
        ("06015151510 F.do amm. impianti specifici", "-600,00", True),
        ("   Totale Immobilizzazioni materiali", "400,00", False),
        (" Totale Immobilizzazioni (B)", "500,00", False),
        ("C) Attivo circolante", None, False),
        (" I) Rimanenze", None, False),
        ("   1) Rimanenze materie prime, sussidiarie e di consumo", "300,00", False),
        ("090101010 Rimanenze materie prime", "300,00", True),
        ("   Totale Rimanenze", "300,00", False),
        (" II) Crediti", None, False),
        ("   Crediti esigibili entro l'esercizio successivo", "400,00", False),
        ("   1) Crediti verso clienti", None, False),
        ("     a) Crediti verso clienti esigibili entro l'esercizio successivo", "400,00", False),
        ("100101003 Crediti vs clienti entro es.succ.", "400,00", True),
        ("   Totale crediti verso clienti", "400,00", False),
        ("   Totale crediti", "400,00", False),
        (" IV) Disponibilita liquide", None, False),
        ("   1) Depositi bancari e postali", "700,00", False),
        ("110101010 Banca c/c", "700,00", True),
        ("   Totale disponibilita liquide", "700,00", False),
        ("Totale attivo circolante (C)", "1.400,00", False),
        ("D) Ratei e risconti attivi", "100,00", False),
        ("Totale stato patrimoniale attivo", "2.000,00", False),
        ("Pagina 1 di 2", None, False),
        ("STATO PATRIMONIALE PASSIVO", None, False),
        ("A) Patrimonio netto", None, False),
        (" I) Capitale", "1.000,00", False),
        (" IX) Utile (perdita) dell'esercizio", "200,00", False),
        ("Totale patrimonio netto (A)", "1.200,00", False),
        ("B) Fondi per rischi e oneri", "0,00", False),
        ("C) Trattamento di fine rapporto di lavoro subordinato", "100,00", False),
        ("D) Debiti", None, False),
        ("   Debiti esigibili entro l'esercizio successivo", "700,00", False),
        ("   7) Debiti verso fornitori", None, False),
        ("     a) Debiti verso fornitori esigibili entro l'esercizio successivo", "700,00", False),
        ("200101010 Fornitori", "700,00", True),
        ("   Totale debiti verso fornitori", "700,00", False),
        ("Totale debiti (D)", "700,00", False),
        ("E) Ratei e risconti passivi", "0,00", False),
        ("Totale stato patrimoniale passivo", "2.000,00", False),
        ("CONTO ECONOMICO", None, False),
        ("A) Valore della produzione", None, False),
        ("1) Ricavi delle vendite e delle prestazioni", "3.000,00", False),
        ("Totale valore della produzione (A)", "3.000,00", False),
        ("B) Costi della produzione", None, False),
        ("7) per servizi", "2.000,00", False),
        ("9) per il personale", None, False),
        ("a) salari e stipendi", "500,00", False),
        ("Totale costi per il personale", "500,00", False),
        ("10) ammortamenti e svalutazioni", None, False),
        ("b) ammortamento delle immobilizzazioni materiali", "100,00", False),
        ("Totale ammortamenti e svalutazioni", "100,00", False),
        ("Totale costi della produzione (B)", "2.600,00", False),
        ("Differenza tra valore e costi della produzione (A - B)", "400,00", False),
        ("C) Proventi e oneri finanziari", None, False),
        ("Totale proventi e oneri finanziari (15 + 16 - 17 + - 17-bis)", "0,00", False),
        ("D) Rettifiche di valore di attivita e passivita finanziarie", "0,00", False),
        ("Risultato prima delle imposte (A - B +- C +- D)", "400,00", False),
        ("20) Imposte sul reddito dell'esercizio, correnti, differite e anticipate", None, False),
        ("Totale delle imposte sul reddito dell'esercizio, correnti, differite e anticipate", "200,00", False),
        ("21) Utile (perdita) dell'esercizio", utile_ce, False),
    ]
    if scadenze:
        # crediti 300 entro + 100 oltre; debiti 600 entro + 100 oltre (banche)
        sost = {
            "   Crediti esigibili entro l'esercizio successivo": ("   Crediti esigibili entro l'esercizio successivo", "300,00"),
            "   Debiti esigibili entro l'esercizio successivo": ("   Debiti esigibili entro l'esercizio successivo", "600,00"),
        }
        nuove = []
        for label, valore, conto in righe:
            if label in sost:
                nuove.append((label, sost[label][1], conto))
                if label.startswith("   Crediti"):
                    nuove.append(("   Crediti esigibili oltre l'esercizio successivo", "100,00", False))
                else:
                    nuove.append(("   Debiti esigibili oltre l'esercizio successivo", "100,00", False))
            elif label.startswith("     a) Debiti verso fornitori"):
                nuove.append(("   4) Debiti verso banche", None, False))
                nuove.append(("     b) Debiti verso banche esigibili oltre l'esercizio successivo", "100,00", False))
                nuove.append(("   Totale debiti verso banche", "100,00", False))
                nuove.append((label, "600,00", conto))
            elif label == "   Totale debiti verso fornitori":
                nuove.append((label, "600,00", conto))
            elif label.startswith("200101010"):
                nuove.append((label, "600,00", conto))
            else:
                nuove.append((label, valore, conto))
        righe = nuove
    doc = fitz.open()
    page = doc.new_page(width=595, height=2000)
    y = 40
    for label, valore, conto in righe:
        _sx(page, 30, y, label)
        if conto:
            _sx(page, 370, y, "A")
        if valore:
            _dest(page, 540, y, valore)
        y += 10
    doc.save(str(path))
    return str(path)


# --------------------------------------------------------------------------- riconoscimento
def test_313_si_riconosce_come_schema_con_righe_conto(tmp_path):
    f = _pdf_313(tmp_path / "a.pdf")
    r = riconosci_schema_con_dettaglio(f)
    assert r is not None and r["conti"] >= 5 and r["didascalie"] >= 12


def test_352_si_riconosce_come_schema_con_righe_conto(tmp_path):
    f = _pdf_352(tmp_path / "b.pdf")
    assert riconosci_schema_con_dettaglio(f) is not None


def test_un_bilancio_di_verifica_vero_non_e_questa_famiglia(tmp_path):
    """Un bilancio di verifica (nessuna didascalia di legge con importo) resta in modo "conti"."""
    from tests.test_snello_deterministico import _pdf_situazione_contabile
    f = _pdf_situazione_contabile(tmp_path / "tb.pdf")
    assert riconosci_schema_con_dettaglio(f) is None
    bs, ce, conti = extract_ivcee_didascalie(f)
    assert bs is None and ce is None


def test_uno_schema_di_legge_senza_conti_sotto_non_e_questa_famiglia(tmp_path):
    from tests.test_snello_deterministico import _pdf_comparativo_bilanciato
    f = _pdf_comparativo_bilanciato(tmp_path / "legge.pdf")
    assert riconosci_schema_con_dettaglio(f) is None


# --------------------------------------------------------------------------- lettura offline
def test_313_macro_voci_dalle_didascalie_e_totali_stampati(tmp_path):
    bs, ce, conti = extract_ivcee_didascalie(_pdf_313(tmp_path / "a.pdf"))
    assert conti == 7
    assert bs["totale_attivo"] == bs["totale_passivo"] == D("1000.00")
    assert bs["sp02_immob_immateriali"] == D("500.00")      # netto della didascalia, non il lordo 600
    assert bs["sp06_crediti_breve"] == D("300.00")
    assert bs["sp09_disponibilita_liquide"] == D("200.00")
    assert bs["sp13_utile_perdita"] == D("150.00")
    assert bs["sp16_debiti_breve"] == D("850.00")
    assert ce["ce01_ricavi_vendite"] == D("2000.00")
    assert ce["ce06_servizi"] == D("1200.00")
    assert ce["ce08_costi_personale"] == D("300.00")
    assert ce["ce09_ammortamenti"] == D("100.00")
    assert ce["ce15_oneri_finanziari"] == D("50.00")
    assert ce["ce20_imposte"] == D("100.00")


def test_313_la_colonna_differenza_non_e_mai_un_saldo(tmp_path):
    """Le colonne 3 e 4 (DIFFERENZA, SCOST.) hanno importi diversi da corrente e comparato: un
    totale preso dalla quarta colonna non chiuderebbe mai."""
    bs, ce, _ = extract_ivcee_didascalie(_pdf_313(tmp_path / "a.pdf"))
    assert bs["totale_attivo"] == D("1000.00") != D("150.00")
    assert bs["sp13_utile_perdita"] == D("150.00") != D("30.00")


def _pdf_313_con_date(path) -> str:
    """Lo stesso documento con l'intestazione a date complete (31/12/2025 | 31/12/2024) e due sole
    colonne: il layout che il parser storico riconosce, con le etichette di 313 (varianti)."""
    doc = fitz.open()
    for righe in (_RIGHE_313_SP, _RIGHE_313_CE):
        page = doc.new_page(width=595, height=842)
        _dest(page, 373, 100, "31/12/2025")
        _dest(page, 445, 100, "31/12/2024")
        y = 140
        for label, valori in righe:
            _sx(page, 74, y, label)
            if valori:
                for x, v in zip((373, 445), valori[:2]):
                    if v:
                        _dest(page, x, y, v)
            y += 10
    doc.save(str(path))
    return str(path)


def test_i_punti_di_ingresso_storici_non_leggono_le_varianti(tmp_path):
    """F6: senza ``varianti`` i due estrattori restituiscono cio' che restituivano a d0b20d5
    (None su questo documento: etichette "i) immobilizzazioni", "totale diff. ...", conto
    economico con totali "N totale ..."); con ``varianti=True`` lo stesso file si legge."""
    from importers.standard_ivcee_parser import extract_standard_ivcee_income
    f = _pdf_313_con_date(tmp_path / "d.pdf")
    assert extract_standard_ivcee_balances(f) == (None, None)
    assert extract_standard_ivcee_income(f) == (None, None)
    bs, ce, _ = extract_ivcee_didascalie(f)
    assert bs["totale_attivo"] == D("1000.00") and ce["ce20_imposte"] == D("100.00")


def test_il_compatto_storico_non_legge_i_totali_stampati_senza_flag(tmp_path):
    from importers.standard_ivcee_parser import extract_standard_ivcee_income
    f = _pdf_352(tmp_path / "b.pdf")
    assert extract_standard_ivcee_income(f)[0] is None          # "10) ammortamenti" senza importo
    assert extract_standard_ivcee_income(f, varianti=True)[0] is not None


def test_352_macro_voci_dalle_didascalie(tmp_path):
    bs, ce, conti = extract_ivcee_didascalie(_pdf_352(tmp_path / "b.pdf"))
    assert conti == 8
    assert bs["totale_attivo"] == bs["totale_passivo"] == D("2000.00")
    assert bs["sp13_utile_perdita"] == D("200.00")
    assert ce["ce01_ricavi_vendite"] == D("3000.00")
    assert ce["ce08_costi_personale"] == D("500.00")
    assert ce["ce09_ammortamenti"] == D("100.00")
    assert ce["ce20_imposte"] == D("200.00")


def test_352_il_piede_di_pagina_non_e_un_importo(tmp_path):
    """"Pagina 1 di 2": il numero cade a destra di x=300 e finirebbe fra gli importi."""
    bs, ce, _ = extract_ivcee_didascalie(_pdf_352(tmp_path / "b.pdf"))
    assert bs is not None and bs["totale_debiti"] == D("700.00")


# --------------------------------------------------------------------------- non adottare
def test_didascalie_che_non_quadrano_non_si_adottano(tmp_path):
    """Un CE le cui didascalie non chiudono sul risultato stampato (utile CE != utile SP) non si
    legge: mai un importo inventato per farlo tornare."""
    f = _pdf_352(tmp_path / "x.pdf", utile_ce="999,00")
    bs, ce, conti = extract_ivcee_didascalie(f)
    assert conti == 8 and ce is None
    esito = DET.tentativo(f)
    assert not esito["adottato"]


def test_313_sbilanciato_nelle_didascalie_non_si_adotta(tmp_path):
    righe = [(l, v) for l, v in _RIGHE_313_SP]
    righe[-1] = ("TOTALE STATO PATRIMONIALE - PASSIVO", ["1.200,00", "1.150,00", "50,00", "4,000"])
    f = _pdf_313(tmp_path / "x.pdf", righe_sp=righe)
    bs, ce, _ = extract_ivcee_didascalie(f)
    assert bs is None
    assert not DET.tentativo(f)["adottato"]


# --------------------------------------------------------------------------- tentativo / importa
def test_tentativo_adotta_313_e_352_con_il_parser_dello_schema_con_dettaglio(tmp_path):
    for f in (_pdf_313(tmp_path / "a.pdf"), _pdf_352(tmp_path / "b.pdf")):
        esito = DET.tentativo(f)
        assert esito["adottato"], esito
        assert esito["esito"] in ("ok", "tappo")
        # 313 (intestazione a soli anni) la legge solo il parser delle didascalie; 352 la legge
        # anche il parser standard di sempre, che ora riconosce le sue didascalie.
        assert esito["parser"] in ("schema_legge_con_dettaglio", "standard_ivcee_parser")


def test_tentativo_313_e_del_parser_delle_didascalie(tmp_path):
    esito = DET.tentativo(_pdf_313(tmp_path / "a.pdf"))
    assert esito["adottato"] and esito["parser"] == "schema_legge_con_dettaglio"
    assert esito["conti_esclusi"] == 7


def _vision_vietata(*a, **k):
    raise AssertionError("la struttura (vision) non deve girare quando il deterministico adotta")


def test_importa_non_chiama_la_struttura_se_il_deterministico_adotta(tmp_path):
    f = _pdf_313(tmp_path / "a.pdf")
    r = import_snello.importa(f, analizza=_vision_vietata)
    assert r.report["esito"] in ("ok", "tappo")
    assert r.report["fonte"] == "deterministico:schema_legge_con_dettaglio"
    assert r.report["modo"] == "legge_con_dettaglio"
    assert r.report["struttura"]["stato"] == "non_richiesta"
    assert r.report["struttura"]["fonte"] == "deterministico"
    assert r.report["struttura"]["chiamate_vision"] == 0
    assert r.report["letture"]["chiamate"] == 0
    assert r.bs["sp13_utile_perdita"] == D("150.00")


def test_importa_senza_adozione_la_struttura_gira_come_prima(tmp_path):
    """Un documento che nessun parser adotta passa ancora dalla struttura."""
    chiamate = []

    def _analizza(p, **kw):
        chiamate.append(p)
        raise RuntimeError("struttura chiamata")

    f = tmp_path / "vuoto.pdf"
    doc = fitz.open()
    pg = doc.new_page()
    pg.insert_text((50, 50), "Lettera accompagnatoria senza alcun bilancio", fontname=FONT)
    doc.save(str(f))
    with pytest.raises(import_snello.SnelloNonRiuscito) as exc:
        import_snello.importa(str(f), analizza=_analizza)
    assert chiamate and exc.value.report["fase"] == "struttura"


def test_il_report_di_struttura_deterministica_ha_la_forma_attesa_da_pdf_importer(tmp_path):
    """``pdf_importer`` legge ``report["modo"]`` e ``struttura.pagine_dettagli()``."""
    r = import_snello.importa(_pdf_352(tmp_path / "b.pdf"), analizza=_vision_vietata)
    assert r.report["modo"] in ("legge", "legge_con_dettaglio")
    pagine = r.struttura.pagine_dettagli()
    assert pagine is None or isinstance(pagine, set)


def test_un_bilancio_di_verifica_resta_in_modo_conti_come_prima(tmp_path):
    from tests.test_snello_deterministico import _pdf_situazione_contabile
    f = _pdf_situazione_contabile(tmp_path / "tb.pdf")
    esito = DET.tentativo(f)
    assert esito["parser"] != "schema_legge_con_dettaglio"


# --------------------------------------------------------------------------- modo e report della struttura
def test_il_modo_legge_con_dettaglio_si_decide_dal_testo_non_dal_voto_della_vision(tmp_path):
    """Anche con una vision che vota "elenco_piatto" (conti), un documento con didascalie di legge
    e righe-conto sotto e' "legge_con_dettaglio"."""
    from importers.struttura_documento.analisi import analizza_struttura
    f = _pdf_313(tmp_path / "a.pdf")

    def _mappa(pagina_png, n, **kw):
        return {"pagina": n, "tipo_pagina": "prospetto_sp", "schema": "elenco_piatto", "sezioni": []}

    s = analizza_struttura(f, mappa_pagina_fn=_mappa)
    assert s.modo == "legge_con_dettaglio"
    assert s.macro_include_dettaglio is True


def test_il_report_della_struttura_porta_i_voti_della_vision(tmp_path):
    from importers.struttura_documento.analisi import Struttura
    s = Struttura(fonte="vision", route=None, pagine_sp=[1], pagine_ce=[2], pagine_dettaglio=[],
                  chiamate_vision=2, secondi=0.1,
                  mappe=[{"pagina": 1, "tipo_pagina": "prospetto_sp", "schema": "iv_cee_di_legge"},
                         {"pagina": 2, "tipo_pagina": "prospetto_ce", "schema": "elenco_piatto"},
                         {"pagina": 3, "tipo_pagina": "nota_o_testo"}])
    rep = s.report()
    assert rep["schemi"] == {"iv_cee_di_legge": 1, "elenco_piatto": 1}
    assert rep["tipi_pagina"] == {"prospetto_sp": 1, "prospetto_ce": 1, "nota_o_testo": 1}


# --------------------------------------------------------------------------- ripiego Qwen sul testo filtrato
def _struttura_stub(modo, **kw):
    from importers.struttura_documento.analisi import Struttura
    base = dict(fonte="vision", route=None, pagine_sp=[1, 2], pagine_ce=[2], pagine_dettaglio=[],
                chiamate_vision=1, secondi=0.1, mappe=[], modo=modo,
                colonne_sp=["saldo_corrente", "saldo_precedente"],
                colonne_ce=["saldo_corrente", "saldo_precedente"],
                intestazioni_sp=["2025", "2024"], intestazioni_ce=["2025", "2024"],
                pagine_senza_testo=[], macro_include_dettaglio=True)
    base.update(kw)
    return Struttura(**base)


def test_qwen_legge_il_testo_senza_le_righe_conto_in_modo_legge_con_dettaglio(tmp_path):
    """Quando il parser delle didascalie non adotta (qui: totale stampato che non chiude), il
    ripiego e' Qwen modo "legge" sul testo FILTRATO: nessuna riga con codice conto nel prompt."""
    righe = list(_RIGHE_313_SP)
    righe[-1] = ("TOTALE STATO PATRIMONIALE - PASSIVO", ["1.200,00", "1.150,00", "50,00", "4,000"])
    f = _pdf_313(tmp_path / "x.pdf", righe_sp=righe)
    visti = []

    def voci(testo, intestazioni, nota=""):
        visti.append(testo)
        return {"corrente": [("SPA.C.IV.1", D("1000")), ("SPP.A.IX", D("150")), ("SPP.D.O", D("850")),
                             ("CE.A.1", D("2000")), ("CE.B.7", D("1850")), ("CE.21", D("150"))],
                "precedente": [], "totali": {}}

    r = import_snello.importa(f, analizza=lambda p, **k: _struttura_stub("legge_con_dettaglio"),
                              leggi_voci=voci)
    assert r.report["modo"] == "legge_con_dettaglio"
    assert visti
    for t in visti:
        assert "03/15/015" not in t and "14/00000" not in t and "40/00000" not in t
        assert "CREDITI V/CLIENTI" not in t and "DENARO IN CASSA" not in t
    assert any("IMMOBILIZZAZIONI IMMATERIALI" in t for t in visti)   # le didascalie restano


def test_in_modo_legge_ordinario_le_righe_conto_restano_nel_prompt(tmp_path):
    """Simmetrico: il filtro vale solo per "legge_con_dettaglio", non per ogni "legge"."""
    righe = list(_RIGHE_313_SP)
    righe[-1] = ("TOTALE STATO PATRIMONIALE - PASSIVO", ["1.200,00", "1.150,00", "50,00", "4,000"])
    f = _pdf_313(tmp_path / "x.pdf", righe_sp=righe)
    visti = []

    def voci(testo, intestazioni, nota=""):
        visti.append(testo)
        return {"corrente": [("SPA.C.IV.1", D("1000")), ("SPP.A.IX", D("150")), ("SPP.D.O", D("850")),
                             ("CE.A.1", D("2000")), ("CE.B.7", D("1850")), ("CE.21", D("150"))],
                "precedente": [], "totali": {}}

    import_snello.importa(f, analizza=lambda p, **k: _struttura_stub("legge", macro_include_dettaglio=False),
                          leggi_voci=voci)
    assert any("03/15/015" in t for t in visti)


# --------------------------------------------------------------------------- F1: falsi positivi
def _pdf_note_con_riferimenti_di_legge(path) -> str:
    """Uno schema di legge senza conti sotto, piu' una pagina di nota con righe che cominciano
    come un codice ("173/2008 di recepimento...", "23/2020") ma senza importo (budget_162)."""
    from tests.test_snello_deterministico import _pdf_comparativo_bilanciato
    base = _pdf_comparativo_bilanciato(path)
    doc = fitz.open(base)
    pg = doc.new_page()
    y = 50
    for t in ("173/2008 di recepimento della direttiva", "23/2020 convertito in legge",
              "139/2015 e relativo regolamento", "12/2025 delibera", "5.2 nota"):
        pg.insert_text((40, y), t, fontname=FONT, fontsize=9)
        y += 14
    doc.saveIncr()
    return base


def test_riferimenti_di_legge_senza_importo_non_sono_conti(tmp_path):
    assert riconosci_schema_con_dettaglio(_pdf_note_con_riferimenti_di_legge(tmp_path / "n.pdf")) is None


def test_un_kpi_numerato_senza_importo_non_e_un_conto(tmp_path):
    from tests.test_snello_deterministico import _pdf_comparativo_bilanciato
    f = _pdf_comparativo_bilanciato(tmp_path / "k.pdf")
    doc = fitz.open(f)
    pg = doc.new_page()
    for i, t in enumerate(("1.1 roe", "3.1 current ratio", "6.2 posizione finanziaria netta",
                           "2.2 roi", "4.1 indice")):
        pg.insert_text((40, 50 + 14 * i), t, fontname=FONT, fontsize=9)
    doc.saveIncr()
    assert riconosci_schema_con_dettaglio(f) is None


def test_il_predicato_del_conto_e_uno_solo():
    from importers.standard_ivcee_parser import riga_conto
    assert riga_conto("03/15/015 SPESE DI COSTITUZIONE", True)
    assert not riga_conto("03/15/015 SPESE DI COSTITUZIONE", False)       # senza importo
    assert not riga_conto("31/12/2025 31/12/2024", True)                  # data
    assert not riga_conto("1.671.195", True)                              # importo spezzato
    assert riga_conto("CII1A 208.00121 CLIENTI", True)                    # riclassificato


def test_una_riga_di_intestazione_con_date_sopravvive_al_filtro_per_qwen(tmp_path):
    righe = list(_RIGHE_313_SP)
    righe[-1] = ("TOTALE STATO PATRIMONIALE - PASSIVO", ["1.200,00", "1.150,00", "50,00", "4,000"])
    f = _pdf_313(tmp_path / "x.pdf", righe_sp=righe)
    doc = fitz.open(f)
    doc[0].insert_text((74, 125), "31/12/2025 31/12/2024", fontname=FONT, fontsize=8)
    doc[0].insert_text((400, 125), "1,00", fontname=FONT, fontsize=8)
    doc.saveIncr()
    visti = []

    def voci(testo, intestazioni, nota=""):
        visti.append(testo)
        return {"corrente": [], "precedente": [], "totali": {}}

    with pytest.raises(import_snello.SnelloNonRiuscito):
        import_snello.importa(f, analizza=lambda p, **k: _struttura_stub("legge_con_dettaglio"), leggi_voci=voci)
    assert any("31/12/2025 31/12/2024" in t for t in visti)


# --------------------------------------------------------------------------- F3: scadenze stampate
def test_352_le_scadenze_stampate_si_leggono(tmp_path):
    bs, ce, _ = extract_ivcee_didascalie(_pdf_352(tmp_path / "s.pdf", scadenze=True))
    assert bs is not None
    assert bs["sp06_crediti_breve"] == D("300.00") and bs["sp07_crediti_lungo"] == D("100.00")
    assert bs["sp16_debiti_breve"] == D("600.00") and bs["sp17_debiti_lungo"] == D("100.00")
    assert bs["sp17a_debiti_banche_lungo"] == D("100.00")
    assert bs["totale_attivo"] == bs["totale_passivo"] == D("2000.00")
    assert "_source_maturity_unspecified" not in bs


def test_352_senza_scadenze_stampate_resta_a_breve_e_dichiarato(tmp_path):
    bs, _, _ = extract_ivcee_didascalie(_pdf_352(tmp_path / "b.pdf"))
    assert bs["sp07_crediti_lungo"] == D("0") and bs["sp17_debiti_lungo"] == D("0")
    assert bs["_source_maturity_unspecified"] == D("1")


# --------------------------------------------------------------------------- F7 / F8 / vuoto
def _pdf_pagine(path, pagine):
    doc = fitz.open()
    for righe in pagine:
        pg = doc.new_page()
        y = 50
        for t in righe:
            pg.insert_text((40, y), t, fontname=FONT, fontsize=9)
            y += 14
    doc.save(str(path))
    return str(path)


def _importi(n):
    return [f"voce {i} {1000 + i},00" for i in range(n)]


def test_pagine_dettagli_da_testo_salta_l_indice_che_nomina_i_titoli(tmp_path):
    from importers.struttura_documento.analisi import pagine_dettagli_da_testo
    f = _pdf_pagine(tmp_path / "p.pdf", [
        ["Indice", "STATO PATRIMONIALE", "CONTO ECONOMICO"],           # indice: nessun importo
        ["STATO PATRIMONIALE ATTIVO"] + _importi(6),
        ["STATO PATRIMONIALE PASSIVO"] + _importi(6),
        ["CONTO ECONOMICO"] + _importi(6),
        ["Nota integrativa"] + _importi(1),
    ])
    assert pagine_dettagli_da_testo(f) == [2, 3]


def test_pagine_dettagli_da_testo_include_la_pagina_dove_lo_sp_finisce_sopra_il_titolo_ce(tmp_path):
    from importers.struttura_documento.analisi import pagine_dettagli_da_testo
    f = _pdf_pagine(tmp_path / "q.pdf", [
        ["STATO PATRIMONIALE ATTIVO"] + _importi(6),
        ["STATO PATRIMONIALE PASSIVO"] + _importi(4) + ["CONTO ECONOMICO"] + _importi(4),
        ["segue"] + _importi(6),
    ])
    assert pagine_dettagli_da_testo(f) == [1, 2]


def test_il_nuovo_estrattore_dichiara_le_chiavi_diagnostiche_anche_a_zero(tmp_path):
    bs, _, _ = extract_ivcee_didascalie(_pdf_313(tmp_path / "a.pdf"))
    assert bs["_unclassified_mass"] == D("0") and bs["_plug_residual"] == D("0")


def test_un_estrazione_vuota_non_si_adotta(tmp_path):
    """Attivo = Passivo = 0 non e' una quadratura: didascalie tutte a zero + righe-conto."""
    f = _pdf_313(tmp_path / "z.pdf", righe_sp=[(l, [("0,00" if v else v) for v in vals[:1]] + ["0,00", "0,00", ""] if vals else None)
                                              for l, vals in _RIGHE_313_SP],
                 righe_ce=[(l, ["0,00", "0,00", "0,00", ""] if vals else None) for l, vals in _RIGHE_313_CE])
    assert not DET.tentativo(f)["adottato"]
