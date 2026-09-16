// @vitest-environment node
import { describe, it, expect } from "vitest";
import {
  SOGLIA_CHIUSURA_AUTOMATICA,
  chiusuraAutomatica,
  chiusuraSbilancio,
  quadra,
  scartoQuadratura,
} from "@/lib/pratica-quadratura";

/** Il foglio di AMBIENTA 2026/6M, ridotto alle voci che contano. */
const foglio = (attivo: number, passivo: number): Record<string, number> => ({
  sp09_disponibilita_liquide: attivo,
  sp16_debiti_breve: passivo,
});

describe("scartoQuadratura", () => {
  it("misura attivo meno passivo al centesimo", () => {
    expect(scartoQuadratura(foglio(2460463.09, 2460463.32))).toBe(-0.23);
    expect(scartoQuadratura(foglio(1000, 1000))).toBe(0);
  });

  it("ignora le sotto-voci, che sarebbero contate due volte", () => {
    const values = { ...foglio(1000, 900), sp09a_depositi_bancari: 999 };
    expect(scartoQuadratura(values)).toBe(100);
  });
});

describe("quadra", () => {
  it("i 23 centesimi di AMBIENTA NON quadrano", () => {
    // Regressione: la soglia era 1 €, il riquadro era verde e la proiezione
    // rifiutava comunque di partire per lo stesso scarto.
    expect(quadra(-0.23)).toBe(false);
  });

  it("il centesimo di arrotondamento quadra, come per il motore", () => {
    expect(quadra(0.01)).toBe(true);
    expect(quadra(-0.01)).toBe(true);
    expect(quadra(0.02)).toBe(false);
  });
});

describe("chiusuraSbilancio", () => {
  it("quando il passivo eccede, toglie dagli altri debiti", () => {
    const c = chiusuraSbilancio(-0.23);
    expect(c?.field).toBe("sp16g_altri_debiti_breve");
    expect(c?.delta).toBe(-0.23);
    expect(c?.explanation).toContain("0,23");
  });

  it("quando l'attivo eccede, toglie dalla cassa", () => {
    const c = chiusuraSbilancio(0.23);
    expect(c?.field).toBe("sp09_disponibilita_liquide");
    expect(c?.delta).toBe(-0.23);
  });

  it("su un foglio che quadra non propone nulla", () => {
    expect(chiusuraSbilancio(0)).toBeNull();
    expect(chiusuraSbilancio(0.01)).toBeNull();
  });

  it("chiude anche gli scarti grandi: sopra la soglia cambia CHI decide, non se si può", () => {
    expect(chiusuraSbilancio(1500)?.field).toBe("sp09_disponibilita_liquide");
  });
});

describe("chiusuraAutomatica", () => {
  it("chiude da sola il rumore di arrotondamento", () => {
    expect(chiusuraAutomatica(-0.23)?.delta).toBe(-0.23);
    expect(chiusuraAutomatica(SOGLIA_CHIUSURA_AUTOMATICA)?.delta).toBe(-2);
    expect(chiusuraAutomatica(-SOGLIA_CHIUSURA_AUTOMATICA)?.delta).toBe(-2);
  });

  it("sopra i 2 € non tocca nulla: decide l'utente", () => {
    expect(chiusuraAutomatica(2.01)).toBeNull();
    expect(chiusuraAutomatica(-2.01)).toBeNull();
    expect(chiusuraAutomatica(1500)).toBeNull();
  });

  it("su un foglio che già quadra non scrive una rettifica da zero euro", () => {
    expect(chiusuraAutomatica(0)).toBeNull();
    expect(chiusuraAutomatica(-0.01)).toBeNull();
  });
});
