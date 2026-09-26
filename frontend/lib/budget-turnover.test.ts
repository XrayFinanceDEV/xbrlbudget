import { describe, it, expect } from "vitest";
import { computeAutoDays } from "@/lib/budget-turnover";
import type { BalanceSheet, IncomeStatement } from "@/types/api";

const income = (over: Record<string, unknown>) =>
  ({
    ce01_ricavi_vendite: "0",
    ce05_materie_prime: "0",
    ce06_servizi: "0",
    ce10_var_rimanenze_mat_prime: "0",
    ...over,
  }) as unknown as IncomeStatement;

const balance = (over: Record<string, unknown>) =>
  ({
    sp05_rimanenze: "0",
    sp05a_materie_prime: "0",
    sp05e_acconti: "0",
    sp06_crediti_breve: "0",
    sp06e_crediti_tributari_breve: "0",
    sp06f_imposte_anticipate_breve: "0",
    sp16d_debiti_fornitori_breve: "0",
    ...over,
  }) as unknown as BalanceSheet;

describe("computeAutoDays — dso", () => {
  // I numeri sono quelli di AIC SRL, anno base 2024, dall'issue #31.
  const aicIncome = income({ ce01_ricavi_vendite: "24950524" });
  const aicBalance = balance({
    sp06_crediti_breve: "8451310",
    sp06e_crediti_tributari_breve: "387213",
  });

  it("scorpora i crediti tributari, come fa il motore", () => {
    // (8.451.310 - 387.213) / 24.950.524 x 360 = 116,35 -> 116.
    // Il segnaposto diceva 122 — l'aggregato intero — mentre il motore
    // applicava 116: 122 giorni valgono ~430.000 EUR di crediti in piu' sul
    // primo anno di piano, che si scaricano sul plug di cassa e quindi su
    // current ratio, CCN e componente A dell'Altman.
    expect(computeAutoDays("dso", aicIncome, aicBalance)).toBe(116);
  });

  it("scorpora anche le imposte anticipate", () => {
    const bs = balance({
      sp06_crediti_breve: "8451310",
      sp06e_crediti_tributari_breve: "387213",
      sp06f_imposte_anticipate_breve: "100000",
    });
    // (8.451.310 - 387.213 - 100.000) / 24.950.524 x 360 = 114,91 -> 115.
    expect(computeAutoDays("dso", aicIncome, bs)).toBe(115);
  });

  it("con entrambe le componenti a zero il valore non cambia", () => {
    const bs = balance({ sp06_crediti_breve: "3600000" });
    expect(computeAutoDays("dso", income({ ce01_ricavi_vendite: "3600000" }), bs)).toBe(360);
  });

  it("clampa a zero quando le componenti non commerciali superano l'aggregato", () => {
    // Stesso `max(ZERO, ...)` del motore: un aggregato incoerente non produce
    // giorni negativi, che nel piano diventerebbero crediti negativi.
    const bs = balance({
      sp06_crediti_breve: "100000",
      sp06e_crediti_tributari_breve: "150000",
    });
    expect(computeAutoDays("dso", income({ ce01_ricavi_vendite: "3600000" }), bs)).toBe(0);
  });

  it("tace senza ricavi", () => {
    expect(computeAutoDays("dso", income({}), aicBalance)).toBeNull();
  });
});

// lotto 1 fix rilievi (2026-09-26): B01 — il ramo `dio` non guida più le rimanenze sui
// ricavi, ma le sole materie prime (sp05a) sul CONSUMO dell'anno base (ce05 + ce10), perché
// il motore ora calcola sp05a dal consumo, non più dal fatturato. Il vecchio test pinnava
// "410.000 / 3.600.000 x 360 = 41" sull'aggregato intero e sui ricavi: comportamento che la
// spec B01 cambia di proposito, quindi si aggiorna qui invece di restare xfail.
describe("computeAutoDays — dio sul consumo delle materie (B01)", () => {
  it("scorpora le materie prime e divide sul consumo, non sui ricavi", () => {
    const bs = balance({ sp05_rimanenze: "36", sp05a_materie_prime: "36" });
    const is = income({ ce01_ricavi_vendite: "1000", ce05_materie_prime: "260" });
    // 36 / (260 + 0) x 360 = 49,85 -> 50. I ricavi (1.000) non intervengono più.
    expect(computeAutoDays("dio", is, bs)).toBe(50);
  });

  it("tace quando il consumo (ce05 + ce10) non è positivo", () => {
    const bs = balance({ sp05_rimanenze: "36", sp05a_materie_prime: "36" });
    // ce05 260 + ce10 -260 = consumo 0.
    const is = income({ ce01_ricavi_vendite: "1000", ce05_materie_prime: "260", ce10_var_rimanenze_mat_prime: "-260" });
    expect(computeAutoDays("dio", is, bs)).toBeNull();
  });

  it("base senza sp05a usa l'aggregato meno gli acconti come materie", () => {
    const bs = balance({ sp05_rimanenze: "36", sp05e_acconti: "6" });
    const is = income({ ce01_ricavi_vendite: "1000", ce05_materie_prime: "260" });
    // (36 - 6) / 260 x 360 = 41,54 -> 42.
    expect(computeAutoDays("dio", is, bs)).toBe(42);
  });
});

describe("computeAutoDays — dpo resta invariato", () => {
  it("dpo sui fornitori sugli acquisti (materie + servizi)", () => {
    const bs = balance({ sp16d_debiti_fornitori_breve: "470000" });
    const is = income({ ce05_materie_prime: "2600000", ce06_servizi: "1000000" });
    // 470.000 / 3.600.000 x 360 = 47.
    expect(computeAutoDays("dpo", is, bs)).toBe(47);
  });

  it("tace senza acquisti", () => {
    expect(computeAutoDays("dpo", income({}), balance({}))).toBeNull();
  });
});

describe("computeAutoDays — dati mancanti", () => {
  it("tace senza anno base", () => {
    expect(computeAutoDays("dso", undefined, balance({}))).toBeNull();
    expect(computeAutoDays("dso", income({}), undefined)).toBeNull();
  });
});
