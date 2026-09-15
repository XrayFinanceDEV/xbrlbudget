import { isFinalReportModel, type ChartSeries, type DecimalString, type FinalReportBase, type InfrannualClosing, type InfrannualPractice, type AnnualPractice, type StartupPractice } from "./final-report";

export const FINAL_REPORT_DOSSIER_SCHEMA_VERSION = 2 as const;
export type DossierUnit = "eur" | "percent" | "days" | "ratio" | "score";
export interface DocumentIdentity { title: string; budget_years: number[]; language: "it-IT"; presentation_unit: "eur" | "eur_thousands" }
export interface StatementPeriod { id: string; year: number; label: string; basis: "historical" | "observed" | "adjusted" | "closing" | "forecast"; period_months?: number | null; period_end?: string | null; source: string }
export interface DetailedStatementRow { id: string; code: string; label: string; parent_id?: string | null; level: number; kind: "section" | "group" | "detail" | "subtotal" | "total"; applicable: boolean; values: (DecimalString | null)[]; unavailable_reasons: (string | null)[]; source: string }
export interface DetailedStatement { id: "income_statement" | "balance_sheet" | "cashflow"; title: string; unit?: "eur"; catalog_version: string; periods: StatementPeriod[]; rows: DetailedStatementRow[] }
export interface IndicatorDefinition { id: string; label: string; family: string; unit: DossierUnit; methodology: string; convention: string; periods: StatementPeriod[]; values: (DecimalString | null)[]; unavailable_reasons: (string | null)[]; source: string; thresholds?: { label: string; value: DecimalString; source: string }[] }
export interface DossierChartSeries { id: string; title: string; unit: DossierUnit; categories: number[]; series: {key: string; label: string; values: (DecimalString | null)[]}[]; indicator_ids?: string[]; methodology: string }
export interface EditorialTablePart { statement_id: DetailedStatement["id"]; row_ids: string[] }
export interface EditorialNoteSlot { width_pt: DecimalString; height_pt: DecimalString; font_size_pt: DecimalString; max_lines: number }
export interface EditorialPage { id: string; section_id: string; content_ids: string[]; table_parts?: EditorialTablePart[]; note_id: string; note_slot: EditorialNoteSlot }
export interface EditorialPlan { layout_version: string; font_version: string; asset_version: string; source_hash: string; plan_hash: string; pages: EditorialPage[] }
export interface EditorialNote { id: string; content_ids: string[]; text: string; provenance: "ai" | "user" | "automatic"; updated_at: string; source_hash: string; plan_hash: string; revision: number; freshness: "fresh" | "stale" | "missing" }
export interface EditorialReadiness { status: "pending" | "ready" | "blocked"; reasons: string[] }
export interface DossierBase extends Omit<FinalReportBase, "schema_version" | "chart_series"> { schema_version: 2; document: DocumentIdentity; detailed_statements: DetailedStatement[]; indicator_catalog: IndicatorDefinition[]; chart_series: (ChartSeries | DossierChartSeries)[]; editorial_plan?: EditorialPlan | null; editorial_notes?: EditorialNote[]; editorial_readiness: EditorialReadiness }
export type FinalReportModelV2 = (DossierBase & {practice: InfrannualPractice; infrannual_closing: InfrannualClosing}) | (DossierBase & {practice: AnnualPractice | StartupPractice; infrannual_closing?: never});

