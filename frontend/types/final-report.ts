import assumptionCatalog from "../../tests/fixtures/final_report/assumption_sections.json";

export const FINAL_REPORT_SCHEMA_VERSION = 1 as const;
export const ASSUMPTION_SECTION_CATALOG = assumptionCatalog as readonly AssumptionSectionCatalogEntry[];

export type DecimalString = string;
export type WorkflowType = "infrannuale" | "bilancio" | "startup";
export type Provenance = "user" | "automatic" | "default" | "override" | "ignored" | "legacy_unknown";
export type DiagnosticSeverity = "info" | "warning" | "error";
export type ChartId = "income_results" | "margins" | "cashflows" | "liquidity_debt" | "working_capital_days" | "coverage";
export type NarrativeId = "executive_summary" | "adjustments_and_closing" | "budget_assumptions" | "economic_outlook" | "financial_outlook" | "risks_and_actions";
export type AssumptionSectionKey = "scenario" | "fatturato" | "costi" | "altre-voci-ce" | "circolante" | "pregresso-nuovo" | "imposte";

export interface AssumptionSectionCatalogEntry { key: AssumptionSectionKey; title: string; fields: readonly string[] }
export interface CompanyIdentity { id: number; name: string; tax_id: string | null }
export interface ScenarioIdentity { id: number; name: string; base_year: number; period_months?: number | null }
export interface Periods { historical_year: number | null; closing_year: number | null; forecast_years: number[] }
export interface InfrannualPractice { workflow_type: "infrannuale"; budget_scenario: ScenarioIdentity; source_scenario: ScenarioIdentity; periods: Periods }
export interface AnnualPractice { workflow_type: "bilancio"; budget_scenario: ScenarioIdentity; source_scenario: ScenarioIdentity | null; periods: Periods }
export interface StartupPractice { workflow_type: "startup"; budget_scenario: ScenarioIdentity; source_scenario: ScenarioIdentity | null; periods: Periods }
export type Practice = InfrannualPractice | AnnualPractice | StartupPractice;
export interface SourceRevision { source: "historical_financial_year" | "adjustments" | "source_scenario" | "budget_assumptions" | "forecast" | "narrative" | "calculation_engine"; identifier: string | null; revision: string | null; revision_at: string | null; available: boolean }
export interface Diagnostic { code: string; severity: DiagnosticSeverity; section: string; message: string }
export interface Readiness { status: "ready" | "draft" | "blocked"; reasons: Diagnostic[] }
export interface SourceDataQuality { status: "complete" | "partial" | "legacy"; diagnostics: Diagnostic[] }
export interface AdjustmentEntry { id: string; edited_field: string; edited_label: string; edit_delta: DecimalString; counterpart_field: string; counterpart_label: string; counterpart_delta: DecimalString; explanation: string | null; created_at: string }
export interface Adjustments { confirmed: boolean; entries: AdjustmentEntry[]; net_effect: DecimalString }
export interface ClosingValue { code: string; label: string; observed: DecimalString | null; comparable: DecimalString | null; automatic: DecimalString | null; override: DecimalString | null; closing_used: DecimalString }
export interface InfrannualClosing { period_end: string; values: ClosingValue[]; extra_accounting_alerts: string[] }
export interface FinancingLoan { name: string | null; amount: DecimalString; opening_residual: DecimalString; duration_years: number; interest_rate: DecimalString; grace_years: number; balloon_pct: DecimalString }
export interface RunoffPlan { opening: DecimalString; amounts: DecimalString[]; writeoff: DecimalString[] | null }
export interface TaxRunoffPlan extends RunoffPlan { saldo: DecimalString; rateizzato: DecimalString; acconto_pct: DecimalString }
export interface Pregresso { crediti_commerciali: RunoffPlan | null; debiti_fornitori: RunoffPlan | null; debiti_tributari: TaxRunoffPlan | null; debiti_previdenziali: RunoffPlan | null; altri_debiti: RunoffPlan | null }
export interface TemporaryDifference { name: string; kind: "deductible" | "taxable"; maturity: "short" | "long"; opening_amount: DecimalString; additions: DecimalString; reversals: DecimalString; tax_rate: DecimalString | null }
export interface AssumptionValue { field: string; label: string; values: (DecimalString | null)[]; provenance: Provenance; active: boolean; financing_loans?: FinancingLoan[] | null; pregresso?: Pregresso | null; temporary_differences?: TemporaryDifference[] | null }
export interface AssumptionSection { key: AssumptionSectionKey; title: string; assumptions: AssumptionValue[] }
export interface FinancialLine { code: string; label: string; value: DecimalString }
export interface ForecastYear { year: number; income_statement: FinancialLine[]; balance_sheet: FinancialLine[]; cashflow: FinancialLine[]; calculations: FinancialLine[] }
export interface Forecast { years: ForecastYear[] }
export interface ChartMetric { key: string; label: string; values: (DecimalString | null)[] }
export interface ChartSeries { id: ChartId; title: string; unit: "eur" | "percent" | "days" | "ratio"; categories: number[]; series: ChartMetric[] }
export interface NarrativeBlock { id: NarrativeId; text: string; provenance: "ai" | "user" | "migrated"; updated_at: string; source_hash: string; freshness: "fresh" | "stale" | "missing" }
export interface FinalReportModel { schema_version: 1; generated_at: string; model_hash: string; source_hash: string; company: CompanyIdentity; practice: Practice; source_revisions: SourceRevision[]; readiness: Readiness; source_data_quality: SourceDataQuality; adjustments: Adjustments; infrannual_closing: InfrannualClosing | null; assumption_sections: AssumptionSection[]; forecast: Forecast; diagnostics: Diagnostic[]; chart_series: ChartSeries[]; narrative: NarrativeBlock[] }

