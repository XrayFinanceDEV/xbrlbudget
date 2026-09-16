// @vitest-environment node
import { describe, it, expect } from "vitest";
import { spiegazioneRiclassifica } from "@/lib/pratica-rettifiche-rules";

describe("la didascalia di una riclassifica dice il verso vero", () => {
  const acconti = "Acconti (rimanenze)";
  const materie = "Rimanenze materie prime";

  it("valore in aumento: la massa ARRIVA dalla contropartita", () => {
    // Il caso che è successo davvero: +287.312,00 sugli acconti e -287.312,00
    // sulle materie. La frase diceva «Acconti → Materie prime», cioè l'opposto,
    // e tutto il magazzino è finito negli acconti a fornitori.
    expect(spiegazioneRiclassifica(acconti, materie, 287312)).toBe(
      `Riclassifica: ${materie} → ${acconti}`,
    );
  });

  it("valore in diminuzione: la massa VA verso la contropartita", () => {
    expect(spiegazioneRiclassifica(acconti, materie, -287312)).toBe(
      `Riclassifica: ${acconti} → ${materie}`,
    );
  });

  it("un delta nullo non inventa un verso all'indietro", () => {
    expect(spiegazioneRiclassifica(acconti, materie, 0)).toBe(
      `Riclassifica: ${materie} → ${acconti}`,
    );
  });
});
