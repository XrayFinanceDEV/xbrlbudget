import { describe, expect, it } from "vitest";
import {
  DEAD_FIELDS, ROUTE_DOPO_CALCOLO, STEP_FIELDS, WIZARD_STEPS, groupWizardSteps, nextStep,
  parseStoredStep, prevStep,
  primaryLabel, saveOutcome, stepFooterHint, stepForErrorMessage, stepLead, stepStorageKey,
  stepsUpTo, wizardChrome, type WizardStep,
} from "./budget-wizard-steps";

describe("budget-wizard-steps", () => {
  it("ha sette passi numerati in ordine, in tre gruppi", () => {
    expect(WIZARD_STEPS.map((s) => s.n)).toEqual([1, 2, 3, 4, 5, 6, 7]);
    expect(WIZARD_STEPS.map((s) => s.group)).toEqual([
      "Impostazione", "Conto economico", "Conto economico", "Conto economico",
      "Stato patrimoniale", "Stato patrimoniale", "Stato patrimoniale",
    ]);
  });
  it("ogni campo esposto appartiene a un solo passo e i campi morti a nessuno", () => {
    const seen = new Map<string, string>();
    for (const [step, fields] of Object.entries(STEP_FIELDS)) {
      for (const f of fields) {
        expect(seen.has(f), `${f} in ${seen.get(f)} e ${step}`).toBe(false);
        seen.set(f, step);
      }
    }
    for (const dead of DEAD_FIELDS) expect(seen.has(dead)).toBe(false);
    expect(seen.get("revenue_growth_pct")).toBe("fatturato");
    expect(seen.get("fixed_materials_percentage")).toBe("costi");
    expect(seen.get("sp16e_growth_pct")).toBe("imposte");
    expect(seen.get("existing_debt_repayment_years")).toBe("pregresso-nuovo");
  });
  it("etichetta del primario e navigazione", () => {
    expect(primaryLabel("costi")).toBe("Avanti");
    expect(primaryLabel("imposte")).toBe("Salva e calcola previsionale");
    expect(nextStep("scenario")).toBe("fatturato");
    expect(nextStep("imposte")).toBeNull();
    expect(prevStep("scenario")).toBeNull();
    expect(stepForErrorMessage("Unfunded financing requirement 84,120.00: add ...")).toBe("pregresso-nuovo");
    expect(stepForErrorMessage("altro")).toBe("imposte");
    expect(stepStorageKey(12)).toBe("budget-wizard-step:12");
  });
  it("raggruppa per identita' di gruppo, non per vicinanza (I3)", () => {
    // Fixture deliberatamente non contigua: A, B, A. Un raggruppamento che si
    // fonde solo col vicino precedente produrrebbe due gruppi "A".
    const steps: WizardStep[] = [
      { n: 1, key: "scenario", title: "Uno", subtitle: "", group: "Impostazione" },
      { n: 2, key: "fatturato", title: "Due", subtitle: "", group: "Conto economico" },
      { n: 3, key: "costi", title: "Tre", subtitle: "", group: "Impostazione" },
    ];
    const grouped = groupWizardSteps(steps);
    expect(grouped).toHaveLength(2);
    expect(grouped.map((g) => g.group)).toEqual(["Impostazione", "Conto economico"]);
    expect(grouped[0].steps.map((s) => s.key)).toEqual(["scenario", "costi"]);
    expect(grouped[1].steps.map((s) => s.key)).toEqual(["fatturato"]);
  });
  it("sui sette passi veri produce i tre gruppi noti, in ordine", () => {
    const grouped = groupWizardSteps(WIZARD_STEPS);
    expect(grouped.map((g) => g.group)).toEqual(["Impostazione", "Conto economico", "Stato patrimoniale"]);
    expect(grouped.reduce((n, g) => n + g.steps.length, 0)).toBe(7);
  });
});

describe("stepLead", () => {
  it("ogni passo ha un sottotitolo non vuoto", () => {
    for (const s of WIZARD_STEPS) expect(stepLead(s.key, 2024).length).toBeGreaterThan(0);
  });
  it("l'anno base e' quello vero, non il 2025 scritto a mano nel prototipo", () => {
    expect(stepLead("scenario", 2022)).toContain("2022");
    expect(stepLead("scenario", 2022)).not.toContain("2025");
    expect(stepLead("circolante", 2022)).toContain("2022");
  });
});

describe("stepFooterHint", () => {
  it("porta la posizione nel percorso", () => {
    expect(stepFooterHint("scenario")).toBe("Passo 1 di 7 · Scenario");
    expect(stepFooterHint("circolante")).toBe("Passo 5 di 7 · Capitale circolante");
  });
  it("l'ultimo passo dice dove si atterra dopo il calcolo", () => {
    const hint = stepFooterHint("imposte");
    expect(hint).toContain("Passo 7 di 7");
    expect(hint).toContain("CE Prev.");
    expect(hint).toContain("SP Prev.");
  });
});

