import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatEuro, formatNumber } from "./final-report-format";
import { FinalReportChart } from "./ChartSeries";
import type { DetailedStatement, IndicatorDefinition, FinalReportModelV2 } from "@/types/final-report-v2";

const UNIT: Record<IndicatorDefinition["unit"], string> = { eur: "Euro", percent: "%", days: "giorni", ratio: "indice", score: "punteggio" };
function value(value: string | null, unit: IndicatorDefinition["unit"]): string {
  if (value === null) return "Non disponibile";
  if (unit === "eur") return formatEuro(value);
  return `${formatNumber(value)}${unit === "percent" ? "%" : unit === "days" ? " giorni" : ""}`;
}

export function DossierStatement({ statement }: { statement: DetailedStatement }) {
  return <section aria-labelledby={`statement-${statement.id}`} className="space-y-2">
    <h3 id={`statement-${statement.id}`} className="text-base font-semibold">{statement.title}</h3>
    <div className="overflow-x-auto"><table className="w-full text-sm print:text-[10px]">
      <caption className="sr-only">{statement.title}, dettaglio completo</caption>
      <thead><tr><th scope="col" className="border-b px-2 py-1 text-left">Voce</th>{statement.periods.map((period) => <th key={period.id} scope="col" className="border-b px-2 py-1 text-right">{period.label}</th>)}</tr></thead>
      <tbody>{statement.rows.map((row) => <tr key={row.id} className={row.kind === "total" || row.kind === "subtotal" ? "font-semibold" : ""}>
        <th scope="row" className="border-b px-2 py-1 text-left" style={{ paddingLeft: `${8 + row.level * 16}px` }}>{row.label}<span className="ml-1 text-xs font-normal text-muted-foreground">{row.code}</span></th>
        {row.values.map((amount, index) => <td key={`${row.id}-${index}`} className="border-b px-2 py-1 text-right tabular-nums">{amount === null ? (row.kind === "section" || row.kind === "group" ? "" : <span>— <span className="text-xs text-muted-foreground">{row.unavailable_reasons[index] ?? "Valore non disponibile"}</span></span>) : formatEuro(amount)}</td>)}
      </tr>)}</tbody>
    </table></div>
  </section>;
}

export function DossierIndicators({ indicators }: { indicators: IndicatorDefinition[] }) {
  return <Card><CardHeader><CardTitle>Indicatori e metodologia</CardTitle></CardHeader><CardContent className="space-y-5">
    {indicators.map((indicator) => <section key={indicator.id} className="break-inside-avoid"><h3 className="font-medium">{indicator.label}</h3><p className="text-xs text-muted-foreground">{indicator.family} · Unità: {UNIT[indicator.unit]} · {indicator.methodology}</p>
      <div className="overflow-x-auto"><table className="mt-1 w-full text-sm"><caption className="sr-only">{indicator.label}: valori e convenzione</caption><thead><tr>{indicator.periods.map((period) => <th key={period.id} scope="col" className="border-b px-2 py-1 text-right">{period.label}</th>)}</tr></thead><tbody><tr>{indicator.values.map((amount, index) => <td key={indicator.periods[index]?.id} className="border-b px-2 py-1 text-right tabular-nums">{amount === null ? <span title={indicator.unavailable_reasons[index] ?? undefined}>— {indicator.unavailable_reasons[index]}</span> : value(amount, indicator.unit)}</td>)}</tr></tbody></table></div>
      <p className="mt-1 text-xs text-muted-foreground">Convenzione: {indicator.convention}</p>
      {indicator.thresholds?.length ? <p className="mt-1 text-xs text-muted-foreground">Soglie: {indicator.thresholds.map((threshold) => `${threshold.label} ${value(threshold.value, indicator.unit)} (${threshold.source})`).join(" · ")}</p> : null}
      <p className="mt-1 text-xs text-muted-foreground">Fonte: {indicator.source}</p></section>)}
  </CardContent></Card>;
}

export function DossierContent({ report, includeCanonicalCharts = true }: { report: FinalReportModelV2; includeCanonicalCharts?: boolean }) {
  const charts = includeCanonicalCharts ? report.chart_series : report.chart_series.filter((series) => !["income_results", "margins", "cashflows", "liquidity_debt", "working_capital_days", "coverage"].includes(series.id));
  return <>
    {charts.length ? <section id="dossier-charts"><Card><CardHeader><CardTitle>Grafici</CardTitle></CardHeader><CardContent className="space-y-7">{charts.map((series) => <FinalReportChart key={series.id} series={series} />)}</CardContent></Card></section> : null}
    <section id="indicators"><DossierIndicators indicators={report.indicator_catalog} /></section>
    <section id="appendices"><Card><CardHeader><CardTitle>Allegati</CardTitle></CardHeader><CardContent className="space-y-8">{report.detailed_statements.map((statement) => <DossierStatement key={statement.id} statement={statement} />)}</CardContent></Card></section>
  </>;
}
