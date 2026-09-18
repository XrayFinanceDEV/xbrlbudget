/**
 * «Prepara Report AI» — un solo pulsante al posto di tre azioni separate su
 * `/report`: prepara il piano editoriale, genera i sei blocchi narrativi
 * (solo quelli assenti o superati) e le note di pagina candidate (solo
 * quelle senza bozza locale non salvata e non di provenienza utente).
 *
 * Regola CLAUDE.md «Frontend»: la sequenza e la scelta di «che cosa è da
 * rigenerare» vivono qui, in un modulo puro testabile in `environment:
 * node`; il componente (`app/report/page.tsx`) chiama `runPrepareReportAI`
 * iniettando le tre chiamate API vere e due decisori che applicano
 * `decidePrepareReportAI`, e mostra solo lo stato e il riepilogo che questo
 * modulo produce. Non importa nulla da `app/` o da `components/`.
 *
 * L'ORDINE conta, ed è: **commenti generali, poi piano, poi note di pagina.**
 * I sei blocchi narrativi fanno parte del corpo del dossier, e il piano
 * editoriale è misurato contro quel corpo (`body_hash` lato server):
 * generarli DOPO aver preparato il piano lo rende immediatamente non più
 * attuale, e lo scarico del PDF risponde «Piano editoriale non preparato o
 * non più valido» a un utente che ha appena premuto il pulsante. Era il
 * difetto segnalato dal proprietario il 2026-09-18.
 *
 * Perché la decisione sulle note si prende SOLO dopo il piano: prima di
 * prepararlo non si sa quali note esistono né la loro freschezza —
 * `POST /editorial/prepare` può creare o riassociare pagine e restituisce la
 * sessione aggiornata (`revision`, `plan.plan_hash`, `report.source_hash`,
 * `report.editorial_notes`). Decidere sulle note lette PRIMA del prepare, e
 * poi chiamare la generazione con una `revision` non più corrente, farebbe
 * fallire la chiamata per conflitto ottimistico — o peggio, la farebbe
 * girare su un piano già superato. La decisione sui commenti generali,
 * invece, non dipende dal piano: si legge dal modello già a schermo.
 */

export type Freshness = "fresh" | "stale" | "missing";
export type NarrativeProvenance = "ai" | "user" | "migrated";
export type NoteProvenance = "ai" | "user" | "automatic";

export interface PrepareReportNarrativeBlock {
  id: string;
  provenance: NarrativeProvenance;
  freshness: Freshness;
}

export interface PrepareReportNote {
  id: string;
  revision: number;
  provenance: NoteProvenance;
  freshness: Freshness;
}

export interface PrepareReportAIInput {
  /** I sei id canonici dei blocchi narrativi. Un id assente dall'array sotto conta come mancante. */
  narrativeIds: readonly string[];
  narrativeBlocks: readonly PrepareReportNarrativeBlock[];
  notes: readonly PrepareReportNote[];
  /** Id delle note con una bozza locale non salvata: mai candidate, con o senza «Rigenera tutto». */
  dirtyNoteIds: ReadonlySet<string>;
  /** «Rigenera tutto»: ignora la freschezza, non i testi manuali né le bozze non salvate. */
  forceAll: boolean;
}

export interface PrepareReportAIDecision {
  narrativeNeeded: boolean;
  /** True se esiste almeno un blocco narrativo non di provenienza utente (o assente): altrimenti «già aggiornato» è la parola sbagliata, sono tutti manuali. */
  narrativeHasEligible: boolean;
  noteTargets: ReadonlyArray<{ id: string; revision: number }>;
  /** Note candidate (non utente, senza bozza) ma saltate perché già `fresh` — sempre 0 con `forceAll`. */
  noteSkippedUpToDateCount: number;
}

function isNarrativeBlockUpToDate(block: PrepareReportNarrativeBlock | undefined): boolean {
  if (!block) return false; // assente dal modello: va sempre generato
  if (block.provenance === "user") return true; // non si tocca mai: non conta come "da generare"
  return block.freshness === "fresh";
}

