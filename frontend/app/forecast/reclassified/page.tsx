"use client";

import { useState, useEffect } from "react";
import { useApp } from "@/contexts/AppContext";
import { useScenarios, useReclassifiedData, getPreferredScenario } from "@/hooks/use-queries";
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
  ComposedChart,
  Area,
} from "recharts";
import {
  ClipboardList,
  BarChart3,
  Coins,
  TrendingUp,
  Loader2,
  AlertCircle,
  AlertTriangle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { PageHeader } from "@/components/page-header";
import { ScenarioSelector } from "@/components/scenario-selector";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  ChartLegend,
  ChartLegendContent,
  type ChartConfig,
} from "@/components/ui/chart";

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

// Chart configs
const revenueChartConfig = {
  revenue: { label: "Ricavi", color: "hsl(var(--chart-1))" },
  ebitda: { label: "EBITDA", color: "hsl(var(--chart-2))" },
  ebit: { label: "EBIT", color: "hsl(var(--chart-3))" },
  net_profit: { label: "Utile Netto", color: "hsl(var(--chart-4))" },
} satisfies ChartConfig;

const marginChartConfig = {
  ebitda_margin: { label: "Margine EBITDA", color: "hsl(var(--chart-2))" },
  roe: { label: "ROE", color: "hsl(var(--chart-1))" },
  roi: { label: "ROI", color: "hsl(var(--chart-3))" },
} satisfies ChartConfig;

const structureChartConfig = {
  total_assets: { label: "Totale Attivo", color: "hsl(var(--chart-1))" },
  total_equity: { label: "Patrimonio Netto", color: "hsl(var(--chart-2))" },
  total_debt: { label: "Debiti Totali", color: "hsl(var(--chart-5))" },
} satisfies ChartConfig;

const wcChartConfig = {
  working_capital: { label: "Capitale Circolante Netto", color: "hsl(var(--chart-1))" },
  current_ratio: { label: "Indice Liquidità Corrente", color: "hsl(var(--chart-2))" },
} satisfies ChartConfig;

const solvencyChartConfig = {
  debt_to_equity: { label: "Debt-to-Equity", color: "hsl(var(--chart-5))" },
} satisfies ChartConfig;

