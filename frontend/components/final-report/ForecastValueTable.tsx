import { statementRows, type ForecastStatement } from "@/components/report/final-report-adapters";
import { formatEuro, formatNumber } from "./final-report-format";
import type { FinalReportModel } from "@/types/final-report";

const STATEMENT_TITLES: Record<ForecastStatement, string> = {
  income_statement: "Conto economico previsionale",
  balance_sheet: "Stato patrimoniale previsionale",
  cashflow: "Flussi di cassa",
  calculations: "Calcoli e indicatori disponibili",
};

/** Statements are monetary; persisted calculation lines have no unit metadata. */
export function formatStatementValue(value: string | null, statement: ForecastStatement): string {
  return statement === "calculations" ? formatNumber(value) : formatEuro(value);
}

export function ForecastValueTable({ report, statement }: { report: FinalReportModel; statement: ForecastStatement }) {
  const rows = statementRows(report, statement);
  return <div className="overflow-x-auto"><table className="w-full text-sm print:text-xs">
    <caption className="sr-only">{STATEMENT_TITLES[statement]} per anno di previsione</caption>
    <thead><tr><th scope="col" className="border-b px-3 py-1.5 text-left font-medium print:px-1">Voce</th>{report.forecast.years.map((year) => <th key={year.year} scope="col" className="border-b px-3 py-1.5 text-right font-medium print:px-1">{year.year}</th>)}</tr></thead>
    <tbody>{rows.map((row) => <tr key={row.code}><th scope="row" className="border-b px-3 py-1.5 text-left font-medium print:px-1">{row.label}<span className="ml-1 text-xs font-normal text-muted-foreground">{row.code}</span></th>{row.values.map((value, index) => <td key={index} className="border-b px-3 py-1.5 text-right tabular-nums print:px-1">{formatStatementValue(value, statement)}</td>)}</tr>)}</tbody>
  </table></div>;
}
