import { describe, expect, it } from "vitest";
import { rifiutoDaErrore } from "./import-rifiuto";

const errore = (status: number, detail: unknown) => ({ response: { status, data: { detail } } });

describe("rifiutoDaErrore", () => {
  it("legge motivo, categoria e suggerimento di un PDF rifiutato", () => {
    const r = rifiutoDaErrore(errore(422, {
      error: "Documento non importabile come bilancio completo: documento solo Conto Economico",
      error_type: "PDFImportError", categoria: "solo_conto_economico",
      suggerimento: "Carica un documento che abbia anche lo stato patrimoniale.",
    }));
    expect(r).toEqual({
      motivo: "Documento non importabile come bilancio completo: documento solo Conto Economico",
      categoria: "solo_conto_economico",
      suggerimento: "Carica un documento che abbia anche lo stato patrimoniale.",
    });
  });

  it("un rifiuto senza suggerimento mostra il solo motivo", () => {
    const r = rifiutoDaErrore(errore(422, { error: "qualcos'altro", error_type: "PDFImportError" }));
    expect(r).toEqual({ motivo: "qualcos'altro", suggerimento: null, categoria: null });
  });

  it("gli altri errori non sono un rifiuto del file", () => {
    expect(rifiutoDaErrore(errore(503, { error: "OCR non disponibile", error_type: "PDFImportError" }))).toBeNull();
    expect(rifiutoDaErrore(errore(422, [{ msg: "campo mancante" }]))).toBeNull();
    expect(rifiutoDaErrore(errore(422, { error: "x", error_type: "ValueError" }))).toBeNull();
    expect(rifiutoDaErrore(new Error("rete"))).toBeNull();
  });
});
