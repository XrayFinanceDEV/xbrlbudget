import { describe, expect, it } from "vitest";
import { FIELD_RULES, parseFieldValue } from "./budget-field-rules";
import { STEP_FIELDS } from "./budget-wizard-steps";

describe("budget-field-rules", () => {
  it("ogni campo scalare dei passi ha una regola", () => {
    const json = new Set(["financing_loans", "tax_temporary_differences"]);
    for (const fields of Object.values(STEP_FIELDS))
      for (const f of fields) if (!json.has(f)) expect(FIELD_RULES[f], f).toBeDefined();
  });

  it("parse: virgola, vuoto, clamp", () => {
    expect(parseFieldValue("revenue_growth_pct", "12,5")).toBe(12.5);
    expect(parseFieldValue("dso_days", "")).toBeNull();
    expect(parseFieldValue("revenue_growth_pct", "")).toBe(0);
    expect(parseFieldValue("fixed_materials_percentage", "140")).toBe(100);
    expect(parseFieldValue("tangible_investments", "-5")).toBe(0);
  });

  it("financing_interest_rate ha un intervallo piu' stretto del pct % generico", () => {
    // -100..100 e' il range di default: se l'override sparisse, questi due
    // valori (dentro il range generico ma fuori da 0..30) non verrebbero
    // clampati e il test lo rileverebbe.
    expect(FIELD_RULES.financing_interest_rate).toEqual({ kind: "pct", step: "0.1", min: 0, max: 30 });
    expect(parseFieldValue("financing_interest_rate", "50")).toBe(30);
    expect(parseFieldValue("financing_interest_rate", "-5")).toBe(0);
  });

  it("i campi days() clampano al massimo reale, non solo nullable -> null", () => {
    expect(FIELD_RULES.dso_days).toEqual({ kind: "days", nullable: true, min: 0, max: 365 });
    expect(parseFieldValue("dso_days", "400")).toBe(365);
  });

  it("un campo per ogni kind distinto, con step pinnato", () => {
    expect(FIELD_RULES.revenue_growth_pct).toEqual({ kind: "pct", step: "0.1", min: -100, max: 100 });
    expect(FIELD_RULES.tangible_investments).toEqual({ kind: "eur", min: 0, step: "1000" });
    expect(FIELD_RULES.existing_debt_repayment_years).toEqual({ kind: "years", nullable: true, min: 0, max: 30 });
    expect(FIELD_RULES.dio_days).toEqual({ kind: "days", nullable: true, min: 0, max: 365 });
    expect(FIELD_RULES.cash_sweep_enabled).toEqual({ kind: "bool" });
  });
});
