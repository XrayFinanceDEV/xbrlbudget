"""Banco di triage dei rilievi AMBIENTA (inbox/Verifica_piano_Ambienta_problemi.xlsx).

Spec: docs/superpowers/specs/2026-09-25-triage-rilievi-ambienta-design.md. Un test per rilievo software;
l'oracolo è il comportamento che il consulente si aspetta, quindi un test ROSSO vuol dire che il difetto
c'è. Nessun fix in questo file: il verdetto lo scrive tools/triage_rilievi.py.
"""
from decimal import Decimal as D

import pytest

from tests.rilievi_kit import BASE_BS, BASE_CE, genera, righe

SP = "sp"  # solo per leggibilità dei commenti


def test_kit_la_base_ambienta_genera_un_piano_a_crescita_zero():
    e = genera(righe())
    assert e.res["forecast_generated"] is True, e.res["message"]
    assert sorted(e.anni) == [2027, 2028, 2029]
    assert e.anni[2027][1]["ce01_ricavi_vendite"] == BASE_CE["ce01_ricavi_vendite"]
    assert e.anni[2027][0]["_total_assets"] == e.anni[2027][0]["_total_liabilities"]
