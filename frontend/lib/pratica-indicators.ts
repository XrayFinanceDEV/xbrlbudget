import { formatEuro } from "@/lib/pratica-format";

/**
 * Il CALCOLO degli indicatori della crisi d'impresa (insieme, punteggio,
 * rating) sta sul server: `calculations/crisi_impresa.py`, letto da
 * `GET .../infrannuale/crisi` (vedi `lib/pratica-crisi.ts`). Qui restano il
 * tipo dell'insieme, le etichette di tabella e tutto cio' che serve a
 * RENDERLO: pallino, grafici, assi.
 */

export interface IndicatorSet {
  dscr: number;
  ebitda_margin: number;
  mt: number;
  ccn: number;
  current_ratio: number;
  ms: number;
  copertura_immob: number;
  indipendenza: number;
  pfn: number;
  pfn_ebitda: number;
  roi: number;
  roe: number;
  ros: number;
  // Due domande diverse, tenute entrambe: `of_mol` dice quanto pesano gli
  // oneri sulla capacita' di generare cassa ed e' quello usato dal punteggio
  // di crisi; `of_revenue` dice quanto pesano sul giro d'affari.
  of_mol: number;
  of_revenue: number;
  materials_revenue: number;
  services_revenue: number;
  // Grezzi, calcolati dal server come il resto: il punteggio li usa per
  // distinguere «zero» da «il rapporto non esiste», i grafici qui sotto pure.
  _ebitda_raw: number;
  _quick_ratio: number;
  _equity_over_fixed: number;
  // Serve al punteggio di `of_revenue`: il rapporto da solo non distingue
  // «oneri nulli» da «ricavi nulli», e su un punteggio invertito i due
  // porterebbero allo stesso verdetto di eccellenza.
  _revenue_raw: number;
  // I tre denominatori che servono solo alla RESA dei grafici, non al
  // punteggio: `DENOMINATORE_DEL_RAPPORTO` li legge per rendere `null` — e non
  // zero — `roi`, `roe` e `dscr` quando il rapporto non esiste. Stessa ragione
  // di `_ebitda_raw` e `_revenue_raw`, che sono nati per questo.
  _total_assets_raw: number;
  _equity_raw: number;
  _oneri_finanziari_raw: number;
}

/**
 * Etichette e formati della tabella a schermo. Lo stesso elenco, nello stesso
 * ordine, sta in `calculations/crisi_impresa.py` (`INDICATORI`), che lo manda
 * anche al report PDF: `lib/pratica-crisi.test.ts` non puo' confrontarli, quindi
 * una modifica qui va fatta anche li'.
 */
export const INDICATOR_DEFS: Array<{
  key: keyof IndicatorSet;
  label: string;
  format: "euro" | "pct" | "ratio";
}> = [
  { key: "dscr", label: "DSCR", format: "ratio" },
  { key: "ebitda_margin", label: "EBITDA %", format: "pct" },
  { key: "mt", label: "Margine di Tesoreria", format: "euro" },
  { key: "ccn", label: "CCN", format: "euro" },
  { key: "current_ratio", label: "Liquidità Corrente", format: "ratio" },
  { key: "ms", label: "Margine di Struttura", format: "euro" },
  { key: "copertura_immob", label: "Copertura Immobilizzazioni", format: "pct" },
  { key: "indipendenza", label: "Indipendenza Finanziaria", format: "pct" },
  { key: "pfn", label: "PFN", format: "euro" },
  { key: "pfn_ebitda", label: "PFN / EBITDA", format: "ratio" },
  { key: "roi", label: "ROI", format: "pct" },
  { key: "roe", label: "ROE", format: "pct" },
  { key: "ros", label: "ROS", format: "pct" },
  { key: "of_mol", label: "Oneri Finanziari / MOL", format: "pct" },
  { key: "of_revenue", label: "Oneri Finanziari / Fatturato", format: "pct" },
];

/**
 * Una serie dei grafici della sezione Indicatori: l'etichetta della colonna e
 * il suo set di indicatori, oppure `null` quando quel periodo non esiste
 * (bilancio già annuale, o previsionale non ancora generato).
 */
export type SerieIndicatori = { periodo: string; indicatori: IndicatorSet | null };

