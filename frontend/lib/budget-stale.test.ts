import { describe, expect, it } from "vitest";

import { forecastStaleFromAnalysis, isForecastStale } from "@/lib/budget-stale";
import type { ScenarioAnalysis } from "@/types/api";

const PRIMA = "2026-09-10T08:00:00.100000";
const DOPO = "2026-09-10T08:00:00.900000";

describe("isForecastStale", () => {
  it("e' stantio quando le ipotesi sono piu' recenti del previsionale", () => {
    expect(
      isForecastStale({
        assumptionsUpdatedAt: DOPO,
        forecastUpdatedAt: PRIMA,
        forecastYearsCount: 3,
      }),
    ).toBe(true);
  });

  it("non e' stantio quando il previsionale e' piu' recente delle ipotesi", () => {
    expect(
      isForecastStale({
        assumptionsUpdatedAt: PRIMA,
        forecastUpdatedAt: DOPO,
        forecastYearsCount: 3,
      }),
    ).toBe(false);
  });

  it("non e' stantio a parita' di istante: il confronto e' stretto", () => {
    expect(
      isForecastStale({
        assumptionsUpdatedAt: PRIMA,
        forecastUpdatedAt: PRIMA,
        forecastYearsCount: 3,
      }),
    ).toBe(false);
  });

  it("senza anni di previsionale non c'e' nulla di stantio da mostrare", () => {
    // La vista e' vuota, e il vuoto si vede da solo: qui l'avviso
    // ingannerebbe, perche' non c'e' alcun numero «precedente» a schermo.
    expect(
      isForecastStale({
        assumptionsUpdatedAt: DOPO,
        forecastUpdatedAt: PRIMA,
        forecastYearsCount: 0,
      }),
    ).toBe(false);
  });

  it("un timestamp mancante non alza l'avviso", () => {
    // Un verdetto negativo vuole una contraddizione, non un controllo
    // assente: un backend che tace non si dichiara sporco.
    for (const facts of [
      { assumptionsUpdatedAt: null, forecastUpdatedAt: PRIMA },
      { assumptionsUpdatedAt: DOPO, forecastUpdatedAt: null },
      { assumptionsUpdatedAt: undefined, forecastUpdatedAt: undefined },
    ]) {
      expect(isForecastStale({ ...facts, forecastYearsCount: 3 })).toBe(false);
    }
  });

  it("un timestamp illeggibile non alza l'avviso", () => {
    expect(
      isForecastStale({
        assumptionsUpdatedAt: "non una data",
        forecastUpdatedAt: PRIMA,
        forecastYearsCount: 3,
      }),
    ).toBe(false);
    expect(
      isForecastStale({
        assumptionsUpdatedAt: DOPO,
        forecastUpdatedAt: "",
        forecastYearsCount: 3,
      }),
    ).toBe(false);
  });

  it("distingue istanti che cadono nello stesso secondo", () => {
    // I due timestamp arrivano da `datetime.utcnow()`, che ha i microsecondi,
    // e la generazione scrive subito dopo le ipotesi: una sonda che campiona
    // solo istanti a distanza di giorni non proverebbe nulla sul caso reale.
    expect(
      isForecastStale({
        assumptionsUpdatedAt: "2026-09-10T08:00:00.500000",
        forecastUpdatedAt: "2026-09-10T08:00:00.499000",
        forecastYearsCount: 2,
      }),
    ).toBe(true);
    expect(
      isForecastStale({
        assumptionsUpdatedAt: "2026-09-10T08:00:00.499000",
        forecastUpdatedAt: "2026-09-10T08:00:00.500000",
        forecastYearsCount: 2,
      }),
    ).toBe(false);
  });

  it("confronta gli istanti, non le stringhe: una data piu' lunga non vince per lunghezza", () => {
    expect(
      isForecastStale({
        assumptionsUpdatedAt: "2026-09-09T23:59:59.999999",
        forecastUpdatedAt: "2026-09-10T00:00:00",
        forecastYearsCount: 2,
      }),
    ).toBe(false);
  });
});

describe("forecastStaleFromAnalysis", () => {
  const analysis = (
    fields: Partial<ScenarioAnalysis>,
  ): ScenarioAnalysis => ({ forecast_years: [], ...fields } as unknown as ScenarioAnalysis);

  it("legge i tre campi di /analysis", () => {
    expect(
      forecastStaleFromAnalysis(
        analysis({
          assumptions_updated_at: DOPO,
          forecast_updated_at: PRIMA,
          forecast_years: [{ year: 2027 }, { year: 2028 }] as ScenarioAnalysis["forecast_years"],
        }),
      ),
    ).toBe(true);
  });

  it("non alza l'avviso su un'analisi allineata", () => {
    expect(
      forecastStaleFromAnalysis(
        analysis({
          assumptions_updated_at: PRIMA,
          forecast_updated_at: DOPO,
          forecast_years: [{ year: 2027 }] as ScenarioAnalysis["forecast_years"],
        }),
      ),
    ).toBe(false);
  });

  it("con timestamp disallineati ma nessun anno a schermo non alza nulla", () => {
    // E' il caso di una generazione respinta su uno scenario che non aveva
    // ancora prodotto nulla: le ipotesi sono piu' recenti, ma la vista non
    // mostra alcun numero «precedente» da smentire.
    expect(
      forecastStaleFromAnalysis(
        analysis({
          assumptions_updated_at: DOPO,
          forecast_updated_at: PRIMA,
          forecast_years: [],
        }),
      ),
    ).toBe(false);
  });

  it("senza analisi non alza nulla", () => {
    expect(forecastStaleFromAnalysis(undefined)).toBe(false);
    expect(forecastStaleFromAnalysis(null)).toBe(false);
  });

  it("un'analisi senza le chiavi nuove non alza nulla", () => {
    // Un backend piu' vecchio non manda i tre campi: l'assenza vale
    // «allineato», mai «stantio».
    expect(
      forecastStaleFromAnalysis(
        analysis({ forecast_years: [{ year: 2027 }] as ScenarioAnalysis["forecast_years"] }),
      ),
    ).toBe(false);
  });
});
