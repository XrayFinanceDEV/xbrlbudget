"""Richiesta del PDF del report infrannuale (ReportLab): nessun parametro, contratto stretto."""
from pydantic import BaseModel, ConfigDict


class InfrannualePdfRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
