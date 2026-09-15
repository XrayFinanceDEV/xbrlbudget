"use client";

import { useEffect, useState } from "react";
import { ArchiveRestore, Loader2, Save, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Textarea } from "@/components/ui/textarea";
import type { EditorialNote, EditorialPage, EditorialPlan } from "@/types/final-report-v2";
import type { EditorialNoteReference } from "@/types/editorial-session";

type Drafts = Record<string, string>;
export interface EditorialNotesProps {
  plan: EditorialPlan; notes: EditorialNote[]; archivedNotes: EditorialNote[]; drafts: Drafts; dirty: Record<string, boolean>;
  savingId?: string; generating?: boolean; onDraft: (id: string, text: string) => void;
  onSave: (note: EditorialNote, text: string, fromNote?: EditorialNoteReference) => void;
  onGenerate: (notes: EditorialNote[]) => void; onReassociate: (note: EditorialNote) => void;
}
function pageLabel(page: EditorialPage, index: number): string { return `Pagina ${index + 1} · ${page.section_id.replaceAll("-", " ")}`; }
export function eligibleForGeneration(notes: EditorialNote[], selected: Record<string, boolean>, dirty: Record<string, boolean>): EditorialNote[] {
  return notes.filter((note) => note.provenance !== "user" && selected[note.id] && !dirty[note.id]);
}
export function EditorialNotes({ plan, notes, archivedNotes, drafts, dirty, savingId, generating, onDraft, onSave, onGenerate, onReassociate }: EditorialNotesProps) {
  const [selectedAi, setSelectedAi] = useState<Record<string, boolean>>({});
  const [selectedCurrent, setSelectedCurrent] = useState<string>(notes[0]?.id ?? "");
  const [references, setReferences] = useState<Record<string, EditorialNoteReference>>({});
  useEffect(() => setSelectedCurrent((current) => notes.some((note) => note.id === current) ? current : (notes[0]?.id ?? "")), [notes]);
  const byId = new Map(notes.map((note) => [note.id, note]));
  const planned = plan.pages.map((page) => ({ page, note: byId.get(page.note_id) })).filter((item): item is { page: EditorialPage; note: EditorialNote } => Boolean(item.note));
  const aiEligible = planned.map((item) => item.note).filter((note) => note.provenance !== "user");
  const checked = eligibleForGeneration(aiEligible, selectedAi, dirty);
  return <><section id="editorial-notes" className="space-y-5 print:hidden">
    <Card><CardHeader><CardTitle>Commenti per pagina</CardTitle></CardHeader><CardContent className="space-y-4">
      <p className="text-sm text-muted-foreground">Ogni commento ha spazio per {plan.pages[0]?.note_slot.max_lines ?? 0} righe. Origine e freschezza provengono dal server; i commenti utente non sono selezionabili per l&apos;AI.</p>
      <div className="flex flex-wrap items-center gap-3"><Button type="button" onClick={() => onGenerate(checked)} disabled={generating || checked.length === 0}>{generating ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Sparkles className="mr-2 h-4 w-4" />}Genera selezionati ({checked.length})</Button><label className="text-sm">Nota corrente per archivio <select value={selectedCurrent} onChange={(event) => setSelectedCurrent(event.target.value)} className="ml-2 rounded border bg-background p-1">{notes.map((note) => <option key={note.id} value={note.id}>{note.id}</option>)}</select></label></div>
      {planned.map(({ page, note }, index) => <Card key={page.id} className="border-dashed"><CardHeader className="pb-2"><CardTitle className="text-base">{pageLabel(page, index)}</CardTitle></CardHeader><CardContent>
        <p className="mb-2 text-xs text-muted-foreground">{note.id} · {note.provenance} · {note.freshness} · revisione {note.revision} · tabella: {page.table_parts?.map((part) => `${part.statement_id} (${part.row_ids.length})`).join(", ") || "nessuna"}</p>
        {note.provenance !== "user" ? <label className="mb-2 flex items-center gap-2 text-sm"><Checkbox checked={Boolean(selectedAi[note.id])} disabled={Boolean(dirty[note.id])} onCheckedChange={(checked) => setSelectedAi((current) => ({ ...current, [note.id]: checked === true }))} />Generabile dall&apos;AI{dirty[note.id] ? " (salva prima la bozza)" : ""}</label> : <p className="mb-2 text-xs text-muted-foreground">Commento utente: non viene rigenerato dall&apos;AI.</p>}
        <Textarea aria-label={`Commento ${note.id}`} value={drafts[note.id] ?? note.text} onChange={(event) => onDraft(note.id, event.target.value)} className="min-h-24" />
        <Button type="button" size="sm" className="mt-2" onClick={() => onSave(note, drafts[note.id] ?? note.text, references[note.id])} disabled={savingId === note.id || !dirty[note.id]}>{savingId === note.id ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}Salva commento</Button>
      </CardContent></Card>)}
    </CardContent></Card></section>
    {archivedNotes.length ? <Card className="print:hidden"><CardHeader><CardTitle>Commenti archiviati</CardTitle></CardHeader><CardContent className="space-y-3">{archivedNotes.map((note) => <article key={`${note.id}-${note.plan_hash}-${note.revision}`} className="rounded border p-3"><p className="text-xs text-muted-foreground">{note.id} · {note.provenance} · revisione {note.revision}</p><p className="mt-1 whitespace-pre-wrap text-sm">{note.text}</p><Button type="button" variant="outline" size="sm" className="mt-2" disabled={!selectedCurrent} onClick={() => { const current = byId.get(selectedCurrent); if (!current) return; if (note.provenance === "user") setReferences((references) => ({ ...references, [current.id]: { id: note.id, plan_hash: note.plan_hash, revision: note.revision } })); onDraft(current.id, note.text); onReassociate(note); }}><ArchiveRestore className="mr-2 h-4 w-4" />{note.provenance === "user" ? "Copia e ricollega alla nota selezionata" : "Copia nella nota selezionata"}</Button></article>)}</CardContent></Card> : null}</>;
}
