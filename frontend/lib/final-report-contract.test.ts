import { describe, expect, it } from "vitest";
import bilancio from "../../tests/fixtures/final_report/bilancio.json";
import infrannuale from "../../tests/fixtures/final_report/infrannuale.json";
import startup from "../../tests/fixtures/final_report/startup.json";
import { ASSUMPTION_SECTION_CATALOG, isFinalReportModel, parseFinalReportModel, type AssumptionValue, type FinalReportModel } from "@/types/final-report";

describe("FinalReportModel v1 runtime contract", () => {
  it("accepts the three shared JSON fixtures", () => {
    for (const fixture of [infrannuale, bilancio, startup]) expect(isFinalReportModel(fixture)).toBe(true);
  });

  it("rejects a future schema version", () => {
    expect(() => parseFinalReportModel({ ...bilancio, schema_version: 2 })).toThrow(/Unsupported/);
  });

  it("requires closing only for the infrannuale workflow", () => {
    expect(isFinalReportModel(bilancio)).toBe(true);
    expect(isFinalReportModel({ ...bilancio, infrannual_closing: null })).toBe(false);
  });

  it("matches Python's defaulted nullable input semantics and ISO date boundary", () => {
    const defaults = structuredClone(bilancio) as Record<string, any>;
    delete defaults.company.tax_id;
    delete defaults.source_revisions[0].available;
    delete defaults.readiness.reasons;
    expect(isFinalReportModel(defaults)).toBe(true);

    expect(isFinalReportModel({ ...bilancio, generated_at: "2026-02-30T11:00:00Z" })).toBe(false);
    const badPeriodEnd = structuredClone(infrannuale) as Record<string, any>;
    badPeriodEnd.infrannual_closing.period_end = "2026-09-31";
    expect(isFinalReportModel(badPeriodEnd)).toBe(false);
  });

  it("uses the same seven group catalog as the fixtures", () => {
    expect(ASSUMPTION_SECTION_CATALOG).toHaveLength(7);
    expect(infrannuale.assumption_sections.map((section) => section.key)).toEqual(ASSUMPTION_SECTION_CATALOG.map((section) => section.key));
  });

  it("accepts typed nested CE/SP structures and a tax runoff plan", () => {
    const report = structuredClone(infrannuale) as FinalReportModel;
    // index 4 = "patrimoniale-pregresso" (Task 8: scenario, fatturato, costi,
    // circolante, patrimoniale-pregresso, patrimoniale-piano, imposte) — dove
    // vive il campo `pregresso`.
    report.assumption_sections[4].assumptions.push({
      field: "pregresso", label: "Pregresso", values: [null, null, null], provenance: "user", active: true,
      pregresso: {
        crediti_commerciali: null, debiti_fornitori: null,
        debiti_tributari: { opening: "100", amounts: ["20"], writeoff: null, saldo: "40", rateizzato: "60", acconto_pct: "100" },
        debiti_previdenziali: null, altri_debiti: null,
      },
    });
    expect(isFinalReportModel(report)).toBe(true);
  });

  it("uses a unary integer predicate for every chart category", () => {
    expect(isFinalReportModel(infrannuale)).toBe(true);
    const malformed = structuredClone(infrannuale) as FinalReportModel;
    malformed.chart_series[0].categories[1] = 2028.5;
    expect(isFinalReportModel(malformed)).toBe(false);
  });

  it("rejects duplicate or mismatched forecast years and empty ready statements", () => {
    const duplicate = structuredClone(infrannuale) as Record<string, any>;
    duplicate.practice.periods.forecast_years = [2027, 2027, 2029];
    expect(isFinalReportModel(duplicate)).toBe(false);

    const emptyCashflow = structuredClone(bilancio) as Record<string, any>;
    emptyCashflow.forecast.years[0].cashflow = [];
    expect(isFinalReportModel(emptyCashflow)).toBe(false);
  });

  it("rejects malformed nested SP and CE entries", () => {
    const malformed = structuredClone(infrannuale) as FinalReportModel;
    // index 2 = "costi" (Task 8: `altre-voci-ce` si e' fusa in `costi`, che
    // porta ancora `ce_overrides`).
    const ce = malformed.assumption_sections[2].assumptions[0];
    if (!ce.ce_overrides) throw new Error("fixture must exercise ce_overrides");
    ce.ce_overrides[0].field = "ce99_override" as never;
    expect(isFinalReportModel(malformed)).toBe(false);
  });

  it("exercises all non-vacuous nested structures and strict boolean scalar drivers", () => {
    const values = new Map<string, AssumptionValue>(
      (infrannuale as unknown as FinalReportModel).assumption_sections.flatMap((section) =>
        section.assumptions.map((value): [string, AssumptionValue] => [value.field, value]),
      ),
    );
    expect(values.get("financing_loans")?.financing_loans?.[0].amount).toBe("100000.00");
    expect(values.get("pregresso")?.pregresso?.debiti_tributari?.rateizzato).toBe("90");
    expect(values.get("tax_temporary_differences")?.temporary_differences?.[0].kind).toBe("deductible");
    expect(values.get("ce_overrides")?.ce_overrides?.[0].field).toBe("ce02_override");
    expect(values.get("sp_indexing")?.sp_indexing?.[0].driver).toBe("ricavi");
    expect(values.get("sp_overrides")?.sp_overrides?.[0].value).toBe("50.00");
    for (const field of ["cash_sweep_enabled", "overdraft_allowed", "previdenza_scales_with_personnel", "tfr_accrual_suspended"]) {
      expect(values.get(field)?.values.every((value) => typeof value === "boolean")).toBe(true);
    }

    const invalid = structuredClone(infrannuale) as Record<string, any>;
    invalid.assumption_sections[5].assumptions[1].values[0] = { unexpected: "object" };
    expect(isFinalReportModel(invalid)).toBe(false);

    const mixed = structuredClone(infrannuale) as Record<string, any>;
    mixed.assumption_sections[5].assumptions[1].values[0] = "1";
    expect(isFinalReportModel(mixed)).toBe(false);
  });
});
