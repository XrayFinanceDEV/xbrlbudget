import { describe, expect, it } from "vitest";
import type { BalanceSheet, ForecastPreviewResponse, ForecastPreviewYear, IncomeStatement, PregressoKey } from "@/types/api";
import type { AssumptionsMap } from "@/lib/budget-horizon";
import { euro } from "@/lib/budget-format";
import { validatePregresso } from "@/lib/budget-pregresso-circolante";
import {
  DEFAULT_TAX_RATE,
  SP17E_NOTA_AUTOMATICA,
  TAX_RATE_PLACEHOLDER,
  accontoPctValue,
  impostePreview,
  manualTaxPosition,
  pregressoIgnoredTributari,
  rateOptions,
  spTributariRows,
  taxRateInputDisplay,
  taxRateValue,
  tributariMasses,
  tributariOpening,
  tributariPlanOrDefault,
  tributariTabella,
  withAccontoPct,
  withRate,
  withRateUguali,
  withSaldo,
} from "./budget-imposte-step";

/** Le masse degli altri quattro saldi non entrano in questi casi: si passano a
 *  zero perche' `validatePregresso` vuole il record intero. */
const ZERO_MASSES: Record<PregressoKey, number> = {
  crediti_commerciali: 0, debiti_fornitori: 0, debiti_tributari: 0,
  debiti_previdenziali: 0, altri_debiti: 0,
};

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
  details: { ce05_fixed: null, ce05_variable: null, ce06_fixed: null, ce06_variable: null, dso_applied: 60, dio_applied: 45, dpo_applied: 78, pregresso: { crediti_commerciali: { opening: 0, closed: 0, writeoff: 0, residual_short: 0, residual_long: 0, generated: 0, mode: "legacy" }, debiti_fornitori: { opening: 0, closed: 0, writeoff: 0, residual_short: 0, residual_long: 0, generated: 0, mode: "legacy" }, debiti_tributari: { opening: 0, closed: 0, writeoff: 0, residual_short: 0, residual_long: 0, generated: 0, mode: "legacy" }, debiti_previdenziali: { opening: 0, closed: 0, writeoff: 0, residual_short: 0, residual_long: 0, generated: 0, mode: "legacy" }, altri_debiti: { opening: 0, closed: 0, writeoff: 0, residual_short: 0, residual_long: 0, generated: 0, mode: "legacy" } }, imposte: { current_tax: 0, saldo_paid: 0, acconti_paid: 0, rate_paid: 0, generated_debt: 0, generated_credit: 0, opening_credit_left: 0, mode: "manual" }, degenerate_turnover_ratio: [], pregresso_ignored: [], indicizzazione: {}, indicizzazione_ignorata: [], svalutazioni_cumulate: 0, residuo_quadratura: [] },
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
    const rows = spTributariRows(undefined, true);
    expect(rows.map((r) => r.baseLabel)).toEqual(["—", "—"]);
  });

  it("sp16e/sp17e esistono gia' nell'anno base: la colonna base porta l'importo vero", () => {
    const baseBs = {
      sp16e_debiti_tributari_breve: "40", sp17e_debiti_tributari_lungo: "10",
    } as unknown as BalanceSheet;
    const rows = spTributariRows(baseBs, true);
    expect(rows.map((r) => [r.field, r.label, r.baseLabel])).toEqual([
      ["sp16e_growth_pct", "Debiti tributari entro %", "40 €"],
      ["sp17e_growth_pct", "Debiti tributari oltre %", "10 €"],
    ]);
  });

  it("uno zero vero nell'anno base resta zero, non trattino", () => {
    const baseBs = {
      sp16e_debiti_tributari_breve: "0", sp17e_debiti_tributari_lungo: "10",
    } as unknown as BalanceSheet;
    expect(spTributariRows(baseBs, true)[0].baseLabel).toBe("0 €");
  });
});

