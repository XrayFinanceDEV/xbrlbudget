import { describe, expect, it } from "vitest";
import type { BalanceSheet, FinancingLoanInput } from "@/types/api";
import {
  chiusuraResidui, contrattiPregressi, contrattoRows, controlliBanche, controlloAltri, finanziatoreDalBilancio, nuovoContratto,
  prestitiNuovi, quotaMutui, restaStato, serveInizializzareFidi, unisciContratti, withRimborso,
} from "./budget-finanziamenti-pregresso";

// sp17a 557.500 + sp17b 150.000 = sp17 707.500 (quadra sull'aggregato): il debito bancario base
// vale 730.000 (sp16a 172.500 + sp17a 557.500) — coerente col resto del bilancio, a differenza
// della prima versione del banco (rilievo del coordinatore su 5dceddb: 172.500+467.500=640.000
// non tornava con nessuna combinazione sensata di fidi/residui usata sotto).
const bs = {
  sp16_debiti_breve: "172500", sp16a_debiti_banche_breve: "172500", sp17_debiti_lungo: "707500",
  sp17a_debiti_banche_lungo: "557500", sp17b_debiti_altri_finanz_lungo: "150000", sp16b_debiti_altri_finanz_breve: "0",
} as unknown as BalanceSheet;
const mutuo: FinancingLoanInput = { name: "Mutuo Intesa 2022", amount: 0, opening_residual: 330000, interest_rate: 3.8, grace_years: 0, balloon_pct: 0, duration_years: null, repayments: [82500, 82500, 82500] };
const mcc: FinancingLoanInput = { name: "Chirografario MCC 2024", amount: 0, opening_residual: 310000, interest_rate: 4.6, grace_years: 0, balloon_pct: 0, duration_years: null, repayments: [0, 55000, 55000] };
const nuovo: FinancingLoanInput = { name: "Nuovo finanziamento BPM", amount: 500000, opening_residual: 0, interest_rate: 4.5, grace_years: 1, balloon_pct: 0, duration_years: 6 };