/** Riga appiattita come la vuole Recharts: etichetta + tutti gli indicatori. */
export type RigaGraficoIndicatori = { periodo: string } & {
  [K in keyof IndicatorSet]: number | null;
};

/**
 * Gli indicatori il cui zero NON significa zero, con il grezzo che lo dice.
 *
 * `safeDivide` restituisce 0 su denominatore nullo, e a quel punto lo zero di
 * `pfn_ebitda` («nessun debito netto», ottimo) e quello di un EBITDA inesistente
 * («il rapporto non esiste», pessimo) sono lo stesso numero. Sul punteggio la
 * distinzione c'è già — `scoreIndicator` guarda `_ebitda_raw` e `_revenue_raw` —
 * ma i grafici la perdevano: una barra a zero è indistinguibile da un'azienda
 * con EBITDA nullo, che è esattamente ciò che l'issue #15 vieta.
 */
const DENOMINATORE_DEL_RAPPORTO: Partial<Record<keyof IndicatorSet, keyof IndicatorSet>> = {
  pfn_ebitda: "_ebitda_raw",
  of_mol: "_ebitda_raw",
  of_revenue: "_revenue_raw",
  // Le tre serie dell'incidenza economica: senza ricavi la percentuale non
  // esiste, e uno zero su «materie / ricavi» legge «nessun costo di materia».
  ebitda_margin: "_revenue_raw",
  materials_revenue: "_revenue_raw",
  services_revenue: "_revenue_raw",
  // ROI e ROE: uno zero qui legge «nessun ritorno sul capitale», che e' un
  // giudizio sull'azienda, mentre un attivo o un patrimonio netto nulli dicono
  // solo che il rapporto non esiste. Su patrimonio netto NEGATIVO il ROE non ha
  // nemmeno significato — un utile diviso un PN negativo cambia segno per il
  // denominatore, non per la redditivita' — e il confronto `<= 0` lo esclude.
  roi: "_total_assets_raw",
  roe: "_equity_raw",
  // Il DSCR e' il caso opposto agli altri, ed e' il piu' insidioso: zero oneri
  // finanziari significa copertura INFINITA, cioe' il valore migliore
  // possibile, e `safeDivide` lo rende come zero, cioe' il peggiore. L'azienda
  // piu' sana su questo indicatore apparirebbe come la meno solvibile.
  dscr: "_oneri_finanziari_raw",
};

/**
 * Oltre quanti punti percentuali un'incidenza SUI RICAVI smette di essere
 * un'incidenza.
 *
 * La guardia qui sopra è su denominatore ZERO, e un denominatore minuscolo non
 * è zero: su AIC SRL i ricavi 2025 valgono 100,92 € (il fatturato vero sta su
 * `ce04_altri_ricavi`), «Materie / Ricavi» risulta 421.930,8%, l'asse arriva a
 * 600.000% e le altre due colonne — 3.246,0% e 149,3% — diventano linee piatte
 * indistinguibili dallo zero. Il grafico è corretto rispetto ai dati; sono i
 * dati a non essere un'incidenza.
 *
 * La soglia è **adimensionale** di proposito: un minimo di ricavi in euro
 * varrebbe solo per aziende di una certa taglia, mentre «il numeratore supera
 * dieci volte il proprio denominatore» dice la stessa cosa a ogni scala. È
 * l'analogo del rapporto di rotazione che implica più di un anno di magazzino
 * (`_turnover_ratio` → `None` in `intra_year_engine`): una soglia di dominio,
 * non un epsilon numerico. Il valore è tarabile dal proprietario; ciò che non
 * si può fare è cambiarlo credendo di toccare solo l'estetica.
 *
 * **Vale per i soli rapporti che dividono per i RICAVI**, e non per «ogni
 * percentuale grande». Fra i denominatori che i grafici usano, `_revenue_raw` è
 * l'unico che può essere prossimo a zero mentre l'azienda non lo è: un
 * fatturato finito su `ce04` in fase di import è un esito reale e frequente,
 * ed è esattamente il caso di questa issue. Gli altri no — patrimonio netto e
 * attivo non positivi sono già esclusi dal `<= 0` qui sopra, e un ROE del
 * 1.500% su un patrimonio sottile o oneri finanziari pari a quindici volte il
 * MOL sono numeri **genuini**, che vanno visti: nasconderli sarebbe perdere
 * un'informazione vera per rendere più bello un asse.
 *
 * **Solo la RESA.** `computeIndicators` e `scoreIndicator` non cambiano, quindi
 * il pallino di riga e il rating di crisi restano quelli di prima. Correggere
 * il denominatore a monte — usare il valore della produzione invece di `ce01` —
 * sposterebbe i punteggi di OGNI azienda, ed è una decisione di prodotto.
 */
