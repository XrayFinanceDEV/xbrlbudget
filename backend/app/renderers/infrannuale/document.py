"""Assemblaggio del report infrannuale: catalogo fisso delle sezioni e due passate per l'indice."""
from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Callable, Optional

from reportlab.lib.colors import HexColor, white
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import BaseDocTemplate, Frame, NextPageTemplate, PageBreak, PageTemplate

from app.renderers.business_plan import theme
from app.renderers.business_plan.layout import SectionStart, fit
from app.renderers.business_plan.theme import BOLD, LM, PAGE_H, PAGE_W, REGULAR

from .data import InfrannualeData

C = HexColor


class IndexShifted(RuntimeError):
    """La seconda passata ha spostato le sezioni: l'indice stampato sarebbe sbagliato."""


@dataclass(frozen=True)
class SectionSpec:
    key: str
    index_title: Optional[str]
    build: Callable[[InfrannualeData, dict], list]
    cover: bool = False


SECTIONS: list = []  # riempito da _register() in fondo al modulo


def _body_page(data: InfrannualeData):
    right = data.header_title
    foot = f"Riservato e confidenziale · {data.legend}"

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
        canvas.drawString(LM, PAGE_H - 820, fit(foot, REGULAR, 7.8, PAGE_W - 2 * LM - 20))
        canvas.drawRightString(PAGE_W - LM, PAGE_H - 820, str(canvas.getPageNumber()))
        canvas.restoreState()
    return on_page


def _cover_page(data: InfrannualeData):
    from .sections_sintesi import draw_cover_band
    return lambda canvas, doc: draw_cover_band(canvas, data)


def _build(data: InfrannualeData, specs: list, pages: dict) -> tuple:
    theme.register_fonts()
    buf = io.BytesIO()
    registry: dict = {}
    doc = BaseDocTemplate(buf, pagesize=(PAGE_W, PAGE_H), leftMargin=LM, rightMargin=LM, topMargin=55,
                          bottomMargin=40, title=f"{data.company_name} – {data.header_title}",
                          author="", subject="Report infrannuale", creator="XBRL Budget")
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


def render_infrannuale(data: InfrannualeData, *, only: Optional[tuple] = None) -> bytes:
    """Due passate: la prima misura in che pagina comincia ogni sezione, la seconda stampa l'indice giusto."""
    specs = [s for s in SECTIONS if only is None or s.key in only]
    _, pages = _build(data, specs, {})
    pdf, second = _build(data, specs, pages)
    if second != pages:
        raise IndexShifted("l'indice ha spostato le pagine: la copertina deve avere altezza fissa")
    return pdf


def _register() -> None:
    from . import sections as sec
    SECTIONS.clear()
    SECTIONS.extend([
        SectionSpec("economia", "Conto economico: infrannuale, annualizzato e forecast", sec.economia),
        SectionSpec("patrimonio", "Stato patrimoniale", sec.patrimonio),
        SectionSpec("crisi", "Indicatori della crisi d'impresa", sec.crisi),
    ])


_register()
