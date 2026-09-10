import { describe, expect, it } from "vitest";
import { pendingEditsAfterSave } from "@/lib/forecast-balance-save";

describe("pendingEditsAfterSave (rilievo 6, giro di correzione 1)", () => {
  it("un salvataggio riuscito svuota le modifiche in sospeso: la cella rilegge il valore dal server", () => {
    const pending = { "2027:sp16a_debiti_banche_breve": 1000000 };
    expect(pendingEditsAfterSave(pending, "success")).toEqual({});
  });

  it("un salvataggio RIFIUTATO svuota anch'esso le modifiche in sospeso: il valore rifiutato non resta a schermo come se fosse applicato", () => {
    // CLAUDE.md § Frontend: «un salvataggio che il server ha rifiutato non
    // si applica mai localmente». Qui il difetto era l'opposto — un rifiuto
    // che NON disapplicava un valore gia' mostrato in sospeso, lasciando la
    // cella indistinguibile da un salvataggio riuscito.
    const pending = { "2027:sp16a_debiti_banche_breve": 1000000 };
    expect(pendingEditsAfterSave(pending, "error")).toEqual({});
  });

  it("svuota anche un piano di modifiche su piu' anni e piu' campi, non solo la prima chiave", () => {
    const pending = {
      "2026:sp16a_debiti_banche_breve": 500000,
      "2027:sp16a_debiti_banche_breve": 1000000,
      "2027:sp17a_debiti_banche_lungo": 200000,
    };
    expect(pendingEditsAfterSave(pending, "error")).toEqual({});
    expect(pendingEditsAfterSave(pending, "success")).toEqual({});
  });

  it("un piano gia' vuoto resta vuoto in entrambi i casi", () => {
    expect(pendingEditsAfterSave({}, "success")).toEqual({});
    expect(pendingEditsAfterSave({}, "error")).toEqual({});
  });
});
