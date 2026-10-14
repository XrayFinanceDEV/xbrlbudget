"""Risultato dell'anno prima non ancora destinato, stampato sotto i totali di una
situazione contabile a sezioni contrapposte (Unicarton 31/08/2026: "Eccedenza esercizio
precedente 173.463,79" sotto "Totale passivita'"). E' patrimonio netto: senza toglierlo
dalla differenza dei totali diventava utile del periodo. PDF sintetici, mai il file reale."""
from decimal import Decimal as D

import fitz

from importers.situazione_contabile_parser import extract_situazione_contabile


def _riga(page, y, x_codice, codice, descrizione, importo):
    if codice:
        page.insert_text((x_codice, y), codice, fontsize=9)
    page.insert_text((x_codice + 45, y), descrizione, fontsize=9)
    page.insert_text((x_codice + 200, y), importo, fontsize=9)


def _situazione(path, *, sotto_i_totali: bool):
    doc = fitz.open()
    sp = doc.new_page(width=595, height=842)
    sp.insert_text((40, 30), "Bilancio di verifica al 31/08/2026", fontsize=10)
    sp.insert_text((240, 50), "STATO PATRIMONIALE", fontsize=10)
    sp.insert_text((60, 70), "Attivita'", fontsize=9)
    sp.insert_text((360, 70), "Passivita'", fontsize=9)
    attivo = [("05", "IMMOBILIZZAZIONI MATERIALI", "500.000,00"),
              ("11", "CREDITI COMMERCIALI", "300.000,00"),
              ("19", "DISPONIBILITA' LIQUIDE", "200.000,00")]
    passivo = [("23", "CAPITALE SOCIALE", "100.000,00"),
               ("29", "FONDO TFR", "50.000,00"),
               ("33", "DEBITI COMMERCIALI", "600.000,00")]
    y = 95
    for (ca, da, ia), (cp, dp, ip) in zip(attivo, passivo):
        _riga(sp, y, 20, ca, da, ia)
        _riga(sp, y, 310, cp, dp, ip)
        y += 18
    # utile anno prima 150.000 + utile del periodo 100.000 = eccedenza 250.000
    _riga(sp, y + 10, 20, "", "Totale attivita'", "1.000.000,00")
    _riga(sp, y + 10, 310, "", "Totale passivita'", "750.000,00")
    if sotto_i_totali:
        _riga(sp, y + 24, 310, "", "Eccedenza esercizio precedente", "150.000,00")
        _riga(sp, y + 38, 310, "", "Eccedenza (Utile)", "100.000,00")
    else:
        _riga(sp, y + 24, 310, "", "Eccedenza (Utile)", "250.000,00")
    _riga(sp, y + 52, 20, "", "Totale a quadratura", "1.000.000,00")
    _riga(sp, y + 52, 310, "", "", "1.000.000,00")

    ce = doc.new_page(width=595, height=842)
    ce.insert_text((40, 30), "Bilancio di verifica al 31/08/2026", fontsize=10)
    ce.insert_text((240, 50), "CONTO ECONOMICO", fontsize=10)
    ce.insert_text((60, 70), "Costi", fontsize=9)
    ce.insert_text((360, 70), "Ricavi", fontsize=9)
    _riga(ce, 95, 20, "55", "ACQUISTI DI BENI", "300.000,00")
    _riga(ce, 95, 310, "47", "RICAVI DELLE VENDITE", "400.000,00")
    _riga(ce, 125, 20, "", "Totale costi", "300.000,00")
    _riga(ce, 125, 310, "", "Totale ricavi", "400.000,00")
    _riga(ce, 139, 20, "", "Utile d'esercizio", "100.000,00")
    doc.save(path)
    doc.close()


def test_l_eccedenza_dell_anno_prima_va_negli_utili_portati_non_nell_utile(tmp_path):
    path = tmp_path / "situazione.pdf"
    _situazione(str(path), sotto_i_totali=True)
    bs, ce = extract_situazione_contabile(str(path))
    assert bs["sp13"] == D("100000.00")
    assert bs["sp12g_utili_perdite_portati"] == D("150000.00")
    assert bs["_prior_result_footer"] == D("150000.00")


def test_senza_eccedenza_precedente_l_utile_resta_la_differenza_dei_totali(tmp_path):
    path = tmp_path / "situazione.pdf"
    _situazione(str(path), sotto_i_totali=False)
    bs, ce = extract_situazione_contabile(str(path))
    assert bs["sp13"] == D("250000.00")
    assert not bs.get("sp12g_utili_perdite_portati")
    assert "_prior_result_footer" not in bs
