import { describe, it, expect } from "vitest";
import { formatCurrency, formatNumberOrNA, formatPercentageOrNA, parseItalianAmount } from "./formatters";

// Un solo parser per CE e SP Previsionale: se questi casi divergessero fra le
// due pagine, si scriverebbe un importo diverso da quello digitato senza che
// nulla dia errore.
describe("formatCurrency", () => {
  it("uno zero negativo, o un negativo sotto il mezzo euro, si scrive senza segno (collaudo R5)", () => {
    expect(formatCurrency(-0)).toBe(formatCurrency(0));
    expect(formatCurrency(-0.3)).toBe(formatCurrency(0));
    expect(formatCurrency(-1)).not.toBe(formatCurrency(0));
  });
});

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

// Fix round 1 (review lotto 2, 2026-09-26): ROD e DIO arrivano `null` dal backend quando sono
// indefiniti (nessun debito finanziario, consumo di materie non positivo) — "n.d.", mai uno "0,00%"
// o uno "0" che dichiarerebbe un indice misurato quando non lo è.
describe("formatPercentageOrNA", () => {
  it("scrive «n.d.» per null, mai uno zero", () => {
    expect(formatPercentageOrNA(null)).toBe("n.d.");
    expect(formatPercentageOrNA(null)).not.toBe(formatPercentageOrNA(0));
  });

  it("formatta un valore reale come formatPercentage", () => {
    expect(formatPercentageOrNA(0.045)).toBe("4,50%");
  });
});

describe("formatNumberOrNA", () => {
  it("scrive «n.d.» per null, mai uno zero", () => {
    expect(formatNumberOrNA(null)).toBe("n.d.");
    expect(formatNumberOrNA(null)).not.toBe(formatNumberOrNA(0));
  });

  it("formatta un valore reale come formatNumber", () => {
    expect(formatNumberOrNA(1.5, 2)).toBe("1,50");
  });
});
