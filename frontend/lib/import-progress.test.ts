import { describe, expect, it } from "vitest";
import {
  DURATA_ATTESA_IMPORT_SECONDI,
  messaggioImport,
  percentualeImport,
} from "./import-progress";

describe("percentualeImport", () => {
  it("parte da zero e ha 120 s di default", () => {
    expect(DURATA_ATTESA_IMPORT_SECONDI).toBe(120);
    expect(percentualeImport(0)).toBe(0);
    expect(percentualeImport(-5)).toBe(0);
  });

  it("sale lineare fino al 90% alla durata attesa", () => {
    expect(percentualeImport(60)).toBeCloseTo(45);
    expect(percentualeImport(120)).toBeCloseTo(90);
    expect(percentualeImport(30, 60)).toBeCloseTo(45);
  });

  it("oltre la durata attesa cresce ma non arriva mai a 100", () => {
    const a = percentualeImport(180);
    const b = percentualeImport(600);
    expect(a).toBeGreaterThan(90);
    expect(b).toBeGreaterThan(a);
    expect(percentualeImport(1e6)).toBeLessThanOrEqual(99);
  });

  it("una durata attesa non valida non produce NaN", () => {
    expect(percentualeImport(10, 0)).toBe(0);
    expect(percentualeImport(Number.NaN)).toBe(0);
  });
});

describe("messaggioImport", () => {
  it("dice il tempo trascorso e l'attesa tipica", () => {
    expect(messaggioImport(45)).toBe(
      "Lettura del bilancio in corso · 45 s (di solito circa 2 minuti)",
    );
  });

  it("oltre la durata attesa avvisa che sta impiegando più del solito", () => {
    expect(messaggioImport(150)).toContain("più del solito");
  });
});
