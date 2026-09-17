"""Renderer-neutral, lossless editorial content inventory for the Typst dossier.

This module deliberately only projects the canonical report.  It does not
calculate, round, annualise, or infer financial information.
"""
from __future__ import annotations

from collections import OrderedDict
from decimal import Decimal
from typing import Any

from app.schemas.final_report_v2 import FinalReportModelV2


SECTION_IDS = (
    "cover", "executive_summary", "source_data_quality", "adjustments",
    "infrannual_closing", "budget_assumptions", "income_statement_forecast",
    "balance_sheet_forecast", "cashflow_sustainability", "indicators",
    "diagnostics_actions", "appendices_methodology",
)

_SECTION_TITLES = {
    "cover": "Copertina",
    "executive_summary": "Sintesi esecutiva",
    "source_data_quality": "Bilancio infrannuale e fonti",
    "adjustments": "Rettifiche apportate",
    "infrannual_closing": "Dall'infrannuale alla chiusura",
    "budget_assumptions": "Ipotesi del piano",
    "income_statement_forecast": "Conto economico previsionale",
    "balance_sheet_forecast": "Stato patrimoniale previsionale",
    "cashflow_sustainability": "Flussi di cassa e sostenibilità",
    "indicators": "Indicatori del piano",
    "diagnostics_actions": "Diagnostica e punti da verificare",
    "appendices_methodology": "Allegati e metodologia",
}

# Occhiello v4: una famiglia editoriale per pagina, seguita dal numero di pagina
# fisica (es. «SINTESI · 02», «DATI DI PARTENZA · 04»). M-2-0-2B, 2026-09-17.
_SECTION_FAMILY = {
    "cover": None,
    "executive_summary": "Sintesi",
    "source_data_quality": "Dati di partenza",
    "adjustments": "Dati di partenza",
    "infrannual_closing": "Dati di partenza",
    "budget_assumptions": "Piano e risultati",
    "income_statement_forecast": "Piano e risultati",
    "balance_sheet_forecast": "Piano e risultati",
    "cashflow_sustainability": "Piano e risultati",
    "indicators": "Piano e risultati",
    "diagnostics_actions": "Piano e risultati",
    "appendices_methodology": "Allegati",
}

# Sottotitolo di metodo, statico per pagina: descrive la convenzione di lettura,
# mai un numero (il titolo-messaggio arriva dal commento AI, non da qui).
_SECTION_SUBTITLES = {
    "cover": None,
    "executive_summary": "I dati osservati, la chiusura attesa e gli anni di piano sono tenuti distinti in tutto il dossier.",
    "source_data_quality": "Il bilancio di verifica e le sue fonti, con durate e stato di ciascun periodo.",
    "adjustments": "Le rettifiche confermate e il loro effetto sui valori di partenza, con le contropartite.",
    "infrannual_closing": "Il progressivo rettificato, la stima del periodo mancante e la chiusura attesa.",
    "budget_assumptions": "Le ipotesi sono presentate per anno e per area, con provenienza ed efficacia.",
    "income_statement_forecast": "Gli anni di piano sono confrontati sulla medesima base annuale.",
    "balance_sheet_forecast": "Il prospetto evidenzia impieghi e fonti, mantenendo separati liquidità e debiti finanziari.",
    "cashflow_sustainability": "I flussi sono rappresentati con segno: entrate positive, uscite negative.",
    "indicators": "PFN = debiti finanziari meno disponibilità liquide. Percentuali, importi e rapporti non sono mai mescolati nello stesso grafico.",
    "diagnostics_actions": "Controlli di quadratura e diagnostiche del modello, distinti dalle valutazioni.",
    "appendices_methodology": "I prospetti completi e le metodologie degli indicatori, con il registro delle fonti.",
}

_NARRATIVE_SECTION = {
    "executive_summary": "executive_summary",
    "adjustments_and_closing": "adjustments",
    "budget_assumptions": "budget_assumptions",
    "economic_outlook": "income_statement_forecast",
    "financial_outlook": "balance_sheet_forecast",
    "risks_and_actions": "diagnostics_actions",
}

# Il titolo stampato dei blocchi narrativi: l'ID tecnico non compare nel
# documento e il testo resta quello autoritativo del modello (M2-02B difetto 3).
_NARRATIVE_TITLES = {
    "executive_summary": "Sintesi del documento",
    "adjustments_and_closing": "Rettifiche e raccordo alla chiusura",
    "budget_assumptions": "Ipotesi del piano",
    "economic_outlook": "Andamento economico atteso",
    "financial_outlook": "Andamento patrimoniale e finanziario atteso",
    "risks_and_actions": "Rischi e azioni",
}

_BASIS_LABELS = {
    "historical": "storico",
    "observed": "osservato",
    "adjusted": "rettificato",
    "closing": "chiusura",
    "forecast": "previsione di piano",
}

_PROVENANCE_LABELS = {
    "user": "manuale",
    "automatic": "automatica",
    "default": "default",
    "override": "da override",
    "ignored": "ignorata",
    "legacy_unknown": "non dichiarata",
}

_SEVERITY_LABELS = {"info": "informativo", "warning": "attenzione", "error": "errore"}

_QUALITY_STATUS_LABELS = {"complete": "Completa", "partial": "Parziale", "legacy": "pregressa"}

_SOURCE_LABELS = {
    "historical_financial_year": "Bilancio storico",
    "adjustments": "Registro delle rettifiche",
    "source_scenario": "Scenario di origine",
    "budget_assumptions": "Ipotesi di budget",
    "forecast": "Proiezioni di piano",
    "narrative": "Commenti del dossier",
    "calculation_engine": "Motore di calcolo",
}

_ALERT_LABELS = {
    "retribuzioni": "Fondo retributi",
    "fornitori": "Fondo fornitori",
    "banche": "Debiti bancari",
    "inps": "Debiti INPS",
    "inail": "Debiti INAIL",
    "riscossione": "Cartelle di riscossione",
    "iva": "IVA da versare",
}

_TEMPORARY_KIND_LABELS = {"deductible": "deducibile", "taxable": "tassabile"}
_TEMPORARY_MATURITY_LABELS = {"short": "breve", "long": "lunga"}

_UNIT_LABELS = {"eur": "euro", "percent": "%", "days": "giorni", "ratio": "volte", "score": "punti"}

# Le cause di indisponibilità sono codici canonici: qui trovano una frase in
# italiano, ciò che non è conosciuto resta dichiarato come tale (mai silenzioso).
_UNAVAILABLE_REASON_LABELS = {
    "zero_denominator": "denominatore nullo nel periodo",
    "non_positive_denominator": "denominatore non positivo nel periodo",
    "source_calculation_unavailable": "calcolo sorgente non disponibile",
    "model_field_unavailable": "campo non previsto dal modello",
    "source_period_unavailable": "periodo non presente nella fonte",
    "detail_not_declared": "dettaglio non dichiarato",
    "source_field_unavailable": "campo non disponibile nella fonte",
    "presentation_header": "riga di solo contesto",
}

