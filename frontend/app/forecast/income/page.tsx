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
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

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
        <div className="bg-yellow-50 border border-yellow-200 text-yellow-700 px-4 py-3 rounded">
          Seleziona un&apos;azienda per visualizzare i previsionali
        </div>
      </div>
    );
  }

  if (scenarios.length === 0 && !loading) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <h1 className="text-2xl font-bold text-gray-900 mb-4">
          Conto Economico Previsionale
        </h1>
        <div className="bg-blue-50 border border-blue-200 text-blue-700 px-4 py-3 rounded">
          Nessuno scenario budget trovato. Vai alla tab &quot;Input Ipotesi&quot; per creare uno scenario.
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <h1 className="text-2xl font-bold text-gray-900 mb-4">
        Conto Economico Previsionale
      </h1>

      {/* Scenario Selector */}
      <div className="bg-white shadow rounded-lg p-4 mb-6">
        <label className="block text-sm font-medium text-gray-700 mb-2">
          Scenario Budget:
        </label>
        <select
          value={selectedScenario?.id || ""}
          onChange={(e) => {
            const scenario = scenarios.find((s) => s.id === Number(e.target.value));
            setSelectedScenario(scenario || null);
          }}
          className="w-full md:w-96 px-3 py-2 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          {scenarios.map((scenario) => (
            <option key={scenario.id} value={scenario.id}>
              {scenario.name} - Anno Base: {scenario.base_year}
              {scenario.is_active ? " (Attivo)" : ""}
            </option>
          ))}
        </select>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded mb-6">
          {error}
        </div>
      )}

      {loading && (
        <div className="text-center py-12">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
          <p className="mt-4 text-gray-600">Caricamento...</p>
        </div>
      )}

      {!loading && selectedScenario && historicalYears.length > 0 && (
        <>
          {/* Income Statement Table */}
          <div className="bg-white shadow rounded-lg p-6 mb-6">
            <h2 className="text-xl font-semibold text-gray-900 mb-4">
              Conto Economico: Confronto Storico vs Previsionale
            </h2>
            <div className="overflow-x-auto">
              <IncomeStatementTable
                historicalYears={historicalYears}
                historicalData={historicalData}
                forecastYears={forecastYears}
                forecastData={forecastData}
              />
            </div>
          </div>

          {/* Charts */}
          {Object.keys(forecastData).length > 0 && (
            <>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
                {/* Revenue & EBITDA Chart */}
                <div className="bg-white shadow rounded-lg p-6">
                  <h3 className="text-lg font-semibold text-gray-900 mb-4">
                    Ricavi ed EBITDA
                  </h3>
                  <ResponsiveContainer width="100%" height={300}>
                    <LineChart
                      data={prepareChartData(
                        historicalYears,
                        historicalData,
                        forecastYears,
                        forecastData,
                        ["revenue", "ebitda"]
                      )}
                    >
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="year" />
                      <YAxis />
                      <Tooltip formatter={(value: number) => formatCurrency(value)} />
                      <Legend />
                      <Line
                        type="monotone"
                        dataKey="revenue"
                        stroke="#3b82f6"
                        name="Ricavi"
                        strokeWidth={2}
                      />
                      <Line
                        type="monotone"
                        dataKey="ebitda"
                        stroke="#10b981"
                        name="EBITDA"
                        strokeWidth={2}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>

                {/* Net Profit Chart */}
                <div className="bg-white shadow rounded-lg p-6">
                  <h3 className="text-lg font-semibold text-gray-900 mb-4">
                    EBIT e Utile Netto
                  </h3>
                  <ResponsiveContainer width="100%" height={300}>
                    <BarChart
                      data={prepareChartData(
                        historicalYears,
                        historicalData,
                        forecastYears,
                        forecastData,
                        ["ebit", "net_profit"]
                      )}
                    >
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="year" />
                      <YAxis />
                      <Tooltip formatter={(value: number) => formatCurrency(value)} />
                      <Legend />
                      <Bar dataKey="ebit" fill="#f59e0b" name="EBIT" />
                      <Bar dataKey="net_profit" fill="#8b5cf6" name="Utile Netto" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>

              {/* Key Metrics Summary */}
              <div className="bg-white shadow rounded-lg p-6">
                <h3 className="text-lg font-semibold text-gray-900 mb-4">
                  Riepilogo Indicatori Chiave
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                  {forecastYears.map((year) => {
                    const forecast = forecastData[year];
                    if (!forecast) return null;

                    return (
                      <div key={year} className="border border-gray-200 rounded-lg p-4">
                        <h4 className="font-semibold text-gray-700 mb-3 text-center">
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
                      </div>
                    );
                  })}
                </div>
              </div>
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
      label: "2) Variazioni delle rimanenze di prodotti",
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
      label: "6) Materie prime, sussidiarie, di consumo e merci",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "ce05_materie_prime")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.ce05_materie_prime || 0),
    },
    {
      label: "7) Servizi",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "ce06_servizi")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.ce06_servizi || 0),
    },
    {
      label: "8) Godimento beni di terzi",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "ce07_godimento_beni")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.ce07_godimento_beni || 0),
    },
    {
      label: "9) Personale",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "ce08_costi_personale")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.ce08_costi_personale || 0),
    },
    {
      label: "10) Ammortamenti e svalutazioni",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "ce09_ammortamenti")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.ce09_ammortamenti || 0),
    },
    {
      label: "11) Variazioni rimanenze materie prime",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "ce10_var_rimanenze_mat_prime")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.ce10_var_rimanenze_mat_prime || 0),
    },
    {
      label: "12) Accantonamenti per rischi",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "ce11_accantonamenti")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.ce11_accantonamenti || 0),
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
      label: "D) RETTIFICHE DI VALORE ATTIVITÀ FINANZIARIE",
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
    <table className="min-w-full divide-y divide-gray-200 border border-gray-300">
      <thead className="bg-gray-100">
        <tr>
          <th className="px-4 py-3 text-left text-xs font-bold text-gray-900 uppercase border-r border-gray-300">
            Descrizione
          </th>
          {historicalYears.map((year) => (
            <th
              key={year}
              className="px-4 py-3 text-center text-xs font-bold text-gray-900 uppercase border-r border-gray-300"
            >
              {year}
              <div className="text-gray-600 font-normal">(Storico)</div>
            </th>
          ))}
          {forecastYears.map((year) => (
            <th
              key={year}
              className="px-4 py-3 text-center text-xs font-bold text-cyan-700 uppercase border-r border-gray-300 bg-cyan-50"
            >
              {year}
              <div className="text-cyan-600 font-normal">(Previsionale)</div>
            </th>
          ))}
        </tr>
      </thead>
      <tbody className="bg-white divide-y divide-gray-200">
        {rows.map((row, index) => {
          const bgClass = row.isTotal
            ? "bg-gray-200 font-bold"
            : row.isSubtotal
            ? "bg-blue-50 font-semibold"
            : "hover:bg-gray-50";

          return (
            <tr key={index} className={bgClass}>
              <td className="px-4 py-2 text-sm text-gray-900 border-r border-gray-200">
                {row.label}
              </td>
              {/* Historical columns */}
              {row.historicalValues.map((value, i) => {
                const isNegative = value < 0;
                return (
                  <td
                    key={`hist-${i}`}
                    className={`px-4 py-2 text-sm text-right border-r border-gray-200 ${
                      isNegative ? "text-red-600" : "text-gray-900"
                    } ${row.isTotal || row.isSubtotal ? "font-semibold" : ""}`}
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
                    className={`px-4 py-2 text-sm text-right border-r border-gray-200 ${
                      forecastNegative ? "text-red-600" : "text-gray-900"
                    } ${row.isTotal || row.isSubtotal ? "font-semibold" : ""}`}
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
      <span className="text-gray-600">{label}:</span>
      <span className="font-semibold text-gray-900">{value}</span>
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