export const INCIDENZA_MAX_PCT = 1000;

/**
 * Costruisce le righe dei due grafici (incidenza economica ed equilibrio
 * finanziario) da un elenco di serie.
 *
 * Vive qui, e non dentro il componente, perché la consumano DUE viste — la tab
 * Indicatori e la Stampa — e perché è l'unica parte testabile: la suite di
 * questo progetto gira senza DOM (`environment: "node"`), quindi il componente
 * si verifica nel browser e la logica si verifica qui.
 *
 * Una serie assente viene SCARTATA, non resa a zero: una barra a zero sarebbe
 * indistinguibile da un'azienda con EBITDA nullo. Vale per l'intero periodo
 * (`indicatori === null`) e, dentro un periodo che esiste, per il singolo
 * rapporto il cui denominatore è nullo: là lo zero di `safeDivide` non è un
 * valore, è l'assenza di un valore. Recharts salta un punto `null`.
 *
 * Un denominatore che esiste ma è troppo piccolo per reggere il rapporto è
 * trattato allo stesso modo, ma per i soli rapporti sui RICAVI: vedi
 * `INCIDENZA_MAX_PCT` qui sopra.
 */
export function buildIndicatorChartData(serie: SerieIndicatori[]): RigaGraficoIndicatori[] {
  return serie
    .filter((s): s is { periodo: string; indicatori: IndicatorSet } => s.indicatori !== null)
    .map((s) => {
      const riga = { periodo: s.periodo, ...s.indicatori } as RigaGraficoIndicatori;
      for (const [rapporto, grezzo] of Object.entries(DENOMINATORE_DEL_RAPPORTO)) {
        const chiave = rapporto as keyof IndicatorSet;
        if (s.indicatori[grezzo as keyof IndicatorSet] <= 0) {
          riga[chiave] = null;
          continue;
        }
        // I ricavi ci sono ma sono troppo piccoli per fare da base: il rapporto
        // esiste, non è un'incidenza. Vedi `INCIDENZA_MAX_PCT`. Il controllo
        // sull'unità non è ridondanza: se un domani un rapporto in VOLTE
        // dividesse per i ricavi, confrontarlo con una soglia in punti
        // percentuali sarebbe un confronto fra unità diverse.
        if (
          grezzo === "_revenue_raw" &&
          indicatorFormat(chiave) === "pct" &&
          Math.abs(s.indicatori[chiave]) > INCIDENZA_MAX_PCT
        ) {
          riga[chiave] = null;
        }
      }
      return riga;
    });
}

export type IndicatorFormat = "euro" | "pct" | "ratio";

/**
 * Le unità degli indicatori che i GRAFICI rendono ma la tabella no.
 *
 * `materials_revenue` e `services_revenue` non stanno in `INDICATOR_DEFS`, e
 * non vanno aggiunti lì per comodità: `CRISIS_SCORING_KEYS` deriva da quella
 * lista, e le bande di `computeCrisisRating` sono tarate sul NUMERO di
 * indicatori che le alimentano — due voci in più sposterebbero la classe di
 * rischio di aziende reali senza che nessuno l'abbia deciso. Sono incidenze sui
 * ricavi, quindi percentuali.
 */
const FORMATI_FUORI_TABELLA: Partial<Record<keyof IndicatorSet, IndicatorFormat>> = {
  materials_revenue: "pct",
  services_revenue: "pct",
};

/**
 * L'unità di un indicatore. `INDICATOR_DEFS` resta la fonte per tutto ciò che
 * la tabella rende; il resto viene da `FORMATI_FUORI_TABELLA`.
 */
