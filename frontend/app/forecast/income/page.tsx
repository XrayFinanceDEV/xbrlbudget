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
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  ChartLegend,
  ChartLegendContent,
  type ChartConfig,
} from "@/components/ui/chart";
import { Loader2, TrendingUp, AlertTriangle, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { PageHeader } from "@/components/page-header";
import { ScenarioSelector } from "@/components/scenario-selector";

const revenueChartConfig = {
  revenue: { label: "Ricavi", color: "hsl(var(--chart-1))" },
  ebitda: { label: "EBITDA", color: "hsl(var(--chart-2))" },
} satisfies ChartConfig;

const profitChartConfig = {
  ebit: { label: "EBIT", color: "hsl(var(--chart-3))" },
  net_profit: { label: "Utile Netto", color: "hsl(var(--chart-4))" },
} satisfies ChartConfig;

export default function ForecastIncomePage() {
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
        <Alert>
          <AlertTriangle className="h-4 w-4" />
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
          title="Conto Economico Previsionale"
          icon={<TrendingUp className="h-6 w-6" />}
        />
        <Alert>
          <AlertCircle className="h-4 w-4" />
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
        title="Conto Economico Previsionale"
        icon={<TrendingUp className="h-6 w-6" />}
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
          {/* Income Statement Table */}
          <Card className="mb-6">
            <CardHeader>
              <CardTitle>
                Conto Economico: Confronto Storico vs Previsionale
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <IncomeStatementTable
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
                {/* Revenue & EBITDA Chart */}
                <Card>
                  <CardHeader>
                    <CardTitle>Ricavi ed EBITDA</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <ChartContainer config={revenueChartConfig} className="h-[300px] w-full">
                      <LineChart
                        data={prepareChartData(historicalYears, forecastYears, ["revenue", "ebitda"])}
                      >
                        <CartesianGrid vertical={false} />
                        <XAxis dataKey="year" />
                        <YAxis />
                        <ChartTooltip
                          content={
                            <ChartTooltipContent
                              formatter={(value) => formatCurrency(value as number)}
                            />
                          }
                        />
                        <ChartLegend content={<ChartLegendContent />} />
                        <Line
                          type="monotone"
                          dataKey="revenue"
                          stroke="var(--color-revenue)"
                          strokeWidth={2}
                        />
                        <Line
                          type="monotone"
                          dataKey="ebitda"
                          stroke="var(--color-ebitda)"
                          strokeWidth={2}
                        />
                      </LineChart>
                    </ChartContainer>
                  </CardContent>
                </Card>

                {/* EBIT & Net Profit Chart */}
                <Card>
                  <CardHeader>
                    <CardTitle>EBIT e Utile Netto</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <ChartContainer config={profitChartConfig} className="h-[300px] w-full">
                      <BarChart
                        data={prepareChartData(historicalYears, forecastYears, ["ebit", "net_profit"])}
                      >
                        <CartesianGrid vertical={false} />
                        <XAxis dataKey="year" />
                        <YAxis />
                        <ChartTooltip
                          content={
                            <ChartTooltipContent
                              formatter={(value) => formatCurrency(value as number)}
                            />
                          }
                        />
                        <ChartLegend content={<ChartLegendContent />} />
                        <Bar dataKey="ebit" fill="var(--color-ebit)" />
                        <Bar dataKey="net_profit" fill="var(--color-net_profit)" />
                      </BarChart>
                    </ChartContainer>
                  </CardContent>
                </Card>
              </div>

              {/* Key Metrics Summary */}
              <Card>
                <CardHeader>
                  <CardTitle>Riepilogo Indicatori Chiave</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                    {forecastYears.map((fy) => {
                      const inc = fy.income_statement;
                      if (!inc) return null;

                      return (
                        <Card key={fy.year}>
                          <CardContent className="pt-6">
                            <h4 className="font-semibold text-muted-foreground mb-3 text-center">
                              {fy.year}
                            </h4>
                            <div className="space-y-2 text-sm">
                              <MetricRow
                                label="Ricavi"
                                value={formatCurrency(inc.revenue)}
                              />
                              <MetricRow
                                label="EBITDA"
                                value={formatCurrency(inc.ebitda)}
                              />
                              <MetricRow
                                label="Margine EBITDA"
                                value={formatPercentage(inc.revenue ? inc.ebitda / inc.revenue : 0)}
                              />
                              <MetricRow
                                label="EBIT"
                                value={formatCurrency(inc.ebit)}
                              />
                              <MetricRow
                                label="Utile Netto"
                                value={formatCurrency(inc.net_profit)}
                              />
                            </div>
                          </CardContent>
                        </Card>
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

// Type for year data from analysis endpoint
type YearData = {
  year: number;
  type: "historical" | "forecast";
  income_statement: Record<string, number>;
  balance_sheet: Record<string, number>;
};

// Income Statement Table Component
function IncomeStatementTable({
  historicalYears,
  forecastYears,
}: {
  historicalYears: YearData[];
  forecastYears: YearData[];
}) {
  const getVal = (yearData: YearData, field: string): number => {
    return yearData.income_statement[field] || 0;
  };

  const rows: Array<{
    label: string;
    field?: string;
    calculated?: (yd: YearData) => number;
    isTotal?: boolean;
    isSubtotal?: boolean;
    indent?: number;
  }> = [
    // A) VALORE DELLA PRODUZIONE
    { label: "A) VALORE DELLA PRODUZIONE", isTotal: true },
    { label: "1) Ricavi delle vendite e delle prestazioni", field: "ce01_ricavi_vendite" },
    { label: "2) Variazioni delle rim. di prodotti in corso di lav., semilav. e finiti", field: "ce02_variazioni_rimanenze" },
    { label: "3) Variazioni dei lavori in corso su ordinazione", field: "ce03_lavori_interni" },
    { label: "5) Altri ricavi e proventi", field: "ce04_altri_ricavi" },
    { label: "Totale Valore della Produzione", field: "production_value", isSubtotal: true },
    // B) COSTI DELLA PRODUZIONE
    { label: "B) COSTI DELLA PRODUZIONE", isTotal: true },
    { label: "6) Materie prime, sussidiarie, di consumo e di merci", field: "ce05_materie_prime" },
    { label: "7) Servizi", field: "ce06_servizi" },
    { label: "8) Godimento di beni di terzi", field: "ce07_godimento_beni" },
    { label: "9) Personale", field: "ce08_costi_personale" },
    { label: "di cui per acc.to trattamento di fine rapporto, di quiescenza e simili", field: "ce08a_tfr_accrual", indent: 1 },
    { label: "10) Ammortamenti e svalutazioni:" },
    { label: "a) Ammortamento delle immobilizzazioni immateriali", field: "ce09a_ammort_immateriali", indent: 1 },
    { label: "b) Ammortamento delle immobilizzazioni materiali", field: "ce09b_ammort_materiali", indent: 1 },
    { label: "c) Altre svalutazioni delle immobilizzazioni", field: "ce09c_svalutazioni", indent: 1 },
    { label: "d) Sval. dei crediti compresi nell'attivo circ. e delle disp. liquide", field: "ce09d_svalutazione_crediti", indent: 1 },
    { label: "Totale ammortamenti e svalutazioni", field: "ce09_ammortamenti", indent: 1 },
    { label: "11) Variazioni delle rim. di materie prime, sussidiarie, di cons. e merci", field: "ce10_var_rimanenze_mat_prime" },
    { label: "12) Accantonamenti per rischi", field: "ce11_accantonamenti" },
    { label: "13) Altri accantonamenti", field: "ce11b_altri_accantonamenti" },
    { label: "14) Oneri diversi di gestione", field: "ce12_oneri_diversi" },
    { label: "Totale Costi della Produzione", field: "production_cost", isSubtotal: true },
    // EBITDA
    { label: "EBITDA (MOL)", field: "ebitda", isSubtotal: true },
    // EBIT
    { label: "EBIT (Risultato Operativo)", field: "ebit", isSubtotal: true },
    // C) PROVENTI E ONERI FINANZIARI
    { label: "C) PROVENTI E ONERI FINANZIARI", isTotal: true },
    { label: "15) Proventi da partecipazioni", field: "ce13_proventi_partecipazioni" },
    { label: "16) Altri proventi finanziari", field: "ce14_altri_proventi_finanziari" },
    { label: "17) Interessi e altri oneri finanziari", field: "ce15_oneri_finanziari" },
    { label: "17-bis) Utili e perdite su cambi", field: "ce16_utili_perdite_cambi" },
    { label: "Totale Proventi/Oneri Finanziari", field: "financial_result", isSubtotal: true },
    // D) RETTIFICHE DI VALORE
    { label: "D) RETTIFICHE DI VALORE ATTIVIT\u00c0 FINANZIARIE", isTotal: true },
    { label: "18-19) Rettifiche di valore", field: "ce17_rettifiche_attivita_fin" },
    // E) PROVENTI E ONERI STRAORDINARI
    { label: "E) PROVENTI E ONERI STRAORDINARI", isTotal: true },
    { label: "20) Proventi straordinari", field: "ce18_proventi_straordinari" },
    { label: "21) Oneri straordinari", field: "ce19_oneri_straordinari" },
    { label: "Totale Proventi/Oneri Straordinari", field: "extraordinary_result", isSubtotal: true },
    // RISULTATO PRIMA DELLE IMPOSTE
    { label: "Risultato prima delle imposte", field: "profit_before_tax", isSubtotal: true },
    // IMPOSTE
    { label: "22) Imposte sul reddito", field: "ce20_imposte" },
    // UTILE/PERDITA
    { label: "23) UTILE (PERDITA) DELL'ESERCIZIO", field: "net_profit", isTotal: true },
  ];

  return (
    <Table>
      <TableHeader>
        <TableRow className="bg-muted">
          <TableHead className="px-4 py-3 text-left text-xs font-bold text-foreground uppercase border-r border-border">
            Descrizione
          </TableHead>
          {historicalYears.map((yd) => (
            <TableHead
              key={yd.year}
              className="px-4 py-3 text-center text-xs font-bold text-foreground uppercase border-r border-border"
            >
              {yd.year}
              <div className="text-muted-foreground font-normal">(Storico)</div>
            </TableHead>
          ))}
          {forecastYears.map((yd) => (
            <TableHead
              key={yd.year}
              className="px-4 py-3 text-center text-xs font-bold text-primary uppercase border-r border-border bg-primary/10"
            >
              {yd.year}
              <div className="text-primary font-normal">(Previsionale)</div>
            </TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row, index) => {
          const histValues = row.field
            ? historicalYears.map((yd) => getVal(yd, row.field!))
            : [];
          const fcValues = row.field
            ? forecastYears.map((yd) => getVal(yd, row.field!))
            : [];

          return (
            <TableRow
              key={index}
              className={cn(
                row.isTotal
                  ? "bg-muted font-bold hover:bg-muted"
                  : row.isSubtotal
                  ? "bg-primary/10 font-semibold hover:bg-primary/10"
                  : "hover:bg-muted/50"
              )}
            >
              <TableCell
                className="px-4 py-2 text-sm text-foreground border-r border-border"
                style={{ paddingLeft: row.indent ? `${1 + row.indent * 1.5}rem` : undefined }}
              >
                {row.label}
              </TableCell>
              {/* Historical columns */}
              {histValues.map((value, i) => (
                <TableCell
                  key={`hist-${i}`}
                  className={cn(
                    "px-4 py-2 text-sm text-right border-r border-border",
                    value < 0 ? "text-destructive" : "text-foreground",
                    (row.isTotal || row.isSubtotal) && "font-semibold"
                  )}
                >
                  {row.isTotal && !value ? "" : formatCurrency(value)}
                </TableCell>
              ))}
              {/* Forecast columns */}
              {fcValues.map((value, i) => (
                <TableCell
                  key={`forecast-${i}`}
                  className={cn(
                    "px-4 py-2 text-sm text-right border-r border-border",
                    value < 0 ? "text-destructive" : "text-foreground",
                    (row.isTotal || row.isSubtotal) && "font-semibold"
                  )}
                >
                  {row.isTotal && !value ? "" : formatCurrency(value)}
                </TableCell>
              ))}
              {/* Empty cells for section headers without field */}
              {!row.field && historicalYears.map((yd) => (
                <TableCell key={`hist-empty-${yd.year}`} className="px-4 py-2 text-sm text-right border-r border-border" />
              ))}
              {!row.field && forecastYears.map((yd) => (
                <TableCell key={`fc-empty-${yd.year}`} className="px-4 py-2 text-sm text-right border-r border-border" />
              ))}
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
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
  forecastYears: YearData[],
  metrics: string[]
): any[] {
  const allYears = [...historicalYears, ...forecastYears];
  return allYears.map((yd) => ({
    year: yd.year.toString(),
    revenue: yd.income_statement.revenue || 0,
    ebitda: yd.income_statement.ebitda || 0,
    ebit: yd.income_statement.ebit || 0,
    net_profit: yd.income_statement.net_profit || 0,
  }));
}
