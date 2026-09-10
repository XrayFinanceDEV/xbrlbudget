// Shared prop/state shapes for the seven-step budget-assumptions wizard
// (spec 2026-09-08 §4). Types only, no runtime code: the steps (task 11-14)
// and the shared components in this directory (task 8) both import from here
// so the shape of a step's props exists in exactly one place.
import type { FinancingLoanInput, SpIndexingDriver, TemporaryDifferenceInput } from "@/types/api";
import type { AssumptionsMap } from "@/lib/budget-horizon";
import type { HistoricalData } from "@/lib/budget-trend";
// Dichiarazione unica in lib/ (lib/ non puo' importare da components/): qui
// si importa e si ri-esporta, cosi' chi importava PreviewState da questo
// file non deve cambiare percorso.
import type { PreviewState } from "@/lib/budget-preview-state";
export type { PreviewState };

export interface StepProps {
  companyId: number;
  scenarioId: number | null;
  baseYear: number;
  forecastYears: number[];
  assumptions: AssumptionsMap;
  historical: HistoricalData;
  historicalYears: number[];
  preview: PreviewState;
  /** `object` per le ipotesi strutturate scritte per anno — il piano di
   *  scadenziamento del pregresso (`pregresso`), che vive nel PRIMO anno di
   *  piano e non e' ne' un numero ne' un interruttore. */
  update: (year: number, field: string, value: number | boolean | null | object) => void;
  updateAll: (field: string, value: number | boolean | null) => void;
  updateFinancingLoans: (year: number, loans: FinancingLoanInput[]) => void;
  updateTemporaryDifferences: (year: number, lines: TemporaryDifferenceInput[]) => void;
  /** Aggancia (o slega, con `null`) una voce minore dello SP a un driver di
   *  volume, su tutti gli anni di piano. */
  updateSpIndexing: (code: string, driver: SpIndexingDriver | null) => void;
}
