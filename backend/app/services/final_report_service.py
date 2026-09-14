"""Read-only assembler for the versioned final-report contract.

The financial engine remains the owner of calculations: this module only
collects persisted records and the canonical ``get_complete_analysis`` output.
"""
from __future__ import annotations

import json
from calendar import monthrange
from datetime import date
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Iterable

from sqlalchemy.orm import Session, joinedload

from app.schemas.final_report import (
    ASSUMPTION_SECTION_CATALOG, AnnualPractice, CompanyIdentity, Diagnostic,
    FinalReportModel, FinancialLine, Forecast, ForecastYear, InfrannualPractice,
    NarrativeBlock, Periods, Readiness, ScenarioIdentity, SourceDataQuality,
    SourceRevision, StartupPractice,
)
from app.services.analysis_service import get_complete_analysis
from app.services.final_report_assumptions import build_assumption_sections
from app.services.final_report_charts import build_chart_series
from app.services.final_report_domain import (
    ChainMatch, build_adjustments, build_infrannual_closing, reconcile_adjustments,
    resolve_source_scenario,
)
from calculations.intra_year_engine import CE_OVERRIDE_FIELDS as INTRA_YEAR_CE_OVERRIDE_FIELDS
from importers.iv_cee_hierarchy import check_quadratura
from database.models import BudgetScenario, FinancialYear, ForecastYear as ForecastYearRecord


class FinalReportNotFound(ValueError):
    """The requested scenario, or a transitive source, is not accessible."""


class FinalReportChainConflict(ValueError):
    """The model cannot name one source because the legacy chain is ambiguous."""


NARRATIVE_IDS = (
    "executive_summary", "adjustments_and_closing", "budget_assumptions",
    "economic_outlook", "financial_outlook", "risks_and_actions",
)
ZERO = Decimal("0")


def _diagnostic(code: str, severity: str, section: str, message: str) -> Diagnostic:
    return Diagnostic(code=code, severity=severity, section=section, message=message)


def _stamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _latest(rows: Iterable[Any]) -> datetime | None:
    values = [getattr(row, "updated_at", None) or getattr(row, "created_at", None) for row in rows]
    values = [value for value in values if isinstance(value, datetime)]
    return max(values) if values else None


def _decimal(value: Any) -> Decimal:
    if value is None:
        return ZERO
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _identity(scenario: BudgetScenario) -> ScenarioIdentity:
    return ScenarioIdentity(
        id=scenario.id, name=scenario.name, base_year=scenario.base_year,
        period_months=scenario.period_months,
    )


def _workflow(scenario: BudgetScenario) -> str:
    if scenario.workflow_type in ("infrannuale", "bilancio", "startup"):
        return scenario.workflow_type
    return "infrannuale" if scenario.scenario_type == "infrannuale" else "bilancio"


def _full_year(db: Session, company_id: int, year: int) -> FinancialYear | None:
    return db.query(FinancialYear).options(
        joinedload(FinancialYear.balance_sheet), joinedload(FinancialYear.income_statement),
    ).filter(
        FinancialYear.company_id == company_id, FinancialYear.year == year,
        (FinancialYear.period_months.is_(None)) | (FinancialYear.period_months == 12),
    ).first()


def _partial_year(db: Session, company_id: int, year: int, months: int | None) -> FinancialYear | None:
    """The persisted progressivo belongs to the intra-year source, not its budget."""
    if months is None:
        return None
    return db.query(FinancialYear).options(
        joinedload(FinancialYear.balance_sheet), joinedload(FinancialYear.income_statement),
    ).filter(
        FinancialYear.company_id == company_id,
        FinancialYear.year == year,
        FinancialYear.period_months == months,
    ).first()


def _statement_map(statement: Any) -> dict[str, Decimal]:
    if statement is None:
        return {}
    return {
        column.name: _decimal(getattr(statement, column.name))
        for column in statement.__table__.columns
        if column.name.startswith(("sp", "ce"))
    }


def _snapshot(financial_year: FinancialYear | None) -> dict[str, Decimal] | None:
    if financial_year is None or not financial_year.original_bs_snapshot or not financial_year.original_is_snapshot:
        return None
    try:
        raw = {**json.loads(financial_year.original_bs_snapshot), **json.loads(financial_year.original_is_snapshot)}
        return {key: _decimal(value) for key, value in raw.items()}
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def _lines(statement: Any) -> list[FinancialLine]:
    """Expose persisted statement fields; aggregate formulas are never copied here."""
    if statement is None:
        return []
    return [
        FinancialLine(code=column.name, label=column.name, value=_decimal(getattr(statement, column.name)))
        for column in statement.__table__.columns if column.name.startswith(("sp", "ce"))
    ]


