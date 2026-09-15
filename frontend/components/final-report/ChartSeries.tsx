/**
 * Presentazione delle serie canoniche del report finale.
 *
 * I dati visuali derivano esclusivamente da `chart_series`. I numeri JavaScript
 * sono creati soltanto nella proiezione interna usata da Recharts; testo,
 * tooltip e tabella mantengono sempre il DecimalString ricevuto dal server.
 */
import { Bar, BarChart, CartesianGrid, Line, LineChart, Tooltip, XAxis, YAxis } from "recharts";

import { ChartContainer, type ChartConfig } from "@/components/ui/chart";
import { chartRows } from "@/components/report/final-report-adapters";
import { formatEuro, formatNumber } from "./final-report-format";
import type { ChartSeries, DecimalString } from "@/types/final-report";

const SERIES_COLORS = ["#2563eb", "#d97706", "#059669", "#7c3aed"];

type ChartKind = "line" | "bar";

// The six IDs are a closed, server-validated canonical vocabulary. This maps
// their documented visual treatment only; it does not classify or calculate a
// financial value in the browser.
const CHART_KINDS: Record<ChartSeries["id"], ChartKind> = {
  income_results: "bar",
  margins: "line",
  cashflows: "bar",
  liquidity_debt: "line",
  working_capital_days: "line",
  coverage: "line",
};

const UNIT_LABELS: Record<ChartSeries["unit"], string> = {
  eur: "Euro",
  percent: "Percentuale",
  days: "Giorni",
  ratio: "Indice",
};

export function formatChartValue(value: DecimalString | null, unit: ChartSeries["unit"]): string {
  if (value === null) return formatNumber(value);
  if (unit === "eur") return formatEuro(value);
  if (unit === "percent") return `${formatNumber(value)}%`;
  if (unit === "days") return `${formatNumber(value)} giorni`;
  return formatNumber(value);
}

type GeometryRow = { category: number; raw: Record<string, DecimalString | null> } & Record<string, number | null | Record<string, DecimalString | null>>;

/** Number conversion is intentionally limited to Recharts geometry. */
function chartGeometry(series: ChartSeries): GeometryRow[] {
  return series.categories.map((category, index) => {
    const raw = Object.fromEntries(series.series.map((metric) => [metric.key, metric.values[index] ?? null]));
    const geometry: GeometryRow = { category, raw };
    for (const metric of series.series) {
      const value = raw[metric.key];
      const numeric = value === null ? null : Number(value);
      geometry[metric.key] = numeric !== null && Number.isFinite(numeric) ? numeric : null;
    }
    return geometry;
  });
}

export function ChartValueTooltip({ active, payload, unit }: { active?: boolean; payload?: Array<{ dataKey?: string | number; name?: string; payload?: GeometryRow }>; unit: ChartSeries["unit"] }) {
  if (!active || !payload?.length) return null;
  const year = payload[0]?.payload?.category;
  return <div className="rounded-md border bg-background px-3 py-2 text-xs shadow-md">
    <p className="font-medium">Anno {year}</p>
    {payload.map((item) => {
      const key = String(item.dataKey);
      return <p key={key}>{item.name}: {formatChartValue(item.payload?.raw[key] ?? null, unit)}</p>;
    })}
  </div>;
}

function TextLegend({ series }: { series: ChartSeries }) {
  return <ul aria-label={`Legenda ${series.title}`} className="mb-2 flex flex-wrap gap-x-4 gap-y-1 text-xs">
    {series.series.map((metric, index) => <li key={metric.key} className="flex items-center gap-1.5">
      <span aria-hidden="true" className="inline-block h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: SERIES_COLORS[index % SERIES_COLORS.length] }} />
      <span>{metric.label}</span>
    </li>)}
  </ul>;
}

function ChartDataTable({ series }: { series: ChartSeries }) {
  return <div className="overflow-x-auto">
    <table className="w-full text-sm print:text-xs">
      <caption className="sr-only">Dati accessibili del grafico {series.title}, unità {UNIT_LABELS[series.unit]}</caption>
      <thead><tr><th scope="col" className="border-b px-3 py-1.5 text-left font-medium print:px-1">Serie</th>{series.categories.map((year) => <th key={year} scope="col" className="border-b px-3 py-1.5 text-right font-medium print:px-1">{year}</th>)}</tr></thead>
      <tbody>{chartRows(series).map((row) => <tr key={row.key}><th scope="row" className="border-b px-3 py-1.5 text-left font-medium print:px-1">{row.label}</th>{row.values.map((value, index) => <td key={index} className="border-b px-3 py-1.5 text-right tabular-nums print:px-1">{formatChartValue(value, series.unit)}</td>)}</tr>)}</tbody>
    </table>
  </div>;
}

/** A complete chart: visual geometry, text legend, and its adjacent data table. */
export function FinalReportChart({ series }: { series: ChartSeries }) {
  const config = Object.fromEntries(series.series.map((metric, index) => [metric.key, { label: metric.label, color: SERIES_COLORS[index % SERIES_COLORS.length] }])) as ChartConfig;
  const kind = CHART_KINDS[series.id];
  const data = chartGeometry(series);
  const chartElements = series.series.map((metric, index) => kind === "bar"
    ? <Bar key={metric.key} dataKey={metric.key} name={metric.label} fill={`var(--color-${metric.key})`} radius={[3, 3, 0, 0]} />
    : <Line key={metric.key} type="monotone" dataKey={metric.key} name={metric.label} stroke={`var(--color-${metric.key})`} strokeWidth={2} dot />,
  );

  return <section aria-labelledby={`chart-${series.id}-title`} className="space-y-2 overflow-x-auto print:break-inside-avoid" data-testid={`final-report-chart-${series.id}`}>
    <h3 id={`chart-${series.id}-title`} className="text-base font-semibold">{series.title}</h3>
    <p className="text-xs text-muted-foreground">Unità: {UNIT_LABELS[series.unit]} · Periodo: {series.categories.join(", ")}</p>
    <TextLegend series={series} />
    <ChartContainer config={config} className="h-[280px] w-full print:h-[180px]" aria-label={`Grafico ${series.title}`}>
      {kind === "bar"
        ? <BarChart data={data}><CartesianGrid vertical={false} /><XAxis dataKey="category" /><YAxis tick={false} axisLine={false} width={8} /><Tooltip content={<ChartValueTooltip unit={series.unit} />} />{chartElements}</BarChart>
        : <LineChart data={data}><CartesianGrid vertical={false} /><XAxis dataKey="category" /><YAxis tick={false} axisLine={false} width={8} /><Tooltip content={<ChartValueTooltip unit={series.unit} />} />{chartElements}</LineChart>}
    </ChartContainer>
    <ChartDataTable series={series} />
  </section>;
}
