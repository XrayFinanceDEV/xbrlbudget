// Banco di triage dei rilievi AMBIENTA — lato wizard. Spec: docs/superpowers/specs/2026-09-25-triage-rilievi-ambienta-design.md.
// Oracolo = comportamento che il consulente si aspetta: un test rosso vuol dire che il difetto c'è.
//
// Import statici (ruling del fix finale): tutte le funzioni usate qui esistono già su 62bfed1 (verificato con
// `git show 62bfed1:frontend/lib/<file>.ts`), quindi tools/triage_rilievi.py può copiare questo file sul commit
// vecchio senza che l'intero file esploda. Un import che un giorno mancasse su 62bfed1 farebbe fallire la
// raccolta dell'intero file su quel lato: il verdetto del wizard su 62bfed1 va allora letto dall'esito del file.
import { describe, expect, it } from "vitest";

import { variableGrowthDeviation } from "@/lib/budget-costi-step";
import { type AssumptionsMap, withRevenueGrowth } from "@/lib/budget-horizon";
import { accontiRow } from "@/lib/budget-imposte-step";
import { minorFieldsRows } from "@/lib/budget-circolante-step";
import { withSpRule } from "@/lib/budget-sp-manuale";

const asMap = (m: Record<number, Record<string, unknown>>) => m as unknown as AssumptionsMap;

describe("rilievi AMBIENTA · wizard", () => {
  // A01 (foglio: «Scostamento −5 punti sulle materie prime ignorato»). Il percorso VERO di un cambio dei ricavi
  // non è variableGrowthChange + variableGrowthDeviation (il vecchio test di questo banco, un falso positivo):
  // è updateAssumption → withRevenueGrowth (hooks/use-scenario-assumptions.ts, lib/budget-horizon.ts), che
  // riscrive la parte variabile come nuovi ricavi + (variabile − vecchi ricavi), quindi lo scostamento resta.
  // Lo fissa già budget-horizon.test.ts («withRevenueGrowth (Task 10)» e l'idratazione con _auto=false).
  it("A01 lo scostamento digitato resta lo scostamento dopo un cambio dei ricavi", () => {
    // Ricavi +5, scostamento −5 → materie 0, casella automatica spenta (come la salva il passo Costi).
    const salvata = asMap({ 2027: {
      revenue_growth_pct: 5, variable_materials_growth_pct: 0, variable_materials_growth_auto: false,
    } });
    // I ricavi passano a +7 dopo: il consulente si aspetta che lo scostamento resti −5 (materie +2).
    const dopo = withRevenueGrowth(salvata, 2027, 7)[2027];
    expect(dopo.variable_materials_growth_pct).toBe(2);
    expect(variableGrowthDeviation(dopo.variable_materials_growth_pct as number, 7)).toBe("-5");
  });

  it("A03 il passo Imposte ha un campo per anno collegato a tax_advances_paid", () => {
    expect(accontiRow({ forecast_years: [] } as never, 100).field).toBe("tax_advances_paid");
  });

  // A05 · CARATTERIZZAZIONE (verde = comportamento di oggi). Il motore con sp04 senza regola tiene il saldo
  // costante (tests/test_rilievi_ambienta.py, test_A05_…); ma il wizard non produce mai quello stato quando la
  // voce aveva già la regola «ricavi»: passare a «Manuale» congela in sp_overrides i valori dell'anteprima, che
  // sono proprio quelli cresciuti coi ricavi (52.550 → 55.178 / 58.488 / 62.582, i numeri del consulente).
  // È voluto (beb33c5, budget-sp-manuale.test.ts «scegliere Manuale congela i valori dell'anteprima per anno»):
  // il sintomo del consulente nasce da una decisione del proprietario, non da un difetto del motore.
  it("A05 passare a Manuale da «ricavi» congela in sp_overrides la crescita coi ricavi", () => {
    const years = [2027, 2028, 2029];
    const field = "sp04_immob_finanziarie";
    const conRicavi = asMap({
      2027: { sp_indexing: { sp04: "ricavi" } },
      2028: { sp_indexing: { sp04: "ricavi" } },
      2029: { sp_indexing: { sp04: "ricavi" } },
    });
    const c = (x: number) => Math.round(x * 100) / 100;
    const anteprima: Record<number, number> = {
      2027: c(52550 * 1.05), 2028: c(52550 * 1.05 * 1.06), 2029: c(52550 * 1.05 * 1.06 * 1.07),
    };
    const manuale = withSpRule(conRicavi, years, "sp04", field, "sp04_growth_pct", null, anteprima);
    for (const y of years) {
      expect(manuale[y].sp_indexing).toBeNull();
      expect(manuale[y].sp_overrides?.[field]).toBe(anteprima[y]);
    }
    expect(years.map((y) => Math.round(Number(manuale[y].sp_overrides?.[field])))).toEqual([55178, 58488, 62582]);
  });

  // Ruling (controller): l'oracolo del brief (`riga.driver` null con casella spenta e indicizzazione
  // {sp16f:"ricavi"}) sarebbe rosso per uno stato legittimo — a casella spenta la tendina e' l'unico
  // comando attivo, quindi un driver non nullo e' corretto, non un difetto. Il rilievo vero del
  // consulente e' un altro: lo schermo diceva «Cresce con il costo del personale» mentre l'output
  // cresceva coi ricavi, casella NON spuntata. Il test verifica quindi che l'etichetta di sp16f
  // concordi con ciò che il motore farà davvero: a casella spenta la tendina governa e l'etichetta
  // non deve nominare «personale»; a casella accesa e' la casella a governare e l'etichetta deve
  // nominare «personale». Il doppio comando (casella + tendina, lib/budget-circolante-step.ts:229-232)
  // resta: confermato per ispezione, non da questo test.
  it("A06 l'etichetta dei previdenziali dice quello che fa il motore", () => {
    const baseBs = { sp16f_debiti_previdenza_breve: 163536.55 } as never;

    // Casella spenta, tendina su "ricavi": il motore segue i ricavi (indicizzazione esplicita).
    const spenta = minorFieldsRows(baseBs, { sp16f: "ricavi" }, false, []) as any[];
    const rigaSpenta = spenta.find((r) => r.code === "sp16f" || r.balanceField === "sp16f_debiti_previdenza_breve");
    expect(rigaSpenta).toBeDefined();
    expect(String(rigaSpenta.andamento ?? "")).not.toMatch(/personale/);

    // Casella accesa: il motore ignora la tendina e segue il personale.
    const accesa = minorFieldsRows(baseBs, {}, true, []) as any[];
    const rigaAccesa = accesa.find((r) => r.code === "sp16f" || r.balanceField === "sp16f_debiti_previdenza_breve");
    expect(rigaAccesa).toBeDefined();
    expect(String(rigaAccesa.andamento ?? "")).toMatch(/personale/);
  });
});
