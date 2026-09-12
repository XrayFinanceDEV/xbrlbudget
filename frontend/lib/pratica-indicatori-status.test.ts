import { describe, expect, it } from "vitest";

import { praticaIndicatoriStatus } from "./pratica-indicatori-status";
import type { IntraYearComparison, ScenarioAnalysis } from "@/types/api";

const COMPARISON = {} as unknown as IntraYearComparison;
const ANALYSIS_VUOTO = { forecast_years: [] } as unknown as ScenarioAnalysis;
const ANALYSIS_PIENO = { forecast_years: [{}] } as unknown as ScenarioAnalysis;

describe("praticaIndicatoriStatus", () => {
  it("in caricamento vince su tutto", () => {
    expect(
      praticaIndicatoriStatus({ loading: true, error: "x", analysis: ANALYSIS_PIENO, comparison: COMPARISON }),
    ).toBe("caricamento");
  });

  it("un errore di lettura e' distinto da nessuna proiezione", () => {
    // L'errore e' quello grezzo (vedi lib/forecast-page-status.ts), non un
    // messaggio gia' risolto: qui basta un valore truthy qualunque.
    expect(
      praticaIndicatoriStatus({
        loading: false,
        error: new Error("Network Error"),
        analysis: null,
        comparison: COMPARISON,
      }),
    ).toBe("errore");
  });

  it("nessun ForecastYear, nessun errore: invita al passo 3", () => {
    expect(
      praticaIndicatoriStatus({ loading: false, error: null, analysis: ANALYSIS_VUOTO, comparison: COMPARISON }),
    ).toBe("non_generato");
    expect(
      praticaIndicatoriStatus({ loading: false, error: null, analysis: null, comparison: COMPARISON }),
    ).toBe("non_generato");
  });

  it("dati e comparison presenti, forecast_years non vuoto: pronto", () => {
    expect(
      praticaIndicatoriStatus({ loading: false, error: null, analysis: ANALYSIS_PIENO, comparison: COMPARISON }),
    ).toBe("pronto");
  });

  it("senza comparison non e' mai pronto, anche con forecast_years pieno", () => {
    expect(
      praticaIndicatoriStatus({ loading: false, error: null, analysis: ANALYSIS_PIENO, comparison: null }),
    ).toBe("non_generato");
  });
});
