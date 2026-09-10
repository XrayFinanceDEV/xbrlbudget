import { describe, expect, it } from "vitest";
import type { ForecastPreviewResponse, ForecastPreviewYear, IncomeStatement } from "@/types/api";
import type { AssumptionsMap } from "@/lib/budget-horizon";
import type { CostiTableRow, ForcedSplit } from "./budget-costi-step";
import {
  FIXED_SHARE_DEFAULT,
  alignVariablesToRevenue,
  costiBase,
  costiPreview,
  costiTableRows,
  fixedShareOf,
  forcedNote,
  forcedSplitYears,
  splitBaseAmount,
} from "./budget-costi-step";
import { yearCellState, type YearCellOff } from "./budget-year-cell";

const baseInc = {
  ce01_ricavi_vendite: "1000", ce04_altri_ricavi: "50", ce05_materie_prime: "400",
  ce06_servizi: "200", ce07_godimento_beni: "30", ce08_costi_personale: "150",
  ce12_oneri_diversi: "20", ce09_ammortamenti: "40", ce15_oneri_finanziari: "10", ce20_imposte: "30",
} as unknown as IncomeStatement;

const year = (y: number, over: Partial<ForecastPreviewYear> = {}): ForecastPreviewYear => ({
  year: y,
  income_statement: {
    ce01_ricavi_vendite: 1100, ce04_altri_ricavi: 50, ce05_materie_prime: 430, ce06_servizi: 210,
    ce07_godimento_beni: 30, ce08_costi_personale: 155, ce12_oneri_diversi: 20, ce09_ammortamenti: 40,
    ce15_oneri_finanziari: 10, ce20_imposte: 33,
  },
  balance_sheet: { sp16d_debiti_fornitori_breve: 140 },
  details: {
    ce05_fixed: 130, ce05_variable: 300, ce06_fixed: 120, ce06_variable: 90,
    dso_applied: 60, dio_applied: 45, dpo_applied: 78,
    pregresso: { crediti_commerciali: { opening: 0, closed: 0, writeoff: 0, residual_short: 0, residual_long: 0, generated: 0, mode: "legacy" }, debiti_fornitori: { opening: 0, closed: 0, writeoff: 0, residual_short: 0, residual_long: 0, generated: 0, mode: "legacy" }, debiti_tributari: { opening: 0, closed: 0, writeoff: 0, residual_short: 0, residual_long: 0, generated: 0, mode: "legacy" }, debiti_previdenziali: { opening: 0, closed: 0, writeoff: 0, residual_short: 0, residual_long: 0, generated: 0, mode: "legacy" }, altri_debiti: { opening: 0, closed: 0, writeoff: 0, residual_short: 0, residual_long: 0, generated: 0, mode: "legacy" } },
    imposte: { current_tax: 0, saldo_paid: 0, acconti_paid: 0, rate_paid: 0, generated_debt: 0, generated_credit: 0, opening_credit_left: 0, mode: "manual" },
    degenerate_turnover_ratio: [], pregresso_ignored: [], indicizzazione: {}, indicizzazione_ignorata: [], svalutazioni_cumulate: 0, residuo_quadratura: [],
  },
  ...over,
});

const response = (years: ForecastPreviewYear[]): ForecastPreviewResponse =>
  ({ scenario_id: 1, base_year: 2026, forecast_years: years, error: null });

const asMap = (m: Record<number, Record<string, unknown>>): AssumptionsMap =>
  m as unknown as AssumptionsMap;

