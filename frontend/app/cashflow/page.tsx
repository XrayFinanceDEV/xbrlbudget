"use client";

import { useState, useEffect } from "react";
import { useApp } from "@/contexts/AppContext";
import { getDetailedCashFlow } from "@/lib/api";
import { formatCurrency } from "@/lib/formatters";
import { cn } from "@/lib/utils";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Wallet, AlertTriangle, Loader2, CheckCircle2, Info } from "lucide-react";
import type { MultiYearDetailedCashFlow, DetailedCashFlowStatement } from "@/types/api";

export default function CashflowPage() {
  const { selectedCompanyId } = useApp();
  const [cashflowData, setCashflowData] = useState<MultiYearDetailedCashFlow | null>(null);
  const [selectedScenario, setSelectedScenario] = useState<number | null>(null);
  const [scenarios, setScenarios] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load scenarios when company changes
  useEffect(() => {
    if (!selectedCompanyId) {
      setScenarios([]);
      setSelectedScenario(null);
      setCashflowData(null);
      return;
    }
    loadScenarios();
  }, [selectedCompanyId]);

  // Load cashflow when scenario changes
  useEffect(() => {
    if (selectedScenario && selectedCompanyId) {
      loadCashflow();
    }
  }, [selectedScenario, selectedCompanyId]);

  const loadScenarios = async () => {
    if (!selectedCompanyId) return;

    try {
      const response = await fetch(
        `http://localhost:8000/api/v1/companies/${selectedCompanyId}/scenarios`
      );
      const data = await response.json();
      setScenarios(data);

      // Auto-select first active scenario
      const activeScenario = data.find((s: any) => s.is_active === 1);
      if (activeScenario) {
        setSelectedScenario(activeScenario.id);
      }
    } catch (err) {
      console.error("Error loading scenarios:", err);
    }
  };

  const loadCashflow = async () => {
    if (!selectedCompanyId || !selectedScenario) return;

    try {
      setLoading(true);
      setError(null);

      const data = await getDetailedCashFlow(selectedCompanyId, selectedScenario);
      setCashflowData(data);
    } catch (err: any) {
      console.error("Error loading cashflow:", err);
      if (err.response?.status === 404) {
        setError("Dati non disponibili per questo scenario");
      } else {
        setError("Impossibile caricare il rendiconto finanziario");
      }
    } finally {
      setLoading(false);
    }
  };

  if (loading && !cashflowData) {
    return (
      <div className="max-w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="flex flex-col items-center justify-center h-64 gap-3">
          <Loader2 className="h-12 w-12 animate-spin text-primary" />
          <p className="text-sm text-muted-foreground">Caricamento...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <PageHeader
          title="Rendiconto Finanziario"
          icon={<Wallet className="h-6 w-6" />}
        />
        <Alert>
          <AlertTriangle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      </div>
    );
  }

  if (!selectedCompanyId) {
    return (
      <div className="max-w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <PageHeader
          title="Rendiconto Finanziario"
          icon={<Wallet className="h-6 w-6" />}
        />
        <Alert>
          <Info className="h-4 w-4" />
          <AlertDescription>
            Seleziona un&apos;azienda per visualizzare il rendiconto finanziario
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  if (!cashflowData) {
    return (
      <div className="max-w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <PageHeader
          title="Rendiconto Finanziario"
          icon={<Wallet className="h-6 w-6" />}
        />

        {/* Scenario Selector */}
        {scenarios.length > 0 && (
          <Card className="mb-6">
            <CardContent className="pt-6">
              <label className="block text-sm font-medium text-muted-foreground mb-2">
                Seleziona Scenario:
              </label>
              <select
                className="flex h-9 w-full max-w-md rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                value={selectedScenario || ""}
                onChange={(e) => setSelectedScenario(parseInt(e.target.value))}
              >
                <option value="">-- Seleziona uno scenario --</option>
                {scenarios.map((scenario) => (
                  <option key={scenario.id} value={scenario.id}>
                    {scenario.name} (Base: {scenario.base_year})
                    {scenario.is_active ? " - Attivo" : ""}
                  </option>
                ))}
              </select>
            </CardContent>
          </Card>
        )}

        {scenarios.length === 0 && (
          <Alert>
            <Info className="h-4 w-4" />
            <AlertDescription>
              Nessuno scenario disponibile. Crea uno scenario budget per visualizzare il rendiconto finanziario.
            </AlertDescription>
          </Alert>
        )}
      </div>
    );
  }

  // Separate historical and forecast years
  const baseYear = cashflowData.base_year;
  const allYears = cashflowData.cashflows.map((cf) => cf.year);
  const historicalYears = allYears.filter((y) => y <= baseYear);
  const forecastYears = allYears.filter((y) => y > baseYear);

  // Helper to get values
  const getValues = (
    extractor: (cf: DetailedCashFlowStatement) => number,
    years: number[]
  ) => years.map((year) => {
    const cf = cashflowData.cashflows.find((c) => c.year === year);
    return cf ? extractor(cf) : 0;
  });

  // Row component matching forecast/balance style
  const CashFlowRow = ({
    label,
    historicalValues,
    forecastValues,
    isSubtotal = false,
    isTotal = false,
    isSection = false,
    indent = 0,
  }: {
    label: string;
    historicalValues: number[];
    forecastValues: number[];
    isSubtotal?: boolean;
    isTotal?: boolean;
    isSection?: boolean;
    indent?: number;
  }) => {
    const bgClass = isTotal
      ? "bg-muted font-bold"
      : isSection
      ? "bg-primary/15 font-bold"
      : isSubtotal
      ? "bg-primary/10 font-semibold"
      : "hover:bg-muted/50";

    return (
      <tr className={bgClass}>
        <td
          className="px-4 py-2 text-sm text-foreground border-r border-border"
          style={{ paddingLeft: indent > 0 ? `${1 + indent * 1.5}rem` : undefined }}
        >
          {label}
        </td>
        {/* Historical columns */}
        {historicalValues.map((value, i) => {
          const isNegative = value < 0;
          return (
            <td
              key={`hist-${i}`}
              className={cn(
                "px-4 py-2 text-sm text-right border-r border-border",
                isNegative ? "text-destructive font-medium" : "text-foreground",
                (isTotal || isSubtotal || isSection) && "font-semibold"
              )}
            >
              {isSection && !value ? "" : formatCurrency(value)}
            </td>
          );
        })}
        {/* Forecast columns */}
        {forecastValues.map((value, i) => {
          const isNegative = value < 0;
          return (
            <td
              key={`forecast-${i}`}
              className={cn(
                "px-4 py-2 text-sm text-right border-r border-border",
                isNegative ? "text-destructive font-medium" : "text-foreground",
                (isTotal || isSubtotal || isSection) && "font-semibold"
              )}
            >
              {isSection && !value ? "" : formatCurrency(value)}
            </td>
          );
        })}
      </tr>
    );
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <PageHeader
        title="Rendiconto Finanziario (Metodo Indiretto)"
        description="Analisi dettagliata dei flussi di cassa secondo principi contabili italiani"
        icon={<Wallet className="h-6 w-6" />}
      />

      {/* Scenario Selector */}
      {scenarios.length > 0 && (
        <Card className="mb-6">
          <CardContent className="pt-6 pb-4">
            <label className="block text-sm font-medium text-muted-foreground mb-2">
              Scenario Budget:
            </label>
            <select
              className="flex h-9 w-full max-w-md rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              value={selectedScenario || ""}
              onChange={(e) => setSelectedScenario(parseInt(e.target.value))}
            >
              {scenarios.map((scenario) => (
                <option key={scenario.id} value={scenario.id}>
                  {scenario.name} - Anno Base: {scenario.base_year}
                  {scenario.is_active ? " (Attivo)" : ""}
                </option>
              ))}
            </select>
          </CardContent>
        </Card>
      )}

      {/* Detailed Cash Flow Table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-xl">
            Rendiconto Finanziario: Confronto Storico vs Previsionale
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-border border border-border">
              <thead className="bg-muted">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-bold text-foreground uppercase border-r border-border">
                    RENDICONTO FINANZIARIO (METODO INDIRETTO)
                  </th>
                  {historicalYears.map((year) => (
                    <th
                      key={year}
                      className="px-4 py-3 text-center text-xs font-bold text-foreground uppercase border-r border-border bg-muted"
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
                {/* A. OPERATING ACTIVITIES */}
                <CashFlowRow
                  label="A. Flussi finanziari derivanti dell'attivit\u00e0 operativa"
                  historicalValues={Array(historicalYears.length).fill(0)}
                  forecastValues={Array(forecastYears.length).fill(0)}
                  isSection={true}
                />

                <CashFlowRow
                  label="Utile (perdita) dell'esercizio"
                  historicalValues={getValues((cf) => cf.operating_activities.start.net_profit, historicalYears)}
                  forecastValues={getValues((cf) => cf.operating_activities.start.net_profit, forecastYears)}
                  indent={1}
                />
                <CashFlowRow
                  label="Imposte sul reddito"
                  historicalValues={getValues((cf) => cf.operating_activities.start.income_taxes, historicalYears)}
                  forecastValues={getValues((cf) => cf.operating_activities.start.income_taxes, forecastYears)}
                  indent={1}
                />
                <CashFlowRow
                  label="Interessi passivi/(interessi attivi)"
                  historicalValues={getValues((cf) => cf.operating_activities.start.interest_expense_income, historicalYears)}
                  forecastValues={getValues((cf) => cf.operating_activities.start.interest_expense_income, forecastYears)}
                  indent={1}
                />
                <CashFlowRow
                  label="(Dividendi)"
                  historicalValues={getValues((cf) => cf.operating_activities.start.dividends, historicalYears)}
                  forecastValues={getValues((cf) => cf.operating_activities.start.dividends, forecastYears)}
                  indent={1}
                />
                <CashFlowRow
                  label="(Plusvalenze)/minusvalenze derivanti dalla cessione di attivit\u00e0"
                  historicalValues={getValues((cf) => cf.operating_activities.start.capital_gains_losses, historicalYears)}
                  forecastValues={getValues((cf) => cf.operating_activities.start.capital_gains_losses, forecastYears)}
                  indent={1}
                />
                <CashFlowRow
                  label="1. Utile (perdita) dell'esercizio prima d'imposte sul reddito, interessi, dividendi e plus/minusvalenze da cessione"
                  historicalValues={getValues((cf) => cf.operating_activities.start.profit_before_adjustments, historicalYears)}
                  forecastValues={getValues((cf) => cf.operating_activities.start.profit_before_adjustments, forecastYears)}
                  isSubtotal={true}
                  indent={1}
                />

                <CashFlowRow
                  label="Rettifiche per elementi non monetari che non hanno avuto contropartita nel capitale circolante netto"
                  historicalValues={Array(historicalYears.length).fill(0)}
                  forecastValues={Array(forecastYears.length).fill(0)}
                  indent={1}
                />
                <CashFlowRow
                  label="Accantonamenti ai fondi"
                  historicalValues={getValues((cf) => cf.operating_activities.non_cash_adjustments.provisions, historicalYears)}
                  forecastValues={getValues((cf) => cf.operating_activities.non_cash_adjustments.provisions, forecastYears)}
                  indent={2}
                />
                <CashFlowRow
                  label="Ammortamenti delle immobilizzazioni"
                  historicalValues={getValues((cf) => cf.operating_activities.non_cash_adjustments.depreciation_amortization, historicalYears)}
                  forecastValues={getValues((cf) => cf.operating_activities.non_cash_adjustments.depreciation_amortization, forecastYears)}
                  indent={2}
                />
                <CashFlowRow
                  label="Svalutazioni per perdite durevoli di valore"
                  historicalValues={getValues((cf) => cf.operating_activities.non_cash_adjustments.write_downs, historicalYears)}
                  forecastValues={getValues((cf) => cf.operating_activities.non_cash_adjustments.write_downs, forecastYears)}
                  indent={2}
                />
                <CashFlowRow
                  label="Totale rettifiche per elementi non monetari che non hanno avuto contropartita nel capitale circolante netto"
                  historicalValues={getValues((cf) => cf.operating_activities.non_cash_adjustments.total, historicalYears)}
                  forecastValues={getValues((cf) => cf.operating_activities.non_cash_adjustments.total, forecastYears)}
                  isSubtotal={true}
                  indent={1}
                />

                <CashFlowRow
                  label="2. Flusso finanziario prima delle variazioni del ccn"
                  historicalValues={getValues((cf) => cf.operating_activities.cashflow_before_wc, historicalYears)}
                  forecastValues={getValues((cf) => cf.operating_activities.cashflow_before_wc, forecastYears)}
                  isSubtotal={true}
                  indent={1}
                />

                <CashFlowRow
                  label="Variazioni del capitale circolante netto"
                  historicalValues={Array(historicalYears.length).fill(0)}
                  forecastValues={Array(forecastYears.length).fill(0)}
                  indent={1}
                />
                <CashFlowRow
                  label="Decremento/(incremento) delle rimanenze"
                  historicalValues={getValues((cf) => cf.operating_activities.working_capital_changes.delta_inventory, historicalYears)}
                  forecastValues={getValues((cf) => cf.operating_activities.working_capital_changes.delta_inventory, forecastYears)}
                  indent={2}
                />
                <CashFlowRow
                  label="Decremento/(incremento) dei crediti entro esercizio precedente"
                  historicalValues={getValues((cf) => cf.operating_activities.working_capital_changes.delta_receivables, historicalYears)}
                  forecastValues={getValues((cf) => cf.operating_activities.working_capital_changes.delta_receivables, forecastYears)}
                  indent={2}
                />
                <CashFlowRow
                  label="Incremento/(decremento) dei debiti entro esercizio precedente"
                  historicalValues={getValues((cf) => cf.operating_activities.working_capital_changes.delta_payables, historicalYears)}
                  forecastValues={getValues((cf) => cf.operating_activities.working_capital_changes.delta_payables, forecastYears)}
                  indent={2}
                />
                <CashFlowRow
                  label="Decremento/(incremento) ratei e risconti attivi"
                  historicalValues={getValues((cf) => cf.operating_activities.working_capital_changes.delta_accruals_deferrals_active, historicalYears)}
                  forecastValues={getValues((cf) => cf.operating_activities.working_capital_changes.delta_accruals_deferrals_active, forecastYears)}
                  indent={2}
                />
                <CashFlowRow
                  label="Incremento/(decremento) ratei e risconti passivi"
                  historicalValues={getValues((cf) => cf.operating_activities.working_capital_changes.delta_accruals_deferrals_passive, historicalYears)}
                  forecastValues={getValues((cf) => cf.operating_activities.working_capital_changes.delta_accruals_deferrals_passive, forecastYears)}
                  indent={2}
                />
                <CashFlowRow
                  label="Altri incrementi/(decrementi) del capitale circolante netto"
                  historicalValues={getValues((cf) => cf.operating_activities.working_capital_changes.other_wc_changes, historicalYears)}
                  forecastValues={getValues((cf) => cf.operating_activities.working_capital_changes.other_wc_changes, forecastYears)}
                  indent={2}
                />
                <CashFlowRow
                  label="Totale variazioni del capitale circolante netto"
                  historicalValues={getValues((cf) => cf.operating_activities.working_capital_changes.total, historicalYears)}
                  forecastValues={getValues((cf) => cf.operating_activities.working_capital_changes.total, forecastYears)}
                  isSubtotal={true}
                  indent={1}
                />

                <CashFlowRow
                  label="3. Flusso finanziario dopo le variazioni del ccn"
                  historicalValues={getValues((cf) => cf.operating_activities.cashflow_after_wc, historicalYears)}
                  forecastValues={getValues((cf) => cf.operating_activities.cashflow_after_wc, forecastYears)}
                  isSubtotal={true}
                  indent={1}
                />

                <CashFlowRow
                  label="Altre rettifiche"
                  historicalValues={Array(historicalYears.length).fill(0)}
                  forecastValues={Array(forecastYears.length).fill(0)}
                  indent={1}
                />
                <CashFlowRow
                  label="Interessi incassati/(pagati)"
                  historicalValues={getValues((cf) => cf.operating_activities.cash_adjustments.interest_paid_received, historicalYears)}
                  forecastValues={getValues((cf) => cf.operating_activities.cash_adjustments.interest_paid_received, forecastYears)}
                  indent={2}
                />
                <CashFlowRow
                  label="(Imposte sul reddito pagate)"
                  historicalValues={getValues((cf) => cf.operating_activities.cash_adjustments.taxes_paid, historicalYears)}
                  forecastValues={getValues((cf) => cf.operating_activities.cash_adjustments.taxes_paid, forecastYears)}
                  indent={2}
                />
                <CashFlowRow
                  label="Dividendi incassati"
                  historicalValues={getValues((cf) => cf.operating_activities.cash_adjustments.dividends_received, historicalYears)}
                  forecastValues={getValues((cf) => cf.operating_activities.cash_adjustments.dividends_received, forecastYears)}
                  indent={2}
                />
                <CashFlowRow
                  label="(Utilizzo dei fondi)"
                  historicalValues={getValues((cf) => cf.operating_activities.cash_adjustments.use_of_provisions, historicalYears)}
                  forecastValues={getValues((cf) => cf.operating_activities.cash_adjustments.use_of_provisions, forecastYears)}
                  indent={2}
                />
                <CashFlowRow
                  label="Altri incassi/(pagamenti)"
                  historicalValues={getValues((cf) => cf.operating_activities.cash_adjustments.other_cash_changes, historicalYears)}
                  forecastValues={getValues((cf) => cf.operating_activities.cash_adjustments.other_cash_changes, forecastYears)}
                  indent={2}
                />
                <CashFlowRow
                  label="Totale altre rettifiche"
                  historicalValues={getValues((cf) => cf.operating_activities.cash_adjustments.total, historicalYears)}
                  forecastValues={getValues((cf) => cf.operating_activities.cash_adjustments.total, forecastYears)}
                  isSubtotal={true}
                  indent={1}
                />

                <CashFlowRow
                  label="Flusso finanziario dell'attivit\u00e0 operativa (A)"
                  historicalValues={getValues((cf) => cf.operating_activities.total_operating_cashflow, historicalYears)}
                  forecastValues={getValues((cf) => cf.operating_activities.total_operating_cashflow, forecastYears)}
                  isTotal={true}
                />

                {/* B. INVESTING ACTIVITIES */}
                <CashFlowRow
                  label="B. Flussi finanziari derivanti dall'attivit\u00e0 d'investimento"
                  historicalValues={Array(historicalYears.length).fill(0)}
                  forecastValues={Array(forecastYears.length).fill(0)}
                  isSection={true}
                />

                <CashFlowRow
                  label="Immobilizzazioni materiali"
                  historicalValues={Array(historicalYears.length).fill(0)}
                  forecastValues={Array(forecastYears.length).fill(0)}
                  indent={1}
                />
                <CashFlowRow
                  label="(Investimenti)"
                  historicalValues={getValues((cf) => cf.investing_activities.tangible_assets.investments, historicalYears)}
                  forecastValues={getValues((cf) => cf.investing_activities.tangible_assets.investments, forecastYears)}
                  indent={2}
                />
                <CashFlowRow
                  label="Disinvestimenti"
                  historicalValues={getValues((cf) => cf.investing_activities.tangible_assets.disinvestments, historicalYears)}
                  forecastValues={getValues((cf) => cf.investing_activities.tangible_assets.disinvestments, forecastYears)}
                  indent={2}
                />

                <CashFlowRow
                  label="Immobilizzazioni immateriali"
                  historicalValues={Array(historicalYears.length).fill(0)}
                  forecastValues={Array(forecastYears.length).fill(0)}
                  indent={1}
                />
                <CashFlowRow
                  label="(Investimenti)"
                  historicalValues={getValues((cf) => cf.investing_activities.intangible_assets.investments, historicalYears)}
                  forecastValues={getValues((cf) => cf.investing_activities.intangible_assets.investments, forecastYears)}
                  indent={2}
                />
                <CashFlowRow
                  label="Disinvestimenti"
                  historicalValues={getValues((cf) => cf.investing_activities.intangible_assets.disinvestments, historicalYears)}
                  forecastValues={getValues((cf) => cf.investing_activities.intangible_assets.disinvestments, forecastYears)}
                  indent={2}
                />

                <CashFlowRow
                  label="Attivit\u00e0 finanziarie (immobilizzate e circolanti)"
                  historicalValues={Array(historicalYears.length).fill(0)}
                  forecastValues={Array(forecastYears.length).fill(0)}
                  indent={1}
                />
                <CashFlowRow
                  label="(Investimenti)"
                  historicalValues={getValues((cf) => cf.investing_activities.financial_assets.investments, historicalYears)}
                  forecastValues={getValues((cf) => cf.investing_activities.financial_assets.investments, forecastYears)}
                  indent={2}
                />
                <CashFlowRow
                  label="Disinvestimenti"
                  historicalValues={getValues((cf) => cf.investing_activities.financial_assets.disinvestments, historicalYears)}
                  forecastValues={getValues((cf) => cf.investing_activities.financial_assets.disinvestments, forecastYears)}
                  indent={2}
                />

                <CashFlowRow
                  label="Flusso finanziario dell'attivit\u00e0 di investimento (B)"
                  historicalValues={getValues((cf) => cf.investing_activities.total_investing_cashflow, historicalYears)}
                  forecastValues={getValues((cf) => cf.investing_activities.total_investing_cashflow, forecastYears)}
                  isTotal={true}
                />

                {/* C. FINANCING ACTIVITIES */}
                <CashFlowRow
                  label="C. Flussi finanziari derivanti dall'attivit\u00e0 di finanziamento"
                  historicalValues={Array(historicalYears.length).fill(0)}
                  forecastValues={Array(forecastYears.length).fill(0)}
                  isSection={true}
                />

                <CashFlowRow
                  label="Mezzi di terzi"
                  historicalValues={Array(historicalYears.length).fill(0)}
                  forecastValues={Array(forecastYears.length).fill(0)}
                  indent={1}
                />
                <CashFlowRow
                  label="Incremento mezzi di terzi"
                  historicalValues={getValues((cf) => cf.financing_activities.third_party_funds.increases, historicalYears)}
                  forecastValues={getValues((cf) => cf.financing_activities.third_party_funds.increases, forecastYears)}
                  indent={2}
                />
                <CashFlowRow
                  label="(Decremento mezzi di terzi)"
                  historicalValues={getValues((cf) => cf.financing_activities.third_party_funds.decreases, historicalYears)}
                  forecastValues={getValues((cf) => cf.financing_activities.third_party_funds.decreases, forecastYears)}
                  indent={2}
                />

                <CashFlowRow
                  label="Mezzi propri"
                  historicalValues={Array(historicalYears.length).fill(0)}
                  forecastValues={Array(forecastYears.length).fill(0)}
                  indent={1}
                />
                <CashFlowRow
                  label="Incrementi mezzi propri"
                  historicalValues={getValues((cf) => cf.financing_activities.own_funds.increases, historicalYears)}
                  forecastValues={getValues((cf) => cf.financing_activities.own_funds.increases, forecastYears)}
                  indent={2}
                />
                <CashFlowRow
                  label="(Decrementi mezzi propri)"
                  historicalValues={getValues((cf) => cf.financing_activities.own_funds.decreases, historicalYears)}
                  forecastValues={getValues((cf) => cf.financing_activities.own_funds.decreases, forecastYears)}
                  indent={2}
                />

                <CashFlowRow
                  label="Flusso finanziario dell'attivit\u00e0 di finanziamento (C)"
                  historicalValues={getValues((cf) => cf.financing_activities.total_financing_cashflow, historicalYears)}
                  forecastValues={getValues((cf) => cf.financing_activities.total_financing_cashflow, forecastYears)}
                  isTotal={true}
                />

                {/* CASH RECONCILIATION */}
                <tr className="h-4"></tr>
                <CashFlowRow
                  label="Incremento (decremento) delle disponibilit\u00e0 liquide (A\u00b1B\u00b1C)"
                  historicalValues={getValues((cf) => cf.cash_reconciliation.total_cashflow, historicalYears)}
                  forecastValues={getValues((cf) => cf.cash_reconciliation.total_cashflow, forecastYears)}
                  isTotal={true}
                />

                <tr className="h-4"></tr>
                <CashFlowRow
                  label="Disponibilit\u00e0 liquide all'inizio dell'esercizio"
                  historicalValues={getValues((cf) => cf.cash_reconciliation.cash_beginning, historicalYears)}
                  forecastValues={getValues((cf) => cf.cash_reconciliation.cash_beginning, forecastYears)}
                />
                <CashFlowRow
                  label="Disponibilit\u00e0 liquide alla fine dell'esercizio"
                  historicalValues={getValues((cf) => cf.cash_reconciliation.cash_ending, historicalYears)}
                  forecastValues={getValues((cf) => cf.cash_reconciliation.cash_ending, forecastYears)}
                />
                <CashFlowRow
                  label="Differenza"
                  historicalValues={getValues((cf) => cf.cash_reconciliation.difference, historicalYears)}
                  forecastValues={getValues((cf) => cf.cash_reconciliation.difference, forecastYears)}
                  isSubtotal={true}
                />
              </tbody>
            </table>
          </div>

          {/* Verification Status */}
          <div className="mt-4">
            {cashflowData.cashflows.every((cf) => cf.cash_reconciliation.verification_ok) ? (
              <Alert className="border-green-500/50 bg-green-50 dark:bg-green-950/50">
                <CheckCircle2 className="h-4 w-4 text-green-600 dark:text-green-400" />
                <AlertDescription className="text-green-700 dark:text-green-400 font-medium">
                  VERIFICA: Tutti i flussi sono bilanciati correttamente
                </AlertDescription>
              </Alert>
            ) : (
              <Alert variant="destructive">
                <AlertTriangle className="h-4 w-4" />
                <AlertDescription className="font-medium">
                  ATTENZIONE: Alcuni flussi presentano discrepanze
                </AlertDescription>
              </Alert>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
