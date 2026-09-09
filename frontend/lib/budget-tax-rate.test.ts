import { describe, expect, it } from "vitest";
import { planTaxRate } from "./budget-tax-rate";
import type { AssumptionsMap } from "@/lib/budget-horizon";

/** `tax_rate` e' NOT NULL: un'ipotesi non forzata porta comunque il 27,9. */
const nonForzata: AssumptionsMap = { 2025: { tax_rate: 27.9 }, 2026: { tax_rate: 27.9 } };
const forzata: AssumptionsMap = { 2025: { tax_rate: 32 }, 2026: { tax_rate: 32 } };
const YEARS = [2025, 2026];

describe("planTaxRate", () => {
  it("l'effettiva dell'anno base vince: e' la sola che si mostra senza provenienza", () => {
    const p = planTaxRate(25, nonForzata, YEARS);
    expect(p.source).toBe("effettiva");
    expect(p.ratePct).toBe(25);
    expect(p.value).toBe("25,0%");
    expect(p.label).toBe("25,0%");
    expect(p.nota).toBeNull();
  });

  it("l'effettiva vince ANCHE su un'aliquota forzata, e lo dichiara", () => {
    // Il motore (forecast_engine._tax_components) guarda `tax_rate` solo
    // quando l'effettiva non e' derivabile: senza questa nota l'utente
    // scrive 32 e non vede mai il perche' il piano usa 25.
    const p = planTaxRate(25, forzata, YEARS);
    expect(p.source).toBe("effettiva");
    expect(p.ratePct).toBe(25);
    expect(p.ignoredForcedPct).toBe(32);
    expect(p.nota).toContain("32,0%");
    expect(p.nota).toContain("non viene usata");
  });

  it("effettiva non derivabile + valore forzato: si usa il forzato, dichiarato tale", () => {
    const p = planTaxRate(null, forzata, YEARS);
    expect(p.source).toBe("forzata");
    expect(p.ratePct).toBe(32);
    expect(p.value).toBe("32,0%");
    expect(p.label).toBe("32,0% · forzata nelle ipotesi");
    expect(p.ignoredForcedPct).toBeNull();
  });

  it("effettiva non derivabile e nessun forzato: il predefinito NON si presenta come calcolato", () => {
    const p = planTaxRate(null, nonForzata, YEARS);
    expect(p.source).toBe("predefinita");
    expect(p.ratePct).toBe(27.9);
    expect(p.value).toBe("27,9%");
    // Il difetto che questo modulo chiude: prima il passo 4 mostrava "27,9%"
    // nudo, indistinguibile da un'aliquota calcolata.
    expect(p.label).not.toBe("27,9%");
    expect(p.label).toContain("predefinita");
    expect(p.nota).toContain("IRES + IRAP");
  });

  it("un'ipotesi senza `tax_rate` (anno non ancora idratato) e' come non forzata", () => {
    const p = planTaxRate(null, {}, YEARS);
    expect(p.source).toBe("predefinita");
    expect(p.ratePct).toBe(27.9);
  });

  it("la stessa domanda ha una sola risposta: passo 4 e passo 7 leggono gli stessi campi", () => {
    // Non c'e' un secondo percorso: chiunque passi gli stessi input ottiene
    // lo stesso oggetto. E' il contratto che ha sostituito le due letture.
    expect(planTaxRate(null, nonForzata, YEARS)).toEqual(planTaxRate(null, nonForzata, YEARS));
    expect(planTaxRate(25, forzata, YEARS).label).toBe(planTaxRate(25, forzata, YEARS).label);
  });
});