_CLOSING_STATE_LABELS = {"observed": "osservato", "comparable": "comparabile", "automatic": "automatico", "override": "override"}

_READINESS_LABELS = {"ready": "pronto", "draft": "bozza", "blocked": "bloccato"}


def _label(mapping: dict[str, str], value: Any) -> Any:
    if value is None:
        return None
    return mapping.get(str(value), str(value))

_CHART_SECTION = {
    "income_results": "executive_summary",
    "margins": "executive_summary",
    "economic_incidence": "income_statement_forecast",
    "financial_charges": "income_statement_forecast",
    "liquidity_debt": "balance_sheet_forecast",
    "cashflows": "cashflow_sustainability",
    "coverage": "cashflow_sustainability",
    # Le pagine 11-15 della v4 sono tutte «indicatori»: i grafici degli indici
    # stanno nella sezione indicatori, non distribuiti sulle sezioni di CE/SP/flussi.
    "structural_balance": "indicators",
    "working_capital_days": "indicators",
    "practice_liquidity": "indicators",
    "practice_profitability": "indicators",
    "practice_asset_coverage": "indicators",
    "practice_net_debt": "indicators",
    "practice_net_debt_ebitda": "indicators",
    "practice_dscr_proxy": "indicators",
    "analytical_liquidity": "indicators",
}


def _exact(value: Any) -> str | None:
    """Preserve canonical Decimal precision; never pass a float to Typst."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, bool):
        return "sì" if value else "no"
    return str(value)


def _missing(reason: str | None) -> str | None:
    return None if not reason else f"n.d.: {reason}"


def _unavailability_text(entries: list[tuple[str, str]]) -> str | None:
    """Group and deduplicate what used to be one motivation line per row (or
    per row-period): reason text → the item labels it applies to, in
    first-seen order on both axes. Replaces a repeated «Indisponibilità»
    column with a single note after the table (M2-02B rilievi 3 e 6): the
    reason is never invented here, only the identical phrases the table
    already carried are grouped once."""
    grouped: "OrderedDict[str, list[str]]" = OrderedDict()
    for item_label, reason in entries:
        bucket = grouped.setdefault(reason, [])
        if item_label not in bucket:
            bucket.append(item_label)
    if not grouped:
        return None
    return " ".join(f"{reason}: {', '.join(labels)}." for reason, labels in grouped.items())


def _row(identifier: str, cells: list[Any], units: list[str | None] | None = None) -> dict[str, Any]:
    rendered = [_exact(value) for value in cells]
    unit_values = units if units is not None else [None] * len(rendered)
    if len(rendered) != len(unit_values):
        raise ValueError("editorial table row has mismatched cells and units")
    return {"id": identifier, "cells": rendered, "units": list(unit_values)}


def _table(identifier: str, title: str, columns: list[str], rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        rows = [_row(f"{identifier}:empty", ["n.d.: nessun dato disponibile"] + [None] * (len(columns) - 1))]
    if any(len(row["cells"]) != len(columns) or len(row["units"]) != len(columns) for row in rows):
        raise ValueError("editorial table rows must follow columns")
    return {"id": identifier, "kind": "table", "title": title, "columns": columns, "rows": rows}


# Numero massimo di colonne di periodo affiancate perché la tabella resti
# leggibile in verticale (M2-02B difetto 5). Oltre, `editorial.typ` divide la
# tabella in parti per gruppi di periodi e `expected_content_inventory` dichiara
# i marcatori aggiuntivi «{riga}#parte:N»: ogni parte deve poter dimostrare la
# propria copertura di pagina, e le parti non sono mai orizzontali.
PERIOD_PART_SIZE = 6
INDICATOR_PART_SIZE = 4


def _periodic_table(item: dict[str, Any], *, value_start: int, part_size: int) -> dict[str, Any]:
    item["value_start"] = value_start
    item["part_size"] = part_size
    return item


def _text(identifier: str, title: str, text: str) -> dict[str, Any]:
    return {"id": identifier, "kind": "text", "title": title, "text": text or "n.d.: testo non disponibile"}


def _period_label(period: Any) -> str:
    suffix = f" ({period.period_months} mesi)" if period.period_months is not None else ""
    return f"{period.label}{suffix}"


def _period_role(period: Any) -> str:
    """Ruolo leggibile di un periodo: l'enumerazione tecnica `basis` non si stampa."""
    return _label(_BASIS_LABELS, period.basis)


# ── KPI della pagina tipo (M2-02B) ───────────────────────────────────────────────
# Ogni valore viene dal modello v2: il template formatta soltanto. Un KPI che il
# modello non fornisce si omette (mai «n.d.» in colonna), e nessuna somma o
# scostamento è calcolato qui: conteggi di righe e valori canonici, nulla più.

def _kpi(label: str, value: Any, unit: str | None = None, to: Any = None) -> dict[str, Any] | None:
    if value is None and to is None:
        return None
    return {"label": label, "value": _exact(value), "to": _exact(to), "unit": unit, "series": None}


def _kpi_series(label: str, values: list[Any], unit: str | None) -> dict[str, Any] | None:
    shown = [value for value in values if value is not None]
    if not shown:
        return None
    return {"label": label, "value": None, "to": None, "unit": unit, "series": [_exact(value) for value in shown]}


def _indicator_by_id(report: FinalReportModelV2, identifier: str) -> Any:
    for indicator in report.indicator_catalog:
        if indicator.id == identifier:
            return indicator
    return None


def _kpi_indicator(report: FinalReportModelV2, identifier: str, desc: str, mode: str = "last") -> dict[str, Any] | None:
    indicator = _indicator_by_id(report, identifier)
    if indicator is None:
        return None
    pairs = [(period, value) for period, value in zip(indicator.periods, indicator.values) if value is not None]
    if not pairs:
        return None
    if mode == "series":
        return _kpi_series(f"{desc} · per periodo", [value for _, value in pairs], indicator.unit)
    if mode == "first_last" and len(pairs) > 1:
        (first_period, first), (last_period, last) = pairs[0], pairs[-1]
        if first == last:
            return _kpi(f"{desc} · {last_period.year}", last, indicator.unit)
        return _kpi(f"{desc} · {first_period.year}–{last_period.year}", first, indicator.unit, to=last)
    period, value = pairs[-1]
    return _kpi(f"{desc} · {period.year}", value, indicator.unit)


def _kpi_forecast(report: FinalReportModelV2, attribute: str, codes: tuple[str, ...], desc: str,
                  *, which: str = "last") -> dict[str, Any] | None:
    years = report.forecast.years[-1:] if which == "last" else report.forecast.years[:1]
    for year in years:
        for line in getattr(year, attribute):
            if line.code in codes and line.value is not None:
                return _kpi(f"{desc} · {year.year}", line.value, "eur")
    return None


def _kpi_closing(report: FinalReportModelV2, codes: tuple[str, ...], desc: str,
                 attribute: str = "closing_used") -> dict[str, Any] | None:
    closing = report.infrannual_closing
    if closing is None:
        return None
    for value in closing.values:
        if value.code in codes and getattr(value, attribute) is not None:
            return _kpi(f"{desc} · chiusura {closing.period_end.year}", getattr(value, attribute), "eur")
    return None


