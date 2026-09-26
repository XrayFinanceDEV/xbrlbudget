"""Grafici: misure del riferimento (1584 px di larghezza, altezza = decimi di pollice × 220), assenze, thread."""
import io
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal as D

from PIL import Image

from app.renderers.business_plan import charts

L = ["2026 F", "2027 P", "2028 P", "2029 P"]
R = [D("4109510"), D("4314986"), D("4573885"), D("4673885")]


def _size(png):
    return Image.open(io.BytesIO(png)).size


def test_misure_come_il_riferimento():
    assert _size(charts.ricavi_margine(L, R, [D("4.04"), D("4.36"), D("8.64"), D("8.61")])) == (1584, 682)
    assert _size(charts.sicurezza(L, [D("-4.31"), D("5.02"), D("14.3"), D("14.39")])) == (1584, 528)
    assert charts.HEIGHTS == {"ricavi_margine": 3.1, "risultati": 2.8, "pareggio": 3.2, "sicurezza": 2.4,
                              "flussi": 3.1, "debito": 2.9, "dscr_pfn": 2.7, "circolante": 2.8}


def test_sfondo_trasparente_e_png_deterministico():
    a = charts.flussi(L, [D("-225519"), D("399355"), D("262189"), D("406154")],
                      [D("61790"), D("-150000"), D("0"), D("0")], [D("134517"), D("96591"), D("-105000"), D("-105000")],
                      [D("55"), D("346000"), D("503190"), D("804344")])
    b = charts.flussi(L, [D("-225519"), D("399355"), D("262189"), D("406154")],
                      [D("61790"), D("-150000"), D("0"), D("0")], [D("134517"), D("96591"), D("-105000"), D("-105000")],
                      [D("55"), D("346000"), D("503190"), D("804344")])
    assert a == b
    assert Image.open(io.BytesIO(a)).mode == "RGBA"


def test_grafici_con_valori_assenti():
    none4 = [None] * 4
    for png in (charts.ricavi_margine(L, none4, none4), charts.risultati(L, none4, none4, none4),
                charts.pareggio(L, none4, none4, none4, none4), charts.sicurezza(L, none4),
                charts.flussi(L, none4, none4, none4, none4), charts.debito(L, none4, none4, none4, none4),
                charts.dscr_pfn(L, none4, none4), charts.circolante(L, none4, none4, none4, none4)):
        assert png.startswith(b"\x89PNG")


def test_sei_categorie_e_valori_negativi():
    L6 = ["2025 C"] + [f"{y} P" for y in range(2026, 2031)]
    neg = [D("-50000"), D("-20000"), D("10000"), D("30000"), D("60000"), D("90000")]
    assert _size(charts.risultati(L6, neg, neg, neg))[0] == 1584


def test_render_concorrente():
    def job(_):
        return charts.ricavi_margine(L, R, [D("4"), D("5"), D("6"), D("7")])
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(job, range(12)))
    assert len(set(results)) == 1
