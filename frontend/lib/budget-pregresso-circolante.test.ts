import { describe, expect, it } from "vitest";
import type { BalanceSheet } from "@/types/api";
import { amountToPct, equalInstalments, openingMasses, pctToAmount, residualAfter, validatePregresso, withAmount } from "./budget-pregresso-circolante";

const bs = { sp06_crediti_breve: "500", sp06e_crediti_tributari_breve: "20", sp06f_imposte_anticipate_breve: "10",
  sp07_crediti_lungo: "40", sp07e_crediti_tributari_lungo: "0", sp07f_imposte_anticipate_lungo: "0",
  sp16d_debiti_fornitori_breve: "300", sp17d_debiti_fornitori_lungo: "0", sp16e_debiti_tributari_breve: "61",
  sp17e_debiti_tributari_lungo: "35", sp16f_debiti_previdenza_breve: "41", sp17f_debiti_previdenza_lungo: "0",
  sp16g_altri_debiti_breve: "58", sp17g_altri_debiti_lungo: "0" } as unknown as BalanceSheet;

describe("budget-pregresso-circolante", () => {
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

  it("amountToPct: incidenza, e apertura nulla non e' un'incidenza di zero", () => {
    expect(amountToPct(50, 200)).toBe(25);
    expect(amountToPct(50, 0)).toBeNull();
  });

  it("validatePregresso esercita crediti_commerciali e debiti_previdenziali, non solo le altre tre chiavi", () => {
    const masses = openingMasses(bs);
    expect(validatePregresso({ crediti_commerciali: { opening: 510, amounts: [510] } }, masses, 3)).toEqual([]);
    expect(validatePregresso({ crediti_commerciali: { opening: 500, amounts: [] } }, masses, 3)[0]).toMatch(/apertura/);
    expect(validatePregresso({ debiti_previdenziali: { opening: 41, amounts: [41] } }, masses, 3)).toEqual([]);
    expect(validatePregresso({ debiti_previdenziali: { opening: 41, amounts: [42] } }, masses, 3)[0]).toMatch(/supera/);
  });

  it("validatePregresso segnala un importo negativo, e null'altro sullo stesso piano", () => {
    const masses = openingMasses(bs);
    const errs = validatePregresso({ altri_debiti: { opening: 58, amounts: [-5] } }, masses, 3);
    expect(errs).toHaveLength(1);
    expect(errs[0]).toMatch(/negativo/);
  });

  it("validatePregresso tributari: le rate superano il rateizzato, distinto dal mismatch saldo+rateizzato", () => {
    const masses = openingMasses(bs);
    // saldo + rateizzato = opening (nessun mismatch), ma le rate (50) superano il rateizzato (46).
    const errs = validatePregresso({ debiti_tributari: { opening: 96, saldo: 50, rateizzato: 46, amounts: [50], acconto_pct: 100 } }, masses, 3);
    expect(errs).toHaveLength(1);
    expect(errs[0]).toMatch(/rate superano/);
  });

  it("residualAfter clampa a zero quando gli importi sforano l'apertura", () => {
    expect(residualAfter({ opening: 100, amounts: [80, 80] }, 1)).toBe(0);
  });

  it("equalInstalments con orizzonte nullo, negativo, o a una sola rata", () => {
    expect(equalInstalments(100, 0)).toEqual([]);
    expect(equalInstalments(100, -1)).toEqual([]);
    expect(equalInstalments(100, 1)).toEqual([100]);
  });

  it("validatePregresso: un Pregresso vuoto non produce errori, e più chiavi ne accumulano più di uno", () => {
    const masses = openingMasses(bs);
    expect(validatePregresso({}, masses, 3)).toEqual([]);
    const errs = validatePregresso({
      debiti_fornitori: { opening: 300, amounts: [200, 200] },
      debiti_tributari: { opening: 96, saldo: 50, rateizzato: 40, amounts: [], acconto_pct: 100 },
    }, masses, 3);
    expect(errs).toHaveLength(2);
    expect(errs[0]).toMatch(/supera/);
    expect(errs[1]).toMatch(/saldo \+ rateizzato/);
  });
});
