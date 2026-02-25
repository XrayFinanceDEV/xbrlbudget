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
import { formatCurrency } from "@/lib/formatters";
import type { ScenarioAnalysis } from "@/types/api";

interface ReportStructuralProps {
  data: ScenarioAnalysis;
}

const structuralConfig: ChartConfig = {
  ms: { label: "Margine di Struttura (MS)", color: "hsl(var(--chart-1))" },
  ccn: { label: "Capitale Circ. Netto (CCN)", color: "hsl(var(--chart-2))" },
  mt: { label: "Margine di Tesoreria (MT)", color: "hsl(var(--chart-3))" },
};

export function ReportStructural({ data }: ReportStructuralProps) {
  const allYears = [...data.historical_years, ...data.forecast_years].sort(
    (a, b) => a.year - b.year
  );

  const chartData = allYears.map((y) => {
    const calc = data.calculations.by_year[String(y.year)];
    const wc = calc?.ratios.working_capital;
    return {
      year: y.year,
      ms: wc?.ms ?? 0,
      ccn: wc?.ccn ?? 0,
      mt: wc?.mt ?? 0,
    };
  });

  return (
    <section id="structural">
      <Card>
        <CardHeader>
          <CardTitle className="text-xl">Analisi Strutturale</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <ChartContainer config={structuralConfig} className="h-[300px] w-full">
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="year" />
              <YAxis tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} />
              <ReferenceLine y={0} stroke="hsl(var(--muted-foreground))" strokeDasharray="3 3" />
              <ChartTooltip
                content={<ChartTooltipContent />}
                formatter={(value: number) => formatCurrency(value)}
              />
              <Legend />
              <Line type="monotone" dataKey="ms" stroke="hsl(var(--chart-1))" strokeWidth={2} dot={{ r: 3 }} />
              <Line type="monotone" dataKey="ccn" stroke="hsl(var(--chart-2))" strokeWidth={2} dot={{ r: 3 }} />
              <Line type="monotone" dataKey="mt" stroke="hsl(var(--chart-3))" strokeWidth={2} dot={{ r: 3 }} />
            </LineChart>
          </ChartContainer>

          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Indicatore</TableHead>
                {allYears.map((y) => (
                  <TableHead key={y.year} className="text-right">{y.year}</TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow>
                <TableCell className="font-medium">Margine di Struttura (MS)</TableCell>
                {chartData.map((d) => (
                  <TableCell key={d.year} className="text-right">{formatCurrency(d.ms)}</TableCell>
                ))}
              </TableRow>
              <TableRow>
                <TableCell className="font-medium">Cap. Circ. Netto (CCN)</TableCell>
                {chartData.map((d) => (
                  <TableCell key={d.year} className="text-right">{formatCurrency(d.ccn)}</TableCell>
                ))}
              </TableRow>
              <TableRow>
                <TableCell className="font-medium">Margine di Tesoreria (MT)</TableCell>
                {chartData.map((d) => (
                  <TableCell key={d.year} className="text-right">{formatCurrency(d.mt)}</TableCell>
                ))}
              </TableRow>
              <TableRow>
                <TableCell className="font-medium">Cap. Circ. Lordo (CCLN)</TableCell>
                {allYears.map((y) => {
                  const calc = data.calculations.by_year[String(y.year)];
                  return (
                    <TableCell key={y.year} className="text-right">
                      {formatCurrency(calc?.ratios.working_capital.ccln ?? 0)}
                    </TableCell>
                  );
                })}
              </TableRow>
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </section>
  );
}
