"""Task 5-6 (Fase 3): il percorso del lettore, anno corrente e anno precedente. Qwen sempre finto."""
import re
from datetime import date
from decimal import Decimal as D
from types import SimpleNamespace

import pytest

from importers.import_snello.deterministico import _esito
from importers.lettore import percorso
from importers.lettore.classifica import PROMPT_MACRO
from importers.llm_provider import LLMProviderError
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
    assert d["classi_per_fonte"] == {"legale": 9} and r["prior_stato"] == "letto"
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
    assert d["blocchi"] == [] and d["foglie_rivotate"] == 3 and d["voti"] == 9
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


def test_due_anni_stesse_classi(tmp_path):
    finto = Finto(_REGOLE)
    # niente percorso di legge: etichette semplici, due colonne; il modello e' chiamato una volta per etichetta
    voci = [_testata(373, 120, "31/12/2025"), _testata(453, 120, "31/12/2024")]
    sx = [("Banca c/c", "110,00", "100,00"), ("Clienti Rossi", "210,00", "190,00"), ("Magazzino merci", "330,00", "300,00"),
          ("Impianti", "450,00", "410,00")]
    voci += _righe(140, sx + [("Fornitori Alfa", "400,00", "350,00"), ("Capitale sociale", "700,00", "650,00")])
    r = importa_col_lettore(_pdf(tmp_path, voci), chiama_json=finto)
    d = r["diagnostica"]
    assert finto.macro == 1 and "errore" not in d        # un blocco, ogni etichetta una volta sola
    assert r["bs"]["sp09_disponibilita_liquide"] == D("110.00")
    assert r["anno_precedente"] == 2024
    # solo SP: il cancello `_esito` (bs e ce) non adotta il precedente, come non adotta il corrente
    assert r["prior_stato"] == "scartato" and r["diagnostica"]["prior_rifiuto"]["controllo"] == "vuoto"


def test_modello_che_solleva_ferma_le_chiamate_e_non_adotta(tmp_path):
    # interruttore: dopo il primo errore del provider (timeout, connessione) il documento non chiama piu' il modello
    chiamate = []

    def rotto(*a, **k):
        chiamate.append(1)
        raise LLMProviderError("timeout")
    voci = [_testata(373, 120, "31/12/2025"), _testata(453, 120, "31/12/2024")]
    sx = [("Banca c/c", "110,00", "100,00"), ("Clienti Rossi", "210,00", "190,00"), ("Magazzino merci", "330,00", "300,00"),
          ("Impianti", "450,00", "410,00")]
    voci += _righe(140, sx + [("Fornitori Alfa", "400,00", "350,00"), ("Capitale sociale", "700,00", "650,00")])
    r = importa_col_lettore(_pdf(tmp_path, voci), chiama_json=rotto)
    assert r["diagnostica"]["motivo"] == "modello_non_disponibile"
    assert r["bs"] == {} and r["ce"] == {} and r["prior_stato"] == "assente"
    assert len(chiamate) == 1 and "errore" not in r["diagnostica"]


def test_foglia_solo_nel_precedente_stesso_giro(monkeypatch):
    corr = _anno(100, 60)
    prec = _anno(90, 70, extra=[_f("b", 20, "L", "Banca")])
    _due_anni(monkeypatch, corr, prec)
    finto = Finto(_REGOLE)
    r = importa_col_lettore("x.pdf", chiama_json=finto)
    assert finto.macro == 1
    assert r["prior_stato"] == "letto" and r["prior_bs"]["sp09_disponibilita_liquide"] == D("20")
    assert r["prior_bs"]["sp06_crediti_breve"] == D("90")


def test_precedente_di_nove_mesi(tmp_path):
    voci = _schema_di_legge(intestazioni=("dal 01/01/2026 al 30/09/2026", "dal 01/01/2025 al 30/09/2025"))
    r = importa_col_lettore(_pdf(tmp_path, voci), chiama_json=_mai)
    assert r["diagnostica"]["mesi_precedente"] == 9 and r["anno_precedente"] == 2025


