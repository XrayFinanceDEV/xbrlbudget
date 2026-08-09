# Stepper pratica a fasi + barra azioni — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sostituire la barra piatta di 15 step della pratica con uno stepper a due livelli (3 fasi + sotto-barra contestuale) e una barra azioni unica che centralizza l'avanzamento.

**Architecture:** Tutta la logica del percorso vive in `frontend/lib/pratica-steps.ts`, un modulo puro senza React né rete (fasi, gruppi, step successivo/precedente, stato delle fasi, motivi di blocco, derivazione dei gate). Due componenti la disegnano: `PraticaStepper` (in alto, montato da `Navigation`) e `PraticaActionBar` (in basso, montata da `app/layout.tsx`). Le pagine registrano la propria azione primaria in `PraticaActionContext` tramite l'hook `usePrimaryAction`; chi non registra nulla riceve un fallback di sola navigazione.

**Tech Stack:** Next.js 15 (app router) · React 19 · TypeScript 5 · Tailwind v3 · shadcn/ui (new-york) · lucide-react · Vitest 3 (nuovo, solo per il modulo puro)

**Spec:** `docs/superpowers/specs/2026-08-09-stepper-pratica-a-fasi-design.md`

## Global Constraints

- Tutto il testo UI è in **italiano**. Nessuna emoji: solo icone `lucide-react`.
- Solo componenti shadcn/ui (`Button`, `Tooltip`, …), mai HTML grezzo per bottoni/tabelle.
- Solo colori semantici (`text-foreground`, `text-muted-foreground`, `bg-card`, `border-border`, `bg-background`): mai hex hardcoded.
- Stepper e barra azioni sono `print:hidden`.
- **Nessuna logica di salvataggio esistente va riscritta.** Le migrazioni dei CTA spostano l'handler e le sue condizioni di `disabled` *intatte*.
- Non si tocca il backend, non si toccano i gate semantici, non si scompone `app/pratica/page.tsx`.
- Tutti i comandi si eseguono da `frontend/`.
- Prima di ogni commit: `git diff --stat` per verificare che non ci siano righe fantasma da conversione CRLF/LF (rischio noto del repo).

## File Structure

| File | Responsabilità |
|---|---|
| `lib/pratica-steps.ts` *(modifica)* | Modello puro del percorso: costruzione step, fasi, gruppi, `nextStep`/`prevStep`/`phaseStatus`/`gateReason`/`praticaGates`/`currentStepId`/`firstEnabledStep` |
| `lib/pratica-steps.test.ts` *(nuovo)* | Test unitari del modulo puro |
| `vitest.config.ts` *(nuovo)* | Configurazione Vitest (solo `lib/**/*.test.ts`) |
| `components/PraticaStepper.tsx` *(riscrittura)* | Disegna identità pratica, chip di fase, sotto-barra della fase attiva |
| `contexts/PraticaActionContext.tsx` *(nuovo)* | Registro dell'azione primaria corrente |
| `components/pratica/PraticaActionBar.tsx` *(nuovo)* | Barra in basso: Indietro + azione primaria (registrata o fallback) |
| `app/layout.tsx` *(modifica)* | Monta provider e barra |
| `components/pratica/AnagraficheStep.tsx` *(modifica)* | Registra la propria azione; `seededFor` ref → stato |
| `app/pratica/page.tsx` *(modifica)* | 6 CTA inline → `usePrimaryAction` |
| `app/budget/page.tsx` *(modifica)* | 1 CTA inline → `usePrimaryAction` |

---

### Task 1: Il modello puro del percorso

**Files:**
- Create: `frontend/vitest.config.ts`
- Create: `frontend/lib/pratica-steps.test.ts`
- Modify: `frontend/lib/pratica-steps.ts` (intero file)
- Modify: `frontend/package.json` (script `test` + devDependency)

**Interfaces:**
- Consumes: `PraticaState` da `contexts/PraticaContext` (solo come tipo).
- Produces: `PraticaPhase = "dati" | "analisi" | "previsionale"`; `PraticaStepGroup = "azione" | "vista"`; `PraticaStep` con i campi nuovi `group`; `PHASE_ORDER: PraticaPhase[]`; `PHASE_LABELS: Record<PraticaPhase, string>`; `buildPraticaSteps(pratica, gates): PraticaStep[]`; `praticaGates(pratica): PraticaGates`; `currentStepId(pathname, analysisStep): string`; `nextStep(steps, currentId): PraticaStep | null`; `prevStep(steps, currentId): PraticaStep | null`; `firstEnabledStep(steps, phase): PraticaStep | null`; `phaseStatus(steps, phase, currentId): "done" | "active" | "todo" | "locked"`; `gateReason(step, gates, pratica): string | null`.

- [ ] **Step 1: Installare Vitest e aggiungere lo script**

```bash
cd frontend
npm install -D vitest@^3
npm pkg set scripts.test="vitest run"
```

- [ ] **Step 2: Creare `frontend/vitest.config.ts`**

```ts
import path from "path";
import { defineConfig } from "vitest/config";

// Solo il modulo puro del percorso pratica: nessun ambiente DOM, nessun React.
export default defineConfig({
  test: {
    environment: "node",
    include: ["lib/**/*.test.ts"],
  },
  resolve: {
    alias: { "@": path.resolve(__dirname, ".") },
  },
});
```

- [ ] **Step 3: Scrivere il test che fallisce — `frontend/lib/pratica-steps.test.ts`**

