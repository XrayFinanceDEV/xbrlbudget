import type { PraticaState } from "@/contexts/PraticaContext";
import type { BudgetScenarioCreate, ScenarioSummary } from "@/types/api";

export interface BudgetRecovery {
  companyId: number;
  infrannualeScenarioId: number;
  sourceName: string;
  promoteProjection: boolean;
  scenario: BudgetScenarioCreate;
}

/**
 * Rebuild the infrannuale -> budget bridge after its budget was deleted.
 *
 * Ordinary free-form creation on /budget stays disabled: the recovery is
 * available only for the currently selected company's guided practice, when
 * its source infrannuale still exists and the server returned no budget
 * scenarios.  That preserves the corrected/promoted accounting lineage used
 * by the original "Prosegui al Budget" action in Stampa.
 */
export function budgetRecovery(
  pratica: PraticaState | null,
  selectedCompanyId: number | null,
  budgetScenarioCount: number,
): BudgetRecovery | null {
  if (
    !pratica ||
    pratica.workflow !== "bilancio" ||
    selectedCompanyId === null ||
    pratica.companyId !== selectedCompanyId ||
    pratica.fiscalYear === null ||
    pratica.infrannualeScenarioId === null ||
    pratica.periodMonths === null ||
    pratica.periodMonths < 1 ||
    pratica.periodMonths > 12 ||
    budgetScenarioCount !== 0
  ) {
    return null;
  }

  const baseYear = pratica.fiscalYear;
  return {
    companyId: selectedCompanyId,
    infrannualeScenarioId: pratica.infrannualeScenarioId,
    sourceName: "Infrannuale della pratica",
    // A partial-year source must be promoted again so the FinancialYear and
    // its server-owned provenance reflect the current projection.  A 12M
    // import is already the authoritative full-year base.
    promoteProjection: pratica.periodMonths < 12,
    scenario: {
      company_id: selectedCompanyId,
      name: `Budget ${baseYear + 1}–${baseYear + 3}`,
      base_year: baseYear,
      scenario_type: "budget",
      reuse_existing: true,
    },
  };
}

/**
 * Recovery when /budget was opened from the normal navigation and therefore
 * has no active PraticaContext.  The company summary exposes `has_forecast`,
 * so only an infrannuale that has actually produced its projection is offered
 * as a source.  The target full year is the year after its reference base,
 * exactly as in `ingressoRiprendi` and the guided Stampa bridge.
 */
export function budgetRecoveryFromInfrannuale(
  source: ScenarioSummary,
  selectedCompanyId: number | null,
  budgetScenarioCount: number,
): BudgetRecovery | null {
  if (
    selectedCompanyId === null ||
    source.scenario_type !== "infrannuale" ||
    !source.has_forecast ||
    source.period_months === null ||
    source.period_months < 1 ||
    source.period_months > 12 ||
    budgetScenarioCount !== 0
  ) {
    return null;
  }

  const baseYear = source.base_year + 1;
  return {
    companyId: selectedCompanyId,
    infrannualeScenarioId: source.id,
    sourceName: source.name,
    promoteProjection: source.period_months < 12,
    scenario: {
      company_id: selectedCompanyId,
      name: `Budget ${baseYear + 1}–${baseYear + 3}`,
      base_year: baseYear,
      scenario_type: "budget",
      reuse_existing: true,
    },
  };
}

/** Clear only the deleted scenario from the active practice. */
export function deletedBudgetPraticaPatch(
  pratica: PraticaState | null,
  companyId: number,
  deletedScenarioId: number,
): Pick<PraticaState, "budgetScenarioId"> | null {
  if (
    !pratica ||
    pratica.companyId !== companyId ||
    pratica.budgetScenarioId !== deletedScenarioId
  ) {
    return null;
  }
  return { budgetScenarioId: null };
}
