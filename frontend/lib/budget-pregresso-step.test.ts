import { describe, expect, it } from "vitest";
import type { BalanceSheet, ForecastPreviewResponse, ForecastPreviewYear } from "@/types/api";
import type { AssumptionsMap } from "@/lib/budget-horizon";
import { euro } from "@/lib/budget-format";
import {
  boolAssumption,
  pregressoBase,
  pregressoPreview,
  singleYearValue,
} from "./budget-pregresso-step";

const baseBs = {
  sp16a_debiti_banche_breve: "300", sp17a_debiti_banche_lungo: "700",
  sp16_debiti_breve: "300", sp17_debiti_lungo: "700",
  sp16b_debiti_altri_finanz_breve: "50", sp17b_debiti_altri_finanz_lungo: "150",
  sp16c_debiti_obbligazioni_breve: "0", sp17c_debiti_obbligazioni_lungo: "0",
  sp16d_debiti_fornitori_breve: "0", sp17d_debiti_fornitori_lungo: "0",
  sp16e_debiti_tributari_breve: "40", sp17e_debiti_tributari_lungo: "10",
  sp16f_debiti_previdenza_breve: "0", sp17f_debiti_previdenza_lungo: "0",
  sp16g_altri_debiti_breve: "0", sp17g_altri_debiti_lungo: "0",
  sp06_crediti_breve: "500", sp06e_crediti_tributari_breve: "20", sp06f_imposte_anticipate_breve: "5",
  sp02_immob_immateriali: "10", sp03_immob_materiali: "90", sp09_disponibilita_liquide: "60",
} as unknown as BalanceSheet;

const year = (y: number, over: Partial<ForecastPreviewYear> = {}): ForecastPreviewYear => ({
  year: y,
  income_statement: {},
  balance_sheet: {
    sp16a_debiti_banche_breve: 280, sp17a_debiti_banche_lungo: 650,
    sp16b_debiti_altri_finanz_breve: 40, sp17b_debiti_altri_finanz_lungo: 130,
    sp02_immob_immateriali: 8, sp03_immob_materiali: 85, sp09_disponibilita_liquide: 90,
  },
  details: { ce05_fixed: null, ce05_variable: null, ce06_fixed: null, ce06_variable: null, dso_applied: 60, dio_applied: 45, dpo_applied: 78, pregresso: { crediti_commerciali: { opening: 0, closed: 0, writeoff: 0, residual_short: 0, residual_long: 0, generated: 0, mode: "legacy" }, debiti_fornitori: { opening: 0, closed: 0, writeoff: 0, residual_short: 0, residual_long: 0, generated: 0, mode: "legacy" }, debiti_tributari: { opening: 0, closed: 0, writeoff: 0, residual_short: 0, residual_long: 0, generated: 0, mode: "legacy" }, debiti_previdenziali: { opening: 0, closed: 0, writeoff: 0, residual_short: 0, residual_long: 0, generated: 0, mode: "legacy" }, altri_debiti: { opening: 0, closed: 0, writeoff: 0, residual_short: 0, residual_long: 0, generated: 0, mode: "legacy" } }, imposte: { current_tax: 0, saldo_paid: 0, acconti_paid: 0, rate_paid: 0, generated_debt: 0, generated_credit: 0, opening_credit_left: 0, mode: "manual" }, degenerate_turnover_ratio: [], pregresso_ignored: [], indicizzazione: {}, indicizzazione_ignorata: [], svalutazioni_cumulate: 0, residuo_quadratura: [], pregresso_writeoff_ignored: [], debito_bancario: { pregresso_senza_piano: null, pregresso_piano_anni: null, contratti: [] }, override_conflicts: [] },
  ...over,
});

const response = (years: ForecastPreviewYear[], error: ForecastPreviewResponse["error"] = null): ForecastPreviewResponse =>
  ({ scenario_id: 1, base_year: 2026, forecast_years: years, error });

const asMap = (m: Record<number, Record<string, unknown>>): AssumptionsMap => m as unknown as AssumptionsMap;

describe("pregressoBase", () => {
  it("anno base assente => tutto null, mai zero", () => {
    expect(pregressoBase(undefined)).toEqual({
      bankDebt: null, bankDebtShort: null, altriFinanziatori: null, creditiClienti: null, debitiTributari: null,
    });
  });

  it("somma i saldi al 31/12 secondo la formula di ciascuna riga", () => {
    const b = pregressoBase(baseBs);
    expect(b.bankDebt).toBe(1000); // sp16a + sp17a, nessuno scarto aggregato/dettagli qui
    expect(b.bankDebtShort).toBe(300);
    expect(b.altriFinanziatori).toBe(200); // sp16b + sp17b
    expect(b.creditiClienti).toBe(475); // sp06 - sp06e - sp06f
    expect(b.debitiTributari).toBe(50); // sp16e + sp17e
  });

  it("uno scarto positivo fra aggregato e dettagli va alle banche (stessa convenzione di base-bank-debt)", () => {
    // Bilancio abbreviato: tutto il debito sull'aggregato, nessun dettaglio.
    const abbreviato = {
      sp16a_debiti_banche_breve: "0", sp17a_debiti_banche_lungo: "0",
      sp16_debiti_breve: "1000", sp17_debiti_lungo: "700",
      sp16b_debiti_altri_finanz_breve: "0", sp17b_debiti_altri_finanz_lungo: "0",
      sp16c_debiti_obbligazioni_breve: "0", sp17c_debiti_obbligazioni_lungo: "0",
      sp16d_debiti_fornitori_breve: "0", sp17d_debiti_fornitori_lungo: "0",
      sp16e_debiti_tributari_breve: "0", sp17e_debiti_tributari_lungo: "0",
      sp16f_debiti_previdenza_breve: "0", sp17f_debiti_previdenza_lungo: "0",
      sp16g_altri_debiti_breve: "0", sp17g_altri_debiti_lungo: "0",
      sp06_crediti_breve: "0", sp06e_crediti_tributari_breve: "0", sp06f_imposte_anticipate_breve: "0",
    } as unknown as BalanceSheet;
    expect(pregressoBase(abbreviato).bankDebt).toBe(1700);
  });
});