```ts
import { describe, expect, it } from "vitest";
import type { PraticaState } from "@/contexts/PraticaContext";
import {
  buildPraticaSteps,
  currentStepId,
  firstEnabledStep,
  gateReason,
  nextStep,
  phaseStatus,
  praticaGates,
  prevStep,
  type PraticaGates,
} from "./pratica-steps";

const PRATICA: PraticaState = {
  workflow: "bilancio",
  companyId: 1,
  fiscalYear: 2025,
  periodMonths: 9,
  infrannualeScenarioId: null,
  budgetScenarioId: null,
  analysisStep: "anagrafiche",
  rettificheConfirmed: { storico: false, verifica: false },
};

const NO_GATES: PraticaGates = {
  imported: false,
  rettificheOk: false,
  comparisonReady: false,
  projectionReady: false,
  budgetScenario: false,
  forecastReady: false,
};

const ALL_GATES: PraticaGates = {
  imported: true,
  rettificheOk: true,
  comparisonReady: true,
  projectionReady: true,
  budgetScenario: true,
  forecastReady: true,
};

const ids = (steps: { id: string }[]) => steps.map((s) => s.id);

describe("buildPraticaSteps", () => {
  it("percorso bilancio: tre fasi nell'ordine dati → analisi → previsionale", () => {
    const steps = buildPraticaSteps(PRATICA, ALL_GATES);
    expect(ids(steps)).toEqual([
      "anagrafiche", "import", "rettifiche",
      "comparison", "projection", "results", "stampa",
      "budget", "indici", "ce-previsionale", "sp-previsionale",
      "riclassificato", "rendiconto", "report",
    ]);
    expect(steps.filter((s) => s.phase === "dati").length).toBe(3);
    expect(steps.filter((s) => s.phase === "analisi").length).toBe(4);
    expect(steps.filter((s) => s.phase === "previsionale").length).toBe(7);
  });

  it("marca come vista tutto ciò che è di sola lettura", () => {
    const steps = buildPraticaSteps(PRATICA, ALL_GATES);
    const group = (id: string) => steps.find((s) => s.id === id)?.group;
    expect(group("rettifiche")).toBe("azione");
    expect(group("comparison")).toBe("azione");
    expect(group("projection")).toBe("azione");
    expect(group("results")).toBe("vista");
    expect(group("stampa")).toBe("vista");
    expect(group("budget")).toBe("azione");
    expect(group("indici")).toBe("vista");
    expect(group("report")).toBe("vista");
  });

  it("bilancio annuale: nessuno step Proiezione", () => {
    const steps = buildPraticaSteps({ ...PRATICA, periodMonths: 12 }, ALL_GATES);
    expect(ids(steps)).not.toContain("projection");
  });

  it("startup: nessuna fase analisi, anagrafiche è una rotta", () => {
    const steps = buildPraticaSteps({ ...PRATICA, workflow: "startup" }, ALL_GATES);
    expect(steps.filter((s) => s.phase === "analisi")).toHaveLength(0);
    const anagrafiche = steps.find((s) => s.id === "anagrafiche");
    expect(anagrafiche?.phase).toBe("dati");
    expect(anagrafiche?.kind).toBe("route");
    expect(anagrafiche?.route).toBe("/budget");
  });

  it("legacy budget resume: solo la fase previsionale", () => {
    const steps = buildPraticaSteps(
      { ...PRATICA, budgetScenarioId: 7, infrannualeScenarioId: null },
      ALL_GATES,
    );
    expect(steps.every((s) => s.phase === "previsionale")).toBe(true);
  });
});

describe("nextStep / prevStep", () => {
  it("a 9 mesi il Confronto porta alla Proiezione", () => {
    const steps = buildPraticaSteps(PRATICA, ALL_GATES);
    expect(nextStep(steps, "comparison")?.id).toBe("projection");
  });

  it("a 12 mesi il Confronto salta agli Indicatori", () => {
    const steps = buildPraticaSteps({ ...PRATICA, periodMonths: 12 }, ALL_GATES);
    expect(nextStep(steps, "comparison")?.id).toBe("results");
    expect(prevStep(steps, "results")?.id).toBe("comparison");
  });

  it("null oltre l'ultimo step e prima del primo", () => {
    const steps = buildPraticaSteps(PRATICA, ALL_GATES);
    expect(nextStep(steps, "report")).toBeNull();
    expect(prevStep(steps, "anagrafiche")).toBeNull();
  });

  it("null quando lo step corrente non appartiene al percorso", () => {
    const steps = buildPraticaSteps(PRATICA, ALL_GATES);
    expect(nextStep(steps, "inesistente")).toBeNull();
    expect(prevStep(steps, "inesistente")).toBeNull();
  });

  it("restituisce lo step successivo anche se disabilitato", () => {
    const steps = buildPraticaSteps(PRATICA, NO_GATES);
    const next = nextStep(steps, "import");
    expect(next?.id).toBe("rettifiche");
    expect(next?.enabled).toBe(false);
  });
});

describe("phaseStatus", () => {
  it("done / active / todo secondo la posizione della fase attiva", () => {
    const steps = buildPraticaSteps(PRATICA, ALL_GATES);
    expect(phaseStatus(steps, "dati", "comparison")).toBe("done");
    expect(phaseStatus(steps, "analisi", "comparison")).toBe("active");
    expect(phaseStatus(steps, "previsionale", "comparison")).toBe("todo");
  });

  it("locked quando nessuno step della fase è abilitato", () => {
    const steps = buildPraticaSteps(PRATICA, NO_GATES);
    expect(phaseStatus(steps, "previsionale", "import")).toBe("locked");
  });

  it("active vince su locked", () => {
    const steps = buildPraticaSteps(PRATICA, NO_GATES);
    expect(phaseStatus(steps, "analisi", "comparison")).toBe("active");
  });
});

describe("firstEnabledStep", () => {
  it("primo step abilitato della fase, null se non ce n'è", () => {
    const steps = buildPraticaSteps(PRATICA, { ...NO_GATES, imported: true });
    expect(firstEnabledStep(steps, "dati")?.id).toBe("anagrafiche");
    expect(firstEnabledStep(steps, "previsionale")).toBeNull();
  });
});

describe("gateReason", () => {
  it("null quando lo step è abilitato", () => {
    const steps = buildPraticaSteps(PRATICA, ALL_GATES);
    const rettifiche = steps.find((s) => s.id === "rettifiche")!;
    expect(gateReason(rettifiche, ALL_GATES, PRATICA)).toBeNull();
  });

  it("motivo specifico per ogni gate non soddisfatto", () => {
    const steps = buildPraticaSteps(PRATICA, NO_GATES);
    const step = (id: string) => steps.find((s) => s.id === id)!;
    expect(gateReason(step("rettifiche"), NO_GATES, PRATICA)).toBe("Nessun bilancio importato");
    expect(gateReason(step("comparison"), NO_GATES, PRATICA)).toBe("Nessun bilancio importato");
    expect(
      gateReason(step("comparison"), { ...NO_GATES, imported: true }, PRATICA),
    ).toBe("Rettifiche non confermate");
    expect(gateReason(step("report"), NO_GATES, PRATICA)).toBe("Previsionale non generato");
  });
});

describe("praticaGates", () => {
  it("le rettifiche sono ok solo con entrambe le schede confermate", () => {
    expect(praticaGates(PRATICA).rettificheOk).toBe(false);
    expect(
      praticaGates({ ...PRATICA, rettificheConfirmed: { storico: true, verifica: true } })
        .rettificheOk,
    ).toBe(true);
  });

  it("imported segue fiscalYear, i gate previsionali seguono budgetScenarioId", () => {
    expect(praticaGates(PRATICA).imported).toBe(true);
    expect(praticaGates({ ...PRATICA, fiscalYear: null }).imported).toBe(false);
    expect(praticaGates({ ...PRATICA, budgetScenarioId: 3 }).forecastReady).toBe(true);
  });
});

describe("currentStepId", () => {
  it("dentro /pratica vince la tab del wizard, fuori vince la rotta", () => {
    expect(currentStepId("/pratica", "rettifiche")).toBe("rettifiche");
    expect(currentStepId("/forecast/balance", "rettifiche")).toBe("sp-previsionale");
    expect(currentStepId("/forecast/reclassified", "x")).toBe("riclassificato");
    expect(currentStepId("/forecast/income", "x")).toBe("ce-previsionale");
    expect(currentStepId("/analysis", "x")).toBe("indici");
    expect(currentStepId("/cashflow", "x")).toBe("rendiconto");
    expect(currentStepId("/report", "x")).toBe("report");
    expect(currentStepId("/budget", "x")).toBe("budget");
    expect(currentStepId("/", "x")).toBe("");
  });
});
```

- [ ] **Step 4: Eseguire i test e verificare che falliscano**

Run: `npm test`
Expected: FAIL — `pratica-steps.ts` non esporta ancora `nextStep`, `prevStep`, `phaseStatus`, `gateReason`, `praticaGates`, `currentStepId`, `firstEnabledStep`, e non conosce le fasi `dati` né il campo `group`.

- [ ] **Step 5: Riscrivere `frontend/lib/pratica-steps.ts`**

Sostituire l'intero file con:

