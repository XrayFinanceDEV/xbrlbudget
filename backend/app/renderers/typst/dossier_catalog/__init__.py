"""Dossier PDF as a fixed page catalog (M2-02D), replacing the generic model
dump `editorial_inventory.py` used to be. The catalog is a **finite, ordered
list of v4 pages** — copertina, sintesi, fonti, rettifiche, ..., allegati —
one Python module per group of pages (`apertura`, `dati`, `piano`,
`indicatori`, `allegati`), each registered here in the fixed catalog order.
A group not yet implemented exposes an empty `build(report) -> []`: its pages
simply do not appear (never a blank placeholder). See
`docs/testing/M2-02D-catalogo.md` for how to add a page.

Downstream consumers (`editorial_plan.py`, `editorial_notes_service.py`) see
the SAME wire shape the old `editorial_inventory.py` produced — a list of
"page" dicts (`id`, `title`, `family`, `subtitle`, `kpis`, `items`) and an
ordered `content_id -> page_id` map — so neither module needed to change its
own validation algorithm, only the source of that shape.
"""
from __future__ import annotations

from collections import OrderedDict
from typing import Any

from app.schemas.final_report_v2 import FinalReportModelV2

from . import allegati, apertura, dati, indicatori, piano
from .shared import (  # noqa: F401  (riesportati: `editorial_plan.py` li importa da qui)
    CHART_WIDTH_FULL_MM, CHART_WIDTH_KPI_MM, CHART_WIDTH_PANEL_MM, CHART_WIDTH_RAIL_MM,
    PAGE_FORMS, RAIL_WIDTH_MM, chart_marker_width_mm,
)

# Ordine fisso del catalogo v4: apertura (1-2) · dati (3-6, solo infrannuale) ·
# piano e risultati (7-10) · indicatori (11-18) · allegati (19-33).
GROUPS = (apertura, dati, piano, indicatori, allegati)


def _leading_rail_run(items: list[dict[str, Any]]) -> int:
    """Quanti blocchi stanno dentro la `.row` della v4, cioe quelli accanto al
    rail: la corsa iniziale di grafici (pagine 12, 14, 15, 17: due grafici uno
    sopra l'altro nella colonna principale), altrimenti il solo primo blocco
    (pagine 3, 7, 18: una tabella nella colonna principale, il resto a
    larghezza intera sotto il rail)."""
    if items and items[0]["kind"] == "chart":
        count = 0
        while count < len(items) and items[count]["kind"] == "chart":
            count += 1
        return count
    return 1 if items else 0


def _apply_page_form(page: dict[str, Any]) -> dict[str, Any]:
    """Normalizza la forma di pagina: e l'unico punto che decide le geometrie
    che Typst deve riprodurre e che `editorial_plan.py` rivuole identiche nel
    marcatore (`chart_marker_width_mm`).

    Una pagina che non dichiara `form` si comporta esattamente come prima di
    questa funzione: `single`, grafico a 178 mm (o 118 mm con la colonna KPI
    agganciata al grafico), tabellina dei valori sotto il grafico. Una pagina
    executive dichiara `rail+main` (rail di 47 mm a sinistra della `.row`) o
    `full+panels` (due grafici affiancati a meta larghezza) e ottiene le
    colonne, il rail e la value-table disattivata.

    Il rail prende i KPI della pagina; se la pagina non ne ha, eredita quelli
    che il catalogo teneva appesi al primo grafico, e quel grafico li perde —
    altrimenti la stessa cifra uscirebbe due volte, una nel rail e una nella
    colonna da 55 mm del grafico.
    """
    form = page.get("form")
    if form is not None and form not in PAGE_FORMS:
        raise ValueError(f"unknown page form: {form!r} (expected one of {PAGE_FORMS})")
    if form is None:
        form = "cover" if any(item["kind"] == "cover" for item in page["items"]) else "single"
    page["form"] = form
    blocks = list(_iter_blocks(page))
    if form == "single":
        page["rail"] = list(page.get("kpis") or [])
        return page
    inside = _leading_rail_run(blocks) if form == "rail+main" else 0
    rail_kpis = list(page.get("kpis") or [])
    for position, item in enumerate(blocks):
        item["rail"] = form == "rail+main" and position < inside
        if item["kind"] != "chart":
            continue
        item["value_table"] = False
        item["width_mm"] = (CHART_WIDTH_RAIL_MM if item["rail"]
                            else CHART_WIDTH_PANEL_MM if form == "full+panels"
                            else CHART_WIDTH_FULL_MM)
    for item in blocks:
        if item["kind"] == "chart" and item["rail"] and item.get("kpis"):
            rail_kpis = rail_kpis or list(item["kpis"])
            item["kpis"] = []
    page["rail"] = rail_kpis
    return page


