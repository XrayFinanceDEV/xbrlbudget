"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Legend,
  ReferenceLine,
} from "recharts";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import { formatNumber } from "@/lib/formatters";
import type { ScenarioAnalysis } from "@/types/api";

interface ReportRatiosProps {
  data: ScenarioAnalysis;
}

interface RatioRow {
  key: string;
  label: string;
  category: string;
  format: "ratio" | "pct" | "days" | "number";
}

const RATIO_SECTIONS: Array<{
  title: string;
  ratios: RatioRow[];
}> = [
  {
    title: "Indici di Liquidita",
    ratios: [
      { key: "liquidity.current_ratio", label: "Current Ratio (ILC)", category: "liquidity", format: "ratio" },
      { key: "liquidity.quick_ratio", label: "Quick Ratio (ISL)", category: "liquidity", format: "ratio" },
      { key: "liquidity.acid_test", label: "Acid Test", category: "liquidity", format: "ratio" },
    ],
  },
  {
    title: "Indici di Solvibilita",
    ratios: [
      { key: "solvency.autonomy_index", label: "Autonomia Finanziaria", category: "solvency", format: "pct" },
      { key: "solvency.leverage_ratio", label: "Indice di Indebitamento", category: "solvency", format: "ratio" },
      { key: "solvency.debt_to_equity", label: "Debiti/Patrimonio Netto", category: "solvency", format: "ratio" },
      { key: "solvency.debt_to_production", label: "Debiti/Valore Produzione", category: "solvency", format: "ratio" },
    ],
  },
  {
    title: "Indici di Redditivita",
    ratios: [
      { key: "profitability.roe", label: "ROE", category: "profitability", format: "pct" },
      { key: "profitability.roi", label: "ROI", category: "profitability", format: "pct" },
      { key: "profitability.ros", label: "ROS", category: "profitability", format: "pct" },
      { key: "profitability.rod", label: "ROD (Costo Denaro)", category: "profitability", format: "pct" },
      { key: "profitability.ebitda_margin", label: "EBITDA Margin", category: "profitability", format: "pct" },
    ],
  },
  {
    title: "Indici di Solidita (Copertura)",
    ratios: [
      { key: "coverage.fixed_assets_coverage_with_equity_and_ltdebt", label: "(CN+PF)/AF", category: "coverage", format: "ratio" },
      { key: "coverage.fixed_assets_coverage_with_equity", label: "CN/AF", category: "coverage", format: "ratio" },
      { key: "coverage.independence_from_third_parties", label: "CN/(PC+PF)", category: "coverage", format: "ratio" },
    ],
  },
  {
    title: "Indici di Rotazione",
    ratios: [
      { key: "activity.inventory_turnover_days", label: "Giorni Magazzino (DMAG)", category: "activity", format: "days" },
      { key: "activity.receivables_turnover_days", label: "Giorni Credito (DCRED)", category: "activity", format: "days" },
      { key: "activity.payables_turnover_days", label: "Giorni Debito (DDEB)", category: "activity", format: "days" },
      { key: "activity.cash_conversion_cycle", label: "Ciclo Conv. Denaro", category: "activity", format: "days" },
      { key: "activity.asset_turnover", label: "Rotazione Attivo", category: "activity", format: "ratio" },
    ],
  },
  {
    title: "Indici di Redditivita Estesa",
    ratios: [
      { key: "extended_profitability.spread", label: "Spread (ROI-ROD)", category: "extended_profitability", format: "pct" },
      { key: "extended_profitability.financial_leverage_effect", label: "Leva Finanziaria", category: "extended_profitability", format: "ratio" },
      { key: "extended_profitability.ebitda_on_sales", label: "MOL/Ricavi", category: "extended_profitability", format: "pct" },
      { key: "extended_profitability.financial_charges_on_revenue", label: "OF/Ricavi", category: "extended_profitability", format: "pct" },
    ],
  },
  {
    title: "Indici di Efficienza",
    ratios: [
      { key: "efficiency.revenue_per_employee_cost", label: "Ricavi/Costo Personale", category: "efficiency", format: "ratio" },
      { key: "efficiency.revenue_per_materials_cost", label: "Ricavi/Costo Materie", category: "efficiency", format: "ratio" },
    ],
  },
];