def test_precedente_esercizio_non_solare_senza_inizio_stampato(tmp_path):
    # esercizio 1/7-30/6: la colonna stampa solo «30/06/2025», senza inizio; contare da gennaio darebbe 6 mesi.
    # Senza inizio stampato la durata del precedente non e' nota: None, mai un parziale finto.
    voci = _schema_di_legge(intestazioni=("30/06/2026", "30/06/2025"))
    r = importa_col_lettore(_pdf(tmp_path, voci), chiama_json=_mai)
    assert r["diagnostica"]["mesi_precedente"] is None and r["anno_precedente"] == 2025


def test_precedente_che_non_torna_scartato(tmp_path):
    # il deposito del precedente vale 540 invece di 550: l'attivo stampato (1.700) non torna
    prec = ("700,00", "450,00", "540,00", "950,00", "100,00", "650,00", "2.470,00", "30,00", "2.400,00",
            "1.700,00", "1.700,00", "100,00")
    r = importa_col_lettore(_pdf(tmp_path, _schema_di_legge(prec=prec)), chiama_json=_mai)
    assert r["prior_stato"] == "scartato" and r["prior_bs"] is None and r["prior_ce"] is None
    assert r["diagnostica"]["blocchi"] == []
    assert _esito("lettore", r["bs"], r["ce"], r["stampati"])["adottato"]


def test_una_colonna_niente_precedente(tmp_path):
    r = importa_col_lettore(_pdf(tmp_path, _schema_di_legge(due_colonne=False)), chiama_json=_mai)
    assert r["prior_bs"] is None and r["prior_stato"] == "assente" and r["anno_precedente"] is None


def _ce(id, importo, verso, etichetta):
    return Foglia(id, etichetta, "", "U", "CE", D(importo), None, (), verso, None)


def _due_anni(monkeypatch, corr, prec):
    cols = [Colonna(0, 0.0, "U", "esercizio", date(2025, 12, 31), None, 12, True),
            Colonna(1, 0.0, "U", "esercizio", date(2024, 12, 31), None, 12, False)]
    _finta_lettura(monkeypatch, corr, [], cols)
    monkeypatch.setattr(percorso, "colonne_utili", lambda d: (0, 1))
    monkeypatch.setattr(percorso, "foglie_contabili", lambda d, c: corr if c == 0 else prec)


_REGOLE_CE = _REGOLE | {"ricavi": "ce01", "costi": "ce06", "xyz": "X"}


def _anno(a, capitale, extra=()):
    return [_f("a", a, "L", "Clienti"), *extra, _f("p", capitale, "R", "Capitale"),
            _ce("r", 100, "ricavo", "Ricavi vendite"), _ce("c", 60, "costo", "Costi servizi")]


def test_precedente_con_massa_non_classificata_scartato(monkeypatch):
    # il precedente quadra (la massa va nel secchio «altri») ma 5.000 EUR non hanno classe: non si adotta
    corr = _anno(100, 60)
    prec = _anno(100, 5060, extra=[_f("x", 5000, "L", "Xyz")])
    _due_anni(monkeypatch, corr, prec)
    r = importa_col_lettore("x.pdf", chiama_json=Finto(_REGOLE_CE))
    assert _esito("lettore", r["bs"], r["ce"], r["stampati"])["esito"] == "ok"
    assert r["prior_stato"] == "scartato" and r["prior_bs"] is None
    assert r["diagnostica"]["prior_rifiuto"]["controllo"] == "massa_non_classificata"


def test_precedente_pulito_letto_con_il_cancello(monkeypatch):
    _due_anni(monkeypatch, _anno(100, 60), _anno(90, 50))
    r = importa_col_lettore("x.pdf", chiama_json=Finto(_REGOLE_CE))
    assert r["prior_stato"] == "letto" and r["prior_bs"]["sp06_crediti_breve"] == D("90")


