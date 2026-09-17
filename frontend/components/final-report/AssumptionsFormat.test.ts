import { describe, it, expect } from "vitest";
import {
  describeScalar,
  formatDecimalString,
  indexingDriverLabel,
  integerText,
  overrideFieldLabel,
  PREGRESSO_BALANCES,
  scalarKindOf,
  temporaryDifferenceKind,
  temporaryDifferenceMaturity,
  yearsText,
} from "./AssumptionsFormat";

/**
 * La formattazione dei valori di ipotesi. È il punto dove un `DecimalString`
 * diventa testo leggibile, e dove un `null`, uno zero, un negativo e un booleano
 * devono restare quattro cose diverse.
 */
describe("formatDecimalString", () => {
  it("usa il separatore italiano senza toccare le cifre", () => {
    expect(formatDecimalString("1234.5")).toBe("1.234,5");
    expect(formatDecimalString("120.00")).toBe("120,00");
    expect(formatDecimalString("5")).toBe("5");
    expect(formatDecimalString("-1000")).toBe("-1.000");
    expect(formatDecimalString("1000000.67")).toBe("1.000.000,67");
  });

  it("non passa da un float: le cifre restano quelle persistite", () => {
    // 15.2 con Numeric(15,2): un `Number(...)` qui perderebbe il centesimo.
    expect(formatDecimalString("99999999999999.99")).toBe("99.999.999.999.999,99");
    expect(formatDecimalString("0.01")).toBe("0,01");
  });

  it("lo zero non ha segno, il meno sì", () => {
    expect(formatDecimalString("-0.00")).toBe("0,00");
    expect(formatDecimalString("0")).toBe("0");
    expect(formatDecimalString("-0.01")).toBe("-0,01");
  });

  it("una stringa che non è un decimale piano resta com'è", () => {
    expect(formatDecimalString("1e3")).toBe("1e3");
    expect(formatDecimalString("non un numero")).toBe("non un numero");
  });
});

describe("describeScalar", () => {
  it("null è assenza dichiarata, non zero", () => {
    const view = describeScalar(null, "eur");
    expect(view.text).toBe("—");
    expect(view.absent).toBe(true);
    expect(view.zero).toBe(false);
    expect(view.srText).toBe("nessun valore");
  });

  it("zero e negativo si vedono nel testo", () => {
    expect(describeScalar("0", "pct")).toMatchObject({ text: "0%", zero: true, negative: false });
    const negative = describeScalar("-2.5", "pct");
    expect(negative.text).toBe("-2,5%");
    expect(negative.negative).toBe(true);
    expect(negative.zero).toBe(false);
  });

  it("i booleani si leggono, non si colorano", () => {
    expect(describeScalar(true, "bool").text).toBe("Sì");
    expect(describeScalar(false, "bool")).toMatchObject({ text: "No", absent: false, zero: false });
  });

  it("ogni specie ha la sua unità, nel testo e nello screen reader", () => {
    expect(describeScalar("58", "days").text).toBe("58 giorni");
    expect(describeScalar("5", "years").text).toBe("5 anni");
    expect(describeScalar("1000", "eur").text).toBe("1.000 €");
    expect(describeScalar("27.9", "pct").srText).toBe("27,9 per cento");
    expect(describeScalar("58", "days").srText).toBe("58 giorni");
  });

  it("un testo che non è un decimale si mostra, marcato non riconosciuto", () => {
    const view = describeScalar("1e3", "eur");
    expect(view.text).toContain("1e3");
    expect(view.malformed).toBe(true);
    expect(view.absent).toBe(false);
  });

  it("null nelle nidificate non è un valore a zero", () => {
    // Le righe nidificate portano `values: [null, null, null]` e il dato nella
    // tabella: il trattino della cella non deve leggersi come "zero".
    expect(describeScalar(null, "number").text).toBe("—");
    expect(describeScalar(null, "eur").text.includes("0")).toBe(false);
    expect(describeScalar("0", "eur").text).toBe("0 €");
  });
});

describe("scalarKindOf", () => {
  it("prende l'unità dalla regola del campo, non da una tabella parallela", () => {
    expect(scalarKindOf("revenue_growth_pct")).toBe("pct");
    expect(scalarKindOf("dso_days")).toBe("days");
    expect(scalarKindOf("existing_debt_repayment_years")).toBe("years");
    expect(scalarKindOf("cash_sweep_enabled")).toBe("bool");
    expect(scalarKindOf("tax_advances_paid")).toBe("eur");
    expect(scalarKindOf("financing_loans")).toBe("number");
    expect(scalarKindOf("fixed_materials_growth_auto")).toBe("bool");
  });

  it("la regola dei fidi è un testo, e si legge con le parole del wizard", () => {
    // Senza questo ramo «costante» usciva tale e quale, con accanto «valore non riconosciuto».
    expect(scalarKindOf("bank_lines_rule")).toBe("text");
    expect(describeScalar("costante", "text")).toMatchObject({ text: "Costanti", malformed: false, absent: false });
    expect(describeScalar("ricavi", "text")).toMatchObject({ text: "Seguono i ricavi", malformed: false });
    // Un valore che il wizard non conosce non si traveste da regola: si mostra com'è e si segnala.
    expect(describeScalar("altro", "text")).toMatchObject({ text: "altro", malformed: true });
    expect(describeScalar(null, "text").absent).toBe(true);
  });
});

describe("etichette delle tabelle nidificate", () => {
  it("gli anni hanno il plurale giusto", () => {
    expect(yearsText(1)).toBe("1 anno");
    expect(yearsText(5)).toBe("5 anni");
    expect(integerText(1234)).toBe("1.234");
    expect(yearsText(0)).toBe("0 anni");
  });

  it("le posizioni del pregresso sono cinque, in ordine", () => {
    expect(PREGRESSO_BALANCES.map((balance) => balance.key)).toEqual([
      "crediti_commerciali",
      "debiti_fornitori",
      "debiti_tributari",
      "debiti_previdenziali",
      "altri_debiti",
    ]);
  });

  it("natura, scadenza e pilota si leggono in italiano", () => {
    expect(temporaryDifferenceKind("deductible")).toBe("Deducibile");
    expect(temporaryDifferenceKind("taxable")).toBe("Tassabile");
    expect(temporaryDifferenceMaturity("short")).toBe("Breve");
    expect(temporaryDifferenceMaturity("long")).toBe("Lunga");
    expect(indexingDriverLabel("ricavi")).toBe("Ricavi");
    expect(indexingDriverLabel("acquisti")).toBe("Acquisti");
    expect(indexingDriverLabel("personale")).toBe("Personale");
  });
});

describe("overrideFieldLabel", () => {
  it("la voce del catalogo vince sul codice", () => {
    expect(overrideFieldLabel("sp09_disponibilita_liquide")).toBe("IV - Disponibilità liquide");
    expect(overrideFieldLabel("ce02_override")).toBe(overrideFieldLabel("ce02_variazioni_rimanenze"));
  });

  it("un prefisso ambiguo non diventa un'etichetta", () => {
    // `sp16` è l'aggregato, `sp16a` un'altra voce: chi non trova UNA SOLA voce
    // col prefisso richiesto mostra il codice, non la prima corrispondenza.
    expect(overrideFieldLabel("zz99_inventato")).toBe("zz99_inventato");
    expect(overrideFieldLabel("")).toBe("");
  });
});
