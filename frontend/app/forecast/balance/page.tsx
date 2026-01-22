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
  Tooltip,
  Legend,
  ResponsiveContainer,
  ComposedChart,
  Area,
} from "recharts";

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
          Stato Patrimoniale Previsionale
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
        Stato Patrimoniale Previsionale
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
          {/* Balance Sheet Table */}
          <div className="bg-white shadow rounded-lg p-6 mb-6">
            <h2 className="text-xl font-semibold text-gray-900 mb-4">
              Stato Patrimoniale: Confronto Storico vs Previsionale
            </h2>

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
          </div>

          {/* Charts */}
          {Object.keys(forecastData).length > 0 && (
            <>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
                {/* Assets Composition Chart */}
                <div className="bg-white shadow rounded-lg p-6">
                  <h3 className="text-lg font-semibold text-gray-900 mb-4">
                    Composizione Attivo
                  </h3>
                  <ResponsiveContainer width="100%" height={300}>
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
                      <Tooltip formatter={(value: number) => formatCurrency(value)} />
                      <Legend />
                      <Area
                        type="monotone"
                        dataKey="fixed_assets"
                        fill="#f59e0b"
                        stroke="#f59e0b"
                        name="Immobilizzazioni"
                      />
                      <Area
                        type="monotone"
                        dataKey="current_assets"
                        fill="#3b82f6"
                        stroke="#3b82f6"
                        name="Attivo Circolante"
                      />
                      <Line
                        type="monotone"
                        dataKey="total_assets"
                        stroke="#ef4444"
                        strokeWidth={2}
                        name="Totale Attivo"
                      />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>

                {/* Equity vs Debt Chart */}
                <div className="bg-white shadow rounded-lg p-6">
                  <h3 className="text-lg font-semibold text-gray-900 mb-4">
                    Patrimonio Netto vs Debiti
                  </h3>
                  <ResponsiveContainer width="100%" height={300}>
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
                      <Tooltip formatter={(value: number) => formatCurrency(value)} />
                      <Legend />
                      <Bar dataKey="total_equity" fill="#10b981" name="Patrimonio Netto" />
                      <Bar dataKey="total_debt" fill="#ef4444" name="Debiti Totali" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>

              {/* Working Capital Chart */}
              <div className="bg-white shadow rounded-lg p-6 mb-6">
                <h3 className="text-lg font-semibold text-gray-900 mb-4">
                  Capitale Circolante Netto (CCN)
                </h3>
                <ResponsiveContainer width="100%" height={300}>
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
                    <Tooltip formatter={(value: number) => formatCurrency(value)} />
                    <Legend />
                    <Line
                      type="monotone"
                      dataKey="working_capital_net"
                      stroke="#8b5cf6"
                      strokeWidth={2}
                      name="CCN"
                    />
                  </LineChart>
                </ResponsiveContainer>
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

                    const debtToEquity = forecast.total_equity !== 0
                      ? forecast.total_debt / forecast.total_equity
                      : 0;

                    return (
                      <div key={year} className="border border-gray-200 rounded-lg p-4">
                        <h4 className="font-semibold text-gray-700 mb-3 text-center">
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
              </div>
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
    <div className="mb-4 bg-yellow-50 border border-yellow-200 rounded p-4">
      <div className="flex items-start">
        <div className="flex-shrink-0">
          <svg
            className="h-5 w-5 text-yellow-400"
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 20 20"
            fill="currentColor"
          >
            <path
              fillRule="evenodd"
              d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
              clipRule="evenodd"
            />
          </svg>
        </div>
        <div className="ml-3 flex-1">
          <h3 className="text-sm font-medium text-yellow-800">
            Sbilancio Rilevato
          </h3>
          <div className="mt-2 text-sm text-yellow-700">
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
          </div>
        </div>
      </div>
    </div>
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
      label: "III - Attività finanziarie che non costituiscono immobilizzazioni",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "sp08_attivita_finanziarie")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.sp08_attivita_finanziarie || 0),
      indent: true,
    },
    {
      label: "IV - Disponibilità liquide",
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
      label: "IV-VII - Riserve",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "sp12_riserve")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.sp12_riserve || 0),
      indent: true,
    },
    {
      label: "IX - Utile (perdita) dell'esercizio",
      historicalValues: historicalYears.map((y) => getHistoricalValue(y, "sp13_utile_perdita")),
      forecastValues: forecastYears.map((y) => forecastData[y]?.sp13_utile_perdita || 0),
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
              <td className={`px-4 py-2 text-sm text-gray-900 border-r border-gray-200 ${row.indent ? 'pl-8' : ''}`}>
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
