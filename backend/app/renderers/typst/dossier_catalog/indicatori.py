"""Gruppo INDICATORI (v4 pagine 11-18): indicatori del piano, liquidità e
margini strutturali, redditività e costo del debito, solidità e copertura del
debito, circolante e ciclo monetario, composizione economica e patrimoniale,
break-even e margine di sicurezza, diagnostica e punti da verificare.

Non implementato in questa fase (fondazione M2-02D): registro vuoto.

Nota per chi implementa «composizione» e «break-even»: i dati sono già nel
modello v2 (`report.structure_series`, quattro `ReportSeriesGroup` fissi —
`composition_uses`, `composition_sources`, `cost_incidence`, `break_even`,
aggiunti da M2-02C), con serie canoniche in ordine fisso
(`STRUCTURE_GROUP_SERIES` in `app.schemas.final_report_v2`). Nessun calcolo:
solo lettura e formattazione.
"""
from __future__ import annotations

from typing import Any

from app.schemas.final_report_v2 import FinalReportModelV2

GROUP = "indicatori"


def build(report: FinalReportModelV2) -> list[dict[str, Any]]:
    return []
