"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText, Loader2, Printer, RefreshCw, Sparkles } from "lucide-react";
import { toast } from "sonner";

import { useApp } from "@/contexts/AppContext";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Textarea } from "@/components/ui/textarea";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { PageHeader } from "@/components/page-header";
import { ReportTOC } from "@/components/report/report-toc";
import { chartRows, hasStaleForecast, narrativeFor, statementRows, type ForecastStatement } from "@/components/report/final-report-adapters";
import { ReportScope } from "@/components/final-report/Scope";
import { ReportSources } from "@/components/final-report/Sources";
import { ReportAdjustments } from "@/components/final-report/Adjustments";
import { ReportClosing } from "@/components/final-report/Closing";
import { AssumptionsSections } from "@/components/final-report/AssumptionsSections";
import { ReadinessBanner } from "@/components/final-report/ReadinessBanner";
import { DiagnosticsPanel } from "@/components/final-report/DiagnosticsPanel";
import { generateFinalReportNarrative, generateForecast, getFinalReport, saveFinalReportNarrative } from "@/lib/api";
import { getErrorMessage } from "@/lib/utils";
import type { FinalReportModel, NarrativeBlock } from "@/types/final-report";

const NARRATIVE_TITLES: Record<NarrativeBlock["id"], string> = {
  executive_summary: "Sintesi esecutiva", adjustments_and_closing: "Commento su rettifiche e chiusura",
  budget_assumptions: "Commento sulle ipotesi", economic_outlook: "Prospettiva economica",
  financial_outlook: "Prospettiva finanziaria", risks_and_actions: "Rischi e azioni suggerite",
};
const STATEMENT_TITLES: Record<ForecastStatement, string> = {
  income_statement: "Conto economico previsionale", balance_sheet: "Stato patrimoniale previsionale",
  cashflow: "Flussi di cassa", calculations: "Calcoli e indicatori disponibili",
};

function ValueTable({ report, statement }: { report: FinalReportModel; statement: ForecastStatement }) {
  const rows = statementRows(report, statement);
  return <div className="overflow-x-auto"><table className="w-full text-sm print:text-xs">
    <caption className="sr-only">{STATEMENT_TITLES[statement]} per anno di previsione</caption>
    <thead><tr><th scope="col" className="border-b px-3 py-1.5 text-left font-medium print:px-1">Voce</th>{report.forecast.years.map((year) => <th key={year.year} scope="col" className="border-b px-3 py-1.5 text-right font-medium print:px-1">{year.year}</th>)}</tr></thead>
    <tbody>{rows.map((row) => <tr key={row.code}><th scope="row" className="border-b px-3 py-1.5 text-left font-medium print:px-1">{row.label}<span className="ml-1 text-xs font-normal text-muted-foreground">{row.code}</span></th>{row.values.map((value, index) => <td key={index} className="border-b px-3 py-1.5 text-right tabular-nums print:px-1">{value ?? "—"}</td>)}</tr>)}</tbody>
  </table></div>;
}

function ChartSeriesTable({ report, ids }: { report: FinalReportModel; ids: FinalReportModel["chart_series"][number]["id"][] }) {
  return <div className="space-y-5">{report.chart_series.filter((series) => ids.includes(series.id)).map((series) => <div key={series.id} className="overflow-x-auto print:break-inside-avoid">
    <h3 className="mb-1 text-base font-semibold">{series.title}</h3><p className="mb-2 text-xs text-muted-foreground">Unità: {series.unit}</p>
    <table className="w-full text-sm print:text-xs"><caption className="sr-only">Serie {series.title}</caption><thead><tr><th scope="col" className="border-b px-3 py-1.5 text-left font-medium print:px-1">Serie</th>{series.categories.map((year) => <th key={year} scope="col" className="border-b px-3 py-1.5 text-right font-medium print:px-1">{year}</th>)}</tr></thead><tbody>{chartRows(series).map((row) => <tr key={row.key}><th scope="row" className="border-b px-3 py-1.5 text-left font-medium print:px-1">{row.label}</th>{row.values.map((value, index) => <td key={index} className="border-b px-3 py-1.5 text-right tabular-nums print:px-1">{value ?? "—"}</td>)}</tr>)}</tbody></table>
  </div>)}</div>;
}

function NarrativeCard({ block, onSave }: { block: NarrativeBlock; onSave: (id: NarrativeBlock["id"], text: string) => Promise<void> }) {
  const [text, setText] = useState(block.text);
  const [saving, setSaving] = useState(false);
  useEffect(() => setText(block.text), [block.id, block.text]);
  const save = async () => { if (!text.trim()) return; setSaving(true); try { await onSave(block.id, text.trim()); } finally { setSaving(false); } };
  return <Card className="border-dashed"><CardHeader className="pb-2"><CardTitle className="text-base">{NARRATIVE_TITLES[block.id]}</CardTitle></CardHeader><CardContent>
    <p className="mb-2 text-xs text-muted-foreground">Origine: {block.provenance} · stato: {block.freshness}</p>
    <Textarea aria-label={NARRATIVE_TITLES[block.id]} value={text} onChange={(event) => setText(event.target.value)} className="min-h-24 print:hidden" />
    <p className="hidden whitespace-pre-wrap text-sm print:block">{text || "Commento non disponibile."}</p>
    <Button type="button" variant="outline" size="sm" onClick={save} disabled={saving || !text.trim() || text === block.text} className="mt-2 print:hidden">{saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}Salva commento</Button>
  </CardContent></Card>;
}

