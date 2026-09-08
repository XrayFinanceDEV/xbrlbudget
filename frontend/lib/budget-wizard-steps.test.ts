import { describe, expect, it } from "vitest";
import {
  DEAD_FIELDS, STEP_FIELDS, WIZARD_STEPS, groupWizardSteps, nextStep, prevStep,
  primaryLabel, stepForErrorMessage, stepStorageKey, type WizardStep,
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
