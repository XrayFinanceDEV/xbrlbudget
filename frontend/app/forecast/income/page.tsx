"use client";

import { useState, useEffect } from "react";
import { useApp } from "@/contexts/AppContext";
import {
  getBudgetScenarios,
  getForecastIncomeStatement,
  getIncomeStatement,
} from "@/lib/api";
import { formatCurrency, formatPercentage } from "@/lib/formatters";
import type {
  BudgetScenario,
  ForecastIncomeStatement,
  IncomeStatement,
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
  const { selectedCompanyId, years: availableYears } = useApp();
  const [scenarios, setScenarios] = useState<BudgetScenario[]>([]);
  const [selectedScenario, setSelectedScenario] = useState<BudgetScenario | null>(null);
  const [forecastYears, setForecastYears] = useState<number[]>([]);
  const [historicalYears, setHistoricalYears] = useState<number[]>([]);
  const [historicalData, setHistoricalData] = useState<Record<number, IncomeStatement>>({});
  const [forecastData, setForecastData] = useState<Record<number, ForecastIncomeStatement>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load scenarios when company changes
  useEffect(() => {
    if (!selectedCompanyId) {
      setScenarios([]);
      setSelectedScenario(null);
      return;
    }
    loadScenarios();
  }, [selectedCompanyId]);

  // Load forecast data when scenario changes
  useEffect(() => {
    if (!selectedScenario || !selectedCompanyId) {
      setForecastData({});
      setHistoricalData({});
      setHistoricalYears([]);
      return;
    }
    loadForecastData();
  }, [selectedScenario, selectedCompanyId]);

  const loadScenarios = async () => {
    if (!selectedCompanyId) return;

    try {
      setLoading(true);
      const data = await getBudgetScenarios(selectedCompanyId);
      setScenarios(data);
      // Auto-select active scenario or first one
      const activeScenario = data.find((s) => s.is_active === 1) || data[0];
      if (activeScenario) {
        setSelectedScenario(activeScenario);
      }
    } catch (err) {
      console.error("Error loading scenarios:", err);
      setError("Impossibile caricare gli scenari");
    } finally {
      setLoading(false);
    }
  };

  const loadForecastData = async () => {
    if (!selectedScenario || !selectedCompanyId) return;

    try {
      setLoading(true);
      setError(null);

      const baseYear = selectedScenario.base_year;

      // Load historical years (all years up to and including base year)
      const histYears = availableYears
        .filter((y) => y <= baseYear)
        .sort((a, b) => a - b);
      setHistoricalYears(histYears);

      // Load historical data for all years
      const historical: Record<number, IncomeStatement> = {};
      for (const year of histYears) {
        try {
          const data = await getIncomeStatement(selectedCompanyId, year);
          historical[year] = data;
        } catch (err: any) {
          console.error(`Error loading historical data for year ${year}:`, err);
        }
      }
      setHistoricalData(historical);

      // Calculate forecast years (typically 3 years after base)
      const forecastYrs = [baseYear + 1, baseYear + 2, baseYear + 3];
      setForecastYears(forecastYrs);

      // Load forecast data for each year
      const forecasts: Record<number, ForecastIncomeStatement> = {};
      for (const year of forecastYrs) {
        try {
          const forecast = await getForecastIncomeStatement(
            selectedCompanyId,
            selectedScenario.id,
            year
          );
          forecasts[year] = forecast;
        } catch (err: any) {
          if (err.response?.status !== 404) {
            console.error(`Error loading forecast for year ${year}:`, err);
          }
        }
      }
      setForecastData(forecasts);
    } catch (err: any) {
      console.error("Error loading forecast data:", err);
      setError("Impossibile caricare i dati previsionali");
    } finally {
      setLoading(false);
    }
  };

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
            Nessuno scenario budget trovato. Vai alla tab &quot;Input Ipotesi&quot; per creare uno scenario.
          </AlertDescription>
        </Alert>
      </div>
    );
  }

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

      {!loading && selectedScenario && historicalYears.length > 0 && (
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
                  historicalData={historicalData}
                  forecastYears={forecastYears}
                  forecastData={forecastData}
                />
              </div>
            </CardContent>
          </Card>

          {/* Charts */}
          {Object.keys(forecastData).length > 0 && (
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
                        data={prepareChartData(
                          historicalYears,
                          historicalData,
                          forecastYears,
                          forecastData,
                          ["revenue", "ebitda"]
                        )}
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
                        data={prepareChartData(
                          historicalYears,
                          historicalData,
                          forecastYears,
                          forecastData,
                          ["ebit", "net_profit"]
                        )}
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
                    {forecastYears.map((year) => {
                      const forecast = forecastData[year];
                      if (!forecast) return null;

                      return (
                        <Card key={year}>
                          <CardContent className="pt-6">
                            <h4 className="font-semibold text-muted-foreground mb-3 text-center">
                              {year}
                            </h4>
                            <div className="space-y-2 text-sm">
                              <MetricRow
                                label="Ricavi"
                                value={formatCurrency(forecast.revenue)}
                              />
                              <MetricRow
                                label="EBITDA"
                                value={formatCurrency(forecast.ebitda)}
                              />
                              <MetricRow
                                label="Margine EBITDA"
                                value={formatPercentage(forecast.ebitda / forecast.revenue)}
                              />
                              <MetricRow
                                label="EBIT"
                                value={formatCurrency(forecast.ebit)}
                              />
                              <MetricRow
                                label="Utile Netto"
                                value={formatCurrency(forecast.net_profit)}
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

// Income Statement Table Component
function IncomeStatementTable({
  historicalYears,
  historicalData,
  forecastYears,
  forecastData,
}: {
  historicalYears: number[];
  historicalData: Record<number, IncomeStatement>;
  forecastYears: number[];
  forecastData: Record<number, ForecastIncomeStatement>;
}) {
  // Helper function to get value from historical data
  const getHistoricalValue = (year: number, field: string, isCalculated: boolean = false): number => {
    const data = historicalData[year];
    if (!data) return 0;

    if (isCalculated) {
      // For calculated fields like production_value, ebitda, etc.
      return (data as any)[field] || 0;
    }
    // For regular string fields that need parsing
    return parseFloat((data as any)[field]) || 0;
  };

  const rows: Array<{
    label: string;
    historicalValues: number[];
    forecastValues: number[];
    isTotal?: boolean;
    isSubtotal?: boolean;
    indent?: number;
  }> = [
    // A) VALORE DELLA PRODUZIONE
    {
      label: "A) VALORE DELLA PRODUZIONE",
      historicalValues: [],
      forecastValues: [],
      isTotal: true,
    },
    {
      label: "1) Ricavi delle vendite e delle prestazioni",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "ce01_ricavi_vendite")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.ce01_ricavi_vendite || 0),
    },
    {
      label: "2) Variazioni delle rim. di prodotti in corso di lav., semilav. e finiti",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "ce02_variazioni_rimanenze")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.ce02_variazioni_rimanenze || 0),
    },
    {
      label: "3) Variazioni dei lavori in corso su ordinazione",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "ce03_lavori_interni")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.ce03_lavori_interni || 0),
    },
    {
      label: "5) Altri ricavi e proventi",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "ce04_altri_ricavi")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.ce04_altri_ricavi || 0),
    },
    {
      label: "Totale Valore della Produzione",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "production_value", true)),
      forecastValues: forecastYears.map((y) => forecastData[y]?.production_value || 0),
      isSubtotal: true,
    },
    // B) COSTI DELLA PRODUZIONE
    {
      label: "B) COSTI DELLA PRODUZIONE",
      historicalValues: [],
      forecastValues: [],
      isTotal: true,
    },
    {
      label: "6) Materie prime, sussidiarie, di consumo e di merci",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "ce05_materie_prime")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.ce05_materie_prime || 0),
    },
    {
      label: "7) Servizi",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "ce06_servizi")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.ce06_servizi || 0),
    },
    {
      label: "8) Godimento di beni di terzi",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "ce07_godimento_beni")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.ce07_godimento_beni || 0),
    },
    {
      label: "9) Personale",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "ce08_costi_personale")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.ce08_costi_personale || 0),
    },
    {
      label: "di cui per acc.to trattamento di fine rapporto, di quiescenza e simili",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "ce08a_tfr_accrual")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.ce08a_tfr_accrual || 0),
      indent: 1,
    },
    {
      label: "10) Ammortamenti e svalutazioni:",
      historicalValues: [],
      forecastValues: [],
    },
    {
      label: "a) Ammortamento delle immobilizzazioni immateriali",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "ce09a_ammort_immateriali")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.ce09a_ammort_immateriali || 0),
      indent: 1,
    },
    {
      label: "b) Ammortamento delle immobilizzazioni materiali",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "ce09b_ammort_materiali")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.ce09b_ammort_materiali || 0),
      indent: 1,
    },
    {
      label: "c) Altre svalutazioni delle immobilizzazioni",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "ce09c_svalutazioni")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.ce09c_svalutazioni || 0),
      indent: 1,
    },
    {
      label: "d) Sval. dei crediti compresi nell'attivo circ. e delle disp. liquide",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "ce09d_svalutazione_crediti")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.ce09d_svalutazione_crediti || 0),
      indent: 1,
    },
    {
      label: "Totale ammortamenti e svalutazioni",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "ce09_ammortamenti")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.ce09_ammortamenti || 0),
      indent: 1,
    },
    {
      label: "11) Variazioni delle rim. di materie prime, sussidiarie, di cons. e merci",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "ce10_var_rimanenze_mat_prime")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.ce10_var_rimanenze_mat_prime || 0),
    },
    {
      label: "12) Accantonamenti per rischi",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "ce11_accantonamenti")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.ce11_accantonamenti || 0),
    },
    {
      label: "13) Altri accantonamenti",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "ce11b_altri_accantonamenti")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.ce11b_altri_accantonamenti || 0),
    },
    {
      label: "14) Oneri diversi di gestione",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "ce12_oneri_diversi")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.ce12_oneri_diversi || 0),
    },
    {
      label: "Totale Costi della Produzione",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "production_cost", true)),
      forecastValues: forecastYears.map((y) => forecastData[y]?.production_cost || 0),
      isSubtotal: true,
    },
    // EBITDA
    {
      label: "EBITDA (MOL)",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "ebitda", true)),
      forecastValues: forecastYears.map((y) => forecastData[y]?.ebitda || 0),
      isSubtotal: true,
    },
    // EBIT
    {
      label: "EBIT (Risultato Operativo)",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "ebit", true)),
      forecastValues: forecastYears.map((y) => forecastData[y]?.ebit || 0),
      isSubtotal: true,
    },
    // C) PROVENTI E ONERI FINANZIARI
    {
      label: "C) PROVENTI E ONERI FINANZIARI",
      historicalValues: [],
      forecastValues: [],
      isTotal: true,
    },
    {
      label: "15) Proventi da partecipazioni",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "ce13_proventi_partecipazioni")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.ce13_proventi_partecipazioni || 0),
    },
    {
      label: "16) Altri proventi finanziari",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "ce14_altri_proventi_finanziari")),
      forecastValues: forecastYears.map(
        (y) => forecastData[y]?.ce14_altri_proventi_finanziari || 0
      ),
    },
    {
      label: "17) Interessi e altri oneri finanziari",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "ce15_oneri_finanziari")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.ce15_oneri_finanziari || 0),
    },
    {
      label: "17-bis) Utili e perdite su cambi",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "ce16_utili_perdite_cambi")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.ce16_utili_perdite_cambi || 0),
    },
    {
      label: "Totale Proventi/Oneri Finanziari",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "financial_result", true)),
      forecastValues: forecastYears.map((y) => forecastData[y]?.financial_result || 0),
      isSubtotal: true,
    },
    // D) RETTIFICHE DI VALORE
    {
      label: "D) RETTIFICHE DI VALORE ATTIVIT\u00c0 FINANZIARIE",
      historicalValues: [],
      forecastValues: [],
      isTotal: true,
    },
    {
      label: "18-19) Rettifiche di valore",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "ce17_rettifiche_attivita_fin")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.ce17_rettifiche_attivita_fin || 0),
    },
    // E) PROVENTI E ONERI STRAORDINARI
    {
      label: "E) PROVENTI E ONERI STRAORDINARI",
      historicalValues: [],
      forecastValues: [],
      isTotal: true,
    },
    {
      label: "20) Proventi straordinari",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "ce18_proventi_straordinari")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.ce18_proventi_straordinari || 0),
    },
    {
      label: "21) Oneri straordinari",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "ce19_oneri_straordinari")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.ce19_oneri_straordinari || 0),
    },
    {
      label: "Totale Proventi/Oneri Straordinari",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "extraordinary_result", true)),
      forecastValues: forecastYears.map((y) => forecastData[y]?.extraordinary_result || 0),
      isSubtotal: true,
    },
    // RISULTATO PRIMA DELLE IMPOSTE
    {
      label: "Risultato prima delle imposte",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "profit_before_tax", true)),
      forecastValues: forecastYears.map((y) => forecastData[y]?.profit_before_tax || 0),
      isSubtotal: true,
    },
    // IMPOSTE
    {
      label: "22) Imposte sul reddito",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "ce20_imposte")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.ce20_imposte || 0),
    },
    // UTILE/PERDITA
    {
      label: "23) UTILE (PERDITA) DELL'ESERCIZIO",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "net_profit", true)),
      forecastValues: forecastYears.map((y) => forecastData[y]?.net_profit || 0),
      isTotal: true,
    },
  ];

  return (
    <Table>
      <TableHeader>
        <TableRow className="bg-muted">
          <TableHead className="px-4 py-3 text-left text-xs font-bold text-foreground uppercase border-r border-border">
            Descrizione
          </TableHead>
          {historicalYears.map((year) => (
            <TableHead
              key={year}
              className="px-4 py-3 text-center text-xs font-bold text-foreground uppercase border-r border-border"
            >
              {year}
              <div className="text-muted-foreground font-normal">(Storico)</div>
            </TableHead>
          ))}
          {forecastYears.map((year) => (
            <TableHead
              key={year}
              className="px-4 py-3 text-center text-xs font-bold text-primary uppercase border-r border-border bg-primary/10"
            >
              {year}
              <div className="text-primary font-normal">(Previsionale)</div>
            </TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row, index) => (
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
            {row.historicalValues.map((value, i) => (
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
            {row.forecastValues.map((value, i) => (
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
          </TableRow>
        ))}
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
  historicalYears: number[],
  historicalData: Record<number, IncomeStatement>,
  forecastYears: number[],
  forecastData: Record<number, ForecastIncomeStatement>,
  metrics: string[]
): any[] {
  const data: any[] = [];

  // Add historical data
  historicalYears.forEach((year) => {
    const historical = historicalData[year];
    if (historical) {
      data.push({
        year: year.toString(),
        revenue: historical.revenue,
        ebitda: historical.ebitda,
        ebit: historical.ebit,
        net_profit: historical.net_profit,
      });
    }
  });

  // Add forecast data
  forecastYears.forEach((year) => {
    const forecast = forecastData[year];
    if (forecast) {
      data.push({
        year: year.toString(),
        revenue: forecast.revenue,
        ebitda: forecast.ebitda,
        ebit: forecast.ebit,
        net_profit: forecast.net_profit,
      });
    }
  });

  return data;
}