describe("fixedShareOf", () => {
  it("un anno senza valore vale il default del motore, non zero", () => {
    const s = fixedShareOf(asMap({ 2027: {}, 2028: {} }), [2027, 2028], "fixed_materials_percentage");
    expect(s.value).toBe(FIXED_SHARE_DEFAULT);
    expect(s.uneven).toBe(false);
  });

  it("mostra la quota del primo anno previsto", () => {
    const s = fixedShareOf(
      asMap({ 2027: { fixed_services_percentage: 65 }, 2028: { fixed_services_percentage: 65 } }),
      [2027, 2028], "fixed_services_percentage"
    );
    expect(s).toEqual({ value: 65, uneven: false });
  });

  it("anni discordi si dichiarano: e' l'avviso che lo slider li allineera'", () => {
    const s = fixedShareOf(
      asMap({ 2027: { fixed_materials_percentage: 30 }, 2028: { fixed_materials_percentage: 55 } }),
      [2027, 2028], "fixed_materials_percentage"
    );
    expect(s).toEqual({ value: 30, uneven: true });
  });

  it("uno zero esplicito e' zero, e discorda dal default dell'anno che non ce l'ha", () => {
    const s = fixedShareOf(
      asMap({ 2027: { fixed_materials_percentage: 0 }, 2028: {} }),
      [2027, 2028], "fixed_materials_percentage"
    );
    expect(s.value).toBe(0);
    expect(s.uneven).toBe(true);
  });

  it("un null e' assenza, quindi vale il default", () => {
    const s = fixedShareOf(
      asMap({ 2027: { fixed_materials_percentage: null } }), [2027], "fixed_materials_percentage"
    );
    expect(s.value).toBe(FIXED_SHARE_DEFAULT);
  });

  it("senza anni previsti resta il default e nessuna discordanza", () => {
    expect(fixedShareOf(asMap({}), [], "fixed_materials_percentage"))
      .toEqual({ value: FIXED_SHARE_DEFAULT, uneven: false });
  });
});

describe("forcedSplitYears", () => {
  it("risponde QUALI anni sono forzati, non se lo e' almeno uno", () => {
    expect(forcedSplitYears(
      asMap({ 2027: {}, 2028: { ce05_override: 500 }, 2029: {} }), [2027, 2028, 2029], "ce05_override"
    )).toEqual([2028]);
  });

  it("un override a zero e' comunque un override", () => {
    expect(forcedSplitYears(asMap({ 2027: { ce06_override: 0 } }), [2027], "ce06_override")).toEqual([2027]);
  });

  it("null, assente e stringa vuota non forzano nulla", () => {
    expect(forcedSplitYears(
      asMap({ 2027: { ce05_override: null }, 2028: {}, 2029: { ce05_override: "" } }),
      [2027, 2028, 2029], "ce05_override"
    )).toEqual([]);
  });

  it("gli anni tornano nell'ordine del piano, non in quello della mappa", () => {
    expect(forcedSplitYears(
      asMap({ 2029: { ce05_override: 1 }, 2027: { ce05_override: 1 } }), [2027, 2028, 2029], "ce05_override"
    )).toEqual([2027, 2029]);
  });
});

describe("forcedNote", () => {
  it("nessun anno forzato, nessun avviso: un badge acceso ovunque non distingue nulla", () => {
    expect(forcedNote([], [2027, 2028, 2029])).toBeNull();
  });

  it("un anno solo: l'avviso dice QUALE", () => {
    expect(forcedNote([2027], [2027, 2028, 2029])).toBe("forzato in CE Prev. nel 2027");
  });

  it("due anni su tre si legge «e», tre su quattro con la virgola", () => {
    expect(forcedNote([2027, 2029], [2027, 2028, 2029])).toBe("forzato in CE Prev. nel 2027 e 2029");
    expect(forcedNote([2027, 2028, 2029], [2027, 2028, 2029, 2030]))
      .toBe("forzato in CE Prev. nel 2027, 2028 e 2029");
  });

  it("tutti gli anni previsti: elencarli non aggiunge nulla, l'avviso resta secco", () => {
    expect(forcedNote([2027, 2028], [2027, 2028])).toBe("forzato in CE Prev.");
  });
});

describe("costiBase", () => {
  it("legge le quattro voci dell'anno base", () => {
    expect(costiBase(baseInc)).toEqual({ mat: 400, serv: 200, pers: 150, god: 30 });
  });

  it("senza anno base sono assenti, non zero", () => {
    expect(costiBase(undefined)).toEqual({ mat: null, serv: null, pers: null, god: null });
  });
});

describe("splitBaseAmount", () => {
  it("taglia l'importo dell'anno base secondo la quota digitata", () => {
    expect(splitBaseAmount(400, 32.5)).toEqual({ fixed: 130, variable: 270 });
  });

  it("a quota 100 non resta variabile; a quota 0 non resta fisso", () => {
    expect(splitBaseAmount(400, 100)).toEqual({ fixed: 400, variable: 0 });
    expect(splitBaseAmount(400, 0)).toEqual({ fixed: 0, variable: 400 });
  });

  it("un importo assente non diventa uno zero", () => {
    expect(splitBaseAmount(null, 40)).toEqual({ fixed: null, variable: null });
  });
});

