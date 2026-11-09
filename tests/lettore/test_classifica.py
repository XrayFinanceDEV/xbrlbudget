"""Classificazione in due passi (Task 3): Qwen sempre finto."""
from decimal import Decimal

from importers.llm_provider import ContestoEccessivo, LLMProviderError, RispostaTroncata
from importers.lettore import classifica as c
from importers.lettore.foglie import Ancora, Foglia


def F(id, etichetta="Crediti vari", lato="L", sezione="SP", percorso=None, verso=None, antenati=(), lato_sp=None):
    return Foglia(id, etichetta, "", lato, sezione, Decimal(10), percorso, antenati, verso, lato_sp)


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
    cache = {}
    c.classifica_macro([F("a")], chiama_json=finto, cache=cache)
    n = len(finto.chiamate)
    out = c.classifica_macro([F("b")], chiama_json=finto, cache=cache)
    assert len(finto.chiamate) == n and out["b"].macro == "sp06"
    assert c.classifica_macro([F("z")], chiama_json=finto, cache={})["z"].macro == "sp06"
    assert len(finto.chiamate) == n + 1


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
    d = {}
    out = c.classifica_macro([F("a")], chiama_json=Finto(LLMProviderError("giu'")), diagnostica=d)
    assert out["a"].macro is None and out["a"].fonte == "errore" and d["foglie_errore"] == 1
    out = c.rivota([F("a")], out, chiama_json=Finto(LLMProviderError("giu'")))
    assert out["a"].macro is None


def _deterministico(schema_msgs_risposta):
    """Risponde solo dal contenuto del prompt: stesso prompt, stessa risposta."""
    visti = []

    def fa(system, messaggi, schema, *, max_tokens, timeout):
        testo = messaggi[0]["content"]
        visti.append(testo)
        risp = schema_msgs_risposta(testo)
        return {i: risp for i in schema["properties"]}
    fa.visti = visti
    return fa


def test_voti_con_prompt_diversi():
    fa = _deterministico(lambda t: "sp07" if "oggi sommano" in t else "sp06")
    a = Ancora("sp06", Decimal(100), "Crediti", ("a",))
    out = c.rivota([F("a", antenati=("Crediti",)), F("b", antenati=("Crediti",))], {}, chiama_json=fa,
                   ancora=a, somma=Decimal(90))
    assert len(set(fa.visti)) == 3
    assert any("sp06 = 100" in t and "90" in t for t in fa.visti)
    assert out["a"].macro == "sp06" and out["a"].fonte == "voto"
    assert not any("10" == x for x in fa.visti)   # nessun importo di foglia nel prompt


def test_antenato_distingue_la_cache():
    finto = Finto("sp06")
    c.classifica_macro([F("a", "Altri", antenati=("Crediti",)), F("b", "Altri", antenati=("Rimanenze",))],
                       chiama_json=finto)
    assert len(finto.chiamate[0][1]["properties"]) == 2


def test_oltre_sessanta_foglie_due_blocchi():
    finto = Finto("sp06")
    out = c.classifica_macro([F(f"f{i}", f"Voce {i}") for i in range(61)], chiama_json=finto)
    assert len(finto.chiamate) == 2 and all(o.macro == "sp06" for o in out.values())
    assert sorted(len(m[1]["properties"]) for m in finto.chiamate) == [1, 60]
    assert all(set(m[1]["required"]) == set(m[1]["properties"]) for m in finto.chiamate)


def test_troncata_si_dimezza():
    chiamate = []

    def fa(system, messaggi, schema, *, max_tokens, timeout):
        chiamate.append(len(schema["properties"]))
        if len(schema["properties"]) > 2:
            raise RispostaTroncata("tagliata")
        return {i: "sp06" for i in schema["properties"]}
    d = {}
    out = c.classifica_macro([F(f"f{i}", f"Voce {i}") for i in range(4)], chiama_json=fa, diagnostica=d)
    assert all(o.macro == "sp06" and o.fonte == "modello" for o in out.values())
    assert chiamate == [4, 2, 2] and d["dimezzamenti"] == 1 and d["foglie_errore"] == 0


def test_troncata_persistente_errore():
    def fa(system, messaggi, schema, *, max_tokens, timeout):
        raise ContestoEccessivo("troppo")
    out = c.classifica_macro([F("a"), F("b", "Altro")], chiama_json=fa)
    assert {o.fonte for o in out.values()} == {"errore"}


def test_x_in_maggioranza_nei_voti():
    out = c.rivota([F("a")], {"a": c.Classe("sp06", None, "modello")}, chiama_json=Finto("X"))
    assert out["a"].macro is None and out["a"].fonte == "voto"


def test_lato_u_con_lato_sp():
    finto = Finto("X")
    c.classifica_macro([F("a", lato="U", lato_sp="A"), F("b", "Debiti", lato="U", lato_sp="P"),
                        F("u", "Ignoto", lato="U")], chiama_json=finto)
    p = finto.chiamate[0][1]["properties"]
    assert "sp16" not in p["a"]["enum"] and "sp06" not in p["b"]["enum"]
    assert "sp06" in p["u"]["enum"] and "sp16" in p["u"]["enum"]