export default function ForecastReclassifiedPage() {
  const { selectedCompanyId } = useApp();
  const { data: scenarios = [], isLoading: scenariosLoading } = useScenarios(selectedCompanyId);
  const [selectedScenario, setSelectedScenario] = useState<BudgetScenario | null>(null);

  // Auto-select preferred scenario when scenarios load
  useEffect(() => {
    if (scenarios.length > 0 && !selectedScenario) {
      setSelectedScenario(getPreferredScenario(scenarios));
    }
    if (!selectedCompanyId) setSelectedScenario(null);
  }, [scenarios, selectedCompanyId, selectedScenario]);

  const { data: reclassifiedData, isLoading: dataLoading, error: dataError } = useReclassifiedData(
    selectedCompanyId,
    selectedScenario?.id ?? null
  );
  const loading = scenariosLoading || dataLoading;
  const error = dataError ? "Impossibile caricare i dati riclassificati" : null;

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
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          <span className="ml-2 text-lg text-muted-foreground">Caricamento...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Errore</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      </div>
    );
  }

  if (!selectedCompanyId) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <Alert>
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Nessuna azienda selezionata</AlertTitle>
          <AlertDescription>
            Seleziona un&apos;azienda per visualizzare i dati previsionali
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  if (scenarios.length === 0) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <Alert>
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Nessuno scenario disponibile</AlertTitle>
          <AlertDescription>
            Nessuno scenario disponibile. Crea uno scenario nella pagina &quot;Scenari&quot;.
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <PageHeader
        title="Previsionale Riclassificato"
        description="Analisi degli indicatori finanziari previsionali con confronto storico"
        icon={<ClipboardList className="h-6 w-6" />}
      />

      {/* Scenario Selector */}
      <Card className="mb-6">
        <CardContent className="pt-6">
          <ScenarioSelector
            scenarios={scenarios}
            selectedScenario={selectedScenario}
            onSelect={setSelectedScenario}
          />

          {selectedScenario && reclassifiedData && (
            <div className="mt-4 grid grid-cols-3 gap-4 text-sm">
              <div>
                <span className="text-muted-foreground">Anno Base:</span>
                <span className="ml-2 font-semibold text-foreground">
                  {reclassifiedData.scenario.base_year}
                </span>
              </div>
              <div>
                <span className="text-muted-foreground">Anni Previsionali:</span>
                <span className="ml-2 font-semibold text-foreground">
                  {reclassifiedData.scenario.projection_years}
                </span>
              </div>
              <div>
                <span className="text-muted-foreground">Totale Anni:</span>
                <span className="ml-2 font-semibold text-foreground">
                  {reclassifiedData.years.length}
                </span>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {!reclassifiedData ? (
        <Card>
          <CardContent className="pt-6">
            <p className="text-muted-foreground">Seleziona uno scenario per visualizzare i dati</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-6">
          {/* Income Statement Reclassified */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <BarChart3 className="h-5 w-5" />
                Conto Economico Riclassificato
              </CardTitle>
            </CardHeader>
            <CardContent>
              {/* Revenue and Profitability */}
              <div className="mb-6">
                <h3 className="text-md font-medium text-muted-foreground mb-3">
                  Ricavi e Redditività
                </h3>
                <ChartContainer config={revenueChartConfig} className="h-[300px] w-full">
                  <ComposedChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="year" />
                    <YAxis
                      yAxisId="left"
                      label={{ value: "\u20AC", angle: -90, position: "insideLeft" }}
                    />
                    <ChartTooltip
                      content={
                        <ChartTooltipContent
                          formatter={(value) => formatCurrency(value as number)}
                          labelFormatter={(label) => `Anno ${label}`}
                        />
                      }
                    />
                    <ChartLegend content={<ChartLegendContent />} />
                    <Bar
                      yAxisId="left"
                      dataKey="revenue"
                      fill="var(--color-revenue)"
                      fillOpacity={0.8}
                    />
                    <Line
                      yAxisId="left"
                      type="monotone"
                      dataKey="ebitda"
                      stroke="var(--color-ebitda)"
                      strokeWidth={2}
                      dot={{ r: 4 }}
                    />
                    <Line
                      yAxisId="left"
                      type="monotone"
                      dataKey="ebit"
                      stroke="var(--color-ebit)"
                      strokeWidth={2}
                      dot={{ r: 4 }}
                    />
                    <Line
                      yAxisId="left"
                      type="monotone"
                      dataKey="net_profit"
                      stroke="var(--color-net_profit)"
                      strokeWidth={2}
                      dot={{ r: 4 }}
                    />
                  </ComposedChart>
                </ChartContainer>
              </div>

              {/* Profitability Margins */}
              <div>
                <h3 className="text-md font-medium text-muted-foreground mb-3">
                  Margini di Redditività (%)
                </h3>
                <ChartContainer config={marginChartConfig} className="h-[300px] w-full">
                  <LineChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="year" />
                    <YAxis
                      label={{ value: "%", angle: -90, position: "insideLeft" }}
                    />
                    <ChartTooltip
                      content={
                        <ChartTooltipContent
                          formatter={(value) => `${(value as number).toFixed(2)}%`}
                          labelFormatter={(label) => `Anno ${label}`}
                        />
                      }
                    />
                    <ChartLegend content={<ChartLegendContent />} />
                    <Line
                      type="monotone"
                      dataKey="ebitda_margin"
                      stroke="var(--color-ebitda_margin)"
                      strokeWidth={2}
                      dot={{ r: 4 }}
                    />
                    <Line
                      type="monotone"
                      dataKey="roe"
                      stroke="var(--color-roe)"
                      strokeWidth={2}
                      dot={{ r: 4 }}
                    />
                    <Line
                      type="monotone"
                      dataKey="roi"
                      stroke="var(--color-roi)"
                      strokeWidth={2}
                      dot={{ r: 4 }}
                    />
                  </LineChart>
                </ChartContainer>
              </div>
            </CardContent>
          </Card>

          {/* Balance Sheet Reclassified */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Coins className="h-5 w-5" />
                Stato Patrimoniale Riclassificato
              </CardTitle>
            </CardHeader>
            <CardContent>
              {/* Assets, Equity, Debt */}
              <div className="mb-6">
                <h3 className="text-md font-medium text-muted-foreground mb-3">
                  Struttura Patrimoniale
                </h3>
                <ChartContainer config={structureChartConfig} className="h-[300px] w-full">
                  <ComposedChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="year" />
                    <YAxis
                      label={{ value: "\u20AC", angle: -90, position: "insideLeft" }}
                    />
                    <ChartTooltip
                      content={
                        <ChartTooltipContent
                          formatter={(value) => formatCurrency(value as number)}
                          labelFormatter={(label) => `Anno ${label}`}
                        />
                      }
                    />
                    <ChartLegend content={<ChartLegendContent />} />
                    <Area
                      type="monotone"
                      dataKey="total_assets"
                      fill="var(--color-total_assets)"
                      fillOpacity={0.3}
                      stroke="var(--color-total_assets)"
                      strokeWidth={2}
                    />
                    <Bar
                      dataKey="total_equity"
                      fill="var(--color-total_equity)"
                      fillOpacity={0.8}
                    />
                    <Bar
                      dataKey="total_debt"
                      fill="var(--color-total_debt)"
                      fillOpacity={0.8}
                    />
                  </ComposedChart>
                </ChartContainer>
              </div>

              {/* Working Capital and Liquidity */}
              <div>
                <h3 className="text-md font-medium text-muted-foreground mb-3">
                  Capitale Circolante e Liquidità
                </h3>
                <ChartContainer config={wcChartConfig} className="h-[300px] w-full">
                  <ComposedChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="year" />
                    <YAxis
                      yAxisId="left"
                      label={{ value: "\u20AC", angle: -90, position: "insideLeft" }}
                    />
                    <YAxis
                      yAxisId="right"
                      orientation="right"
                      label={{ value: "Ratio", angle: 90, position: "insideRight" }}
                    />
                    <ChartTooltip
                      content={
                        <ChartTooltipContent
                          formatter={(value, name) =>
                            name === "current_ratio"
                              ? (value as number).toFixed(2)
                              : formatCurrency(value as number)
                          }
                          labelFormatter={(label) => `Anno ${label}`}
                        />
                      }
                    />
                    <ChartLegend content={<ChartLegendContent />} />
                    <Bar
                      yAxisId="left"
                      dataKey="working_capital"
                      fill="var(--color-working_capital)"
                      fillOpacity={0.8}
                    />
                    <Line
                      yAxisId="right"
                      type="monotone"
                      dataKey="current_ratio"
                      stroke="var(--color-current_ratio)"
                      strokeWidth={2}
                      dot={{ r: 4 }}
                    />
                  </ComposedChart>
                </ChartContainer>
              </div>
            </CardContent>
          </Card>

          {/* Solvency Ratios */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <TrendingUp className="h-5 w-5" />
                Indici di Solvibilità
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ChartContainer config={solvencyChartConfig} className="h-[300px] w-full">
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="year" />
                  <YAxis />
                  <ChartTooltip
                    content={
                      <ChartTooltipContent
                        formatter={(value) => (value as number).toFixed(2)}
                        labelFormatter={(label) => `Anno ${label}`}
                      />
                    }
                  />
                  <ChartLegend content={<ChartLegendContent />} />
                  <Line
                    type="monotone"
                    dataKey="debt_to_equity"
                    stroke="var(--color-debt_to_equity)"
                    strokeWidth={2}
                    dot={{ r: 4 }}
                  />
                </LineChart>
              </ChartContainer>
            </CardContent>
          </Card>

          {/* Data Table Summary */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <ClipboardList className="h-5 w-5" />
                Riepilogo Dati
              </CardTitle>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Anno</TableHead>
                    <TableHead>Tipo</TableHead>
                    <TableHead className="text-right">Ricavi</TableHead>
                    <TableHead className="text-right">EBITDA</TableHead>
                    <TableHead className="text-right">EBIT</TableHead>
                    <TableHead className="text-right">Utile Netto</TableHead>
                    <TableHead className="text-right">Totale Attivo</TableHead>
                    <TableHead className="text-right">CCN</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {[...reclassifiedData.historical_data, ...reclassifiedData.forecast_data].map(
                    (yearData) => (
                      <TableRow
                        key={yearData.year}
                        className={cn(
                          yearData.type === "forecast" && "bg-primary/10"
                        )}
                      >
                        <TableCell className="font-medium">
                          {yearData.year}
                        </TableCell>
                        <TableCell>
                          <Badge variant={yearData.type === "forecast" ? "default" : "secondary"}>
                            {yearData.type === "historical" ? "Storico" : "Previsionale"}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right">
                          {formatCurrency(yearData.income_statement.revenue)}
                        </TableCell>
                        <TableCell className="text-right">
                          {formatCurrency(yearData.income_statement.ebitda)}
                        </TableCell>
                        <TableCell className="text-right">
                          {formatCurrency(yearData.income_statement.ebit)}
                        </TableCell>
                        <TableCell className="text-right">
                          {formatCurrency(yearData.income_statement.net_profit)}
                        </TableCell>
                        <TableCell className="text-right">
                          {formatCurrency(yearData.balance_sheet.total_assets)}
                        </TableCell>
                        <TableCell className="text-right">
                          {formatCurrency(yearData.balance_sheet.working_capital)}
                        </TableCell>
                      </TableRow>
                    )
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
