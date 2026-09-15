import { describe, expect, it } from "vitest";
import type { IncomeStatement } from "@/types/api";
import type { AssumptionsMap } from "@/lib/budget-horizon";
import type { CostiTableRow, ForcedSplit } from "./budget-costi-step";
import {
  FIXED_SHARE_DEFAULT,
  autoYearsOf,
  calcolateAltrove,
  costiBase,
  costiTableRows,
  fixedGrowthChange,
  fixedShareOf,
  forcedNote,
  forcedSplitYears,
  splitBaseAmount,
} from "./budget-costi-step";
import { euro } from "@/lib/budget-format";
import { yearCellState, type YearCellOff } from "./budget-year-cell";

const baseInc = {
  ce01_ricavi_vendite: "1000", ce04_altri_ricavi: "50", ce05_materie_prime: "400",
  ce06_servizi: "200", ce07_godimento_beni: "30", ce08_costi_personale: "150",
  ce12_oneri_diversi: "20", ce09_ammortamenti: "40", ce15_oneri_finanziari: "10", ce20_imposte: "30",
} as unknown as IncomeStatement;

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
  it("legge le cinque voci dell'anno base, oneri diversi compresi", () => {
    expect(costiBase(baseInc)).toEqual({ mat: 400, serv: 200, pers: 150, god: 30, od: 20 });
  });

  it("senza anno base sono assenti, non zero", () => {
    expect(costiBase(undefined)).toEqual({ mat: null, serv: null, pers: null, god: null, od: null });
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

describe("fixedGrowthChange", () => {
  it("vuoto torna all'inflazione e diventa automatico", () => {
    expect(fixedGrowthChange(null, 2.5)).toEqual({ value: 2.5, auto: true });
    expect(fixedGrowthChange(0, 2.5)).toEqual({ value: 0, auto: false });
  });
  it("un numero scritto a mano resta suo, e non e' piu' automatico", () => {
    expect(fixedGrowthChange(4.2, 2.5)).toEqual({ value: 4.2, auto: false });
  });
});

describe("autoYearsOf", () => {
  it("legge il flag per anno", () => {
    const map = asMap({ 2027: { fixed_materials_growth_auto: true }, 2028: { fixed_materials_growth_auto: false } });
    expect(autoYearsOf(map, [2027, 2028], "fixed_materials_growth_auto")).toEqual([2027]);
  });
  it("un anno assente non e' automatico", () => {
    expect(autoYearsOf(asMap({ 2027: {} }), [2027], "fixed_services_growth_auto")).toEqual([]);
  });
});

describe("costiTableRows", () => {
  const base = { mat: 1000, serv: 500, pers: 300, god: 100, od: 50 };
  const even = (v: number) => ({ value: v, uneven: false });
  const PIANO = [2027, 2028];
  const nulla: ForcedSplit = { years: PIANO, materials: [], services: [] };
  const nessunAuto = { materials: [] as number[], services: [] as number[] };
  const rows = (m: number, s: number, forced: ForcedSplit = nulla, auto = nessunAuto) =>
    costiTableRows(base, even(m), even(s), forced, auto);

  it("due gruppi: parte fissa (con anni automatici) e ipotesi manuali", () => {
    const rows = costiTableRows({ mat: 1000, serv: 500, pers: 300, god: 100, od: 50 }, { value: 40, uneven: false }, { value: 60, uneven: false },
      { years: [2027, 2028], materials: [], services: [] }, { materials: [2027, 2028], services: [2028] });
    expect(rows.map((r) => ("group" in r ? `#${r.group}` : r.field))).toEqual([
      "#Parte fissa", "fixed_materials_growth_pct", "fixed_services_growth_pct",
      "#Ipotesi manuali", "personnel_growth_pct", "rent_growth_pct", "other_costs_growth_pct",
    ]);
    const mat = rows[1] as { autoYears?: number[]; baseLabel: string };
    expect(mat.autoYears).toEqual([2027, 2028]);
    expect(mat.baseLabel).toBe(euro(400));
    const serv = rows[2] as { autoYears?: number[] };
    expect(serv.autoYears).toEqual([2028]);
  });

  it("i due gruppi portano il loro sottotitolo, e solo «Parte fissa» il pallino", () => {
    const r = rows(40, 40);
    expect(r[0]).toMatchObject({ group: "Parte fissa", swatch: "fixed" });
    expect(r[3]).toMatchObject({ group: "Ipotesi manuali" });
    expect((r[3] as { swatch?: string }).swatch).toBeUndefined();
  });

  it("le due righe di godimento e oneri diversi portano l'importo base, senza quota", () => {
    const r = rows(40, 40);
    const row = (field: string) => r.find((x) => "field" in x && x.field === field) as { baseLabel: string; sub?: string };
    expect(row("personnel_growth_pct").baseLabel).toBe(euro(300));
    expect(row("rent_growth_pct").baseLabel).toBe(euro(100));
    expect(row("other_costs_growth_pct").baseLabel).toBe(euro(50));
    expect(row("other_costs_growth_pct").sub).toBe("spostata qui da «Altre voci CE»");
  });

  it("la colonna base delle righe «fissa» mostra il taglio della quota, non l'importo intero", () => {
    const r = rows(25, 40);
    const baseLabel = (field: string) =>
      (r.find((x) => "field" in x && x.field === field) as { baseLabel: string }).baseLabel;
    expect(baseLabel("fixed_materials_growth_pct")).toBe(euro(250));
    expect(baseLabel("fixed_services_growth_pct")).toBe(euro(200));
  });

  it("senza anno base la colonna base e' un trattino, non uno zero", () => {
    const r = costiTableRows({ mat: null, serv: null, pers: null, god: null, od: null }, even(40), even(40),
      nulla, nessunAuto);
    const labels = r.flatMap((x) => ("baseLabel" in x ? [x.baseLabel] : []));
    expect(labels.every((l) => l === "—")).toBe(true);
  });

  it("a quota 0 la riga «fissa» si spegne, mai quella di personale/godimento/oneri", () => {
    const off = (r: ReturnType<typeof rows>, field: string) =>
      r.find((x) => "field" in x && x.field === field) as { off?: boolean };
    const zero = rows(0, 0);
    expect(off(zero, "fixed_materials_growth_pct").off).toBe(true);
    expect(off(zero, "fixed_services_growth_pct").off).toBe(true);
    expect(off(zero, "personnel_growth_pct").off).toBeUndefined();
    const quaranta = rows(40, 40);
    expect(off(quaranta, "fixed_materials_growth_pct").off).toBe(false);
  });

  it("con gli anni discordi l'estremo non spegne niente: un controllo che non sa non blocca", () => {
    const off = (r: CostiTableRow[], field: string) =>
      r.find((x) => "field" in x && x.field === field) as { off?: boolean };
    const zeroPoiQuaranta = { value: 0, uneven: true };
    const r = costiTableRows(base, zeroPoiQuaranta, even(40), nulla, nessunAuto);
    expect(off(r, "fixed_materials_growth_pct").off).toBe(false);
  });

  it("l'override marca la sola riga «fissa» del suo gruppo, e dice in quale anno", () => {
    const r = rows(40, 40, { years: PIANO, materials: [2027], services: [] });
    const sub = (field: string) =>
      (r.find((x) => "field" in x && x.field === field) as { sub?: string }).sub;
    expect(sub("fixed_materials_growth_pct")).toBe("forzato in CE Prev. nel 2027");
    expect(sub("fixed_services_growth_pct")).toBeUndefined();
    expect(sub("personnel_growth_pct")).toBeUndefined();
  });

  // La prova che la granularita' dell'override e' l'ANNO: `costiTableRows` produce le
  // righe, `yearCellState` — la stessa funzione che `YearInputTable` chiama per ogni
  // casella — dice se quella casella e' inerte. Le due insieme sono cio' che l'utente vede.
  const cella = (r: CostiTableRow[], field: string, y: number) =>
    yearCellState(r.find((x) => "field" in x && x.field === field) as YearCellOff, y);

  it("un anno forzato su due spegne SOLO quell'anno, e dice perche'", () => {
    const r = rows(40, 40, { years: PIANO, materials: [2027], services: [] });
    expect(cella(r, "fixed_materials_growth_pct", 2027).disabled).toBe(true);
    expect(cella(r, "fixed_materials_growth_pct", 2027).title).toContain("Forzato in CE Prev.");
    expect(cella(r, "fixed_materials_growth_pct", 2028).disabled).toBe(false);
    for (const y of PIANO) expect(cella(r, "personnel_growth_pct", y).disabled).toBe(false);
  });

  it("nessun anno forzato: nessuna cella si spegne, su nessuna riga", () => {
    const r = rows(40, 40);
    const fields = r.flatMap((x) => ("field" in x ? [x.field] : []));
    for (const field of fields) {
      for (const y of PIANO) expect(cella(r, field, y), `${field} ${y}`).toEqual({ disabled: false });
    }
  });

  it("una casella spenta dalla quota a zero porta il suo perche', non quello dell'override", () => {
    const r = rows(0, 40);
    const c = cella(r, "fixed_materials_growth_pct", 2027);
    expect(c.disabled).toBe(true);
    expect(c.title).toContain("quota fissa a 0%");
    expect(c.title).not.toContain("CE Prev.");
  });
});

describe("calcolateAltrove", () => {
  it("le tre righe della card, con la loro provenienza", () => {
    const rows = calcolateAltrove(2026);
    expect(rows.map((r) => r.label)).toEqual(["Ammortamenti", "Oneri finanziari", "Imposte"]);
    expect(rows.map((r) => r.passo)).toEqual(["passo 6", "passi 5 e 6", "passo 7"]);
  });
});
