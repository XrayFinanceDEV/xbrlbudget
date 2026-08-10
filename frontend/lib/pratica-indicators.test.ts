import { describe, expect, it } from "vitest";
import {
  computeCrisisRating,
  computeIndicators,
  invertedScore,
  linearScore,
  safeDivide,
  scoreDotColor,
  scoreIndicator,
} from "./pratica-indicators";

/** Azienda sana: utile, poco debito, buona liquidita'. */
const BS_SANA: Record<string, number> = {
  sp02_immob_immateriali: 20_000,
  sp03_immob_materiali: 300_000,
  sp05_rimanenze: 150_000,
  sp06_crediti_breve: 250_000,
  sp09_disponibilita_liquide: 80_000,
  sp11_capitale: 100_000,
  sp12_riserve: 250_000,
  sp13_utile_perdita: 90_000,
  sp16_debiti_breve: 260_000,
  sp16a_debiti_banche_breve: 60_000,
  sp17_debiti_lungo: 100_000,
  sp17a_debiti_banche_lungo: 100_000,
};

const IS_SANA: Record<string, number> = {
  ce01_ricavi_vendite: 1_200_000,
  ce05_materie_prime: 400_000,
  ce06_servizi: 300_000,
  ce08_costi_personale: 250_000,
  ce09_ammortamenti: 50_000,
  ce15_oneri_finanziari: 12_000,
  ce20_imposte: 30_000,
};

describe("linearScore / invertedScore", () => {
  it("clampa agli estremi", () => {
    expect(linearScore(0, 1, 2)).toBe(0);
    expect(linearScore(5, 1, 2)).toBe(1);
  });

  it("interpola linearmente a meta' scala", () => {
    expect(linearScore(1.5, 1, 2)).toBeCloseTo(0.5, 10);
  });

  it("invertedScore e' il complemento a 1", () => {
    expect(invertedScore(1.5, 1, 2)).toBeCloseTo(0.5, 10);
    expect(invertedScore(0, 1, 2)).toBe(1);
  });
});

describe("safeDivide", () => {
  it("divide normalmente", () => {
    expect(safeDivide(10, 4)).toBe(2.5);
  });

  it("denominatore zero: restituisce 0, non Infinity", () => {
    expect(safeDivide(10, 0)).toBe(0);
  });
});

describe("computeIndicators", () => {
  const ind = computeIndicators(BS_SANA, IS_SANA);

  it("produce tutti i campi dell'IndicatorSet", () => {
    for (const k of [
      "dscr", "ebitda_margin", "mt", "ccn", "current_ratio", "ms",
      "copertura_immob", "indipendenza", "pfn", "pfn_ebitda",
      "roi", "roe", "ros", "of_mol", "materials_revenue", "services_revenue",
      "_ebitda_raw", "_quick_ratio", "_equity_over_fixed",
    ]) {
      expect(Number.isFinite(ind[k as keyof typeof ind])).toBe(true);
    }
  });

  it("EBITDA = VP - costi operativi, ammortamenti esclusi", () => {
    // 1.200.000 - (400.000 + 300.000 + 250.000) = 250.000
    expect(ind._ebitda_raw).toBeCloseTo(250_000, 2);
  });

  it("margine EBITDA in percentuale assoluta, non in decimali", () => {
    expect(ind.ebitda_margin).toBeGreaterThan(1);
    expect(ind.ebitda_margin).toBeCloseTo(250_000 / 1_200_000 * 100, 2);
  });

  it("bilancio vuoto: nessun NaN ne' Infinity", () => {
    const empty = computeIndicators({}, {});
    for (const value of Object.values(empty)) {
      expect(Number.isFinite(value)).toBe(true);
    }
  });
});

describe("scoreIndicator", () => {
  const ind = computeIndicators(BS_SANA, IS_SANA);

  it("ogni punteggio sta in [0,1]", () => {
    for (const k of ["dscr", "ebitda_margin", "current_ratio", "indipendenza",
                     "roi", "roe", "ros", "pfn_ebitda", "of_mol"] as const) {
      const s = scoreIndicator(k, ind);
      expect(s).toBeGreaterThanOrEqual(0);
      expect(s).toBeLessThanOrEqual(1);
    }
  });

  it("EBITDA negativo con PFN positiva: pfn_ebitda vale 0", () => {
    const bad = { ...ind, _ebitda_raw: -10_000, pfn: 50_000, pfn_ebitda: -5 };
    expect(scoreIndicator("pfn_ebitda", bad)).toBe(0);
  });

  it("EBITDA negativo senza oneri finanziari: of_mol vale 0,5", () => {
    const bad = { ...ind, _ebitda_raw: -10_000, of_mol: 0 };
    expect(scoreIndicator("of_mol", bad)).toBe(0.5);
  });
});

describe("computeCrisisRating", () => {
  it("nessun indicatore oltre soglia e nessun segnale: A3", () => {
    expect(computeCrisisRating([1, 1, 1, 0.9], 0).code).toBe("A3");
  });

  it("due indicatori oltre soglia e nessun segnale: A2", () => {
    expect(computeCrisisRating([0.1, 0.2, 1, 1], 0).code).toBe("A2");
  });

  it("i segnali extracontabili peggiorano il rating", () => {
    const senza = computeCrisisRating([1, 1, 1, 1], 0).code;
    const con = computeCrisisRating([1, 1, 1, 1], 3).code;
    expect(con).not.toBe(senza);
  });
});

describe("scoreDotColor", () => {
  it("verde sopra 0,67, giallo in mezzo, rosso sotto 0,33", () => {
    expect(scoreDotColor(0.9)).not.toBe(scoreDotColor(0.5));
    expect(scoreDotColor(0.5)).not.toBe(scoreDotColor(0.1));
  });
});
