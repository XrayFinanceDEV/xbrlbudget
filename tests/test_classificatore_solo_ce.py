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


def test_un_elenco_di_conti_con_dare_e_avere_e_una_situazione_contabile():
    # budget_1562 (testo inventato): codici puntati alfanumerici, colonne dare/avere/saldo, nessun percorso
    # di legge; prima finiva fra gli schemi di legge o fra i non riconosciuti. La testata di budget_1776 (saldo
    # iniziale, dare, avere, senza saldo finale) dal 2026-11-21 si rifiuta: test sotto.
    from importers.bilancio_classifier import ROUTE_TRIAL
    righe = ["CONTO Dare Avere Saldo", "1 - ATTIVITA'", "10 - Immobilizzazioni"]
    righe += [f"10.{k:02d}.{k + 40} - CONTO {k}\n{k},00\n{k},00" for k in range(1, 40)]
    c = classify_bilancio(text="\n".join(righe))
    assert c.route == ROUTE_TRIAL


_MOVIMENTI = """
1 / 4
CONTO
SALDO INIZ.
Dare
Avere
1 - ATTIVITA'
0,00
900.000,00
700.000,00
10 - Immobilizzazioni
0,00
300.000,00
20.000,00
2 - PASSIVITA'
0,00
150.000,00
400.000,00
"""


def test_saldo_iniziale_e_movimenti_senza_saldo_finale_si_rifiuta():
    # decisione del proprietario (2026-11-21, budget_1776): i movimenti del periodo non sono un bilancio, e il saldo
    # non si ricostruisce. Testo inventato.
    c = classify_bilancio(text=_MOVIMENTI)

    assert c.route == ROUTE_UNSUPPORTED
    assert c.subcategory == "movimenti senza saldo finale"


def test_con_il_saldo_finale_sulla_stessa_testata_resta_una_verifica():
    testo = _MOVIMENTI.replace("Avere\n", "Avere\nSALDO FINALE\n", 1)

    c = classify_bilancio(text=testo)

    assert c.subcategory != "movimenti senza saldo finale"
