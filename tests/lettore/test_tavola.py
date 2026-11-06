"""La tavola unica: percorso di legge -> campo -> macro-voce -> dettaglio KPI -> secchio «altri»."""
from decimal import Decimal

import pytest

from importers import iv_cee_hierarchy as h
from importers.import_snello import percorsi
from importers.lettore import tavola as t
from importers.residual_finalization import CE_BUCKETS
from importers.situazione_contabile_parser import TIER0_FIELDS


@pytest.mark.parametrize("percorso,atteso", [
    ("SPA.C.II.1.E", "sp06a"), ("SPP.D.4.E", "sp16a"), ("SPP.D.4.O", "sp17a"), ("CE.B.9.a", "ce08b"), ("CE.B.9.c", "ce08a"),
    ("CE.B.10.b", "ce09b"), ("CE.A.3", "ce03"), ("CE.A.4", "ce03a"),
])
def test_percorsi_noti(percorso, atteso):
    assert t.campo_da_percorso_legale(percorso) == atteso
    assert t.campo_da_percorso_legale(percorso) == percorsi.campo_da_percorso(percorso)


def test_macro_e_altri():
    assert t.macro_di("sp16b") == "sp16"
    assert t.macro_di("sp06") == "sp06"
    assert t.macro_di("ce08d") == "ce08"
    assert t.macro_di("ce03a") == "ce03a"
    assert t.altri_di("sp16") == "sp16g"
    assert t.altri_di("sp06") == "sp06g"
    assert t.altri_di("ce08") == "ce08d"
    assert t.altri_di("sp01") == "sp01b"
    assert t.altri_di("sp13") == "sp13"
    assert t.altri_di("ce05") == "ce05"
    assert t.nome_pieno(t.altri_di("ce09")) == CE_BUCKETS["ce09_ammortamenti"]
    assert t.nome_pieno(t.altri_di("sp16")) == h.residual_bucket("sp16_debiti_breve", Decimal(1))


def test_macro_ammesse_per_lato():
    assert "sp06" in t.macro_ammesse("L", "SP", None)
    assert "sp16" not in t.macro_ammesse("L", "SP", None)
    assert "sp16" in t.macro_ammesse("R", "SP", None)
    assert "ce05" in t.macro_ammesse("U", "CE", "costo")
    assert "ce01" not in t.macro_ammesse("U", "CE", "costo")
    assert "ce01" in t.macro_ammesse("U", "CE", "ricavo")
    assert set(t.macro_ammesse("L", "CE", None)) == set(t.MACRO_COSTI) | set(t.MACRO_RICAVI)


def test_nessun_tier0_come_altri():
    for macro in t.MACRO_ATTIVO + t.MACRO_PASSIVO + t.MACRO_COSTI + t.MACRO_RICAVI:
        altri = t.altri_di(macro)
        if altri in TIER0_FIELDS:
            assert altri == macro and macro not in t.DETTAGLI_KPI and not h.detail_fields(t.nome_pieno(macro))


def test_dettagli_kpi_dentro_la_macro():
    for macro, dettagli in t.DETTAGLI_KPI.items():
        for d in dettagli:
            assert t.macro_di(d) == macro
            assert t.nome_pieno(d) in h.detail_fields(t.nome_pieno(macro))


def test_macro_note_e_ordinate():
    assert t.MACRO_ATTIVO == tuple(f"sp{n:02d}" for n in range(1, 11))
    assert t.MACRO_PASSIVO == tuple(f"sp{n:02d}" for n in range(11, 19))
    for m in t.MACRO_ATTIVO + t.MACRO_PASSIVO + t.MACRO_COSTI + t.MACRO_RICAVI:
        assert m in percorsi.NOMI and t.ETICHETTE_MACRO[m]


def test_lato_sconosciuto():
    with pytest.raises(ValueError):
        t.macro_ammesse("X", "SP", None)
    with pytest.raises(ValueError):
        t.macro_ammesse("L", "ZZ", None)
