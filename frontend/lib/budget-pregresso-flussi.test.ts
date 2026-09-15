import { describe, expect, it } from "vitest";
import type { ForecastPreviewYear } from "@/types/api";
import { flussiPregresso } from "./budget-pregresso-flussi";

const y = (year: number): ForecastPreviewYear => ({
  year, income_statement: {}, balance_sheet: {},
  details: {
    pregresso: {
      crediti_commerciali: { opening: 452000, closed: year === 2027 ? 432000 : 0, writeoff: 0, residual_short: 0, residual_long: 20000, generated: 0, mode: "runoff", non_incassato: false },
      debiti_fornitori: { opening: 322000, closed: year === 2027 ? 322000 : 0, writeoff: 0, residual_short: 0, residual_long: 0, generated: 0, mode: "runoff" },
      debiti_tributari: { opening: 96000, closed: 0, writeoff: 0, residual_short: 0, residual_long: 23000, generated: 0, mode: "runoff" },
      debiti_previdenziali: { opening: 28000, closed: 0, writeoff: 0, residual_short: 0, residual_long: 0, generated: 0, mode: "legacy" },
      altri_debiti: { opening: 85000, closed: year === 2027 ? 45000 : 0, writeoff: 0, residual_short: 0, residual_long: 40000, generated: 0, mode: "runoff" },
    },
    imposte: { saldo_paid: year === 2027 ? 61000 : 0, rate_paid: 12000, acconti_paid: 0, current_tax: 0, generated_debt: 0, generated_credit: 0, opening_credit_left: 0, mode: "saldo_acconto" },
    debito_bancario: { fidi: { apertura: 90000, variazione_ricavi: 0, rimborso_sweep: 0, residuo: 90000, regola: "costante" }, pregresso_senza_piano: null, pregresso_piano_anni: null,
      contratti: [{ indice: 0, anno: 2027, tasso: 3.8, erogato: 0, residuo_iniziale: 330000, rimborso: 82500, interessi: 0, breve: 82500, lungo: 165000 }] },
    altri_finanziatori: { apertura: 150000, rimborso: year === 2028 ? 50000 : 0, interessi: 0, breve: 0, lungo: 100000, mode: "contratti", contratti: [] },
  } as never,
} as unknown as ForecastPreviewYear);

const breve = { crediti_commerciali: 422000, debiti_fornitori: 322000, debiti_previdenziali: 28000, altri_debiti: 45000 };

describe("flussiPregresso", () => {
  it("una riga per flusso, segno per direzione, totale netto e debito aperto", () => {
    const rows = flussiPregresso([y(2027), y(2028)], breve);
    const by = (k: string) => rows.find((r) => r.key === k)!;
    expect(rows.map((r) => r.key)).toEqual(["h-breve", "crediti", "fornitori", "trib-saldo", "previd-altri", "h-oltre", "banche", "fidi", "altri-fin", "trib-rate", "altri-oltre", "crediti-oltre", "netto", "aperto"]);
    expect(by("crediti").years.map((c) => c.value)).toEqual([422000, 0]);
    expect(by("crediti-oltre").years.map((c) => c.value)).toEqual([10000, 0]);
    expect(by("fornitori").years[0].value).toBe(-322000);
    expect(by("banche").years[0].value).toBe(-82500);
    expect(by("altri-fin").years[1].value).toBe(-50000);
    expect(by("netto").years[0].value).toBe(422000 + 10000 - 322000 - 61000 - 45000 - 82500 - 0 - 0 - 12000 - 0);
    expect(by("aperto").years[0].value).toBe(90000 + 247500 + 100000 + 23000 + 40000);
  });
});

describe("flussiPregresso · saldo tributario (collaudo R4)", () => {
  it("dal secondo anno il saldo e' delle imposte del piano, non del pregresso", () => {
    const due = y(2028);
    (due.details as unknown as { imposte: { saldo_paid: number } }).imposte.saldo_paid = 16289;
    const rows = flussiPregresso([y(2027), due], breve);
    expect(rows.find((r) => r.key === "trib-saldo")!.years.map((c) => c.value)).toEqual([-61000, 0]);
  });
});
