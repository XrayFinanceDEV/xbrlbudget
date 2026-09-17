"""PDF del dossier finale: modello v2 congelato, renderer condiviso, nessuna scrittura.

Costruisce il modello v2 esattamente come `GET /final-report?schema_version=2`
(quindi con il piano editoriale e le note già persistiti) e lo rende con il
`TypstRenderer` del bundle del dossier: un'istanza sola per processo, ripresa
dal servizio editoriale, il cui semaforo interno limita i compilatori concorrenti.
Qui non si genera nulla di narrativo, non si rigenera il previsionale e non si
scrive su DB: si misura, si vara il cancello e si mappa l'errore.
"""
from __future__ import annotations

import re

from dataclasses import dataclass

from app.renderers.typst.runtime import RenderedPdf
from app.schemas.final_report import canonical_hash
from app.schemas.final_report_v2 import FinalReportModelV2
from app.services.editorial_notes_service import get_dossier_probe
from app.services.final_report_service import assemble_final_report


class EditorialPlanRequired(ValueError):
    """Il dossier non ha un piano editoriale valido per il modello corrente."""


class FinalNotReady(ValueError):
    """È stato chiesto il documento «final» su un report la cui readiness non è ready."""


@dataclass(frozen=True)
class PdfResult:
    """Il PDF renderizzato con le identità osservabili che finiscono negli header."""
    report: FinalReportModelV2
    rendered: RenderedPdf
    etag: str


#: Caratteri vietati o ambigui in un nome file (Windows li vieta, il shell li interpreta).
_UNSAFE = re.compile(r'[\\/:*?"<>|\x00-\x1f\x7f]')


def artifact_filename(report: FinalReportModelV2) -> str:
    """«Report Budget 2027 - 2029 - <azienda>.pdf», ripulito dai caratteri non sicuri.

    Il titolo viene dal modello (già neutro e vincolato dal contratto), il nome
    azienda è testo utente: si appiattiscono gli spazi, si tolgono i caratteri
    vietati e si limita la lunghezza. L'encoder dell'HTTP mette poi la versione
    UTF-8 in `filename*`; questa resta il fallback ASCII-safe.
    """
    raw = f"{report.document.title} - {report.company.name}"
    safe = re.sub(r"\s+", " ", _UNSAFE.sub(" ", raw)).strip().strip(".").rstrip()
    return (safe[:160].rstrip(" .-") or "Report Budget") + ".pdf"


def render_pdf(db, company_id: int, scenario_id: int, *,
               document_state: str = "draft", grayscale: bool = False) -> PdfResult:
    """Assemble → gate → render. Solo letture: né AI, né forecast, né DB writes."""
    report = assemble_final_report(db, company_id, scenario_id, schema_version=2)
    if report.editorial_plan is None:
        # Il piano mancante (o non più attuale) arriva qui come proiezione pending:
        # non è un'opzione di salvataggio, l'utente lo prepara dalla schermata editoriale.
        raise EditorialPlanRequired(
            "Piano editoriale non preparato o non più valido per il modello corrente: "
            "premere «Prepara piano editoriale» prima di scaricare il PDF."
        )
    if document_state == "final" and report.readiness.status != "ready":
        raise FinalNotReady(
            f"Il report non è pronto per la versione finale (stato: {report.readiness.status}). "
            "Risolvi gli avvisi pubblicati nel dossier, oppure scarica la bozza."
        )
    rendered = get_dossier_probe().render(report, document_state=document_state, grayscale=grayscale)
    etag = canonical_hash({"model": report.model_hash, "plan": report.editorial_plan.plan_hash},
                          exclude_volatile=False)
    return PdfResult(report, rendered, etag)
