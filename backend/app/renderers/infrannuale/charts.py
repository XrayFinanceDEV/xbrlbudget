"""I sei grafici del report infrannuale, misurati sul PDF del committente.

Stessa grammatica del Business plan (Lato, palette, assi despinati, 220 dpi, sfondo trasparente) e stesse primitive
di `business_plan.charts`, che qui si importano senza modificarle. Solo `Figure`, mai `pyplot`: FastAPI esegue la
rotta in un threadpool.
"""
from __future__ import annotations

import math
from typing import Optional, Sequence

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.font_manager import FontProperties
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter, MaxNLocator

from app.renderers.business_plan import theme
from app.renderers.business_plan.charts import (DPI, FAMILY, LABEL, SMALL, TICK, WIDTH_IN, _f, _finite, _grouped, _k,
                                                _legend, _limits, _panel_title, _png, _style, _text, _thousands,
                                                _xticks, _ylabel)
from app.renderers.business_plan.fmt import chart_num

HEIGHTS = {"ricavi_periodi": 3.0, "risultati": 2.6, "stato_patrimoniale": 2.8, "circolante": 2.7, "debito": 2.6,
           "crisi": 2.4}
CRISI_BG = "#e4e7ec"
Values = Sequence[Optional[object]]


def classe_colore(codice: Optional[str]) -> str:
    """Colore della classe di rischio per codice, come nel riferimento: A teal, B e C arancio, D rosso."""
    if not codice:
        return theme.GREY
    return {"A": theme.TEAL, "B": theme.ORANGE, "C": theme.ORANGE, "D": theme.RED}.get(codice[0], theme.GREY)


def _fig(key: str, ncols: int = 1):
    fig = Figure(figsize=(WIDTH_IN, HEIGHTS[key]), dpi=DPI)
    FigureCanvasAgg(fig)
    axes = fig.subplots(1, ncols)
    for ax in (axes if ncols > 1 else [axes]):
        _style(ax)
    return fig, axes


def _twin(ax):
    ax2 = ax.twinx()
    ax2.spines["top"].set_visible(False)
    ax2.spines["left"].set_visible(False)
    ax2.spines["right"].set_color(theme.GREY)
    ax2.tick_params(colors=theme.GREY, length=4)
    ax2.tick_params(labelcolor=theme.AXIS, labelsize=TICK, labelfontfamily=FAMILY)
    return ax2


def ricavi_periodi(labels, ricavi: Values, margine: Values, kinds: Sequence[str]) -> bytes:
    """Ricavi per periodo (C grigio, 6M azzurro tratteggiato, Ann. azzurro, F navy) e linea dell'EBITDA margin."""
    fig, ax = _fig("ricavi_periodi")
    fig.subplots_adjust(left=0.105, right=0.935, top=0.95, bottom=0.12)
    k = _k(ricavi)
    style = {"C": (theme.GREY, None, "white"), "6M": (theme.LIGHTBLUE, "//", theme.NAVY),
             "Ann": (theme.LIGHTBLUE, None, theme.NAVY), "F": (theme.NAVY, None, "white")}
    for i, (v, kind) in enumerate(zip(k, kinds)):
        if math.isnan(v):
            continue
        face, hatch, ink = style[kind]
        ax.bar(i, v, 0.55, color=face, hatch=hatch, edgecolor="white" if hatch else face, linewidth=0, zorder=2)
        _text(ax, i, v / 2, chart_num(v), ha="center", va="center", color=ink, fontweight="bold", fontsize=LABEL)
    lo, hi = min([0.0] + _finite(k)), max([0.0] + _finite(k))
    ax.set_ylim(lo * 1.25, (hi or 1.0) * 1.57)
    _thousands(ax)
    ax.yaxis.set_major_locator(MaxNLocator(nbins=7, steps=[1, 2, 2.5, 5, 10]))
    _xticks(ax, labels)
    _ylabel(ax, "Ricavi delle vendite (€ k)")
    ax2 = _twin(ax)
    m = _f(margine)
    ax2.plot(list(range(len(labels))), m, color=theme.ORANGE, linewidth=2.2, marker="o", markersize=6, zorder=3)
    fm = _finite(m)
    top = max(5.0, math.ceil(max(fm + [0.0]) * 1.12))
    ax2.set_ylim(min([0.0] + [x * 1.25 for x in fm]), top)
    ax2.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0f}%"))
    span = ax2.get_ylim()[1] - ax2.get_ylim()[0]
    for i, v in enumerate(m):
        if not math.isnan(v):
            _text(ax2, i, v + 0.035 * span, chart_num(v, 2) + "%", ha="center", va="bottom",
                  color=theme.ORANGE_DARK, fontweight="bold", fontsize=LABEL)
    _legend(ax, [Line2D([], [], color=theme.ORANGE, linewidth=2.2, marker="o", markersize=6)], ["EBITDA margin %"],
            loc="upper left", bbox_to_anchor=(0, 1.035))
    return _png(fig)


def risultati(labels, ebitda: Values, ebit: Values, utile: Values) -> bytes:
    fig, ax = _fig("risultati")
    fig.subplots_adjust(left=0.085, right=0.985, top=0.96, bottom=0.12)
    series = [(_k(ebitda), theme.NAVY, "EBITDA"), (_k(ebit), theme.TEAL, "EBIT"), (_k(utile), theme.ORANGE, "Utile netto")]
    handles = _grouped(ax, labels, series, 0.26)
    _limits(ax, _finite(*[s[0] for s in series]), top_room=1.2)
    _thousands(ax)
    _ylabel(ax, "€ migliaia")
    _xticks(ax, labels)
    _legend(ax, handles, [s[2] for s in series], loc="upper left", ncol=3, columnspacing=2.2)
    return _png(fig)