def _kpi_revenue_now(report: FinalReportModelV2) -> dict[str, Any] | None:
    """Ricavi di riferimento: la chiusura attesa, altrimenti il primo anno di piano."""
    return (_kpi_closing(report, ("ce01_ricavi_vendite", "revenue"), "ricavi")
            or _kpi_forecast(report, "income_statement",
                             ("revenue", "ce01_ricavi_vendite", "production_value"), "ricavi", which="first"))


def _kpi_assumption(report: FinalReportModelV2, field: str, desc: str) -> dict[str, Any] | None:
    for section in report.assumption_sections:
        for assumption in section.assumptions:
            if assumption.field == field:
                return _kpi_series(f"{desc} · per anno", list(assumption.values), _assumption_unit(field))
    return None


def _kpi_horizon(report: FinalReportModelV2) -> dict[str, Any] | None:
    years = report.practice.periods.forecast_years
    if not years:
        return None
    if len(years) == 1:
        return _kpi("orizzonte di piano", "1 anno")
    return _kpi("orizzonte di piano", f"{len(years)} anni · {years[0]}–{years[-1]}")


def _section_kpis(report: FinalReportModelV2, section_id: str) -> list[dict[str, Any]]:
    builders: dict[str, list[Any]] = {
        "cover": [
            _kpi_revenue_now(report),
            _kpi_indicator(report, "practice.ebitda_margin", "EBITDA margin"),
            _kpi_indicator(report, "practice.pfn", "PFN"),
            _kpi_horizon(report),
        ],
        "source_data_quality": [
            _kpi("data del bilancio", report.infrannual_closing.period_end if report.infrannual_closing is not None else None),
            _kpi("periodo osservato", f"{report.practice.source_scenario.period_months} mesi"
                 if report.practice.workflow_type == "infrannuale" and report.practice.source_scenario is not None
                 and report.practice.source_scenario.period_months is not None else None),
            _kpi_closing(report, ("ce01_ricavi_vendite", "revenue"), "ricavi prima delle rettifiche", attribute="observed"),
        ],
        "adjustments": [
            _kpi("rettifiche economiche", str(len(report.adjustments.entries))),
            _kpi("effetto netto sul risultato", report.adjustments.net_effect, "eur"),
        ],
        "infrannual_closing": [
            _kpi_closing(report, ("ce01_ricavi_vendite", "revenue"), "ricavi rettificati", attribute="comparable"),
            _kpi_closing(report, ("ce01_ricavi_vendite", "revenue"), "ricavi di chiusura"),
        ],
        "budget_assumptions": [
            _kpi_horizon(report),
            _kpi_assumption(report, "revenue_growth_pct", "crescita dei ricavi"),
            _kpi_indicator(report, "practice.ebitda_margin", "EBITDA margin", mode="series"),
        ],
        "diagnostics_actions": [
            _kpi("stato del documento", _label(_READINESS_LABELS, report.readiness.status)),
            _kpi("diagnostiche aperte", str(len(report.diagnostics) + len(report.readiness.reasons))),
        ],
    }
    return [kpi for kpi in builders.get(section_id, []) if kpi is not None]


# ── Vista grafico della pagina tipo (M2-02B passo 4) ────────────────────────────
# Il grafico canónico della v4 non è solo «ultimi tre anni di piano»: mostra la
# serie completa storico → osservato → chiusura → piano, e piúú serie quando il
# modello le offre. Ogni valore è letto dal modello (indicatori o righe di
# prospetto): nessuna somma, nessuna proiezione inventata.

_BASIS_ORDER = {"historical": 0, "observed": 1, "adjusted": 2, "closing": 3, "forecast": 4}
_BASIS_INITIAL = {"observed": "O", "adjusted": "R", "closing": "C", "forecast": "P"}


def _period_key(period: Any) -> tuple:
    return (period.year, period.basis, period.period_months)


def _axis_label(period: Any) -> str:
    initial = _BASIS_INITIAL.get(period.basis)
    return str(period.year) if initial is None else f"{period.year} {initial}"


def _timeline(report: FinalReportModelV2) -> list:
    keys: dict[tuple, Any] = {}
    for statement in report.detailed_statements:
        for period in statement.periods:
            keys.setdefault(_period_key(period), period)
    for indicator in report.indicator_catalog:
        for period in indicator.periods:
            keys.setdefault(_period_key(period), period)
    return sorted(keys.values(), key=lambda period: (period.year, _BASIS_ORDER[period.basis]))


# Serie dei grafici canónici v1: nessuna referenzazione di indici nel modello,
# la timeline viene letta dalle righe di prospetto e dagli indicatori omonimi.
_CANONICAL_CHART_SERIES = {
    "income_results": [("statement", "income_statement", ("ce01_ricavi_vendite", "revenue", "production_value"), "Ricavi"),
                       ("statement", "income_statement", ("ebitda",), None)],
    "margins": [("indicator", "practice.ebitda_margin")],
    "coverage": [("indicator", "practice.dscr")],
    "working_capital_days": [("indicator", "analytical.activity.receivables_turnover_days"),
                             ("indicator", "analytical.activity.inventory_turnover_days"),
                             ("indicator", "analytical.activity.payables_turnover_days")],
    "cashflows": [("statement", "cashflow", ("operating.total_operating_cashflow", "operating"), None),
                  ("statement", "cashflow", ("investing.total_investing_cashflow", "investing"), None),
                  ("statement", "cashflow", ("financing.total_financing_cashflow", "financing"), None)],
    "liquidity_debt": [("statement", "balance_sheet", ("sp09_disponibilita_liquide", "cash"), "Cassa"),
                       ("indicator", "practice.pfn"),
                       ("statement", "balance_sheet", ("sp16_debiti_breve+sp17_debiti_lungo",), None)],
}


