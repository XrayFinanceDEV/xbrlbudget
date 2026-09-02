import { describe, expect, it } from "vitest";
import {
  AXIS_WIDTH_MAX,
  AXIS_WIDTH_MIN,
  INCIDENZA_MAX_PCT,
  INDICATOR_CHART_BOXES,
  INDICATOR_DEFS,
  buildIndicatorChartData,
  computeIndicators,
  indicatorAxisWidth,
  indicatorFormat,
  formatIndicatorAxis,
  formatIndicatorTooltip,
  scoreIndicator,
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
    _total_assets_raw: 0,
    _equity_raw: 0,
    _oneri_finanziari_raw: 0,
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
          _total_assets_raw: 900000, _equity_raw: 300000, _oneri_finanziari_raw: 12000,
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

  it("ROI e ROE valgono `null` quando attivo o patrimonio netto non esistono", () => {
    // Il denominatore di questi due non e' in `IndicatorSet` per il punteggio,
    // ma per la RESA: un ROI a zero legge «nessun ritorno sul capitale», che e'
    // un giudizio, mentre l'attivo nullo dice solo che il rapporto non esiste.
    const [senzaAttivo] = buildIndicatorChartData([
      {
        periodo: "Storico 2025",
        indicatori: indicatori({ roi: 0, _total_assets_raw: 0, _equity_raw: 300000 }),
      },
    ]);
    expect(senzaAttivo.roi).toBeNull();
    expect(senzaAttivo.roe).toBeTypeOf("number");

    // Patrimonio netto NEGATIVO: il ROE non ha significato — un utile diviso un
    // patrimonio negativo esce positivo per il segno, non per la redditivita'.
    const [pnNegativo] = buildIndicatorChartData([
      {
        periodo: "Storico 2025",
        indicatori: indicatori({ roe: 0, _total_assets_raw: 900000, _equity_raw: -50000 }),
      },
    ]);
    expect(pnNegativo.roe).toBeNull();
    expect(pnNegativo.roi).toBeTypeOf("number");
  });

  it("il DSCR senza oneri finanziari vale `null`, non zero: mente al contrario", () => {
    // E' il caso piu' insidioso dei tre. Zero oneri finanziari significa DSCR
    // infinito, cioe' la situazione MIGLIORE possibile su questo indicatore;
    // `safeDivide` lo rende come zero, cioe' la peggiore. L'azienda piu' sana
    // del campione apparirebbe come quella che non copre il proprio debito.
    const [senzaOneri] = buildIndicatorChartData([
      {
        periodo: "Storico 2025",
        indicatori: indicatori({ dscr: 0, _oneri_finanziari_raw: 0 }),
      },
    ]);
    expect(senzaOneri.dscr).toBeNull();

    const [conOneri] = buildIndicatorChartData([
      {
        periodo: "Storico 2025",
        indicatori: indicatori({ dscr: 1.4, _oneri_finanziari_raw: 12000 }),
      },
    ]);
    expect(conOneri.dscr).toBe(1.4);
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

describe("indicatorAxisWidth", () => {
  // Recharts riserva all'asse Y una larghezza FISSA (60px di default) e ritaglia
  // ciò che non ci sta: `600.000%` esce come `00.000%`, con la prima cifra
  // mangiata dal bordo. Il difetto è indipendente dalla scala — un margine in
  // euro su un'azienda grande si taglia allo stesso modo — quindi la larghezza
  // va calcolata dalle etichette che quel riquadro renderà davvero.
  const riquadroPct = INDICATOR_CHART_BOXES.find((b) => b.id === "incidenza-economica")!;
  const riquadroEuro = INDICATOR_CHART_BOXES.find((b) => b.id === "equilibrio-finanziario")!;
  const riquadroVolte = INDICATOR_CHART_BOXES.find((b) => b.id === "sostenibilita-debito")!;

  it("un'etichetta lunga allarga l'asse oltre il default di Recharts", () => {
    const strette = buildIndicatorChartData([
      {
        periodo: "Storico 2025",
        indicatori: indicatori({ mt: 1200, ms: 800, pfn: -300 }),
      },
    ]);
    const larghe = buildIndicatorChartData([
      {
        periodo: "Storico 2025",
        indicatori: indicatori({ mt: 1200, ms: -450000000, pfn: 0 }),
      },
    ]);
    expect(indicatorAxisWidth(strette, riquadroEuro)).toBe(AXIS_WIDTH_MIN);
    expect(indicatorAxisWidth(larghe, riquadroEuro)).toBeGreaterThan(AXIS_WIDTH_MIN);
  });

  it("misura solo le serie del proprio riquadro", () => {
    // Un valore enorme che sta in un ALTRO riquadro non deve allargare questo:
    // l'asse rende le sue serie, non tutto l'`IndicatorSet`.
    const righe = buildIndicatorChartData([
      {
        periodo: "Storico 2025",
        indicatori: indicatori({
          ebitda_margin: 12,
          materials_revenue: 40,
          services_revenue: 8,
          mt: -123456789,
          _revenue_raw: 400000,
        }),
      },
    ]);
    expect(indicatorAxisWidth(righe, riquadroPct)).toBe(AXIS_WIDTH_MIN);
    expect(indicatorAxisWidth(righe, riquadroEuro)).toBeGreaterThan(AXIS_WIDTH_MIN);
  });

  it("un punto `null` non conta e non fa saltare il calcolo", () => {
    // Un rapporto senza denominatore vale `null`: non ha etichetta, quindi non
    // ha larghezza. Trattarlo come 0 andrebbe bene, trattarlo come `NaN` no.
    const righe = buildIndicatorChartData([
      {
        periodo: "Storico 2025",
        indicatori: indicatori({ ebitda_margin: 0, _revenue_raw: 0 }),
      },
    ]);
    expect(righe[0].ebitda_margin).toBeNull();
    expect(indicatorAxisWidth(righe, riquadroPct)).toBe(AXIS_WIDTH_MIN);
  });

  it("nessuna riga: resta il default, non zero", () => {
    expect(indicatorAxisWidth([], riquadroPct)).toBe(AXIS_WIDTH_MIN);
  });

  it("non oltre il massimo: l'asse non si mangia il grafico", () => {
    const assurde = buildIndicatorChartData([
      {
        periodo: "Storico 2025",
        indicatori: indicatori({ pfn_ebitda: 999999999999, _ebitda_raw: 1 }),
      },
    ]);
    expect(indicatorAxisWidth(assurde, riquadroVolte)).toBe(AXIS_WIDTH_MAX);
  });
});

describe("ricavi troppo piccoli per fare da base (#33)", () => {
  // La guardia esistente è su denominatore ZERO, e 100,92 € di ricavi non sono
  // zero: su AIC SRL «Materie / Ricavi» 2025 vale 421.930,8%, l'asse arriva a
  // 600.000% e le altre due colonne — 3.246,0% e 149,3% — diventano linee
  // piatte indistinguibili dallo zero. Il grafico è corretto rispetto ai dati;
  // sono i dati a non essere un'incidenza.
  //
  // La correzione è di RESA e basta: `computeIndicators` e `scoreIndicator` non
  // si toccano, perché cambiare il denominatore a monte sposterebbe i punteggi
  // e quindi il rating di crisi di ogni azienda.

  it("i ricavi di AIC SRL: l'incidenza a sei cifre non finisce sul grafico", () => {
    const ind = computeIndicators(
      {},
      { ce01_ricavi_vendite: 100.92, ce05_materie_prime: 425850 },
    );
    // Il rapporto grezzo resta quello che è: nessuno lo ha ritoccato.
    expect(ind.materials_revenue).toBeGreaterThan(400000);

    const [riga] = buildIndicatorChartData([{ periodo: "Storico 2025", indicatori: ind }]);
    expect(riga.materials_revenue).toBeNull();
    expect(riga.ebitda_margin).toBeNull();
  });

  it("l'asse si restringe perché il valore degenere non produce più un'etichetta", () => {
    // È l'effetto che l'issue chiede: senza la riga a sei cifre l'asse torna
    // alla larghezza minima invece di riservare spazio a «600.000%».
    const ind = computeIndicators(
      {},
      { ce01_ricavi_vendite: 100.92, ce05_materie_prime: 425850 },
    );
    const riquadro = INDICATOR_CHART_BOXES.find((b) => b.id === "incidenza-economica")!;
    const righe = buildIndicatorChartData([{ periodo: "Storico 2025", indicatori: ind }]);
    expect(indicatorAxisWidth(righe, riquadro)).toBe(AXIS_WIDTH_MIN);
  });

  it("un'incidenza alta ma plausibile resta sul grafico", () => {
    // Materie pari a tre volte i ricavi è un'azienda in difficoltà, non un
    // denominatore sbagliato: si deve vedere.
    const [riga] = buildIndicatorChartData([
      {
        periodo: "Storico 2025",
        indicatori: indicatori({
          materials_revenue: 300,
          ebitda_margin: -250,
          _revenue_raw: 120000,
        }),
      },
    ]);
    expect(riga.materials_revenue).toBe(300);
    expect(riga.ebitda_margin).toBe(-250);
  });

  it("la soglia è sul valore assoluto, e il limite esatto passa", () => {
    const [riga] = buildIndicatorChartData([
      {
        periodo: "Storico 2025",
        indicatori: indicatori({
          materials_revenue: INCIDENZA_MAX_PCT,
          services_revenue: -INCIDENZA_MAX_PCT - 1,
          _revenue_raw: 120000,
        }),
      },
    ]);
    expect(riga.materials_revenue).toBe(INCIDENZA_MAX_PCT);
    expect(riga.services_revenue).toBeNull();
  });

  it("vale anche su «OF / Fatturato», che divide per gli stessi ricavi", () => {
    const [riga] = buildIndicatorChartData([
      {
        periodo: "Storico 2025",
        indicatori: indicatori({ of_revenue: 9500, _revenue_raw: 100.92 }),
      },
    ]);
    expect(riga.of_revenue).toBeNull();
  });

  it("gli altri denominatori NON sono toccati: il loro estremo è un dato vero", () => {
    // Un ROE del 1.500% su un patrimonio netto sottile, o oneri finanziari pari
    // a quindici volte il MOL, sono numeri genuini e vanno visti: il difetto di
    // questa issue è il denominatore «ricavi», non la grandezza del rapporto.
    const [riga] = buildIndicatorChartData([
      {
        periodo: "Storico 2025",
        indicatori: indicatori({
          roe: 1500,
          _equity_raw: 5000,
          of_mol: 1500,
          _ebitda_raw: 800,
          pfn_ebitda: 1200,
        }),
      },
    ]);
    expect(riga.roe).toBe(1500);
    expect(riga.of_mol).toBe(1500);
    // `pfn_ebitda` è in volte, non in punti percentuali: confrontarlo con una
    // soglia percentuale sarebbe un confronto fra unità diverse.
    expect(riga.pfn_ebitda).toBe(1200);
  });

  it("il PUNTEGGIO non si muove: la correzione è solo sulla resa", () => {
    // Il pallino di riga e il rating di crisi continuano a leggere
    // l'`IndicatorSet`, non la riga del grafico. È il confine che #25 aveva
    // già fissato e che questa correzione non attraversa.
    const ind = computeIndicators(
      {},
      { ce01_ricavi_vendite: 100.92, ce05_materie_prime: 425850 },
    );
    const [riga] = buildIndicatorChartData([{ periodo: "Storico 2025", indicatori: ind }]);
    expect(riga.ebitda_margin).toBeNull();
    // EBITDA largamente negativo: il punteggio resta 0, come prima.
    expect(scoreIndicator("ebitda_margin", ind)).toBe(0);
  });
});
