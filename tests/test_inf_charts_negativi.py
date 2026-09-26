"""Rilievo 3 della revisione finale: su serie negative (D2M) o fuori scala (AIC 12M, margine 80.000%) nessun testo
esce dalla figura, nessun testo ne copre un altro, la legenda non sta sopra le barre. Serie positive di AMBIENTA come
controllo: il rimedio non deve spostare il caso buono."""
from decimal import Decimal as D

import pytest

from app.renderers.infrannuale import charts

L3 = ["2025 C", "3M 2026", "2026 F"]


@pytest.fixture
def figura(monkeypatch):
    prese = []
    orig = charts._png
    monkeypatch.setattr(charts, "_png", lambda fig: (prese.append(fig), orig(fig))[1])
    return prese


def _testi(fig):
    """I testi davvero disegnati: etichette di tick nella vista (matplotlib ne tiene di nascoste fuori), testi
    liberi, titoli, etichette d'asse e legende."""
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    arts = list(fig.texts)
    for ax in fig.axes:
        for axis in (ax.xaxis, ax.yaxis):
            for t in axis._update_ticks():
                arts += [t.label1, t.label2]
            arts.append(axis.label)
        arts += list(ax.texts) + [ax.title, ax._left_title, ax._right_title]
        if ax.get_legend():
            arts += list(ax.get_legend().get_texts())
    out, visti = [], set()
    for a in arts:
        if a.get_visible() and a.get_text().strip():
            b = a.get_window_extent(r)
            chiave = (a.get_text(), round(b.x0), round(b.y0))  # l'asse gemello ripete le stesse etichette x
            if chiave not in visti:
                visti.add(chiave)
                out.append((a.get_text(), b))
    return out


def _controlla(fig):
    W, H = fig.bbox.width, fig.bbox.height
    testi = _testi(fig)
    for s, b in testi:
        assert b.x0 >= -1 and b.y0 >= -1 and b.x1 <= W + 1 and b.y1 <= H + 1, f"«{s}» esce dalla figura"
    for i, (s1, b1) in enumerate(testi):
        for s2, b2 in testi[i + 1:]:
            ov = min(b1.x1, b2.x1) - max(b1.x0, b2.x0), min(b1.y1, b2.y1) - max(b1.y0, b2.y0)
            assert not (ov[0] > 1 and ov[1] > 1), f"«{s1}» copre «{s2}»"
    r = fig.canvas.get_renderer()
    for ax in fig.axes:
        leg = ax.get_legend()
        if leg is None:
            continue
        lb = leg.get_window_extent(r)
        for p in ax.patches:
            pb = p.get_window_extent(r)
            if pb.width > 1 and pb.height > 1 and p.get_facecolor()[3] > 0:
                ov = min(lb.x1, pb.x1) - max(lb.x0, pb.x0), min(lb.y1, pb.y1) - max(lb.y0, pb.y0)
                assert not (ov[0] > 1 and ov[1] > 1), "la legenda copre una barra"


CASI = {
    "debito_d2m": lambda: charts.debito(L3, [D("-53.45"), D("-1.25"), D("-10.2")], [D("-1.12"), D("-0.45"), D("-1.25")]),
    "debito_pfn_nd": lambda: charts.debito(L3, [D("-7.11"), D("-53.451"), D("-19.938")], [None] * 3),
    "debito_ambienta": lambda: charts.debito(L3, [D("3.026"), D("2.98"), D("3.4")], [D("5.79"), D("4.1"), D("3.2")]),
    "risultati_d2m": lambda: charts.risultati(L3 + ["x"], [D(-289298), D(-120000), D(-300000), D(-50000)],
                                              [D(-310000), D(-130000), D(-340000), D(-60000)],
                                              [D(-330000), D(-150000), D(-360000), D(-70000)]),
    "risultati_ambienta": lambda: charts.risultati(L3 + ["x"], [D(410000), D(260000), D(520000), D(480000)],
                                                   [D(330000), D(220000), D(440000), D(400000)],
                                                   [D(210000), D(150000), D(300000), D(280000)]),
    "ricavi_aic_12m": lambda: charts.ricavi_periodi(["2024 C", "12M 2025"], [D(101), D(120)], [D(80395), D(1200)],
                                                    ["C", "6M"]),
    "ricavi_d2m": lambda: charts.ricavi_periodi(L3 + ["x"], [D(900000), D(200000), D(800000), D(850000)],
                                                [D(-32), D(-60), D(-60), D(-35)], ["C", "6M", "Ann", "F"]),
}


@pytest.mark.parametrize("caso", sorted(CASI))
def test_testi_dentro_e_separati(figura, caso):
    CASI[caso]()
    _controlla(figura[-1])
