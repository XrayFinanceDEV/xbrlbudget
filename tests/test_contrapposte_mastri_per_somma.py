"""Bilancio contabile a sezioni contrapposte con mastri a 2 cifre e conti a 3 cifre che non
ne portano il prefisso e si ripetono sotto mastri diversi (budget_703, "BILANCIO
CONTABILE"). La parentela non si deduce dal codice: un mastro e' tale quando i conti che lo
seguono ne ricostruiscono l'importo. In piu' un importo corto allineato a destra nella
colonna sinistra cade oltre la separazione stimata fra le colonne. PDF sintetico."""
from decimal import Decimal as D

import fitz

from importers.detail_enrichment import collect_source_rows
from importers.situazione_contabile_parser import extract_situazione_contabile


def _riga(page, y, x, codice, descrizione, importo):
    page.insert_text((x, y), codice, fontsize=8)
    page.insert_text((x + 25, y), descrizione, fontsize=8)
    font = fitz.Font("helv")
    page.insert_text((x + 260 - font.text_length(importo, fontsize=8), y), importo, fontsize=8)


def _pagina(doc, intestazione_sx, intestazione_dx, sinistra, destra, piede):
    p = doc.new_page(width=595, height=842)
    p.insert_text((200, 30), "BILANCIO CONTABILE", fontsize=10)
    p.insert_text((200, 42), "Dal 01/01/2025 Al 31/12/2025", fontsize=8)
    p.insert_text((80, 60), intestazione_sx, fontsize=9)
    p.insert_text((360, 60), intestazione_dx, fontsize=9)
    for x, righe in ((22, sinistra), (294, destra)):
        y = 80
        for r in righe:
            _riga(p, y, x, *r)
            y += 13
    p.insert_text((22, 600), piede, fontsize=8)


def _documento(path):
    doc = fitz.open()
    _pagina(doc, "Attività", "Passività", [
        ("1", "ATTIVITA'", "1.015.000,00"),
        ("10", "IMMOBILIZZI TECNICI", "700.000,00"),
        ("005", "FABBRICATI INDUSTRIALI", "600.000,00"),
        ("011", "IMPIANTI", "100.000,00"),
        ("16", "BANCHE", "300.000,00"),
        ("300", "CASSA RURALE ED ARTIGIANA", "300.000,00"),
        ("15", "LIQUIDITA'", "5.000,00"),
        ("250", "CASSA", "5.000,00"),
        ("19", "CLIENTI", "10.000,00"),
    ], [
        ("2", "PASSIVITA'", "1.005.000,00"),
        ("10", "FORNITORI", "400.000,00"),
        ("30", "PATRIMONIO NETTO", "500.000,00"),
        ("500", "CAPITALE SOCIALE", "500.000,00"),
        ("33", "FONDI AMMORTAMENTO", "100.000,00"),
        ("611", "F.DO AMMORT. IMPIANTI", "100.000,00"),
        ("35", "F.DO TRATT. FINE RAPPORTO", "5.000,00"),
        ("675", "F.DO T.F.R.", "5.000,00"),
    ], "Utile Esercizio 10.000,00")
    _pagina(doc, "Costi", "Ricavi", [
        ("3", "COSTI", "190.000,00"),
        ("30", "MANO D'OPERA", "100.000,00"),
        ("300", "RETRIBUZIONI", "99.000,00"),
        ("336", "ALTRI COSTI MANO D'OPERA", "1.000,00"),
        ("85", "ONERI FINANZIARI", "90.000,00"),
        ("070", "INTERESSI PASSIVI C/C", "8,19"),
        ("075", "INTERESSI PASSIVI MUTUI", "89.991,81"),
    ], [
        ("4", "RICAVI", "200.000,00"),
        ("01", "VENDITE", "200.000,00"),
        ("004", "VENDITE ITALIA", "200.000,00"),
    ], "Utile Esercizio 10.000,00")
    doc.save(path)
    doc.close()


def test_mastri_riconosciuti_dalla_somma_dei_conti(tmp_path):
    path = tmp_path / "contabile.pdf"
    _documento(str(path))
    bs, ce = extract_situazione_contabile(str(path))
    assert bs["sp13"] == D("10000.00")
    assert bs["totale_attivo"] == bs["totale_passivo"] == D("915000.00")
    assert bs["sp15"] == D("5000.00")
    assert not bs.get("_plug_residual")
    assert ce["ce15"] == D("90000.00")               # gli interessi una volta sola


def test_l_importo_corto_resta_nella_sua_colonna(tmp_path):
    path = tmp_path / "contabile.pdf"
    _documento(str(path))
    righe = {r.text.split()[0] + r.side: r for r in collect_source_rows(str(path))
             if r.text[:3].isdigit()}
    assert righe["070L"].amounts == (D("8.19"),)
