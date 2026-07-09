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
import type { ScenarioAnalysis, ScenarioAnalysisCashflowYear } from "@/types/api";

interface ReportCashflowProps {
  data: ScenarioAnalysis;
}

// Full OIC indirect-method rendiconto rows. Each `get` reads a value from the
// per-year cashflow object already present in the /analysis payload (no extra
// fetch). `kind` drives styling: section header / subtotal / total / detail.
type CFRow = {
  label: string;
  get?: (cf: ScenarioAnalysisCashflowYear) => number;
  kind?: "section" | "subtotal" | "total" | "detail" | "group";
};

const CF_ROWS: CFRow[] = [
  { label: "A) Flussi finanziari dell'attività operativa", kind: "section" },
  { label: "Utile (perdita) dell'esercizio", get: (cf) => cf.operating.start.net_profit, kind: "detail" },
  { label: "Imposte sul reddito", get: (cf) => cf.operating.start.income_taxes, kind: "detail" },
  { label: "Interessi passivi/(interessi attivi)", get: (cf) => cf.operating.start.interest_expense_income, kind: "detail" },
  { label: "(Dividendi)", get: (cf) => cf.operating.start.dividends, kind: "detail" },
  { label: "(Plusvalenze)/minusvalenze da cessione", get: (cf) => cf.operating.start.capital_gains_losses, kind: "detail" },
  { label: "1. Utile prima di imposte, interessi, dividendi e plus/minusvalenze", get: (cf) => cf.operating.start.profit_before_adjustments, kind: "subtotal" },
  { label: "Rettifiche per elementi non monetari:", kind: "group" },
  { label: "Accantonamenti ai fondi", get: (cf) => cf.operating.non_cash_adjustments.provisions, kind: "detail" },
  { label: "Ammortamenti delle immobilizzazioni", get: (cf) => cf.operating.non_cash_adjustments.depreciation_amortization, kind: "detail" },
  { label: "Svalutazioni per perdite durevoli di valore", get: (cf) => cf.operating.non_cash_adjustments.write_downs, kind: "detail" },
  { label: "Totale rettifiche per elementi non monetari", get: (cf) => cf.operating.non_cash_adjustments.total, kind: "subtotal" },
  { label: "2. Flusso finanziario prima delle variazioni del ccn", get: (cf) => cf.operating.cashflow_before_wc, kind: "subtotal" },
  { label: "Variazioni del capitale circolante netto:", kind: "group" },
  { label: "Decremento/(incremento) delle rimanenze", get: (cf) => cf.operating.working_capital_changes.delta_inventory, kind: "detail" },
  { label: "Decremento/(incremento) dei crediti", get: (cf) => cf.operating.working_capital_changes.delta_receivables, kind: "detail" },
  { label: "Incremento/(decremento) dei debiti", get: (cf) => cf.operating.working_capital_changes.delta_payables, kind: "detail" },
  { label: "Decremento/(incremento) ratei e risconti attivi", get: (cf) => cf.operating.working_capital_changes.delta_accruals_deferrals_active, kind: "detail" },
  { label: "Incremento/(decremento) ratei e risconti passivi", get: (cf) => cf.operating.working_capital_changes.delta_accruals_deferrals_passive, kind: "detail" },
  { label: "Altri incrementi/(decrementi) del ccn", get: (cf) => cf.operating.working_capital_changes.other_wc_changes, kind: "detail" },
  { label: "Totale variazioni del capitale circolante netto", get: (cf) => cf.operating.working_capital_changes.total, kind: "subtotal" },
  { label: "3. Flusso finanziario dopo le variazioni del ccn", get: (cf) => cf.operating.cashflow_after_wc, kind: "subtotal" },
  { label: "Altre rettifiche:", kind: "group" },
  { label: "Interessi incassati/(pagati)", get: (cf) => cf.operating.cash_adjustments.interest_paid_received, kind: "detail" },
  { label: "(Imposte sul reddito pagate)", get: (cf) => cf.operating.cash_adjustments.taxes_paid, kind: "detail" },
  { label: "Dividendi incassati", get: (cf) => cf.operating.cash_adjustments.dividends_received, kind: "detail" },
  { label: "(Utilizzo dei fondi)", get: (cf) => cf.operating.cash_adjustments.use_of_provisions, kind: "detail" },
  { label: "Altri incassi/(pagamenti)", get: (cf) => cf.operating.cash_adjustments.other_cash_changes, kind: "detail" },
  { label: "Totale altre rettifiche", get: (cf) => cf.operating.cash_adjustments.total, kind: "subtotal" },
  { label: "Flusso finanziario dell'attività operativa (A)", get: (cf) => cf.operating.total_operating_cashflow, kind: "total" },
  { label: "B) Flussi finanziari dell'attività d'investimento", kind: "section" },
  { label: "Immobilizzazioni materiali — (Investimenti)", get: (cf) => cf.investing.tangible_assets.investments, kind: "detail" },
  { label: "Immobilizzazioni materiali — Disinvestimenti", get: (cf) => cf.investing.tangible_assets.disinvestments, kind: "detail" },
  { label: "Immobilizzazioni immateriali — (Investimenti)", get: (cf) => cf.investing.intangible_assets.investments, kind: "detail" },
  { label: "Immobilizzazioni immateriali — Disinvestimenti", get: (cf) => cf.investing.intangible_assets.disinvestments, kind: "detail" },
  { label: "Immobilizzazioni finanziarie — (Investimenti)", get: (cf) => cf.investing.financial_assets.investments, kind: "detail" },
  { label: "Immobilizzazioni finanziarie — Disinvestimenti", get: (cf) => cf.investing.financial_assets.disinvestments, kind: "detail" },
  { label: "Flusso finanziario dell'attività di investimento (B)", get: (cf) => cf.investing.total_investing_cashflow, kind: "total" },
  { label: "C) Flussi finanziari dell'attività di finanziamento", kind: "section" },
  { label: "Mezzi di terzi — Incremento", get: (cf) => cf.financing.third_party_funds.increases, kind: "detail" },
  { label: "Mezzi di terzi — (Decremento)", get: (cf) => cf.financing.third_party_funds.decreases, kind: "detail" },
  { label: "Mezzi propri — Incremento", get: (cf) => cf.financing.own_funds.increases, kind: "detail" },
  { label: "Mezzi propri — (Decremento)", get: (cf) => cf.financing.own_funds.decreases, kind: "detail" },
  { label: "Flusso finanziario dell'attività di finanziamento (C)", get: (cf) => cf.financing.total_financing_cashflow, kind: "total" },
  { label: "Incremento (decremento) delle disponibilità liquide (A±B±C)", get: (cf) => cf.cash_reconciliation.total_cashflow, kind: "total" },
  { label: "Disponibilità liquide all'inizio dell'esercizio", get: (cf) => cf.cash_reconciliation.cash_beginning, kind: "detail" },
  { label: "Disponibilità liquide alla fine dell'esercizio", get: (cf) => cf.cash_reconciliation.cash_ending, kind: "subtotal" },
];

