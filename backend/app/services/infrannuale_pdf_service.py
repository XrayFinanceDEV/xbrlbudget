"""Report infrannuale PDF: assemble_intermedio → from_intermedio → render. Solo letture: niente AI, niente scritture."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.renderers.infrannuale.data import from_intermedio
from app.renderers.infrannuale.document import render_infrannuale, render_infrannuale_docx
from app.services.intermedio_report_service import assemble_intermedio


DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@dataclass(frozen=True)
class InfrannualePdf:
    data: bytes
    filename: str
    ascii_filename: str
    etag: str


def filenames(company_name: str, partial_label: str, ext: str = "pdf") -> tuple:
    full = f"Report infrannuale {company_name} {partial_label}.{ext}"
    ascii_name = unicodedata.normalize("NFKD", full).encode("ascii", "ignore").decode("ascii")
    ascii_name = re.sub(r"[^A-Za-z0-9 ._-]+", "", ascii_name)
    ascii_name = re.sub(r"\s+", " ", ascii_name).strip() or f"Report infrannuale.{ext}"
    return full, ascii_name


def render(db: Session, scenario: Any) -> InfrannualePdf:
    """Solleva ValueError se i bilanci del periodo non ci sono (la rotta risponde 400, come quella Typst)."""
    data = from_intermedio(assemble_intermedio(db, scenario))
    pdf = render_infrannuale(data)
    full, ascii_name = filenames(data.company_name, data.partial_label)
    return InfrannualePdf(pdf, full, ascii_name, hashlib.sha256(pdf).hexdigest()[:32])


def render_docx(db: Session, scenario: Any) -> InfrannualePdf:
    """Lo stesso report in Word: stesse eccezioni della PDF, nome con estensione .docx."""
    data = from_intermedio(assemble_intermedio(db, scenario))
    docx = render_infrannuale_docx(data)
    full, ascii_name = filenames(data.company_name, data.partial_label, ext="docx")
    return InfrannualePdf(docx, full, ascii_name, hashlib.sha256(docx).hexdigest()[:32])
