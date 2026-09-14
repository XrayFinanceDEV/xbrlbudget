import assumptionCatalog from "../../contracts/final_report_assumption_sections.json";

export const FINAL_REPORT_SCHEMA_VERSION = 1 as const;
export const ASSUMPTION_SECTION_CATALOG = assumptionCatalog as readonly AssumptionSectionCatalogEntry[];

export type DecimalString = string;
export type WorkflowType = "infrannuale" | "bilancio" | "startup";
export type Provenance = "user" | "automatic" | "default" | "override" | "ignored" | "legacy_unknown";
export type DiagnosticSeverity = "info" | "warning" | "error";
export type ChartId = "income_results" | "margins" | "cashflows" | "liquidity_debt" | "working_capital_days" | "coverage";
export type NarrativeId = "executive_summary" | "adjustments_and_closing" | "budget_assumptions" | "economic_outlook" | "financial_outlook" | "risks_and_actions";
export type AssumptionSectionKey = "scenario" | "fatturato" | "costi" | "altre-voci-ce" | "circolante" | "pregresso-nuovo" | "imposte";

export interface AssumptionSectionCatalogEntry { key: AssumptionSectionKey; title: string; fields: readonly string[]; nested_fields?: readonly string[] }
export interface CompanyIdentity { id: number; name: string; tax_id?: string | null }
export interface ScenarioIdentity { id: number; name: string; base_year: number; period_months?: number | null }
export interface Periods { historical_year: number | null; closing_year: number | null; forecast_years: number[] }
export interface InfrannualPractice { workflow_type: "infrannuale"; budget_scenario: ScenarioIdentity; source_scenario: ScenarioIdentity; periods: Periods }
export interface AnnualPractice { workflow_type: "bilancio"; budget_scenario: ScenarioIdentity; source_scenario?: ScenarioIdentity | null; periods: Periods }
export interface StartupPractice { workflow_type: "startup"; budget_scenario: ScenarioIdentity; source_scenario?: ScenarioIdentity | null; periods: Periods }
export type Practice = InfrannualPractice | AnnualPractice | StartupPractice;
export interface SourceRevision { source: "historical_financial_year" | "adjustments" | "source_scenario" | "budget_assumptions" | "forecast" | "narrative" | "calculation_engine"; identifier?: string | null; revision?: string | null; revision_at?: string | null; available?: boolean }
export interface Diagnostic { code: string; severity: DiagnosticSeverity; section: string; message: string }
export interface Readiness { status: "ready" | "draft" | "blocked"; reasons?: Diagnostic[] }
export interface SourceDataQuality { status: "complete" | "partial" | "legacy"; diagnostics?: Diagnostic[] }
export interface AdjustmentEntry { id: string; edited_field: string; edited_label: string; edit_delta: DecimalString; counterpart_field: string; counterpart_label: string; counterpart_delta: DecimalString; explanation?: string | null; created_at: string }
export interface Adjustments { confirmed: boolean; entries?: AdjustmentEntry[]; net_effect: DecimalString }
export interface ClosingValue { code: string; label: string; observed?: DecimalString | null; comparable?: DecimalString | null; automatic?: DecimalString | null; override?: DecimalString | null; closing_used: DecimalString }
export interface ExtraAccountingAlerts { retribuzioni: boolean; fornitori: boolean; banche: boolean; inps: boolean; inail: boolean; riscossione: boolean; iva: boolean }
export interface InfrannualClosing { period_end: string; values: ClosingValue[]; extra_accounting_alerts: ExtraAccountingAlerts }
export interface FinancingLoan { name?: string | null; amount: DecimalString; opening_residual: DecimalString; duration_years: number; interest_rate: DecimalString; grace_years: number; balloon_pct: DecimalString }
export interface RunoffPlan { opening: DecimalString; amounts: DecimalString[]; writeoff?: DecimalString[] | null }
export interface TaxRunoffPlan extends RunoffPlan { saldo: DecimalString; rateizzato: DecimalString; acconto_pct: DecimalString }
export interface Pregresso { crediti_commerciali?: RunoffPlan | null; debiti_fornitori?: RunoffPlan | null; debiti_tributari?: TaxRunoffPlan | null; debiti_previdenziali?: RunoffPlan | null; altri_debiti?: RunoffPlan | null }
export interface TemporaryDifference { name: string; kind: "deductible" | "taxable"; maturity: "short" | "long"; opening_amount: DecimalString; additions: DecimalString; reversals: DecimalString; tax_rate?: DecimalString | null }
export type CEOverrideField = "ce01_override" | "ce02_override" | "ce03_override" | "ce03a_override" | "ce04_override" | "ce05_override" | "ce06_override" | "ce07_override" | "ce08_override" | "ce08a_override" | "ce08b_override" | "ce08c_override" | "ce08d_override" | "ce09_override" | "ce09a_override" | "ce09b_override" | "ce09c_override" | "ce09d_override" | "ce10_override" | "ce11_override" | "ce11b_override" | "ce12_override" | "ce13_override" | "ce14_override" | "ce15_override" | "ce16_override" | "ce17_override" | "ce17a_override" | "ce17b_override" | "ce18_override" | "ce19_override" | "ce20_override";
export interface CEOverride { field: CEOverrideField; value: DecimalString }
export interface SPIndexing { field: string; driver: "ricavi" | "acquisti" | "personale" }
export interface SPOverride { field: string; value: DecimalString }
export type AssumptionScalar = DecimalString | boolean | null;
export interface AssumptionValue { field: string; label: string; values: AssumptionScalar[]; provenance: Provenance; active: boolean; financing_loans?: FinancingLoan[] | null; pregresso?: Pregresso | null; temporary_differences?: TemporaryDifference[] | null; ce_overrides?: CEOverride[] | null; sp_indexing?: SPIndexing[] | null; sp_overrides?: SPOverride[] | null }
export interface AssumptionSection { key: AssumptionSectionKey; title: string; assumptions: AssumptionValue[] }
export interface FinancialLine { code: string; label: string; value: DecimalString }
export interface ForecastYear { year: number; income_statement: FinancialLine[]; balance_sheet: FinancialLine[]; cashflow: FinancialLine[]; calculations: FinancialLine[] }
export interface Forecast { years: ForecastYear[] }
export interface ChartMetric { key: string; label: string; values: (DecimalString | null)[] }
export interface ChartSeries { id: ChartId; title: string; unit: "eur" | "percent" | "days" | "ratio"; categories: number[]; series: ChartMetric[] }
export interface NarrativeBlock { id: NarrativeId; text: string; provenance: "ai" | "user" | "migrated"; updated_at: string; source_hash: string; freshness: "fresh" | "stale" | "missing" }
export interface FinalReportBase { schema_version: 1; generated_at: string; model_hash: string; source_hash: string; company: CompanyIdentity; practice: Practice; source_revisions: SourceRevision[]; readiness: Readiness; source_data_quality: SourceDataQuality; adjustments: Adjustments; assumption_sections: AssumptionSection[]; forecast: Forecast; diagnostics?: Diagnostic[]; chart_series: ChartSeries[]; narrative: NarrativeBlock[] }
export type FinalReportModel = (FinalReportBase & { practice: InfrannualPractice; infrannual_closing: InfrannualClosing }) | (FinalReportBase & { practice: AnnualPractice | StartupPractice; infrannual_closing?: never });

