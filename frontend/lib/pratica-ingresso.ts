import type { ScenarioSummary } from "@/types/api";

/**
 * I tre ingressi al percorso, come dato puro.
 *
 * Vivono qui, e non dentro `app/page.tsx`, per una ragione sola: la suite di
 * questo progetto gira senza DOM (`environment: "node"`), quindi la home non e'
 * verificabile e questa e' la sua unica parte testabile. E' anche la parte in
 * cui stava il difetto — «Nuova pratica» in testata e «Nuova pratica» sulla
 * riga dell'azienda eseguivano lo STESSO codice, con lo stesso workflow e la
 * stessa destinazione, e cambiava solo il `companyId`: `null` nel primo caso.
 *
 * Con `companyId: null` lo step Anagrafiche si apre come CREAZIONE, e chi ci
 * arriva dopo aver premuto un pulsante chiamato «Nuova pratica» fa la cosa
 * ovvia — riscrive il nome dell'azienda su cui voleva lavorare — e ne nasce una
 * seconda. Qui il caso e' impossibile per tipo: `companyId` e' `number`, e
 * nessuna firma accetta `null`. Non e' una guardia: e' l'assenza della causa.
 */

export type WorkflowPratica = "bilancio" | "startup";

export interface IngressoPratica {
  /** Da passare a `setStartupMode` PRIMA di avviare la pratica. */
  startupMode: boolean;
  /** L'inizializzazione per `startPratica`. */
  pratica: {
    workflow: WorkflowPratica;
    companyId: number;
    analysisStep: string;
    fiscalYear?: number;
    periodMonths?: number;
    infrannualeScenarioId: number | null;
    budgetScenarioId: number | null;
  };
  /** Dove atterrare dopo `startPratica`. */
  route: "/pratica" | "/budget";
}

/**
 * Il motivo per cui il percorso Startup NON si puo' aprire su quest'azienda,
 * oppure `null` se si puo'. Da leggere PRIMA di navigare.
 *
 * Il wizard del business plan sta dietro un cancello che chiede zero anni
 * (`app/budget/page.tsx`): su un'azienda con `FinancialYear` si atterrava
 * sull'elenco scenari ordinario, intestato «Previsionale Startup» e muto —
 * nessuna schermata per capitale, periodo e driver, e nessun modo di capire
 * che il percorso non stava facendo nulla.
 *
 * Rifiutare, e non aprire il wizard lo stesso, e' la scelta onesta: il
 * percorso semina un bilancio di APERTURA sull'anno precedente al piano, e su
 * un'azienda con storico quell'anno esiste gia'. Chi faceva in tempo a
 * compilare il wizard apparso per un istante — `years` arriva dopo il mount —
 * ne ricavava un 400 e un «Impossibile creare il business plan» che non
 * nominava nemmeno l'anno.
 *
 * Chi chiama lo usa SOLO su un elenco di anni davvero letto: un elenco che non
 * si e' potuto caricare non e' un elenco vuoto, e un controllo che manca e'
 * «non lo so», non un verdetto negativo.
 */
export function rifiutoIngressoStartup(anniEsistenti: readonly number[]): string | null {
  if (anniEsistenti.length === 0) return null;
  const anni = [...anniEsistenti].sort((a, b) => a - b).join(", ");
  const esercizi =
    anniEsistenti.length === 1
      ? `l'esercizio ${anni} esiste già`
      : `gli esercizi ${anni} esistono già`;
  return (
    `Il percorso Startup parte da un bilancio di apertura e vuole un'azienda ` +
    `senza storico: qui ${esercizi}. Usa «Da bilancio», oppure crea ` +
    `un'azienda nuova.`
  );
}

/**
 * Una pratica NUOVA su un'azienda che esiste gia'.
 *
 * Unico punto per i due modi di chiederla — «Nuova pratica» sotto una riga
 * della tendina e «Nuova azienda» in testata, che la crea e poi entra qui.
 * Il tipo si chiede sempre DOPO aver chiesto la pratica: una startup, per
 * definizione, non ha un bilancio da importare, ed e' proprio il caso in cui
 * si crea un'azienda nuova perche' non esiste uno storico. Mandare ogni
 * azienda nuova all'import farebbe atterrare quel caso su una schermata che
 * chiede un documento inesistente.
 */
export function ingressoNuovaPratica(
  companyId: number,
  workflow: WorkflowPratica,
): IngressoPratica {
  return {
    startupMode: workflow === "startup",
    pratica: {
      workflow,
      companyId,
      analysisStep: "anagrafiche",
      // Espliciti, non omessi: `startPratica` fonde sul default, e uno
      // scenario rimasto dalla pratica precedente farebbe RIAPRIRE quella
      // invece di crearne una nuova.
      infrannualeScenarioId: null,
      budgetScenarioId: null,
    },
    route: workflow === "startup" ? "/budget" : "/pratica",
  };
}

/**
 * Riprendere una pratica esistente. Sequenza invariata rispetto a `resume`.
 *
 * Uno scenario budget legacy non ha una fase ANALISI ricostruibile (nessun
 * `infrannualeScenarioId`, quindi nessun `rettifiche_log` da riaprire): si apre
 * direttamente sul budget, e lo stepper nasconde del tutto la fase Analisi
 * invece di mostrarla abilitata-ma-rotta (`pratica-steps.ts`,
 * `isLegacyBudgetResume`).
 */
export function ingressoRiprendi(
  companyId: number,
  scenario: ScenarioSummary,
): IngressoPratica {
  const isInfra = scenario.scenario_type === "infrannuale";
  return {
    startupMode: false,
    pratica: {
      workflow: "bilancio",
      companyId,
      // L'infrannuale proietta l'anno successivo a quello di riferimento.
      fiscalYear: isInfra ? scenario.base_year + 1 : scenario.base_year,
      periodMonths: isInfra ? scenario.period_months ?? 12 : 12,
      infrannualeScenarioId: isInfra ? scenario.id : null,
      budgetScenarioId: isInfra ? null : scenario.id,
      analysisStep: isInfra ? "rettifiche" : "anagrafiche",
    },
    route: isInfra ? "/pratica" : "/budget",
  };
}
