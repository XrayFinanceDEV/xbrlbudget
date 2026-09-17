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
import { ReportTOC } from "@/components/report/report-toc";
import { ReportScope } from "@/components/final-report/Scope";
import { ReportSources } from "@/components/final-report/Sources";
import { ReportAdjustments } from "@/components/final-report/Adjustments";
import { ReportClosing } from "@/components/final-report/Closing";
import { ReadinessBanner } from "@/components/final-report/ReadinessBanner";
import { DiagnosticsPanel } from "@/components/final-report/DiagnosticsPanel";
import { AssumptionsSections } from "@/components/final-report/AssumptionsSections";
import { FinalReportChart } from "@/components/final-report/ChartSeries";
import { ForecastValueTable } from "@/components/final-report/ForecastValueTable";
import { DossierContent } from "@/components/final-report/Dossier";
import { EditorialNotes } from "@/components/final-report/EditorialNotes";
import { generateEditorialNotes, generateFinalReportNarrative, generateForecast, getEditorialSession, prepareEditorialSession, saveEditorialNotes, saveFinalReportNarrative } from "@/lib/api";
import { getErrorMessage } from "@/lib/utils";
import type { EditorialNote } from "@/types/final-report-v2";
import type { EditorialNoteReference } from "@/types/editorial-session";
import type { FinalReportModel, NarrativeBlock } from "@/types/final-report";
import { Textarea } from "@/components/ui/textarea";

const narrativeTitles: Record<string, string> = { executive_summary: "Sintesi esecutiva", adjustments_and_closing: "Commento su rettifiche e chiusura", budget_assumptions: "Commento sulle ipotesi", economic_outlook: "Prospettiva economica", financial_outlook: "Prospettiva finanziaria", risks_and_actions: "Rischi e azioni suggerite" };
import { acknowledgeReportDraft, editReportDraft, syncReportDrafts, type ReportDraftBuckets as StoredDrafts } from "@/lib/report-drafts";
import { useFinalReportDownload } from "@/hooks/use-final-report-download";

type DraftBucket = StoredDrafts[string];
function NarrativeBlocks({ notes, onSave, drafts, onDraft }: { notes: Array<{ id: string; text: string; provenance: string; freshness: string }>; onSave: (id: string, text: string) => Promise<boolean>; drafts: DraftBucket; onDraft: (id: string, text: string) => void }) {
  return <section className="grid gap-4 md:grid-cols-2">{notes.map((note) => <NarrativeCard key={note.id} note={note} onSave={onSave} drafts={drafts} onDraft={onDraft} />)}</section>;
}
function NarrativeCard({ note, onSave, drafts, onDraft }: { note: { id: string; text: string; provenance: string; freshness: string }; onSave: (id: string, text: string) => Promise<boolean>; drafts: DraftBucket; onDraft: (id: string, text: string) => void }) {
  const text = drafts.values[note.id] ?? note.text;
  const dirty = Boolean(drafts.dirty[note.id]);
  const [saving, setSaving] = useState(false);
  return <Card><CardHeader className="pb-2"><CardTitle className="text-base">{narrativeTitles[note.id] ?? note.id}</CardTitle></CardHeader><CardContent><p className="mb-2 text-xs text-muted-foreground">Origine: {note.provenance} · stato: {note.freshness}</p><Textarea value={text} aria-label={narrativeTitles[note.id] ?? note.id} onChange={(event) => onDraft(note.id, event.target.value)} className="min-h-24 print:hidden" /><p className="hidden whitespace-pre-wrap text-sm print:block">{text}</p><Button type="button" variant="outline" size="sm" className="mt-2 print:hidden" disabled={saving || !text.trim() || !dirty} onClick={async () => { setSaving(true); try { await onSave(note.id, text.trim()); } finally { setSaving(false); } }}>{saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}Salva commento</Button></CardContent></Card>;
}