```ts
import type { PraticaState } from "@/contexts/PraticaContext";

export type PraticaPhase = "dati" | "analisi" | "previsionale";

/** "azione" fa avanzare il percorso; "vista" è output di sola lettura. */
export type PraticaStepGroup = "azione" | "vista";

export const PHASE_ORDER: PraticaPhase[] = ["dati", "analisi", "previsionale"];

export const PHASE_LABELS: Record<PraticaPhase, string> = {
  dati: "Dati",
  analisi: "Analisi",
  previsionale: "Previsionale",
};

export interface PraticaStep {
  id: string;
  label: string;
  phase: PraticaPhase;
  group: PraticaStepGroup;
  /** "tab" = tab interna di /pratica; "route" = pagina Next a sé stante. */
  kind: "tab" | "route";
  route?: string;
  enabled: boolean;
}

/**
 * Condizioni di sblocco, calcolate da chi conosce i dati (il wizard o la
 * pagina che monta lo stepper) e passate qui già risolte in booleani.
 */
export interface PraticaGates {
  /** Esiste un bilancio importato per la pratica. */
  imported: boolean;
  /** Tutte le schede Rettifiche richieste sono state confermate. */
  rettificheOk: boolean;
  /** Il confronto è stato caricato. */
  comparisonReady: boolean;
  /** La proiezione è stata calcolata (solo periodo < 12 mesi). */
  projectionReady: boolean;
  /** Esiste lo scenario budget della pratica. */
  budgetScenario: boolean;
  /** Il previsionale è stato generato. */
  forecastReady: boolean;
}

export const ANALYSIS_STEP_IDS = [
  "anagrafiche",
  "import",
  "rettifiche",
  "comparison",
  "projection",
  "results",
  "stampa",
] as const;

/**
 * I gate derivati dal solo stato persistito della pratica. Unica definizione,
 * condivisa da stepper e barra azioni: due derivazioni parallele divergerebbero.
 */
export function praticaGates(pratica: PraticaState): PraticaGates {
  return {
    imported: pratica.fiscalYear !== null,
    // storico è true anche quando la scheda storico non esiste (import senza
    // anno di raffronto): è il wizard a scriverlo così.
    rettificheOk:
      pratica.rettificheConfirmed.verifica && pratica.rettificheConfirmed.storico,
    comparisonReady: pratica.infrannualeScenarioId !== null,
    projectionReady: pratica.infrannualeScenarioId !== null,
    budgetScenario: pratica.budgetScenarioId !== null,
    forecastReady: pratica.budgetScenarioId !== null,
  };
}

/**
 * Quale step è attivo, dedotto dalla rotta corrente (fasi su rotta) o dalla tab
 * del wizard (fase ANALISI dentro /pratica).
 */
export function currentStepId(pathname: string, analysisStep: string): string {
  if (pathname.startsWith("/pratica")) return analysisStep;
  if (pathname.startsWith("/forecast/balance")) return "sp-previsionale";
  if (pathname.startsWith("/forecast/reclassified")) return "riclassificato";
  if (pathname.startsWith("/forecast")) return "ce-previsionale";
  if (pathname.startsWith("/analysis")) return "indici";
  if (pathname.startsWith("/cashflow")) return "rendiconto";
  if (pathname.startsWith("/report")) return "report";
  if (pathname.startsWith("/budget")) return "budget";
  return "";
}

/**
 * Gli step della pratica, nell'ordine in cui vanno mostrati.
 *
 * Percorso "bilancio": fase DATI e fase ANALISI dentro /pratica, poi fase
 * PREVISIONALE su rotte reali. Lo step "projection" compare solo con periodo
 * < 12 mesi, perché un bilancio già annuale non va proiettato a 12 mesi.
 *
 * Percorso "startup": nessuna fase ANALISI (non c'è nulla da importare); lo
 * step "anagrafiche" è il form business plan su /budget.
 */
export function buildPraticaSteps(
  pratica: PraticaState,
  gates: PraticaGates,
): PraticaStep[] {
  const previsionale: PraticaStep[] = [
    {
      id: "budget",
      label: "Budget",
      phase: "previsionale",
      group: "azione",
      kind: "route",
      route: "/budget",
      enabled: pratica.workflow === "startup" ? true : gates.budgetScenario,
    },
    {
      id: "indici",
      label: "Indici",
      phase: "previsionale",
      group: "vista",
      kind: "route",
      route: "/analysis",
      enabled: gates.forecastReady,
    },
    {
      id: "ce-previsionale",
      label: "CE Prev.",
      phase: "previsionale",
      group: "vista",
      kind: "route",
      route: "/forecast/income",
      enabled: gates.forecastReady,
    },
    {
      id: "sp-previsionale",
      label: "SP Prev.",
      phase: "previsionale",
      group: "vista",
      kind: "route",
      route: "/forecast/balance",
      enabled: gates.forecastReady,
    },
    {
      id: "riclassificato",
      label: "Riclassificato",
      phase: "previsionale",
      group: "vista",
      kind: "route",
      route: "/forecast/reclassified",
      enabled: gates.forecastReady,
    },
    {
      id: "rendiconto",
      label: "Rendiconto",
      phase: "previsionale",
      group: "vista",
      kind: "route",
      route: "/cashflow",
      enabled: gates.forecastReady,
    },
    {
      id: "report",
      label: "Report",
      phase: "previsionale",
      group: "vista",
      kind: "route",
      route: "/report",
      enabled: gates.forecastReady,
    },
  ];

  if (pratica.workflow === "startup") {
    return [
      {
        id: "anagrafiche",
        label: "Anagrafiche",
        phase: "dati",
        group: "azione",
        kind: "route",
        route: "/budget",
        enabled: true,
      },
      ...previsionale,
    ];
  }

  // A pratica resumed from a LEGACY budget scenario (created before this
  // refactor, or otherwise never taken through the infrannuale wizard) has
  // `budgetScenarioId` set but `infrannualeScenarioId` null and stays null —
  // there is no rettifiche_log / adjustable FinancialYear to rehydrate the
  // wizard from, so the ANALISI phase can never actually work here (Rettifiche
  // dead-ends on "Pratica da riaprire"). This is NOT the same state as a brand
  // new pratica between Anagrafiche and Import, which also has
  // infrannualeScenarioId === null but budgetScenarioId === null too — those
  // early steps stay reachable. See FINDING 4, 2026-08-08 final review.
  const isLegacyBudgetResume =
    pratica.budgetScenarioId !== null && pratica.infrannualeScenarioId === null;

  if (isLegacyBudgetResume) {
    return previsionale;
  }

  const isAnnual = pratica.periodMonths === 12;

  const dati: PraticaStep[] = [
    { id: "anagrafiche", label: "Anagrafiche", phase: "dati", group: "azione", kind: "tab", enabled: true },
    { id: "import", label: "Import", phase: "dati", group: "azione", kind: "tab", enabled: pratica.companyId !== null },
    { id: "rettifiche", label: "Rettifiche", phase: "dati", group: "azione", kind: "tab", enabled: gates.imported },
  ];

  const analisi: PraticaStep[] = [
    {
      id: "comparison",
      label: "Confronto",
      phase: "analisi",
      group: "azione",
      kind: "tab",
      enabled: gates.imported && gates.rettificheOk,
    },
    ...(isAnnual
      ? []
      : [
          {
            id: "projection",
            label: "Proiezione",
            phase: "analisi" as const,
            group: "azione" as const,
            kind: "tab" as const,
            // Le rettifiche sono un prerequisito di tutto ciò che segue Confronto,
            // non solo di Confronto: senza questa AND uno scenario già creato
            // (infrannualeScenarioId valorizzato all'import) basterebbe da solo a
            // sbloccare Proiezione/Indicatori/Stampa anche a rettifiche non
            // confermate (o dopo un "Ripristina originale").
            enabled: gates.rettificheOk && gates.comparisonReady,
          },
        ]),
    {
      id: "results",
      label: "Indicatori",
      phase: "analisi",
      group: "vista",
      kind: "tab",
      enabled: gates.rettificheOk && gates.comparisonReady,
    },
    {
      id: "stampa",
      label: "Stampa",
      phase: "analisi",
      group: "vista",
      kind: "tab",
      enabled: gates.rettificheOk && (isAnnual ? gates.comparisonReady : gates.projectionReady),
    },
  ];

  return [...dati, ...analisi, ...previsionale];
}

/** Lo step immediatamente successivo nell'ordine, abilitato o no. */
export function nextStep(steps: PraticaStep[], currentId: string): PraticaStep | null {
  const i = steps.findIndex((s) => s.id === currentId);
  if (i < 0) return null;
  return steps[i + 1] ?? null;
}

/** Lo step immediatamente precedente nell'ordine, abilitato o no. */
export function prevStep(steps: PraticaStep[], currentId: string): PraticaStep | null {
  const i = steps.findIndex((s) => s.id === currentId);
  if (i <= 0) return null;
  return steps[i - 1] ?? null;
}

export function firstEnabledStep(
  steps: PraticaStep[],
  phase: PraticaPhase,
): PraticaStep | null {
  return steps.find((s) => s.phase === phase && s.enabled) ?? null;
}

export type PhaseStatus = "done" | "active" | "todo" | "locked";

/**
 * Stato del chip di fase. L'ordine di valutazione conta: "active" vince su
 * tutto (una fase può contenere lo step corrente pur avendo il resto bloccato),
 * "done" vince su "locked" (una fase superata non va mostrata come bloccata).
 */
export function phaseStatus(
  steps: PraticaStep[],
  phase: PraticaPhase,
  currentId: string,
): PhaseStatus {
  const own = steps.filter((s) => s.phase === phase);
  if (own.length === 0) return "locked";
  if (own.some((s) => s.id === currentId)) return "active";

  const currentPhase = steps.find((s) => s.id === currentId)?.phase;
  if (currentPhase && PHASE_ORDER.indexOf(phase) < PHASE_ORDER.indexOf(currentPhase)) {
    return "done";
  }
  if (!own.some((s) => s.enabled)) return "locked";
  return "todo";
}

/**
 * Perché questo step non è raggiungibile. Copre solo i motivi derivabili dai
 * gate: il motivo di un'azione registrata da una pagina (es. "2 schede da
 * confermare") lo fornisce la pagina stessa.
 */
export function gateReason(
  step: PraticaStep,
  gates: PraticaGates,
  pratica: PraticaState,
): string | null {
  if (step.enabled) return null;
  switch (step.id) {
    case "import":
      return "Completa prima l'anagrafica";
    case "rettifiche":
      return "Nessun bilancio importato";
    case "comparison":
      return gates.imported ? "Rettifiche non confermate" : "Nessun bilancio importato";
    case "projection":
    case "results":
      return gates.rettificheOk ? "Confronto non caricato" : "Rettifiche non confermate";
    case "stampa":
      if (!gates.rettificheOk) return "Rettifiche non confermate";
      return pratica.periodMonths === 12 ? "Confronto non caricato" : "Proiezione non calcolata";
    case "budget":
      return "Completa la Stampa per creare lo scenario budget";
    default:
      return "Previsionale non generato";
  }
}
```

