"""Dossier extensions of the v1 economic model; no renderer-specific formulas."""
from __future__ import annotations

from typing import Literal, Optional
from pydantic import Field, StrictBool, StrictInt, ValidationInfo, model_validator

from app.schemas.final_report import (
    ChartMetric, ChartSeries, ContractModel, FinalReportModel, ISODate, ISODatetime,
    PlainDecimal, canonical_hash, source_hash,
)

HASH_PATTERN = r"^[0-9a-f]{64}$"
ID_PATTERN = r"^[a-z][a-z0-9_.:+-]*$"
Unit = Literal["eur", "percent", "days", "ratio", "score"]


class DocumentIdentity(ContractModel):
    title: str
    budget_years: list[StrictInt] = Field(min_length=1)
    language: Literal["it-IT"] = "it-IT"
    presentation_unit: Literal["eur", "eur_thousands"] = "eur_thousands"

    @model_validator(mode="after")
    def neutral_title(self):
        if self.budget_years != sorted(set(self.budget_years)):
            raise ValueError("budget_years must be ordered and unique")
        expected = f"Report Budget {self.budget_years[0]}"
        if len(self.budget_years) > 1:
            expected += f" - {self.budget_years[-1]}"
        if self.title != expected:
            raise ValueError("document title must be the neutral budget title")
        return self


class StatementPeriod(ContractModel):
    id: str = Field(pattern=ID_PATTERN)
    year: StrictInt = Field(ge=2000, le=2100)
    label: str
    basis: Literal["historical", "observed", "adjusted", "closing", "forecast"]
    period_months: Optional[StrictInt] = Field(default=None, ge=1, le=12)
    period_end: Optional[ISODate] = None
    source: str = Field(min_length=1)


class DetailedStatementRow(ContractModel):
    id: str = Field(pattern=ID_PATTERN)
    code: str
    label: str
    parent_id: Optional[str] = None
    level: StrictInt = Field(ge=0)
    kind: Literal["section", "group", "detail", "subtotal", "total"]
    applicable: StrictBool
    values: list[Optional[PlainDecimal]]
    unavailable_reasons: list[Optional[str]]
    source: str


class DetailedStatement(ContractModel):
    id: Literal["income_statement", "balance_sheet", "cashflow"]
    title: str
    unit: Literal["eur"] = "eur"
    catalog_version: str
    periods: list[StatementPeriod] = Field(min_length=1)
    rows: list[DetailedStatementRow] = Field(min_length=1)

    @model_validator(mode="after")
    def ordered_rows_and_period_values(self):
        if len({p.id for p in self.periods}) != len(self.periods):
            raise ValueError("statement period IDs must be unique")
        seen = {}
        for row in self.rows:
            if row.id in seen:
                raise ValueError("statement row IDs must be unique")
            if row.parent_id is not None and row.parent_id not in seen:
                raise ValueError("statement parent must precede its child")
            if row.parent_id is not None and row.level != seen[row.parent_id] + 1:
                raise ValueError("statement row level must follow its parent")
            if row.parent_id is None and row.level != 0:
                raise ValueError("root statement rows must have level zero")
            if len(row.values) != len(self.periods) or len(row.unavailable_reasons) != len(self.periods):
                raise ValueError("statement values must follow periods")
            for value, reason in zip(row.values, row.unavailable_reasons):
                if (value is None) != (reason is not None):
                    raise ValueError("null statement values need explicit unavailability reasons")
            if row.kind in ("section", "group") and any(v is not None for v in row.values):
                raise ValueError("statement headers cannot contain financial values")
            seen[row.id] = row.level
        return self


class IndicatorThreshold(ContractModel):
    label: str
    value: PlainDecimal
    source: str = Field(min_length=1)


class IndicatorDefinition(ContractModel):
    id: str = Field(pattern=ID_PATTERN)
    label: str
    family: str
    unit: Unit
    methodology: str = Field(min_length=1)
    convention: str = Field(min_length=1)
    periods: list[StatementPeriod] = Field(min_length=1)
    values: list[Optional[PlainDecimal]]
    unavailable_reasons: list[Optional[str]]
    source: str
    thresholds: list[IndicatorThreshold] = Field(default_factory=list)

    @model_validator(mode="after")
    def period_alignment(self):
        if len({p.id for p in self.periods}) != len(self.periods):
            raise ValueError("indicator period IDs must be unique")
        if len(self.values) != len(self.periods) or len(self.unavailable_reasons) != len(self.periods):
            raise ValueError("indicator values must follow periods")
        if any((value is None) != (reason is not None) for value, reason in zip(self.values, self.unavailable_reasons)):
            raise ValueError("null indicator values need explicit unavailability reasons")
        return self


class DossierChartSeries(ContractModel):
    id: str = Field(pattern=ID_PATTERN)
    title: str
    unit: Unit
    categories: list[StrictInt] = Field(min_length=1)
    series: list[ChartMetric] = Field(min_length=1)
    indicator_ids: list[str] = Field(default_factory=list)
    methodology: str

    @model_validator(mode="after")
    def category_alignment(self):
        if len(set(self.categories)) != len(self.categories):
            raise ValueError("chart categories must be unique")
        if any(len(metric.values) != len(self.categories) for metric in self.series):
            raise ValueError("chart metric length must equal category length")
        if len({metric.key for metric in self.series}) != len(self.series):
            raise ValueError("chart metric keys must be unique")
        return self


class EditorialTablePart(ContractModel):
    statement_id: Literal["income_statement", "balance_sheet", "cashflow"]
    row_ids: list[str] = Field(min_length=1)


