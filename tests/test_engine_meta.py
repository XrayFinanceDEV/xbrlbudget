"""Firma del motore e pareggio persistiti sul ForecastYear (spec fix rilievi 2026-09-26 §3, lotto 1)."""
from decimal import Decimal as D

from calculations.forecast_engine import ENGINE_VERSION, engine_meta
from tests.rilievi_kit import genera, generato, righe


def test_engine_meta_serializza_il_pareggio_in_stringhe():
    meta = engine_meta({"pareggio": {"costi_variabili": D("10.005"), "fatturato_pareggio": None}})
    # lotto 2 fix rilievi (2026-09-26): C08 aggiunge `erogazioni`, sempre presente.
    # F2 (decisione del proprietario, 2026-09-26): aggiunge `rimborsi_piano`, sempre presente.
    assert meta == {"engine_version": ENGINE_VERSION,
                    "pareggio": {"costi_variabili": "10.01", "fatturato_pareggio": None},
                    "erogazioni": "0.00", "rimborsi_piano": "0.00", "avvisi": []}


def test_engine_meta_senza_pareggio_dichiara_none():
    # lotto 2 fix rilievi (2026-09-26): C08 aggiunge `erogazioni`, "0.00" quando `details` non ha
    # ne' debito bancario ne' altri finanziatori ne' fidi ne' scoperto — zero vero, non assenza.
    # F2 (decisione del proprietario, 2026-09-26): stesso zero vero per `rimborsi_piano`.
    assert engine_meta({}) == {"engine_version": ENGINE_VERSION, "pareggio": None,
                               "erogazioni": "0.00", "rimborsi_piano": "0.00", "avvisi": []}


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


def test_engine_meta_rimborsi_piano_somma_contratti_piano_anni_e_altri_finanziatori():
    """F2 (decisione del proprietario, 2026-09-26): `rimborsi_piano` somma il `rimborso` dei
    contratti bancari (nuovi e pregressi con calendario), il `rimborso` del pregresso bancario su
    piano anni e il `rimborso` degli altri finanziatori — ESCLUSI il pregresso bancario senza
    piano (solo `rimborso_sweep`), i fidi (`tiraggio`/`rimborso_sweep`, mai una rata) e lo
    scoperto (non vive in `debito_bancario`)."""
    details = {
        "debito_bancario": {
            "contratti": [{"rimborso": D("53409.00")}, {"rimborso": D("1000.005")}],
            "pregresso_piano_anni": {"rimborso": D("2000.50")},
            "pregresso_senza_piano": {"rimborso_sweep": D("999999.00")},
            "fidi": {"tiraggio": D("300000.00"), "rimborso_sweep": D("888888.00")},
        },
        "altri_finanziatori": {"rimborso": D("300.001")},
        "scoperto_generato": D("500000.00"),
    }
    meta = engine_meta(details)
    # 53409.00 + 1000.005 + 2000.50 + 300.001 = 56709.506, arrotondato una volta sola alla fine —
    # lo sweep, i fidi e lo scoperto non entrano affatto nella somma.
    assert meta["rimborsi_piano"] == "56709.51"


def test_engine_meta_rimborsi_piano_senza_alcun_piano_e_zero_vero():
    """Un anno interamente a sweep (nessun contratto, nessun piano anni, altri finanziatori mai
    dichiarati) non ha rate: "0.00", non `None` — zero vero, non assenza."""
    details = {
        "debito_bancario": {"pregresso_senza_piano": {"rimborso_sweep": D("100.00")}},
    }
    assert engine_meta(details)["rimborsi_piano"] == "0.00"


def test_ogni_anno_generato_porta_firma_e_pareggio_del_motore():
    e = generato(genera(righe()))
    assert set(e.meta) == {2027, 2028, 2029}
    for anno, meta in e.meta.items():
        assert meta["engine_version"] == ENGINE_VERSION == "3"
        atteso = {k: (None if v is None else str(D(str(v)).quantize(D("0.01"))))
                  for k, v in e.det[anno]["pareggio"].items()}
        assert meta["pareggio"] == atteso, anno


def test_engine_meta_porta_gli_avvisi_e_la_versione_3():
    from calculations.forecast_engine import ENGINE_VERSION, engine_meta
    assert ENGINE_VERSION == "3"
    meta = engine_meta({'avvisi': ['uno', 'due']})
    assert meta['avvisi'] == ['uno', 'due']
    assert engine_meta({})['avvisi'] == []


def test_ogni_anno_generato_ha_la_lista_avvisi():
    e = generato(genera(righe()))
    for anno in e.meta:
        assert e.det[anno]['avvisi'] == []
        assert e.meta[anno]['avvisi'] == []