const cfConfig: ChartConfig = {
  operating: { label: "Operativa", color: "hsl(var(--chart-1))" },
  investing: { label: "Investimento", color: "hsl(var(--chart-2))" },
  financing: { label: "Finanziamento", color: "hsl(var(--chart-3))" },
  total: { label: "Totale", color: "hsl(var(--chart-4))" },
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
        <CardContent className="space-y-6 print:space-y-1">
          {/* Cashflow trend chart */}
          <div className="print-together">
          <ChartContainer config={cfConfig} className="h-[300px] print:h-[180px] w-full">
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
              <Line type="monotone" dataKey="operating" stroke="hsl(var(--chart-1))" strokeWidth={2} dot={{ r: 3 }} />
              <Line type="monotone" dataKey="investing" stroke="hsl(var(--chart-2))" strokeWidth={2} dot={{ r: 3 }} />
              <Line type="monotone" dataKey="financing" stroke="hsl(var(--chart-3))" strokeWidth={2} dot={{ r: 3 }} />
              <Line type="monotone" dataKey="total" stroke="hsl(var(--chart-4))" strokeWidth={2} strokeDasharray="5 5" dot={{ r: 3 }} />
            </LineChart>
          </ChartContainer>
          </div>

          {/* Full OIC indirect-method detail table */}
          <div className="overflow-x-auto print-together">
            <Table className="print:text-[11px] print-compact-table">
              <TableHeader>
                <TableRow>
                  <TableHead className="min-w-[280px] print:min-w-0">Rendiconto Finanziario (metodo indiretto)</TableHead>
                  {cfYears.map((cf) => (
                    <TableHead key={cf.year} className="text-right min-w-[110px] print:min-w-0">{cf.year}</TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {CF_ROWS.map((row, idx) => {
                  const rowClass =
                    row.kind === "section"
                      ? "bg-muted/50 font-bold"
                      : row.kind === "total"
                      ? "border-t-2 font-bold"
                      : row.kind === "subtotal"
                      ? "border-t font-semibold"
                      : row.kind === "group"
                      ? "text-muted-foreground italic"
                      : "";
                  const isDetail = row.kind === "detail" || !row.kind;
                  return (
                    <TableRow key={`${row.label}-${idx}`} className={rowClass}>
                      <TableCell className={isDetail ? "pl-6" : undefined}>{row.label}</TableCell>
                      {cfYears.map((cf) => (
                        <TableCell key={cf.year} className="text-right">
                          {row.get ? formatCurrency(row.get(cf)) : ""}
                        </TableCell>
                      ))}
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>
    </section>
  );
}
