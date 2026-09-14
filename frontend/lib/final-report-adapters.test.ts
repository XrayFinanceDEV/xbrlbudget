import { describe, expect, it } from "vitest";
import bilancio from "../../tests/fixtures/final_report/bilancio.json";
import infrannuale from "../../tests/fixtures/final_report/infrannuale.json";
import startup from "../../tests/fixtures/final_report/startup.json";
import { hasStaleForecast, narrativeFor, statementRows } from "@/components/report/final-report-adapters";
import type { FinalReportModel } from "@/types/final-report";

describe("final-report web adapters", () => {
  it("projects only the serialized forecast statements for all three workflows", () => {
    for (const report of [infrannuale, bilancio, startup] as unknown as FinalReportModel[]) {
      const rows = statementRows(report, "income_statement");
      expect(rows.every((row) => row.values.length === report.forecast.years.length)).toBe(true);
      // A blocked/draft workflow may honestly carry no persisted statements;
      // the adapter preserves that absence instead of inventing zero rows.
      if (rows.length === 0) expect(report.readiness.status).not.toBe("ready");
      expect(narrativeFor(report, "executive_summary").id).toBe("executive_summary");
    }
  });

  it("does not infer staleness from timestamps or recalculate it", () => {
    expect(hasStaleForecast(infrannuale as unknown as FinalReportModel)).toBe(true);
    expect(hasStaleForecast(bilancio as unknown as FinalReportModel)).toBe(false);
    expect(hasStaleForecast(startup as unknown as FinalReportModel)).toBe(false);
  });
});
