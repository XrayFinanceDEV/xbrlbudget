import math, threading
from decimal import Decimal as D
from PIL import Image
import io
from app.renderers.infrannuale import charts

L3 = ["2025 C", "6M 2026", "2026 F"]


def _size(png):
    return Image.open(io.BytesIO(png)).size


def test_misure_come_il_riferimento():
    assert _size(charts.ricavi_periodi(["a", "b", "c", "d"], [D(1)] * 4, [D(1)] * 4, ["C", "6M", "Ann", "F"])) == (1584, 660)
    assert _size(charts.stato_patrimoniale(L3, *([[D(1)] * 3] * 4))) == (1584, 616)
    assert _size(charts.crisi(L3, [9, 7, 8], 14, ["D · Crisi", "C2 · Rischio grave", "D · Crisi"])) == (1584, 528)


def test_valori_assenti_e_negativi():
    charts.circolante(L3, [D(1), None, D(3)], [None] * 3, [D(-5), D(-6), None], [D(-1), D(2), None])
    charts.debito(L3, [None, D("2.9"), None], [None] * 3)
    charts.crisi(L3, [None, 7, 8], 14, ["A3 · Nessun rischio", "B1 · Rischio lieve", "D · Crisi"])


def test_render_concorrente():
    out = []
    ts = [threading.Thread(target=lambda: out.append(charts.crisi(L3, [9, 7, 8], 14, ["D · Crisi"] * 3))) for _ in range(6)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert len(set(out)) == 1