def chart_view(report: FinalReportModelV2, chart_id: str) -> dict[str, Any] | None:
    """La vista che il template disegna e che `editorial_plan` rivailida.

    Python e Typst devono vedere la stessa identica serie: il marcatore del
    grafico riporta `categories`/`series` di questa funzione, non quelle del
    modello v1 (che fermo agli anni di piano darebbe un grafico monco).
    """
    chart = next((item for item in report.chart_series if item.id == chart_id), None)
    if chart is None:
        return None
    timeline = _timeline(report)
    if not timeline:
        timeline = [period for period in report.detailed_statements[0].periods]
    axis = [_axis_label(period) for period in timeline]

    def indicator_series(identifier: str):
        indicator = _indicator_by_id(report, identifier)
        if indicator is None or not any(value is not None for value in indicator.values):
            return None
        by_key = {_period_key(period): value for period, value in zip(indicator.periods, indicator.values)}
        return {"label": indicator.label, "values": [_exact(by_key.get(_period_key(period))) for period in timeline]}

    def statement_series(statement_id: str, codes: tuple, label: str | None):
        for statement in report.detailed_statements:
            if statement.id != statement_id:
                continue
            for row in statement.rows:
                if row.code in codes and any(value is not None for value in row.values):
                    by_key = {_period_key(period): value
                              for period, value in zip(statement.periods, row.values)}
                    return {"label": label or row.label,
                            "values": [_exact(by_key.get(_period_key(period))) for period in timeline]}
        return None

    references = list(getattr(chart, "indicator_ids", []) or [])
    series: list[dict[str, Any]] = []
    if references:
        series = [built for built in (indicator_series(ref) for ref in references) if built is not None]
    elif chart_id in _CANONICAL_CHART_SERIES:
        for spec in _CANONICAL_CHART_SERIES[chart_id]:
            built = (indicator_series(spec[1]) if spec[0] == "indicator"
                     else statement_series(spec[1], spec[2], spec[3]))
            if built is not None:
                series.append(built)
                if spec[0] == "indicator":
                    references.append(spec[1])
    if not series:
        # Ripiego onesto: le serie del modello, collocate sugli anni di piano.
        for metric in chart.series:
            by_year = {year: value for year, value in zip(chart.categories, metric.values)}
            series.append({"label": metric.label, "values": [
                _exact(by_year.get(period.year)) if period.basis == "forecast" and period.year in by_year else None
                for period in timeline]})
    return {"id": chart.id, "title": chart.title, "unit": str(chart.unit), "categories": axis,
            "series": series, "indicator_ids": references,
            "thresholds": [{"label": _indicator_by_id(report, ref).label + " · " + threshold.label,
                            "value": format(threshold.value, "f"), "source": threshold.source}
                           for ref in references for threshold in _indicator_by_id(report, ref).thresholds]}


def chart_marker_width_mm(report: FinalReportModelV2, chart_id: str) -> str:
    """Rilievo 1: sulla pagina tipo il grafico con colonna KPI occupa 118 mm
    (55 mm di colonna + 5 di gutter); senza KPI resta a 178. Il piano editoriale
    valida la geometria dichiarata dalla stessa fonte."""
    return '118' if _chart_kpis(report, chart_id) else '178'


def _chart_kpis(report: FinalReportModelV2, chart_id: str) -> list[dict[str, Any]]:
    """KPI della pagina tipo per grafico canónico (tabella del piano, §M2-02B).

    Ciò che il modello v2 non fornisce (somme di piano, effetti su EBITDA delle
    rettifiche, incrementi stimati) non è calcolato qui: il KPI si omette e la
    lacuna è annotata nella ricevuta.
    """
    builders: dict[str, list[Any]] = {
        "income_results": [
            _kpi_revenue_now(report),
            _kpi_indicator(report, "practice.ebitda_margin", "EBITDA margin", mode="first_last"),
            _kpi_indicator(report, "practice.pfn", "PFN"),
            _kpi_forecast(report, "balance_sheet", ("cash", "sp09_disponibilita_liquide"), "cassa"),
        ],
        "margins": [_kpi_indicator(report, "practice.ebitda_margin", "EBITDA margin")],
        "economic_incidence": [
            _kpi_forecast(report, "income_statement", ("revenue", "ce01_ricavi_vendite", "production_value"), "ricavi"),
            _kpi_forecast(report, "income_statement", ("ebitda",), "EBITDA"),
            _kpi_indicator(report, "practice.ebitda_margin", "margine EBITDA"),
            _kpi_forecast(report, "income_statement", ("net_profit", "profit_after_tax"), "utile netto"),
        ],
        "financial_charges": [
            _kpi_indicator(report, "practice.of_mol", "Oneri finanziari / MOL"),
            _kpi_indicator(report, "practice.of_revenue", "Oneri finanziari / ricavi"),
        ],
        "liquidity_debt": [
            _kpi_forecast(report, "balance_sheet", ("total_assets",), "totale attivo"),
            _kpi_forecast(report, "balance_sheet", ("net_equity", "sp11_capitale+sp12_riserve+sp13_utile_perdita"), "patrimonio netto"),
            _kpi_forecast(report, "balance_sheet", ("fixed_assets",), "immobilizzazioni nette"),
            _kpi_forecast(report, "balance_sheet", ("financial_debt",), "debiti finanziari"),
        ],
        "cashflows": [
            _kpi_forecast(report, "cashflow", ("operating", "operating.total_operating_cashflow"), "flussi operativi"),
            _kpi_forecast(report, "cashflow", ("investing", "investing.total_investing_cashflow"), "investimenti"),
            _kpi_forecast(report, "cashflow", ("financing", "financing.total_financing_cashflow"), "rimborsi"),
            _kpi_forecast(report, "cashflow", ("cash_change", "cash_reconciliation.total_cashflow"), "variazione cassa"),
        ],
        "coverage": [_kpi_indicator(report, "practice.dscr", "DSCR proxy")],
        "structural_balance": [
            _kpi_indicator(report, "practice.ccn", "CCN"),
            _kpi_indicator(report, "practice.mt", "margine di tesoreria"),
            _kpi_indicator(report, "practice.ms", "margine di struttura"),
        ],
        "practice_liquidity": [
            _kpi_indicator(report, "practice.current_ratio", "liquidità corrente"),
            _kpi_indicator(report, "practice.mt", "margine di tesoreria"),
            _kpi_indicator(report, "practice.ms", "margine di struttura"),
        ],
        "practice_profitability": [
            _kpi_indicator(report, "practice.roi", "ROI"),
            _kpi_indicator(report, "practice.roe", "ROE"),
        ],
        "practice_asset_coverage": [
            _kpi_indicator(report, "practice.indipendenza", "indipendenza finanziaria"),
            _kpi_indicator(report, "practice.copertura_immob", "copertura immobilizzazioni"),
            _kpi_indicator(report, "practice.pfn_ebitda", "PFN / EBITDA"),
        ],
        "practice_net_debt": [
            _kpi_indicator(report, "practice.pfn", "PFN", mode="first_last"),
            _kpi_indicator(report, "practice.pfn_ebitda", "PFN / EBITDA", mode="first_last"),
            _kpi_indicator(report, "practice.ccn", "circolante operativo"),
        ],
        "practice_net_debt_ebitda": [_kpi_indicator(report, "practice.pfn_ebitda", "PFN / EBITDA")],
        "practice_dscr_proxy": [_kpi_indicator(report, "practice.dscr", "DSCR proxy")],
        "working_capital_days": [
            _kpi_indicator(report, "analytical.activity.receivables_turnover_days", "giorni di credito"),
            _kpi_indicator(report, "analytical.activity.inventory_turnover_days", "giorni di magazzino"),
            _kpi_indicator(report, "analytical.activity.payables_turnover_days", "giorni di debito"),
        ],
        "analytical_liquidity": [
            _kpi_indicator(report, "analytical.liquidity.current_ratio", "Current Ratio"),
            _kpi_indicator(report, "analytical.liquidity.quick_ratio", "Quick Ratio"),
            _kpi_indicator(report, "analytical.liquidity.acid_test", "Acid Test"),
        ],
    }
    return [kpi for kpi in builders.get(chart_id, []) if kpi is not None]


