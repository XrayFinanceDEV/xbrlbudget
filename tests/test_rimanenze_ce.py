"""Rimanenze a conto economico negli elenchi di conti: prodotti in A.2 (ce02), materie e
merci in B.11 (ce10), mai nel secchio di ripiego.

Contesto (2026-10-19, Unicarton 2025, bilancio di verifica a sezioni contrapposte per
segno): le rimanenze finali (193.691,65) finivano in ``ce04`` altri ricavi e le iniziali
(218.314,13) in ``ce12`` oneri diversi. L'utile quadrava al centesimo; valore e costi
della produzione erano gonfiati dello stesso importo, e il previsionale avrebbe ripetuto
ogni anno quei ricavi e quei costi accanto alla variazione di magazzino che calcola da
se'. Gli altri lettori mettevano tutto in ``ce10``, prodotti finiti compresi.

Le cifre qui sono SINTETICHE e riproducono le forme dei documenti reali del corpus
(``Test/``, fuori dal repo): mastro senza natura con conti che la dicono (Unicarton),
mastro dal nome sbagliato (AITEC: "RIM.INIZ.SEMILAVORATI PROD-FINITI" porta sotto anche le
materie prime), conto senza natura accanto all'altro capo che la dice (COLOMBO).

Run: python -m pytest tests/test_rimanenze_ce.py -v
"""
import os
import sys
from decimal import Decimal as D

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from importers.rimanenze_ce import e_conto_rimanenze, natura_rimanenze  # noqa: E402
from importers.situazione_contabile_parser import (  # noqa: E402
    Entry, _be_reclassify, _vseg_classify_ce, build_iv_cee, classify_costi, classify_ricavi)


# --- la regola ----------------------------------------------------------------------

def test_natura_dalle_descrizioni_reali():
    assert natura_rimanenze("RIMANENZE FINALI PRODOTTI FINITI") == "ce02"
    assert natura_rimanenze("RIM.INIZ.PROD.IN CORSO LAVORAZ.E SEMIL.") == "ce02"
    assert natura_rimanenze("RIM.FIN.LAV.CORSO ORD.<12MESI") == "ce02"
    assert natura_rimanenze("RIM.INIZ.MAT.PRIME, SUSSID.E DI CONSUMO") == "ce10"
    assert natura_rimanenze("RIMANENZE INIZIALI DI MERCI") == "ce10"
    assert natura_rimanenze("RIM.FIN.PRODOTTI COMMERCIALIZZATI") == "ce10"


def test_natura_non_detta_o_mista_resta_none():
    assert natura_rimanenze("RIMANENZE FINALI") is None
    assert natura_rimanenze("RIMANENZE PRODOTTI FINITI E MERCI") is None


def test_natura_dal_padre_quando_il_conto_tace():
    assert natura_rimanenze("RIMANENZE INIZIALI", "ESIST.INIZ.PROD.FINITI E SEMIL") == "ce02"
    # un conto misto non si fa decidere dal padre
    assert natura_rimanenze("PRODOTTI FINITI E MERCI", "MATERIE PRIME") is None


def test_rim_da_solo_non_e_un_conto_di_rimanenze():
    assert e_conto_rimanenze("VARIAZ.RIM.FINALI E COSTRUZIONI INTERNE")
    assert e_conto_rimanenze("RIM.INIZ.MATERIE PRIME")
    assert not e_conto_rimanenze("RIMBORSI SPESE")


def test_classificatori_a_parole():
    assert classify_costi("RIMANENZE INIZIALI PRODOTTI FINITI") == ("ce02_open", True)
    assert classify_costi("RIMANENZE INIZIALI MATERIE PRIME") == ("ce10", True)
    assert classify_ricavi("RIMANENZE FINALI PRODOTTI FINITI") == ("ce02", True)
    assert classify_ricavi("RIMANENZE FINALI MATERIE PRIME") == ("ce10_close", True)


# --- sezioni contrapposte per segno (Unicarton) --------------------------------------

def _unicarton(dettagli_finali=True):
    costi = [
        ("51", "VARIAZ. RIMANENZE INIZIALI", D("218314.13")),
        ("51.01", "RIMANENZE INIZIALI", D("218314.13")),
        ("59", "GESTIONE VEICOLI AZIENDALI", D("46303.51")),
        ("71", "ONERI DIVERSI DI GESTIONE", D("19846.30")),
    ]
    ricavi = [
        ("47", "RICAVI DELLE VENDITE E DELLE PRESTAZIONI", D("2173902.91")),
        ("49", "VARIAZ.RIM.FINALI E COSTRUZIONI INTERNE", D("193691.65")),
        ("49.01", "RIMANENZE FINALI", D("193691.65")),
        ("53", "ALTRI RICAVI E PROVENTI", D("5698.40")),
    ]
    dettagli = [
        ("left", "51.01.01", "RIMANENZE INIZIALI PRODOTTI FINITI", D("118958.92")),
        ("left", "51.01.13", "RIM.INIZ.MAT.PRIME, SUSSID.E DI CONSUMO", D("99355.21")),
    ]
    if dettagli_finali:
        dettagli += [
            ("right", "49.01.01", "RIMANENZE FINALI PRODOTTI FINITI", D("96795.70")),
            ("right", "49.01.90", "RIM.FINALI MAT.PRIME", D("92543.55")),
            ("right", "49.01.91", "RIM.FINALI MAT. DI CONSUMO", D("4352.40")),
        ]
    ce = {}
    _vseg_classify_ce(ce, costi, 0, dettagli, ricavi)
    _vseg_classify_ce(ce, ricavi, 1, dettagli, costi)
    return ce


