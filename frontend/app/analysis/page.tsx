"use client";

import { useState, useEffect } from "react";
import { useApp } from "@/contexts/AppContext";
import {
  getCompleteAnalysis,
  getAllRatios,
  getAltmanZScore,
  getFGPMIRating,
  getMultiYearRatios,
  getBudgetScenarios,
  downloadReportPDF,
} from "@/lib/api";
import { formatCurrency, formatPercentage } from "@/lib/formatters";
import type {
  FinancialAnalysis,
  AllRatios,
  AltmanResult,
  FGPMIResult,
  MultiYearRatios,
} from "@/types/api";
import {
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  Legend,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Cell,
} from "recharts";
import {
  TrendingUp,
  Target,
  Star,
  BarChart3,
  Droplets,
  Landmark,
  Coins,
  RefreshCw,
  Hash,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Sparkles,
  PieChart,
  Loader2,
  Download,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { PageHeader } from "@/components/page-header";
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
import { Button } from "@/components/ui/button";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  ChartLegend,
  ChartLegendContent,
  type ChartConfig,
} from "@/components/ui/chart";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

// Formula abbreviation explanations for the multi-year ratios table
const formulaTooltips: Record<string, string> = {
  "CN-AF": "CN = Capitale Netto (Patrimonio Netto), AF = Attivo Fisso (Immobilizzazioni)",
  "[LI+LD+RD]-PC": "LI = Liquidita Immediata, LD = Liquidita Differita, RD = Rimanenze, PC = Passivo Corrente",
  "[LI+LD]-PC": "LI = Liquidita Immediata, LD = Liquidita Differita, PC = Passivo Corrente",
  "(CN+PF)/AF": "CN = Capitale Netto, PF = Passivo Fisso (Debiti M/L termine), AF = Attivo Fisso",
  "CN/AF": "CN = Capitale Netto (Patrimonio Netto), AF = Attivo Fisso (Immobilizzazioni)",
  "CN/(PC+PF)": "CN = Capitale Netto, PC = Passivo Corrente, PF = Passivo Fisso",
  "(LI+LD+RD)/PC": "LI = Liquidita Immediata, LD = Liquidita Differita, RD = Rimanenze, PC = Passivo Corrente",
  "(LI+LD)/PC": "LI = Liquidita Immediata, LD = Liquidita Differita, PC = Passivo Corrente",
  "CO/RD": "CO = Costi Operativi (Materie Prime), RD = Rimanenze",
  "RIC/LD": "RIC = Ricavi delle Vendite, LD = Liquidita Differita (Crediti)",
  "(CO+AC+ODG)/PC": "CO = Costi Operativi, AC = Acquisti, ODG = Oneri Diversi di Gestione, PC = Passivo Corrente",
  "RIC/CCN": "RIC = Ricavi delle Vendite, CCN = Capitale Circolante Netto",
  "RIC/TA": "RIC = Ricavi delle Vendite, TA = Totale Attivo",
  "360/TdM": "360 giorni / Turnover del Magazzino",
  "360/TdC": "360 giorni / Turnover dei Crediti",
  "360/TdD": "360 giorni / Turnover dei Debiti",
  "360/TdCCN": "360 giorni / Turnover del Capitale Circolante Netto",
  "360/TdAT": "360 giorni / Turnover delle Attivita Totali",
  "RN/CN": "RN = Risultato Netto (Utile/Perdita), CN = Capitale Netto (Patrimonio Netto)",
  "MON/TA": "MON = Margine Operativo Netto (EBIT), TA = Totale Attivo",
  "MON/RIC": "MON = Margine Operativo Netto (EBIT), RIC = Ricavi delle Vendite",
  "OF/(PC+PF)": "OF = Oneri Finanziari, PC = Passivo Corrente, PF = Passivo Fisso",
  "(ROI-ROD)": "Differenza tra rendimento del capitale investito e costo del debito",
  "(PC+PF)/CN": "PC = Passivo Corrente, PF = Passivo Fisso, CN = Capitale Netto",
  "MOL/RIC": "MOL = Margine Operativo Lordo (EBITDA), RIC = Ricavi delle Vendite",
  "OF/RIC": "OF = Oneri Finanziari, RIC = Ricavi delle Vendite",
  "RIC/CL": "RIC = Ricavi delle Vendite, CL = Costo del Lavoro",
  "RIC/CO": "RIC = Ricavi delle Vendite, CO = Costi Operativi (Materie Prime)",
  "CF/%MdC": "CF = Costi Fissi, %MdC = Percentuale Margine di Contribuzione",
  "1-(RICAVI BEP/RIC)": "Margine tra ricavi effettivi e punto di pareggio",
  "MdC/MON": "MdC = Margine di Contribuzione, MON = Margine Operativo Netto (EBIT)",
  "1/%MdC": "Inverso della percentuale del Margine di Contribuzione",
};

function FormulaCell({ formula }: { formula: string }) {
  const tip = formulaTooltips[formula];
  if (!tip) {
    return <td className="py-2 px-4 text-muted-foreground">{formula}</td>;
  }
  return (
    <td className="py-2 px-4 text-muted-foreground">
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="cursor-help border-b border-dashed border-muted-foreground/50">
            {formula}
          </span>
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-xs text-xs">
          <p>{tip}</p>
        </TooltipContent>
      </Tooltip>
    </td>
  );
}

