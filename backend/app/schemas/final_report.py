"""Versioned, renderer-neutral contract for the final practice report.

The report assembler is deliberately not part of this module.  This file is the
wire contract shared by the API, the React report and the later Typst renderer.
Amounts are ``Decimal`` in Python and are emitted as JSON strings, never floats.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
import re
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StrictBool, StrictInt, ValidationInfo, field_serializer, model_serializer, model_validator


FINAL_REPORT_SCHEMA_VERSION = 1
_VOLATILE_HASH_FIELDS = frozenset({
    "generated_at", "model_hash", "source_hash", "created_at", "updated_at",
    "revision_at", "checked_at", "calculated_at", "generated_by",
})
_PLAIN_DECIMAL_RE = re.compile(r"^-?(?:0|[1-9]\d*)(?:\.\d+)?$")


def _plain_decimal(value: object) -> Decimal:
    """Parse the one Decimal spelling admitted by the v1 JSON wire contract."""
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("financial decimals must be finite")
        return value
    if not isinstance(value, str) or not _PLAIN_DECIMAL_RE.fullmatch(value):
        raise ValueError("financial decimals must be plain finite JSON strings (no floats or exponent notation)")
    parsed = Decimal(value)
    if not parsed.is_finite():  # defensive: the grammar already rules this out
        raise ValueError("financial decimals must be finite")
    return parsed


PlainDecimal = Annotated[Decimal, BeforeValidator(_plain_decimal)]
AssumptionScalar = Union[PlainDecimal, StrictBool, None]


def _iso_date(value: object) -> date:
    """Accept date objects in-process and canonical extended ISO dates on the wire."""
    if isinstance(value, datetime):
        raise ValueError("dates must be ISO calendar dates, not datetimes")
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("dates must be extended ISO calendar strings")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError("dates must be valid ISO calendar strings") from error


def _iso_datetime(value: object) -> datetime:
    """Accept datetime objects in-process and RFC 3339-like ISO datetimes on the wire."""
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})?", value,
    ):
        raise ValueError("datetimes must be extended ISO datetime strings")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("datetimes must be valid ISO datetime strings") from error


ISODate = Annotated[date, BeforeValidator(_iso_date)]
ISODatetime = Annotated[datetime, BeforeValidator(_iso_datetime)]


_CATALOG_PATH = Path(__file__).resolve().parents[3] / "contracts" / "final_report_assumption_sections.json"
ASSUMPTION_SECTION_CATALOG: list[dict[str, object]] = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
_CATALOG_FIELDS = {
    section["key"]: frozenset([*section["fields"], *section.get("nested_fields", [])])
    for section in ASSUMPTION_SECTION_CATALOG
}
_BOOLEAN_ASSUMPTION_FIELDS = frozenset({
    "cash_sweep_enabled", "overdraft_allowed",
    "previdenza_scales_with_personnel", "tfr_accrual_suspended",
})


class ContractModel(BaseModel):
    """Strict JSON contract base, with stable decimal strings at the boundary."""
    model_config = ConfigDict(extra="forbid")

    @field_serializer("*", when_used="json", check_fields=False)
    def _serialize_decimal(self, value):
        if isinstance(value, Decimal):
            # ``format(..., "f")`` never emits Decimal exponent notation and
            # preserves accounting precision, including trailing zeroes.
            return format(value, "f")
        return value

    @model_validator(mode="before")
    @classmethod
    def _reject_float_anywhere(cls, value):
        """The canonical wire format never accepts lossy JSON float amounts."""
        def visit(item):
            if isinstance(item, float):
                raise ValueError("financial decimals must be exact JSON strings, never floats")
            if isinstance(item, dict):
                for nested in item.values():
                    visit(nested)
            elif isinstance(item, list):
                for nested in item:
                    visit(nested)
        visit(value)
        return value


def _canonical_value(value, *, volatile: bool) -> object:
    """Return JSON-safe hash data with deterministic object order.

    This operates after Pydantic validation/default materialisation.  Therefore
    Decimal instances are the *only* numeric values canonicalised; a string
    such as an identifier that merely resembles a number is ordinary data.
    """
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="python")
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("canonical JSON rejects non-finite Decimal values")
        normalized = value.normalize()
        return "0" if normalized == 0 else format(normalized, "f")
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
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
    id: StrictInt
    name: str
    tax_id: Optional[str] = None


class ScenarioIdentity(ContractModel):
    id: StrictInt
    name: str
    base_year: StrictInt = Field(ge=2000, le=2100)
    period_months: Optional[StrictInt] = Field(default=None, ge=1, le=12)


class Periods(ContractModel):
    historical_year: Optional[StrictInt] = Field(default=None, ge=2000, le=2100)
    closing_year: Optional[StrictInt] = Field(default=None, ge=2000, le=2100)
    forecast_years: list[StrictInt] = Field(min_length=1)

    @model_validator(mode="after")
    def forecast_years_are_unique(self):
        if len(set(self.forecast_years)) != len(self.forecast_years):
            raise ValueError("forecast years must be unique")
        return self


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
    revision_at: Optional[ISODatetime] = None
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
    edit_delta: PlainDecimal
    counterpart_field: str
    counterpart_label: str
    counterpart_delta: PlainDecimal
    explanation: Optional[str] = None
    created_at: ISODatetime


class Adjustments(ContractModel):
    confirmed: bool
    entries: list[AdjustmentEntry] = Field(default_factory=list)
    net_effect: PlainDecimal


class ClosingValue(ContractModel):
    code: str
    label: str
    observed: Optional[PlainDecimal] = None
    comparable: Optional[PlainDecimal] = None
    automatic: Optional[PlainDecimal] = None
    override: Optional[PlainDecimal] = None
    closing_used: PlainDecimal


class ExtraAccountingAlerts(ContractModel):
    """The seven persisted M1-03 alert flags; no display-only aliases."""
    retribuzioni: bool
    fornitori: bool
    banche: bool
    inps: bool
    inail: bool
    riscossione: bool
    iva: bool


class InfrannualClosing(ContractModel):
    period_end: ISODate
    values: list[ClosingValue] = Field(min_length=1)
    extra_accounting_alerts: ExtraAccountingAlerts


class FinancingLoan(ContractModel):
    name: Optional[str] = None
    amount: PlainDecimal
    opening_residual: PlainDecimal
    duration_years: Optional[StrictInt] = Field(default=None, gt=0)
    interest_rate: PlainDecimal
    grace_years: StrictInt = Field(ge=0)
    balloon_pct: PlainDecimal
    repayments: Optional[list[PlainDecimal]] = None

    @model_serializer(mode="wrap")
    def serialize_v1_loan_shape(self, handler):
        """Il wire v1 non guadagna chiavi nuove per i contratti a durata: `repayments` esce solo
        quando c'e', e `duration_years` solo quando vale (regime 5.1: `repayments` senza durata)."""
        serialized = handler(self)
        if self.duration_years is None:
            serialized.pop("duration_years", None)
        if self.repayments is None:
            serialized.pop("repayments", None)
        return serialized


class RunoffPlan(ContractModel):
    opening: PlainDecimal
    amounts: list[PlainDecimal]
    writeoff: Optional[list[PlainDecimal]] = None


class TaxRunoffPlan(RunoffPlan):
    saldo: PlainDecimal
    rateizzato: PlainDecimal
    acconto_pct: PlainDecimal


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
    opening_amount: PlainDecimal
    additions: PlainDecimal
    reversals: PlainDecimal
    tax_rate: Optional[PlainDecimal] = None


CEOverrideField = Literal[
    "ce01_override", "ce02_override", "ce03_override", "ce03a_override",
    "ce04_override", "ce05_override", "ce06_override", "ce07_override",
    "ce08_override", "ce08a_override", "ce08b_override", "ce08c_override",
    "ce08d_override", "ce09_override", "ce09a_override", "ce09b_override",
    "ce09c_override", "ce09d_override", "ce10_override", "ce11_override",
    "ce11b_override", "ce12_override", "ce13_override", "ce14_override",
    "ce15_override", "ce16_override", "ce17_override", "ce17a_override",
    "ce17b_override", "ce18_override", "ce19_override", "ce20_override",
]


class CEOverride(ContractModel):
    field: CEOverrideField
    value: PlainDecimal


class SPIndexing(ContractModel):
    field: str = Field(pattern=r"^sp\d{2}[a-z]?(?:_[a-z]+)*$")
    driver: Literal["ricavi", "acquisti", "personale"]


class SPOverride(ContractModel):
    field: str = Field(pattern=r"^sp\d{2}[a-z]?(?:_[a-z]+)*$")
    value: PlainDecimal


class AssumptionValue(ContractModel):
    field: str
    label: str
    values: list[AssumptionScalar] = Field(min_length=1)
    # `legacy_unknown` is an explicit read-model outcome for a NULL
    # explicitly_supplied_fields record.  This contract never infers it by
    # comparing an amount with a default; persisting new provenance is M1-05B.
    provenance: Literal["user", "automatic", "default", "override", "ignored", "legacy_unknown"]
    active: bool
    financing_loans: Optional[list[FinancingLoan]] = None
    pregresso: Optional[Pregresso] = None
    temporary_differences: Optional[list[TemporaryDifference]] = None
    ce_overrides: Optional[list[CEOverride]] = None
    sp_indexing: Optional[list[SPIndexing]] = None
    sp_overrides: Optional[list[SPOverride]] = None

    @model_validator(mode="after")
    def nested_value_has_a_known_field(self):
        if self.field in _BOOLEAN_ASSUMPTION_FIELDS:
            if any(value is not None and not isinstance(value, bool) for value in self.values):
                raise ValueError(f"{self.field} accepts only boolean or null scalar values")
        elif any(isinstance(value, bool) for value in self.values):
            raise ValueError("non-boolean assumptions accept only Decimal strings or null scalar values")
        nested = sum((
            self.financing_loans is not None, self.pregresso is not None,
            self.temporary_differences is not None, self.ce_overrides is not None,
            self.sp_indexing is not None, self.sp_overrides is not None,
        ))
        if nested > 1:
            raise ValueError("an assumption value has at most one nested table")
        if self.financing_loans is not None and self.field != "financing_loans":
            raise ValueError("financing_loans data is only valid for the financing_loans field")
        if self.pregresso is not None and self.field != "pregresso":
            raise ValueError("pregresso data is only valid for the pregresso field")
        if self.temporary_differences is not None and self.field != "tax_temporary_differences":
            raise ValueError("temporary_differences data is only valid for tax_temporary_differences")
        if self.ce_overrides is not None and self.field != "ce_overrides":
            raise ValueError("ce_overrides data is only valid for the ce_overrides field")
        if self.sp_indexing is not None and self.field != "sp_indexing":
            raise ValueError("sp_indexing data is only valid for the sp_indexing field")
        if self.sp_overrides is not None and self.field != "sp_overrides":
            raise ValueError("sp_overrides data is only valid for the sp_overrides field")
        return self


class AssumptionSection(ContractModel):
    key: Literal["scenario", "fatturato", "costi", "altre-voci-ce", "circolante", "pregresso-nuovo", "imposte"]
    title: str
    assumptions: list[AssumptionValue] = Field(default_factory=list)

    @model_validator(mode="after")
    def fields_belong_to_section_catalog(self):
        allowed = _CATALOG_FIELDS[self.key]
        invalid = [assumption.field for assumption in self.assumptions if assumption.field not in allowed]
        if invalid:
            raise ValueError(f"assumption fields are not valid for {self.key}: {', '.join(invalid)}")
        return self


class FinancialLine(ContractModel):
    code: str
    label: str
    value: PlainDecimal


class ForecastYear(ContractModel):
    year: StrictInt = Field(ge=2000, le=2100)
    income_statement: list[FinancialLine]
    balance_sheet: list[FinancialLine]
    cashflow: list[FinancialLine]
    calculations: list[FinancialLine]


class Forecast(ContractModel):
    years: list[ForecastYear] = Field(min_length=1)


class ChartMetric(ContractModel):
    key: str
    label: str
    values: list[Optional[PlainDecimal]] = Field(min_length=1)


class ChartSeries(ContractModel):
    id: Literal["income_results", "margins", "cashflows", "liquidity_debt", "working_capital_days", "coverage"]
    title: str
    unit: Literal["eur", "percent", "days", "ratio"]
    categories: list[StrictInt] = Field(min_length=1)
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
    updated_at: ISODatetime
    source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    freshness: Literal["fresh", "stale", "missing"]


class NarrativeEdit(ContractModel):
    """Explicit user-authored replacement for one stable narrative block."""
    id: Literal["executive_summary", "adjustments_and_closing", "budget_assumptions", "economic_outlook", "financial_outlook", "risks_and_actions"]
    text: str = Field(min_length=1)


class NarrativeSaveRequest(ContractModel):
    """A partial save keeps unrelated generated or migrated blocks intact."""
    blocks: list[NarrativeEdit] = Field(min_length=1, max_length=6)

    @model_validator(mode="after")
    def unique_ids(self):
        if len({block.id for block in self.blocks}) != len(self.blocks):
            raise ValueError("narrative block IDs must be unique")
        return self


class FinalReportModel(ContractModel):
    schema_version: Literal[1] = FINAL_REPORT_SCHEMA_VERSION
    generated_at: ISODatetime
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

    @model_serializer(mode="wrap")
    def serialize_v1_wire_shape(self, handler):
        """Annual/startup JSON never has an infrannual closing key, even as null."""
        serialized = handler(self)
        if self.practice.workflow_type != "infrannuale":
            serialized.pop("infrannual_closing", None)
        return serialized

    @model_validator(mode="after")
    def enforce_v1_shape(self, info: ValidationInfo):
        expected_sections = [item["key"] for item in ASSUMPTION_SECTION_CATALOG]
        if [section.key for section in self.assumption_sections] != expected_sections:
            raise ValueError("assumption_sections must use the seven canonical wizard groups in order")
        if len({series.id for series in self.chart_series}) != 6:
            raise ValueError("chart_series must contain each of the six canonical series exactly once")
        if len({block.id for block in self.narrative}) != 6:
            raise ValueError("narrative must contain each of the six canonical blocks exactly once")
        has_closing = "infrannual_closing" in self.model_fields_set
        if self.practice.workflow_type == "infrannuale" and self.infrannual_closing is None:
            raise ValueError("infrannuale reports require infrannual_closing")
        if self.practice.workflow_type != "infrannuale" and has_closing:
            raise ValueError("infrannual_closing is omitted for non-infrannuale reports")
        if [year.year for year in self.forecast.years] != self.practice.periods.forecast_years:
            raise ValueError("forecast years must match practice periods")
        forecast_years = self.practice.periods.forecast_years
        if any(series.categories != forecast_years for series in self.chart_series):
            raise ValueError("chart categories must match practice forecast years")
        if self.readiness.status == "ready":
            if any(not source.available for source in self.source_revisions):
                raise ValueError("ready reports require every source revision to be available")
            if any(reason.severity == "error" for reason in self.readiness.reasons):
                raise ValueError("ready reports cannot carry error readiness reasons")
            # V1's smallest renderable ready forecast includes the three
            # financial statements for every forecast year. Calculations are
            # supplementary and may legitimately be empty.
            required_statements = ("income_statement", "balance_sheet", "cashflow")
            if any(not getattr(year, statement) for year in self.forecast.years for statement in required_statements):
                raise ValueError("ready reports require non-empty income_statement, balance_sheet, and cashflow for every forecast year")
        if not (info.context or {}).get("skip_hash_validation"):
            expected_source = self.calculate_source_hash()
            expected_model = self.calculate_model_hash()
            if self.source_hash != expected_source:
                raise ValueError("source_hash must match the validated report source hash")
            if self.model_hash != expected_model:
                raise ValueError("model_hash must match the validated report model hash")
        return self

    def calculate_source_hash(self) -> str:
        return source_hash(self)

    def calculate_model_hash(self) -> str:
        return model_hash(self)