- [ ] **Step 6: Eseguire i test e verificare che passino**

Run: `npm test`
Expected: PASS — tutti i `describe` verdi.

- [ ] **Step 7: Verificare che il progetto compili ancora**

Run: `npx tsc --noEmit`
Expected: errori SOLO in `components/PraticaStepper.tsx` (usa ancora le vecchie fasi `"analisi" | "previsionale"` come letterali e ridefinisce `currentStepId`/`gates` in locale). Sono attesi: li risolve il Task 2. Nessun altro file deve comparire.

- [ ] **Step 8: Commit**

```bash
cd frontend && git add package.json package-lock.json vitest.config.ts lib/pratica-steps.ts lib/pratica-steps.test.ts
git diff --cached --stat
git commit -m "feat(pratica): modello a fasi del percorso + test vitest

Tre fasi (dati/analisi/previsionale), gruppo azione/vista per step,
nextStep/prevStep/phaseStatus/firstEnabledStep/gateReason, e la
derivazione dei gate (praticaGates) e dello step corrente
(currentStepId) estratte dal componente per non duplicarle nella
barra azioni. Aggiunge /analysis come vista, oggi irraggiungibile
dentro una pratica."
```

---

### Task 2: Stepper a due livelli

**Files:**
- Modify: `frontend/components/PraticaStepper.tsx` (riscrittura completa)

**Interfaces:**
- Consumes: da Task 1 `buildPraticaSteps`, `praticaGates`, `currentStepId`, `phaseStatus`, `firstEnabledStep`, `gateReason`, `PHASE_ORDER`, `PHASE_LABELS`, `PraticaStep`, `PraticaPhase`.
- Produces: nessuna nuova API. `Navigation.tsx` continua a montarlo senza props.

- [ ] **Step 1: Verificare che il componente Tooltip di shadcn esista**

Run: `ls components/ui/tooltip.tsx`
Se manca: `npx shadcn@latest add tooltip`

- [ ] **Step 2: Riscrivere `frontend/components/PraticaStepper.tsx`**

```tsx
"use client";

import { usePathname, useRouter } from "next/navigation";
import { Check, LogOut } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useApp } from "@/contexts/AppContext";
import { usePratica } from "@/contexts/PraticaContext";
import {
  buildPraticaSteps,
  currentStepId,
  firstEnabledStep,
  gateReason,
  phaseStatus,
  praticaGates,
  PHASE_LABELS,
  PHASE_ORDER,
  type PraticaPhase,
  type PraticaStep,
} from "@/lib/pratica-steps";

export function PraticaStepper() {
  const pathname = usePathname();
  const router = useRouter();
  const { companies } = useApp();
  const { pratica, setAnalysisStep, exitPratica } = usePratica();

  // La home è la pagina di uscita: là comanda la nav normale.
  if (!pratica || pathname === "/") return null;

  const gates = praticaGates(pratica);
  const steps = buildPraticaSteps(pratica, gates);
  const active = currentStepId(pathname, pratica.analysisStep);
  const activePhase: PraticaPhase =
    steps.find((s) => s.id === active)?.phase ?? steps[0]?.phase ?? "dati";

  const go = (step: PraticaStep) => {
    if (!step.enabled) return;
    if (step.kind === "tab") {
      setAnalysisStep(step.id);
      if (!pathname.startsWith("/pratica")) router.push("/pratica");
      return;
    }
    if (step.route) router.push(step.route);
  };

  const company = companies.find((c) => c.id === pratica.companyId);
  const periodo =
    pratica.fiscalYear === null
      ? null
      : pratica.periodMonths !== null && pratica.periodMonths < 12
      ? `Bil. di verifica ${pratica.periodMonths}M ${pratica.fiscalYear}`
      : `Bilancio ${pratica.fiscalYear}`;

  const phaseSteps = steps.filter((s) => s.phase === activePhase);
  const azioni = phaseSteps.filter((s) => s.group === "azione");
  const viste = phaseSteps.filter((s) => s.group === "vista");

  return (
    <TooltipProvider delayDuration={200}>
      <div className="border-b border-border bg-background print:hidden">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          {/* Riga 1: identità della pratica, fasi, uscita */}
          <div className="flex items-center gap-4 py-2">
            <div className="min-w-0 shrink">
              <p className="truncate text-sm font-semibold text-foreground">
                {company?.name ?? "Nuova pratica"}
              </p>
              {periodo && (
                <p className="truncate text-xs text-muted-foreground">{periodo}</p>
              )}
            </div>

            <nav className="flex items-center gap-1 overflow-x-auto" aria-label="Fasi della pratica">
              {PHASE_ORDER.map((phase, i) => {
                const own = steps.filter((s) => s.phase === phase);
                if (own.length === 0) return null;
                const status = phaseStatus(steps, phase, active);
                const target = firstEnabledStep(steps, phase);
                const locked = status === "locked" || target === null;
                const reason = locked && own[0] ? gateReason(own[0], gates, pratica) : null;

                const chip = (
                  <button
                    onClick={() => target && go(target)}
                    disabled={locked}
                    aria-current={status === "active" ? "step" : undefined}
                    className={cn(
                      "flex shrink-0 items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-wide transition-colors",
                      status === "active" && "bg-primary text-primary-foreground",
                      status === "done" && "text-foreground hover:bg-muted",
                      status === "todo" && "text-muted-foreground hover:bg-muted",
                      locked && "text-muted-foreground/40 cursor-not-allowed",
                    )}
                  >
                    {status === "done" ? (
                      <Check className="h-3 w-3" />
                    ) : (
                      <span
                        className={cn(
                          "h-2 w-2 rounded-full border",
                          status === "active"
                            ? "border-primary-foreground bg-primary-foreground"
                            : "border-current",
                        )}
                      />
                    )}
                    {i + 1} {PHASE_LABELS[phase]}
                  </button>
                );

                return (
                  <div key={phase} className="flex items-center gap-1">
                    {i > 0 && <span className="h-px w-4 shrink-0 bg-border" />}
                    {reason ? (
                      <Tooltip>
                        {/* span: un button disabilitato non emette eventi puntatore */}
                        <TooltipTrigger asChild><span>{chip}</span></TooltipTrigger>
                        <TooltipContent>{reason}</TooltipContent>
                      </Tooltip>
                    ) : (
                      chip
                    )}
                  </div>
                );
              })}
            </nav>

            <span className="flex-1" />
            <Button
              variant="ghost"
              size="sm"
              className="shrink-0 text-muted-foreground"
              onClick={() => {
                exitPratica();
                router.push("/");
              }}
            >
              <LogOut className="h-4 w-4 mr-1" /> Esci dalla pratica
            </Button>
          </div>

          {/* Riga 2: gli step della sola fase attiva, azioni ┊ viste */}
          <nav
            className="flex items-center gap-1 overflow-x-auto"
            aria-label={`Passaggi: ${PHASE_LABELS[activePhase]}`}
          >
            {azioni.map((step) => (
              <StepTab key={step.id} step={step} active={active === step.id} onClick={() => go(step)} />
            ))}
            {azioni.length > 0 && viste.length > 0 && (
              <span className="mx-2 h-5 w-px shrink-0 bg-border" aria-hidden />
            )}
            {viste.map((step) => (
              <StepTab key={step.id} step={step} active={active === step.id} onClick={() => go(step)} />
            ))}
          </nav>
        </div>
      </div>
    </TooltipProvider>
  );
}

function StepTab({
  step,
  active,
  onClick,
}: {
  step: PraticaStep;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      disabled={!step.enabled}
      aria-current={active ? "page" : undefined}
      className={cn(
        "flex items-center gap-1.5 whitespace-nowrap border-b-2 px-3 py-2.5 text-sm font-medium transition-colors",
        active
          ? "border-primary text-foreground"
          : step.enabled
          ? "border-transparent text-muted-foreground hover:text-foreground hover:border-border"
          : "border-transparent text-muted-foreground/40 cursor-not-allowed",
      )}
    >
      {step.label}
    </button>
  );
}
```

