import { describe, expect, it, vi } from "vitest";

import {
  decidePrepareReportAI,
  runPrepareReportAI,
  type PrepareReportAIDecision,
  type PrepareReportNarrativeBlock,
  type PrepareReportNote,
} from "./prepare-report-ai";

const NARRATIVE_IDS = ["executive_summary", "adjustments_and_closing", "budget_assumptions", "economic_outlook", "financial_outlook", "risks_and_actions"] as const;

function freshBlocks(overrides: Partial<Record<string, Partial<PrepareReportNarrativeBlock>>> = {}): PrepareReportNarrativeBlock[] {
  return NARRATIVE_IDS.map((id) => ({ id, provenance: "ai", freshness: "fresh", ...overrides[id] }));
}

describe("decidePrepareReportAI", () => {
  it("non serve nulla quando tutti i blocchi sono freschi e tutte le note sono fresh", () => {
    const decision = decidePrepareReportAI({
      narrativeIds: NARRATIVE_IDS,
      narrativeBlocks: freshBlocks(),
      notes: [{ id: "n1", revision: 1, provenance: "ai", freshness: "fresh" }],
      dirtyNoteIds: new Set(),
      forceAll: false,
    });
    expect(decision.narrativeNeeded).toBe(false);
    expect(decision.noteTargets).toEqual([]);
    expect(decision.noteSkippedUpToDateCount).toBe(1);
  });

  it("chiede la narrativa quando un blocco manca dal modello", () => {
    const decision = decidePrepareReportAI({
      narrativeIds: NARRATIVE_IDS,
      narrativeBlocks: freshBlocks().filter((block) => block.id !== "risks_and_actions"),
      notes: [],
      dirtyNoteIds: new Set(),
      forceAll: false,
    });
    expect(decision.narrativeNeeded).toBe(true);
  });

  it("chiede la narrativa quando un blocco automatico è stale, ma non tocca un blocco utente stale", () => {
    const decision = decidePrepareReportAI({
      narrativeIds: NARRATIVE_IDS,
      narrativeBlocks: freshBlocks({ economic_outlook: { freshness: "stale" }, financial_outlook: { provenance: "user", freshness: "stale" } }),
      notes: [],
      dirtyNoteIds: new Set(),
      forceAll: false,
    });
    expect(decision.narrativeNeeded).toBe(true);
    expect(decision.narrativeHasEligible).toBe(true);
  });

  it("segnala che non c'è nulla di automatico quando tutti i blocchi sono utente", () => {
    const decision = decidePrepareReportAI({
      narrativeIds: NARRATIVE_IDS,
      narrativeBlocks: freshBlocks().map((block) => ({ ...block, provenance: "user" as const, freshness: "stale" as const })),
      notes: [],
      dirtyNoteIds: new Set(),
      forceAll: false,
    });
    expect(decision.narrativeNeeded).toBe(false);
    expect(decision.narrativeHasEligible).toBe(false);
  });

  it("esclude sempre le note utente e le note con bozza locale non salvata, anche con forceAll", () => {
    const notes: PrepareReportNote[] = [
      { id: "user-note", revision: 1, provenance: "user", freshness: "stale" },
      { id: "dirty-note", revision: 1, provenance: "ai", freshness: "stale" },
      { id: "candidate", revision: 2, provenance: "automatic", freshness: "stale" },
    ];
    const decisionNormal = decidePrepareReportAI({ narrativeIds: NARRATIVE_IDS, narrativeBlocks: freshBlocks(), notes, dirtyNoteIds: new Set(["dirty-note"]), forceAll: false });
    expect(decisionNormal.noteTargets).toEqual([{ id: "candidate", revision: 2 }]);

    const decisionForced = decidePrepareReportAI({ narrativeIds: NARRATIVE_IDS, narrativeBlocks: freshBlocks(), notes, dirtyNoteIds: new Set(["dirty-note"]), forceAll: true });
    expect(decisionForced.noteTargets).toEqual([{ id: "candidate", revision: 2 }]);
  });

  it("con forceAll rigenera anche le note già fresh, purché non utente e non in bozza", () => {
    const notes: PrepareReportNote[] = [
      { id: "fresh-note", revision: 3, provenance: "automatic", freshness: "fresh" },
      { id: "user-note", revision: 1, provenance: "user", freshness: "fresh" },
    ];
    const decision = decidePrepareReportAI({ narrativeIds: NARRATIVE_IDS, narrativeBlocks: freshBlocks(), notes, dirtyNoteIds: new Set(), forceAll: true });
    expect(decision.noteTargets).toEqual([{ id: "fresh-note", revision: 3 }]);
    expect(decision.noteSkippedUpToDateCount).toBe(0);
  });

  it("con forceAll rigenera comunque la narrativa anche se tutti i blocchi automatici sono fresh", () => {
    const decision = decidePrepareReportAI({ narrativeIds: NARRATIVE_IDS, narrativeBlocks: freshBlocks(), notes: [], dirtyNoteIds: new Set(), forceAll: true });
    expect(decision.narrativeNeeded).toBe(true);
  });
});

