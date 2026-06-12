"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useApp } from "@/contexts/AppContext";
import { useScenarios, useAnalysis, useInvalidateAnalysis, getPreferredScenario } from "@/hooks/use-queries";
import { formatCurrency, formatPercentage } from "@/lib/formatters";
import { patchCeOverrides } from "@/lib/api";
import type {
  BudgetScenario,
  ScenarioAnalysis,
  ScenarioAnalysisYearData,
} from "@/types/api";
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  ChartLegend,
  ChartLegendContent,
  type ChartConfig,
} from "@/components/ui/chart";
import { Input } from "@/components/ui/input";
import { Loader2, TrendingUp, AlertTriangle, AlertCircle, Pencil, RefreshCw } from "lucide-react";
import { cn, getErrorMessage } from "@/lib/utils";
import { PageHeader } from "@/components/page-header";
import { ScenarioSelector } from "@/components/scenario-selector";
import { toast } from "sonner";

const revenueChartConfig = {
  revenue: { label: "Ricavi", color: "hsl(var(--chart-1))" },
  ebitda: { label: "EBITDA", color: "hsl(var(--chart-2))" },
} satisfies ChartConfig;

const profitChartConfig = {
  ebit: { label: "EBIT", color: "hsl(var(--chart-3))" },
  net_profit: { label: "Utile Netto", color: "hsl(var(--chart-4))" },
} satisfies ChartConfig;

// Map IS field names to their CE override field names
// Only fields with an override are editable
const FIELD_TO_OVERRIDE: Record<string, string> = {
  ce01_ricavi_vendite: "ce01_override",
  ce02_variazioni_rimanenze: "ce02_override",
  ce03_lavori_interni: "ce03_override",
  ce04_altri_ricavi: "ce04_override",
  ce05_materie_prime: "ce05_override",
  ce06_servizi: "ce06_override",
  ce07_godimento_beni: "ce07_override",
  ce08_costi_personale: "ce08_override",
  ce08a_tfr_accrual: "ce08a_override",
  ce08b_salari_stipendi: "ce08b_override",
  ce08c_oneri_sociali: "ce08c_override",
  ce08d_altri_costi_personale: "ce08d_override",
  ce09_ammortamenti: "ce09_override",
  ce09a_ammort_immateriali: "ce09a_override",
  ce09b_ammort_materiali: "ce09b_override",
  ce09c_svalutazioni: "ce09c_override",
  ce09d_svalutazione_crediti: "ce09d_override",
  ce10_var_rimanenze_mat_prime: "ce10_override",
  ce11_accantonamenti: "ce11_override",
  ce11b_altri_accantonamenti: "ce11b_override",
  ce12_oneri_diversi: "ce12_override",
  ce13_proventi_partecipazioni: "ce13_override",
  ce14_altri_proventi_finanziari: "ce14_override",
  ce15_oneri_finanziari: "ce15_override",
  ce16_utili_perdite_cambi: "ce16_override",
  ce17_rettifiche_attivita_fin: "ce17_override",
  ce17a_rivalutazioni: "ce17a_override",
  ce17b_svalutazioni: "ce17b_override",
  ce18_proventi_straordinari: "ce18_override",
  ce19_oneri_straordinari: "ce19_override",
  ce20_imposte: "ce20_override",
};

type YearData = ScenarioAnalysisYearData;

// Key for pending edits: "year:field"
type PendingEdits = Record<string, number | null>;

