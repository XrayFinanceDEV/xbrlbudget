"use client";

import { useState, useEffect } from "react";
import { useApp } from "@/contexts/AppContext";
import { useScenarios, useAnalysis, getPreferredScenario } from "@/hooks/use-queries";
import { formatCurrency, formatPercentage } from "@/lib/formatters";
import type {
  BudgetScenario,
  ScenarioAnalysis,
} from "@/types/api";
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Legend,
  ComposedChart,
  Area,
} from "recharts";
import { BarChart3, AlertTriangle, AlertCircle, Loader2, Info } from "lucide-react";
import { cn } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { PageHeader } from "@/components/page-header";
import { ScenarioSelector } from "@/components/scenario-selector";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";

// Chart configs
const assetsChartConfig = {
  fixed_assets: { label: "Immobilizzazioni", color: "hsl(var(--chart-3))" },
  current_assets: { label: "Attivo Circolante", color: "hsl(var(--chart-1))" },
  total_assets: { label: "Totale Attivo", color: "hsl(var(--chart-5))" },
} satisfies ChartConfig;

const equityDebtChartConfig = {
  total_equity: { label: "Patrimonio Netto", color: "hsl(var(--chart-2))" },
  total_debt: { label: "Debiti Totali", color: "hsl(var(--chart-5))" },
} satisfies ChartConfig;

const wcChartConfig = {
  working_capital_net: { label: "CCN", color: "hsl(var(--chart-4))" },
} satisfies ChartConfig;

// Type for year data from analysis endpoint
type YearData = {
  year: number;
  type: "historical" | "forecast";
  income_statement: Record<string, number>;
  balance_sheet: Record<string, number>;
};

