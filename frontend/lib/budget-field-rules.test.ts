import { describe, expect, it } from "vitest";
import { FIELD_RULES, fieldRule, parseFieldValue, type FieldName, type FieldRule } from "./budget-field-rules";
import { STEP_FIELDS } from "./budget-wizard-steps";

describe("budget-field-rules", () => {
  it("ogni campo scalare dei passi ha una regola", () => {
    const json = new Set(["financing_loans", "tax_temporary_differences"]);
    for (const fields of Object.values(STEP_FIELDS))
      for (const f of fields) if (!json.has(f)) expect(fieldRule(f), f).toBeDefined();
  });

  /**
   * La guardia vera delle righe di `components/budget/assumption-rows.ts` e' il
   * TIPO, non un test: `rule()` accetta solo `FieldName`, cioe' le chiavi di
   * `FIELD_RULES`. `lib/` non puo' importare da `components/`, quindi la regola
   * non si puo' esercitare da qui su quelle righe — ma un errore di tipo non
   * spiega perche' la regola esiste, e questo test lo scrive.
   *
   * Prima, `rule(["campo_inventato"], {...})` faceva lo spread di `undefined` e
   * produceva una riga senza `kind` e senza `min/max/step`: la casella nasceva
   * senza validazione, `tsc` restava pulito e la suite verde. L'iniezione del
   * revisore era esattamente quella.
   *
   * `@ts-expect-error` qui sotto e' un'asserzione a tutti gli effetti: se
   * qualcuno riportasse `FIELD_RULES` a `Record<string, FieldRule>`, l'errore
   * atteso sparirebbe e `tsc` fallirebbe su questa riga.
   */
  it("un campo senza regola non e' un `FieldName`: lo ferma tsc", () => {
    const noto: FieldName = "revenue_growth_pct";
    expect(FIELD_RULES[noto]).toBeDefined();

    // @ts-expect-error — "campo_inventato" non e' una chiave di FIELD_RULES.
    const inventato: FieldRule = FIELD_RULES["campo_inventato"];
    expect(inventato).toBeUndefined();

    // Chi ha in mano una stringa qualunque passa da `fieldRule`, che dichiara
    // l'assenza invece di nasconderla in uno spread.
    expect(fieldRule("campo_inventato")).toBeUndefined();
  });

  it("parse: virgola, vuoto, clamp", () => {
    expect(parseFieldValue("revenue_growth_pct", "12,5")).toBe(12.5);
    expect(parseFieldValue("dso_days", "")).toBeNull();
    expect(parseFieldValue("revenue_growth_pct", "")).toBe(0);
    expect(parseFieldValue("fixed_materials_percentage", "140")).toBe(100);
    expect(parseFieldValue("tangible_investments", "-5")).toBe(0);
  });

  it("financing_interest_rate ha un intervallo piu' stretto del pct % generico", () => {
    // -100..100 e' il range di default: se l'override sparisse, questi due
    // valori (dentro il range generico ma fuori da 0..30) non verrebbero
    // clampati e il test lo rileverebbe.
    expect(FIELD_RULES.financing_interest_rate).toEqual({ kind: "pct", step: "0.1", min: 0, max: 30 });
    expect(parseFieldValue("financing_interest_rate", "50")).toBe(30);
    expect(parseFieldValue("financing_interest_rate", "-5")).toBe(0);
  });

  it("i campi days() clampano al massimo reale, non solo nullable -> null", () => {
    expect(FIELD_RULES.dso_days).toEqual({ kind: "days", nullable: true, min: 0, max: 365 });
    expect(parseFieldValue("dso_days", "400")).toBe(365);
  });

  it("un campo per ogni kind distinto, con step pinnato", () => {
    expect(FIELD_RULES.revenue_growth_pct).toEqual({ kind: "pct", step: "0.1", min: -100, max: 100 });
    expect(FIELD_RULES.tangible_investments).toEqual({ kind: "eur", min: 0, step: "1000" });
    expect(FIELD_RULES.existing_debt_repayment_years).toEqual({ kind: "years", nullable: true, min: 0, max: 30 });
    expect(FIELD_RULES.dio_days).toEqual({ kind: "days", nullable: true, min: 0, max: 365 });
    expect(FIELD_RULES.cash_sweep_enabled).toEqual({ kind: "bool" });
  });
});
