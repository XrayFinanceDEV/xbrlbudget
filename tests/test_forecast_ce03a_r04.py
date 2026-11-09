"""Task 5-bis parte 2: R04 vale anche per ce03a (A.4, incrementi per lavori interni): zero negli anni
di piano salvo ``ce03a_override`` (come ce03/A.3, ce18, ce19). ENGINE_VERSION 5."""
from decimal import Decimal as D

from calculations.forecast_engine import ENGINE_VERSION
from tests.rilievi_kit import BASE_CE, genera, generato, righe

A4 = "ce03a_incrementi_immobilizzazioni"
# base a utile invariato: 40.000 di A.4 tolti da A.5, cosi' CE e sp13 quadrano ancora
BASE_A4 = {A4: D("40000"), "ce04_altri_ricavi": BASE_CE["ce04_altri_ricavi"] - D("40000")}


def test_ce03a_della_base_non_si_riporta_e_l_override_vince():
    e = generato(genera(righe(), ce=BASE_A4))
    assert all(e.anni[y][1][A4] == 0 for y in (2027, 2028, 2029))
    e = generato(genera(righe(ce03a_override=7000), ce=BASE_A4))
    assert e.anni[2027][1][A4] == D("7000")


def test_engine_version_5():
    assert ENGINE_VERSION == "5"
