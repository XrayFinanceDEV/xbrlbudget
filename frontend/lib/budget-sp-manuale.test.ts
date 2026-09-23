import { describe, expect, it } from "vitest";
import type { AssumptionsMap } from "./budget-horizon";
import { manualSpValue, previewTotalAssets, withManualSpAmount, withSpRule } from "./budget-sp-manuale";

const years = [2027, 2028];
const field = "sp04_immob_finanziarie";
const growth = "sp04_growth_pct";

describe("valori manuali delle voci patrimoniali", () => {
  it("ricava il totale attivo dell'anteprima dalle voci SP, dove total_assets non è presente", () => {
    const balance = {
      sp01_crediti_soci: 0, sp02_immob_immateriali: 20, sp03_immob_materiali: 30,
      sp04_immob_finanziarie: 50, sp05_rimanenze: 40, sp06_crediti_breve: 60,
      sp07_crediti_lungo: 10, sp08_attivita_finanziarie: 0,
      sp09_disponibilita_liquide: 90, sp10_ratei_risconti_attivi: 20,
    };
    expect(previewTotalAssets(balance)).toBe(320);
    expect(previewTotalAssets(undefined)).toBeNull();
    expect(previewTotalAssets({ sp04_immob_finanziarie: 50 })).toBeNull();
  });

  it("mostra il calcolo finché non c'è un importo manuale, incluso lo zero", () => {
    const rows: AssumptionsMap = { 2027: { sp_overrides: { [field]: 0 } }, 2028: {} };
    expect(manualSpValue(rows, 2027, field, 100)).toBe(0);
    expect(manualSpValue(rows, 2028, field, 120)).toBe(120);
  });

  it("al primo importo fissa entrambi gli anni, lasciando intatti gli altri override", () => {
    const rows: AssumptionsMap = {
      2027: { sp_indexing: { sp04: "ricavi" }, sp04_growth_pct: 4,
        sp_overrides: { sp08_attivita_finanziarie: 9 } },
      2028: { sp_indexing: { sp04: "ricavi", sp10: "personale" }, sp04_growth_pct: 5 },
    };
    const next = withManualSpAmount(rows, years, 2027, "sp04", field, growth, 60000, { 2027: 55000, 2028: 58000 });
    expect(next[2027].sp_overrides).toEqual({ sp08_attivita_finanziarie: 9, [field]: 60000 });
    expect(next[2028].sp_overrides).toEqual({ [field]: 58000 });
    expect(next[2028].sp_indexing).toEqual({ sp10: "personale" });
    expect(next[2027].sp04_growth_pct).toBeNull();
  });

  it("scegliere un driver elimina importi e vecchie percentuali solo per la voce scelta", () => {
    const rows: AssumptionsMap = { 2027: {
      sp_overrides: { [field]: 60000, sp08_attivita_finanziarie: 9 }, sp04_growth_pct: 4,
    }, 2028: { sp_overrides: { [field]: 62000 } } };
    const next = withSpRule(rows, years, "sp04", field, growth, "ricavi", {});
    expect(next[2027].sp_overrides).toEqual({ sp08_attivita_finanziarie: 9 });
    expect(next[2028].sp_overrides).toBeNull();
    expect(next[2027].sp_indexing).toEqual({ sp04: "ricavi" });
    expect(next[2027].sp04_growth_pct).toBeNull();
  });

  it("scegliere Manuale congela i valori dell'anteprima per anno", () => {
    const rows: AssumptionsMap = { 2027: { sp_indexing: { sp04: "ricavi" } }, 2028: { sp_indexing: { sp04: "ricavi" } } };
    const next = withSpRule(rows, years, "sp04", field, growth, null, { 2027: 55000, 2028: 58000 });
    expect(next[2027].sp_indexing).toBeNull();
    expect(next[2027].sp_overrides?.[field]).toBe(55000);
    expect(next[2028].sp_overrides?.[field]).toBe(58000);
  });
});