// Chart configs
const radarChartConfig = {
  value: { label: "Performance", color: "hsl(var(--chart-1))" },
} satisfies ChartConfig;

const altmanChartConfig = {
  value: { label: "Valore", color: "hsl(var(--chart-1))" },
} satisfies ChartConfig;

const fgpmiChartConfig = {
  points: { label: "Punti", color: "hsl(var(--chart-2))" },
  maxPoints: { label: "Max", color: "hsl(var(--chart-5))" },
} satisfies ChartConfig;

export default function AnalysisPage() {
  const { selectedCompanyId, selectedCompany, selectedYear } = useApp();
  const [analysis, setAnalysis] = useState<FinancialAnalysis | null>(null);
  const [multiYearRatios, setMultiYearRatios] = useState<MultiYearRatios | null>(null);
  const [scenarios, setScenarios] = useState<any[]>([]);
  const [selectedScenario, setSelectedScenario] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [downloadingPDF, setDownloadingPDF] = useState(false);
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

  // Load analysis when year changes
  useEffect(() => {
    if (!selectedCompanyId || !selectedYear) {
      setAnalysis(null);
      return;
    }
    loadAnalysis();
  }, [selectedCompanyId, selectedYear]);

  // Load multi-year ratios when scenario is selected
  useEffect(() => {
    if (!selectedCompanyId || !selectedScenario) {
      setMultiYearRatios(null);
      return;
    }
    loadMultiYearRatios();
  }, [selectedCompanyId, selectedScenario]);

  const loadScenarios = async () => {
    if (!selectedCompanyId) return;

    try {
      const data = await getBudgetScenarios(selectedCompanyId);
      setScenarios(data);
      // Auto-select active scenario if available
      const activeScenario = data.find((s: any) => s.is_active === 1);
      if (activeScenario) {
        setSelectedScenario(activeScenario.id);
      } else if (data.length > 0) {
        setSelectedScenario(data[0].id);
      }
    } catch (err) {
      console.error("Error loading scenarios:", err);
    }
  };

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

  const loadMultiYearRatios = async () => {
    if (!selectedCompanyId || !selectedScenario) return;

    try {
      setLoading(true);
      setError(null);

      const data = await getMultiYearRatios(selectedCompanyId, selectedScenario);
      setMultiYearRatios(data);
    } catch (err) {
      console.error("Error loading multi-year ratios:", err);
      setError("Impossibile caricare gli indici pluriennali");
    } finally {
      setLoading(false);
    }
  };

  const handleDownloadPDF = async () => {
    if (!selectedCompanyId || !selectedScenario) return;
    try {
      setDownloadingPDF(true);
      await downloadReportPDF(selectedCompanyId, selectedScenario, selectedCompany?.name);
    } catch (err) {
      console.error("Error downloading PDF:", err);
      setError("Impossibile generare il report PDF");
    } finally {
      setDownloadingPDF(false);
    }
  };

  // Get color for Altman classification
  const getAltmanColor = (classification: string) => {
    switch (classification) {
      case "safe":
        return "border-green-500/50 bg-green-50 text-green-700 dark:bg-green-950/50 dark:text-green-400";
      case "gray_zone":
        return "border-yellow-500/50 bg-yellow-50 text-yellow-700 dark:bg-yellow-950/50 dark:text-yellow-400";
      case "distress":
        return "border-red-500/50 bg-red-50 text-red-700 dark:bg-red-950/50 dark:text-red-400";
      default:
        return "border-border bg-muted text-muted-foreground";
    }
  };

  // Get color for FGPMI rating
  const getFGPMIColor = (ratingCode: string) => {
    if (ratingCode.startsWith("A")) {
      return "border-green-500/50 bg-green-50 text-green-700 dark:bg-green-950/50 dark:text-green-400";
    } else if (ratingCode.startsWith("BB")) {
      return "border-yellow-500/50 bg-yellow-50 text-yellow-700 dark:bg-yellow-950/50 dark:text-yellow-400";
    } else {
      return "border-red-500/50 bg-red-50 text-red-700 dark:bg-red-950/50 dark:text-red-400";
    }
  };

  // Prepare radar chart data for financial ratios
  const prepareRadarData = () => {
    if (!analysis) return [];

    return [
      {
        metric: "Liquidita",
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
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          <span className="ml-3 text-lg text-muted-foreground">Caricamento...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Errore</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      </div>
    );
  }

  if (!selectedCompanyId) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <Alert className="border-yellow-500/50 bg-yellow-50 text-yellow-700 dark:bg-yellow-950/50 dark:text-yellow-400">
          <AlertTriangle className="h-4 w-4" />
          <AlertDescription>
            Seleziona un&apos;azienda per visualizzare l&apos;analisi
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  if (!selectedYear) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <Alert className="border-yellow-500/50 bg-yellow-50 text-yellow-700 dark:bg-yellow-950/50 dark:text-yellow-400">
          <AlertTriangle className="h-4 w-4" />
          <AlertDescription>
            Seleziona un anno per visualizzare l&apos;analisi
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  if (!analysis) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <Alert className="border-border bg-muted text-muted-foreground">
          <AlertDescription>Nessun dato disponibile</AlertDescription>
        </Alert>
      </div>
    );
  }

  const radarData = prepareRadarData();
  const altmanComponentsData = prepareAltmanComponentsData();
  const fgpmiIndicatorsData = prepareFGPMIIndicatorsData();

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <PageHeader
        title="Analisi Finanziaria Completa"
        description={`Indici finanziari, Altman Z-Score e Rating FGPMI per l'anno ${selectedYear}`}
        icon={<PieChart className="h-6 w-6" />}
      >
        {selectedScenario && (
          <Button
            variant="outline"
            onClick={handleDownloadPDF}
            disabled={downloadingPDF}
          >
            {downloadingPDF ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <Download className="h-4 w-4 mr-2" />
            )}
            {downloadingPDF ? "Generazione..." : "Scarica PDF"}
          </Button>
        )}
      </PageHeader>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <Card>
          <CardContent className="pt-6">
            <div className="text-sm text-muted-foreground mb-1">Ricavi</div>
            <div className="text-2xl font-bold text-foreground">
              {formatCurrency(analysis.summary.revenue)}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="text-sm text-muted-foreground mb-1">EBITDA</div>
            <div className="text-2xl font-bold text-foreground">
              {formatCurrency(analysis.summary.ebitda)}
            </div>
            <div className="text-xs text-muted-foreground">
              Margine: {formatPercentage(analysis.summary.ebitda_margin)}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="text-sm text-muted-foreground mb-1">Patrimonio Netto</div>
            <div className="text-2xl font-bold text-foreground">
              {formatCurrency(analysis.summary.total_equity)}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="text-sm text-muted-foreground mb-1">ROE</div>
            <div className="text-2xl font-bold text-foreground">
              {formatPercentage(analysis.summary.roe)}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Altman Z-Score Section */}
      <Card className="mb-6">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <Target className="h-5 w-5" />
            Altman Z-Score - Analisi del Rischio di Insolvenza
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Z-Score Result */}
            <div>
              <div
                className={cn(
                  "border-2 rounded-lg p-6 mb-4",
                  getAltmanColor(analysis.altman.classification)
                )}
              >
                <div className="text-sm font-medium mb-2">Z-Score</div>
                <div className="text-4xl font-bold mb-2">
                  {analysis.altman.z_score.toFixed(2)}
                </div>
                <div className="text-sm font-medium mb-1 flex items-center gap-1.5">
                  {analysis.altman.classification === "safe" && (
                    <>
                      <CheckCircle2 className="h-4 w-4" />
                      Zona Sicura
                    </>
                  )}
                  {analysis.altman.classification === "gray_zone" && (
                    <>
                      <AlertTriangle className="h-4 w-4" />
                      Zona d&apos;Ombra
                    </>
                  )}
                  {analysis.altman.classification === "distress" && (
                    <>
                      <XCircle className="h-4 w-4" />
                      Zona di Rischio
                    </>
                  )}
                </div>
                <div className="text-sm mt-2">
                  {analysis.altman.interpretation_it}
                </div>
              </div>

              <div className="text-xs text-muted-foreground space-y-1">
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
              <h3 className="text-md font-medium text-muted-foreground mb-3">
                Componenti del Z-Score
              </h3>
              <ChartContainer config={altmanChartConfig} className="h-[250px] w-full">
                <BarChart data={altmanComponentsData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="name" />
                  <YAxis />
                  <ChartTooltip
                    content={
                      <ChartTooltipContent
                        formatter={(value: any) => value.toFixed(4)}
                        labelFormatter={(label) => `Componente ${label}`}
                      />
                    }
                  />
                  <Bar dataKey="value" fill="var(--color-value)" />
                </BarChart>
              </ChartContainer>
              <div className="mt-2 text-xs text-muted-foreground space-y-1">
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
        </CardContent>
      </Card>

      {/* FGPMI Rating Section */}
      <Card className="mb-6">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <Star className="h-5 w-5" />
            Rating FGPMI - Valutazione Creditizia
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Rating Result */}
            <div>
              <div
                className={cn(
                  "border-2 rounded-lg p-6 mb-4",
                  getFGPMIColor(analysis.fgpmi.rating_code)
                )}
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
                  <div className="text-sm mt-1 flex items-center gap-1.5">
                    <Sparkles className="h-4 w-4" />
                    Bonus Fatturato: +{analysis.fgpmi.revenue_bonus} punti
                  </div>
                )}
              </div>

              <div className="text-xs text-muted-foreground space-y-1">
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
              <h3 className="text-md font-medium text-muted-foreground mb-3">
                Indicatori FGPMI
              </h3>
              <ChartContainer config={fgpmiChartConfig} className="h-[250px] w-full">
                <BarChart data={fgpmiIndicatorsData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="name" />
                  <YAxis />
                  <ChartTooltip
                    content={
                      <ChartTooltipContent
                        formatter={(value: any, name: any) => {
                          if (name === "points") return `${value} punti`;
                          if (name === "maxPoints") return `${value} max`;
                          return `${value.toFixed(1)}%`;
                        }}
                      />
                    }
                  />
                  <ChartLegend content={<ChartLegendContent />} />
                  <Bar dataKey="points" name="Punti" fill="var(--color-points)" />
                  <Bar dataKey="maxPoints" name="Max" fill="var(--color-maxPoints)" />
                </BarChart>
              </ChartContainer>
            </div>
          </div>

          {/* FGPMI Indicators Details */}
          <div className="mt-6">
            <Table>
              <TableHeader>
                <TableRow className="bg-muted/50">
                  <TableHead className="font-medium uppercase text-xs">
                    Indicatore
                  </TableHead>
                  <TableHead className="text-right font-medium uppercase text-xs">
                    Valore
                  </TableHead>
                  <TableHead className="text-right font-medium uppercase text-xs">
                    Punti
                  </TableHead>
                  <TableHead className="text-right font-medium uppercase text-xs">
                    Max
                  </TableHead>
                  <TableHead className="text-right font-medium uppercase text-xs">
                    %
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {Object.values(analysis.fgpmi.indicators).map((indicator) => (
                  <TableRow key={indicator.code}>
                    <TableCell className="whitespace-nowrap font-medium">
                      {indicator.name}
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-right">
                      {indicator.value.toFixed(4)}
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-right">
                      {indicator.points}
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-right text-muted-foreground">
                      {indicator.max_points}
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-right">
                      {indicator.percentage.toFixed(1)}%
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      {/* Financial Ratios Overview */}
      <Card className="mb-6">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <BarChart3 className="h-5 w-5" />
            Indici Finanziari
          </CardTitle>
        </CardHeader>
        <CardContent>
          {/* Radar Chart */}
          <div className="mb-6">
            <h3 className="text-md font-medium text-muted-foreground mb-3">
              Panoramica Indici Chiave
            </h3>
            <ChartContainer config={radarChartConfig} className="mx-auto aspect-square h-[400px] w-full">
              <RadarChart data={radarData}>
                <PolarGrid />
                <PolarAngleAxis dataKey="metric" />
                <PolarRadiusAxis angle={90} domain={[0, 100]} />
                <Radar
                  name="Performance"
                  dataKey="value"
                  stroke="var(--color-value)"
                  fill="var(--color-value)"
                  fillOpacity={0.6}
                />
                <ChartLegend content={<ChartLegendContent />} />
              </RadarChart>
            </ChartContainer>
          </div>

          {/* Ratios Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            {/* Liquidity Ratios */}
            <div>
              <h3 className="text-sm font-semibold text-muted-foreground mb-3 flex items-center gap-1.5">
                <Droplets className="h-4 w-4" />
                Liquidita
              </h3>
              <div className="space-y-2">
                <div className="flex justify-between">
                  <span className="text-sm text-muted-foreground">Current Ratio:</span>
                  <span className="text-sm font-medium text-foreground">
                    {analysis.ratios.liquidity.current_ratio.toFixed(2)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-sm text-muted-foreground">Quick Ratio:</span>
                  <span className="text-sm font-medium text-foreground">
                    {analysis.ratios.liquidity.quick_ratio.toFixed(2)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-sm text-muted-foreground">Acid Test:</span>
                  <span className="text-sm font-medium text-foreground">
                    {analysis.ratios.liquidity.acid_test.toFixed(2)}
                  </span>
                </div>
              </div>
            </div>

            {/* Solvency Ratios */}
            <div>
              <h3 className="text-sm font-semibold text-muted-foreground mb-3 flex items-center gap-1.5">
                <Landmark className="h-4 w-4" />
                Solvibilita
              </h3>
              <div className="space-y-2">
                <div className="flex justify-between">
                  <span className="text-sm text-muted-foreground">Autonomia:</span>
                  <span className="text-sm font-medium text-foreground">
                    {formatPercentage(analysis.ratios.solvency.autonomy_index)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-sm text-muted-foreground">Debt/Equity:</span>
                  <span className="text-sm font-medium text-foreground">
                    {analysis.ratios.solvency.debt_to_equity.toFixed(2)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-sm text-muted-foreground">Leverage:</span>
                  <span className="text-sm font-medium text-foreground">
                    {analysis.ratios.solvency.leverage_ratio.toFixed(2)}
                  </span>
                </div>
              </div>
            </div>

            {/* Profitability Ratios */}
            <div>
              <h3 className="text-sm font-semibold text-muted-foreground mb-3 flex items-center gap-1.5">
                <Coins className="h-4 w-4" />
                Redditivita
              </h3>
              <div className="space-y-2">
                <div className="flex justify-between">
                  <span className="text-sm text-muted-foreground">ROE:</span>
                  <span className="text-sm font-medium text-foreground">
                    {formatPercentage(analysis.ratios.profitability.roe)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-sm text-muted-foreground">ROI:</span>
                  <span className="text-sm font-medium text-foreground">
                    {formatPercentage(analysis.ratios.profitability.roi)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-sm text-muted-foreground">ROS:</span>
                  <span className="text-sm font-medium text-foreground">
                    {formatPercentage(analysis.ratios.profitability.ros)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-sm text-muted-foreground">EBITDA Margin:</span>
                  <span className="text-sm font-medium text-foreground">
                    {formatPercentage(analysis.ratios.profitability.ebitda_margin)}
                  </span>
                </div>
              </div>
            </div>

            {/* Activity Ratios */}
            <div>
              <h3 className="text-sm font-semibold text-muted-foreground mb-3 flex items-center gap-1.5">
                <RefreshCw className="h-4 w-4" />
                Attivita
              </h3>
              <div className="space-y-2">
                <div className="flex justify-between">
                  <span className="text-sm text-muted-foreground">Rotazione Attivo:</span>
                  <span className="text-sm font-medium text-foreground">
                    {analysis.ratios.activity.asset_turnover.toFixed(2)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-sm text-muted-foreground">Giorni Credito:</span>
                  <span className="text-sm font-medium text-foreground">
                    {analysis.ratios.activity.receivables_turnover_days.toFixed(0)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-sm text-muted-foreground">Giorni Debito:</span>
                  <span className="text-sm font-medium text-foreground">
                    {analysis.ratios.activity.payables_turnover_days.toFixed(0)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-sm text-muted-foreground">Ciclo Cassa:</span>
                  <span className="text-sm font-medium text-foreground">
                    {analysis.ratios.activity.cash_conversion_cycle.toFixed(0)}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Working Capital Metrics */}
      <Card className="mb-6">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <Hash className="h-5 w-5" />
            Capitale Circolante
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="rounded-lg p-4 bg-primary/10">
              <div className="text-sm text-primary mb-1">CCLN</div>
              <div className="text-xl font-bold text-foreground">
                {formatCurrency(analysis.ratios.working_capital.ccln)}
              </div>
            </div>
            <div className="rounded-lg p-4 bg-green-500/10 dark:bg-green-500/15">
              <div className="text-sm text-green-700 dark:text-green-400 mb-1">CCN</div>
              <div className="text-xl font-bold text-foreground">
                {formatCurrency(analysis.ratios.working_capital.ccn)}
              </div>
            </div>
            <div className="rounded-lg p-4 bg-purple-500/10 dark:bg-purple-500/15">
              <div className="text-sm text-purple-700 dark:text-purple-400 mb-1">MS</div>
              <div className="text-xl font-bold text-foreground">
                {formatCurrency(analysis.ratios.working_capital.ms)}
              </div>
            </div>
            <div className="rounded-lg p-4 bg-orange-500/10 dark:bg-orange-500/15">
              <div className="text-sm text-orange-700 dark:text-orange-400 mb-1">MT</div>
              <div className="text-xl font-bold text-foreground">
                {formatCurrency(analysis.ratios.working_capital.mt)}
              </div>
            </div>
          </div>
          <div className="mt-4 text-xs text-muted-foreground space-y-1">
            <div>CCLN = Capitale Circolante Lordo Netto (Attivo Corrente)</div>
            <div>CCN = Capitale Circolante Netto (Attivo Corrente - Passivo Corrente)</div>
            <div>MS = Margine di Struttura (Patrimonio Netto - Immobilizzazioni)</div>
            <div>MT = Margine di Tesoreria (Liquidita + Crediti - Passivo Corrente)</div>
          </div>
        </CardContent>
      </Card>

      {/* Multi-Year Ratios Table */}
      {multiYearRatios && (
        <Card>
          <CardHeader>
            <div className="flex justify-between items-center">
              <CardTitle className="flex items-center gap-2 text-lg">
                <BarChart3 className="h-5 w-5" />
                Indici Finanziari Pluriennali
              </CardTitle>
              {scenarios.length > 0 && (
                <Select
                  value={selectedScenario?.toString() || ""}
                  onValueChange={(value) => setSelectedScenario(Number(value))}
                >
                  <SelectTrigger className="w-[220px]">
                    <SelectValue placeholder="Seleziona scenario" />
                  </SelectTrigger>
                  <SelectContent>
                    {scenarios.map((s) => (
                      <SelectItem key={s.id} value={s.id.toString()}>
                        {s.name} {s.is_active === 1 && "(Attivo)"}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </div>
          </CardHeader>
          <CardContent>
            <TooltipProvider delayDuration={200}>
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="border-b-2 border-border">
                    <th className="text-left py-3 px-4 font-semibold text-muted-foreground sticky left-0 bg-background z-10">INDICE</th>
                    <th className="text-left py-3 px-4 font-semibold text-muted-foreground">FORMULA</th>
                    {multiYearRatios.years.map((year) => (
                      <th key={year} className="text-right py-3 px-4 font-semibold text-muted-foreground">
                        {year}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {/* ANALISI STRUTTURALE O PER MARGINI */}
                  <tr className="bg-primary/10">
                    <td colSpan={2 + multiYearRatios.years.length} className="py-2 px-4 font-bold text-primary">
                      ANALISI STRUTTURALE O PER MARGINI
                    </td>
                  </tr>
                  <tr className="border-b border-border hover:bg-muted/50">
                    <td className="py-2 px-4 sticky left-0 bg-background">MARGINE DI STRUTTURA</td>
                    <FormulaCell formula="CN-AF" />
                    {multiYearRatios.ratios.map((r, i) => (
                      <td key={i} className="py-2 px-4 text-right font-medium">
                        {formatCurrency(r.working_capital.ms)}
                      </td>
                    ))}
                  </tr>
                  <tr className="border-b border-border hover:bg-muted/50">
                    <td className="py-2 px-4 sticky left-0 bg-background">CAPITALE CIRCOLANTE NETTO</td>
                    <FormulaCell formula="[LI+LD+RD]-PC" />
                    {multiYearRatios.ratios.map((r, i) => (
                      <td key={i} className="py-2 px-4 text-right font-medium">
                        {formatCurrency(r.working_capital.ccn)}
                      </td>
                    ))}
                  </tr>
                  <tr className="border-b border-border hover:bg-muted/50">
                    <td className="py-2 px-4 sticky left-0 bg-background">MARGINE DI TESORERIA</td>
                    <FormulaCell formula="[LI+LD]-PC" />
                    {multiYearRatios.ratios.map((r, i) => (
                      <td key={i} className="py-2 px-4 text-right font-medium">
                        {formatCurrency(r.working_capital.mt)}
                      </td>
                    ))}
                  </tr>

                  {/* INDICI DI SOLIDITA */}
                  <tr className="bg-primary/10">
                    <td colSpan={2 + multiYearRatios.years.length} className="py-2 px-4 font-bold text-primary pt-6">
                      INDICI DI SOLIDITA
                    </td>
                  </tr>
                  <tr className="border-b border-border hover:bg-muted/50">
                    <td className="py-2 px-4 sticky left-0 bg-background">INDICE DI COPERTURA DELLE IMMOB. CON FONTI DUREVOLI</td>
                    <FormulaCell formula="(CN+PF)/AF" />
                    {multiYearRatios.ratios.map((r, i) => (
                      <td key={i} className="py-2 px-4 text-right font-medium">
                        {formatPercentage(r.coverage.fixed_assets_coverage_with_equity_and_ltdebt)}
                      </td>
                    ))}
                  </tr>
                  <tr className="border-b border-border hover:bg-muted/50">
                    <td className="py-2 px-4 sticky left-0 bg-background">INDICE DI COPERTURA DELLE IMMOB. CON CAPITALE PROPRIO</td>
                    <FormulaCell formula="CN/AF" />
                    {multiYearRatios.ratios.map((r, i) => (
                      <td key={i} className="py-2 px-4 text-right font-medium">
                        {formatPercentage(r.coverage.fixed_assets_coverage_with_equity)}
                      </td>
                    ))}
                  </tr>
                  <tr className="border-b border-border hover:bg-muted/50">
                    <td className="py-2 px-4 sticky left-0 bg-background">INDICE DI INDIPENDENZA DAI TERZI</td>
                    <FormulaCell formula="CN/(PC+PF)" />
                    {multiYearRatios.ratios.map((r, i) => (
                      <td key={i} className="py-2 px-4 text-right font-medium">
                        {formatPercentage(r.coverage.independence_from_third_parties)}
                      </td>
                    ))}
                  </tr>

                  {/* INDICI DI LIQUIDITA */}
                  <tr className="bg-primary/10">
                    <td colSpan={2 + multiYearRatios.years.length} className="py-2 px-4 font-bold text-primary pt-6">
                      INDICI DI LIQUIDITA
                    </td>
                  </tr>
                  <tr className="border-b border-border hover:bg-muted/50">
                    <td className="py-2 px-4 sticky left-0 bg-background">INDICE DI LIQUIDITA CORRENTE O DI DISPONIBILITA</td>
                    <FormulaCell formula="(LI+LD+RD)/PC" />
                    {multiYearRatios.ratios.map((r, i) => (
                      <td key={i} className="py-2 px-4 text-right font-medium">
                        {formatPercentage(r.liquidity.current_ratio)}
                      </td>
                    ))}
                  </tr>
                  <tr className="border-b border-border hover:bg-muted/50">
                    <td className="py-2 px-4 sticky left-0 bg-background">INDICE SECCO DI LIQUIDITA (ACID TEST RATIO - ATR)</td>
                    <FormulaCell formula="(LI+LD)/PC" />
                    {multiYearRatios.ratios.map((r, i) => (
                      <td key={i} className="py-2 px-4 text-right font-medium">
                        {formatPercentage(r.liquidity.quick_ratio)}
                      </td>
                    ))}
                  </tr>

                  {/* INDICI DI ROTAZIONE E DURATA */}
                  <tr className="bg-primary/10">
                    <td colSpan={2 + multiYearRatios.years.length} className="py-2 px-4 font-bold text-primary pt-6">
                      INDICI DI ROTAZIONE E DURATA
                    </td>
                  </tr>
                  <tr className="border-b border-border hover:bg-muted/50">
                    <td className="py-2 px-4 sticky left-0 bg-background">TURNOVER DEL MAGAZZINO (TdM)</td>
                    <FormulaCell formula="CO/RD" />
                    {multiYearRatios.ratios.map((r, i) => (
                      <td key={i} className="py-2 px-4 text-right font-medium">
                        {r.turnover.inventory_turnover.toFixed(2)}
                      </td>
                    ))}
                  </tr>
                  <tr className="border-b border-border hover:bg-muted/50">
                    <td className="py-2 px-4 sticky left-0 bg-background">TURNOVER DEI CREDITI (TdC)</td>
                    <FormulaCell formula="RIC/LD" />
                    {multiYearRatios.ratios.map((r, i) => (
                      <td key={i} className="py-2 px-4 text-right font-medium">
                        {r.turnover.receivables_turnover.toFixed(2)}
                      </td>
                    ))}
                  </tr>
                  <tr className="border-b border-border hover:bg-muted/50">
                    <td className="py-2 px-4 sticky left-0 bg-background">TURNOVER DEI DEBITI (TdD)</td>
                    <FormulaCell formula="(CO+AC+ODG)/PC" />
                    {multiYearRatios.ratios.map((r, i) => (
                      <td key={i} className="py-2 px-4 text-right font-medium">
                        {r.turnover.payables_turnover.toFixed(2)}
                      </td>
                    ))}
                  </tr>
                  <tr className="border-b border-border hover:bg-muted/50">
                    <td className="py-2 px-4 sticky left-0 bg-background">TURNOVER DEL CAPITALE CIRCOLANTE NETTO (TdCCN)</td>
                    <FormulaCell formula="RIC/CCN" />
                    {multiYearRatios.ratios.map((r, i) => (
                      <td key={i} className="py-2 px-4 text-right font-medium">
                        {r.turnover.working_capital_turnover.toFixed(2)}
                      </td>
                    ))}
                  </tr>
                  <tr className="border-b border-border hover:bg-muted/50">
                    <td className="py-2 px-4 sticky left-0 bg-background">TURNOVER DELLE ATTIVITA TOTALI (TdAT)</td>
                    <FormulaCell formula="RIC/TA" />
                    {multiYearRatios.ratios.map((r, i) => (
                      <td key={i} className="py-2 px-4 text-right font-medium">
                        {r.turnover.total_assets_turnover.toFixed(2)}
                      </td>
                    ))}
                  </tr>
                  <tr className="border-b border-border hover:bg-muted/50">
                    <td className="py-2 px-4 sticky left-0 bg-background">DURATA DEL MAGAZZINO (IN GIORNI)</td>
                    <FormulaCell formula="360/TdM" />
                    {multiYearRatios.ratios.map((r, i) => (
                      <td key={i} className="py-2 px-4 text-right font-medium">
                        {r.activity.inventory_turnover_days.toFixed(0)} gg
                      </td>
                    ))}
                  </tr>
                  <tr className="border-b border-border hover:bg-muted/50">
                    <td className="py-2 px-4 sticky left-0 bg-background">DURATA DEI CREDITI (IN GIORNI)</td>
                    <FormulaCell formula="360/TdC" />
                    {multiYearRatios.ratios.map((r, i) => (
                      <td key={i} className="py-2 px-4 text-right font-medium">
                        {r.activity.receivables_turnover_days.toFixed(0)} gg
                      </td>
                    ))}
                  </tr>
                  <tr className="border-b border-border hover:bg-muted/50">
                    <td className="py-2 px-4 sticky left-0 bg-background">DURATA DEI DEBITI (IN GIORNI)</td>
                    <FormulaCell formula="360/TdD" />
                    {multiYearRatios.ratios.map((r, i) => (
                      <td key={i} className="py-2 px-4 text-right font-medium">
                        {r.activity.payables_turnover_days.toFixed(0)} gg
                      </td>
                    ))}
                  </tr>
                  <tr className="border-b border-border hover:bg-muted/50">
                    <td className="py-2 px-4 sticky left-0 bg-background">DURATA DEL CAPITALE CIRCOLANTE NETTO (IN GIORNI)</td>
                    <FormulaCell formula="360/TdCCN" />
                    {multiYearRatios.ratios.map((r, i) => (
                      <td key={i} className="py-2 px-4 text-right font-medium">
                        {r.activity.working_capital_days.toFixed(0)} gg
                      </td>
                    ))}
                  </tr>
                  <tr className="border-b border-border hover:bg-muted/50">
                    <td className="py-2 px-4 sticky left-0 bg-background">DURATA DELLE ATTIVITA TOTALI (IN GIORNI)</td>
                    <FormulaCell formula="360/TdAT" />
                    {multiYearRatios.ratios.map((r, i) => (
                      <td key={i} className="py-2 px-4 text-right font-medium">
                        {(360 / r.activity.asset_turnover).toFixed(0)} gg
                      </td>
                    ))}
                  </tr>

                  {/* INDICI DI REDDITIVITA */}
                  <tr className="bg-primary/10">
                    <td colSpan={2 + multiYearRatios.years.length} className="py-2 px-4 font-bold text-primary pt-6">
                      INDICI DI REDDITIVITA
                    </td>
                  </tr>
                  <tr className="border-b border-border hover:bg-muted/50">
                    <td className="py-2 px-4 sticky left-0 bg-background">REDDITIVITA DEL CAPITALE PROPRIO (ROE)</td>
                    <FormulaCell formula="RN/CN" />
                    {multiYearRatios.ratios.map((r, i) => (
                      <td key={i} className="py-2 px-4 text-right font-medium">
                        {formatPercentage(r.profitability.roe)}
                      </td>
                    ))}
                  </tr>
                  <tr className="border-b border-border hover:bg-muted/50">
                    <td className="py-2 px-4 sticky left-0 bg-background">REDDITIVITA DEL CAPITALE INVESTITO (ROI)</td>
                    <FormulaCell formula="MON/TA" />
                    {multiYearRatios.ratios.map((r, i) => (
                      <td key={i} className="py-2 px-4 text-right font-medium">
                        {formatPercentage(r.profitability.roi)}
                      </td>
                    ))}
                  </tr>
                  <tr className="border-b border-border hover:bg-muted/50">
                    <td className="py-2 px-4 sticky left-0 bg-background">REDDITIVITA DELLE VENDITE (ROS)</td>
                    <FormulaCell formula="MON/RIC" />
                    {multiYearRatios.ratios.map((r, i) => (
                      <td key={i} className="py-2 px-4 text-right font-medium">
                        {formatPercentage(r.profitability.ros)}
                      </td>
                    ))}
                  </tr>
                  <tr className="border-b border-border hover:bg-muted/50">
                    <td className="py-2 px-4 sticky left-0 bg-background">COSTO DEL DENARO A PRESTITO (ROD)</td>
                    <FormulaCell formula="OF/(PC+PF)" />
                    {multiYearRatios.ratios.map((r, i) => (
                      <td key={i} className="py-2 px-4 text-right font-medium">
                        {formatPercentage(r.profitability.rod)}
                      </td>
                    ))}
                  </tr>
                  <tr className="border-b border-border hover:bg-muted/50">
                    <td className="py-2 px-4 sticky left-0 bg-background">ROI - ROD (SPREAD)</td>
                    <FormulaCell formula="(ROI-ROD)" />
                    {multiYearRatios.ratios.map((r, i) => (
                      <td key={i} className="py-2 px-4 text-right font-medium">
                        {r.extended_profitability.spread.toFixed(2)}
                      </td>
                    ))}
                  </tr>
                  <tr className="border-b border-border hover:bg-muted/50">
                    <td className="py-2 px-4 sticky left-0 bg-background">EFFETTO DI LEVA FINANZIARIA O TASSO DI RISCHIO</td>
                    <FormulaCell formula="(PC+PF)/CN" />
                    {multiYearRatios.ratios.map((r, i) => (
                      <td key={i} className="py-2 px-4 text-right font-medium">
                        {formatPercentage(r.extended_profitability.financial_leverage_effect)}
                      </td>
                    ))}
                  </tr>
                  <tr className="border-b border-border hover:bg-muted/50">
                    <td className="py-2 px-4 sticky left-0 bg-background">MARGINE OPERATIVO LORDO SULLE VENDITE</td>
                    <FormulaCell formula="MOL/RIC" />
                    {multiYearRatios.ratios.map((r, i) => (
                      <td key={i} className="py-2 px-4 text-right font-medium">
                        {formatPercentage(r.extended_profitability.ebitda_on_sales)}
                      </td>
                    ))}
                  </tr>
                  <tr className="border-b border-border hover:bg-muted/50">
                    <td className="py-2 px-4 sticky left-0 bg-background">INCIDENZA DEGLI ONERI FINANZIARI SUL FATTURATO</td>
                    <FormulaCell formula="OF/RIC" />
                    {multiYearRatios.ratios.map((r, i) => (
                      <td key={i} className="py-2 px-4 text-right font-medium">
                        {formatPercentage(r.extended_profitability.financial_charges_on_revenue)}
                      </td>
                    ))}
                  </tr>

                  {/* INDICI DI EFFICIENZA */}
                  <tr className="bg-primary/10">
                    <td colSpan={2 + multiYearRatios.years.length} className="py-2 px-4 font-bold text-primary pt-6">
                      INDICI DI EFFICIENZA
                    </td>
                  </tr>
                  <tr className="border-b border-border hover:bg-muted/50">
                    <td className="py-2 px-4 sticky left-0 bg-background">RENDIMENTO DEI DIPENDENTI</td>
                    <FormulaCell formula="RIC/CL" />
                    {multiYearRatios.ratios.map((r, i) => (
                      <td key={i} className="py-2 px-4 text-right font-medium">
                        {r.efficiency.revenue_per_employee_cost.toFixed(2)}
                      </td>
                    ))}
                  </tr>
                  <tr className="border-b border-border hover:bg-muted/50">
                    <td className="py-2 px-4 sticky left-0 bg-background">RENDIMENTO DELLE MATERIE</td>
                    <FormulaCell formula="RIC/CO" />
                    {multiYearRatios.ratios.map((r, i) => (
                      <td key={i} className="py-2 px-4 text-right font-medium">
                        {r.efficiency.revenue_per_materials_cost.toFixed(2)}
                      </td>
                    ))}
                  </tr>

                  {/* BREAK EVEN POINT (BEP) */}
                  <tr className="bg-primary/10">
                    <td colSpan={2 + multiYearRatios.years.length} className="py-2 px-4 font-bold text-primary pt-6">
                      BREAK EVEN POINT (BEP)
                    </td>
                  </tr>
                  <tr className="border-b border-border hover:bg-muted/50">
                    <td className="py-2 px-4 sticky left-0 bg-background">RICAVI BEP</td>
                    <FormulaCell formula="CF/%MdC" />
                    {multiYearRatios.ratios.map((r, i) => (
                      <td key={i} className="py-2 px-4 text-right font-medium">
                        {formatCurrency(r.break_even.break_even_revenue)}
                      </td>
                    ))}
                  </tr>
                  <tr className="border-b border-border hover:bg-muted/50">
                    <td className="py-2 px-4 sticky left-0 bg-background">MARGINE DI SICUREZZA</td>
                    <FormulaCell formula="1-(RICAVI BEP/RIC)" />
                    {multiYearRatios.ratios.map((r, i) => (
                      <td key={i} className="py-2 px-4 text-right font-medium">
                        {formatPercentage(r.break_even.safety_margin)}
                      </td>
                    ))}
                  </tr>
                  <tr className="border-b border-border hover:bg-muted/50">
                    <td className="py-2 px-4 sticky left-0 bg-background">LEVA OPERATIVA</td>
                    <FormulaCell formula="MdC/MON" />
                    {multiYearRatios.ratios.map((r, i) => (
                      <td key={i} className="py-2 px-4 text-right font-medium">
                        {r.break_even.operating_leverage.toFixed(2)}
                      </td>
                    ))}
                  </tr>
                  <tr className="border-b border-border hover:bg-muted/50">
                    <td className="py-2 px-4 sticky left-0 bg-background">MOLTIPLICATORE DEI COSTI FISSI</td>
                    <FormulaCell formula="1/%MdC" />
                    {multiYearRatios.ratios.map((r, i) => (
                      <td key={i} className="py-2 px-4 text-right font-medium">
                        {r.break_even.fixed_cost_multiplier.toFixed(2)}
                      </td>
                    ))}
                  </tr>
                </tbody>
              </table>
            </div>
            </TooltipProvider>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
