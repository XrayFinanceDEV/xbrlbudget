import { describe, expect, it } from "vitest";
import bilancio from "../../tests/fixtures/final_report/bilancio.json";
import infrannuale from "../../tests/fixtures/final_report/infrannuale.json";
import startup from "../../tests/fixtures/final_report/startup.json";
import { ASSUMPTION_SECTION_CATALOG, isFinalReportModel, parseFinalReportModel, type FinalReportModel } from "@/types/final-report";

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

  it("uses the same seven group catalog as the fixtures", () => {
    expect(ASSUMPTION_SECTION_CATALOG).toHaveLength(7);
    expect(infrannuale.assumption_sections.map((section) => section.key)).toEqual(ASSUMPTION_SECTION_CATALOG.map((section) => section.key));
  });

  it("accepts typed nested CE/SP structures and a tax runoff plan", () => {
    const report = structuredClone(infrannuale) as FinalReportModel;
    report.assumption_sections[5].assumptions.push({
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

  it("rejects malformed nested SP and CE entries", () => {
    const malformed = structuredClone(infrannuale) as FinalReportModel;
    const ce = malformed.assumption_sections[3].assumptions[0];
    if (!ce.ce_overrides) throw new Error("fixture must exercise ce_overrides");
    ce.ce_overrides[0].field = "ce99_override" as never;
    expect(isFinalReportModel(malformed)).toBe(false);
  });
});
