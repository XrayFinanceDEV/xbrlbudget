"""Documenti che non sono un bilancio completo si rifiutano subito e col motivo giusto: un
conto economico da solo, anche quando le sue voci di legge contengono parole patrimoniali
(budget_1667), e il riepilogo di una contabilità semplificata (budget_1710). Testi inventati."""
from importers.bilancio_classifier import ROUTE_UNSUPPORTED, classify_bilancio

_CE_RICLASSIFICATO = """
Conto Economico Riclassificato al 30/09
Valore della produzione 1.000.000 1.100.000
Costi per materie prime 400.000 420.000
Ammortamenti delle immobilizzazioni materiali 50.000 52.000
Altre svalutazioni delle immobilizzazioni 0 0
Rettifiche di valore di attività e passività finanziarie 0 0
Risultato prima delle imposte 120.000 130.000
"""


def test_un_ce_con_voci_dai_nomi_patrimoniali_resta_solo_conto_economico():
    c = classify_bilancio(text=_CE_RICLASSIFICATO)

    assert c.route == ROUTE_UNSUPPORTED
    assert c.subcategory.startswith("C4/")


def test_uno_stato_patrimoniale_vero_resta_uno_stato_patrimoniale():
    testo = _CE_RICLASSIFICATO + "\nStato patrimoniale\nB) Immobilizzazioni 300.000\nTotale attivo 900.000\n"

    c = classify_bilancio(text=testo)

    assert not c.subcategory.startswith("C4/")


def test_una_contabilita_semplificata_si_rifiuta_col_suo_motivo():
    testo = """
    SITUAZIONE CONTABILE
    RIEPILOGO DEI RICAVI
    58/0005 Ricavi delle vendite 300.000,00
    RIEPILOGO DEI COSTI
    66/0010 Acquisti di merci 120.000,00
    UTILE FISCALE 80.000,00
    ALTRI CONTI
    20/0015 Automezzi 40.000,00
    """

    c = classify_bilancio(text=testo)

    assert c.route == ROUTE_UNSUPPORTED
    assert "semplificata" in c.reason
    assert "elenco conti" not in c.reason
