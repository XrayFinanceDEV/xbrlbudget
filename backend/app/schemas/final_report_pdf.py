"""Strict request contract for the dossier PDF endpoint (M2-05).

I messaggi d'errore dell'endpoint sono `detail` stringhe in italiano, come nel
resto dell'API: non portano percorsi né dati del documento. Questo modulo tiene
solo il corpo di richiesta, chiuso e senza campi browser-side.
"""
from typing import Literal

from app.schemas.final_report import ContractModel


class FinalReportPdfRequest(ContractModel):
    """Che cosa si chiede di stampare: una bozza marcata o il documento finale."""
    document_state: Literal["draft", "final"] = "draft"
    grayscale: bool = False