def _value_columns(periods: list[Any]) -> list[str]:
    return [_period_label(period) for period in periods]


def _assumption_unit(field: str) -> str | None:
    if field.endswith("_pct") or field in {"interest_rate", "tax_rate", "balloon_pct", "acconto_pct"}:
        return "percent"
    if field.endswith("_days"):
        return "days"
    return None


def _assumption_rows(section: Any, period_labels: list[str], unavailable_entries: list[tuple[str, str]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for assumption in section.assumptions:
        unit = _assumption_unit(assumption.field)
        values = [*assumption.values, *([None] * (len(period_labels) - len(assumption.values)))]
        # Rilievo 6: la colonna «Indisponibilità» coi periodi mancanti elencati
        # riga per riga sparisce; ogni periodo mancante diventa una voce da
        # raggruppare in nota dopo la tabella (`_unavailability_text`).
        for label, value in zip(period_labels, values):
            if value is None:
                unavailable_entries.append((assumption.label, f"valore non dichiarato per {label}"))
        rows.append(_row(
            f"assumption:{section.key}:{assumption.field}:value",
            [assumption.label, *values, _label(_PROVENANCE_LABELS, assumption.provenance), assumption.active],
            [None, *([unit] * len(values)), None, None],
        ))
        if assumption.financing_loans is not None:
            for index, loan in enumerate(assumption.financing_loans):
                rows.append(_row(
                    f"assumption:{section.key}:{assumption.field}:loan:{index}",
                    [f"Finanziamento {index + 1}: {loan.name or 'n.d.'}", loan.amount,
                     loan.opening_residual, loan.duration_years, loan.interest_rate,
                     loan.grace_years, loan.balloon_pct],
                    [None, "eur", "eur", None, "percent", None, "percent"],
                ))
                if loan.repayments is not None:
                    for repayment_index, amount in enumerate(loan.repayments):
                        rows.append(_row(
                            f"assumption:{section.key}:{assumption.field}:loan:{index}:repayment:{repayment_index}",
                            [f"Finanziamento {index + 1}: {loan.name or 'n.d.'} — rimborso {repayment_index + 1}", amount],
                            [None, "eur"],
                        ))
        if assumption.pregresso is not None:
            for plan_name in ("crediti_commerciali", "debiti_fornitori", "debiti_tributari", "debiti_previdenziali", "altri_debiti"):
                plan = getattr(assumption.pregresso, plan_name)
                if plan is None:
                    rows.append(_row(f"assumption:{section.key}:{assumption.field}:{plan_name}:unavailable",
                                     [f"Pregresso {plan_name}", None, "n.d.: piano non dichiarato"],
                                     [None, "eur", None]))
                    continue
                rows.append(_row(f"assumption:{section.key}:{assumption.field}:{plan_name}:opening",
                                 [f"Pregresso {plan_name} — apertura", plan.opening, None], [None, "eur", None]))
                for index, value in enumerate(plan.amounts):
                    rows.append(_row(f"assumption:{section.key}:{assumption.field}:{plan_name}:amount:{index}",
                                     [f"Pregresso {plan_name} — quota {index + 1}", value, None], [None, "eur", None]))
                if plan.writeoff is not None:
                    for index, value in enumerate(plan.writeoff):
                        rows.append(_row(f"assumption:{section.key}:{assumption.field}:{plan_name}:writeoff:{index}",
                                         [f"Pregresso {plan_name} — stralcio {index + 1}", value, None], [None, "eur", None]))
                if plan.non_incassato is not None:
                    rows.append(_row(f"assumption:{section.key}:{assumption.field}:{plan_name}:non_incassato",
                                     [f"Pregresso {plan_name} — non incassato", plan.non_incassato], [None, None]))
                if plan_name == "debiti_tributari":
                    for field in ("saldo", "rateizzato", "acconto_pct"):
                        rows.append(_row(f"assumption:{section.key}:{assumption.field}:{plan_name}:{field}",
                                         [f"Pregresso {plan_name} — {field}", getattr(plan, field), None],
                                         [None, "percent" if field == "acconto_pct" else "eur", None]))
        if assumption.temporary_differences is not None:
            for index, difference in enumerate(assumption.temporary_differences):
                rows.append(_row(
                    f"assumption:{section.key}:{assumption.field}:temporary_difference:{index}",
                    [f"Differenza temporanea: {difference.name}", _label(_TEMPORARY_KIND_LABELS, difference.kind),
                     _label(_TEMPORARY_MATURITY_LABELS, difference.maturity),
                     difference.opening_amount, difference.additions, difference.reversals, difference.tax_rate,
                     _missing("aliquota non dichiarata") if difference.tax_rate is None else None],
                    [None, None, None, "eur", "eur", "eur", "percent", None],
                ))
        if assumption.ce_overrides is not None:
            for index, override in enumerate(assumption.ce_overrides):
                rows.append(_row(f"assumption:{section.key}:{assumption.field}:ce_override:{index}",
                                 [f"Override CE {override.field}", override.value, None], [None, "eur", None]))
        if assumption.sp_indexing is not None:
            for index, indexing in enumerate(assumption.sp_indexing):
                rows.append(_row(f"assumption:{section.key}:{assumption.field}:sp_indexing:{index}",
                                 [f"Indicizzazione SP {indexing.field}", indexing.driver, None], [None, None, None]))
        if assumption.sp_overrides is not None:
            for index, override in enumerate(assumption.sp_overrides):
                rows.append(_row(f"assumption:{section.key}:{assumption.field}:sp_override:{index}",
                                 [f"Override SP {override.field}", override.value, None], [None, "eur", None]))
        if assumption.other_lenders is not None:
            for index, lender in enumerate(assumption.other_lenders):
                rows.append(_row(
                    f"assumption:{section.key}:{assumption.field}:other_lender:{index}",
                    [f"Altro finanziatore {index + 1}: {lender.name or 'n.d.'}",
                     lender.opening_residual, lender.interest_rate],
                    [None, "eur", "percent"],
                ))
                for repayment_index, amount in enumerate(lender.repayments):
                    rows.append(_row(
                        f"assumption:{section.key}:{assumption.field}:other_lender:{index}:repayment:{repayment_index}",
                        [f"Altro finanziatore {index + 1}: {lender.name or 'n.d.'} — rimborso {repayment_index + 1}", amount],
                        [None, "eur"],
                    ))
    # The compact base table has stable columns.  Nested records use a separate
    # detail table below so their full structures stay legible and lossless.
    return rows


def _assumption_items(report: FinalReportModelV2) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Base (matrice per anni) nel corpo, dettagli annidati in Allegato E.

    La v4 mostra a pagina 7 la griglia compatta dei driver; gli elenchi di
    finanziamenti, pregressi, override e differenze restano negli Allegati,
    dove ogni campo è una riga atomica. Nessuna riga è duplicata: i marcatori
    stanno una sola volta, nella tabella che li espone.
    """
    years = list(report.practice.periods.forecast_years)
    scalar_width = max((len(assumption.values) for section in report.assumption_sections
                        for assumption in section.assumptions), default=len(years))
    period_labels = [str(year) for year in years]
    period_labels.extend(f"Periodo non associato {index}" for index in range(1, scalar_width - len(period_labels) + 1))
    base_items: list[dict[str, Any]] = []
    detail_items: list[dict[str, Any]] = []
    for section in report.assumption_sections:
        base_rows: list[dict[str, Any]] = []
        detail_rows: list[dict[str, Any]] = []
        unavailable_entries: list[tuple[str, str]] = []
        for row in _assumption_rows(section, period_labels, unavailable_entries):
            # Scalar rows have one label + all year values + provenance/active.
            if row["id"].endswith(":value"):
                base_rows.append(row)
            else:
                detail_rows.append(row)
        base_columns = ["Parametro", *period_labels, "Provenienza", "Attiva"]
        base_items.append(_table(f"assumptions:{section.key}", section.title, base_columns, base_rows))
        unavailable_note = _unavailability_text(unavailable_entries)
        if unavailable_note:
            base_items.append(_text(f"assumptions:{section.key}:unavailable",
                                    f"Indisponibilità — {section.title}", unavailable_note))
        # Detail records remain atomic: a field never becomes a compound string
        # carrying an ambiguous numeric unit.  This also leaves every nested
        # source field independently addressable by the page planner.
        if detail_rows:
            normalized: list[dict[str, Any]] = []
            for row in detail_rows:
                cells = row["cells"]
                units = row["units"]
                if ":loan:" in row["id"] and ":repayment:" not in row["id"]:
                    labels = ("Importo", "Residuo iniziale", "Durata (anni)", "Tasso", "Preammortamento (anni)", "Balloon")
                elif ":other_lender:" in row["id"] and ":repayment:" not in row["id"]:
                    labels = ("Residuo iniziale", "Tasso")
                elif ":repayment:" in row["id"]:
                    labels = ("Rimborso",)
                elif ":temporary_difference:" in row["id"]:
                    labels = ("Natura", "Scadenza", "Importo iniziale", "Incrementi", "Riversamenti", "Aliquota", "Nota")
                else:
                    labels = tuple("Nota" if index == len(cells) - 1 and value and str(value).startswith("n.d.") else "Valore"
                                   for index, value in enumerate(cells[1:], start=1))
                for index, (label, value, unit) in enumerate(zip(labels, cells[1:], units[1:]), start=1):
                    normalized.append(_row(f"{row['id']}:field:{index}", [f"{cells[0]} — {label}", value], [None, unit]))
            detail_items.append(_table(f"assumptions:{section.key}:details", f"{section.title} — dettagli", ["Voce", "Valore"], normalized))
    return base_items, detail_items


def _statement_table(identifier: str, title: str, statement: Any, prefix: str, *, context: bool) -> dict[str, Any]:
    """Allegato: etichette di prospetto e valori. Codici, tipo, fonte e catalogo
    non si stampano (M2-02B difetto 2): il contesto padre è già nelle righe
    «sezione/gruppo» del prospetto stesso."""
    columns = ["Voce", *_value_columns(statement.periods), "Indisponibilità"]

    rows = []
    for row in statement.rows:
        reasons = [_label(_UNAVAILABLE_REASON_LABELS, reason) for reason in row.unavailable_reasons
                   if reason and reason != "presentation_header"]
        header = row.kind in ("section", "group")
        values = [""] * len(row.values) if header else row.values
        value_units = [None] * len(values) if header else ["eur"] * len(values)
        rows.append(_row(
            f"{prefix}:{statement.id}:{row.id}",
            [row.label, *values, _missing("; ".join(reasons)) if reasons else None],
            [None, *value_units, None],
        ))
    return _periodic_table(_table(identifier, title, columns, rows), value_start=1, part_size=PERIOD_PART_SIZE)


def _forecast_table(identifier: str, title: str, years: list[Any], attribute: str) -> dict[str, Any]:
    codes: OrderedDict[str, Any] = OrderedDict()
    for year in years:
        seen: set[str] = set()
        for line in getattr(year, attribute):
            if line.code in seen:
                raise ValueError(f"duplicate canonical forecast line {line.code!r} for {attribute} {year.year}")
            seen.add(line.code)
            codes.setdefault(line.code, line.label)
    columns = ["Voce", *[str(year.year) for year in years], "Indisponibilità"]
    rows = []
    for code, label in codes.items():
        values = [next((line.value for line in getattr(year, attribute) if line.code == code), None) for year in years]
        missing = [str(year.year) for year, value in zip(years, values) if value is None]
        units = [None, *("eur" if attribute != "calculations" else None,) * len(values), None]
        rows.append(_row(f"forecast:{attribute}:{code}", [label, *values,
                         _missing("riga non presente nel forecast canonico per " + ", ".join(missing)) if missing else None], units))
    return _periodic_table(_table(identifier, title, columns, rows), value_start=1, part_size=PERIOD_PART_SIZE)


def _comparison_items(report: FinalReportModelV2) -> list[dict[str, Any]]:
    items = []
    for statement in report.detailed_statements:
        rows = [row for row in statement.rows if row.kind in ("subtotal", "total")]
        columns = ["Voce", *_value_columns(statement.periods), "Indisponibilità"]
        comparison_rows = []
        for row in rows:
            reasons = [_label(_UNAVAILABLE_REASON_LABELS, reason) for reason in row.unavailable_reasons if reason]
            comparison_rows.append(_row(
                f"comparison:{statement.id}:{row.id}", [row.label, *row.values,
                _missing("; ".join(reasons)) if reasons else None],
                [None, *("eur",) * len(row.values), None],
            ))
        items.append(_periodic_table(_table(f"comparison:{statement.id}", f"Confronto dei periodi disponibili — {statement.title}", columns, comparison_rows), value_start=1, part_size=PERIOD_PART_SIZE))
    return items


def build_inventory(report: FinalReportModelV2) -> list[dict[str, Any]]:
    """Return the complete ordered content inventory for a canonical v2 report."""
    if not isinstance(report, FinalReportModelV2):
        raise TypeError("build_inventory requires FinalReportModelV2")
    applicable_sections = tuple(identifier for identifier in SECTION_IDS if identifier != "infrannual_closing" or report.infrannual_closing is not None)
    sections = [{"id": identifier, "title": _SECTION_TITLES[identifier], "family": _SECTION_FAMILY[identifier],
                 "subtitle": _SECTION_SUBTITLES[identifier], "items": []} for identifier in applicable_sections]
    section = {value["id"]: value for value in sections}
    section["cover"]["items"].append({"id": "cover", "kind": "cover", "title": report.document.title})

    for narrative in report.narrative:
        text = (narrative.text or "").strip()
        # Rilievo 2: un blocco narrativo senza testo vero (vuoto o una sola
        # parola, come «Sintesi»/«Finanza») non si stampa: titolo+segnaposto
        # erano pagine bianche con cornice. Il commento vive nel riquadro
        # «Lettura del consulente».
        if len(text.split()) >= 2:
            section[_NARRATIVE_SECTION[narrative.id]]["items"].append(
                _text(narrative.id, _NARRATIVE_TITLES[narrative.id], text))

    periods = []
    for statement in report.detailed_statements:
        for period in statement.periods:
            periods.append(_row(f"source-period:{statement.id}:{period.id}",
                                [statement.title, _period_label(period), _period_role(period), period.period_end],
                                [None] * 4))
    section["source_data_quality"]["items"].append(_table("source-periods", "Periodi delle fonti", ["Prospetto", "Periodo", "Ruolo", "Chiusura"], periods))
    revisions = [_row(f"source-revision:{index}:{item.source}", [_label(_SOURCE_LABELS, item.source), item.identifier, item.revision, item.revision_at, item.available], [None] * 5) for index, item in enumerate(report.source_revisions)]
    section["source_data_quality"]["items"].append(_table("source-revisions", "Revisioni delle fonti", ["Fonte", "Identificativo", "Revisione", "Data revisione", "Disponibile"], revisions))
    quality_rows = [_row(f"source-quality:{index}:{item.code}", [_label(_QUALITY_STATUS_LABELS, report.source_data_quality.status), item.code, _label(_SEVERITY_LABELS, item.severity), _label(_SECTION_TITLES, item.section), item.message], [None] * 5) for index, item in enumerate(report.source_data_quality.diagnostics)]
    section["source_data_quality"]["items"].append(_table("source-quality", "Qualità dei dati", ["Stato", "Codice", "Severità", "Sezione", "Messaggio"], quality_rows or [_row("source-quality:status", [_label(_QUALITY_STATUS_LABELS, report.source_data_quality.status), None, None, None, "n.d.: nessuna diagnostica di qualità"], [None] * 5)]))

    adjustment_rows = [_row(f"adjustment:{entry.id}", [entry.edited_label, entry.edit_delta, entry.counterpart_label, entry.counterpart_delta, entry.explanation, entry.created_at, _missing("spiegazione non fornita") if entry.explanation is None else None], [None, "eur", None, "eur", None, None, None]) for entry in report.adjustments.entries]
    adjustment_rows.append(_row("adjustment:net-effect", ["Effetto netto sul risultato", report.adjustments.net_effect, f"Rettifiche confermate: {'sì' if report.adjustments.confirmed else 'no'}", None, None, None, None], [None, "eur", None, None, None, None, None]))
    adjustments_register = _table("adjustments-register", "Allegato D — Registro delle rettifiche", ["Voce rettificata", "Delta", "Contropartita", "Delta contropartita", "Motivazione", "Data", "Nota"], adjustment_rows)
    if report.practice.workflow_type == "infrannuale":
        section["adjustments"]["items"].append(_text("period-comparability", "Comparabilità dei periodi",
            "Osservato e rettificato mantengono gli importi del periodo infrannuale; "
            "chiusura e budget sono distinti nelle intestazioni. Le durate sono esposte "
            "nella sezione delle fonti. Il confronto non annualizza gli importi infrannuali "
            "e non equipara periodi di diversa durata."))
    section["adjustments"]["items"].extend(_comparison_items(report))

    if report.infrannual_closing is not None:
        closing_rows = []
        for value in report.infrannual_closing.values:
            absent = [_label(_CLOSING_STATE_LABELS, name) for name in ("observed", "comparable", "automatic", "override") if getattr(value, name) is None]
            closing_rows.append(_row(f"infrannual-closing:{value.code}", [value.label, value.observed, value.comparable, value.automatic, value.override, value.closing_used, _missing("valore " + "; ".join(absent) + " non dichiarato") if absent else None], [None, "eur", "eur", "eur", "eur", "eur", None]))
        section["infrannual_closing"]["items"].append(_periodic_table(_table("infrannual-closing-values", f"Valori di chiusura al {report.infrannual_closing.period_end}", ["Voce", "Osservato", "Comparabile", "Automatico", "Override", "Chiusura utilizzata", "Indisponibilità"], closing_rows), value_start=1, part_size=PERIOD_PART_SIZE))
        alerts = report.infrannual_closing.extra_accounting_alerts
        section["infrannual_closing"]["items"].append(_table("infrannual-closing-alerts", "Alert contabili extra", ["Alert", "Attivo"], [_row(f"infrannual-alert:{name}", [_label(_ALERT_LABELS, name), getattr(alerts, name)], [None, None]) for name in alerts.model_fields]))
    assumption_base, assumption_details = _assumption_items(report)
    section["budget_assumptions"]["items"].extend(assumption_base)
    section["income_statement_forecast"]["items"].append(_forecast_table("forecast-income-statement", "Conto economico previsto", report.forecast.years, "income_statement"))
    section["balance_sheet_forecast"]["items"].append(_forecast_table("forecast-balance-sheet", "Stato patrimoniale previsto", report.forecast.years, "balance_sheet"))
    section["cashflow_sustainability"]["items"].append(_forecast_table("forecast-cashflow", "Rendiconto finanziario previsto", report.forecast.years, "cashflow"))
    # Niente «Calcoli previsionali canonici»: riversava gli output interni dei calcolatori col codice
    # tecnico come etichetta, senza unità e senza arrotondamento (73.33333333333333333333333333). Gli
    # stessi indicatori stanno nel catalogo, con etichetta, unità e metodologia (proprietario, 2026-09-17).

    dropped: dict[str, dict[str, Any]] = {}
    for chart in report.chart_series:
        destination = _CHART_SECTION.get(chart.id, "indicators")
        view = chart_view(report, chart.id)
        item = {"id": f"chart:{chart.id}", "kind": "chart", "title": chart.title,
                "chart_id": chart.id, "chart": view, "kpis": _chart_kpis(report, chart.id)}
        if not any(value is not None for series in view["series"] for value in series["values"]):
            # Difetto v4: la pagina «n.d.» per intera. Un grafico senza alcun
            # valore nel timeline non si stampa; la pagina resta occupata dal
            # resto della sezione. Se la sezione restasse senza maricatori,
            # il primo grafico vuoto tiene la pagina con la sola griglia.
            dropped.setdefault(destination, item)
            continue
        section[destination]["items"].append(item)
    for destination, orphan in dropped.items():
        if not section[destination]["items"]:
            # Sezione rimasta senza alcun marcatore: il grafico vuoto tiene la
            # pagina (con la sola griglia), altrimenti la pagina sarebbe vuota.
            section[destination]["items"].append(orphan)
    for value in sections:
        value["kpis"] = [] if any(item["kind"] == "chart" for item in value["items"]) else _section_kpis(report, value["id"])

    indicator_periods: OrderedDict[str, Any] = OrderedDict()
    for indicator in report.indicator_catalog:
        for period in indicator.periods:
            existing = indicator_periods.get(period.id)
            if existing is not None and (
                existing.year, existing.label, existing.basis, existing.period_months, existing.period_end, existing.source
            ) != (
                period.year, period.label, period.basis, period.period_months, period.period_end, period.source
            ):
                raise ValueError(f"conflicting indicator period definition for {period.id!r}")
            indicator_periods.setdefault(period.id, period)
    # Il catalogo per-voce con i blocchi «practice.pfn / Unità: ratio / Convenzione:
    # pratica-v1…» non si stampa più: gli indicatori diventano due tabelle F/G
    # (indicatore × periodo) e una tabella compatta di metodologia e
    # convenzione in «Allegati e metodologia» (M2-02B difetto 2). Rilievo 3:
    # niente colonna «Unità» separata (l'unità entra fra parentesi
    # nell'etichetta) e niente riga di motivazione per indicatore — le
    # motivazioni raggruppate e deduplicate diventano una nota dopo ciascuna
    # tabella (`_unavailability_text`). La colonna di coda resta riservata
    # (sempre `None`): il template divide la tabella in parti sull'ipotesi che
    # l'ultima colonna non sia un valore di periodo (`editorial.typ`,
    # `compact-period-table`), e qui nessun template si tocca.
    indicator_columns = ["Indicatore", *[_period_label(period) for period in indicator_periods.values()], "Indisponibilità"]

    def _indicator_row(indicator: Any, entries: list[tuple[str, str]]) -> dict[str, Any]:
        values_by_period = dict(zip((period.id for period in indicator.periods), indicator.values))
        values = [values_by_period.get(identifier) for identifier in indicator_periods]
        unit_suffix = _label(_UNIT_LABELS, indicator.unit)
        label = f"{indicator.label} ({unit_suffix})" if unit_suffix else indicator.label
        for period, reason in zip(indicator.periods, indicator.unavailable_reasons):
            if reason:
                entries.append((indicator.label, f"{_period_label(period)} — {_label(_UNAVAILABLE_REASON_LABELS, reason)}"))
        return _row(f"indicator:{indicator.id}", [label, *values, None],
                     [None, *([indicator.unit] * len(values)), None])

    practice_entries: list[tuple[str, str]] = []
    analytical_entries: list[tuple[str, str]] = []
    practice_rows = [_indicator_row(indicator, practice_entries) for indicator in report.indicator_catalog if indicator.id.startswith("practice.")]
    analytical_rows = [_indicator_row(indicator, analytical_entries) for indicator in report.indicator_catalog if not indicator.id.startswith("practice.")]
    indicator_tables: list[dict[str, Any]] = []
    if practice_rows:
        indicator_tables.append(_periodic_table(_table("indicator-practice-table", "Tabella F — Indicatori della pratica", indicator_columns, practice_rows), value_start=1, part_size=INDICATOR_PART_SIZE))
        practice_note = _unavailability_text(practice_entries)
        if practice_note:
            indicator_tables.append(_text("indicator-practice-table:unavailable", "Indisponibilità — Tabella F", practice_note))
    if analytical_rows:
        indicator_tables.append(_periodic_table(_table("indicator-analytical-table", "Tabella G — Indici del report analitico", indicator_columns, analytical_rows), value_start=1, part_size=INDICATOR_PART_SIZE))
        analytical_note = _unavailability_text(analytical_entries)
        if analytical_note:
            indicator_tables.append(_text("indicator-analytical-table:unavailable", "Indisponibilità — Tabella G", analytical_note))

    diagnostics = list(report.diagnostics) + list(report.readiness.reasons)
    diagnostic_rows = [_row(f"diagnostic:{index}:{item.code}", [item.code, _label(_SEVERITY_LABELS, item.severity), _label(_SECTION_TITLES, item.section), item.message], [None] * 4) for index, item in enumerate(diagnostics)]
    section["diagnostics_actions"]["items"].append(_table("diagnostics", f"Diagnostica (stato: {_label(_READINESS_LABELS, report.readiness.status)})", ["Codice", "Severità", "Sezione", "Messaggio"], diagnostic_rows))

    section["appendices_methodology"]["items"].append(_text("appendix-index", "Indice delle appendici", "Indice delle appendici e riferimenti di pagina da compilare dall'impaginazione Typst."))
    for letter, statement in zip("ABC", report.detailed_statements):
        section["appendices_methodology"]["items"].append(
            _statement_table(f"appendix:{statement.id}", f"Allegato {letter} — {statement.title}", statement, "row", context=True))
    # Allegati in ordine v4: indice, A/B/C dei prospetti, D registro rettifiche,
    # E dettagli delle ipotesi, F/G indicatori, metodologia e convenzioni.
    section["appendices_methodology"]["items"].append(adjustments_register)
    section["appendices_methodology"]["items"].extend(assumption_details)
    section["appendices_methodology"]["items"].extend(indicator_tables)
    # Rilievo 4: niente più il catalogo a blocchi (Famiglia/Metodologia/
    # Convenzione/Soglie ripetuti per indicatore, ~5 pagine): una tabella
    # compatta Indicatore | Metodologia, una riga ciascuno. «Famiglia» e
    # «Soglie» (quasi sempre n.d.) non si stampano più. La convenzione è
    # comune agli indicatori della stessa famiglia di calcolo (pratica vs
    # analitica — `calculations/report_indicators.py`), non un valore per
    # indicatore: si scrive una volta per ciascun testo distinto, come nota
    # prima della tabella, senza scartarne uno se il modello ne dichiarasse
    # più di uno (mai tappare un divario).
    conventions: "OrderedDict[str, None]" = OrderedDict()
    for indicator in report.indicator_catalog:
        conventions.setdefault(indicator.convention, None)
    for index, convention in enumerate(conventions):
        section["appendices_methodology"]["items"].append(_text(
            f"indicator-methodology:convention:{index}",
            "Convenzione degli indicatori" if len(conventions) == 1 else f"Convenzione degli indicatori ({index + 1}/{len(conventions)})",
            convention))
    methodology_rows = [_row(
        f"indicator-method:{indicator.id}",
        [indicator.label, indicator.methodology],
        [None, None]) for indicator in report.indicator_catalog]
    section["appendices_methodology"]["items"].append(_table("indicator-methodology", "Metodologia e convenzioni degli indicatori", ["Indicatore", "Metodologia"], methodology_rows))

    return sections


def expected_content_inventory(report: FinalReportModelV2) -> OrderedDict[str, str]:
    """Map every exact marker emitted by the inventory to its owning section."""
    expected: OrderedDict[str, str] = OrderedDict()
    for section in build_inventory(report):
        for item in section["items"]:
            if item["kind"] == "cover":
                content_ids = ["cover"]
            elif item["kind"] == "chart":
                content_ids = [item["id"]]
            elif item["kind"] == "text":
                content_ids = [item["id"]]
            else:
                content_ids = [f"heading:{item['id']}", *(row["id"] for row in item["rows"])]
                if "value_start" in item:
                    total = len(item["columns"]) - item["value_start"] - 1
                    for part in range(2, (total + item["part_size"] - 1) // item["part_size"] + 1):
                        content_ids.extend(f"{row['id']}#parte:{part}" for row in item["rows"])
            for content_id in content_ids:
                if content_id in expected:
                    raise ValueError(f"duplicate editorial content id: {content_id}")
                expected[content_id] = section["id"]
    return expected