def _flatten_calculations(value: Any, prefix: str = "") -> list[FinancialLine]:
    if not isinstance(value, dict):
        return []
    lines: list[FinancialLine] = []
    for key in sorted(value):
        item = value[key]
        code = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(item, dict):
            lines.extend(_flatten_calculations(item, code))
        elif item is not None and not isinstance(item, bool):
            try:
                lines.append(FinancialLine(code=code, label=code, value=_decimal(item)))
            except Exception:
                pass
    return lines


def _forecast_rows(scenario: BudgetScenario, analysis: dict[str, Any], required_years: list[int]) -> list[ForecastYear]:
    by_year = {row.year: row for row in scenario.forecast_years}
    cashflows = {
        entry.get("year"): entry for entry in analysis.get("calculations", {}).get("cashflow", {}).get("years", [])
        if isinstance(entry, dict) and entry.get("year") is not None
    }
    calculations = analysis.get("calculations", {}).get("by_year", {})
    result = []
    for year in required_years:
        row = by_year.get(year)
        cashflow = _flatten_calculations(cashflows.get(year, {}), "cashflow")
        result.append(ForecastYear(
            year=year,
            income_statement=_lines(getattr(row, "income_statement", None)),
            balance_sheet=_lines(getattr(row, "balance_sheet", None)),
            cashflow=cashflow,
            calculations=_flatten_calculations(calculations.get(str(year), calculations.get(year, {}))),
        ))
    return result


def _narrative(scenario: BudgetScenario, generated_at: datetime, diagnostics: list[Diagnostic]) -> list[NarrativeBlock]:
    raw = getattr(scenario, "narrative_blocks", None) or {}
    blocks = raw.get("blocks", []) if isinstance(raw, dict) else []
    by_id = {item.get("id"): item for item in blocks if isinstance(item, dict) and item.get("id") in NARRATIVE_IDS}
    output: list[NarrativeBlock] = []
    for ident in NARRATIVE_IDS:
        item = by_id.get(ident)
        if item:
            output.append(NarrativeBlock(
                id=ident, text=str(item.get("text", "")), provenance=item.get("origin", "migrated"),
                updated_at=_stamp(item.get("updated_at") or scenario.narrative_blocks_updated_at),
                source_hash=str(item.get("source_hash") or scenario.narrative_source_hash or "0" * 64),
                freshness="fresh",
            ))
        else:
            diagnostics.append(_diagnostic("narrative_missing", "warning", "narrative", f"Blocco narrativo {ident} non disponibile."))
            output.append(NarrativeBlock(id=ident, text="", provenance="migrated", updated_at=generated_at,
                                         source_hash="0" * 64, freshness="missing"))
    return output


def _source_revisions(
    financial_year: FinancialYear | None, adjustment_year: FinancialYear | None,
    scenario: BudgetScenario, source: BudgetScenario | None,
    diagnostics: list[Diagnostic],
) -> list[SourceRevision]:
    assumptions_at, forecast_at = _latest(scenario.assumptions), _latest(scenario.forecast_years)
    revisions = [
        SourceRevision(source="historical_financial_year", identifier=str(financial_year.id) if financial_year else None,
                       revision=financial_year.source_sha256 if financial_year else None,
                       revision_at=_stamp(financial_year.updated_at) if financial_year and financial_year.updated_at else None,
                       available=financial_year is not None),
        # Rettifiche are owned by the progressivo in an infrannuale practice.
        # A timestamp is all this schema persists as a revision; do not mint a
        # content hash and imply precision that the source does not provide.
        SourceRevision(source="adjustments", identifier=str(adjustment_year.id) if adjustment_year else None,
                       revision=None,
                       revision_at=_stamp(adjustment_year.updated_at) if adjustment_year and adjustment_year.updated_at else None,
                       available=adjustment_year is not None),
        SourceRevision(source="source_scenario", identifier=str(source.id) if source else None,
                       revision=None, revision_at=_stamp(source.updated_at) if source and source.updated_at else None,
                       available=source is not None or _workflow(scenario) != "infrannuale"),
        SourceRevision(source="budget_assumptions", identifier=str(scenario.id), revision=None,
                       revision_at=_stamp(assumptions_at) if assumptions_at else None, available=bool(scenario.assumptions)),
        SourceRevision(source="forecast", identifier=str(scenario.id), revision=None,
                       revision_at=_stamp(forecast_at) if forecast_at else None, available=bool(scenario.forecast_years)),
        SourceRevision(source="narrative", identifier=str(scenario.id), revision=scenario.narrative_source_hash,
                       revision_at=_stamp(scenario.narrative_blocks_updated_at) if scenario.narrative_blocks_updated_at else None,
                       available=True),
        SourceRevision(source="calculation_engine", identifier="analysis_service", revision=None, available=True),
    ]
    for revision in revisions:
        if not revision.available:
            diagnostics.append(_diagnostic("source_revision_unavailable", "warning", "sources",
                                           f"Revisione sorgente {revision.source} non disponibile."))
    return revisions


