"""Low-level, renderer-neutral helpers shared by every page group of the dossier
catalog. Pure projection of `FinalReportModelV2`: no calculation, no rounding
beyond string formatting, no invented values. A page group module (`apertura.py`,
`piano.py`, ...) composes these into `PageSpec` dicts; nothing here decides which
pages exist — see `dossier_catalog/__init__.py` for the catalog itself.
"""
from __future__ import annotations

import json
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.schemas.final_report_v2 import FinalReportModelV2

# ── Forme di pagina e `kind` dei grafici (M2-02G fase 2, traccia A) ─────────
# Il contratto di pagina (`contracts/dossier_page_contract.json`) vincola,
# oltre alla sequenza dei blocchi, la FORMA di ciascun grafico e la forma di
# ciascuna pagina. Il catalogo le dichiarava implicitamente: bar/line si
# decideva dalla sola lista `bars` di `chart-layout.json`, e il KPI era o
# della pagina o del grafico. Qui stanno le costanti dell'unico punto che le
# risolve; la resa è in `pagine/comuni.typ`/`charts.typ`.
#
# Le larghezze sono vincolate dalla geometria del bundle (`chart-layout.json`:
# 178 × 94 mm, e `chart_components._dimensions` non accetta chiavi nuove):
# ogni grafico è alto 94 mm e largo quanto la colonna in cui sta.
CHART_KINDS = ("bar", "line", "stacked", "dumbbell")
PAGE_FORMS = ("cover", "single", "rail+main", "full+panels")
CHART_WIDTH_FULL_MM = "178"      # nessuna colonna accanto
CHART_WIDTH_KPI_MM = "118"       # colonna KPI da 55 mm a sinistra del grafico
CHART_WIDTH_RAIL_MM = "126"      # rail di pagina da 47 mm + gutter da 5 mm
CHART_WIDTH_PANEL_MM = "86"      # due pannelli affiancati + gutter da 6 mm
RAIL_WIDTH_MM = "47"

_CHART_LAYOUT_PATH = (Path(__file__).resolve().parents[1]
                      / "templates" / "dossier-base" / "chart-layout.json")


@lru_cache(maxsize=1)
def _layout_bars() -> frozenset[str]:
    """La lista `bars` del bundle, come ripiego per un item che non dichiara
    alcun `kind`. Non è più la fonte della verità: è il comportamento storico
    di chi non ha ancora adeguato la propria pagina."""
    raw = json.loads(_CHART_LAYOUT_PATH.read_text(encoding="utf-8"))
    return frozenset(raw["bars"])


def chart_kind(chart: dict[str, Any], kind: str | None = None) -> str:
    """Il `kind` effettivo di un grafico: quello dichiarato (dall'item o dal
    `chart` stesso), altrimenti il ripiego storico della lista `bars`.
    Una chiave `bars` non è più letta dal template se il kind è dichiarato."""
    declared = kind if kind is not None else chart.get("kind")
    if declared is None:
        return "bar" if chart.get("id") in _layout_bars() else "line"
    if declared not in CHART_KINDS:
        raise ValueError(f"unknown chart kind: {declared!r} (expected one of {CHART_KINDS})")
    return declared


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
                    periods: list[Any], indicator_ids: list[str],
                    kind: str | None = None) -> dict[str, Any] | None:
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
    chart = {"id": chart_id, "title": title, "unit": unit, "categories": axis,
             "series": series, "indicator_ids": references, "thresholds": thresholds}
    chart["kind"] = chart_kind(chart, kind)
    return chart


def statement_chart(report: FinalReportModelV2, statement_id: str, chart_id: str, title: str, unit: str,
                    periods: list[Any], rows: list[tuple[str, str]],
                    kind: str | None = None) -> dict[str, Any] | None:
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
    chart = {"id": chart_id, "title": title, "unit": unit, "categories": axis,
             "series": series, "indicator_ids": [], "thresholds": []}
    chart["kind"] = chart_kind(chart, kind)
    return chart


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
                      named_series: list[tuple[str, list[Any]]],
                      kind: str | None = None) -> dict[str, Any] | None:
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
    chart = {"id": chart_id, "title": title, "unit": unit, "categories": axis,
             "series": series, "indicator_ids": [], "thresholds": []}
    chart["kind"] = chart_kind(chart, kind)
    return chart


