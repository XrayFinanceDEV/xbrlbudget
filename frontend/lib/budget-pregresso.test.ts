import { describe, expect, it } from "vitest";
import type { BalanceSheet } from "@/types/api";
import { equalInstalments, openingMasses, pctToAmount, residualAfter, validatePregresso, withAmount } from "./budget-pregresso";

const bs = { sp06_crediti_breve: "500", sp06e_crediti_tributari_breve: "20", sp06f_imposte_anticipate_breve: "10",
  sp07_crediti_lungo: "40", sp07e_crediti_tributari_lungo: "0", sp07f_imposte_anticipate_lungo: "0",
  sp16d_debiti_fornitori_breve: "300", sp17d_debiti_fornitori_lungo: "0", sp16e_debiti_tributari_breve: "61",
  sp17e_debiti_tributari_lungo: "35", sp16f_debiti_previdenza_breve: "41", sp17f_debiti_previdenza_lungo: "0",
  sp16g_altri_debiti_breve: "58", sp17g_altri_debiti_lungo: "0" } as unknown as BalanceSheet;

describe("budget-pregresso", () => {
  it("masse di apertura come la spec §3.1", () => {
    expect(openingMasses(bs)).toEqual({ crediti_commerciali: 510, debiti_fornitori: 300, debiti_tributari: 96,
      debiti_previdenziali: 41, altri_debiti: 58 });
  });
  it("rate uguali con i centesimi sull'ultima, residuo, percentuali", () => {
    expect(equalInstalments(100, 3)).toEqual([33.33, 33.33, 33.34]);
    expect(residualAfter({ opening: 1000, amounts: [800], writeoff: [50] }, 0)).toBe(150);
    expect(pctToAmount(33.333, 1000)).toBe(333.33);
    expect(withAmount({ opening: 100, amounts: [10] }, 2, 5)).toEqual({ opening: 100, amounts: [10, 0, 5] });
  });
  it("validazione: massa, orizzonte, tributari", () => {
    const masses = openingMasses(bs);
    expect(validatePregresso({ debiti_fornitori: { opening: 300, amounts: [200, 200] } }, masses, 3)[0]).toMatch(/supera/);
    expect(validatePregresso({ debiti_fornitori: { opening: 299, amounts: [] } }, masses, 3)[0]).toMatch(/apertura/);
    expect(validatePregresso({ altri_debiti: { opening: 58, amounts: [1, 1, 1, 1] } }, masses, 3)[0]).toMatch(/orizzonte/);
    expect(validatePregresso({ debiti_tributari: { opening: 96, saldo: 50, rateizzato: 40, amounts: [], acconto_pct: 100 } }, masses, 3)[0]).toMatch(/saldo \+ rateizzato/);
    expect(validatePregresso({ debiti_tributari: { opening: 96, saldo: 61, rateizzato: 35, amounts: [12, 12, 11], acconto_pct: 100 } }, masses, 3)).toEqual([]);
  });
});
