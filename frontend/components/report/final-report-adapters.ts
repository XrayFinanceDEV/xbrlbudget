/**
 * Pure projections of the final-report contract for the web renderer.
 *
 * The final-report endpoint already owns all domain loading and financial
 * calculations.  These helpers only preserve its order and make table-shaped
 * data; they must never fetch, use hooks, or derive a financial result.
 */
import type {
  ChartSeries,
  FinalReportModel,
  FinancialLine,
  NarrativeBlock,
} from "@/types/final-report";

export type ForecastStatement = "income_statement" | "balance_sheet" | "cashflow" | "calculations";

export interface StatementRow {
  code: string;
  label: string;
  values: Array<string | null>;
}

/** Keep the server's first-seen line order and expose absence as null, never zero. */
export function statementRows(report: FinalReportModel, statement: ForecastStatement): StatementRow[] {
  const lines = new Map<string, { label: string; values: Array<string | null> }>();
  report.forecast.years.forEach((year, yearIndex) => {
    (year[statement] as FinancialLine[]).forEach((line) => {
      const existing = lines.get(line.code) ?? {
        label: line.label,
        values: Array(report.forecast.years.length).fill(null),
      };
      existing.values[yearIndex] = line.value;
      lines.set(line.code, existing);
    });
  });
  return [...lines.entries()].map(([code, row]) => ({ code, ...row }));
}

export interface ChartRow {
  key: string;
  label: string;
  values: Array<string | null>;
}

/** Chart values stay strings from the contract; formatting is a view concern. */
export function chartRows(series: ChartSeries): ChartRow[] {
  return series.series.map((item) => ({ key: item.key, label: item.label, values: [...item.values] }));
}

export function narrativeFor(
  report: FinalReportModel,
  id: NarrativeBlock["id"],
): NarrativeBlock {
  const block = report.narrative.find((item) => item.id === id);
  if (!block) throw new Error(`Final report is missing narrative block ${id}`);
  return block;
}

export function hasStaleForecast(report: FinalReportModel): boolean {
  return report.readiness.reasons?.some((reason) => reason.code === "forecast_stale") ?? false;
}