def _iter_blocks(page: dict[str, Any]):
    """I blocchi di una pagina in ordine di lettura: un pannello non è un
    blocco per il piano editoriale, i suoi grafici sí."""
    for item in page["items"]:
        if item["kind"] == "panel":
            yield from item["items"]
        else:
            yield item


#: Le sezioni che la copertina elenca, nell'ordine del catalogo (v4 pagina 1:
#: 13 voci su due colonne, ciascuna col proprio numero di pagina). Non sono
#: tutte le 33 pagine: le pagine di approfondimento degli indicatori (12-17) e
#: i singoli allegati stanno sotto la voce che li introduce, come nella v4.
#: Una sezione assente dal flusso (le pagine dati mancano su un budget annuale)
#: semplicemente non compare.
COVER_SECTIONS = ("sintesi", "fonti", "rettifiche", "chiusura", "indicatori-infrannuali",
                  "ipotesi", "ce", "sp", "flussi", "indicatori", "diagnostica",
                  "allegati", "metodologia")


def _fill_cover_toc(pages: list[dict[str, Any]]) -> None:
    """L'indice della copertina, costruito dall'inventario stesso: etichetta =
    titolo neutro della pagina, numero = posizione della pagina nel catalogo.

    Il numero si conta qui, non lo risolve Typst dal vivo come fa l'indice
    degli allegati: il catalogo garantisce **una pagina fisica per voce**, e
    `editorial_plan._validate_inventory` lo verifica misurando il documento
    compilato (una sola sezione per pagina, pagine contigue da 1). Se
    quell'invariante saltasse, il piano editoriale fallirebbe forte prima che
    un indice sbagliato possa uscire in un PDF.
    """
    entries = []
    for position, page in enumerate(pages, start=1):
        if page["id"] in COVER_SECTIONS:
            entries.append({"label": page["title"], "page": position})
    pages[0]["toc"] = entries


def build_inventory(report: FinalReportModelV2) -> list[dict[str, Any]]:
    """The ordered list of pages for this report's workflow. Each page's
    `items` are already the exact, curated v4 content for that one physical
    page — not a spillable list a renderer must paginate on its own."""
    if not isinstance(report, FinalReportModelV2):
        raise TypeError("build_inventory requires FinalReportModelV2")
    pages: list[dict[str, Any]] = []
    for group in GROUPS:
        pages.extend(group.build(report))
    if not pages or pages[0]["id"] != "cover":
        raise ValueError("the catalog must start with the cover page")
    shaped = [_apply_page_form(page) for page in pages]
    _fill_cover_toc(shaped)
    return shaped


def expected_content_inventory(report: FinalReportModelV2) -> OrderedDict[str, str]:
    """Map every exact marker Typst must emit to the id of the page that owns
    it. Order is significant: this is the canonical linear reading order the
    whole document must reproduce, checked position-for-position by
    `editorial_plan.py`."""
    expected: OrderedDict[str, str] = OrderedDict()
    for page in build_inventory(report):
        for item in _iter_blocks(page):
            if item["kind"] == "cover":
                content_ids = ["cover"]
            elif item["kind"] in ("chart", "text", "note", "index"):
                content_ids = [item["id"]]
            else:  # table
                content_ids = [f"heading:{item['id']}", *(row["id"] for row in item["rows"])]
            for content_id in content_ids:
                if content_id in expected:
                    raise ValueError(f"duplicate editorial content id: {content_id}")
                expected[content_id] = page["id"]
    return expected


def chart_declarations(report: FinalReportModelV2) -> dict[str, dict[str, Any]]:
    """content_id -> chart item dict (`chart`, `kpis`, `title`, ...), for
    every chart block in the catalog. Used by `editorial_plan.py` to
    cross-check what Typst actually drew against what Python declared — a
    chart is built once, in Python; Typst never looks one up by id in a
    separate registry keyed on the raw `report.chart_series`."""
    charts: dict[str, dict[str, Any]] = {}
    for page in build_inventory(report):
        for item in _iter_blocks(page):
            if item["kind"] == "chart":
                charts[item["id"]] = item
    return charts


__all__ = ["build_inventory", "expected_content_inventory", "chart_declarations",
           "chart_marker_width_mm", "PAGE_FORMS"]
