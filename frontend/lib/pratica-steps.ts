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