export default function ForecastBalancePage() {
  const { selectedCompanyId } = useApp();
  const { data: scenarios = [], isLoading: scenariosLoading } = useScenarios(selectedCompanyId);
  const [selectedScenario, setSelectedScenario] = useState<BudgetScenario | null>(null);

  // Auto-select preferred scenario when scenarios load
  useEffect(() => {
    if (scenarios.length > 0 && !selectedScenario) {
      setSelectedScenario(getPreferredScenario(scenarios));
    }
    if (!selectedCompanyId) setSelectedScenario(null);
  }, [scenarios, selectedCompanyId, selectedScenario]);

  const { data: analysisData, isLoading: analysisLoading, error: analysisError } = useAnalysis(
    selectedCompanyId,
    selectedScenario?.id ?? null
  );
  const loading = scenariosLoading || analysisLoading;
  const error = analysisError ? "Impossibile caricare i dati previsionali" : null;

  if (!selectedCompanyId) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <Alert variant="default" className="border-yellow-500/50 text-yellow-700 dark:text-yellow-400 [&>svg]:text-yellow-600">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Attenzione</AlertTitle>
          <AlertDescription>
            Seleziona un&apos;azienda per visualizzare i previsionali
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  if (scenarios.length === 0 && !loading) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <PageHeader
          title="Stato Patrimoniale Previsionale"
          icon={<BarChart3 className="h-6 w-6" />}
        />
        <Alert>
          <Info className="h-4 w-4" />
          <AlertTitle>Nessuno scenario trovato</AlertTitle>
          <AlertDescription>
            Nessuno scenario budget trovato. Vai alla tab &quot;Scenari&quot; per creare uno scenario.
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  const historicalYears = analysisData?.historical_years ?? [];
  const forecastYears = analysisData?.forecast_years ?? [];

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <PageHeader
        title="Stato Patrimoniale Previsionale"
        icon={<BarChart3 className="h-6 w-6" />}
      />

      {/* Scenario Selector */}
      <Card className="mb-6">
        <CardContent className="pt-6">
          <ScenarioSelector
            scenarios={scenarios}
            selectedScenario={selectedScenario}
            onSelect={setSelectedScenario}
          />
        </CardContent>
      </Card>

      {error && (
        <Alert variant="destructive" className="mb-6">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Errore</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {loading && (
        <div className="text-center py-12">
          <Loader2 className="h-12 w-12 animate-spin text-primary mx-auto" />
          <p className="mt-4 text-muted-foreground">Caricamento...</p>
        </div>
      )}

      {!loading && analysisData && historicalYears.length > 0 && (
        <>
          {/* Balance Sheet Table */}
          <Card className="mb-6">
            <CardHeader>
              <CardTitle className="text-xl">
                Stato Patrimoniale: Confronto Storico vs Previsionale
              </CardTitle>
            </CardHeader>
            <CardContent>
              {/* Balance Check Warning */}
              <BalanceCheckWarning
                historicalYears={historicalYears}
                forecastYears={forecastYears}
              />

              <div className="overflow-x-auto">
                <BalanceSheetTable
                  historicalYears={historicalYears}
                  forecastYears={forecastYears}
                />
              </div>
            </CardContent>
          </Card>

          {/* Charts */}
          {forecastYears.length > 0 && (
            <>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
                {/* Assets Composition Chart */}
                <Card>
                  <CardHeader>
                    <CardTitle>Composizione Attivo</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <ChartContainer config={assetsChartConfig} className="h-[300px] w-full">
                      <ComposedChart data={prepareChartData(historicalYears, forecastYears)}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="year" />
                        <YAxis />
                        <ChartTooltip
                          content={
                            <ChartTooltipContent
                              formatter={(value: any) => formatCurrency(Number(value))}
                            />
                          }
                        />
                        <Legend />
                        <Area
                          type="monotone"
                          dataKey="fixed_assets"
                          fill="var(--color-fixed_assets)"
                          stroke="var(--color-fixed_assets)"
                          name="Immobilizzazioni"
                        />
                        <Area
                          type="monotone"
                          dataKey="current_assets"
                          fill="var(--color-current_assets)"
                          stroke="var(--color-current_assets)"
                          name="Attivo Circolante"
                        />
                        <Line
                          type="monotone"
                          dataKey="total_assets"
                          stroke="var(--color-total_assets)"
                          strokeWidth={2}
                          name="Totale Attivo"
                        />
                      </ComposedChart>
                    </ChartContainer>
                  </CardContent>
                </Card>

                {/* Equity vs Debt Chart */}
                <Card>
                  <CardHeader>
                    <CardTitle>Patrimonio Netto vs Debiti</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <ChartContainer config={equityDebtChartConfig} className="h-[300px] w-full">
                      <BarChart data={prepareChartData(historicalYears, forecastYears)}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="year" />
                        <YAxis />
                        <ChartTooltip
                          content={
                            <ChartTooltipContent
                              formatter={(value: any) => formatCurrency(Number(value))}
                            />
                          }
                        />
                        <Legend />
                        <Bar dataKey="total_equity" fill="var(--color-total_equity)" name="Patrimonio Netto" />
                        <Bar dataKey="total_debt" fill="var(--color-total_debt)" name="Debiti Totali" />
                      </BarChart>
                    </ChartContainer>
                  </CardContent>
                </Card>
              </div>

              {/* Working Capital Chart */}
              <Card className="mb-6">
                <CardHeader>
                  <CardTitle>Capitale Circolante Netto (CCN)</CardTitle>
                </CardHeader>
                <CardContent>
                  <ChartContainer config={wcChartConfig} className="h-[300px] w-full">
                    <LineChart data={prepareChartData(historicalYears, forecastYears)}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="year" />
                      <YAxis />
                      <ChartTooltip
                        content={
                          <ChartTooltipContent
                            formatter={(value: any) => formatCurrency(Number(value))}
                          />
                        }
                      />
                      <Legend />
                      <Line
                        type="monotone"
                        dataKey="working_capital_net"
                        stroke="var(--color-working_capital_net)"
                        strokeWidth={2}
                        name="CCN"
                      />
                    </LineChart>
                  </ChartContainer>
                </CardContent>
              </Card>

              {/* Key Metrics Summary */}
              <Card>
                <CardHeader>
                  <CardTitle>Riepilogo Indicatori Chiave</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                    {forecastYears.map((fy) => {
                      const bs = fy.balance_sheet;
                      if (!bs) return null;

                      const debtToEquity = bs.total_equity !== 0
                        ? bs.total_debt / bs.total_equity
                        : 0;

                      return (
                        <div key={fy.year} className="border border-border rounded-lg p-4">
                          <h4 className="font-semibold text-muted-foreground mb-3 text-center">
                            {fy.year}
                          </h4>
                          <div className="space-y-2 text-sm">
                            <MetricRow
                              label="Totale Attivo"
                              value={formatCurrency(bs.total_assets)}
                            />
                            <MetricRow
                              label="Patrimonio Netto"
                              value={formatCurrency(bs.total_equity)}
                            />
                            <MetricRow
                              label="Debiti Totali"
                              value={formatCurrency(bs.total_debt)}
                            />
                            <MetricRow
                              label="CCN"
                              value={formatCurrency(bs.working_capital_net)}
                            />
                            <MetricRow
                              label="Debt/Equity"
                              value={debtToEquity.toFixed(2)}
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </CardContent>
              </Card>
            </>
          )}
        </>
      )}
    </div>
  );
}

// Balance Check Warning Component
function BalanceCheckWarning({
  historicalYears,
  forecastYears,
}: {
  historicalYears: YearData[];
  forecastYears: YearData[];
}) {
  const TOLERANCE = 1.0;
  const issues: Array<{ year: number; diff: number; type: 'historical' | 'forecast' }> = [];

  historicalYears.forEach((yd) => {
    const bs = yd.balance_sheet;
    if (bs) {
      const diff = Math.abs(bs.total_assets - (bs.total_equity + bs.total_debt + (bs.sp14_fondi_rischi || 0) + (bs.sp15_tfr || 0) + (bs.sp18_ratei_risconti_passivi || 0)));
      if (diff > TOLERANCE) {
        issues.push({ year: yd.year, diff, type: 'historical' });
      }
    }
  });

  forecastYears.forEach((yd) => {
    const bs = yd.balance_sheet;
    if (bs) {
      const diff = Math.abs(bs.total_assets - (bs.total_equity + bs.total_debt + (bs.sp14_fondi_rischi || 0) + (bs.sp15_tfr || 0) + (bs.sp18_ratei_risconti_passivi || 0)));
      if (diff > TOLERANCE) {
        issues.push({ year: yd.year, diff, type: 'forecast' });
      }
    }
  });

  if (issues.length === 0) return null;

  return (
    <Alert variant="default" className="mb-4 border-yellow-500/50 text-yellow-700 dark:text-yellow-400 [&>svg]:text-yellow-600">
      <AlertTriangle className="h-4 w-4" />
      <AlertTitle>Sbilancio Rilevato</AlertTitle>
      <AlertDescription>
        <p className="mb-1">
          Il bilancio non quadra per i seguenti anni (differenza tra Attivo e Passivo):
        </p>
        <ul className="list-disc list-inside space-y-1">
          {issues.map((issue) => (
            <li key={issue.year}>
              <strong>{issue.year}</strong> ({issue.type === 'historical' ? 'Storico' : 'Previsionale'}):
              <span className="font-semibold ml-1">{formatCurrency(issue.diff)}</span>
            </li>
          ))}
        </ul>
        <p className="mt-2 text-xs">
          Possibili cause: errori di arrotondamento nell&apos;importazione XBRL/CSV, imprecisione nei dati originali.
        </p>
      </AlertDescription>
    </Alert>
  );
}

// Balance Sheet Table Component
function BalanceSheetTable({
  historicalYears,
  forecastYears,
}: {
  historicalYears: YearData[];
  forecastYears: YearData[];
}) {
  const getVal = (yearData: YearData, field: string): number => {
    return yearData.balance_sheet[field] || 0;
  };

  const rows: Array<{
    label: string;
    field?: string;
    computed?: (yd: YearData) => number;
    isTotal?: boolean;
    isSubtotal?: boolean;
    indent?: boolean;
  }> = [
    // ATTIVO (ASSETS)
    { label: "ATTIVO", isTotal: true },
    { label: "A) Crediti verso soci per versamenti ancora dovuti", field: "sp01_crediti_soci" },
    { label: "B) IMMOBILIZZAZIONI", isSubtotal: true },
    { label: "I - Immobilizzazioni immateriali", field: "sp02_immob_immateriali", indent: true },
    { label: "II - Immobilizzazioni materiali", field: "sp03_immob_materiali", indent: true },
    { label: "III - Immobilizzazioni finanziarie", field: "sp04_immob_finanziarie", indent: true },
    { label: "1) Partecipazioni", field: "sp04a_partecipazioni", indent: true },
    { label: "2) Crediti" },
    { label: "Esigibili entro l'esercizio successivo", field: "sp04b_crediti_immob_breve", indent: true },
    { label: "Esigibili oltre l'esercizio successivo", field: "sp04c_crediti_immob_lungo", indent: true },
    {
      label: "Totale crediti",
      computed: (yd) => (yd.balance_sheet.sp04b_crediti_immob_breve || 0) + (yd.balance_sheet.sp04c_crediti_immob_lungo || 0),
      indent: true,
    },
    { label: "3) Altri titoli", field: "sp04d_altri_titoli", indent: true },
    { label: "4) Strumenti finanziari derivati attivi", field: "sp04e_strumenti_derivati_attivi", indent: true },
    { label: "Totale immobilizzazioni finanziarie", field: "sp04_immob_finanziarie", indent: true },
    { label: "Totale Immobilizzazioni", field: "fixed_assets", isSubtotal: true },
    { label: "C) ATTIVO CIRCOLANTE", isSubtotal: true },
    { label: "I - Rimanenze", field: "sp05_rimanenze", indent: true },
    { label: "II - Crediti (entro esercizio successivo)", field: "sp06_crediti_breve", indent: true },
    { label: "II - Crediti (oltre esercizio successivo)", field: "sp07_crediti_lungo", indent: true },
    { label: "III - Attivit\u00e0 finanziarie che non costituiscono immobilizzazioni", field: "sp08_attivita_finanziarie", indent: true },
    { label: "IV - Disponibilit\u00e0 liquide", field: "sp09_disponibilita_liquide", indent: true },
    { label: "Totale Attivo Circolante", field: "current_assets", isSubtotal: true },
    { label: "D) Ratei e risconti attivi", field: "sp10_ratei_risconti_attivi" },
    { label: "TOTALE ATTIVO", field: "total_assets", isTotal: true },
    // PASSIVO (LIABILITIES & EQUITY)
    { label: "PASSIVO E PATRIMONIO NETTO", isTotal: true },
    { label: "A) PATRIMONIO NETTO", isSubtotal: true },
    { label: "I - Capitale", field: "sp11_capitale", indent: true },
    { label: "II - Riserva da soprapprezzo delle azioni", field: "sp12a_riserva_sovrapprezzo", indent: true },
    { label: "III - Riserve di rivalutazione", field: "sp12b_riserve_rivalutazione", indent: true },
    { label: "IV - Riserva legale", field: "sp12c_riserva_legale", indent: true },
    { label: "V - Riserve statutarie", field: "sp12d_riserve_statutarie", indent: true },
    { label: "VI - Altre riserve", field: "sp12e_altre_riserve", indent: true },
    { label: "VII - Riserva per operazioni di copertura dei flussi finanziari attesi", field: "sp12f_riserva_copertura_flussi", indent: true },
    { label: "VIII - Utili (perdite) portati a nuovo", field: "sp12g_utili_perdite_portati", indent: true },
    { label: "IX - Utile (perdita) dell'esercizio", field: "sp13_utile_perdita", indent: true },
    { label: "X - Riserva negativa per azioni proprie in portafoglio", field: "sp12h_riserva_neg_azioni_proprie", indent: true },
    { label: "Totale Patrimonio Netto", field: "total_equity", isSubtotal: true },
    { label: "B) Fondi per rischi e oneri", field: "sp14_fondi_rischi" },
    { label: "C) Trattamento di fine rapporto di lavoro subordinato", field: "sp15_tfr" },
    { label: "D) DEBITI", isSubtotal: true },
    { label: "Debiti (entro esercizio successivo)", field: "sp16_debiti_breve", indent: true },
    { label: "Debiti (oltre esercizio successivo)", field: "sp17_debiti_lungo", indent: true },
    { label: "Totale Debiti", field: "total_debt", isSubtotal: true },
    { label: "E) Ratei e risconti passivi", field: "sp18_ratei_risconti_passivi" },
    {
      label: "TOTALE PASSIVO E PATRIMONIO NETTO",
      computed: (yd) => {
        const bs = yd.balance_sheet;
        return (bs.total_equity || 0) + (bs.total_debt || 0) + (bs.sp14_fondi_rischi || 0) + (bs.sp15_tfr || 0) + (bs.sp18_ratei_risconti_passivi || 0);
      },
      isTotal: true,
    },
    {
      label: "DIFFERENZA (Attivo - Passivo)",
      computed: (yd) => {
        const bs = yd.balance_sheet;
        const totalPassivo = (bs.total_equity || 0) + (bs.total_debt || 0) + (bs.sp14_fondi_rischi || 0) + (bs.sp15_tfr || 0) + (bs.sp18_ratei_risconti_passivi || 0);
        return (bs.total_assets || 0) - totalPassivo;
      },
      isSubtotal: true,
    },
  ];

  return (
    <table className="min-w-full divide-y divide-border border border-border">
      <thead className="bg-muted">
        <tr>
          <th className="px-4 py-3 text-left text-xs font-bold text-foreground uppercase border-r border-border">
            Descrizione
          </th>
          {historicalYears.map((yd) => (
            <th
              key={yd.year}
              className="px-4 py-3 text-center text-xs font-bold text-foreground uppercase border-r border-border"
            >
              {yd.year}
              <div className="text-muted-foreground font-normal">(Storico)</div>
            </th>
          ))}
          {forecastYears.map((yd) => (
            <th
              key={yd.year}
              className="px-4 py-3 text-center text-xs font-bold text-primary uppercase border-r border-border bg-primary/10"
            >
              {yd.year}
              <div className="text-primary font-normal">(Previsionale)</div>
            </th>
          ))}
        </tr>
      </thead>
      <tbody className="bg-card divide-y divide-border">
        {rows.map((row, index) => {
          const getValue = (yd: YearData): number | null => {
            if (row.computed) return row.computed(yd);
            if (row.field) return getVal(yd, row.field);
            return null;
          };

          const histValues = historicalYears.map(getValue);
          const fcValues = forecastYears.map(getValue);
          const hasValues = row.field || row.computed;

          const bgClass = row.isTotal
            ? "bg-muted font-bold"
            : row.isSubtotal
            ? "bg-primary/10 font-semibold"
            : "hover:bg-muted/50";

          return (
            <tr key={index} className={bgClass}>
              <td className={cn(
                "px-4 py-2 text-sm text-foreground border-r border-border",
                row.indent && "pl-8"
              )}>
                {row.label}
              </td>
              {histValues.map((value, i) => (
                <td
                  key={`hist-${i}`}
                  className={cn(
                    "px-4 py-2 text-sm text-right border-r border-border",
                    value !== null && value < 0 ? "text-destructive" : "text-foreground",
                    (row.isTotal || row.isSubtotal) && "font-semibold"
                  )}
                >
                  {value === null ? "" : (row.isTotal && !value ? "" : formatCurrency(value))}
                </td>
              ))}
              {fcValues.map((value, i) => (
                <td
                  key={`forecast-${i}`}
                  className={cn(
                    "px-4 py-2 text-sm text-right border-r border-border",
                    value !== null && value < 0 ? "text-destructive" : "text-foreground",
                    (row.isTotal || row.isSubtotal) && "font-semibold"
                  )}
                >
                  {value === null ? "" : (row.isTotal && !value ? "" : formatCurrency(value))}
                </td>
              ))}
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

// Metric Row Component
function MetricRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between">
      <span className="text-muted-foreground">{label}:</span>
      <span className="font-semibold text-foreground">{value}</span>
    </div>
  );
}

// Helper function to prepare chart data
function prepareChartData(
  historicalYears: YearData[],
  forecastYears: YearData[]
): any[] {
  const allYears = [...historicalYears, ...forecastYears];
  return allYears.map((yd) => ({
    year: yd.year.toString(),
    total_assets: yd.balance_sheet.total_assets || 0,
    total_equity: yd.balance_sheet.total_equity || 0,
    total_debt: yd.balance_sheet.total_debt || 0,
    fixed_assets: yd.balance_sheet.fixed_assets || 0,
    current_assets: yd.balance_sheet.current_assets || 0,
    working_capital_net: yd.balance_sheet.working_capital_net || 0,
  }));
}
