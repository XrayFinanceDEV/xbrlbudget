"""Situazione a sezioni contrapposte con codici a segmenti azzerati e percorso di legge
davanti alle descrizioni (M.C.T. 30/06/2026): mastro "102.00.00000", conto
"102.01.00000", sottoconto "102.01.00004"; "B) I) IMMOBILIZZAZ.IMMATERIALI", fondi
"F/A - ...", totali stampati come "Totali", pagina di continuazione senza intestazione.
PDF sintetici, mai il file reale."""
from decimal import Decimal as D

import fitz

from importers.situazione_contabile_parser import classify_attivo, classify_passivo, \
    extract_situazione_contabile


def _riga(page, y, x, codice, descrizione, importo):
    page.insert_text((x, y), codice, fontsize=7)
    page.insert_text((x + 60, y), descrizione, fontsize=7)
    page.insert_text((x + 300, y), importo, fontsize=7)


def _documento(path):
    doc = fitz.open()
    p1 = doc.new_page(width=842, height=595)
    p1.insert_text((300, 30), "BILANCIO A SEZIONI CONTRAPPOSTE dal 01/01/2026 al 30/06/2026", fontsize=8)
    p1.insert_text((350, 45), "SITUAZIONE PATRIMONIALE", fontsize=8)
    p1.insert_text((150, 60), "ATTIVITA'", fontsize=8)
    p1.insert_text((560, 60), "PASSIVITA'", fontsize=8)
    attivo = [
        ("102.00.00000", "B) I) IMMOBILIZZAZ.IMMATERIALI", "10.000,00"),
        ("102.07.00000", "7) Altre immobil.immateriali", "10.000,00"),
        ("102.07.00003", "Altre Spese Pluriennali", "10.000,00"),
        ("103.00.00000", "B) II) IMMOBILZZ.MATERIALI", "500.000,00"),
        ("103.01.00000", "B) II) IMMOBILIZZ.MATERIALI", "500.000,00"),
        ("103.01.00004", "2) Macchinario", "500.000,00"),
        ("106.00.00000", "MASTRO CLIENTI", "300.000,00"),
        ("107.00.00000", "C) II) CREDITI DIVERSI", "2.000,00"),
        ("107.05.00007", "Crediti vs. Ad Immobiliare", "2.000,00"),
    ]
    passivo = [
        ("201.00.00000", "A) PATRIMONIO NETTO", "150.000,00"),
        ("201.01.00001", "Capitale sociale", "100.000,00"),
        ("201.21.00001", "Utile di esercizio", "50.000,00"),
        ("202.00.00000", "B) F.DI AMMORTAM. ORDINARIO", "200.000,00"),
        ("202.01.00004", "2) F/A - Macchinari", "200.000,00"),
        ("205.00.00000", "C) TRATTAMENTO DI FINE RAPPOR.", "40.000,00"),
        ("206.00.00000", "MASTRO FORNITORI", "300.000,00"),
    ]
    y = 80
    for i in range(max(len(attivo), len(passivo))):
        if i < len(attivo):
            _riga(p1, y, 20, *attivo[i])
        if i < len(passivo):
            _riga(p1, y, 470, *passivo[i])
        y += 12
    # pagina 2: continuazione senza intestazione di sezione
    p2 = doc.new_page(width=842, height=595)
    p2.insert_text((300, 30), "BILANCIO A SEZIONI CONTRAPPOSTE dal 01/01/2026 al 30/06/2026", fontsize=8)
    _riga(p2, 80, 20, "108.00.00000", "C) III) ATTIV.FIN.NON IMMOBIL.", "50.000,00")
    _riga(p2, 92, 20, "108.05.00012", "F.do assicurativo Unicredit", "50.000,00")
    _riga(p2, 104, 20, "109.00.00000", "C) IV) DISPONIBILITA'LIQUIDE", "8.000,00")
    _riga(p2, 116, 20, "109.10.00001", "Disponibilita' di cassa", "8.000,00")
    _riga(p2, 128, 470, "207.00.00000", "D) DEBITI DIVERSI", "160.000,00")
    _riga(p2, 140, 470, "207.20.00000", "3) Debiti vs. Banche", "160.000,00")
    # attivo 870.000 lordo; passivo 850.000 con l'utile dell'anno prima, + utile 20.000
    p2.insert_text((20, 170), "Totali", fontsize=7)
    p2.insert_text((350, 170), "870.000,00", fontsize=7)
    p2.insert_text((485, 170), "Totali", fontsize=7)
    p2.insert_text((800, 170), "850.000,00", fontsize=7)
    p2.insert_text((470, 182), "Utile di esercizio dal 01/01/2026 al 30/06/2026", fontsize=7)
    p2.insert_text((800, 182), "20.000,00", fontsize=7)

    ce = doc.new_page(width=842, height=595)
    ce.insert_text((300, 30), "BILANCIO A SEZIONI CONTRAPPOSTE dal 01/01/2026 al 30/06/2026", fontsize=8)
    ce.insert_text((350, 45), "CONTO ECONOMICO", fontsize=8)
    ce.insert_text((150, 60), "COSTI", fontsize=8)
    ce.insert_text((560, 60), "RICAVI", fontsize=8)
    _riga(ce, 80, 20, "301.00.00000", "A) 2) ESISTENZE INIZIALI", "20.000,00")
    _riga(ce, 92, 20, "302.00.00000", "B) 6) COSTI ACQUISTO MERCI", "100.000,00")
    _riga(ce, 80, 470, "401.00.00000", "A) 1) RICAVI VEND.E PRESTAZ.", "120.000,00")
    _riga(ce, 92, 470, "402.00.00000", "A) 2) RIMANENZE FINALI", "20.000,00")
    doc.save(path)
    doc.close()


def test_codici_a_segmenti_percorso_di_legge_e_pagina_di_continuazione(tmp_path):
    path = tmp_path / "mct.pdf"
    _documento(str(path))
    bs, ce = extract_situazione_contabile(str(path))
    assert bs["sp02"] == D("10000.00")
    assert bs["sp03"] == D("300000.00")          # 500.000 lordo - fondo F/A 200.000
    assert bs["sp06"] == D("302000.00")          # clienti + "Crediti vs. Ad Immobiliare"
    assert bs["sp08"] == D("50000.00")           # pagina 2, C.III
    assert bs["sp09"] == D("8000.00")
    assert bs["sp15"] == D("40000.00")
    assert bs["sp13"] == D("20000.00")
    assert bs["_plug_residual"] == D("0.00")
    assert ce["ce10"] == D("0.00")               # esistenze iniziali = rimanenze finali


def test_il_percorso_di_legge_non_decide_la_voce():
    assert classify_attivo("B) I) IMMOBILIZZAZ.IMMATERIALI") == ("sp02", True)
    assert classify_attivo("C) III) ATTIV.FIN.NON IMMOBIL.") == ("sp08", True)
    assert classify_attivo("CREDITI VS. AD IMMOBILIARE")[0] == "sp06"
    # "B)" al passivo sarebbero i fondi rischi: qui e' un fondo ammortamento
    assert classify_passivo("B) F.DI AMMORTAM. ORDINARIO")[0] == "depr_sp03"
    assert classify_passivo("C) TRATTAMENTO DI FINE RAPPOR.")[0] == "sp15"
