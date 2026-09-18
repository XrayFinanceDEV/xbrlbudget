"""Low-level, renderer-neutral helpers shared by every page group of the dossier
catalog. Pure projection of `FinalReportModelV2`: no calculation, no rounding
beyond string formatting, no invented values. A page group module (`apertura.py`,
`piano.py`, ...) composes these into `PageSpec` dicts; nothing here decides which
pages exist — see `dossier_catalog/__init__.py` for the catalog itself.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.schemas.final_report_v2 import FinalReportModelV2

# ── Value formatting ─────────────────────────────────────────────────────────


def exact(value: Any) -> str | None:
    """Preserve canonical Decimal precision; never pass a float to Typst."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, bool):
        return "sì" if value else "no"
    return str(value)


def missing(reason: str | None) -> str | None:
    return None if not reason else f"n.d.: {reason}"


def label(mapping: dict[str, str], value: Any) -> Any:
    if value is None:
        return None
    return mapping.get(str(value), str(value))


BASIS_LABELS = {
    "historical": "storico", "observed": "osservato", "adjusted": "rettificato",
    "closing": "chiusura", "forecast": "previsione di piano",
}


def period_label(period: Any) -> str:
    suffix = f" ({period.period_months} mesi)" if period.period_months is not None else ""
    return f"{period.label}{suffix}"


# ── Rows and tables ──────────────────────────────────────────────────────────


def row(identifier: str, cells: list[Any], units: list[str | None] | None = None) -> dict[str, Any]:
    rendered = [exact(value) for value in cells]
    unit_values = units if units is not None else [None] * len(rendered)
    if len(rendered) != len(unit_values):
        raise ValueError("dossier table row has mismatched cells and units")
    return {"id": identifier, "cells": rendered, "units": list(unit_values)}