/** Decide che cosa rigenerare — nessuna chiamata di rete: pura funzione dei dati del modello (già a schermo, o appena tornati da `prepare`). */
export function decidePrepareReportAI(input: PrepareReportAIInput): PrepareReportAIDecision {
  const findBlock = (id: string) => input.narrativeBlocks.find((block) => block.id === id);

  const narrativeHasEligible = input.narrativeIds.some((id) => {
    const block = findBlock(id);
    return !block || block.provenance !== "user";
  });

  const narrativeNeeded = input.forceAll
    ? narrativeHasEligible
    : input.narrativeIds.some((id) => !isNarrativeBlockUpToDate(findBlock(id)));

  const eligibleNotes = input.notes.filter((note) => note.provenance !== "user" && !input.dirtyNoteIds.has(note.id));
  // Una nota `automatic` è il testo neutro che `prepare` mette in ogni pagina
  // per misurarne lo spazio, non un commento: nasce `fresh` rispetto al piano
  // e senza questa riga il pulsante la considerava «già aggiornata» e non
  // generava mai nulla — il dossier restava pieno di «Pagina 8. I grafici
  // confrontano le serie disponibili.» (segnalato dal proprietario il
  // 2026-09-18). Un segnaposto è sempre da generare.
  const targets = eligibleNotes.filter((note) =>
    input.forceAll || note.provenance === "automatic" || note.freshness !== "fresh");

  return {
    narrativeNeeded,
    narrativeHasEligible,
    noteTargets: targets.map((note) => ({ id: note.id, revision: note.revision })),
    noteSkippedUpToDateCount: eligibleNotes.length - targets.length,
  };
}

export type PrepareReportAIStep = "plan" | "narrative" | "notes";
export type PrepareReportAIStepOutcome = "done" | "skipped" | "failed" | "not_attempted";

export interface PrepareReportAIStepResult {
  outcome: PrepareReportAIStepOutcome;
  error?: unknown;
}

export interface PrepareReportAISteps<TSession> {
  /** Sempre chiamato, anche a piano già attuale: è l'unico modo di ottenere la revisione corrente (§1 del brief). */
  preparePlan: () => Promise<TSession>;
  regenerateNarrative: () => Promise<void>;
  regenerateNotes: (session: TSession, targets: ReadonlyArray<{ id: string; revision: number }>) => Promise<void>;
}

/** La parte di decisione che riguarda i sei blocchi narrativi: si prende dal modello già a schermo, prima del piano. */
export type PrepareReportNarrativeDecision = Pick<PrepareReportAIDecision, "narrativeNeeded" | "narrativeHasEligible">;

export interface PrepareReportAIDeciders<TSession> {
  /** Dal modello corrente: i commenti generali si rigenerano PRIMA del piano. */
  narrative: () => PrepareReportNarrativeDecision;
  /** Dalla sessione tornata da `preparePlan`: solo lì le note sono quelle vere. */
  notes: (session: TSession) => PrepareReportAIDecision;
}

export interface PrepareReportAIResult {
  plan: PrepareReportAIStepResult;
  narrative: PrepareReportAIStepResult;
  notes: PrepareReportAIStepResult & { generatedCount: number };
  /** False solo quando il piano è fallito: le note non sono nemmeno state tentate. */
  continued: boolean;
  /** Null quando il piano è fallito: senza una sessione fresca non c'è nulla da decidere. */
  decision: PrepareReportAIDecision | null;
  summary: string;
}

async function runStep(run: () => Promise<void>): Promise<PrepareReportAIStepResult> {
  try {
    await run();
    return { outcome: "done" };
  } catch (error) {
    return { outcome: "failed", error };
  }
}

const defaultDescribeError = (error: unknown): string => (error instanceof Error ? error.message : String(error));

