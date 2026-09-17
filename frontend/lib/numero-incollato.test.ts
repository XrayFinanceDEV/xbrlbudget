import { describe, expect, it } from "vitest";
import { numeroIncollato } from "./numero-incollato";

describe("numeroIncollato", () => {
  it("legge un importo italiano copiato dallo schermo (il caso segnalato, 2026-09-17)", () => {
    // Il campo numerico del browser prendeva il punto per un decimale: 45,6.
    expect(numeroIncollato("45.600,74")).toBe("45600.74");
    expect(numeroIncollato("960.937,42 €")).toBe("960937.42");
    expect(numeroIncollato("1.247.893")).toBe("1247893");
    expect(numeroIncollato("45.600")).toBe("45600");
    // Senza virgola, un punto seguito da tre cifre è un separatore delle migliaia: «3.500» è
    // tremilacinquecento, non tre e mezzo (decisione del proprietario, 2026-09-17).
    expect(numeroIncollato("3.500")).toBe("3500");
    expect(numeroIncollato("0,42")).toBe("0.42");
    expect(numeroIncollato("-5.000,00")).toBe("-5000");
    expect(numeroIncollato("1 247 893")).toBe("1247893");
    expect(numeroIncollato(" 960.937,42 €")).toBe("960937.42");
  });

  it("lascia al browser un numero già scritto con il punto decimale", () => {
    // Un valore copiato da un foglio di calcolo o da un JSON: il punto È il decimale.
    expect(numeroIncollato("3.5")).toBeNull();
    expect(numeroIncollato("45600.74")).toBeNull();
    expect(numeroIncollato("6.000000")).toBeNull();
    expect(numeroIncollato("0.125")).toBeNull();
    expect(numeroIncollato("45600")).toBeNull();
  });

  it("non inventa un numero da un testo che numero non è", () => {
    expect(numeroIncollato("")).toBeNull();
    expect(numeroIncollato("Finanziamento A")).toBeNull();
    expect(numeroIncollato("1,2,3")).toBeNull();
    expect(numeroIncollato("12.34,56")).toBeNull();
  });
});
