import { describe, expect, it } from "vitest";
import { buildIndicatorChartData, type SerieIndicatori } from "@/lib/pratica-indicators";
import type { IndicatorSet } from "@/lib/pratica-indicators";

/**
 * Le righe dei due grafici della sezione Indicatori (incidenza economica ed
 * equilibrio finanziario) si costruiscono qui, una volta sola, perché le
 * consumano DUE viste: la tab Indicatori e la Stampa. Le etichette invece
 * restano di ciascuna vista — in Indicatori la colonna si chiama
 * "Infrann. 9M", in Stampa "Infrann. 9M 2026".
 */

function indicatori(patch: Partial<IndicatorSet> = {}): IndicatorSet {
  // Solo i campi che i due grafici leggono davvero; il resto a zero.
  return {
    dscr: 0,
    ebitda_margin: 0,
    mt: 0,
    ccn: 0,
    current_ratio: 0,
    indipendenza: 0,
    ms: 0,
    copertura_immob: 0,
    pfn: 0,
    pfn_ebitda: 0,
    roi: 0,
    roe: 0,
    ros: 0,
    of_mol: 0,
    materials_revenue: 0,
    services_revenue: 0,
    _ebitda_raw: 0,
    _quick_ratio: 0,
    _equity_over_fixed: 0,
    ...patch,
  } as IndicatorSet;
}

describe("buildIndicatorChartData", () => {
  it("appiattisce ogni serie in una riga con la propria etichetta", () => {
    const serie: SerieIndicatori[] = [
      { periodo: "Storico 2025", indicatori: indicatori({ ebitda_margin: 12.5 }) },
      { periodo: "Infrann. 9M", indicatori: indicatori({ ebitda_margin: 8.25 }) },
    ];

    const righe = buildIndicatorChartData(serie);

    expect(righe).toHaveLength(2);
    expect(righe[0].periodo).toBe("Storico 2025");
    expect(righe[0].ebitda_margin).toBe(12.5);
    expect(righe[1].periodo).toBe("Infrann. 9M");
    expect(righe[1].ebitda_margin).toBe(8.25);
  });

  it("scarta le serie assenti invece di renderle a zero", () => {
    // Una proiezione mancante (bilancio già annuale, o previsionale non
    // generato) NON deve diventare una barra a zero: sarebbe indistinguibile
    // da un'azienda con EBITDA nullo.
    const serie: SerieIndicatori[] = [
      { periodo: "Storico 2025", indicatori: indicatori({ ebitda_margin: 12.5 }) },
      { periodo: "Infrann. 9M", indicatori: indicatori({ ebitda_margin: 8.25 }) },
      { periodo: "Proiezione 2026", indicatori: null },
    ];

    const righe = buildIndicatorChartData(serie);

    expect(righe).toHaveLength(2);
    expect(righe.map((r) => r.periodo)).toEqual(["Storico 2025", "Infrann. 9M"]);
  });

  it("conserva l'ordine delle serie", () => {
    const serie: SerieIndicatori[] = [
      { periodo: "A", indicatori: indicatori() },
      { periodo: "B", indicatori: null },
      { periodo: "C", indicatori: indicatori() },
    ];

    expect(buildIndicatorChartData(serie).map((r) => r.periodo)).toEqual(["A", "C"]);
  });

  it("porta i tre campi di ciascun grafico", () => {
    const serie: SerieIndicatori[] = [
      {
        periodo: "Storico 2025",
        indicatori: indicatori({
          ebitda_margin: 10,
          materials_revenue: 30,
          services_revenue: 20,
          mt: 1000,
          ms: -500,
          pfn: 2000,
        }),
      },
    ];

    const [riga] = buildIndicatorChartData(serie);

    // Incidenza economica sui ricavi
    expect(riga.ebitda_margin).toBe(10);
    expect(riga.materials_revenue).toBe(30);
    expect(riga.services_revenue).toBe(20);
    // Equilibrio finanziario e strutturale
    expect(riga.mt).toBe(1000);
    expect(riga.ms).toBe(-500);
    expect(riga.pfn).toBe(2000);
  });

  it("restituisce un elenco vuoto quando nessuna serie è disponibile", () => {
    expect(buildIndicatorChartData([{ periodo: "Solo", indicatori: null }])).toEqual([]);
  });
});
