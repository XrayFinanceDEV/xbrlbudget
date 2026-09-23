"""Palette, misure di pagina e font del Business plan, misurati sul PDF del committente."""
from __future__ import annotations

from pathlib import Path
from threading import Lock

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

FONT_DIR = Path(__file__).parent / "fonts"
REGULAR, BOLD = "Lato-Regular", "Lato-Bold"

NAVY, TEAL, ORANGE, ORANGE_DARK = "#1f3a5f", "#2a9d8f", "#e9a23b", "#9a6512"
GREY, RED, LIGHTBLUE = "#9aa5b1", "#c8553d", "#a9c4e2"
GRID, AXIS, INK, MUTED, RULE = "#e6e8ec", "#3e4c59", "#1f2933", "#616e7c", "#d9dee4"
TILE, HL, PANEL, WEAK, COVER_SUB = "#e8f1f8", "#e6f4f1", "#f2f5f8", "#fbedea", "#c9d6e3"

PAGE_W, PAGE_H = A4
LM = 48.2
CW = PAGE_W - 2 * LM
HEADER_H = 31.2
FOOTER_RULE_Y = 807.9  # dall'alto, come lo misura PyMuPDF

_lock = Lock()
_registered = False


def register_fonts() -> None:
    """Registra Lato in ReportLab una volta sola, anche con render concorrenti."""
    global _registered
    with _lock:
        if _registered:
            return
        for name in (REGULAR, BOLD):
            pdfmetrics.registerFont(TTFont(name, str(FONT_DIR / f"{name}.ttf")))
        _registered = True