const own = (value: unknown, key: string): boolean => typeof value === "object" && value !== null && key in value;
const object = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value);
const array = (value: unknown): value is unknown[] => Array.isArray(value);
const string = (value: unknown): value is string => typeof value === "string";
const number = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const decimal = (value: unknown): value is DecimalString | null => value === null || (string(value) && /^-?(?:0|[1-9]\d*)(?:\.\d+)?$/.test(value));
const isHash = (value: unknown): value is string => string(value) && /^[0-9a-f]{64}$/.test(value);
const required = (value: unknown, keys: readonly string[]): value is Record<string, unknown> => object(value) && keys.every((key) => own(value, key));

/** Runtime boundary for API/fixture JSON.  It intentionally rejects future schemas. */
export function isFinalReportModel(value: unknown): value is FinalReportModel {
  if (!required(value, ["schema_version", "generated_at", "model_hash", "source_hash", "company", "practice", "source_revisions", "readiness", "source_data_quality", "adjustments", "infrannual_closing", "assumption_sections", "forecast", "diagnostics", "chart_series", "narrative"])) return false;
  if (value.schema_version !== FINAL_REPORT_SCHEMA_VERSION || !string(value.generated_at) || !isHash(value.model_hash) || !isHash(value.source_hash)) return false;
  if (!required(value.company, ["id", "name", "tax_id"]) || !number(value.company.id) || !string(value.company.name) || !(string(value.company.tax_id) || value.company.tax_id === null)) return false;
  if (!required(value.practice, ["workflow_type", "budget_scenario", "source_scenario", "periods"]) || !["infrannuale", "bilancio", "startup"].includes(String(value.practice.workflow_type))) return false;
  if (value.practice.workflow_type === "infrannuale" ? !object(value.infrannual_closing) || !object(value.practice.source_scenario) : value.infrannual_closing !== null) return false;
  if (!array(value.assumption_sections) || value.assumption_sections.length !== 7 || value.assumption_sections.some((section, index) => !required(section, ["key", "title", "assumptions"]) || section.key !== ASSUMPTION_SECTION_CATALOG[index]?.key || !string(section.title) || !array(section.assumptions))) return false;
  if (!required(value.forecast, ["years"]) || !array(value.forecast.years) || !value.forecast.years.every((year) => required(year, ["year", "income_statement", "balance_sheet", "cashflow", "calculations"]) && number(year.year) && [year.income_statement, year.balance_sheet, year.cashflow, year.calculations].every(array))) return false;
  if (!array(value.chart_series) || value.chart_series.length !== 6 || new Set(value.chart_series.map((series) => object(series) ? series.id : "")).size !== 6) return false;
  if (!value.chart_series.every((series) => {
    if (!required(series, ["id", "title", "unit", "categories", "series"]) || !array(series.categories) || !series.categories.every(number) || !array(series.series)) return false;
    const categories = series.categories;
    return series.series.every((metric) => required(metric, ["key", "label", "values"]) && string(metric.key) && string(metric.label) && array(metric.values) && metric.values.length === categories.length && metric.values.every(decimal));
  })) return false;
  if (!array(value.narrative) || value.narrative.length !== 6 || new Set(value.narrative.map((block) => object(block) ? block.id : "")).size !== 6 || !value.narrative.every((block) => required(block, ["id", "text", "provenance", "updated_at", "source_hash", "freshness"]) && string(block.text) && isHash(block.source_hash))) return false;
  return true;
}

export function parseFinalReportModel(value: unknown): FinalReportModel {
  if (!isFinalReportModel(value)) throw new Error("Unsupported or invalid FinalReportModel v1 payload");
  return value;
}
