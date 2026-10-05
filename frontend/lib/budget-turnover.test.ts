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

  it("base senza ALCUNA sotto-voce usa l'aggregato meno gli acconti come materie", () => {
    // sp05a..sp05e tutte a zero, aggregato positivo: nessun dettaglio, stesso ripiego
    // di `_alloc`/`_materie_base` nel motore.
    const bs = balance({ sp05_rimanenze: "36" });
    const is = income({ ce01_ricavi_vendite: "1000", ce05_materie_prime: "260" });
    // (36 - 0) / 260 x 360 = 49,85 -> 50.
    expect(computeAutoDays("dio", is, bs)).toBe(50);
  });

  // lotto 1 fix rilievi (2026-09-26), fix round 1: il ripiego sull'aggregato scatta SOLO
  // quando NESSUNA sotto-voce di sp05 e' valorizzata — non quando sp05a e' a zero ma
  // un'altra sotto-voce (qui sp05c) non lo e'. Materie davvero a zero non sono la stessa
  // cosa di materie senza dettaglio: confonderle sposterebbe la giacenza di un'altra
  // rimanenza sul DIO delle materie.
  it("sp05a a zero con sp05c valorizzato non attiva il ripiego: materie restano zero", () => {
    const bs = balance({ sp05_rimanenze: "36", sp05c_lavori_in_corso: "36" });
    const is = income({ ce01_ricavi_vendite: "1000", ce05_materie_prime: "260" });
    expect(computeAutoDays("dio", is, bs)).toBe(0);
  });
});

// #62 nota S04: due gruppi di giorni. `dio` = materie + semilavorati sul consumo; `dio_pf` =
// prodotti finiti sui ricavi. Il numero si restituisce anche oltre 365: decide il chiamante.
describe("computeAutoDays — due gruppi di magazzino (#62 S04)", () => {
  it("dio somma materie e semilavorati sul consumo", () => {
    const bs = balance({ sp05_rimanenze: "60", sp05a_materie_prime: "36", sp05b_prodotti_in_corso: "24" });
    const is = income({ ce01_ricavi_vendite: "1000", ce05_materie_prime: "260", ce10_var_rimanenze_mat_prime: "0" });
    // (36 + 24) / 260 x 360 = 83,08 -> 83.
    expect(computeAutoDays("dio", is, bs)).toBe(83);
  });

  it("dio_pf = sp05d / ricavi x 360", () => {
    const bs = balance({ sp05_rimanenze: "100", sp05d_prodotti_finiti: "100" });
    const is = income({ ce01_ricavi_vendite: "1000", ce05_materie_prime: "260" });
    expect(computeAutoDays("dio_pf", is, bs)).toBe(36);
  });

  it("dio_pf tace senza ricavi", () => {
    const bs = balance({ sp05d_prodotti_finiti: "100" });
    expect(computeAutoDays("dio_pf", income({ ce01_ricavi_vendite: "0" }), bs)).toBeNull();
  });

  it("dio oltre 365 restituisce il numero (807, caso AMBIENTA), non null", () => {
    const bs = balance({ sp05_rimanenze: "287312", sp05a_materie_prime: "287312" });
    const is = income({ ce05_materie_prime: "129308", ce10_var_rimanenze_mat_prime: "-1217" });
    expect(computeAutoDays("dio", is, bs)).toBe(807);
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
