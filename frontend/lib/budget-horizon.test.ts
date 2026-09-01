import { describe, it, expect } from "vitest";
import {
  forecastYearsFor,
  defaultAssumption,
  withDefaultsForYears,
} from "@/lib/budget-horizon";

describe("forecastYearsFor", () => {
  it("elenca gli anni successivi all'anno base", () => {
    expect(forecastYearsFor(2024, 3)).toEqual([2025, 2026, 2027]);
    expect(forecastYearsFor(2024, 5)).toEqual([2025, 2026, 2027, 2028, 2029]);
  });

  it("non produce anni con un orizzonte non valido", () => {
    expect(forecastYearsFor(2024, 0)).toEqual([]);
    expect(forecastYearsFor(2024, -1)).toEqual([]);
    expect(forecastYearsFor(2024, 2.6)).toEqual([2025, 2026]);
  });
});

describe("defaultAssumption", () => {
  it("marca l'anno e l'aliquota reale (IRES + IRAP), non il 24 dello schema", () => {
    const a = defaultAssumption(2026, 17);
    expect(a.forecast_year).toBe(2026);
    expect(a.scenario_id).toBe(17);
    expect(a.tax_rate).toBe(27.9);
  });

  it("senza scenario non inventa un id", () => {
    expect(defaultAssumption(2026).scenario_id).toBeUndefined();
  });
});

describe("withDefaultsForYears", () => {
  it("riempie di default una mappa vuota", () => {
    const out = withDefaultsForYears({}, [2025, 2026, 2027]);
    expect(Object.keys(out).map(Number).sort()).toEqual([2025, 2026, 2027]);
    expect(out[2026].forecast_year).toBe(2026);
  });

  it("allungando l'orizzonte aggiunge gli anni mancanti e NON tocca quelli salvati", () => {
    const salvate = {
      2025: { forecast_year: 2025, revenue_growth_pct: 12 },
      2026: { forecast_year: 2026, revenue_growth_pct: 8 },
      2027: { forecast_year: 2027, revenue_growth_pct: 4 },
    };
    const out = withDefaultsForYears(salvate, [2025, 2026, 2027, 2028, 2029], 17);

    expect(Object.keys(out).map(Number).sort()).toEqual([
      2025, 2026, 2027, 2028, 2029,
    ]);
    expect(out[2025]).toBe(salvate[2025]);
    expect(out[2026].revenue_growth_pct).toBe(8);
    expect(out[2028].revenue_growth_pct).toBe(0);
    expect(out[2029].scenario_id).toBe(17);
  });

  it("restituisce la STESSA mappa quando non manca nulla", () => {
    // È questa identità a fermare l'effetto che riempie i default: senza,
    // `setAssumptions` rende di nuovo e l'effetto riparte da solo.
    const gia = withDefaultsForYears({}, [2025, 2026]);
    expect(withDefaultsForYears(gia, [2025, 2026])).toBe(gia);
    expect(withDefaultsForYears(gia, [2025])).toBe(gia);
  });

  it("accorciando l'orizzonte conserva gli anni fuori range", () => {
    // L'utente che torna da 5 a 3 anni e poi ci ripensa non deve perdere ciò
    // che aveva scritto: a filtrare è il salvataggio, non questa mappa.
    const cinque = withDefaultsForYears({}, [2025, 2026, 2027, 2028, 2029]);
    const tre = withDefaultsForYears(cinque, [2025, 2026, 2027]);
    expect(tre[2029]).toBeDefined();
  });
});
