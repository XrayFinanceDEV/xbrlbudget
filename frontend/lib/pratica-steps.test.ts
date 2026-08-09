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
