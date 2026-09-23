"""Allegati A–E: prospetti completi e indicatori, colonne del report (base + piano)."""
from __future__ import annotations

from reportlab.platypus import PageBreak, Spacer

from . import fmt, layout
from .data import BusinessPlanData
from .sections_economia import headers

_KIND = {"section": "group", "group": "bold", "subtotal": "bold", "total": "hl", "detail": ""}


def _rows(annex_rows) -> list:
    out = []
    for r in annex_rows:
        indent = "&nbsp;" * 3 * max(r.level - 1, 0)
        kind = _KIND.get(r.kind, "")
        if all(v is None for v in r.values):
            kind = "group"  # intestazione di gruppo del prospetto («Rettifiche per elementi non monetari:»)
        cells = [] if kind == "group" else [fmt.eur(v) for v in r.values]
        out.append((indent + r.label, cells, kind))
    return out


def _zero_note(data: BusinessPlanData, key: str) -> list:
    labels = data.annex_zero_labels.get(key, ())
    if not labels:
        return []
    uniq = list(dict.fromkeys(labels))
    return [Spacer(0, 4), layout.note("Voci pari a zero in tutti gli anni: " + "; ".join(uniq).lower() + ".")]


def _statement(data, key, eyebrow, title, sub):
    rows = data.annex.get(key, ())
    s = layout.section_head(eyebrow, title, sub)
    return s + [layout.fin_table(headers(data), _rows(rows), value_size=8.2, pad=2.2, label_size=8)] + _zero_note(data, key)


def allegato_a(data: BusinessPlanData, pages: dict) -> list:
    return _statement(data, "income_statement", "ALLEGATO A", "Conto economico completo",
                      "Valori in euro · schema civilistico · voci a zero in tutti gli anni raggruppate in nota.")


def allegato_b(data: BusinessPlanData, pages: dict) -> list:
    rows = list(data.annex.get("balance_sheet", ()))
    split = next((i for i, r in enumerate(rows) if r.label.upper().startswith("PASSIVO")), len(rows))
    s = layout.section_head("ALLEGATO B", "Stato patrimoniale completo",
                            "Valori in euro · saldi di fine esercizio · voci a zero in tutti gli anni raggruppate.")
    s += [layout.fin_table(headers(data), _rows(rows[:split]), value_size=8.2, pad=2.2, label_size=8)]
    if split < len(rows):
        s += [PageBreak()] + layout.section_head("ALLEGATO B", "Stato patrimoniale completo (segue)",
                                                 "Passivo e patrimonio netto · valori in euro.")
        s += [layout.fin_table(headers(data), _rows(rows[split:]), value_size=8.2, pad=2.2, label_size=8)]
    return s + _zero_note(data, "balance_sheet")


def allegato_c(data: BusinessPlanData, pages: dict) -> list:
    return _statement(data, "cashflow", "ALLEGATO C", "Rendiconto finanziario completo — metodo indiretto",
                      "Valori in euro.")


def allegato_d(data: BusinessPlanData, pages: dict) -> list:
    sub = (f"R = progressivo rettificato {data.partial_label[:-2]}."
           if data.partial_label and data.partial_label in data.indicators_practice_headers
           else "Indicatori della pratica.")
    s = layout.section_head("ALLEGATO D", "Indicatori di sintesi", sub)
    rows = [(r.label, [fmt.value(v, r.unit) for v in r.values], "") for r in data.indicators_practice]
    return s + [layout.fin_table(list(data.indicators_practice_headers), rows, first="Indicatore")]


def allegato_e(data: BusinessPlanData, pages: dict) -> list:
    s = layout.section_head("ALLEGATO E", "Indici analitici",
                            "Quadro completo degli indici. ROE, ROI, ROS ed EBITDA margin sono nell'Allegato D.")
    rows = [(r.label, [fmt.value(v, r.unit) for v in r.values], "") for r in data.indicators_analytical]
    return s + [layout.fin_table(headers(data), rows, first="Indicatore"), Spacer(0, 5),
                layout.note("Lo Z-Score di Altman, il rating FGPMI e l'EMScore sono disponibili per ogni anno di piano "
                            "nel modello previsionale e non sono riportati in questo prospetto.")]
