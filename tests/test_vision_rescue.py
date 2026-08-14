"""Tests per il riscatto vision per sezione (route C).

Spec: docs/superpowers/specs/2026-08-14-riscatto-vision-route-c-design.md
Run:  python -m pytest tests/test_vision_rescue.py -v

Nessun test in questo file effettua una chiamata di rete: la risposta vision e'
sempre passata con un doppio.
"""
import os
import sys
from decimal import Decimal

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from importers.pdf_extractor_llm import _declared_control_totals  # noqa: E402

D = Decimal


# ------------------------------------------------- ancore dichiarate del CE

def test_declared_totals_legge_i_totali_del_conto_economico():
    text = (
        "CONTO ECONOMICO\n"
        "73020005 Amm.to immobilizzazioni materiali 4.656,95\n"
        "TOTALE COSTI 2.482.879,59\n"
        "TOTALE RICAVI 2.491.786,38\n"
        "UTILE D'ESERCIZIO 8.906,79\n"
    )
    out = _declared_control_totals("ignorato.pdf", text=text)
    assert out["costi"] == D("2482879.59")
    assert out["ricavi"] == D("2491786.38")
    assert out["utile"] == D("8906.79")


def test_declared_totals_costi_ricavi_sono_none_se_non_stampati():
    text = "STATO PATRIMONIALE\nTOTALE ATTIVO 1.000,00\nTOTALE PASSIVO 1.000,00\n"
    out = _declared_control_totals("ignorato.pdf", text=text)
    assert out["costi"] is None
    assert out["ricavi"] is None


def test_declared_totals_costi_ricavi_tollerano_le_intestazioni_spaziate():
    text = "T O T A L E   C O S T I 1.234,56\nT O T A L E   R I C A V I 2.345,67\n"
    out = _declared_control_totals("ignorato.pdf", text=text)
    assert out["costi"] == D("1234.56")
    assert out["ricavi"] == D("2345.67")


def test_declared_totals_non_scambia_il_subtotale_b_per_il_totale_costi():
    # "Totale costi della produzione (B)" e' un subtotale di sezione dello schema
    # IV-CEE. Un bilancio ordinario non stampa affatto un totale costi complessivo:
    # l'ancora deve tornare None, non il subtotale.
    text = (
        "Totale valore della produzione (A) 392.761,56\n"
        "Totale costi della produzione (B) 311.646,32\n"
        "Utile dell'esercizio 45.000,00\n"
    )
    out = _declared_control_totals("ignorato.pdf", text=text)
    assert out["costi"] is None
    assert out["ricavi"] is None


def test_declared_totals_legge_ancora_il_totale_costi_di_una_situazione_contabile():
    # Il caso che serve: una situazione contabile stampa i totali di colonna, e
    # quelli devono continuare a leggersi anche se il documento cita altrove i
    # subtotali di schema.
    text = (
        "Totale costi della produzione (B) 311.646,32\n"
        "TOTALE COSTI 2.482.879,59\n"
        "TOTALE RICAVI 2.491.786,38\n"
    )
    out = _declared_control_totals("ignorato.pdf", text=text)
    assert out["costi"] == D("2482879.59")
    assert out["ricavi"] == D("2491786.38")


from importers.situazione_contabile_parser import (  # noqa: E402
    classify_attivo,
    classify_costi,
    classify_passivo,
    classify_ricavi,
)


# ------------------------------------------------- classificatori promossi

def test_classify_attivo_banche_e_cassa_sul_lato_attivo():
    # Nel layout contrapposte il LATO e' verita': BANCHE in colonna attivo e'
    # liquidita', non il fallback generico dei crediti.
    assert classify_attivo("BANCHE C/C") == ("sp09", True)


def test_classify_attivo_categoria_legale_esatta_ferma_la_discesa():
    assert classify_attivo("IMMOBILIZZAZIONI MATERIALI") == ("sp03", True)