type Obj = Record<string, unknown>;
const object = (v: unknown): v is Obj => v !== null && typeof v === "object" && !Array.isArray(v);
const string = (v: unknown): v is string => typeof v === "string";
const nonempty = (v: unknown): v is string => string(v) && v.length > 0;
const integer = (v: unknown): v is number => typeof v === "number" && Number.isInteger(v);
const decimal = (v: unknown): v is string => string(v) && /^-?(?:0|[1-9]\d*)(?:\.\d+)?$/.test(v);
const id = (v: unknown): v is string => string(v) && /^[a-z][a-z0-9_.:+-]*$/.test(v);
const hash = (v: unknown): v is string => string(v) && /^[0-9a-f]{64}$/.test(v);
const strings = (v: unknown): v is string[] => Array.isArray(v) && v.every(string);
const unique = (v: unknown[]): boolean => new Set(v).size === v.length;
const shape = (v: unknown, required: string[], optional: string[] = []): v is Obj => object(v) && required.every(k => Object.hasOwn(v, k)) && Object.keys(v).every(k => required.includes(k) || optional.includes(k));
const unit = (v: unknown): boolean => ["eur", "percent", "days", "ratio", "score"].includes(String(v));
const date = (v: unknown): boolean => string(v) && /^\d{4}-\d{2}-\d{2}$/.test(v) && !Number.isNaN(Date.parse(v)) && new Date(v).toISOString().slice(0, 10) === v;
const datetime = (v: unknown): boolean => string(v) && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})?$/.test(v) && date(v.slice(0, 10)) && Number(v.slice(11, 13)) < 24 && Number(v.slice(14, 16)) < 60 && Number(v.slice(17, 19)) < 60 && !Number.isNaN(Date.parse(v));
const decimalKey = (v: string | null): string | null => v === null ? null : v.replace(/(\.\d*?)0+$/, "$1").replace(/\.$/, "").replace(/^-0$/, "0");
const sameValues = (a: (string | null)[], b: (string | null)[]): boolean => a.length === b.length && a.every((v, i) => decimalKey(v) === decimalKey(b[i]));
const aligned = (v: Obj, n: number): boolean => Array.isArray(v.values) && Array.isArray(v.unavailable_reasons) && v.values.length === n && v.unavailable_reasons.length === n && v.values.every((x, i) => (x === null || decimal(x)) && (x === null ? string((v.unavailable_reasons as unknown[])[i]) : (v.unavailable_reasons as unknown[])[i] === null));
function period(v: unknown): v is StatementPeriod {
  return shape(v, ["id", "year", "label", "basis", "source"], ["period_months", "period_end"]) && id(v.id) && integer(v.year) && v.year >= 2000 && v.year <= 2100 && string(v.label) && ["historical", "observed", "adjusted", "closing", "forecast"].includes(String(v.basis)) && nonempty(v.source) && (v.period_months == null || (integer(v.period_months) && v.period_months >= 1 && v.period_months <= 12)) && (v.period_end == null || date(v.period_end));
}
function periods(v: unknown): v is StatementPeriod[] { return Array.isArray(v) && v.length > 0 && v.every(period) && unique(v.map(p => p.id)); }
function statement(v: unknown): v is DetailedStatement {
  if (!shape(v, ["id", "title", "catalog_version", "periods", "rows"], ["unit"]) || !["income_statement", "balance_sheet", "cashflow"].includes(String(v.id)) || !string(v.title) || !string(v.catalog_version) || (v.unit !== undefined && v.unit !== "eur") || !periods(v.periods) || !Array.isArray(v.rows) || !v.rows.length) return false;
  const seen = new Map<string, number>();
  for (const row of v.rows) {
    if (!shape(row, ["id", "code", "label", "level", "kind", "applicable", "values", "unavailable_reasons", "source"], ["parent_id"]) || !id(row.id) || seen.has(row.id) || !string(row.code) || !string(row.label) || !integer(row.level) || row.level < 0 || typeof row.applicable !== "boolean" || !string(row.source) || !["section", "group", "detail", "subtotal", "total"].includes(String(row.kind)) || !aligned(row, v.periods.length)) return false;
    if (row.parent_id != null ? !string(row.parent_id) || !seen.has(row.parent_id) || row.level !== seen.get(row.parent_id)! + 1 : row.level !== 0) return false;
    if (["section", "group"].includes(String(row.kind)) && (row.values as unknown[]).some(x => x !== null)) return false;
    seen.set(row.id, row.level);
  }
  return true;
}
function indicator(v: unknown): v is IndicatorDefinition {
  return shape(v, ["id", "label", "family", "unit", "methodology", "convention", "periods", "values", "unavailable_reasons", "source"], ["thresholds"]) && id(v.id) && string(v.label) && string(v.family) && unit(v.unit) && nonempty(v.methodology) && nonempty(v.convention) && string(v.source) && periods(v.periods) && aligned(v, v.periods.length) && (v.thresholds === undefined || (Array.isArray(v.thresholds) && v.thresholds.every(t => shape(t, ["label", "value", "source"]) && string(t.label) && decimal(t.value) && nonempty(t.source))));
}
const canonicalIds = new Set(["income_results", "margins", "cashflows", "liquidity_debt", "working_capital_days", "coverage"]);
function additionalChart(v: unknown, years: number[], indicators: Map<string, IndicatorDefinition>): v is DossierChartSeries {
  if (!shape(v, ["id", "title", "unit", "categories", "series", "methodology"], ["indicator_ids"]) || !id(v.id) || !string(v.title) || !unit(v.unit) || !string(v.methodology) || !Array.isArray(v.categories) || v.categories.length !== years.length || v.categories.some((y, i) => y !== years[i]) || !Array.isArray(v.series) || !v.series.length) return false;
  if (!v.series.every(s => shape(s, ["key", "label", "values"]) && string(s.key) && string(s.label) && Array.isArray(s.values) && s.values.length === years.length && s.values.every(x => x === null || decimal(x))) || !unique(v.series.map(s => s.key))) return false;
  const refs = v.indicator_ids ?? [];
  if (!strings(refs) || (refs.length > 0 && refs.length !== v.series.length)) return false;
  return refs.every((ref, i) => {
    const def = indicators.get(ref); if (!def || def.unit !== v.unit) return false;
    const values = new Map(def.periods.flatMap((p, j) => p.basis === "forecast" ? [[p.year, def.values[j]] as const] : []));
    return sameValues((v.series as {values: (string | null)[]}[])[i].values, years.map(y => values.get(y) ?? null));
  });
}
function page(v: unknown): v is EditorialPage {
  if (!shape(v, ["id", "section_id", "content_ids", "note_id", "note_slot"], ["table_parts"]) || !id(v.id) || !string(v.section_id) || !strings(v.content_ids) || !v.content_ids.length || !string(v.note_id) || !shape(v.note_slot, ["width_pt", "height_pt", "font_size_pt", "max_lines"])) return false;
  const slot = v.note_slot;
  if (![slot.width_pt, slot.height_pt, slot.font_size_pt].every(x => decimal(x) && !x.startsWith('-') && decimalKey(x) !== '0') || !integer(slot.max_lines) || slot.max_lines <= 0) return false;
  return v.table_parts === undefined || (Array.isArray(v.table_parts) && v.table_parts.every(p => shape(p, ["statement_id", "row_ids"]) && ["income_statement", "balance_sheet", "cashflow"].includes(String(p.statement_id)) && strings(p.row_ids) && p.row_ids.length > 0));
}
function note(v: unknown): v is EditorialNote {
  return shape(v, ["id", "content_ids", "text", "provenance", "updated_at", "source_hash", "plan_hash", "revision", "freshness"]) && string(v.id) && strings(v.content_ids) && v.content_ids.length > 0 && nonempty(v.text) && ["ai", "user", "automatic"].includes(String(v.provenance)) && datetime(v.updated_at) && hash(v.source_hash) && hash(v.plan_hash) && integer(v.revision) && v.revision >= 0 && ["fresh", "stale", "missing"].includes(String(v.freshness));
}

