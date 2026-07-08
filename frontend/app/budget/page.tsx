"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { useRouter } from "next/navigation";
import { useApp } from "@/contexts/AppContext";
import { useScenarios, useInvalidateScenarios, useInvalidateAnalysis } from "@/hooks/use-queries";
import {
  createCompany,
  createFinancialYear,
  updateBalanceSheet,
  createBudgetScenario,
  updateBudgetScenario,
  deleteBudgetScenario,
  getBudgetAssumptions,
  createBudgetAssumptions,
  bulkUpsertAssumptions,
  generateForecast,
  getIncomeStatement,
  getBalanceSheet,
} from "@/lib/api";
import { formatCurrency } from "@/lib/formatters";
import { getErrorMessage } from "@/lib/utils";
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
  Rocket,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
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
import Link from "next/link";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { AssumptionsGrid } from "@/components/budget/AssumptionsGrid";
import {
  ADVANCED_GROUPS,
  ESSENTIAL_ROWS,
  computeEffectiveTaxRate,
} from "@/components/budget/assumption-rows";

// Round percentage values to 1 decimal to avoid showing e.g. "11,000000"
const fmtPct = (v: number | string | null | undefined, fallback = 0): number =>
  parseFloat((Number(v ?? fallback)).toFixed(1));