describe("budget-finanziamenti-pregresso", () => {
  it("separa i contratti pregressi dai prestiti nuovi", () => {
    expect(contrattiPregressi([mutuo, nuovo, mcc]).map((l) => l.name)).toEqual(["Mutuo Intesa 2022", "Chirografario MCC 2024"]);
    expect(prestitiNuovi([mutuo, nuovo]).map((l) => l.name)).toEqual(["Nuovo finanziamento BPM"]);
  });
  it("una riga appena aggiunta, a residuo zero, resta fra i pregressi (collaudo R6)", () => {
    const vuota = nuovoContratto(2, 3);
    expect(contrattiPregressi([mutuo, vuota]).map((l) => l.name)).toEqual(["Mutuo Intesa 2022", "Finanziamento B"]);
    expect(contrattoRows(contrattiPregressi([mutuo, vuota]), 3)).toHaveLength(2);
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
  it("precompila il residuo degli altri finanziatori dal bilancio, senza rate inventate", () => {
    const base = {
      sp16b_debiti_altri_finanz_breve: "12503.74",
      sp17b_debiti_altri_finanz_lungo: "24000",
    } as unknown as BalanceSheet;
    const iniziale = finanziatoreDalBilancio(base, 5);
    expect(iniziale).toEqual({
      name: "Finanziatore 1", opening_residual: 36503.74,
      interest_rate: 0, repayments: [0, 0, 0, 0, 0],
    });
    expect(controlloAltri(base, [iniziale!]).ok).toBe(true);
    expect(finanziatoreDalBilancio({} as BalanceSheet, 3)).toBeNull();
  });
  it("quota dei mutui e controlli sulle banche", () => {
    expect(quotaMutui(bs, 90000)).toBe(82500);
    const c = controlliBanche(bs, 90000, [mutuo, mcc], 3, 2026);
    expect(c.fidiOltre).toBeNull();
    expect(c.quadra).toEqual({ ok: true, testo: "Fidi 90.000 € + residui dei finanziamenti 640.000 € · debiti verso banche nel bilancio: 730.000 €", esito: "quadra", differenza: 0 });
    expect(c.rata).toEqual({ ok: true, testo: "Rimborsi 2027 dei finanziamenti: 82.500 € · quota dei mutui entro 12 mesi: 82.500 €", esito: "coerente", differenza: 0 });
    const k = controlliBanche(bs, 200000, [mutuo], 3, 2026);
    expect(k.fidiOltre?.esito).toBe("da correggere");
    expect(k.quadra).toMatchObject({ ok: false, esito: "differenza 200.000 €" });
    // Sforamento: fidi + residui superano il debito bancario del bilancio — il motore lo
    // rifiuta esattamente come la carenza (§5.2: |scarto| oltre 0,01), quindi il controllo
    // simmetrico segnala anche questo caso, col segno meno.
    const sforo = controlliBanche(
      bs, 90000, [mutuo, mcc, { opening_residual: 10000, interest_rate: 0, repayments: [] }], 3, 2026,
    );
    expect(sforo.quadra).toMatchObject({ ok: false, esito: "differenza -10.000 €" });
    expect(controlliBanche(bs, 90000, [{ ...mutuo, repayments: [100000, 0, 0] }, mcc], 3, 2026).rata.esito).toBe("17.500 € oltre la quota a breve");
    expect(controlliBanche(bs, 90000, [{ ...mutuo, repayments: [60000, 0, 0] }, mcc], 3, 2026).rata.esito).toBe("nel 2027 ne scadono 22.500 € in più");
  });
  // Il caso segnalato dal proprietario il 2026-09-16: debito bancario 960.937,42 nel bilancio,
  // fidi 450.000 e residuo dichiarato 510.937. Il client diceva «quadra» (misurava all'euro) e il
  // motore rifiutava il piano (misura al centesimo): verde a sinistra, rifiuto a destra, e i 42
  // centesimi non comparivano da nessuna parte perché ogni importo era reso all'euro.
  it("42 centesimi non sono «quadra»: la soglia e la resa sono quelle del motore", () => {
    const bs42 = {
      sp16_debiti_breve: "450000", sp16a_debiti_banche_breve: "450000",
      sp17_debiti_lungo: "510937.42", sp17a_debiti_banche_lungo: "510937.42",
    } as unknown as BalanceSheet;
    const uno: FinancingLoanInput = { ...mutuo, name: "Finanziamento A", opening_residual: 510937, repayments: [43409, 45000, 48000] };
    const c = controlliBanche(bs42, 450000, [uno], 3, 2026);
    expect(c.quadra.ok).toBe(false);
    expect(c.quadra.esito).toBe("differenza 0,42 €");
    // Il bersaglio si legge al centesimo: è la cifra che l'utente deve raggiungere.
    expect(c.quadra.testo).toContain("960.937,42 €");
    // Gli importi tondi restano tondi: nessun «,00» sparso ovunque.
    expect(c.quadra.testo).toContain("Fidi 450.000 €");
    // Un clic chiude lo scarto, sul contratto più grosso e dicendo quale.
    const fix = chiusuraResidui([uno], c.quadra.differenza);
    expect(fix).toEqual({ indice: 0, nome: "Finanziamento A", importo: 0.42 });
    const dopo = controlliBanche(bs42, 450000, [{ ...uno, opening_residual: 510937.42 }], 3, 2026);
    expect(dopo.quadra).toMatchObject({ ok: true, esito: "quadra" });
  });
  it("la chiusura si offre solo per uno scarto da arrotondamento", () => {
    const a: FinancingLoanInput = { ...mutuo, name: "Piccolo", opening_residual: 1000 };
    const b: FinancingLoanInput = { ...mutuo, name: "Grosso", opening_residual: 9000 };
    // Il bersaglio è il residuo più alto, non il primo della lista.
    expect(chiusuraResidui([a, b], 1.5)).toMatchObject({ indice: 1, nome: "Grosso" });
    // Sopra i due euro è una scelta di piano: la fa l'utente.
    expect(chiusuraResidui([a, b], 2.5)).toBeNull();
    // Dentro la tolleranza del motore non c'è nulla da chiudere.
    expect(chiusuraResidui([a, b], 0.01)).toBeNull();
    // Senza contratti non c'è dove posarlo.
    expect(chiusuraResidui([], 0.42)).toBeNull();
    // Mai un residuo negativo.
    expect(chiusuraResidui([{ opening_residual: 0.1, interest_rate: 0, repayments: [] }], -1)).toBeNull();
  });
  it("controllo sugli altri finanziatori", () => {
    expect(controlloAltri(bs, [{ opening_residual: 150000, interest_rate: 0, repayments: [] }])).toMatchObject({ ok: true, esito: "quadra" });
    expect(controlloAltri(bs, [{ opening_residual: 100000, interest_rate: 0, repayments: [] }]).esito).toBe("differenza 50.000 €");
    // Sforamento simmetrico: 200.000 dichiarati contro 150.000 nel bilancio.
    expect(controlloAltri(bs, [{ opening_residual: 200000, interest_rate: 0, repayments: [] }]).esito).toBe("differenza -50.000 €");
  });
  it("serveInizializzareFidi: solo a riga presente e senza valore", () => {
    expect(serveInizializzareFidi(undefined)).toBe(false);
    expect(serveInizializzareFidi(null)).toBe(false);
    expect(serveInizializzareFidi({ bank_lines_amount: null })).toBe(true);
    expect(serveInizializzareFidi({ bank_lines_amount: 0 })).toBe(false);
    const legacy = { bank_lines_amount: null, bank_lines_rule: "costante" };
    expect(serveInizializzareFidi(legacy)).toBe(true);
  });
});
