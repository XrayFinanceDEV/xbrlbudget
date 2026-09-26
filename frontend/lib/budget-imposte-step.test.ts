import { describe, expect, it } from "vitest";
import type { BalanceSheet, ForecastPreviewResponse, ForecastPreviewYear, IncomeStatement, Pregresso } from "@/types/api";
import type { AssumptionsMap } from "@/lib/budget-horizon";
import { euro } from "@/lib/budget-format";
import {
  ACCONTO_CHIOSA,
  DEFAULT_ACCONTO_PCT,
  DEFAULT_TAX_RATE,
  SP17E_NOTA_AUTOMATICA,
  accontiRow,
  accontoPctValue,
  draftDisplay,
  impostePreview,
  manualTaxPosition,
  manualTaxYears,
  pregressoIgnoredTributari,
  singleYearValue,
  spTributariRows,
  taxRateValue,
  tributariOpening,
  tributariPlanOrDefault,
  withAccontoPct,
  withRate,
} from "./budget-imposte-step";

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
  details: { ce05_fixed: null, ce05_variable: null, ce06_fixed: null, ce06_variable: null, dso_applied: 60, dio_applied: 45, dpo_applied: 78, pregresso: { crediti_tributari_breve: { opening: 0, closed: 0, writeoff: 0, residual_short: 0, residual_long: 0, generated: 0, mode: "legacy" }, crediti_tributari_lungo: { opening: 0, closed: 0, writeoff: 0, residual_short: 0, residual_long: 0, generated: 0, mode: "legacy" }, crediti_commerciali: { opening: 0, closed: 0, writeoff: 0, residual_short: 0, residual_long: 0, generated: 0, mode: "legacy" }, debiti_fornitori: { opening: 0, closed: 0, writeoff: 0, residual_short: 0, residual_long: 0, generated: 0, mode: "legacy" }, debiti_tributari: { opening: 0, closed: 0, writeoff: 0, residual_short: 0, residual_long: 0, generated: 0, mode: "legacy" }, debiti_previdenziali: { opening: 0, closed: 0, writeoff: 0, residual_short: 0, residual_long: 0, generated: 0, mode: "legacy" }, altri_debiti: { opening: 0, closed: 0, writeoff: 0, residual_short: 0, residual_long: 0, generated: 0, mode: "legacy" } }, imposte: { current_tax: 0, saldo_paid: 0, acconti_paid: 0, rate_paid: 0, generated_debt: 0, generated_credit: 0, opening_credit_left: 0, mode: "manual" }, degenerate_turnover_ratio: [], pregresso_ignored: [], indicizzazione: {}, indicizzazione_ignorata: [], svalutazioni_cumulate: 0, residuo_quadratura: [], pregresso_writeoff_ignored: [], debito_bancario: { pregresso_senza_piano: null, pregresso_piano_anni: null, contratti: [], fidi: null }, pareggio: { costi_variabili: null, costi_fissi: null, costi_fissi_operativi: null, margine_contribuzione_pct: null, fatturato_pareggio: null, margine_sicurezza: null, margine_sicurezza_pct: null }, tfr: { apertura: 0, accantonamento: 0, liquidazioni: 0, chiusura: 0, sospeso: false }, altri_finanziatori: { apertura: 0, rimborso: 0, interessi: 0, breve: 0, lungo: 0, mode: "legacy", contratti: [] }, override_conflicts: [] },
  ...over,
});

const response = (years: ForecastPreviewYear[]): ForecastPreviewResponse =>
  ({ scenario_id: 1, base_year: 2026, forecast_years: years, error: null });

const asMap = (m: Record<number, Record<string, unknown>>): AssumptionsMap => m as unknown as AssumptionsMap;

// ── singleYearValue (Task 16: spostata qui da `lib/budget-pregresso-step.ts`
// prima della sua cancellazione — questo modulo ne resta l'unico chiamante
// di produzione, via `taxRateValue` sotto) ──────────────────────────────────
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
      [2027, 2028], "existing_debt_repayment_years",
    );
    expect(v).toEqual({ value: 5, uneven: false });
  });

  it("anni non concordi => uneven true, mostra comunque il primo", () => {
    const v = singleYearValue(
      asMap({ 2027: { existing_debt_repayment_years: 5 }, 2028: { existing_debt_repayment_years: 7 } }),
      [2027, 2028], "existing_debt_repayment_years",
    );
    expect(v).toEqual({ value: 5, uneven: true });
  });
});

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

