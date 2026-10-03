"""Segno dei costi della produzione nel modo "legge" (budget_253, 2026-10-03).

budget_253 stampa «14) Oneri diversi di gestione -1.239» fra costi positivi, e il «Totale costi
della produzione» 1.328.513 lo conferma (1.329.752 - 1.239). Il valore assoluto lo faceva +1.239
e l'utile CE si allontanava da quello dello SP del doppio (1.918 contro 4.396).
"""
from decimal import Decimal

from importers.import_snello.conti import da_coppie

_COSTI_POSITIVI = [("CE.A.1", "1318515"), ("CE.B.6", "300868"), ("CE.B.7", "325573"),
                   ("CE.B.8", "28057"), ("CE.B.9.a", "457876"), ("CE.B.10.b", "59756")]


def test_un_costo_di_produzione_stampato_contro_la_convenzione_e_una_riduzione_vera():
    _, ce, _ = da_coppie(_COSTI_POSITIVI + [("CE.B.14", "-1239")])
    assert ce["ce12_oneri_diversi"] == Decimal("-1239")
    assert ce["ce05_materie_prime"] == Decimal("300868")


def test_con_i_costi_stampati_negativi_un_costo_positivo_e_la_riduzione():
    _, ce, _ = da_coppie([("CE.A.1", "1000"), ("CE.B.6", "-300"), ("CE.B.7", "-200"),
                          ("CE.B.8", "-100"), ("CE.B.14", "50")])
    assert ce["ce05_materie_prime"] == Decimal("300")
    assert ce["ce12_oneri_diversi"] == Decimal("-50")


def test_gli_oneri_finanziari_stampati_col_meno_restano_un_costo():
    """La sezione C stampa spesso «17) interessi e altri oneri finanziari» col meno per
    presentazione (budget_289: -7.821): non e' una riduzione."""
    _, ce, _ = da_coppie(_COSTI_POSITIVI + [("CE.C.17", "-21093")])
    assert ce["ce15_oneri_finanziari"] == Decimal("21093")
