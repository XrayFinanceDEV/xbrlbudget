"use client";

import { useState, useEffect } from "react";
import { useApp } from "@/contexts/AppContext";
import {
  getBudgetScenarios,
  createBudgetScenario,
  updateBudgetScenario,
  deleteBudgetScenario,
  getBudgetAssumptions,
  createBudgetAssumptions,
  updateBudgetAssumptions,
  generateForecast,
  getIncomeStatement,
  getBalanceSheet,
} from "@/lib/api";
import { formatCurrency } from "@/lib/formatters";
import type {
  BudgetScenario,
  BudgetScenarioCreate,
  BudgetAssumptions,
  BudgetAssumptionsCreate,
  IncomeStatement,
  BalanceSheet,
} from "@/types/api";

export default function BudgetPage() {
  const { selectedCompanyId, years } = useApp();
  const [scenarios, setScenarios] = useState<BudgetScenario[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"list" | "create">("list");
  const [editingScenario, setEditingScenario] = useState<BudgetScenario | null>(null);

  // Load scenarios
  useEffect(() => {
    if (!selectedCompanyId) {
      setScenarios([]);
      return;
    }
    loadScenarios();
  }, [selectedCompanyId]);

  const loadScenarios = async () => {
    if (!selectedCompanyId) return;

    try {
      setLoading(true);
      const data = await getBudgetScenarios(selectedCompanyId);
      setScenarios(data);
    } catch (err) {
      console.error("Error loading scenarios:", err);
      setError("Impossibile caricare gli scenari");
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteScenario = async (scenarioId: number) => {
    if (!selectedCompanyId) return;
    if (!confirm("Sei sicuro di voler eliminare questo scenario?")) return;

    try {
      await deleteBudgetScenario(selectedCompanyId, scenarioId);
      await loadScenarios();
    } catch (err) {
      console.error("Error deleting scenario:", err);
      alert("Errore durante l'eliminazione dello scenario");
    }
  };

  const handleRegenerateScenario = async (scenarioId: number) => {
    if (!selectedCompanyId) return;

    try {
      setLoading(true);
      await generateForecast(selectedCompanyId, scenarioId);
      alert("Previsionale ricalcolato con successo!");
      await loadScenarios();
    } catch (err: any) {
      console.error("Error regenerating forecast:", err);
      alert(`Errore: ${err.response?.data?.detail || "Impossibile ricalcolare il previsionale"}`);
    } finally {
      setLoading(false);
    }
  };

  const handleEditScenario = (scenario: BudgetScenario) => {
    setEditingScenario(scenario);
    setActiveTab("create");
  };

  const handleScenarioSaved = () => {
    setEditingScenario(null);
    setActiveTab("list");
    loadScenarios();
  };

  if (!selectedCompanyId) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="bg-yellow-50 border border-yellow-200 text-yellow-700 px-4 py-3 rounded">
          ⚠️ Seleziona un'azienda per gestire gli scenari di budget
        </div>
      </div>
    );
  }

  if (years.length === 0) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
          ❌ Nessun anno fiscale trovato. Importa prima i dati del bilancio.
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <h1 className="text-2xl font-bold text-gray-900 mb-4">📊 Budget & Previsionale</h1>
      <p className="text-gray-600 mb-6">Crea scenari di budget e previsionali finanziari a 3 anni</p>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded mb-6">
          {error}
        </div>
      )}

      {/* Tabs */}
      <div className="border-b border-gray-200 mb-6">
        <nav className="-mb-px flex space-x-8">
          <button
            onClick={() => {
              setActiveTab("list");
              setEditingScenario(null);
            }}
            className={`py-2 px-1 border-b-2 font-medium text-sm ${
              activeTab === "list"
                ? "border-blue-500 text-blue-600"
                : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
            }`}
          >
            📋 Scenari
          </button>
          <button
            onClick={() => setActiveTab("create")}
            className={`py-2 px-1 border-b-2 font-medium text-sm ${
              activeTab === "create"
                ? "border-blue-500 text-blue-600"
                : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
            }`}
          >
            ➕ Nuovo Scenario
          </button>
        </nav>
      </div>

      {/* Tab Content */}
      {activeTab === "list" && (
        <ScenariosList
          scenarios={scenarios}
          loading={loading}
          onEdit={handleEditScenario}
          onDelete={handleDeleteScenario}
          onRegenerate={handleRegenerateScenario}
        />
      )}

      {activeTab === "create" && (
        <ScenarioForm
          companyId={selectedCompanyId}
          years={years}
          scenario={editingScenario}
          onSaved={handleScenarioSaved}
          onCancel={() => {
            setEditingScenario(null);
            setActiveTab("list");
          }}
        />
      )}
    </div>
  );
}

