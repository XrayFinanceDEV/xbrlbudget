import { describe, expect, it } from "vitest";
import type { PraticaState } from "@/contexts/PraticaContext";
import {
  budgetRecovery,
  budgetRecoveryFromInfrannuale,
  deletedBudgetPraticaPatch,
} from "./budget-recovery";

const PRATICA: PraticaState = {
  workflow: "bilancio",
  companyId: 21,
  fiscalYear: 2026,
  periodMonths: 9,
  infrannualeScenarioId: 71,
  // This is deliberately stale: it is the id left in localStorage after the
  // user deletes the old budget from /budget.
  budgetScenarioId: 84,
  analysisStep: "stampa",
  rettificheConfirmed: { storico: true, verifica: true },
};

describe("budgetRecovery", () => {
  it("recreates a deleted budget from the ready infrannuale practice", () => {
    expect(budgetRecovery(PRATICA, 21, 0)).toEqual({
      companyId: 21,
      infrannualeScenarioId: 71,
      sourceName: "Infrannuale della pratica",
      promoteProjection: true,
      scenario: {
        company_id: 21,
        name: "Budget 2027–2029",
        base_year: 2026,
        scenario_type: "budget",
        reuse_existing: true,
      },
    });
  });

  it("does not re-promote an annual source", () => {
    expect(budgetRecovery({ ...PRATICA, periodMonths: 12 }, 21, 0)?.promoteProjection)
      .toBe(false);
  });

  it("does not expose free-form creation outside the exact recovery state", () => {
    expect(budgetRecovery(null, 21, 0)).toBeNull();
    expect(budgetRecovery({ ...PRATICA, workflow: "startup" }, 21, 0)).toBeNull();
    expect(budgetRecovery({ ...PRATICA, infrannualeScenarioId: null }, 21, 0)).toBeNull();
    expect(budgetRecovery(PRATICA, 99, 0)).toBeNull();
    expect(budgetRecovery(PRATICA, 21, 1)).toBeNull();
  });
});

describe("budgetRecoveryFromInfrannuale", () => {
  const source = {
    id: 71,
    name: "Infrannuale 9M 2026",
    scenario_type: "infrannuale",
    base_year: 2025,
    period_months: 9,
    is_active: 1,
    has_forecast: true,
    created_at: "2026-09-01T00:00:00Z",
  };

  it("also works from /budget without creating or resuming a pratica", () => {
    expect(budgetRecoveryFromInfrannuale(source, 21, 0)).toEqual({
      companyId: 21,
      infrannualeScenarioId: 71,
      sourceName: "Infrannuale 9M 2026",
      promoteProjection: true,
      scenario: {
        company_id: 21,
        name: "Budget 2027–2029",
        base_year: 2026,
        scenario_type: "budget",
        reuse_existing: true,
      },
    });
  });

  it("offers only generated infrannuali while no budget exists", () => {
    expect(budgetRecoveryFromInfrannuale({ ...source, has_forecast: false }, 21, 0))
      .toBeNull();
    expect(budgetRecoveryFromInfrannuale({ ...source, scenario_type: "budget" }, 21, 0))
      .toBeNull();
    expect(budgetRecoveryFromInfrannuale(source, 21, 1)).toBeNull();
  });
});

describe("deletedBudgetPraticaPatch", () => {
  it("clears the id when the active practice owns the deleted budget", () => {
    expect(deletedBudgetPraticaPatch(PRATICA, 21, 84)).toEqual({
      budgetScenarioId: null,
    });
  });

  it("does not touch another practice or another budget", () => {
    expect(deletedBudgetPraticaPatch(PRATICA, 99, 84)).toBeNull();
    expect(deletedBudgetPraticaPatch(PRATICA, 21, 999)).toBeNull();
    expect(deletedBudgetPraticaPatch(null, 21, 84)).toBeNull();
  });
});
