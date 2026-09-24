"""Rilievi del banco visivo su AMBIENTA (13 pagine affiancate al riferimento): ogni test fissa una differenza vista."""
import fitz
import pytest

from app.renderers.infrannuale.document import render_infrannuale
from tests.test_inf_data import _data, db  # noqa: F401  (fixture condivisa)


@pytest.fixture(scope="module")
def pagine(db):  # noqa: F811
    pdf = fitz.open(stream=render_infrannuale(_data(db, 17)), filetype="pdf")
    return [p.get_text() for p in pdf], pdf


def test_arrotondamenti_come_la_tabella(pagine):
    t, _ = pagine
    assert "833.386" in t[1] and "833.386" in t[6]   # 1.198.959 + 287.312 − 652.885, non 833.385
    # Le variazioni restano ai centesimi come nel riferimento (1.224,51%): il suo 776,87% sul forecast nasce da
    # un 11.751 del committente contro il nostro 11.750, una differenza di dato e non di calcolo.
    assert "1.224,51%" in t[3]


def test_punti_chiave_in_grassetto(pagine):
    _, pdf = pagine
    spans = [s for b in pdf[1].get_text("dict")["blocks"] for l in b.get("lines", []) for s in l["spans"]]
    lead = next(s for s in spans if s["text"].startswith("Ricavi in crescita"))
    assert "Bold" in lead["font"]


def test_tile_e_etichette_del_riferimento(pagine):
    t, _ = pagine
    assert "da € 29.267 nel 2025 C" in t[6]
    assert "Debiti verso altri finanziatori (oltre 12 mesi)" in t[7]


def test_allegato_a_come_il_riferimento(pagine):
    t, _ = pagine
    a = " ".join(t[10].split())  # a capo e rientri (spazi non separabili) diventano un solo spazio
    for s in ("2) Variazioni rimanenze prodotti in corso, semilavorati e finiti",
              "10) Ammortamenti e svalutazioni 76.057", "a) Amm.to immobilizzazioni immateriali",
              "D) RETTIFICHE DI VALORE DI ATTIVITÀ FINANZIARIE", "E) PROVENTI E ONERI STRAORDINARI",
              "EBIT (risultato operativo)", "23) Utile (perdita) dell'esercizio",
              "D) voci 18–19 ed E) voci 20–21 pari a zero"):
        assert s in a, s
    assert "Totale ammortamenti e svalutazioni" not in a
    assert "n.d. n.d. n.d. n.d. e) Altri" in a and "n.d. 12)" not in a  # solo la riga senza dati, mai sulle variazioni


def test_allegato_b_come_il_riferimento(pagine):
    t, _ = pagine
    attivo, passivo = t[11], t[12]
    for s in ("A) Crediti verso soci per versamenti ancora dovuti", "B) Totale immobilizzazioni",
              "I – Rimanenze (materie prime)", "III – Attività finanziarie non immobilizzate",
              "C) Totale attivo circolante"):
        assert s in attivo, s
    for s in ("Utili/perdite portati a nuovo", "B) Fondi per rischi e oneri", "Obbligazioni",
              "Debiti verso fornitori (entro 12 mesi)", "Debiti verso altri finanziatori (oltre 12 mesi)",
              "D) Totale debiti", "Differenza (attivo − passivo)",
              "Voci pari a zero in tutti i periodi: crediti immobilizzati, derivati attivi; rimanenze diverse dalle "
              "materie prime; crediti verso controllate, collegate e controllanti; imposte anticipate; sovrapprezzo, "
              "rivalutazione, riserve statutarie, copertura flussi, azioni proprie; fondi di quiescenza, imposte, "
              "derivati passivi e altri fondi."):
        assert s in passivo.replace("\n", " ") if " " in s else s in passivo, s
    assert "B) IMMOBILIZZAZIONI" not in attivo and "D) DEBITI" not in passivo


@pytest.mark.parametrize("scenario", (3, 5, 17, 23))
def test_allegato_a_sta_in_una_pagina(db, scenario):  # noqa: F811
    """Rilievo 4 della revisione finale: con dettaglio in D o E (AIC 3 e 5) imposte e utile finivano da soli sulla
    pagina dopo, staccati dalla loro tabella."""
    try:
        d = _data(db, scenario)
    except ValueError as e:
        pytest.skip(f"scenario {scenario} incompleto nel DB locale: {e}")
    testo = [p.get_text() for p in fitz.open(stream=render_infrannuale(d), filetype="pdf")]
    a = next(i for i, t in enumerate(testo) if "ALLEGATO A" in t)
    b = next(i for i, t in enumerate(testo) if "ALLEGATO B" in t)
    assert b == a + 1, f"Allegato A su {b - a} pagine"
