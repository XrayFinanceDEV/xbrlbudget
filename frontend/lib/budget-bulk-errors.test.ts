import { describe, expect, it } from "vitest";
import { righeErroriIpotesi } from "./budget-bulk-errors";

const errore422 = (detail: unknown) => ({ response: { status: 422, data: { detail } } });

describe("righeErroriIpotesi", () => {
  it("un 422 del bulk diventa una riga per campo, con l'anno quando c'e'", () => {
    expect(righeErroriIpotesi(errore422({
      message: "Ipotesi non valide: nulla è stato salvato",
      errori: [
        { forecast_year: 2027, campo: "overdraft_limit", messaggio: "deve essere maggiore o uguale a 0 (ricevuto: -100)" },
        { forecast_year: null, campo: "forecast_year", messaggio: "forecast_year non valido: 'abc'" },
      ],
    }))).toEqual([
      "2027 · overdraft_limit: deve essere maggiore o uguale a 0 (ricevuto: -100)",
      "forecast_year: forecast_year non valido: 'abc'",
    ]);
  });

  it("un 422 di FastAPI senza l'elenco italiano non e' nostro: null", () => {
    expect(righeErroriIpotesi(errore422([{ loc: ["body"], msg: "Field required", type: "missing" }]))).toBeNull();
  });

  it("un altro status, un errore senza risposta o nessun errore: null", () => {
    expect(righeErroriIpotesi({ response: { status: 400, data: { detail: "x" } } })).toBeNull();
    expect(righeErroriIpotesi(new Error("rete"))).toBeNull();
    expect(righeErroriIpotesi(undefined)).toBeNull();
  });

  it("voci malformate si scartano; se non resta nulla, null", () => {
    expect(righeErroriIpotesi(errore422({ errori: [{ campo: 3 }] }))).toBeNull();
  });
});