/**
 * Esegue la sequenza: (se serve) i sei blocchi narrativi, poi il piano, poi
 * (se ci sono note candidate) le note di pagina. Un fallimento del piano
 * ferma le note — senza piano non si generano — mentre la narrativa, che è
 * già stata tentata, conserva il proprio esito. Un fallimento della
 * narrativa non ferma nulla: sono contenuti indipendenti nello schema, e
 * ciò che riesce resta (§5 del brief). `notify`, se
 * passato, avvisa il chiamante prima di ogni passo *tentato* (mai per un
 * passo saltato), per aggiornare l'etichetta di stato a schermo.
 */
export async function runPrepareReportAI<TSession>(
  deciders: PrepareReportAIDeciders<TSession>,
  steps: PrepareReportAISteps<TSession>,
  options?: { describeError?: (error: unknown) => string; notify?: (step: PrepareReportAIStep) => void }
): Promise<PrepareReportAIResult> {
  const describeError = options?.describeError ?? defaultDescribeError;
  const notify = options?.notify;

  // 1. I commenti generali PRIMA del piano: fanno parte del corpo su cui il
  //    piano è misurato, e rigenerarli dopo lo renderebbe subito superato.
  const narrativeDecision = deciders.narrative();
  let narrative: PrepareReportAIStepResult;
  if (narrativeDecision.narrativeNeeded) {
    notify?.("narrative");
    narrative = await runStep(() => steps.regenerateNarrative());
  } else {
    narrative = { outcome: "skipped" };
  }

  notify?.("plan");
  let session: TSession;
  try {
    session = await steps.preparePlan();
  } catch (error) {
    return {
      plan: { outcome: "failed", error },
      narrative,
      notes: { outcome: "not_attempted", generatedCount: 0 },
      continued: false,
      decision: null,
      summary: `Impossibile preparare il piano editoriale: ${describeError(error)}`,
    };
  }
  const plan: PrepareReportAIStepResult = { outcome: "done" };
  const decision = { ...deciders.notes(session), ...narrativeDecision };

  let notes: PrepareReportAIStepResult & { generatedCount: number };
  if (decision.noteTargets.length > 0) {
    notify?.("notes");
    const noteResult = await runStep(() => steps.regenerateNotes(session, decision.noteTargets));
    notes = { ...noteResult, generatedCount: noteResult.outcome === "done" ? decision.noteTargets.length : 0 };
  } else {
    notes = { outcome: "skipped", generatedCount: 0 };
  }

  return {
    plan,
    narrative,
    notes,
    continued: true,
    decision,
    summary: summarizePrepareReportAI(narrative, notes, decision, describeError),
  };
}

function summarizePrepareReportAI(
  narrative: PrepareReportAIStepResult,
  notes: PrepareReportAIStepResult & { generatedCount: number },
  decision: PrepareReportAIDecision,
  describeError: (error: unknown) => string
): string {
  const parts: string[] = ["piano aggiornato"];

  if (narrative.outcome === "done") parts.push("commenti generati");
  else if (narrative.outcome === "failed") parts.push(`generazione commenti non riuscita: ${describeError(narrative.error)}`);
  else if (narrative.outcome === "skipped") parts.push(decision.narrativeHasEligible ? "commenti già aggiornati" : "nessun commento automatico da rigenerare");

  if (notes.outcome === "done") {
    const generated = notes.generatedCount;
    const skipped = decision.noteSkippedUpToDateCount;
    const generatedPhrase = generated === 1 ? "1 nota generata" : `${generated} note generate`;
    const skippedPhrase = skipped > 0 ? (skipped === 1 ? ", 1 già aggiornata" : `, ${skipped} già aggiornate`) : "";
    parts.push(generatedPhrase + skippedPhrase);
  } else if (notes.outcome === "failed") {
    parts.push(`generazione note non riuscita: ${describeError(notes.error)}`);
  } else if (notes.outcome === "skipped") {
    parts.push(decision.noteSkippedUpToDateCount > 0 ? "note già aggiornate" : "nessuna nota da generare");
  }

  return parts.join("; ");
}
