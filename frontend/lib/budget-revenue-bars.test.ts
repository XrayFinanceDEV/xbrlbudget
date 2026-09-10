import { describe, expect, it } from "vitest";
import type { ForecastPreviewYear } from "@/types/api";
import { revenueBarGeometry } from "./budget-revenue-bars";

const year = (v: number): ForecastPreviewYear => ({
  year: 2027, income_statement: { ce01_ricavi_vendite: v }, balance_sheet: {},
  details: { ce05_fixed: null, ce05_variable: null, ce06_fixed: null, ce06_variable: null,
    dso_applied: 0, dio_applied: 0, dpo_applied: 0, pregresso: { crediti_commerciali: { opening: 0, closed: 0, writeoff: 0, residual_short: 0, residual_long: 0, generated: 0, mode: "legacy" }, debiti_fornitori: { opening: 0, closed: 0, writeoff: 0, residual_short: 0, residual_long: 0, generated: 0, mode: "legacy" }, debiti_tributari: { opening: 0, closed: 0, writeoff: 0, residual_short: 0, residual_long: 0, generated: 0, mode: "legacy" }, debiti_previdenziali: { opening: 0, closed: 0, writeoff: 0, residual_short: 0, residual_long: 0, generated: 0, mode: "legacy" }, altri_debiti: { opening: 0, closed: 0, writeoff: 0, residual_short: 0, residual_long: 0, generated: 0, mode: "legacy" } }, imposte: { current_tax: 0, saldo_paid: 0, acconti_paid: 0, rate_paid: 0, generated_debt: 0, generated_credit: 0, opening_credit_left: 0, mode: "manual" }, degenerate_turnover_ratio: [], pregresso_ignored: [], indicizzazione: {}, indicizzazione_ignorata: [], svalutazioni_cumulate: 0, residuo_quadratura: [], pregresso_writeoff_ignored: [] },
});

describe("revenueBarGeometry", () => {
  it("un rettangolo per valore, base compresa, nello stesso ordine", () => {
    const bars = revenueBarGeometry(1000, [year(1100), year(1210)]);
    expect(bars.map((b) => b.value)).toEqual([1000, 1100, 1210]);
    expect(bars.map((b) => b.isBase)).toEqual([true, false, false]);
  });

  it("altezza proporzionale su [min*0.9, max*1.05], il minimo vicino al fondo e il massimo vicino alla cima", () => {
    const bars = revenueBarGeometry(1000, [year(1100), year(1210)]);
    // min = 1000*0.9 = 900, max = 1210*1.05 = 1270.5, span = 370.5
    const min = 1000 * 0.9, max = 1210 * 1.05, span = max - min;
    expect(bars[0].height).toBeCloseTo(((1000 - min) / span) * 56, 6);
    expect(bars[2].height).toBeCloseTo(((1210 - min) / span) * 56, 6);
    // y + height = 56 sempre (base del grafico allineata in fondo)
    for (const b of bars) expect(b.y + b.height).toBeCloseTo(56, 6);
  });

  it("un solo valore non nullo: altezza proporzionale sulla stessa scala [min*0.9, max*1.05], non l'intera altezza", () => {
    // min = max = 1000, quindi la scala e' comunque [900, 1050] (span 150): un
    // solo valore non e' un caso degenere, la sua altezza resta a 2/3 di 56.
    const bars = revenueBarGeometry(1000, []);
    expect(bars).toEqual([{ value: 1000, height: (100 / 150) * 56, y: 56 - (100 / 150) * 56, isBase: true }]);
  });

  it("scala di ampiezza zero (tutti i valori a zero): riempie tutta l'altezza invece di dividere per zero", () => {
    const bars = revenueBarGeometry(0, [year(0)]);
    expect(bars.every((b) => b.height === 56 && b.y === 0)).toBe(true);
  });
});
