"use client";

import { useState, useEffect } from "react";
import { useApp } from "@/contexts/AppContext";
import {
  getBudgetScenarios,
  getForecastReclassifiedData,
} from "@/lib/api";
import { formatCurrency, formatPercentage } from "@/lib/formatters";
import type { BudgetScenario } from "@/types/api";
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

interface ReclassifiedYearData {
  year: number;
  type: "historical" | "forecast";
  income_statement: {
    revenue: number;
    production_value: number;
    production_cost: number;
    ebitda: number;
    ebit: number;
    financial_result: number;
    extraordinary_result: number;
    profit_before_tax: number;
    net_profit: number;
  };
  balance_sheet: {
    total_assets: number;
    fixed_assets: number;
    current_assets: number;
    total_equity: number;
    total_debt: number;
    current_liabilities: number;
    long_term_debt: number;
    working_capital: number;
  };
  ratios: {
    current_ratio: number;
    quick_ratio: number;
    roe: number;
    roi: number;
    ros: number;
    ebitda_margin: number;
    ebit_margin: number;
    net_margin: number;
    debt_to_equity: number;
    autonomy_index: number;
  };
}

interface ReclassifiedData {
  scenario: {
    id: number;
    name: string;
    base_year: number;
    projection_years: number;
  };
  years: number[];
  historical_data: ReclassifiedYearData[];
  forecast_data: ReclassifiedYearData[];
}

