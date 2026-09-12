import { describe, expect, it } from "vitest";
import { deltaPct, formatPct } from "./pratica-format";

describe("deltaPct", () => {
  it("torna null quando il riferimento e' un residuo di somma float sotto il centesimo (indagine-3, 2026-09-11)", () => {
    // Stesso ordine di grandezza del residuo riprodotto: 3.725290298461914e-9, con lo
    // sbilancio reale del collaudo (5.509,29) come valore corrente.
    expect(deltaPct(5509.29, 3.725290298461914e-9)).toBeNull();
  });

  it("torna null quando il riferimento e' zero letterale (caso gia' gestito prima del fix)", () => {
    expect(deltaPct(5509.29, 0)).toBeNull();
  });

  it("torna null appena sotto il centesimo (0,004 arrotonda a zero)", () => {
    expect(deltaPct(1000, 0.004)).toBeNull();
  });

  it("calcola normalmente a un centesimo esatto (0,01 non arrotonda a zero)", () => {
    // (1000 - 0.01) / 0.01 * 100 = 9999900
    expect(deltaPct(1000, 0.01)).toBeCloseTo(9999900, 0);
  });

  it("riga sana: ricavi 1.000.000 -> 1.100.000 e' +10,0%, invariata dal fix", () => {
    expect(deltaPct(1100000, 1000000)).toBeCloseTo(10, 6);
  });

  it("riga sana: EBIT storico -50.000 -> proiezione -40.000 e' +20,0%, invariata dal fix", () => {
    expect(deltaPct(-40000, -50000)).toBeCloseTo(20, 6);
  });

  it("riga sana: debiti previdenziali 12.345,67 -> 15.000 e' ~21,5%, invariata dal fix", () => {
    expect(deltaPct(15000, 12345.67)).toBeCloseTo(21.503, 2);
  });
});

describe("formatPct rete secondaria", () => {
  it("un valore normale non cambia", () => {
    expect(formatPct(21.5)).toBe("21.5%");
  });

  it("NaN si rende come indefinito (-), non come testo NaN%", () => {
    expect(formatPct(NaN)).toBe("-");
  });

  it("Infinity si rende come indefinito (-), non come numero enorme", () => {
    expect(formatPct(Infinity)).toBe("-");
    expect(formatPct(-Infinity)).toBe("-");
  });
});
