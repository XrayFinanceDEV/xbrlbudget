from decimal import Decimal as D

import pytest

from importers.import_snello import percorsi as P


@pytest.mark.parametrize("p, atteso", [
    ("SPA.B.I.5", "sp02e"), ("SPA.B.II.2", "sp03b"), ("SPA.B.II.2.F", "sp03b"), ("SPA.B.II", "sp03"),
    ("SPA.B.III.2", "sp04b"), ("SPA.B.III.2.O", "sp04c"), ("SPA.C.I.1", "sp05a"), ("SPA.C.I", "sp05"),
    ("SPA.C.II.1", "sp06a"), ("SPA.C.II.1.E", "sp06a"), ("SPA.C.II.1.O", "sp07a"), ("SPA.C.II.5-bis", "sp06e"),
    ("SPA.C.II.5-quater.O", "sp07g"), ("SPA.C.II.E", "sp06"), ("SPA.C.II.O", "sp07"), ("SPA.C.IV.3", "sp09"),
    ("SPA.D", "sp10"), ("SPP.A.I", "sp11"), ("SPP.A.IV", "sp12c"), ("SPP.A.VIII", "sp12g"), ("SPP.A.IX", "sp13"),
    ("SPP.B.4", "sp14d"), ("SPP.C", "sp15"), ("SPP.D.4", "sp16a"), ("SPP.D.4.O", "sp17a"), ("SPP.D.3", "sp16b"),
    ("SPP.D.7.E", "sp16d"), ("SPP.D.12", "sp16e"), ("SPP.D.13", "sp16f"), ("SPP.D.14.O", "sp17g"),
    ("SPP.D.E", "sp16"), ("SPP.D.O", "sp17"), ("SPP.E", "sp18"),
    ("CE.A.1", "ce01"), ("CE.A.2", "ce02"), ("CE.A.3", "ce03"), ("CE.A.4", "ce03a"), ("CE.A.5", "ce04"), ("CE.B.6", "ce05"),
    ("CE.B.7", "ce06"), ("CE.B.8", "ce07"), ("CE.B.9.a", "ce08b"), ("CE.B.9.b", "ce08c"), ("CE.B.9.c", "ce08a"),
    ("CE.B.9.e", "ce08d"), ("CE.B.9", "ce08"), ("CE.B.10.a", "ce09a"), ("CE.B.10.d", "ce09d"), ("CE.B.10", "ce09"),
    ("CE.B.11", "ce10"), ("CE.B.12", "ce11"), ("CE.B.13", "ce11b"), ("CE.B.14", "ce12"), ("CE.C.16.d", "ce14"),
    ("CE.C.17", "ce15"), ("CE.C.17-bis", "ce16"), ("CE.D.18", "ce17a"), ("CE.D.19", "ce17b"), ("CE.20", "ce20"),
    ("CE.D.20", "ce20"), ("CE.21", None), ("X", None), ("R", None), ("SPA.Z.9", None), ("", None),
])
def test_campo_da_percorso(p, atteso):
    assert P.campo_da_percorso(p) == atteso


def test_nomi_completi_dal_modello_orm():
    assert P.NOMI["sp06a"] == "sp06a_crediti_clienti_breve"
    assert P.NOMI["ce08b"] == "ce08b_salari_stipendi"
    assert P.NOMI["sp16"] == "sp16_debiti_breve"
    assert P.NOMI["ce03a"] == "ce03a_incrementi_immobilizzazioni"


def test_fondo_risultato_lato():
    assert P.e_fondo("SPA.B.II.4.F") and not P.e_fondo("SPA.B.II.4")
    assert P.e_risultato("CE.21") and P.e_risultato("CE.D.21") and not P.e_risultato("CE.20")
    assert P.lato_di("SPA.C.IV.1") == "att" and P.lato_di("SPP.D.4") == "pas" and P.lato_di("CE.B.7") == "ce"


def test_famiglia():
    assert P.famiglia("sp03b") == "att" and P.famiglia("sp16a") == "pas"
    assert P.famiglia("ce01") == "ric" and P.famiglia("ce17a") == "ric" and P.famiglia("ce18") == "ric"
    assert P.famiglia("ce06") == "cos" and P.famiglia("ce17b") == "cos" and P.famiglia("ce20") == "cos"


def test_completa_aggregati_e_nomi():
    bs, ce = P.completa({"sp03b": D("100"), "sp03d": D("50"), "sp06": D("30"), "sp06a": D("70"),
                         "sp16a": D("10"), "ce08b": D("5"), "ce08c": D("2"), "ce06": D("9")})
    assert bs["sp03_immob_materiali"] == D("150.00")
    assert bs["sp03b_impianti_macchinari"] == D("100.00")
    assert bs["sp06_crediti_breve"] == D("100.00")      # 30 stampato senza dettaglio + 70 clienti
    assert bs["sp16_debiti_breve"] == D("10.00")
    assert ce["ce08_costi_personale"] == D("7.00")
    assert ce["ce06_servizi"] == D("9.00")
    assert all(k.startswith("sp") for k in bs) and all(k.startswith("ce") for k in ce)