export default function ReportPage() {
  const { selectedCompanyId, selectedCompany, companies } = useApp();
  const queryClient = useQueryClient();
  const scenarios = useMemo(() => companies.find((company) => company.id === selectedCompanyId)?.scenarios.filter((scenario) => scenario.scenario_type === "budget") ?? [], [companies, selectedCompanyId]);
  const [scenarioId, setScenarioId] = useState<number | null>(null);
  const [regenerating, setRegenerating] = useState(false);
  const [generatingNarrative, setGeneratingNarrative] = useState(false);
  useEffect(() => setScenarioId((current) => scenarios.some((scenario) => scenario.id === current) ? current : (scenarios.find((scenario) => scenario.is_active === 1)?.id ?? scenarios[0]?.id ?? null)), [scenarios]);

  const finalReportQueryKey = ["companies", selectedCompanyId, "scenarios", scenarioId, "final-report"] as const;
  const report = useQuery({ queryKey: finalReportQueryKey, queryFn: () => getFinalReport(selectedCompanyId!, scenarioId!), enabled: selectedCompanyId !== null && scenarioId !== null });
  const model = report.data;
  const saveNarrative = async (id: NarrativeBlock["id"], text: string) => {
    if (!selectedCompanyId || !scenarioId) return;
    try { queryClient.setQueryData(finalReportQueryKey, await saveFinalReportNarrative(selectedCompanyId, scenarioId, [{ id, text }])); toast.success("Commento salvato"); }
    catch (error) { toast.error(getErrorMessage(error, "Impossibile salvare il commento")); }
  };
  const regenerate = async () => {
    if (!selectedCompanyId || !scenarioId) return;
    setRegenerating(true);
    try { await generateForecast(selectedCompanyId, scenarioId); await report.refetch(); toast.success("Previsionale rigenerato; stato del report aggiornato"); }
    catch (error) { toast.error(getErrorMessage(error, "Impossibile rigenerare il previsionale")); }
    finally { setRegenerating(false); }
  };
  const generateNarrative = async () => {
    if (!selectedCompanyId || !scenarioId) return;
    setGeneratingNarrative(true);
    try { queryClient.setQueryData(finalReportQueryKey, await generateFinalReportNarrative(selectedCompanyId, scenarioId)); toast.success("Commenti rigenerati"); }
    catch (error) { toast.error(getErrorMessage(error, "Impossibile rigenerare i commenti")); }
    finally { setGeneratingNarrative(false); }
  };
  if (!selectedCompanyId) return <div className="mx-auto max-w-7xl px-4 py-6"><PageHeader title="Report finale" description="Seleziona un'azienda dalla home page per visualizzare il report" icon={<FileText className="h-6 w-6" />} /></div>;

  const unsupportedSchema = report.error instanceof Error && /Unsupported or invalid FinalReportModel/.test(report.error.message);
  return <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8 print:max-w-none print:px-0 print:py-0">
    <div className="print:hidden"><PageHeader title="Report finale" description={selectedCompany?.name} icon={<FileText className="h-6 w-6" />}><div className="flex flex-wrap items-center gap-2"><label className="text-sm font-medium" htmlFor="report-scenario">Scenario budget</label><select id="report-scenario" value={scenarioId ?? ""} onChange={(event) => setScenarioId(Number(event.target.value) || null)} className="h-9 rounded-md border border-input bg-background px-3 text-sm">{scenarios.map((scenario) => <option key={scenario.id} value={scenario.id}>{scenario.name} — anno base {scenario.base_year}</option>)}</select><Button type="button" variant="outline" onClick={generateNarrative} disabled={!model || generatingNarrative}>{generatingNarrative ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Sparkles className="mr-2 h-4 w-4" />}Rigenera commenti</Button><Button type="button" variant="outline" onClick={() => window.print()} disabled={!model}><Printer className="mr-2 h-4 w-4" />Anteprima stampa</Button></div></PageHeader><p className="mb-5 text-xs text-muted-foreground">La stampa browser è solo un&apos;anteprima: il PDF ufficiale sarà disponibile con M2.</p></div>
    {scenarios.length === 0 && !report.isLoading ? <Alert><AlertTitle>Nessuno scenario budget</AlertTitle><AlertDescription>Crea e genera uno scenario budget prima di aprire il report finale.</AlertDescription></Alert> : null}
    {report.isLoading ? <Card><CardContent className="flex items-center justify-center py-12"><Loader2 className="mr-3 h-8 w-8 animate-spin" /><span>Caricamento del report finale…</span></CardContent></Card> : null}
    {report.error ? <Alert variant="destructive" role="alert"><AlertTitle>{unsupportedSchema ? "Schema del report non supportato" : "Impossibile caricare il report"}</AlertTitle><AlertDescription className="space-y-3"><p>{unsupportedSchema ? "Il server ha restituito un modello non compatibile con il renderer v1. Aggiorna il client o verifica il contratto del server." : getErrorMessage(report.error, "Il report non è disponibile.")}</p><Button type="button" variant="outline" onClick={() => report.refetch()}><RefreshCw className="mr-2 h-4 w-4" />Riprova</Button></AlertDescription></Alert> : null}
    {model ? <div className="flex gap-6 print:block"><div className="print:hidden"><ReportTOC /></div><main className="min-w-0 flex-1 space-y-6 print:space-y-2">
      <ReadinessBanner readiness={model.readiness} className="print:hidden" />
      {hasStaleForecast(model) ? <Alert className="border-amber-400 print:hidden"><AlertTitle>Previsionale da rigenerare</AlertTitle><AlertDescription className="flex flex-wrap items-center gap-3"><span>Le ipotesi sono cambiate dopo l&apos;ultima generazione. Rigenera e ricarica il modello prima di considerarlo pronto.</span><Button type="button" variant="outline" onClick={regenerate} disabled={regenerating}>{regenerating ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}Rigenera previsionale</Button></AlertDescription></Alert> : null}
      <section id="scope" className="report-section"><ReportScope company={model.company} practice={model.practice} generated_at={model.generated_at} readiness={model.readiness} /></section>
      <section id="executive-summary" className="report-section"><NarrativeCard block={narrativeFor(model, "executive_summary")} onSave={saveNarrative} /></section>
      <section id="sources" className="report-section"><ReportSources workflow={model.practice.workflow_type} budgetScenarioName={model.practice.budget_scenario.name} sourceRevisions={model.source_revisions} sourceDataQuality={model.source_data_quality} /></section>
      <section id="adjustments" className="report-section"><ReportAdjustments adjustments={model.adjustments} /><div className="mt-3"><NarrativeCard block={narrativeFor(model, "adjustments_and_closing")} onSave={saveNarrative} /></div></section>
      <section id="closing" className="report-section"><ReportClosing workflow={model.practice.workflow_type} closing={model.practice.workflow_type === "infrannuale" ? model.infrannual_closing : undefined} /></section>
      <section id="assumptions" className="report-section"><AssumptionsSections model={model} /><div className="mt-3"><NarrativeCard block={narrativeFor(model, "budget_assumptions")} onSave={saveNarrative} /></div></section>
      <section id="income-forecast" className="report-section"><Card><CardHeader><CardTitle>Conto economico previsionale</CardTitle></CardHeader><CardContent className="space-y-5"><ValueTable report={model} statement="income_statement" /><ChartSeriesTable report={model} ids={["income_results", "margins"]} /><NarrativeCard block={narrativeFor(model, "economic_outlook")} onSave={saveNarrative} /></CardContent></Card></section>
      <section id="balance-forecast" className="report-section"><Card><CardHeader><CardTitle>Stato patrimoniale previsionale</CardTitle></CardHeader><CardContent><ValueTable report={model} statement="balance_sheet" /></CardContent></Card></section>
      <section id="cashflow-sustainability" className="report-section"><Card><CardHeader><CardTitle>Flussi di cassa e sostenibilità finanziaria</CardTitle></CardHeader><CardContent className="space-y-5"><ValueTable report={model} statement="cashflow" /><ChartSeriesTable report={model} ids={["cashflows", "liquidity_debt"]} /><NarrativeCard block={narrativeFor(model, "financial_outlook")} onSave={saveNarrative} /></CardContent></Card></section>
      <section id="indicators-risks" className="report-section"><Card><CardHeader><CardTitle>Indicatori e rischi</CardTitle></CardHeader><CardContent className="space-y-5"><ChartSeriesTable report={model} ids={["working_capital_days", "coverage"]} /><NarrativeCard block={narrativeFor(model, "risks_and_actions")} onSave={saveNarrative} /></CardContent></Card></section>
      <section id="diagnostics" className="report-section"><DiagnosticsPanel diagnostics={model.diagnostics} /></section>
      <section id="appendices" className="report-section"><Card><CardHeader><CardTitle>Appendici e metodologia</CardTitle></CardHeader><CardContent><Accordion type="multiple" className="print:block"><AccordionItem value="calculations"><AccordionTrigger>Calcoli disponibili</AccordionTrigger><AccordionContent><ValueTable report={model} statement="calculations" /></AccordionContent></AccordionItem><AccordionItem value="methodology"><AccordionTrigger>Nota metodologica</AccordionTrigger><AccordionContent>I valori, le serie, la readiness e la diagnostica provengono dal modello finale versionato; questa pagina non ricalcola formule finanziarie.</AccordionContent></AccordionItem></Accordion></CardContent></Card></section>
    </main></div> : null}
  </div>;
}
