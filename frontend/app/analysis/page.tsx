"use client";

import { useState, useEffect } from "react";
import { useApp } from "@/contexts/AppContext";
import {
  getCompleteAnalysis,
  getAllRatios,
  getAltmanZScore,
  getFGPMIRating,
} from "@/lib/api";
import { formatCurrency, formatPercentage } from "@/lib/formatters";
import type {
  FinancialAnalysis,
  AllRatios,
  AltmanResult,
  FGPMIResult,
} from "@/types/api";
import {
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  Legend,
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Cell,
} from "recharts";

export default function AnalysisPage() {
  const { selectedCompanyId, selectedYear } = useApp();
  const [analysis, setAnalysis] = useState<FinancialAnalysis | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedCompanyId || !selectedYear) {
      setAnalysis(null);
      return;
    }
    loadAnalysis();
  }, [selectedCompanyId, selectedYear]);

  const loadAnalysis = async () => {
    if (!selectedCompanyId || !selectedYear) return;

    try {
      setLoading(true);
      setError(null);

      const data = await getCompleteAnalysis(selectedCompanyId, selectedYear);
      setAnalysis(data);
    } catch (err) {
      console.error("Error loading analysis:", err);
      setError("Impossibile caricare l'analisi finanziaria");
    } finally {
      setLoading(false);
    }
  };

  // Get color for Altman classification
  const getAltmanColor = (classification: string) => {
    switch (classification) {
      case "safe":
        return "text-green-600 bg-green-50 border-green-200";
      case "gray_zone":
        return "text-yellow-600 bg-yellow-50 border-yellow-200";
      case "distress":
        return "text-red-600 bg-red-50 border-red-200";
      default:
        return "text-gray-600 bg-gray-50 border-gray-200";
    }
  };

  // Get color for FGPMI rating
  const getFGPMIColor = (ratingCode: string) => {
    if (ratingCode.startsWith("A")) {
      return "text-green-600 bg-green-50 border-green-200";
    } else if (ratingCode.startsWith("BB")) {
      return "text-yellow-600 bg-yellow-50 border-yellow-200";
    } else {
      return "text-red-600 bg-red-50 border-red-200";
    }
  };

  // Prepare radar chart data for financial ratios
  const prepareRadarData = () => {
    if (!analysis) return [];

    return [
      {
        metric: "Liquidità",
        value: Math.min(analysis.ratios.liquidity.current_ratio * 100, 200),
        fullMark: 200,
      },
      {
        metric: "Autonomia",
        value: analysis.ratios.solvency.autonomy_index * 100,
        fullMark: 100,
      },
      {
        metric: "ROE",
        value: Math.min(analysis.ratios.profitability.roe * 100 + 50, 100),
        fullMark: 100,
      },
      {
        metric: "ROI",
        value: Math.min(analysis.ratios.profitability.roi * 100 + 50, 100),
        fullMark: 100,
      },
      {
        metric: "EBITDA %",
        value: Math.min(analysis.ratios.profitability.ebitda_margin * 100 + 50, 100),
        fullMark: 100,
      },
      {
        metric: "Rotazione",
        value: Math.min(analysis.ratios.activity.asset_turnover * 100, 200),
        fullMark: 200,
      },
    ];
  };

  // Prepare data for Altman components chart
  const prepareAltmanComponentsData = () => {
    if (!analysis) return [];

    const components = analysis.altman.components;
    return [
      { name: "A (CCN/TA)", value: components.A, label: "Working Capital" },
      { name: "B (RIS/TA)", value: components.B, label: "Retained Earnings" },
      { name: "C (EBIT/TA)", value: components.C, label: "Operating Profit" },
      { name: "D (CN/TD)", value: components.D, label: "Equity/Debt" },
      ...(analysis.altman.model_type === "manufacturing"
        ? [{ name: "E (FAT/TA)", value: components.E, label: "Asset Turnover" }]
        : []),
    ];
  };

  // Prepare data for FGPMI indicators chart
  const prepareFGPMIIndicatorsData = () => {
    if (!analysis) return [];

    return Object.values(analysis.fgpmi.indicators).map((indicator) => ({
      name: indicator.code,
      points: indicator.points,
      maxPoints: indicator.max_points,
      percentage: indicator.percentage,
    }));
  };

  if (loading && !analysis) {
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
          <p className="text-yellow-800">
            Seleziona un&apos;azienda per visualizzare l&apos;analisi
          </p>
        </div>
      </div>
    );
  }

  if (!selectedYear) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
          <p className="text-yellow-800">
            Seleziona un anno per visualizzare l&apos;analisi
          </p>
        </div>
      </div>
    );
  }

  if (!analysis) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
          <p className="text-gray-600">Nessun dato disponibile</p>
        </div>
      </div>
    );
  }

  const radarData = prepareRadarData();
  const altmanComponentsData = prepareAltmanComponentsData();
  const fgpmiIndicatorsData = prepareFGPMIIndicatorsData();

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900 mb-2">
          📈 Analisi Finanziaria Completa
        </h1>
        <p className="text-gray-600">
          Indici finanziari, Altman Z-Score e Rating FGPMI per l&apos;anno{" "}
          {selectedYear}
        </p>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <div className="bg-white shadow rounded-lg p-4">
          <div className="text-sm text-gray-600 mb-1">Ricavi</div>
          <div className="text-2xl font-bold text-gray-900">
            {formatCurrency(analysis.summary.revenue)}
          </div>
        </div>
        <div className="bg-white shadow rounded-lg p-4">
          <div className="text-sm text-gray-600 mb-1">EBITDA</div>
          <div className="text-2xl font-bold text-gray-900">
            {formatCurrency(analysis.summary.ebitda)}
          </div>
          <div className="text-xs text-gray-500">
            Margine: {formatPercentage(analysis.summary.ebitda_margin)}
          </div>
        </div>
        <div className="bg-white shadow rounded-lg p-4">
          <div className="text-sm text-gray-600 mb-1">Patrimonio Netto</div>
          <div className="text-2xl font-bold text-gray-900">
            {formatCurrency(analysis.summary.total_equity)}
          </div>
        </div>
        <div className="bg-white shadow rounded-lg p-4">
          <div className="text-sm text-gray-600 mb-1">ROE</div>
          <div className="text-2xl font-bold text-gray-900">
            {formatPercentage(analysis.summary.roe)}
          </div>
        </div>
      </div>

      {/* Altman Z-Score Section */}
      <div className="bg-white shadow rounded-lg p-6 mb-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">
          🎯 Altman Z-Score - Analisi del Rischio di Insolvenza
        </h2>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Z-Score Result */}
          <div>
            <div
              className={`border-2 rounded-lg p-6 mb-4 ${getAltmanColor(
                analysis.altman.classification
              )}`}
            >
              <div className="text-sm font-medium mb-2">Z-Score</div>
              <div className="text-4xl font-bold mb-2">
                {analysis.altman.z_score.toFixed(2)}
              </div>
              <div className="text-sm font-medium mb-1">
                {analysis.altman.classification === "safe" && "✅ Zona Sicura"}
                {analysis.altman.classification === "gray_zone" &&
                  "⚠️ Zona d'Ombra"}
                {analysis.altman.classification === "distress" &&
                  "⛔ Zona di Rischio"}
              </div>
              <div className="text-sm mt-2">
                {analysis.altman.interpretation_it}
              </div>
            </div>

            <div className="text-xs text-gray-600 space-y-1">
              <div>
                <strong>Modello:</strong>{" "}
                {analysis.altman.model_type === "manufacturing"
                  ? "Industria (5 componenti)"
                  : "Servizi (4 componenti)"}
              </div>
              <div>
                <strong>Settore:</strong> {analysis.altman.sector}
              </div>
            </div>
          </div>

          {/* Altman Components Chart */}
          <div>
            <h3 className="text-md font-medium text-gray-700 mb-3">
              Componenti del Z-Score
            </h3>
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={altmanComponentsData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" />
                <YAxis />
                <Tooltip
                  formatter={(value: any) => value.toFixed(4)}
                  labelFormatter={(label) => `Componente ${label}`}
                />
                <Bar dataKey="value" fill="#3b82f6" />
              </BarChart>
            </ResponsiveContainer>
            <div className="mt-2 text-xs text-gray-600 space-y-1">
              <div>A = Capitale Circolante / Totale Attivo</div>
              <div>B = Riserve / Totale Attivo</div>
              <div>C = EBIT / Totale Attivo</div>
              <div>D = Patrimonio Netto / Debiti Totali</div>
              {analysis.altman.model_type === "manufacturing" && (
                <div>E = Fatturato / Totale Attivo</div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* FGPMI Rating Section */}
      <div className="bg-white shadow rounded-lg p-6 mb-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">
          ⭐ Rating FGPMI - Valutazione Creditizia
        </h2>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Rating Result */}
          <div>
            <div
              className={`border-2 rounded-lg p-6 mb-4 ${getFGPMIColor(
                analysis.fgpmi.rating_code
              )}`}
            >
              <div className="text-sm font-medium mb-2">Rating FGPMI</div>
              <div className="text-4xl font-bold mb-2">
                {analysis.fgpmi.rating_code}
              </div>
              <div className="text-sm font-medium mb-1">
                {analysis.fgpmi.rating_description}
              </div>
              <div className="text-sm mt-2">
                <strong>Livello Rischio:</strong> {analysis.fgpmi.risk_level}
              </div>
              <div className="text-sm mt-1">
                <strong>Punteggio:</strong> {analysis.fgpmi.total_score} /{" "}
                {analysis.fgpmi.max_score}
              </div>
              {analysis.fgpmi.revenue_bonus > 0 && (
                <div className="text-sm mt-1">
                  ✨ Bonus Fatturato: +{analysis.fgpmi.revenue_bonus} punti
                </div>
              )}
            </div>

            <div className="text-xs text-gray-600 space-y-1">
              <div>
                <strong>Modello Settoriale:</strong>{" "}
                {analysis.fgpmi.sector_model}
              </div>
              <div>
                <strong>Classe Rating:</strong> {analysis.fgpmi.rating_class}/13
              </div>
            </div>
          </div>

          {/* FGPMI Indicators Chart */}
          <div>
            <h3 className="text-md font-medium text-gray-700 mb-3">
              Indicatori FGPMI
            </h3>
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={fgpmiIndicatorsData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" />
                <YAxis />
                <Tooltip
                  formatter={(value: any, name: any) => {
                    if (name === "points") return `${value} punti`;
                    if (name === "maxPoints") return `${value} max`;
                    return `${value.toFixed(1)}%`;
                  }}
                />
                <Legend />
                <Bar dataKey="points" name="Punti" fill="#10b981" />
                <Bar dataKey="maxPoints" name="Max" fill="#e5e7eb" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* FGPMI Indicators Details */}
        <div className="mt-6 overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                  Indicatore
                </th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                  Valore
                </th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                  Punti
                </th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                  Max
                </th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                  %
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {Object.values(analysis.fgpmi.indicators).map((indicator) => (
                <tr key={indicator.code}>
                  <td className="px-4 py-3 whitespace-nowrap text-sm font-medium text-gray-900">
                    {indicator.name}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap text-sm text-right text-gray-900">
                    {indicator.value.toFixed(4)}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap text-sm text-right text-gray-900">
                    {indicator.points}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap text-sm text-right text-gray-500">
                    {indicator.max_points}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap text-sm text-right text-gray-900">
                    {indicator.percentage.toFixed(1)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Financial Ratios Overview */}
      <div className="bg-white shadow rounded-lg p-6 mb-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">
          📊 Indici Finanziari
        </h2>

        {/* Radar Chart */}
        <div className="mb-6">
          <h3 className="text-md font-medium text-gray-700 mb-3">
            Panoramica Indici Chiave
          </h3>
          <ResponsiveContainer width="100%" height={400}>
            <RadarChart data={radarData}>
              <PolarGrid />
              <PolarAngleAxis dataKey="metric" />
              <PolarRadiusAxis angle={90} domain={[0, 100]} />
              <Radar
                name="Performance"
                dataKey="value"
                stroke="#3b82f6"
                fill="#3b82f6"
                fillOpacity={0.6}
              />
              <Legend />
            </RadarChart>
          </ResponsiveContainer>
        </div>

        {/* Ratios Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {/* Liquidity Ratios */}
          <div>
            <h3 className="text-sm font-semibold text-gray-700 mb-3">
              💧 Liquidità
            </h3>
            <div className="space-y-2">
              <div className="flex justify-between">
                <span className="text-sm text-gray-600">Current Ratio:</span>
                <span className="text-sm font-medium">
                  {analysis.ratios.liquidity.current_ratio.toFixed(2)}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-gray-600">Quick Ratio:</span>
                <span className="text-sm font-medium">
                  {analysis.ratios.liquidity.quick_ratio.toFixed(2)}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-gray-600">Acid Test:</span>
                <span className="text-sm font-medium">
                  {analysis.ratios.liquidity.acid_test.toFixed(2)}
                </span>
              </div>
            </div>
          </div>

          {/* Solvency Ratios */}
          <div>
            <h3 className="text-sm font-semibold text-gray-700 mb-3">
              🏦 Solvibilità
            </h3>
            <div className="space-y-2">
              <div className="flex justify-between">
                <span className="text-sm text-gray-600">Autonomia:</span>
                <span className="text-sm font-medium">
                  {formatPercentage(analysis.ratios.solvency.autonomy_index)}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-gray-600">Debt/Equity:</span>
                <span className="text-sm font-medium">
                  {analysis.ratios.solvency.debt_to_equity.toFixed(2)}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-gray-600">Leverage:</span>
                <span className="text-sm font-medium">
                  {analysis.ratios.solvency.leverage_ratio.toFixed(2)}
                </span>
              </div>
            </div>
          </div>

          {/* Profitability Ratios */}
          <div>
            <h3 className="text-sm font-semibold text-gray-700 mb-3">
              💰 Redditività
            </h3>
            <div className="space-y-2">
              <div className="flex justify-between">
                <span className="text-sm text-gray-600">ROE:</span>
                <span className="text-sm font-medium">
                  {formatPercentage(analysis.ratios.profitability.roe)}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-gray-600">ROI:</span>
                <span className="text-sm font-medium">
                  {formatPercentage(analysis.ratios.profitability.roi)}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-gray-600">ROS:</span>
                <span className="text-sm font-medium">
                  {formatPercentage(analysis.ratios.profitability.ros)}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-gray-600">EBITDA Margin:</span>
                <span className="text-sm font-medium">
                  {formatPercentage(analysis.ratios.profitability.ebitda_margin)}
                </span>
              </div>
            </div>
          </div>

          {/* Activity Ratios */}
          <div>
            <h3 className="text-sm font-semibold text-gray-700 mb-3">
              🔄 Attività
            </h3>
            <div className="space-y-2">
              <div className="flex justify-between">
                <span className="text-sm text-gray-600">Rotazione Attivo:</span>
                <span className="text-sm font-medium">
                  {analysis.ratios.activity.asset_turnover.toFixed(2)}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-gray-600">Giorni Credito:</span>
                <span className="text-sm font-medium">
                  {analysis.ratios.activity.receivables_turnover_days.toFixed(0)}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-gray-600">Giorni Debito:</span>
                <span className="text-sm font-medium">
                  {analysis.ratios.activity.payables_turnover_days.toFixed(0)}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-gray-600">Ciclo Cassa:</span>
                <span className="text-sm font-medium">
                  {analysis.ratios.activity.cash_conversion_cycle.toFixed(0)}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Working Capital Metrics */}
      <div className="bg-white shadow rounded-lg p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">
          🔢 Capitale Circolante
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="bg-blue-50 rounded-lg p-4">
            <div className="text-sm text-blue-600 mb-1">CCLN</div>
            <div className="text-xl font-bold text-blue-900">
              {formatCurrency(analysis.ratios.working_capital.ccln)}
            </div>
          </div>
          <div className="bg-green-50 rounded-lg p-4">
            <div className="text-sm text-green-600 mb-1">CCN</div>
            <div className="text-xl font-bold text-green-900">
              {formatCurrency(analysis.ratios.working_capital.ccn)}
            </div>
          </div>
          <div className="bg-purple-50 rounded-lg p-4">
            <div className="text-sm text-purple-600 mb-1">MS</div>
            <div className="text-xl font-bold text-purple-900">
              {formatCurrency(analysis.ratios.working_capital.ms)}
            </div>
          </div>
          <div className="bg-orange-50 rounded-lg p-4">
            <div className="text-sm text-orange-600 mb-1">MT</div>
            <div className="text-xl font-bold text-orange-900">
              {formatCurrency(analysis.ratios.working_capital.mt)}
            </div>
          </div>
        </div>
        <div className="mt-4 text-xs text-gray-600 space-y-1">
          <div>CCLN = Capitale Circolante Lordo Netto (Attivo Corrente)</div>
          <div>CCN = Capitale Circolante Netto (Attivo Corrente - Passivo Corrente)</div>
          <div>MS = Margine di Struttura (Patrimonio Netto - Immobilizzazioni)</div>
          <div>MT = Margine di Tesoreria (Liquidità + Crediti - Passivo Corrente)</div>
        </div>
      </div>
    </div>
  );
}