class EditorialNoteSlot(ContractModel):
    width_pt: PlainDecimal = Field(gt=0)
    height_pt: PlainDecimal = Field(gt=0)
    font_size_pt: PlainDecimal = Field(gt=0)
    max_lines: StrictInt = Field(gt=0)


class EditorialPage(ContractModel):
    id: str = Field(pattern=ID_PATTERN)
    section_id: str
    content_ids: list[str] = Field(min_length=1)
    table_parts: list[EditorialTablePart] = Field(default_factory=list)
    note_id: str
    note_slot: EditorialNoteSlot


class EditorialPlan(ContractModel):
    layout_version: str
    font_version: str
    asset_version: str
    source_hash: str = Field(pattern=HASH_PATTERN)
    plan_hash: str = Field(pattern=HASH_PATTERN)
    pages: list[EditorialPage] = Field(min_length=1)

    @model_validator(mode="after")
    def reproducible_plan(self, info: ValidationInfo):
        if len({page.id for page in self.pages}) != len(self.pages) or len({page.note_id for page in self.pages}) != len(self.pages):
            raise ValueError("editorial page and note IDs must be unique")
        if not (info.context or {}).get("skip_hash_validation") and self.plan_hash != self.calculate_plan_hash():
            raise ValueError("plan_hash must match the editorial plan")
        return self

    def calculate_plan_hash(self):
        payload = self.model_dump(mode="python")
        payload.pop("plan_hash")
        return canonical_hash(payload, exclude_volatile=False)


class EditorialNote(ContractModel):
    id: str
    content_ids: list[str] = Field(min_length=1)
    text: str = Field(min_length=1)
    provenance: Literal["ai", "user", "automatic"]
    updated_at: ISODatetime
    source_hash: str = Field(pattern=HASH_PATTERN)
    plan_hash: str = Field(pattern=HASH_PATTERN)
    revision: StrictInt = Field(ge=0)
    freshness: Literal["fresh", "stale", "missing"]


class EditorialReadiness(ContractModel):
    status: Literal["pending", "ready", "blocked"]
    reasons: list[str]


class FinalReportModelV2(FinalReportModel):
    schema_version: Literal[2] = 2
    document: DocumentIdentity
    detailed_statements: list[DetailedStatement] = Field(min_length=3, max_length=3)
    indicator_catalog: list[IndicatorDefinition] = Field(min_length=1)
    chart_series: list[ChartSeries | DossierChartSeries] = Field(min_length=6)
    editorial_plan: Optional[EditorialPlan] = None
    editorial_notes: list[EditorialNote] = Field(default_factory=list)
    editorial_readiness: EditorialReadiness

    def calculate_source_hash(self):
        payload = self.model_dump(mode="python")
        for key in ("editorial_plan", "editorial_notes", "editorial_readiness"):
            payload.pop(key, None)
        return source_hash(payload)

    @model_validator(mode="after")
    def dossier_invariants(self):
        if self.document.budget_years != self.practice.periods.forecast_years:
            raise ValueError("document budget years must match forecast periods")
        if [s.id for s in self.detailed_statements] != ["income_statement", "balance_sheet", "cashflow"]:
            raise ValueError("detailed statements must contain CE, SP, cashflow in order")
        indicators = {item.id: item for item in self.indicator_catalog}
        if len(indicators) != len(self.indicator_catalog):
            raise ValueError("indicator IDs must be unique")
        canonical_ids = {"income_results", "margins", "cashflows", "liquidity_debt", "working_capital_days", "coverage"}
        for chart in self.chart_series:
            if chart.id in canonical_ids and not isinstance(chart, ChartSeries):
                raise ValueError("canonical charts must retain their v1 shape")
            if isinstance(chart, DossierChartSeries):
                if any(ref not in indicators for ref in chart.indicator_ids):
                    raise ValueError("chart indicator references must exist")
                if chart.indicator_ids and len(chart.indicator_ids) != len(chart.series):
                    raise ValueError("chart indicator references must align with metrics")
                for metric, ref in zip(chart.series, chart.indicator_ids):
                    indicator = indicators[ref]
                    values = {p.year: v for p, v in zip(indicator.periods, indicator.values) if p.basis == "forecast"}
                    if indicator.unit != chart.unit or metric.values != [values.get(y) for y in chart.categories]:
                        raise ValueError("chart values and units must match referenced indicators")
        if len({n.id for n in self.editorial_notes}) != len(self.editorial_notes):
            raise ValueError("editorial note IDs must be unique")
        if self.editorial_plan is None:
            if self.editorial_notes or self.editorial_readiness.status != "pending":
                raise ValueError("unplanned reports must have pending editorial readiness and no page notes")
        else:
            if self.editorial_plan.source_hash != self.source_hash:
                raise ValueError("editorial plan must refer to current report sources")
            rows = {s.id: {r.id for r in s.rows} for s in self.detailed_statements}
            for page in self.editorial_plan.pages:
                for part in page.table_parts:
                    if len(set(part.row_ids)) != len(part.row_ids) or any(r not in rows[part.statement_id] for r in part.row_ids):
                        raise ValueError("editorial table parts must reference known unique rows")
            notes = {n.id: n for n in self.editorial_notes}
            pages = {p.note_id: p for p in self.editorial_plan.pages}
            if any(n.id not in pages or n.content_ids != pages[n.id].content_ids for n in self.editorial_notes):
                raise ValueError("editorial notes must match planned page contents")
            if self.editorial_readiness.status == "ready" and (
                set(notes) != set(pages) or any(n.freshness != "fresh" or n.source_hash != self.source_hash or n.plan_hash != self.editorial_plan.plan_hash for n in notes.values())
            ):
                raise ValueError("editorially ready reports need a fresh note for every planned page")
        return self
