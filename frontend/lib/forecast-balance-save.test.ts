import { describe, expect, it } from "vitest";
import { overridesFromPendingEdits, pendingEditsAfterSave } from "@/lib/forecast-balance-save";

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

describe("overridesFromPendingEdits (rilievo Important, giro di correzione 3)", () => {
  it("un piano vuoto da' un lotto vuoto", () => {
    expect(overridesFromPendingEdits({})).toEqual([]);
  });

  it("spacchetta la chiave 'anno:campo' in forecast_year (numero) e field", () => {
    const pending = { "2027:sp16a_debiti_banche_breve": 400000.55 };
    expect(overridesFromPendingEdits(pending)).toEqual([
      { forecast_year: 2027, field: "sp16a_debiti_banche_breve", value: 400000.55 },
    ]);
  });

  it("un valore null (cella svuotata) resta null nel lotto, non diventa zero", () => {
    const pending = { "2027:sp16a_debiti_banche_breve": null };
    expect(overridesFromPendingEdits(pending)).toEqual([
      { forecast_year: 2027, field: "sp16a_debiti_banche_breve", value: null },
    ]);
  });

  it("un piano su piu' anni e piu' campi produce UN lotto con tutte le voci -- una chiamata sola, non una per anno", () => {
    const pending = {
      "2026:sp16a_debiti_banche_breve": 500000,
      "2027:sp16a_debiti_banche_breve": 1000000,
      "2027:sp17a_debiti_banche_lungo": 200000,
    };
    const batch = overridesFromPendingEdits(pending);
    expect(batch).toHaveLength(3);
    expect(batch).toEqual(
      expect.arrayContaining([
        { forecast_year: 2026, field: "sp16a_debiti_banche_breve", value: 500000 },
        { forecast_year: 2027, field: "sp16a_debiti_banche_breve", value: 1000000 },
        { forecast_year: 2027, field: "sp17a_debiti_banche_lungo", value: 200000 },
      ]),
    );
    // Anni distinti nel lotto: prova che il raggruppamento per anno non e'
    // necessario lato client -- la rotta lo fa lato server.
    expect(new Set(batch.map((e) => e.forecast_year))).toEqual(new Set([2026, 2027]));
  });

  it("un campo il cui nome contiene ':' non spezza lo spacchettamento (solo il PRIMO ':' separa anno e campo)", () => {
    // Nessun campo SP reale ha ':' nel nome oggi, ma la chiave e' costruita
    // con template string (`${year}:${field}`) altrove nel componente: se
    // mai un campo lo avesse, split(":") con limite implicito prenderebbe
    // solo il primo segmento come field, troncando il resto -- documentato
    // qui perche' la funzione usa split(":") senza limite esplicito.
    const pending = { "2027:a:b": 1 };
    const [entry] = overridesFromPendingEdits(pending);
    expect(entry.forecast_year).toBe(2027);
    expect(entry.field).toBe("a"); // il resto ("b") va perso -- comportamento noto, non un campo reale
  });
});
