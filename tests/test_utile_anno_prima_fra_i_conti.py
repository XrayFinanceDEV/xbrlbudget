"""Situazione contabile a sezioni contrapposte con l'utile dell'anno prima ancora fra i
conti del patrimonio netto (AITEC 30/06/2026: mastro "309 UTILE (PERDITA)
DELL'ESERCIZIO" 269.255,83, dentro il totale passivita'), e totali stampati con l'importo
prima della didascalia (STB 30/06/2026). PDF sintetici, mai i file reali."""
from decimal import Decimal as D

import fitz

from importers.situazione_contabile_parser import extract_situazione_contabile


def _riga(page, y, x, codice, descrizione, importo):
    if codice:
        page.insert_text((x, y), codice, fontsize=9)
    page.insert_text((x + 45, y), descrizione, fontsize=9)
    page.insert_text((x + 200, y), importo, fontsize=9)


def _situazione(path, *, utile_anno_prima: str, totale_passivita: str,
                importo_prima: bool = False, nei_conti_d_ordine: bool = False):
    doc = fitz.open()
    sp = doc.new_page(width=595, height=842)
    sp.insert_text((40, 30), "Bilancio di verifica al 30/06/2026", fontsize=10)
    sp.insert_text((240, 50), "STATO PATRIMONIALE", fontsize=10)
    sp.insert_text((60, 70), "Attivita'", fontsize=9)
    sp.insert_text((360, 70), "Passivita'", fontsize=9)
    attivo = [("05", "IMMOBILIZZAZIONI MATERIALI", "500.000,00"),
              ("11", "CREDITI COMMERCIALI", "300.000,00"),
              ("19", "DISPONIBILITA' LIQUIDE", "200.000,00")]
    passivo = [("23", "CAPITALE SOCIALE", "100.000,00"),
               ("29", "FONDO TFR", "50.000,00"),
               ("33", "DEBITI COMMERCIALI", "600.000,00")]
    if not nei_conti_d_ordine:
        passivo.append(("309", "UTILE (PERDITA) DELL'ESERCIZIO", utile_anno_prima))
    y = 95
    for i in range(max(len(attivo), len(passivo))):
        if i < len(attivo):
            _riga(sp, y, 20, *attivo[i])
        if i < len(passivo):
            _riga(sp, y, 310, *passivo[i])
        y += 18
    if nei_conti_d_ordine:
        _riga(sp, y, 310, "005", "CONTI D'ORDINE", "")
        _riga(sp, y + 18, 310, "501", "UTILE D'ESERCIZIO", utile_anno_prima)
        y += 36
    y += 10
    if importo_prima:
        # Al suo posto sulla pagina, ma nel flusso di testo l'importo viene PRIMA della
        # didascalia ("1.406.600,60 Totale Attivita': *** 1.352.014,11 Totale
        # Passivita':", STB): scritto per primo.
        sp.insert_text((220, y), "1.000.000,00", fontsize=9)
        sp.insert_text((65, y), "Totale Attivita':", fontsize=9)
        sp.insert_text((510, y), totale_passivita, fontsize=9)
        sp.insert_text((355, y), "Totale Passivita':", fontsize=9)
    else:
        _riga(sp, y, 20, "", "Totale attivita'", "1.000.000,00")
        _riga(sp, y, 310, "", "Totale passivita'", totale_passivita)

    ce = doc.new_page(width=595, height=842)
    ce.insert_text((40, 30), "Bilancio di verifica al 30/06/2026", fontsize=10)
    ce.insert_text((240, 50), "CONTO ECONOMICO", fontsize=10)
    ce.insert_text((60, 70), "Costi", fontsize=9)
    ce.insert_text((360, 70), "Ricavi", fontsize=9)
    _riga(ce, 95, 20, "55", "ACQUISTI DI BENI", "300.000,00")
    _riga(ce, 95, 310, "47", "RICAVI DELLE VENDITE", "400.000,00")
    _riga(ce, 125, 20, "", "Totale costi", "300.000,00")
    _riga(ce, 125, 310, "", "Totale ricavi", "400.000,00")
    doc.save(path)
    doc.close()


def test_il_conto_utile_dell_anno_prima_dentro_il_totale_va_negli_utili_portati(tmp_path):
    path = tmp_path / "s.pdf"
    _situazione(str(path), utile_anno_prima="150.000,00", totale_passivita="900.000,00")
    bs, _ce = extract_situazione_contabile(str(path))
    assert bs["sp13"] == D("100000.00")
    assert bs["sp12g_utili_perdite_portati"] == D("150000.00")
    assert bs["_prior_result_booked"] == D("150000.00")
    assert bs["_plug_residual"] == D("0.00")


def test_il_conto_utile_fuori_dai_totali_non_entra_nel_patrimonio(tmp_path):
    path = tmp_path / "s.pdf"
    _situazione(str(path), utile_anno_prima="40.000,00", totale_passivita="900.000,00",
                importo_prima=True, nei_conti_d_ordine=True)
    bs, _ce = extract_situazione_contabile(str(path))
    assert "_prior_result_booked" not in bs
    assert not bs.get("sp12g_utili_perdite_portati")


def test_totali_con_l_importo_prima_della_didascalia(tmp_path):
    path = tmp_path / "s.pdf"
    _situazione(str(path), utile_anno_prima="150.000,00", totale_passivita="900.000,00",
                importo_prima=True)
    bs, _ce = extract_situazione_contabile(str(path))
    # prima il testo lineare prendeva 900.000 per entrambi i totali: utile zero
    assert bs["sp13"] == D("100000.00")
    assert bs["sp12g_utili_perdite_portati"] == D("150000.00")
    assert bs["_plug_residual"] == D("0.00")