export default function BudgetPage() {
  const router = useRouter();
  const { selectedCompanyId, selectedCompany, years, startupMode, setSelectedCompanyId } = useApp();
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

  const [regenScenarioId, setRegenScenarioId] = useState<number | null>(null);
  const [regenClearOverrides, setRegenClearOverrides] = useState(false);

  const handleRegenerateScenario = async () => {
    if (!selectedCompanyId || regenScenarioId === null) return;
    try {
      await generateForecast(selectedCompanyId, regenScenarioId, regenClearOverrides);
      toast.success("Previsionale ricalcolato con successo!");
      invalidateScenarios(selectedCompanyId);
      invalidateAnalysis(selectedCompanyId, regenScenarioId);
    } catch (err: unknown) {
      console.error("Error regenerating forecast:", err);
      toast.error(getErrorMessage(err, "Impossibile ricalcolare il previsionale"));
    } finally {
      setRegenScenarioId(null);
      setRegenClearOverrides(false);
    }
  };

  const handleEditScenario = (scenario: BudgetScenario) => {
    setEditingScenario(scenario);
    setActiveTab("info");
  };

  const handleScenarioSaved = () => {
    setEditingScenario(null);
    setActiveTab("list");
    if (selectedCompanyId) invalidateScenarios(selectedCompanyId);
    toast.success("Vai al CE Previsionale per rifinire le voci", {
      action: { label: "CE Previsionale", onClick: () => router.push("/forecast/income") },
    });
  };

  // Startup mode has no imported bilancio: when there's no base year yet, show
  // the from-zero business-plan wizard that seeds a manual base year, scenario
  // and per-year assumptions, then opens the scenario on the Patrimoniali tab.
  if (startupMode && years.length === 0) {
    // After creation we set editingScenario but the founding-year FinancialYear
    // may not have propagated into `years` yet — show a loader until it does so
    // ScenarioForm doesn't render with an empty `years` array.
    if (editingScenario) {
      return (
        <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-16 text-center">
          <Loader2 className="h-12 w-12 animate-spin text-primary mx-auto" />
          <p className="mt-4 text-muted-foreground">Apertura business plan...</p>
        </div>
      );
    }
    return (
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <PageHeader
          title="Crea Previsione"
          description="Business plan startup: dati di base, periodo e driver economici attesi"
          icon={<Rocket className="h-6 w-6" />}
        />
        <StartupSetup
          onCreated={(sc) => {
            setEditingScenario(sc);
            setActiveTab("ipotesi");
          }}
        />
      </div>
    );
  }

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
        title={startupMode ? "Previsionale Startup" : "Budget & Previsionale"}
        description={
          startupMode
            ? "Definisci la crescita attesa e genera la proiezione a 3-5 anni"
            : "Crea scenari di budget e previsionali finanziari a 3 anni"
        }
        icon={startupMode ? <Rocket className="h-6 w-6" /> : <FileSpreadsheet className="h-6 w-6" />}
      />

      {error && (
        <Alert variant="destructive" className="mb-6">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {activeTab === "list" ? (
        <>
          <div className="flex justify-end mb-4">
            {startupMode ? (
              // In startup mode each business plan is its own project: starting a
              // new one must reset the company selection so the from-zero wizard
              // reappears, instead of adding another scenario to the same startup.
              <Button
                onClick={() => {
                  setEditingScenario(null);
                  setActiveTab("list");
                  setSelectedCompanyId(null);
                }}
              >
                <Plus className="h-4 w-4" />
                Nuovo business plan
              </Button>
            ) : (
              <Button onClick={() => setActiveTab("info")}>
                <Plus className="h-4 w-4" />
                Nuovo Scenario
              </Button>
            )}
          </div>
          <ScenariosList
            scenarios={scenarios}
            loading={loading}
            companyName={selectedCompany?.name ?? null}
            onEdit={handleEditScenario}
            onDelete={handleDeleteScenario}
            onRegenerate={setRegenScenarioId}
          />
        </>
      ) : (
        <ScenarioForm
          companyId={selectedCompanyId}
          years={years}
          scenario={editingScenario}
          activeTab={activeTab}
          setActiveTab={setActiveTab}
          startup={startupMode}
          onSaved={handleScenarioSaved}
          onCancel={() => {
            setEditingScenario(null);
            setActiveTab("list");
          }}
        />
      )}

      <AlertDialog open={regenScenarioId !== null} onOpenChange={(open) => !open && setRegenScenarioId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Ricalcola previsionale</AlertDialogTitle>
            <AlertDialogDescription>
              Il previsionale viene rigenerato dalle ipotesi correnti.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="flex items-center space-x-2 py-2">
            <Checkbox
              id="regen-clear"
              checked={regenClearOverrides}
              onCheckedChange={(c) => setRegenClearOverrides(c === true)}
            />
            <Label htmlFor="regen-clear" className="text-sm font-normal">
              Azzera le modifiche manuali del CE previsionale
            </Label>
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel>Annulla</AlertDialogCancel>
            <AlertDialogAction onClick={handleRegenerateScenario}>Ricalcola</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

// Per-year economic driver entered in the startup business-plan wizard.
// `dipendenti` (headcount) is planning-only info — not persisted.
type StartupYearDriver = { ricavi: number; margine: number; personale: number; dipendenti: number };

// Effective tax rate (IRES + IRAP blend) applied to the whole startup plan: it
// seeds the founding-year taxes AND is passed as every forecast year's tax_rate,
// so the base year and the projected years are taxed consistently.
const STARTUP_TAX_RATE_PCT = 27.9;

// Round a monetary value to 2 decimals, so the seeded statements store exact
// cents and the founding-year balance sheet ties to its P&L to the cent.
const round2 = (n: number): number => Math.round(n * 100) / 100;

// Build a complete BudgetAssumptionsCreate with neutral defaults. The startup
// flow drives the P&L with absolute CE overrides (ce01/ce06/ce08) instead of
// growth %, so every growth field is left at 0 — the overrides win in the engine.
function buildStartupAssumption(
  scenarioId: number,
  year: number,
  overrides: { ce01: number; ce06: number; ce08: number }
): BudgetAssumptionsCreate {
  return {
    scenario_id: scenarioId,
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
    intangible_investments: 0,
    tangible_investments: 0,
    asset_disposal_nbv: null,
    asset_disposal_proceeds: null,
    receivables_short_growth_pct: 0,
    receivables_long_growth_pct: 0,
    payables_short_growth_pct: 0,
    dso_days: null,
    dio_days: null,
    dpo_days: null,
    existing_debt_repayment_years: null,
    altri_finanz_repayment_years: null,
    cash_sweep_enabled: false,
    cash_sweep_min_cash: null,
    tfr_accrual_suspended: false,
    previdenza_scales_with_personnel: false,
    tax_rate: STARTUP_TAX_RATE_PCT,
    fixed_materials_percentage: 0,
    fixed_services_percentage: 0,
    depreciation_rate: 20,
    depreciation_rate_intangible: 20,
    financing_amount: 0,
    financing_duration_years: 5,
    financing_interest_rate: 3,
    ce01_override: overrides.ce01,
    ce06_override: overrides.ce06,
    ce08_override: overrides.ce08,
  };
}

// Startup business-plan wizard: collects identity (name, description), opening
// capital and the planning horizon (3 or 5 years), then a per-year grid of the
// three economic drivers (revenue, EBITDA margin %, personnel). From these it
// creates the company, the founding-year statements, the scenario and one
// assumptions row per following year (driven by absolute CE overrides), then
// generates the forecast and opens the scenario on the Patrimoniali tab.
function StartupSetup({ onCreated }: { onCreated: (sc: BudgetScenario) => void }) {
  const { setSelectedCompanyId, refreshCompanies } = useApp();
  const currentYear = new Date().getFullYear();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [capitale, setCapitale] = useState(0);
  // Planning horizon, current year INCLUDED: 3 → current + 2 following,
  // 5 → current + 4 following.
  const [period, setPeriod] = useState<3 | 5>(3);
  const [drivers, setDrivers] = useState<Record<number, StartupYearDriver>>({});
  const [loading, setLoading] = useState(false);

  const years = Array.from({ length: period }, (_, i) => currentYear + i);

  const getVal = (year: number, key: keyof StartupYearDriver): number =>
    drivers[year]?.[key] ?? 0;
  const setVal = (year: number, key: keyof StartupYearDriver, v: number) =>
    setDrivers((prev) => {
      const cur = prev[year] ?? { ricavi: 0, margine: 0, personale: 0, dipendenti: 0 };
      return { ...prev, [year]: { ...cur, [key]: v } };
    });

  // Derive EBITDA (€) and the implied non-personnel operating cost from the
  // three drivers. The residual is booked entirely to Costi per servizi (B.7).
  const deriveYear = (year: number) => {
    const ricavi = getVal(year, "ricavi");
    const margine = getVal(year, "margine");
    const personale = getVal(year, "personale");
    const ebitda = (ricavi * margine) / 100;
    const servizi = Math.max(0, ricavi - ebitda - personale);
    return { ricavi, margine, personale, ebitda, servizi };
  };

  const numCls = "w-full px-3 py-2 text-sm border border-border rounded bg-card text-foreground focus:outline-none focus:ring-2 focus:ring-primary";
  const cellCls = "w-full px-2 py-1 text-xs text-right border border-primary/50 rounded bg-card text-foreground font-medium focus:outline-none focus:ring-2 focus:ring-primary";

  const handleCreate = async () => {
    if (!name.trim()) {
      toast.error("Inserisci il nome della startup");
      return;
    }
    if ((capitale || 0) <= 0) {
      toast.error("Inserisci il capitale sociale di partenza");
      return;
    }
    setLoading(true);
    try {
      const foundingYear = years[0];
      // A startup has no operating history: the scenario base year is a pure
      // OPENING balance the year BEFORE the plan starts, carrying only the
      // paid-in capital (cash = capital, no P&L). Every plan year — INCLUDING
      // the first (founding) year — is then a fully editable forecast column, so
      // 2026 can be compiled exactly like 2027/2028: economics from the wizard
      // drivers and patrimonial drivers/TFR from the Patrimoniali tab. The TFR
      // fund (sp15) therefore starts at 0 and accrues from the first plan year.
      const openingYear = foundingYear - 1;
      const cap = round2(capitale || 0);
      const company = await createCompany({ name: name.trim(), sector: 3 });
      await createFinancialYear(company.id, openingYear);
      // Opening balance sheet: paid-in capital only (Attivo cash == Passivo
      // capitale, no result). The income statement stays empty.
      await updateBalanceSheet(company.id, openingYear, {
        sp11_capitale: cap,
        sp09_disponibilita_liquide: cap,
      });

      const scenario = await createBudgetScenario(company.id, {
        company_id: company.id,
        name: name.trim(),
        base_year: openingYear,
        description: description.trim() || undefined,
        is_active: 1,
      });

      // Every plan year → one assumptions row, driven by absolute CE overrides.
      for (const year of years) {
        const d = deriveYear(year);
        await createBudgetAssumptions(
          company.id,
          scenario.id,
          buildStartupAssumption(scenario.id, year, {
            ce01: d.ricavi,
            ce06: d.servizi,
            ce08: d.personale,
          })
        );
      }

      await generateForecast(company.id, scenario.id, false);
      await refreshCompanies();
      setSelectedCompanyId(company.id);
      toast.success("Business plan creato! Completa le variabili patrimoniali.");
      onCreated(scenario);
    } catch (err: any) {
      console.error("Error creating startup business plan:", err);
      toast.error(getErrorMessage(err, "Impossibile creare il business plan"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Rocket className="h-5 w-5" /> Nuovo business plan startup
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        <Alert>
          <Info className="h-4 w-4" />
          <AlertDescription>
            Una startup non ha un bilancio storico. Inserisci l&apos;identità, il
            capitale di partenza e i driver economici attesi per ogni anno: le
            variabili economiche del previsionale vengono generate in automatico.
          </AlertDescription>
        </Alert>

        {/* Identity */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label htmlFor="startup-name">Nome startup *</Label>
            <Input
              id="startup-name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="es. La mia Startup S.r.l."
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="startup-desc">Descrizione</Label>
            <Textarea
              id="startup-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Breve descrizione dell'attività..."
              rows={2}
            />
          </div>
        </div>

        {/* Technical: capital + horizon */}
        <div className="border-t border-border pt-4 grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label htmlFor="startup-capitale">Capitale sociale di partenza (€) *</Label>
            <input id="startup-capitale" type="number" step="1000" min="0" className={numCls}
              value={capitale} onChange={(e) => setCapitale(parseFloat(e.target.value) || 0)} />
            <p className="text-xs text-muted-foreground">
              Conferito come liquidità: costituisce il patrimonio netto e la cassa
              dello stato patrimoniale di partenza.
            </p>
          </div>
          <div className="space-y-2">
            <Label>Periodo di piano</Label>
            <div className="flex gap-2">
              {([3, 5] as const).map((p) => (
                <Button
                  key={p}
                  type="button"
                  variant={period === p ? "default" : "outline"}
                  onClick={() => setPeriod(p)}
                  className="flex-1"
                >
                  {p} anni
                </Button>
              ))}
            </div>
            <p className="text-xs text-muted-foreground">
              {period === 3
                ? `Anno corrente (${currentYear}) e i 2 successivi.`
                : `Anno corrente (${currentYear}) e i 4 successivi.`}
            </p>
          </div>
        </div>

        {/* Per-year economic drivers */}
        <div className="border-t border-border pt-4">
          <p className="text-sm font-semibold text-foreground mb-3">
            Driver economici attesi per anno
          </p>
          <div className="overflow-x-auto">
            <table className="min-w-full text-xs border border-border divide-y divide-border">
              <thead className="bg-muted">
                <tr>
                  <th className="px-3 py-2 text-left font-semibold text-foreground border-r border-border">Voce</th>
                  {years.map((year, i) => (
                    <th key={year} className="px-3 py-2 text-center font-semibold text-foreground border-r border-border" style={{ minWidth: "120px" }}>
                      {year}
                      {i === 0 && <span className="block text-[10px] font-normal text-muted-foreground">anno corrente</span>}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="bg-card divide-y divide-border">
                <tr>
                  <td className="px-3 py-2 font-medium text-foreground border-r border-border">Ricavi (€)</td>
                  {years.map((year) => (
                    <td key={year} className="px-2 py-1 border-r border-border">
                      <input type="number" step="1000" min="0" className={cellCls}
                        value={getVal(year, "ricavi")}
                        onChange={(e) => setVal(year, "ricavi", parseFloat(e.target.value) || 0)} />
                    </td>
                  ))}
                </tr>
                <tr>
                  <td className="px-3 py-2 font-medium text-foreground border-r border-border">Margine EBITDA (%)</td>
                  {years.map((year) => (
                    <td key={year} className="px-2 py-1 border-r border-border">
                      <input type="number" step="0.5" className={cellCls}
                        value={getVal(year, "margine")}
                        onChange={(e) => setVal(year, "margine", parseFloat(e.target.value) || 0)} />
                    </td>
                  ))}
                </tr>
                <tr>
                  <td className="px-3 py-2 font-medium text-foreground border-r border-border">Costi del personale (€)</td>
                  {years.map((year) => (
                    <td key={year} className="px-2 py-1 border-r border-border">
                      <input type="number" step="1000" min="0" className={cellCls}
                        value={getVal(year, "personale")}
                        onChange={(e) => setVal(year, "personale", parseFloat(e.target.value) || 0)} />
                    </td>
                  ))}
                </tr>
                <tr>
                  <td className="px-3 py-2 font-medium text-foreground border-r border-border">Numero dipendenti</td>
                  {years.map((year) => (
                    <td key={year} className="px-2 py-1 border-r border-border">
                      <input type="number" step="1" min="0" className={cellCls}
                        value={getVal(year, "dipendenti")}
                        onChange={(e) => setVal(year, "dipendenti", parseInt(e.target.value) || 0)} />
                    </td>
                  ))}
                </tr>
                {/* Derived read-only preview */}
                <tr className="bg-muted/40">
                  <td className="px-3 py-2 text-muted-foreground border-r border-border">EBITDA (€) — calcolato</td>
                  {years.map((year) => (
                    <td key={year} className="px-3 py-2 text-right text-muted-foreground border-r border-border">
                      {formatCurrency(deriveYear(year).ebitda)}
                    </td>
                  ))}
                </tr>
                <tr className="bg-muted/40">
                  <td className="px-3 py-2 text-muted-foreground border-r border-border">Costi per servizi (€) — residuo</td>
                  {years.map((year) => (
                    <td key={year} className="px-3 py-2 text-right text-muted-foreground border-r border-border">
                      {formatCurrency(deriveYear(year).servizi)}
                    </td>
                  ))}
                </tr>
              </tbody>
            </table>
          </div>
          <p className="text-xs text-muted-foreground mt-2">
            EBITDA = Ricavi × Margine%. I costi operativi residui (Ricavi − EBITDA
            − Personale) sono imputati ai Costi per servizi (B.7).
          </p>
        </div>

        <div className="flex justify-end pt-2">
          <Button onClick={handleCreate} disabled={loading}>
            {loading ? (
              <><Loader2 className="h-4 w-4 animate-spin" /> Creazione...</>
            ) : (
              <><Rocket className="h-4 w-4" /> Crea business plan e continua</>
            )}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

// Scenarios List Component
function ScenariosList({
  scenarios,
  loading,
  companyName,
  onEdit,
  onDelete,
  onRegenerate,
}: {
  scenarios: BudgetScenario[];
  loading: boolean;
  companyName: string | null;
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
                {companyName && (
                  <Badge variant="secondary" className="mb-2">{companyName}</Badge>
                )}
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
  activeTab,
  setActiveTab,
  startup,
  onSaved,
  onCancel,
}: {
  companyId: number;
  years: number[];
  scenario: BudgetScenario | null;
  activeTab: string;
  setActiveTab: (tab: string) => void;
  startup: boolean;
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
            intangible_investments: a.intangible_investments,
            tangible_investments: a.tangible_investments,
            asset_disposal_nbv: a.asset_disposal_nbv,
            asset_disposal_proceeds: a.asset_disposal_proceeds,
            dso_days: a.dso_days,
            dio_days: a.dio_days,
            dpo_days: a.dpo_days,
            existing_debt_repayment_years: a.existing_debt_repayment_years,
            altri_finanz_repayment_years: a.altri_finanz_repayment_years,
            cash_sweep_enabled: a.cash_sweep_enabled ?? false,
            cash_sweep_min_cash: a.cash_sweep_min_cash,
            tfr_accrual_suspended: a.tfr_accrual_suspended ?? false,
            previdenza_scales_with_personnel: a.previdenza_scales_with_personnel ?? false,
            receivables_short_growth_pct: a.receivables_short_growth_pct,
            receivables_long_growth_pct: a.receivables_long_growth_pct,
            payables_short_growth_pct: a.payables_short_growth_pct,
            tax_rate: a.tax_rate,
            fixed_materials_percentage: a.fixed_materials_percentage,
            fixed_services_percentage: a.fixed_services_percentage,
            depreciation_rate: a.depreciation_rate,
            depreciation_rate_intangible: a.depreciation_rate_intangible,
            financing_amount: a.financing_amount,
            financing_duration_years: a.financing_duration_years,
            financing_interest_rate: a.financing_interest_rate,
            sp01_growth_pct: a.sp01_growth_pct,
            sp04_growth_pct: a.sp04_growth_pct,
            sp08_growth_pct: a.sp08_growth_pct,
            sp10_growth_pct: a.sp10_growth_pct,
            sp14_growth_pct: a.sp14_growth_pct,
            sp16e_growth_pct: a.sp16e_growth_pct,
            sp16f_growth_pct: a.sp16f_growth_pct,
            sp16g_growth_pct: a.sp16g_growth_pct,
            sp17d_growth_pct: a.sp17d_growth_pct,
            sp17e_growth_pct: a.sp17e_growth_pct,
            sp17f_growth_pct: a.sp17f_growth_pct,
            sp17g_growth_pct: a.sp17g_growth_pct,
            sp18_growth_pct: a.sp18_growth_pct,
            ce01_override: a.ce01_override,
            ce05_override: a.ce05_override,
            ce06_override: a.ce06_override,
            ce07_override: a.ce07_override,
            ce08_override: a.ce08_override,
            ce02_override: a.ce02_override,
            ce03_override: a.ce03_override,
            ce03a_override: a.ce03a_override,
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
      // Initialize with defaults. New scenarios start with all CE overrides NULL
      // (absolute P&L edits live on /forecast/income); dead fields
      // (investments, receivables_short/payables_short) are no longer written.
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
          intangible_investments: 0,
          tangible_investments: 0,
          asset_disposal_nbv: null,
          asset_disposal_proceeds: null,
          receivables_long_growth_pct: 0,
          dso_days: null,
          dio_days: null,
          dpo_days: null,
          existing_debt_repayment_years: null,
          altri_finanz_repayment_years: null,
          cash_sweep_enabled: false,
          cash_sweep_min_cash: null,
          tfr_accrual_suspended: false,
          previdenza_scales_with_personnel: false,
          tax_rate: 27.9,
          fixed_materials_percentage: 0,
          fixed_services_percentage: 0,
          depreciation_rate: 20,
          depreciation_rate_intangible: 20,
          financing_amount: 0,
          financing_duration_years: 5,
          financing_interest_rate: 3,
        };
      });
      setAssumptions(defaultAssumptions);
    }
  }, [scenario, companyId]);

  // Auto-generator state
  const [inflationRate, setInflationRate] = useState(2.5);
  const [showAutoGen, setShowAutoGen] = useState(false);

  const updateAssumption = useCallback((year: number, field: string, value: number | boolean | null) => {
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

      // ONE call: bulk upsert (delete-all + reinsert server-side) + generation.
      // Rows are FULL objects (hydration map for existing scenarios includes CE
      // overrides and legacy fields) so overrides made on /forecast/income
      // survive this save. Never pass clear_overrides here.
      const rows = forecastYears
        .filter((year) => assumptions[year])
        .map((year) => ({
          ...assumptions[year],
          scenario_id: savedScenario.id,
          forecast_year: year,
        }));
      const result = await bulkUpsertAssumptions(companyId, savedScenario.id, {
        assumptions: rows,
        auto_generate: true,
      });

      // The backend returns success:true even when generation fails
      // (assumptions_service.py:210-217) — check the explicit flag.
      if (result?.forecast_generated === false) {
        toast.warning(
          result?.message ?? "Ipotesi salvate, ma il previsionale non è stato generato"
        );
      } else {
        toast.success("Scenario salvato e previsionale calcolato con successo!");
      }
      onSaved();
    } catch (err: any) {
      console.error("Error saving scenario:", err);
      toast.error(getErrorMessage(err, "Impossibile salvare lo scenario"));
    } finally {
      setLoading(false);
    }
  };

  const historicalYears = [...new Set(years)].filter(y => y <= baseYear).sort((a, b) => a - b);

  return (
    <div>
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="mb-4">
          <TabsTrigger value="info" className="gap-1.5">
            <ClipboardList className="h-4 w-4" />
            Informazioni
          </TabsTrigger>
          <TabsTrigger value="ipotesi" className="gap-1.5">
            <FileSpreadsheet className="h-4 w-4" />
            Ipotesi
          </TabsTrigger>
        </TabsList>

        <TabsContent value="info">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                {scenario ? (
                  <><Pencil className="h-5 w-5" /> Modifica Scenario: {scenario.name}</>
                ) : (
                  <><Plus className="h-5 w-5" /> Nuovo Scenario Budget</>
                )}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
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

              {startup ? (
                <div className="border-t border-border pt-6 mb-6">
                  <p className="text-sm text-muted-foreground">
                    Periodo di piano: <strong>{numYears} anni</strong> (
                    {forecastYears[0]}–{forecastYears[forecastYears.length - 1]}),
                    tutti compilabili. Apertura {baseYear}: solo capitale sociale
                    versato. Le variabili economiche sono generate automaticamente
                    dai driver inseriti.
                  </p>
                </div>
              ) : (
                <>
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
                </>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="ipotesi">
          <div className="space-y-4">
            {startup && (
              <StartupEconomicsRecap
                forecastYears={forecastYears}
                assumptions={assumptions}
              />
            )}

            <AssumptionsGrid
              rows={startup
                ? ESSENTIAL_ROWS.filter((r) => r.kind !== "pct" || r.key.startsWith("fin-"))
                : ESSENTIAL_ROWS}
              historicalYears={historicalYears}
              forecastYears={forecastYears}
              historicalData={historicalData}
              assumptions={assumptions}
              onUpdate={updateAssumption}
            />

            <p className="text-xs text-muted-foreground">
              Per modificare singole voci del CE previsionale (valori assoluti) vai a{" "}
              <Link href="/forecast/income" className="underline text-primary">
                CE Previsionale
              </Link>
              .
            </p>

            <Accordion type="single" collapsible>
              <AccordionItem value="avanzate">
                <AccordionTrigger className="text-sm font-semibold">
                  Avanzate
                </AccordionTrigger>
                <AccordionContent className="space-y-6">
                  {ADVANCED_GROUPS.map((group) => (
                    <div key={group.title}>
                      <h4 className="text-xs font-bold uppercase text-muted-foreground mb-2">
                        {group.title}
                      </h4>
                      {group.title === "Fiscale" && (
                        <p className="text-xs text-muted-foreground mb-2">
                          {(() => {
                            const eff = historicalData[baseYear]?.income
                              ? computeEffectiveTaxRate(historicalData[baseYear].income)
                              : null;
                            return eff !== null
                              ? `Aliquota effettiva dall'anno base ${baseYear}: ≈ ${eff}% (usata automaticamente dal motore)`
                              : "Aliquota effettiva dall'anno base non derivabile: il motore usa il valore qui sotto";
                          })()}
                        </p>
                      )}
                      <AssumptionsGrid
                        rows={group.rows}
                        historicalYears={historicalYears}
                        forecastYears={forecastYears}
                        historicalData={historicalData}
                        assumptions={assumptions}
                        onUpdate={updateAssumption}
                        showHistorical={false}
                      />
                    </div>
                  ))}
                </AccordionContent>
              </AccordionItem>
            </Accordion>
          </div>
        </TabsContent>
      </Tabs>

      {/* Actions - always visible */}
      <div className="flex justify-center gap-4 pt-6 mt-6 border-t border-border">
        <Button variant="outline" onClick={onCancel}>
          <X className="h-4 w-4" />
          {scenario ? "Annulla" : "Indietro"}
        </Button>
        <Button onClick={handleSave} disabled={loading}>
          {loading ? (
            <><Loader2 className="h-4 w-4 animate-spin" /> Salvataggio...</>
          ) : (
            <><Save className="h-4 w-4" /> Salva e Calcola Previsionale</>
          )}
        </Button>
      </div>
    </div>
  );
}

// Startup economics recap (read-only): the economic variables of a startup
// business plan are generated automatically from the per-year drivers entered
// in the wizard (revenue / EBITDA margin / personnel, stored as absolute CE
// overrides). This shows the resulting P&L drivers per year — no editing here.
function StartupEconomicsRecap({
  forecastYears,
  assumptions,
}: {
  forecastYears: number[];
  assumptions: Record<number, Partial<BudgetAssumptionsCreate>>;
}) {
  // Every plan year is now a forecast column (the base year is a capital-only
  // opening with no economics), so the recap lists the plan years directly.
  const years = forecastYears;

  const valuesFor = (year: number) => {
    const a = assumptions[year];
    const ricavi = Number(a?.ce01_override ?? 0);
    const servizi = Number(a?.ce06_override ?? 0);
    const personale = Number(a?.ce08_override ?? 0);
    const ebitda = ricavi - servizi - personale;
    const margine = ricavi ? (ebitda / ricavi) * 100 : 0;
    return { ricavi, servizi, personale, ebitda, margine };
  };

  const rows: { label: string; get: (v: ReturnType<typeof valuesFor>) => string; strong?: boolean }[] = [
    { label: "Ricavi", get: (v) => formatCurrency(v.ricavi) },
    { label: "Costi per servizi (B.7)", get: (v) => formatCurrency(v.servizi) },
    { label: "Costi del personale (B.9)", get: (v) => formatCurrency(v.personale) },
    { label: "EBITDA", get: (v) => formatCurrency(v.ebitda), strong: true },
    { label: "Margine EBITDA %", get: (v) => `${v.margine.toFixed(1)}%`, strong: true },
  ];

  return (
    <div className="space-y-4">
      <Alert>
        <Info className="h-4 w-4" />
        <AlertDescription>
          Le variabili economiche sono generate automaticamente dai driver
          inseriti nel business plan. Per modificarle, agisci sui driver o edita
          le voci di conto economico dalla pagina Previsionale &gt; Conto Economico.
        </AlertDescription>
      </Alert>
      <div className="overflow-x-auto">
        <table className="min-w-full text-xs border border-border divide-y divide-border">
          <thead className="bg-muted">
            <tr>
              <th className="px-3 py-2 text-left font-semibold text-foreground border-r border-border">Voce</th>
              {years.map((year, i) => (
                <th key={year} className="px-3 py-2 text-center font-semibold text-foreground border-r border-border" style={{ minWidth: "120px" }}>
                  {year}
                  {i === 0 && <span className="block text-[10px] font-normal text-muted-foreground">anno corrente</span>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="bg-card divide-y divide-border">
            {rows.map((row) => (
              <tr key={row.label} className={row.strong ? "bg-muted/40" : ""}>
                <td className={`px-3 py-2 border-r border-border ${row.strong ? "font-semibold text-foreground" : "text-foreground"}`}>{row.label}</td>
                {years.map((year) => (
                  <td key={year} className={`px-3 py-2 text-right border-r border-border ${row.strong ? "font-semibold text-foreground" : "text-muted-foreground"}`}>
                    {row.get(valuesFor(year))}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
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
  updateAssumption: (year: number, field: string, value: number | boolean | null) => void;
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
    // BS: only receivables_long has an engine effect (sp07). The old
    // receivables_short/payables_short fields are dead (no engine reads) —
    // working capital scales via DSO/DIO/DPO instead.
    for (const year of forecastYears) {
      updateAssumption(year, "receivables_long_growth_pct", Math.round(inflationRate * 100) / 100);
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
                  <td className="px-3 py-1.5 font-medium text-foreground">Crediti oltre 12 mesi</td>
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