def test_modello_che_fallisce_non_adottato(monkeypatch):
    def cade(*a, **k):
        raise LLMProviderError("gx10 giu'")
    _finta_lettura(monkeypatch, _anno(5000, 4960), [])
    r = importa_col_lettore("x.pdf", chiama_json=cade)
    assert r["diagnostica"]["motivo"] == "modello_non_disponibile"      # interruttore: nessuna composizione
    assert _esito("lettore", r["bs"], r["ce"], r["stampati"])["esito"] != "ok"


def test_errore_imprevisto_dict_completo(tmp_path):
    r = importa_col_lettore(str(tmp_path / "no.pdf"), chiama_json=_mai)
    assert r["prior_bs"] is None and r["prior_ce"] is None and r["prior_stato"] == "assente"
    assert r["stampati"] == {} and r["diagnostica"]["mesi_precedente"] is None


def test_chiamate_due_anni_come_un_anno(tmp_path):
    righe = [("Banca c/c", "110,00", "100,00"), ("Clienti Rossi", "210,00", "190,00"),
             ("Magazzino merci", "330,00", "300,00"), ("Impianti", "450,00", "410,00"),
             ("Fornitori Alfa", "400,00", "350,00"), ("Capitale sociale", "700,00", "650,00")]
    due = [_testata(373, 120, "31/12/2025"), _testata(453, 120, "31/12/2024")] + _righe(140, righe)
    uno = [_testata(373, 120, "31/12/2025")] + _righe(140, [(a, b) for a, b, _ in righe])
    f2, f1 = Finto(_REGOLE), Finto(_REGOLE)
    importa_col_lettore(_pdf(tmp_path, due, "2.pdf"), chiama_json=f2)
    importa_col_lettore(_pdf(tmp_path, uno, "1.pdf"), chiama_json=f1)
    assert f2.chiamate == f1.chiamate >= 1


def test_foglie_non_in_pari_nessuna_chiamata(tmp_path):
    # i totali stampati tornano, le foglie no (Impianti 500 -> 5.000): la colonna decide il lato, nessuna classe lo sistema
    voci = [(x, y, "5.000,00" if t == "500,00" and x == 280 and y == 210 else t) for x, y, t in _contrapposte_sp()]
    assert any(t == "5.000,00" for _, _, t in voci)
    r = importa_col_lettore(_pdf(tmp_path, voci), chiama_json=_mai)
    assert r["diagnostica"]["motivo"] == "foglie_non_in_pari" and r["bs"] == {} and "errore" not in r["diagnostica"]
    assert _esito("lettore", r["bs"], r["ce"], r["stampati"])["esito"] == "vuoto"


def test_tetto_di_chiamate_dichiarato(tmp_path, monkeypatch):
    monkeypatch.setattr(percorso, "MAX_CHIAMATE", 1)
    finto = Finto(_REGOLE)
    r = importa_col_lettore(_pdf(tmp_path, _contrapposte_sp()), chiama_json=finto)
    assert finto.chiamate <= 1 and r["diagnostica"]["tetto_chiamate"] == 1


# --- guardia di costo con la stessa regola di lato della composizione (Task 9, fix 1) ---------------------------

def _sp(id, importo, lato, lato_sp, etichetta="Conto"):
    return Foglia(id, etichetta, "", lato, "SP", D(importo), None, (), None, lato_sp)


def test_guardia_foglia_senza_sezione_non_blocca():
    # una foglia di sezione ignota con un importo puo' essere CE: non si sa, quindi non si blocca
    foglie = [_sp("a", 100, "L", "A"), _sp("p", 100, "R", "P"),
              Foglia("x", "Acquisti merci", "", "L", "", D(5000), None, (), None, None)]
    assert percorso._foglie_non_in_pari(foglie) is None


def test_guardia_lato_come_la_composizione():
    # colonna destra con lato_sp «A»: la composizione la mette nel passivo (decide la colonna), la guardia pure
    foglie = [_sp("a", 100, "L", "A"), _sp("p", 100, "R", "A")]
    assert percorso._foglie_non_in_pari(foglie) is None


