import { describe, expect, it } from "vitest";
import type { PraticaState } from "@/contexts/PraticaContext";
import {
  blockedStep,
  buildPraticaSteps,
  currentStepId,
  firstEnabledStep,
  gateReason,
  nextStep,
  phaseStatus,
  praticaGates,
  prevStep,
  rescueStep,
  senzaPraticaAttiva,
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
    expect(currentStepId("/pratica", "rettifiche", PRATICA)).toBe("rettifiche");
    expect(currentStepId("/forecast/balance", "rettifiche", PRATICA)).toBe("sp-previsionale");
    expect(currentStepId("/forecast/reclassified", "x", PRATICA)).toBe("riclassificato");
    expect(currentStepId("/forecast/income", "x", PRATICA)).toBe("ce-previsionale");
    expect(currentStepId("/analysis", "x", PRATICA)).toBe("indici");
    expect(currentStepId("/cashflow", "x", PRATICA)).toBe("rendiconto");
    expect(currentStepId("/report", "x", PRATICA)).toBe("report");
    expect(currentStepId("/budget", "x", PRATICA)).toBe("budget");
    expect(currentStepId("/", "x", PRATICA)).toBe("");
  });

  it("percorso startup su /budget: anagrafiche finché non c'è uno scenario budget", () => {
    const startup: PraticaState = { ...PRATICA, workflow: "startup" };
    expect(currentStepId("/budget", "x", startup)).toBe("anagrafiche");
    expect(currentStepId("/budget", "x", { ...startup, budgetScenarioId: 5 })).toBe("budget");
  });
});

describe("blockedStep", () => {
  it("nessuna pratica attiva: non blocca", () => {
    expect(blockedStep(null, "stampa")).toBeNull();
  });

  it("step raggiungibile: non blocca", () => {
    expect(blockedStep(PRATICA, "anagrafiche")).toBeNull();
  });

  it("step sconosciuto: non blocca (i workflow ne omettono di proposito)", () => {
    expect(blockedStep(PRATICA, "questo-step-non-esiste")).toBeNull();
  });

  it("Import senza azienda: blocca e riporta ad Anagrafiche", () => {
    // fiscalYear azzerato insieme a companyId: senza azienda non può esistere
    // un anno fiscale importato — altrimenti gates.imported (che guarda solo
    // fiscalYear) lascerebbe "rettifiche" abilitata da uno stato che non può
    // verificarsi nel flusso reale.
    const p: PraticaState = { ...PRATICA, companyId: null, fiscalYear: null };
    const block = blockedStep(p, "import");
    expect(block?.reason).toBe("Completa prima l'anagrafica");
    expect(block?.back?.id).toBe("anagrafiche");
  });

  it("Stampa con rettifiche non confermate: blocca e riporta a Rettifiche", () => {
    const p: PraticaState = {
      ...PRATICA,
      infrannualeScenarioId: 7,
      rettificheConfirmed: { storico: false, verifica: false },
    };
    const block = blockedStep(p, "stampa");
    expect(block?.reason).toBe("Rettifiche non confermate");
    expect(block?.back?.id).toBe("rettifiche");
  });

  it("Proiezione senza confronto: riporta al Confronto, l'ultima tab raggiungibile", () => {
    const p: PraticaState = {
      ...PRATICA,
      infrannualeScenarioId: null,
      rettificheConfirmed: { storico: true, verifica: true },
    };
    const block = blockedStep(p, "projection");
    expect(block?.reason).toBe("Confronto non caricato");
    expect(block?.back?.id).toBe("comparison");
  });

  it("il ritorno resta dentro il wizard, mai su una rotta previsionale", () => {
    // infrannualeScenarioId valorizzato (non null): budgetScenarioId!==null
    // insieme a infrannualeScenarioId===null è esattamente il trigger di
    // isLegacyBudgetResume (v. buildPraticaSteps), che fa sparire "projection"
    // dalla lista degli step — lo step diventerebbe "sconosciuto" e
    // blockedStep non bloccherebbe nulla per il motivo 1 del suo JSDoc,
    // vanificando questo test. rettificheConfirmed resta quella di default
    // (non confermate) così "projection" è comunque bloccata, mentre
    // budgetScenarioId abilita gli step-rotta del previsionale (budget,
    // indici, …) che il "back" deve scartare in favore di una tab.
    const p: PraticaState = {
      ...PRATICA,
      infrannualeScenarioId: 7,
      budgetScenarioId: 3,
    };
    const block = blockedStep(p, "projection");
    expect(block?.back?.kind).toBe("tab");
  });
});

