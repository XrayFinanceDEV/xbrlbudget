"use client";

import { useState, useEffect } from "react";
import { useApp } from "@/contexts/AppContext";
import {
  getBudgetScenarios,
  getForecastBalanceSheet,
  getBalanceSheet,
} from "@/lib/api";
import { formatCurrency, formatPercentage } from "@/lib/formatters";
import type {
  BudgetScenario,
  ForecastBalanceSheet,
  BalanceSheet,
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

export default function ForecastBalancePage() {
  const { selectedCompanyId, years: availableYears } = useApp();
  const [scenarios, setScenarios] = useState<BudgetScenario[]>([]);
  const [selectedScenario, setSelectedScenario] = useState<BudgetScenario | null>(null);
  const [forecastYears, setForecastYears] = useState<number[]>([]);
  const [historicalYears, setHistoricalYears] = useState<number[]>([]);
  const [historicalData, setHistoricalData] = useState<Record<number, BalanceSheet>>({});
  const [forecastData, setForecastData] = useState<Record<number, ForecastBalanceSheet>>({});
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
      const historical: Record<number, BalanceSheet> = {};
      for (const year of histYears) {
        try {
          const data = await getBalanceSheet(selectedCompanyId, year);
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
      const forecasts: Record<number, ForecastBalanceSheet> = {};
      for (const year of forecastYrs) {
        try {
          const forecast = await getForecastBalanceSheet(
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
            Nessuno scenario budget trovato. Vai alla tab &quot;Input Ipotesi&quot; per creare uno scenario.
          </AlertDescription>
        </Alert>
      </div>
    );
  }

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

      {!loading && selectedScenario && historicalYears.length > 0 && (
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
                historicalData={historicalData}
                forecastYears={forecastYears}
                forecastData={forecastData}
              />

              <div className="overflow-x-auto">
                <BalanceSheetTable
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
                {/* Assets Composition Chart */}
                <Card>
                  <CardHeader>
                    <CardTitle>Composizione Attivo</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <ChartContainer config={assetsChartConfig} className="h-[300px] w-full">
                      <ComposedChart
                        data={prepareChartData(
                          historicalYears,
                          historicalData,
                          forecastYears,
                          forecastData
                        )}
                      >
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
                      <BarChart
                        data={prepareChartData(
                          historicalYears,
                          historicalData,
                          forecastYears,
                          forecastData
                        )}
                      >
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
                    <LineChart
                      data={prepareChartData(
                        historicalYears,
                        historicalData,
                        forecastYears,
                        forecastData
                      )}
                    >
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
                    {forecastYears.map((year) => {
                      const forecast = forecastData[year];
                      if (!forecast) return null;

                      const debtToEquity = forecast.total_equity !== 0
                        ? forecast.total_debt / forecast.total_equity
                        : 0;

                      return (
                        <div key={year} className="border border-border rounded-lg p-4">
                          <h4 className="font-semibold text-muted-foreground mb-3 text-center">
                            {year}
                          </h4>
                          <div className="space-y-2 text-sm">
                            <MetricRow
                              label="Totale Attivo"
                              value={formatCurrency(forecast.total_assets)}
                            />
                            <MetricRow
                              label="Patrimonio Netto"
                              value={formatCurrency(forecast.total_equity)}
                            />
                            <MetricRow
                              label="Debiti Totali"
                              value={formatCurrency(forecast.total_debt)}
                            />
                            <MetricRow
                              label="CCN"
                              value={formatCurrency(forecast.working_capital_net)}
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
  historicalData,
  forecastYears,
  forecastData,
}: {
  historicalYears: number[];
  historicalData: Record<number, BalanceSheet>;
  forecastYears: number[];
  forecastData: Record<number, ForecastBalanceSheet>;
}) {
  const TOLERANCE = 1.0; // 1 euro tolerance (rounding errors below this are acceptable)
  const issues: Array<{ year: number; diff: number; type: 'historical' | 'forecast' }> = [];

  // Check historical years
  historicalYears.forEach((year) => {
    const data = historicalData[year];
    if (data) {
      const diff = Math.abs(data.total_assets - data.total_liabilities);
      if (diff > TOLERANCE) {
        issues.push({ year, diff, type: 'historical' });
      }
    }
  });

  // Check forecast years
  forecastYears.forEach((year) => {
    const data = forecastData[year];
    if (data) {
      const diff = Math.abs(data.total_assets - data.total_liabilities);
      if (diff > TOLERANCE) {
        issues.push({ year, diff, type: 'forecast' });
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
  historicalData,
  forecastYears,
  forecastData,
}: {
  historicalYears: number[];
  historicalData: Record<number, BalanceSheet>;
  forecastYears: number[];
  forecastData: Record<number, ForecastBalanceSheet>;
}) {
  // Helper function to get value from historical data
  const getHistoricalValue = (year: number, field: string, isCalculated: boolean = false): number => {
    const data = historicalData[year];
    if (!data) return 0;

    if (isCalculated) {
      // For calculated fields like total_assets, total_equity, etc.
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
    indent?: boolean;
  }> = [
    // ATTIVO (ASSETS)
    {
      label: "ATTIVO",
      historicalValues: [],
      forecastValues: [],
      isTotal: true,
    },
    // A) CREDITI VERSO SOCI
    {
      label: "A) Crediti verso soci per versamenti ancora dovuti",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "sp01_crediti_soci")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.sp01_crediti_soci || 0),
    },
    // B) IMMOBILIZZAZIONI
    {
      label: "B) IMMOBILIZZAZIONI",
      historicalValues: [],
      forecastValues: [],
      isSubtotal: true,
    },
    {
      label: "I - Immobilizzazioni immateriali",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "sp02_immob_immateriali")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.sp02_immob_immateriali || 0),
      indent: true,
    },
    {
      label: "II - Immobilizzazioni materiali",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "sp03_immob_materiali")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.sp03_immob_materiali || 0),
      indent: true,
    },
    {
      label: "III - Immobilizzazioni finanziarie",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "sp04_immob_finanziarie")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.sp04_immob_finanziarie || 0),
      indent: true,
    },
    {
      label: "1) Partecipazioni",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "sp04a_partecipazioni")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.sp04a_partecipazioni || 0),
      indent: true,
    },
    {
      label: "2) Crediti",
      historicalValues: [],
      forecastValues: [],
      indent: true,
    },
    {
      label: "Esigibili entro l'esercizio successivo",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "sp04b_crediti_immob_breve")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.sp04b_crediti_immob_breve || 0),
      indent: true,
    },
    {
      label: "Esigibili oltre l'esercizio successivo",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "sp04c_crediti_immob_lungo")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.sp04c_crediti_immob_lungo || 0),
      indent: true,
    },
    {
      label: "Totale crediti",
      historicalValues: historicalYears.map((y) =>
        getHistoricalValue(y, "sp04b_crediti_immob_breve") +
        getHistoricalValue(y, "sp04c_crediti_immob_lungo")
      ),
      forecastValues: forecastYears.map((y) =>
        (forecastData[y]?.sp04b_crediti_immob_breve || 0) +
        (forecastData[y]?.sp04c_crediti_immob_lungo || 0)
      ),
      indent: true,
    },
    {
      label: "3) Altri titoli",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "sp04d_altri_titoli")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.sp04d_altri_titoli || 0),
      indent: true,
    },
    {
      label: "4) Strumenti finanziari derivati attivi",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "sp04e_strumenti_derivati_attivi")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.sp04e_strumenti_derivati_attivi || 0),
      indent: true,
    },
    {
      label: "Totale immobilizzazioni finanziarie",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "sp04_immob_finanziarie")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.sp04_immob_finanziarie || 0),
      indent: true,
    },
    {
      label: "Totale Immobilizzazioni",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "fixed_assets", true)),
      forecastValues: forecastYears.map((y) => forecastData[y]?.fixed_assets || 0),
      isSubtotal: true,
    },
    // C) ATTIVO CIRCOLANTE
    {
      label: "C) ATTIVO CIRCOLANTE",
      historicalValues: [],
      forecastValues: [],
      isSubtotal: true,
    },
    {
      label: "I - Rimanenze",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "sp05_rimanenze")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.sp05_rimanenze || 0),
      indent: true,
    },
    {
      label: "II - Crediti (entro esercizio successivo)",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "sp06_crediti_breve")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.sp06_crediti_breve || 0),
      indent: true,
    },
    {
      label: "II - Crediti (oltre esercizio successivo)",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "sp07_crediti_lungo")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.sp07_crediti_lungo || 0),
      indent: true,
    },
    {
      label: "III - Attivit\u00e0 finanziarie che non costituiscono immobilizzazioni",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "sp08_attivita_finanziarie")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.sp08_attivita_finanziarie || 0),
      indent: true,
    },
    {
      label: "IV - Disponibilit\u00e0 liquide",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "sp09_disponibilita_liquide")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.sp09_disponibilita_liquide || 0),
      indent: true,
    },
    {
      label: "Totale Attivo Circolante",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "current_assets", true)),
      forecastValues: forecastYears.map((y) => forecastData[y]?.current_assets || 0),
      isSubtotal: true,
    },
    // D) RATEI E RISCONTI
    {
      label: "D) Ratei e risconti attivi",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "sp10_ratei_risconti_attivi")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.sp10_ratei_risconti_attivi || 0),
    },
    {
      label: "TOTALE ATTIVO",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "total_assets", true)),
      forecastValues: forecastYears.map((y) => forecastData[y]?.total_assets || 0),
      isTotal: true,
    },
    // PASSIVO (LIABILITIES & EQUITY)
    {
      label: "PASSIVO E PATRIMONIO NETTO",
      historicalValues: [],
      forecastValues: [],
      isTotal: true,
    },
    // A) PATRIMONIO NETTO
    {
      label: "A) PATRIMONIO NETTO",
      historicalValues: [],
      forecastValues: [],
      isSubtotal: true,
    },
    {
      label: "I - Capitale",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "sp11_capitale")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.sp11_capitale || 0),
      indent: true,
    },
    {
      label: "II - Riserva da soprapprezzo delle azioni",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "sp12a_riserva_sovrapprezzo")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.sp12a_riserva_sovrapprezzo || 0),
      indent: true,
    },
    {
      label: "III - Riserve di rivalutazione",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "sp12b_riserve_rivalutazione")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.sp12b_riserve_rivalutazione || 0),
      indent: true,
    },
    {
      label: "IV - Riserva legale",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "sp12c_riserva_legale")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.sp12c_riserva_legale || 0),
      indent: true,
    },
    {
      label: "V - Riserve statutarie",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "sp12d_riserve_statutarie")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.sp12d_riserve_statutarie || 0),
      indent: true,
    },
    {
      label: "VI - Altre riserve",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "sp12e_altre_riserve")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.sp12e_altre_riserve || 0),
      indent: true,
    },
    {
      label: "VII - Riserva per operazioni di copertura dei flussi finanziari attesi",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "sp12f_riserva_copertura_flussi")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.sp12f_riserva_copertura_flussi || 0),
      indent: true,
    },
    {
      label: "VIII - Utili (perdite) portati a nuovo",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "sp12g_utili_perdite_portati")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.sp12g_utili_perdite_portati || 0),
      indent: true,
    },
    {
      label: "IX - Utile (perdita) dell'esercizio",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "sp13_utile_perdita")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.sp13_utile_perdita || 0),
      indent: true,
    },
    {
      label: "X - Riserva negativa per azioni proprie in portafoglio",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "sp12h_riserva_neg_azioni_proprie")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.sp12h_riserva_neg_azioni_proprie || 0),
      indent: true,
    },
    {
      label: "Totale Patrimonio Netto",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "total_equity", true)),
      forecastValues: forecastYears.map((y) => forecastData[y]?.total_equity || 0),
      isSubtotal: true,
    },
    // B) FONDI PER RISCHI E ONERI
    {
      label: "B) Fondi per rischi e oneri",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "sp14_fondi_rischi")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.sp14_fondi_rischi || 0),
    },
    // C) TRATTAMENTO DI FINE RAPPORTO
    {
      label: "C) Trattamento di fine rapporto di lavoro subordinato",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "sp15_tfr")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.sp15_tfr || 0),
    },
    // D) DEBITI
    {
      label: "D) DEBITI",
      historicalValues: [],
      forecastValues: [],
      isSubtotal: true,
    },
    {
      label: "Debiti (entro esercizio successivo)",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "sp16_debiti_breve")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.sp16_debiti_breve || 0),
      indent: true,
    },
    {
      label: "Debiti (oltre esercizio successivo)",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "sp17_debiti_lungo")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.sp17_debiti_lungo || 0),
      indent: true,
    },
    {
      label: "Totale Debiti",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "total_debt", true)),
      forecastValues: forecastYears.map((y) => forecastData[y]?.total_debt || 0),
      isSubtotal: true,
    },
    // E) RATEI E RISCONTI
    {
      label: "E) Ratei e risconti passivi",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "sp18_ratei_risconti_passivi")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.sp18_ratei_risconti_passivi || 0),
    },
    {
      label: "TOTALE PASSIVO E PATRIMONIO NETTO",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "total_liabilities", true)),
      forecastValues: forecastYears.map((y) => forecastData[y]?.total_liabilities || 0),
      isTotal: true,
    },
    // Difference row to show balance check
    {
      label: "DIFFERENZA (Attivo - Passivo)",
      historicalValues: historicalYears.map((y) => {
        const data = historicalData[y];
        if (!data) return 0;
        return data.total_assets - data.total_liabilities;
      }),
      forecastValues: forecastYears.map((y) => {
        const forecast = forecastData[y];
        if (!forecast) return 0;
        return forecast.total_assets - forecast.total_liabilities;
      }),
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
          {historicalYears.map((year) => (
            <th
              key={year}
              className="px-4 py-3 text-center text-xs font-bold text-foreground uppercase border-r border-border"
            >
              {year}
              <div className="text-muted-foreground font-normal">(Storico)</div>
            </th>
          ))}
          {forecastYears.map((year) => (
            <th
              key={year}
              className="px-4 py-3 text-center text-xs font-bold text-primary uppercase border-r border-border bg-primary/10"
            >
              {year}
              <div className="text-primary font-normal">(Previsionale)</div>
            </th>
          ))}
        </tr>
      </thead>
      <tbody className="bg-card divide-y divide-border">
        {rows.map((row, index) => {
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
              {/* Historical columns */}
              {row.historicalValues.map((value, i) => {
                const isNegative = value < 0;
                return (
                  <td
                    key={`hist-${i}`}
                    className={cn(
                      "px-4 py-2 text-sm text-right border-r border-border",
                      isNegative ? "text-destructive" : "text-foreground",
                      (row.isTotal || row.isSubtotal) && "font-semibold"
                    )}
                  >
                    {row.isTotal && !value ? "" : formatCurrency(value)}
                  </td>
                );
              })}
              {/* Forecast columns */}
              {row.forecastValues.map((value, i) => {
                const forecastNegative = value < 0;
                return (
                  <td
                    key={`forecast-${i}`}
                    className={cn(
                      "px-4 py-2 text-sm text-right border-r border-border",
                      forecastNegative ? "text-destructive" : "text-foreground",
                      (row.isTotal || row.isSubtotal) && "font-semibold"
                    )}
                  >
                    {row.isTotal && !value ? "" : formatCurrency(value)}
                  </td>
                );
              })}
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
  historicalYears: number[],
  historicalData: Record<number, BalanceSheet>,
  forecastYears: number[],
  forecastData: Record<number, ForecastBalanceSheet>
): any[] {
  const data: any[] = [];

  // Add historical data
  historicalYears.forEach((year) => {
    const historical = historicalData[year];
    if (historical) {
      data.push({
        year: year.toString(),
        total_assets: historical.total_assets,
        total_equity: historical.total_equity,
        total_debt: historical.total_debt,
        fixed_assets: historical.fixed_assets,
        current_assets: historical.current_assets,
        working_capital_net: historical.working_capital_net,
      });
    }
  });

  // Add forecast data
  forecastYears.forEach((year) => {
    const forecast = forecastData[year];
    if (forecast) {
      data.push({
        year: year.toString(),
        total_assets: forecast.total_assets,
        total_equity: forecast.total_equity,
        total_debt: forecast.total_debt,
        fixed_assets: forecast.fixed_assets,
        current_assets: forecast.current_assets,
        working_capital_net: forecast.working_capital_net,
      });
    }
  });

  return data;
}