describe("singleYearValue", () => {
  it("nessun anno => value null, non uneven", () => {
    expect(singleYearValue(asMap({}), [], "existing_debt_repayment_years")).toEqual({ value: null, uneven: false });
  });

  it("campo non impostato => null", () => {
    const v = singleYearValue(asMap({ 2027: {}, 2028: {} }), [2027, 2028], "existing_debt_repayment_years");
    expect(v).toEqual({ value: null, uneven: false });
  });

  it("mostra il valore del primo anno previsto", () => {
    const v = singleYearValue(
      asMap({ 2027: { existing_debt_repayment_years: 5 }, 2028: { existing_debt_repayment_years: 5 } }),
      [2027, 2028], "existing_debt_repayment_years"
    );
    expect(v).toEqual({ value: 5, uneven: false });
  });

  it("anni non concordi => uneven true, mostra comunque il primo", () => {
    const v = singleYearValue(
      asMap({ 2027: { existing_debt_repayment_years: 5 }, 2028: { existing_debt_repayment_years: 7 } }),
      [2027, 2028], "existing_debt_repayment_years"
    );
    expect(v).toEqual({ value: 5, uneven: true });
  });
});

describe("boolAssumption", () => {
  it("assente => false, il default del motore", () => {
    expect(boolAssumption(asMap({}), [2027], "cash_sweep_enabled")).toBe(false);
  });

  it("legge il primo anno previsto", () => {
    expect(boolAssumption(asMap({ 2027: { cash_sweep_enabled: true } }), [2027], "cash_sweep_enabled")).toBe(true);
    expect(boolAssumption(asMap({ 2027: { cash_sweep_enabled: false } }), [2027], "cash_sweep_enabled")).toBe(false);
  });
});

describe("pregressoPreview", () => {
  it("senza anno base o senza risposta: nessuna riga", () => {
    const vuota = { years: [], rows: [], unfunded: null, writeoffIgnored: [], writeoffIgnoredByYear: {} };
    expect(pregressoPreview(undefined, response([year(2027)]))).toEqual(vuota);
    expect(pregressoPreview(baseBs, null)).toEqual(vuota);
  });

  it("gli anni sono quelli che il motore ha davvero prodotto", () => {
    const p = pregressoPreview(baseBs, response([year(2027)]));
    expect(p.years).toEqual([2027]);
    expect(p.rows.length).toBeGreaterThan(0);
    expect(p.unfunded).toBeNull();
  });

  it("un fabbisogno scoperto si legge dall'errore strutturato, non si inventa", () => {
    const p = pregressoPreview(baseBs, response([year(2027)], { year: 2028, message: "Fabbisogno finanziario scoperto di 1.234,56" }));
    expect(p.unfunded).toEqual({ year: 2028, amount: 1234.56 });
  });
});

// ── Il pregresso scadenziato nell'anteprima (Task 7) ────────────────────────
describe("pregressoPreview · pregresso di circolante", () => {
  it("senza chiavi l'anteprima e' quella di prima: nessuna riga di pregresso", () => {
    const p = pregressoPreview(baseBs, response([year(2027)]));
    expect(p.rows.some((r) => r.label.endsWith("· residuo a breve"))).toBe(false);
  });

  it("con le chiavi le righe del residuo si aggiungono SOTTO quelle di debito e cassa", () => {
    const p = pregressoPreview(baseBs, response([year(2027)]), ["altri_debiti"]);
    const pfn = p.rows.findIndex((r) => r.key === "pfn");
    const head = p.rows.findIndex((r) => r.label === "Pregresso: residuo a breve · oltre");
    expect(pfn).toBeGreaterThanOrEqual(0);
    expect(head).toBeGreaterThan(pfn);
    expect(p.rows.some((r) => r.label === "Altri debiti · residuo a breve")).toBe(true);
  });

  it("l'inesigibile non scaricato arriva all'interfaccia, invece di restare nei details", () => {
    const conAvviso = year(2027, {
      details: {
        ...year(2027).details,
        pregresso_writeoff_ignored: [
          { saldo: "crediti_commerciali", field: "ce09d_svalutazione_crediti", requested: 5000, reason: "ce09d_override" },
        ],
      },
    });
    const p = pregressoPreview(baseBs, response([conAvviso]), ["crediti_commerciali"]);
    expect(p.writeoffIgnored).toHaveLength(1);
    expect(p.writeoffIgnored[0]).toContain("2027");
    expect(pregressoPreview(baseBs, response([year(2027)]), ["crediti_commerciali"]).writeoffIgnored).toEqual([]);
  });

  it("lo stesso avviso arriva anche indicizzato sull'anno (rilievo 6): la tabella lo legge da li'", () => {
    const conAvviso = year(2027, {
      details: {
        ...year(2027).details,
        pregresso_writeoff_ignored: [
          { saldo: "crediti_commerciali", field: "ce09d_svalutazione_crediti", requested: 5000, reason: "ce09d_override" },
        ],
      },
    });
    const p = pregressoPreview(baseBs, response([conAvviso]), ["crediti_commerciali"]);
    expect(Object.keys(p.writeoffIgnoredByYear)).toEqual(["2027"]);
    expect(p.writeoffIgnoredByYear[2027]).toContain(euro(5000));
    expect(pregressoPreview(baseBs, response([year(2027)])).writeoffIgnoredByYear).toEqual({});
  });
});