export default function ReportPage() {
  const { selectedCompanyId, selectedCompany, companies } = useApp();
  const queryClient = useQueryClient();
  const scenarios = useMemo(() => companies.find((company) => company.id === selectedCompanyId)?.scenarios.filter((scenario) => scenario.scenario_type === "budget") ?? [], [companies, selectedCompanyId]);
  const [scenarioId, setScenarioId] = useState<number | null>(null);
  const [savingId, setSavingId] = useState<string>();
  const [preparing, setPreparing] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [generatingNarrative, setGeneratingNarrative] = useState(false);
  const [regeneratingForecast, setRegeneratingForecast] = useState(false);
  const finalReportDownload = useFinalReportDownload();
  const draftsByScope = useRef<StoredDrafts>({});
  const [, setDraftVersion] = useState(0);
  useEffect(() => setScenarioId((current) => scenarios.some((scenario) => scenario.id === current) ? current : (scenarios.find((scenario) => scenario.is_active === 1)?.id ?? scenarios[0]?.id ?? null)), [scenarios]);
  const queryKey = ["companies", selectedCompanyId, "scenarios", scenarioId, "final-report", "editorial"] as const;
  const scope = `${selectedCompanyId ?? "none"}:${scenarioId ?? "none"}`;
  const scopeRef = useRef(scope); scopeRef.current = scope;
  const session = useQuery({ queryKey, queryFn: () => getEditorialSession(selectedCompanyId!, scenarioId!), enabled: selectedCompanyId !== null && scenarioId !== null });
  const model = session.data?.report;
  const plan = model?.editorial_plan;
  const draftScope = `${scope}:${plan?.plan_hash ?? "unprepared"}`;
  const legacyScope = `${scope}:narrative`;
  const legacyDraftBucket = draftsByScope.current[legacyScope] ?? { values: {}, dirty: {} };
  const requestScope = `${draftScope}:${model?.source_hash ?? "unknown"}`;
  scopeRef.current = requestScope;
  const draftBucket = draftsByScope.current[draftScope] ?? { values: {}, dirty: {} };
  const previousDrafts = Object.entries(draftsByScope.current).filter(([key, bucket]) => key.startsWith(`${scope}:`) && key !== draftScope && key !== legacyScope && Object.values(bucket.dirty).some(Boolean));
  useEffect(() => {
    if (!session.data) return;
    syncReportDrafts(draftsByScope.current, draftScope, session.data.report.editorial_notes ?? []);
    syncReportDrafts(draftsByScope.current, legacyScope, session.data.report.narrative);
    setDraftVersion((version) => version + 1);
  }, [draftScope, legacyScope, session.data]);
  const updateDraft = (id: string, text: string) => { editReportDraft(draftsByScope.current, draftScope, id, text); setDraftVersion((version) => version + 1); };
  const updateNarrativeDraft = (id: string, text: string) => { editReportDraft(draftsByScope.current, legacyScope, id, text); setDraftVersion((version) => version + 1); };
  const completeAction = async (actionScope: string) => { if (scopeRef.current !== actionScope) return; await queryClient.invalidateQueries({ queryKey }); };
  const prepare = async () => { if (!selectedCompanyId || !scenarioId || !session.data) return; const actionScope = requestScope; setPreparing(true); try { await prepareEditorialSession(selectedCompanyId, scenarioId, { source_hash: session.data.report.source_hash, expected_revision: session.data.revision }); await completeAction(actionScope); toast.success("Piano editoriale preparato"); } catch (error) { toast.error(getErrorMessage(error, "Impossibile preparare il piano editoriale")); } finally { setPreparing(false); } };
  const saveNarrative = async (id: string, text: string): Promise<boolean> => { if (!selectedCompanyId || !scenarioId) return false; const actionScope = requestScope; try { await saveFinalReportNarrative(selectedCompanyId, scenarioId, [{ id: id as NarrativeBlock["id"], text }]); acknowledgeReportDraft(draftsByScope.current, legacyScope, id, text); await completeAction(actionScope); toast.success("Commento salvato"); return true; } catch (error) { toast.error(getErrorMessage(error, "Impossibile salvare il commento")); return false; } };
  const regenerateNarrative = async () => { if (!selectedCompanyId || !scenarioId) return; const actionScope = requestScope; setGeneratingNarrative(true); try { await generateFinalReportNarrative(selectedCompanyId, scenarioId); await completeAction(actionScope); toast.success("Commenti rigenerati"); } catch (error) { toast.error(getErrorMessage(error, "Impossibile rigenerare i commenti")); } finally { setGeneratingNarrative(false); } };
  const regenerateForecast = async () => { if (!selectedCompanyId || !scenarioId) return; const actionScope = requestScope; setRegeneratingForecast(true); try { await generateForecast(selectedCompanyId, scenarioId); await completeAction(actionScope); toast.success("Previsionale rigenerato; dossier aggiornato"); } catch (error) { toast.error(getErrorMessage(error, "Impossibile rigenerare il previsionale")); } finally { setRegeneratingForecast(false); } };
  const save = async (note: EditorialNote, text: string, fromNote?: EditorialNoteReference) => { if (!selectedCompanyId || !scenarioId || !session.data || !plan || !text.trim()) return; const actionScope = requestScope; const submitted = text.trim(); setSavingId(note.id); try { await saveEditorialNotes(selectedCompanyId, scenarioId, { source_hash: model!.source_hash, plan_hash: plan.plan_hash, expected_revision: session.data.revision, notes: [{ id: note.id, text: submitted, revision: note.revision, ...(fromNote ? { from_note: fromNote } : {}) }] }); acknowledgeReportDraft(draftsByScope.current, draftScope, note.id, submitted); await completeAction(actionScope); toast.success("Commento salvato"); } catch (error) { toast.error(getErrorMessage(error, "Impossibile salvare il commento; la bozza è stata mantenuta")); } finally { setSavingId(undefined); } };
  const generate = async (notes: EditorialNote[]) => { if (!selectedCompanyId || !scenarioId || !session.data || !plan || notes.length === 0) return; const safeNotes = notes.filter((note) => !draftsByScope.current[draftScope]?.dirty[note.id] && note.provenance !== "user"); if (!safeNotes.length) return; const actionScope = requestScope; setGenerating(true); try { const next = await generateEditorialNotes(selectedCompanyId, scenarioId, { source_hash: model!.source_hash, plan_hash: plan.plan_hash, expected_revision: session.data.revision, notes: safeNotes.map((note) => ({ id: note.id, revision: note.revision })) }); if (next.generation_warnings.length) next.generation_warnings.forEach((warning) => toast.warning(`${warning.note_id}: ${warning.message}`)); else toast.success("Commenti generati"); await completeAction(actionScope); } catch (error) { toast.error(getErrorMessage(error, "Generazione parziale o non riuscita")); } finally { setGenerating(false); } };
  if (!selectedCompanyId) return <div className="mx-auto max-w-7xl px-4 py-6"><PageHeader title="Dossier finale" description="Seleziona un'azienda dalla home page per visualizzare il dossier" icon={<FileText className="h-6 w-6" />} /></div>;
  const pending = !plan || model?.editorial_readiness.status === "pending" || model?.editorial_readiness.status === "blocked" || plan?.source_hash !== model?.source_hash;
  const finalReportReady = model?.readiness.status === "ready";
  const downloadPdf = () => { if (!selectedCompanyId || !scenarioId) return; finalReportDownload.download(selectedCompanyId, scenarioId, finalReportReady ? "final" : "draft"); };
  const previewPdf = () => { if (!selectedCompanyId || !scenarioId) return; finalReportDownload.preview(selectedCompanyId, scenarioId, finalReportReady ? "final" : "draft"); };
  const pdfRequestBusy = finalReportDownload.downloading || finalReportDownload.previewing;
  return <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8 print:max-w-none print:px-0 print:py-0">
    <div className="print:hidden"><PageHeader title="Dossier finale" description={selectedCompany?.name} icon={<FileText className="h-6 w-6" />}><div className="flex flex-wrap items-center gap-2"><label className="text-sm" htmlFor="report-scenario">Scenario budget</label><select id="report-scenario" value={scenarioId ?? ""} onChange={(event) => setScenarioId(Number(event.target.value) || null)} className="h-9 rounded-md border bg-background px-2 text-sm">{scenarios.map((scenario) => <option key={scenario.id} value={scenario.id}>{scenario.name} — anno base {scenario.base_year}</option>)}</select><Button type="button" variant="outline" onClick={regenerateNarrative} disabled={!model || generatingNarrative}>{generatingNarrative ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Sparkles className="mr-2 h-4 w-4" />}Rigenera commenti</Button><Button type="button" variant="outline" onClick={prepare} disabled={!session.data || preparing}>{preparing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Sparkles className="mr-2 h-4 w-4" />}Prepara piano editoriale</Button><Button type="button" variant="outline" onClick={previewPdf} disabled={!model || !selectedCompanyId || !scenarioId || pdfRequestBusy}>{finalReportDownload.previewing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Eye className="mr-2 h-4 w-4" />}{finalReportDownload.previewing ? "Preparazione anteprima…" : "Anteprima PDF"}</Button><Button type="button" variant="outline" onClick={downloadPdf} disabled={!model || !selectedCompanyId || !scenarioId || pdfRequestBusy}>{finalReportDownload.downloading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Download className="mr-2 h-4 w-4" />}{finalReportDownload.downloading ? "Preparazione PDF…" : finalReportReady ? "Scarica PDF finale" : "Scarica bozza"}</Button></div></PageHeader></div>
    {scenarios.length === 0 && !session.isLoading ? <Alert><AlertTitle>Nessuno scenario budget</AlertTitle><AlertDescription>Crea e genera uno scenario budget prima di aprire il dossier.</AlertDescription></Alert> : null}
    {session.isLoading ? <Card><CardContent className="flex items-center justify-center py-12"><Loader2 className="mr-3 h-8 w-8 animate-spin" />Caricamento del dossier…</CardContent></Card> : null}
    {session.error ? <Alert variant="destructive"><AlertTitle>Impossibile caricare il dossier</AlertTitle><AlertDescription className="space-y-3"><p>{getErrorMessage(session.error, "Il dossier non è disponibile.")}</p><Button type="button" variant="outline" onClick={() => session.refetch()}><RefreshCw className="mr-2 h-4 w-4" />Riprova</Button></AlertDescription></Alert> : null}
    {model ? <main className="space-y-6"><h1 className="text-3xl font-bold print:block">{model.document.title}</h1><ReadinessBanner readiness={model.readiness} className="print:hidden" />{model.readiness.reasons?.some((reason) => reason.code === "forecast_stale") ? <Alert className="border-amber-400 print:hidden"><AlertTitle>Previsionale da rigenerare</AlertTitle><AlertDescription className="flex flex-wrap items-center gap-3"><span>Le ipotesi sono cambiate dopo l&apos;ultima generazione.</span><Button type="button" variant="outline" onClick={regenerateForecast} disabled={regeneratingForecast}>{regeneratingForecast ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}Rigenera previsionale</Button></AlertDescription></Alert> : null}{pending ? <Alert className="print:hidden"><AlertTitle>Piano editoriale da preparare</AlertTitle><AlertDescription>{model.editorial_readiness.reasons.join(" ")} Usa “Prepara piano editoriale” prima di modificare o generare commenti.</AlertDescription></Alert> : null}
      <div className="flex gap-6 print:block"><div className="print:hidden"><ReportTOC /></div><div className="min-w-0 flex-1 space-y-6">
      <section id="scope"><ReportScope company={model.company} practice={model.practice} generated_at={model.generated_at} readiness={model.readiness} /></section>
      <section id="executive-summary"><NarrativeBlocks notes={model.narrative.filter((note) => note.id === "executive_summary")} onSave={saveNarrative} drafts={legacyDraftBucket} onDraft={updateNarrativeDraft} /></section><section id="sources"><ReportSources workflow={model.practice.workflow_type} budgetScenarioName={model.practice.budget_scenario.name} sourceRevisions={model.source_revisions} sourceDataQuality={model.source_data_quality} /></section>
      <section id="adjustments" className="space-y-3"><ReportAdjustments adjustments={model.adjustments} /><NarrativeBlocks notes={model.narrative.filter((note) => note.id === "adjustments_and_closing")} onSave={saveNarrative} drafts={legacyDraftBucket} onDraft={updateNarrativeDraft} /></section>
      <section id="closing"><ReportClosing workflow={model.practice.workflow_type} closing={model.practice.workflow_type === "infrannuale" ? model.infrannual_closing : undefined} /></section><section id="assumptions" className="space-y-3"><AssumptionsSections model={model} /><NarrativeBlocks notes={model.narrative.filter((note) => note.id === "budget_assumptions")} onSave={saveNarrative} drafts={legacyDraftBucket} onDraft={updateNarrativeDraft} /></section>
      <section id="income-forecast"><Card><CardHeader><CardTitle>Conto economico previsionale</CardTitle></CardHeader><CardContent className="space-y-5"><ForecastValueTable report={model as unknown as FinalReportModel} statement="income_statement" />{model.chart_series.filter((chart) => ["income_results", "margins"].includes(chart.id)).map((chart) => <FinalReportChart key={chart.id} series={chart} />)}<NarrativeBlocks notes={model.narrative.filter((note) => note.id === "economic_outlook")} onSave={saveNarrative} drafts={legacyDraftBucket} onDraft={updateNarrativeDraft} /></CardContent></Card></section>
      <section id="balance-forecast"><Card><CardHeader><CardTitle>Stato patrimoniale previsionale</CardTitle></CardHeader><CardContent><ForecastValueTable report={model as unknown as FinalReportModel} statement="balance_sheet" /></CardContent></Card></section>
      <section id="cashflow-sustainability"><Card><CardHeader><CardTitle>Flussi di cassa e sostenibilità finanziaria</CardTitle></CardHeader><CardContent className="space-y-5"><ForecastValueTable report={model as unknown as FinalReportModel} statement="cashflow" />{model.chart_series.filter((chart) => ["cashflows", "liquidity_debt"].includes(chart.id)).map((chart) => <FinalReportChart key={chart.id} series={chart} />)}<NarrativeBlocks notes={model.narrative.filter((note) => note.id === "financial_outlook")} onSave={saveNarrative} drafts={legacyDraftBucket} onDraft={updateNarrativeDraft} /></CardContent></Card></section>
      <section id="indicators-risks"><Card><CardHeader><CardTitle>Indicatori e rischi</CardTitle></CardHeader><CardContent className="space-y-5">{model.chart_series.filter((chart) => ["working_capital_days", "coverage"].includes(chart.id)).map((chart) => <FinalReportChart key={chart.id} series={chart} />)}<NarrativeBlocks notes={model.narrative.filter((note) => note.id === "risks_and_actions")} onSave={saveNarrative} drafts={legacyDraftBucket} onDraft={updateNarrativeDraft} /></CardContent></Card></section>
      {plan ? <EditorialNotes key={draftScope} plan={plan} notes={model.editorial_notes ?? []} archivedNotes={session.data!.archived_notes} drafts={draftBucket.values} dirty={draftBucket.dirty} savingId={savingId} generating={generating} onDraft={updateDraft} onSave={save} onGenerate={generate} onReassociate={() => toast.info("Testo archiviato copiato nella bozza della nota selezionata")} /> : null}
      {!plan && session.data!.archived_notes.length ? <Card className="print:hidden"><CardHeader><CardTitle>Commenti archiviati</CardTitle></CardHeader><CardContent className="space-y-3"><p className="text-sm text-muted-foreground">I testi precedenti restano recuperabili. Prepara un nuovo piano per associarli alle pagine correnti.</p>{session.data!.archived_notes.map((note) => <div key={`${note.plan_hash}:${note.id}`}><p className="text-xs text-muted-foreground">{note.provenance} · revisione {note.revision}</p><Textarea readOnly value={note.text} className="min-h-20" /></div>)}</CardContent></Card> : null}
      {previousDrafts.length ? <Card className="print:hidden"><CardHeader><CardTitle>Bozze di un piano precedente</CardTitle></CardHeader><CardContent className="space-y-3"><p className="text-sm text-muted-foreground">Il piano è cambiato. Queste bozze non sono state associate automaticamente alle nuove pagine; puoi copiarne il testo nella nota corrente.</p>{previousDrafts.flatMap(([, bucket]) => Object.entries(bucket.values).filter(([id]) => bucket.dirty[id]).map(([id, text]) => <div key={id}><p className="text-xs text-muted-foreground">{id}</p><Textarea readOnly value={text} className="min-h-20" /></div>))}</CardContent></Card> : null}
      {session.data!.generation_warnings.map((warning) => <Alert key={`${warning.note_id}-${warning.message}`} className="border-amber-400"><AlertTitle>Generazione parziale: {warning.note_id}</AlertTitle><AlertDescription>{warning.message}</AlertDescription></Alert>)}
      <section id="diagnostics"><DiagnosticsPanel diagnostics={model.diagnostics} /></section><DossierContent report={model} includeCanonicalCharts={false} />
      </div></div>
    </main> : null}
  </div>;
}
