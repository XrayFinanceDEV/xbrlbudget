import { describe, it, expect } from "vitest";
import { turnoverRatio, scaledOrCarried } from "@/lib/pratica-turnover";

describe("turnoverRatio", () => {
  it("calcola il rapporto quando la base spiega la giacenza", () => {
    // 250.000 di crediti su 1.000.000 di ricavi = 91 giorni.
    expect(turnoverRatio(250_000, 1_000_000)).toBeCloseTo(0.25, 10);
  });

  it("rifiuta la base nulla o negativa", () => {
    expect(turnoverRatio(250_000, 0)).toBeNull();
    expect(turnoverRatio(250_000, -5)).toBeNull();
  });

  it("rifiuta il denominatore trascurabile (il caso AIC SRL)", () => {
    // ce01 = 100,92 contro 1.035.249,26 di crediti: 10.258x.
    expect(turnoverRatio(1_035_249.26, 100.92)).toBeNull();
  });

  it("accetta esattamente un anno di giacenza e rifiuta oltre", () => {
    expect(turnoverRatio(1_000, 1_000)).toBe(1);
    expect(turnoverRatio(1_000.01, 1_000)).toBeNull();
  });
});

describe("scaledOrCarried", () => {
  it("scala normalmente quando il rapporto è sano", () => {
    // 1.200.000 * (250.000/1.000.000) = 300.000
    expect(scaledOrCarried(250_000, 1_000_000, 1_200_000, 999)).toBeCloseTo(300_000, 6);
  });

  it("riporta la giacenza infrannuale quando il rapporto è degenere", () => {
    // Senza guardia: 16.249 * 10.258 = 166,68 M.
    const risultato = scaledOrCarried(1_035_249.26, 100.92, 16_249, 1_100_048.69);
    expect(risultato).toBe(1_100_048.69);
    expect(risultato).toBeLessThan(10_000_000);
  });
});
