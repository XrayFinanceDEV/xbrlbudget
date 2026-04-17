"use client";

import { useState, useEffect } from "react";
import { useApp } from "@/contexts/AppContext";
import { useScenarios, useAnalysis, getPreferredScenario } from "@/hooks/use-queries";
import { getReportAIComments, generateReportAIComments, saveReportAIComments, type ReportAICommentsResponse } from "@/lib/api";
import type { ScenarioAnalysis, BudgetScenario } from "@/types/api";
import { PageHeader } from "@/components/page-header";
import { ScenarioSelector } from "@/components/scenario-selector";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Textarea } from "@/components/ui/textarea";
import { FileText, Loader2, AlertTriangle, Sparkles, Printer } from "lucide-react";
import { cn } from "@/lib/utils";
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

  // Save AI comments on blur (user edits)
  const handleCommentChange = (key: keyof ReportAICommentsResponse, value: string) => {
    setAiComments((prev) => ({ ...prev, [key]: value }));
  };

  const handleCommentBlur = async () => {
    if (!selectedCompanyId || !selectedScenario) return;
    try {
      await saveReportAIComments(selectedCompanyId, selectedScenario.id, aiComments);
    } catch {
      // silent — toast on repeated failures would be noisy
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
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 print:px-0 print:py-0 print:max-w-none">
      <div className="print:hidden">
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
              onClick={() => setTimeout(() => window.print(), 100)}
              disabled={!analysisData}
              variant="outline"
            >
              <Printer className="h-4 w-4 mr-2" />
              Stampa
            </Button>
          </div>
        </PageHeader>
      </div>

      {error && (
        <Alert variant="destructive" className="mb-6 print:hidden">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Errore</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {loading && (
        <Card className="mb-6 print:hidden">
          <CardContent className="flex items-center justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            <span className="ml-3 text-muted-foreground">Caricamento analisi...</span>
          </CardContent>
        </Card>
      )}

      {!loading && !analysisData && !error && scenarios.length === 0 && (
        <Alert className="mb-6 print:hidden">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Nessuno Scenario</AlertTitle>
          <AlertDescription>
            Nessuno scenario budget trovato. Vai alla pagina Scenari per
            creare uno scenario e generare le previsioni.
          </AlertDescription>
        </Alert>
      )}

      {analysisData && (
        <div className="flex gap-6 print:block">
          <div className="print:hidden">
            <ReportTOC />
          </div>
          <div className="flex-1 min-w-0 space-y-6 print:space-y-2">
            <div className="report-section">
              <ReportCover data={analysisData} />
            </div>
            {/* Editable overall AI comment — like Stampa tab CommentBlock */}
            <div className={cn("report-ai-comment rounded-md border border-border/60 bg-muted/20 p-3 print:p-2", !aiComments.overall_comment && !aiCommentsLoading && "print:hidden")}>
              {aiCommentsLoading ? (
                <div className="flex items-start gap-3 py-1">
                  <Sparkles className="h-4 w-4 mt-0.5 text-muted-foreground shrink-0 animate-pulse" />
                  <div className="flex-1 space-y-2">
                    <div className="h-4 w-full bg-muted animate-pulse rounded" />
                    <div className="h-4 w-3/4 bg-muted animate-pulse rounded" />
                  </div>
                </div>
              ) : (
                <>
                  <Textarea
                    value={aiComments.overall_comment ?? ""}
                    onChange={(e) => handleCommentChange("overall_comment", e.target.value)}
                    onBlur={handleCommentBlur}
                    placeholder="Commento complessivo sull'analisi (clicca 'Commenti AI' per generare o scrivi manualmente)..."
                    className="min-h-[80px] resize-y text-sm bg-transparent border-0 focus-visible:ring-1 print:hidden"
                  />
                  {aiComments.overall_comment && (
                    <p className="hidden print:block text-xs leading-relaxed whitespace-pre-wrap m-0">
                      {aiComments.overall_comment}
                    </p>
                  )}
                </>
              )}
            </div>
            <div className="report-section space-y-2 print:space-y-1">
              <ReportDashboard data={analysisData} />
              <ReportAIComment comment={aiComments.dashboard_comment} loading={aiCommentsLoading} />
            </div>
            <div className="report-section space-y-2 print:space-y-1">
              <ReportComposition data={analysisData} />
              <ReportAIComment comment={aiComments.composition_comment} loading={aiCommentsLoading} />
            </div>
            <div className="report-section space-y-2 print:space-y-1">
              <ReportIncomeMargins data={analysisData} />
              <ReportAIComment comment={aiComments.income_margins_comment} loading={aiCommentsLoading} />
            </div>
            <div className="report-section space-y-2 print:space-y-1">
              <ReportStructural data={analysisData} />
              <ReportAIComment comment={aiComments.structural_comment} loading={aiCommentsLoading} />
            </div>
            <ReportRatios data={analysisData} aiComments={aiComments} aiCommentsLoading={aiCommentsLoading} />
            <ReportScoring data={analysisData} />
            <div className="report-section space-y-2 print:space-y-1">
              <ReportBreakEven data={analysisData} />
              <ReportAIComment comment={aiComments.break_even_comment} loading={aiCommentsLoading} />
            </div>
            <div className="report-section space-y-2 print:space-y-1">
              <ReportCashflow data={analysisData} />
              <ReportAIComment comment={aiComments.cashflow_comment} loading={aiCommentsLoading} />
            </div>
            <div className="report-section print:break-before-page">
              <ReportAppendices data={analysisData} section="bs" />
            </div>
            <div className="report-section">
              <ReportAppendices data={analysisData} section="is" />
            </div>
            <div className="report-section print:break-before-page">
              <ReportNotes />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
