"""Gruppo PIANO E RISULTATI (v4 pagine 7-10): ipotesi del piano, conto economico
previsionale, stato patrimoniale previsionale, flussi di cassa e sostenibilità.

In questa fase (fondazione M2-02D) è implementata solo la pagina «ce» (v4
pagina 8), come dimostrazione del modulo. «ipotesi», «sp», «flussi» restano da
fare: TODO per il prossimo agente del gruppo.
"""
from __future__ import annotations

from typing import Any

from app.schemas.final_report_v2 import FinalReportModelV2

from . import shared as s

GROUP = "piano"

FAMILY = "Piano e risultati"

# Le nove righe di sintesi del CE previsionale (vincolo del proprietario,
# 2026-09-17: «rettifiche al minimo» si applica anche qui — la pagina di
# sezione mostra un aggregato, non le 47 righe del prospetto completo, che
# stanno nell'Allegato A). Etichette brevi, non il testo legale della riga
# (`row.label`), per restare leggibili nella tabella di sintesi — stesso
# principio di `_FORECAST_LABEL_OVERRIDES` nel vecchio inventario: si sceglie
# quale testo stampare per una riga canonica nota, non se ne inventa il
# valore. `production_value` (non `ce01_ricavi_vendite`) è la stessa base
# usata dal grafico di sintesi (v. apertura.py), così Ricavi − Costi = EBITDA
# torna visibile nella tabella.
_CE_SUMMARY_ROWS: tuple[tuple[str, str], ...] = (
    ("production_value", "Ricavi"),
    ("production_cost", "Costi operativi"),
    ("ebitda", "EBITDA"),
    ("ce09_ammortamenti", "Ammortamenti"),
    ("ebit", "EBIT"),
    ("ce15_oneri_finanziari", "Oneri finanziari"),
    ("profit_before_tax", "Risultato ante imposte"),
    ("ce20_imposte", "Imposte"),
    ("net_profit", "Risultato netto"),
)


def _ce_summary_table(report: FinalReportModelV2, statement: Any, periods: list[Any]) -> dict[str, Any]:
    columns = ["Voce", *[s.period_label(period) for period in periods]]
    rows = []
    for code, display_label in _CE_SUMMARY_ROWS:
        row_obj = s.statement_row(statement, code)
        values = s.values_for_periods(row_obj, statement, periods)
        rows.append(s.row(f"ce-summary:{code}", [display_label, *values],
                          [None, *(["eur"] * len(values))]))
    return s.table("ce-summary", "Conto economico · sintesi", columns, rows)


def _ce(report: FinalReportModelV2) -> dict[str, Any]:
    statement = s.statement_by_id(report, "income_statement")
    periods = s.forecast_periods(statement)  # «CE previsionale = anni di piano», m2-02d.md
    kpis = [kpi for kpi in (
        s.kpi_forecast(report, "income_statement",
                       ("ce01_ricavi_vendite", "revenue", "production_value"), "ricavi"),
        s.kpi_forecast(report, "income_statement", ("ebitda",), "EBITDA"),
        s.kpi_indicator(report, "practice.ebitda_margin", "margine EBITDA"),
        s.kpi_forecast(report, "income_statement", ("net_profit", "profit_after_tax"), "utile netto"),
    ) if kpi is not None]
    # «Evoluzione dei margini»: due indicatori reali (non una formula nuova),
    # limitati agli anni di piano. `analytical.profitability.ros` è il
    # margine operativo (EBIT/ricavi) già nel catalogo indicatori — nessun
    # calcolo qui, solo una finestra sui periodi che la pagina racconta.
    chart = s.indicator_chart(report, "ce-margini", "Evoluzione dei margini", "percent", periods,
        ["practice.ebitda_margin", "analytical.profitability.ros"])
    items: list[dict[str, Any]] = []
    block = s.chart_block("ce-margini", "Evoluzione dei margini", chart, kpis)
    if block is not None:
        items.append(block)
    items.append(_ce_summary_table(report, statement, periods))
    return {"id": "ce", "title": "Conto economico previsionale", "family": FAMILY,
            "subtitle": "Gli anni di piano sono confrontati sulla medesima base annuale.",
            "kpis": [] if block is not None else kpis, "items": items}


def build(report: FinalReportModelV2) -> list[dict[str, Any]]:
    return [_ce(report)]
