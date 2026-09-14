import { describe, expect, it } from "vitest";
import bilancio from "../../tests/fixtures/final_report/bilancio.json";
import infrannuale from "../../tests/fixtures/final_report/infrannuale.json";
import startup from "../../tests/fixtures/final_report/startup.json";
import { ASSUMPTION_SECTION_CATALOG, isFinalReportModel, parseFinalReportModel } from "@/types/final-report";

describe("FinalReportModel v1 runtime contract", () => {
  it("accepts the three shared JSON fixtures", () => {
    for (const fixture of [infrannuale, bilancio, startup]) expect(isFinalReportModel(fixture)).toBe(true);
  });

  it("rejects a future schema version", () => {
    expect(() => parseFinalReportModel({ ...bilancio, schema_version: 2 })).toThrow(/Unsupported/);
  });

  it("uses the same seven group catalog as the fixtures", () => {
    expect(ASSUMPTION_SECTION_CATALOG).toHaveLength(7);
    expect(infrannuale.assumption_sections.map((section) => section.key)).toEqual(ASSUMPTION_SECTION_CATALOG.map((section) => section.key));
  });
});
