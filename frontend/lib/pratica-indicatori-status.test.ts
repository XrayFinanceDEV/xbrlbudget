import { describe, expect, it } from "vitest";

import { generaAnnualeAutomatica, praticaIndicatoriStatus } from "./pratica-indicatori-status";
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

describe("generaAnnualeAutomatica", () => {
  const base = {
    periodMonths: 12,
    status: "non_generato" as const,
    scenarioId: 7,
    tentatoPer: null,
    inCorso: false,
    datiPronti: true,
  };

  it("su 12 mesi senza anno generato la generazione parte da sola", () => {
    // Si arriva agli Indicatori dallo stepper, non da «Vai agli Indicatori»: prima
    // restava «Genera prima la proiezione nel passaggio 3», un passo che sui 12 mesi
    // non esiste.
    expect(generaAnnualeAutomatica(base)).toBe(true);
  });

  it("una volta sola per scenario: un rifiuto del motore non si ritenta in loop", () => {
    expect(generaAnnualeAutomatica({ ...base, tentatoPer: 7 })).toBe(false);
    expect(generaAnnualeAutomatica({ ...base, tentatoPer: 6 })).toBe(true);
  });

  it("non sotto i 12 mesi, non mentre gira, non se c'e' gia' o se la lettura e' fallita", () => {
    expect(generaAnnualeAutomatica({ ...base, periodMonths: 6 })).toBe(false);
    expect(generaAnnualeAutomatica({ ...base, inCorso: true })).toBe(false);
    expect(generaAnnualeAutomatica({ ...base, status: "pronto" })).toBe(false);
    expect(generaAnnualeAutomatica({ ...base, status: "errore" })).toBe(false);
    expect(generaAnnualeAutomatica({ ...base, status: "caricamento" })).toBe(false);
    expect(generaAnnualeAutomatica({ ...base, scenarioId: null })).toBe(false);
    // Confronto o analisi non ancora letti: aspettare, non consumare il tentativo
    expect(generaAnnualeAutomatica({ ...base, datiPronti: false })).toBe(false);
  });
});