def _grouped_labels(ax, labels, series, width, size: float = LABEL) -> None:
    """Barre raggruppate con l'etichetta sopra (o sotto, se negativa) in nero, anche per i valori piccoli."""
    allk = _finite(*[s[0] for s in series])
    span = (max([0.0] + allk) - min([0.0] + allk)) or 1.0
    n = len(series)
    for j, (k, color, _) in enumerate(series):
        off = (j - (n - 1) / 2) * width
        for i, v in enumerate(k):
            if math.isnan(v):
                continue
            ax.bar(i + off, v, width, color=color, zorder=2)
            _text(ax, i + off, v + (0.005 * span if v >= 0 else -0.005 * span), chart_num(v), ha="center",
                  va="bottom" if v >= 0 else "top", color="black", fontsize=size)


def stato_patrimoniale(labels, attivo: Values, deb_fin: Values, deb_op: Values, pn: Values) -> bytes:
    fig, ax = _fig("stato_patrimoniale")
    fig.subplots_adjust(left=0.10, right=0.985, top=0.95, bottom=0.12)
    series = [(_k(attivo), theme.GREY, "Totale attivo"), (_k(deb_fin), theme.NAVY, "Debiti finanziari"),
              (_k(deb_op), theme.LIGHTBLUE, "Debiti operativi"), (_k(pn), theme.ORANGE, "Patrimonio netto")]
    _grouped_labels(ax, labels, series, 0.2)
    _limits(ax, _finite(*[s[0] for s in series]), top_room=1.16)
    _thousands(ax)
    _xticks(ax, labels)
    _ylabel(ax, "€ migliaia")
    _legend(ax, [Patch(color=c) for _, c, _ in series], [lab for _, _, lab in series], loc="upper left", ncol=4,
            handlelength=2.2, columnspacing=2.2)
    return _png(fig)


def circolante(labels, crediti: Values, rimanenze: Values, fornitori_neg: Values, cc_comm: Values) -> bytes:
    """Crediti verso clienti, rimanenze, debiti verso fornitori (negativi) e circolante commerciale."""
    fig, ax = _fig("circolante")
    fig.subplots_adjust(left=0.10, right=0.985, top=0.95, bottom=0.12)
    series = [(_k(crediti), theme.NAVY, "Crediti vs clienti"), (_k(rimanenze), theme.ORANGE, "Rimanenze"),
              (_k(fornitori_neg), theme.GREY, "Debiti vs fornitori"), (_k(cc_comm), theme.TEAL, "Circolante commerciale")]
    _grouped_labels(ax, labels, series, 0.2, size=SMALL)
    _limits(ax, _finite(*[s[0] for s in series]), top_room=1.4, bottom_room=1.25)
    ax.axhline(0, color=theme.AXIS, linewidth=1.2, zorder=3)
    _thousands(ax)
    _xticks(ax, labels)
    _ylabel(ax, "€ migliaia")
    ax.legend([Patch(color=c) for _, c, _ in series], [lab for _, _, lab in series], loc="upper left", ncol=4,
              handlelength=2.2, columnspacing=2.2, frameon=False, prop=FontProperties(family=FAMILY, size=SMALL))
    return _png(fig)


def debito(labels, dscr: Values, pfn_ebitda: Values) -> bytes:
    """Due pannelli: DSCR con la soglia 1,0× e PFN / EBITDA."""
    fig, (a1, a2) = _fig("debito", ncols=2)
    fig.subplots_adjust(left=0.04, right=0.985, top=0.88, bottom=0.12, wspace=0.12)
    for ax, vals, color, title in ((a1, _f(dscr), theme.NAVY, "DSCR"), (a2, _f(pfn_ebitda), theme.RED, "PFN / EBITDA")):
        ax.bar(list(range(len(labels))), vals, 0.55, color=color, zorder=2)
        _limits(ax, _finite(vals) + [1.2], top_room=1.18)
        ax.yaxis.set_major_locator(MaxNLocator(nbins=4, integer=True))
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


def crisi(labels, oltre: Sequence[Optional[int]], totale: int, classi: Sequence[str]) -> bytes:
    """Barre orizzontali: indicatori oltre soglia su `totale`, nel colore della classe, con la classe a lato."""
    fig, ax = _fig("crisi")
    fig.subplots_adjust(left=0.105, right=0.985, top=0.95, bottom=0.14)
    y = list(range(len(labels)))[::-1]
    for yi, n, cls in zip(y, oltre, classi):
        ax.barh(yi, totale, 0.55, color=CRISI_BG, zorder=1)
        color = classe_colore(cls)
        if n:
            ax.barh(yi, n, 0.55, color=color, zorder=2)
            _text(ax, n - 0.15, yi, f"{n} su {totale} oltre soglia", ha="right", va="center", color="white",
                  fontweight="bold", fontsize=TICK)
        _text(ax, totale + 0.2, yi, cls, ha="left", va="center", color=color, fontweight="bold", fontsize=TICK)
    ax.set_yticks(y, labels)
    ax.set_xlim(0, totale * 1.32)
    ax.set_xticks(list(range(0, totale + 1, 2)))
    ax.set_ylim(-0.55, len(labels) - 0.45)
    ax.grid(True, axis="x", color=theme.GRID, linewidth=0.8)
    ax.grid(False, axis="y")
    return _png(fig)
