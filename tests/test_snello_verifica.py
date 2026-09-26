from decimal import Decimal as D

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