describe("runPrepareReportAI", () => {
  interface FakeSession {
    revision: number;
  }

  const decisionCompleta: PrepareReportAIDecision = {
    narrativeNeeded: true,
    narrativeHasEligible: true,
    noteTargets: [{ id: "n1", revision: 1 }, { id: "n2", revision: 2 }],
    noteSkippedUpToDateCount: 1,
  };
  const buildDecisionCompleta = () => decisionCompleta;
  const fakeSession: FakeSession = { revision: 7 };

  it("esegue la sequenza completa nell'ordine piano → narrativa → note, passando la sessione fresca a entrambi i passi successivi", async () => {
    const calls: string[] = [];
    const preparePlan = vi.fn().mockImplementation(async () => { calls.push("plan"); return fakeSession; });
    const regenerateNarrative = vi.fn().mockImplementation(async (session: FakeSession) => { calls.push(`narrative:${session.revision}`); });
    const regenerateNotes = vi.fn().mockImplementation(async (session: FakeSession, targets) => { calls.push(`notes:${session.revision}:${targets.length}`); });

    const result = await runPrepareReportAI(buildDecisionCompleta, { preparePlan, regenerateNarrative, regenerateNotes });

    expect(calls).toEqual(["plan", "narrative:7", "notes:7:2"]);
    expect(regenerateNotes).toHaveBeenCalledWith(fakeSession, decisionCompleta.noteTargets);
    expect(result.plan.outcome).toBe("done");
    expect(result.narrative.outcome).toBe("done");
    expect(result.notes).toEqual({ outcome: "done", generatedCount: 2 });
    expect(result.continued).toBe(true);
    expect(result.decision).toEqual(decisionCompleta);
    expect(result.summary).toBe("piano aggiornato; commenti generati; 2 note generate, 1 già aggiornata");
  });

  it("decide dopo il piano, non prima: buildDecision riceve la sessione appena restituita da preparePlan", async () => {
    const preparePlan = vi.fn().mockResolvedValue(fakeSession);
    const buildDecision = vi.fn().mockReturnValue({ narrativeNeeded: false, narrativeHasEligible: true, noteTargets: [], noteSkippedUpToDateCount: 0 });

    await runPrepareReportAI(buildDecision, { preparePlan, regenerateNarrative: vi.fn(), regenerateNotes: vi.fn() });

    expect(buildDecision).toHaveBeenCalledWith(fakeSession);
    expect(preparePlan.mock.invocationCallOrder[0]).toBeLessThan(buildDecision.mock.invocationCallOrder[0]);
  });

  it("salta i passi già aggiornati senza chiamare le rispettive API", async () => {
    const preparePlan = vi.fn().mockResolvedValue(fakeSession);
    const regenerateNarrative = vi.fn().mockResolvedValue(undefined);
    const regenerateNotes = vi.fn().mockResolvedValue(undefined);
    const decision: PrepareReportAIDecision = { narrativeNeeded: false, narrativeHasEligible: true, noteTargets: [], noteSkippedUpToDateCount: 3 };

    const result = await runPrepareReportAI(() => decision, { preparePlan, regenerateNarrative, regenerateNotes });

    expect(preparePlan).toHaveBeenCalledOnce();
    expect(regenerateNarrative).not.toHaveBeenCalled();
    expect(regenerateNotes).not.toHaveBeenCalled();
    expect(result.narrative.outcome).toBe("skipped");
    expect(result.notes).toEqual({ outcome: "skipped", generatedCount: 0 });
    expect(result.summary).toBe("piano aggiornato; commenti già aggiornati; note già aggiornate");
  });

  it("si interrompe al fallimento del piano: narrativa e note non vengono nemmeno tentate", async () => {
    const preparePlan = vi.fn().mockRejectedValue(new Error("scenario non trovato"));
    const regenerateNarrative = vi.fn().mockResolvedValue(undefined);
    const regenerateNotes = vi.fn().mockResolvedValue(undefined);

    const result = await runPrepareReportAI(buildDecisionCompleta, { preparePlan, regenerateNarrative, regenerateNotes });

    expect(regenerateNarrative).not.toHaveBeenCalled();
    expect(regenerateNotes).not.toHaveBeenCalled();
    expect(result.plan.outcome).toBe("failed");
    expect(result.narrative.outcome).toBe("not_attempted");
    expect(result.notes).toEqual({ outcome: "not_attempted", generatedCount: 0 });
    expect(result.continued).toBe(false);
    expect(result.decision).toBeNull();
    expect(result.summary).toBe("Impossibile preparare il piano editoriale: scenario non trovato");
  });

  it("un errore parziale sulla narrativa non blocca le note, e il riepilogo nomina il passo fallito", async () => {
    const preparePlan = vi.fn().mockResolvedValue(fakeSession);
    const regenerateNarrative = vi.fn().mockRejectedValue(new Error("timeout del modello"));
    const regenerateNotes = vi.fn().mockResolvedValue(undefined);

    const result = await runPrepareReportAI(buildDecisionCompleta, { preparePlan, regenerateNarrative, regenerateNotes });

    expect(regenerateNotes).toHaveBeenCalledOnce();
    expect(result.narrative.outcome).toBe("failed");
    expect(result.notes.outcome).toBe("done");
    expect(result.notes.generatedCount).toBe(2);
    expect(result.summary).toBe("piano aggiornato; generazione commenti non riuscita: timeout del modello; 2 note generate, 1 già aggiornata");
  });

  it("un errore sulle note non azzera ciò che la narrativa ha già ottenuto, e riporta zero note generate", async () => {
    const preparePlan = vi.fn().mockResolvedValue(fakeSession);
    const regenerateNarrative = vi.fn().mockResolvedValue(undefined);
    const regenerateNotes = vi.fn().mockRejectedValue(new Error("nota non valida"));

    const result = await runPrepareReportAI(buildDecisionCompleta, { preparePlan, regenerateNarrative, regenerateNotes });

    expect(result.narrative.outcome).toBe("done");
    expect(result.notes.outcome).toBe("failed");
    expect(result.notes.generatedCount).toBe(0);
    expect(result.summary).toContain("generazione note non riuscita: nota non valida");
  });

  it("avvisa `notify` solo per i passi tentati, mai per quelli saltati", async () => {
    const preparePlan = vi.fn().mockResolvedValue(fakeSession);
    const regenerateNarrative = vi.fn().mockResolvedValue(undefined);
    const regenerateNotes = vi.fn().mockResolvedValue(undefined);
    const notify = vi.fn();
    const decision: PrepareReportAIDecision = { narrativeNeeded: false, narrativeHasEligible: true, noteTargets: [{ id: "n1", revision: 1 }], noteSkippedUpToDateCount: 0 };

    await runPrepareReportAI(() => decision, { preparePlan, regenerateNarrative, regenerateNotes }, { notify });

    expect(notify.mock.calls.map((call) => call[0])).toEqual(["plan", "notes"]);
  });

  it("usa `describeError` per tradurre l'errore nel riepilogo", async () => {
    const preparePlan = vi.fn().mockRejectedValue({ weird: "shape" });
    const result = await runPrepareReportAI(
      buildDecisionCompleta,
      { preparePlan, regenerateNarrative: vi.fn(), regenerateNotes: vi.fn() },
      { describeError: () => "errore tradotto" }
    );
    expect(result.summary).toBe("Impossibile preparare il piano editoriale: errore tradotto");
  });
});