export function indicatorFormat(key: keyof IndicatorSet): IndicatorFormat | undefined {
  return INDICATOR_DEFS.find((d) => d.key === key)?.format ?? FORMATI_FUORI_TABELLA[key];
}

/**
 * Un riquadro dei grafici della sezione Indicatori: titolo, unità dell'asse e
 * le serie che vi finiscono dentro.
 *
 * È dato PURO, e vive qui e non nel componente per una ragione sola: la suite
 * gira in `environment: "node"`, quindi il componente non è verificabile e
 * questa configurazione sì. Il componente si limita a renderla, così non può
 * divergere da ciò che i test fissano.
 */
export type IndicatorChartSeries = {
  key: keyof IndicatorSet;
  label: string;
  /** Riferimento a una variabile CSS del tema, non una classe Tailwind. */
  color: string;
};

export type IndicatorChartBox = {
  id: string;
  title: string;
  description: string;
  /**
   * L'unità dell'INTERO riquadro. Deve coincidere con il `format` che
   * `INDICATOR_DEFS` dichiara per OGNI serie: `pratica-chart-boxes.test.ts` lo
   * verifica voce per voce.
   */
  format: IndicatorFormat;
  series: IndicatorChartSeries[];
};

/**
 * I sei riquadri, nell'ordine in cui vengono resi.
 *
 * **Nessun riquadro mescola unità.** Un CCN in euro accanto a un ROI in
 * percentuale tara l'asse sulle centinaia di migliaia e schiaccia la
 * percentuale sullo zero: escono due grafici, e nessuno dei due si legge. È
 * anche il motivo per cui il CCN (euro) ha un riquadro tutto suo invece di
 * stare con ROI e ROE.
 *
 * L'ordine non è casuale. A schermo la griglia è 2×3, quindi le coppie di riga
 * sono (1,2), (3,4), (5,6): ogni riga accosta un riquadro percentuale e uno in
 * euro o in volte, così due assi identici non finiscono mai affiancati. In
 * stampa la griglia diventa 3×2 e le righe sono (1,2,3) e (4,5,6).
 */
export const INDICATOR_CHART_BOXES: IndicatorChartBox[] = [
  {
    id: "incidenza-economica",
    title: "Incidenza economica sui ricavi",
    description: "EBITDA, materie prime e servizi in percentuale dei ricavi.",
    format: "pct",
    series: [
      { key: "ebitda_margin", label: "EBITDA / Ricavi", color: "hsl(var(--chart-2))" },
      { key: "materials_revenue", label: "Materie / Ricavi", color: "hsl(var(--chart-3))" },
      { key: "services_revenue", label: "Servizi / Ricavi", color: "hsl(var(--chart-4))" },
    ],
  },
  {
    id: "equilibrio-finanziario",
    title: "Equilibrio finanziario e strutturale",
    description: "Margine di tesoreria, margine di struttura e PFN.",
    format: "euro",
    series: [
      { key: "mt", label: "Margine di Tesoreria", color: "hsl(var(--chart-1))" },
      { key: "ms", label: "Margine di Struttura", color: "hsl(var(--chart-2))" },
      { key: "pfn", label: "PFN", color: "hsl(var(--chart-5))" },
    ],
  },
  {
    id: "redditivita",
    title: "Redditività",
    description: "ROI e ROE: ritorno sul capitale investito e sul patrimonio netto.",
    format: "pct",
    series: [
      { key: "roi", label: "ROI", color: "hsl(var(--chart-1))" },
      { key: "roe", label: "ROE", color: "hsl(var(--chart-3))" },
    ],
  },
  {
    id: "capitale-circolante",
    title: "Capitale circolante netto",
    description: "Attivo corrente meno passivo corrente (CCN).",
    format: "euro",
    series: [{ key: "ccn", label: "CCN", color: "hsl(var(--chart-1))" }],
  },
  {
    id: "sostenibilita-debito",
    title: "Sostenibilità del debito",
    description: "PFN / EBITDA e DSCR, espressi in volte.",
    format: "ratio",
    series: [
      { key: "pfn_ebitda", label: "PFN / EBITDA", color: "hsl(var(--chart-5))" },
      { key: "dscr", label: "DSCR", color: "hsl(var(--chart-2))" },
    ],
  },
  {
    id: "oneri-finanziari",
    title: "Peso degli oneri finanziari",
    description: "Oneri finanziari sul fatturato e sul MOL.",
    format: "pct",
    series: [
      // Due domande diverse sullo stesso costo: quanto pesa sul giro d'affari
      // e quanto sulla cassa generata. Stanno insieme perché la risposta si
      // legge nel confronto, e condividono l'unità.
      { key: "of_revenue", label: "OF / Fatturato", color: "hsl(var(--chart-4))" },
      { key: "of_mol", label: "OF / MOL", color: "hsl(var(--chart-2))" },
    ],
  },
];

