import { isFinalReportModel, type ChartSeries, type DecimalString, type FinalReportBase, type InfrannualClosing, type InfrannualPractice, type AnnualPractice, type StartupPractice } from "./final-report";

export const FINAL_REPORT_DOSSIER_SCHEMA_VERSION = 2 as const;
export type DossierUnit = "eur" | "percent" | "days" | "ratio" | "score";
export interface DocumentIdentity { title: string; budget_years: number[]; language: "it-IT"; presentation_unit: "eur" | "eur_thousands" }
export interface StatementPeriod { id: string; year: number; label: string; basis: "historical" | "observed" | "adjusted" | "closing" | "forecast"; period_months?: number | null; period_end?: string | null; source: string }
export interface DetailedStatementRow { id: string; code: string; label: string; parent_id?: string | null; level: number; kind: "section" | "group" | "detail" | "subtotal" | "total"; applicable: boolean; values: (DecimalString | null)[]; unavailable_reasons: (string | null)[]; source: string }
export interface DetailedStatement { id: "income_statement" | "balance_sheet" | "cashflow"; title: string; unit?: "eur"; catalog_version: string; periods: StatementPeriod[]; rows: DetailedStatementRow[] }
export interface IndicatorDefinition { id: string; label: string; family: string; unit: DossierUnit; methodology: string; convention: string; periods: StatementPeriod[]; values: (DecimalString | null)[]; unavailable_reasons: (string | null)[]; source: string; thresholds?: { label: string; value: DecimalString; source: string }[] }
export interface DossierChartSeries { id: string; title: string; unit: DossierUnit; categories: number[]; series: {key: string; label: string; values: (DecimalString | null)[]}[]; indicator_ids?: string[]; structure_refs?: string[]; period_ids?: string[]; methodology: string }
export interface EditorialTablePart { statement_id: DetailedStatement["id"]; row_ids: string[] }
export interface EditorialNoteSlot { width_pt: DecimalString; height_pt: DecimalString; font_size_pt: DecimalString; max_lines: number }
export interface EditorialPage { id: string; section_id: string; content_ids: string[]; table_parts?: EditorialTablePart[]; note_id: string; note_slot: EditorialNoteSlot }
export interface EditorialPlan { layout_version: string; font_version: string; asset_version: string; source_hash: string; plan_hash: string; pages: EditorialPage[] }
export interface EditorialNote { id: string; content_ids: string[]; text: string; provenance: "ai" | "user" | "automatic"; updated_at: string; source_hash: string; plan_hash: string; revision: number; freshness: "fresh" | "stale" | "missing" }
export interface EditorialReadiness { status: "pending" | "ready" | "blocked"; reasons: string[] }
export interface ReportSeries { id: string; label: string; unit: DossierUnit; values: (DecimalString | null)[]; unavailable_reasons: (string | null)[] }
export interface ReportSeriesGroup { id: "composition_uses" | "composition_sources" | "cost_incidence" | "break_even"; title: string; periods: StatementPeriod[]; series: ReportSeries[]; source: string; methodology: string }
export interface DossierBase extends Omit<FinalReportBase, "schema_version" | "chart_series"> { schema_version: 2; document: DocumentIdentity; detailed_statements: DetailedStatement[]; indicator_catalog: IndicatorDefinition[]; structure_series: ReportSeriesGroup[]; chart_series: (ChartSeries | DossierChartSeries)[]; editorial_plan?: EditorialPlan | null; editorial_notes?: EditorialNote[]; editorial_readiness: EditorialReadiness }
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
// Parità con STRUCTURE_GROUP_SERIES di backend/app/schemas/final_report_v2.py:
// un test di parity Python blocca la deriva fra i due elenchi.
export const STRUCTURE_GROUP_SERIES: Readonly<Record<string, readonly string[]>> = {
  composition_uses: ["fixed_assets", "fixed_assets_share", "current_other", "current_other_share", "cash", "cash_share"],
  composition_sources: ["equity", "equity_share", "financial_debt", "financial_debt_share", "other_liabilities", "other_liabilities_share"],
  cost_incidence: ["materials", "services", "personnel", "financial_charges"],
  break_even: ["fixed_costs", "variable_costs", "contribution_margin", "break_even_revenue", "safety_margin_pct"],
};
const STRUCTURE_GROUP_ORDER = ["composition_uses", "composition_sources", "cost_incidence", "break_even"];
const S = (v: string): bigint => {
  // Decimale → intero in unità da 1e-30: aritmetica esatta, niente float.
  const neg = v.startsWith("-");
  const [w, f = ""] = (neg ? v.slice(1) : v).split(".");
  const b = BigInt((w || "0") + f.padEnd(30, "0").slice(0, 30));
  return neg ? -b : b;
};
const TOLERANCE = S("0.01");
const near = (a: bigint, b: bigint): boolean => (a - b < 0n ? b - a : a - b) <= TOLERANCE;
function structureSeries(v: unknown, periodCount: number): v is ReportSeries {
  return shape(v, ["id", "label", "unit", "values", "unavailable_reasons"]) && id(v.id) && string(v.label) && unit(v.unit) && aligned(v, periodCount);
}
function structureGroup(v: unknown, expectedId: string, statements: DetailedStatement[], indicators: Map<string, IndicatorDefinition>): boolean {
  if (!shape(v, ["id", "title", "periods", "series", "source", "methodology"]) || v.id !== expectedId || !string(v.title) || !nonempty(v.source) || !nonempty(v.methodology) || !periods(v.periods)) return false;
  const canonical = statements[0].periods.map(p => p.id);
  if (v.periods.length !== canonical.length || v.periods.some((p, i) => p.id !== canonical[i])) return false;
  if (statements.some(st => st.periods.length !== canonical.length || st.periods.some((p, i) => p.id !== canonical[i]))) return false;
  const expected = STRUCTURE_GROUP_SERIES[expectedId];
  if (!Array.isArray(v.series) || v.series.length !== expected.length || !v.series.every(s => structureSeries(s, canonical.length)) || v.series.some((s, i) => (s as ReportSeries).id !== expected[i])) return false;
  const series = Object.fromEntries((v.series as ReportSeries[]).map(s => [s.id, s])) as Record<string, ReportSeries>;
  const rowsOf = (statementId: string, rowId: string): (string | null)[] | null =>
    statements.find(s => s.id === statementId)?.rows.find(r => r.id === rowId)?.values ?? null;
  for (let i = 0; i < canonical.length; i++) {
    if (expectedId === "composition_uses") {
      const fixedRow = rowsOf("balance_sheet", "balance_sheet:fixed_assets");
      const cashRow = rowsOf("balance_sheet", "balance_sheet:sp09_disponibilita_liquide");
      const totalRow = rowsOf("balance_sheet", "balance_sheet:total_assets");
      if (!fixedRow || !cashRow || !totalRow) return false;
      if (fixedRow[i] === null ? series.fixed_assets.values[i] !== null : series.fixed_assets.values[i] === null || !near(S(series.fixed_assets.values[i] as string), S(fixedRow[i] as string))) return false;
      if (cashRow[i] === null ? series.cash.values[i] !== null : series.cash.values[i] === null || !near(S(series.cash.values[i] as string), S(cashRow[i] as string))) return false;
      if (totalRow[i] === null || fixedRow[i] === null || cashRow[i] === null) {
        if (series.current_other.values[i] !== null) return false;
      } else if (series.current_other.values[i] === null || !near(S(series.current_other.values[i] as string), S(totalRow[i] as string) - S(fixedRow[i] as string) - S(cashRow[i] as string))) return false;
    } else if (expectedId === "composition_sources") {
      const equityRow = rowsOf("balance_sheet", "balance_sheet:sp11_capitale+sp12_riserve+sp13_utile_perdita");
      const passivoRow = rowsOf("balance_sheet", "balance_sheet:sp11_capitale+sp12_riserve+sp13_utile_perdita+sp16_debiti_breve+sp17_debiti_lungo+sp14_fondi_rischi+sp15_tfr+sp18_ratei_risconti_passivi");
      if (!equityRow || !passivoRow) return false;
      if (equityRow[i] === null ? series.equity.values[i] !== null : series.equity.values[i] === null || !near(S(series.equity.values[i] as string), S(equityRow[i] as string))) return false;
      if (passivoRow[i] !== null && series.equity.values[i] !== null && series.financial_debt.values[i] !== null && series.other_liabilities.values[i] !== null
        && !near(S(series.equity.values[i] as string) + S(series.financial_debt.values[i] as string) + S(series.other_liabilities.values[i] as string), S(passivoRow[i] as string))) return false;
      if (passivoRow[i] === null && series.other_liabilities.values[i] !== null) return false;
    } else if (expectedId === "break_even") {
      const ce01 = rowsOf("income_statement", "income_statement:ce01_ricavi_vendite");
      const costRows = ["ce05_materie_prime", "ce06_servizi", "ce07_godimento_beni", "ce08_costi_personale", "ce12_oneri_diversi"].map(c => rowsOf("income_statement", `income_statement:${c}`));
      if (!ce01 || costRows.some(r => !r)) return false;
      const costs = costRows.reduce<bigint | null>((acc, r) => acc === null || r === null || r[i] === null ? null : acc + S(r[i] as string), 0n);
      if (costs !== null && series.fixed_costs.values[i] !== null && series.variable_costs.values[i] !== null
        && !near(S(series.fixed_costs.values[i] as string) + S(series.variable_costs.values[i] as string), costs)) return false;
      if (series.contribution_margin.values[i] !== null && series.variable_costs.values[i] !== null && ce01[i] !== null
        && !near(S(series.contribution_margin.values[i] as string), S(ce01[i] as string) - S(series.variable_costs.values[i] as string))) return false;
    } else {
      const incidence: [string, string][] = [["materials", "practice.materials_revenue"], ["services", "practice.services_revenue"], ["personnel", "practice.personnel_revenue"], ["financial_charges", "practice.of_revenue"]];
      for (const [seriesId, indicatorId] of incidence) {
        const indicator = indicators.get(indicatorId);
        if (!indicator || indicator.periods.map(p => p.id).join("|") !== canonical.join("|")) return false;
        if (!sameValues(series[seriesId].values, indicator.values)) return false;
      }
    }
  }
  return true;
}
function additionalChart(v: unknown, years: number[], indicators: Map<string, IndicatorDefinition>, statementPeriods: StatementPeriod[], structureGroups: unknown[]): v is DossierChartSeries {
  // Parità col validatore Python (`dossier_invariants` in final_report_v2.py):
  // `period_ids` dichiara l'asse per id di periodo (chiusura + piano, M2-02G
  // fase 2); senza, l'asse resta quello v1 (solo anni di piano, base forecast).
  // `structure_refs` («gruppo:serie») aggancia alle serie di `structure_series`.
  if (!shape(v, ["id", "title", "unit", "categories", "series", "methodology"], ["indicator_ids", "structure_refs", "period_ids"]) || !id(v.id) || !string(v.title) || !unit(v.unit) || !string(v.methodology) || !Array.isArray(v.categories) || !Array.isArray(v.series) || !v.series.length) return false;
  const refs = v.indicator_ids ?? [];
  const srefs = v.structure_refs ?? [];
  const pids = v.period_ids ?? [];
  if (!strings(refs) || !strings(srefs) || !strings(pids) || !unique(pids)) return false;
  if (refs.length && srefs.length) return false;
  if (refs.length && refs.length !== v.series.length) return false;
  if (srefs.length && (srefs.length !== v.series.length || !pids.length)) return false;
  const byId = new Map(statementPeriods.map(p => [p.id, p.year] as const));
  if (pids.some(pid => !byId.has(pid))) return false;
  const axis = pids.length ? pids.map(pid => byId.get(pid)!) : years;
  if (v.categories.length !== axis.length || v.categories.some((y, i) => y !== axis[i])) return false;
  if (!v.series.every(s => shape(s, ["key", "label", "values"]) && string(s.key) && string(s.label) && Array.isArray(s.values) && s.values.length === axis.length && s.values.every(x => x === null || decimal(x))) || !unique(v.series.map(s => s.key))) return false;
  const metricValues = (i: number): (string | null)[] => (v.series as {values: (string | null)[]}[])[i].values;
  if (!refs.every((ref, i) => {
    const def = indicators.get(ref); if (!def || def.unit !== v.unit) return false;
    if (pids.length) {
      const values = new Map(def.periods.map((p, j) => [p.id, def.values[j]] as const));
      return pids.every(pid => values.has(pid)) && sameValues(metricValues(i), pids.map(pid => values.get(pid) ?? null));
    }
    const values = new Map(def.periods.flatMap((p, j) => p.basis === "forecast" ? [[p.year, def.values[j]] as const] : []));
    return sameValues(metricValues(i), years.map(y => values.get(y) ?? null));
  })) return false;
  return srefs.every((ref, i) => {
    const sep = ref.indexOf(":"); if (sep <= 0 || sep === ref.length - 1) return false;
    const group = (structureGroups as ReportSeriesGroup[]).find(g => g.id === ref.slice(0, sep));
    const series = group?.series.find(s => s.id === ref.slice(sep + 1));
    if (!group || !series || series.unit !== v.unit) return false;
    const values = new Map(group.periods.map((p, j) => [p.id, series.values[j]] as const));
    return pids.every(pid => values.has(pid)) && sameValues(metricValues(i), pids.map(pid => values.get(pid) ?? null));
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
  const {document, detailed_statements, indicator_catalog, structure_series, editorial_plan, editorial_notes, editorial_readiness, ...core} = value;
  const primary = value.chart_series.filter(c => object(c) && canonicalIds.has(String(c.id)));
  if (!isFinalReportModel({...core, schema_version: 1, chart_series: primary})) return false;
  const years = (core.practice as FinalReportBase['practice']).periods.forecast_years;
  if (!shape(document, ["title", "budget_years"], ["language", "presentation_unit"]) || !Array.isArray(document.budget_years) || document.budget_years.length !== years.length || document.budget_years.some((y, i) => y !== years[i]) || !unique(years) || years.some((y, i) => i > 0 && y < years[i - 1]) || (document.language !== undefined && document.language !== "it-IT") || (document.presentation_unit !== undefined && !["eur", "eur_thousands"].includes(String(document.presentation_unit)))) return false;
  if (document.title !== `Report Budget ${years[0]}${years.length > 1 ? ` - ${years.at(-1)}` : ""}`) return false;
  if (!Array.isArray(detailed_statements) || detailed_statements.length !== 3 || !detailed_statements.every(statement) || detailed_statements.some((s, i) => s.id !== ["income_statement", "balance_sheet", "cashflow"][i]) || !Array.isArray(indicator_catalog) || !indicator_catalog.length || !indicator_catalog.every(indicator) || !unique(indicator_catalog.map(i => i.id))) return false;
  const indicators = new Map(indicator_catalog.map(i => [i.id, i]));
  if (!Array.isArray(structure_series) || structure_series.length !== STRUCTURE_GROUP_ORDER.length
    || structure_series.some((g, i) => !structureGroup(g, STRUCTURE_GROUP_ORDER[i], detailed_statements, indicators))) return false;
  if (!unique(value.chart_series.map(c => object(c) ? c.id : null)) || !value.chart_series.every(c => primary.includes(c) || additionalChart(c, years, indicators, (detailed_statements as DetailedStatement[])[0].periods, structure_series as unknown[]))) return false;
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
