import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { REPORT_SECTIONS } from "@/components/report/report-types";

const page = readFileSync(join(__dirname, "..", "app", "report", "page.tsx"), "utf-8");
const CANONICAL_IDS = [
  "scope", "executive-summary", "sources", "adjustments", "closing", "assumptions",
  "income-forecast", "balance-forecast", "cashflow-sustainability", "indicators-risks",
  "diagnostics", "appendices",
];

describe("ordine del report finale", () => {
  it("keeps the twelve canonical sections in the TOC order", () => {
    expect(REPORT_SECTIONS.map((section) => section.id)).toEqual(CANONICAL_IDS);
  });

  it("la pagina Report non rende più la vista web del dossier (tolta il 2026-11-24)", () => {
    expect(page).not.toContain("Vista web del dossier");
    expect(page).not.toContain("<DossierContent");
    for (const section of REPORT_SECTIONS) {
      expect(page, `anchor ${section.id} ancora in pagina`).not.toContain(`<section id="${section.id}"`);
    }
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