#: Altezza del riquadro grafico. Quella piena è la geometria base di
#: `chart-layout.json`; la ridotta serve alle pagine che ne mettono DUE in
#: colonna più una tavola — due riquadri da 94 mm non stanno in un foglio, e
#: la v4 infatti li disegna più bassi (misurato: con 94 il dossier passava da
#: 33 a 38 pagine fisiche).
CHART_HEIGHT_FULL_MM = "94"
CHART_HEIGHT_COMPACT_MM = "58"


def chart_marker_height_mm(item: dict[str, Any]) -> str:
    """Altezza del grafico in millimetri, dichiarata dalla forma di pagina.
    Senza dichiarazione vale la geometria base, come prima di M2-02G."""
    declared = item.get("height_mm")
    return str(declared) if declared is not None else CHART_HEIGHT_FULL_MM


def chart_marker_width_mm(item: dict[str, Any]) -> str:
    """Larghezza del grafico, in millimetri, per la pagina tipo.
    La fonte è `width_mm`, cioé la colonna che la forma di pagina (`form`) gli
    ha assegnato: 126 mm dentro un rail da 47, 86 mm in un pannello, 118 mm con
    la colonna KPI del solo grafico, 178 mm senza nulla accanto. Il ripiego
    alla vecchia maniera (colonna KPI sì/no) resta per un item costruito fuori
    dal catalogo, mai per una pagina che dichiari una forma."""
    declared = item.get("width_mm")
    if declared is not None:
        return str(declared)
    return CHART_WIDTH_KPI_MM if item.get("kpis") else CHART_WIDTH_FULL_MM


def chart_block(chart_id: str, title: str, chart: dict[str, Any] | None,
                kpis: list[dict[str, Any] | None], kind: str | None = None) -> dict[str, Any] | None:
    """Il blocco grafico di pagina. `kind` è la forma del grafico (bar · line ·
    stacked · dumbbell): un item che non lo dichiara ottiene il ripiego della
    lista `bars`, dichiarato qui una volta sola perché Typst legga sempre un
    `chart.kind` esplicito e non debba indovinarlo."""
    if chart is None:
        return None
    view = dict(chart)
    view["kind"] = chart_kind(view, kind)
    shown_kpis = [item for item in kpis if item is not None]
    return {"id": f"chart:{chart_id}", "kind": "chart", "title": title,
            "chart_id": chart_id, "chart": view, "kpis": shown_kpis}


def panel_grid(identifier: str, title: str, items: list[dict[str, Any]],
               panels: int = 2) -> dict[str, Any] | None:
    """Due (o `panels`) grafici affiancati a metà larghezza: la forma `full+panels`
    delle pagine 13 e 16 della v4. I figli restano block-chart normali — cadauno
    con il proprio `content_id`, la propria misura e la propria dichiarazione
    Python — perché il piano editoriale e il probe di layout non hanno una
    seconda anagrafe dei pannelli. Meno di due figli non sono un pannello: None,
    gli item restano blocchi autonomi."""
    shown = [item for item in items if item is not None]
    if len(shown) < 2:
        return None
    return {"id": f"panel:{identifier}", "kind": "panel", "title": title, "panels": panels, "items": shown}


# ── Short period headers + basis legend (Allegati, M2-02D fase 2) ───────────
# `period_label` ("2026 chiusura stimata (12 mesi)") wraps onto several lines
# in a 5-column table — measured on Allegati A-C before this fix. The short
# form carries a letter + year, with the legend spelled out once in the page
# subtitle via `period_basis_legend`, never repeated per column.

_BASIS_LETTERS = {"historical": "S", "observed": "O", "adjusted": "R", "closing": "C", "forecast": "P"}


