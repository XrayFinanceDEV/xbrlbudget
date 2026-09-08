import { describe, expect, it } from "vitest";
import type { BalanceSheet, ForecastPreviewResponse, ForecastPreviewYear, IncomeStatement } from "@/types/api";
import type { AssumptionsMap } from "@/lib/budget-horizon";
import {
  DEFAULT_TAX_RATE,
  impostePreview,
  spTributariRows,
  taxRateInputDisplay,
  taxRateValue,
} from "./budget-imposte-step";

const baseInc = {
  ce01_ricavi_vendite: "1000", ce04_altri_ricavi: "0", ce05_materie_prime: "400", ce06_servizi: "200",
  ce07_godimento_beni: "0", ce08_costi_personale: "150", ce12_oneri_diversi: "0", ce09_ammortamenti: "40",
  ce15_oneri_finanziari: "10", ce20_imposte: "30",
} as unknown as IncomeStatement;

const year = (y: number, over: Partial<ForecastPreviewYear> = {}): ForecastPreviewYear => ({
  year: y,
  income_statement: {
    ce01_ricavi_vendite: 1100, ce04_altri_ricavi: 0, ce05_materie_prime: 430, ce06_servizi: 210,
    ce07_godimento_beni: 0, ce08_costi_personale: 155, ce12_oneri_diversi: 0, ce09_ammortamenti: 40,
    ce15_oneri_finanziari: 10, ce20_imposte: 33,
  },
  balance_sheet: { sp16e_debiti_tributari_breve: 12 },
  details: { ce05_fixed: null, ce05_variable: null, ce06_fixed: null, ce06_variable: null, dso_applied: 60, dio_applied: 45, dpo_applied: 78 },
  ...over,
});

const response = (years: ForecastPreviewYear[]): ForecastPreviewResponse =>
  ({ scenario_id: 1, base_year: 2026, forecast_years: years, error: null });

const asMap = (m: Record<number, Record<string, unknown>>): AssumptionsMap => m as unknown as AssumptionsMap;

describe("taxRateValue", () => {
  it("nessun anno => value null, non uneven", () => {
    expect(taxRateValue(asMap({}), [])).toEqual({ value: null, uneven: false });
  });

  it("mostra il valore del primo anno previsto", () => {
    const v = taxRateValue(asMap({ 2027: { tax_rate: 30 }, 2028: { tax_rate: 30 } }), [2027, 2028]);
    expect(v).toEqual({ value: 30, uneven: false });
  });

  it("anni non concordi => uneven true", () => {
    const v = taxRateValue(asMap({ 2027: { tax_rate: 30 }, 2028: { tax_rate: 25 } }), [2027, 2028]);
    expect(v).toEqual({ value: 30, uneven: true });
  });
});

describe("taxRateInputDisplay", () => {
  it("valore assente => casella vuota", () => {
    expect(taxRateInputDisplay({ value: null, uneven: false })).toBe("");
  });

  it("valore uguale al default 27,9 => casella vuota (non forzata)", () => {
    expect(taxRateInputDisplay({ value: DEFAULT_TAX_RATE, uneven: false })).toBe("");
  });

  it("un valore diverso dal default si mostra per intero", () => {
    expect(taxRateInputDisplay({ value: 24, uneven: false })).toBe(24);
    expect(taxRateInputDisplay({ value: 0, uneven: false })).toBe(0); // zero vero, non "vuoto"
  });
});

describe("spTributariRows", () => {
  it("anno base assente => baseLabel a trattino, mai zero", () => {
    const rows = spTributariRows(undefined);
    expect(rows.map((r) => r.baseLabel)).toEqual(["—", "—"]);
  });

  it("sp16e/sp17e esistono gia' nell'anno base: la colonna base porta l'importo vero", () => {
    const baseBs = {
      sp16e_debiti_tributari_breve: "40", sp17e_debiti_tributari_lungo: "10",
    } as unknown as BalanceSheet;
    const rows = spTributariRows(baseBs);
    expect(rows).toEqual([
      { field: "sp16e_growth_pct", label: "Debiti tributari entro %", baseLabel: "40 €" },
      { field: "sp17e_growth_pct", label: "Debiti tributari oltre %", baseLabel: "10 €" },
    ]);
  });

  it("uno zero vero nell'anno base resta zero, non trattino", () => {
    const baseBs = {
      sp16e_debiti_tributari_breve: "0", sp17e_debiti_tributari_lungo: "10",
    } as unknown as BalanceSheet;
    expect(spTributariRows(baseBs)[0].baseLabel).toBe("0 €");
  });
});

describe("impostePreview", () => {
  it("senza anno base o senza risposta: nessuna riga", () => {
    expect(impostePreview(undefined, response([year(2027)]))).toEqual({ years: [], rows: [] });
    expect(impostePreview(baseInc, null)).toEqual({ years: [], rows: [] });
  });

  it("gli anni sono quelli che il motore ha davvero prodotto", () => {
    const p = impostePreview(baseInc, response([year(2027)]));
    expect(p.years).toEqual([2027]);
    expect(p.rows.length).toBeGreaterThan(0);
  });

  it("un calcolo fermato a meta' mostra solo gli anni prodotti, non quelli richiesti", () => {
    const p = impostePreview(baseInc, response([year(2027)])); // 2028 non prodotto (es. fabbisogno scoperto al passo 6)
    expect(p.years).toEqual([2027]);
  });
});
