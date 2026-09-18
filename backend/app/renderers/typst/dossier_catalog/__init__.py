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
from .shared import chart_marker_width_mm  # re-exported: editorial_plan.py imports it from here

# Ordine fisso del catalogo v4: apertura (1-2) · dati (3-6, solo infrannuale) ·
# piano e risultati (7-10) · indicatori (11-18) · allegati (19-33).
GROUPS = (apertura, dati, piano, indicatori, allegati)


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
    return pages


def expected_content_inventory(report: FinalReportModelV2) -> OrderedDict[str, str]:
    """Map every exact marker Typst must emit to the id of the page that owns
    it. Order is significant: this is the canonical linear reading order the
    whole document must reproduce, checked position-for-position by
    `editorial_plan.py`."""
    expected: OrderedDict[str, str] = OrderedDict()
    for page in build_inventory(report):
        for item in page["items"]:
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
        for item in page["items"]:
            if item["kind"] == "chart":
                charts[item["id"]] = item
    return charts


__all__ = ["build_inventory", "expected_content_inventory", "chart_declarations", "chart_marker_width_mm"]