export default function ForecastReclassifiedPage() {
  const { selectedCompanyId } = useApp();
  const [scenarios, setScenarios] = useState<BudgetScenario[]>([]);
  const [selectedScenario, setSelectedScenario] = useState<BudgetScenario | null>(null);
  const [reclassifiedData, setReclassifiedData] = useState<ReclassifiedData | null>(null);
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

  // Load reclassified data when scenario changes
  useEffect(() => {
    if (!selectedScenario || !selectedCompanyId) {
      setReclassifiedData(null);
      return;
    }
    loadReclassifiedData();
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

  const loadReclassifiedData = async () => {
    if (!selectedScenario || !selectedCompanyId) return;

    try {
      setLoading(true);
      setError(null);

      const data = await getForecastReclassifiedData(
        selectedCompanyId,
        selectedScenario.id
      );
      setReclassifiedData(data);
    } catch (err) {
      console.error("Error loading reclassified data:", err);
      setError("Impossibile caricare i dati riclassificati");
    } finally {
      setLoading(false);
    }
  };

  // Prepare chart data by combining historical and forecast
  const prepareChartData = () => {
    if (!reclassifiedData) return [];

    const allData = [
      ...reclassifiedData.historical_data,
      ...reclassifiedData.forecast_data,
    ];

    return allData.map((yearData) => ({
      year: yearData.year.toString(),
      type: yearData.type,
      // Income Statement
      revenue: yearData.income_statement.revenue,
      ebitda: yearData.income_statement.ebitda,
      ebit: yearData.income_statement.ebit,
      net_profit: yearData.income_statement.net_profit,
      // Balance Sheet
      total_assets: yearData.balance_sheet.total_assets,
      total_equity: yearData.balance_sheet.total_equity,
      total_debt: yearData.balance_sheet.total_debt,
      working_capital: yearData.balance_sheet.working_capital,
      // Ratios
      current_ratio: yearData.ratios.current_ratio,
      roe: yearData.ratios.roe * 100, // Convert to percentage
      roi: yearData.ratios.roi * 100,
      ebitda_margin: yearData.ratios.ebitda_margin * 100,
      debt_to_equity: yearData.ratios.debt_to_equity,
    }));
  };

  const chartData = prepareChartData();

  if (loading && !reclassifiedData) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="flex items-center justify-center h-64">
          <div className="text-lg text-gray-600">Caricamento...</div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <p className="text-red-800">{error}</p>
        </div>
      </div>
    );
  }

  if (!selectedCompanyId) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
          <p className="text-yellow-800">Seleziona un&apos;azienda per visualizzare i dati previsionali</p>
        </div>
      </div>
    );
  }

  if (scenarios.length === 0) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
          <p className="text-yellow-800">
            Nessuno scenario disponibile. Crea uno scenario nella pagina &quot;Input Ipotesi&quot;.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900 mb-2">
          📋 Previsionale Riclassificato
        </h1>
        <p className="text-gray-600">
          Analisi degli indicatori finanziari previsionali con confronto storico
        </p>
      </div>

      {/* Scenario Selector */}
      <div className="bg-white shadow rounded-lg p-6 mb-6">
        <div className="flex items-center gap-4">
          <label className="text-sm font-medium text-gray-700">
            Scenario:
          </label>
          <select
            className="flex-1 max-w-md rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
            value={selectedScenario?.id || ""}
            onChange={(e) => {
              const scenario = scenarios.find(
                (s) => s.id === parseInt(e.target.value)
              );
              setSelectedScenario(scenario || null);
            }}
          >
            {scenarios.map((scenario) => (
              <option key={scenario.id} value={scenario.id}>
                {scenario.name}
                {scenario.is_active === 1 && " (Attivo)"}
              </option>
            ))}
          </select>
        </div>

        {selectedScenario && reclassifiedData && (
          <div className="mt-4 grid grid-cols-3 gap-4 text-sm">
            <div>
              <span className="text-gray-600">Anno Base:</span>
              <span className="ml-2 font-semibold">
                {reclassifiedData.scenario.base_year}
              </span>
            </div>
            <div>
              <span className="text-gray-600">Anni Previsionali:</span>
              <span className="ml-2 font-semibold">
                {reclassifiedData.scenario.projection_years}
              </span>
            </div>
            <div>
              <span className="text-gray-600">Totale Anni:</span>
              <span className="ml-2 font-semibold">
                {reclassifiedData.years.length}
              </span>
            </div>
          </div>
        )}
      </div>

      {!reclassifiedData ? (
        <div className="bg-white shadow rounded-lg p-6">
          <p className="text-gray-600">Seleziona uno scenario per visualizzare i dati</p>
        </div>
      ) : (
        <div className="space-y-6">
          {/* Income Statement Reclassified */}
          <div className="bg-white shadow rounded-lg p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">
              📊 Conto Economico Riclassificato
            </h2>

            {/* Revenue and Profitability */}
            <div className="mb-6">
              <h3 className="text-md font-medium text-gray-700 mb-3">
                Ricavi e Redditività
              </h3>
              <ResponsiveContainer width="100%" height={300}>
                <ComposedChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="year" />
                  <YAxis
                    yAxisId="left"
                    label={{ value: "€", angle: -90, position: "insideLeft" }}
                  />
                  <Tooltip
                    formatter={(value: any) => formatCurrency(value)}
                    labelFormatter={(label) => `Anno ${label}`}
                  />
                  <Legend />
                  <Bar
                    yAxisId="left"
                    dataKey="revenue"
                    name="Ricavi"
                    fill="#3b82f6"
                    fillOpacity={0.8}
                  />
                  <Line
                    yAxisId="left"
                    type="monotone"
                    dataKey="ebitda"
                    name="EBITDA"
                    stroke="#10b981"
                    strokeWidth={2}
                    dot={{ r: 4 }}
                  />
                  <Line
                    yAxisId="left"
                    type="monotone"
                    dataKey="ebit"
                    name="EBIT"
                    stroke="#f59e0b"
                    strokeWidth={2}
                    dot={{ r: 4 }}
                  />
                  <Line
                    yAxisId="left"
                    type="monotone"
                    dataKey="net_profit"
                    name="Utile Netto"
                    stroke="#8b5cf6"
                    strokeWidth={2}
                    dot={{ r: 4 }}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>

            {/* Profitability Margins */}
            <div>
              <h3 className="text-md font-medium text-gray-700 mb-3">
                Margini di Redditività (%)
              </h3>
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="year" />
                  <YAxis
                    label={{ value: "%", angle: -90, position: "insideLeft" }}
                  />
                  <Tooltip
                    formatter={(value: any) => `${value.toFixed(2)}%`}
                    labelFormatter={(label) => `Anno ${label}`}
                  />
                  <Legend />
                  <Line
                    type="monotone"
                    dataKey="ebitda_margin"
                    name="Margine EBITDA"
                    stroke="#10b981"
                    strokeWidth={2}
                    dot={{ r: 4 }}
                  />
                  <Line
                    type="monotone"
                    dataKey="roe"
                    name="ROE"
                    stroke="#3b82f6"
                    strokeWidth={2}
                    dot={{ r: 4 }}
                  />
                  <Line
                    type="monotone"
                    dataKey="roi"
                    name="ROI"
                    stroke="#f59e0b"
                    strokeWidth={2}
                    dot={{ r: 4 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Balance Sheet Reclassified */}
          <div className="bg-white shadow rounded-lg p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">
              💰 Stato Patrimoniale Riclassificato
            </h2>

            {/* Assets, Equity, Debt */}
            <div className="mb-6">
              <h3 className="text-md font-medium text-gray-700 mb-3">
                Struttura Patrimoniale
              </h3>
              <ResponsiveContainer width="100%" height={300}>
                <ComposedChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="year" />
                  <YAxis
                    label={{ value: "€", angle: -90, position: "insideLeft" }}
                  />
                  <Tooltip
                    formatter={(value: any) => formatCurrency(value)}
                    labelFormatter={(label) => `Anno ${label}`}
                  />
                  <Legend />
                  <Area
                    type="monotone"
                    dataKey="total_assets"
                    name="Totale Attivo"
                    fill="#3b82f6"
                    fillOpacity={0.3}
                    stroke="#3b82f6"
                    strokeWidth={2}
                  />
                  <Bar
                    dataKey="total_equity"
                    name="Patrimonio Netto"
                    fill="#10b981"
                    fillOpacity={0.8}
                  />
                  <Bar
                    dataKey="total_debt"
                    name="Debiti Totali"
                    fill="#ef4444"
                    fillOpacity={0.8}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>

            {/* Working Capital and Liquidity */}
            <div>
              <h3 className="text-md font-medium text-gray-700 mb-3">
                Capitale Circolante e Liquidità
              </h3>
              <ResponsiveContainer width="100%" height={300}>
                <ComposedChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="year" />
                  <YAxis
                    yAxisId="left"
                    label={{ value: "€", angle: -90, position: "insideLeft" }}
                  />
                  <YAxis
                    yAxisId="right"
                    orientation="right"
                    label={{ value: "Ratio", angle: 90, position: "insideRight" }}
                  />
                  <Tooltip
                    formatter={(value: any, name: any) =>
                      name === "Indice Liquidità Corrente"
                        ? value.toFixed(2)
                        : formatCurrency(value)
                    }
                    labelFormatter={(label) => `Anno ${label}`}
                  />
                  <Legend />
                  <Bar
                    yAxisId="left"
                    dataKey="working_capital"
                    name="Capitale Circolante Netto"
                    fill="#3b82f6"
                    fillOpacity={0.8}
                  />
                  <Line
                    yAxisId="right"
                    type="monotone"
                    dataKey="current_ratio"
                    name="Indice Liquidità Corrente"
                    stroke="#10b981"
                    strokeWidth={2}
                    dot={{ r: 4 }}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Solvency Ratios */}
          <div className="bg-white shadow rounded-lg p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">
              📈 Indici di Solvibilità
            </h2>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="year" />
                <YAxis />
                <Tooltip
                  formatter={(value: any) => value.toFixed(2)}
                  labelFormatter={(label) => `Anno ${label}`}
                />
                <Legend />
                <Line
                  type="monotone"
                  dataKey="debt_to_equity"
                  name="Debt-to-Equity"
                  stroke="#ef4444"
                  strokeWidth={2}
                  dot={{ r: 4 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* Data Table Summary */}
          <div className="bg-white shadow rounded-lg p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">
              📋 Riepilogo Dati
            </h2>
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      Anno
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      Tipo
                    </th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                      Ricavi
                    </th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                      EBITDA
                    </th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                      EBIT
                    </th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                      Utile Netto
                    </th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                      Totale Attivo
                    </th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                      CCN
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {[...reclassifiedData.historical_data, ...reclassifiedData.forecast_data].map(
                    (yearData) => (
                      <tr
                        key={yearData.year}
                        className={
                          yearData.type === "forecast"
                            ? "bg-blue-50"
                            : ""
                        }
                      >
                        <td className="px-4 py-3 whitespace-nowrap text-sm font-medium text-gray-900">
                          {yearData.year}
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-500">
                          {yearData.type === "historical" ? (
                            <span className="text-gray-600">Storico</span>
                          ) : (
                            <span className="text-blue-600 font-medium">Previsionale</span>
                          )}
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap text-sm text-right text-gray-900">
                          {formatCurrency(yearData.income_statement.revenue)}
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap text-sm text-right text-gray-900">
                          {formatCurrency(yearData.income_statement.ebitda)}
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap text-sm text-right text-gray-900">
                          {formatCurrency(yearData.income_statement.ebit)}
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap text-sm text-right text-gray-900">
                          {formatCurrency(yearData.income_statement.net_profit)}
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap text-sm text-right text-gray-900">
                          {formatCurrency(yearData.balance_sheet.total_assets)}
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap text-sm text-right text-gray-900">
                          {formatCurrency(yearData.balance_sheet.working_capital)}
                        </td>
                      </tr>
                    )
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
