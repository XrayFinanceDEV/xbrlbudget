"""Classificazione in due passi (Task 3): Qwen sempre finto."""
from decimal import Decimal

from importers.llm_provider import LLMProviderError
from importers.lettore import classifica as c
from importers.lettore.foglie import Foglia


def F(id, etichetta="Crediti vari", lato="L", sezione="SP", percorso=None, verso=None):
    return Foglia(id, etichetta, "", lato, sezione, Decimal(10), percorso, (), verso, None)


class Finto:
    def __init__(self, risposta):
        self.risposta, self.chiamate = risposta, []

    def __call__(self, system, messaggi, schema, *, max_tokens, timeout):
        self.chiamate.append((messaggi, schema))
        if isinstance(self.risposta, Exception):
            raise self.risposta
        r = self.risposta
        if callable(r):
            r = r(len(self.chiamate))
        return {i: r for i in schema["properties"]} if isinstance(r, str) else r


def test_percorso_legale_senza_modello():
    finto = Finto("sp06")
    out = c.classifica_macro([F("a", percorso="SPA.C.II.1.E"), F("b", percorso="SPA.B.II.1")], chiama_json=finto)
    assert finto.chiamate == []
    assert out["a"].fonte == "legale" and out["a"].macro == "sp06"


def test_enum_ristretto_al_lato():
    finto = Finto("X")
    c.classifica_macro([F("a", lato="L"), F("b", "Debiti diversi", lato="R")], chiama_json=finto)
    p = finto.chiamate[0][1]["properties"]
    assert "sp16" not in p["a"]["enum"] and "sp06" in p["a"]["enum"]
    assert "sp06" not in p["b"]["enum"] and "sp16" in p["b"]["enum"]


def test_risposta_fuori_lato_scartata():
    out = c.classifica_macro([F("a")], chiama_json=Finto("sp16"))
    assert out["a"].macro is None and out["a"].fonte == "nessuna"


def test_cache_una_domanda_per_etichetta():
    finto = Finto("sp06")
    out = c.classifica_macro([F("a"), F("b")], chiama_json=finto)
    assert len(finto.chiamate[0][1]["properties"]) == 1
    assert out["a"].macro == out["b"].macro == "sp06"
    c.classifica_macro([F("z")], chiama_json=finto, cache={})  # cache nuova: richiede
    cache = {}
    c.classifica_macro([F("a")], chiama_json=finto, cache=cache)
    n = len(finto.chiamate)
    c.classifica_macro([F("b")], chiama_json=finto, cache=cache)
    assert len(finto.chiamate) == n


def test_voti_maggioranza():
    finto = Finto(lambda n: ["sp06", "sp06", "sp07"][n - 1] if n <= 3 else "sp06")
    prec = {"a": c.Classe("sp05", None, "modello")}
    out = c.rivota([F("a")], prec, chiama_json=finto)
    assert out["a"].macro == "sp06" and out["a"].fonte == "voto" and len(out["a"].voti) == 3
    assert prec["a"].macro == "sp05"


def test_voti_senza_maggioranza():
    finto = Finto(lambda n: ["sp06", "sp07", "sp05"][n - 1])
    out = c.rivota([F("a")], {"a": c.Classe("sp08", None, "modello")}, chiama_json=finto)
    assert out["a"].macro == "sp08" and out["a"].fonte == "voto"
    assert sorted(out["a"].voti) == ["sp05", "sp06", "sp07"]


def test_dettaglio_dentro_la_macro():
    f = F("a", "Banca c/c", lato="R")
    classi = {"a": c.Classe("sp16", None, "modello")}
    c.classifica_dettagli([f], classi, chiama_json=Finto("sp16b"))
    assert classi["a"].dettaglio == "sp16b" and classi["a"].macro == "sp16"
    classi = {"a": c.Classe("sp16", None, "modello")}
    c.classifica_dettagli([f], classi, chiama_json=Finto("sp17a"))
    assert classi["a"].dettaglio is None


def test_macro_senza_dettagli_kpi_non_chiede():
    finto = Finto("altri")
    c.classifica_dettagli([F("a")], {"a": c.Classe("sp04", None, "modello")}, chiama_json=finto)
    assert finto.chiamate == []


def test_errore_del_modello():
    out = c.classifica_macro([F("a")], chiama_json=Finto(LLMProviderError("giu'")))
    assert out["a"].macro is None and out["a"].fonte == "nessuna"
    out = c.rivota([F("a")], out, chiama_json=Finto(LLMProviderError("giu'")))
    assert out["a"].macro is None
