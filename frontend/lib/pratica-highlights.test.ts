import { describe, expect, it } from "vitest";
import {
  HIGHLIGHT_RATIO_DEFS,
  buildConfrontoHighlights,
  type HighlightFlusso,
  type HighlightRapporto,
} from "./pratica-highlights";
import type { IntraYearComparisonItem } from "@/types/api";

function voce(
  code: string,
  partial: number,
  reference: number,
  label = code,
): IntraYearComparisonItem {
  return {
    code,
    label,
    partial_value: partial,
    reference_value: reference,
    prior_value: 0,
    pct_of_reference: reference !== 0 ? (partial / reference) * 100 : 0,
    annualized_value: partial * 2, // 6M → 12M, coerente coi casi qui sotto
  };
}

/**
 * Nove mesi. Ricavi al 75% dello storico (esattamente in linea con la
 * frazione d'anno), margine EBITDA in CALO: 10% contro il 12,5% storico.
 */
const NOVE_MESI: IntraYearComparisonItem[] = [
  voce("ce01_ricavi_vendite", 900_000, 1_200_000, "Ricavi delle vendite"),
  voce("ce05_materie_prime", 270_000, 400_000, "Materie prime"),
  voce("ce06_servizi", 180_000, 300_000, "Servizi"),
  voce("ce08_costi_personale", 360_000, 450_000, "Costi del personale"),
  voce("_ebitda", 90_000, 150_000, "EBITDA (MOL)"),
];

const NOVE = { period_months: 9, has_reference: true };

const flussi = (h: ReturnType<typeof buildConfrontoHighlights>) =>
  h.filter((x): x is HighlightFlusso => x.kind === "flusso");
const rapporti = (h: ReturnType<typeof buildConfrontoHighlights>) =>
  h.filter((x): x is HighlightRapporto => x.kind === "rapporto");

