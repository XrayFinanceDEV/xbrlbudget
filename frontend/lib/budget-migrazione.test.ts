import { describe, expect, it } from "vitest";
import type { AssumptionsMap } from "@/lib/budget-horizon";
import { isScenarioPrecedente, migraScenario } from "./budget-migrazione";

const anni = [2027, 2028, 2029];
const base = {
  sp16_debiti_breve: "500000", sp16a_debiti_banche_breve: "172500", sp16d_debiti_fornitori_breve: "327500",
  sp17_debiti_lungo: "617500", sp17a_debiti_banche_lungo: "467500", sp17b_debiti_altri_finanz_lungo: "150000",
};
const vecchio = (over: Record<string, unknown> = {}): AssumptionsMap => {
  const out: AssumptionsMap = {};
  for (const y of anni) out[y] = {
    forecast_year: y, revenue_growth_pct: 5, variable_materials_growth_pct: 3, variable_services_growth_pct: 3,
    fixed_materials_growth_pct: 3, fixed_services_growth_pct: 2.5, inflation_pct: null,
    existing_debt_repayment_years: 4, altri_finanz_repayment_years: 5, financing_amount: y === 2028 ? 200000 : 0,
    financing_duration_years: 5, financing_interest_rate: 4, financing_loans: null, pregresso: null, ...over,
  } as AssumptionsMap[number];
  return out;
};

describe("budget-migrazione", () => {
  it("riconosce uno scenario precedente dall'inflazione assente sul primo anno", () => {
    expect(isScenarioPrecedente(vecchio(), anni)).toBe(true);
    expect(isScenarioPrecedente(vecchio({ inflation_pct: 2 }), anni)).toBe(false);
    expect(isScenarioPrecedente({}, anni)).toBe(false);
  });

  it("ricalcola le variabili sui ricavi e tiene le fisse come scritte", () => {
    const { map, ricalcolato } = migraScenario(vecchio(), anni, base, 2026);
    for (const y of anni) {
      expect(map[y].variable_materials_growth_pct).toBe(5);
      expect(map[y].variable_services_growth_pct).toBe(5);
      expect(map[y].fixed_materials_growth_pct).toBe(3);
      expect(map[y].fixed_materials_growth_auto).toBe(false);
      expect(map[y].inflation_pct).toBe(2);
    }
    expect(ricalcolato.some((r) => r.includes("parte variabile"))).toBe(true);
  });

  it("converte «rimborso in N anni» in un contratto con rate uguali e gli altri finanziatori allo stesso modo", () => {
    const { map } = migraScenario(vecchio(), anni, base, 2026);
    const [contratto] = map[2027].financing_loans ?? [];
    expect(contratto).toEqual({
      name: "Debiti verso banche · da «rimborso in 4 anni»", amount: 0, opening_residual: 640000,
      interest_rate: 4, grace_years: 0, balloon_pct: 0, duration_years: null, repayments: [160000, 160000, 160000],
    });
    expect(map[2027].existing_debt_repayment_years).toBeNull();
    expect(map[2027].bank_lines_amount).toBe(0);
    expect(map[2027].bank_lines_rule).toBe("costante");
    expect(map[2027].bank_lines_rate).toBe(4);
    expect(map[2027].other_lenders).toEqual([
      { name: "Altri finanziatori · da «rimborso in 5 anni»", opening_residual: 150000, interest_rate: 0, repayments: [30000, 30000, 30000] },
    ]);
    expect(map[2027].altri_finanz_repayment_years).toBeNull();
  });

  it("converte il finanziamento legacy dell'anno in un contratto nuovo con nome", () => {
    const { map } = migraScenario(vecchio(), anni, base, 2026);
    expect(map[2028].financing_loans).toEqual([
      { name: "Nuovo finanziamento 2028", amount: 200000, opening_residual: 0, duration_years: 5, interest_rate: 4, grace_years: 0, balloon_pct: 0 },
    ]);
    expect(map[2028].financing_amount).toBe(0);
  });

  it("segnala da integrare i passi 1 e 5", () => {
    const { daIntegrare } = migraScenario(vecchio(), anni, base, 2026);
    expect(daIntegrare.map((d) => d.step)).toEqual(["scenario", "patrimoniale-pregresso", "patrimoniale-pregresso"]);
  });

  it("senza debito bancario né altri finanziatori non inventa contratti", () => {
    const { map } = migraScenario(vecchio(), anni, { ...base, sp16a_debiti_banche_breve: "0", sp17a_debiti_banche_lungo: "0", sp16_debiti_breve: "327500", sp17_debiti_lungo: "150000" }, 2026);
    expect(map[2027].financing_loans).toBeNull();
    expect(map[2027].bank_lines_amount).toBe(0);
  });
});
