import { describe, expect, it } from "vitest";
import {
  DEAD_FIELDS, STEP_FIELDS, WIZARD_STEPS, nextStep, prevStep,
  primaryLabel, stepForErrorMessage, stepStorageKey,
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
});
