import { describe, expect, it } from "vitest";
import { planTaxRate } from "./budget-tax-rate";
import { altreVociCalculated } from "./budget-altre-voci-step";
import type { AssumptionsMap } from "@/lib/budget-horizon";
import type { ForecastPreviewResponse, IncomeStatement } from "@/types/api";

/** `tax_rate` e' NOT NULL: un'ipotesi non forzata porta comunque il 27,9. */
const nonForzata: AssumptionsMap = { 2025: { tax_rate: 27.9 }, 2026: { tax_rate: 27.9 } };
const forzata: AssumptionsMap = { 2025: { tax_rate: 32 }, 2026: { tax_rate: 32 } };
const YEARS = [2025, 2026];

/** Imposte forzate a importo dal CE previsionale, su tutti gli anni. */
const overrideTutti: AssumptionsMap = {
  2025: { tax_rate: 27.9, ce20_override: 10000 },
  2026: { tax_rate: 27.9, ce20_override: 12000 },
};
/** ...e su un anno solo. */
const overrideParziale: AssumptionsMap = {
  2025: { tax_rate: 27.9, ce20_override: 10000 },
  2026: { tax_rate: 27.9 },
};

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
});

describe("planTaxRate · ce20_override", () => {
  // forecast_engine.py:723-726 — con `ce20_override` quell'importo E' l'imposta
  // totale dell'anno: il motore NON applica nessuna aliquota. Dichiararne una
  // sarebbe affermare qualcosa che il motore non fa.
  it("override su tutti gli anni: nessuna aliquota, e l'etichetta lo dice", () => {
    const p = planTaxRate(25, overrideTutti, YEARS);
    expect(p.source).toBe("sostituita");
    expect(p.ratePct).toBeNull();
    expect(p.value).toBe("—");
    // Il difetto: prima qui usciva «27,9% · predefinita, non calcolata».
    expect(p.label).not.toContain("%");
    expect(p.nota).toContain("non applica nessuna aliquota");
    expect(p.overriddenYears).toEqual(YEARS);
  });

  it("l'override batte anche l'aliquota effettiva derivabile", () => {
    expect(planTaxRate(25, overrideTutti, YEARS).source).toBe("sostituita");
    expect(planTaxRate(null, { ...overrideTutti, 2025: { tax_rate: 32, ce20_override: 1 } }, YEARS).source)
      .toBe("sostituita");
  });

  it("override su alcuni anni: l'aliquota resta per gli altri, e si dice quanti", () => {
    const p = planTaxRate(25, overrideParziale, YEARS);
    expect(p.source).toBe("sostituita");
    expect(p.ratePct).toBe(25);
    expect(p.value).toBe("25,0%");
    expect(p.overriddenYears).toEqual([2025]);
    expect(p.totalYears).toBe(2);
    // Singolare: «1 anni su 2» e' un errore che l'utente legge a schermo.
    expect(p.label).toContain("1 anno su 2");
    expect(p.label).not.toContain("1 anni");
    expect(p.nota).toContain("1 anno su 2");
    expect(p.nota).toContain("2025");
    expect(p.nota).toContain("effettiva dell'anno base");
  });

  it("due anni su tre restano al plurale", () => {
    const p = planTaxRate(25, { 2025: { ce20_override: 100 }, 2026: { ce20_override: 100 } }, [2025, 2026, 2027]);
    expect(p.label).toContain("2 anni su 3");
    expect(p.nota).toContain("2 anni su 3");
  });

  it("un override a zero e' un override vero (imposte azzerate), non un'assenza", () => {
    const p = planTaxRate(25, { 2025: { ce20_override: 0 }, 2026: { ce20_override: 0 } }, YEARS);
    expect(p.source).toBe("sostituita");
    expect(p.ratePct).toBeNull();
  });

  it("senza override il campo non entra in gioco", () => {
    expect(planTaxRate(25, nonForzata, YEARS).overriddenYears).toEqual([]);
    expect(planTaxRate(25, { 2025: { ce20_override: null }, 2026: {} }, YEARS).source).toBe("effettiva");
  });
});

describe("planTaxRate · addsInformation", () => {
  it("nel caso comune la riga «usata dal piano» non aggiunge nulla e si nasconde", () => {
    // Effettiva derivabile, nulla di forzato, nessun override: la riga
    // ripeterebbe numero e badge dell'aliquota effettiva.
    expect(planTaxRate(25, nonForzata, YEARS).addsInformation).toBe(false);
  });
  it("in ogni altro caso la riga dice qualcosa che le altre non dicono", () => {
    expect(planTaxRate(25, forzata, YEARS).addsInformation).toBe(true); // forzata ignorata
    expect(planTaxRate(null, forzata, YEARS).addsInformation).toBe(true);
    expect(planTaxRate(null, nonForzata, YEARS).addsInformation).toBe(true);
    expect(planTaxRate(25, overrideTutti, YEARS).addsInformation).toBe(true);
  });
});

describe("passo 4 e passo 7 non possono discordare", () => {
  const income = (): IncomeStatement =>
    ({ ce12_oneri_diversi: "50", ce09_ammortamenti: "80", ce15_oneri_finanziari: "20" } as unknown as IncomeStatement);
  const response = (): ForecastPreviewResponse =>
    ({ scenario_id: 1, base_year: 2024, forecast_years: [], error: null });

  // Falsificabile: cade se il passo 4 torna a formattare per conto proprio,
  // o se rende `value` invece di `label` — cioe' se ricompare un'aliquota
  // senza provenienza li' dove il passo 7 ne mostra una.
  it.each([
    ["effettiva", 25 as number | null, nonForzata],
    ["forzata", null, forzata],
    ["predefinita", null, nonForzata],
    ["sostituita", 25, overrideTutti],
  ])("il passo 4 rende la label di planTaxRate — caso %s", (_caso, effettiva, assumptions) => {
    const plan = planTaxRate(effettiva, assumptions, YEARS);
    const c = altreVociCalculated(2024, income(), plan, assumptions, YEARS, response());
    expect(c.imposte.value).toBe(plan.label);
  });
});
