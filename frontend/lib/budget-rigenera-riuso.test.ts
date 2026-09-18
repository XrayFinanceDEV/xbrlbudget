import { describe, expect, it } from "vitest";
import type { BalanceSheet, BudgetAssumptions, BulkAssumptionsResult } from "@/types/api";
import { rigeneraBudgetRiusato } from "./budget-rigenera-riuso";

// Anno base DOPO la ripromozione: i crediti commerciali sono scesi a 439.293,74.
const baseBs = {
  sp06_crediti_breve: "445226.74", sp06e_crediti_tributari_breve: "5933", sp06f_imposte_anticipate_breve: "0",
  sp07_crediti_lungo: "0",
} as unknown as BalanceSheet;

const riga = (year: number, extra: Partial<BudgetAssumptions> = {}) =>
  ({ id: year, scenario_id: 20, forecast_year: year, revenue_growth_pct: "5", inflation_pct: "2", pregresso: null, ...extra }) as unknown as BudgetAssumptions;

function deps(rows: BudgetAssumptions[], result: Partial<BulkAssumptionsResult> = { forecast_generated: true }) {
  const sent: Record<string, unknown>[][] = [];
  return {
    sent,
    d: {
      getAssumptions: async () => rows,
      getBaseBalanceSheet: async () => baseBs,
      bulkSave: async (r: Record<string, unknown>[]) => { sent.push(r); return result as BulkAssumptionsResult; },
    },
  };
}

describe("rigeneraBudgetRiusato", () => {
  it("scenario nuovo, senza ipotesi: niente da rigenerare", async () => {
    const { d, sent } = deps([]);
    expect(await rigeneraBudgetRiusato(20, d)).toBeNull();
    expect(sent).toEqual([]);
  });

  it("rimanda le ipotesi salvate e riallinea l'apertura del pregresso al nuovo anno base", async () => {
    const pregresso = { crediti_commerciali: { opening: 443912.8, amounts: [443912.8, 0, 0], writeoff: null, non_incassato: false } };
    const { d, sent } = deps([riga(2027, { pregresso } as never), riga(2028), riga(2029)]);
    expect(await rigeneraBudgetRiusato(20, d)).toEqual({ ok: true, message: "Previsionale ricalcolato sul nuovo anno base" });
    expect(sent).toHaveLength(1);
    expect(sent[0].map((r) => r.forecast_year)).toEqual([2027, 2028, 2029]);
    expect(sent[0][0].pregresso).toMatchObject({ crediti_commerciali: { opening: 439293.74, amounts: [439293.74, 0, 0] } });
    expect(sent[0][1].revenue_growth_pct).toBe(5);
  });

  it("un previsionale rifiutato non e' un successo: conta forecast_generated, non il 200", async () => {
    const { d } = deps([riga(2027)], { forecast_generated: false, message: "Fabbisogno finanziario scoperto di 1.000,00" });
    const esito = await rigeneraBudgetRiusato(20, d);
    expect(esito?.ok).toBe(false);
    expect(esito?.message).toContain("Fabbisogno");
  });

  it("uno scenario da migrare non si salva da qui", async () => {
    const { d, sent } = deps([riga(2027, { inflation_pct: null } as never)]);
    expect((await rigeneraBudgetRiusato(20, d))?.ok).toBe(false);
    expect(sent).toEqual([]);
  });
});
