import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PreviewSequencer, createDebouncedRunner } from "./budget-preview-queue";

/**
 * `useForecastPreview` vive in `hooks/` e chiama `useState`/`useEffect`: fuori
 * da un render React quelle chiamate lanciano ("Invalid hook call"), e jsdom
 * non e' installato in questo progetto (ruling gia' preso per Task 5 — vedi
 * `budget-preview-queue.test.ts`). Questo test isola la STESSA composizione
 * che l'hook usa internamente — `PreviewSequencer` + `createDebouncedRunner`
 * attorno a `previewForecast` — e dimostra l'invariante che l'hook deve
 * rispettare: una risposta arrivata in ritardo non sovrascrive mai una piu'
 * recente, anche quando la promise non onora l'abort (rete lenta, o un mock
 * che ignora il signal come questo).
 */

const postMock = vi.fn();
vi.mock("axios", () => {
  const instance = {
    post: (...args: unknown[]) => postMock(...args),
    get: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
  };
  return {
    default: {
      create: vi.fn(() => instance),
      isCancel: vi.fn(() => false),
    },
  };
});

import { previewForecast } from "./api";

type FakeState = { data: unknown; error: string | null; loading: boolean };

describe("composizione hook (sequencer + runner attorno a previewForecast)", () => {
  beforeEach(() => {
    postMock.mockReset();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("una risposta stale arrivata dopo una piu' recente non sovrascrive lo stato", async () => {
    const seq = new PreviewSequencer();
    let state: FakeState = { data: null, error: null, loading: false };

    // Due chiamate pendenti, risolte manualmente in ordine INVERSO rispetto
    // all'invocazione — cosi' la prova non dipende dall'ordine di arrivo in
    // rete, solo dal guard `isCurrent`.
    const resolvers: Array<(v: unknown) => void> = [];
    postMock.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolvers.push((data) => resolve({ data }));
        })
    );

    // Wiring identico a quello dell'hook (vedi task-10-brief.md, Step 2): ogni
    // push prende un numero di sequenza, e solo la risposta ancora corrente
    // aggiorna lo stato.
    const runner = createDebouncedRunner<Record<string, unknown>[]>((rows, signal) => {
      const mine = seq.next();
      state = { ...state, loading: true };
      previewForecast(1, 2, rows, signal)
        .then((data) => {
          if (seq.isCurrent(mine)) state = { data, error: null, loading: false };
        })
        .catch(() => {
          // annullamento/errore: fuori dallo scope di questo test
        });
    }, 400);

    runner.push([{ forecast_year: 2025 }]);
    vi.advanceTimersByTime(400); // chiamata #1 in volo (seq=1)
    runner.push([{ forecast_year: 2025 }, { forecast_year: 2026 }]);
    vi.advanceTimersByTime(400); // chiamata #2 in volo (seq=2); #1 annullata ma non rigettata dal mock

    expect(postMock).toHaveBeenCalledTimes(2);
    expect(resolvers).toHaveLength(2);

    // La chiamata corrente (#2) risolve per prima...
    resolvers[1]({ forecast_years: ["second"] });
    await Promise.resolve();
    await Promise.resolve();
    expect(state.data).toEqual({ forecast_years: ["second"] });
    expect(state.loading).toBe(false);

    // ...poi la chiamata stale (#1) risolve in ritardo: non deve toccare lo stato.
    resolvers[0]({ forecast_years: ["first-late"] });
    await Promise.resolve();
    await Promise.resolve();
    expect(state.data).toEqual({ forecast_years: ["second"] });
  });

  it("una 200 con error valorizzato non svuota data, e non tocca l'errore di trasporto", async () => {
    const seq = new PreviewSequencer();
    let state: FakeState = { data: null, error: null, loading: false };

    // Il motore si e' fermato al 2026 (fabbisogno scoperto), ma il 2025 e'
    // valido: il backend risponde 200 con ENTRAMBI, non un fallimento secco.
    const response = {
      scenario_id: 1,
      base_year: 2024,
      forecast_years: [
        { year: 2025, income_statement: { ce01_ricavi_vendite: 1000 }, balance_sheet: { sp09_disponibilita_liquide: 50 }, details: {} },
      ],
      error: { year: 2026, message: "Unfunded financing requirement 12.345,67" },
    };
    postMock.mockResolvedValueOnce({ data: response });

    // Stesso wiring del blocco precedente e dell'hook: il ramo `.then` non
    // ispeziona mai `data.error`, quindi non esiste un percorso che possa
    // svuotare `data` quando il campo e' valorizzato.
    const runner = createDebouncedRunner<Record<string, unknown>[]>((rows, signal) => {
      const mine = seq.next();
      state = { ...state, loading: true };
      previewForecast(1, 2, rows, signal)
        .then((data) => {
          if (seq.isCurrent(mine)) state = { data, error: null, loading: false };
        })
        .catch(() => {
          // annullamento/errore: fuori dallo scope di questo test
        });
    }, 400);

    runner.push([{ forecast_year: 2025 }, { forecast_year: 2026 }]);
    vi.advanceTimersByTime(400);
    await Promise.resolve();
    await Promise.resolve();

    // `data` porta l'intera risposta: gli anni popolati COME l'errore annidato.
    expect(state.data).toEqual(response);
    expect((state.data as typeof response).forecast_years).toHaveLength(1);
    expect((state.data as typeof response).forecast_years[0].year).toBe(2025);
    expect((state.data as typeof response).error).toEqual({
      year: 2026,
      message: "Unfunded financing requirement 12.345,67",
    });

    // Una 200 non e' un guasto di trasporto: il canale PreviewState.error
    // (400/rete/annullamento) resta null, anche se il corpo porta un errore.
    expect(state.error).toBeNull();
    expect(state.loading).toBe(false);
  });
});
