"use client";

import { useState, useEffect } from "react";
import { useApp } from "@/contexts/AppContext";
import { useScenarios, useAnalysis, getPreferredScenario } from "@/hooks/use-queries";
import { downloadReportPDF, getReportAIComments, generateReportAIComments, type ReportAICommentsResponse } from "@/lib/api";
import type { ScenarioAnalysis, BudgetScenario } from "@/types/api";
import { PageHeader } from "@/components/page-header";
import { ScenarioSelector } from "@/components/scenario-selector";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { FileText, Download, Loader2, AlertTriangle, Sparkles } from "lucide-react";
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
import { ReportAIComment } from "@/components/report/report-ai-comment";

export default function ReportPage() {
  const { selectedCompanyId, selectedCompany } = useApp();

  const { data: scenarios = [], isLoading: scenariosLoading } = useScenarios(selectedCompanyId);
  const [selectedScenario, setSelectedScenario] = useState<BudgetScenario | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [aiComments, setAiComments] = useState<ReportAICommentsResponse>({});
  const [aiCommentsLoading, setAiCommentsLoading] = useState(false);

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
  const error = analysisError ? "Errore nel caricamento dell'analisi" : null;

  // Load stored AI comments when scenario/analysis changes
  useEffect(() => {
    if (!selectedCompanyId || !selectedScenario) {
      setAiComments({});
      return;
    }
    let cancelled = false;
    getReportAIComments(selectedCompanyId, selectedScenario.id)
      .then((data) => {
        if (!cancelled) setAiComments(data);
      })
      .catch(() => {
        if (!cancelled) setAiComments({});
      });
    return () => { cancelled = true; };
  }, [selectedCompanyId, selectedScenario]);

  // Generate AI comments on button click
  const handleGenerateAIComments = async () => {
    if (!selectedCompanyId || !selectedScenario) return;
    setAiCommentsLoading(true);
    try {
      const data = await generateReportAIComments(selectedCompanyId, selectedScenario.id);
      setAiComments(data);
      if (Object.keys(data).length > 0) {
        toast.success("Commenti AI generati");
      } else {
        toast.info("Nessun commento generato (chiave API mancante?)");
      }
    } catch {
      toast.error("Errore nella generazione dei commenti AI");
    } finally {
      setAiCommentsLoading(false);
    }
  };

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
            onClick={handleGenerateAIComments}
            disabled={aiCommentsLoading || !analysisData}
            variant="outline"
          >
            {aiCommentsLoading ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <Sparkles className="h-4 w-4 mr-2" />
            )}
            Commenti AI
          </Button>
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
            Nessuno scenario budget trovato. Vai alla pagina Scenari per
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
            <ReportAIComment comment={aiComments.dashboard_comment} loading={aiCommentsLoading} />
            <ReportComposition data={analysisData} />
            <ReportAIComment comment={aiComments.composition_comment} loading={aiCommentsLoading} />
            <ReportIncomeMargins data={analysisData} />
            <ReportAIComment comment={aiComments.income_margins_comment} loading={aiCommentsLoading} />
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
