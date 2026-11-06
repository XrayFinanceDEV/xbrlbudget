"""Task 5-6 (Fase 3): il percorso del lettore, anno corrente e anno precedente. Qwen sempre finto."""
import re
from decimal import Decimal as D
from types import SimpleNamespace

import pytest

from importers.import_snello.deterministico import _esito
from importers.lettore import percorso
from importers.lettore.classifica import PROMPT_MACRO
from importers.lettore.colonne import Colonna
from importers.lettore.foglie import Ancora, Foglia
from importers.lettore.percorso import importa_col_lettore
from tests.lettore.pdf_sintetico import scrivi_pdf
from tests.lettore.test_colonne import _testata
from tests.lettore.test_foglie import _contrapposte_sp
from tests.lettore.test_totali import _righe


def _schema_di_legge(prec=("700,00", "450,00", "550,00", "950,00", "100,00", "650,00", "2.470,00", "30,00", "2.400,00",
                           "1.700,00", "1.700,00", "100,00"),
                     intestazioni=("31/12/2025", "31/12/2024"), due_colonne=True):
    """Schema di legge con percorsi in etichetta; importi scelti perche' nessuna riga sia somma di altre."""
    cur = ("800,00", "500,00", "700,00", "950,00", "400,00", "650,00", "2.950,00", "100,00", "2.650,00",
           "2.000,00", "2.000,00", "400,00")
    p = prec

    def riga(etichetta, k):
        return (etichetta, cur[k], p[k]) if due_colonne else (etichetta, cur[k])

    righe = [("B) IMMOBILIZZAZIONI",), ("II - Immobilizzazioni materiali",), riga("2) impianti e macchinario", 0),
             ("C) ATTIVO CIRCOLANTE",), ("II - Crediti",), riga("1) verso clienti esigibili entro", 1),
             ("IV - Disponibilita' liquide",), riga("1) depositi bancari", 2),
             (("TOTALE ATTIVO", cur[9], p[9]) if due_colonne else ("TOTALE ATTIVO", cur[9])),
             ("STATO PATRIMONIALE PASSIVO",), ("A) PATRIMONIO NETTO",), riga("I - Capitale", 3),
             riga("IX - Utile (perdita) dell'esercizio", 4), ("D) DEBITI",),
             riga("7) debiti verso fornitori esigibili entro", 5),
             (("TOTALE PASSIVO", cur[10], p[10]) if due_colonne else ("TOTALE PASSIVO", cur[10])),
             ("CONTO ECONOMICO",), ("A) VALORE DELLA PRODUZIONE",),
             riga("1) ricavi delle vendite e delle prestazioni", 6), riga("5) altri ricavi e proventi", 7),
             ("B) COSTI DELLA PRODUZIONE",), riga("7) per servizi", 8),
             riga("21) Utile (perdita) dell'esercizio", 11)]
    voci = [(50, 100, "STATO PATRIMONIALE ATTIVO"), _testata(373, 120, intestazioni[0])]
    if due_colonne:
        voci.append(_testata(453, 120, intestazioni[1]))
    return voci + _righe(140, righe)


def _pdf(tmp_path, voci, nome="d.pdf"):
    p = tmp_path / nome
    scrivi_pdf(p, [voci])
    return str(p)


def _mai(*a, **k):
    raise AssertionError("il modello non va chiamato")


class Finto:
    """Qwen finto: la classe da una parola chiave dell'etichetta; conta le chiamate."""

    def __init__(self, regole, sbaglia=None):
        self.regole, self.sbaglia, self.chiamate, self.macro = regole, sbaglia or {}, 0, 0

    def __call__(self, system, messaggi, schema, **k):
        self.chiamate += 1
        testo = messaggi[0]["content"]
        voto = "non torna" in testo
        out = {}
        self.macro += system.startswith(PROMPT_MACRO[:30])
        for i, enum in ((i, p["enum"]) for i, p in schema["properties"].items()):
            etichetta = re.search(rf"^{re.escape(i)} \| ([^|]*)\|", testo, re.M).group(1).strip().lower()
            scelta = next((c for k_, c in self.regole.items() if k_ in etichetta), None)
            if i in self.sbaglia and not voto:
                scelta = self.sbaglia[i]
            out[i] = scelta if scelta in enum else ("altri" if "altri" in enum else enum[0])
        return out


