"""Testo di un PDF cifrato da un font senza mappa Unicode (Unicarton, upload 1269-1279)."""
import os

import fitz

from importers import testo_cifrato

RIGHE = [
    "Unicarton Srl - Bilancio di verifica al 31/08/2026",
    "STATO PATRIMONIALE Attivita Passivita",
    "Conto Descrizione Importo",
    "23.01.01 Capitale sociale 110.000,00",
    "23.01.05 Riserva legale 22.000,00",
    "29.01.01 Fondo TFR 119.867,09",
    "31.03.03 Mutui ipotecari bancari 720.248,62",
    "Totale attivo 9.876.543,21 Totale passivo 9.876.543,21",
]


def _cifra(testo, k=29):
    return "".join(c if c == " " else chr(ord(c) - k) for c in testo)


def _pdf(tmp_path, righe):
    """Un carattere per volta, come lo strato OCR di una scansione; il passo è quello
    del carattere in chiaro, come in un font che ha perso solo la mappa Unicode."""
    doc = fitz.open()
    page = doc.new_page()
    font = fitz.Font("helv")
    tw = fitz.TextWriter(page.rect)
    for i, (riga, chiara) in enumerate(zip(righe, RIGHE)):
        x = 40.0
        for c, c_chiaro in zip(riga, chiara):
            tw.append((x, 60 + 20 * i), c, font=font, fontsize=10)
            x += font.text_length(c_chiaro, fontsize=10)
    tw.write_text(page)
    percorso = tmp_path / "bilancio.pdf"
    doc.save(percorso)
    return str(percorso)


def test_il_testo_cifrato_si_riconosce_e_si_decodifica():
    testo = "\n".join(_cifra(r) for r in RIGHE)
    esito = testo_cifrato.rileva(testo)
    assert esito is not None and esito.spostamento == 29 and esito.parole_prima == 0
    decodificato = testo_cifrato._decodifica(testo, 29)
    # \x1c (il 9 cifrato) è uno spazio per str.isspace(): non va lasciato com'è.
    assert "720.248,62" in decodificato and "119.867,09" in decodificato
    assert "Mutui ipotecari bancari" in decodificato


def test_un_testo_leggibile_non_si_tocca(tmp_path):
    assert testo_cifrato.rileva("\n".join(RIGHE)) is None
    assert testo_cifrato.ripara(_pdf(tmp_path, RIGHE)) is None


def test_la_copia_riparata_ha_il_testo_leggibile_nelle_stesse_posizioni(tmp_path):
    # Spostamento 10, non 29: un PDF sintetico non sa scrivere i codici sotto 0x20
    # (MuPDF li ripesca come glifi a caso). Lo spostamento si misura, quindi vale
    # lo stesso; il caso 29 con \x1c è coperto dal test sul testo, sopra.
    originale = _pdf(tmp_path, [_cifra(r, 10) for r in RIGHE])
    copia, esito = testo_cifrato.ripara(originale)
    try:
        assert esito.spostamento == 10
        with fitz.open(copia) as doc:
            testo = doc[0].get_text()
            parole = doc[0].get_text("words")
        assert "Totale attivo 9.876.543,21" in testo
        assert "Fondo TFR 119.867,09" in testo
        # la riga del TFR resta alla sua altezza (sesta riga, y = 160)
        tfr = next(w for w in parole if w[4] == "TFR")
        assert abs(tfr[3] - 160) < 4
        assert "PDF24" in testo_cifrato.avviso(esito)
    finally:
        os.remove(copia)
