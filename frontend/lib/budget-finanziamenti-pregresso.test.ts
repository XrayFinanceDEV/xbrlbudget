import { describe, expect, it } from "vitest";
import type { BalanceSheet, FinancingLoanInput } from "@/types/api";
import {
  contrattiPregressi, contrattoRows, controlliBanche, controlloAltri, nuovoContratto, prestitiNuovi,
  quotaMutui, restaStato, unisciContratti, withRimborso,
} from "./budget-finanziamenti-pregresso";

const bs = {
  sp16_debiti_breve: "172500", sp16a_debiti_banche_breve: "172500", sp17_debiti_lungo: "617500",
  sp17a_debiti_banche_lungo: "467500", sp17b_debiti_altri_finanz_lungo: "150000", sp16b_debiti_altri_finanz_breve: "0",
} as unknown as BalanceSheet;
const mutuo: FinancingLoanInput = { name: "Mutuo Intesa 2022", amount: 0, opening_residual: 330000, interest_rate: 3.8, grace_years: 0, balloon_pct: 0, duration_years: null, repayments: [82500, 82500, 82500] };
const mcc: FinancingLoanInput = { name: "Chirografario MCC 2024", amount: 0, opening_residual: 310000, interest_rate: 4.6, grace_years: 0, balloon_pct: 0, duration_years: null, repayments: [0, 55000, 55000] };
const nuovo: FinancingLoanInput = { name: "Nuovo finanziamento BPM", amount: 500000, opening_residual: 0, interest_rate: 4.5, grace_years: 1, balloon_pct: 0, duration_years: 6 };

describe("budget-finanziamenti-pregresso", () => {
  it("separa i contratti pregressi dai prestiti nuovi", () => {
    expect(contrattiPregressi([mutuo, nuovo, mcc]).map((l) => l.name)).toEqual(["Mutuo Intesa 2022", "Chirografario MCC 2024"]);
    expect(prestitiNuovi([mutuo, nuovo]).map((l) => l.name)).toEqual(["Nuovo finanziamento BPM"]);
  });
  it("righe: rimborsi riempiti all'orizzonte, resta e stato", () => {
    const [r] = contrattoRows([mutuo], 5);
    expect(r).toMatchObject({ name: "Mutuo Intesa 2022", residuo: 330000, tasso: 3.8, rimborsi: [82500, 82500, 82500, 0, 0], resta: 82500, stato: "resta aperto" });
    expect(restaStato(100, [100])).toBe("chiuso");
    expect(restaStato(100, [0, 0])).toBe("nessun rimborso nel piano");
    expect(restaStato(100, [60, 60])).toBe("oltre il residuo");
  });
  it("withRimborso scrive l'anno e tronca la lista all'orizzonte", () => {
    const out = withRimborso([mutuo], 0, 3, 82500, 3);
    expect(out[0].repayments).toEqual([82500, 82500, 82500]);
    expect(withRimborso([mutuo], 0, 1, null, 3)[0].repayments).toEqual([82500, 0, 82500]);
  });
  it("unisci: somma dei residui, tasso medio ponderato, rimborsi sommati", () => {
    const [u] = unisciContratti([mutuo, mcc], 3);
    expect(u).toMatchObject({ name: "Debiti verso banche", opening_residual: 640000, interest_rate: 4.2, repayments: [82500, 137500, 137500], amount: 0, duration_years: null });
  });
  it("nuovoContratto e' vuoto e nominato in sequenza", () => {
    expect(nuovoContratto(3, 3)).toEqual({ name: "Finanziamento C", amount: 0, opening_residual: 0, interest_rate: 4, grace_years: 0, balloon_pct: 0, duration_years: null, repayments: [0, 0, 0] });
  });
  it("quota dei mutui e controlli sulle banche", () => {
    expect(quotaMutui(bs, 90000)).toBe(82500);
    const c = controlliBanche(bs, 90000, [mutuo, mcc], 3, 2026);
    expect(c.fidiOltre).toBeNull();
    expect(c.quadra).toEqual({ ok: true, testo: "Fidi 90.000 € + residui dei finanziamenti 640.000 € · debiti verso banche nel bilancio: 640.000 €", esito: "quadra" });
    expect(c.rata).toEqual({ ok: true, testo: "Rimborsi 2027 dei finanziamenti: 82.500 € · quota dei mutui entro 12 mesi: 82.500 €", esito: "coerente" });
    const k = controlliBanche(bs, 200000, [mutuo], 3, 2026);
    expect(k.fidiOltre?.esito).toBe("da correggere");
    expect(k.quadra).toMatchObject({ ok: false, esito: "differenza 110.000 €" });
    expect(controlliBanche(bs, 90000, [{ ...mutuo, repayments: [100000, 0, 0] }, mcc], 3, 2026).rata.esito).toBe("17.500 € oltre la quota a breve");
    expect(controlliBanche(bs, 90000, [{ ...mutuo, repayments: [60000, 0, 0] }, mcc], 3, 2026).rata.esito).toBe("nel 2027 ne scadono 22.500 € in più");
  });
  it("controllo sugli altri finanziatori", () => {
    expect(controlloAltri(bs, [{ opening_residual: 150000, interest_rate: 0, repayments: [] }])).toMatchObject({ ok: true, esito: "quadra" });
    expect(controlloAltri(bs, [{ opening_residual: 100000, interest_rate: 0, repayments: [] }]).esito).toBe("differenza 50.000 €");
  });
});
