import { describe, expect, it } from "vitest";
import { euro, num, numOrNull, pct1, pctOf } from "./budget-format";

describe("budget-format", () => {
  it("num: numero, stringa, virgola decimale assente, assenza", () => {
    expect(num(12.5)).toBe(12.5);
    expect(num("12.5")).toBe(12.5);
    expect(num(null)).toBe(0);
    expect(num(undefined)).toBe(0);
    expect(num("")).toBe(0);
    expect(num("non un numero")).toBe(0);
  });

  it("num: la variante scelta ferma NaN e infinito invece di propagarli", () => {
    // La variante scartata (`typeof v === "number" ? v : parseFloat(...) || 0`)
    // restituiva questi valori tali e quali, e un NaN dentro una somma di CE
    // rende «—» un'intera colonna senza spiegare perche'.
    expect(num(NaN), "un NaN gia' numerico deve valere 0, non NaN").toBe(0);
    expect(num(Infinity), "un infinito deve valere 0, non Infinity").toBe(0);
    expect(num(-Infinity)).toBe(0);
  });

  it("numOrNull: assenza e zero vero non si confondono", () => {
    expect(numOrNull(0)).toBe(0);
    expect(numOrNull("0")).toBe(0);
    expect(numOrNull(null)).toBeNull();
    expect(numOrNull(undefined)).toBeNull();
    expect(numOrNull("")).toBeNull();
    expect(numOrNull("boh")).toBeNull();
  });

  it("euro: il trattino e' l'assenza, lo zero e' uno zero", () => {
    expect(euro(null)).toBe("—");
    expect(euro(0)).not.toBe("—");
  });

  it("pct1: un decimale, percentuale assoluta in ingresso", () => {
    expect(pct1(60.5)).toBe("60,5%");
    expect(pct1(40)).toBe("40,0%");
    expect(pct1(null)).toBe("—");
  });

  it("pctOf: denominatore zero, nullo o assente non danno zero ma nulla", () => {
    expect(pctOf(50, 200)).toBe(25);
    expect(pctOf(null, 200)).toBeNull();
    expect(pctOf(50, 0)).toBeNull();
    expect(pctOf(50, null)).toBeNull();
    expect(pctOf(50, undefined)).toBeNull();
  });
});