def table(identifier: str, title: str, columns: list[str], rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        rows = [row(f"{identifier}:empty", ["n.d.: nessun dato disponibile"] + [None] * (len(columns) - 1))]
    if any(len(item["cells"]) != len(columns) or len(item["units"]) != len(columns) for item in rows):
        raise ValueError("dossier table rows must follow columns")
    return {"id": identifier, "kind": "table", "title": title, "columns": columns, "rows": rows}


def text(identifier: str, title: str, body: str) -> dict[str, Any]:
    return {"id": identifier, "kind": "text", "title": title, "text": body or "n.d.: testo non disponibile"}


def note(identifier: str, body: str) -> dict[str, Any]:
    return {"id": identifier, "kind": "note", "text": body or "n.d.: nota non disponibile"}


# ── KPI ───────────────────────────────────────────────────────────────────────
# A KPI the model does not supply is omitted entirely (never printed as "n.d.").


def kpi(text_label: str, value: Any, unit: str | None = None, to: Any = None) -> dict[str, Any] | None:
    if value is None and to is None:
        return None
    return {"label": text_label, "value": exact(value), "to": exact(to), "unit": unit, "series": None}


def kpi_series(text_label: str, values: list[Any], unit: str | None) -> dict[str, Any] | None:
    shown = [value for value in values if value is not None]
    if not shown:
        return None
    return {"label": text_label, "value": None, "to": None, "unit": unit, "series": [exact(value) for value in shown]}


def indicator_by_id(report: FinalReportModelV2, identifier: str) -> Any:
    for indicator in report.indicator_catalog:
        if indicator.id == identifier:
            return indicator
    return None


def kpi_indicator(report: FinalReportModelV2, identifier: str, desc: str, mode: str = "last") -> dict[str, Any] | None:
    """KPI read off `indicator_catalog`: `mode` picks the last value, the full
    per-period series, or a "first -> last" pair (arrow display)."""
    indicator = indicator_by_id(report, identifier)
    if indicator is None:
        return None
    pairs = [(period, value) for period, value in zip(indicator.periods, indicator.values) if value is not None]
    if not pairs:
        return None
    if mode == "series":
        return kpi_series(f"{desc} · per periodo", [value for _, value in pairs], indicator.unit)
    if mode == "first_last" and len(pairs) > 1:
        (first_period, first), (last_period, last) = pairs[0], pairs[-1]
        if first == last:
            return kpi(f"{desc} · {last_period.year}", last, indicator.unit)
        return kpi(f"{desc} · {first_period.year}–{last_period.year}", first, indicator.unit, to=last)
    period, value = pairs[-1]
    return kpi(f"{desc} · {period.year}", value, indicator.unit)


def kpi_forecast(report: FinalReportModelV2, attribute: str, codes: tuple[str, ...], desc: str,
                 *, which: str = "last") -> dict[str, Any] | None:
    years = report.forecast.years[-1:] if which == "last" else report.forecast.years[:1]
    for year in years:
        for line in getattr(year, attribute):
            if line.code in codes and line.value is not None:
                return kpi(f"{desc} · {year.year}", line.value, "eur")
    return None


def kpi_closing(report: FinalReportModelV2, codes: tuple[str, ...], desc: str,
                attribute: str = "closing_used") -> dict[str, Any] | None:
    closing = report.infrannual_closing
    if closing is None:
        return None
    for value in closing.values:
        if value.code in codes and getattr(value, attribute) is not None:
            return kpi(f"{desc} · chiusura {closing.period_end.year}", getattr(value, attribute), "eur")
    return None


def kpi_revenue_now(report: FinalReportModelV2) -> dict[str, Any] | None:
    """Ricavi di riferimento: la chiusura attesa, altrimenti il primo anno di piano."""
    return (kpi_closing(report, ("ce01_ricavi_vendite", "revenue"), "ricavi")
            or kpi_forecast(report, "income_statement",
                            ("revenue", "ce01_ricavi_vendite", "production_value"), "ricavi", which="first"))


def kpi_horizon(report: FinalReportModelV2) -> dict[str, Any] | None:
    years = report.practice.periods.forecast_years
    if not years:
        return None
    if len(years) == 1:
        return kpi("orizzonte di piano", "1 anno")
    return kpi("orizzonte di piano", f"{len(years)} anni · {years[0]}–{years[-1]}")


def statement_row(statement: Any, code: str) -> Any:
    """A row from a `DetailedStatement` by its bare `code` (e.g.
    `ce01_ricavi_vendite`, `ebitda`, `net_profit` — never the id, which
    already carries the statement prefix: `income_statement:ebitda`).
    Raises if the code is not on the statement — a page must never silently
    render nothing for a wrong code."""
    for candidate in statement.rows:
        if candidate.code == code:
            return candidate
    raise ValueError(f"no row with code {code!r} on statement {statement.id!r}")


def statement_by_id(report: FinalReportModelV2, statement_id: str) -> Any:
    for statement in report.detailed_statements:
        if statement.id == statement_id:
            return statement
    raise ValueError(f"no detailed statement {statement_id!r}")


def forecast_periods(statement: Any) -> list[Any]:
    """Plan years only, in period order — used by section pages (CE/SP/Flussi)
    that show only the years of the plan, never historical/observed/closing."""
    return [period for period in statement.periods if period.basis == "forecast"]


_BASIS_RANK = {"historical": 0, "observed": 1, "adjusted": 2, "closing": 3, "forecast": 4}


def select_periods(periods: list[Any], max_periods: int = 5) -> list[Any]:
    """Colonne del vincolo (2026-09-17): chiusura, o in mancanza l'ultimo
    esercizio storico, più gli anni di piano — mai storico, osservato e
    rettificato insieme (quelli stanno nelle pagine 3-5). Con `max_periods`
    anni di piano l'ancora esce e restano solo quelli: l'ancora si prepone e
    l'elenco si taglia mantenendo la coda, così il piano non perde mai un anno."""
    forecast = sorted((p for p in periods if p.basis == "forecast"), key=lambda p: p.year)
    closings = sorted((p for p in periods if p.basis == "closing"), key=lambda p: p.year)
    historicals = sorted((p for p in periods if p.basis == "historical"), key=lambda p: p.year)
    anchor = closings[-1] if closings else (historicals[-1] if historicals else None)
    selected = ([anchor] if anchor is not None else []) + forecast
    return selected[-max_periods:] if len(selected) > max_periods else selected


def values_for_periods(row_obj: Any, statement: Any, periods: list[Any]) -> list[Any]:
    """`row_obj.values`, reindexed onto a (possibly reordered/filtered)
    subset of `statement.periods` — by period id, never by position."""
    by_id = {period.id: value for period, value in zip(statement.periods, row_obj.values)}
    return [by_id.get(period.id) for period in periods]


# ── Period-aligned indicator chart, scoped to a chosen set of periods ───────
# Unlike a global chart keyed only by id, a page-scoped chart is built once,
# in Python, from real `indicator_catalog` entries restricted to the periods
# the page tells: no re-derivation, only a different window on the same data.

def indicator_chart(report: FinalReportModelV2, chart_id: str, title: str, unit: str,
                    periods: list[Any], indicator_ids: list[str]) -> dict[str, Any] | None:
    axis = [str(period.year) for period in periods]
    series: list[dict[str, Any]] = []
    references: list[str] = []
    for identifier in indicator_ids:
        indicator = indicator_by_id(report, identifier)
        if indicator is None:
            continue
        by_period = {period.id: value for period, value in zip(indicator.periods, indicator.values)}
        values = [by_period.get(period.id) for period in periods]
        if not any(value is not None for value in values):
            continue
        series.append({"label": indicator.label, "values": [exact(value) for value in values]})
        references.append(identifier)
    if not series:
        return None
    thresholds = [{"label": indicator_by_id(report, ref).label + " · " + threshold.label,
                   "value": format(threshold.value, "f"), "source": threshold.source}
                  for ref in references for threshold in indicator_by_id(report, ref).thresholds]
    return {"id": chart_id, "title": title, "unit": unit, "categories": axis,
            "series": series, "indicator_ids": references, "thresholds": thresholds}


def statement_chart(report: FinalReportModelV2, statement_id: str, chart_id: str, title: str, unit: str,
                    periods: list[Any], rows: list[tuple[str, str]]) -> dict[str, Any] | None:
    """A chart drawn directly from `DetailedStatement` row values (euro
    amounts), never from a derived indicator. `rows` is a list of
    `(row_id, display_label)`; a row absent for every chosen period is
    dropped rather than shown empty."""
    statement = statement_by_id(report, statement_id)
    axis = [str(period.year) for period in periods]
    series: list[dict[str, Any]] = []
    for row_id, display_label in rows:
        row_obj = statement_row(statement, row_id)
        values = values_for_periods(row_obj, statement, periods)
        if not any(value is not None for value in values):
            continue
        series.append({"label": display_label, "values": [exact(value) for value in values]})
    if not series:
        return None
    return {"id": chart_id, "title": title, "unit": unit, "categories": axis,
            "series": series, "indicator_ids": [], "thresholds": []}


def appendix_table_rows(statement: Any, periods: list[Any]) -> list[dict[str, Any]]:
    """One row per `DetailedStatementRow`, values reindexed onto `periods`.
    A `section`/`group` header row never carries a value (never "n.d." either
    — an empty cell, exactly as the statement itself declares it). Row ids
    follow `row:<statement_id>:<row_id>` — `editorial_plan.py` reconstructs
    which physical page holds which appendix row from this exact convention."""
    rows_out: list[dict[str, Any]] = []
    for row_obj in statement.rows:
        header = row_obj.kind in ("section", "group")
        if header:
            cells = [row_obj.label, *([""] * len(periods))]
            units: list[str | None] = [None] * (1 + len(periods))
        else:
            values = values_for_periods(row_obj, statement, periods)
            cells = [row_obj.label, *values]
            units = [None, *(["eur"] * len(values))]
        rows_out.append(row(f"row:{statement.id}:{row_obj.id}", cells, units))
    return rows_out


def index_block(identifier: str, title: str, entries: list[dict[str, str]]) -> dict[str, Any]:
    """A link-list block (v4 «Allegati · indice dei prospetti»): each entry is
    `{"label": ..., "target": <content_id>}`; Typst resolves the target's
    physical page live via `query(metadata)`, so Python never has to know
    page numbers in advance."""
    return {"id": identifier, "kind": "index", "title": title, "entries": entries}


def chunk(sequence: list[Any], size: int) -> list[list[Any]]:
    return [sequence[i:i + size] for i in range(0, len(sequence), size)]


# ── Piano e risultati (v4 pagine 7-10): KPI/valori letti da più di una fonte ──
# Aggiunte in fondo al file, come richiesto dalla regola comune della fase: un
# helper qui solo se serve a più pagine — questi servono a «ipotesi», «sp» e
# «flussi» (e, per `kpi_statement`, alla correzione dei due KPI di «ce»
# descritta sotto), non a una pagina sola.
#
# `kpi_forecast` legge SOLO i campi grezzi persistiti (`sp*`/`ce*`, colonne
# vere della tabella ORM): un aggregato come `ebitda`, `net_profit` o
# `total_assets` è una `@property` Python su `ForecastIncomeStatement`/
# `ForecastBalanceSheet`, mai una colonna — `kpi_forecast(report,
# "income_statement", ("ebitda",), ...)` non trova mai un codice "ebitda" fra
# le righe grezze di un report reale e ritorna sempre `None` (silenziosamente
# omesso, mai un errore: verificato su AMBIENTA/575, scenario 18 — la pagina
# «ce» mostrava così solo 2 dei 4 KPI dichiarati). Un aggregato vive già,
# corretto, in `detailed_statements` (`build_detailed_statements` lo arricchisce
# con `calculate_ce_result`/`balance_aggregates`): `kpi_statement` legge da lì.


def kpi_statement(report: FinalReportModelV2, statement_id: str, code: str, desc: str,
                  *, basis: str = "forecast", which: str = "last") -> dict[str, Any] | None:
    """KPI da una riga di `detailed_statements` (aggregati compresi, a
    differenza di `kpi_forecast`) al primo/ultimo periodo del `basis` dato.
    Nessun valore inventato: un periodo senza valore è saltato, mai un altro
    periodo al suo posto."""
    statement = statement_by_id(report, statement_id)
    row_obj = statement_row(statement, code)
    periods = [period for period in statement.periods if period.basis == basis]
    if not periods:
        return None
    period = periods[-1] if which == "last" else periods[0]
    value = values_for_periods(row_obj, statement, [period])[0]
    if value is None:
        return None
    return kpi(f"{desc} · {period.year}", value, "eur")


def structure_group_by_id(report: FinalReportModelV2, group_id: str) -> Any:
    for group in report.structure_series:
        if group.id == group_id:
            return group
    raise ValueError(f"no structure series group {group_id!r}")


def structure_values_for_periods(report: FinalReportModelV2, group_id: str, series_id: str,
                                 periods: list[Any]) -> list[Any]:
    """Come `values_for_periods`, ma per una serie di `structure_series`
    (`composition_sources.financial_debt`, ...): la pagina che compone un
    grafico misto (una riga di prospetto + una serie strutturale, mai un
    secondo calcolo) legge da qui e da `values_for_periods` con la stessa
    finestra di periodi."""
    group = structure_group_by_id(report, group_id)
    series_obj = next((series for series in group.series if series.id == series_id), None)
    if series_obj is None:
        return [None] * len(periods)
    by_id = {period.id: value for period, value in zip(group.periods, series_obj.values)}
    return [by_id.get(period.id) for period in periods]


def kpi_structure(report: FinalReportModelV2, group_id: str, series_id: str, desc: str,
                  *, basis: str = "forecast", which: str = "last") -> dict[str, Any] | None:
    group = structure_group_by_id(report, group_id)
    series_obj = next((series for series in group.series if series.id == series_id), None)
    if series_obj is None:
        return None
    candidates = [(period, value) for period, value in zip(group.periods, series_obj.values)
                 if period.basis == basis and value is not None]
    if not candidates:
        return None
    period, value = candidates[-1] if which == "last" else candidates[0]
    return kpi(f"{desc} · {period.year}", value, series_obj.unit)


def indicator_values_for_periods(report: FinalReportModelV2, identifier: str, periods: list[Any]) -> list[Any] | None:
    """Come `values_for_periods`, per un indicatore di `indicator_catalog`:
    la finestra di periodi la sceglie la pagina, mai un `basis` implicito —
    stesso principio del filtro già dentro `indicator_chart`, qui riusabile
    anche per una riga di tabella o un KPI a serie (`kpi_indicator_periods`)."""
    indicator = indicator_by_id(report, identifier)
    if indicator is None:
        return None
    by_id = {period.id: value for period, value in zip(indicator.periods, indicator.values)}
    return [by_id.get(period.id) for period in periods]


def kpi_indicator_periods(report: FinalReportModelV2, identifier: str, desc: str,
                          periods: list[Any]) -> dict[str, Any] | None:
    """KPI a serie di un indicatore, ristretto esplicitamente ai `periods`
    dati — a differenza di `kpi_indicator(mode="series")`, che prende TUTTI i
    periodi disponibili dell'indicatore (storico/osservato/rettificato/
    chiusura compresi sull'infrannuale): qui la pagina decide la finestra,
    come già fa `indicator_chart` per un grafico."""
    indicator = indicator_by_id(report, identifier)
    if indicator is None:
        return None
    values = indicator_values_for_periods(report, identifier, periods)
    return kpi_series(desc, values, indicator.unit)


def assumption_section_by_key(report: FinalReportModelV2, key: str) -> Any:
    for section in report.assumption_sections:
        if section.key == key:
            return section
    raise ValueError(f"no assumption section {key!r}")


def assumption_value(section: Any, field: str) -> Any:
    """`None` se il campo non è fra le ipotesi lette per questa sezione (mai
    un errore): non ogni campo del catalogo ha un valore per ogni scenario."""
    for assumption in section.assumptions:
        if assumption.field == field:
            return assumption
    return None


def chart_from_series(chart_id: str, title: str, unit: str, periods: list[Any],
                      named_series: list[tuple[str, list[Any]]]) -> dict[str, Any] | None:
    """Un grafico composto da serie già risolte dal chiamante (righe di
    prospetto, valori di `structure_series`, indicatori — qualunque
    combinazione): a differenza di `statement_chart`/`indicator_chart`, che
    leggono ciascuno una sola fonte, questo è il punto di composizione
    quando un grafico ha bisogno di più di una fonte insieme (es. «Patrimonio
    e indebitamento»: una riga di SP + una serie di `structure_series`). Una
    serie assente su ogni periodo si scarta, come nei costruttori a fonte
    singola."""
    axis = [str(period.year) for period in periods]
    series: list[dict[str, Any]] = []
    for label, values in named_series:
        if not any(value is not None for value in values):
            continue
        series.append({"label": label, "values": [exact(value) for value in values]})
    if not series:
        return None
    return {"id": chart_id, "title": title, "unit": unit, "categories": axis,
            "series": series, "indicator_ids": [], "thresholds": []}


def chart_marker_width_mm(item: dict[str, Any]) -> str:
    """Pagina tipo: il grafico con colonna KPI occupa 118 mm (colonna 55 mm +
    gutter), senza KPI resta a 178 — geometria dichiarata dalla stessa fonte
    che il piano editoriale rivalida."""
    return '118' if item.get("kpis") else '178'


def chart_block(chart_id: str, title: str, chart: dict[str, Any] | None,
                kpis: list[dict[str, Any] | None]) -> dict[str, Any] | None:
    if chart is None:
        return None
    shown_kpis = [item for item in kpis if item is not None]
    return {"id": f"chart:{chart_id}", "kind": "chart", "title": title,
            "chart_id": chart_id, "chart": chart, "kpis": shown_kpis}
