"""Righe dello schema di legge generico: un importo stampato fuori asse si riattacca alla
propria didascalia.

Contesto (2026-10-19, Napolitano Solution, CEE ordinario a colonna unica stampato da
wkhtmltopdf): alcuni importi stanno 3-7 punti sotto o sopra la loro didascalia ("Totale
crediti verso imprese collegate" a 750,4 e il suo "0" a 757,0; "2) impianti e macchinario" e
"-141"). Il raggruppamento a 3 punti ne faceva righe orfane, una diventava un "Totale crediti"
fuori posto e l'albero di B.III scivolava di un livello: documento rifiutato
("didascalia_non_collocabile"), letto dal modello e importato squadrato di 93.767.

Parole sintetiche nella forma di ``fitz.Page.get_text("words")``: (x0, y0, x1, y1, testo).

Run: python -m pytest tests/test_schema_legge_generico_righe.py -v
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from importers.schema_legge_generico import _riattacca_importi  # noqa: E402


def _w(x, y, testo, h=13.8):
    return (x, y, x + 10, y + h, testo)


def _testi(gruppi):
    return [[w[4] for w in sorted(g, key=lambda w: w[0])] for g in gruppi]


def test_importo_sotto_la_didascalia_si_riattacca():
    gruppi = [
        [_w(10, 734.2, "esigibili"), _w(580, 734.2, "0")],
        [_w(10, 750.4, "Totale"), _w(41, 750.4, "crediti")],
        [_w(580, 757.0, "0")],
        [_w(10, 779.8, "c)"), _w(22, 779.8, "verso")],
    ]
    assert _testi(_riattacca_importi(gruppi)) == [
        ["esigibili", "0"], ["Totale", "crediti", "0"], ["c)", "verso"]]


def test_importo_sopra_la_didascalia_si_riattacca_alla_riga_dopo():
    gruppi = [
        [_w(580, 269.0, "0")],
        [_w(10, 273.0, "1)"), _w(22, 273.0, "partecipazioni")],
    ]
    assert _testi(_riattacca_importi(gruppi)) == [["1)", "partecipazioni", "0"]]


def test_importo_lontano_o_vicino_a_una_riga_con_importo_resta_solo():
    """Un totale senza didascalia vero resta riga a se': lontano dalla riga sopra, o vicino
    solo a righe che hanno gia' il proprio importo."""
    lontano = [[_w(10, 700.0, "Totale")], [_w(580, 720.0, "100")]]
    assert _testi(_riattacca_importi(lontano)) == [["Totale"], ["100"]]
    occupata = [[_w(10, 700.0, "4)"), _w(580, 700.0, "50")], [_w(580, 704.0, "100")]]
    assert _testi(_riattacca_importi(occupata)) == [["4)", "50"], ["100"]]