def test_guardia_utile_stampato_col_suo_segno():
    # la riga del risultato non e' mai una foglia (componi): la perdita stampata fra le attivita' torna con l'ancora
    foglie = [_sp("a", 100000, "L", "A"), _sp("r", 5000, "L", "A", "Perdita d'esercizio"), _sp("p", 105000, "R", "P")]
    assert percorso._foglie_non_in_pari(foglie, [Ancora("utile", D(-5000), "Perdita", ())]) is None
    assert percorso._foglie_non_in_pari(foglie) == "foglie_non_in_pari"


def test_guardia_lato_ignoto_non_blocca():
    foglie = [_sp("a", 100, "L", "A"), _sp("u", 900, "U", None)]
    assert percorso._foglie_non_in_pari(foglie) is None


def test_guardia_solo_ce_senza_foglie_sp():
    assert percorso._foglie_non_in_pari([_ce("r", 100, "ricavo", "Ricavi")]) == "senza_foglie_sp"


def test_guardia_verso_ce_ignoto_non_blocca_neanche_con_utile_stampato():
    # l'utile composto viene dal CE, non dallo stampato: con un verso ignoto e' libero, quindi non si sa
    foglie = [_sp("a", 100000, "L", "A"), _sp("p", 50000, "R", "P"), _ce("c", 10, None, "Varie")]
    assert percorso._foglie_non_in_pari(foglie, [Ancora("utile", D(0), "Utile", ())]) is None


def test_guardia_utile_di_un_altro_esercizio_resta_nel_passivo():
    # l'utile stampato nel passivo non e' quello del CE: resta un conto del passivo (come in `componi`), quadra
    foglie = [_sp("a", 11500, "L", "A"), _sp("p", 9000, "R", "P"), _sp("u", 1500, "R", "P", "Utile d'esercizio"),
              _ce("r", 1000, "ricavo", "Ricavi")]
    assert percorso._foglie_non_in_pari(foglie) is None


def _contrapposte_con_fondo():
    """Contrapposte con il fondo ammortamento nella colonna del passivo: i totali stampati sono lordi."""
    sx = [("Impianti", "1.130,00"), ("Cassa", "470,00"), ("Clienti Rossi", "610,00"), ("Totale attivita", "2.210,00")]
    dx = [("Fondo amm. impianti", "380,00"), ("Capitale sociale", "250,00"), ("Fornitori Alfa", "1.440,00"),
          ("Utile d'esercizio", "140,00"), ("Totale passivita", "2.210,00")]
    voci = [(40, 100, "STATO PATRIMONIALE"), (40, 120, "Attivo"), (310, 120, "Passivo")]
    for k, (a, b) in enumerate(zip(sx + [("", "")], dx)):
        y = 140 + 14 * k
        voci += [(310, y, b[0]), (560, y, b[1])] + ([(40, y, a[0]), (280, y, a[1])] if a[0] else [])
    return voci


def test_fondo_nella_colonna_del_passivo_adottabile(tmp_path):
    regole = {"fondo": "sp03.F", **_REGOLE}
    r = importa_col_lettore(_pdf(tmp_path, _contrapposte_con_fondo()), chiama_json=Finto(regole))
    bs = r["bs"]
    assert bs["sp03_immob_materiali"] == D("750.00")
    assert bs["_netted_contra"] == D("380.00") and bs["_unclassified_mass"] == 0
    # i totali stampati sono lordi: il cancello li confronta al netto della rettifica
    assert r["stampati"] == {"totale_attivo": D("1830.00"), "totale_passivo": D("1830.00")}
    assert r["diagnostica"]["sbilancio"] == "0.00" and r["diagnostica"]["rettifiche"] == "380.00"
    assert r["diagnostica"]["immobilizzazioni_negative_tagliate"] == []


