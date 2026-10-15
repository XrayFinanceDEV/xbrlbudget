"""Sezioni contrapposte di soli conti, senza codici e senza mastri (budget_435): cespiti
lordi all'attivo con il loro fondo di fronte, utile dentro il totale del passivo (i due
totali stampati sono uguali), un CE con molti costi e pochi ricavi chiuso da un "Totale a
pareggio". PDF sintetico, mai il file reale.
"""
from decimal import Decimal as D

import fitz

from importers.import_snello.deterministico import tentativo
from importers.situazione_contabile_parser import extract_situazione_contabile


def _riga(page, y, sx, ix, dx, ax):
    """Importo a sinistra con il bordo destro a 296, descrizione di destra subito dopo,
    come nel PDF vero: il varco fra le colonne e' largo un punto."""
    if sx:
        page.insert_text((37, y), sx, fontsize=8)
    if ix:
        page.insert_text((296 - 4.45 * len(ix), y), ix, fontsize=8)
    if dx:
        page.insert_text((297, y), dx, fontsize=8)
    if ax:
        page.insert_text((556 - 4.45 * len(ax), y), ax, fontsize=8)


def _intestazione(page, titolo):
    page.insert_text((28, 67), "Societa' Prova srl", fontsize=8)
    page.insert_text((453, 77), "Codice fiscale 01234567890", fontsize=8)
    page.insert_text((258, 82), "Bilancio di esercizio", fontsize=8)
    page.insert_text((225, 113), titolo, fontsize=8)


SP = [
    ("Automezzi", "100.000,00", "F.do amm.to automezzi", "40.000,00"),
    ("Contenitori", "10000,00", "F.do amm.to contenitori", "4.000,00"),
    ("Disaggi su prestiti", "1.000,00", "F.do amm.to disaggi su prestiti", "400,00"),
    ("Clienti", "50.000,00", "Fornitori", "30.000,00"),
    ("Intesa SanPaolo c/c 1000/2800", "6.000,00", "Banche c/c passivi", "20.000,00"),
    ("Cassa", "1.000,00", "Fondo T.F.R.", "10.000,00"),
    (None, None, "Capitale sociale", "10.000,00"),
    (None, None, "Riserva legale", "2.600,00"),
    (None, None, "Utile di esercizio", "51.000,00"),
    ("Totale attivita'", "168.000,00", "Totale passivita' e netto", "168.000,00"),
]

COSTI = [
    ("Materiali di pulizia", "1.000,00"),
    ("Carburanti e lubrificanti", "20.000,00"),
    ("Manutenzioni e riparazioni", "3.000,00"),
    ("Trasporti stradali", "4.000,00"),
    ("Premi RCA", "2.000,00"),
    ("Canoni di locazione", "6.000,00"),
    ("Salari e stipendi", "30.000,00"),
    ("Contributi previdenziali e assistenziali", "9.000,00"),
    ("Trattamento di fine rapporto", "2.000,00"),
    ("Ammortamento automezzi", "20.000,00"),
    ("Ammortamento disaggi su prestiti", "200,00"),
    ("Interessi passivi", "800,00"),
    ("IRES dell'esercizio", "1.000,00"),
]
RICAVI = [
    ("Corrispettivi da trasporto di merci su strada", "150.000,00"),
    ("Arrotondamenti attivi", "0,00"),
]


def _documento(path):
    doc = fitz.open()
    p = doc.new_page(width=595, height=842)
    _intestazione(p, "ATTIVITA'   IMPORTI   PASSIVITA' e NETTO   IMPORTI")
    y = 125
    for r in SP:
        _riga(p, y, *r)
        y += 11.5
    p = doc.new_page(width=595, height=842)
    _intestazione(p, "CONTO ECONOMICO GENERALE")
    y = 148
    for i, (dc, ic) in enumerate(COSTI):
        dr, ir = RICAVI[i] if i < len(RICAVI) else (None, None)
        _riga(p, y, dc, ic, dr, ir)
        y += 11.5
    _riga(p, y, "Totale componenti negativi", "99.000,00",
          "Totale componenti positivi", "150.000,00")
    _riga(p, y + 11.5, "Utile di esercizio", "51.000,00", None, None)
    _riga(p, y + 23, "Totale a pareggio", "150.000,00", "Totale a pareggio", "150.000,00")
    doc.save(path)
    doc.close()


def test_contrapposte_di_soli_conti_si_legge_e_quadra(tmp_path):
    path = str(tmp_path / "soli_conti.pdf")
    _documento(path)
    bs, ce = extract_situazione_contabile(path)
    # cespite e fondo in coppia: anche i contenitori e i disaggi sono immobilizzazioni
    assert bs["sp03"] == D("66000.00")           # 100.000 + 10.000 - 40.000 - 4.000
    assert bs["sp02"] == D("600.00")             # disaggi, netti del fondo
    assert bs["sp09"] == D("7000.00")            # il c/c col solo nome della banca
    assert bs["sp06"] == D("50000.00")
    # i totali stampati sono uguali: l'utile e' il conto di risultato, non la differenza
    assert bs["sp13"] == D("51000.00")
    assert bs["totale_attivo"] == bs["totale_passivo"] == D("123600.00")
    # il CE si legge per intero, anche con 13 costi contro 2 ricavi
    assert ce["ce01"] == D("150000.00")
    assert ce["ce05"] == D("21000.00")
    assert ce["ce06"] == D("9000.00")
    assert ce["ce07"] == D("6000.00")
    assert ce["ce08"] == D("41000.00")
    assert ce["ce09"] == D("20200.00")

    r = tentativo(path)
    assert r["adottato"] and r["esito"] == "ok"


def test_un_conto_sotto_un_mastro_che_lo_dice_resta_del_mastro():
    """Le parole dei conti foglia sono l'ultima risorsa: non scavalcano il mastro."""
    from importers.situazione_contabile_parser import (
        _classify_ce_costi, _classify_ce_costi_foglia)
    assert _classify_ce_costi("MATERIALE RIPAR/MANUTENZ.MACC/IMPIANTI") is None
    assert _classify_ce_costi_foglia("MATERIALE RIPAR/MANUTENZ.MACC/IMPIANTI") == "ce06"
    assert _classify_ce_costi_foglia("PREMIO DI PRODUZIONE") == "ce08b"
    assert _classify_ce_costi_foglia("ACCAN.TFR FORMAZIONE LAVORO") == "ce08a_tfr"
    assert _classify_ce_costi_foglia("CANONI DI ASSISTENZA TECNICA") == "ce06"
    assert _classify_ce_costi("AMMORTAMENTO MANUTENZIONI E RIPARAZIONI") == "ce09a"
