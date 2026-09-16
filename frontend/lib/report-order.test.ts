import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { REPORT_SECTIONS } from "@/components/report/report-types";

const page = readFileSync(join(__dirname, "..", "app", "report", "page.tsx"), "utf-8");
const dossier = readFileSync(join(__dirname, "..", "components", "final-report", "Dossier.tsx"), "utf-8");
const CANONICAL_IDS = [
  "scope", "executive-summary", "sources", "adjustments", "closing", "assumptions",
  "income-forecast", "balance-forecast", "cashflow-sustainability", "indicators-risks",
  "diagnostics", "appendices",
];

describe("ordine del report finale", () => {
  it("keeps the twelve canonical sections in the TOC order", () => {
    expect(REPORT_SECTIONS.map((section) => section.id)).toEqual(CANONICAL_IDS);
  });

  it("renders every stable anchor in exactly the TOC order", () => {
    const positions = REPORT_SECTIONS.map((section) => {
      const marker = section.id === "appendices" ? "<DossierContent report={model}" : `<section id=\"${section.id}\"`;
      const position = page.indexOf(marker);
      expect(position, `missing anchor ${section.id}`).toBeGreaterThan(-1);
      return position;
    });
    expect(positions).toEqual([...positions].sort((a, b) => a - b));
    expect(dossier).toContain('<section id="appendices"');
  });

  it("loads the versioned editorial session and has explicit stale regeneration", () => {
    expect(page).toContain("getEditorialSession(selectedCompanyId!, scenarioId!)");
    expect(page).not.toContain("useAnalysis(");
    expect(page).not.toContain("useScenarios(");
    expect(page).toContain('reason.code === "forecast_stale"');
    expect(page).toContain("generateForecast(selectedCompanyId, scenarioId)");
    expect(page).toContain("await completeAction(actionScope)");
  });
});
