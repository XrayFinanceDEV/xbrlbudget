"""Bilancio di verifica a "Totale Sub / Totale Mastro" (budget_1343, piede C44-1.0): conto
"NN NNNNNNN", importo del conto nella colonna Totale Sub, riga del mastro con il codice
dell'ultimo conto e l'importo nella colonna Totale Mastro, segno meno in coda. PDF sintetico."""
from decimal import Decimal as D

import fitz

from importers.import_snello.deterministico import tentativo
from importers.situazione_contabile_parser import extract_situazione_contabile, is_verifica_sub_mastro

FONT = fitz.Font("helv")
SUB, MASTRO = 407, 558


def _riga(p, y, codice, desc, importo=None, colonna=SUB):
    p.insert_text((18, y), codice[:2], fontsize=7)
    p.insert_text((29, y), codice[2:], fontsize=7)
    p.insert_text((72, y), desc, fontsize=7)
    if importo:
        p.insert_text((colonna - FONT.text_length(importo, fontsize=7), y), importo, fontsize=7)


def _pagina(doc, titolo, sezione, mastri, chiusura):
    p = doc.new_page(width=595, height=842)
    p.insert_text((151, 26), "BILANCIO PROVVISORIO", fontsize=9)
    p.insert_text((245, 43), titolo, fontsize=8)
    for x, t in ((18, "Conto"), (72, "Descrizione"), (381, sezione), (439, "Totale Sub"), (508, "Totale Mastro")):
        p.insert_text((x, 54), t, fontsize=7)
    y = 68
    for conti, (codice, desc, tot) in mastri:
        for c in conti:
            _riga(p, y, *c)
            y += 10
        _riga(p, y, codice, desc, tot, MASTRO)
        y += 13
    for testo, importo in chiusura:
        p.insert_text((104, y), testo, fontsize=7)
        p.insert_text((MASTRO - FONT.text_length(importo, fontsize=7), y), importo, fontsize=7)
        y += 13


def _documento(path, *, fornitori="900,00"):
    doc = fitz.open()
    _pagina(doc, "STATO PATRIMONIALE", "Attivita'", [
        ([("010000004", "IMPIANTI GENERICI", "1.000,00")], ("010000004", "IMMOBILIZZAZIONI MATERIALI", "1.000,00")),
        ([("040000001", "RIMAN. FINALI MAT. PRIME/MERCI", "500,00")], ("040000001", "RIMANENZE FINALI", "500,00")),
        ([("100000000", "CLIENTI", "800,00")], ("100000000", "C L I E N T I", "800,00")),
        ([("140000010", "CASSA", "100,00")], ("140000010", "DISPONIBILITA' LIQUIDE", "100,00")),
    ], [("TOTALE ATTIVITA'", "2.400,00")])
    _pagina(doc, "STATO PATRIMONIALE", "Passivita'", [
        ([("050000004", "F.DO AMM.TO IMPIANTI", "400,00")], ("050000004", "FONDI AMMORTAMENTO", "400,00")),
        ([("120000005", "IVA ERARIO", "50,00-")], ("120000007", "ERARIO C/IVA", "50,00-")),
        ([("200000000", "FORNITORI", fornitori)], ("200000000", "FORNITORI", fornitori)),
        ([("300000001", "CAP. SOC./PATR.NET./F.DO CONS.", "1.000,00")], ("300000005", "PATRIMONIO NETTO", "1.000,00")),
    ], [("TOTALE PASSIVITA'", "2.250,00"), ("DIFFERENZA D'ESERCIZIO", "150,00"), ("TOTALE A PAREGGIO", "2.400,00")])
    _pagina(doc, "CONTO ECONOMICO", "Ricavi", [
        ([("400000001", "VENDITE", "3.000,00")], ("400000001", "RICAVI E RETTIFICHE RICAVI", "3.000,00")),
        ([("440000001", "MATERIE PRIME/MERCI", "500,00")], ("440000001", "RIMANENZE FINALI", "500,00")),
    ], [("TOTALE RICAVI", "3.500,00")])
    _pagina(doc, "CONTO ECONOMICO", "Costi", [
        ([("450000001", "MERCI C/ACQUISTI", "2.600,00")], ("450000001", "ACQUISTI", "2.600,00")),
        ([("480000001", "RIMAN. INIZIALI MAT. PRIME/MER", "400,00")], ("480000001", "RIMANENZE INIZIALI", "400,00")),
        ([("560000004", "AMM.TO IMPIANTI", "350,00")], ("560000004", "AMMORTAMENTI", "350,00")),
    ], [("TOTALE COSTI", "3.350,00"), ("DIFFERENZA D'ESERCIZIO", "150,00"), ("TOTALE A PAREGGIO", "3.500,00")])
    # abbastanza righe-conto per riconoscere il formato
    p = doc.new_page(width=595, height=842)
    for i in range(12):
        p.insert_text((18, 100 + i * 10), f"99 {i:07d}", fontsize=6)
    doc.save(path)


def test_verifica_sub_mastro_si_legge_e_quadra(tmp_path):
    path = str(tmp_path / "sub.pdf")
    _documento(path)
    assert is_verifica_sub_mastro("\n".join(p.get_text() for p in fitz.open(path)))
    bs, ce = extract_situazione_contabile(path)
    assert bs["sp13"] == D("150.00")
    assert bs["sp11"] == D("1000.00")
    assert bs["sp03"] == D("600.00")
    assert bs["sp05"] == D("500.00")
    assert bs["sp06"] == D("850.00")                 # clienti + IVA a credito (meno in coda)
    assert bs["totale_attivo"] == bs["totale_passivo"] == D("2050.00")
    assert ce["ce10"] == D("-100.00")                # iniziali 400 - finali 500
    assert ce["ce01"] == D("3000.00")
    assert ce["ce09"] == D("350.00")
    r = tentativo(path)
    assert r["adottato"] and r["esito"] == "ok"


def test_mastro_che_non_torna_scarta_la_lettura(tmp_path):
    path = str(tmp_path / "sub.pdf")
    _documento(path, fornitori="900,00")
    doc = fitz.open(path)
    p = doc[1]
    for r in p.search_for("900,00")[:1]:
        p.add_redact_annot(r)
    p.apply_redactions()
    p.insert_text((SUB - FONT.text_length("890,00", fontsize=7), 68 + 10 * 2 + 13 * 2), "890,00", fontsize=7)
    path2 = str(tmp_path / "sub2.pdf")
    doc.save(path2)
    bs, _ce = extract_situazione_contabile(path2)
    assert not bs.get("totale_attivo")