def period_label_short(period: Any) -> str:
    """`<year> <letter>` (v4: `2026 C`, `2027 P`), with a leading `<N>M `
    only for a genuinely partial period (`period_months` below 12) — read
    from the model, never a hardcoded "9M"."""
    letter = _BASIS_LETTERS.get(period.basis, period.basis[:1].upper())
    months = f"{period.period_months}M " if period.period_months is not None and period.period_months < 12 else ""
    return f"{months}{period.year} {letter}"


def period_basis_legend(periods: list[Any]) -> str:
    """The letters used by `period_label_short` on this exact column set,
    spelled out once (`BASIS_LABELS`), in order of first appearance."""
    seen: list[str] = []
    for period in periods:
        if period.basis not in seen:
            seen.append(period.basis)
    return "; ".join(f"{_BASIS_LETTERS.get(basis, basis[:1].upper())}: {BASIS_LABELS.get(basis, basis)}"
                     for basis in seen)


def select_periods_with_adjusted(periods: list[Any], max_periods: int = 5) -> list[Any]:
    """Like `select_periods`, but keeps `basis == 'adjusted'` (the infrannuale
    progressivo rettificato) when the statement has one — Allegato F (v4
    pagina 30) tells the practice's own indicators through the partial
    period too, unlike Allegati A-C/G which show only chiusura/storico +
    piano. A workflow without an adjusted period degrades to exactly what
    `select_periods` would return."""
    forecast = sorted((p for p in periods if p.basis == "forecast"), key=lambda p: p.year)
    closings = sorted((p for p in periods if p.basis == "closing"), key=lambda p: p.year)
    historicals = sorted((p for p in periods if p.basis == "historical"), key=lambda p: p.year)
    adjusted = sorted((p for p in periods if p.basis == "adjusted"), key=lambda p: p.year)
    anchor = closings[-1] if closings else (historicals[-1] if historicals else None)
    selected = adjusted[-1:] + ([anchor] if anchor is not None else []) + forecast
    return selected[-max_periods:] if len(selected) > max_periods else selected


def indicator_object_values_for_periods(indicator: Any, periods: list[Any]) -> list[Any]:
    """Come `indicator_values_for_periods`, ma a partire dall'oggetto indicatore
    già risolto invece che dal suo identificativo: le due firme nascono da due
    gruppi del catalogo (allegati e piano) e restano distinte per non costringere
    chi ha già l'oggetto a ricercarlo di nuovo per id."""
    by_id = {period.id: value for period, value in zip(indicator.periods, indicator.values)}
    return [by_id.get(period.id) for period in periods]


# ── Value + unit in the same cell (Allegati E/F/G) ───────────────────────────
# `cell()` (comuni.typ) only special-cases `unit == "eur"`; a bare "percent"/
# "days"/"ratio" table cell would print the raw digits with no suffix. Rather
# than touch that shared component, the suffix is baked into the string here
# (Decimal-exact, never a float) and sent through as a plain token — `cell()`
# already renders an arbitrary string verbatim when `unit` is `None`.

_UNIT_SUFFIX = {"percent": "%", "days": " gg", "ratio": "×", "score": " punti"}
_UNIT_PLACES = {"percent": 2, "days": 2, "ratio": 2, "score": 1}


def format_unit(value: Any, unit: str) -> str | None:
    """`7,57×`, `17,75%`, `228,12 gg` — unit in the value's own cell, never in
    parentheses in the row label (owner's decision, Allegati F/G). Rounds an
    exact `Decimal` (never a float) to the unit's own precision, Italian
    locale (comma decimal, dot thousands). `unit == "eur"` is not handled
    here: those cells go through the usual `row`/`cell` path instead, in
    whole euros, exactly like Allegati A-C."""
    if value is None:
        return None
    places = _UNIT_PLACES.get(unit, 2)
    quant = Decimal(1).scaleb(-places)
    rounded = Decimal(value).quantize(quant, rounding=ROUND_HALF_UP)
    negative = rounded < 0
    text = f"{abs(rounded):,.{places}f}"
    text = text.replace(",", "").replace(".", ",").replace("", ".")
    sign = "−" if negative else ""
    return f"{sign}{text}{_UNIT_SUFFIX.get(unit, '')}"
