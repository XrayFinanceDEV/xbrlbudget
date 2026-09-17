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
    "source_data_quality": "Qualità e provenienza dei dati",
    "adjustments": "Rettifiche e raccordo alla chiusura",
    "infrannual_closing": "Chiusura infrannuale",
    "budget_assumptions": "Ipotesi di budget",
    "income_statement_forecast": "Previsione conto economico",
    "balance_sheet_forecast": "Previsione stato patrimoniale",
    "cashflow_sustainability": "Flussi finanziari e sostenibilità",
    "indicators": "Indicatori e convenzioni",
    "diagnostics_actions": "Diagnostica e azioni",
    "appendices_methodology": "Appendici e metodologia",
}

_NARRATIVE_SECTION = {
    "executive_summary": "executive_summary",
    "adjustments_and_closing": "adjustments",
    "budget_assumptions": "budget_assumptions",
    "economic_outlook": "income_statement_forecast",
    "financial_outlook": "balance_sheet_forecast",
    "risks_and_actions": "diagnostics_actions",
}

_CHART_SECTION = {
    "income_results": "executive_summary",
    "margins": "executive_summary",
    "economic_incidence": "income_statement_forecast",
    "financial_charges": "income_statement_forecast",
    "liquidity_debt": "balance_sheet_forecast",
    "structural_balance": "balance_sheet_forecast",
    "cashflows": "cashflow_sustainability",
    "working_capital_days": "cashflow_sustainability",
    "coverage": "cashflow_sustainability",
    "practice_liquidity": "cashflow_sustainability",
    "practice_net_debt": "cashflow_sustainability",
    "practice_net_debt_ebitda": "cashflow_sustainability",
    "practice_dscr_proxy": "cashflow_sustainability",
    "practice_profitability": "indicators",
    "practice_asset_coverage": "indicators",
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


def _text(identifier: str, title: str, text: str) -> dict[str, Any]:
    return {"id": identifier, "kind": "text", "title": title, "text": text or "n.d.: testo non disponibile"}


def _period_label(period: Any) -> str:
    suffix = f" ({period.period_months} mesi)" if period.period_months is not None else ""
    return f"{period.label}{suffix}"


def _value_columns(periods: list[Any]) -> list[str]:
    return [_period_label(period) for period in periods]


def _assumption_unit(field: str) -> str | None:
    if field.endswith("_pct") or field in {"interest_rate", "tax_rate", "balloon_pct", "acconto_pct"}:
        return "percent"
    if field.endswith("_days"):
        return "days"
    return None


def _assumption_rows(section: Any, period_labels: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for assumption in section.assumptions:
        unit = _assumption_unit(assumption.field)
        values = [*assumption.values, *([None] * (len(period_labels) - len(assumption.values)))]
        missing = "; ".join(label for label, value in zip(period_labels, values) if value is None)
        rows.append(_row(
            f"assumption:{section.key}:{assumption.field}:value",
            [assumption.label, *values, assumption.provenance, assumption.active,
             _missing(f"valore non dichiarato per {missing}") if missing else None],
            [None, *([unit] * len(values)), None, None, None],
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
                    [f"Differenza temporanea: {difference.name}", difference.kind, difference.maturity,
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


def _assumption_items(report: FinalReportModelV2) -> list[dict[str, Any]]:
    years = list(report.practice.periods.forecast_years)
    scalar_width = max((len(assumption.values) for section in report.assumption_sections
                        for assumption in section.assumptions), default=len(years))
    period_labels = [str(year) for year in years]
    period_labels.extend(f"Periodo non associato {index}" for index in range(1, scalar_width - len(period_labels) + 1))
    items: list[dict[str, Any]] = []
    for section in report.assumption_sections:
        base_rows: list[dict[str, Any]] = []
        detail_rows: list[dict[str, Any]] = []
        for row in _assumption_rows(section, period_labels):
            # Scalar rows have one label + all year values + provenance/active/reason.
            if row["id"].endswith(":value"):
                base_rows.append(row)
            else:
                detail_rows.append(row)
        base_columns = ["Parametro", *period_labels, "Provenienza", "Attiva", "Indisponibilità"]
        items.append(_table(f"assumptions:{section.key}", section.title, base_columns, base_rows))
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
            items.append(_table(f"assumptions:{section.key}:details", f"{section.title} — dettagli", ["Voce", "Valore"], normalized))
    return items


def _statement_table(identifier: str, title: str, statement: Any, prefix: str, *, context: bool) -> dict[str, Any]:
    columns = ["Voce", *_value_columns(statement.periods), "Catalogo / indisponibilità"]
    by_id = {row.id: row for row in statement.rows}

    def parent_chain(row: Any) -> str:
        parents = []
        parent_id = row.parent_id
        while parent_id is not None:
            parent = by_id[parent_id]
            parents.append(parent.label)
            parent_id = parent.parent_id
        return " › ".join(reversed(parents))

    rows = []
    for row in statement.rows:
        reasons = [reason for reason in row.unavailable_reasons if reason and reason != "presentation_header"]
        source_note = row.source.split(";", 1)[0]
        catalog_note = f"codice: {row.code}; tipo: {row.kind}; applicabile: {'sì' if row.applicable else 'no'}; fonte: {source_note}"
        if context and parent_chain(row):
            catalog_note = f"contesto: {parent_chain(row)}; {catalog_note}"
        if reasons:
            catalog_note += f"; {_missing('; '.join(reasons))}"
        header = row.kind in ("section", "group")
        values = [""] * len(row.values) if header else row.values
        value_units = [None] * len(values) if header else ["eur"] * len(values)
        rows.append(_row(
            f"{prefix}:{statement.id}:{row.id}",
            [row.label, *values, catalog_note],
            [None, *value_units, None],
        ))
    return _table(identifier, title, columns, rows)


def _forecast_table(identifier: str, title: str, years: list[Any], attribute: str) -> dict[str, Any]:
    codes: OrderedDict[str, Any] = OrderedDict()
    for year in years:
        seen: set[str] = set()
        for line in getattr(year, attribute):
            if line.code in seen:
                raise ValueError(f"duplicate canonical forecast line {line.code!r} for {attribute} {year.year}")
            seen.add(line.code)
            codes.setdefault(line.code, line.label)
    columns = ["Codice", "Voce", *[str(year.year) for year in years], "Indisponibilità"]
    rows = []
    for code, label in codes.items():
        values = [next((line.value for line in getattr(year, attribute) if line.code == code), None) for year in years]
        missing = [str(year.year) for year, value in zip(years, values) if value is None]
        units = [None, None, *(["eur"] * len(values)), None] if attribute != "calculations" else [None] * (3 + len(values))
        rows.append(_row(f"forecast:{attribute}:{code}", [code, label, *values,
                         _missing("riga non presente nel forecast canonico per " + ", ".join(missing)) if missing else None], units))
    return _table(identifier, title, columns, rows)


def _comparison_items(report: FinalReportModelV2) -> list[dict[str, Any]]:
    items = []
    for statement in report.detailed_statements:
        rows = [row for row in statement.rows if row.kind in ("subtotal", "total")]
        columns = ["Codice", "Voce", *_value_columns(statement.periods), "Indisponibilità"]
        comparison_rows = []
        for row in rows:
            reasons = [reason for reason in row.unavailable_reasons if reason]
            comparison_rows.append(_row(
                f"comparison:{statement.id}:{row.id}", [row.code, row.label, *row.values,
                _missing("; ".join(reasons)) if reasons else None],
                [None, None, *(["eur"] * len(row.values)), None],
            ))
        items.append(_table(f"comparison:{statement.id}", f"Confronto dei periodi disponibili — {statement.title}", columns, comparison_rows))
    return items


def build_inventory(report: FinalReportModelV2) -> list[dict[str, Any]]:
    """Return the complete ordered content inventory for a canonical v2 report."""
    if not isinstance(report, FinalReportModelV2):
        raise TypeError("build_inventory requires FinalReportModelV2")
    applicable_sections = tuple(identifier for identifier in SECTION_IDS if identifier != "infrannual_closing" or report.infrannual_closing is not None)
    sections = [{"id": identifier, "title": _SECTION_TITLES[identifier], "items": []} for identifier in applicable_sections]
    section = {value["id"]: value for value in sections}
    section["cover"]["items"].append({"id": "cover", "kind": "cover", "title": report.document.title})

    for narrative in report.narrative:
        section[_NARRATIVE_SECTION[narrative.id]]["items"].append(_text(narrative.id, narrative.id.replace("_", " ").capitalize(), narrative.text))

    periods = []
    for statement in report.detailed_statements:
        for period in statement.periods:
            periods.append(_row(f"source-period:{statement.id}:{period.id}", [statement.title, period.id, _period_label(period), period.basis, period.source], [None] * 5))
    section["source_data_quality"]["items"].append(_table("source-periods", "Periodi delle fonti", ["Prospetto", "ID", "Periodo", "Base", "Fonte"], periods))
    revisions = [_row(f"source-revision:{index}:{item.source}", [item.source, item.identifier, item.revision, item.revision_at, item.available], [None] * 5) for index, item in enumerate(report.source_revisions)]
    section["source_data_quality"]["items"].append(_table("source-revisions", "Revisioni delle fonti", ["Fonte", "Identificativo", "Revisione", "Data revisione", "Disponibile"], revisions))
    quality_rows = [_row(f"source-quality:{index}:{item.code}", [report.source_data_quality.status, item.code, item.severity, item.section, item.message], [None] * 5) for index, item in enumerate(report.source_data_quality.diagnostics)]
    section["source_data_quality"]["items"].append(_table("source-quality", "Qualità dei dati", ["Stato", "Codice", "Severità", "Sezione", "Messaggio"], quality_rows or [_row("source-quality:status", [report.source_data_quality.status, None, None, None, "n.d.: nessuna diagnostica di qualità"], [None] * 5)]))

    adjustment_rows = [_row(f"adjustment:{entry.id}", [entry.edited_field, entry.edited_label, entry.edit_delta, entry.counterpart_field, entry.counterpart_label, entry.counterpart_delta, entry.explanation, entry.created_at, _missing("spiegazione non fornita") if entry.explanation is None else None], [None, None, "eur", None, None, "eur", None, None, None]) for entry in report.adjustments.entries]
    adjustment_rows.append(_row("adjustment:net-effect", ["Effetto netto", None, report.adjustments.net_effect, None, None, None, f"Confermate: {'sì' if report.adjustments.confirmed else 'no'}", None, None], [None, None, "eur", None, None, "eur", None, None, None]))
    section["adjustments"]["items"].append(_table("adjustments-register", "Rettifiche, contropartite e motivazioni", ["Campo rettificato", "Voce", "Delta", "Campo contropartita", "Voce contropartita", "Delta contropartita", "Spiegazione", "Creato il", "Indisponibilità"], adjustment_rows))
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
            absent = [name for name in ("observed", "comparable", "automatic", "override") if getattr(value, name) is None]
            closing_rows.append(_row(f"infrannual-closing:{value.code}", [value.code, value.label, value.observed, value.comparable, value.automatic, value.override, value.closing_used, _missing("; ".join(absent)) if absent else None], [None, None, "eur", "eur", "eur", "eur", "eur", None]))
        section["infrannual_closing"]["items"].append(_table("infrannual-closing-values", f"Valori di chiusura al {report.infrannual_closing.period_end}", ["Codice", "Voce", "Osservato", "Comparabile", "Automatico", "Override", "Chiusura utilizzata", "Indisponibilità"], closing_rows))
        alerts = report.infrannual_closing.extra_accounting_alerts
        section["infrannual_closing"]["items"].append(_table("infrannual-closing-alerts", "Alert contabili extra", ["Alert", "Attivo"], [_row(f"infrannual-alert:{name}", [name, getattr(alerts, name)], [None, None]) for name in alerts.model_fields]))
    section["budget_assumptions"]["items"].extend(_assumption_items(report))
    section["income_statement_forecast"]["items"].append(_forecast_table("forecast-income-statement", "Conto economico previsto", report.forecast.years, "income_statement"))
    section["balance_sheet_forecast"]["items"].append(_forecast_table("forecast-balance-sheet", "Stato patrimoniale previsto", report.forecast.years, "balance_sheet"))
    section["cashflow_sustainability"]["items"].append(_forecast_table("forecast-cashflow", "Rendiconto finanziario previsto", report.forecast.years, "cashflow"))
    # Niente «Calcoli previsionali canonici»: riversava gli output interni dei calcolatori col codice
    # tecnico come etichetta, senza unità e senza arrotondamento (73.33333333333333333333333333). Gli
    # stessi indicatori stanno nel catalogo, con etichetta, unità e metodologia (proprietario, 2026-09-17).

    for chart in report.chart_series:
        destination = _CHART_SECTION.get(chart.id, "indicators")
        section[destination]["items"].append({"id": f"chart:{chart.id}", "kind": "chart", "title": chart.title, "chart_id": chart.id})

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
    indicator_columns = ["ID", "Indicatore", "Famiglia", "Unità", *[
        f"{_period_label(period)} [{period.id}]" for period in indicator_periods.values()
    ], "Indisponibilità", "Metodologia", "Convenzione", "Fonte", "Soglie"]
    indicator_rows = []
    for indicator in report.indicator_catalog:
        values_by_period = dict(zip((period.id for period in indicator.periods), indicator.values))
        reasons_by_period = dict(zip((period.id for period in indicator.periods), indicator.unavailable_reasons))
        values = [values_by_period.get(identifier) for identifier in indicator_periods]
        reasons = "; ".join(f"{identifier}: {reason}" for identifier, reason in reasons_by_period.items() if reason)
        thresholds = "; ".join(f"{threshold.label}: {_exact(threshold.value)} ({threshold.source})" for threshold in indicator.thresholds)
        indicator_rows.append(_row(f"indicator:{indicator.id}", [indicator.id, indicator.label, indicator.family, indicator.unit, *values, _missing(reasons) if reasons else None, indicator.methodology, indicator.convention, indicator.source, thresholds or None], [None, None, None, None, *([indicator.unit] * len(values)), None, None, None, None, None]))
    section["indicators"]["items"].append(_table("indicator-catalog", "Catalogo completo degli indicatori", indicator_columns, indicator_rows))

    diagnostics = list(report.diagnostics) + list(report.readiness.reasons)
    diagnostic_rows = [_row(f"diagnostic:{index}:{item.code}", [item.code, item.severity, item.section, item.message], [None] * 4) for index, item in enumerate(diagnostics)]
    section["diagnostics_actions"]["items"].append(_table("diagnostics", f"Diagnostica (stato: {report.readiness.status})", ["Codice", "Severità", "Sezione", "Messaggio"], diagnostic_rows))

    section["appendices_methodology"]["items"].append(_text("appendix-index", "Indice delle appendici", "Indice delle appendici e riferimenti di pagina da compilare dall'impaginazione Typst."))
    for statement in report.detailed_statements:
        section["appendices_methodology"]["items"].append(_statement_table(f"appendix:{statement.id}", statement.title, statement, "row", context=True))

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
            for content_id in content_ids:
                if content_id in expected:
                    raise ValueError(f"duplicate editorial content id: {content_id}")
                expected[content_id] = section["id"]
    return expected