// ── withRate (Task 16: il saldo e il rateizzato ora si scrivono al passo 5
// "Patrimoniale pregresso", `lib/budget-pregresso-oltre.ts`; qui resta solo
// la scrittura delle rate su un piano gia' esistente, con saldo/acconto
// dichiarati altrove) ────────────────────────────────────────────────────
describe("withRate — scrive le sole rate, conserva apertura, saldo, rateizzato e acconto", () => {
  it("prende le sole rate e non tocca il resto del piano", () => {
    const con: Pregresso = {
      debiti_tributari: { opening: 91713.37, saldo: 34500.12, rateizzato: 57213.25, amounts: [], acconto_pct: 40 },
    };
    const next = withRate(con, 91713.37, [20000.5, 37212.75]);
    expect(next.debiti_tributari).toEqual({
      opening: 91713.37, saldo: 34500.12, rateizzato: 57213.25,
      amounts: [20000.5, 37212.75], acconto_pct: 40,
    });
  });

  it("senza piano ne crea uno di partenza (tutto saldo, nulla rateizzato) e scrive le rate sopra", () => {
    const next = withRate({}, 91713.37, [1000]);
    expect(next.debiti_tributari).toEqual({
      opening: 91713.37, saldo: 91713.37, rateizzato: 0, amounts: [1000], acconto_pct: 100,
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

  it("sp06e_growth_pct cambia il credito senza spegnere i pagamenti", () => {
    expect(manualTaxPosition(asMap({ 2027: { sp06e_growth_pct: -100 } }), [2027])).toBe(false);
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

  // ── fix1 R4: la nota indicava la direzione sbagliata («qui sotto» mentre la
  // riga «Debiti tributari entro %» e' resa PRIMA della nota in StepImposte.tsx,
  // quindi sta sopra) e citava un'etichetta che il passo Circolante non usa
  // («Crediti tributari %» invece di «Crediti tributari»).
  it("indica «qui sopra», non «qui sotto»: la riga sp16e e' resa prima della nota", () => {
    expect(SP17E_NOTA_AUTOMATICA).toContain("qui sopra");
    expect(SP17E_NOTA_AUTOMATICA).not.toContain("qui sotto");
  });

  it("non suggerisce più che la modifica dei crediti tributari attivi la via manuale", () => {
    expect(SP17E_NOTA_AUTOMATICA).not.toContain("Crediti tributari");
  });

  // ── fix1 R2: la visibilita' di sp17e_growth_pct e' per ANNO, con la stessa
  // condizione del motore — non un booleano unico su tutto il piano.
  it("con automaticYears la riga sp17e resta ma le sue celle sugli anni automatici sono inerti", () => {
    const rows = spTributariRows(bsTrib, true, [2027]);
    const sp17e = rows.find((r) => r.field === "sp17e_growth_pct")!;
    expect(sp17e.offYears).toEqual([2027]);
    expect(sp17e.offYearsNote).toBeTruthy();
    // sp16e resta sempre vivo: e' l'interruttore, non il controllo governato
    const sp16e = rows.find((r) => r.field === "sp16e_growth_pct")!;
    expect(sp16e.offYears).toBeUndefined();
  });

  it("senza automaticYears (default) sp17e non porta offYears: comportamento invariato", () => {
    const rows = spTributariRows(bsTrib, true);
    expect(rows.find((r) => r.field === "sp17e_growth_pct")!.offYears).toBeUndefined();
  });
});

// ── manualTaxYears (fix1 R2) ────────────────────────────────────────────────
describe("manualTaxYears — il complemento per anno di manualTaxPosition", () => {
  it("il caso del revisore: sp17e=50 nel 2027 (inerte da solo), sp16e=0 solo nel 2028", () => {
    const assumptions = asMap({ 2027: { sp17e_growth_pct: 50 }, 2028: { sp16e_growth_pct: 0 } });
    // 2027 NON e' manuale: sp17e da solo non accende nulla nel motore
    expect(manualTaxYears(assumptions, [2027, 2028])).toEqual([2028]);
    // ma manualTaxPosition (il booleano "almeno un anno") e' true: la riga resta a schermo
    expect(manualTaxPosition(assumptions, [2027, 2028])).toBe(true);
  });

  it("nessun anno manuale => lista vuota", () => {
    expect(manualTaxYears(asMap({ 2027: { tax_rate: 27.9 } }), [2027])).toEqual([]);
  });

  it("tutti gli anni manuali => lista intera", () => {
    const assumptions = asMap({ 2027: { sp16e_growth_pct: 0 }, 2028: { sp06e_growth_pct: 3 } });
    expect(manualTaxYears(assumptions, [2027, 2028])).toEqual([2027]);
  });
});

// ── ACCONTO_CHIOSA (fix1 C1) ─────────────────────────────────────────────────
// Il proprietario ha chiesto di dirlo in chiaro: un acconto per anno vince SOLO
// se maggiore di zero; zero vuol dire "usa la percentuale", non "zero acconti"
// — il difetto che il Ruling 11 chiamava "il piu' silenzioso del progetto".
describe("ACCONTO_CHIOSA", () => {
  it("dice esplicitamente che serve un importo MAGGIORE DI ZERO per scavalcare la percentuale", () => {
    expect(ACCONTO_CHIOSA).toMatch(/maggiore di zero/i);
  });

  it("dice esplicitamente che zero vuol dire usare la percentuale, non zero acconti", () => {
    expect(ACCONTO_CHIOSA).toMatch(/zero.*percentuale/i);
  });

  it("niente testo sulla compensazione del credito d'imposta: il proprietario l'ha rifiutato esplicitamente", () => {
    expect(ACCONTO_CHIOSA.toLowerCase()).not.toContain("compens");
  });
});

// ── draftDisplay (fix1 R6) ───────────────────────────────────────────────────
// Che cosa una casella controllata mostra mentre l'utente digita: una casella
// appena svuotata resta VUOTA, non il valore di ripiego che il modello salva.
describe("draftDisplay", () => {
  it("draft null (nessuna digitazione in corso) => mostra il valore salvato", () => {
    expect(draftDisplay(null, 100)).toBe(100);
    expect(draftDisplay(null, 0)).toBe(0);
  });

  it("draft vuoto ('') => casella VUOTA, mai il valore salvato/di ripiego", () => {
    // il caso misurato: dopo backspace il modello e' gia' ricaduto sul default
    // (100 per l'acconto, 0 per il saldo), ma la casella deve restare vuota
    expect(draftDisplay("", 100)).toBe("");
    expect(draftDisplay("", 0)).toBe("");
  });

  it("draft con un numero => mostra quel numero, non il salvato: la digitazione non si interrompe", () => {
    expect(draftDisplay("1", 100)).toBe(1); // "10" -> backspace -> "1": non deve tornare 100
    expect(draftDisplay("42", 0)).toBe(42);
  });

  it("draft non numerico (testo incollato a caso) => vuoto, non NaN", () => {
    expect(draftDisplay("abc", 100)).toBe("");
  });

  it("il caso misurato per esteso: 10 -> backspace -> 1 -> backspace -> vuoto -> 5, sul default reale del kernel", () => {
    // simula la sequenza di onChange che StepImposte.tsx produce, e il "saved"
    // e' esattamente cio' che withAccontoPct(..., null) scrive: DEFAULT_ACCONTO_PCT
    expect(draftDisplay("10", DEFAULT_ACCONTO_PCT)).toBe(10);
    expect(draftDisplay("1", DEFAULT_ACCONTO_PCT)).toBe(1);
    expect(draftDisplay("", DEFAULT_ACCONTO_PCT)).toBe(""); // qui una mutazione "pct || 100" romperebbe: darebbe 100
    expect(draftDisplay("5", DEFAULT_ACCONTO_PCT)).toBe(5); // la cifra successiva riparte da vuoto, non da 105/1005
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

describe("accontiRow", () => {
  it("lo zero salvato e' «non dichiarato»: casella vuota, e il segnaposto dice l'acconto del motore", () => {
    const preview = {
      scenario_id: 1, base_year: 2026, error: null,
      forecast_years: [{ year: 2027, income_statement: {}, balance_sheet: {},
        details: { imposte: { mode: "saldo_acconto", acconti_paid: "45000.00" } } }],
    } as unknown as ForecastPreviewResponse;
    const r = accontiRow(preview, 100);
    expect(r.zeroIsEmpty).toBe(true);
    expect(r.placeholder(2027)).toBe(`auto ${euro(45000)}`);
    expect(r.placeholder(2028)).toBe("auto");
    expect(r.sub).toContain("100% delle imposte dell'anno prima");
  });
});
