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


def test_gli_interessi_su_debiti_verso_altri_non_sono_uno_stato_patrimoniale():
    # budget_1801 (cifre inventate): il conto di oneri finanziari diceva «debiti verso» e il CE da
    # solo passava per bilancio completo, fino a un rifiuto tardivo come «lettura non riuscita».
    testo = ("CONTO ECONOMICO\nCOSTI 10.000,00\n600100 Merci per la vendita 8.000,00\n"
             "690100 Interessi e oneri su debiti verso altri 12,00\nRICAVI 12.000,00\n"
             "UTILE CONTO ECONOMICO 2.000,00\n")
    c = classify_bilancio(text=testo)
    assert c.route == ROUTE_UNSUPPORTED and c.subcategory.startswith("C4/")


def test_un_debito_verso_altri_finanziatori_resta_uno_stato_patrimoniale():
    testo = ("CONTO ECONOMICO\nRICAVI 12.000,00\nSTATO\nDebiti verso altri finanziatori 5.000,00\n")
    assert not classify_bilancio(text=testo).subcategory.startswith("C4/")


_SEMPLIFICATA_PERDITA = "SITUAZIONE CONTABILE AL\n31/12/2025\nRIEPILOGO DEI RICAVI\n" + "".join(
    f"58/05/{i:03d}\nRICAVO {i}\n1.000,00\n" for i in range(1, 8)) + "RIEPILOGO DEI COSTI\n" + "".join(
    f"68/05/{i:03d}\nCOSTO {i}\n1.500,00\n" for i in range(1, 8)) + (
    "PERDITA FISCALE\n3.500,00\nALTRI CONTI\nAttività'\nPassività\n18/45/090\nCREDITI DIVERSI\n9,56\n")


def test_una_semplificata_in_perdita_con_testata_situazione_contabile_si_rifiuta_col_suo_motivo():
    # budget_1804/1827 (cifre inventate): «perdita fiscale» invece di «utile fiscale», e la testata
    # «SITUAZIONE CONTABILE AL» la mandava alla rotta delle verifiche prima della regola.
    c = classify_bilancio(text=_SEMPLIFICATA_PERDITA)
    assert c.signals["is_sc"]                     # senza la regola anticipata andava alla rotta C
    assert c.route == ROUTE_UNSUPPORTED and c.subcategory == "contabilità semplificata"


def test_una_situazione_con_patrimonio_netto_non_e_una_semplificata():
    c = classify_bilancio(text=_SEMPLIFICATA_PERDITA + "PATRIMONIO NETTO\n10.000,00\n")
    assert c.subcategory != "contabilità semplificata"
