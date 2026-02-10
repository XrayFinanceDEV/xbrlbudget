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

interface ReportCashflowProps {
  data: ScenarioAnalysis;
}

const cfConfig: ChartConfig = {
  operating: { label: "Operativa", color: "var(--chart-1)" },
  investing: { label: "Investimento", color: "var(--chart-2)" },
  financing: { label: "Finanziamento", color: "var(--chart-3)" },
  total: { label: "Totale", color: "var(--chart-4)" },
};

export function ReportCashflow({ data }: ReportCashflowProps) {
  const cfYears = data.calculations.cashflow?.years || [];

  if (cfYears.length === 0) {
    return (
      <section id="cashflow">
        <Card>
          <CardHeader>
            <CardTitle className="text-xl">Rendiconto Finanziario</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-muted-foreground">
              Dati insufficienti per il calcolo del rendiconto finanziario
              (servono almeno 2 anni consecutivi).
            </p>
          </CardContent>
        </Card>
      </section>
    );
  }

  const chartData = cfYears.map((cf) => ({
    year: cf.year,
    operating: cf.operating.total_operating_cashflow,
    investing: cf.investing.total_investing_cashflow,
    financing: cf.financing.total_financing_cashflow,
    total: cf.cash_reconciliation.total_cashflow,
  }));

  return (
    <section id="cashflow">
      <Card>
        <CardHeader>
          <CardTitle className="text-xl">Rendiconto Finanziario</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Cashflow trend chart */}
          <ChartContainer config={cfConfig} className="h-[300px] w-full">
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
              <Line type="monotone" dataKey="operating" stroke="var(--chart-1)" strokeWidth={2} dot={{ r: 3 }} />
              <Line type="monotone" dataKey="investing" stroke="var(--chart-2)" strokeWidth={2} dot={{ r: 3 }} />
              <Line type="monotone" dataKey="financing" stroke="var(--chart-3)" strokeWidth={2} dot={{ r: 3 }} />
              <Line type="monotone" dataKey="total" stroke="var(--chart-4)" strokeWidth={2} strokeDasharray="5 5" dot={{ r: 3 }} />
            </LineChart>
          </ChartContainer>

          {/* Summary table */}
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Flusso</TableHead>
                  {cfYears.map((cf) => (
                    <TableHead key={cf.year} className="text-right">{cf.year}</TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                <TableRow>
                  <TableCell className="font-medium">A) Attivita Operativa</TableCell>
                  {cfYears.map((cf) => (
                    <TableCell key={cf.year} className="text-right">
                      {formatCurrency(cf.operating.total_operating_cashflow)}
                    </TableCell>
                  ))}
                </TableRow>
                <TableRow className="text-xs text-muted-foreground">
                  <TableCell className="pl-6">di cui: var. CCN</TableCell>
                  {cfYears.map((cf) => (
                    <TableCell key={cf.year} className="text-right">
                      {formatCurrency(cf.operating.working_capital_changes.total)}
                    </TableCell>
                  ))}
                </TableRow>
                <TableRow>
                  <TableCell className="font-medium">B) Attivita di Investimento</TableCell>
                  {cfYears.map((cf) => (
                    <TableCell key={cf.year} className="text-right">
                      {formatCurrency(cf.investing.total_investing_cashflow)}
                    </TableCell>
                  ))}
                </TableRow>
                <TableRow>
                  <TableCell className="font-medium">C) Attivita di Finanziamento</TableCell>
                  {cfYears.map((cf) => (
                    <TableCell key={cf.year} className="text-right">
                      {formatCurrency(cf.financing.total_financing_cashflow)}
                    </TableCell>
                  ))}
                </TableRow>
                <TableRow className="border-t-2 font-bold">
                  <TableCell>Variazione Netta Liquidita (A+B+C)</TableCell>
                  {cfYears.map((cf) => (
                    <TableCell key={cf.year} className="text-right">
                      {formatCurrency(cf.cash_reconciliation.total_cashflow)}
                    </TableCell>
                  ))}
                </TableRow>
                <TableRow>
                  <TableCell className="font-medium">Disponibilita Inizio</TableCell>
                  {cfYears.map((cf) => (
                    <TableCell key={cf.year} className="text-right">
                      {formatCurrency(cf.cash_reconciliation.cash_beginning)}
                    </TableCell>
                  ))}
                </TableRow>
                <TableRow>
                  <TableCell className="font-medium">Disponibilita Fine</TableCell>
                  {cfYears.map((cf) => (
                    <TableCell key={cf.year} className="text-right font-semibold">
                      {formatCurrency(cf.cash_reconciliation.cash_ending)}
                    </TableCell>
                  ))}
                </TableRow>
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>
    </section>
  );
}
