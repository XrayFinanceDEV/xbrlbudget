"""Sbilancio chiuso dal risultato stampato nel documento, al centesimo e mai altrimenti."""
from decimal import Decimal as D

from importers.risultato_stampato import avviso, chiudi_col_risultato_stampato


def _bs(sp13="100000.00", debiti="600000.00"):
    bs = {"sp03_immob_materiali": D("500000.00"), "sp06_crediti_breve": D("300000.00"),
          "sp09_disponibilita_liquide": D("200000.00"), "sp11_capitale": D("100000.00"),
          "sp15_tfr": D("50000.00"), "sp16_debiti_breve": D(debiti),
          "sp13_utile_perdita": D(sp13)}
    bs["totale_attivo"] = D("1000000.00")
    bs["totale_passivo"] = sum((v for k, v in bs.items() if k.startswith(("sp1",))), D(0))
    return bs


_CE = {"ce01_ricavi_vendite": D("400000.00"), "ce05_materie_prime": D("300000.00")}


def test_l_utile_dell_anno_prima_stampato_chiude_lo_sbilancio():
    righe = ["212.00038 CREDITI IMPOSTA 102.499,51 309 UTILE (PERDITA)DELL'ESERCIZIO 150.000,00"]
    bs, rep = chiudi_col_risultato_stampato(_bs(), _CE, righe)
    assert rep["esito"] == "risultato_anno_prima"
    assert bs["sp12g_utili_perdite_portati"] == D("150000.00")
    assert bs["sp12_riserve"] == D("150000.00")
    assert bs["totale_passivo"] == D("1000000.00")
    assert "150.000,00" in avviso(rep)


def test_l_utile_del_periodo_mancante_si_prende_dal_documento():
    righe = ["Utile esercizio: 100.000,00"]
    bs, rep = chiudi_col_risultato_stampato(_bs(sp13="0", debiti="750000.00"), _CE, righe)
    assert rep["esito"] == "risultato_del_periodo"
    assert bs["sp13_utile_perdita"] == D("100000.00")
    assert bs["totale_passivo"] == D("1000000.00")


def test_importo_non_stampato_non_tocca_nulla():
    bs0 = _bs()
    bs, rep = chiudi_col_risultato_stampato(bs0, _CE, ["Debiti diversi 150.000,00"])
    assert rep is None and bs is bs0


def test_importo_di_un_altro_conto_sulla_stessa_riga_non_conta():
    # 150.000 sta accanto a CREDITI, la didascalia di risultato accompagna un altro importo
    righe = ["CREDITI DIVERSI 150.000,00 309 UTILE D'ESERCIZIO 99.000,00"]
    _bs_, rep = chiudi_col_risultato_stampato(_bs(), _CE, righe)
    assert rep is None


def test_una_perdita_non_chiude_uno_sbilancio_da_utile():
    _bs_, rep = chiudi_col_risultato_stampato(_bs(), _CE, ["Perdita esercizio precedente 150.000,00"])
    assert rep is None


def test_foglio_quadrato_non_si_tocca():
    bs0 = _bs(debiti="750000.00")
    bs, rep = chiudi_col_risultato_stampato(bs0, _CE, ["Utile 150.000,00"])
    assert rep is None and bs is bs0
