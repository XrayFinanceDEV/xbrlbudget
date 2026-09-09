import { describe, expect, it, vi } from "vitest";
import { PreviewSequencer, createDebouncedRunner } from "./budget-preview-queue";

describe("PreviewSequencer", () => {
  it("solo l'ultimo numero e' corrente", () => {
    const s = new PreviewSequencer();
    const a = s.next(), b = s.next();
    expect(s.isCurrent(a)).toBe(false);
    expect(s.isCurrent(b)).toBe(true);
  });
});

describe("createDebouncedRunner", () => {
  it("coalesce le chiamate entro il ritardo e annulla quella in volo", () => {
    vi.useFakeTimers();
    const run = vi.fn<(p: number, s: AbortSignal) => void>();
    const runner = createDebouncedRunner(run, 400);
    runner.push(1); runner.push(2);
    vi.advanceTimersByTime(399);
    expect(run).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(run).toHaveBeenCalledTimes(1);
    expect(run.mock.calls[0][0]).toBe(2);
    const firstSignal = run.mock.calls[0][1];
    runner.push(3);
    vi.advanceTimersByTime(400);
    expect(firstSignal.aborted).toBe(true);
    expect(run).toHaveBeenCalledTimes(2);
    runner.cancel();
    expect(run.mock.calls[1][1].aborted).toBe(true);
    vi.useRealTimers();
  });

  /**
   * Riproduce in node la regola del browser che nessun test vedeva: i timer di
   * `window` invocati con un ricevitore diverso da `window` lanciano
   * `TypeError: Illegal invocation`. Il difetto reale era
   * `timers.setTimeout(...)` su un oggetto che teneva i globali — l'anteprima
   * crollava all'ingresso di OGNI passo che la usa, e la suite restava verde.
   * Trovato col browser (`lib/budget-preview-queue.ts:37` nella traccia).
   *
   * I timer di node non controllano il ricevitore, quindi il controllo va
   * simulato: si sostituisce il globale con una versione severa. I parametri
   * di default sono valutati a ogni chiamata, quindi la versione severa e'
   * quella che il codice sotto prova legge davvero.
   */
  it("i timer di default si chiamano nudi, non come metodi di un oggetto", () => {
    const realSet = globalThis.setTimeout;
    const realClear = globalThis.clearTimeout;
    const severo = <F extends (...a: never[]) => unknown>(reale: F) =>
      function (this: unknown, ...args: Parameters<F>) {
        if (this !== undefined && this !== globalThis) throw new TypeError("Illegal invocation");
        return (reale as (...a: Parameters<F>) => unknown)(...args);
      };
    globalThis.setTimeout = severo(realSet) as unknown as typeof setTimeout;
    globalThis.clearTimeout = severo(realClear) as unknown as typeof clearTimeout;
    try {
      const runner = createDebouncedRunner<number>(() => {}, 400);
      expect(() => runner.push(1)).not.toThrow();
      // `cancel` passa per clearTimeout: anche quello va chiamato nudo.
      expect(() => runner.cancel()).not.toThrow();
    } finally {
      globalThis.setTimeout = realSet;
      globalThis.clearTimeout = realClear;
    }
  });
});
