import { describe, expect, it } from "vitest";
import { baseBankDebt, sommaResiduiIniziali, statoResidui } from "./base-bank-debt";

/**
 * Questi casi valgono come specchio di
 * `calculations/projection_common.py:base_bank_debt`. Il numero mostrato
 * all'utente deve essere lo STESSO contro cui valida il motore: se qui si
 * scrivesse la formula «ovvia» (`sp16a + sp17a`) la card direbbe «coperto» su
 * un piano che il server poi rifiuta.
 */

/** Bilancio ordinario: gli aggregati coincidono con la somma dei dettagli. */
const ORDINARIO = {
  sp16_debiti_breve: "300000",
  sp16a_debiti_banche_breve: "100000",
  sp16d_debiti_fornitori_breve: "150000",
  sp16e_debiti_tributari_breve: "50000",
  sp17_debiti_lungo: "200000",
  sp17a_debiti_banche_lungo: "180000",
  sp17b_debiti_altri_finanz_lungo: "20000",
};

describe("baseBankDebt", () => {
  it("bilancio ordinario: sono le sole banche esplicite", () => {
    expect(baseBankDebt(ORDINARIO)).toBe(280_000); // 100.000 + 180.000
  });

  // Il caso che rende la formula «ovvia» sbagliata.
  it("bilancio abbreviato: lo scarto aggregato/dettagli va alle banche", () => {
    const abbreviato = {
      sp16_debiti_breve: "300000",
      sp17_debiti_lungo: "200000",
      // nessun dettaglio: tutto sta negli aggregati
    };
    expect(baseBankDebt(abbreviato)).toBe(500_000);
    // la formula «ovvia» darebbe zero, cioe' un piano «coperto» da nulla
    expect(baseBankDebt(abbreviato)).not.toBe(0);
  });

  it("scarto parziale: banche esplicite più il residuo dell'aggregato", () => {
    const misto = {
      sp16_debiti_breve: "300000",
      sp16a_debiti_banche_breve: "100000",
      sp16d_debiti_fornitori_breve: "120000",
      sp17_debiti_lungo: "200000",
      sp17a_debiti_banche_lungo: "180000",
    };
    // breve: 100.000 + (300.000 - 220.000) = 180.000
    // lungo: 180.000 + (200.000 - 180.000) =  20.000 → 200.000
    expect(baseBankDebt(misto)).toBe(380_000);
  });

  // `max(0, gap)` su ENTRAMBE le scadenze.
  it("uno scarto NEGATIVO non toglie debito alle banche", () => {
    const dettagliEccedenti = {
      sp16_debiti_breve: "100000",
      sp16a_debiti_banche_breve: "80000",
      sp16d_debiti_fornitori_breve: "90000", // dettagli 170.000 > aggregato
      sp17_debiti_lungo: "0",
    };
    // 80.000 + max(0, -70.000) = 80.000, non 10.000
    expect(baseBankDebt(dettagliEccedenti)).toBe(80_000);
  });

  it("le due scadenze si guardano separatamente", () => {
    const unaSbilanciata = {
      sp16_debiti_breve: "100000",
      sp16a_debiti_banche_breve: "80000",
      sp16d_debiti_fornitori_breve: "90000", // gap negativo, azzerato
      sp17_debiti_lungo: "200000",
      sp17a_debiti_banche_lungo: "50000", // gap +150.000, tenuto
    };
    expect(baseBankDebt(unaSbilanciata)).toBe(80_000 + 50_000 + 150_000);
  });

  it("i campi mancanti valgono zero, non NaN", () => {
    expect(baseBankDebt({})).toBe(0);
    expect(baseBankDebt(null)).toBe(0);
    expect(baseBankDebt(undefined)).toBe(0);
    expect(baseBankDebt({ sp16_debiti_breve: "non un numero" })).toBe(0);
  });

  it("accetta sia numeri sia le stringhe che arrivano dall'API", () => {
    expect(baseBankDebt({ sp16_debiti_breve: 300000, sp17_debiti_lungo: 0 })).toBe(300_000);
    expect(baseBankDebt({ sp16_debiti_breve: "300000", sp17_debiti_lungo: "0" })).toBe(300_000);
  });
});

describe("sommaResiduiIniziali", () => {
  it("somma i residui dichiarati", () => {
    expect(sommaResiduiIniziali([{ opening_residual: 100 }, { opening_residual: 200 }])).toBe(300);
  });

  it("tratta assente, null e non numerico come zero", () => {
    expect(sommaResiduiIniziali(undefined)).toBe(0);
    expect(sommaResiduiIniziali([{}, { opening_residual: null }, { opening_residual: 50 }])).toBe(50);
  });
});

/**
 * Il vincolo del motore: `use_detailed_existing_schedule = totale > 0`, e poi
 * `abs(base_bank_total - totale) > Decimal('0.01')` → errore.
 */
describe("statoResidui", () => {
  it("nessun residuo: il vincolo non è attivo, niente avviso", () => {
    const s = statoResidui(ORDINARIO, []);
    expect(s.attivo).toBe(false);
    expect(s.bloccante).toBe(false);
    expect(s.debitoBancario).toBe(280_000);
  });

  // A metà compilazione lo scarto è normale: l'avviso c'è, l'input non si blocca.
  it("residui parziali: attivo e bloccante, con la differenza esatta", () => {
    const s = statoResidui(ORDINARIO, [{ opening_residual: 100_000 }]);
    expect(s.attivo).toBe(true);
    expect(s.bloccante).toBe(true);
    expect(s.differenza).toBe(180_000);
  });

  it("pareggio al centesimo: non più bloccante", () => {
    const s = statoResidui(ORDINARIO, [
      { opening_residual: 100_000 },
      { opening_residual: 180_000 },
    ]);
    expect(s.differenza).toBe(0);
    expect(s.bloccante).toBe(false);
  });

  it("la tolleranza è di un centesimo, come quella del motore", () => {
    expect(statoResidui(ORDINARIO, [{ opening_residual: 279_999.995 }]).bloccante).toBe(false);
    expect(statoResidui(ORDINARIO, [{ opening_residual: 279_999.9 }]).bloccante).toBe(true);
  });

  it("residui in eccesso sono bloccanti quanto quelli in difetto", () => {
    const s = statoResidui(ORDINARIO, [{ opening_residual: 400_000 }]);
    expect(s.differenza).toBe(-120_000);
    expect(s.bloccante).toBe(true);
  });

  it("su un abbreviato il riferimento è l'aggregato, non i dettagli a zero", () => {
    const abbreviato = { sp16_debiti_breve: "300000", sp17_debiti_lungo: "200000" };
    expect(statoResidui(abbreviato, [{ opening_residual: 500_000 }]).bloccante).toBe(false);
  });
});
