"""Versioned, renderer-neutral contract for the final practice report.

The report assembler is deliberately not part of this module.  This file is the
wire contract shared by the API, the React report and the later Typst renderer.
Amounts are ``Decimal`` in Python and are emitted as JSON strings, never floats.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator


FINAL_REPORT_SCHEMA_VERSION = 1
_VOLATILE_HASH_FIELDS = frozenset({
    "generated_at", "model_hash", "source_hash", "created_at", "updated_at",
    "revision_at", "checked_at", "calculated_at", "generated_by",
})


class ContractModel(BaseModel):
    """Strict JSON contract base, with stable decimal strings at the boundary."""
    model_config = ConfigDict(extra="forbid")

    @field_serializer("*", when_used="json", check_fields=False)
    def _serialize_decimal(self, value):
        if isinstance(value, Decimal):
            # ``str`` preserves the supplied accounting precision (including zeroes).
            return str(value)
        return value


def _canonical_value(value, *, volatile: bool) -> object:
    """Return JSON-safe data with deterministic object order and decimal spelling."""
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="python")
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list) or isinstance(value, tuple):
        return [_canonical_value(item, volatile=volatile) for item in value]
    if isinstance(value, dict):
        return {
            key: _canonical_value(item, volatile=volatile)
            for key, item in sorted(value.items())
            if not (volatile and key in _VOLATILE_HASH_FIELDS)
        }
    return value


def canonical_json(value: object, *, exclude_volatile: bool = True) -> str:
    """Canonical UTF-8 JSON used for reproducible report hashes.

    Arrays retain their semantic order.  Object keys are sorted, null is kept,
    and Decimal values become exact strings only at this serialization boundary.
    """
    return json.dumps(
        _canonical_value(value, volatile=exclude_volatile),
        ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False,
    )


def canonical_hash(value: object, *, exclude_volatile: bool = True) -> str:
    return hashlib.sha256(canonical_json(value, exclude_volatile=exclude_volatile).encode("utf-8")).hexdigest()


def source_hash(value: object) -> str:
    """Hash source/economic content only, deliberately excluding report prose.

    Narrative blocks retain their own source hashes; changing a comment therefore
    changes ``model_hash`` but does not claim that a financial source changed.
    """
    canonical = _canonical_value(value, volatile=True)
    if isinstance(canonical, dict):
        canonical.pop("narrative", None)
    return hashlib.sha256(json.dumps(canonical, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False).encode("utf-8")).hexdigest()


def model_hash(value: object) -> str:
    """Hash report economic/narrative content, excluding every volatile field."""
    return canonical_hash(value)


class CompanyIdentity(ContractModel):
    id: int
    name: str
    tax_id: Optional[str] = None


class ScenarioIdentity(ContractModel):
    id: int
    name: str
    base_year: int = Field(ge=2000, le=2100)
    period_months: Optional[int] = Field(default=None, ge=1, le=12)


class Periods(ContractModel):
    historical_year: Optional[int] = Field(default=None, ge=2000, le=2100)
    closing_year: Optional[int] = Field(default=None, ge=2000, le=2100)
    forecast_years: list[int] = Field(min_length=1)


class InfrannualPractice(ContractModel):
    workflow_type: Literal["infrannuale"]
    budget_scenario: ScenarioIdentity
    source_scenario: ScenarioIdentity
    periods: Periods


class AnnualPractice(ContractModel):
    workflow_type: Literal["bilancio"]
    budget_scenario: ScenarioIdentity
    source_scenario: Optional[ScenarioIdentity] = None
    periods: Periods


class StartupPractice(ContractModel):
    workflow_type: Literal["startup"]
    budget_scenario: ScenarioIdentity
    source_scenario: Optional[ScenarioIdentity] = None
    periods: Periods


Practice = Annotated[Union[InfrannualPractice, AnnualPractice, StartupPractice], Field(discriminator="workflow_type")]


class SourceRevision(ContractModel):
    source: Literal["historical_financial_year", "adjustments", "source_scenario", "budget_assumptions", "forecast", "narrative", "calculation_engine"]
    identifier: Optional[str] = None
    revision: Optional[str] = None
    revision_at: Optional[datetime] = None
    available: bool = True


class Diagnostic(ContractModel):
    code: str
    severity: Literal["info", "warning", "error"]
    section: str
    message: str


class Readiness(ContractModel):
    status: Literal["ready", "draft", "blocked"]
    reasons: list[Diagnostic] = Field(default_factory=list)


class SourceDataQuality(ContractModel):
    status: Literal["complete", "partial", "legacy"]
    diagnostics: list[Diagnostic] = Field(default_factory=list)


class AdjustmentEntry(ContractModel):
    id: str
    edited_field: str
    edited_label: str
    edit_delta: Decimal
    counterpart_field: str
    counterpart_label: str
    counterpart_delta: Decimal
    explanation: Optional[str] = None
    created_at: datetime


class Adjustments(ContractModel):
    confirmed: bool
    entries: list[AdjustmentEntry] = Field(default_factory=list)
    net_effect: Decimal


class ClosingValue(ContractModel):
    code: str
    label: str
    observed: Optional[Decimal] = None
    comparable: Optional[Decimal] = None
    automatic: Optional[Decimal] = None
    override: Optional[Decimal] = None
    closing_used: Decimal


class InfrannualClosing(ContractModel):
    period_end: str
    values: list[ClosingValue] = Field(min_length=1)
    extra_accounting_alerts: list[str] = Field(default_factory=list)


class FinancingLoan(ContractModel):
    name: Optional[str] = None
    amount: Decimal
    opening_residual: Decimal
    duration_years: int = Field(gt=0)
    interest_rate: Decimal
    grace_years: int = Field(ge=0)
    balloon_pct: Decimal


class RunoffPlan(ContractModel):
    opening: Decimal
    amounts: list[Decimal]
    writeoff: Optional[list[Decimal]] = None


class TaxRunoffPlan(RunoffPlan):
    saldo: Decimal
    rateizzato: Decimal
    acconto_pct: Decimal


class Pregresso(ContractModel):
    crediti_commerciali: Optional[RunoffPlan] = None
    debiti_fornitori: Optional[RunoffPlan] = None
    debiti_tributari: Optional[TaxRunoffPlan] = None
    debiti_previdenziali: Optional[RunoffPlan] = None
    altri_debiti: Optional[RunoffPlan] = None


class TemporaryDifference(ContractModel):
    name: str
    kind: Literal["deductible", "taxable"]
    maturity: Literal["short", "long"]
    opening_amount: Decimal
    additions: Decimal
    reversals: Decimal
    tax_rate: Optional[Decimal] = None


class AssumptionValue(ContractModel):
    field: str
    label: str
    values: list[Optional[Decimal]] = Field(min_length=1)
    provenance: Literal["user", "automatic", "default", "override", "ignored", "legacy_unknown"]
    active: bool
    financing_loans: Optional[list[FinancingLoan]] = None
    pregresso: Optional[Pregresso] = None
    temporary_differences: Optional[list[TemporaryDifference]] = None

    @model_validator(mode="after")
    def nested_value_has_a_known_field(self):
        nested = (self.financing_loans is not None) + (self.pregresso is not None) + (self.temporary_differences is not None)
        if nested > 1:
            raise ValueError("an assumption value has at most one nested table")
        return self


class AssumptionSection(ContractModel):
    key: Literal["scenario", "fatturato", "costi", "altre-voci-ce", "circolante", "pregresso-nuovo", "imposte"]
    title: str
    assumptions: list[AssumptionValue] = Field(default_factory=list)


class FinancialLine(ContractModel):
    code: str
    label: str
    value: Decimal


class ForecastYear(ContractModel):
    year: int = Field(ge=2000, le=2100)
    income_statement: list[FinancialLine]
    balance_sheet: list[FinancialLine]
    cashflow: list[FinancialLine]
    calculations: list[FinancialLine]


class Forecast(ContractModel):
    years: list[ForecastYear] = Field(min_length=1)


class ChartMetric(ContractModel):
    key: str
    label: str
    values: list[Optional[Decimal]] = Field(min_length=1)


class ChartSeries(ContractModel):
    id: Literal["income_results", "margins", "cashflows", "liquidity_debt", "working_capital_days", "coverage"]
    title: str
    unit: Literal["eur", "percent", "days", "ratio"]
    categories: list[int] = Field(min_length=1)
    series: list[ChartMetric] = Field(min_length=1)

    @model_validator(mode="after")
    def all_metrics_follow_categories(self):
        if any(len(metric.values) != len(self.categories) for metric in self.series):
            raise ValueError("chart metric length must equal category length")
        return self


class NarrativeBlock(ContractModel):
    id: Literal["executive_summary", "adjustments_and_closing", "budget_assumptions", "economic_outlook", "financial_outlook", "risks_and_actions"]
    text: str
    provenance: Literal["ai", "user", "migrated"]
    updated_at: datetime
    source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    freshness: Literal["fresh", "stale", "missing"]


class FinalReportModel(ContractModel):
    schema_version: Literal[1] = FINAL_REPORT_SCHEMA_VERSION
    generated_at: datetime
    model_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    company: CompanyIdentity
    practice: Practice
    source_revisions: list[SourceRevision] = Field(min_length=1)
    readiness: Readiness
    source_data_quality: SourceDataQuality
    adjustments: Adjustments
    infrannual_closing: Optional[InfrannualClosing] = None
    assumption_sections: list[AssumptionSection] = Field(min_length=7, max_length=7)
    forecast: Forecast
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    chart_series: list[ChartSeries] = Field(min_length=6, max_length=6)
    narrative: list[NarrativeBlock] = Field(min_length=6, max_length=6)

    @model_validator(mode="after")
    def enforce_v1_shape(self):
        expected_sections = [item["key"] for item in ASSUMPTION_SECTION_CATALOG]
        if [section.key for section in self.assumption_sections] != expected_sections:
            raise ValueError("assumption_sections must use the seven canonical wizard groups in order")
        if len({series.id for series in self.chart_series}) != 6:
            raise ValueError("chart_series must contain each of the six canonical series exactly once")
        if len({block.id for block in self.narrative}) != 6:
            raise ValueError("narrative must contain each of the six canonical blocks exactly once")
        if self.practice.workflow_type == "infrannuale" and self.infrannual_closing is None:
            raise ValueError("infrannuale reports require infrannual_closing")
        if self.practice.workflow_type != "infrannuale" and self.infrannual_closing is not None:
            raise ValueError("only infrannuale reports may contain infrannual_closing")
        if [year.year for year in self.forecast.years] != self.practice.periods.forecast_years:
            raise ValueError("forecast years must match practice periods")
        return self

    def calculate_source_hash(self) -> str:
        return source_hash(self)

    def calculate_model_hash(self) -> str:
        return model_hash(self)


_CATALOG_PATH = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "final_report" / "assumption_sections.json"
ASSUMPTION_SECTION_CATALOG: list[dict[str, object]] = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
