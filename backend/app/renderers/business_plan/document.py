"""Assemblaggio del Business plan: catalogo fisso delle sezioni e due passate per l'indice."""
from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Callable, Optional

from reportlab.lib.colors import HexColor, white
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import BaseDocTemplate, Frame, NextPageTemplate, PageBreak, PageTemplate

from . import theme
from .data import BusinessPlanData, legend
from .layout import SectionStart, fit
from .theme import BOLD, LM, PAGE_H, PAGE_W, REGULAR

C = HexColor


@dataclass(frozen=True)
class SectionSpec:
    key: str
    index_title: Optional[str]
    build: Callable[[BusinessPlanData, dict], list]
    cover: bool = False


SECTIONS: list = []  # riempito da _register() in fondo al modulo


def header_title(data: BusinessPlanData) -> str:
    years = data.plan_years
    span = f"{years[0]} – {years[-1]}" if len(years) > 1 else f"{years[0]}"
    return f"Piano economico-finanziario {span}"


def page_texts(data: BusinessPlanData) -> tuple:
    """Intestazione sinistra, destra e piè di pagina: gli stessi nel PDF e nel Word."""
    return (data.company_name, header_title(data) + (" · BOZZA" if data.draft else ""),
            f"Riservato e confidenziale · {legend(data)}")


def _body_page(data: BusinessPlanData):
    _, right, foot = page_texts(data)

    def on_page(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(C(theme.NAVY))
        canvas.rect(0, PAGE_H - theme.HEADER_H, PAGE_W, theme.HEADER_H, stroke=0, fill=1)
        canvas.setFillColor(white)
        canvas.setFont(BOLD, 9)
        room = PAGE_W - 2 * LM - pdfmetrics.stringWidth(right, REGULAR, 9) - 16
        canvas.drawString(LM, PAGE_H - 20.5, fit(data.company_name, BOLD, 9, room))
        canvas.setFont(REGULAR, 9)
        canvas.drawRightString(PAGE_W - LM, PAGE_H - 20.5, right)
        canvas.setStrokeColor(C(theme.RULE))
        canvas.setLineWidth(0.5)
        canvas.line(LM, PAGE_H - theme.FOOTER_RULE_Y, PAGE_W - LM, PAGE_H - theme.FOOTER_RULE_Y)
        canvas.setFillColor(C(theme.MUTED))
        canvas.setFont(REGULAR, 7.8)
        canvas.drawString(LM, PAGE_H - 820, foot)
        canvas.drawRightString(PAGE_W - LM, PAGE_H - 820, str(canvas.getPageNumber()))
        canvas.restoreState()
    return on_page


def _cover_page(data: BusinessPlanData):
    from .sections_sintesi import draw_cover_band  # import locale: esiste solo dal Task 7
    return lambda canvas, doc: draw_cover_band(canvas, data)


def _build(data: BusinessPlanData, specs: list, pages: dict) -> tuple:
    theme.register_fonts()
    buf = io.BytesIO()
    registry: dict = {}
    doc = BaseDocTemplate(buf, pagesize=(PAGE_W, PAGE_H), leftMargin=LM, rightMargin=LM, topMargin=55,
                          bottomMargin=40, title=f"{data.company_name} – {header_title(data)}",
                          author="", subject="Business plan", creator="XBRL Budget")
    body = PageTemplate(id="body", frames=[Frame(LM, 40, theme.CW, PAGE_H - 95, id="b", leftPadding=0,
                                                 rightPadding=0, topPadding=0, bottomPadding=0)],
                        onPage=_body_page(data))
    if any(s.cover for s in specs):
        cover = PageTemplate(id="cover", frames=[Frame(LM, 40, theme.CW, PAGE_H - 300 - 40, id="c", leftPadding=0,
                                                       rightPadding=0, topPadding=0, bottomPadding=0)],
                             onPage=_cover_page(data))
        doc.addPageTemplates([cover, body])
    else:
        doc.addPageTemplates([body])
    story: list = []
    for n, spec in enumerate(specs):
        if n > 0:
            story.append(PageBreak())
        story.append(SectionStart(spec.key, registry))
        story.extend(spec.build(data, pages))
        if spec.cover:
            story.append(NextPageTemplate("body"))
    doc.build(story)
    return buf.getvalue(), registry


def render_business_plan(data: BusinessPlanData, *, only: Optional[tuple] = None) -> bytes:
    """Due passate: la prima misura in che pagina comincia ogni sezione, la seconda stampa l'indice giusto."""
    specs = [s for s in SECTIONS if only is None or s.key in only]
    _, pages = _build(data, specs, {})
    pdf, second = _build(data, specs, pages)
    assert second == pages, "l'indice ha spostato le pagine: la copertina deve avere altezza fissa"
    return pdf


def render_business_plan_docx(data: BusinessPlanData) -> bytes:
    """Lo stesso Business plan in Word (spec 2026-09-24): stesse sezioni, indice senza numeri di pagina."""
    from app.renderers import docx_export
    from .sections_sintesi import cover_lines
    theme.register_fonts()
    left, right, foot = page_texts(data)
    return docx_export.build([s.build(data, {}) for s in SECTIONS], cover=cover_lines(data), header_left=left,
                             header_right=right, footer=foot, title=f"{data.company_name} – {header_title(data)}")


def _register() -> None:
    from . import sections_allegati as ann
    from . import sections_economia as eco
    from . import sections_finanza as fin
    from . import sections_partenza as par
    from . import sections_sintesi as sin
    SECTIONS.clear()
    SECTIONS.extend([
        SectionSpec("copertina", None, sin.copertina, cover=True),
        SectionSpec("sintesi", "Sintesi del piano", sin.sintesi),
        SectionSpec("forza", None, sin.forza),
        SectionSpec("economia", "Evoluzione economica dell'impresa", eco.economia),
        SectionSpec("costi", "EBITDA margin e struttura dei costi", eco.costi),
        SectionSpec("pareggio", "Costi fissi e variabili · break even point", eco.pareggio),
        SectionSpec("flussi", "Flussi di cassa", eco.flussi),
        SectionSpec("debito", "Sostenibilità del debito · DSCR e PFN", fin.debito),
        SectionSpec("circolante", "Capitale circolante commerciale", fin.circolante),
        SectionSpec("solidita", "Solidità patrimoniale, liquidità e redditività", fin.solidita),
        SectionSpec("partenza", "Punto di partenza", par.partenza),
        SectionSpec("ipotesi", "Assunzioni del piano", par.ipotesi),
        SectionSpec("allegato_a", "Allegati A–E", ann.allegato_a),
        SectionSpec("allegato_b", None, ann.allegato_b),
        SectionSpec("allegato_c", None, ann.allegato_c),
        SectionSpec("allegato_d", None, ann.allegato_d),
        SectionSpec("allegato_e", None, ann.allegato_e),
    ])


_register()
