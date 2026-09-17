import { describe, expect, it } from "vitest";
import { execFileSync } from "node:child_process";
import path from "node:path";
import annual from "../../tests/fixtures/final_report/v2/bilancio.json";
import intra from "../../tests/fixtures/final_report/v2/infrannuale.json";
import startup from "../../tests/fixtures/final_report/v2/startup.json";
import v1 from "../../tests/fixtures/final_report/bilancio.json";
import { isFinalReportModel } from "@/types/final-report";
import { isFinalReportModelV2, parseFinalReportModelV2 } from "@/types/final-report-v2";

describe("Final report dossier v2 boundary", () => {
  it("keeps the backend presentation catalog synchronized with the existing report", () => {
    expect(execFileSync(process.execPath, ["tools/final_report/export_catalog.cjs", "--check"], {cwd: path.resolve(process.cwd(), ".."), encoding: "utf8"})).toContain("catalog checked");
  });
  it("accepts the three shared backend fixtures and keeps version boundaries explicit", () => {
    const {document, detailed_statements, indicator_catalog, structure_series, editorial_plan, editorial_notes, editorial_readiness, ...core} = intra;
    expect(isFinalReportModel({...core, schema_version: 1, chart_series: intra.chart_series.filter(c => ["income_results", "margins", "cashflows", "liquidity_debt", "working_capital_days", "coverage"].includes(c.id))}), "infrannuale v1 projection").toBe(true);
    for (const [workflow, fixture] of [["bilancio", annual], ["infrannuale", intra], ["startup", startup]] as const) {
      expect(isFinalReportModelV2(fixture), workflow).toBe(true);
      expect(isFinalReportModel(fixture)).toBe(false);
    }
    expect(() => parseFinalReportModelV2(v1)).toThrow(/v2/);
  });
  it("rejects changed titles, extra properties and lossy financial values", () => {
    const title = structuredClone(annual); title.document.title = "Margini in crescita";
    expect(isFinalReportModelV2(title)).toBe(false);
    expect(isFinalReportModelV2({...annual, debug: true})).toBe(false);
    const value = structuredClone(annual) as Record<string, any>;
    value.detailed_statements[0].rows[1].values[0] = 1.25;
    expect(isFinalReportModelV2(value)).toBe(false);
  });
  it("requires correct parent links, period lengths and reasons for unavailable values", () => {
    const parent = structuredClone(annual); parent.detailed_statements[0].rows[1].parent_id = "missing";
    expect(isFinalReportModelV2(parent)).toBe(false);
    const missing = structuredClone(annual); missing.detailed_statements[0].rows[1].values[0] = null;
    expect(isFinalReportModelV2(missing)).toBe(false);
    const length = structuredClone(annual); length.indicator_catalog[0].values.pop();
    expect(isFinalReportModelV2(length)).toBe(false);
  });
  it("checks referenced chart values and units without financial arithmetic", () => {
    const chart = structuredClone(annual); chart.chart_series.at(-1)!.series[0].values[0] = "999";
    expect(isFinalReportModelV2(chart)).toBe(false);
    const unit = structuredClone(annual); unit.indicator_catalog[0].unit = "percent";
    expect(isFinalReportModelV2(unit)).toBe(false);
  });
  it("cannot declare editorial completion before a plan and notes exist", () => {
    const ready = structuredClone(annual); ready.editorial_readiness.status = "ready";
    expect(isFinalReportModelV2(ready)).toBe(false);
  });
  it("rejects structural series whose periods were swapped or whose key is missing", () => {
    const raw = structuredClone(intra) as Record<string, any>;
    delete raw.structure_series;
    expect(isFinalReportModelV2(raw), "structure_series is a required v2 block").toBe(false);
    const swapped = structuredClone(intra) as Record<string, any>;
    const cash = swapped.structure_series[0].series.find((s: {id: string}) => s.id === "cash");
    [cash.values[0], cash.values[1]] = [cash.values[1], cash.values[0]];
    expect(isFinalReportModelV2(swapped), "swapping a series across periods").toBe(false);
    const bumped = structuredClone(intra) as Record<string, any>;
    const fixed = bumped.structure_series[3].series.find((s: {id: string}) => s.id === "fixed_costs");
    fixed.values[0] = String(Number(fixed.values[0]) + 1);
    expect(isFinalReportModelV2(bumped), "a break-even that stops splitting the operating costs").toBe(false);
    const reordered = structuredClone(intra) as Record<string, any>;
    reordered.structure_series[1].periods.reverse();
    expect(isFinalReportModelV2(reordered), "a group reading the periods in another order").toBe(false);
  });
});
