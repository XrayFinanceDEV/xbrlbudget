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
});
