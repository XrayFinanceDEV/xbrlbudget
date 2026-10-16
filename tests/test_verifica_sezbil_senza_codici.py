"""Verifica SEZBIL (COLOMBO 2026), tre varianti che il primo lettore non reggeva:

- importi con tre decimali ("1712097,143": conto di un factor), che la regex degli importi scartava;
- mastri di un solo conto senza codice numerico, stampati come un'unica riga che e' insieme il
  conto e il totale del mastro ("CLIENTI IT  Totale CLIENTI ITALIA  CLIENTI IT  Totale ...");
- l'abbreviazione "RIM." attaccata alla parola dopo ("RIM.PRODOTTI FINITI E MERCI"), che non
  veniva letta come rimanenze e portava 1,25 milioni nei crediti.

Il PDF e' sintetico: stessa geometria, nessun dato del cliente.
"""
from decimal import Decimal as D

import fitz

from importers import situazione_contabile_parser as scp

X_FINE_IMPORTO = 686


def _pdf(tmp_path):
    doc = fitz.open()
    font = fitz.Font("helv")
    pagina = doc.new_page(width=842, height=595)
    y = [74.0]

    def testo(x, t):
        pagina.insert_text((x, y[0]), t, fontsize=8)

    def importo(t):
        pagina.insert_text((X_FINE_IMPORTO - font.text_length(t, fontsize=8), y[0]), t, fontsize=8)

    def riga():
        y[0] += 12.5

    for x, t in ((53, "Mastro"), (142, "Descrizione"), (342, "Conto"), (397, "Descrizione"),
                 (630, "Importo"), (690, "SEZBIL")):
        testo(x, t)
    riga()

    def mastro(codice, desc, conti, sez):
        tot = sum((D(c[2].replace(",", ".")) for c in conti), D(0))
        for i, (conto, cdesc, imp) in enumerate(conti):
            if i == 0:
                testo(53, codice)
                testo(142, desc)
            testo(342, conto)
            testo(397, cdesc)
            importo(imp)
            testo(690, sez)
            riga()
        testo(142, f"Totale {desc}")
        importo(f"{tot:f}".replace(".", ","))
        testo(690, sez)
        riga()

    def mastro_solo(sigla, nome, imp, sez):
        # una riga sola: mastro e conto senza codice numerico, "Totale" due volte
        testo(53, sigla)
        testo(142, f"Totale {nome}")
        testo(342, sigla)
        testo(397, f"Totale {nome}")
        importo(imp)
        testo(690, sez)
        riga()

    mastro("150", "RIM.PRODOTTI FINITI E MERCI", [("17405", "Merci / Imballi", "500")], "A")
    mastro("162", "CREDITI ESIGIBILI", [("29001", "crediti diversi", "10"),
                                        ("3056EQ", "CREDITI V.SO FACTOR", "100,125")], "A")
    mastro_solo("CLIENTI IT", "CLIENTI ITALIA", "700,5", "A")
    mastro("200", "BANCHE E POSTA", [("32001", "banca intesa c/c", "290")], "A")
    mastro("300", "CAPITALE SOCIALE", [("33001", "capitale sociale", "1000")], "P")
    mastro_solo("FORNIT IT", "FORNITORI ITALIA", "400", "P")
    mastro("600", "ACQUISTI MERCI", [("60001", "acquisti merci", "500")], "C")
    mastro("495", "RICAVI VENDITE", [("51601", "vendite Italia", "700,625")], "R")
    riga()
    testo(53, "RIEPILOGO")
    riga()
    testo(142, "TOTALE ATTIVITA'")
    testo(260, "1600,625")
    testo(330, "TOTALE COSTI")
    testo(430, "500")
    riga()
    testo(142, "TOTALE PASSIVITA'")
    testo(260, "1400")
    testo(330, "TOTALE RICAVI")
    testo(430, "700,625")
    riga()
    testo(142, "DIFFERENZA")
    testo(260, "200,625")
    testo(330, "DIFFERENZA")
    testo(430, "200,625")
    percorso = tmp_path / "sezbil.pdf"
    doc.save(percorso)
    return str(percorso)


def test_lettura_con_tre_decimali_e_mastri_senza_codice(tmp_path):
    bs, ce = scp.extract_situazione_contabile(_pdf(tmp_path))
    assert bs["totale_attivo"] == bs["totale_passivo"] == D("1600.625")
    assert bs["sp06a_crediti_clienti_breve"] == D("700.5")           # CLIENTI IT, nessun codice
    assert bs["sp16d_debiti_fornitori_breve"] == D("400")            # FORNIT IT
    assert bs["sp13"] == D("200.625")


def test_rim_attaccato_e_rimanenze_non_crediti(tmp_path):
    bs, _ = scp.extract_situazione_contabile(_pdf(tmp_path))
    assert bs["sp05"] == D("500")
    assert bs["sp06g_crediti_altri_breve"] == D("110.125")           # solo i crediti veri
