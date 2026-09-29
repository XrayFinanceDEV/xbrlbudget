from decimal import Decimal as D

from importers.import_snello.risultato import (control_caption, has_account_code, prior_caption,
                                               sign_by_caption)


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


def test_control_caption_riconosce_pareggio_differenza_e_sbilancio():
    assert control_caption("Totale a pareggio")
    assert control_caption("Differenza attivo passivo")
    assert control_caption("Sbilancio")


def test_control_caption_falso_su_un_conto_qualunque():
    assert not control_caption("Banca c/c")
    assert not control_caption("c9")


def test_control_caption_falso_sul_risultato_corrente_round_2():
    """Fix round 2 (review): 'Utile d'esercizio'/'Risultato d'esercizio' non sono piu' una
    riga di controllo - sono esattamente il caso ambiguo che l'ipotesi in conti.da_foglie deve
    risolvere (owner: "a volte c'e' scritto risultato ma in realta' e' quello dell'anno
    precedente, mentre quello di quest'anno e' la differenza"), mai un'esclusione decisa a
    priori dalla sola didascalia."""
    assert not control_caption("Utile d'esercizio")
    assert not control_caption("Risultato d'esercizio")
    assert not control_caption("Perdita d'esercizio")


def test_sign_by_caption_segue_la_didascalia_non_il_valore_stampato():
    assert sign_by_caption("Perdita portata a nuovo", D("500")) == D("-500")
    assert sign_by_caption("Utile portato a nuovo", D("-500")) == D("500")
    assert sign_by_caption("Risultato esercizio", D("120")) == D("120")


def test_has_account_code_riconosce_un_codice_conto_davanti():
    """Round 2 (banco FORMETAL-TEST): un codice conto davanti alla didascalia (cifre, punti,
    barre, asterischi) rende il risultato SEMPRE dell'anno precedente - stesso riconoscimento
    di situazione_contabile_parser._hier_prior_result."""
    assert has_account_code("28/45/090 RISULTATO DI ESERCIZIO")
    assert has_account_code("2801 Utile esercizio precedente")
    assert has_account_code("28.45.090 Risultato")


def test_has_account_code_falso_senza_codice_davanti():
    assert not has_account_code("UTILE DI ESERCIZIO")
    assert not has_account_code("Risultato d'esercizio")
    assert not has_account_code("")
    assert not has_account_code(None)