describe("costiTableRows", () => {
  const base = { mat: 400, serv: 200, pers: 150, god: 30 };
  const even = (v: number) => ({ value: v, uneven: false });
  const PIANO = [2027, 2028, 2029];
  const nulla: ForcedSplit = { years: PIANO, materials: [], services: [] };
  const rows = (m: number, s: number, forced: ForcedSplit = nulla) =>
    costiTableRows(base, even(m), even(s), forced);

  it("tre gruppi: la quota, poi le variabili, poi le fisse — coi loro pallini", () => {
    const r = rows(40, 40);
    expect(r[0]).toEqual({ group: "Quota fissa, anno per anno" });
    expect(r[3]).toEqual({ group: "Costi variabili", swatch: "variable" });
    expect(r[6]).toEqual({ group: "Costi fissi", swatch: "fixed" });
  });

  it("tutti gli otto campi del passo che la tabella edita, nell'ordine", () => {
    const fields = rows(40, 40).flatMap((r) => ("field" in r ? [r.field] : []));
    expect(fields).toEqual([
      "fixed_materials_percentage", "fixed_services_percentage",
      "variable_materials_growth_pct", "variable_services_growth_pct",
      "fixed_materials_growth_pct", "fixed_services_growth_pct",
      "personnel_growth_pct", "rent_growth_pct",
    ]);
  });

  it("la quota fissa e' editabile anno per anno, e non si spegne mai", () => {
    for (const share of [0, 40, 100]) {
      const r = rows(share, share);
      for (const field of ["fixed_materials_percentage", "fixed_services_percentage"]) {
        const row = r.find((x) => "field" in x && x.field === field) as
          { off?: boolean; baseLabel: string } | undefined;
        expect(row, `${field} a quota ${share}`).toBeDefined();
        expect(row!.off).toBeUndefined();
        // L'anno base non ha una quota: e' un'ipotesi sul futuro.
        expect(row!.baseLabel).toBe("—");
      }
    }
  });

  it("un valore differenziato per anno non viene appiattito dalla tabella", () => {
    // La tabella scrive con `update(anno, campo, valore)`: espone il campo una
    // volta e YearInputTable ne rende una casella per anno. Cio' che l'utente ha
    // differenziato resta differenziato finche' non muove lo slider — che e'
    // l'unico gesto che chiama `updateAll` — e nel frattempo `uneven` lo dichiara.
    const differenziato = asMap({
      2027: { fixed_materials_percentage: 30 },
      2028: { fixed_materials_percentage: 55 },
    });
    const share = fixedShareOf(differenziato, [2027, 2028], "fixed_materials_percentage");
    expect(share).toEqual({ value: 30, uneven: true });
    const r = costiTableRows(base, share, even(40), nulla);
    expect(r.some((x) => "field" in x && x.field === "fixed_materials_percentage")).toBe(true);
    // Nessuna riga porta con se' un valore: i valori restano nella mappa per anno.
    expect(r.every((x) => !("value" in x))).toBe(true);
    expect(differenziato[2028].fixed_materials_percentage).toBe(55);
  });

  it("a quota 100 si spengono le variabili, a quota 0 le fisse — e mai le altre", () => {
    const off = (r: ReturnType<typeof rows>, field: string) =>
      r.find((x) => "field" in x && x.field === field) as { off?: boolean };
    const hundred = rows(100, 100);
    expect(off(hundred, "variable_materials_growth_pct").off).toBe(true);
    expect(off(hundred, "fixed_materials_growth_pct").off).toBe(false);
    const zero = rows(0, 0);
    expect(off(zero, "fixed_services_growth_pct").off).toBe(true);
    expect(off(zero, "variable_services_growth_pct").off).toBe(false);
    expect(off(zero, "personnel_growth_pct").off).toBeUndefined();
  });

  it("con gli anni discordi l'estremo non spegne niente: un controllo che non sa non blocca", () => {
    // `off` e' un flag di RIGA e YearInputTable lo traduce in `disabled` su OGNI
    // anno. Con quota 100 sul 2027 e 40 sul 2028, spegnere la parte variabile
    // renderebbe indigitabile un campo che sul 2028 il motore usa eccome.
    const off = (r: CostiTableRow[], field: string) =>
      r.find((x) => "field" in x && x.field === field) as { off?: boolean };
    const centoPoiQuaranta = { value: 100, uneven: true };
    const zeroPoiQuaranta = { value: 0, uneven: true };
    const r = costiTableRows(base, centoPoiQuaranta, zeroPoiQuaranta,
      nulla);
    expect(off(r, "variable_materials_growth_pct").off).toBe(false);
    expect(off(r, "fixed_services_growth_pct").off).toBe(false);
    // Quando invece gli anni concordano, l'estremo spegne come prima.
    const concordi = costiTableRows(base, { value: 100, uneven: false }, { value: 0, uneven: false },
      nulla);
    expect(off(concordi, "variable_materials_growth_pct").off).toBe(true);
    expect(off(concordi, "fixed_services_growth_pct").off).toBe(true);
  });

  it("la colonna base mostra il taglio della quota, non l'importo intero", () => {
    const r = rows(25, 40);
    const baseLabel = (field: string) =>
      (r.find((x) => "field" in x && x.field === field) as { baseLabel: string }).baseLabel;
    expect(baseLabel("fixed_materials_growth_pct")).toContain("100");
    expect(baseLabel("variable_materials_growth_pct")).toContain("300");
  });

  it("senza anno base la colonna base e' un trattino, non uno zero", () => {
    const r = costiTableRows({ mat: null, serv: null, pers: null, god: null }, even(40), even(40),
      nulla);
    const labels = r.flatMap((x) => ("baseLabel" in x ? [x.baseLabel] : []));
    expect(labels.every((l) => l === "—")).toBe(true);
  });

  it("l'override marca le sole righe del suo gruppo, e dice in quale anno", () => {
    const r = rows(40, 40, { years: PIANO, materials: [2027], services: [] });
    const sub = (field: string) =>
      (r.find((x) => "field" in x && x.field === field) as { sub?: string }).sub;
    expect(sub("fixed_materials_percentage")).toBe("forzato in CE Prev. nel 2027");
    expect(sub("variable_materials_growth_pct")).toBe("forzato in CE Prev. nel 2027");
    expect(sub("fixed_materials_growth_pct")).toBe("forzato in CE Prev. nel 2027");
    expect(sub("fixed_services_percentage")).toBeUndefined();
    expect(sub("variable_services_growth_pct")).toBeUndefined();
    expect(sub("personnel_growth_pct")).toBeUndefined();
  });

  // La prova che la granularita' e' l'ANNO: `costiTableRows` produce le righe,
  // `yearCellState` — la stessa funzione che `YearInputTable` chiama per ogni
  // casella — dice se quella casella e' inerte. Le due insieme sono cio' che
  // l'utente vede.
  const cella = (r: CostiTableRow[], field: string, y: number) =>
    yearCellState(r.find((x) => "field" in x && x.field === field) as YearCellOff, y);

  it("un anno forzato su tre spegne SOLO quell'anno, e dice perche'", () => {
    const r = rows(40, 40, { years: PIANO, materials: [2027], services: [] });
    for (const field of [
      "fixed_materials_percentage", "variable_materials_growth_pct", "fixed_materials_growth_pct",
    ]) {
      expect(cella(r, field, 2027).disabled, `${field} 2027`).toBe(true);
      expect(cella(r, field, 2027).title, `${field} 2027`).toContain("Forzato in CE Prev.");
      expect(cella(r, field, 2028).disabled, `${field} 2028`).toBe(false);
      expect(cella(r, field, 2029).disabled, `${field} 2029`).toBe(false);
    }
    // Le righe dei servizi e le due voci non collegate restano intatte.
    for (const field of ["variable_services_growth_pct", "personnel_growth_pct"]) {
      for (const y of PIANO) expect(cella(r, field, y).disabled, `${field} ${y}`).toBe(false);
    }
  });

  it("nessun anno forzato: nessuna cella si spegne, su nessuna riga", () => {
    const r = rows(40, 40);
    const fields = r.flatMap((x) => ("field" in x ? [x.field] : []));
    for (const field of fields) {
      for (const y of PIANO) expect(cella(r, field, y), `${field} ${y}`).toEqual({ disabled: false });
    }
  });

  it("una casella spenta dalla quota all'estremo porta il suo perche', non quello dell'override", () => {
    const r = rows(100, 40);
    const c = cella(r, "variable_materials_growth_pct", 2027);
    expect(c.disabled).toBe(true);
    expect(c.title).toContain("quota fissa al 100%");
    expect(c.title).not.toContain("CE Prev.");
  });
});