function getRatioValue(ratios: Record<string, any>, key: string): number | null {
  const parts = key.split(".");
  let val: any = ratios;
  for (const part of parts) {
    if (val == null) return null;
    val = val[part];
  }
  return typeof val === "number" ? val : null;
}

function formatRatioValue(value: number | null, format: RatioRow["format"]): string {
  if (value == null) return "N/D";
  switch (format) {
    case "pct":
      return formatNumber(value * 100, 2) + "%";
    case "ratio":
      return formatNumber(value, 2);
    case "days":
      return formatNumber(value, 0) + " gg";
    case "number":
      return formatNumber(value, 2);
  }
}

export function ReportRatios({ data }: ReportRatiosProps) {
  const allYears = [...data.historical_years, ...data.forecast_years]
    .map((y) => y.year)
    .sort((a, b) => a - b);

  return (
    <section id="ratios">
      <div className="space-y-6">
        {RATIO_SECTIONS.map((section) => (
          <Card key={section.title}>
            <CardHeader>
              <CardTitle className="text-lg">{section.title}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              {/* Chart for this section */}
              <RatioChart data={data} years={allYears} ratios={section.ratios} />

              {/* Table */}
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="min-w-[200px]">Indice</TableHead>
                      {allYears.map((year) => (
                        <TableHead key={year} className="text-right min-w-[100px]">
                          {year}
                        </TableHead>
                      ))}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {section.ratios.map((ratio) => (
                      <TableRow key={ratio.key}>
                        <TableCell className="font-medium">{ratio.label}</TableCell>
                        {allYears.map((year) => {
                          const calc = data.calculations.by_year[String(year)];
                          const value = calc ? getRatioValue(calc.ratios, ratio.key) : null;
                          return (
                            <TableCell key={year} className="text-right">
                              {formatRatioValue(value, ratio.format)}
                            </TableCell>
                          );
                        })}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </section>
  );
}

function RatioChart({
  data,
  years,
  ratios,
}: {
  data: ScenarioAnalysis;
  years: number[];
  ratios: RatioRow[];
}) {
  const chartData = years.map((year) => {
    const calc = data.calculations.by_year[String(year)];
    const row: Record<string, any> = { year };
    for (const ratio of ratios) {
      const val = calc ? getRatioValue(calc.ratios, ratio.key) : null;
      // For chart display, convert pct to percentage
      row[ratio.key] = val != null
        ? ratio.format === "pct" ? +(val * 100).toFixed(2) : +val.toFixed(2)
        : null;
    }
    return row;
  });

  const config: ChartConfig = {};
  const colors = ["var(--chart-1)", "var(--chart-2)", "var(--chart-3)", "var(--chart-4)", "var(--chart-5)"];
  ratios.forEach((r, i) => {
    config[r.key] = { label: r.label, color: colors[i % colors.length] };
  });

  const isPct = ratios[0]?.format === "pct";
  const isDays = ratios[0]?.format === "days";

  return (
    <ChartContainer config={config} className="h-[250px] w-full">
      <LineChart data={chartData}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="year" />
        <YAxis tickFormatter={(v) => isPct ? `${v}%` : isDays ? `${v}gg` : `${v}`} />
        {isPct && <ReferenceLine y={0} stroke="hsl(var(--muted-foreground))" strokeDasharray="3 3" />}
        <ChartTooltip
          content={<ChartTooltipContent />}
          formatter={(value: number) =>
            isPct ? `${value.toFixed(2)}%` : isDays ? `${value.toFixed(0)} gg` : value.toFixed(2)
          }
        />
        <Legend />
        {ratios.map((r, i) => (
          <Line
            key={r.key}
            type="monotone"
            dataKey={r.key}
            stroke={colors[i % colors.length]}
            strokeWidth={2}
            dot={{ r: 3 }}
            connectNulls
          />
        ))}
      </LineChart>
    </ChartContainer>
  );
}
