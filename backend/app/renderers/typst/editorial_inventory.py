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
            [assumption.label, *values, _label(_PROVENANCE_LABELS, assumption.provenance), assumption.active,
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
        for row in _assumption_rows(section, period_labels):
            # Scalar rows have one label + all year values + provenance/active/reason.
            if row["id"].endswith(":value"):
                base_rows.append(row)
            else:
                detail_rows.append(row)
        base_columns = ["Parametro", *period_labels, "Provenienza", "Attiva", "Indisponibilità"]
        base_items.append(_table(f"assumptions:{section.key}", section.title, base_columns, base_rows))
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
        section[_NARRATIVE_SECTION[narrative.id]]["items"].append(
            _text(narrative.id, _NARRATIVE_TITLES[narrative.id], narrative.text))

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
    # Il catalogo per-voce con i blocchi «practice.pfn / Unità: ratio / Convenzione:
    # pratica-v1…» non si stampa più: gli indicatori diventano due tabelle F/G
    # (indicatore × periodo, unità in colonna) e una tabella compatta di
    # metodologia e convenzione in «Allegati e metodologia» (M2-02B difetto 2).
    indicator_columns = ["Indicatore", "Unità", *[_period_label(period) for period in indicator_periods.values()], "Indisponibilità"]

    def _indicator_row(indicator: Any) -> dict[str, Any]:
        values_by_period = dict(zip((period.id for period in indicator.periods), indicator.values))
        values = [values_by_period.get(identifier) for identifier in indicator_periods]
        reasons = "; ".join(
            f"{_period_label(period)} — {_label(_UNAVAILABLE_REASON_LABELS, reason)}"
            for period, reason in zip(indicator.periods, indicator.unavailable_reasons) if reason)
        return _row(f"indicator:{indicator.id}", [indicator.label, _label(_UNIT_LABELS, indicator.unit), *values,
                     _missing(reasons) if reasons else None],
                     [None, None, *([indicator.unit] * len(values)), None])

    practice_rows = [_indicator_row(indicator) for indicator in report.indicator_catalog if indicator.id.startswith("practice.")]
    analytical_rows = [_indicator_row(indicator) for indicator in report.indicator_catalog if not indicator.id.startswith("practice.")]
    indicator_tables: list[dict[str, Any]] = []
    if practice_rows:
        indicator_tables.append(_periodic_table(_table("indicator-practice-table", "Tabella F — Indicatori della pratica", indicator_columns, practice_rows), value_start=2, part_size=INDICATOR_PART_SIZE))
    if analytical_rows:
        indicator_tables.append(_periodic_table(_table("indicator-analytical-table", "Tabella G — Indici del report analitico", indicator_columns, analytical_rows), value_start=2, part_size=INDICATOR_PART_SIZE))

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
    methodology_rows = [_row(
        f"indicator-method:{indicator.id}",
        [indicator.label, indicator.family, indicator.methodology, indicator.convention,
         "; ".join(f"{threshold.label}: {_exact(threshold.value)} ({threshold.source})" for threshold in indicator.thresholds) or None],
        [None, None, None, None, None]) for indicator in report.indicator_catalog]
    section["appendices_methodology"]["items"].append(_table("indicator-methodology", "Metodologia e convenzioni degli indicatori", ["Indicatore", "Famiglia", "Metodologia", "Convenzione", "Soglie"], methodology_rows))

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
