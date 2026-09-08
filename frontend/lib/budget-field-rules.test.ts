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
});
