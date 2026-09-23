"""Grafici del Business plan. matplotlib con API Figure (thread-safe, mai pyplot), PNG 7,2″ × h a 220 dpi."""
from __future__ import annotations

import io
import math
from decimal import Decimal
from typing import Optional, Sequence

import matplotlib

matplotlib.use("Agg")
from matplotlib import font_manager  # noqa: E402
from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.font_manager import FontProperties  # noqa: E402
from matplotlib.ticker import FuncFormatter, MaxNLocator  # noqa: E402

from . import theme  # noqa: E402
from .fmt import chart_num  # noqa: E402

DPI = 220
WIDTH_IN = 7.2
HEIGHTS = {"ricavi_margine": 3.1, "risultati": 2.8, "pareggio": 3.2, "sicurezza": 2.4,
           "flussi": 3.1, "debito": 2.9, "dscr_pfn": 2.7, "circolante": 2.8}
TICK, LEGEND, LABEL, SMALL = 9.3, 9.3, 8.9, 8.1
for _f in ("Lato-Regular.ttf", "Lato-Bold.ttf"):
    font_manager.fontManager.addfont(str(theme.FONT_DIR / _f))
FAMILY = "Lato"

Values = Sequence[Optional[Decimal]]


def _k(vals: Values) -> list:
    """Euro → migliaia di euro in float; None → nan (barra non disegnata)."""
    return [math.nan if v is None else float(v) / 1000 for v in vals]


def _f(vals: Values) -> list:
    return [math.nan if v is None else float(v) for v in vals]


def _finite(*series) -> list:
    return [x for s in series for x in s if not math.isnan(x)]


def _fig(key: str, ncols: int = 1):
    fig = Figure(figsize=(WIDTH_IN, HEIGHTS[key]), dpi=DPI)
    FigureCanvasAgg(fig)
    axes = fig.subplots(1, ncols)
    for ax in (axes if ncols > 1 else [axes]):
        _style(ax)
    return fig, axes


def _style(ax) -> None:
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(theme.GREY)
    ax.grid(True, color=theme.GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(colors=theme.GREY, length=4)  # `colors` imposta anche le etichette: si sovrascrivono dopo
    ax.tick_params(labelcolor=theme.AXIS, labelsize=TICK, labelfontfamily=FAMILY)


def _legend(ax, handles, labels, **kw) -> None:
    ax.legend(handles, labels, frameon=False, prop=FontProperties(family=FAMILY, size=LEGEND), **kw)


def _text(ax, x, y, s, **kw) -> None:
    ax.text(x, y, s, fontfamily=FAMILY, **kw)


def _thousands(ax) -> None:
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: chart_num(v)))
    ax.yaxis.set_major_locator(MaxNLocator(nbins=6, steps=[1, 2, 2.5, 5, 10]))


def _ylabel(ax, text: str) -> None:
    ax.set_ylabel(text, fontfamily=FAMILY, fontsize=TICK, color=theme.AXIS)


def _limits(ax, values: list, top_room: float = 1.2, bottom_room: float = 1.25) -> None:
    lo = min([0.0] + values)
    hi = max([0.0] + values)
    span = (hi - lo) or 1.0
    ax.set_ylim(lo * bottom_room - (0.04 * span if lo < 0 else 0), hi * top_room + 0.02 * span)


def _png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=DPI, transparent=True, metadata={"Software": None})
    return buf.getvalue()


def _xticks(ax, labels) -> None:
    ax.set_xticks(list(range(len(labels))), labels)


def ricavi_margine(labels, ricavi: Values, margine: Values) -> bytes:
    fig, ax = _fig("ricavi_margine")
    fig.subplots_adjust(left=0.075, right=0.93, top=0.96, bottom=0.12)
    x = list(range(len(labels)))
    k = _k(ricavi)
    bars = ax.bar(x, k, width=0.55, color=theme.NAVY, label="Ricavi delle vendite (€ migliaia)", zorder=2)
    _limits(ax, _finite(k), top_room=1.2)
    _thousands(ax)
    _xticks(ax, labels)
    top = ax.get_ylim()[1]
    for b, v in zip(bars, k):
        if math.isnan(v):
            continue
        inside = v > 0.12 * top
        _text(ax, b.get_x() + b.get_width() / 2, v - 0.02 * top if inside else v + 0.01 * top, chart_num(v),
              ha="center", va="top" if inside else "bottom", color="white" if inside else theme.NAVY,
              fontweight="bold", fontsize=LABEL)
    ax2 = ax.twinx()
    ax2.spines["top"].set_visible(False)
    ax2.spines["left"].set_visible(False)
    ax2.spines["right"].set_color(theme.GREY)
    ax2.tick_params(colors=theme.GREY, length=4)
    ax2.tick_params(labelcolor=theme.AXIS, labelsize=TICK, labelfontfamily=FAMILY)
    m = _f(margine)
    line, = ax2.plot(x, m, color=theme.ORANGE, linewidth=2.2, marker="o", markersize=6, zorder=3)
    fm = _finite(m)
    ax2.set_ylim(min([0.0] + fm) * 1.5, max([1.0] + fm) * 1.5)
    ax2.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{chart_num(v)}%"))
    span2 = ax2.get_ylim()[1] - ax2.get_ylim()[0]
    for xi, v in zip(x, m):
        if not math.isnan(v):
            _text(ax2, xi, v + 0.045 * span2, f"{chart_num(v, 2)}%", ha="center", va="bottom",
                  color=theme.ORANGE_DARK, fontweight="bold", fontsize=LABEL)
    _legend(ax, [bars, line], ["Ricavi delle vendite (€ migliaia)", "EBITDA margin %"], loc="upper left",
            ncol=2, handlelength=2.2, columnspacing=2.2, bbox_to_anchor=(0.0, 1.0))
    return _png(fig)


