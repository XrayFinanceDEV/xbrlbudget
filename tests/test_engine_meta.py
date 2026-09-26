"""Firma del motore e pareggio persistiti sul ForecastYear (spec fix rilievi 2026-09-26 §3, lotto 1)."""
from decimal import Decimal as D

from calculations.forecast_engine import ENGINE_VERSION, engine_meta
from tests.rilievi_kit import genera, generato, righe


def test_engine_meta_serializza_il_pareggio_in_stringhe():
    meta = engine_meta({"pareggio": {"costi_variabili": D("10.005"), "fatturato_pareggio": None}})
    assert meta == {"engine_version": ENGINE_VERSION,
                    "pareggio": {"costi_variabili": "10.01", "fatturato_pareggio": None}}


def test_engine_meta_senza_pareggio_dichiara_none():
    assert engine_meta({}) == {"engine_version": ENGINE_VERSION, "pareggio": None}


def test_ogni_anno_generato_porta_firma_e_pareggio_del_motore():
    e = generato(genera(righe()))
    assert set(e.meta) == {2027, 2028, 2029}
    for anno, meta in e.meta.items():
        assert meta["engine_version"] == ENGINE_VERSION == "2"
        atteso = {k: (None if v is None else str(D(str(v)).quantize(D("0.01"))))
                  for k, v in e.det[anno]["pareggio"].items()}
        assert meta["pareggio"] == atteso, anno
