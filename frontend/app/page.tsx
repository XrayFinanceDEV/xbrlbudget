"use client";

import { useState, useEffect } from "react";
import { useApp } from "@/contexts/AppContext";
import { getSummaryMetrics } from "@/lib/api";
import type { SummaryMetrics } from "@/types/api";
import { formatCurrency, formatPercentage } from "@/lib/formatters";

export default function Home() {
  const { companies, selectedCompanyId, selectedYear } = useApp();
  const [summary, setSummary] = useState<SummaryMetrics | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load summary when company and year are selected
  useEffect(() => {
    if (!selectedCompanyId || !selectedYear) {
      setSummary(null);
      return;
    }

    const loadSummary = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await getSummaryMetrics(selectedCompanyId, selectedYear);
        setSummary(data);
      } catch (err: any) {
        console.error("Error loading summary:", err);
        if (err.response?.status === 404) {
          setError(`Dati finanziari non trovati per l'anno ${selectedYear}`);
        } else {
          setError("Impossibile caricare i dati finanziari");
        }
      } finally {
        setLoading(false);
      }
    };
    loadSummary();
  }, [selectedCompanyId, selectedYear]);

  const totalCompanies = companies.length;

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Welcome Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-6">
          <h3 className="text-lg font-semibold text-blue-900 mb-2">📊 Analisi Completa</h3>
          <p className="text-sm text-blue-700">
            Importa bilanci da XBRL, calcola indici finanziari e ottieni rating creditizio automatico.
          </p>
        </div>
        <div className="bg-green-50 border border-green-200 rounded-lg p-6">
          <h3 className="text-lg font-semibold text-green-900 mb-2">⚖️ Altman Z-Score</h3>
          <p className="text-sm text-green-700">
            Valutazione del rischio di insolvenza con modelli settoriali specifici.
          </p>
        </div>
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-6">
          <h3 className="text-lg font-semibold text-yellow-900 mb-2">⭐ Rating FGPMI</h3>
          <p className="text-sm text-yellow-700">
            Rating creditizio per PMI secondo il modello Fondo di Garanzia.
          </p>
        </div>
      </div>

      {/* Statistics */}
      <div className="mb-8">
        <h2 className="text-xl font-semibold text-gray-900 mb-4">📈 Statistiche Sistema</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <MetricCard title="Aziende" value={totalCompanies.toString()} icon="🏢" />
          <MetricCard
            title="Azienda Selezionata"
            value={selectedCompanyId ? "Sì" : "No"}
            icon="✓"
          />
          <MetricCard
            title="Anno Selezionato"
            value={selectedYear ? selectedYear.toString() : "N/A"}
            icon="📆"
          />
        </div>
      </div>

      {/* Features */}
      <div className="mb-8">
        <h2 className="text-xl font-semibold text-gray-900 mb-4">✨ Funzionalità</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="bg-white shadow rounded-lg p-6">
            <h3 className="font-semibold text-gray-900 mb-3">Gestione Dati:</h3>
            <ul className="space-y-2 text-sm text-gray-700">
              <li>✅ Creazione e modifica aziende</li>
              <li>✅ Gestione multi-anno (fino a 5 anni)</li>
              <li>✅ Importazione da XBRL (formato italiano)</li>
              <li>✅ Importazione da CSV (TEBE)</li>
              <li>✅ Previsioni budget 3 anni</li>
            </ul>
          </div>
          <div className="bg-white shadow rounded-lg p-6">
            <h3 className="font-semibold text-gray-900 mb-3">Analisi Finanziaria:</h3>
            <ul className="space-y-2 text-sm text-gray-700">
              <li>✅ Indici di liquidità, solvibilità, redditività</li>
              <li>✅ Capitale circolante netto (CCN)</li>
              <li>✅ Altman Z-Score settoriale</li>
              <li>✅ Rating FGPMI (13 classi di rating)</li>
              <li>✅ Rendiconto finanziario</li>
            </ul>
          </div>
        </div>
      </div>

      {/* Divider */}
      <div className="border-t border-gray-200 my-8"></div>

      {/* Financial Summary Section */}
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

      {!loading && summary && (
        <div>
          <h2 className="text-2xl font-bold text-gray-900 mb-6">
            Dashboard - Sintesi Finanziaria {selectedYear}
          </h2>

          {/* Financial Results */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
            <MetricCard
              title="Ricavi"
              value={formatCurrency(summary.revenue)}
              icon="💰"
            />
            <MetricCard
              title="EBITDA"
              value={formatCurrency(summary.ebitda)}
              subtitle={formatPercentage(summary.ebitda_margin) + " margin"}
              icon="📈"
            />
            <MetricCard title="EBIT" value={formatCurrency(summary.ebit)} icon="📊" />
            <MetricCard
              title="Utile Netto"
              value={formatCurrency(summary.net_profit)}
              icon="✨"
            />
          </div>

          {/* Balance Sheet */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            <MetricCard
              title="Totale Attivo"
              value={formatCurrency(summary.total_assets)}
              icon="🏦"
            />
            <MetricCard
              title="Patrimonio Netto"
              value={formatCurrency(summary.total_equity)}
              icon="💎"
            />
            <MetricCard
              title="Debiti Totali"
              value={formatCurrency(summary.total_debt)}
              icon="📉"
            />
          </div>

          {/* Key Ratios */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <MetricCard
              title="Current Ratio"
              value={summary.current_ratio.toFixed(2)}
              icon="💧"
            />
            <MetricCard title="ROE" value={formatPercentage(summary.roe)} icon="📊" />
            <MetricCard title="ROI" value={formatPercentage(summary.roi)} icon="💹" />
            <MetricCard
              title="Debt/Equity"
              value={summary.debt_to_equity.toFixed(2)}
              icon="⚖️"
            />
          </div>
        </div>
      )}

      {!loading && !summary && !error && selectedCompanyId && selectedYear && (
        <div className="text-center py-12 bg-white rounded-lg shadow">
          <p className="text-gray-500">
            Nessun dato finanziario disponibile per l&apos;azienda e l&apos;anno selezionati
          </p>
        </div>
      )}
    </div>
  );
}

// Metric Card Component
function MetricCard({
  title,
  value,
  subtitle,
  icon,
}: {
  title: string;
  value: string;
  subtitle?: string;
  icon?: string;
}) {
  return (
    <div className="bg-white shadow rounded-lg p-6">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-medium text-gray-600">{title}</h3>
        {icon && <span className="text-2xl">{icon}</span>}
      </div>
      <p className="text-2xl font-bold text-gray-900">{value}</p>
      {subtitle && <p className="text-sm text-gray-500 mt-1">{subtitle}</p>}
    </div>
  );
}
