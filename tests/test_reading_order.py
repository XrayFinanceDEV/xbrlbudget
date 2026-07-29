"""Il testo inviato all'LLM deve seguire l'ordine di LETTURA, non il content-stream.

`page.get_text()` restituisce il testo nell'ordine in cui il generatore lo ha
scritto nello stream, che NON e' necessariamente l'ordine visivo. Su un bilancio
comparativo scritto dal basso verso l'alto le etichette si legano ai numeri della
colonna sbagliata: l'anno precedente viene importato come anno corrente
(«Bilancio riclassificato / Fascicolo»: colonna 2024 letta come 2025) e le voci
di dettaglio finiscono sotto la voce di legge sbagliata.

Il rilevamento e' deterministico e geometrico: si ordina per coordinate SOLO
quando lo stream e' dimostrabilmente fuori ordine, cosi' i PDF ben formati
continuano a ricevere il testo identico a prima (zero regressioni).
"""
import os
import sys

import fitz
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from importers.pdf_extractor_llm import (  # noqa: E402
    _stream_order_is_scrambled,
    reading_order_text,
)

# Righe di un conto economico comparativo: (etichetta, importo 2025, importo 2024)
ROWS = [
    ("15) proventi da partecipazioni", "0", "0"),
    ("17) interessi e altri oneri finanziari", "", ""),
    ("altri", "38.629", "27.777"),
    ("Totale interessi e altri oneri finanziari", "38.629", "27.777"),
    ("17-bis) utili e perdite su cambi", "0", "0"),
    ("Totale proventi e oneri finanziari (C)", "-38.626", "-27.777"),
    ("D) RETTIFICHE DI VALORE DI ATTIVITA' FINANZIARIE:", "", ""),
    ("18) Rivalutazioni:", "", ""),
    ("Risultato prima delle imposte", "-120.048", "33.248"),
    ("Imposte correnti", "7.947", "15.943"),
    ("21) UTILE (PERDITA) D'ESERCIZIO", "-127.995", "17.305"),
]


def _write_pdf(path: str, bottom_up: bool) -> str:
    """Stessa pagina visiva, scritta nello stream in ordine normale o invertito."""
    doc = fitz.open()
    page = doc.new_page()
    order = list(enumerate(ROWS))
    if bottom_up:
        order.reverse()  # il generatore disegna l'ultima riga per prima
    for index, (label, current, prior) in order:
        y = 100 + index * 20
        page.insert_text((40, y), label, fontsize=9)
        if current:
            page.insert_text((350, y), current, fontsize=9)
        if prior:
            page.insert_text((460, y), prior, fontsize=9)
    doc.save(path)
    doc.close()
    return path


@pytest.fixture()
def normal_pdf(tmp_path):
    return _write_pdf(str(tmp_path / "normale.pdf"), bottom_up=False)


@pytest.fixture()
def scrambled_pdf(tmp_path):
    return _write_pdf(str(tmp_path / "invertito.pdf"), bottom_up=True)


def _page(path: str) -> fitz.Page:
    return fitz.open(path)[0]


def test_stream_ordinato_non_e_considerato_scomposto(normal_pdf):
    assert _stream_order_is_scrambled(_page(normal_pdf)) is False


def test_stream_invertito_e_riconosciuto_come_scomposto(scrambled_pdf):
    assert _stream_order_is_scrambled(_page(scrambled_pdf)) is True


def test_pdf_ben_formato_riceve_il_testo_invariato(normal_pdf):
    """Zero regressioni: se lo stream e' gia' in ordine, il testo non cambia."""
    page = _page(normal_pdf)
    assert reading_order_text(page) == page.get_text()


def test_pdf_scomposto_viene_riletto_in_ordine_di_lettura(scrambled_pdf):
    page = _page(scrambled_pdf)
    lines = [line for line in reading_order_text(page).splitlines() if line.strip()]
    labels = [label for label, _c, _p in ROWS]
    positions = [
        next(i for i, line in enumerate(lines) if label[:18] in line)
        for label in labels
    ]
    assert positions == sorted(positions), (
        "le righe devono uscire nell'ordine stampato, non in quello dello stream"
    )


def test_importo_resta_legato_alla_propria_voce(scrambled_pdf):
    """Il difetto contabile concreto: 27.777 e' un ONERE finanziario (voce 17),
    non una rivalutazione (voce 18). Nell'ordine di stream invertito «18)
    Rivalutazioni:» precede «altri 27.777» e l'importo viene attribuito alla
    voce sbagliata, gonfiando l'utile CE di 27.777."""
    lines = [
        line for line in reading_order_text(_page(scrambled_pdf)).splitlines()
        if line.strip()
    ]
    oneri = next(i for i, line in enumerate(lines) if "17) interessi" in line)
    altri = next(i for i, line in enumerate(lines) if line.strip().startswith("altri"))
    rivalutazioni = next(i for i, line in enumerate(lines) if "18) Rivalutazioni" in line)
    assert oneri < altri < rivalutazioni