def test_chiamate_del_passo_2_dichiarate(tmp_path):
    finto = Finto({"magazzino": "sp05", "impianti": "sp03", **_REGOLE})
    r = importa_col_lettore(_pdf(tmp_path, _contrapposte_sp()), chiama_json=finto)
    d = r["diagnostica"]
    # magazzino e impianti hanno dettagli: il passo 2 li chiede (prima solo le macro KPI)
    assert d["chiamate_dettagli"] >= 1 and d["chiamate_dettagli"] <= d["chiamate"] == finto.chiamate


def test_scadenza_dei_debiti_dal_testo_non_dal_modello(monkeypatch):
    # il modello manda il finanziamento senza scadenza oltre e il debito «oltre 12 mesi» a breve: decide il testo
    foglie = [_f("c", 1000, "L", "Cassa"), _f("m", 600, "R", "Mutuo banca"),
              _f("o", 400, "R", "Erario c/iva oltre 12 mesi")]
    _finta_lettura(monkeypatch, foglie, [])
    finto = Finto({"cassa": "sp09", "mutuo": "sp17", "erario": "sp16"})
    r = importa_col_lettore("x.pdf", chiama_json=finto)
    assert r["bs"]["sp16_debiti_breve"] == D("600") and r["bs"]["sp17_debiti_lungo"] == D("400")
    assert r["diagnostica"]["sbilancio"] == "0.00" and len(r["diagnostica"]["scadenze"]) == 2


def test_saldo_negativo_spostato_e_i_totali_stampati_seguono(monkeypatch):
    foglie = [_f("c", 1000, "L", "Cassa"), _f("n", -100, "L", "Crediti diversi"), _f("p", 900, "R", "Fornitori")]
    _finta_lettura(monkeypatch, foglie, [Ancora("attivo", D(900), "r1", ("c", "n")),
                                         Ancora("passivo", D(900), "r2", ("p",))])
    finto = Finto({"cassa": "sp09", "crediti": "sp06", "fornitori": "sp16"})
    r = importa_col_lettore("x.pdf", chiama_json=finto)
    assert r["stampati"] == {"totale_attivo": D(1000), "totale_passivo": D(1000)}
    assert r["bs"]["sp16_debiti_breve"] == D(1000)
    # attivo composto = cassa 1.000 (il credito negativo e' ora un debito): uguale al totale stampato corretto
    assert r["bs"]["sp09_disponibilita_liquide"] + r["bs"].get("sp06_crediti_breve", 0) == D(1000)
    assert r["diagnostica"]["blocchi"] == [] and all(D(v) == 0 for v in r["diagnostica"]["scarti"].values())


def test_scadenza_non_rompe_un_ancora_stampata_che_tornava(monkeypatch):
    # il documento stampa il totale dei debiti oltre (sp17) che contiene il mutuo: la classe del modello lo chiude, la
    # regola «senza prova a breve» lo romperebbe. Il totale stampato decide, e la scelta si dichiara.
    foglie = [_f("c", 1000, "L", "Cassa"), _f("m", 600, "R", "Mutuo banca"), _f("d", 400, "R", "Fornitori")]
    _finta_lettura(monkeypatch, foglie, [Ancora("sp17", D(600), "Debiti oltre", ("m",)),
                                         Ancora("sp16", D(400), "Debiti entro", ("d",))])
    finto = Finto({"cassa": "sp09", "mutuo": "sp17", "fornitori": "sp16"})
    r = importa_col_lettore("x.pdf", chiama_json=finto)
    assert r["bs"]["sp17_debiti_lungo"] == D("600") and r["bs"]["sp16_debiti_breve"] == D("400")
    assert r["diagnostica"]["blocchi"] == []
    assert any("ancora" in s and s.endswith(": m") for s in r["diagnostica"]["scadenze"])
    assert not any(s.startswith("debito a breve") and s.endswith(": m") for s in r["diagnostica"]["scadenze"])


# --- Review Focus della Fase 4 (Task 3) ---------------------------------------------------------------------------