def assemble_final_report(db: Session, company_id: int, scenario_id: int) -> FinalReportModel:
    """Build one deterministic read model without flushing, writing, or calling AI."""
    with db.no_autoflush:
        scenario = db.query(BudgetScenario).options(
            joinedload(BudgetScenario.company), joinedload(BudgetScenario.assumptions),
            joinedload(BudgetScenario.forecast_years).joinedload(ForecastYearRecord.balance_sheet),
            joinedload(BudgetScenario.forecast_years).joinedload(ForecastYearRecord.income_statement),
        ).filter(BudgetScenario.id == scenario_id, BudgetScenario.company_id == company_id).first()
        if scenario is None:
            raise FinalReportNotFound("Scenario non disponibile")

        # A foreign explicit pointer is an inaccessible transitive resource, never a
        # chain diagnostic that would reveal it.
        if scenario.source_scenario_id is not None:
            pointed = db.get(BudgetScenario, scenario.source_scenario_id)
            if pointed is not None and pointed.company_id != company_id:
                raise FinalReportNotFound("Sorgente scenario non disponibile")

        # The promotion marker is also a transitive scenario reference.  Check
        # it before asking the chain resolver so a cross-tenant id can never be
        # reflected in a "broken chain" diagnostic.
        financial_year = _full_year(db, company_id, scenario.base_year)
        marker_id = getattr(financial_year, "promoted_from_scenario_id", None)
        if marker_id is not None:
            marker_source = db.get(BudgetScenario, marker_id)
            if marker_source is not None and marker_source.company_id != company_id:
                raise FinalReportNotFound("Sorgente scenario non disponibile")

        chain = resolve_source_scenario(db, scenario)
        if chain.match is ChainMatch.AMBIGUOUS:
            raise FinalReportChainConflict("Catena sorgente ambigua")
        source = chain.source_scenario
        workflow = _workflow(scenario)
        diagnostics = list(chain.diagnostics)
        generated_at = datetime.now(timezone.utc)
        adjustment_year = financial_year if workflow != "infrannuale" else None
        if workflow == "infrannuale" and source is not None:
            adjustment_year = _partial_year(db, company_id, source.base_year + 1, source.period_months)
            if adjustment_year is None:
                diagnostics.append(_diagnostic("chain_partial_year_missing", "error", "chain", "Il progressivo infrannuale collegato non è disponibile."))
        entries: list[Any] = []
        if adjustment_year and adjustment_year.rettifiche_log:
            try:
                parsed = json.loads(adjustment_year.rettifiche_log)
                entries = parsed if isinstance(parsed, list) else []
                if not isinstance(parsed, list):
                    diagnostics.append(_diagnostic("adjustments_log_invalid", "error", "adjustments", "Log rettifiche non valido."))
            except (TypeError, json.JSONDecodeError):
                diagnostics.append(_diagnostic("adjustments_log_invalid", "error", "adjustments", "Log rettifiche non leggibile."))
        try:
            adjustments = build_adjustments(entries)
        except (ArithmeticError, TypeError, ValueError):
            # Old hand-edited JSON can contain a non-decimal movement.  It is
            # source data, not a reason for the read endpoint to fail.
            diagnostics.append(_diagnostic("adjustments_log_invalid", "error", "adjustments", "Log rettifiche contiene importi non validi."))
            entries = []
            adjustments = build_adjustments(entries)
        before = _snapshot(adjustment_year)
        after = {**_statement_map(getattr(adjustment_year, "balance_sheet", None)), **_statement_map(getattr(adjustment_year, "income_statement", None))}
        if entries and before is not None:
            reconciliation = reconcile_adjustments(before, after, entries)
            diagnostics.extend(reconciliation.diagnostics)
        elif adjustments.entries:
            diagnostics.append(_diagnostic("adjustments_reconciliation_unavailable", "warning", "adjustments", "Snapshot precedente alle rettifiche non disponibile."))
        if adjustments.entries and not adjustments.confirmed:
            diagnostics.append(_diagnostic("adjustments_unconfirmed", "error", "adjustments", "Le rettifiche economiche non sono state confermate."))

        analysis = get_complete_analysis(db, company_id, scenario_id)
        wanted = sorted({row.forecast_year for row in scenario.assumptions} | {row.year for row in scenario.forecast_years})
        if not wanted:
            wanted = [scenario.base_year + 1]
            diagnostics.append(_diagnostic("forecast_missing", "error", "forecast", "Forecast persistito non disponibile."))
        actual_years = {row.year for row in scenario.forecast_years}
        missing = sorted(set(wanted) - actual_years)
        if missing:
            diagnostics.append(_diagnostic("forecast_years_missing", "error", "forecast", f"Anni forecast mancanti: {', '.join(map(str, missing))}."))
        if analysis.get("forecast_stale"):
            diagnostics.append(_diagnostic("forecast_stale", "error", "forecast", "Forecast precedente alle ipotesi salvate."))

        by_forecast_year = {row.year: row for row in scenario.forecast_years}
        for year in wanted:
            row = by_forecast_year.get(year)
            if row is None:
                continue
            if row.balance_sheet is None or row.income_statement is None:
                diagnostics.append(_diagnostic("forecast_statements_incomplete", "error", "forecast", f"Forecast {year} privo di stato patrimoniale o conto economico."))
                continue
            validation = check_quadratura(_statement_map(row.balance_sheet), _statement_map(row.income_statement))
            if not validation.semantic_valid:
                diagnostics.append(_diagnostic("forecast_unbalanced", "error", "forecast", f"Forecast {year} non supera la quadratura semantica."))

        cashflow_years = analysis.get("calculations", {}).get("cashflow", {}).get("years", [])
        cashflow_available = {entry.get("year") for entry in cashflow_years if isinstance(entry, dict)}
        for year in wanted:
            if year not in cashflow_available:
                diagnostics.append(_diagnostic("forecast_cashflow_missing", "error", "forecast", f"Cashflow forecast {year} non disponibile."))

        if workflow == "infrannuale" and source is None:
            # A missing or broken link is still representable, but a promoted
            # budget cannot be finalised without naming its infrannual source.
            # Only ambiguity is a 409 because only ambiguity prevents choosing
            # a deterministic model at all.
            diagnostics.append(_diagnostic("chain_blocked", "error", "chain", "La catena della pratica è assente o interrotta."))

        try:
            assumptions = build_assumption_sections(scenario.assumptions)
            sections, assumption_diagnostics = assumptions.sections, assumptions.diagnostics
            diagnostics.extend(assumption_diagnostics)
        except ValueError:
            from app.schemas.final_report import AssumptionSection
            sections = [AssumptionSection(key=item["key"], title=item["title"], assumptions=[]) for item in ASSUMPTION_SECTION_CATALOG]
            diagnostics.append(_diagnostic("assumptions_missing", "error", "assumptions", "Ipotesi budget non disponibili."))

        forecasts = _forecast_rows(scenario, analysis, wanted)
        charts = build_chart_series(
            [by_forecast_year.get(year, type("ForecastStub", (), {"year": year})()) for year in wanted],
            calculations_by_year=analysis.get("calculations", {}).get("by_year", {}),
            cashflow_years=analysis.get("calculations", {}).get("cashflow", {}).get("years", []),
        )
        narrative = _narrative(scenario, generated_at, diagnostics)
        revisions = _source_revisions(financial_year, adjustment_year, scenario, source, diagnostics)
        if financial_year is None:
            diagnostics.append(_diagnostic("historical_year_missing", "error", "sources", "Bilancio storico non disponibile."))

        periods = Periods(historical_year=scenario.base_year, closing_year=scenario.base_year if workflow == "infrannuale" else None, forecast_years=wanted)
        # The infrannuale scenario is its own practice head.  The contract has a
        # required source identity for that workflow, so name the head rather than
        # fabricate a parent; a broken link remains explicitly diagnostic.
        practice_source = source or scenario if workflow == "infrannuale" else source
        practice_kwargs = dict(workflow_type=workflow, budget_scenario=_identity(scenario), source_scenario=_identity(practice_source) if practice_source else None, periods=periods)
        if workflow == "infrannuale":
            partial_year = adjustment_year if source is not None else None
            observed = {**_statement_map(getattr(partial_year, "balance_sheet", None)), **_statement_map(getattr(partial_year, "income_statement", None))}
            comparable_year = _full_year(db, company_id, source.base_year) if source is not None else None
            comparable = {**_statement_map(getattr(comparable_year, "balance_sheet", None)), **_statement_map(getattr(comparable_year, "income_statement", None))}
            automatic_row = next((item for item in (source.forecast_years if source is not None else []) if item.year == scenario.base_year), None)
            automatic = {**_statement_map(getattr(automatic_row, "balance_sheet", None)), **_statement_map(getattr(automatic_row, "income_statement", None))}
            source_assumption = next((item for item in (source.assumptions if source is not None else []) if item.forecast_year == scenario.base_year), None)
            sp_overrides = getattr(source_assumption, "sp_overrides", None) if source_assumption else None
            overrides = {
                statement_field: _decimal(getattr(source_assumption, assumption_field))
                for statement_field, assumption_field in INTRA_YEAR_CE_OVERRIDE_FIELDS.items()
                if source_assumption is not None
                and getattr(source_assumption, assumption_field) is not None
            }
            if isinstance(sp_overrides, dict):
                overrides.update({key: _decimal(value) for key, value in sp_overrides.items() if value is not None})
            # The persisted source forecast already includes explicit overrides.
            # Its pre-override automatic value is not stored, so exposing the
            # same number as both automatic and override would invent provenance.
            automatic = {key: value for key, value in automatic.items() if key not in overrides}
            closing_rows = [
                {"code": key, "label": key, "observed": observed.get(key), "comparable": comparable.get(key),
                 "automatic": automatic.get(key), "override": overrides.get(key)}
                for key in sorted(set(observed) | set(comparable) | set(automatic) | set(overrides))
                if any(value is not None for value in (observed.get(key), automatic.get(key), overrides.get(key)))
            ]
            if not closing_rows:
                closing_rows = [{"code": "unavailable", "label": "Chiusura non disponibile", "observed": ZERO}]
                diagnostics.append(_diagnostic("closing_missing", "error", "closing", "Chiusura infrannuale non disponibile."))
            period_month = source.period_months if source is not None and source.period_months else 12
            period_end = date(scenario.base_year, period_month, monthrange(scenario.base_year, period_month)[1])
            closing = build_infrannual_closing(period_end=period_end, rows=closing_rows,
                                               alerts=source.extra_accounting_alerts if source is not None else None)
            practice = InfrannualPractice(**practice_kwargs)
        elif workflow == "startup":
            closing, practice = None, StartupPractice(**practice_kwargs)
        else:
            closing, practice = None, AnnualPractice(**practice_kwargs)

        errors = [item for item in diagnostics if item.severity == "error"]
        warnings = [item for item in diagnostics if item.severity == "warning"]
        readiness = Readiness(status="blocked" if errors else "draft" if warnings else "ready", reasons=[*errors, *warnings])
        quality = SourceDataQuality(status="legacy" if any(item.code.startswith("legacy_") for item in diagnostics) else "partial" if errors or warnings else "complete", diagnostics=diagnostics)

        payload = dict(schema_version=1, generated_at=generated_at, model_hash="0" * 64, source_hash="0" * 64,
                       company=CompanyIdentity(id=scenario.company.id, name=scenario.company.name, tax_id=scenario.company.tax_id),
                       practice=practice, source_revisions=revisions, readiness=readiness, source_data_quality=quality,
                       adjustments=adjustments, assumption_sections=sections, forecast=Forecast(years=forecasts),
                       diagnostics=diagnostics, chart_series=charts, narrative=narrative)
        if closing is not None:
            payload["infrannual_closing"] = closing
        report = FinalReportModel.model_validate(payload, context={"skip_hash_validation": True})
        payload["source_hash"] = report.calculate_source_hash()
        report = FinalReportModel.model_validate(payload, context={"skip_hash_validation": True})
        payload["model_hash"] = report.calculate_model_hash()
        return FinalReportModel.model_validate(payload)
