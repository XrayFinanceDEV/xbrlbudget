"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Eye, FileText, Loader2, RefreshCw, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { useApp } from "@/contexts/AppContext";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PageHeader } from "@/components/page-header";
import { ReadinessBanner } from "@/components/final-report/ReadinessBanner";
import { generateEditorialNotes, generateFinalReportNarrative, generateForecast, getEditorialSession, prepareEditorialSession } from "@/lib/api";
import { getErrorMessage } from "@/lib/utils";
import type { EditorialSession } from "@/types/editorial-session";
import { decidePrepareReportAI, runPrepareReportAI, type PrepareReportAIStep } from "@/lib/prepare-report-ai";
import { buildPdfOutline, pdfPageUrl } from "@/lib/report-pdf-outline";
import { REPORT_MODELS, wordAvailable, type ReportModel } from "@/lib/final-report-download";

const narrativeTitles: Record<string, string> = { executive_summary: "Sintesi esecutiva", adjustments_and_closing: "Commento su rettifiche e chiusura", budget_assumptions: "Commento sulle ipotesi", economic_outlook: "Prospettiva economica", financial_outlook: "Prospettiva finanziaria", risks_and_actions: "Rischi e azioni suggerite" };
const NARRATIVE_IDS = Object.keys(narrativeTitles);
const AI_STEP_LABELS: Record<PrepareReportAIStep, string> = { plan: "Preparazione piano…", narrative: "Generazione commenti…", notes: "Generazione note…" };
import { syncReportDrafts, type ReportDraftBuckets as StoredDrafts } from "@/lib/report-drafts";
import { useFinalReportDownload } from "@/hooks/use-final-report-download";
import { useFileDownload } from "@/hooks/use-file-download";
import { downloadReportDocx } from "@/lib/api";