describe("rescueStep", () => {
  it("preferisce l'ultima tab abilitata del percorso, non la prima abilitata in assoluto", () => {
    const steps = buildPraticaSteps(PRATICA, ALL_GATES);
    // Con tutti i gate aperti sono abilitate sia tab (anagrafiche..stampa) sia
    // rotte previsionali (budget..report): deve tornare l'ultima TAB, non la
    // prima route abilitata dell'intero array.
    expect(rescueStep(steps)?.id).toBe("stampa");
    expect(rescueStep(steps)?.kind).toBe("tab");
  });

  it("null quando nessuna tab è abilitata: il chiamante ricade sul primo step abilitato", () => {
    // Legacy budget resume: solo la fase PREVISIONALE, tutta a kind "route" —
    // nessuna tab esiste nell'array, quindi rescueStep non ha nulla da
    // proporre dentro il wizard.
    const steps = buildPraticaSteps(
      { ...PRATICA, budgetScenarioId: 7, infrannualeScenarioId: null },
      ALL_GATES,
    );
    expect(rescueStep(steps)).toBeNull();
    // Lo stesso pattern usato da PraticaActionBar (`rescueStep(steps) ??
    // steps.find((s) => s.enabled)`) ricade sul primo step abilitato di
    // qualsiasi tipo, cosicché la barra azioni non resti mai senza un rescue
    // fuori dal wizard.
    const fallback = rescueStep(steps) ?? steps.find((s) => s.enabled) ?? null;
    expect(fallback?.id).toBe("budget");
    expect(fallback?.kind).toBe("route");
  });
});

/**
 * #32 — `/pratica` senza pratica attiva era un vicolo cieco: la card
 * «Anagrafica azienda» con tre campi vuoti e NESSUN bottone nel corpo della
 * pagina. Il primario del percorso vive in `usePraticaPrimaryAction`, che
 * restituisce `null` fuori da una pratica, quindi il form non era inviabile:
 * si compilavano tre campi che non si potevano mandare da nessuna parte.
 *
 * La parte insidiosa è l'idratazione: `pratica` è `null` anche nel primo
 * render, prima che il context legga `localStorage` (lo legge in un
 * `useEffect`, mai nell'inizializzatore di `useState`). Decidere sul solo
 * `pratica === null` rimanderebbe alla home chiunque ricarichi /pratica su una
 * pratica valida.
 */
describe("senzaPraticaAttiva", () => {
  it("non decide nulla finché il context non è stato letto", () => {
    expect(senzaPraticaAttiva(null, false)).toBe(false);
  });

  it("letto il context e trovato nulla: qui non c'è niente da fare", () => {
    expect(senzaPraticaAttiva(null, true)).toBe(true);
  });

  it("una pratica attiva non viene mai rimandata alla home", () => {
    expect(senzaPraticaAttiva(PRATICA, true)).toBe(false);
    expect(senzaPraticaAttiva(PRATICA, false)).toBe(false);
  });

  it("una pratica ancora senza azienda resta una pratica", () => {
    // Il form di Anagrafiche in modalità CREAZIONE (`companyId: null`) è uno
    // stato legittimo del percorso: il vicolo cieco era l'assenza della
    // pratica, non l'assenza dell'azienda.
    expect(senzaPraticaAttiva({ ...PRATICA, companyId: null }, true)).toBe(false);
  });
});