describe("parseStoredStep", () => {
  it("riconosce un passo valido", () => {
    expect(parseStoredStep("circolante")).toBe("circolante");
  });
  it("una chiave assente o un valore ignoto non aprono un passo inesistente", () => {
    expect(parseStoredStep(null)).toBeNull();
    expect(parseStoredStep(undefined)).toBeNull();
    expect(parseStoredStep("")).toBeNull();
    expect(parseStoredStep("riepilogo")).toBeNull();
    // Non deve bastare che la stringa sia una proprieta' di Object.prototype.
    expect(parseStoredStep("toString")).toBeNull();
  });
});

describe("stepsUpTo", () => {
  it("porta tutti i passi fino a quello dato, compreso", () => {
    expect(stepsUpTo("scenario")).toEqual(["scenario"]);
    expect(stepsUpTo("costi")).toEqual(["scenario", "fatturato", "costi"]);
    expect(stepsUpTo("imposte")).toHaveLength(7);
  });
  it("chi riapre al passo 7 non trova sei pallini grigi", () => {
    // Segnare come visitato il solo passo ripristinato farebbe dire alla
    // guida il contrario di dove si trova l'utente.
    expect(stepsUpTo("imposte")).toContain("scenario");
    expect(stepsUpTo("imposte")).toContain("circolante");
  });
});

describe("wizardChrome", () => {
  it("dentro la pratica il wizard NON rende la propria barra in fondo", () => {
    // Due barre a bottom:0: quella della pratica (z-30, sticky) copre quella
    // del wizard (z-10, fixed), e il click su «Indietro» finisce sull'«Avanti»
    // del percorso. Misurato nel browser, non dedotto.
    const c = wizardChrome(true);
    expect(c.bottomBar).toBe(false);
    expect(c.primaryButton).toBe(false);
    // Ma Annulla e Indietro devono restare raggiungibili: risalgono in testa.
    expect(c.headerControls).toBe(true);
    // Nessuna barra `fixed` da compensare.
    expect(c.containerClass).toBe("");
  });
  it("fuori dalla pratica la barra del wizard e' l'unica e resta", () => {
    const c = wizardChrome(false);
    expect(c.bottomBar).toBe(true);
    expect(c.primaryButton).toBe(true);
    expect(c.headerControls).toBe(false);
    expect(c.containerClass).toBe("pb-24");
  });
  it("i comandi esistono sempre in esattamente un posto", () => {
    for (const inPratica of [true, false]) {
      const c = wizardChrome(inPratica);
      // Mai due barre insieme, e mai zero posti in cui premere Indietro.
      expect(c.bottomBar).toBe(!c.headerControls);
      // Il `pb-24` esiste se e solo se c'e' una barra `fixed` da compensare.
      expect(c.containerClass === "pb-24").toBe(c.bottomBar);
    }
  });
});

describe("saveOutcome", () => {
  it("un previsionale rifiutato torna 200: la verita' e' in forecast_generated", () => {
    const out = saveOutcome({
      forecast_generated: false,
      message: "Unfunded financing requirement 84,120.00",
    });
    expect(out.ok).toBe(false);
    expect(out.message).toContain("Unfunded");
    expect(out.step).toBe("pregresso-nuovo");
  });
  it("un rifiuto non naviga MAI: niente toast verde su una Proiezione vuota", () => {
    // E' il difetto piu' costoso documentato in CLAUDE.md, e prima era
    // rimediabile togliendo un `return` dal componente senza rompere nulla.
    expect(saveOutcome({ forecast_generated: false, message: "x" }).route).toBeNull();
    expect(saveOutcome({ forecast_generated: false }).route).toBeNull();
  });
  it("un rifiuto senza ragione ha comunque un messaggio, e cade sull'ultimo passo", () => {
    expect(saveOutcome({ forecast_generated: false, message: "   " })).toEqual({
      ok: false, message: "Previsionale non generato", step: "imposte", route: null,
    });
  });
  it("si atterra sul CE previsionale, dove i numeri appena calcolati si leggono", () => {
    expect(saveOutcome({ forecast_generated: true }).route).toBe(ROUTE_DOPO_CALCOLO);
    expect(ROUTE_DOPO_CALCOLO).toBe("/forecast/income");
  });
  it("solo un false esplicito e' un rifiuto: un campo assente non e' una negazione", () => {
    const atteso = { ok: true, message: "Previsionale calcolato", step: null, route: ROUTE_DOPO_CALCOLO };
    expect(saveOutcome({ forecast_generated: true })).toEqual(atteso);
    expect(saveOutcome({})).toEqual(atteso);
    expect(saveOutcome(null)).toEqual(atteso);
    expect(saveOutcome(undefined)).toEqual(atteso);
  });
  it("un successo non sposta il passo: si resta dove si e', poi si naviga", () => {
    expect(saveOutcome({ forecast_generated: true }).step).toBeNull();
  });
});