def test_unicarton_rimanenze_per_natura_e_non_nel_ripiego():
    ce = _unicarton()
    assert ce["ce02"] == D("96795.70") - D("118958.92")          # -22.163,22
    assert ce["ce10"] == D("99355.21") - D("92543.55") - D("4352.40")  # 2.459,26
    assert ce["ce04"] == D("5698.40")
    assert ce["ce12"] == D("19846.30")
    assert ce["ce06"] == D("46303.51")                            # gestione veicoli: B.7


def test_unicarton_risultato_invariato():
    """Lo spostamento sta tutto dentro valore e costi della produzione: l'utile no."""
    ce = _unicarton()
    ricavi = ce["ce01"] + ce["ce02"] + ce["ce04"]
    costi = ce["ce06"] + ce["ce10"] + ce["ce12"]
    assert ricavi - costi == D("2173902.91") + D("5698.40") + D("193691.65") \
        - D("218314.13") - D("46303.51") - D("19846.30")


def test_mastro_senza_dettaglio_che_quadra_resta_intero_in_ce10():
    """Le finali senza conti sotto: niente natura, quindi B.11 come sempre - ma il lato
    opposto ha due nature, e nessun ripiego vale."""
    ce = _unicarton(dettagli_finali=False)
    assert ce["ce02"] == D("-118958.92")
    assert ce["ce10"] == D("99355.21") - D("193691.65")
    assert "ce04" not in ce or ce["ce04"] == D("5698.40")


# --- best-effort a codici (AITEC, COLOMBO) -------------------------------------------

def _tags(out):
    tot = {}
    for t, a in out:
        tot[t] = tot.get(t, D(0)) + a
    return tot


def test_i_conti_decidono_contro_il_nome_del_mastro():
    costi = [
        ("701", "RIM.INIZ.SEMILAVORATI PROD-FINITI", D("1485450.00")),
        ("70100001", "RIM.INIZ.MATERIE PRIME", D("536397.00")),
        ("70100053", "RIM.INIZ.SEMILAVORATI", D("949053.00")),
    ]
    tot = _tags(_be_reclassify(costi, classify_costi))
    assert tot == {"ce10": D("536397.00"), "ce02_open": D("949053.00")}


def test_figli_che_non_quadrano_lasciano_decidere_il_mastro():
    costi = [
        ("701", "RIM.INIZ.SEMILAVORATI PROD-FINITI", D("1485450.00")),
        ("70100001", "RIM.INIZ.MATERIE PRIME", D("536397.00")),
    ]
    tot = _tags(_be_reclassify(costi, classify_costi))
    assert tot == {"ce02_open": D("1485450.00")}


def test_conto_senza_natura_prende_quella_del_capo_opposto():
    """COLOMBO: 'RIMANENZE INIZIALI' accanto a 'Prodotti finiti rimanenze finali'. In B.11
    le iniziali e in A.2 le finali avrebbero gonfiato valore e costi di 1,25 e 1,03 milioni."""
    ricavi = [("56805", "PRODOTTI FINITI RIMANENZE FINALI", D("1251811.08"))]
    costi = [("52005", "RIMANENZE INIZIALI", D("1028115.10"))]
    tot = _tags(_be_reclassify(costi, classify_costi, "ce02"))
    assert tot == {"ce02_open": D("1028115.10")}
    assert _tags(_be_reclassify(ricavi, classify_ricavi)) == {"ce02": D("1251811.08")}


# --- elenco a subtotali (build_iv_cee) -----------------------------------------------

def test_build_iv_cee_scende_nei_conti_della_categoria():
    entries = [
        Entry("61/**/***", "RIMANENZE INIZIALI", D("100"), level=2, section="costi"),
        Entry("61/01/001", "PRODOTTI FINITI", D("60"), level=0, section="costi"),
        Entry("61/01/002", "MATERIE PRIME", D("40"), level=0, section="costi"),
        Entry("81/**/***", "RIMANENZE FINALI", D("130"), level=2, section="ricavi"),
        Entry("81/01/001", "PRODOTTI FINITI", D("80"), level=0, section="ricavi"),
        Entry("81/01/002", "MATERIE PRIME", D("50"), level=0, section="ricavi"),
    ]
    _bs, ce = build_iv_cee(entries)
    assert ce["ce02"] == D("20")      # 80 - 60
    assert ce["ce10"] == D("-10")     # 40 - 50
    assert ce.get("ce04", D(0)) == 0 and ce.get("ce12", D(0)) == 0


