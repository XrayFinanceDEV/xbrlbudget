from decimal import Decimal as D

from importers.import_snello.risultato import control_caption, prior_caption, sign_by_caption


def test_prior_caption_riconosce_precedente_e_portato():
    assert prior_caption("Utile esercizio precedente")
    assert prior_caption("perdite portate a nuovo")
    assert prior_caption("UTILI PORTATI A NUOVO")


def test_prior_caption_falso_su_risultato_corrente_o_didascalia_generica():
    assert not prior_caption("Utile d'esercizio")
    assert not prior_caption("Risultato esercizio")
    assert not prior_caption("Totale a pareggio")
    assert not prior_caption("c9")
    assert not prior_caption("")


def test_control_caption_riconosce_pareggio_differenza_sbilancio_e_risultato_corrente():
    assert control_caption("Totale a pareggio")
    assert control_caption("Differenza attivo passivo")
    assert control_caption("Sbilancio")
    assert control_caption("Utile d'esercizio")
    assert control_caption("Risultato d'esercizio")


def test_control_caption_falso_su_un_conto_qualunque():
    assert not control_caption("Banca c/c")
    assert not control_caption("c9")


def test_sign_by_caption_segue_la_didascalia_non_il_valore_stampato():
    assert sign_by_caption("Perdita portata a nuovo", D("500")) == D("-500")
    assert sign_by_caption("Utile portato a nuovo", D("-500")) == D("500")
    assert sign_by_caption("Risultato esercizio", D("120")) == D("120")
