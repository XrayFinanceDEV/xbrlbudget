"""Primitivi ReportLab del Business plan: misure prese dal PDF del committente (spike approvato)."""
from __future__ import annotations

import io

from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import Flowable, Image, Paragraph, Spacer, Table, TableStyle

from . import theme
from .theme import BOLD, CW, REGULAR

C = HexColor


def _ps(name, font=REGULAR, size=8.6, leading=None, color=theme.INK, **kw):
    return ParagraphStyle(name, fontName=font, fontSize=size, leading=leading or size * 1.2,
                          textColor=C(color), **kw)


ST = {
    "eyebrow": _ps("eyebrow", BOLD, 8.5, 11, theme.TEAL),
    "title": _ps("title", BOLD, 19, 23, theme.NAVY),
    "sub": _ps("sub", REGULAR, 10, 13, theme.MUTED),
    "h2": _ps("h2", BOLD, 12.2, 15, theme.NAVY),
    "note": _ps("note", REGULAR, 8.3, 10.4, theme.MUTED),
    "kv": _ps("kv", BOLD, 14.5, 17, theme.NAVY),
    "kl": _ps("kl", BOLD, 8.4, 10, theme.INK),
    "ks": _ps("ks", REGULAR, 7.8, 9.4, theme.MUTED),
    "cell": _ps("cell", REGULAR, 8.6, 10),
    "cellb": _ps("cellb", BOLD, 8.6, 10),
    "body": _ps("body", REGULAR, 9.3, 12.2),
    "bullet": _ps("bullet", REGULAR, 9.3, 12.2, leftIndent=10, bulletIndent=0),
    "cardtitle": _ps("cardtitle", BOLD, 11, 14, theme.TEAL),
    "cardhead": _ps("cardhead", BOLD, 9.3, 11.5),
    "paneltitle": _ps("paneltitle", BOLD, 10, 13, theme.NAVY),
}
ST["value"] = _ps("value", REGULAR, 9.2, 10.5, alignment=TA_RIGHT)
ST["valueh"] = _ps("valueh", BOLD, 9.2, 10.5, "#ffffff", alignment=TA_RIGHT)
ST["cellh"] = _ps("cellh", BOLD, 8.6, 10, "#ffffff")


def section_head(eyebrow: str, title: str, sub: str) -> list:
    out = [Paragraph(eyebrow, ST["eyebrow"]), Spacer(0, 3), Paragraph(title, ST["title"])]
    if sub:
        out += [Spacer(0, 1), Paragraph(sub, ST["sub"])]
    return out + [Spacer(0, 9)]


def h2(text: str, after: float = 2) -> list:
    return [Paragraph(text, ST["h2"]), Spacer(0, after)]


def note(text: str) -> Paragraph:
    return Paragraph(text, ST["note"])


def tiles(items: list) -> Table:
    """Quattro riquadri KPI: valore, etichetta, riga di confronto; filetto navy in alto."""
    gap = 8.5
    w = (CW - 3 * gap) / 4
    cells = [[Paragraph(v, ST["kv"]), Spacer(0, 2), Paragraph(lab, ST["kl"]), Spacer(0, 1.5), Paragraph(s, ST["ks"])]
             for v, lab, s in items]
    while len(cells) < 4:
        cells.append("")
    data = [[cells[0], "", cells[1], "", cells[2], "", cells[3]]]
    t = Table(data, colWidths=[w, gap, w, gap, w, gap, w])
    style = [("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("LEFTPADDING", (0, 0), (-1, -1), 8.8), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
             ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]
    for c in range(0, 2 * len(items), 2):
        style += [("BACKGROUND", (c, 0), (c, 0), C(theme.TILE)), ("LINEABOVE", (c, 0), (c, 0), 2.2, C(theme.NAVY))]
    t.setStyle(TableStyle(style))
    return t


ST["chip"] = _ps("chip", BOLD, 8.6, 10, "#ffffff")
ST["kv13"] = _ps("kv13", BOLD, 13, 15.5, theme.NAVY)


def tiles_chip(items: list, value_style: str = "kv") -> Table:
    """Quattro riquadri KPI del report infrannuale: bollino teal col periodo, valore, etichetta, confronto.

    items = [(bollino, valore, etichetta, confronto)]. Misure della p. 4 del riferimento: riquadro alto 65,8 pt,
    bollino alto 13,5 pt a 6 pt dal bordo superiore.
    """
    gap = 8.5
    w = (CW - 3 * gap) / 4
    cells = []
    for chip, v, lab, s in items:
        badge = Table([[Paragraph(chip, ST["chip"])]], colWidths=[w - 11], rowHeights=[13.5])
        badge.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), C(theme.TEAL)),
                                   ("LEFTPADDING", (0, 0), (-1, -1), 3), ("TOPPADDING", (0, 0), (-1, -1), 1.6),
                                   ("BOTTOMPADDING", (0, 0), (-1, -1), 0), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        cells.append([badge, Spacer(0, 2.5), Paragraph(v, ST[value_style]), Spacer(0, 1.5),
                      Paragraph(lab, ST["kl"]), Spacer(0, 1), Paragraph(s, ST["ks"])])
    while len(cells) < 4:
        cells.append("")
    t = Table([[cells[0], "", cells[1], "", cells[2], "", cells[3]]], colWidths=[w, gap, w, gap, w, gap, w])
    style = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 5.5),
             ("RIGHTPADDING", (0, 0), (-1, -1), 5.5), ("TOPPADDING", (0, 0), (-1, -1), 6),
             ("BOTTOMPADDING", (0, 0), (-1, -1), 4.9)]
    for c in range(0, 2 * len(items), 2):
        style += [("BACKGROUND", (c, 0), (c, 0), C(theme.TILE)), ("LINEABOVE", (c, 0), (c, 0), 2.2, C(theme.NAVY))]
    t.setStyle(TableStyle(style))
    return t


