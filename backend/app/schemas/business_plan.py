"""Corpo di richiesta del PDF Business plan: bozza marcata o documento finale, nient'altro."""
from typing import Literal

from app.schemas.final_report import ContractModel


class BusinessPlanPdfRequest(ContractModel):
    document_state: Literal["draft", "final"] = "draft"
