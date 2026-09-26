"""Firma del motore e pareggio persistiti sul ForecastYear (spec fix rilievi 2026-09-26 §3, lotto 1)."""
from decimal import Decimal as D

from calculations.forecast_engine import ENGINE_VERSION, engine_meta
from tests.rilievi_kit import genera, generato, righe


def test_engine_meta_serializza_il_pareggio_in_stringhe():
    meta = engine_meta({"pareggio": {"costi_variabili": D("10.005"), "fatturato_pareggio": None}})
    # lotto 2 fix rilievi (2026-09-26): C08 aggiunge `erogazioni`, sempre presente.
    assert meta == {"engine_version": ENGINE_VERSION,
                    "pareggio": {"costi_variabili": "10.01", "fatturato_pareggio": None},
                    "erogazioni": "0.00"}


def test_engine_meta_senza_pareggio_dichiara_none():
    # lotto 2 fix rilievi (2026-09-26): C08 aggiunge `erogazioni`, "0.00" quando `details` non ha
    # ne' debito bancario ne' altri finanziatori ne' fidi ne' scoperto — zero vero, non assenza.
    assert engine_meta({}) == {"engine_version": ENGINE_VERSION, "pareggio": None, "erogazioni": "0.00"}


def test_engine_meta_erogazioni_somma_contratti_altri_finanziatori_fidi_e_scoperto():
    """C08: `erogazioni` somma l'erogato dei contratti bancari, l'erogato degli altri
    finanziatori (prima scartato), il tiraggio dei fidi e lo scoperto generato nell'anno."""
    details = {
        "debito_bancario": {
            "contratti": [{"erogato": D("280000")}, {"erogato": D("1000.005")}],
            "fidi": {"tiraggio": D("500.001")},
        },
        "altri_finanziatori": {"contratti": [{"erogato": D("2000.50")}]},
        "scoperto_generato": D("100.004"),
    }
    meta = engine_meta(details)
    # 280000 + 1000.005 + 2000.50 + 500.001 + 100.004 = 283600.510, arrotondato una volta sola alla fine
    assert meta["erogazioni"] == "283600.51"


def test_ogni_anno_generato_porta_firma_e_pareggio_del_motore():
    e = generato(genera(righe()))
    assert set(e.meta) == {2027, 2028, 2029}
    for anno, meta in e.meta.items():
        assert meta["engine_version"] == ENGINE_VERSION == "2"
        atteso = {k: (None if v is None else str(D(str(v)).quantize(D("0.01"))))
                  for k, v in e.det[anno]["pareggio"].items()}
        assert meta["pareggio"] == atteso, anno