// Scenarios List Component
function ScenariosList({
  scenarios,
  loading,
  onEdit,
  onDelete,
  onRegenerate,
}: {
  scenarios: BudgetScenario[];
  loading: boolean;
  onEdit: (scenario: BudgetScenario) => void;
  onDelete: (id: number) => void;
  onRegenerate: (id: number) => void;
}) {
  if (loading) {
    return (
      <div className="text-center py-12">
        <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
        <p className="mt-4 text-gray-600">Caricamento...</p>
      </div>
    );
  }

  if (scenarios.length === 0) {
    return (
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-6 text-center">
        <p className="text-gray-700">
          📝 Nessuno scenario presente. Crea il primo scenario nella tab "Nuovo Scenario"
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {scenarios.map((scenario) => (
        <div
          key={scenario.id}
          className="bg-white shadow rounded-lg p-6 border border-gray-200"
        >
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <h3 className="text-lg font-semibold text-gray-900 mb-2">
                {scenario.is_active ? "✅ " : "📦 "}
                {scenario.name}
              </h3>
              <div className="text-sm text-gray-600 space-y-1">
                <p>
                  <strong>Anno Base:</strong> {scenario.base_year}
                </p>
                {scenario.description && (
                  <p>
                    <strong>Descrizione:</strong> {scenario.description}
                  </p>
                )}
                <p>
                  <strong>Stato:</strong> {scenario.is_active ? "Attivo" : "Archiviato"}
                </p>
                <p>
                  <strong>Creato:</strong>{" "}
                  {new Date(scenario.created_at).toLocaleDateString("it-IT")}
                </p>
              </div>
            </div>
            <div className="ml-6 flex flex-col space-y-2">
              <button
                onClick={() => onEdit(scenario)}
                className="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded"
              >
                ✏️ Modifica
              </button>
              <button
                onClick={() => onRegenerate(scenario.id)}
                className="px-4 py-2 text-sm font-medium text-white bg-green-600 hover:bg-green-700 rounded"
              >
                🔄 Ricalcola
              </button>
              <button
                onClick={() => onDelete(scenario.id)}
                className="px-4 py-2 text-sm font-medium text-white bg-red-600 hover:bg-red-700 rounded"
              >
                🗑️ Elimina
              </button>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

// Scenario Form Component
function ScenarioForm({
  companyId,
  years,
  scenario,
  onSaved,
  onCancel,
}: {
  companyId: number;
  years: number[];
  scenario: BudgetScenario | null;
  onSaved: () => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState(scenario?.name || "");
  const [description, setDescription] = useState(scenario?.description || "");
  const [isActive, setIsActive] = useState(scenario?.is_active === 1);
  const [numYears, setNumYears] = useState(3);
  const [loading, setLoading] = useState(false);
  const [historicalData, setHistoricalData] = useState<
    Record<number, { income: IncomeStatement; balance: BalanceSheet }>
  >({});

  // Get base year (latest available year)
  const baseYear = Math.max(...years);
  const forecastYears = Array.from({ length: numYears }, (_, i) => baseYear + i + 1);

  // Load historical data for display
  useEffect(() => {
    const loadHistoricalData = async () => {
      const data: Record<number, { income: IncomeStatement; balance: BalanceSheet }> = {};
      for (const year of years) {
        try {
          const [income, balance] = await Promise.all([
            getIncomeStatement(companyId, year),
            getBalanceSheet(companyId, year),
          ]);
          data[year] = { income, balance };
        } catch (err) {
          console.error(`Error loading data for year ${year}:`, err);
        }
      }
      setHistoricalData(data);
    };
    loadHistoricalData();
  }, [companyId, years]);

  // Initialize assumptions with defaults or existing values
  const [assumptions, setAssumptions] = useState<Record<number, Partial<BudgetAssumptionsCreate>>>(
    {}
  );
  const [existingAssumptionYears, setExistingAssumptionYears] = useState<Set<number>>(new Set());

  useEffect(() => {
    if (scenario) {
      // Load existing assumptions
      getBudgetAssumptions(companyId, scenario.id).then((data) => {
        const assumptionsMap: Record<number, Partial<BudgetAssumptionsCreate>> = {};
        const existingYears = new Set<number>();
        data.forEach((a) => {
          existingYears.add(a.forecast_year);
          assumptionsMap[a.forecast_year] = {
            scenario_id: scenario.id,
            forecast_year: a.forecast_year,
            revenue_growth_pct: a.revenue_growth_pct,
            other_revenue_growth_pct: a.other_revenue_growth_pct,
            variable_materials_growth_pct: a.variable_materials_growth_pct,
            fixed_materials_growth_pct: a.fixed_materials_growth_pct,
            variable_services_growth_pct: a.variable_services_growth_pct,
            fixed_services_growth_pct: a.fixed_services_growth_pct,
            rent_growth_pct: a.rent_growth_pct,
            personnel_growth_pct: a.personnel_growth_pct,
            other_costs_growth_pct: a.other_costs_growth_pct,
            investments: a.investments,
            receivables_short_growth_pct: a.receivables_short_growth_pct,
            receivables_long_growth_pct: a.receivables_long_growth_pct,
            payables_short_growth_pct: a.payables_short_growth_pct,
            tax_rate: a.tax_rate,
            fixed_materials_percentage: a.fixed_materials_percentage,
            fixed_services_percentage: a.fixed_services_percentage,
            depreciation_rate: a.depreciation_rate,
            financing_amount: a.financing_amount,
            financing_duration_years: a.financing_duration_years,
            financing_interest_rate: a.financing_interest_rate,
          };
        });
        setAssumptions(assumptionsMap);
        setExistingAssumptionYears(existingYears);
        setNumYears(data.length || 3);
      });
    } else {
      // Initialize with defaults
      setExistingAssumptionYears(new Set());
      const defaultAssumptions: Record<number, Partial<BudgetAssumptionsCreate>> = {};
      forecastYears.forEach((year) => {
        defaultAssumptions[year] = {
          forecast_year: year,
          revenue_growth_pct: 0,
          other_revenue_growth_pct: 0,
          variable_materials_growth_pct: 0,
          fixed_materials_growth_pct: 0,
          variable_services_growth_pct: 0,
          fixed_services_growth_pct: 0,
          rent_growth_pct: 0,
          personnel_growth_pct: 0,
          other_costs_growth_pct: 0,
          investments: 0,
          receivables_short_growth_pct: 0,
          receivables_long_growth_pct: 0,
          payables_short_growth_pct: 0,
          tax_rate: 27.9,
          fixed_materials_percentage: 22,
          fixed_services_percentage: 22,
          depreciation_rate: 20,
          financing_amount: 0,
          financing_duration_years: 5,
          financing_interest_rate: 3,
        };
      });
      setAssumptions(defaultAssumptions);
    }
  }, [scenario, companyId]);

  const updateAssumption = (year: number, field: string, value: number) => {
    setAssumptions((prev) => ({
      ...prev,
      [year]: {
        ...prev[year],
        [field]: value,
      },
    }));
  };

  const handleSave = async () => {
    if (!name.trim()) {
      alert("Il nome dello scenario è obbligatorio!");
      return;
    }

    setLoading(true);
    try {
      let savedScenario: BudgetScenario;

      if (scenario) {
        // Update existing scenario
        savedScenario = await updateBudgetScenario(companyId, scenario.id, {
          name,
          description,
          is_active: isActive ? 1 : 0,
        });
      } else {
        // Create new scenario
        const scenarioData: BudgetScenarioCreate = {
          company_id: companyId,
          name,
          base_year: baseYear,
          description,
          is_active: isActive ? 1 : 0,
        };
        savedScenario = await createBudgetScenario(companyId, scenarioData);
      }

      // Save assumptions for each forecast year
      for (const year of forecastYears) {
        const assumptionData = assumptions[year];
        if (assumptionData) {
          // Check if assumption already exists for this year
          if (scenario && existingAssumptionYears.has(year)) {
            // Update existing assumption
            await updateBudgetAssumptions(companyId, savedScenario.id, year, assumptionData);
          } else {
            // Create new assumption
            const payload: BudgetAssumptionsCreate = {
              scenario_id: savedScenario.id,
              forecast_year: year,
              ...assumptionData,
            };
            await createBudgetAssumptions(companyId, savedScenario.id, payload);
          }
        }
      }

      // Generate forecast
      await generateForecast(companyId, savedScenario.id);

      alert("✅ Scenario salvato e previsionale calcolato con successo!");
      onSaved();
    } catch (err: any) {
      console.error("Error saving scenario:", err);
      alert(`❌ Errore: ${err.response?.data?.detail || "Impossibile salvare lo scenario"}`);
    } finally {
      setLoading(false);
    }
  };

  const historicalYears = years.sort((a, b) => a - b);

  return (
    <div className="bg-white shadow rounded-lg p-6">
      <h2 className="text-xl font-bold text-gray-900 mb-4">
        {scenario ? `✏️ Modifica Scenario: ${scenario.name}` : "➕ Nuovo Scenario Budget"}
      </h2>

      {/* Scenario Details */}
      <div className="mb-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-3">1️⃣ Informazioni Scenario</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Nome Scenario *</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="es. Budget 2025-2027"
              className="w-full px-3 py-2 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500 text-gray-900 font-medium"
            />
            <p className="text-sm text-gray-600 mt-2">
              📅 <strong>Anno Base:</strong> {baseYear} (ultimo anno disponibile)
            </p>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Descrizione</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Descrizione dello scenario..."
              rows={2}
              className="w-full px-3 py-2 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500 text-gray-900 font-medium"
            />
            <div className="mt-2">
              <label className="flex items-center">
                <input
                  type="checkbox"
                  checked={isActive}
                  onChange={(e) => setIsActive(e.target.checked)}
                  className="mr-2"
                />
                <span className="text-sm">Scenario Attivo</span>
              </label>
            </div>
          </div>
        </div>
      </div>

      <div className="border-t pt-6 mb-6">
        <label className="block text-sm font-semibold text-gray-900 mb-2">
          Numero di anni da prevedere
        </label>
        <input
          type="number"
          min={1}
          max={5}
          value={numYears}
          onChange={(e) => setNumYears(parseInt(e.target.value) || 3)}
          className="w-32 px-3 py-2 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500 text-gray-900 font-medium"
        />
      </div>

      {/* Assumptions Table */}
      <div className="mb-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-3">2️⃣ Ipotesi Previsionali</h3>
        <div className="bg-blue-50 border border-blue-200 rounded p-3 mb-4">
          <p className="text-sm text-blue-800">
            💡 Inserisci le ipotesi per ciascun anno. Le celle in blu rappresentano i valori
            modificabili.
          </p>
        </div>

        <AssumptionsTable
          historicalYears={historicalYears}
          forecastYears={forecastYears}
          historicalData={historicalData}
          assumptions={assumptions}
          onUpdate={updateAssumption}
        />
      </div>

      {/* Actions */}
      <div className="flex justify-center space-x-4 pt-6 border-t">
        {scenario && (
          <button
            onClick={onCancel}
            className="px-6 py-2 bg-gray-300 text-gray-700 rounded hover:bg-gray-400"
          >
            ❌ Annulla
          </button>
        )}
        <button
          onClick={handleSave}
          disabled={loading}
          className="px-6 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:bg-gray-400"
        >
          {loading ? "⏳ Salvataggio..." : "💾 Salva e Calcola Previsionale"}
        </button>
      </div>
    </div>
  );
}

// Assumptions Table Component (full version matching design)
function AssumptionsTable({
  historicalYears,
  forecastYears,
  historicalData,
  assumptions,
  onUpdate,
}: {
  historicalYears: number[];
  forecastYears: number[];
  historicalData: Record<number, { income: IncomeStatement; balance: BalanceSheet }>;
  assumptions: Record<number, Partial<BudgetAssumptionsCreate>>;
  onUpdate: (year: number, field: string, value: number) => void;
}) {
  const totalYears = historicalYears.length + forecastYears.length;

  // Calculate historical percentages for display
  const getHistoricalValue = (year: number, field: string): string => {
    const data = historicalData[year];
    if (!data) return "—";

    const income = data.income;
    const balance = data.balance;

    switch (field) {
      case "ce01_ricavi_vendite":
        return formatCurrency(parseFloat(income.ce01_ricavi_vendite));
      case "ce04_altri_ricavi":
        return formatCurrency(parseFloat(income.ce04_altri_ricavi));
      case "ce05_materie_prime":
        return formatCurrency(Math.abs(parseFloat(income.ce05_materie_prime)));
      case "ce06_servizi":
        return formatCurrency(Math.abs(parseFloat(income.ce06_servizi)));
      case "ce07_godimento_beni":
        return formatCurrency(Math.abs(parseFloat(income.ce07_godimento_beni)));
      case "ce08_costi_personale":
        return formatCurrency(Math.abs(parseFloat(income.ce08_costi_personale)));
      case "ce12_oneri_diversi":
        return formatCurrency(Math.abs(parseFloat(income.ce12_oneri_diversi)));
      default:
        return "—";
    }
  };

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-gray-200 border border-gray-300">
        <thead className="bg-gray-100">
          <tr>
            <th className="px-3 py-2 text-left text-xs font-bold text-gray-900 uppercase tracking-wider border-r border-gray-300 sticky left-0 bg-gray-100 z-10" style={{minWidth: '300px'}}>
              ANNI ANALISI
            </th>
            {historicalYears.map((year) => (
              <th
                key={year}
                className="px-3 py-2 text-center text-xs font-bold text-gray-900 uppercase border-r border-gray-300"
                style={{minWidth: '120px'}}
              >
                {year}
              </th>
            ))}
            {forecastYears.map((year) => (
              <th
                key={year}
                className="px-3 py-2 text-center text-xs font-bold text-cyan-700 uppercase border-r border-gray-300 bg-cyan-50"
                style={{minWidth: '120px'}}
              >
                {year}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="bg-white divide-y divide-gray-200">
          {/* VARIABILI ECONOMICHE Section */}
          <tr className="bg-gray-200">
            <td colSpan={totalYears + 1} className="px-3 py-2 text-sm font-bold text-gray-900 border-t-2 border-gray-400">
              VARIABILI ECONOMICHE
            </td>
          </tr>

          {/* Revenue Growth */}
          <tr className="hover:bg-gray-50">
            <td className="px-3 py-2 text-xs text-gray-900 border-r border-gray-200 sticky left-0 bg-white z-10">
              <div className="font-medium flex items-center gap-1">
                VAR. % RICAVI RISPETTO ALL&apos;ANNO {Math.max(...historicalYears)}
                <span className="text-gray-400 cursor-help" title="Variazione percentuale dei ricavi rispetto all'anno base. Valori accettati: da -100% a +1.000%">ⓘ</span>
              </div>
            </td>
            {historicalYears.map((year) => (
              <td key={year} className="px-3 py-2 text-xs text-center text-gray-700 border-r border-gray-200 bg-gray-50">
                {getHistoricalValue(year, "ce01_ricavi_vendite")}
              </td>
            ))}
            {forecastYears.map((year) => (
              <td key={year} className="px-2 py-2 border-r border-gray-200 bg-cyan-50">
                <input
                  type="number"
                  step="0.01"
                  min="-100"
                  max="1000"
                  value={assumptions[year]?.revenue_growth_pct || 0}
                  onChange={(e) => onUpdate(year, "revenue_growth_pct", parseFloat(e.target.value) || 0)}
                  className="w-full px-2 py-1 text-xs border border-cyan-400 rounded text-center bg-white text-gray-900 font-medium focus:outline-none focus:ring-2 focus:ring-cyan-500"
                  placeholder="0.00%"
                  title="Inserire variazione % da -100% a +1.000%"
                />
              </td>
            ))}
          </tr>

          {/* Other Revenue Growth */}
          <tr className="hover:bg-gray-50">
            <td className="px-3 py-2 text-xs text-gray-900 border-r border-gray-200 sticky left-0 bg-white z-10">
              <div className="font-medium flex items-center gap-1">
                VAR. % ALTRI RICAVI RISPETTO ALL&apos;ANNO {Math.max(...historicalYears)}
                <span className="text-gray-400 cursor-help" title="Variazione percentuale degli altri ricavi rispetto all'anno base. Valori accettati: da -100% a +1.000%">ⓘ</span>
              </div>
            </td>
            {historicalYears.map((year) => (
              <td key={year} className="px-3 py-2 text-xs text-center text-gray-700 border-r border-gray-200 bg-gray-50">
                {getHistoricalValue(year, "ce04_altri_ricavi")}
              </td>
            ))}
            {forecastYears.map((year) => (
              <td key={year} className="px-2 py-2 border-r border-gray-200 bg-cyan-50">
                <input
                  type="number"
                  step="0.01"
                  min="-100"
                  max="1000"
                  value={assumptions[year]?.other_revenue_growth_pct || 0}
                  onChange={(e) => onUpdate(year, "other_revenue_growth_pct", parseFloat(e.target.value) || 0)}
                  className="w-full px-2 py-1 text-xs border border-cyan-400 rounded text-center bg-white text-gray-900 font-medium focus:outline-none focus:ring-2 focus:ring-cyan-500"
                  placeholder="0.00%"
                  title="Inserire variazione % da -100% a +1.000%"
                />
              </td>
            ))}
          </tr>

          {/* Fixed Materials Percentage */}
          <tr className="hover:bg-gray-50">
            <td className="px-3 py-2 text-xs text-gray-900 border-r border-gray-200 sticky left-0 bg-white z-10">
              <div className="font-medium flex items-center gap-1">
                <div>
                  <div>% QUOTA FISSA COSTI PER MATERIE PRIME,</div>
                  <div>SUSSIDIARIE, DI CONSUMO E MERCI</div>
                </div>
                <span className="text-gray-400 cursor-help flex-shrink-0" title="Quota fissa di costi che non varieranno nel previsionale">ⓘ</span>
              </div>
            </td>
            {historicalYears.map((year) => (
              <td key={year} className="px-3 py-2 text-xs text-center text-gray-700 border-r border-gray-200 bg-gray-50">
                {getHistoricalValue(year, "ce05_materie_prime")}
              </td>
            ))}
            {forecastYears.map((year) => (
              <td key={year} className="px-2 py-2 border-r border-gray-200 bg-cyan-50">
                <input
                  type="number"
                  step="1"
                  min="0"
                  max="100"
                  value={assumptions[year]?.fixed_materials_percentage || 22}
                  onChange={(e) => onUpdate(year, "fixed_materials_percentage", parseFloat(e.target.value) || 22)}
                  className="w-full px-2 py-1 text-xs border border-cyan-400 rounded text-center bg-white text-gray-900 font-medium focus:outline-none focus:ring-2 focus:ring-cyan-500"
                  placeholder="22.00%"
                  title="Quota fissa di costi che non varieranno nel previsionale (0-100%)"
                />
              </td>
            ))}
          </tr>

          {/* Variable Materials Growth */}
          <tr className="hover:bg-gray-50">
            <td className="px-3 py-2 text-xs text-gray-900 border-r border-gray-200 sticky left-0 bg-white z-10">
              <div className="font-medium flex items-center gap-1">
                VAR. % COSTI VARIABILI PER MAT. PRIME RISPETTO ALL&apos;ANNO {Math.max(...historicalYears)}
                <span className="text-gray-400 cursor-help" title="Variazione percentuale dei costi variabili per materie prime. Valori accettati: da -100% a +1.000%">ⓘ</span>
              </div>
            </td>
            {historicalYears.map((year) => (
              <td key={year} className="px-3 py-2 text-xs text-center text-gray-700 border-r border-gray-200 bg-gray-50">
                —
              </td>
            ))}
            {forecastYears.map((year) => (
              <td key={year} className="px-2 py-2 border-r border-gray-200 bg-cyan-50">
                <input
                  type="number"
                  step="0.01"
                  min="-100"
                  max="1000"
                  value={assumptions[year]?.variable_materials_growth_pct || 0}
                  onChange={(e) => onUpdate(year, "variable_materials_growth_pct", parseFloat(e.target.value) || 0)}
                  className="w-full px-2 py-1 text-xs border border-cyan-400 rounded text-center bg-white text-gray-900 font-medium focus:outline-none focus:ring-2 focus:ring-cyan-500"
                  placeholder="0.00%"
                  title="Inserire variazione % da -100% a +1.000%"
                />
              </td>
            ))}
          </tr>

          {/* Fixed Materials Growth */}
          <tr className="hover:bg-gray-50">
            <td className="px-3 py-2 text-xs text-gray-900 border-r border-gray-200 sticky left-0 bg-white z-10">
              <div className="font-medium flex items-center gap-1">
                VAR. % COSTI FISSI PER MAT. PRIME RISPETTO ALL&apos;ANNO {Math.max(...historicalYears)}
                <span className="text-gray-400 cursor-help" title="Variazione percentuale dei costi fissi per materie prime. Valori accettati: da -100% a +1.000%">ⓘ</span>
              </div>
            </td>
            {historicalYears.map((year) => (
              <td key={year} className="px-3 py-2 text-xs text-center text-gray-700 border-r border-gray-200 bg-gray-50">
                —
              </td>
            ))}
            {forecastYears.map((year) => (
              <td key={year} className="px-2 py-2 border-r border-gray-200 bg-cyan-50">
                <input
                  type="number"
                  step="0.01"
                  min="-100"
                  max="1000"
                  value={assumptions[year]?.fixed_materials_growth_pct || 0}
                  onChange={(e) => onUpdate(year, "fixed_materials_growth_pct", parseFloat(e.target.value) || 0)}
                  className="w-full px-2 py-1 text-xs border border-cyan-400 rounded text-center bg-white text-gray-900 font-medium focus:outline-none focus:ring-2 focus:ring-cyan-500"
                  placeholder="0.00%"
                  title="Inserire variazione % da -100% a +1.000%"
                />
              </td>
            ))}
          </tr>

          {/* Fixed Services Percentage */}
          <tr className="hover:bg-gray-50">
            <td className="px-3 py-2 text-xs text-gray-900 border-r border-gray-200 sticky left-0 bg-white z-10">
              <div className="font-medium flex items-center gap-1">
                % QUOTA FISSA COSTI PER SERVIZI
                <span className="text-gray-400 cursor-help" title="Quota fissa di costi che non varieranno nel previsionale">ⓘ</span>
              </div>
            </td>
            {historicalYears.map((year) => (
              <td key={year} className="px-3 py-2 text-xs text-center text-gray-700 border-r border-gray-200 bg-gray-50">
                {getHistoricalValue(year, "ce06_servizi")}
              </td>
            ))}
            {forecastYears.map((year) => (
              <td key={year} className="px-2 py-2 border-r border-gray-200 bg-cyan-50">
                <input
                  type="number"
                  step="1"
                  min="0"
                  max="100"
                  value={assumptions[year]?.fixed_services_percentage || 22}
                  onChange={(e) => onUpdate(year, "fixed_services_percentage", parseFloat(e.target.value) || 22)}
                  className="w-full px-2 py-1 text-xs border border-cyan-400 rounded text-center bg-white text-gray-900 font-medium focus:outline-none focus:ring-2 focus:ring-cyan-500"
                  placeholder="22.00%"
                  title="Quota fissa di costi che non varieranno nel previsionale (0-100%)"
                />
              </td>
            ))}
          </tr>

          {/* Variable Services Growth */}
          <tr className="hover:bg-gray-50">
            <td className="px-3 py-2 text-xs text-gray-900 border-r border-gray-200 sticky left-0 bg-white z-10">
              <div className="font-medium flex items-center gap-1">
                VAR. % COSTI VARIABILI PER SERVIZI RISPETTO ALL&apos;ANNO {Math.max(...historicalYears)}
                <span className="text-gray-400 cursor-help" title="Variazione percentuale dei costi variabili per servizi. Valori accettati: da -100% a +1.000%">ⓘ</span>
              </div>
            </td>
            {historicalYears.map((year) => (
              <td key={year} className="px-3 py-2 text-xs text-center text-gray-700 border-r border-gray-200 bg-gray-50">
                —
              </td>
            ))}
            {forecastYears.map((year) => (
              <td key={year} className="px-2 py-2 border-r border-gray-200 bg-cyan-50">
                <input
                  type="number"
                  step="0.01"
                  min="-100"
                  max="1000"
                  value={assumptions[year]?.variable_services_growth_pct || 0}
                  onChange={(e) => onUpdate(year, "variable_services_growth_pct", parseFloat(e.target.value) || 0)}
                  className="w-full px-2 py-1 text-xs border border-cyan-400 rounded text-center bg-white text-gray-900 font-medium focus:outline-none focus:ring-2 focus:ring-cyan-500"
                  placeholder="0.00%"
                  title="Inserire variazione % da -100% a +1.000%"
                />
              </td>
            ))}
          </tr>

          {/* Fixed Services Growth */}
          <tr className="hover:bg-gray-50">
            <td className="px-3 py-2 text-xs text-gray-900 border-r border-gray-200 sticky left-0 bg-white z-10">
              <div className="font-medium flex items-center gap-1">
                VAR. % COSTI FISSI PER SERVIZI RISPETTO ALL&apos;ANNO {Math.max(...historicalYears)}
                <span className="text-gray-400 cursor-help" title="Variazione percentuale dei costi fissi per servizi. Valori accettati: da -100% a +1.000%">ⓘ</span>
              </div>
            </td>
            {historicalYears.map((year) => (
              <td key={year} className="px-3 py-2 text-xs text-center text-gray-700 border-r border-gray-200 bg-gray-50">
                —
              </td>
            ))}
            {forecastYears.map((year) => (
              <td key={year} className="px-2 py-2 border-r border-gray-200 bg-cyan-50">
                <input
                  type="number"
                  step="0.01"
                  min="-100"
                  max="1000"
                  value={assumptions[year]?.fixed_services_growth_pct || 0}
                  onChange={(e) => onUpdate(year, "fixed_services_growth_pct", parseFloat(e.target.value) || 0)}
                  className="w-full px-2 py-1 text-xs border border-cyan-400 rounded text-center bg-white text-gray-900 font-medium focus:outline-none focus:ring-2 focus:ring-cyan-500"
                  placeholder="0.00%"
                  title="Inserire variazione % da -100% a +1.000%"
                />
              </td>
            ))}
          </tr>

          {/* Rent Growth */}
          <tr className="hover:bg-gray-50">
            <td className="px-3 py-2 text-xs text-gray-900 border-r border-gray-200 sticky left-0 bg-white z-10">
              <div className="font-medium flex items-center gap-1">
                VAR. % COSTI GODIMENTO BENI DI TERZI RISPETTO ALL&apos;ANNO {Math.max(...historicalYears)}
                <span className="text-gray-400 cursor-help" title="Variazione percentuale dei costi di godimento beni di terzi. Valori accettati: da -100% a +1.000%">ⓘ</span>
              </div>
            </td>
            {historicalYears.map((year) => (
              <td key={year} className="px-3 py-2 text-xs text-center text-gray-700 border-r border-gray-200 bg-gray-50">
                {getHistoricalValue(year, "ce07_godimento_beni")}
              </td>
            ))}
            {forecastYears.map((year) => (
              <td key={year} className="px-2 py-2 border-r border-gray-200 bg-cyan-50">
                <input
                  type="number"
                  step="0.01"
                  min="-100"
                  max="1000"
                  value={assumptions[year]?.rent_growth_pct || 0}
                  onChange={(e) => onUpdate(year, "rent_growth_pct", parseFloat(e.target.value) || 0)}
                  className="w-full px-2 py-1 text-xs border border-cyan-400 rounded text-center bg-white text-gray-900 font-medium focus:outline-none focus:ring-2 focus:ring-cyan-500"
                  placeholder="0.00%"
                  title="Inserire variazione % da -100% a +1.000%"
                />
              </td>
            ))}
          </tr>

          {/* Personnel Growth */}
          <tr className="hover:bg-gray-50">
            <td className="px-3 py-2 text-xs text-gray-900 border-r border-gray-200 sticky left-0 bg-white z-10">
              <div className="font-medium flex items-center gap-1">
                VAR. % COSTI DEL PERSONALE RISPETTO ALL&apos;ANNO {Math.max(...historicalYears)}
                <span className="text-gray-400 cursor-help" title="Variazione percentuale dei costi del personale. Valori accettati: da -100% a +1.000%">ⓘ</span>
              </div>
            </td>
            {historicalYears.map((year) => (
              <td key={year} className="px-3 py-2 text-xs text-center text-gray-700 border-r border-gray-200 bg-gray-50">
                {getHistoricalValue(year, "ce08_costi_personale")}
              </td>
            ))}
            {forecastYears.map((year) => (
              <td key={year} className="px-2 py-2 border-r border-gray-200 bg-cyan-50">
                <input
                  type="number"
                  step="0.01"
                  min="-100"
                  max="1000"
                  value={assumptions[year]?.personnel_growth_pct || 0}
                  onChange={(e) => onUpdate(year, "personnel_growth_pct", parseFloat(e.target.value) || 0)}
                  className="w-full px-2 py-1 text-xs border border-cyan-400 rounded text-center bg-white text-gray-900 font-medium focus:outline-none focus:ring-2 focus:ring-cyan-500"
                  placeholder="0.00%"
                  title="Inserire variazione % da -100% a +1.000%"
                />
              </td>
            ))}
          </tr>

          {/* Other Costs Growth */}
          <tr className="hover:bg-gray-50">
            <td className="px-3 py-2 text-xs text-gray-900 border-r border-gray-200 sticky left-0 bg-white z-10">
              <div className="font-medium flex items-center gap-1">
                VAR. % ONERI DIVERSI DI GESTIONE ALL&apos;ANNO {Math.max(...historicalYears)}
                <span className="text-gray-400 cursor-help" title="Variazione percentuale degli oneri diversi di gestione. Valori accettati: da -100% a +1.000%">ⓘ</span>
              </div>
            </td>
            {historicalYears.map((year) => (
              <td key={year} className="px-3 py-2 text-xs text-center text-gray-700 border-r border-gray-200 bg-gray-50">
                {getHistoricalValue(year, "ce12_oneri_diversi")}
              </td>
            ))}
            {forecastYears.map((year) => (
              <td key={year} className="px-2 py-2 border-r border-gray-200 bg-cyan-50">
                <input
                  type="number"
                  step="0.01"
                  min="-100"
                  max="1000"
                  value={assumptions[year]?.other_costs_growth_pct || 0}
                  onChange={(e) => onUpdate(year, "other_costs_growth_pct", parseFloat(e.target.value) || 0)}
                  className="w-full px-2 py-1 text-xs border border-cyan-400 rounded text-center bg-white text-gray-900 font-medium focus:outline-none focus:ring-2 focus:ring-cyan-500"
                  placeholder="0.00%"
                  title="Inserire variazione % da -100% a +1.000%"
                />
              </td>
            ))}
          </tr>

          {/* Tax Rate */}
          <tr className="hover:bg-gray-50">
            <td className="px-3 py-2 text-xs text-gray-900 border-r border-gray-200 sticky left-0 bg-white z-10">
              <div className="font-medium flex items-center gap-1">
                % ALIQUOTA IRES/IRAP ATTESA
                <span className="text-gray-400 cursor-help" title="Aliquota fiscale attesa (IRES + IRAP). Valori tipici: 24-30%">ⓘ</span>
              </div>
            </td>
            {historicalYears.map((year) => (
              <td key={year} className="px-3 py-2 text-xs text-center text-gray-700 border-r border-gray-200 bg-gray-50">
                30,00%
              </td>
            ))}
            {forecastYears.map((year) => (
              <td key={year} className="px-2 py-2 border-r border-gray-200 bg-cyan-50">
                <input
                  type="number"
                  step="0.1"
                  min="0"
                  max="100"
                  value={assumptions[year]?.tax_rate || 27.9}
                  onChange={(e) => onUpdate(year, "tax_rate", parseFloat(e.target.value) || 27.9)}
                  className="w-full px-2 py-1 text-xs border border-cyan-400 rounded text-center bg-white text-gray-900 font-medium focus:outline-none focus:ring-2 focus:ring-cyan-500"
                  placeholder="27.90%"
                  title="Aliquota fiscale attesa (0-100%)"
                />
              </td>
            ))}
          </tr>

          {/* IMMOBILIZZAZIONI Section */}
          <tr className="bg-gray-200">
            <td colSpan={totalYears + 1} className="px-3 py-2 text-sm font-bold text-gray-900 border-t-2 border-gray-400">
              IMMOBILIZZAZIONI
            </td>
          </tr>

          {/* Intangible Assets Header */}
          <tr className="bg-gray-100">
            <td colSpan={totalYears + 1} className="px-3 py-2 text-xs font-bold text-gray-800 text-center">
              IMMOBILIZZAZIONI IMMATERIALI
            </td>
          </tr>

          {/* Intangible Investment */}
          <tr className="hover:bg-gray-50">
            <td className="px-3 py-2 text-xs text-gray-900 border-r border-gray-200 sticky left-0 bg-white z-10">
              <div className="font-medium flex items-center gap-1">
                INVESTIMENTO
                <span className="text-gray-400 cursor-help" title="Importo investimento in immobilizzazioni immateriali (€)">ⓘ</span>
              </div>
            </td>
            {historicalYears.map((year) => (
              <td key={year} className="px-3 py-2 text-xs text-center text-gray-700 border-r border-gray-200 bg-gray-50">
                —
              </td>
            ))}
            {forecastYears.map((year) => (
              <td key={year} className="px-2 py-2 border-r border-gray-200 bg-cyan-50">
                <input
                  type="number"
                  step="1000"
                  min="0"
                  value={(assumptions[year]?.investments || 0) / 2}
                  onChange={(e) => onUpdate(year, "investments", (parseFloat(e.target.value) || 0) * 2)}
                  className="w-full px-2 py-1 text-xs border border-cyan-400 rounded text-center bg-white text-gray-900 font-medium focus:outline-none focus:ring-2 focus:ring-cyan-500"
                  placeholder="0"
                  title="Investimento in immobilizzazioni immateriali (€)"
                />
              </td>
            ))}
          </tr>

          {/* Intangible Depreciation Rate */}
          <tr className="hover:bg-gray-50">
            <td className="px-3 py-2 text-xs text-gray-900 border-r border-gray-200 sticky left-0 bg-white z-10">
              <div className="font-medium flex items-center gap-1">
                % AMM.TO MEDIA
                <span className="text-gray-400 cursor-help" title="Percentuale ammortamento media annua">ⓘ</span>
              </div>
            </td>
            {historicalYears.map((year) => (
              <td key={year} className="px-3 py-2 text-xs text-center text-gray-700 border-r border-gray-200 bg-gray-50">
                —
              </td>
            ))}
            {forecastYears.map((year) => (
              <td key={year} className="px-2 py-2 border-r border-gray-200 bg-cyan-50">
                <input
                  type="number"
                  step="1"
                  min="0"
                  max="100"
                  value={assumptions[year]?.depreciation_rate || 20}
                  onChange={(e) => onUpdate(year, "depreciation_rate", parseFloat(e.target.value) || 20)}
                  className="w-full px-2 py-1 text-xs border border-cyan-400 rounded text-center bg-white text-gray-900 font-medium focus:outline-none focus:ring-2 focus:ring-cyan-500"
                  placeholder="20.00%"
                  title="Percentuale ammortamento (0-100%)"
                />
              </td>
            ))}
          </tr>

          {/* Tangible Assets Header */}
          <tr className="bg-gray-100">
            <td colSpan={totalYears + 1} className="px-3 py-2 text-xs font-bold text-gray-800 text-center">
              IMMOBILIZZAZIONI MATERIALI
            </td>
          </tr>

          {/* Tangible Investment */}
          <tr className="hover:bg-gray-50">
            <td className="px-3 py-2 text-xs text-gray-900 border-r border-gray-200 sticky left-0 bg-white z-10">
              <div className="font-medium flex items-center gap-1">
                INVESTIMENTO
                <span className="text-gray-400 cursor-help" title="Importo investimento in immobilizzazioni materiali (€)">ⓘ</span>
              </div>
            </td>
            {historicalYears.map((year) => (
              <td key={year} className="px-3 py-2 text-xs text-center text-gray-700 border-r border-gray-200 bg-gray-50">
                —
              </td>
            ))}
            {forecastYears.map((year) => (
              <td key={year} className="px-2 py-2 border-r border-gray-200 bg-cyan-50">
                <input
                  type="number"
                  step="1000"
                  min="0"
                  value={assumptions[year]?.investments || 0}
                  onChange={(e) => onUpdate(year, "investments", parseFloat(e.target.value) || 0)}
                  className="w-full px-2 py-1 text-xs border border-cyan-400 rounded text-center bg-white text-gray-900 font-medium focus:outline-none focus:ring-2 focus:ring-cyan-500"
                  placeholder="0"
                  title="Investimento in immobilizzazioni materiali (€)"
                />
              </td>
            ))}
          </tr>

          {/* Tangible Depreciation Rate */}
          <tr className="hover:bg-gray-50">
            <td className="px-3 py-2 text-xs text-gray-900 border-r border-gray-200 sticky left-0 bg-white z-10">
              <div className="font-medium flex items-center gap-1">
                % AMM.TO MEDIA
                <span className="text-gray-400 cursor-help" title="Percentuale ammortamento media annua">ⓘ</span>
              </div>
            </td>
            {historicalYears.map((year) => (
              <td key={year} className="px-3 py-2 text-xs text-center text-gray-700 border-r border-gray-200 bg-gray-50">
                —
              </td>
            ))}
            {forecastYears.map((year) => (
              <td key={year} className="px-2 py-2 border-r border-gray-200 bg-cyan-50">
                <input
                  type="number"
                  step="1"
                  min="0"
                  max="100"
                  value={assumptions[year]?.depreciation_rate || 20}
                  onChange={(e) => onUpdate(year, "depreciation_rate", parseFloat(e.target.value) || 20)}
                  className="w-full px-2 py-1 text-xs border border-cyan-400 rounded text-center bg-white text-gray-900 font-medium focus:outline-none focus:ring-2 focus:ring-cyan-500"
                  placeholder="20.00%"
                  title="Percentuale ammortamento (0-100%)"
                />
              </td>
            ))}
          </tr>

          {/* CREDITI DELL'ATTIVO CIRCOLANTE Section */}
          <tr className="bg-gray-200">
            <td colSpan={totalYears + 1} className="px-3 py-2 text-sm font-bold text-gray-900 border-t-2 border-gray-400">
              CREDITI DELL&apos;ATTIVO CIRCOLANTE
            </td>
          </tr>

          {/* Short-term Receivables Growth */}
          <tr className="hover:bg-gray-50">
            <td className="px-3 py-2 text-xs text-gray-900 border-r border-gray-200 sticky left-0 bg-white z-10">
              <div className="font-medium flex items-center gap-1">
                VAR. % CREDITI ESIG. ENTRO ES. SUCC. RISPETTO ALL&apos;ANNO {Math.max(...historicalYears)}
                <span className="text-gray-400 cursor-help" title="Variazione percentuale crediti esigibili entro l'esercizio successivo. Valori accettati: da -100% a +1.000%">ⓘ</span>
              </div>
            </td>
            {historicalYears.map((year) => (
              <td key={year} className="px-3 py-2 text-xs text-center text-gray-700 border-r border-gray-200 bg-gray-50">
                —
              </td>
            ))}
            {forecastYears.map((year) => (
              <td key={year} className="px-2 py-2 border-r border-gray-200 bg-cyan-50">
                <input
                  type="number"
                  step="0.01"
                  min="-100"
                  max="1000"
                  value={assumptions[year]?.receivables_short_growth_pct || 0}
                  onChange={(e) => onUpdate(year, "receivables_short_growth_pct", parseFloat(e.target.value) || 0)}
                  className="w-full px-2 py-1 text-xs border border-cyan-400 rounded text-center bg-white text-gray-900 font-medium focus:outline-none focus:ring-2 focus:ring-cyan-500"
                  placeholder="0.00%"
                  title="Inserire variazione % da -100% a +1.000%"
                />
              </td>
            ))}
          </tr>

          {/* Long-term Receivables Growth */}
          <tr className="hover:bg-gray-50">
            <td className="px-3 py-2 text-xs text-gray-900 border-r border-gray-200 sticky left-0 bg-white z-10">
              <div className="font-medium flex items-center gap-1">
                VAR. % CREDITI ESIG. OLTRE ES. SUCC. RISPETTO ALL&apos;ANNO {Math.max(...historicalYears)}
                <span className="text-gray-400 cursor-help" title="Variazione percentuale crediti esigibili oltre l'esercizio successivo. Valori accettati: da -100% a +1.000%">ⓘ</span>
              </div>
            </td>
            {historicalYears.map((year) => (
              <td key={year} className="px-3 py-2 text-xs text-center text-gray-700 border-r border-gray-200 bg-gray-50">
                —
              </td>
            ))}
            {forecastYears.map((year) => (
              <td key={year} className="px-2 py-2 border-r border-gray-200 bg-cyan-50">
                <input
                  type="number"
                  step="0.01"
                  min="-100"
                  max="1000"
                  value={assumptions[year]?.receivables_long_growth_pct || 0}
                  onChange={(e) => onUpdate(year, "receivables_long_growth_pct", parseFloat(e.target.value) || 0)}
                  className="w-full px-2 py-1 text-xs border border-cyan-400 rounded text-center bg-white text-gray-900 font-medium focus:outline-none focus:ring-2 focus:ring-cyan-500"
                  placeholder="0.00%"
                  title="Inserire variazione % da -100% a +1.000%"
                />
              </td>
            ))}
          </tr>

          {/* DEBITI Section */}
          <tr className="bg-gray-200">
            <td colSpan={totalYears + 1} className="px-3 py-2 text-sm font-bold text-gray-900 border-t-2 border-gray-400">
              DEBITI
            </td>
          </tr>

          {/* Short-term Payables Header */}
          <tr className="bg-gray-100">
            <td colSpan={totalYears + 1} className="px-3 py-2 text-xs font-bold text-gray-800 text-center">
              DEBITI ESIGIBILI ENTRO L&apos;ESERCIZIO SUCCESSIVO
            </td>
          </tr>

          {/* Short-term Payables Growth */}
          <tr className="hover:bg-gray-50">
            <td className="px-3 py-2 text-xs text-gray-900 border-r border-gray-200 sticky left-0 bg-white z-10">
              <div className="font-medium flex items-center gap-1">
                VAR. % DEBITI ESIG. ENTRO ES. SUCC. RISPETTO ALL&apos;ANNO {Math.max(...historicalYears)}
                <span className="text-gray-400 cursor-help" title="Variazione percentuale debiti esigibili entro l'esercizio successivo. Valori accettati: da -100% a +1.000%">ⓘ</span>
              </div>
            </td>
            {historicalYears.map((year) => (
              <td key={year} className="px-3 py-2 text-xs text-center text-gray-700 border-r border-gray-200 bg-gray-50">
                —
              </td>
            ))}
            {forecastYears.map((year) => (
              <td key={year} className="px-2 py-2 border-r border-gray-200 bg-cyan-50">
                <input
                  type="number"
                  step="0.01"
                  min="-100"
                  max="1000"
                  value={assumptions[year]?.payables_short_growth_pct || 0}
                  onChange={(e) => onUpdate(year, "payables_short_growth_pct", parseFloat(e.target.value) || 0)}
                  className="w-full px-2 py-1 text-xs border border-cyan-400 rounded text-center bg-white text-gray-900 font-medium focus:outline-none focus:ring-2 focus:ring-cyan-500"
                  placeholder="0.00%"
                  title="Inserire variazione % da -100% a +1.000%"
                />
              </td>
            ))}
          </tr>

          {/* Long-term Payables Header */}
          <tr className="bg-gray-100">
            <td colSpan={totalYears + 1} className="px-3 py-2 text-xs font-bold text-gray-800 text-center">
              DEBITI ESIGIBILI OLTRE L&apos;ESERCIZIO SUCCESSIVO
            </td>
          </tr>

          {/* Financing Amount */}
          <tr className="hover:bg-gray-50">
            <td className="px-3 py-2 text-xs text-gray-900 border-r border-gray-200 sticky left-0 bg-white z-10">
              <div className="font-medium flex items-center gap-1">
                IMPORTO FINANZIAMENTO
                <span className="text-gray-400 cursor-help" title="Importo nuovo finanziamento a medio-lungo termine (€)">ⓘ</span>
              </div>
            </td>
            {historicalYears.map((year) => (
              <td key={year} className="px-3 py-2 text-xs text-center text-gray-700 border-r border-gray-200 bg-gray-50">
                —
              </td>
            ))}
            {forecastYears.map((year) => (
              <td key={year} className="px-2 py-2 border-r border-gray-200 bg-cyan-50">
                <input
                  type="number"
                  step="1000"
                  min="0"
                  value={assumptions[year]?.financing_amount || 0}
                  onChange={(e) => onUpdate(year, "financing_amount", parseFloat(e.target.value) || 0)}
                  className="w-full px-2 py-1 text-xs border border-cyan-400 rounded text-center bg-white text-gray-900 font-medium focus:outline-none focus:ring-2 focus:ring-cyan-500"
                  placeholder="0"
                  title="Importo nuovo finanziamento (€)"
                />
              </td>
            ))}
          </tr>

          {/* Financing Duration */}
          <tr className="hover:bg-gray-50">
            <td className="px-3 py-2 text-xs text-gray-900 border-r border-gray-200 sticky left-0 bg-white z-10">
              <div className="font-medium flex items-center gap-1">
                DURATA MEDIA
                <span className="text-gray-400 cursor-help" title="Durata media del finanziamento in anni">ⓘ</span>
              </div>
            </td>
            {historicalYears.map((year) => (
              <td key={year} className="px-3 py-2 text-xs text-center text-gray-700 border-r border-gray-200 bg-gray-50">
                —
              </td>
            ))}
            {forecastYears.map((year) => (
              <td key={year} className="px-2 py-2 border-r border-gray-200 bg-cyan-50">
                <input
                  type="number"
                  step="1"
                  min="1"
                  max="30"
                  value={assumptions[year]?.financing_duration_years || 5}
                  onChange={(e) => onUpdate(year, "financing_duration_years", parseFloat(e.target.value) || 5)}
                  className="w-full px-2 py-1 text-xs border border-cyan-400 rounded text-center bg-white text-gray-900 font-medium focus:outline-none focus:ring-2 focus:ring-cyan-500"
                  placeholder="5"
                  title="Durata in anni (1-30)"
                />
              </td>
            ))}
          </tr>

          {/* Financing Interest Rate */}
          <tr className="hover:bg-gray-50">
            <td className="px-3 py-2 text-xs text-gray-900 border-r border-gray-200 sticky left-0 bg-white z-10">
              <div className="font-medium flex items-center gap-1">
                % TASSO INTERESSE PASSIVO MEDIO
                <span className="text-gray-400 cursor-help" title="Tasso di interesse medio del finanziamento">ⓘ</span>
              </div>
            </td>
            {historicalYears.map((year) => (
              <td key={year} className="px-3 py-2 text-xs text-center text-gray-700 border-r border-gray-200 bg-gray-50">
                —
              </td>
            ))}
            {forecastYears.map((year) => (
              <td key={year} className="px-2 py-2 border-r border-gray-200 bg-cyan-50">
                <input
                  type="number"
                  step="0.1"
                  min="0"
                  max="100"
                  value={assumptions[year]?.financing_interest_rate || 3}
                  onChange={(e) => onUpdate(year, "financing_interest_rate", parseFloat(e.target.value) || 3)}
                  className="w-full px-2 py-1 text-xs border border-cyan-400 rounded text-center bg-white text-gray-900 font-medium focus:outline-none focus:ring-2 focus:ring-cyan-500"
                  placeholder="3.00%"
                  title="Tasso interesse (0-100%)"
                />
              </td>
            ))}
          </tr>
        </tbody>
      </table>
    </div>
  );
}
