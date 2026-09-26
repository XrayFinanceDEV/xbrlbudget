from decimal import Decimal as D

import pytest

from importers.import_snello.verifica import misura, normalizza_forma, soglia, tappa


def _bs(**kw):
    base = {"sp03_immob_materiali": D("1000"), "sp09_disponibilita_liquide": D("500"),
            "sp11_capitale": D("800"), "sp13_utile_perdita": D("100"), "sp16_debiti_breve": D("600"),
            "sp16d_debiti_fornitori_breve": D("600")}
    base.update({k: D(v) for k, v in kw.items()})
    return base


CE = {"ce01_ricavi_vendite": D("400"), "ce06_servizi": D("300")}    # utile 100


def test_soglia_relativa_con_minimo():
    assert soglia(D("50000")) == D("100.00")
    assert soglia(D("2000000")) == D("2000.00")


def test_bilancio_che_quadra():
    m = misura(_bs(), CE)
    assert m["forma"] == "bilancio" and m["scarto_sp"] == 0 and m["scarto_ce"] == 0
    bs, ce, tappo, esito = tappa(_bs(), CE, m, D("100"))
    assert esito == "ok" and tappo is None


def test_forma_verifica_sposta_il_risultato_dell_anno_prima():
    bs = _bs(sp13_utile_perdita="-40", sp09_disponibilita_liquide="460")   # nel netto la perdita dell'anno prima; attivo = netto + debiti + utile corrente
    m = misura(bs, CE)
    assert m["forma"] == "verifica" and m["scarto_sp"] == 0
    nuovo = normalizza_forma(bs, CE, m)
    assert nuovo["sp12g_utili_perdite_portati"] == D("-40") and nuovo["sp13_utile_perdita"] == D("100")
    assert nuovo["sp12_riserve"] == D("-40")


def test_tappo_entro_soglia_su_altri_debiti_e_crediti():
    bs = _bs(sp09_disponibilita_liquide="550")                   # attivo in piu' di 50
    bs2, ce2, tappo, esito = tappa(bs, CE, misura(bs, CE), D("100"))
    assert esito == "tappo" and tappo["campo"] == "sp16g_altri_debiti_breve" and tappo["importo"] == "50.00"
    assert bs2["sp16g_altri_debiti_breve"] == D("50.00") and bs2["sp16_debiti_breve"] == D("650.00")
    bs = _bs(sp09_disponibilita_liquide="470")                   # attivo in meno di 30
    bs3, _, tappo, _ = tappa(bs, CE, misura(bs, CE), D("100"))
    assert tappo["campo"] == "sp06g_crediti_altri_breve" and bs3["sp06_crediti_breve"] == D("30.00")


def test_tappo_ce_su_servizi():
    ce = {"ce01_ricavi_vendite": D("400"), "ce06_servizi": D("290")}   # utile CE 110 contro sp13 100
    bs2, ce2, tappo, esito = tappa(_bs(), ce, misura(_bs(), ce), D("100"))
    assert esito == "tappo" and ce2["ce06_servizi"] == D("300.00") and tappo["ce"]["campo"] == "ce06_servizi"


def test_oltre_soglia_non_tocca_nulla():
    bs = _bs(sp09_disponibilita_liquide="900")
    bs2, ce2, tappo, esito = tappa(bs, CE, misura(bs, CE), D("100"))
    assert esito == "oltre_soglia" and tappo is None and bs2 == bs


def test_estrazione_vuota_non_e_ok():
    bs, ce = {}, {}
    m = misura(bs, ce)
    bs2, ce2, tappo, esito = tappa(bs, ce, m, D("100"))
    assert esito == "vuoto" and tappo is None and bs2 == bs and ce2 == ce


def test_forma_esplicita_non_maschera_lo_scarto_reale():
    # sp13 = 0 e utile CE = 100 con una vera eccedenza di attivo di 100 (sp13 azzerato,
    # non 100 come nella fixture base): con forma="bilancio" lo scarto si vede;
    # con forma=None l'euristica (somma degli scarti assoluti piu' piccola: 0 contro 200)
    # preferisce "verifica" e lo maschera. E' l'ambiguita' nota fra le due forme quando
    # utile CE e l'eccedenza di attivo coincidono: documentata qui, non risolta.
    bs = _bs(sp13_utile_perdita="0")
    m_bilancio = misura(bs, CE, forma="bilancio")
    assert m_bilancio["forma"] == "bilancio" and m_bilancio["scarto_sp"] == D("100.00")
    m_auto = misura(bs, CE)
    assert m_auto["forma"] == "verifica" and m_auto["scarto_sp"] == D("0.00")


def test_tappo_ce_negativo_si_rifiuta():
    ce = {"ce01_ricavi_vendite": D("50"), "ce06_servizi": D("5")}   # utile CE 45 contro sp13 100 (scarto -55)
    m = misura(_bs(), ce, forma="bilancio")
    bs2, ce2, tappo, esito = tappa(_bs(), ce, m, D("100"))
    assert esito == "oltre_soglia" and tappo is None and ce2["ce06_servizi"] == D("5")


def test_forma_invalida_solleva():
    with pytest.raises(ValueError):
        misura(_bs(), CE, forma="xyz")