# --- ammortamenti: le sotto-voci di B.10 ---------------------------------------------
# Senza ce09a/ce09b il previsionale e l'infrannuale non ammortizzano sp02/sp03, e il
# vecchio ripiego ce09c il motore lo legge come svalutazione di sp04.

def test_unicarton_ammortamenti_ripartiti_dai_conti():
    from importers.situazione_contabile_parser import _vseg_classify_ce
    costi = [
        ("80", "AMMORTAMENTI", D("75275.95")),
        ("80.01", "AMMORTAMENTI IMMOBILIZZAZ.IMMATERIALI", D("429.00")),
        ("80.03", "AMMORTAMENTI IMMOBILIZZAZIONI MATERIALI", D("74846.95")),
        ("83", "SVALUTAZIONI", D("3633.12")),
        ("83.09", "SVALUTAZIONE CREDITI", D("3633.12")),
    ]
    ce = {}
    _vseg_classify_ce(ce, costi, 0)
    assert ce["ce09"] == D("78909.07")
    assert ce["ce09a_ammort_immateriali"] == D("429.00")
    assert ce["ce09b_ammort_materiali"] == D("74846.95")
    assert ce["ce09d_svalutazione_crediti"] == D("3633.12")


def test_descrizione_troncata_la_decidono_i_conti():
    """budget_588: la stampa a tre colonne tronca entrambi i mastri in "AMM.TI CIVILISTICI
    IMMOBILIZZ"; il ripiego li dava tutti ai materiali, l'avviamento compreso."""
    from importers.situazione_contabile_parser import _ce09_dal_dettaglio, _figli_puntati
    righe = [
        ("80", "AMMORTAMENTI", D("11972.48")),
        ("80.05", "AMM.TI CIVILISTICI IMMOBILIZZ", D("8936.63")),
        ("80.07", "AMM.TI CIVILISTICI IMMOBILIZZ", D("3035.85")),
        ("80.07.19", "AMM.TO CIVILISTICO AVVIAMENTO", D("3035.85")),
    ]
    tot = _tags(_ce09_dal_dettaglio("80", "AMMORTAMENTI", D("11972.48"), _figli_puntati(righe)))
    assert tot == {"ce09b": D("8936.63"), "ce09a": D("3035.85")}


def test_ammortamenti_e_svalutazioni_non_e_svalutazione_crediti():
    """Pandoro: "AMMORTAMENTI E SVALUTAZIONI" andava per intero in ce09d per la parola
    SVALUT. Con i conti che quadrano decidono loro; senza resta ce09 non ripartito."""
    costi = [
        ("35", "AMMORTAMENTI E SVALUTAZIONI", D("1000")),
        ("355", "AMMORTAMENTO IMMOBILIZZ.IMMATERIALI", D("100")),
        ("3510", "AMMORTAMENTO IMMOBILIZZ.MATERIALI", D("900")),
    ]
    assert _tags(_be_reclassify(costi, classify_costi)) == {"ce09a": D("100"), "ce09b": D("900")}
    assert _tags(_be_reclassify(costi[:1], classify_costi)) == {"ce09": D("1000")}


def test_build_iv_cee_ammortamenti_nudi_non_vanno_negli_oneri_diversi():
    entries = [
        Entry("70/**/***", "AMMORTAMENTI", D("100"), level=2, section="costi"),
        Entry("70/01/001", "AMM.TO SOFTWARE", D("30"), level=0, section="costi"),
        Entry("70/01/002", "AMM.TO IMPIANTI E MACCHINARI", D("70"), level=0, section="costi"),
    ]
    _bs, ce = build_iv_cee(entries, default_ce=True)
    assert ce["ce09"] == D("100")
    assert ce["ce09a_ammort_immateriali"] == D("30")
    assert ce["ce09b_ammort_materiali"] == D("70")
    assert ce.get("ce12", D(0)) == 0


def test_schema_di_legge_legge_le_lettere_di_b10():
    from importers.standard_ivcee_parser import _ce09_dettaglio, _Row
    righe = [
        _Row(1, 0, "10) ammortamenti e svalutazioni", (D("30310"), None)),
        _Row(1, 1, "a) ammortamento delle immobilizzazioni immateriali", (D("780"), None)),
        _Row(1, 2, "b) ammortamento delle immobilizzazioni materiali", (D("14581"), None)),
        _Row(1, 3, "c) altre svalutazioni delle immobilizzazioni", (None, None)),
        _Row(1, 4, "d) svalutazioni dei crediti compresi nell'attivo", (D("14949"), None)),
    ]
    assert _ce09_dettaglio(righe, 0, 5, 0, D("30310")) == {
        "ce09a_ammort_immateriali": D("780"), "ce09b_ammort_materiali": D("14581"),
        "ce09d_svalutazione_crediti": D("14949")}
    # lettere che non chiudono sul totale stampato: nessuna
    assert _ce09_dettaglio(righe, 0, 5, 0, D("30000")) == {}
