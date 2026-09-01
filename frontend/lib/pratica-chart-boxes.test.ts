import { describe, expect, it } from "vitest";
import {
  INDICATOR_CHART_BOXES,
  INDICATOR_DEFS,
  buildIndicatorChartData,
  indicatorFormat,
  formatIndicatorAxis,
  formatIndicatorTooltip,
  type IndicatorSet,
  type SerieIndicatori,
} from "@/lib/pratica-indicators";

/**
 * La CONFIGURAZIONE dei sei grafici della sezione Indicatori è dato puro, e sta
 * in `lib/` proprio per poter essere fissata qui: la suite di questo progetto
 * gira senza DOM (`environment: "node"`), quindi il componente non è
 * verificabile e la sola difesa contro un riquadro sbagliato è un test sulla
 * sua configurazione.
 *
 * L'invariante che conta è UNO: **nessun riquadro mescola unità**. Un CCN in
 * euro accanto a un ROI in percentuale rende illeggibili entrambi — l'asse si
 * tara sulle centinaia di migliaia e la percentuale diventa una riga schiacciata
 * sullo zero. È il motivo per cui i due grafici storici erano già divisi così, e
 * passando da due a sei riquadri la regola si può violare senza che nulla si
 * rompa a schermo: il grafico esce, è solo inutile.
 */

function indicatori(patch: Partial<IndicatorSet> = {}): IndicatorSet {
  return {
    dscr: 0,
    ebitda_margin: 0,
    mt: 0,
    ccn: 0,
    current_ratio: 0,
    ms: 0,
    copertura_immob: 0,
    indipendenza: 0,
    pfn: 0,
    pfn_ebitda: 0,
    roi: 0,
    roe: 0,
    ros: 0,
    of_mol: 0,
    of_revenue: 0,
    materials_revenue: 0,
    services_revenue: 0,
    _ebitda_raw: 0,
    _quick_ratio: 0,
    _equity_over_fixed: 0,
    _revenue_raw: 0,
    ...patch,
  };
}

describe("INDICATOR_CHART_BOXES", () => {
  it("nessun riquadro mescola unità diverse", () => {
    for (const box of INDICATOR_CHART_BOXES) {
      for (const serie of box.series) {
        expect(
          indicatorFormat(serie.key),
          `il riquadro "${box.title}" è dichiarato ${box.format} ma la serie ` +
            `"${serie.key}" è ${indicatorFormat(serie.key)}`,
        ).toBe(box.format);
      }
    }
  });

  it("rende sei riquadri", () => {
    expect(INDICATOR_CHART_BOXES).toHaveLength(6);
  });

  it("copre i sei indicatori chiesti dall'issue oltre ai due grafici storici", () => {
    const rese = new Set(
      INDICATOR_CHART_BOXES.flatMap((b) => b.series.map((s) => s.key)),
    );
    // I sei nuovi (issue #15).
    for (const key of ["ccn", "dscr", "roi", "of_revenue", "pfn_ebitda", "roe"] as const) {
      expect(rese.has(key), `manca ${key} dai grafici`).toBe(true);
    }
    // I due grafici preesistenti restano interi.
    for (const key of [
      "ebitda_margin",
      "materials_revenue",
      "services_revenue",
      "mt",
      "ms",
      "pfn",
    ] as const) {
      expect(rese.has(key), `il grafico storico ha perso ${key}`).toBe(true);
    }
  });

  it("ogni serie ha un'unità dichiarata", () => {
    // Un'unità mancante non fa errore: `formatIndicatorAxis` cadrebbe sul ramo
    // `ratio` e stamperebbe «1.234.567x» su un asse in euro.
    for (const box of INDICATOR_CHART_BOXES) {
      for (const serie of box.series) {
        expect(indicatorFormat(serie.key), `${serie.key} non ha unità`).toBeDefined();
      }
    }
  });

  it("`indicatorFormat` non contraddice INDICATOR_DEFS", () => {
    // Le due sorgenti (tabella + fuori tabella) non devono divergere: se un
    // giorno `materials_revenue` entrasse in INDICATOR_DEFS con un altro
    // formato, questo test lo dice invece di lasciar vincere l'uno o l'altro.
    for (const def of INDICATOR_DEFS) {
      expect(indicatorFormat(def.key), def.key).toBe(def.format);
    }
  });

  it("non rende lo stesso indicatore in due riquadri", () => {
    // Non è pedanteria: la stessa barra in due box fa credere a due misure
    // diverse, e con `of_mol`/`of_revenue` accanto l'equivoco è facilissimo.
    const chiavi = INDICATOR_CHART_BOXES.flatMap((b) => b.series.map((s) => s.key));
    expect(new Set(chiavi).size).toBe(chiavi.length);
  });

  it("ogni riquadro ha id univoco, titolo e almeno una serie", () => {
    const ids = INDICATOR_CHART_BOXES.map((b) => b.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const box of INDICATOR_CHART_BOXES) {
      expect(box.title.length).toBeGreaterThan(0);
      expect(box.series.length).toBeGreaterThan(0);
    }
  });

  it("un riquadro non porta più di tre serie", () => {
    // Con tre periodi a schermo, quattro serie fanno dodici barre in un
    // riquadro largo un terzo di A4: illeggibile in stampa.
    for (const box of INDICATOR_CHART_BOXES) {
      expect(box.series.length).toBeLessThanOrEqual(3);
    }
  });
});

