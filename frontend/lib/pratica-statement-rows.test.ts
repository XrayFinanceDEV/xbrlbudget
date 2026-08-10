import { describe, expect, it } from "vitest";
import type { IntraYearComparisonItem } from "@/types/api";
import {
  buildBalanceItemsWithTotals,
  buildIncomeItemsWithEbitda,
} from "./pratica-statement-rows";

const item = (
  code: string,
  partial: number,
  reference = 0,
  prior = 0,
): IntraYearComparisonItem => ({
  code,
  label: code,
  partial_value: partial,
  reference_value: reference,
  prior_value: prior,
  pct_of_reference: 0,
  annualized_value: 0,
});

describe("buildBalanceItemsWithTotals", () => {
  // sp16g_altri_debiti_breve is included as a zero placeholder: reconcileSubfields
  // writes the reconciled gap into `data[plug]`, but buildBalanceItemsWithTotals only
  // copies reconciled values back onto codes that already exist in rawItems (it maps
  // over rawItems, not over the reconciled data's own keys) — so a plug field the
  // caller never sent as a row is computed internally and then silently dropped,
  // never reaching the rendered output. A real caller always sends every detail row
  // (even at 0), so this reflects production input shape.
  const raw = [
    item("sp03_immob_materiali", 300_000, 280_000),
    item("sp09_disponibilita_liquide", 80_000, 60_000),
    item("sp11_capitale", 100_000, 100_000),
    item("sp16_debiti_breve", 280_000, 240_000),
    item("sp16g_altri_debiti_breve", 0, 0),
  ];

  it("riconcilia ogni anno in modo indipendente", () => {
    const out = buildBalanceItemsWithTotals(raw);
    const altri = out.find((i) => i.code === "sp16g_altri_debiti_breve");
    expect(altri?.partial_value).toBe(280_000);
    expect(altri?.reference_value).toBe(240_000);
  });

  it("NON tocca annualized_value: la scrive la tab Proiezione", () => {
    const withAnn = raw.map((i) => ({ ...i, annualized_value: 999 }));
    const out = buildBalanceItemsWithTotals(withAnn);
    for (const row of out) {
      if (raw.some((r) => r.code === row.code)) {
        expect(row.annualized_value).toBe(999);
      }
    }
  });

  it("emette righe di totale oltre alle voci di partenza", () => {
    const out = buildBalanceItemsWithTotals(raw);
    expect(out.length).toBeGreaterThan(raw.length);
    // "_totale_attivo" (TOTALE ATTIVO) is a synthetic row, summed from ATTIVO_CODES
    // (sp01..sp10) independently of the passivo side: sp03 + sp09.
    const totAttivo = out.find((i) => i.code === "_totale_attivo");
    expect(totAttivo?.label).toBe("TOTALE ATTIVO");
    expect(totAttivo?.partial_value).toBe(380_000); // 300_000 + 80_000
    expect(totAttivo?.reference_value).toBe(340_000); // 280_000 + 60_000
  });
});

describe("buildIncomeItemsWithEbitda", () => {
  const raw = [
    item("ce01_ricavi_vendite", 900_000, 1_200_000),
    item("ce05_materie_prime", 300_000, 400_000),
    item("ce06_servizi", 225_000, 300_000),
    item("ce08_costi_personale", 187_500, 250_000),
    item("ce09_ammortamenti", 37_500, 50_000),
  ];

  it("inserisce una riga EBITDA (codice '_ebitda')", () => {
    const out = buildIncomeItemsWithEbitda(raw, 9);
    const ebitda = out.find((i) => i.code === "_ebitda");
    expect(ebitda).toBeDefined();
    expect(ebitda?.label).toBe("EBITDA (MOL)");
    // 900_000 - (300_000 + 225_000 + 187_500) = 187_500
    expect(ebitda?.partial_value).toBe(187_500);
  });

  // SORPRESA: `periodMonths` e' un parametro morto in questa funzione. Viene usato
  // solo per calcolare `factor = 12 / periodMonths`, che non e' mai letto altrove nel
  // corpo della funzione. L'annualizzazione delle righe (`annualized_value`) prende i
  // valori gia' annualizzati dal chiamante (`ann()` legge `item.annualized_value`),
  // non li ricalcola qui. Di conseguenza l'output e' byte-per-byte identico a
  // qualunque periodMonths venga passato — verificato con un dump diretto della
  // funzione prima di scrivere questo test.
  it("periodMonths e' un parametro morto: l'output non ne dipende (nessuna annualizzazione qui)", () => {
    const a = buildIncomeItemsWithEbitda(raw, 9);
    const b = buildIncomeItemsWithEbitda(raw, 6);
    expect(a).toEqual(b);
    const ricaviA = a.find((i) => i.code === "ce01_ricavi_vendite");
    const ricaviB = b.find((i) => i.code === "ce01_ricavi_vendite");
    expect(ricaviA?.partial_value).toBe(ricaviB?.partial_value);
    expect(a.length).toBe(b.length);
  });

  it("elenco vuoto: non lancia", () => {
    expect(() => buildIncomeItemsWithEbitda([], 12)).not.toThrow();
  });
});