const own = (value: unknown, key: string): boolean => typeof value === "object" && value !== null && Object.prototype.hasOwnProperty.call(value, key);
const object = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value);
const array = (value: unknown): value is unknown[] => Array.isArray(value);
const string = (value: unknown): value is string => typeof value === "string";
const number = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const integer = (value: unknown, minimum?: number, maximum?: number): value is number => number(value) && Number.isInteger(value) && (minimum === undefined || value >= minimum) && (maximum === undefined || value <= maximum);
const decimal = (value: unknown): value is DecimalString | null => value === null || (string(value) && /^-?(?:0|[1-9]\d*)(?:\.\d+)?$/.test(value));
const assumptionScalar = (value: unknown): value is AssumptionScalar => decimal(value) || typeof value === "boolean";
const booleanAssumptionFields = new Set(["cash_sweep_enabled", "overdraft_allowed", "previdenza_scales_with_personnel", "tfr_accrual_suspended"]);
const isHash = (value: unknown): value is string => string(value) && /^[0-9a-f]{64}$/.test(value);
const isoDate = (value: unknown): boolean => {
  if (!string(value) || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const [year, month, day] = value.split("-").map(Number);
  const parsed = new Date(Date.UTC(year, month - 1, day));
  return parsed.getUTCFullYear() === year && parsed.getUTCMonth() === month - 1 && parsed.getUTCDate() === day;
};
const isoDatetime = (value: unknown): boolean => {
  if (!string(value) || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})?$/.test(value) || !isoDate(value.slice(0, 10))) return false;
  const [hour, minute, second] = value.slice(11, 19).split(":").map(Number);
  const timezone = value.match(/([+-])(\d{2}):(\d{2})$/);
  return hour < 24 && minute < 60 && second < 60 && (!timezone || (Number(timezone[2]) <= 23 && Number(timezone[3]) <= 59));
};
const required = (value: unknown, keys: readonly string[]): value is Record<string, unknown> => object(value) && keys.every((key) => own(value, key));
const exact = (value: unknown, keys: readonly string[]): value is Record<string, unknown> => required(value, keys) && Object.keys(value).every((key) => keys.includes(key));
const only = (value: unknown, requiredKeys: readonly string[], allowedKeys: readonly string[]): value is Record<string, unknown> => required(value, requiredKeys) && Object.keys(value).every((key) => allowedKeys.includes(key));
const diagnostic = (value: unknown): boolean => exact(value, ["code", "severity", "section", "message"]) && string(value.code) && ["info", "warning", "error"].includes(String(value.severity)) && string(value.section) && string(value.message);
const scenario = (value: unknown): boolean => only(value, ["id", "name", "base_year"], ["id", "name", "base_year", "period_months"]) && integer(value.id) && string(value.name) && integer(value.base_year, 2000, 2100) && (!own(value, "period_months") || value.period_months === null || integer(value.period_months, 1, 12));
const periods = (value: unknown): boolean => exact(value, ["historical_year", "closing_year", "forecast_years"]) && (value.historical_year === null || integer(value.historical_year, 2000, 2100)) && (value.closing_year === null || integer(value.closing_year, 2000, 2100)) && array(value.forecast_years) && value.forecast_years.length > 0 && value.forecast_years.every((year) => integer(year)) && new Set(value.forecast_years).size === value.forecast_years.length;
const practice = (value: unknown): boolean => {
  if (!object(value) || !string(value.workflow_type) || !scenario(value.budget_scenario) || !periods(value.periods)) return false;
  if (value.workflow_type === "infrannuale") return exact(value, ["workflow_type", "budget_scenario", "source_scenario", "periods"]) && scenario(value.source_scenario);
  return ["bilancio", "startup"].includes(value.workflow_type) && only(value, ["workflow_type", "budget_scenario", "periods"], ["workflow_type", "budget_scenario", "source_scenario", "periods"]) && (!own(value, "source_scenario") || value.source_scenario === null || scenario(value.source_scenario));
};
const sourceRevision = (value: unknown): boolean => only(value, ["source"], ["source", "identifier", "revision", "revision_at", "available"]) && ["historical_financial_year", "adjustments", "source_scenario", "budget_assumptions", "forecast", "narrative", "calculation_engine"].includes(String(value.source)) && (!own(value, "identifier") || value.identifier === null || string(value.identifier)) && (!own(value, "revision") || value.revision === null || string(value.revision)) && (!own(value, "revision_at") || value.revision_at === null || isoDatetime(value.revision_at)) && (!own(value, "available") || typeof value.available === "boolean");
const readiness = (value: unknown): boolean => only(value, ["status"], ["status", "reasons"]) && ["ready", "draft", "blocked"].includes(String(value.status)) && (!own(value, "reasons") || (array(value.reasons) && value.reasons.every(diagnostic)));
const sourceDataQuality = (value: unknown): boolean => only(value, ["status"], ["status", "diagnostics"]) && ["complete", "partial", "legacy"].includes(String(value.status)) && (!own(value, "diagnostics") || (array(value.diagnostics) && value.diagnostics.every(diagnostic)));
const adjustment = (value: unknown): boolean => only(value, ["id", "edited_field", "edited_label", "edit_delta", "counterpart_field", "counterpart_label", "counterpart_delta", "created_at"], ["id", "edited_field", "edited_label", "edit_delta", "counterpart_field", "counterpart_label", "counterpart_delta", "explanation", "created_at"]) && string(value.id) && string(value.edited_field) && string(value.edited_label) && decimal(value.edit_delta) && value.edit_delta !== null && string(value.counterpart_field) && string(value.counterpart_label) && decimal(value.counterpart_delta) && value.counterpart_delta !== null && (!own(value, "explanation") || value.explanation === null || string(value.explanation)) && isoDatetime(value.created_at);
const adjustments = (value: unknown): boolean => only(value, ["confirmed", "net_effect"], ["confirmed", "entries", "net_effect"]) && typeof value.confirmed === "boolean" && (!own(value, "entries") || (array(value.entries) && value.entries.every(adjustment))) && decimal(value.net_effect) && value.net_effect !== null;
const closingValue = (value: unknown): boolean => only(value, ["code", "label", "closing_used"], ["code", "label", "observed", "comparable", "automatic", "override", "closing_used"]) && string(value.code) && string(value.label) && ["observed", "comparable", "automatic", "override"].every((key) => !own(value, key) || decimal(value[key])) && decimal(value.closing_used) && value.closing_used !== null;
const alerts = (value: unknown): boolean => exact(value, ["retribuzioni", "fornitori", "banche", "inps", "inail", "riscossione", "iva"]) && Object.values(value).every((item) => typeof item === "boolean");
const infrannualClosing = (value: unknown): boolean => exact(value, ["period_end", "values", "extra_accounting_alerts"]) && isoDate(value.period_end) && array(value.values) && value.values.length > 0 && value.values.every(closingValue) && alerts(value.extra_accounting_alerts);
const financingLoan = (value: unknown): boolean => only(value, ["amount", "opening_residual", "duration_years", "interest_rate", "grace_years", "balloon_pct"], ["name", "amount", "opening_residual", "duration_years", "interest_rate", "grace_years", "balloon_pct"]) && (!own(value, "name") || value.name === null || string(value.name)) && [value.amount, value.opening_residual, value.interest_rate, value.balloon_pct].every((item) => decimal(item) && item !== null) && integer(value.duration_years, 1) && integer(value.grace_years, 0);
const runoffData = (value: unknown): boolean => object(value) && required(value, ["opening", "amounts"]) && decimal(value.opening) && value.opening !== null && array(value.amounts) && value.amounts.every((item) => decimal(item) && item !== null) && (!own(value, "writeoff") || value.writeoff === null || (array(value.writeoff) && value.writeoff.every((item) => decimal(item) && item !== null)));
const runoff = (value: unknown): boolean => only(value, ["opening", "amounts"], ["opening", "amounts", "writeoff"]) && runoffData(value);
const taxRunoff = (value: unknown): boolean => only(value, ["opening", "amounts", "saldo", "rateizzato", "acconto_pct"], ["opening", "amounts", "writeoff", "saldo", "rateizzato", "acconto_pct"]) && runoffData(value) && [value.saldo, value.rateizzato, value.acconto_pct].every((item) => decimal(item) && item !== null);
const pregresso = (value: unknown): boolean => only(value, [], ["crediti_commerciali", "debiti_fornitori", "debiti_tributari", "debiti_previdenziali", "altri_debiti"]) && (!own(value, "crediti_commerciali") || value.crediti_commerciali === null || runoff(value.crediti_commerciali)) && (!own(value, "debiti_fornitori") || value.debiti_fornitori === null || runoff(value.debiti_fornitori)) && (!own(value, "debiti_tributari") || value.debiti_tributari === null || taxRunoff(value.debiti_tributari)) && (!own(value, "debiti_previdenziali") || value.debiti_previdenziali === null || runoff(value.debiti_previdenziali)) && (!own(value, "altri_debiti") || value.altri_debiti === null || runoff(value.altri_debiti));
const temporaryDifference = (value: unknown): boolean => only(value, ["name", "kind", "maturity", "opening_amount", "additions", "reversals"], ["name", "kind", "maturity", "opening_amount", "additions", "reversals", "tax_rate"]) && string(value.name) && ["deductible", "taxable"].includes(String(value.kind)) && ["short", "long"].includes(String(value.maturity)) && [value.opening_amount, value.additions, value.reversals].every(decimal) && (!own(value, "tax_rate") || decimal(value.tax_rate));
const ceOverride = (value: unknown): boolean => exact(value, ["field", "value"]) && ["ce01_override", "ce02_override", "ce03_override", "ce03a_override", "ce04_override", "ce05_override", "ce06_override", "ce07_override", "ce08_override", "ce08a_override", "ce08b_override", "ce08c_override", "ce08d_override", "ce09_override", "ce09a_override", "ce09b_override", "ce09c_override", "ce09d_override", "ce10_override", "ce11_override", "ce11b_override", "ce12_override", "ce13_override", "ce14_override", "ce15_override", "ce16_override", "ce17_override", "ce17a_override", "ce17b_override", "ce18_override", "ce19_override", "ce20_override"].includes(String(value.field)) && decimal(value.value) && value.value !== null;
const spField = (value: unknown): value is string => string(value) && /^sp\d{2}[a-z]?(?:_[a-z]+)*$/.test(value);
const spIndexing = (value: unknown): boolean => exact(value, ["field", "driver"]) && spField(value.field) && ["ricavi", "acquisti", "personale"].includes(String(value.driver));
const spOverride = (value: unknown): boolean => exact(value, ["field", "value"]) && spField(value.field) && decimal(value.value) && value.value !== null;
const assumption = (value: unknown): boolean => {
  if (!only(value, ["field", "label", "values", "provenance", "active"], ["field", "label", "values", "provenance", "active", "financing_loans", "pregresso", "temporary_differences", "ce_overrides", "sp_indexing", "sp_overrides"]) || !string(value.field) || !string(value.label) || !array(value.values) || value.values.length === 0 || !value.values.every(assumptionScalar) || !["user", "automatic", "default", "override", "ignored", "legacy_unknown"].includes(String(value.provenance)) || typeof value.active !== "boolean") return false;
  if (booleanAssumptionFields.has(value.field) ? value.values.some((item) => item !== null && typeof item !== "boolean") : value.values.some((item) => typeof item === "boolean")) return false;
  const nested = ["financing_loans", "pregresso", "temporary_differences", "ce_overrides", "sp_indexing", "sp_overrides"].filter((key) => own(value, key) && value[key] !== null).length;
  return nested <= 1 && (!own(value, "financing_loans") || value.financing_loans === null || (value.field === "financing_loans" && array(value.financing_loans) && value.financing_loans.every(financingLoan))) && (!own(value, "pregresso") || value.pregresso === null || (value.field === "pregresso" && pregresso(value.pregresso))) && (!own(value, "temporary_differences") || value.temporary_differences === null || (value.field === "tax_temporary_differences" && array(value.temporary_differences) && value.temporary_differences.every(temporaryDifference))) && (!own(value, "ce_overrides") || value.ce_overrides === null || (value.field === "ce_overrides" && array(value.ce_overrides) && value.ce_overrides.every(ceOverride))) && (!own(value, "sp_indexing") || value.sp_indexing === null || (value.field === "sp_indexing" && array(value.sp_indexing) && value.sp_indexing.every(spIndexing))) && (!own(value, "sp_overrides") || value.sp_overrides === null || (value.field === "sp_overrides" && array(value.sp_overrides) && value.sp_overrides.every(spOverride)));
};
const line = (value: unknown): boolean => exact(value, ["code", "label", "value"]) && string(value.code) && string(value.label) && decimal(value.value) && value.value !== null;
const forecast = (value: unknown): boolean => exact(value, ["years"]) && array(value.years) && value.years.length > 0 && value.years.every((year) => exact(year, ["year", "income_statement", "balance_sheet", "cashflow", "calculations"]) && integer(year.year, 2000, 2100) && [year.income_statement, year.balance_sheet, year.cashflow, year.calculations].every((statement) => array(statement) && statement.every(line)));
const chart = (value: unknown, forecastYears: readonly number[]): boolean => {
  if (!exact(value, ["id", "title", "unit", "categories", "series"]) || !["income_results", "margins", "cashflows", "liquidity_debt", "working_capital_days", "coverage"].includes(String(value.id)) || !string(value.title) || !["eur", "percent", "days", "ratio"].includes(String(value.unit))) return false;
  const categories = value.categories;
  if (!array(categories) || !categories.every((year) => integer(year)) || categories.length !== forecastYears.length || !categories.every((year, index) => year === forecastYears[index]) || !array(value.series) || value.series.length === 0) return false;
  return value.series.every((metric) => exact(metric, ["key", "label", "values"]) && string(metric.key) && string(metric.label) && array(metric.values) && metric.values.length === categories.length && metric.values.every(decimal));
};
const narrative = (value: unknown): boolean => exact(value, ["id", "text", "provenance", "updated_at", "source_hash", "freshness"]) && ["executive_summary", "adjustments_and_closing", "budget_assumptions", "economic_outlook", "financial_outlook", "risks_and_actions"].includes(String(value.id)) && string(value.text) && ["ai", "user", "migrated"].includes(String(value.provenance)) && isoDatetime(value.updated_at) && isHash(value.source_hash) && ["fresh", "stale", "missing"].includes(String(value.freshness));

