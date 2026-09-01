import { describe, it, expect } from "vitest";
import {
  computeProjectedBS,
  ASSET_CODES_WITHOUT_CASH,
  type ProjectedBsInputs,
} from "@/lib/pratica-projected-bs";
import { ATTIVO_CODES, PASSIVO_CODES } from "@/lib/pratica-codes";

/**
 * Lo stato patrimoniale proiettato dell'anteprima («Calcola proiezione SP»).
 *
 * L'invariante è uno solo e non ammette tolleranza: Totale Attivo − Totale
 * Passivo = 0 ESATTO. Il plug di cassa è il residuo delle righe arrotondate,
 * non un numero in piena precisione arrotondato per conto suo insieme alle
 * altre diciassette.
 */

function inputs(patch: Partial<ProjectedBsInputs> = {}): ProjectedBsInputs {
  return {
    partial: {},
    reference: {},
    hasReference: false,
    refRevenue: 0,
    refMaterials: 0,
    refServices: 0,
    projRevenue: 0,
    projMaterials: 0,
    projServices: 0,
    projNetProfit: 0,
    ...patch,
  };
}

describe("computeProjectedBS — quadratura", () => {
  it("quadra esattamente col plug positivo", () => {
    const out = computeProjectedBS(
      inputs({
        partial: {
          sp02_immob_immateriali: 50_000,
          sp03_immob_materiali: 400_000,
          sp05_rimanenze: 120_000,
          sp06_crediti_breve: 300_000,
          sp11_capitale: 100_000,
          sp12_riserve: 250_000,
          sp16_debiti_breve: 400_000,
          sp17_debiti_lungo: 200_000,
        },
        projNetProfit: 80_000,
      }),
    );

    expect(out.totalAssets - out.totalLiabilities).toBe(0);
    expect(out.values.sp09_disponibilita_liquide).toBeGreaterThan(0);
    expect(out.absorbedIntoShortTermDebt).toBe(0);
  });

  it("quadra esattamente anche quando il plug negativo finisce nei debiti a breve", () => {
    const out = computeProjectedBS(
      inputs({
        partial: {
          sp03_immob_materiali: 1_000_000,
          sp06_crediti_breve: 500_000,
          sp11_capitale: 10_000,
          sp16_debiti_breve: 100_000,
        },
        projNetProfit: -20_000,
      }),
    );

    expect(out.values.sp09_disponibilita_liquide).toBe(0);
    expect(out.absorbedIntoShortTermDebt).toBeGreaterThan(0);
    expect(out.values.sp16_debiti_breve).toBe(100_000 + out.absorbedIntoShortTermDebt);
    expect(out.totalAssets - out.totalLiabilities).toBe(0);
  });

  it("REGRESSIONE: i centesimi che facevano derivare i due totali di 2 €", () => {
    // Attivo con la frazione che arrotonda PER ECCESSO, passivo per difetto:
    // col plug calcolato in piena precisione e arrotondato dopo, l'anteprima
    // mostrava Attivo 602 contro Passivo 600.
    const out = computeProjectedBS(
      inputs({
        partial: {
          sp02_immob_immateriali: 100.6,
          sp03_immob_materiali: 100.6,
          sp06_crediti_breve: 100.6,
          sp11_capitale: 100.4,
          sp12_riserve: 100.4,
          sp16_debiti_breve: 100.4,
        },
        projNetProfit: 300,
      }),
    );

    expect(out.totalAssets).toBe(600);
    expect(out.totalLiabilities).toBe(600);
    expect(out.totalAssets - out.totalLiabilities).toBe(0);
    // Il residuo assorbe lo scarto: 600 (passivo arrotondato) − 303 (attivo
    // senza cassa arrotondato). In piena precisione sarebbe stato 299,4 → 299.
    expect(out.values.sp09_disponibilita_liquide).toBe(297);
  });

  it("REGRESSIONE: gli stessi centesimi nel ramo a plug negativo", () => {
    const out = computeProjectedBS(
      inputs({
        partial: {
          sp02_immob_immateriali: 1_000.6,
          sp03_immob_materiali: 1_000.6,
          sp06_crediti_breve: 1_000.6,
          sp11_capitale: 100.4,
          sp12_riserve: 100.4,
          sp16_debiti_breve: 100.4,
        },
        projNetProfit: 0,
      }),
    );

    expect(out.totalAssets).toBe(3_003);
    expect(out.totalLiabilities).toBe(3_003);
    expect(out.values.sp16_debiti_breve).toBe(2_803);
    expect(out.values.sp09_disponibilita_liquide).toBe(0);
  });

  it("quadra su cento estrazioni di centesimi arbitrari", () => {
    // Generatore deterministico: il test deve fallire sempre o mai.
    let seed = 20260901;
    const next = () => {
      seed = (seed * 1103515245 + 12345) % 2147483648;
      return seed / 2147483648;
    };
    const codes = [...ASSET_CODES_WITHOUT_CASH, ...PASSIVO_CODES].filter(
      (c) => c !== "sp13_utile_perdita",
    );

    for (let draw = 0; draw < 100; draw++) {
      const partial: Record<string, number> = {};
      for (const code of codes) partial[code] = next() * 200_000;
      const out = computeProjectedBS(
        inputs({ partial, projNetProfit: (next() - 0.5) * 400_000 }),
      );
      expect(out.totalAssets - out.totalLiabilities).toBe(0);
    }
  });

  it("restituisce solo interi, per tutti e diciotto i codici", () => {
    const out = computeProjectedBS(
      inputs({
        partial: {
          sp03_immob_materiali: 1_234.56,
          sp06_crediti_breve: 7_654.32,
          sp11_capitale: 10_000.49,
          sp16_debiti_breve: 999.51,
        },
        projNetProfit: 1_111.11,
      }),
    );

    for (const code of [...ATTIVO_CODES, ...PASSIVO_CODES]) {
      expect(Number.isInteger(out.values[code])).toBe(true);
    }
    expect(Object.keys(out.values).sort()).toEqual(
      [...ATTIVO_CODES, ...PASSIVO_CODES].sort(),
    );
  });
});

