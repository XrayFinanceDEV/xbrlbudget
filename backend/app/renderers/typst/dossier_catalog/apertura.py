"""Gruppo APERTURA: copertina (v4 pagina 1) e sintesi esecutiva (v4 pagina 2)."""
from __future__ import annotations

from typing import Any

from app.schemas.final_report_v2 import FinalReportModelV2

from . import shared as s

GROUP = "apertura"


def _copertina(report: FinalReportModelV2) -> dict[str, Any]:
    kpis = [kpi for kpi in (
        s.kpi_revenue_now(report),
        s.kpi_indicator(report, "practice.ebitda_margin", "EBITDA margin"),
        s.kpi_indicator(report, "practice.pfn", "PFN"),
        s.kpi_horizon(report),
    ) if kpi is not None]
    return {"id": "cover", "title": None, "family": None, "subtitle": None, "kpis": kpis,
            "items": [{"id": "cover", "kind": "cover", "title": report.document.title}]}


def _sintesi(report: FinalReportModelV2) -> dict[str, Any]:
    kpis = [kpi for kpi in (
        s.kpi_revenue_now(report),
        s.kpi_indicator(report, "practice.ebitda_margin", "EBITDA margin", mode="first_last"),
        s.kpi_indicator(report, "practice.pfn", "PFN"),
        s.kpi_forecast(report, "balance_sheet", ("cash", "sp09_disponibilita_liquide"), "cassa"),
    ) if kpi is not None]
    statement = s.statement_by_id(report, "income_statement")
    periods = s.select_periods(statement.periods)
    # "Ricavi" è qui `production_value` (Totale Valore della Produzione), non
    # `ce01_ricavi_vendite`: affiancato a EBITDA nello stesso grafico, deve
    # essere la stessa base che la tabella dell'aggregato usa altrove nel
    # dossier (pagina CE), altrimenti Ricavi−Costi ≠ EBITDA a vista, come se
    # il prospetto non quadrasse. Il KPI «ricavi» qui sopra resta invece sui
    # ricavi delle vendite (con fallback), la cifra che l'utente riconosce.
    chart = s.statement_chart(report, "income_statement", "sintesi-andamento",
        "Ricavi e redditività del piano", "eur", periods,
        [("production_value", "Ricavi"), ("ebitda", "EBITDA"), ("net_profit", "Risultato netto")])
    items: list[dict[str, Any]] = []
    block = s.chart_block("sintesi-andamento", "Ricavi e redditività del piano", chart, kpis)
    if block is not None:
        items.append(block)
    return {"id": "sintesi", "title": "Sintesi esecutiva", "family": "Sintesi",
            "subtitle": "I dati osservati, la chiusura attesa e gli anni di piano sono tenuti "
                        "distinti in tutto il dossier.",
            "kpis": [] if items else kpis, "items": items}


def build(report: FinalReportModelV2) -> list[dict[str, Any]]:
    return [_copertina(report), _sintesi(report)]
