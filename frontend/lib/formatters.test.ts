import { describe, it, expect } from "vitest";
import { parseItalianAmount } from "./formatters";

// Un solo parser per CE e SP Previsionale: se questi casi divergessero fra le
// due pagine, si scriverebbe un importo diverso da quello digitato senza che
// nulla dia errore.
describe("parseItalianAmount", () => {
  it("legge i separatori delle migliaia nel formato italiano", () => {
    expect(parseItalianAmount("1.247.893")).toBe(1247893);
    expect(parseItalianAmount("1.247")).toBe(1247);
  });

  it("legge la virgola come separatore decimale", () => {
    expect(parseItalianAmount("1.247.893,45")).toBe(1247893.45);
    expect(parseItalianAmount("0,5")).toBe(0.5);
  });

  it("legge una cifra grezza, senza separatori", () => {
    expect(parseItalianAmount("1247893")).toBe(1247893);
  });

  it("tollera gli spazi, anche dentro il numero", () => {
    expect(parseItalianAmount("  1 247 893  ")).toBe(1247893);
  });

  it("legge i negativi", () => {
    expect(parseItalianAmount("-1.247.893")).toBe(-1247893);
  });

  // Il caso che conta: campo svuotato = RIMUOVI l'override, non «forza a
  // zero». `sp_overrides` clampa i negativi a zero e ignora in silenzio le
  // chiavi sconosciute, quindi confondere i due non darebbe alcun errore —
  // darebbe uno zero.
  it("restituisce null sul campo vuoto, mai zero", () => {
    expect(parseItalianAmount("")).toBeNull();
    expect(parseItalianAmount("   ")).toBeNull();
    expect(parseItalianAmount("")).not.toBe(0);
  });

  it("restituisce undefined su ciò che non è un numero", () => {
    expect(parseItalianAmount("abc")).toBeUndefined();
    expect(parseItalianAmount("-")).toBeUndefined();
    expect(parseItalianAmount(",")).toBeUndefined();
  });

  it("distingue zero scritto da campo vuoto", () => {
    expect(parseItalianAmount("0")).toBe(0);
    expect(parseItalianAmount("")).toBeNull();
  });
});
