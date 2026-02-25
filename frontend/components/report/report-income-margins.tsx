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
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Legend,
  Cell,
  ReferenceLine,
} from "recharts";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import { formatCurrency, formatNumber } from "@/lib/formatters";
import type { ScenarioAnalysis, ScenarioAnalysisYearData } from "@/types/api";

interface ReportIncomeMarginsProps {
  data: ScenarioAnalysis;
}

const incomeLineConfig: ChartConfig = {
  revenue: { label: "Fatturato", color: "hsl(var(--chart-1))" },
  ebitda: { label: "EBITDA", color: "hsl(var(--chart-2))" },
  ebit: { label: "EBIT", color: "hsl(var(--chart-3))" },
  net_profit: { label: "Utile Netto", color: "hsl(var(--chart-4))" },
};

const marginConfig: ChartConfig = {
  ebitda_margin: { label: "EBITDA %", color: "hsl(var(--chart-2))" },
  ebit_margin: { label: "EBIT %", color: "hsl(var(--chart-3))" },
  net_margin: { label: "Utile Netto %", color: "hsl(var(--chart-4))" },
};

export function ReportIncomeMargins({ data }: ReportIncomeMarginsProps) {
  const allYears = [...data.historical_years, ...data.forecast_years].sort(
    (a, b) => a.year - b.year
  );

  const lineData = allYears.map((y) => ({
    year: y.year,
    revenue: y.income_statement.revenue || y.income_statement.ce01_ricavi_vendite || 0,
    ebitda: y.income_statement.ebitda || 0,
    ebit: y.income_statement.ebit || 0,
    net_profit: y.income_statement.net_profit || 0,
  }));

  // Margin % data (from ratios)
  const marginData = allYears.map((y) => {
    const calc = data.calculations.by_year[String(y.year)];
    return {
      year: y.year,
      ebitda_margin: calc ? +(calc.ratios.profitability.ebitda_margin * 100).toFixed(2) : 0,
      ebit_margin: calc ? +(calc.ratios.profitability.ebit_margin * 100).toFixed(2) : 0,
      net_margin: calc ? +(calc.ratios.profitability.net_margin * 100).toFixed(2) : 0,
    };
  });

  // Waterfall: from revenue to net profit for latest year
  const latestYear = allYears[allYears.length - 1];
  const inc = latestYear.income_statement;
  const revenue = inc.revenue || inc.ce01_ricavi_vendite || 0;
  const prodCost = inc.production_cost || 0;
  const ebitda = inc.ebitda || 0;
  const depreciation = inc.ce09_ammortamenti || 0;
  const ebit = inc.ebit || 0;
  const financialResult = inc.financial_result || 0;
  const taxes = inc.ce20_imposte || 0;
  const netProfit = inc.net_profit || 0;

  const waterfallData = [
    { name: "Fatturato", value: revenue, base: 0, delta: revenue, fill: "hsl(var(--chart-1))" },
    { name: "Costi Prod.", value: -Math.abs(prodCost), base: revenue - Math.abs(prodCost), delta: -Math.abs(prodCost), fill: "hsl(var(--chart-4))" },
    { name: "EBITDA", value: ebitda, base: 0, delta: ebitda, fill: "hsl(var(--chart-2))" },
    { name: "Ammort.", value: -Math.abs(depreciation), base: ebitda - Math.abs(depreciation), delta: -Math.abs(depreciation), fill: "hsl(var(--chart-4))" },
    { name: "EBIT", value: ebit, base: 0, delta: ebit, fill: "hsl(var(--chart-3))" },
    { name: "Gest. Fin.", value: financialResult, base: ebit + Math.min(0, financialResult), delta: financialResult, fill: financialResult >= 0 ? "hsl(var(--chart-3))" : "hsl(var(--chart-4))" },
    { name: "Imposte", value: -Math.abs(taxes), base: ebit + financialResult - Math.abs(taxes), delta: -Math.abs(taxes), fill: "hsl(var(--chart-5))" },
    { name: "Utile Netto", value: netProfit, base: 0, delta: netProfit, fill: "hsl(var(--chart-1))" },
  ];

  // Variation table
  const variationRows = allYears.slice(1).map((y, i) => {
    const prev = allYears[i];
    const prevRev = prev.income_statement.revenue || prev.income_statement.ce01_ricavi_vendite || 0;
    const currRev = y.income_statement.revenue || y.income_statement.ce01_ricavi_vendite || 0;
    const revChange = prevRev !== 0 ? ((currRev - prevRev) / Math.abs(prevRev)) * 100 : 0;

    const prevEbitda = prev.income_statement.ebitda || 0;
    const currEbitda = y.income_statement.ebitda || 0;
    const ebitdaChange = prevEbitda !== 0 ? ((currEbitda - prevEbitda) / Math.abs(prevEbitda)) * 100 : 0;

    const prevNet = prev.income_statement.net_profit || 0;
    const currNet = y.income_statement.net_profit || 0;
    const netChange = prevNet !== 0 ? ((currNet - prevNet) / Math.abs(prevNet)) * 100 : 0;

    return {
      period: `${prev.year} → ${y.year}`,
      revChange,
      ebitdaChange,
      netChange,
    };
  });

  return (
    <section id="income-margins">
      <Card>
        <CardHeader>
          <CardTitle className="text-xl">Conto Economico e Margini</CardTitle>
        </CardHeader>
        <CardContent className="space-y-8">
          {/* Income Lines */}
          <div>
            <h3 className="text-base font-semibold mb-3">Valori Assoluti</h3>
            <ChartContainer config={incomeLineConfig} className="h-[300px] w-full">
              <LineChart data={lineData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="year" />
                <YAxis tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} />
                <ChartTooltip
                  content={<ChartTooltipContent />}
                  formatter={(value: number) => formatCurrency(value)}
                />
                <Legend />
                <Line type="monotone" dataKey="revenue" stroke="hsl(var(--chart-1))" strokeWidth={2} dot={{ r: 3 }} />
                <Line type="monotone" dataKey="ebitda" stroke="hsl(var(--chart-2))" strokeWidth={2} dot={{ r: 3 }} />
                <Line type="monotone" dataKey="ebit" stroke="hsl(var(--chart-3))" strokeWidth={2} dot={{ r: 3 }} />
                <Line type="monotone" dataKey="net_profit" stroke="hsl(var(--chart-4))" strokeWidth={2} dot={{ r: 3 }} />
              </LineChart>
            </ChartContainer>
          </div>

          {/* Margin % */}
          <div>
            <h3 className="text-base font-semibold mb-3">Margini Percentuali</h3>
            <ChartContainer config={marginConfig} className="h-[300px] w-full">
              <LineChart data={marginData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="year" />
                <YAxis tickFormatter={(v) => `${v}%`} />
                <ReferenceLine y={0} stroke="hsl(var(--muted-foreground))" strokeDasharray="3 3" />
                <ChartTooltip
                  content={<ChartTooltipContent />}
                  formatter={(value: number) => `${value.toFixed(2)}%`}
                />
                <Legend />
                <Line type="monotone" dataKey="ebitda_margin" stroke="hsl(var(--chart-2))" strokeWidth={2} dot={{ r: 3 }} />
                <Line type="monotone" dataKey="ebit_margin" stroke="hsl(var(--chart-3))" strokeWidth={2} dot={{ r: 3 }} />
                <Line type="monotone" dataKey="net_margin" stroke="hsl(var(--chart-4))" strokeWidth={2} dot={{ r: 3 }} />
              </LineChart>
            </ChartContainer>
          </div>

          {/* Waterfall */}
          <div>
            <h3 className="text-base font-semibold mb-3">
              Cascata dal Fatturato all&apos;Utile Netto ({latestYear.year})
            </h3>
            <ChartContainer config={{ value: { label: "Valore" } }} className="h-[300px] w-full">
              <BarChart data={waterfallData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                <YAxis tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} />
                <ChartTooltip
                  formatter={(value: number) => formatCurrency(value)}
                />
                <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                  {waterfallData.map((entry, index) => (
                    <Cell key={index} fill={entry.fill} />
                  ))}
                </Bar>
              </BarChart>
            </ChartContainer>
          </div>

          {/* Variation Table */}
          {variationRows.length > 0 && (
            <div>
              <h3 className="text-base font-semibold mb-3">Variazioni Anno su Anno</h3>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Periodo</TableHead>
                    <TableHead className="text-right">Var. Fatturato</TableHead>
                    <TableHead className="text-right">Var. EBITDA</TableHead>
                    <TableHead className="text-right">Var. Utile Netto</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {variationRows.map((row) => (
                    <TableRow key={row.period}>
                      <TableCell className="font-medium">{row.period}</TableCell>
                      <TableCell className="text-right">
                        <span className={row.revChange >= 0 ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"}>
                          {row.revChange >= 0 ? "+" : ""}{formatNumber(row.revChange, 1)}%
                        </span>
                      </TableCell>
                      <TableCell className="text-right">
                        <span className={row.ebitdaChange >= 0 ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"}>
                          {row.ebitdaChange >= 0 ? "+" : ""}{formatNumber(row.ebitdaChange, 1)}%
                        </span>
                      </TableCell>
                      <TableCell className="text-right">
                        <span className={row.netChange >= 0 ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"}>
                          {row.netChange >= 0 ? "+" : ""}{formatNumber(row.netChange, 1)}%
                        </span>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </section>
  );
}