describe("computeProjectedBS — circolante", () => {
  it("scala rimanenze, crediti e debiti a breve coi rapporti dell'anno di riferimento", () => {
    const out = computeProjectedBS(
      inputs({
        hasReference: true,
        partial: {
          sp05_rimanenze: 60_000,
          sp06_crediti_breve: 150_000,
          sp16_debiti_breve: 90_000,
          // Patrimonio abbondante: il plug resta positivo, così l'asserzione su
          // `sp16` misura la rotazione e non l'assorbimento del fabbisogno.
          sp11_capitale: 400_000,
        },
        reference: {
          sp05_rimanenze: 100_000,
          sp06_crediti_breve: 200_000,
          sp16_debiti_breve: 120_000,
        },
        refRevenue: 1_000_000,
        refMaterials: 400_000,
        refServices: 200_000,
        projRevenue: 1_200_000,
        projMaterials: 480_000,
        projServices: 240_000,
      }),
    );

    // 480.000 * (100.000/400.000)
    expect(out.values.sp05_rimanenze).toBe(120_000);
    // 1.200.000 * (200.000/1.000.000)
    expect(out.values.sp06_crediti_breve).toBe(240_000);
    // 720.000 * (120.000/600.000)
    expect(out.values.sp16_debiti_breve).toBe(144_000);
    expect(out.totalAssets - out.totalLiabilities).toBe(0);
  });

  it("riporta la giacenza infrannuale quando il rapporto è degenere (caso AIC SRL)", () => {
    const out = computeProjectedBS(
      inputs({
        hasReference: true,
        partial: {
          sp06_crediti_breve: 1_100_048.69,
          sp11_capitale: 10_000,
        },
        reference: { sp06_crediti_breve: 1_035_249.26 },
        refRevenue: 100.92,
        projRevenue: 16_249,
      }),
    );

    expect(out.values.sp06_crediti_breve).toBe(1_100_049);
    expect(out.totalAssets - out.totalLiabilities).toBe(0);
  });

  it("senza anno di riferimento porta avanti i valori infrannuali", () => {
    const out = computeProjectedBS(
      inputs({
        hasReference: false,
        partial: {
          sp05_rimanenze: 60_000,
          sp06_crediti_breve: 150_000,
          sp16_debiti_breve: 90_000,
          sp11_capitale: 400_000,
        },
        reference: {
          sp05_rimanenze: 100_000,
          sp06_crediti_breve: 200_000,
          sp16_debiti_breve: 120_000,
        },
        refRevenue: 1_000_000,
        projRevenue: 1_200_000,
        projMaterials: 480_000,
        projServices: 240_000,
      }),
    );

    expect(out.values.sp05_rimanenze).toBe(60_000);
    expect(out.values.sp06_crediti_breve).toBe(150_000);
    expect(out.values.sp16_debiti_breve).toBe(90_000);
    expect(out.totalAssets - out.totalLiabilities).toBe(0);
  });
});
