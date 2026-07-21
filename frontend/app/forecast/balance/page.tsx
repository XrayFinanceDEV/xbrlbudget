"use client";

import { useState, useEffect, useCallback } from "react";
import { useApp } from "@/contexts/AppContext";
import { useScenarios, useAnalysis, useInvalidateAnalysis, getPreferredScenario } from "@/hooks/use-queries";
import { generateForecast, getBudgetAssumptions, updateBudgetAssumptions } from "@/lib/api";
import { formatCurrency, formatPercentage } from "@/lib/formatters";
import { BALANCE_STATEMENT_ROWS } from "@/lib/ivcee-balance-catalog";
import type {
  BudgetScenario,
  ScenarioAnalysis,
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
import { BarChart3, AlertTriangle, AlertCircle, Loader2, Info, Save } from "lucide-react";
import { cn, getErrorMessage } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { PageHeader } from "@/components/page-header";
import { ScenarioSelector } from "@/components/scenario-selector";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
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

const pfnChartConfig = {
  pfn: { label: "PFN", color: "hsl(var(--chart-1))" },
} satisfies ChartConfig;

// Posizione Finanziaria Netta: debito finanziario − cassa − attività finanziarie.
// Priorità: sub-field banche/obbligazioni (detail); fallback: debito totale
// meno voci non finanziarie conosciute; ultimo: debito totale (abbreviato senza dettaglio).
function computePFN(bs: Record<string, number>): number {
  const v = (k: string) => bs[k] || 0;
  const cash = v("sp09_disponibilita_liquide");
  const financialAssets = v("sp08_attivita_finanziarie");
  const totalDebt = v("sp16_debiti_breve") + v("sp17_debiti_lungo");

  const bankDebt =
    v("sp16a_debiti_banche_breve") + v("sp17a_debiti_banche_lungo") +
    v("sp16c_debiti_obbligazioni_breve") + v("sp17c_debiti_obbligazioni_lungo");
  if (bankDebt > 0) return bankDebt - cash - financialAssets;

  const knownNonBankDebt =
    v("sp16b_debiti_altri_finanz_breve") + v("sp17b_debiti_altri_finanz_lungo") +
    v("sp16d_debiti_fornitori_breve") + v("sp17d_debiti_fornitori_lungo") +
    v("sp16e_debiti_tributari_breve") + v("sp17e_debiti_tributari_lungo") +
    v("sp16f_debiti_previdenza_breve") + v("sp17f_debiti_previdenza_lungo");
  if (knownNonBankDebt > 0) return (totalDebt - knownNonBankDebt) - cash - financialAssets;

  return totalDebt - cash - financialAssets;
}

// Type for year data from analysis endpoint
type YearData = {
  year: number;
  type: "historical" | "forecast";
  income_statement: Record<string, number>;
  balance_sheet: Record<string, number>;
};

const SP_EDITABLE_FIELDS = new Set([
  "sp01_crediti_soci", "sp02_immob_immateriali", "sp03_immob_materiali",
  "sp04a_partecipazioni", "sp04b_crediti_immob_breve", "sp04c_crediti_immob_lungo",
  "sp04d_altri_titoli", "sp04e_strumenti_derivati_attivi",
  "sp05a_materie_prime", "sp05b_prodotti_in_corso", "sp05c_lavori_in_corso",
  "sp05d_prodotti_finiti", "sp05e_acconti",
  "sp06a_crediti_clienti_breve", "sp06b_crediti_controllate_breve",
  "sp06c_crediti_collegate_breve", "sp06d_crediti_controllanti_breve",
  "sp06e_crediti_tributari_breve", "sp06f_imposte_anticipate_breve",
  "sp06g_crediti_altri_breve",
  "sp07a_crediti_clienti_lungo", "sp07b_crediti_controllate_lungo",
  "sp07c_crediti_collegate_lungo", "sp07d_crediti_controllanti_lungo",
  "sp07e_crediti_tributari_lungo", "sp07f_imposte_anticipate_lungo",
  "sp07g_crediti_altri_lungo", "sp08_attivita_finanziarie", "sp10_ratei_risconti_attivi",
  "sp11_capitale", "sp12a_riserva_sovrapprezzo", "sp12b_riserve_rivalutazione",
  "sp12c_riserva_legale", "sp12d_riserve_statutarie", "sp12e_altre_riserve",
  "sp12f_riserva_copertura_flussi", "sp12g_utili_perdite_portati",
  "sp12h_riserva_neg_azioni_proprie", "sp14a_fondi_trattamento_quiescenza",
  "sp14b_fondi_imposte", "sp14c_strumenti_derivati_passivi", "sp14d_altri_fondi", "sp15_tfr",
  "sp16a_debiti_banche_breve", "sp16b_debiti_altri_finanz_breve",
  "sp16c_debiti_obbligazioni_breve", "sp16d_debiti_fornitori_breve",
  "sp16e_debiti_tributari_breve", "sp16f_debiti_previdenza_breve",
  "sp16g_altri_debiti_breve", "sp17a_debiti_banche_lungo",
  "sp17b_debiti_altri_finanz_lungo", "sp17c_debiti_obbligazioni_lungo",
  "sp17d_debiti_fornitori_lungo", "sp17e_debiti_tributari_lungo",
  "sp17f_debiti_previdenza_lungo", "sp17g_altri_debiti_lungo",
  "sp18_ratei_risconti_passivi",
]);

type PendingSpEdits = Record<string, number | null>;

export default function ForecastBalancePage() {
  const { selectedCompanyId } = useApp();
  const { data: scenarios = [], isLoading: scenariosLoading } = useScenarios(selectedCompanyId);
  const [selectedScenario, setSelectedScenario] = useState<BudgetScenario | null>(null);
  const [pendingEdits, setPendingEdits] = useState<PendingSpEdits>({});
  const [saving, setSaving] = useState(false);
  const invalidateAnalysis = useInvalidateAnalysis();

  // Auto-select preferred scenario when scenarios load
  useEffect(() => {
    if (scenarios.length > 0 && !selectedScenario) {
      setSelectedScenario(getPreferredScenario(scenarios));
    }
    if (!selectedCompanyId) setSelectedScenario(null);
  }, [scenarios, selectedCompanyId, selectedScenario]);

  const { data: analysisData, isLoading: analysisLoading, error: analysisError } = useAnalysis(
    selectedCompanyId,
    selectedScenario?.id ?? null
  );
  const loading = scenariosLoading || analysisLoading;
  const error = analysisError ? "Impossibile caricare i dati previsionali" : null;

  useEffect(() => setPendingEdits({}), [selectedScenario?.id]);

  const handleSaveOverrides = useCallback(async () => {
    if (!selectedCompanyId || !selectedScenario || Object.keys(pendingEdits).length === 0) return;
    setSaving(true);
    try {
      const assumptions = await getBudgetAssumptions(selectedCompanyId, selectedScenario.id);
      const editsByYear = new Map<number, Array<[string, number | null]>>();
      Object.entries(pendingEdits).forEach(([key, value]) => {
        const [yearRaw, field] = key.split(":");
        const year = Number.parseInt(yearRaw, 10);
        editsByYear.set(year, [...(editsByYear.get(year) ?? []), [field, value]]);
      });
      await Promise.all(Array.from(editsByYear.entries()).map(async ([year, edits]) => {
        const current = assumptions.find((item) => item.forecast_year === year);
        const spOverrides = { ...(current?.sp_overrides ?? {}) };
        edits.forEach(([field, value]) => {
          if (value === null) delete spOverrides[field];
          else spOverrides[field] = value;
        });
        await updateBudgetAssumptions(selectedCompanyId, selectedScenario.id, year, {
          sp_overrides: Object.keys(spOverrides).length > 0 ? spOverrides : null,
        });
      }));
      await generateForecast(selectedCompanyId, selectedScenario.id);
      setPendingEdits({});
      invalidateAnalysis(selectedCompanyId, selectedScenario.id);
      toast.success("Stato patrimoniale aggiornato");
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, "aggiornamento dello stato patrimoniale fallito"));
    } finally {
      setSaving(false);
    }
  }, [selectedCompanyId, selectedScenario, pendingEdits, invalidateAnalysis]);

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
            Nessuno scenario budget trovato. Vai alla tab &quot;Scenari&quot; per creare uno scenario.
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  const historicalYears = analysisData?.historical_years ?? [];
  const forecastYears = analysisData?.forecast_years ?? [];

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

      {!loading && analysisData && historicalYears.length > 0 && (
        <>
          {/* Balance Sheet Table */}
          <Card className="mb-6">
            <CardHeader className="flex flex-row items-center justify-between gap-4">
              <div>
                <CardTitle className="text-xl">
                  Stato Patrimoniale: Confronto Storico vs Previsionale
                </CardTitle>
                <p className="mt-1 text-sm text-muted-foreground">
                  Le celle di dettaglio previsionali sono modificabili; i totali e la cassa vengono ricalcolati.
                </p>
              </div>
              <Button
                onClick={handleSaveOverrides}
                disabled={saving || Object.keys(pendingEdits).length === 0}
              >
                {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
                Salva modifiche
              </Button>
            </CardHeader>
            <CardContent>
              {/* Balance Check Warning */}
              <BalanceCheckWarning
                historicalYears={historicalYears}
                forecastYears={forecastYears}
              />

              <div className="overflow-x-auto">
                <BalanceSheetTable
                  historicalYears={historicalYears}
                  forecastYears={forecastYears}
                  pendingEdits={pendingEdits}
                  onEdit={(year, field, value) => {
                    setPendingEdits((current) => ({ ...current, [`${year}:${field}`]: value }));
                  }}
                />
              </div>
            </CardContent>
          </Card>

          {/* Charts */}
          {forecastYears.length > 0 && (
            <>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
                {/* Assets Composition Chart */}
                <Card>
                  <CardHeader>
                    <CardTitle>Composizione Attivo</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <ChartContainer config={assetsChartConfig} className="h-[300px] w-full">
                      <ComposedChart data={prepareChartData(historicalYears, forecastYears)}>
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
                      <BarChart data={prepareChartData(historicalYears, forecastYears)}>
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

                {/* Working Capital Chart */}
                <Card>
                  <CardHeader>
                    <CardTitle>Capitale Circolante Netto (CCN)</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <ChartContainer config={wcChartConfig} className="h-[300px] w-full">
                      <LineChart data={prepareChartData(historicalYears, forecastYears)}>
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

                {/* PFN (Posizione Finanziaria Netta) Chart */}
                <Card>
                  <CardHeader>
                    <CardTitle>Posizione Finanziaria Netta (PFN)</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <ChartContainer config={pfnChartConfig} className="h-[300px] w-full">
                      <BarChart data={prepareChartData(historicalYears, forecastYears)}>
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
                        <Bar dataKey="pfn" fill="var(--color-pfn)" name="PFN" />
                      </BarChart>
                    </ChartContainer>
                  </CardContent>
                </Card>
              </div>

              {/* Key Metrics Summary */}
              <Card>
                <CardHeader>
                  <CardTitle>Riepilogo Indicatori Chiave</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                    {forecastYears.map((fy) => {
                      const bs = fy.balance_sheet;
                      if (!bs) return null;

                      const debtToEquity = bs.total_equity !== 0
                        ? bs.total_debt / bs.total_equity
                        : 0;

                      return (
                        <div key={fy.year} className="border border-border rounded-lg p-4">
                          <h4 className="font-semibold text-muted-foreground mb-3 text-center">
                            {fy.year}
                          </h4>
                          <div className="space-y-2 text-sm">
                            <MetricRow
                              label="Totale Attivo"
                              value={formatCurrency(bs.total_assets)}
                            />
                            <MetricRow
                              label="Patrimonio Netto"
                              value={formatCurrency(bs.total_equity)}
                            />
                            <MetricRow
                              label="Debiti Totali"
                              value={formatCurrency(bs.total_debt)}
                            />
                            <MetricRow
                              label="CCN"
                              value={formatCurrency(bs.working_capital_net)}
                            />
                            <MetricRow
                              label="PFN"
                              value={formatCurrency(computePFN(bs))}
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
  forecastYears,
}: {
  historicalYears: YearData[];
  forecastYears: YearData[];
}) {
  const TOLERANCE = 1.0;
  const issues: Array<{ year: number; diff: number; type: 'historical' | 'forecast' }> = [];

  historicalYears.forEach((yd) => {
    const bs = yd.balance_sheet;
    if (bs) {
      const diff = Math.abs(bs.total_assets - (bs.total_equity + bs.total_debt + (bs.sp14_fondi_rischi || 0) + (bs.sp15_tfr || 0) + (bs.sp18_ratei_risconti_passivi || 0)));
      if (diff > TOLERANCE) {
        issues.push({ year: yd.year, diff, type: 'historical' });
      }
    }
  });

  forecastYears.forEach((yd) => {
    const bs = yd.balance_sheet;
    if (bs) {
      const diff = Math.abs(bs.total_assets - (bs.total_equity + bs.total_debt + (bs.sp14_fondi_rischi || 0) + (bs.sp15_tfr || 0) + (bs.sp18_ratei_risconti_passivi || 0)));
      if (diff > TOLERANCE) {
        issues.push({ year: yd.year, diff, type: 'forecast' });
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
  forecastYears,
  pendingEdits,
  onEdit,
}: {
  historicalYears: YearData[];
  forecastYears: YearData[];
  pendingEdits: PendingSpEdits;
  onEdit: (year: number, field: string, value: number | null) => void;
}) {
  const getVal = (yearData: YearData, field: string): number => {
    return yearData.balance_sheet[field] || 0;
  };

  const rows = BALANCE_STATEMENT_ROWS.map((row) => ({
    ...row,
    computed: row.computed
      ? (yearData: YearData) => row.computed!(yearData.balance_sheet)
      : undefined,
  }));

  return (
    <table className="min-w-full divide-y divide-border border border-border">
      <thead className="bg-muted">
        <tr>
          <th className="px-4 py-3 text-left text-xs font-bold text-foreground uppercase border-r border-border">
            Descrizione
          </th>
          {historicalYears.map((yd) => (
            <th
              key={yd.year}
              className="px-4 py-3 text-center text-xs font-bold text-foreground uppercase border-r border-border"
            >
              {yd.year}
              <div className="text-muted-foreground font-normal">(Storico)</div>
            </th>
          ))}
          {forecastYears.map((yd) => (
            <th
              key={yd.year}
              className="px-4 py-3 text-center text-xs font-bold text-primary uppercase border-r border-border bg-primary/10"
            >
              {yd.year}
              <div className="text-primary font-normal">(Previsionale)</div>
            </th>
          ))}
        </tr>
      </thead>
      <tbody className="bg-card divide-y divide-border">
        {rows.filter((row) => {
          // Hide detail subfield rows when no historical year has that detail populated.
          // This avoids showing mechanical breakdowns from the forecast engine
          // when the original data (abbreviato) only has aggregate totals.
          if (!row.field || !row.label.startsWith("  ")) return true;
          return historicalYears.some((yd) => Math.abs(getVal(yd, row.field!)) >= 0.5);
        }).map((row, index) => {
          const getValue = (yd: YearData): number | null => {
            if (row.computed) return row.computed(yd);
            if (row.field) return getVal(yd, row.field);
            return null;
          };

          const histValues = historicalYears.map(getValue);
          const fcValues = forecastYears.map(getValue);
          const hasValues = row.field || row.computed;

          const bgClass = row.isTotal
            ? "bg-muted font-bold"
            : row.isSubtotal
            ? "bg-primary/10 font-semibold"
            : "hover:bg-muted/50";

          return (
            <tr key={index} className={bgClass}>
              <td className={cn(
                "px-4 py-2 text-sm border-r border-border",
                row.label.startsWith("  ") ? "pl-12 text-muted-foreground" : row.indent ? "pl-8 text-foreground" : "text-foreground"
              )}>
                {row.label.trimStart()}
              </td>
              {histValues.map((value, i) => (
                <td
                  key={`hist-${i}`}
                  className={cn(
                    "px-4 py-2 text-sm text-right border-r border-border",
                    value !== null && value < 0 ? "text-destructive" : "text-foreground",
                    (row.isTotal || row.isSubtotal) && "font-semibold"
                  )}
                >
                  {value === null ? "" : (row.isTotal && !value ? "" : formatCurrency(value))}
                </td>
              ))}
              {fcValues.map((value, i) => {
                const year = forecastYears[i].year;
                const editKey = row.field ? `${year}:${row.field}` : "";
                const isEditable = Boolean(row.field && SP_EDITABLE_FIELDS.has(row.field));
                const displayedValue = Object.prototype.hasOwnProperty.call(pendingEdits, editKey)
                  ? pendingEdits[editKey]
                  : value;
                return (
                <td
                  key={`forecast-${i}`}
                  className={cn(
                    "px-4 py-2 text-sm text-right border-r border-border",
                    value !== null && value < 0 ? "text-destructive" : "text-foreground",
                    (row.isTotal || row.isSubtotal) && "font-semibold"
                  )}
                >
                  {isEditable ? (
                    <Input
                      type="number"
                      step="100"
                      className="ml-auto h-8 w-32 text-right"
                      value={displayedValue ?? ""}
                      onChange={(event) => {
                        const raw = event.target.value;
                        onEdit(year, row.field!, raw === "" ? null : Number(raw));
                      }}
                      aria-label={`${row.label.trim()} ${year}`}
                    />
                  ) : value === null ? "" : (row.isTotal && !value ? "" : formatCurrency(value))}
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
  historicalYears: YearData[],
  forecastYears: YearData[]
): any[] {
  const allYears = [...historicalYears, ...forecastYears];
  return allYears.map((yd) => ({
    year: yd.year.toString(),
    total_assets: yd.balance_sheet.total_assets || 0,
    total_equity: yd.balance_sheet.total_equity || 0,
    total_debt: yd.balance_sheet.total_debt || 0,
    fixed_assets: yd.balance_sheet.fixed_assets || 0,
    current_assets: yd.balance_sheet.current_assets || 0,
    working_capital_net: yd.balance_sheet.working_capital_net || 0,
    pfn: computePFN(yd.balance_sheet),
  }));
}