describe("INDICATOR_CHART_BOXES + buildIndicatorChartData", () => {
  it("ogni serie di ogni riquadro arriva nelle righe del grafico", () => {
    // `buildIndicatorChartData` appiattisce tutto l'`IndicatorSet`, quindi una
    // chiave nuova arriva da sola: questo test lo fissa, perché se domani
    // l'appiattimento diventasse selettivo un riquadro resterebbe vuoto senza
    // un solo errore.
    // Denominatori non nulli: qui ogni rapporto ESISTE, quindi ogni serie deve
    // arrivare come numero. Il caso opposto — denominatore a zero — ha il suo
    // test qui sotto, ed è il solo in cui una serie può valere `null`.
    const [riga] = buildIndicatorChartData([
      {
        periodo: "Storico 2025",
        indicatori: indicatori({
          ccn: 1000, roi: 7.5, dscr: 1.4, _ebitda_raw: 50000, _revenue_raw: 400000,
        }),
      },
    ]);
    for (const box of INDICATOR_CHART_BOXES) {
      for (const serie of box.series) {
        expect(riga[serie.key], `${serie.key} assente dalla riga`).toBeTypeOf("number");
      }
    }
    expect(riga.ccn).toBe(1000);
    expect(riga.roi).toBe(7.5);
    expect(riga.dscr).toBe(1.4);
  });

  it("un rapporto senza denominatore vale `null`, non zero", () => {
    // `safeDivide` restituisce 0 su denominatore nullo, e su un grafico quello
    // zero è indistinguibile dal caso buono: `pfn_ebitda` a zero legge «nessun
    // debito netto», `of_mol` a zero legge «oneri irrilevanti». Sono i verdetti
    // opposti a quelli veri. Il punteggio la distinzione ce l'ha già
    // (`scoreIndicator` guarda `_ebitda_raw`); questo la porta ai grafici.
    const [senzaEbitda] = buildIndicatorChartData([
      {
        periodo: "Storico 2025",
        indicatori: indicatori({
          pfn: 250000, pfn_ebitda: 0, of_mol: 0, of_revenue: 3.2,
          _ebitda_raw: 0, _revenue_raw: 400000,
        }),
      },
    ]);
    expect(senzaEbitda.pfn_ebitda).toBeNull();
    expect(senzaEbitda.of_mol).toBeNull();
    // `of_revenue` ha il proprio denominatore, che qui esiste: resta un numero.
    expect(senzaEbitda.of_revenue).toBe(3.2);
    // Gli indicatori che non sono rapporti su un grezzo dichiarato non vengono
    // toccati: la PFN in euro è un valore, e 250.000 di debito netto va reso.
    expect(senzaEbitda.pfn).toBe(250000);

    const [senzaRicavi] = buildIndicatorChartData([
      {
        periodo: "Storico 2025",
        indicatori: indicatori({ of_revenue: 0, _ebitda_raw: 50000, _revenue_raw: 0 }),
      },
    ]);
    expect(senzaRicavi.of_revenue).toBeNull();
    // Anche le tre serie del riquadro «Incidenza economica sui ricavi»: senza
    // ricavi la percentuale non esiste, e uno zero su «materie / ricavi»
    // leggerebbe «nessun costo di materia».
    expect(senzaRicavi.ebitda_margin).toBeNull();
    expect(senzaRicavi.materials_revenue).toBeNull();
    expect(senzaRicavi.services_revenue).toBeNull();
  });

  it("un periodo senza dati resta scartato anche con i sei riquadri", () => {
    // Una barra a zero su CCN o DSCR sarebbe indistinguibile da un'azienda
    // senza circolante o senza copertura del servizio del debito.
    const serie: SerieIndicatori[] = [
      { periodo: "Storico 2025", indicatori: indicatori({ ccn: 1000 }) },
      { periodo: "Proiezione 2026", indicatori: null },
    ];
    const righe = buildIndicatorChartData(serie);
    expect(righe.map((r) => r.periodo)).toEqual(["Storico 2025"]);
  });
});

describe("formatIndicatorAxis / formatIndicatorTooltip", () => {
  it("euro: asse compatto, tooltip in valuta", () => {
    expect(formatIndicatorAxis(1500000, "euro")).toBe(
      new Intl.NumberFormat("it-IT", { notation: "compact" }).format(1500000),
    );
    // it-IT non raggruppa le migliaia sotto le cinque cifre: si prova su un valore che le ha.
    expect(formatIndicatorTooltip(1234567, "euro")).toContain("1.234.567");
  });

  it("pct: il simbolo di percentuale su entrambi", () => {
    expect(formatIndicatorAxis(12, "pct")).toBe("12%");
    expect(formatIndicatorTooltip(12.34, "pct")).toBe("12,3%");
  });

  it("ratio: il suffisso `x`, come la tabella degli indicatori", () => {
    expect(formatIndicatorAxis(1.5, "ratio")).toBe("1,5x");
    expect(formatIndicatorTooltip(1.5, "ratio")).toBe("1,50x");
  });

  it("regge i valori negativi, che su PFN e margini sono la norma", () => {
    expect(formatIndicatorTooltip(-2.5, "ratio")).toBe("-2,50x");
    expect(formatIndicatorAxis(-30, "pct")).toBe("-30%");
  });
});
