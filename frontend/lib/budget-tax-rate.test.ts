import { describe, expect, it } from "vitest";
import { planTaxRate, propostaLabel } from "./budget-tax-rate";
import type { AssumptionsMap } from "@/lib/budget-horizon";

// Commercialista, 2026-09-18: il motore applica `tax_rate` cosi' com'e'; il
// wizard lo propone dall'ultimo consuntivo depositato.
const PROPOSTA = { aliquota: 30.93, anno: 2025 };
const NESSUN_BILANCIO = { aliquota: 27.9, anno: null };
const YEARS = [2027, 2028];
const conAliquota = (v: number): AssumptionsMap => ({ 2027: { tax_rate: v }, 2028: { tax_rate: v } });

describe("planTaxRate", () => {
  it("l'aliquota del piano e' quella scritta, anche con uno storico: nessuna effettiva la scavalca", () => {
    const p = planTaxRate(PROPOSTA, conAliquota(24), YEARS);
    expect(p.ratePct).toBe(24);
    expect(p.source).toBe("scelta");
    expect(p.diversaDallaProposta).toBe(true);
    expect(p.nota).toContain("30,9%");
    expect(p.nota).toContain("bilancio 2025");
  });

  it("uguale alla proposta (al decimale mostrato): si dichiara proposta, col suo anno", () => {
    const p = planTaxRate(PROPOSTA, conAliquota(30.9), YEARS);
    expect(p.source).toBe("proposta");
    expect(p.label).toBe("30,9% · proposta · effettiva del bilancio 2025");
    expect(p.diversaDallaProposta).toBe(false);
    expect(p.nota).toBeNull();
  });

  it("senza bilancio depositato la proposta e' il 27,9 predefinito, e lo dice", () => {
    const p = planTaxRate(NESSUN_BILANCIO, conAliquota(27.9), YEARS);
    expect(p.source).toBe("proposta");
    expect(p.sourceLabel).toContain("predefinita 27,9%");
    expect(p.sourceLabel).toContain("IRES + IRAP");
  });

  it("finche' la proposta non arriva non si dichiara nessuna differenza", () => {
    const p = planTaxRate(null, conAliquota(27.9), YEARS);
    expect(p.source).toBe("scelta");
    expect(p.diversaDallaProposta).toBe(false);
    expect(propostaLabel(null)).toBe("in caricamento");
  });

  it("un'ipotesi senza `tax_rate` (anno non ancora idratato) vale il 27,9 di schema", () => {
    expect(planTaxRate(null, {}, YEARS).ratePct).toBe(27.9);
  });
});

describe("planTaxRate · ce20_override", () => {
  // forecast_engine._tax_components — con `ce20_override` quell'importo E'
  // l'imposta totale dell'anno: il motore NON applica nessuna aliquota.
  it("override su tutti gli anni: nessuna aliquota, e l'etichetta lo dice", () => {
    const p = planTaxRate(PROPOSTA, { 2027: { tax_rate: 30.9, ce20_override: 1 }, 2028: { tax_rate: 30.9, ce20_override: 2 } }, YEARS);
    expect(p.source).toBe("sostituita");
    expect(p.ratePct).toBeNull();
    expect(p.value).toBe("—");
    expect(p.label).not.toContain("%");
    expect(p.nota).toContain("non applica nessuna aliquota");
    expect(p.overriddenYears).toEqual(YEARS);
  });

  it("override su alcuni anni: l'aliquota resta per gli altri, al singolare giusto", () => {
    const p = planTaxRate(PROPOSTA, { 2027: { tax_rate: 30.9, ce20_override: 1 }, 2028: { tax_rate: 30.9 } }, YEARS);
    expect(p.ratePct).toBe(30.9);
    expect(p.label).toContain("1 anno su 2");
    expect(p.label).not.toContain("1 anni");
    expect(p.nota).toContain("2027");
  });

  it("un override a zero e' un override vero (imposte azzerate), non un'assenza", () => {
    const p = planTaxRate(PROPOSTA, { 2027: { ce20_override: 0 }, 2028: { ce20_override: 0 } }, YEARS);
    expect(p.source).toBe("sostituita");
    expect(p.ratePct).toBeNull();
  });
});
