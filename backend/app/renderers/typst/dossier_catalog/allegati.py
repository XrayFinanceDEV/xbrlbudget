"""Gruppo ALLEGATI (v4 pagine 19-33): indice dei prospetti, A/B/C (prospetti
completi), D/E/F/G (registro rettifiche, matrice ipotesi, indicatori),
metodologia.

In questa fase (fondazione M2-02D) sono implementate le pagine indice
(v4 pagina 19) e A/B/C (prospetti completi, v4 pagine 20-27), con le colonne
del vincolo del proprietario: chiusura (o ultimo esercizio storico) + anni di
piano, mai più di 5 colonne di valore, nessuna colonna tecnica. D/E/F/G/
metodologia restano da fare: TODO per il prossimo agente del gruppo.
"""
from __future__ import annotations

from typing import Any

from app.schemas.final_report_v2 import FinalReportModelV2

from . import shared as s

GROUP = "allegati"
FAMILY = "Allegati"

# Righe per pagina di un allegato lungo: tarato sulla geometria reale del
# dossier (pagina A4, colonna etichetta + fino a 5 colonne di valore, testata
# ripetuta, nessuna colonna KPI) e validato compilando con Typst — vedi
# `docs/testing/M2-02D-catalogo.md`. Non è il numero della v4 dimostrativa
# (che usava un catalogo sintetico diverso), solo una dimensione simile.
APPENDIX_ROWS_PER_PART = 24

_LETTERS = {"income_statement": "A", "balance_sheet": "B", "cashflow": "C"}
_STATEMENT_ORDER = ("income_statement", "balance_sheet", "cashflow")


def _allegato_pages(report: FinalReportModelV2, statement_id: str) -> list[dict[str, Any]]:
    statement = s.statement_by_id(report, statement_id)
    periods = s.select_periods(statement.periods)
    letter = _LETTERS[statement_id]
    rows = s.appendix_table_rows(statement, periods)
    parts = s.chunk(rows, APPENDIX_ROWS_PER_PART)
    total = len(parts)
    columns = ["Voce", *[s.period_label(period) for period in periods]]
    pages: list[dict[str, Any]] = []
    for index, part_rows in enumerate(parts, start=1):
        page_id = f"allegato-{letter}-{index}"
        heading = f"{letter} · {statement.title}"
        table_title = f"{heading} · parte {index} di {total}" if total > 1 else heading
        table = s.table(page_id, table_title, columns, part_rows)
        subtitle = (f"Allegato {letter} · parte {index} di {total} · valori in euro."
                    if total > 1 else f"Allegato {letter} · valori in euro.")
        pages.append({"id": page_id, "title": f"{heading} — prospetto completo", "family": FAMILY,
                      "subtitle": subtitle, "kpis": [], "items": [table]})
    return pages


def _index_entries(pages_by_statement: dict[str, list[dict[str, Any]]]) -> list[dict[str, str]]:
    entries = []
    for statement_id in _STATEMENT_ORDER:
        for page in pages_by_statement[statement_id]:
            table_item = page["items"][0]
            entries.append({"label": table_item["title"], "target": f"heading:{table_item['id']}"})
    return entries


def _index_page(entries: list[dict[str, str]]) -> dict[str, Any]:
    return {"id": "allegati", "title": "Allegati · indice dei prospetti", "family": FAMILY,
            "subtitle": "Questa sezione raccoglie il dettaglio contabile e finanziario.",
            "kpis": [], "items": [s.index_block("appendix-index", "Indice degli allegati", entries)]}


def build(report: FinalReportModelV2) -> list[dict[str, Any]]:
    pages_by_statement = {statement_id: _allegato_pages(report, statement_id) for statement_id in _STATEMENT_ORDER}
    ordered: list[dict[str, Any]] = [_index_page(_index_entries(pages_by_statement))]
    for statement_id in _STATEMENT_ORDER:
        ordered.extend(pages_by_statement[statement_id])
    return ordered