def test_percorso_legale_del_lato_sbagliato_va_al_modello():
    finto = Finto("sp06")
    out = c.classifica_macro([F("a", lato="R", percorso="SPA.C.II.1.E")], chiama_json=finto)
    assert len(finto.chiamate) == 1 and out["a"].macro is None   # sp06 non e' ammessa sul lato R


def test_rivota_non_tocca_legale_ne_aliasing():
    classi = {"a": c.Classe("sp06", "sp06a", "legale"), "b": c.Classe("sp05", None, "modello")}
    finto = Finto("sp07")
    out = c.rivota([F("a"), F("b", "Altro")], classi, chiama_json=finto)
    assert out["a"].macro == "sp06" and out["a"].fonte == "legale" and out["b"].macro == "sp07"
    out["a"].dettaglio = "zz"
    assert classi["a"].dettaglio == "sp06a" and classi["b"].macro == "sp05"


def test_rivota_aggiorna_la_cache():
    cache = {}
    foglia = F("a")
    c.rivota([foglia], {"a": c.Classe("sp05", None, "modello")}, chiama_json=Finto("sp07"), cache=cache)
    assert list(cache.values()) == ["sp07"]


def test_prompt_dettaglio_nomina_la_macro():
    visti = []

    def fa(system, messaggi, schema, *, max_tokens, timeout):
        visti.append(messaggi[0]["content"])
        return {i: "altri" for i in schema["properties"]}
    c.classifica_dettagli([F("a", "Banca", lato="R")], {"a": c.Classe("sp16", None, "modello")}, chiama_json=fa)
    assert "voce: sp16" in visti[0]


# --- Task 9: «X» solo per cio' che non e' un conto ----------------------------------------------------------------

def test_contesto_dice_il_lato_dello_stato_patrimoniale():
    # il modello vede «attivo»/«passivo», non solo la colonna fisica: un debito in dare fra le attivita' e' un conto
    finto = Finto("sp06")
    c.classifica_macro([F("a", "Fornitori esteri", lato="L"), F("b", "Clienti", lato="R"),
                        F("u", "Banca", lato="U", lato_sp="A")], chiama_json=finto)
    testo = finto.chiamate[0][0][0]["content"]
    riga = {r.split(" | ")[0]: r for r in testo.splitlines() if " | " in r}
    assert "attivo" in riga["a"] and "passivo" in riga["b"] and "attivo" in riga["u"]


def test_prompt_riserva_x_alle_righe_che_non_sono_conti():
    p = c.PROMPT_MACRO.lower()
    assert "lato invertito" in p and "voce ammessa piu' vicina" in p


def test_lato_opposto_solo_rettifiche_nell_enum():
    finto = Finto("X")
    c.classifica_macro([F("a", "Fondo amm. impianti", lato="R"), F("b", "Perdite a nuovo", lato="L")], chiama_json=finto)
    p = finto.chiamate[0][1]["properties"]
    assert "sp03.F" in p["a"]["enum"] and "sp03" not in p["a"]["enum"] and "sp12g.N" not in p["a"]["enum"]
    assert "sp12g.N" in p["b"]["enum"] and "sp12" not in p["b"]["enum"] and "sp03.F" not in p["b"]["enum"]


def test_fondo_dal_modello_si_netta_sul_bene():
    out = c.classifica_macro([F("a", "Fondo amm. impianti", lato="R")], chiama_json=Finto("sp03.F"))
    assert out["a"].macro == "sp03" and out["a"].rettifica == "SPA.B.II.F" and out["a"].dettaglio is None
    out = c.classifica_macro([F("a", "Fondo sval. crediti", lato="R")], chiama_json=Finto("sp06.F"))
    assert out["a"].macro == "sp06" and out["a"].dettaglio == "sp06a" and out["a"].rettifica == "SPA.C.II.1.F"
    out = c.classifica_macro([F("a", "Perdite a nuovo", lato="L")], chiama_json=Finto("sp12g.N"))
    assert out["a"].macro == "sp12" and out["a"].dettaglio == "sp12g" and out["a"].rettifica == "SPP.A.VIII"


def test_rettifica_dal_lato_sbagliato_scartata():
    out = c.classifica_macro([F("a", "Impianti", lato="L")], chiama_json=Finto("sp03.F"))
    assert out["a"].macro is None and out["a"].fonte == "nessuna"


def test_voto_tiene_la_rettifica():
    f = F("a", "Fondo amm. impianti", lato="R")
    out = c.rivota([f], {"a": c.Classe(None, None, "nessuna")}, chiama_json=Finto("sp03.F"))
    assert out["a"].macro == "sp03" and out["a"].rettifica == "SPA.B.II.F" and out["a"].fonte == "voto"