def _grouped(ax, labels, series, width) -> list:
    """series: [(valori_k, colore, etichetta)] → barre raggruppate con etichetta sopra/sotto."""
    x = list(range(len(labels)))
    n = len(series)
    handles = []
    allv = _finite(*[s[0] for s in series])
    span = (max([0.0] + allv) - min([0.0] + allv)) or 1.0
    for j, (vals, color, label) in enumerate(series):
        off = (j - (n - 1) / 2) * width
        h = ax.bar([i + off for i in x], vals, width, color=color, label=label, zorder=2)
        handles.append(h)
        for i, v in enumerate(vals):
            if math.isnan(v) or round(v) == 0:
                continue
            _text(ax, i + off, v + (0.01 * span if v > 0 else -0.01 * span), chart_num(v), ha="center",
                  va="bottom" if v > 0 else "top", color="black", fontsize=SMALL)
    return handles


def risultati(labels, ebitda: Values, ebit: Values, utile: Values) -> bytes:
    fig, ax = _fig("risultati")
    fig.subplots_adjust(left=0.10, right=0.985, top=0.96, bottom=0.12)
    series = [(_k(ebitda), theme.NAVY, "EBITDA"), (_k(ebit), theme.TEAL, "EBIT"), (_k(utile), theme.ORANGE, "Utile netto")]
    handles = _grouped(ax, labels, series, 0.26)
    _limits(ax, _finite(*[s[0] for s in series]), top_room=1.25)
    ax.axhline(0, color=theme.AXIS, linewidth=1.2, zorder=3)
    _thousands(ax)
    _ylabel(ax, "€ migliaia")
    _xticks(ax, labels)
    _legend(ax, handles, [s[2] for s in series], loc="upper left", ncol=3, columnspacing=2.2)
    return _png(fig)


def pareggio(labels, ricavi: Values, variabili: Values, fissi: Values, bep: Values) -> bytes:
    fig, ax = _fig("pareggio")
    fig.subplots_adjust(left=0.10, right=0.985, top=0.96, bottom=0.11)
    x = list(range(len(labels)))
    w = 0.32
    fk, vk, rk, bk = _k(fissi), _k(variabili), _k(ricavi), _k(bep)
    xl = [i - w / 2 - 0.01 for i in x]
    xr = [i + w / 2 + 0.01 for i in x]
    h_f = ax.bar(xl, fk, w, color=theme.NAVY, zorder=2)
    h_v = ax.bar(xl, vk, w, bottom=[0 if math.isnan(a) else a for a in fk], color=theme.LIGHTBLUE, zorder=2)
    h_r = ax.bar(xr, rk, w, color=theme.TEAL, zorder=2)
    h_b = ax.scatter(xr, bk, marker="D", s=60, color=theme.RED, zorder=4)
    for i in x:
        if not math.isnan(fk[i]):
            _text(ax, xl[i], fk[i] / 2, chart_num(fk[i]), ha="center", va="center", color="white", fontsize=8.5)
        if not (math.isnan(fk[i]) or math.isnan(vk[i])):
            _text(ax, xl[i], fk[i] + vk[i] / 2, chart_num(vk[i]), ha="center", va="center", color=theme.NAVY,
                  fontsize=8.5)
        if not math.isnan(rk[i]):
            _text(ax, xr[i], rk[i] / 2, chart_num(rk[i]), ha="center", va="center", color="white",
                  fontweight="bold", fontsize=8.5)
        if not math.isnan(bk[i]):
            _text(ax, xr[i] + 0.25, bk[i], chart_num(bk[i]), ha="left", va="center", color=theme.RED, fontsize=8.5)
    stacks = [a + b for a, b in zip(fk, vk)]
    _limits(ax, _finite(stacks, rk, bk), top_room=1.3)
    _thousands(ax)
    _ylabel(ax, "€ migliaia")
    _xticks(ax, labels)
    ax.set_xlim(-0.55, len(labels) - 0.25)
    _legend(ax, [h_b, h_f, h_v, h_r], ["Break even point", "Costi fissi", "Costi variabili", "Ricavi"],
            loc="upper left", ncol=4, columnspacing=2.2, bbox_to_anchor=(0.01, 1.0))
    return _png(fig)