/** Dedicated v2 boundary: existing v1 consumers continue to reject v2. */
export function isFinalReportModelV2(value: unknown): value is FinalReportModelV2 {
  if (!object(value) || value.schema_version !== 2 || !Array.isArray(value.chart_series)) return false;
  const {document, detailed_statements, indicator_catalog, editorial_plan, editorial_notes, editorial_readiness, ...core} = value;
  const primary = value.chart_series.filter(c => object(c) && canonicalIds.has(String(c.id)));
  if (!isFinalReportModel({...core, schema_version: 1, chart_series: primary})) return false;
  const years = (core.practice as FinalReportBase['practice']).periods.forecast_years;
  if (!shape(document, ["title", "budget_years"], ["language", "presentation_unit"]) || !Array.isArray(document.budget_years) || document.budget_years.length !== years.length || document.budget_years.some((y, i) => y !== years[i]) || !unique(years) || years.some((y, i) => i > 0 && y < years[i - 1]) || (document.language !== undefined && document.language !== "it-IT") || (document.presentation_unit !== undefined && !["eur", "eur_thousands"].includes(String(document.presentation_unit)))) return false;
  if (document.title !== `Report Budget ${years[0]}${years.length > 1 ? ` - ${years.at(-1)}` : ""}`) return false;
  if (!Array.isArray(detailed_statements) || detailed_statements.length !== 3 || !detailed_statements.every(statement) || detailed_statements.some((s, i) => s.id !== ["income_statement", "balance_sheet", "cashflow"][i]) || !Array.isArray(indicator_catalog) || !indicator_catalog.length || !indicator_catalog.every(indicator) || !unique(indicator_catalog.map(i => i.id))) return false;
  const indicators = new Map(indicator_catalog.map(i => [i.id, i]));
  if (!unique(value.chart_series.map(c => object(c) ? c.id : null)) || !value.chart_series.every(c => primary.includes(c) || additionalChart(c, years, indicators))) return false;
  if (!shape(editorial_readiness, ["status", "reasons"]) || !["pending", "ready", "blocked"].includes(String(editorial_readiness.status)) || !strings(editorial_readiness.reasons)) return false;
  const notes = editorial_notes === undefined ? [] : editorial_notes;
  if (!Array.isArray(notes) || !notes.every(note) || !unique(notes.map(n => n.id))) return false;
  if (editorial_plan == null) return notes.length === 0 && editorial_readiness.status === "pending";
  if (!shape(editorial_plan, ["layout_version", "font_version", "asset_version", "source_hash", "plan_hash", "pages"]) || ![editorial_plan.layout_version, editorial_plan.font_version, editorial_plan.asset_version].every(string) || !hash(editorial_plan.source_hash) || !hash(editorial_plan.plan_hash) || editorial_plan.source_hash !== core.source_hash || !Array.isArray(editorial_plan.pages) || !editorial_plan.pages.length || !editorial_plan.pages.every(page) || !unique(editorial_plan.pages.map(p => p.id)) || !unique(editorial_plan.pages.map(p => p.note_id))) return false;
  const pages = new Map(editorial_plan.pages.map(p => [p.note_id, p]));
  const rows = new Map(detailed_statements.map(s => [s.id, new Set(s.rows.map(r => r.id))]));
  if (editorial_plan.pages.some(p => p.table_parts?.some(part => !unique(part.row_ids) || part.row_ids.some(r => !rows.get(part.statement_id)?.has(r)))) || notes.some(n => {const p = pages.get(n.id); return !p || n.content_ids.length !== p.content_ids.length || n.content_ids.some((id, i) => id !== p.content_ids[i]);})) return false;
  return editorial_readiness.status !== "ready" || (notes.length === pages.size && notes.every(n => n.freshness === "fresh" && n.source_hash === core.source_hash && n.plan_hash === editorial_plan.plan_hash));
}
export function parseFinalReportModelV2(value: unknown): FinalReportModelV2 {
  if (!isFinalReportModelV2(value)) throw new Error("Unsupported or invalid FinalReportModel v2 payload");
  return value;
}
