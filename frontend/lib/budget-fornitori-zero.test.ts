import { describe, expect, it } from "vitest";
import type { BalanceSheet, IncomeStatement } from "@/types/api";
import { fornitoriZeroAvviso } from "./budget-fornitori-zero";

const inc = { ce05_materie_prime: "980000", ce06_servizi: "420000", ce07_godimento_beni: "85000" } as unknown as IncomeStatement;
const bs = (forn: string, altri = "367000") => ({ sp16d_debiti_fornitori_breve: forn, sp16g_altri_debiti_breve: altri }) as unknown as BalanceSheet;

describe("fornitoriZeroAvviso", () => {
  it("avvisa quando i fornitori sono zero e i costi d'acquisto no", () => {
    expect(fornitoriZeroAvviso(2026, bs("0"), inc)).toEqual({
      titolo: "Non risultano debiti verso fornitori nell'anno di partenza. Controllare le riclassifiche dei debiti!",
      dettaglio: "I costi di acquisto del 2026 sono 1.485.000 €, i giorni di pagamento non si possono calcolare. Gli altri debiti a breve valgono 367.000 €.",
    });
  });
  it("tace con fornitori positivi, senza costi, o senza bilancio", () => {
    expect(fornitoriZeroAvviso(2026, bs("322000"), inc)).toBeNull();
    expect(fornitoriZeroAvviso(2026, bs("0"), { ce05_materie_prime: "0" } as unknown as IncomeStatement)).toBeNull();
    expect(fornitoriZeroAvviso(2026, null, inc)).toBeNull();
  });
});