def test_classify_passivo_fondo_ammortamento_e_un_contro_conto():
    field, _specific = classify_passivo("F.DO AMM.TO IMMOBILIZZAZIONI MATERIALI")
    assert field == "depr_sp03"


def test_classify_passivo_tipizza_i_debiti_per_creditore():
    assert classify_passivo("DEBITI VERSO FORNITORI")[0].startswith("sp16")


def test_classify_costi_e_ricavi_hanno_catch_all_distinti():
    assert classify_costi("VOCE SCONOSCIUTA XYZ") == ("ce12", False)
    assert classify_ricavi("VOCE SCONOSCIUTA XYZ") == ("ce04", False)


from importers.situazione_contabile_parser import (  # noqa: E402
    build_ce_from_vision,
    build_sp_from_vision,
)


# ------------------------------------------------- montaggio di una sezione

def test_build_sp_netta_i_fondi_dall_attivo():
    rows = [
        ("01", "IMMOBILIZZAZIONI MATERIALI", D("1000.00"), "left"),
        ("02", "F.DO AMM.TO IMMOBILIZZAZIONI MATERIALI", D("400.00"), "right"),
        ("20", "DEBITI VERSO FORNITORI", D("600.00"), "right"),
    ]
    bs = build_sp_from_vision(rows, utile=D("0"))
    assert bs["sp03"] == D("600.00")          # 1000 lordo - 400 fondo
    assert bs["_netted_contra"] == D("400.00")
    assert bs["totale_attivo"] == D("600.00")
    assert bs["totale_passivo"] == D("600.00")


def test_build_sp_scrive_il_risultato_ricevuto_e_non_lo_inventa():
    rows = [
        ("01", "CASSA", D("150.00"), "left"),
        ("20", "DEBITI VERSO FORNITORI", D("100.00"), "right"),
    ]
    bs = build_sp_from_vision(rows, utile=D("50.00"))
    assert bs["sp13"] == D("50.00")
    assert bs["totale_passivo"] == D("150.00")   # 100 debiti + 50 utile


def test_build_sp_tipizza_i_debiti_per_creditore():
    rows = [
        ("01", "CASSA", D("300.00"), "left"),
        ("20", "DEBITI VERSO FORNITORI", D("200.00"), "right"),
        ("21", "BANCHE C/C PASSIVI", D("100.00"), "right"),
    ]
    bs = build_sp_from_vision(rows, utile=D("0"))
    assert bs["sp16"] == D("300.00")                       # aggregato invariato
    assert bs["sp16d_debiti_fornitori_breve"] == D("200.00")
    assert bs["sp16a_debiti_banche_breve"] == D("100.00")


def test_build_ce_usa_la_colonna_come_direzione():
    rows = [
        ("60", "ACQUISTI MATERIE PRIME", D("500.00"), "left"),
        ("70", "RICAVI DELLE VENDITE", D("800.00"), "right"),
    ]
    ce = build_ce_from_vision(rows)
    assert ce["ce05"] == D("500.00")
    assert ce["ce01"] == D("800.00")


def test_build_ce_non_manda_un_costo_su_una_voce_di_ricavo():
    # DIFFERENZE CAMBIO PASSIVE risolve su un nodo di GUADAGNO nell'albero
    # condiviso: sulla colonna dei costi deve cadere sul catch-all neutro, mai
    # su ce16 (che ALZEREBBE il risultato, spostandolo di 2x).
    rows = [("75", "DIFFERENZE CAMBIO PASSIVE", D("90.00"), "left")]
    ce = build_ce_from_vision(rows)
    assert ce.get("ce16", D("0")) == D("0")
    assert sum(v for k, v in ce.items() if k.startswith("ce")) >= D("90.00")


def test_build_ce_arrotola_i_sottocampi_sul_padre():
    rows = [("64", "SALARI E STIPENDI", D("300.00"), "left")]
    ce = build_ce_from_vision(rows)
    assert ce["ce08"] == D("300.00")
    assert ce["ce08b_salari_stipendi"] == D("300.00")