/** Runtime boundary for API/fixture JSON.  It intentionally rejects future schemas. */
export function isFinalReportModel(value: unknown): value is FinalReportModel {
  if (!only(value, ["schema_version", "generated_at", "model_hash", "source_hash", "company", "practice", "source_revisions", "readiness", "source_data_quality", "adjustments", "assumption_sections", "forecast", "chart_series", "narrative"], ["schema_version", "generated_at", "model_hash", "source_hash", "company", "practice", "source_revisions", "readiness", "source_data_quality", "adjustments", "infrannual_closing", "assumption_sections", "forecast", "diagnostics", "chart_series", "narrative"])) return false;
  if (value.schema_version !== FINAL_REPORT_SCHEMA_VERSION || !isoDatetime(value.generated_at) || !isHash(value.model_hash) || !isHash(value.source_hash)) return false;
  const report = value as unknown as FinalReportBase & { infrannual_closing?: unknown };
  if (!only(report.company, ["id", "name"], ["id", "name", "tax_id"]) || !integer(report.company.id) || !string(report.company.name) || (own(report.company, "tax_id") && !(string(report.company.tax_id) || report.company.tax_id === null))) return false;
  if (!practice(report.practice)) return false;
  if (report.practice.workflow_type === "infrannuale" ? !infrannualClosing(report.infrannual_closing) : own(report, "infrannual_closing")) return false;
  if (!array(report.source_revisions) || report.source_revisions.length === 0 || !report.source_revisions.every(sourceRevision) || !readiness(report.readiness) || !sourceDataQuality(report.source_data_quality) || !adjustments(report.adjustments)) return false;
  if (!forecast(report.forecast) || report.forecast.years.length !== report.practice.periods.forecast_years.length || report.forecast.years.some((year, index) => year.year !== report.practice.periods.forecast_years[index])) return false;
  if (report.readiness.status === "ready" && (report.source_revisions.some((source) => source.available === false) || report.readiness.reasons?.some((reason) => reason.severity === "error") || report.forecast.years.some((year) => year.income_statement.length === 0 || year.balance_sheet.length === 0 || year.cashflow.length === 0))) return false;
  if (!array(report.assumption_sections) || report.assumption_sections.length !== ASSUMPTION_SECTION_CATALOG.length || report.assumption_sections.some((section, index) => { const catalog = ASSUMPTION_SECTION_CATALOG[index]; return !exact(section, ["key", "title", "assumptions"]) || section.key !== catalog?.key || !string(section.title) || !array(section.assumptions) || !section.assumptions.every((item) => assumption(item) && (catalog?.fields.includes(item.field) || catalog?.nested_fields?.includes(item.field))); })) return false;
  if (!array(report.chart_series) || report.chart_series.length !== 6 || new Set(report.chart_series.map((series) => object(series) ? series.id : "")).size !== 6) return false;
  if (!report.chart_series.every((series) => chart(series, report.practice.periods.forecast_years))) return false;
  if ((own(report, "diagnostics") && (!array(report.diagnostics) || !report.diagnostics.every(diagnostic))) || !array(report.narrative) || report.narrative.length !== 6 || new Set(report.narrative.map((block) => object(block) ? block.id : "")).size !== 6 || !report.narrative.every(narrative)) return false;
  return true;
}

export function parseFinalReportModel(value: unknown): FinalReportModel {
  if (!isFinalReportModel(value)) throw new Error("Unsupported or invalid FinalReportModel v1 payload");
  return value;
}