def sicurezza(labels, margine: Values) -> bytes:
    fig, ax = _fig("sicurezza")
    fig.subplots_adjust(left=0.10, right=0.985, top=0.96, bottom=0.15)
    x = list(range(len(labels)))
    m = _f(margine)
    colors = [theme.RED if (not math.isnan(v) and v < 0) else theme.TEAL for v in m]
    ax.bar(x, m, width=0.5, color=colors, zorder=2)
    fm = _finite(m)
    lo, hi = min([0.0] + fm), max([0.0] + fm)
    span = (hi - lo) or 1.0
    ax.set_ylim(lo - 0.25 * span if lo < 0 else -0.08 * span, hi + 0.25 * span)
    for i, v in enumerate(m):
        if not math.isnan(v):
            _text(ax, i, v + (0.04 * span if v >= 0 else -0.04 * span), f"{chart_num(v, 2)}%", ha="center",
                  va="bottom" if v >= 0 else "top", color=colors[i], fontweight="bold", fontsize=LABEL)
    ax.axhline(0, color=theme.AXIS, linewidth=1.2, zorder=3)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{chart_num(v)}%"))
    _ylabel(ax, "Margine di sicurezza")
    _xticks(ax, labels)
    return _png(fig)


def flussi(labels, operativo: Values, investimenti: Values, finanziamento: Values, cassa: Values) -> bytes:
    fig, ax = _fig("flussi")
    fig.subplots_adjust(left=0.095, right=0.985, top=0.96, bottom=0.12)
    series = [(_k(operativo), theme.NAVY, "Flusso operativo"), (_k(investimenti), theme.ORANGE, "Flusso di investimento"),
              (_k(finanziamento), theme.GREY, "Flusso finanziario")]
    handles = _grouped(ax, labels, series, 0.26)
    ck = _k(cassa)
    line, = ax.plot(list(range(len(labels))), ck, color=theme.TEAL, linewidth=2.2, marker="o", markersize=6, zorder=4)
    allv = _finite(*[s[0] for s in series], ck)
    _limits(ax, allv, top_room=1.3)
    span = ax.get_ylim()[1] - ax.get_ylim()[0]
    for i, v in enumerate(ck):
        if i > 0 and not math.isnan(v):
            _text(ax, i + 0.05, v + 0.012 * span, chart_num(v), ha="left", va="bottom", color=theme.TEAL,
                  fontweight="bold", fontsize=LABEL)
    ax.axhline(0, color=theme.AXIS, linewidth=1.2, zorder=3)
    _thousands(ax)
    _ylabel(ax, "€ migliaia")
    _xticks(ax, labels)
    _legend(ax, [line] + handles, ["Cassa finale"] + [s[2] for s in series], loc="upper left", ncol=4,
            columnspacing=2.2, handlelength=2.2, bbox_to_anchor=(0.0, 1.0))
    return _png(fig)


def debito(labels, debiti_fin: Values, liquidita: Values, patrimonio: Values, pfn: Values) -> bytes:
    fig, ax = _fig("debito")
    fig.subplots_adjust(left=0.10, right=0.985, top=0.96, bottom=0.12)
    series = [(_k(debiti_fin), theme.GREY, "Debiti finanziari"), (_k(liquidita), theme.TEAL, "Disponibilità liquide"),
              (_k(patrimonio), theme.ORANGE, "Patrimonio netto")]
    x = list(range(len(labels)))
    handles = []
    for j, (vals, color, label) in enumerate(series):
        handles.append(ax.bar([i + (j - 1) * 0.26 for i in x], vals, 0.26, color=color, zorder=2))
    pk = _k(pfn)
    line, = ax.plot(x, pk, color=theme.NAVY, linewidth=2.2, marker="o", markersize=6, zorder=4)
    _limits(ax, _finite(*[s[0] for s in series], pk), top_room=1.3)
    span = ax.get_ylim()[1] - ax.get_ylim()[0]
    for i, v in enumerate(pk):
        if not math.isnan(v):
            _text(ax, i + 0.12, v + 0.015 * span, chart_num(v), ha="left", va="bottom", color=theme.NAVY,
                  fontweight="bold", fontsize=LABEL)
    ax.axhline(0, color=theme.AXIS, linewidth=1.0, zorder=3)
    _thousands(ax)
    _ylabel(ax, "€ migliaia")
    _xticks(ax, labels)
    _legend(ax, [line, handles[0], handles[1], handles[2]],
            ["PFN", "Debiti finanziari", "Disponibilità liquide", "Patrimonio netto"], loc="upper right", ncol=2)
    return _png(fig)


