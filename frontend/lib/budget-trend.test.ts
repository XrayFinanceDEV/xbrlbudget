import { describe, expect, it } from "vitest";
import type { IncomeStatement } from "@/types/api";
import { blendedRate, calculateTrend, trendAssumptions } from "./budget-trend";

const inc = (v: number) => ({ income: { ce01_ricavi_vendite: String(v), ce04_altri_ricavi: "0", ce05_materie_prime: "0",
  ce06_servizi: "0", ce07_godimento_beni: "0", ce08_costi_personale: "0", ce12_oneri_diversi: "0" } as unknown as IncomeStatement,
  balance: {} as never });

describe("budget-trend", () => {
  it("tendenza = variazione % fra i due ultimi anni", () => {
    const h = { 2024: inc(100), 2025: inc(110) };
    expect(calculateTrend(h, 2024, 2025, (i) => parseFloat(i.ce01_ricavi_vendite))).toBeCloseTo(10);
    expect(calculateTrend(h, 2023, 2025, (i) => parseFloat(i.ce01_ricavi_vendite))).toBeNull();
  });
  it("v1 = 0 -> null (variazione da zero non e' definita)", () => {
    const h = { 2024: inc(0), 2025: inc(110) };
    expect(calculateTrend(h, 2024, 2025, (i) => parseFloat(i.ce01_ricavi_vendite))).toBeNull();
  });
  it("v1 negativo passa da Math.abs al denominatore", () => {
    const h = { 2024: inc(-100), 2025: inc(-50) };
    // ((v2 - v1) / Math.abs(v1)) * 100 = ((-50 - -100) / 100) * 100 = 50
    expect(calculateTrend(h, 2024, 2025, (i) => parseFloat(i.ce01_ricavi_vendite))).toBeCloseTo(50);
  });
  it("il tasso smussato parte dalla media e converge linearmente all'inflazione", () => {
    // blended = (10 + 2) / 2 = 6; su un piano di 3 anni pesa 0, 1/2, 1 verso l'inflazione (2)
    expect(blendedRate(10, 2, 0, 3)).toBe(6);
    expect(blendedRate(10, 2, 1, 3)).toBe(4);
    expect(blendedRate(10, 2, 2, 3)).toBe(2);
    expect(blendedRate(null, 2, 0, 3)).toBe(2);
  });
  it("trendAssumptions scrive ogni campo delle TREND_ITEMS per ogni anno", () => {
    const out = trendAssumptions([2024, 2025], [2026, 2027], { 2024: inc(100), 2025: inc(110) }, 2);
    expect(Object.keys(out)).toEqual(["2026", "2027"]);
    expect(out[2026].revenue_growth_pct).toBeGreaterThan(2);
    expect(out[2026].variable_materials_growth_pct).toBeDefined();
  });
});