describe("buildConfrontoHighlights", () => {
  it("produce otto card: cinque di flusso e tre di rapporto", () => {
    const h = buildConfrontoHighlights(NOVE, NOVE_MESI);
    expect(h).toHaveLength(8);
    expect(flussi(h)).toHaveLength(5);
    expect(rapporti(h)).toHaveLength(3);
  });

  it("l'EBITDA in euro è una card di FLUSSO, come le quattro storiche", () => {
    const h = buildConfrontoHighlights(NOVE, NOVE_MESI);
    const ebitda = flussi(h).find((f) => f.code === "_ebitda");
    expect(ebitda).toBeDefined();
    expect(ebitda!.value).toBe(90_000);
    // 90.000 / 150.000 = 60%, sotto il 75% atteso a nove mesi
    expect(ebitda!.pctOfReference).toBeCloseTo(60, 10);
    expect(ebitda!.expectedPct).toBeCloseTo(75, 10);
    expect(ebitda!.ahead).toBe(false);
  });

  // Il cuore della cosa. Un margine non matura pro-quota: confrontarlo con la
  // frazione d'anno direbbe il falso.
  describe("le card di rapporto non si confrontano con la frazione d'anno", () => {
    it("il margine EBITDA è margine contro margine, non contro il 75%", () => {
      const h = buildConfrontoHighlights(NOVE, NOVE_MESI);
      const m = rapporti(h).find((r) => r.key === "ebitda_margin")!;
      // 90.000 / 900.000 = 10%   contro   150.000 / 1.200.000 = 12,5%
      expect(m.value).toBeCloseTo(10, 10);
      expect(m.reference).toBeCloseTo(12.5, 10);
      expect(m.deltaPp).toBeCloseTo(-2.5, 10);
      // e NON il 75% della frazione d'anno, né un 60% annualizzato
      expect(m.value).not.toBeCloseTo(75, 1);
      expect(m.value).not.toBeCloseTo(60, 1);
    });

    it("un margine invariato non risulta né migliorato né peggiorato dal periodo", () => {
      // stesso margine (12,5%) sul parziale e sullo storico
      const items = [
        voce("ce01_ricavi_vendite", 900_000, 1_200_000),
        voce("_ebitda", 112_500, 150_000),
      ];
      const m = rapporti(buildConfrontoHighlights(NOVE, items))
        .find((r) => r.key === "ebitda_margin")!;
      expect(m.value).toBeCloseTo(12.5, 10);
      expect(m.reference).toBeCloseTo(12.5, 10);
      expect(m.deltaPp).toBeCloseTo(0, 10);
      expect(m.improved).toBe(false); // 0 non è un miglioramento
    });

    it("il rapporto non dipende dai mesi: 3M e 9M danno lo stesso valore", () => {
      const a = rapporti(buildConfrontoHighlights({ period_months: 3, has_reference: true }, NOVE_MESI));
      const b = rapporti(buildConfrontoHighlights(NOVE, NOVE_MESI));
      expect(a.map((r) => r.value)).toEqual(b.map((r) => r.value));
    });
  });

  describe("il segno è invertito sulle card di costo", () => {
    it("un'incidenza dei costi che SCENDE è un miglioramento", () => {
      const h = buildConfrontoHighlights(NOVE, NOVE_MESI);
      const materie = rapporti(h).find((r) => r.key === "materie_su_ricavi")!;
      // 270.000/900.000 = 30%   contro   400.000/1.200.000 = 33,3%
      expect(materie.value).toBeCloseTo(30, 10);
      expect(materie.reference).toBeCloseTo(33.333333, 4);
      expect(materie.deltaPp).toBeLessThan(0);
      expect(materie.improved).toBe(true);
    });

    it("un'incidenza dei costi che SALE è un peggioramento", () => {
      const items = [
        voce("ce01_ricavi_vendite", 900_000, 1_200_000),
        voce("ce06_servizi", 270_000, 300_000), // 30% contro 25%
      ];
      const servizi = rapporti(buildConfrontoHighlights(NOVE, items))
        .find((r) => r.key === "servizi_su_ricavi")!;
      expect(servizi.deltaPp).toBeGreaterThan(0);
      expect(servizi.improved).toBe(false);
    });

    it("sul margine il segno NON è invertito: salire è migliorare", () => {
      const items = [
        voce("ce01_ricavi_vendite", 900_000, 1_200_000),
        voce("_ebitda", 135_000, 150_000), // 15% contro 12,5%
      ];
      const m = rapporti(buildConfrontoHighlights(NOVE, items))
        .find((r) => r.key === "ebitda_margin")!;
      expect(m.deltaPp).toBeGreaterThan(0);
      expect(m.improved).toBe(true);
    });

    it("le due card di costo sono dichiarate lowerIsBetter, il margine no", () => {
      const byKey = new Map(HIGHLIGHT_RATIO_DEFS.map((d) => [d.key, d]));
      expect(byKey.get("materie_su_ricavi")!.lowerIsBetter).toBe(true);
      expect(byKey.get("servizi_su_ricavi")!.lowerIsBetter).toBe(true);
      expect(byKey.get("ebitda_margin")!.lowerIsBetter).toBe(false);
    });
  });

  describe("senza anno di riferimento", () => {
    const SENZA = { period_months: 9, has_reference: false };

    it("le otto card ci sono comunque", () => {
      expect(buildConfrontoHighlights(SENZA, NOVE_MESI)).toHaveLength(8);
    });

    it("le card di rapporto mostrano il valore ma nessuna tendenza", () => {
      const h = buildConfrontoHighlights(SENZA, NOVE_MESI);
      for (const r of rapporti(h)) {
        expect(r.value).not.toBeNull();
        expect(r.reference).toBeNull();
        expect(r.deltaPp).toBeNull();
        expect(r.improved).toBeNull();
      }
    });

    it("anche le card di flusso perdono la freccia, come già facevano", () => {
      for (const f of flussi(buildConfrontoHighlights(SENZA, NOVE_MESI))) {
        expect(f.ahead).toBeNull();
      }
    });
  });

  describe("denominatori e voci mancanti", () => {
    it("ricavi a zero: il rapporto è «non lo so», non uno zero", () => {
      const items = [
        voce("ce01_ricavi_vendite", 0, 0),
        voce("_ebitda", 90_000, 150_000),
      ];
      const m = rapporti(buildConfrontoHighlights(NOVE, items))
        .find((r) => r.key === "ebitda_margin")!;
      expect(m.value).toBeNull();
      expect(m.value).not.toBe(0);
      expect(m.improved).toBeNull();
    });

    it("una voce di flusso assente non produce una card vuota", () => {
      const items = [voce("ce01_ricavi_vendite", 900_000, 1_200_000)];
      const h = buildConfrontoHighlights(NOVE, items);
      expect(flussi(h)).toHaveLength(1);
      // i rapporti restano tre, ma quelli senza numeratore dichiarano null
      expect(rapporti(h)).toHaveLength(3);
      expect(rapporti(h).find((r) => r.key === "ebitda_margin")!.value).toBeNull();
    });

    it("senza la riga sintetica _ebitda non si inventa un EBITDA", () => {
      const items = [
        voce("ce01_ricavi_vendite", 900_000, 1_200_000),
        voce("ce05_materie_prime", 270_000, 400_000),
      ];
      const h = buildConfrontoHighlights(NOVE, items);
      expect(flussi(h).some((f) => f.code === "_ebitda")).toBe(false);
      expect(rapporti(h).find((r) => r.key === "ebitda_margin")!.value).toBeNull();
    });
  });

  it("le prime quattro card restano quelle di prima, nello stesso ordine", () => {
    const h = buildConfrontoHighlights(NOVE, NOVE_MESI);
    expect(flussi(h).slice(0, 4).map((f) => f.code)).toEqual([
      "ce01_ricavi_vendite",
      "ce08_costi_personale",
      "ce05_materie_prime",
      "ce06_servizi",
    ]);
  });
});
