"""Dossier extensions of the v1 economic model; no renderer-specific formulas."""
from __future__ import annotations

from decimal import Decimal
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


#: Gruppi canonici delle serie strutturali (pagine «Composizioni» e «Pareggio»
#: del dossier v4) e le loro serie, in ordine fisso: il renderer indicizza per
#: id e non deve scegliere nulla. Parità con
#: `frontend/types/final-report-v2.ts` (test di parity).
STRUCTURE_GROUP_SERIES: dict[str, tuple[str, ...]] = {
    "composition_uses": ("fixed_assets", "fixed_assets_share", "current_other", "current_other_share", "cash", "cash_share"),
    "composition_sources": ("equity", "equity_share", "financial_debt", "financial_debt_share", "other_liabilities", "other_liabilities_share"),
    "cost_incidence": ("materials", "services", "personnel", "financial_charges"),
    "break_even": ("fixed_costs", "variable_costs", "contribution_margin", "break_even_revenue", "safety_margin_pct"),
}


class ReportSeries(ContractModel):
    """Una serie period-aligned: valori Decimal o null con il loro motivo."""
    id: str = Field(pattern=ID_PATTERN)
    label: str
    unit: Unit
    values: list[Optional[PlainDecimal]]
    unavailable_reasons: list[Optional[str]]

    @model_validator(mode="after")
    def value_reason_parity(self):
        if len(self.values) != len(self.unavailable_reasons):
            raise ValueError("series values and reasons must align")
        if any((value is None) != (reason is not None) for value, reason in zip(self.values, self.unavailable_reasons)):
            raise ValueError("null series values need explicit unavailability reasons")
        return self