def _abbreviato(etichetta_immobilizzazioni="II - Immobilizzazioni materiali"):
    righe = [("B) IMMOBILIZZAZIONI",), (etichetta_immobilizzazioni, "800,00"),
             ("C) ATTIVO CIRCOLANTE",), ("II - Crediti", "500,00"), ("IV - Disponibilita' liquide", "700,00"),
             ("TOTALE ATTIVO", "2.000,00"), ("STATO PATRIMONIALE PASSIVO",), ("A) PATRIMONIO NETTO",),
             ("I - Capitale", "950,00"), ("IX - Utile (perdita) dell'esercizio", "400,00"), ("D) DEBITI", "650,00"),
             ("TOTALE PASSIVO", "2.000,00"), ("CONTO ECONOMICO",), ("A) VALORE DELLA PRODUZIONE",),
             ("1) ricavi delle vendite e delle prestazioni", "2.950,00"), ("5) altri ricavi e proventi", "100,00"),
             ("B) COSTI DELLA PRODUZIONE",), ("7) per servizi", "2.650,00"),
             ("21) Utile (perdita) dell'esercizio", "400,00")]
    return [(50, 100, "STATO PATRIMONIALE ATTIVO"), _testata(373, 120, "31/12/2025")] + _righe(140, righe)


def test_legge_precedente_senza_importi_non_dal_modello(tmp_path):
    # RF1: la testata nomina due esercizi ma il precedente non ha importi letti (stampato in un'altra pagina, o non
    # letto): la corrente quadra e si adotta, il precedente resta assente, e il modello non e' mai chiamato
    voci = _schema_di_legge(prec=("",) * 12)
    r = importa_col_lettore(_pdf(tmp_path, voci), chiama_json=_mai)
    assert r["diagnostica"]["chiamate"] == 0 and r["diagnostica"]["blocchi"] == []
    assert r["prior_bs"] is None and r["prior_ce"] is None and r["prior_stato"] in ("assente", "scartato")
    esito = _esito("lettore", r["bs"], r["ce"], r["stampati"])
    assert esito["adottato"] and esito["esito"] == "ok"


def test_legge_abbreviato_dettaglio_in_altri(tmp_path):
    # RF3: l'abbreviato stampa «II - Crediti» senza sotto-voci; la classe e' la macro dal percorso stampato e il
    # dettaglio, che il documento non dice, va in «altri»: nemmeno un modello che lo inventerebbe viene chiesto
    finto = Finto({"crediti": "sp06a", "debiti": "sp16a", "immobilizzazioni": "sp03a"})
    r = importa_col_lettore(_pdf(tmp_path, _abbreviato()), chiama_json=finto)
    assert finto.chiamate == 0 and r["diagnostica"]["classi_per_fonte"] == {"legale": 9}
    bs = r["bs"]
    assert bs["sp06_crediti_breve"] == D("500.00") and bs["sp06g_crediti_altri_breve"] == D("500.00")
    assert not bs.get("sp06a_crediti_clienti_breve") and not bs.get("sp16a_debiti_banche_breve")
    assert bs["sp16g_altri_debiti_breve"] == D("650.00")
    assert _esito("lettore", bs, r["ce"], r["stampati"])["esito"] == "ok"


def test_legge_percorso_stampato_vince_sul_modello(tmp_path):
    # RF4: «B.II.2 Impianti e macchinario» stampa il percorso di legge; un modello che la manderebbe fra le
    # immateriali (sp02) non viene chiesto, e la voce va in sp03b come dice il percorso (`classifica._da_percorso`)
    finto = Finto({"impianti": "sp02"})
    r = importa_col_lettore(_pdf(tmp_path, _abbreviato("B.II.2 Impianti e macchinario")), chiama_json=finto)
    assert finto.chiamate == 0
    bs = r["bs"]
    assert bs["sp03_immob_materiali"] == D("800.00") and bs["sp03b_impianti_macchinari"] == D("800.00")
    assert not bs.get("sp02_immob_immateriali")