_REGOLE = {"mutuo": "sp16", "banca": "sp09", "cassa": "sp09", "client": "sp06", "magazzino": "sp05", "impianti": "sp03",
           "capitale": "sp11", "fornitori": "sp16", "tributari": "sp16", "utile": "sp13"}


def test_schema_di_legge_senza_modello(tmp_path):
    r = importa_col_lettore(_pdf(tmp_path, _schema_di_legge()), chiama_json=_mai)
    d = r["diagnostica"]
    assert d["chiamate"] == 0 and d["blocchi"] == [] and "errore" not in d
    assert d["classi_per_fonte"] == {"legale": 9}
    assert r["bs"]["sp03_immob_materiali"] == D("800.00") and r["bs"]["sp13_utile_perdita"] == D("400.00")
    esito = _esito("lettore", r["bs"], r["ce"], r["stampati"])
    assert esito["adottato"] and esito["esito"] == "ok"


def test_contrapposte_col_modello(tmp_path):
    finto = Finto(_REGOLE)
    r = importa_col_lettore(_pdf(tmp_path, _contrapposte_sp()), chiama_json=finto)
    d = r["diagnostica"]
    assert d["chiamate"] >= 1 and d["chiamate"] == finto.chiamate
    assert d["sbilancio"] == "0.00" and d["blocchi"] == []
    assert r["bs"]["sp09_disponibilita_liquide"] == D("610.00")
    assert r["bs"]["sp11_capitale"] == D("250.00") and r["bs"]["sp13_utile_perdita"] == D("100.00")


def _finta_lettura(monkeypatch, foglie, ancore_, colonne=None):
    doc = SimpleNamespace(righe=[1], colonne=colonne or [Colonna(0, 0.0, "U", "esercizio", None, None, 12, True)])
    monkeypatch.setattr(percorso, "_leggi", lambda *a: doc)
    monkeypatch.setattr(percorso, "colonne_utili", lambda d: (0, None))
    monkeypatch.setattr(percorso, "foglie_contabili", lambda d, c: foglie)
    monkeypatch.setattr(percorso, "ancore", lambda d, c: ancore_)
    monkeypatch.setattr(percorso, "senza_colonna", lambda d, c: ())


def _f(id, importo, lato, etichetta):
    return Foglia(id, etichetta, "", lato, "SP", D(importo), None, (), None, "A" if lato == "L" else "P")


def test_blocco_rivotato(monkeypatch):
    foglie = [_f("c1", 100, "L", "Cliente Uno"), _f("c2", 100, "L", "Cliente Due"), _f("c3", 100, "L", "Cliente Tre"),
              _f("p", 300, "R", "Fornitori")]
    _finta_lettura(monkeypatch, foglie, [Ancora("sp06", D(300), "Crediti", ("c1", "c2", "c3"))])
    finto = Finto(_REGOLE | {"client": "sp06"}, sbaglia={"c1": "sp05"})
    r = importa_col_lettore("x.pdf", chiama_json=finto)
    d = r["diagnostica"]
    assert d["blocchi"] == [] and d["voti"] > 0
    assert d["classi_per_fonte"].get("voto") == 3
    assert r["bs"]["sp06_crediti_breve"] == D("300")


def test_chiavi_diagnostiche_a_zero(tmp_path):
    r = importa_col_lettore(_pdf(tmp_path, _schema_di_legge(due_colonne=False)), chiama_json=_mai)
    assert r["bs"]["_plug_residual"] == 0 and r["bs"]["_unclassified_mass"] == 0
    assert r["diagnostica"]["blocchi"] == []


def test_errore_non_solleva(tmp_path):
    r = importa_col_lettore(str(tmp_path / "non_esiste.pdf"), chiama_json=_mai)
    assert r["bs"] == {} and r["ce"] == {} and r["diagnostica"]["errore"]
    assert _esito("lettore", r["bs"], r["ce"], None)["esito"] == "vuoto"
