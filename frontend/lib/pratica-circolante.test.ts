// @vitest-environment node
import { describe, it, expect } from "vitest";
import {
  MODI_CIRCOLANTE,
  MODO_CIRCOLANTE_PREDEFINITO,
  etichettaModoCircolante,
  isModoCircolante,
  spiegazioneModoCircolante,
} from "@/lib/pratica-circolante";

describe("i tre metodi di proiezione del circolante", () => {
  it("sono quelli che il motore accetta", () => {
    expect([...MODI_CIRCOLANTE]).toEqual(["storico", "infrannuale", "equilibrio"]);
  });

  it("partono dallo storico: è il comportamento di sempre", () => {
    // Nel motore un working_capital_mode nullo vale «storico»: la tendina non
    // deve proporre un valore diverso da quello che uno scenario già salvato ha.
    expect(MODO_CIRCOLANTE_PREDEFINITO).toBe("storico");
  });

  it("hanno un'etichetta breve e una spiegazione, tutte diverse fra loro", () => {
    const etichette = MODI_CIRCOLANTE.map(etichettaModoCircolante);
    const spiegazioni = MODI_CIRCOLANTE.map(spiegazioneModoCircolante);
    expect(new Set(etichette).size).toBe(MODI_CIRCOLANTE.length);
    expect(new Set(spiegazioni).size).toBe(MODI_CIRCOLANTE.length);
    for (const testo of [...etichette, ...spiegazioni]) expect(testo.length).toBeGreaterThan(0);
  });

  it("riconosce un valore buono e ne rifiuta uno inventato", () => {
    expect(isModoCircolante("equilibrio")).toBe(true);
    expect(isModoCircolante("Equilibrio")).toBe(false);
    expect(isModoCircolante("")).toBe(false);
  });
});
