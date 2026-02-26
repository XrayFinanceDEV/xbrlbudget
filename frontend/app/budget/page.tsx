"use client";

import { useState, useEffect, useCallback } from "react";
import { useApp } from "@/contexts/AppContext";
import { useScenarios, useInvalidateScenarios, useInvalidateAnalysis } from "@/hooks/use-queries";
import {
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
import { toast } from "sonner";
import {
  FileSpreadsheet,
  ClipboardList,
  Plus,
  CheckCircle2,
  Package,
  Pencil,
  RefreshCw,
  Trash2,
  X,
  Save,
  Loader2,
  Info,
  Calendar,
  AlertTriangle,
  AlertCircle,
  ChevronDown,
  ChevronRight,
  Zap,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { PageHeader } from "@/components/page-header";

export default function BudgetPage() {
  const { selectedCompanyId, years } = useApp();
  const { data: scenarios = [], isLoading: loading, error: scenariosError, refetch: refetchScenarios } = useScenarios(selectedCompanyId);
  const invalidateScenarios = useInvalidateScenarios();
  const invalidateAnalysis = useInvalidateAnalysis();
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<string>("list");
  const [editingScenario, setEditingScenario] = useState<BudgetScenario | null>(null);

  const handleDeleteScenario = async (scenarioId: number) => {
    if (!selectedCompanyId) return;

    try {
      await deleteBudgetScenario(selectedCompanyId, scenarioId);
      invalidateScenarios(selectedCompanyId);
      toast.success("Scenario eliminato con successo");
    } catch (err) {
      console.error("Error deleting scenario:", err);
      toast.error("Errore durante l'eliminazione dello scenario");
    }
  };

  const handleRegenerateScenario = async (scenarioId: number) => {
    if (!selectedCompanyId) return;

    try {
      await generateForecast(selectedCompanyId, scenarioId);
      toast.success("Previsionale ricalcolato con successo!");
      invalidateScenarios(selectedCompanyId);
      invalidateAnalysis(selectedCompanyId, scenarioId);
    } catch (err: any) {
      console.error("Error regenerating forecast:", err);
      toast.error(
        err.response?.data?.detail || "Impossibile ricalcolare il previsionale"
      );
    }
  };

  const handleEditScenario = (scenario: BudgetScenario) => {
    setEditingScenario(scenario);
    setActiveTab("create");
  };

  const handleScenarioSaved = () => {
    setEditingScenario(null);
    setActiveTab("list");
    if (selectedCompanyId) invalidateScenarios(selectedCompanyId);
  };

  if (!selectedCompanyId) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <Alert>
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Attenzione</AlertTitle>
          <AlertDescription>
            Seleziona un&apos;azienda per gestire gli scenari di budget
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  if (years.length === 0) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            Nessun anno fiscale trovato. Importa prima i dati del bilancio.
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <PageHeader
        title="Budget & Previsionale"
        description="Crea scenari di budget e previsionali finanziari a 3 anni"
        icon={<FileSpreadsheet className="h-6 w-6" />}
      />

      {error && (
        <Alert variant="destructive" className="mb-6">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* Tabs */}
      <Tabs
        value={activeTab}
        onValueChange={(value) => {
          setActiveTab(value);
          if (value === "list") {
            setEditingScenario(null);
          }
        }}
      >
        <TabsList>
          <TabsTrigger value="list" className="gap-1.5">
            <ClipboardList className="h-4 w-4" />
            Scenari
          </TabsTrigger>
          <TabsTrigger value="create" className="gap-1.5">
            <Plus className="h-4 w-4" />
            Nuovo Scenario
          </TabsTrigger>
        </TabsList>

        <TabsContent value="list">
          <ScenariosList
            scenarios={scenarios}
            loading={loading}
            onEdit={handleEditScenario}
            onDelete={handleDeleteScenario}
            onRegenerate={handleRegenerateScenario}
          />
        </TabsContent>

        <TabsContent value="create">
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
        </TabsContent>
      </Tabs>
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
        <Loader2 className="h-12 w-12 animate-spin text-primary mx-auto" />
        <p className="mt-4 text-muted-foreground">Caricamento...</p>
      </div>
    );
  }

  if (scenarios.length === 0) {
    return (
      <Card>
        <CardContent className="py-6 text-center">
          <p className="text-muted-foreground">
            Nessuno scenario presente. Crea il primo scenario nella tab &quot;Nuovo Scenario&quot;
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {scenarios.map((scenario) => (
        <Card key={scenario.id}>
          <CardContent className="p-6">
            <div className="flex items-start justify-between">
              <div className="flex-1">
                <h3 className="text-lg font-semibold text-foreground mb-2 flex items-center gap-2">
                  {scenario.is_active ? (
                    <CheckCircle2 className="h-5 w-5 text-green-600 dark:text-green-400" />
                  ) : (
                    <Package className="h-5 w-5 text-muted-foreground" />
                  )}
                  {scenario.name}
                </h3>
                <div className="text-sm text-muted-foreground space-y-1">
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
                <Button
                  variant="default"
                  size="sm"
                  onClick={() => onEdit(scenario)}
                >
                  <Pencil className="h-4 w-4" />
                  Modifica
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => onRegenerate(scenario.id)}
                >
                  <RefreshCw className="h-4 w-4" />
                  Ricalcola
                </Button>
                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <Button variant="destructive" size="sm">
                      <Trash2 className="h-4 w-4" />
                      Elimina
                    </Button>
                  </AlertDialogTrigger>
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle>Conferma eliminazione</AlertDialogTitle>
                      <AlertDialogDescription>
                        Sei sicuro di voler eliminare questo scenario? Questa azione non
                        puo essere annullata.
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel>Annulla</AlertDialogCancel>
                      <AlertDialogAction
                        onClick={() => onDelete(scenario.id)}
                        className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                      >
                        Elimina
                      </AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              </div>
            </div>
          </CardContent>
        </Card>
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
            ce02_override: a.ce02_override,
            ce03_override: a.ce03_override,
            ce10_override: a.ce10_override,
            ce11_override: a.ce11_override,
            ce13_override: a.ce13_override,
            ce14_override: a.ce14_override,
            ce15_override: a.ce15_override,
            ce16_override: a.ce16_override,
            ce17_override: a.ce17_override,
            ce18_override: a.ce18_override,
            ce19_override: a.ce19_override,
          };
        });
        setAssumptions(assumptionsMap);
        setExistingAssumptionYears(existingYears);
        setNumYears(data.length || 3);
      });
    } else {
      // Initialize with defaults, pre-populating CE overrides from base year
      setExistingAssumptionYears(new Set());
      const defaultAssumptions: Record<number, Partial<BudgetAssumptionsCreate>> = {};
      const baseIncome = historicalData[baseYear]?.income;
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
          fixed_materials_percentage: 0,
          fixed_services_percentage: 0,
          depreciation_rate: 20,
          financing_amount: 0,
          financing_duration_years: 5,
          financing_interest_rate: 3,
          ce02_override: baseIncome ? parseFloat(baseIncome.ce02_variazioni_rimanenze) : null,
          ce03_override: baseIncome ? parseFloat(baseIncome.ce03_lavori_interni) : null,
          ce10_override: baseIncome ? parseFloat(baseIncome.ce10_var_rimanenze_mat_prime) : null,
          ce11_override: baseIncome ? parseFloat(baseIncome.ce11_accantonamenti) : null,
          ce13_override: baseIncome ? parseFloat(baseIncome.ce13_proventi_partecipazioni) : null,
          ce14_override: baseIncome ? parseFloat(baseIncome.ce14_altri_proventi_finanziari) : null,
          ce15_override: baseIncome ? parseFloat(baseIncome.ce15_oneri_finanziari) : null,
          ce16_override: baseIncome ? parseFloat(baseIncome.ce16_utili_perdite_cambi) : null,
          ce17_override: baseIncome ? parseFloat(baseIncome.ce17_rettifiche_attivita_fin) : null,
          ce18_override: baseIncome ? parseFloat(baseIncome.ce18_proventi_straordinari) : null,
          ce19_override: baseIncome ? parseFloat(baseIncome.ce19_oneri_straordinari) : null,
        };
      });
      setAssumptions(defaultAssumptions);
    }
  }, [scenario, companyId]);

  // Auto-generator state
  const [inflationRate, setInflationRate] = useState(2.5);
  const [showAutoGen, setShowAutoGen] = useState(false);

  const updateAssumption = useCallback((year: number, field: string, value: number | null) => {
    setAssumptions((prev) => ({
      ...prev,
      [year]: {
        ...prev[year],
        [field]: value,
      },
    }));
  }, []);

  const handleSave = async () => {
    if (!name.trim()) {
      toast.error("Il nome dello scenario e obbligatorio!");
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

      toast.success("Scenario salvato e previsionale calcolato con successo!");
      onSaved();
    } catch (err: any) {
      console.error("Error saving scenario:", err);
      toast.error(
        err.response?.data?.detail || "Impossibile salvare lo scenario"
      );
    } finally {
      setLoading(false);
    }
  };

  const historicalYears = [...new Set(years)].filter(y => y <= baseYear).sort((a, b) => a - b);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          {scenario ? (
            <>
              <Pencil className="h-5 w-5" />
              Modifica Scenario: {scenario.name}
            </>
          ) : (
            <>
              <Plus className="h-5 w-5" />
              Nuovo Scenario Budget
            </>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {/* Scenario Details */}
        <div className="mb-6">
          <h3 className="text-lg font-semibold text-foreground mb-3">
            Informazioni Scenario
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="scenario-name">Nome Scenario *</Label>
              <Input
                id="scenario-name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="es. Budget 2025-2027"
              />
              <p className="text-sm text-muted-foreground flex items-center gap-1">
                <Calendar className="h-3.5 w-3.5" />
                <strong>Anno Base:</strong> {baseYear} (ultimo anno disponibile)
              </p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="scenario-description">Descrizione</Label>
              <Textarea
                id="scenario-description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Descrizione dello scenario..."
                rows={2}
              />
              <div className="flex items-center space-x-2">
                <Checkbox
                  id="scenario-active"
                  checked={isActive}
                  onCheckedChange={(checked) => setIsActive(checked === true)}
                />
                <Label htmlFor="scenario-active" className="text-sm font-normal">
                  Scenario Attivo
                </Label>
              </div>
            </div>
          </div>
        </div>

        <div className="border-t border-border pt-6 mb-6">
          <Label htmlFor="num-years" className="font-semibold text-foreground">
            Numero di anni da prevedere
          </Label>
          <Input
            id="num-years"
            type="number"
            min={1}
            max={5}
            value={numYears}
            onChange={(e) => setNumYears(parseInt(e.target.value) || 3)}
            className="w-32 mt-2"
          />
        </div>

        {/* Assumptions Table */}
        <div className="mb-6">
          <h3 className="text-lg font-semibold text-foreground mb-3">
            Ipotesi Previsionali
          </h3>
          <Alert className="mb-4">
            <Info className="h-4 w-4" />
            <AlertDescription>
              Inserisci le ipotesi per ciascun anno. Le celle evidenziate rappresentano i valori
              modificabili.
            </AlertDescription>
          </Alert>

          {/* Auto-Generator Card */}
          <AutoGeneratorCard
            historicalYears={historicalYears}
            forecastYears={forecastYears}
            historicalData={historicalData}
            inflationRate={inflationRate}
            setInflationRate={setInflationRate}
            showAutoGen={showAutoGen}
            setShowAutoGen={setShowAutoGen}
            updateAssumption={updateAssumption}
          />

          <AssumptionsTable
            historicalYears={historicalYears}
            forecastYears={forecastYears}
            historicalData={historicalData}
            assumptions={assumptions}
            onUpdate={updateAssumption}
          />
        </div>

        {/* Actions */}
        <div className="flex justify-center gap-4 pt-6 border-t border-border">
          {scenario && (
            <Button variant="outline" onClick={onCancel}>
              <X className="h-4 w-4" />
              Annulla
            </Button>
          )}
          <Button onClick={handleSave} disabled={loading}>
            {loading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Salvataggio...
              </>
            ) : (
              <>
                <Save className="h-4 w-4" />
                Salva e Calcola Previsionale
              </>
            )}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

// Auto-Generator Helper
function calculateTrend(
  historicalData: Record<number, { income: IncomeStatement; balance: BalanceSheet }>,
  year1: number,
  year2: number,
  getValue: (income: IncomeStatement) => number
): number | null {
  const d1 = historicalData[year1];
  const d2 = historicalData[year2];
  if (!d1?.income || !d2?.income) return null;
  const v1 = getValue(d1.income);
  const v2 = getValue(d2.income);
  if (v1 === 0) return null;
  return ((v2 - v1) / Math.abs(v1)) * 100;
}

const TREND_ITEMS: {
  label: string;
  fields: string[];
  getValue: (i: IncomeStatement) => number;
}[] = [
  { label: "Ricavi", fields: ["revenue_growth_pct"], getValue: (i) => parseFloat(i.ce01_ricavi_vendite) },
  { label: "Altri ricavi", fields: ["other_revenue_growth_pct"], getValue: (i) => parseFloat(i.ce04_altri_ricavi) },
  { label: "Materie prime", fields: ["variable_materials_growth_pct", "fixed_materials_growth_pct"], getValue: (i) => Math.abs(parseFloat(i.ce05_materie_prime)) },
  { label: "Servizi", fields: ["variable_services_growth_pct", "fixed_services_growth_pct"], getValue: (i) => Math.abs(parseFloat(i.ce06_servizi)) },
  { label: "Godimento beni", fields: ["rent_growth_pct"], getValue: (i) => Math.abs(parseFloat(i.ce07_godimento_beni)) },
  { label: "Personale", fields: ["personnel_growth_pct"], getValue: (i) => Math.abs(parseFloat(i.ce08_costi_personale)) },
  { label: "Oneri diversi", fields: ["other_costs_growth_pct"], getValue: (i) => Math.abs(parseFloat(i.ce12_oneri_diversi)) },
];

function AutoGeneratorCard({
  historicalYears,
  forecastYears,
  historicalData,
  inflationRate,
  setInflationRate,
  showAutoGen,
  setShowAutoGen,
  updateAssumption,
}: {
  historicalYears: number[];
  forecastYears: number[];
  historicalData: Record<number, { income: IncomeStatement; balance: BalanceSheet }>;
  inflationRate: number;
  setInflationRate: (v: number) => void;
  showAutoGen: boolean;
  setShowAutoGen: (v: boolean) => void;
  updateAssumption: (year: number, field: string, value: number | null) => void;
}) {
  const n = forecastYears.length;
  const hasTwoYears = historicalYears.length >= 2;
  const year1 = hasTwoYears ? historicalYears[historicalYears.length - 2] : 0;
  const year2 = hasTwoYears ? historicalYears[historicalYears.length - 1] : 0;

  // Compute trends and faded rates for each item
  const computedRows = TREND_ITEMS.map((item) => {
    const trend = hasTwoYears
      ? calculateTrend(historicalData, year1, year2, item.getValue)
      : null;
    const blended = trend !== null ? (trend + inflationRate) / 2 : inflationRate;
    const rates = forecastYears.map((_, i) => {
      if (n === 1) return Math.round(blended * 100) / 100;
      const weight = i / (n - 1);
      return Math.round((blended * (1 - weight) + inflationRate * weight) * 100) / 100;
    });
    return { ...item, trend, rates };
  });

  const applyAutoAssumptions = () => {
    for (const row of computedRows) {
      forecastYears.forEach((year, i) => {
        for (const field of row.fields) {
          updateAssumption(year, field, row.rates[i]);
        }
      });
    }
    // BS fields: use inflation directly
    const bsFields = ["receivables_short_growth_pct", "receivables_long_growth_pct", "payables_short_growth_pct"];
    for (const year of forecastYears) {
      for (const field of bsFields) {
        updateAssumption(year, field, Math.round(inflationRate * 100) / 100);
      }
    }
    toast.success("Ipotesi applicate con successo");
  };

  return (
    <Card className="mb-4 border-dashed">
      <CardHeader className="pb-2 cursor-pointer" onClick={() => setShowAutoGen(!showAutoGen)}>
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <Zap className="h-4 w-4 text-amber-500" />
          Auto-genera Ipotesi
          {showAutoGen ? (
            <ChevronDown className="h-4 w-4 ml-auto text-muted-foreground" />
          ) : (
            <ChevronRight className="h-4 w-4 ml-auto text-muted-foreground" />
          )}
        </CardTitle>
      </CardHeader>
      {showAutoGen && (
        <CardContent className="pt-0">
          <div className="flex items-center gap-3 mb-4">
            <Label htmlFor="inflation-rate" className="text-xs font-medium whitespace-nowrap">
              Inflazione attesa:
            </Label>
            <Input
              id="inflation-rate"
              type="number"
              step="0.1"
              min="-10"
              max="50"
              value={inflationRate}
              onChange={(e) => setInflationRate(parseFloat(e.target.value) || 0)}
              className="w-24 h-8 text-xs"
            />
            <span className="text-xs text-muted-foreground">%</span>
          </div>

          {!hasTwoYears && (
            <Alert className="mb-3">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription className="text-xs">
                Serve almeno 2 anni storici per calcolare il trend. Verranno usati i valori di inflazione.
              </AlertDescription>
            </Alert>
          )}

          <div className="overflow-x-auto">
            <table className="min-w-full text-xs border border-border divide-y divide-border">
              <thead className="bg-muted">
                <tr>
                  <th className="px-3 py-1.5 text-left font-semibold text-foreground">Voce</th>
                  <th className="px-3 py-1.5 text-center font-semibold text-foreground">Trend storico</th>
                  {forecastYears.map((year) => (
                    <th key={year} className="px-3 py-1.5 text-center font-semibold text-primary">
                      {year}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {computedRows.map((row) => (
                  <tr key={row.label} className="hover:bg-muted/50">
                    <td className="px-3 py-1.5 font-medium text-foreground">{row.label}</td>
                    <td className="px-3 py-1.5 text-center text-muted-foreground">
                      {row.trend !== null ? `${row.trend >= 0 ? "+" : ""}${row.trend.toFixed(1)}%` : "\u2014"}
                    </td>
                    {row.rates.map((rate, i) => (
                      <td key={i} className="px-3 py-1.5 text-center font-medium text-primary">
                        {rate.toFixed(1)}%
                      </td>
                    ))}
                  </tr>
                ))}
                {/* BS fields row */}
                <tr className="hover:bg-muted/50">
                  <td className="px-3 py-1.5 font-medium text-foreground">Crediti / Debiti breve</td>
                  <td className="px-3 py-1.5 text-center text-muted-foreground">{"\u2014"}</td>
                  {forecastYears.map((year) => (
                    <td key={year} className="px-3 py-1.5 text-center font-medium text-primary">
                      {inflationRate.toFixed(1)}%
                    </td>
                  ))}
                </tr>
              </tbody>
            </table>
          </div>

          <div className="flex justify-end mt-3">
            <Button size="sm" onClick={applyAutoAssumptions}>
              <Zap className="h-3.5 w-3.5" />
              Applica ipotesi
            </Button>
          </div>
        </CardContent>
      )}
    </Card>
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
  onUpdate: (year: number, field: string, value: number | null) => void;
}) {
  const [showCEDetail, setShowCEDetail] = useState(false);
  const totalYears = historicalYears.length + forecastYears.length;

  // Calculate historical percentages for display
  const getHistoricalValue = (year: number, field: string): string => {
    const data = historicalData[year];
    if (!data) return "\u2014";

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
      case "ce02_variazioni_rimanenze":
        return formatCurrency(parseFloat(income.ce02_variazioni_rimanenze));
      case "ce03_lavori_interni":
        return formatCurrency(parseFloat(income.ce03_lavori_interni));
      case "ce10_var_rimanenze_mat_prime":
        return formatCurrency(parseFloat(income.ce10_var_rimanenze_mat_prime));
      case "ce11_accantonamenti":
        return formatCurrency(parseFloat(income.ce11_accantonamenti));
      case "ce13_proventi_partecipazioni":
        return formatCurrency(parseFloat(income.ce13_proventi_partecipazioni));
      case "ce14_altri_proventi_finanziari":
        return formatCurrency(parseFloat(income.ce14_altri_proventi_finanziari));
      case "ce15_oneri_finanziari":
        return formatCurrency(parseFloat(income.ce15_oneri_finanziari));
      case "ce16_utili_perdite_cambi":
        return formatCurrency(parseFloat(income.ce16_utili_perdite_cambi));
      case "ce17_rettifiche_attivita_fin":
        return formatCurrency(parseFloat(income.ce17_rettifiche_attivita_fin));
      case "ce18_proventi_straordinari":
        return formatCurrency(parseFloat(income.ce18_proventi_straordinari));
      case "ce19_oneri_straordinari":
        return formatCurrency(parseFloat(income.ce19_oneri_straordinari));
      default:
        return "\u2014";
    }
  };

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-border border border-border">
        <thead className="bg-muted">
          <tr>
            <th className="px-3 py-2 text-left text-xs font-bold text-foreground uppercase tracking-wider border-r border-border sticky left-0 bg-muted z-10" style={{minWidth: '300px'}}>
              ANNI ANALISI
            </th>
            {historicalYears.map((year) => (
              <th
                key={year}
                className="px-3 py-2 text-center text-xs font-bold text-foreground uppercase border-r border-border"
                style={{minWidth: '120px'}}
              >
                {year}
              </th>
            ))}
            {forecastYears.map((year) => (
              <th
                key={year}
                className="px-3 py-2 text-center text-xs font-bold text-primary uppercase border-r border-border bg-primary/10"
                style={{minWidth: '120px'}}
              >
                {year}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="bg-card divide-y divide-border">
          {/* VARIABILI ECONOMICHE Section */}
          <tr className="bg-muted">
            <td colSpan={totalYears + 1} className="px-3 py-2 text-sm font-bold text-foreground border-t-2 border-border">
              VARIABILI ECONOMICHE
            </td>
          </tr>

          {/* Revenue Growth */}
          <tr className="hover:bg-muted/50">
            <td className="px-3 py-2 text-xs text-foreground border-r border-border sticky left-0 bg-card z-10">
              <div className="font-medium flex items-center gap-1">
                VAR. % RICAVI RISPETTO ALL&apos;ANNO {Math.max(...historicalYears)}
                <span title="Variazione percentuale dei ricavi rispetto all'anno base. Valori accettati: da -100% a +1.000%"><Info className="h-3.5 w-3.5 text-muted-foreground cursor-help flex-shrink-0" /></span>
              </div>
            </td>
            {historicalYears.map((year) => (
              <td key={year} className="px-3 py-2 text-xs text-center text-muted-foreground border-r border-border bg-muted/50">
                {getHistoricalValue(year, "ce01_ricavi_vendite")}
              </td>
            ))}
            {forecastYears.map((year) => (
              <td key={year} className="px-2 py-2 border-r border-border bg-primary/10">
                <input
                  type="number"
                  step="0.01"
                  min="-100"
                  max="1000"
                  value={assumptions[year]?.revenue_growth_pct || 0}
                  onChange={(e) => onUpdate(year, "revenue_growth_pct", parseFloat(e.target.value) || 0)}
                  className="w-full px-2 py-1 text-xs border border-primary/50 rounded text-center bg-card text-foreground font-medium focus:outline-none focus:ring-2 focus:ring-primary"
                  placeholder="0.00%"
                  title="Inserire variazione % da -100% a +1.000%"
                />
              </td>
            ))}
          </tr>

          {/* Other Revenue Growth */}
          <tr className="hover:bg-muted/50">
            <td className="px-3 py-2 text-xs text-foreground border-r border-border sticky left-0 bg-card z-10">
              <div className="font-medium flex items-center gap-1">
                VAR. % ALTRI RICAVI RISPETTO ALL&apos;ANNO {Math.max(...historicalYears)}
                <span title="Variazione percentuale degli altri ricavi rispetto all'anno base. Valori accettati: da -100% a +1.000%"><Info className="h-3.5 w-3.5 text-muted-foreground cursor-help flex-shrink-0" /></span>
              </div>
            </td>
            {historicalYears.map((year) => (
              <td key={year} className="px-3 py-2 text-xs text-center text-muted-foreground border-r border-border bg-muted/50">
                {getHistoricalValue(year, "ce04_altri_ricavi")}
              </td>
            ))}
            {forecastYears.map((year) => (
              <td key={year} className="px-2 py-2 border-r border-border bg-primary/10">
                <input
                  type="number"
                  step="0.01"
                  min="-100"
                  max="1000"
                  value={assumptions[year]?.other_revenue_growth_pct || 0}
                  onChange={(e) => onUpdate(year, "other_revenue_growth_pct", parseFloat(e.target.value) || 0)}
                  className="w-full px-2 py-1 text-xs border border-primary/50 rounded text-center bg-card text-foreground font-medium focus:outline-none focus:ring-2 focus:ring-primary"
                  placeholder="0.00%"
                  title="Inserire variazione % da -100% a +1.000%"
                />
              </td>
            ))}
          </tr>

          {/* Fixed Materials Percentage */}
          <tr className="hover:bg-muted/50">
            <td className="px-3 py-2 text-xs text-foreground border-r border-border sticky left-0 bg-card z-10">
              <div className="font-medium flex items-center gap-1">
                <div>
                  <div>% QUOTA FISSA COSTI PER MATERIE PRIME,</div>
                  <div>SUSSIDIARIE, DI CONSUMO E MERCI</div>
                </div>
                <span title="Quota fissa di costi che non varieranno nel previsionale"><Info className="h-3.5 w-3.5 text-muted-foreground cursor-help flex-shrink-0" /></span>
              </div>
            </td>
            {historicalYears.map((year) => (
              <td key={year} className="px-3 py-2 text-xs text-center text-muted-foreground border-r border-border bg-muted/50">
                {getHistoricalValue(year, "ce05_materie_prime")}
              </td>
            ))}
            {forecastYears.map((year) => (
              <td key={year} className="px-2 py-2 border-r border-border bg-primary/10">
                <input
                  type="number"
                  step="1"
                  min="0"
                  max="100"
                  value={assumptions[year]?.fixed_materials_percentage ?? 0}
                  onChange={(e) => {
                    const val = parseFloat(e.target.value);
                    onUpdate(year, "fixed_materials_percentage", isNaN(val) ? 0 : val);
                  }}
                  className="w-full px-2 py-1 text-xs border border-primary/50 rounded text-center bg-card text-foreground font-medium focus:outline-none focus:ring-2 focus:ring-primary"
                  placeholder="0%"
                  title="Quota fissa di costi che non varieranno nel previsionale (0-100%)"
                />
              </td>
            ))}
          </tr>

          {/* Variable Materials Growth */}
          <tr className="hover:bg-muted/50">
            <td className="px-3 py-2 text-xs text-foreground border-r border-border sticky left-0 bg-card z-10">
              <div className="font-medium flex items-center gap-1">
                VAR. % COSTI VARIABILI PER MAT. PRIME RISPETTO ALL&apos;ANNO {Math.max(...historicalYears)}
                <span title="Variazione percentuale dei costi variabili per materie prime. Valori accettati: da -100% a +1.000%"><Info className="h-3.5 w-3.5 text-muted-foreground cursor-help flex-shrink-0" /></span>
              </div>
            </td>
            {historicalYears.map((year) => (
              <td key={year} className="px-3 py-2 text-xs text-center text-muted-foreground border-r border-border bg-muted/50">
                {"\u2014"}
              </td>
            ))}
            {forecastYears.map((year) => (
              <td key={year} className="px-2 py-2 border-r border-border bg-primary/10">
                <input
                  type="number"
                  step="0.01"
                  min="-100"
                  max="1000"
                  value={assumptions[year]?.variable_materials_growth_pct || 0}
                  onChange={(e) => onUpdate(year, "variable_materials_growth_pct", parseFloat(e.target.value) || 0)}
                  className="w-full px-2 py-1 text-xs border border-primary/50 rounded text-center bg-card text-foreground font-medium focus:outline-none focus:ring-2 focus:ring-primary"
                  placeholder="0.00%"
                  title="Inserire variazione % da -100% a +1.000%"
                />
              </td>
            ))}
          </tr>

          {/* Fixed Materials Growth */}
          <tr className="hover:bg-muted/50">
            <td className="px-3 py-2 text-xs text-foreground border-r border-border sticky left-0 bg-card z-10">
              <div className="font-medium flex items-center gap-1">
                VAR. % COSTI FISSI PER MAT. PRIME RISPETTO ALL&apos;ANNO {Math.max(...historicalYears)}
                <span title="Variazione percentuale dei costi fissi per materie prime. Valori accettati: da -100% a +1.000%"><Info className="h-3.5 w-3.5 text-muted-foreground cursor-help flex-shrink-0" /></span>
              </div>
            </td>
            {historicalYears.map((year) => (
              <td key={year} className="px-3 py-2 text-xs text-center text-muted-foreground border-r border-border bg-muted/50">
                {"\u2014"}
              </td>
            ))}
            {forecastYears.map((year) => (
              <td key={year} className="px-2 py-2 border-r border-border bg-primary/10">
                <input
                  type="number"
                  step="0.01"
                  min="-100"
                  max="1000"
                  value={assumptions[year]?.fixed_materials_growth_pct || 0}
                  onChange={(e) => onUpdate(year, "fixed_materials_growth_pct", parseFloat(e.target.value) || 0)}
                  className="w-full px-2 py-1 text-xs border border-primary/50 rounded text-center bg-card text-foreground font-medium focus:outline-none focus:ring-2 focus:ring-primary"
                  placeholder="0.00%"
                  title="Inserire variazione % da -100% a +1.000%"
                />
              </td>
            ))}
          </tr>

          {/* Fixed Services Percentage */}
          <tr className="hover:bg-muted/50">
            <td className="px-3 py-2 text-xs text-foreground border-r border-border sticky left-0 bg-card z-10">
              <div className="font-medium flex items-center gap-1">
                % QUOTA FISSA COSTI PER SERVIZI
                <span title="Quota fissa di costi che non varieranno nel previsionale"><Info className="h-3.5 w-3.5 text-muted-foreground cursor-help flex-shrink-0" /></span>
              </div>
            </td>
            {historicalYears.map((year) => (
              <td key={year} className="px-3 py-2 text-xs text-center text-muted-foreground border-r border-border bg-muted/50">
                {getHistoricalValue(year, "ce06_servizi")}
              </td>
            ))}
            {forecastYears.map((year) => (
              <td key={year} className="px-2 py-2 border-r border-border bg-primary/10">
                <input
                  type="number"
                  step="1"
                  min="0"
                  max="100"
                  value={assumptions[year]?.fixed_services_percentage ?? 0}
                  onChange={(e) => {
                    const val = parseFloat(e.target.value);
                    onUpdate(year, "fixed_services_percentage", isNaN(val) ? 0 : val);
                  }}
                  className="w-full px-2 py-1 text-xs border border-primary/50 rounded text-center bg-card text-foreground font-medium focus:outline-none focus:ring-2 focus:ring-primary"
                  placeholder="0%"
                  title="Quota fissa di costi che non varieranno nel previsionale (0-100%)"
                />
              </td>
            ))}
          </tr>

          {/* Variable Services Growth */}
          <tr className="hover:bg-muted/50">
            <td className="px-3 py-2 text-xs text-foreground border-r border-border sticky left-0 bg-card z-10">
              <div className="font-medium flex items-center gap-1">
                VAR. % COSTI VARIABILI PER SERVIZI RISPETTO ALL&apos;ANNO {Math.max(...historicalYears)}
                <span title="Variazione percentuale dei costi variabili per servizi. Valori accettati: da -100% a +1.000%"><Info className="h-3.5 w-3.5 text-muted-foreground cursor-help flex-shrink-0" /></span>
              </div>
            </td>
            {historicalYears.map((year) => (
              <td key={year} className="px-3 py-2 text-xs text-center text-muted-foreground border-r border-border bg-muted/50">
                {"\u2014"}
              </td>
            ))}
            {forecastYears.map((year) => (
              <td key={year} className="px-2 py-2 border-r border-border bg-primary/10">
                <input
                  type="number"
                  step="0.01"
                  min="-100"
                  max="1000"
                  value={assumptions[year]?.variable_services_growth_pct || 0}
                  onChange={(e) => onUpdate(year, "variable_services_growth_pct", parseFloat(e.target.value) || 0)}
                  className="w-full px-2 py-1 text-xs border border-primary/50 rounded text-center bg-card text-foreground font-medium focus:outline-none focus:ring-2 focus:ring-primary"
                  placeholder="0.00%"
                  title="Inserire variazione % da -100% a +1.000%"
                />
              </td>
            ))}
          </tr>

          {/* Fixed Services Growth */}
          <tr className="hover:bg-muted/50">
            <td className="px-3 py-2 text-xs text-foreground border-r border-border sticky left-0 bg-card z-10">
              <div className="font-medium flex items-center gap-1">
                VAR. % COSTI FISSI PER SERVIZI RISPETTO ALL&apos;ANNO {Math.max(...historicalYears)}
                <span title="Variazione percentuale dei costi fissi per servizi. Valori accettati: da -100% a +1.000%"><Info className="h-3.5 w-3.5 text-muted-foreground cursor-help flex-shrink-0" /></span>
              </div>
            </td>
            {historicalYears.map((year) => (
              <td key={year} className="px-3 py-2 text-xs text-center text-muted-foreground border-r border-border bg-muted/50">
                {"\u2014"}
              </td>
            ))}
            {forecastYears.map((year) => (
              <td key={year} className="px-2 py-2 border-r border-border bg-primary/10">
                <input
                  type="number"
                  step="0.01"
                  min="-100"
                  max="1000"
                  value={assumptions[year]?.fixed_services_growth_pct || 0}
                  onChange={(e) => onUpdate(year, "fixed_services_growth_pct", parseFloat(e.target.value) || 0)}
                  className="w-full px-2 py-1 text-xs border border-primary/50 rounded text-center bg-card text-foreground font-medium focus:outline-none focus:ring-2 focus:ring-primary"
                  placeholder="0.00%"
                  title="Inserire variazione % da -100% a +1.000%"
                />
              </td>
            ))}
          </tr>

          {/* Rent Growth */}
          <tr className="hover:bg-muted/50">
            <td className="px-3 py-2 text-xs text-foreground border-r border-border sticky left-0 bg-card z-10">
              <div className="font-medium flex items-center gap-1">
                VAR. % COSTI GODIMENTO BENI DI TERZI RISPETTO ALL&apos;ANNO {Math.max(...historicalYears)}
                <span title="Variazione percentuale dei costi di godimento beni di terzi. Valori accettati: da -100% a +1.000%"><Info className="h-3.5 w-3.5 text-muted-foreground cursor-help flex-shrink-0" /></span>
              </div>
            </td>
            {historicalYears.map((year) => (
              <td key={year} className="px-3 py-2 text-xs text-center text-muted-foreground border-r border-border bg-muted/50">
                {getHistoricalValue(year, "ce07_godimento_beni")}
              </td>
            ))}
            {forecastYears.map((year) => (
              <td key={year} className="px-2 py-2 border-r border-border bg-primary/10">
                <input
                  type="number"
                  step="0.01"
                  min="-100"
                  max="1000"
                  value={assumptions[year]?.rent_growth_pct || 0}
                  onChange={(e) => onUpdate(year, "rent_growth_pct", parseFloat(e.target.value) || 0)}
                  className="w-full px-2 py-1 text-xs border border-primary/50 rounded text-center bg-card text-foreground font-medium focus:outline-none focus:ring-2 focus:ring-primary"
                  placeholder="0.00%"
                  title="Inserire variazione % da -100% a +1.000%"
                />
              </td>
            ))}
          </tr>

          {/* Personnel Growth */}
          <tr className="hover:bg-muted/50">
            <td className="px-3 py-2 text-xs text-foreground border-r border-border sticky left-0 bg-card z-10">
              <div className="font-medium flex items-center gap-1">
                VAR. % COSTI DEL PERSONALE RISPETTO ALL&apos;ANNO {Math.max(...historicalYears)}
                <span title="Variazione percentuale dei costi del personale. Valori accettati: da -100% a +1.000%"><Info className="h-3.5 w-3.5 text-muted-foreground cursor-help flex-shrink-0" /></span>
              </div>
            </td>
            {historicalYears.map((year) => (
              <td key={year} className="px-3 py-2 text-xs text-center text-muted-foreground border-r border-border bg-muted/50">
                {getHistoricalValue(year, "ce08_costi_personale")}
              </td>
            ))}
            {forecastYears.map((year) => (
              <td key={year} className="px-2 py-2 border-r border-border bg-primary/10">
                <input
                  type="number"
                  step="0.01"
                  min="-100"
                  max="1000"
                  value={assumptions[year]?.personnel_growth_pct || 0}
                  onChange={(e) => onUpdate(year, "personnel_growth_pct", parseFloat(e.target.value) || 0)}
                  className="w-full px-2 py-1 text-xs border border-primary/50 rounded text-center bg-card text-foreground font-medium focus:outline-none focus:ring-2 focus:ring-primary"
                  placeholder="0.00%"
                  title="Inserire variazione % da -100% a +1.000%"
                />
              </td>
            ))}
          </tr>

          {/* Other Costs Growth */}
          <tr className="hover:bg-muted/50">
            <td className="px-3 py-2 text-xs text-foreground border-r border-border sticky left-0 bg-card z-10">
              <div className="font-medium flex items-center gap-1">
                VAR. % ONERI DIVERSI DI GESTIONE ALL&apos;ANNO {Math.max(...historicalYears)}
                <span title="Variazione percentuale degli oneri diversi di gestione. Valori accettati: da -100% a +1.000%"><Info className="h-3.5 w-3.5 text-muted-foreground cursor-help flex-shrink-0" /></span>
              </div>
            </td>
            {historicalYears.map((year) => (
              <td key={year} className="px-3 py-2 text-xs text-center text-muted-foreground border-r border-border bg-muted/50">
                {getHistoricalValue(year, "ce12_oneri_diversi")}
              </td>
            ))}
            {forecastYears.map((year) => (
              <td key={year} className="px-2 py-2 border-r border-border bg-primary/10">
                <input
                  type="number"
                  step="0.01"
                  min="-100"
                  max="1000"
                  value={assumptions[year]?.other_costs_growth_pct || 0}
                  onChange={(e) => onUpdate(year, "other_costs_growth_pct", parseFloat(e.target.value) || 0)}
                  className="w-full px-2 py-1 text-xs border border-primary/50 rounded text-center bg-card text-foreground font-medium focus:outline-none focus:ring-2 focus:ring-primary"
                  placeholder="0.00%"
                  title="Inserire variazione % da -100% a +1.000%"
                />
              </td>
            ))}
          </tr>

          {/* Tax Rate */}
          <tr className="hover:bg-muted/50">
            <td className="px-3 py-2 text-xs text-foreground border-r border-border sticky left-0 bg-card z-10">
              <div className="font-medium flex items-center gap-1">
                % ALIQUOTA IRES/IRAP ATTESA
                <span title="Aliquota fiscale attesa (IRES + IRAP). Valori tipici: 24-30%"><Info className="h-3.5 w-3.5 text-muted-foreground cursor-help flex-shrink-0" /></span>
              </div>
            </td>
            {historicalYears.map((year) => (
              <td key={year} className="px-3 py-2 text-xs text-center text-muted-foreground border-r border-border bg-muted/50">
                30,00%
              </td>
            ))}
            {forecastYears.map((year) => (
              <td key={year} className="px-2 py-2 border-r border-border bg-primary/10">
                <input
                  type="number"
                  step="0.1"
                  min="0"
                  max="100"
                  value={assumptions[year]?.tax_rate || 27.9}
                  onChange={(e) => onUpdate(year, "tax_rate", parseFloat(e.target.value) || 27.9)}
                  className="w-full px-2 py-1 text-xs border border-primary/50 rounded text-center bg-card text-foreground font-medium focus:outline-none focus:ring-2 focus:ring-primary"
                  placeholder="27.90%"
                  title="Aliquota fiscale attesa (0-100%)"
                />
              </td>
            ))}
          </tr>

          {/* DETTAGLIO CONTO ECONOMICO Section (collapsible) */}
          <tr className="bg-muted cursor-pointer" onClick={() => setShowCEDetail(!showCEDetail)}>
            <td colSpan={totalYears + 1} className="px-3 py-2 text-sm font-bold text-foreground border-t-2 border-border">
              <div className="flex items-center gap-1">
                {showCEDetail ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                DETTAGLIO CONTO ECONOMICO
              </div>
            </td>
          </tr>

          {showCEDetail && (
            <>
              {/* CE Override Rows */}
              {([
                { field: "ce02_override", histField: "ce02_variazioni_rimanenze", label: "Variazioni rimanenze prodotti (A.2)" },
                { field: "ce03_override", histField: "ce03_lavori_interni", label: "Incrementi immobilizzazioni per lavori interni (A.3)" },
                { field: "ce10_override", histField: "ce10_var_rimanenze_mat_prime", label: "Variazioni rimanenze materie prime (B.11)" },
                { field: "ce11_override", histField: "ce11_accantonamenti", label: "Accantonamenti per rischi e oneri (B.12)" },
                { field: "ce13_override", histField: "ce13_proventi_partecipazioni", label: "Proventi da partecipazioni (C.15)" },
                { field: "ce14_override", histField: "ce14_altri_proventi_finanziari", label: "Altri proventi finanziari (C.16)" },
                { field: "ce15_override", histField: "ce15_oneri_finanziari", label: "Interessi e oneri finanziari (C.17)" },
                { field: "ce16_override", histField: "ce16_utili_perdite_cambi", label: "Utili e perdite su cambi (C.17-bis)" },
                { field: "ce17_override", histField: "ce17_rettifiche_attivita_fin", label: "Rettifiche attività finanziarie (D)" },
                { field: "ce18_override", histField: "ce18_proventi_straordinari", label: "Proventi straordinari (E.20)" },
                { field: "ce19_override", histField: "ce19_oneri_straordinari", label: "Oneri straordinari (E.21)" },
              ] as const).map(({ field, histField, label }) => (
                <tr key={field} className="hover:bg-muted/50">
                  <td className="px-3 py-2 text-xs text-foreground border-r border-border sticky left-0 bg-card z-10">
                    <div className="font-medium">{label}</div>
                  </td>
                  {historicalYears.map((year) => (
                    <td key={year} className="px-3 py-2 text-xs text-center text-muted-foreground border-r border-border bg-muted/50">
                      {getHistoricalValue(year, histField)}
                    </td>
                  ))}
                  {forecastYears.map((year) => (
                    <td key={year} className="px-2 py-2 border-r border-border bg-primary/10">
                      <input
                        type="number"
                        step="100"
                        value={assumptions[year]?.[field as keyof typeof assumptions[number]] ?? ""}
                        onChange={(e) => {
                          const val = e.target.value;
                          onUpdate(year, field, val === "" ? null : parseFloat(val) || 0);
                        }}
                        className="w-full px-2 py-1 text-xs border border-primary/50 rounded text-center bg-card text-foreground font-medium focus:outline-none focus:ring-2 focus:ring-primary"
                        placeholder="base year"
                        title={`${label} - valore in EUR (vuoto = usa anno base)`}
                      />
                    </td>
                  ))}
                </tr>
              ))}
            </>
          )}

          {/* IMMOBILIZZAZIONI Section */}
          <tr className="bg-muted">
            <td colSpan={totalYears + 1} className="px-3 py-2 text-sm font-bold text-foreground border-t-2 border-border">
              IMMOBILIZZAZIONI
            </td>
          </tr>

          {/* Intangible Assets Header */}
          <tr className="bg-muted/70">
            <td colSpan={totalYears + 1} className="px-3 py-2 text-xs font-bold text-foreground text-center">
              IMMOBILIZZAZIONI IMMATERIALI
            </td>
          </tr>

          {/* Intangible Investment */}
          <tr className="hover:bg-muted/50">
            <td className="px-3 py-2 text-xs text-foreground border-r border-border sticky left-0 bg-card z-10">
              <div className="font-medium flex items-center gap-1">
                INVESTIMENTO
                <span title="Importo investimento in immobilizzazioni immateriali (EUR)"><Info className="h-3.5 w-3.5 text-muted-foreground cursor-help flex-shrink-0" /></span>
              </div>
            </td>
            {historicalYears.map((year) => (
              <td key={year} className="px-3 py-2 text-xs text-center text-muted-foreground border-r border-border bg-muted/50">
                {"\u2014"}
              </td>
            ))}
            {forecastYears.map((year) => (
              <td key={year} className="px-2 py-2 border-r border-border bg-primary/10">
                <input
                  type="number"
                  step="1000"
                  min="0"
                  value={(assumptions[year]?.investments || 0) / 2}
                  onChange={(e) => onUpdate(year, "investments", (parseFloat(e.target.value) || 0) * 2)}
                  className="w-full px-2 py-1 text-xs border border-primary/50 rounded text-center bg-card text-foreground font-medium focus:outline-none focus:ring-2 focus:ring-primary"
                  placeholder="0"
                  title="Investimento in immobilizzazioni immateriali (EUR)"
                />
              </td>
            ))}
          </tr>

          {/* Intangible Depreciation Rate */}
          <tr className="hover:bg-muted/50">
            <td className="px-3 py-2 text-xs text-foreground border-r border-border sticky left-0 bg-card z-10">
              <div className="font-medium flex items-center gap-1">
                % AMM.TO MEDIA
                <span title="Percentuale ammortamento media annua"><Info className="h-3.5 w-3.5 text-muted-foreground cursor-help flex-shrink-0" /></span>
              </div>
            </td>
            {historicalYears.map((year) => (
              <td key={year} className="px-3 py-2 text-xs text-center text-muted-foreground border-r border-border bg-muted/50">
                {"\u2014"}
              </td>
            ))}
            {forecastYears.map((year) => (
              <td key={year} className="px-2 py-2 border-r border-border bg-primary/10">
                <input
                  type="number"
                  step="1"
                  min="0"
                  max="100"
                  value={assumptions[year]?.depreciation_rate || 20}
                  onChange={(e) => onUpdate(year, "depreciation_rate", parseFloat(e.target.value) || 20)}
                  className="w-full px-2 py-1 text-xs border border-primary/50 rounded text-center bg-card text-foreground font-medium focus:outline-none focus:ring-2 focus:ring-primary"
                  placeholder="20.00%"
                  title="Percentuale ammortamento (0-100%)"
                />
              </td>
            ))}
          </tr>

          {/* Tangible Assets Header */}
          <tr className="bg-muted/70">
            <td colSpan={totalYears + 1} className="px-3 py-2 text-xs font-bold text-foreground text-center">
              IMMOBILIZZAZIONI MATERIALI
            </td>
          </tr>

          {/* Tangible Investment */}
          <tr className="hover:bg-muted/50">
            <td className="px-3 py-2 text-xs text-foreground border-r border-border sticky left-0 bg-card z-10">
              <div className="font-medium flex items-center gap-1">
                INVESTIMENTO
                <span title="Importo investimento in immobilizzazioni materiali (EUR)"><Info className="h-3.5 w-3.5 text-muted-foreground cursor-help flex-shrink-0" /></span>
              </div>
            </td>
            {historicalYears.map((year) => (
              <td key={year} className="px-3 py-2 text-xs text-center text-muted-foreground border-r border-border bg-muted/50">
                {"\u2014"}
              </td>
            ))}
            {forecastYears.map((year) => (
              <td key={year} className="px-2 py-2 border-r border-border bg-primary/10">
                <input
                  type="number"
                  step="1000"
                  min="0"
                  value={assumptions[year]?.investments || 0}
                  onChange={(e) => onUpdate(year, "investments", parseFloat(e.target.value) || 0)}
                  className="w-full px-2 py-1 text-xs border border-primary/50 rounded text-center bg-card text-foreground font-medium focus:outline-none focus:ring-2 focus:ring-primary"
                  placeholder="0"
                  title="Investimento in immobilizzazioni materiali (EUR)"
                />
              </td>
            ))}
          </tr>

          {/* Tangible Depreciation Rate */}
          <tr className="hover:bg-muted/50">
            <td className="px-3 py-2 text-xs text-foreground border-r border-border sticky left-0 bg-card z-10">
              <div className="font-medium flex items-center gap-1">
                % AMM.TO MEDIA
                <span title="Percentuale ammortamento media annua"><Info className="h-3.5 w-3.5 text-muted-foreground cursor-help flex-shrink-0" /></span>
              </div>
            </td>
            {historicalYears.map((year) => (
              <td key={year} className="px-3 py-2 text-xs text-center text-muted-foreground border-r border-border bg-muted/50">
                {"\u2014"}
              </td>
            ))}
            {forecastYears.map((year) => (
              <td key={year} className="px-2 py-2 border-r border-border bg-primary/10">
                <input
                  type="number"
                  step="1"
                  min="0"
                  max="100"
                  value={assumptions[year]?.depreciation_rate || 20}
                  onChange={(e) => onUpdate(year, "depreciation_rate", parseFloat(e.target.value) || 20)}
                  className="w-full px-2 py-1 text-xs border border-primary/50 rounded text-center bg-card text-foreground font-medium focus:outline-none focus:ring-2 focus:ring-primary"
                  placeholder="20.00%"
                  title="Percentuale ammortamento (0-100%)"
                />
              </td>
            ))}
          </tr>

          {/* CREDITI DELL'ATTIVO CIRCOLANTE Section */}
          <tr className="bg-muted">
            <td colSpan={totalYears + 1} className="px-3 py-2 text-sm font-bold text-foreground border-t-2 border-border">
              CREDITI DELL&apos;ATTIVO CIRCOLANTE
            </td>
          </tr>

          {/* Short-term Receivables Growth */}
          <tr className="hover:bg-muted/50">
            <td className="px-3 py-2 text-xs text-foreground border-r border-border sticky left-0 bg-card z-10">
              <div className="font-medium flex items-center gap-1">
                VAR. % CREDITI ESIG. ENTRO ES. SUCC. RISPETTO ALL&apos;ANNO {Math.max(...historicalYears)}
                <span title="Variazione percentuale crediti esigibili entro l'esercizio successivo. Valori accettati: da -100% a +1.000%"><Info className="h-3.5 w-3.5 text-muted-foreground cursor-help flex-shrink-0" /></span>
              </div>
            </td>
            {historicalYears.map((year) => (
              <td key={year} className="px-3 py-2 text-xs text-center text-muted-foreground border-r border-border bg-muted/50">
                {"\u2014"}
              </td>
            ))}
            {forecastYears.map((year) => (
              <td key={year} className="px-2 py-2 border-r border-border bg-primary/10">
                <input
                  type="number"
                  step="0.01"
                  min="-100"
                  max="1000"
                  value={assumptions[year]?.receivables_short_growth_pct || 0}
                  onChange={(e) => onUpdate(year, "receivables_short_growth_pct", parseFloat(e.target.value) || 0)}
                  className="w-full px-2 py-1 text-xs border border-primary/50 rounded text-center bg-card text-foreground font-medium focus:outline-none focus:ring-2 focus:ring-primary"
                  placeholder="0.00%"
                  title="Inserire variazione % da -100% a +1.000%"
                />
              </td>
            ))}
          </tr>

          {/* Long-term Receivables Growth */}
          <tr className="hover:bg-muted/50">
            <td className="px-3 py-2 text-xs text-foreground border-r border-border sticky left-0 bg-card z-10">
              <div className="font-medium flex items-center gap-1">
                VAR. % CREDITI ESIG. OLTRE ES. SUCC. RISPETTO ALL&apos;ANNO {Math.max(...historicalYears)}
                <span title="Variazione percentuale crediti esigibili oltre l'esercizio successivo. Valori accettati: da -100% a +1.000%"><Info className="h-3.5 w-3.5 text-muted-foreground cursor-help flex-shrink-0" /></span>
              </div>
            </td>
            {historicalYears.map((year) => (
              <td key={year} className="px-3 py-2 text-xs text-center text-muted-foreground border-r border-border bg-muted/50">
                {"\u2014"}
              </td>
            ))}
            {forecastYears.map((year) => (
              <td key={year} className="px-2 py-2 border-r border-border bg-primary/10">
                <input
                  type="number"
                  step="0.01"
                  min="-100"
                  max="1000"
                  value={assumptions[year]?.receivables_long_growth_pct || 0}
                  onChange={(e) => onUpdate(year, "receivables_long_growth_pct", parseFloat(e.target.value) || 0)}
                  className="w-full px-2 py-1 text-xs border border-primary/50 rounded text-center bg-card text-foreground font-medium focus:outline-none focus:ring-2 focus:ring-primary"
                  placeholder="0.00%"
                  title="Inserire variazione % da -100% a +1.000%"
                />
              </td>
            ))}
          </tr>

          {/* DEBITI Section */}
          <tr className="bg-muted">
            <td colSpan={totalYears + 1} className="px-3 py-2 text-sm font-bold text-foreground border-t-2 border-border">
              DEBITI
            </td>
          </tr>

          {/* Short-term Payables Header */}
          <tr className="bg-muted/70">
            <td colSpan={totalYears + 1} className="px-3 py-2 text-xs font-bold text-foreground text-center">
              DEBITI ESIGIBILI ENTRO L&apos;ESERCIZIO SUCCESSIVO
            </td>
          </tr>

          {/* Short-term Payables Growth */}
          <tr className="hover:bg-muted/50">
            <td className="px-3 py-2 text-xs text-foreground border-r border-border sticky left-0 bg-card z-10">
              <div className="font-medium flex items-center gap-1">
                VAR. % DEBITI ESIG. ENTRO ES. SUCC. RISPETTO ALL&apos;ANNO {Math.max(...historicalYears)}
                <span title="Variazione percentuale debiti esigibili entro l'esercizio successivo. Valori accettati: da -100% a +1.000%"><Info className="h-3.5 w-3.5 text-muted-foreground cursor-help flex-shrink-0" /></span>
              </div>
            </td>
            {historicalYears.map((year) => (
              <td key={year} className="px-3 py-2 text-xs text-center text-muted-foreground border-r border-border bg-muted/50">
                {"\u2014"}
              </td>
            ))}
            {forecastYears.map((year) => (
              <td key={year} className="px-2 py-2 border-r border-border bg-primary/10">
                <input
                  type="number"
                  step="0.01"
                  min="-100"
                  max="1000"
                  value={assumptions[year]?.payables_short_growth_pct || 0}
                  onChange={(e) => onUpdate(year, "payables_short_growth_pct", parseFloat(e.target.value) || 0)}
                  className="w-full px-2 py-1 text-xs border border-primary/50 rounded text-center bg-card text-foreground font-medium focus:outline-none focus:ring-2 focus:ring-primary"
                  placeholder="0.00%"
                  title="Inserire variazione % da -100% a +1.000%"
                />
              </td>
            ))}
          </tr>

          {/* Long-term Payables Header */}
          <tr className="bg-muted/70">
            <td colSpan={totalYears + 1} className="px-3 py-2 text-xs font-bold text-foreground text-center">
              DEBITI ESIGIBILI OLTRE L&apos;ESERCIZIO SUCCESSIVO
            </td>
          </tr>

          {/* Financing Amount */}
          <tr className="hover:bg-muted/50">
            <td className="px-3 py-2 text-xs text-foreground border-r border-border sticky left-0 bg-card z-10">
              <div className="font-medium flex items-center gap-1">
                IMPORTO FINANZIAMENTO
                <span title="Importo nuovo finanziamento a medio-lungo termine (EUR)"><Info className="h-3.5 w-3.5 text-muted-foreground cursor-help flex-shrink-0" /></span>
              </div>
            </td>
            {historicalYears.map((year) => (
              <td key={year} className="px-3 py-2 text-xs text-center text-muted-foreground border-r border-border bg-muted/50">
                {"\u2014"}
              </td>
            ))}
            {forecastYears.map((year) => (
              <td key={year} className="px-2 py-2 border-r border-border bg-primary/10">
                <input
                  type="number"
                  step="1000"
                  min="0"
                  value={assumptions[year]?.financing_amount || 0}
                  onChange={(e) => onUpdate(year, "financing_amount", parseFloat(e.target.value) || 0)}
                  className="w-full px-2 py-1 text-xs border border-primary/50 rounded text-center bg-card text-foreground font-medium focus:outline-none focus:ring-2 focus:ring-primary"
                  placeholder="0"
                  title="Importo nuovo finanziamento (EUR)"
                />
              </td>
            ))}
          </tr>

          {/* Financing Duration */}
          <tr className="hover:bg-muted/50">
            <td className="px-3 py-2 text-xs text-foreground border-r border-border sticky left-0 bg-card z-10">
              <div className="font-medium flex items-center gap-1">
                DURATA MEDIA
                <span title="Durata media del finanziamento in anni"><Info className="h-3.5 w-3.5 text-muted-foreground cursor-help flex-shrink-0" /></span>
              </div>
            </td>
            {historicalYears.map((year) => (
              <td key={year} className="px-3 py-2 text-xs text-center text-muted-foreground border-r border-border bg-muted/50">
                {"\u2014"}
              </td>
            ))}
            {forecastYears.map((year) => (
              <td key={year} className="px-2 py-2 border-r border-border bg-primary/10">
                <input
                  type="number"
                  step="1"
                  min="1"
                  max="30"
                  value={assumptions[year]?.financing_duration_years || 5}
                  onChange={(e) => onUpdate(year, "financing_duration_years", parseFloat(e.target.value) || 5)}
                  className="w-full px-2 py-1 text-xs border border-primary/50 rounded text-center bg-card text-foreground font-medium focus:outline-none focus:ring-2 focus:ring-primary"
                  placeholder="5"
                  title="Durata in anni (1-30)"
                />
              </td>
            ))}
          </tr>

          {/* Financing Interest Rate */}
          <tr className="hover:bg-muted/50">
            <td className="px-3 py-2 text-xs text-foreground border-r border-border sticky left-0 bg-card z-10">
              <div className="font-medium flex items-center gap-1">
                % TASSO INTERESSE PASSIVO MEDIO
                <span title="Tasso di interesse medio del finanziamento"><Info className="h-3.5 w-3.5 text-muted-foreground cursor-help flex-shrink-0" /></span>
              </div>
            </td>
            {historicalYears.map((year) => (
              <td key={year} className="px-3 py-2 text-xs text-center text-muted-foreground border-r border-border bg-muted/50">
                {"\u2014"}
              </td>
            ))}
            {forecastYears.map((year) => (
              <td key={year} className="px-2 py-2 border-r border-border bg-primary/10">
                <input
                  type="number"
                  step="0.1"
                  min="0"
                  max="100"
                  value={assumptions[year]?.financing_interest_rate || 3}
                  onChange={(e) => onUpdate(year, "financing_interest_rate", parseFloat(e.target.value) || 3)}
                  className="w-full px-2 py-1 text-xs border border-primary/50 rounded text-center bg-card text-foreground font-medium focus:outline-none focus:ring-2 focus:ring-primary"
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