def _panel_title(ax, text: str) -> None:
    ax.set_title(text, loc="left", fontfamily=FAMILY, fontsize=10.5, color=theme.NAVY)


def dscr_pfn(labels, dscr: Values, pfn_ebitda: Values) -> bytes:
    fig, (a1, a2) = _fig("dscr_pfn", ncols=2)
    fig.subplots_adjust(left=0.06, right=0.99, top=0.88, bottom=0.12, wspace=0.12)
    for ax, vals, color, title in ((a1, _f(dscr), theme.NAVY, "DSCR (proxy)"),
                                   (a2, _f(pfn_ebitda), theme.TEAL, "PFN / EBITDA")):
        x = list(range(len(labels)))
        ax.bar(x, vals, 0.55, color=color, zorder=2)
        fv = _finite(vals)
        _limits(ax, fv, top_room=1.18)
        span = ax.get_ylim()[1] - ax.get_ylim()[0]
        for i, v in enumerate(vals):
            if not math.isnan(v):
                _text(ax, i, v + (0.01 * span if v >= 0 else -0.01 * span), f"{chart_num(v, 2)}×",
                      ha="center", va="bottom" if v >= 0 else "top", color="black", fontweight="bold", fontsize=LABEL)
        _xticks(ax, labels)
        ax.tick_params(labelsize=SMALL)
        _panel_title(ax, title)
    a1.axhline(1.0, color=theme.RED, linestyle="--", linewidth=1.2, zorder=3)
    _text(a1, -0.45, 1.05, "soglia 1,0×", color=theme.RED, fontsize=7, va="bottom")
    return _png(fig)


def circolante(labels, dso: Values, dio: Values, dpo: Values, cc_comm: Values) -> bytes:
    fig, (a1, a2) = _fig("circolante", ncols=2)
    fig.subplots_adjust(left=0.06, right=0.99, top=0.88, bottom=0.10, wspace=0.22)
    x = list(range(len(labels)))
    lines = []
    for vals, color, label, below in ((_f(dso), theme.NAVY, "DSO – giorni credito", True),
                                      (_f(dio), theme.ORANGE, "DIO – giorni magazzino", False),
                                      (_f(dpo), theme.TEAL, "DPO – giorni debito", False)):
        ln, = a1.plot(x, vals, color=color, linewidth=2.2, marker="o", markersize=6, zorder=3)
        lines.append((ln, label))
        for i, v in enumerate(vals):
            if not math.isnan(v):
                _text(a1, i, v + (-4 if below else 3), chart_num(v), ha="center", va="top" if below else "bottom",
                      color=color, fontsize=SMALL)
    alld = _finite(_f(dso), _f(dio), _f(dpo))
    a1.set_ylim(min([0.0] + alld), max([10.0] + alld) * 1.2)
    a1.yaxis.set_major_locator(MaxNLocator(nbins=6, steps=[1, 2.5, 5, 10]))
    _xticks(a1, labels)
    a1.tick_params(labelsize=SMALL)
    _panel_title(a1, "Giorni del circolante")
    # «best» evita le linee: con i giorni di AMBIENTA «center right» copriva il DSO e la sua etichetta.
    a1.legend([h for h, _ in lines], [lab for _, lab in lines], loc="best", frameon=False,
              prop=FontProperties(family=FAMILY, size=SMALL))
    ck = _k(cc_comm)
    a2.bar(x, ck, 0.55, color=theme.NAVY, zorder=2)
    _limits(a2, _finite(ck), top_room=1.15)
    span = a2.get_ylim()[1] - a2.get_ylim()[0]
    for i, v in enumerate(ck):
        if not math.isnan(v):
            _text(a2, i, v + (0.01 * span if v >= 0 else -0.01 * span), chart_num(v), ha="center",
                  va="bottom" if v >= 0 else "top", color="black", fontweight="bold", fontsize=LABEL)
    _thousands(a2)
    _xticks(a2, labels)
    a2.tick_params(labelsize=SMALL)
    _panel_title(a2, "Capitale circolante commerciale (€ k)")
    return _png(fig)
