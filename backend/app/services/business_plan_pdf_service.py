"""Business plan PDF: assemble → gate → from_report → render. Solo letture: niente AI, niente DB writes."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass

from app.renderers.business_plan import from_report, render_business_plan
from app.renderers.business_plan.document import render_business_plan_docx
from app.services.final_report_pdf_service import FinalNotReady
from app.services.final_report_service import assemble_final_report


@dataclass(frozen=True)
class BusinessPlanPdf:
    data: bytes
    filename: str
    ascii_filename: str
    etag: str


def filenames(company_name: str, years: list, ext: str = "pdf") -> tuple:
    span = f"{years[0]}-{years[-1]}" if len(years) > 1 else str(years[0])
    full = f"Business plan {company_name} {span}.{ext}"
    ascii_name = unicodedata.normalize("NFKD", full).encode("ascii", "ignore").decode("ascii")
    ascii_name = re.sub(r"[^A-Za-z0-9 ._-]+", "", ascii_name)
    ascii_name = re.sub(r"\s+", " ", ascii_name).strip() or f"Business plan.{ext}"
    return full, ascii_name


def _data(db, company_id: int, scenario_id: int, document_state: str):
    report = assemble_final_report(db, company_id, scenario_id, schema_version=2)
    if document_state == "final" and report.readiness.status != "ready":
        raise FinalNotReady("Il documento finale richiede una pratica pronta: scarica la bozza.")
    return from_report(report, draft=document_state != "final")


def render(db, company_id: int, scenario_id: int, *, document_state: str = "draft") -> BusinessPlanPdf:
    data = _data(db, company_id, scenario_id, document_state)
    pdf = render_business_plan(data)
    full, ascii_name = filenames(data.company_name, data.plan_years)
    return BusinessPlanPdf(pdf, full, ascii_name, hashlib.sha256(pdf).hexdigest()[:32])


def render_docx(db, company_id: int, scenario_id: int, *, document_state: str = "draft") -> BusinessPlanPdf:
    """Lo stesso documento in Word: stessi cancelli, stesso nome con estensione .docx."""
    data = _data(db, company_id, scenario_id, document_state)
    docx = render_business_plan_docx(data)
    full, ascii_name = filenames(data.company_name, data.plan_years, ext="docx")
    return BusinessPlanPdf(docx, full, ascii_name, hashlib.sha256(docx).hexdigest()[:32])
