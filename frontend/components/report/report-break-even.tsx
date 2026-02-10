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
import { formatCurrency, formatNumber } from "@/lib/formatters";
import type { ScenarioAnalysis } from "@/types/api";

interface ReportBreakEvenProps {
  data: ScenarioAnalysis;
}

const bepConfig: ChartConfig = {
  revenue: { label: "Fatturato", color: "var(--chart-1)" },
  bep: { label: "Break Even Point", color: "var(--chart-2)" },
  safety: { label: "Margine Sicurezza %", color: "var(--chart-3)" },
};

export function ReportBreakEven({ data }: ReportBreakEvenProps) {
  const allYears = [...data.historical_years, ...data.forecast_years]
    .map((y) => y.year)
    .sort((a, b) => a - b);

  const chartData = allYears.map((year) => {
    const calc = data.calculations.by_year[String(year)];
    const be = calc?.ratios.break_even;
    const yearData = [...data.historical_years, ...data.forecast_years].find(
      (y) => y.year === year
    );
    const revenue = yearData?.income_statement.revenue ||
      yearData?.income_statement.ce01_ricavi_vendite || 0;
    return {
      year,
      revenue,
      bep: be?.break_even_revenue ?? 0,
      safety: be ? +(be.safety_margin * 100).toFixed(2) : 0,
    };
  });

  return (
    <section id="break-even">
      <Card>
        <CardHeader>
          <CardTitle className="text-xl">Break Even Point</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* BEP vs Revenue chart */}
          <div>
            <h3 className="text-base font-semibold mb-3">Fatturato vs Break Even Point</h3>
            <ChartContainer config={bepConfig} className="h-[300px] w-full">
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="year" />
                <YAxis tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} />
                <ChartTooltip
                  content={<ChartTooltipContent />}
                  formatter={(value: number) => formatCurrency(value)}
                />
                <Legend />
                <Line type="monotone" dataKey="revenue" stroke="var(--chart-1)" strokeWidth={2} dot={{ r: 3 }} />
                <Line type="monotone" dataKey="bep" stroke="var(--chart-2)" strokeWidth={2} strokeDasharray="5 5" dot={{ r: 3 }} />
              </LineChart>
            </ChartContainer>
          </div>

          {/* Safety margin chart */}
          <div>
            <h3 className="text-base font-semibold mb-3">Margine di Sicurezza</h3>
            <ChartContainer config={bepConfig} className="h-[200px] w-full">
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="year" />
                <YAxis tickFormatter={(v) => `${v}%`} />
                <ReferenceLine y={0} stroke="hsl(var(--muted-foreground))" strokeDasharray="3 3" />
                <ChartTooltip
                  content={<ChartTooltipContent />}
                  formatter={(value: number) => `${value.toFixed(2)}%`}
                />
                <Line type="monotone" dataKey="safety" stroke="var(--chart-3)" strokeWidth={2} dot={{ r: 3 }} />
              </LineChart>
            </ChartContainer>
          </div>

          {/* Metrics table */}
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Metrica</TableHead>
                  {allYears.map((year) => (
                    <TableHead key={year} className="text-right">{year}</TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                <TableRow>
                  <TableCell className="font-medium">Costi Fissi</TableCell>
                  {allYears.map((year) => {
                    const be = data.calculations.by_year[String(year)]?.ratios.break_even;
                    return (
                      <TableCell key={year} className="text-right">
                        {be ? formatCurrency(be.fixed_costs) : "N/D"}
                      </TableCell>
                    );
                  })}
                </TableRow>
                <TableRow>
                  <TableCell className="font-medium">Costi Variabili</TableCell>
                  {allYears.map((year) => {
                    const be = data.calculations.by_year[String(year)]?.ratios.break_even;
                    return (
                      <TableCell key={year} className="text-right">
                        {be ? formatCurrency(be.variable_costs) : "N/D"}
                      </TableCell>
                    );
                  })}
                </TableRow>
                <TableRow>
                  <TableCell className="font-medium">Margine Contribuzione</TableCell>
                  {allYears.map((year) => {
                    const be = data.calculations.by_year[String(year)]?.ratios.break_even;
                    return (
                      <TableCell key={year} className="text-right">
                        {be ? formatCurrency(be.contribution_margin) : "N/D"}
                      </TableCell>
                    );
                  })}
                </TableRow>
                <TableRow>
                  <TableCell className="font-medium">% Margine Contribuzione</TableCell>
                  {allYears.map((year) => {
                    const be = data.calculations.by_year[String(year)]?.ratios.break_even;
                    return (
                      <TableCell key={year} className="text-right">
                        {be ? formatNumber(be.contribution_margin_percentage * 100, 2) + "%" : "N/D"}
                      </TableCell>
                    );
                  })}
                </TableRow>
                <TableRow>
                  <TableCell className="font-medium">Ricavi BEP</TableCell>
                  {allYears.map((year) => {
                    const be = data.calculations.by_year[String(year)]?.ratios.break_even;
                    return (
                      <TableCell key={year} className="text-right font-semibold">
                        {be ? formatCurrency(be.break_even_revenue) : "N/D"}
                      </TableCell>
                    );
                  })}
                </TableRow>
                <TableRow>
                  <TableCell className="font-medium">Margine Sicurezza</TableCell>
                  {allYears.map((year) => {
                    const be = data.calculations.by_year[String(year)]?.ratios.break_even;
                    return (
                      <TableCell key={year} className="text-right">
                        {be ? formatNumber(be.safety_margin * 100, 2) + "%" : "N/D"}
                      </TableCell>
                    );
                  })}
                </TableRow>
                <TableRow>
                  <TableCell className="font-medium">Leva Operativa</TableCell>
                  {allYears.map((year) => {
                    const be = data.calculations.by_year[String(year)]?.ratios.break_even;
                    return (
                      <TableCell key={year} className="text-right">
                        {be ? formatNumber(be.operating_leverage, 2) : "N/D"}
                      </TableCell>
                    );
                  })}
                </TableRow>
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>
    </section>
  );
}
