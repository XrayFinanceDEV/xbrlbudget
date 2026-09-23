from scripts.confronta_probe import confronta


def _rec(file, metodo, attivo, sbil, utile, campi, provider=None, ivcee_provider=None,
         dettagli_provider=None, secondi=None):
    return {"file": file, "extraction_method": metodo, "totale_attivo": attivo,
            "sbilancio": sbil, "utile_ce": utile, "quadra": sbil == "0.00", "fields": campi,
            "coge_provider": provider, "ivcee_provider": ivcee_provider,
            "dettagli_provider": dettagli_provider, "secondi": secondi}


def test_confronto_per_file_con_campi_diversi():
    a = [_rec("x.pdf", "situazione_contabile_llm", "1000.00", "0.00", "50.00",
              {"sp09_disponibilita_liquide": "400", "sp16a_debiti_banche_breve": "600"},
              provider="anthropic", ivcee_provider="anthropic", dettagli_provider="anthropic",
              secondi=12.3)]
    b = [_rec("x.pdf", "situazione_contabile", "1000.00", "0.00", "50.00",
              {"sp09_disponibilita_liquide": "400", "sp16g_altri_debiti_breve": "600"},
              provider="gx10", ivcee_provider="gx10", dettagli_provider="gx10",
              secondi=4.1)]
    righe = confronta(a, b)
    assert len(righe) == 1
    r = righe[0]
    assert r["file"] == "x.pdf"
    assert r["metodo"] == ("situazione_contabile_llm", "situazione_contabile")
    assert r["provider"] == (
        ("anthropic", "anthropic", "anthropic"),
        ("gx10", "gx10", "gx10"),
    )
    assert r["secondi"] == (12.3, 4.1)
    assert r["stesso_attivo"] is True
    assert r["campi_diversi"] == ["sp16a_debiti_banche_breve", "sp16g_altri_debiti_breve"]


def test_file_presente_in_una_sola_esecuzione():
    righe = confronta([_rec("x.pdf", "m", "1", "0.00", "0", {})], [])
    assert righe[0]["file"] == "x.pdf" and righe[0]["solo_in"] == "A"
