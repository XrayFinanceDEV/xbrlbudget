import { describe, expect, it } from "vitest";

import { forecastStaleFromAnalysis, isForecastStale } from "@/lib/budget-stale";
import type { ScenarioAnalysis } from "@/types/api";

// Nel formato che /analysis emette davvero: ISO in UTC col suffisso `Z`.
const PRIMA = "2026-09-10T08:00:00.100000Z";
const DOPO = "2026-09-10T08:00:00.900000Z";

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

  it("distingue istanti che cadono nello stesso secondo, al millisecondo", () => {
    // Il server scrive i microsecondi, ma qui la risoluzione e' il
    // MILLISECONDO: `Date` non rappresenta i microsecondi, e `.100001Z` si
    // legge come `.100000Z` (misurato in node). Il troncamento puo' solo
    // trasformare uno stantio in un pareggio, cioe' un avviso mancato e mai un
    // avviso falso; e nel caso reale salvataggio e previsionale a schermo sono
    // due richieste HTTP distinte, non due scritture nello stesso millisecondo.
    // Una sonda su istanti a giorni di distanza non proverebbe nulla, per
    // questo i due casi qui sotto stanno a un millisecondo.
    expect(
      isForecastStale({
        assumptionsUpdatedAt: "2026-09-10T08:00:00.500000Z",
        forecastUpdatedAt: "2026-09-10T08:00:00.499000Z",
        forecastYearsCount: 2,
      }),
    ).toBe(true);
    expect(
      isForecastStale({
        assumptionsUpdatedAt: "2026-09-10T08:00:00.499000Z",
        forecastUpdatedAt: "2026-09-10T08:00:00.500000Z",
        forecastYearsCount: 2,
      }),
    ).toBe(false);
    // Il limite, fissato: un microsecondo di scarto non basta ad alzare
    // l'avviso. E' il verso benigno dell'errore, non un difetto da correggere.
    expect(
      isForecastStale({
        assumptionsUpdatedAt: "2026-09-10T08:00:00.100001Z",
        forecastUpdatedAt: "2026-09-10T08:00:00.100000Z",
        forecastYearsCount: 2,
      }),
    ).toBe(false);
  });

  it("confronta gli istanti, non le stringhe: il formato del server le ordina al contrario", () => {
    // Coppia REALE, non costruita: `datetime.isoformat()` omette la frazione
    // quando i microsecondi sono zero, e il server aggiunge `Z`. Come stringhe
    // `'Z'` (0x5A) > `'.'` (0x2E), quindi `"…00Z"` precede `"…00.500000Z"`
    // nell'ordine lessicografico ma lo segue nel tempo.
    const SENZA_FRAZIONE = "2026-09-10T08:00:00Z";
    const CON_FRAZIONE = "2026-09-10T08:00:00.500000Z";
    expect(SENZA_FRAZIONE > CON_FRAZIONE).toBe(true); // la premessa del test
    expect(
      isForecastStale({
        assumptionsUpdatedAt: CON_FRAZIONE,
        forecastUpdatedAt: SENZA_FRAZIONE,
        forecastYearsCount: 2,
      }),
    ).toBe(true);
    expect(
      isForecastStale({
        assumptionsUpdatedAt: SENZA_FRAZIONE,
        forecastUpdatedAt: CON_FRAZIONE,
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