- [ ] **Step 3: Verificare la compilazione**

Run: `npx tsc --noEmit && npm run lint`
Expected: nessun errore.

- [ ] **Step 4: Verifica visiva nel browser**

Avviare backend e frontend (dalla root del progetto, due terminali):
```bash
cd backend && source venv/bin/activate && DEV_USER_ID=dev-user-001 uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
cd frontend && npm run dev
```
Aprire `http://localhost:3000`, avviare una pratica "Da bilancio" e verificare:
- la barra mostra **3 chip di fase** e, sotto, **solo gli step della fase attiva** (all'inizio: Anagrafiche · Import · Rettifiche);
- il chip PREVISIONALE è grigio e non cliccabile, e il suo tooltip dice "Completa la Stampa per creare lo scenario budget";
- dopo l'import, il chip DATI mostra la spunta quando ci si sposta in ANALISI;
- il separatore `│` verticale compare in ANALISI fra Proiezione e Indicatori.

- [ ] **Step 5: Commit**

```bash
cd frontend && git add components/PraticaStepper.tsx
git diff --cached --stat
git commit -m "feat(pratica): stepper a due livelli, fasi + sotto-barra

Chip di fase (active/done/todo/locked con tooltip del motivo) e
sotto-barra della sola fase attiva, con separatore fra azioni e viste.
Aggiunge l'identita' della pratica (ragione sociale e periodo), finora
assente sia dallo stepper sia dall'AppHeader."
```

---

### Task 3: Barra azioni e registro delle azioni

**Files:**
- Create: `frontend/contexts/PraticaActionContext.tsx`
- Create: `frontend/components/pratica/PraticaActionBar.tsx`
- Modify: `frontend/app/layout.tsx`

**Interfaces:**
- Consumes: da Task 1 `buildPraticaSteps`, `praticaGates`, `currentStepId`, `nextStep`, `prevStep`, `firstEnabledStep`, `gateReason`.
- Produces: `usePrimaryAction({ label: string; onClick: () => void | Promise<void>; disabled?: boolean; reason?: string | null }): void` — hook che i Task 4/5/6 usano in ogni pagina-step. `PraticaActionProvider` e `PraticaActionBar` come componenti.

- [ ] **Step 1: Creare `frontend/contexts/PraticaActionContext.tsx`**

```tsx
"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

/** Ciò che la barra deve DISEGNARE: solo primitivi, così l'identità è stabile. */
export interface PrimaryActionView {
  label: string;
  disabled: boolean;
  reason: string | null;
}

interface PraticaActionContextType {
  action: PrimaryActionView | null;
  runAction: () => void;
  register: (token: symbol, view: PrimaryActionView, run: () => void) => void;
  unregister: (token: symbol) => void;
}

const PraticaActionContext = createContext<PraticaActionContextType | undefined>(
  undefined,
);

export function PraticaActionProvider({ children }: { children: React.ReactNode }) {
  const [action, setAction] = useState<PrimaryActionView | null>(null);
  const runRef = useRef<(() => void) | null>(null);
  // Chi possiede l'azione ora. Un cambio pagina può smontare il vecchio step
  // DOPO che il nuovo si è registrato: senza token, la cleanup del vecchio
  // cancellerebbe l'azione appena registrata dal nuovo.
  const ownerRef = useRef<symbol | null>(null);

  const register = useCallback(
    (token: symbol, view: PrimaryActionView, run: () => void) => {
      ownerRef.current = token;
      runRef.current = run;
      setAction((prev) =>
        prev &&
        prev.label === view.label &&
        prev.disabled === view.disabled &&
        prev.reason === view.reason
          ? prev // stessa vista: nessun re-render inutile
          : view,
      );
    },
    [],
  );

  const unregister = useCallback((token: symbol) => {
    if (ownerRef.current !== token) return;
    ownerRef.current = null;
    runRef.current = null;
    setAction(null);
  }, []);

  const runAction = useCallback(() => {
    runRef.current?.();
  }, []);

  const value = useMemo<PraticaActionContextType>(
    () => ({ action, runAction, register, unregister }),
    [action, runAction, register, unregister],
  );

  return (
    <PraticaActionContext.Provider value={value}>{children}</PraticaActionContext.Provider>
  );
}

export function usePraticaAction() {
  const ctx = useContext(PraticaActionContext);
  if (ctx === undefined) {
    throw new Error("usePraticaAction deve essere usato dentro un PraticaActionProvider");
  }
  return ctx;
}

/**
 * Registra l'azione primaria dello step corrente nella barra in basso.
 *
 * `onClick` è tenuto in un ref aggiornato a ogni render e NON è una dipendenza
 * dell'effetto: passare l'handler (una funzione nuova a ogni render) come
 * dipendenza rifarebbe partire la registrazione a ogni ciclo. Stessa ragione
 * per cui `use-rettifiche-year` non va mai messo intero in un dependency array.
 */
export function usePrimaryAction(opts: {
  /** `null` = questo step non ha un'azione propria: la barra usa il fallback. */
  label: string | null;
  onClick: () => void | Promise<void>;
  disabled?: boolean;
  reason?: string | null;
}) {
  const { register, unregister } = usePraticaAction();
  const { label, disabled = false, reason = null } = opts;

  const onClickRef = useRef(opts.onClick);
  onClickRef.current = opts.onClick;

  const tokenRef = useRef<symbol | null>(null);
  if (tokenRef.current === null) tokenRef.current = Symbol("primary-action");
  const token = tokenRef.current;

  useEffect(() => {
    if (label === null) return;
    register(token, { label, disabled, reason }, () => {
      void onClickRef.current();
    });
    return () => unregister(token);
  }, [token, label, disabled, reason, register, unregister]);
}
```

**Perché `label: null` serve fin da subito.** `app/pratica/page.tsx` rende tutte le tab del
wizard come rami JSX di **un unico** componente (`InfraannualePage`, righe 2919-4512): un hook
non può stare in un ramo condizionale, quindi ci sarà **una sola** registrazione che seleziona
su `activeTab` e deve poter dire "per questa tab nessuna azione" (Task 4 e 5). Serve anche a
non far litigare quella registrazione con `StampaContent`, che è un componente a sé e registra
la propria: React esegue gli effetti dei figli PRIMA di quelli del padre, quindi sulla tab
Stampa il figlio registra e il padre — con `label: null` — non sovrascrive.

- [ ] **Step 2: Creare `frontend/components/pratica/PraticaActionBar.tsx`**

```tsx
"use client";

import { usePathname, useRouter } from "next/navigation";
import { ArrowLeft, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { usePratica } from "@/contexts/PraticaContext";
import { usePraticaAction } from "@/contexts/PraticaActionContext";
import {
  buildPraticaSteps,
  currentStepId,
  firstEnabledStep,
  gateReason,
  nextStep,
  praticaGates,
  prevStep,
  type PraticaStep,
} from "@/lib/pratica-steps";

export function PraticaActionBar() {
  const pathname = usePathname();
  const router = useRouter();
  const { pratica, setAnalysisStep, exitPratica } = usePratica();
  const { action, runAction } = usePraticaAction();

  if (!pratica || pathname === "/") return null;

  const gates = praticaGates(pratica);
  const steps = buildPraticaSteps(pratica, gates);
  const currentId = currentStepId(pathname, pratica.analysisStep);
  const current = steps.find((s) => s.id === currentId) ?? null;

  const go = (step: PraticaStep) => {
    if (!step.enabled) return;
    if (step.kind === "tab") {
      setAnalysisStep(step.id);
      if (!pathname.startsWith("/pratica")) router.push("/pratica");
      return;
    }
    if (step.route) router.push(step.route);
  };

  const back = prevStep(steps, currentId);
  const next = nextStep(steps, currentId);

  // Cosa mostra il bottone primario, in ordine di precedenza.
  let label: string;
  let disabled: boolean;
  let reason: string | null;
  let run: () => void;

  const rescue = current && !current.enabled ? firstEnabledStep(steps, current.phase) : null;

  if (rescue) {
    // Lo step corrente non è (più) raggiungibile: può succedere rientrando su
    // un analysisStep persistito dopo un "Ripristina originale". Non si propone
    // un avanzamento da uno step morto, si torna indietro.
    label = `Torna a ${rescue.label}`;
    disabled = false;
    reason = "Questo passaggio non è più disponibile";
    run = () => go(rescue);
  } else if (action) {
    label = action.label;
    disabled = action.disabled;
    reason = action.reason;
    run = runAction;
  } else if (next) {
    label = `Avanti: ${next.label}`;
    disabled = !next.enabled;
    reason = gateReason(next, gates, pratica);
    run = () => go(next);
  } else {
    label = "Chiudi la pratica";
    disabled = false;
    reason = null;
    run = () => {
      exitPratica();
      router.push("/");
    };
  }

  return (
    // sticky (non fixed): resta in flusso, quindi non copre mai l'ultima riga
    // delle tabelle lunghe e non serve compensare con padding sul contenuto.
    <div className="sticky bottom-0 z-30 border-t border-border bg-background/95 backdrop-blur print:hidden">
      <div className="max-w-7xl mx-auto flex items-center gap-4 px-4 py-3 sm:px-6 lg:px-8">
        {back ? (
          <Button variant="ghost" size="sm" disabled={!back.enabled} onClick={() => go(back)}>
            <ArrowLeft className="h-4 w-4 mr-1" />
            {back.label}
          </Button>
        ) : (
          <span />
        )}
        <span className="flex-1" />
        {disabled && reason && (
          <p className="truncate text-sm text-muted-foreground">{reason}</p>
        )}
        <Button onClick={run} disabled={disabled}>
          {label}
          <ArrowRight className="h-4 w-4 ml-2" />
        </Button>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Montare provider e barra in `frontend/app/layout.tsx`**

Aggiungere gli import accanto a quelli esistenti:
```tsx
import { PraticaActionProvider } from "@/contexts/PraticaActionContext";
import { PraticaActionBar } from "@/components/pratica/PraticaActionBar";
```

Sostituire il blocco `<AppProvider> … </AppProvider>` (righe 34-54 attuali) con:
```tsx
          <AppProvider>
          <PraticaActionProvider>
            <div className="min-h-screen flex flex-col bg-background print:bg-white">
              {/* Header */}
              <div className="print:hidden">
                <AppHeader />
              </div>

              {/* Navigation */}
              <div className="print:hidden">
                <Navigation />
              </div>

              {/* Main Content */}
              <main className="flex-1">
                {children}
              </main>

              {/* Barra azioni della pratica (null fuori da una pratica) */}
              <PraticaActionBar />
            </div>
            <div className="print:hidden">
              <Toaster />
            </div>
          </PraticaActionProvider>
          </AppProvider>
```

- [ ] **Step 4: Verificare la compilazione**

Run: `npx tsc --noEmit && npm run lint && npm test`
Expected: nessun errore, test di Task 1 ancora verdi.

- [ ] **Step 5: Verifica visiva del fallback**

Con backend e frontend attivi, riaprire una pratica che ha già un previsionale generato e navigare alle viste della fase PREVISIONALE:
- su `/forecast/income` la barra in basso mostra `‹ Budget` a sinistra e `Avanti: SP Prev. ›` a destra;
- su `/report` il primario diventa `Chiudi la pratica` e riporta alla home svuotando la pratica;
- fuori da una pratica (home, o dopo l'uscita) la barra **non** compare;
- scorrendo una tabella lunga la barra resta visibile in basso e l'ultima riga della tabella resta leggibile.

- [ ] **Step 6: Commit**

```bash
cd frontend && git add contexts/PraticaActionContext.tsx components/pratica/PraticaActionBar.tsx app/layout.tsx
git diff --cached --stat
git commit -m "feat(pratica): barra azioni unica con registro delle azioni

Un solo punto decide l'avanzamento: azione registrata dalla pagina,
altrimenti fallback di navigazione allo step successivo (disabilitato
col motivo se il gate non e' soddisfatto). Le 6 viste di sola lettura
non richiedono modifiche. La registrazione tiene l'handler in un ref e
dipende solo dai primitivi, per non rientrare in ciclo."
```

---

### Task 4: Migrazione della fase DATI

**Files:**
- Modify: `frontend/components/pratica/AnagraficheStep.tsx:83-93` (ref → stato) e `:172-185` (rimozione bottone)
- Modify: `frontend/app/pratica/page.tsx:4020-4026` (CTA Import) e `:4149-4168` (CTA Rettifiche)

**Interfaces:**
- Consumes: `usePrimaryAction` da Task 3.
- Produces: niente per i task successivi.

- [ ] **Step 1: In `AnagraficheStep.tsx`, affiancare uno stato al ref `seededFor`**

Il `disabled` del bottone legge `seededFor.current` durante il render: funziona oggi solo perché la semina aggiorna anche altri stati, ma un ref non è una dipendenza valida per l'effetto di registrazione. Aggiungere uno stato accanto al ref (il ref resta: serve alla guardia "semina una sola volta").

Dopo la dichiarazione `const seededFor = useRef<number | null>(null);` aggiungere:
```tsx
  // Copia in stato del ref qui sopra: il ref guida la semina, questo stato
  // guida ciò che la UI può abilitare (un ref non fa ri-renderizzare né vale
  // come dipendenza dell'effetto che registra l'azione primaria).
  const [seededId, setSeededId] = useState<number | null>(null);
```

Dentro l'effetto di semina, ovunque venga eseguito `seededFor.current = <valore>`, aggiungere subito sotto `setSeededId(<stesso valore>);` — inclusa la riga `seededFor.current = null;` del ramo `praticaCompanyId === null`, che diventa `setSeededId(null);`.

- [ ] **Step 2: Sostituire il bottone di `AnagraficheStep` con la registrazione**

Aggiungere l'import:
```tsx
import { usePrimaryAction } from "@/contexts/PraticaActionContext";
```

Prima del `return`, registrare l'azione con la STESSA condizione di disabilitazione del bottone attuale:
```tsx
  // In EDIT mode (praticaCompanyId set) il form non deve essere inviabile
  // finché la semina non è atterrata — altrimenti un click in quella finestra
  // manda sector=1 (lo stato locale ancora di default) e azzera silenziosamente
  // il settore Altman/FGPMI dell'azienda (FINDING 6, review 2026-08-08).
  const notSeeded = praticaCompanyId !== null && seededId !== praticaCompanyId;
  usePrimaryAction({
    label: "Salva e prosegui",
    onClick: handleSave,
    disabled: saving || notSeeded,
    reason: notSeeded ? "Caricamento dati azienda in corso" : null,
  });
```

Rimuovere l'intero blocco `<div className="flex justify-end"> … </div>` che contiene il bottone "Salva e prosegui" (righe 172-185), e ripulire gli import `Button`/`ArrowRight`/`Loader2` se non più usati altrove nel file (verificare con `grep -n "Loader2\|ArrowRight\|<Button" components/pratica/AnagraficheStep.tsx`).

- [ ] **Step 3: Migrare il CTA dello step Import**

In `app/pratica/page.tsx`, rimuovere il bottone "Vai alle Rettifiche" (righe ~4020-4026):
```tsx
                  <Button
                    className="mt-3"
                    onClick={() => setActiveTab("rettifiche")}
                  >
                    Vai alle Rettifiche
                    <ArrowRight className="h-4 w-4 ml-2" />
                  </Button>
```
Non serve registrare nulla: il fallback della barra produce già `Avanti: Rettifiche`, abilitato esattamente quando `gates.imported` è vero.

- [ ] **Step 4: Introdurre la registrazione unificata in `InfraannualePage` (caso Rettifiche)**

Le tab del wizard sono rami JSX di un unico componente (`InfraannualePage`, righe 2919-4512):
gli hook non possono stare nei rami, quindi la registrazione è **una sola** e seleziona su
`activeTab`. Questo task ne crea lo scheletro con il solo caso `"rettifiche"`; il Task 5 vi
aggiunge `"comparison"` e `"projection"`.

Aggiungere l'import `import { usePrimaryAction } from "@/contexts/PraticaActionContext";` e,
nel corpo di `InfraannualePage` dopo la definizione di `allRettificheConfirmed` e di
`handleConfirmRettifiche`:

```tsx
  const rettificheDaConfermare =
    (verifica.exists && !verifica.confirmed ? 1 : 0) +
    (storico.exists && !storico.confirmed ? 1 : 0);

  // Le condizioni sono copiate INVARIATE dal bottone che questo sostituisce
  // (era app/pratica/page.tsx:4155-4167).
  const rettificheDisabled =
    verifica.saving ||
    storico.saving ||
    verifica.loading ||
    storico.loading ||
    !verifica.exists ||
    allRettificheConfirmed;

  // Unica registrazione per tutte le tab: `null` lascia il fallback di
  // navigazione alla barra (Import, Indicatori) o l'azione al componente
  // figlio (Stampa → StampaContent).
  const primary = useMemo<{
    label: string | null;
    onClick: () => void | Promise<void>;
    disabled: boolean;
    reason: string | null;
  }>(() => {
    switch (activeTab) {
      case "rettifiche":
        // Già confermate: l'azione diventa navigazione, altrimenti il primario
        // resterebbe disabilitato per sempre (vedi la nota in fondo al passo).
        if (allRettificheConfirmed) {
          return {
            label: "Vai al Confronto",
            onClick: () => setActiveTab("comparison"),
            disabled: false,
            reason: null,
          };
        }
        return {
          label: "Conferma e vai al Confronto",
          onClick: handleConfirmRettifiche,
          disabled: rettificheDisabled,
          reason: !verifica.exists
            ? "Bilancio di verifica non caricato"
            : verifica.saving || storico.saving
            ? "Salvataggio in corso"
            : verifica.loading || storico.loading
            ? "Caricamento in corso"
            : null,
        };
      default:
        return { label: null, onClick: () => {}, disabled: false, reason: null };
    }
  }, [
    activeTab,
    setActiveTab,
    handleConfirmRettifiche,
    rettificheDisabled,
    allRettificheConfirmed,
    verifica.exists,
    verifica.saving,
    verifica.loading,
    storico.saving,
    storico.loading,
  ]);

  usePrimaryAction(primary);
```

Poi sostituire il blocco `<div className="mt-6 flex items-center justify-between gap-4 …>` (righe 4149-4168) con il solo testo informativo, senza bottone:
```tsx
        <div className="mt-6 rounded-lg border border-border bg-card p-4">
          <p className="text-sm text-muted-foreground">
            {allRettificheConfirmed
              ? "Rettifiche confermate. Puoi proseguire con il confronto."
              : `Conferma le rettifiche per sbloccare gli step successivi (${rettificheDaConfermare} ${
                  rettificheDaConfermare === 1 ? "scheda" : "schede"
                } da confermare). Se il bilancio non quadra puoi confermare lo stesso: l'avviso resta.`}
          </p>
        </div>
```

**Attenzione:** `allRettificheConfirmed` resta il gate reale — non toccarlo. Ma a rettifiche
già confermate un primario perennemente disabilitato sarebbe un vicolo cieco (il fallback non
subentra: un'azione registrata ha sempre la precedenza). Il `case "rettifiche"` deve quindi
avere due forme, distinte proprio su quel flag:

```tsx
      case "rettifiche":
        if (allRettificheConfirmed) {
          return {
            label: "Vai al Confronto",
            onClick: () => setActiveTab("comparison"),
            disabled: false,
            reason: null,
          };
        }
        return { /* la forma con handleConfirmRettifiche scritta sopra */ };
```

Con questo, `"Rettifiche già confermate"` non è più un `reason` raggiungibile: toglierlo dalla
catena dei ternari e lasciare `!verifica.exists` / salvataggio / caricamento.

- [ ] **Step 5: Verificare compilazione e lint**

Run: `npx tsc --noEmit && npm run lint && npm test`
Expected: nessun errore.

- [ ] **Step 6: Verifica nel browser della fase DATI**

Avviare una pratica nuova "Da bilancio":
- **Anagrafiche:** dentro la card non c'è più alcun bottone; la barra in basso mostra "Salva e prosegui", disabilitato con "Caricamento dati azienda in corso" mentre l'anagrafica di una pratica esistente si carica; salvando si passa a Import.
- **Import:** dopo un import riuscito, la barra mostra "Avanti: Rettifiche" abilitato; prima dell'import è disabilitato con "Nessun bilancio importato".
- **Rettifiche:** la barra mostra "Conferma e vai al Confronto"; con due schede il testo nella card dice "2 schede da confermare"; su un import senza anno di raffronto dice "1 scheda"; a rettifiche confermate il primario diventa "Vai al Confronto" e la tab Confronto è cliccabile.
- **Caso di regressione da controllare esplicitamente:** riaprire una pratica esistente su Anagrafiche e salvare senza toccare nulla — il settore dell'azienda NON deve tornare a 1.

- [ ] **Step 7: Commit**

```bash
cd frontend && git add components/pratica/AnagraficheStep.tsx app/pratica/page.tsx
git diff --stat
git commit -m "feat(pratica): fase DATI sulla barra azioni

Anagrafiche/Import/Rettifiche perdono i CTA inline a favore della barra
unica. In AnagraficheStep il guard anti-reset del settore passa da ref a
stato: un ref non fa ri-renderizzare e non vale come dipendenza
dell'effetto di registrazione."
```

---

### Task 5: Migrazione della fase ANALISI

**Files:**
- Modify: `frontend/app/pratica/page.tsx:4279-4291` (CTA Confronto), `:4365-4379` (CTA Proiezione), `~:5545-5600` (CTA promote dentro `StampaContent`)

**Interfaces:**
- Consumes: `usePrimaryAction` da Task 3.
- Produces: niente per i task successivi.

- [ ] **Step 1: Estrarre l'handler del Confronto e aggiungere i due casi allo switch**

Estrarre in un `useCallback`, nel corpo di `InfraannualePage`, l'handler oggi inline nel
bottone alle righe 4280-4287 — **senza cambiarne una riga di logica**:

```tsx
  const goFromComparison = useCallback(async () => {
    if (periodMonths === 12) {
      await saveProjection12M();
      setActiveTab("results");
    } else {
      setActiveTab("projection");
    }
  }, [periodMonths, saveProjection12M, setActiveTab]);
```

Poi aggiungere due `case` allo `switch (activeTab)` creato nel Task 4, **prima** del `default`:

```tsx
      case "comparison":
        return {
          label: periodMonths === 12 ? "Vai agli Indicatori" : "Vai alla Proiezione",
          onClick: goFromComparison,
          disabled: !comparison,
          reason: !comparison ? "Confronto non ancora caricato" : null,
        };
      case "projection":
        // Stessa condizione del bottone "Indicatori" che sostituisce
        // (era app/pratica/page.tsx:4373-4375).
        return {
          label: "Vai agli Indicatori",
          onClick: () => setActiveTab("results"),
          disabled: !projectedBS,
          reason: !projectedBS ? "Proiezione non ancora calcolata" : null,
        };
```

e aggiungere alle dipendenze del `useMemo`: `periodMonths`, `comparison`, `projectedBS`,
`goFromComparison`, `setActiveTab`.

Rimuovere il blocco `<div className="flex justify-end"> … </div>` con il bottone
"Vai alla Proiezione / Vai agli Indicatori" (righe 4279-4291).

- [ ] **Step 2: Migrare il CTA della Proiezione**

Rimuovere il blocco `<div className="flex justify-between"> … </div>` (righe ~4365-4379) contenente "Torna al Confronto" e "Indicatori": il "Torna al Confronto" è già coperto dal bottone Indietro della barra, e "Indicatori" dalla registrazione `case "projection"` sopra (stessa condizione `disabled={!projectedBS}`).

- [ ] **Step 3: Migrare il CTA "Prosegui al Budget" in `StampaContent`**

`StampaContent` è un componente a sé: qui la registrazione va nel suo corpo. Estrarre l'handler inline del bottone (righe ~5546-5590) in un `useCallback` chiamato `handlePromote`, **senza modificarne una riga di logica**, poi:

```tsx
  // Il bottone era reso solo dentro `{companyId && scenarioId && (…)}`
  // (app/pratica/page.tsx:5544): la condizione si conserva come label null.
  usePrimaryAction({
    label: companyId !== null && scenarioId !== null ? "Prosegui al Budget" : null,
    onClick: handlePromote,
    disabled: promoting,
    reason: promoting ? "Creazione dello scenario budget in corso" : null,
  });
```

Rimuovere il blocco `{companyId && scenarioId && (<Button …>Prosegui al Budget</Button>)}`
(righe 5544-5600). **Non toccare** i due bottoni fratelli nello stesso `<div>` — "Genera
commenti AI" e "Stampa PDF": sono azioni secondarie della tab, non l'avanzamento del percorso,
e restano dove sono.

- [ ] **Step 4: Verificare compilazione e lint**

Run: `npx tsc --noEmit && npm run lint && npm test`
Expected: nessun errore.

- [ ] **Step 5: Verifica nel browser della fase ANALISI**

Su una pratica con bilancio infrannuale (9M) e su una con bilancio annuale (12M):
- **Confronto:** la barra propone "Vai alla Proiezione" a 9M e "Vai agli Indicatori" a 12M; a 12M il salto scrive comunque la proiezione (`saveProjection12M`) prima di cambiare tab.
- **Proiezione:** primario "Vai agli Indicatori" disabilitato finché la proiezione non è calcolata; il bottone Indietro riporta al Confronto.
- **Indicatori:** nessuna azione registrata → fallback "Avanti: Stampa".
- **Stampa:** primario "Prosegui al Budget"; durante la promozione è disabilitato con "Creazione dello scenario budget in corso"; al termine si atterra su `/budget` e il chip PREVISIONALE è ora attivo.

- [ ] **Step 6: Commit**

```bash
cd frontend && git add app/pratica/page.tsx contexts/PraticaActionContext.tsx
git diff --stat
git commit -m "feat(pratica): fase ANALISI sulla barra azioni

Confronto, Proiezione e la promozione al Budget passano dalla barra
unica; Indicatori usa il fallback di navigazione. Le condizioni di
disabilitazione sono trasferite invariate."
```

---

### Task 6: Migrazione della fase PREVISIONALE e chiusura

**Files:**
- Modify: `frontend/app/budget/page.tsx:1299-1304`
- Modify: `frontend/components/Navigation.tsx:53-56` (commento ormai falso)

**Interfaces:**
- Consumes: `usePrimaryAction` da Task 3.
- Produces: nessuna.

- [ ] **Step 1: Registrare l'azione della pagina Budget**

`/budget` è raggiungibile **anche fuori da una pratica** (voce "Scenari" della nav piatta,
`components/Navigation.tsx:29`), e lì la barra azioni non viene renderizzata. Il bottone inline
va quindi conservato per quel caso, non rimosso: si registra l'azione **e** si rende il bottone
solo senza pratica attiva.

In `app/budget/page.tsx`, aggiungere gli import:
```tsx
import { usePratica } from "@/contexts/PraticaContext";
import { usePrimaryAction } from "@/contexts/PraticaActionContext";
```

Nel corpo del componente che possiede `handleSave` e `loading`:
```tsx
  const { pratica } = usePratica();

  // Dentro una pratica l'avanzamento passa dalla barra unica; fuori (nav
  // piatta → Scenari) la barra non esiste e resta il bottone inline.
  usePrimaryAction({
    label: pratica ? "Salva e Calcola Previsionale" : null,
    onClick: handleSave,
    disabled: loading,
    reason: loading ? "Calcolo in corso" : null,
  });
```

Rendere condizionale il bottone alle righe 1299-1304:
```tsx
        {!pratica && (
          <Button onClick={handleSave} disabled={loading}>
            {/* contenuto invariato */}
          </Button>
        )}
```
**Non toccare** il bottone "Ricalcola" né il dialog associato: è un'azione secondaria distinta (con l'opzione di azzerare le modifiche manuali al CE) e resta dov'è.

- [ ] **Step 2: Correggere il commento obsoleto in `Navigation.tsx`**

Le righe 53-56 dicono che `/infrannuale` ospita ancora il wizard con la sua barra interna.
Non è più vero: `app/infrannuale/page.tsx` è un `redirect("/pratica")` di cinque righe,
verificato durante la stesura di questo piano. Il commento manda fuori strada e la guardia è
morta (quel path non renderizza mai nulla). Sostituire entrambi — righe 53-56, dal commento
fino a `if (pathname.startsWith("/infrannuale")) return null;` incluso — con:
```tsx
  // /infrannuale è solo un redirect verso /pratica: nessuna barra da sopprimere.
```

- [ ] **Step 3: Verificare compilazione, lint e test**

Run: `npx tsc --noEmit && npm run lint && npm test && npm run build`
Expected: build completata senza errori.

- [ ] **Step 4: Verifica end-to-end dei quattro percorsi**

1. **Bilancio 9M:** pratica nuova → Anagrafiche → Import (PDF infrannuale) → Rettifiche (entrambe le schede) → Confronto → Proiezione → Indicatori → Stampa → Budget → Salva e Calcola → le 6 viste previsionali fino a "Chiudi la pratica".
2. **Bilancio 12M:** stesso giro; verificare che lo step Proiezione non compaia MAI nella sotto-barra e che il Confronto porti agli Indicatori.
3. **Startup:** dalla home, card Startup → 2 soli chip di fase (Dati, Previsionale), Anagrafiche è la pagina `/budget`.
4. **Pratica legacy:** riaprire dalla home una pratica con solo `budgetScenarioId` → 1 solo chip (Previsionale), nessuna fase ANALISI.
5. **Fuori pratica:** dalla home senza pratica attiva, la nav piatta è intatta e non c'è alcuna barra in basso.
6. **Stampa:** su `/report` e sulla tab Stampa, `Ctrl+P` — né stepper né barra azioni compaiono nell'anteprima.

- [ ] **Step 5: Aggiornare CLAUDE.md**

Nella sezione "Il percorso unico Pratica", sostituire la descrizione della barra piatta con il modello a fasi: tre fasi (`dati`/`analisi`/`previsionale`), gruppo `azione`/`vista`, `/analysis` aggiunta come vista, e la barra azioni come unico punto di avanzamento. Segnalare che il residuo "il gate è applicato in navigazione, non al render" è ora coperto per l'avanzamento (un solo punto decide), mentre le render guard del wizard restano invariate.

- [ ] **Step 6: Commit**

```bash
cd frontend && git add app/budget/page.tsx components/Navigation.tsx ../CLAUDE.md
git diff --stat
git commit -m "feat(pratica): fase PREVISIONALE sulla barra azioni + doc

Il Budget registra 'Salva e Calcola Previsionale' sulla barra unica; le
cinque viste usano il fallback di navigazione. Aggiorna CLAUDE.md al
modello a fasi."
```

---

## Note per chi esegue

- **Il rischio numero uno è la migrazione dei CTA.** Ogni `disabled` va copiato carattere per carattere dal bottone che si rimuove. Se una condizione dipende da un `useRef`, va prima promossa a stato (come in Task 4, Step 1): un ref non fa ri-renderizzare e non vale come dipendenza dell'effetto di registrazione.
- **Gli hook non vanno dentro i rami condizionali del JSX.** `app/pratica/page.tsx` rende le tab come rami dello stesso componente: lì serve UNA registrazione che seleziona su `activeTab` (Task 5, Step 1), non una per ramo.
- **Non mettere mai un oggetto in un dependency array** in questo codebase: `usePrimaryAction` dipende solo da primitivi e tiene l'handler in un ref proprio per questo.
- Se un passo di verifica nel browser rivela un comportamento diverso da quello descritto, **fermarsi e segnalarlo** invece di adattare il piano in silenzio: il piano è stato scritto leggendo il codice, ma la forma esatta dei componenti di `app/pratica/page.tsx` (5.940 righe) va confermata sul posto.