def _value_width(n: int) -> float:
    return {1: 90, 2: 90, 3: 80, 4: 72, 5: 64, 6: 58}.get(n, 52)


def fin_table(headers: list, rows: list, first: str = "Voce (euro)", label_width: float | None = None,
              value_size: float | None = None, pad: float = 4.6, label_size: float | None = None) -> Table:
    """Tabella finanziaria del riferimento: intestazione navy, filetti sottili, subtotali e righe evidenziate.

    `pad` è la spaziatura verticale di cella: 4,6 pt dà le righe da 19,6 pt delle pagine di lettura, 3,8 quelle da
    18,4 della sezione 8, 2,2 quelle degli allegati (tutte misurate sul riferimento).
    """
    n = len(headers)
    vw = _value_width(n)
    lw = label_width if label_width is not None else CW - n * vw
    vs = ST["value"] if value_size is None else _ps("v2", REGULAR, value_size, value_size * 1.15, alignment=TA_RIGHT)
    cell, cellb = ST["cell"], ST["cellb"]
    if label_size is not None:
        cell = _ps("cs", REGULAR, label_size, label_size * 1.15)
        cellb = _ps("csb", BOLD, label_size, label_size * 1.15)
    data = [[Paragraph(first, ST["cellh"])] + [Paragraph(h, ST["valueh"]) for h in headers]]
    style = [("BACKGROUND", (0, 0), (-1, 0), C(theme.NAVY)), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
             ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
             ("TOPPADDING", (0, 0), (-1, -1), pad), ("BOTTOMPADDING", (0, 0), (-1, -1), pad),
             ("TOPPADDING", (0, 0), (-1, 0), 4.6), ("BOTTOMPADDING", (0, 0), (-1, 0), 4.6),
             ("LINEBELOW", (0, 1), (-1, -1), 0.4, C(theme.RULE))]
    for r, (label, cells, kind) in enumerate(rows, start=1):
        bold = kind in ("bold", "hl", "group")
        data.append([Paragraph(label, cellb if bold else cell)] +
                    [Paragraph(x, vs) for x in (cells if kind != "group" else [""] * n)])
        if kind == "bold":
            style.append(("LINEABOVE", (0, r), (-1, r), 0.8, C(theme.MUTED)))
        elif kind == "hl":
            style += [("BACKGROUND", (0, r), (-1, r), C(theme.HL)), ("LINEABOVE", (0, r), (-1, r), 0.8, C(theme.TEAL))]
        elif kind == "group":
            style += [("BACKGROUND", (0, r), (-1, r), C(theme.PANEL)),
                      ("TOPPADDING", (0, r), (-1, r), min(pad, 3.4)), ("BOTTOMPADDING", (0, r), (-1, r), min(pad, 3.4))]
    t = Table(data, colWidths=[lw] + [vw] * n, repeatRows=1)
    t.setStyle(TableStyle(style))
    return t


def panel(title: str, bullets: list) -> Table:
    """Pannello grigio con filetto teal a sinistra: «Punti chiave», «Lettura». bullets = [(attacco, testo)]."""
    content = [Paragraph(title, ST["paneltitle"]), Spacer(0, 3)]
    for lead, text in bullets:
        lead_html = f"<b>{lead}</b> " if lead else ""
        content.append(Paragraph(f"<font color='{theme.TEAL}'>•</font>&nbsp;&nbsp;{lead_html}{text}", ST["body"]))
        content.append(Spacer(0, 3))
    t = Table([[content]], colWidths=[CW])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), C(theme.PANEL)),
                           ("LINEBEFORE", (0, 0), (0, -1), 3, C(theme.TEAL)),
                           ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                           ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    return t


def chart(png: bytes, height_in: float, width_pt: float = CW) -> Image:
    img = Image(io.BytesIO(png), width=width_pt, height=width_pt * height_in / 7.2)
    img.hAlign = "CENTER"
    return img


class SectionStart(Flowable):
    """Segnaposto a dimensione zero: registra la pagina in cui comincia una sezione (per l'indice)."""

    def __init__(self, key: str, registry: dict):
        super().__init__()
        self.key, self.registry = key, registry

    def wrap(self, *args):
        return 0, 0

    def draw(self):
        self.registry.setdefault(self.key, self.canv.getPageNumber())


def fit(text: str, font: str, size: float, width: float) -> str:
    """Il testo intero se ci sta, altrimenti troncato con «…» alla larghezza data."""
    if pdfmetrics.stringWidth(text, font, size) <= width:
        return text
    while text and pdfmetrics.stringWidth(text + "…", font, size) > width:
        text = text[:-1]
    return text.rstrip() + "…"
