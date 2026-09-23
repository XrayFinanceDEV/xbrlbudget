"""Allegati A–B: conto economico e stato patrimoniale completi, colonne del report (C, 6M, Ann., F)."""
from __future__ import annotations

from reportlab.platypus import PageBreak, Paragraph, Spacer, TableStyle

from app.renderers.business_plan import fmt, layout, theme
from app.renderers.business_plan.layout import ST, _ps

from .data import ANNUALIZZATO, INFRANNUALE, PROIEZIONE, STORICO, InfrannualeData

_KIND = {"section": "group", "group": "group", "subtotal": "bold", "total": "hl", "detail": ""}
_TITLE = _ps("at", theme.REGULAR, 15, 18, theme.INK)
_SUB = _ps("as", theme.REGULAR, 9.8, 12, theme.INK)


def _head(eyebrow: str, title: str, sub: str) -> list:
    return [Paragraph(eyebrow, ST["eyebrow"]), Spacer(0, 2), Paragraph(title, _TITLE), Spacer(0, 2),
            Paragraph(sub, _SUB), Spacer(0, 6)]


def _var(values: tuple, keys: list, col: str):
    if col not in keys:
        return None
    b, v = values[keys.index(STORICO)], values[keys.index(col)]
    if v is None or b is None or b == 0:
        return None
    return (v / b - 1) * 100


def _rows(rows, keys: list, var_col: str) -> list:
    out = []
    for r in rows:
        kind = _KIND.get(r.kind, "")
        if kind != "group" and all(v is None for v in r.values):
            kind = "group" if r.kind != "detail" else ""
        indent = "&nbsp;" * 3 * max(r.level - 1, 0)
        cells = [] if kind == "group" else [fmt.eur(v) for v in r.values] + [fmt.pct(_var(r.values, keys, var_col))]
        out.append((indent + r.label, cells, kind))
    return out


def _is_zero(r) -> bool:
    return all(v is not None and v == 0 for v in r.values)


def _table(d, headers, rows, *, compact: bool):
    t = layout.fin_table(headers, rows, first="Voce", value_size=9.8, label_size=7.6 if compact else 8.0,
                         pad=1.2 if compact else 3.55)
    t.setStyle(TableStyle([("TOPPADDING", (0, 0), (-1, 0), 4.0), ("BOTTOMPADDING", (0, 0), (-1, 0), 4.0)]))
    return t


def allegato_a(d: InfrannualeData, pages: dict) -> list:
    keys = [c.key for c in d.ce_cols]
    var_col = ANNUALIZZATO if d.has_annualized else PROIEZIONE
    # Le sezioni del prospetto interamente a zero (D, E) si tolgono e si nominano nella nota.
    rows, dropped, i = [], [], 0
    src = list(d.annex_ce)
    while i < len(src):
        r = src[i]
        if r.kind == "section":
            j = i + 1
            while j < len(src) and src[j].kind != "section" and src[j].level > 0:
                j += 1
            body = src[i + 1:j]
            if body and all(_is_zero(x) for x in body):
                dropped.append(r.label.split(")")[0] + ")")
                i = j
                continue
        rows.append(r)
        i += 1
    sub = "Valori in euro · schema civilistico"
    if dropped:
        sub += f" · sezioni {' ed '.join(dropped)} pari a zero"
    sub += " · n.d. = non disponibile."
    heads = [c.label for c in d.ce_cols] + [f"{'Ann.' if var_col == ANNUALIZZATO else 'F'} / C"]
    return _head("ALLEGATO A", "Conto economico completo", sub) + \
        [_table(d, heads, _rows(rows, keys, var_col), compact=True)]


def allegato_b(d: InfrannualeData, pages: dict) -> list:
    keys = [c.key for c in d.sp_cols]
    var_col = PROIEZIONE if d.has_forecast else INFRANNUALE
    heads = [c.label for c in d.sp_cols] + [f"{'F' if var_col == PROIEZIONE else '6M'} / C"]
    kept, zero = [], []
    for r in d.annex_sp:
        if r.kind == "detail" and _is_zero(r):
            zero.append(r.label.strip().lower())
        elif not r.label.upper().startswith("DIFFERENZA"):
            kept.append(r)
    split = next((i for i, r in enumerate(kept) if r.label.upper().startswith("PASSIVO")), len(kept))
    s = _head("ALLEGATO B", "Stato patrimoniale completo",
              "Valori in euro · saldi puntuali · voci a zero in tutti i periodi raggruppate in nota.")
    s += [_table(d, heads, _rows(kept[:split], keys, var_col), compact=False)]
    if split < len(kept):
        s += [PageBreak()] + _head("ALLEGATO B", "Stato patrimoniale completo (segue)",
                                   "Passivo e patrimonio netto · valori in euro.")
        s += [_table(d, heads, _rows(kept[split:], keys, var_col), compact=False)]
    if zero:
        s += [Spacer(0, 5), layout.note("Voci pari a zero in tutti i periodi: " + "; ".join(dict.fromkeys(zero)) + ".")]
    return s