export default function ForecastIncomePage() {
  const { selectedCompanyId } = useApp();
  const { data: scenarios = [], isLoading: scenariosLoading } = useScenarios(selectedCompanyId);
  const [selectedScenario, setSelectedScenario] = useState<BudgetScenario | null>(null);
  const invalidateAnalysis = useInvalidateAnalysis();
  const [pendingEdits, setPendingEdits] = useState<PendingEdits>({});
  const [saving, setSaving] = useState(false);

  const hasPendingEdits = Object.keys(pendingEdits).length > 0;

  // Auto-select preferred scenario when scenarios load
  useEffect(() => {
    if (scenarios.length > 0 && !selectedScenario) {
      setSelectedScenario(getPreferredScenario(scenarios));
    }
    if (!selectedCompanyId) setSelectedScenario(null);
  }, [scenarios, selectedCompanyId, selectedScenario]);

  // Clear pending edits when scenario changes
  useEffect(() => {
    setPendingEdits({});
  }, [selectedScenario?.id]);

  const { data: analysisData, isLoading: analysisLoading, error: analysisError } = useAnalysis(
    selectedCompanyId,
    selectedScenario?.id ?? null
  );
  const loading = scenariosLoading || analysisLoading;
  const error = analysisError ? "Impossibile caricare i dati previsionali" : null;

  const handleCellEdit = useCallback((year: number, field: string, value: number | null) => {
    const overrideField = FIELD_TO_OVERRIDE[field];
    if (!overrideField) return;
    const key = `${year}:${field}`;
    setPendingEdits((prev) => {
      const next = { ...prev };
      if (value === null) {
        // null means "clear override"
        next[key] = null;
      } else {
        next[key] = value;
      }
      return next;
    });
  }, []);

  const handleSaveAll = useCallback(async () => {
    if (!selectedCompanyId || !selectedScenario || !hasPendingEdits) return;
    setSaving(true);
    try {
      const overrides = Object.entries(pendingEdits).map(([key, value]) => {
        const [yearStr, field] = key.split(":");
        return {
          forecast_year: parseInt(yearStr),
          field: FIELD_TO_OVERRIDE[field],
          value,
        };
      });
      await patchCeOverrides(selectedCompanyId, selectedScenario.id, overrides);
      setPendingEdits({});
      invalidateAnalysis(selectedCompanyId, selectedScenario.id);
      toast.success("Previsionale aggiornato");
    } catch (err: any) {
      toast.error("Errore: " + getErrorMessage(err, "aggiornamento previsionale fallito"));
    } finally {
      setSaving(false);
    }
  }, [selectedCompanyId, selectedScenario, pendingEdits, hasPendingEdits, invalidateAnalysis]);

  if (!selectedCompanyId) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <Alert>
          <AlertTriangle className="h-4 w-4" />
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
          title="Conto Economico Previsionale"
          icon={<TrendingUp className="h-6 w-6" />}
        />
        <Alert>
          <AlertCircle className="h-4 w-4" />
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
        title="Conto Economico Previsionale"
        icon={<TrendingUp className="h-6 w-6" />}
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
          {/* Income Statement Table */}
          <Card className="mb-6">
            <CardHeader className="flex flex-row items-center justify-between space-y-0">
              <div>
                <CardTitle className="flex items-center gap-2">
                  Conto Economico: Confronto Storico vs Previsionale
                </CardTitle>
                {forecastYears.length > 0 && (
                  <p className="text-xs text-muted-foreground mt-1">
                    <Pencil className="h-3 w-3 inline mr-1" />
                    Clicca sulle celle previsionali per modificarle, poi &quot;Aggiorna Previsionale&quot;
                  </p>
                )}
              </div>
              {hasPendingEdits && (
                <Button
                  onClick={handleSaveAll}
                  disabled={saving}
                  size="sm"
                >
                  {saving ? (
                    <Loader2 className="h-4 w-4 animate-spin mr-2" />
                  ) : (
                    <RefreshCw className="h-4 w-4 mr-2" />
                  )}
                  Aggiorna Previsionale
                </Button>
              )}
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <IncomeStatementTable
                  historicalYears={historicalYears}
                  forecastYears={forecastYears}
                  pendingEdits={pendingEdits}
                  onCellEdit={handleCellEdit}
                />
              </div>
            </CardContent>
          </Card>

          {/* Charts */}
          {forecastYears.length > 0 && (
            <>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
                {/* Revenue & EBITDA Chart */}
                <Card>
                  <CardHeader>
                    <CardTitle>Ricavi ed EBITDA</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <ChartContainer config={revenueChartConfig} className="h-[300px] w-full">
                      <LineChart
                        data={prepareChartData(historicalYears, forecastYears, ["revenue", "ebitda"])}
                      >
                        <CartesianGrid vertical={false} />
                        <XAxis dataKey="year" />
                        <YAxis />
                        <ChartTooltip
                          content={
                            <ChartTooltipContent
                              formatter={(value) => formatCurrency(value as number)}
                            />
                          }
                        />
                        <ChartLegend content={<ChartLegendContent />} />
                        <Line
                          type="monotone"
                          dataKey="revenue"
                          stroke="var(--color-revenue)"
                          strokeWidth={2}
                        />
                        <Line
                          type="monotone"
                          dataKey="ebitda"
                          stroke="var(--color-ebitda)"
                          strokeWidth={2}
                        />
                      </LineChart>
                    </ChartContainer>
                  </CardContent>
                </Card>

                {/* EBIT & Net Profit Chart */}
                <Card>
                  <CardHeader>
                    <CardTitle>EBIT e Utile Netto</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <ChartContainer config={profitChartConfig} className="h-[300px] w-full">
                      <BarChart
                        data={prepareChartData(historicalYears, forecastYears, ["ebit", "net_profit"])}
                      >
                        <CartesianGrid vertical={false} />
                        <XAxis dataKey="year" />
                        <YAxis />
                        <ChartTooltip
                          content={
                            <ChartTooltipContent
                              formatter={(value) => formatCurrency(value as number)}
                            />
                          }
                        />
                        <ChartLegend content={<ChartLegendContent />} />
                        <Bar dataKey="ebit" fill="var(--color-ebit)" />
                        <Bar dataKey="net_profit" fill="var(--color-net_profit)" />
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
                      const inc = fy.income_statement;
                      if (!inc) return null;

                      return (
                        <Card key={fy.year}>
                          <CardContent className="pt-6">
                            <h4 className="font-semibold text-muted-foreground mb-3 text-center">
                              {fy.year}
                            </h4>
                            <div className="space-y-2 text-sm">
                              <MetricRow
                                label="Ricavi"
                                value={formatCurrency(inc.revenue)}
                              />
                              <MetricRow
                                label="EBITDA"
                                value={formatCurrency(inc.ebitda)}
                              />
                              <MetricRow
                                label="Margine EBITDA"
                                value={formatPercentage(inc.revenue ? inc.ebitda / inc.revenue : 0)}
                              />
                              <MetricRow
                                label="EBIT"
                                value={formatCurrency(inc.ebit)}
                              />
                              <MetricRow
                                label="Utile Netto"
                                value={formatCurrency(inc.net_profit)}
                              />
                            </div>
                          </CardContent>
                        </Card>
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

// Editable cell component for forecast values
function EditableCell({
  value,
  pendingValue,
  year,
  field,
  isOverridden,
  isBold,
  onEdit,
}: {
  value: number;
  pendingValue: number | null | undefined; // undefined = no pending edit
  year: number;
  field: string;
  isOverridden: boolean;
  isBold: boolean;
  onEdit: (year: number, field: string, value: number | null) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [editValue, setEditValue] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  // Display value: pending edit takes precedence over server value
  const displayValue = pendingValue !== undefined ? (pendingValue ?? value) : value;
  const hasPending = pendingValue !== undefined;

  const startEdit = () => {
    setEditValue(Math.round(displayValue).toString());
    setEditing(true);
  };

  useEffect(() => {
    if (editing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [editing]);

  const commitEdit = () => {
    setEditing(false);
    const trimmed = editValue.trim();
    if (trimmed === "") {
      // Clear override → revert to engine calculation
      onEdit(year, field, null);
      return;
    }
    const parsed = parseFloat(trimmed.replace(/[.\s]/g, "").replace(",", "."));
    if (isNaN(parsed)) return;
    // Only register edit if value actually changed (within €1 tolerance)
    if (Math.abs(parsed - value) < 1) return;
    onEdit(year, field, Math.round(parsed * 100) / 100);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      commitEdit();
    } else if (e.key === "Escape") {
      setEditing(false);
    }
  };

  if (editing) {
    return (
      <Input
        ref={inputRef}
        type="text"
        value={editValue}
        onChange={(e) => setEditValue(e.target.value)}
        onBlur={commitEdit}
        onKeyDown={handleKeyDown}
        className="h-7 w-28 text-right text-sm px-1 py-0"
      />
    );
  }

  return (
    <span
      onClick={startEdit}
      className={cn(
        "cursor-pointer hover:bg-primary/20 rounded px-1 -mx-1 transition-colors",
        hasPending && "bg-yellow-100 dark:bg-yellow-900/30 border-b-2 border-yellow-500",
        !hasPending && isOverridden && "border-b-2 border-primary",
        isBold && "font-semibold"
      )}
      title={
        hasPending
          ? "Modifica in sospeso — clicca \"Aggiorna Previsionale\" per applicare"
          : isOverridden
          ? "Valore modificato manualmente (svuota per ripristinare)"
          : "Clicca per modificare"
      }
    >
      {formatCurrency(displayValue)}
    </span>
  );
}

// Income Statement Table Component
function IncomeStatementTable({
  historicalYears,
  forecastYears,
  pendingEdits,
  onCellEdit,
}: {
  historicalYears: YearData[];
  forecastYears: YearData[];
  pendingEdits: PendingEdits;
  onCellEdit: (year: number, field: string, value: number | null) => void;
}) {
  const getVal = (yearData: YearData, field: string): number => {
    return yearData.income_statement[field] || 0;
  };

  // Check if a forecast year has an active override for a field
  const isOverridden = (yd: YearData, field: string): boolean => {
    const overrideKey = FIELD_TO_OVERRIDE[field];
    if (!overrideKey || !yd.assumptions) return false;
    return (yd.assumptions as unknown as Record<string, unknown>)[overrideKey] != null;
  };

  const rows: Array<{
    label: string;
    field?: string;
    calculated?: (yd: YearData) => number;
    isTotal?: boolean;
    isSubtotal?: boolean;
    indent?: number;
  }> = [
    // A) VALORE DELLA PRODUZIONE
    { label: "A) VALORE DELLA PRODUZIONE", isTotal: true },
    { label: "1) Ricavi delle vendite e delle prestazioni", field: "ce01_ricavi_vendite" },
    { label: "2) Variazioni delle rim. di prodotti in corso di lav., semilav. e finiti", field: "ce02_variazioni_rimanenze" },
    { label: "3) Variazioni dei lavori in corso su ordinazione", field: "ce03_lavori_interni" },
    { label: "5) Altri ricavi e proventi", field: "ce04_altri_ricavi" },
    { label: "Totale Valore della Produzione", field: "production_value", isSubtotal: true },
    // B) COSTI DELLA PRODUZIONE
    { label: "B) COSTI DELLA PRODUZIONE", isTotal: true },
    { label: "6) Materie prime, sussidiarie, di consumo e di merci", field: "ce05_materie_prime" },
    { label: "7) Servizi", field: "ce06_servizi" },
    { label: "8) Godimento di beni di terzi", field: "ce07_godimento_beni" },
    { label: "9) Personale", field: "ce08_costi_personale" },
    { label: "a) Salari e stipendi", field: "ce08b_salari_stipendi", indent: 1 },
    { label: "b) Oneri sociali", field: "ce08c_oneri_sociali", indent: 1 },
    { label: "c) Trattamento di fine rapporto", field: "ce08a_tfr_accrual", indent: 1 },
    { label: "d) Trattamento di quiescenza e simili" },
    { label: "e) Altri costi del personale", field: "ce08d_altri_costi_personale", indent: 1 },
    { label: "10) Ammortamenti e svalutazioni:" },
    { label: "a) Ammortamento delle immobilizzazioni immateriali", field: "ce09a_ammort_immateriali", indent: 1 },
    { label: "b) Ammortamento delle immobilizzazioni materiali", field: "ce09b_ammort_materiali", indent: 1 },
    { label: "c) Altre svalutazioni delle immobilizzazioni", field: "ce09c_svalutazioni", indent: 1 },
    { label: "d) Sval. dei crediti compresi nell'attivo circ. e delle disp. liquide", field: "ce09d_svalutazione_crediti", indent: 1 },
    { label: "Totale ammortamenti e svalutazioni", field: "ce09_ammortamenti", indent: 1 },
    { label: "11) Variazioni delle rim. di materie prime, sussidiarie, di cons. e merci", field: "ce10_var_rimanenze_mat_prime" },
    { label: "12) Accantonamenti per rischi", field: "ce11_accantonamenti" },
    { label: "13) Altri accantonamenti", field: "ce11b_altri_accantonamenti" },
    { label: "14) Oneri diversi di gestione", field: "ce12_oneri_diversi" },
    { label: "Totale Costi della Produzione", field: "production_cost", isSubtotal: true },
    // EBITDA
    { label: "EBITDA (MOL)", field: "ebitda", isSubtotal: true },
    // EBIT
    { label: "EBIT (Risultato Operativo)", field: "ebit", isSubtotal: true },
    // C) PROVENTI E ONERI FINANZIARI
    { label: "C) PROVENTI E ONERI FINANZIARI", isTotal: true },
    { label: "15) Proventi da partecipazioni", field: "ce13_proventi_partecipazioni" },
    { label: "16) Altri proventi finanziari", field: "ce14_altri_proventi_finanziari" },
    { label: "17) Interessi e altri oneri finanziari", field: "ce15_oneri_finanziari" },
    { label: "17-bis) Utili e perdite su cambi", field: "ce16_utili_perdite_cambi" },
    { label: "Totale Proventi/Oneri Finanziari", field: "financial_result", isSubtotal: true },
    // D) RETTIFICHE DI VALORE
    { label: "D) RETTIFICHE DI VALORE ATTIVITA' FINANZIARIE", isTotal: true },
    { label: "18) Rivalutazioni", field: "ce17a_rivalutazioni", indent: 1 },
    { label: "19) Svalutazioni", field: "ce17b_svalutazioni", indent: 1 },
    { label: "Totale rettifiche di valore", field: "ce17_rettifiche_attivita_fin", isSubtotal: true },
    // E) PROVENTI E ONERI STRAORDINARI
    { label: "E) PROVENTI E ONERI STRAORDINARI", isTotal: true },
    { label: "20) Proventi straordinari", field: "ce18_proventi_straordinari" },
    { label: "21) Oneri straordinari", field: "ce19_oneri_straordinari" },
    { label: "Totale Proventi/Oneri Straordinari", field: "extraordinary_result", isSubtotal: true },
    // RISULTATO PRIMA DELLE IMPOSTE
    { label: "Risultato prima delle imposte", field: "profit_before_tax", isSubtotal: true },
    // IMPOSTE
    { label: "22) Imposte sul reddito", field: "ce20_imposte" },
    // UTILE/PERDITA
    { label: "23) UTILE (PERDITA) DELL'ESERCIZIO", field: "net_profit", isTotal: true },
  ];

  return (
    <Table>
      <TableHeader>
        <TableRow className="bg-muted">
          <TableHead className="px-4 py-3 text-left text-xs font-bold text-foreground uppercase border-r border-border">
            Descrizione
          </TableHead>
          {historicalYears.map((yd) => (
            <TableHead
              key={yd.year}
              className="px-4 py-3 text-center text-xs font-bold text-foreground uppercase border-r border-border"
            >
              {yd.year}
              <div className="text-muted-foreground font-normal">(Storico)</div>
            </TableHead>
          ))}
          {forecastYears.map((yd) => (
            <TableHead
              key={yd.year}
              className="px-4 py-3 text-center text-xs font-bold text-primary uppercase border-r border-border bg-primary/10"
            >
              {yd.year}
              <div className="text-primary font-normal">(Previsionale)</div>
            </TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.filter((row) => {
          // Hide detail subfield rows when no historical year has that detail populated.
          if (!row.field || !row.indent) return true;
          return historicalYears.some((yd) => Math.abs(getVal(yd, row.field!)) >= 0.5);
        }).map((row, index) => {
          const histValues = row.field
            ? historicalYears.map((yd) => getVal(yd, row.field!))
            : [];
          const fcValues = row.field
            ? forecastYears.map((yd) => getVal(yd, row.field!))
            : [];
          const isEditable = !!row.field && !!FIELD_TO_OVERRIDE[row.field] && !row.isTotal && !row.isSubtotal;

          return (
            <TableRow
              key={index}
              className={cn(
                row.isTotal
                  ? "bg-muted font-bold hover:bg-muted"
                  : row.isSubtotal
                  ? "bg-primary/10 font-semibold hover:bg-primary/10"
                  : "hover:bg-muted/50"
              )}
            >
              <TableCell
                className="px-4 py-2 text-sm text-foreground border-r border-border"
                style={{ paddingLeft: row.indent ? `${1 + row.indent * 1.5}rem` : undefined }}
              >
                {row.label}
              </TableCell>
              {/* Historical columns */}
              {histValues.map((value, i) => (
                <TableCell
                  key={`hist-${i}`}
                  className={cn(
                    "px-4 py-2 text-sm text-right border-r border-border",
                    value < 0 ? "text-destructive" : "text-foreground",
                    (row.isTotal || row.isSubtotal) && "font-semibold"
                  )}
                >
                  {row.isTotal && !value ? "" : formatCurrency(value)}
                </TableCell>
              ))}
              {/* Forecast columns — editable for fields with overrides */}
              {fcValues.map((value, i) => {
                const yd = forecastYears[i];
                const pendingKey = `${yd.year}:${row.field}`;
                const pendingVal = pendingEdits[pendingKey];

                return (
                  <TableCell
                    key={`forecast-${i}`}
                    className={cn(
                      "px-4 py-2 text-sm text-right border-r border-border",
                      value < 0 ? "text-destructive" : "text-foreground",
                      (row.isTotal || row.isSubtotal) && "font-semibold"
                    )}
                  >
                    {row.isTotal && !value ? "" : isEditable ? (
                      <EditableCell
                        value={value}
                        pendingValue={pendingVal}
                        year={yd.year}
                        field={row.field!}
                        isOverridden={isOverridden(yd, row.field!)}
                        isBold={false}
                        onEdit={onCellEdit}
                      />
                    ) : (
                      formatCurrency(value)
                    )}
                  </TableCell>
                );
              })}
              {/* Empty cells for section headers without field */}
              {!row.field && historicalYears.map((yd) => (
                <TableCell key={`hist-empty-${yd.year}`} className="px-4 py-2 text-sm text-right border-r border-border" />
              ))}
              {!row.field && forecastYears.map((yd) => (
                <TableCell key={`fc-empty-${yd.year}`} className="px-4 py-2 text-sm text-right border-r border-border" />
              ))}
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
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
  forecastYears: YearData[],
  metrics: string[]
): any[] {
  const allYears = [...historicalYears, ...forecastYears];
  return allYears.map((yd) => ({
    year: yd.year.toString(),
    revenue: yd.income_statement.revenue || 0,
    ebitda: yd.income_statement.ebitda || 0,
    ebit: yd.income_statement.ebit || 0,
    net_profit: yd.income_statement.net_profit || 0,
  }));
}