class ReportSeriesGroup(ContractModel):
    id: Literal["composition_uses", "composition_sources", "cost_incidence", "break_even"]
    title: str
    periods: list[StatementPeriod] = Field(min_length=1)
    series: list[ReportSeries] = Field(min_length=1)
    source: str
    methodology: str

    @model_validator(mode="after")
    def aligned_group(self):
        if len({p.id for p in self.periods}) != len(self.periods):
            raise ValueError("structure group period IDs must be unique")
        if tuple(s.id for s in self.series) != STRUCTURE_GROUP_SERIES[self.id]:
            raise ValueError("structure group series must be the canonical ordered list")
        for series in self.series:
            if len(series.values) != len(self.periods):
                raise ValueError("series values must follow the group periods")
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
    structure_series: list[ReportSeriesGroup] = Field(min_length=4, max_length=4)
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
        self._validate_structure_series(indicators)
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

    def _validate_structure_series(self, indicators):
        """Ogni serie strutturale resta agganciata, colonna per colonna, ai prospetti.

        L'aggancio è ciò che rende illegale scambiare il periodo di una serie:
        gli importi letti si ricontrollano contro la riga del prospetto (o
        l'indicatore del catalogo) dello STESSO periodo; i residui contro il
        totale della stessa colonna. Tolleranza di un centesimo solo dove il
        motore arrotonda fisso e variabile separatamente.
        """
        if [g.id for g in self.structure_series] != list(STRUCTURE_GROUP_SERIES):
            raise ValueError("structure series must contain the four canonical groups in order")
        canonical_periods = [p.id for p in self.detailed_statements[0].periods]
        if [p.id for p in self.detailed_statements[1].periods] != canonical_periods:
            raise ValueError("detailed statements must share one period sequence")
        tolerance = Decimal("0.01")
        ce_rows = {r.id: r for r in self.detailed_statements[0].rows}
        bs_rows = {r.id: r for r in self.detailed_statements[1].rows}
        required_rows = ("income_statement:ce01_ricavi_vendite", "income_statement:ce05_materie_prime",
                         "income_statement:ce06_servizi", "income_statement:ce07_godimento_beni",
                         "income_statement:ce08_costi_personale", "income_statement:ce12_oneri_diversi",
                         "balance_sheet:fixed_assets", "balance_sheet:sp09_disponibilita_liquide", "balance_sheet:total_assets",
                         "balance_sheet:sp11_capitale+sp12_riserve+sp13_utile_perdita",
                         "balance_sheet:sp11_capitale+sp12_riserve+sp13_utile_perdita+sp16_debiti_breve+sp17_debiti_lungo+sp14_fondi_rischi+sp15_tfr+sp18_ratei_risconti_passivi")
        if any(row not in ce_rows and row not in bs_rows for row in required_rows):
            raise ValueError("structure ties require the canonical statement rows")
        groups = {g.id: g for g in self.structure_series}
        for group in groups.values():
            if [p.id for p in group.periods] != canonical_periods:
                raise ValueError("structure groups must follow the canonical statement periods")
        series = {group_id: {s.id: s for s in group.series} for group_id, group in groups.items()}

        def ties(group_id, series_id, expected, label):
            values = series[group_id][series_id].values
            for index, want in enumerate(expected):
                mine, rows_known = values[index], all(w is not None for w in want)
                if rows_known and (mine is None or abs(mine - sum(want, Decimal("0"))) > (tolerance if len(want) > 1 else 0)):
                    raise ValueError(f"structure series {label} must match the statement rows at period {canonical_periods[index]}")
                if not rows_known and mine is not None:
                    raise ValueError(f"structure series {label} cannot carry a value where its statement rows are unavailable at period {canonical_periods[index]}")

        def bs_column(row_id):
            return bs_rows[row_id].values

        def ce_column(row_id):
            return ce_rows[row_id].values

        zero = Decimal("0")
        fixed_row = bs_column("balance_sheet:fixed_assets")
        cash_row = bs_column("balance_sheet:sp09_disponibilita_liquide")
        totals = bs_column("balance_sheet:total_assets")
        ties("composition_uses", "fixed_assets", [[f] for f in fixed_row], "fixed_assets")
        ties("composition_uses", "cash", [[c] for c in cash_row], "cash")
        ties("composition_uses", "current_other", [
            [t, None if f is None else -f, None if c is None else -c] for t, f, c in zip(totals, fixed_row, cash_row)], "current_other")
        equity_row = bs_column("balance_sheet:sp11_capitale+sp12_riserve+sp13_utile_perdita")
        ties("composition_sources", "equity", [[e] for e in equity_row], "equity")
        passivo_row = bs_column("balance_sheet:sp11_capitale+sp12_riserve+sp13_utile_perdita+sp16_debiti_breve+sp17_debiti_lungo+sp14_fondi_rischi+sp15_tfr+sp18_ratei_risconti_passivi")
        # Il totale di colonna è già controllato dal ciclo sotto: qui basta che
        # `other_liabilities` non inventi massa quando il passivo è leggibile.
        for index in range(len(canonical_periods)):
            equity, financial = series["composition_sources"]["equity"].values[index], series["composition_sources"]["financial_debt"].values[index]
            other = series["composition_sources"]["other_liabilities"].values[index]
            total = passivo_row[index]
            if None not in (equity, financial, other, total) and abs(equity + financial + other - total) > tolerance:
                raise ValueError(f"composition sources must close on the statement total at period {canonical_periods[index]}")
            if total is None and other is not None:
                raise ValueError(f"composition sources cannot carry a residual without the statement total at period {canonical_periods[index]}")
            fixed = series["break_even"]["fixed_costs"].values[index]
            variable = series["break_even"]["variable_costs"].values[index]
            costs = [ce_column(r)[index] for r in ("income_statement:ce05_materie_prime", "income_statement:ce06_servizi",
                                                   "income_statement:ce07_godimento_beni", "income_statement:ce08_costi_personale",
                                                   "income_statement:ce12_oneri_diversi")]
            if None not in (fixed, variable, *costs) and abs(fixed + variable - sum(costs, zero)) > tolerance:
                raise ValueError(f"break-even costs must split the operating costs at period {canonical_periods[index]}")
            margin = series["break_even"]["contribution_margin"].values[index]
            revenue = ce_column("income_statement:ce01_ricavi_vendite")[index]
            if None not in (margin, revenue, variable) and abs(margin - (revenue - variable)) > tolerance:
                raise ValueError(f"contribution margin must equal revenue minus variable costs at period {canonical_periods[index]}")
        incidence = {"materials": "practice.materials_revenue", "services": "practice.services_revenue",
                     "personnel": "practice.personnel_revenue", "financial_charges": "practice.of_revenue"}
        for series_id, indicator_id in incidence.items():
            if indicator_id not in indicators:
                raise ValueError("cost incidence requires the referenced indicators")
            indicator = indicators[indicator_id]
            if [p.id for p in indicator.periods] != canonical_periods:
                raise ValueError(f"cost incidence reference {indicator_id} must follow the canonical periods")
            values = [None if v is None else v for v in series["cost_incidence"][series_id].values]
            referenced = [None if v is None else v for v in indicator.values]
            if values != referenced:
                raise ValueError(f"cost incidence {series_id} must match indicator {indicator_id} period by period")
        return self