export default function ReportPage() {
  const { selectedCompanyId, selectedCompany, companies } = useApp();
  const queryClient = useQueryClient();
  const scenarios = useMemo(() => companies.find((company) => company.id === selectedCompanyId)?.scenarios.filter((scenario) => scenario.scenario_type === "budget") ?? [], [companies, selectedCompanyId]);
  const [scenarioId, setScenarioId] = useState<number | null>(null);
  const [reportModel, setReportModel] = useState<ReportModel>("business_plan");
  const [dismissedReadyReport, setDismissedReadyReport] = useState<string>();
  const [regeneratingForecast, setRegeneratingForecast] = useState(false);
  const [aiPrepMode, setAiPrepMode] = useState<"prepare" | "regenerate_all" | null>(null);
  const [aiPrepStepLabel, setAiPrepStepLabel] = useState<string>("");
  const finalReportDownload = useFinalReportDownload();
  // Il Business plan anche in Word, per correggere i testi prima di consegnarlo. Sta qui, prima di ogni return:
  // un hook dopo il return anticipato del componente rompe la build di produzione (react-hooks/rules-of-hooks).
  const wordDownload = useFileDownload();
  const draftsByScope = useRef<StoredDrafts>({});
  const [, setDraftVersion] = useState(0);
  useEffect(() => setScenarioId((current) => scenarios.some((scenario) => scenario.id === current) ? current : (scenarios.find((scenario) => scenario.is_active === 1)?.id ?? scenarios[0]?.id ?? null)), [scenarios]);
  const queryKey = ["companies", selectedCompanyId, "scenarios", scenarioId, "final-report", "editorial"] as const;
  const scope = `${selectedCompanyId ?? "none"}:${scenarioId ?? "none"}`;
  const scopeRef = useRef(scope); scopeRef.current = scope;
  const session = useQuery({ queryKey, queryFn: () => getEditorialSession(selectedCompanyId!, scenarioId!), enabled: selectedCompanyId !== null && scenarioId !== null });
  const model = session.data?.report;
  const plan = model?.editorial_plan;
  const readyReportKey = `${scope}:${model?.model_hash ?? "unknown"}`;
  const draftScope = `${scope}:${plan?.plan_hash ?? "unprepared"}`;
  const legacyScope = `${scope}:narrative`;
  const requestScope = `${draftScope}:${model?.source_hash ?? "unknown"}`;
  scopeRef.current = requestScope;
  useEffect(() => {
    if (!session.data) return;
    syncReportDrafts(draftsByScope.current, legacyScope, session.data.report.narrative);
    setDraftVersion((version) => version + 1);
  }, [draftScope, legacyScope, session.data]);
  const completeAction = async (actionScope: string) => { if (scopeRef.current !== actionScope) return; await queryClient.invalidateQueries({ queryKey }); };
  // «Prepara Report AI» / «Rigenera tutto»: un solo pulsante al posto di tre azioni (prepare, regenerateNarrative,
  // generate). La sequenza e la scelta di che cosa rigenerare vivono in lib/prepare-report-ai.ts (modulo puro);
  // qui c'è solo l'innesto verso le chiamate API vere e lo stato di avanzamento a schermo. La decisione sulle
  // note si prende DOPO che `preparePlan` è tornato: solo allora si conoscono la `revision`, il `plan_hash` e le
  // note davvero candidate — deciderlo prima userebbe dati potenzialmente già superati dal prepare stesso.
  const runPrepareAI = async (forceAll: boolean) => {
    if (!selectedCompanyId || !scenarioId || !session.data) return;
    const companyId = selectedCompanyId;
    const scId = scenarioId;
    const actionScope = requestScope;
    setAiPrepMode(forceAll ? "regenerate_all" : "prepare");
    setAiPrepStepLabel(AI_STEP_LABELS.plan);
    try {
      const result = await runPrepareReportAI<EditorialSession>(
        {
          // I commenti generali si decidono sul modello già a schermo, perché
          // vanno rigenerati PRIMA del piano (vedi lib/prepare-report-ai.ts).
          narrative: () => decidePrepareReportAI({ narrativeIds: NARRATIVE_IDS, narrativeBlocks: session.data!.report.narrative, notes: [], dirtyNoteIds: new Set<string>(), forceAll }),
          notes: (freshSession) => decidePrepareReportAI({ narrativeIds: NARRATIVE_IDS, narrativeBlocks: freshSession.report.narrative, notes: freshSession.report.editorial_notes ?? [], dirtyNoteIds: new Set<string>(), forceAll }),
        },
        {
          preparePlan: () => prepareEditorialSession(companyId, scId),
          regenerateNarrative: () => generateFinalReportNarrative(companyId, scId).then(() => undefined),
          regenerateNotes: (freshSession, targets) => {
            const notePlan = freshSession.report.editorial_plan;
            if (!notePlan) return Promise.resolve();
            return generateEditorialNotes(companyId, scId, { source_hash: freshSession.report.source_hash, plan_hash: notePlan.plan_hash, expected_revision: freshSession.revision, notes: [...targets] }).then(() => undefined);
          },
        },
        { describeError: (error) => getErrorMessage(error, "Operazione non riuscita"), notify: (step) => setAiPrepStepLabel(AI_STEP_LABELS[step]) }
      );
      await completeAction(actionScope);
      if (result.plan.outcome === "failed") toast.error(result.summary);
      else if (result.narrative.outcome === "failed" || result.notes.outcome === "failed") toast.warning(result.summary);
      else toast.success(result.summary);
    } finally {
      setAiPrepMode(null);
      setAiPrepStepLabel("");
    }
  };
  const regenerateForecast = async () => { if (!selectedCompanyId || !scenarioId) return; const actionScope = requestScope; setRegeneratingForecast(true); try { await generateForecast(selectedCompanyId, scenarioId); await completeAction(actionScope); toast.success("Previsionale rigenerato; dossier aggiornato"); } catch (error) { toast.error(getErrorMessage(error, "Impossibile rigenerare il previsionale")); } finally { setRegeneratingForecast(false); } };
  // L'anteprima del PDF è la vista principale della pagina: la resa web del
  // dossier è una seconda lettura, e si apre solo a richiesta. Si ricarica
  // quando cambia il piano editoriale (`draftScope` porta il `plan_hash`) o
  // il modello, mai a ogni render.
  const pdfState: "draft" | "final" = model?.readiness.status === "ready" ? "final" : "draft";
  const previewKey = selectedCompanyId && scenarioId && (reportModel === "business_plan" ? model : plan)
    ? `${reportModel}:${selectedCompanyId}:${scenarioId}:${reportModel === "business_plan" ? model?.model_hash : plan?.plan_hash}:${pdfState}`
    : null;
  // L'indice a sinistra dell'anteprima: la posizione nel piano È il numero di
  // pagina fisica, perché il catalogo garantisce una pagina per voce.
  const pdfOutline = useMemo(() => reportModel === "dossier" ? buildPdfOutline(plan?.pages ?? []) : [], [plan, reportModel]);
  const [previewPage, setPreviewPage] = useState(1);
  const loadedPreviewKey = useRef<string | null>(null);
  // Dipendere da `loadInline`, non dall'oggetto `finalReportDownload`: quello
  // cambia identità a ogni render e l'effetto ripartirebbe da solo ogni volta
  // (regola CLAUDE.md «Frontend»). `loadInline` è stabile: `useCallback([])`.
  const loadInlinePreview = finalReportDownload.loadInline;
  useEffect(() => {
    if (!previewKey || !selectedCompanyId || !scenarioId) return;
    if (loadedPreviewKey.current === previewKey) return;
    loadedPreviewKey.current = previewKey;
    setPreviewPage(1);
    void loadInlinePreview(selectedCompanyId, scenarioId, pdfState, reportModel);
  }, [previewKey, selectedCompanyId, scenarioId, pdfState, reportModel, loadInlinePreview]);

  if (!selectedCompanyId) return <div className="mx-auto max-w-7xl px-4 py-6"><PageHeader title="Dossier finale" description="Seleziona un'azienda dalla home page per visualizzare il dossier" icon={<FileText className="h-6 w-6" />} /></div>;
  const pending = !plan || model?.editorial_readiness.status === "pending" || model?.editorial_readiness.status === "blocked" || plan?.source_hash !== model?.source_hash;
  const finalReportReady = model?.readiness.status === "ready";
  const downloadPdf = () => { if (!selectedCompanyId || !scenarioId) return; finalReportDownload.download(selectedCompanyId, scenarioId, finalReportReady ? "final" : "draft", reportModel); };
  const previewPdf = () => { if (!selectedCompanyId || !scenarioId) return; finalReportDownload.preview(selectedCompanyId, scenarioId, finalReportReady ? "final" : "draft", reportModel); };
  const downloadWord = () => { if (!selectedCompanyId || !scenarioId) return; void wordDownload.download(() => downloadReportDocx(selectedCompanyId, scenarioId, "business-plan", finalReportReady ? "final" : "draft"), "Impossibile scaricare il Word del report"); };
  const pdfRequestBusy = finalReportDownload.downloading || finalReportDownload.previewing || wordDownload.downloading;
  // A01-bis: due diagnostiche di previsionale vecchio, ciascuna con la propria frase; entrambe
  // condividono l'Alert e il pulsante "Rigenera previsionale".
  const staleMessages = [
    model?.readiness.reasons?.some((reason) => reason.code === "forecast_stale") ? "Le ipotesi sono cambiate dopo l'ultima generazione." : null,
    model?.readiness.reasons?.some((reason) => reason.code === "engine_version_stale") ? "Previsionale generato da una versione precedente del motore: da rigenerare." : null,
  ].filter((message): message is string => Boolean(message));
  return <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8 print:max-w-none print:px-0 print:py-0">
    <div className="print:hidden"><PageHeader title={reportModel === "business_plan" ? "Business plan" : "Dossier finale"} description={selectedCompany?.name} icon={<FileText className="h-6 w-6" />}><div className="flex flex-wrap items-center gap-2"><label className="text-sm" htmlFor="report-scenario">Scenario budget</label><select id="report-scenario" value={scenarioId ?? ""} onChange={(event) => setScenarioId(Number(event.target.value) || null)} className="h-9 rounded-md border bg-background px-2 text-sm">{scenarios.map((scenario) => <option key={scenario.id} value={scenario.id}>{scenario.name} — anno base {scenario.base_year}</option>)}</select>{REPORT_MODELS.length > 1 ? <><label className="text-sm" htmlFor="report-model">Modello</label><select id="report-model" value={reportModel} onChange={(event) => setReportModel(event.target.value as ReportModel)} className="h-9 rounded-md border bg-background px-2 text-sm">{REPORT_MODELS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></> : null}{reportModel === "dossier" ? <><Button type="button" variant="outline" onClick={() => runPrepareAI(false)} disabled={!session.data || aiPrepMode !== null || pdfRequestBusy}>{aiPrepMode === "prepare" ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Sparkles className="mr-2 h-4 w-4" />}{aiPrepMode === "prepare" ? aiPrepStepLabel : "Prepara Report AI"}</Button><Button type="button" variant="secondary" onClick={() => runPrepareAI(true)} disabled={!session.data || aiPrepMode !== null || pdfRequestBusy}>{aiPrepMode === "regenerate_all" ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}{aiPrepMode === "regenerate_all" ? aiPrepStepLabel : "Rigenera tutto"}</Button></> : null}<Button type="button" variant="outline" onClick={previewPdf} disabled={!model || !selectedCompanyId || !scenarioId || pdfRequestBusy || aiPrepMode !== null}>{finalReportDownload.previewing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Eye className="mr-2 h-4 w-4" />}{finalReportDownload.previewing ? "Preparazione anteprima…" : "Anteprima PDF"}</Button><Button type="button" variant="outline" onClick={downloadPdf} disabled={!model || !selectedCompanyId || !scenarioId || pdfRequestBusy || aiPrepMode !== null}>{finalReportDownload.downloading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Download className="mr-2 h-4 w-4" />}{finalReportDownload.downloading ? "Preparazione PDF…" : finalReportReady ? "Scarica PDF finale" : "Scarica bozza"}</Button>{wordAvailable(reportModel) ? <Button type="button" variant="outline" onClick={downloadWord} disabled={!model || !selectedCompanyId || !scenarioId || pdfRequestBusy || aiPrepMode !== null}>{wordDownload.downloading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <FileText className="mr-2 h-4 w-4" />}{wordDownload.downloading ? "Preparazione Word…" : "Scarica Word"}</Button> : null}</div></PageHeader></div>
    {scenarios.length === 0 && !session.isLoading ? <Alert><AlertTitle>Nessuno scenario budget</AlertTitle><AlertDescription>Crea e genera uno scenario budget prima di aprire il dossier.</AlertDescription></Alert> : null}
    {session.isLoading ? <Card><CardContent className="flex items-center justify-center py-12"><Loader2 className="mr-3 h-8 w-8 animate-spin" />Caricamento del dossier…</CardContent></Card> : null}
    {session.error ? <Alert variant="destructive"><AlertTitle>Impossibile caricare il dossier</AlertTitle><AlertDescription className="space-y-3"><p>{getErrorMessage(session.error, "Il dossier non è disponibile.")}</p><Button type="button" variant="outline" onClick={() => session.refetch()}><RefreshCw className="mr-2 h-4 w-4" />Riprova</Button></AlertDescription></Alert> : null}
    {model ? <main className="space-y-6"><h1 className="text-3xl font-bold print:block">{model.document.title}</h1>{model.readiness.status !== "ready" || dismissedReadyReport !== readyReportKey ? <ReadinessBanner readiness={model.readiness} className="print:hidden" onDismiss={() => setDismissedReadyReport(readyReportKey)} /> : null}{staleMessages.length ? <Alert className="border-amber-400 print:hidden"><AlertTitle>Previsionale da rigenerare</AlertTitle><AlertDescription className="flex flex-wrap items-center gap-3"><span>{staleMessages.join(" ")}</span><Button type="button" variant="outline" onClick={regenerateForecast} disabled={regeneratingForecast}>{regeneratingForecast ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}Rigenera previsionale</Button></AlertDescription></Alert> : null}{pending && reportModel === "dossier" ? <Alert className="print:hidden"><AlertTitle>Piano editoriale da preparare</AlertTitle><AlertDescription>{model.editorial_readiness.reasons.join(" ")} Usa “Prepara Report AI” per preparare l’anteprima.</AlertDescription></Alert> : null}
      <section id="pdf-preview" className="print:hidden"><Card><CardHeader className="flex flex-row items-center justify-between gap-3 space-y-0"><CardTitle>Anteprima del PDF</CardTitle><Button type="button" variant="outline" size="sm" onClick={() => { if (selectedCompanyId && scenarioId) { loadedPreviewKey.current = previewKey; void finalReportDownload.loadInline(selectedCompanyId, scenarioId, pdfState, reportModel); } }} disabled={pdfRequestBusy || aiPrepMode !== null}>{finalReportDownload.previewing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}Aggiorna anteprima</Button></CardHeader><CardContent>
        {finalReportDownload.inlineUrl ? <div className="flex gap-4">
          {pdfOutline.length ? <nav aria-label="Pagine del report" className="sticky top-4 hidden max-h-[85vh] w-56 shrink-0 overflow-y-auto pr-1 lg:block">
            <ol className="space-y-0.5">{pdfOutline.map((entry) => <li key={`${entry.page}-${entry.sectionId}`}>
              <button type="button" onClick={() => setPreviewPage(entry.page)} className={`flex w-full items-baseline gap-2 rounded px-2 py-1 text-left text-xs hover:bg-muted ${previewPage === entry.page ? "bg-muted font-medium text-foreground" : "text-muted-foreground"}`}>
                <span className="w-5 shrink-0 tabular-nums text-right">{entry.page}</span><span className="truncate">{entry.label}</span>
              </button></li>)}</ol>
          </nav> : null}
          <iframe title="Anteprima del report PDF" src={pdfPageUrl(finalReportDownload.inlineUrl, previewPage)} className="h-[85vh] min-w-0 flex-1 rounded-md border" />
        </div> : <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">{finalReportDownload.previewing ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Preparazione anteprima…</> : pending ? "Prepara il report con «Prepara Report AI» per vedere l'anteprima." : "Anteprima non disponibile."}</div>}
      </CardContent></Card></section>
    </main> : null}
  </div>;
}