describe("alignVariablesToRevenue", () => {
  it("ogni anno prende la crescita dei ricavi di quell'anno, non una cifra sola", () => {
    const w = alignVariablesToRevenue(
      asMap({ 2027: { revenue_growth_pct: 8 }, 2028: { revenue_growth_pct: 3.5 } }), [2027, 2028]
    );
    expect(w).toEqual([
      { year: 2027, field: "variable_materials_growth_pct", value: 8 },
      { year: 2027, field: "variable_services_growth_pct", value: 8 },
      { year: 2028, field: "variable_materials_growth_pct", value: 3.5 },
      { year: 2028, field: "variable_services_growth_pct", value: 3.5 },
    ]);
  });

  it("un anno senza crescita dichiarata allinea a zero, che e' cio' che il motore userebbe", () => {
    expect(alignVariablesToRevenue(asMap({ 2027: {} }), [2027]).map((w) => w.value)).toEqual([0, 0]);
  });

  it("nessun anno previsto, nessuna scrittura", () => {
    expect(alignVariablesToRevenue(asMap({}), [])).toEqual([]);
  });
});

describe("costiPreview", () => {
  const share = { materials: 32.5, services: 60 };

  it("senza risposta del motore non c'e' anteprima: nessuna riga, non righe a zero", () => {
    expect(costiPreview(baseInc, share, null).tableRows).toEqual([]);
    expect(costiPreview(undefined, share, response([year(2027)])).years).toEqual([]);
  });

  it("gli anni sono quelli che il motore ha prodotto, non quelli richiesti", () => {
    const p = costiPreview(baseInc, share, response([year(2027)]));
    expect(p.years).toEqual([2027]);
    expect(p.bars).toHaveLength(1);
  });

  it("la riga dei fornitori esce dalla tabella e resta disponibile da sola", () => {
    const p = costiPreview(baseInc, share, response([year(2027)]));
    expect(p.tableRows.some((r) => r.key === "fornitori")).toBe(false);
    expect(p.fornitori?.key).toBe("fornitori");
    expect(p.tableRows.map((r) => r.key)).toContain("mol");
  });

  it("i giorni dell'occhiello sono il dpo del primo anno previsto", () => {
    const y2 = year(2028);
    y2.details.dpo_applied = 91;
    expect(costiPreview(baseInc, share, response([year(2027), y2])).dpo).toBe(78);
  });

  it("le barre vengono dai details del motore, non dallo slider", () => {
    const p = costiPreview(baseInc, share, response([year(2027)]));
    // 130 + 120 + 155 (personale) + 30 (godimento) e 300 + 90: i numeri del motore.
    expect(p.bars[0]).toEqual({ year: 2027, fixed: 435, variable: 390, fixedFlex: 435, variableFlex: 390 });
  });

  it("con la ripartizione forzata le barre sono assenti, e le larghezze non vanno in negativo", () => {
    const y = year(2027);
    y.details.ce05_fixed = null;
    y.details.ce05_variable = null;
    const p = costiPreview(baseInc, share, response([y]));
    expect(p.bars[0].fixed).toBeNull();
    expect(p.bars[0].variable).toBeNull();
    expect(p.bars[0].fixedFlex).toBe(0);
    expect(p.weight.last).toBeNull();
  });

  it("il peso dei fissi va dall'anno base all'ultimo anno previsto", () => {
    const y2 = year(2028);
    y2.details.ce05_fixed = 140;
    y2.income_statement.ce05_materie_prime = 440;
    y2.details.ce05_variable = 300;
    const p = costiPreview(baseInc, share, response([year(2027), y2]));
    // base: (400*0.325 + 200*0.6 + 150 + 30) / (400+200+30+150)
    expect(p.weight.base).toBeCloseTo((400 * 0.325 + 200 * 0.6 + 180) / 780 * 100, 6);
    // ultimo: (140 + 120 + 155 + 30) / (440 + 210 + 30 + 155)
    expect(p.weight.last).toBeCloseTo((140 + 120 + 185) / 835 * 100, 6);
  });

  it("una risposta senza anni da' la sola colonna base e nessuna barra", () => {
    const p = costiPreview(baseInc, share, response([]));
    expect(p.years).toEqual([]);
    expect(p.bars).toEqual([]);
    expect(p.dpo).toBeNull();
    expect(p.weight.last).toBeNull();
    expect(p.weight.base).not.toBeNull();
    expect(p.tableRows.length).toBeGreaterThan(0);
  });
});