/**
 * L'etichetta di un tick d'asse. Compatta di proposito: in stampa un riquadro
 * è largo un terzo di A4 e un valore per esteso mangia metà del grafico.
 */
export function formatIndicatorAxis(value: number, format: IndicatorFormat): string {
  if (format === "euro") {
    return new Intl.NumberFormat("it-IT", { notation: "compact" }).format(value);
  }
  if (format === "pct") {
    return `${new Intl.NumberFormat("it-IT", { maximumFractionDigits: 0 }).format(value)}%`;
  }
  return `${new Intl.NumberFormat("it-IT", { maximumFractionDigits: 1 }).format(value)}x`;
}

/**
 * La larghezza in pixel che il grafico riserva all'asse Y.
 *
 * Recharts usa una larghezza FISSA (60px di default) e RITAGLIA ciò che non ci
 * sta: un'incidenza a sei cifre come `600.000%` esce come `00.000%`, con la
 * prima cifra mangiata dal bordo e senza alcun errore. Il difetto NON dipende
 * dalla scala dei valori — un margine in euro di un'azienda grande si taglia
 * allo stesso modo — quindi non si chiude ritarando i dati: la larghezza va
 * presa dalle etichette che quel riquadro renderà davvero.
 *
 * La misura è per forza approssimata: la suite gira senza DOM, quindi qui
 * nessuno può misurare il testo. `AXIS_CHAR_PX` è la larghezza di una cifra a
 * 12px nel font di sistema, arrotondata per eccesso, e la cifra di margine
 * copre il tick «tondo» che Recharts sceglie SOPRA il massimo dei dati (950 →
 * 1.000, che è più lungo del dato che l'ha prodotto). Sovrastimare costa un po'
 * di area del grafico, sottostimare taglia una cifra: l'errore è ammesso in un
 * verso solo.
 */
export const AXIS_WIDTH_MIN = 60;
export const AXIS_WIDTH_MAX = 110;
const AXIS_CHAR_PX = 7;
const AXIS_PADDING_PX = 12;

export function indicatorAxisWidth(
  righe: RigaGraficoIndicatori[],
  box: IndicatorChartBox,
): number {
  let lunghezzaMax = 0;
  for (const riga of righe) {
    for (const serie of box.series) {
      const valore = riga[serie.key];
      // `null` è l'assenza di un valore, non uno zero: non produce un'etichetta
      // e non occupa larghezza. Vedi `buildIndicatorChartData`.
      if (valore === null || valore === undefined || !Number.isFinite(valore)) continue;
      lunghezzaMax = Math.max(lunghezzaMax, formatIndicatorAxis(valore, box.format).length);
    }
  }
  if (lunghezzaMax === 0) return AXIS_WIDTH_MIN;
  const larghezza = (lunghezzaMax + 1) * AXIS_CHAR_PX + AXIS_PADDING_PX;
  return Math.min(AXIS_WIDTH_MAX, Math.max(AXIS_WIDTH_MIN, larghezza));
}

/** Il valore per esteso nel tooltip, nella stessa forma della tabella indicatori. */
export function formatIndicatorTooltip(value: number, format: IndicatorFormat): string {
  if (format === "euro") return formatEuro(value);
  if (format === "pct") {
    return `${new Intl.NumberFormat("it-IT", {
      minimumFractionDigits: 1,
      maximumFractionDigits: 1,
    }).format(value)}%`;
  }
  return `${new Intl.NumberFormat("it-IT", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value)}x`;
}

export function scoreDotColor(score: number): string {
  if (score >= 0.67) return "bg-green-500";
  if (score >= 0.33) return "bg-yellow-500";
  return "bg-red-500";
}
