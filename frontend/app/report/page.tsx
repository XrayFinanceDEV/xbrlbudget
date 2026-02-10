"use client";

import { useState, useEffect, useCallback } from "react";
import { useApp } from "@/contexts/AppContext";
import {
  getScenarioAnalysis,
  getBudgetScenarios,
  downloadReportPDF,
} from "@/lib/api";
import type { ScenarioAnalysis, BudgetScenario } from "@/types/api";
import { PageHeader } from "@/components/page-header";
import { ScenarioSelector } from "@/components/scenario-selector";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { FileText, Download, Loader2, AlertTriangle } from "lucide-react";
import { toast } from "sonner";

import { ReportTOC } from "@/components/report/report-toc";
import { ReportCover } from "@/components/report/report-cover";
import { ReportDashboard } from "@/components/report/report-dashboard";
import { ReportComposition } from "@/components/report/report-composition";
import { ReportIncomeMargins } from "@/components/report/report-income-margins";
import { ReportStructural } from "@/components/report/report-structural";
import { ReportRatios } from "@/components/report/report-ratios";
import { ReportScoring } from "@/components/report/report-scoring";
import { ReportBreakEven } from "@/components/report/report-break-even";
import { ReportCashflow } from "@/components/report/report-cashflow";
import { ReportAppendices } from "@/components/report/report-appendices";
import { ReportNotes } from "@/components/report/report-notes";

export default function ReportPage() {
  const { selectedCompanyId, selectedCompany } = useApp();

  const [scenarios, setScenarios] = useState<BudgetScenario[]>([]);
  const [selectedScenario, setSelectedScenario] = useState<BudgetScenario | null>(null);
  const [analysisData, setAnalysisData] = useState<ScenarioAnalysis | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);

  // Load scenarios when company changes
  useEffect(() => {
    if (!selectedCompanyId) {
      setScenarios([]);
      setSelectedScenario(null);
      setAnalysisData(null);
      return;
    }

    const loadScenarios = async () => {
      try {
        const data = await getBudgetScenarios(selectedCompanyId);
        setScenarios(data);
        if (data.length > 0) {
          const active = data.find((s) => s.is_active) || data[0];
          setSelectedScenario(active);
        } else {
          setSelectedScenario(null);
          setAnalysisData(null);
        }
      } catch {
        setScenarios([]);
        setSelectedScenario(null);
      }
    };

    loadScenarios();
  }, [selectedCompanyId]);

  // Load analysis data when scenario changes
  const loadAnalysis = useCallback(async () => {
    if (!selectedCompanyId || !selectedScenario) {
      setAnalysisData(null);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const data = await getScenarioAnalysis(selectedCompanyId, selectedScenario.id);
      setAnalysisData(data);
    } catch (err: any) {
      const msg = err?.response?.data?.detail || "Errore nel caricamento dell'analisi";
      setError(msg);
      setAnalysisData(null);
    } finally {
      setLoading(false);
    }
  }, [selectedCompanyId, selectedScenario]);

  useEffect(() => {
    loadAnalysis();
  }, [loadAnalysis]);

  // PDF download
  const handleDownload = async () => {
    if (!selectedCompanyId || !selectedScenario) return;

    setDownloading(true);
    try {
      await downloadReportPDF(
        selectedCompanyId,
        selectedScenario.id,
        selectedCompany?.name
      );
      toast.success("Report PDF scaricato");
    } catch {
      toast.error("Errore nel download del PDF");
    } finally {
      setDownloading(false);
    }
  };

  if (!selectedCompanyId) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <PageHeader
          title="Report Analisi Finanziaria"
          description="Seleziona un'azienda dalla home page per visualizzare il report"
          icon={<FileText className="h-6 w-6" />}
        />
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
      <PageHeader
        title="Report Analisi Finanziaria"
        description={selectedCompany?.name}
        icon={<FileText className="h-6 w-6" />}
      >
        <div className="flex items-center gap-3">
          {scenarios.length > 0 && (
            <ScenarioSelector
              scenarios={scenarios}
              selectedScenario={selectedScenario}
              onSelect={setSelectedScenario}
              label="Scenario:"
            />
          )}
          <Button
            onClick={handleDownload}
            disabled={downloading || !analysisData}
            variant="outline"
          >
            {downloading ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <Download className="h-4 w-4 mr-2" />
            )}
            Scarica PDF
          </Button>
        </div>
      </PageHeader>

      {error && (
        <Alert variant="destructive" className="mb-6">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Errore</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {loading && (
        <Card className="mb-6">
          <CardContent className="flex items-center justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            <span className="ml-3 text-muted-foreground">Caricamento analisi...</span>
          </CardContent>
        </Card>
      )}

      {!loading && !analysisData && !error && scenarios.length === 0 && (
        <Alert className="mb-6">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Nessuno Scenario</AlertTitle>
          <AlertDescription>
            Nessuno scenario budget trovato. Vai alla pagina Input Ipotesi per
            creare uno scenario e generare le previsioni.
          </AlertDescription>
        </Alert>
      )}

      {analysisData && (
        <div className="flex gap-6">
          <ReportTOC />
          <div className="flex-1 min-w-0 space-y-6">
            <ReportCover data={analysisData} />
            <ReportDashboard data={analysisData} />
            <ReportComposition data={analysisData} />
            <ReportIncomeMargins data={analysisData} />
            <ReportStructural data={analysisData} />
            <ReportRatios data={analysisData} />
            <ReportScoring data={analysisData} />
            <ReportBreakEven data={analysisData} />
            <ReportCashflow data={analysisData} />
            <ReportAppendices data={analysisData} />
            <ReportNotes />
          </div>
        </div>
      )}
    </div>
  );
}