describe("TAX_RATE_PLACEHOLDER", () => {
  // Era `auto ${DEFAULT_TAX_RATE}` e a schermo si leggeva «auto :»: il
  // segnaposto non ci stava nella casella. Rimetterci dentro il numero
  // tornerebbe a troncare — e un troncamento non da' alcun errore.
  it("non ripete l'aliquota: e' la lunghezza a essere il difetto", () => {
    expect(TAX_RATE_PLACEHOLDER).not.toContain(String(DEFAULT_TAX_RATE));
    expect(TAX_RATE_PLACEHOLDER).not.toMatch(/\d/);
  });

  it("resta breve: la casella deve ospitare anche quattro cifre e una virgola", () => {
    expect(TAX_RATE_PLACEHOLDER.length).toBeLessThanOrEqual(6);
    expect(TAX_RATE_PLACEHOLDER.trim()).toBe(TAX_RATE_PLACEHOLDER);
    expect(TAX_RATE_PLACEHOLDER).not.toBe("");
  });
});

describe("impostePreview", () => {
  it("senza anno base o senza risposta: nessuna riga", () => {
    expect(impostePreview(undefined, response([year(2027)]))).toEqual({ years: [], rows: [], pregressoIgnored: false });
    expect(impostePreview(baseInc, null)).toEqual({ years: [], rows: [], pregressoIgnored: false });
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

// ── Pagamento dei debiti tributari (Task 8) ─────────────────────────────────
// Il piano di saldo, rate e acconti che l'utente dichiara al passo 7, e la
// scomparsa del controllo che dal Task 6 non governa piu' nulla.

const bsTrib = {
  sp16e_debiti_tributari_breve: "63213.37", sp17e_debiti_tributari_lungo: "28500",
} as unknown as BalanceSheet;

describe("tributariOpening", () => {
  it("l'apertura e' sp16e + sp17e, la stessa massa di openingMasses", () => {
    expect(tributariOpening(bsTrib)).toBe(91713.37);
  });

  it("senza bilancio base l'apertura e' zero: la forma del valore non cambia mentre i dati arrivano", () => {
    expect(tributariOpening(undefined)).toBe(0);
  });
});

describe("tributariPlanOrDefault — il piano nasce al primo tocco", () => {
  it("senza piano: tutto saldo, nulla rateizzato, acconto al 100%", () => {
    expect(tributariPlanOrDefault({}, 91713.37)).toEqual({
      opening: 91713.37, saldo: 91713.37, rateizzato: 0, amounts: [], acconto_pct: 100,
    });
  });

  it("un piano gia' dichiarato torna com'e': l'apertura non viene riscritta", () => {
    const plan = { opening: 91713.37, saldo: 34500.12, rateizzato: 57213.25, amounts: [1], acconto_pct: 40 };
    expect(tributariPlanOrDefault({ debiti_tributari: plan }, 12)).toBe(plan);
  });
});

describe("withSaldo — il rateizzato e' cio' che il saldo non copre", () => {
  it("scrive il saldo e ne deduce il rateizzato", () => {
    const next = withSaldo({}, 91713.37, 34500.12);
    expect(next.debiti_tributari).toEqual({
      opening: 91713.37, saldo: 34500.12, rateizzato: 57213.25, amounts: [], acconto_pct: 100,
    });
  });

  it("una casella svuotata mette tutto a rate, non lascia il saldo di prima", () => {
    const con = withSaldo({}, 91713.37, 34500.12);
    const dopo = withSaldo(con, 91713.37, null);
    expect(dopo.debiti_tributari!.saldo).toBe(0);
    expect(dopo.debiti_tributari!.rateizzato).toBe(91713.37);
  });

  it("un saldo oltre l'apertura NON viene troncato: si scrive, e la validazione lo dichiara", () => {
    const next = withSaldo({}, 91713.37, 120000);
    expect(next.debiti_tributari!.saldo).toBe(120000);
    expect(next.debiti_tributari!.rateizzato).toBe(-28286.63);
    expect(validatePregresso(next, { ...ZERO_MASSES, debiti_tributari: 91713.37 }, 3).join(" "))
      .toMatch(/negativ/i);
  });

  it("non muta cio' che riceve", () => {
    const prima = {
      debiti_tributari: { opening: 91713.37, saldo: 0, rateizzato: 91713.37, amounts: [10], acconto_pct: 100 },
    };
    const copia = JSON.parse(JSON.stringify(prima));
    withSaldo(prima, 91713.37, 34500.12);
    expect(prima).toEqual(copia);
  });
});

describe("withRateUguali — n rate che sommano esattamente il rateizzato", () => {
  it("i centesimi residui vanno sull'ultima rata, e la somma torna al centesimo", () => {
    const con = withSaldo({}, 91713.37, 34500.12);          // rateizzato 57.213,25
    const next = withRateUguali(con, 91713.37, 4);
    expect(next.debiti_tributari!.amounts).toEqual([14303.31, 14303.31, 14303.31, 14303.32]);
    const somma = next.debiti_tributari!.amounts.reduce((a, b) => a + b, 0);
    expect(Math.round(somma * 100) / 100).toBe(57213.25);
  });

  it("le rate uguali si calcolano sul RATEIZZATO, non sull'apertura", () => {
    const con = withSaldo({}, 91713.37, 34500.12);
    const next = withRateUguali(con, 91713.37, 4);
    expect(next.debiti_tributari!.amounts[0]).not.toBeCloseTo(91713.37 / 4, 2);
  });

  it("saldo e acconto non si muovono", () => {
    const con = withAccontoPct(withSaldo({}, 91713.37, 34500.12), 91713.37, 40);
    const next = withRateUguali(con, 91713.37, 3);
    expect(next.debiti_tributari!.saldo).toBe(34500.12);
    expect(next.debiti_tributari!.acconto_pct).toBe(40);
  });
});

describe("rateOptions — non si offre un piano che l'orizzonte rifiuterebbe", () => {
  it("fino a cinque rate, mai piu' degli anni di piano", () => {
    expect(rateOptions(5)).toEqual([2, 3, 4, 5]);
    expect(rateOptions(7)).toEqual([2, 3, 4, 5]);
    expect(rateOptions(3)).toEqual([2, 3]);
    expect(rateOptions(1)).toEqual([]);
    expect(rateOptions(0)).toEqual([]);
  });
});

describe("withAccontoPct", () => {
  it("scrive la percentuale e crea il piano se non c'era", () => {
    expect(withAccontoPct({}, 91713.37, 40).debiti_tributari).toEqual({
      opening: 91713.37, saldo: 91713.37, rateizzato: 0, amounts: [], acconto_pct: 40,
    });
  });

  it("zero e' un valore vero — zero acconti — non «non dichiarato»", () => {
    expect(withAccontoPct({}, 91713.37, 0).debiti_tributari!.acconto_pct).toBe(0);
  });

  it("una casella svuotata torna al 100%, il default del kernel", () => {
    const con = withAccontoPct({}, 91713.37, 0);
    expect(withAccontoPct(con, 91713.37, null).debiti_tributari!.acconto_pct).toBe(100);
  });
});

describe("accontoPctValue — che cosa mostra la casella", () => {
  it("senza piano mostra il 100 che il kernel applicherebbe, non il vuoto", () => {
    expect(accontoPctValue({})).toBe(100);
  });

  it("uno zero dichiarato si legge zero, non 100", () => {
    expect(accontoPctValue(withAccontoPct({}, 91713.37, 0))).toBe(0);
  });
});

describe("la tabella delle rate scadenzia il RATEIZZATO, non l'apertura", () => {
  it("la massa che la tabella mostra e' il rateizzato", () => {
    const con = withSaldo({}, 91713.37, 34500.12);
    expect(tributariMasses(con, 91713.37).debiti_tributari).toBe(57213.25);
  });

  it("senza piano non c'e' nulla da scadenziare: massa zero, tabella vuota", () => {
    expect(tributariMasses({}, 91713.37).debiti_tributari).toBe(0);
    expect(tributariTabella({}, 91713.37)).toEqual({});
  });

  it("il piano passato alla tabella porta il RATEIZZATO come apertura: il residuo torna", () => {
    const con = withSaldo({}, 91713.37, 34500.12);
    expect(tributariTabella(con, 91713.37).debiti_tributari!.opening).toBe(57213.25);
    // e il piano VERO resta con la sua apertura: quella della tabella e' una vista
    expect(con.debiti_tributari!.opening).toBe(91713.37);
  });
});

describe("withRate — dal ritorno della tabella al piano vero", () => {
  it("prende le sole rate e conserva apertura, saldo, rateizzato e acconto", () => {
    const con = withAccontoPct(withSaldo({}, 91713.37, 34500.12), 91713.37, 40);
    const next = withRate(con, 91713.37, [20000.5, 37212.75]);
    expect(next.debiti_tributari).toEqual({
      opening: 91713.37, saldo: 34500.12, rateizzato: 57213.25,
      amounts: [20000.5, 37212.75], acconto_pct: 40,
    });
  });
});

describe("manualTaxPosition — la via manuale, misurata sul motore", () => {
  it("nessuna percentuale => via automatica", () => {
    expect(manualTaxPosition(asMap({ 2027: { tax_rate: 27.9 } }), [2027])).toBe(false);
  });

  it("sp16e_growth_pct accende la via manuale, e lo zero e' un valore, non un'assenza", () => {
    expect(manualTaxPosition(asMap({ 2027: { sp16e_growth_pct: 0 } }), [2027])).toBe(true);
  });

  it("sp06e_growth_pct (crediti tributari, passo Circolante) la accende allo stesso modo", () => {
    expect(manualTaxPosition(asMap({ 2027: { sp06e_growth_pct: 3 } }), [2027])).toBe(true);
  });

  it("sp17e_growth_pct DA SOLO non accende nulla: nel motore compare una volta, dentro il ramo manuale", () => {
    expect(manualTaxPosition(asMap({ 2027: { sp17e_growth_pct: 12 } }), [2027])).toBe(false);
  });

  it("basta un anno qualsiasi: la via e' per anno, e il controllo governa se governa un anno", () => {
    expect(manualTaxPosition(asMap({ 2027: {}, 2028: { sp16e_growth_pct: 5 } }), [2027, 2028])).toBe(true);
    expect(manualTaxPosition(asMap({ 2027: { sp16e_growth_pct: 5 } }), [2028])).toBe(false);
  });
});

describe("spTributariRows — sulla via automatica il controllo inerte sparisce", () => {
  it("via automatica: la sola riga che governa qualcosa, sp17e assente", () => {
    const rows = spTributariRows(bsTrib, false);
    expect(rows.map((r) => r.field)).toEqual(["sp16e_growth_pct"]);
    expect(rows[0].baseLabel).toBe(euro(63213.37));
  });

  it("via manuale: sp17e torna, perche' li' governa il debito oltre l'esercizio", () => {
    const rows = spTributariRows(bsTrib, true);
    expect(rows.map((r) => r.field)).toEqual(["sp16e_growth_pct", "sp17e_growth_pct"]);
    expect(rows[1].baseLabel).toBe(euro(28500));
  });

  it("anno base assente => trattino, mai zero", () => {
    expect(spTributariRows(undefined, true).map((r) => r.baseLabel)).toEqual(["—", "—"]);
  });

  it("la scomparsa non e' muta: c'e' una riga che dice perche', e come farlo tornare", () => {
    expect(SP17E_NOTA_AUTOMATICA).toContain("oltre");
    expect(SP17E_NOTA_AUTOMATICA.length).toBeGreaterThan(40);
  });
});

describe("pregressoIgnoredTributari — misurato sul motore, non dedotto", () => {
  const conIgnored = (ignored: string[]): ForecastPreviewYear => {
    const y = year(2027);
    return { ...y, details: { ...y.details, pregresso_ignored: ignored } } as unknown as ForecastPreviewYear;
  };

  it("nessun anno lo dichiara => nessun avviso", () => {
    expect(pregressoIgnoredTributari([conIgnored([]), conIgnored(["altri_debiti"])])).toBe(false);
  });

  it("un anno solo basta", () => {
    expect(pregressoIgnoredTributari([conIgnored([]), conIgnored(["debiti_tributari"])])).toBe(true);
  });
});
