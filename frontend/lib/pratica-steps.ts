import type { PraticaState } from "@/contexts/PraticaContext";

export type PraticaPhase = "analisi" | "previsionale";

export interface PraticaStep {
  id: string;
  label: string;
  phase: PraticaPhase;
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
 * Gli step della pratica, nell'ordine in cui vanno mostrati.
 *
 * Percorso "bilancio": fase ANALISI dentro /pratica, poi fase PREVISIONALE su
 * rotte reali. Lo step "projection" compare solo con periodo < 12 mesi, perché
 * un bilancio già annuale non va proiettato a 12 mesi.
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
      kind: "route",
      route: "/budget",
      enabled: pratica.workflow === "startup" ? true : gates.budgetScenario,
    },
    {
      id: "ce-previsionale",
      label: "CE Prev.",
      phase: "previsionale",
      kind: "route",
      route: "/forecast/income",
      enabled: gates.forecastReady,
    },
    {
      id: "sp-previsionale",
      label: "SP Prev.",
      phase: "previsionale",
      kind: "route",
      route: "/forecast/balance",
      enabled: gates.forecastReady,
    },
    {
      id: "riclassificato",
      label: "Riclassificato",
      phase: "previsionale",
      kind: "route",
      route: "/forecast/reclassified",
      enabled: gates.forecastReady,
    },
    {
      id: "rendiconto",
      label: "Rendiconto",
      phase: "previsionale",
      kind: "route",
      route: "/cashflow",
      enabled: gates.forecastReady,
    },
    {
      id: "report",
      label: "Report",
      phase: "previsionale",
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
        phase: "previsionale",
        kind: "route",
        route: "/budget",
        enabled: true,
      },
      ...previsionale,
    ];
  }

  const isAnnual = pratica.periodMonths === 12;

  const analisi: PraticaStep[] = [
    { id: "anagrafiche", label: "Anagrafiche", phase: "analisi", kind: "tab", enabled: true },
    { id: "import", label: "Import", phase: "analisi", kind: "tab", enabled: pratica.companyId !== null },
    { id: "rettifiche", label: "Rettifiche", phase: "analisi", kind: "tab", enabled: gates.imported },
    { id: "comparison", label: "Confronto", phase: "analisi", kind: "tab", enabled: gates.imported && gates.rettificheOk },
    ...(isAnnual
      ? []
      : [
          {
            id: "projection",
            label: "Proiezione",
            phase: "analisi" as const,
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
      kind: "tab",
      enabled: gates.rettificheOk && gates.comparisonReady,
    },
    {
      id: "stampa",
      label: "Stampa",
      phase: "analisi",
      kind: "tab",
      enabled: gates.rettificheOk && (isAnnual ? gates.comparisonReady : gates.projectionReady),
    },
  ];

  return [...analisi, ...previsionale];
}
