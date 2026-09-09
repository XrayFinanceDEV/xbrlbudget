import { describe, expect, it } from "vitest";
import type { IncomeStatement } from "@/types/api";
import { blendedRate, calculateTrend, shouldSeedTrend, trendAssumptions } from "./budget-trend";

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

describe("shouldSeedTrend — il cancello guarda i dati, non l'elenco degli anni", () => {
  const anni = [2024, 2025];
  const dati = { 2024: inc(100), 2025: inc(110) };

  it("scenario nuovo con i due anni CARICATI: si precompila", () => {
    expect(shouldSeedTrend(true, anni, dati)).toBe(true);
  });

  it("elenco pieno ma dati non ancora arrivati: NON si precompila", () => {
    // Il caso che si autobloccava: `historicalYears` e' gia' lungo due al primo
    // render, `historical` arriva dopo. Precompilare qui scrive l'inflazione su
    // ogni campo, e il flag one-shot impedisce per sempre la ripetizione.
    const perche = "col solo elenco degli anni trendAssumptions scrive l'inflazione ovunque";
    expect(shouldSeedTrend(true, anni, {}), perche).toBe(false);
    expect(trendAssumptions(anni, [2026], {}, 2)[2026].revenue_growth_pct, perche).toBe(2);
  });

  it("un solo anno caricato dei due non e' una tendenza", () => {
    expect(shouldSeedTrend(true, anni, { 2025: inc(110) })).toBe(false);
    expect(shouldSeedTrend(true, anni, { 2024: inc(100) })).toBe(false);
  });

  it("guarda gli ULTIMI due anni, quelli che trendAssumptions legge davvero", () => {
    const tre = [2023, 2024, 2025];
    expect(shouldSeedTrend(true, tre, { 2023: inc(90), 2024: inc(100) })).toBe(false);
    expect(shouldSeedTrend(true, tre, { 2024: inc(100), 2025: inc(110) })).toBe(true);
  });

  it("scenario gia' salvato, o meno di due anni: mai", () => {
    expect(shouldSeedTrend(false, anni, dati)).toBe(false);
    expect(shouldSeedTrend(true, [2025], { 2025: inc(110) })).toBe(false);
    expect(shouldSeedTrend(true, [], {})).toBe(false);
  });
});
