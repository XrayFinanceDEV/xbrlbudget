import type { IntraYearComparison, IntraYearComparisonItem } from "@/types/api";

/**
 * Gli otto valori in evidenza della tab Confronto.
 *
 * Sono di DUE tipi, e la differenza è sostanziale.
 *
 * Una card di **flusso** confronta la voce con la frazione d'anno trascorsa —
 * `pct_of_reference` contro `period_months / 12 × 100` — e risponde a «questa
 * voce sta correndo più o meno di quanto ci si aspetti a questo punto
 * dell'anno». Ha senso solo per una grandezza che matura pro-quota.
 *
 * Su un **rapporto** quel confronto è privo di significato: un margine non
 * matura pro-quota, e mostrarlo al 75% dopo nove mesi direbbe il falso. Le
 * card di rapporto si confrontano quindi col rapporto dell'ANNO DI
 * RIFERIMENTO — margine parziale contro margine storico — e il periodo si
 * semplifica da solo, perché numeratore e denominatore vengono entrambi dal
 * periodo parziale.
 *
 * Vive qui, e non dentro la pagina, perché è la parte che si può provare: la
 * suite gira senza DOM (`environment: "node"`).
 */

export type HighlightFlusso = {
  kind: "flusso";
  code: string;
  label: string;
  /** Valore del periodo parziale, in euro. */
  value: number;
  /** Quanto vale il parziale rispetto all'anno di riferimento, in %. */
  pctOfReference: number;
  /** La frazione d'anno trascorsa, in %. */
  expectedPct: number;
  /**
   * Il termine di paragone EFFETTIVO di questa card: la frazione d'anno per
   * ricavi ed EBITDA, il ritmo dei RICAVI per le tre voci di costo.
   */
  benchmarkPct: number;
  /** Come si chiama quel termine, per scriverlo in chiaro sulla card. */
  benchmarkLabel: string;
  annualized: number;
  /**
   * `true` = meglio del proprio termine di paragone. `null` quando un verdetto
   * non si può dare: nessun anno di riferimento, un riferimento non positivo,
   * il termine di paragone non calcolabile, o un pareggio esatto.
   *
   * Su un costo «meglio» vuol dire **cresciuto meno dei ricavi**, non
   * «cresciuto meno del calendario» — vedi `verdettoFlusso()`.
   */
  better: boolean | null;
};

export type HighlightRapporto = {
  kind: "rapporto";
  key: string;
  label: string;
  /** Il rapporto del periodo parziale, in punti percentuali. */
  value: number | null;
  /** Lo stesso rapporto sull'anno di riferimento. */
  reference: number | null;
  /** Differenza in punti percentuali fra i due. */
  deltaPp: number | null;
  /**
   * `true` = migliore del riferimento. Sui costi il segno è INVERTITO:
   * un'incidenza sui ricavi che scende è un miglioramento.
   *
   * `null` quando non c'è un verdetto da dare: nessun riferimento, un
   * denominatore a zero, **oppure uno scarto esattamente nullo** — un rapporto
   * identico al riferimento non è né migliorato né peggiorato, e `false`
   * dipingerebbe di rosso una freccia in giù su zero punti di scarto.
   */
  improved: boolean | null;
};

export type Highlight = HighlightFlusso | HighlightRapporto;

/**
 * Le card di flusso, nell'ordine in cui vanno rese, e **contro che cosa** si
 * giudica ciascuna.
 *
 * `calendario` — la voce si confronta con la frazione d'anno trascorsa: «sta
 * correndo più o meno di quanto ci si aspetti a questo punto dell'anno». Vale
 * per ricavi ed EBITDA, dove «più» è una buona notizia.
 *
 * `controRicavi` — la voce si confronta col **ritmo dei ricavi**. Vale per i
 * costi, e non è una rifinitura: contro il calendario si sbaglia in due modi
 * opposti e non se ne esce. Col verde su «sopra la quota» un'azienda che
 * cresce ha i costi verdi mentre corrono; invertendo il segno, un'azienda che
 * si contrae ha tre card verdi mentre il fatturato crolla — i costi scendono
 * solo perché scende tutto. Il fatto che conta è uno: il costo sta crescendo
 * più o meno del giro d'affari.
 */
type FlussoDef = {
  code: string;
  judge: "calendario" | "controRicavi";
};

export const HIGHLIGHT_FLOW_DEFS: FlussoDef[] = [
  { code: "ce01_ricavi_vendite", judge: "calendario" },
  { code: "ce08_costi_personale", judge: "controRicavi" },
  { code: "ce05_materie_prime", judge: "controRicavi" },
  { code: "ce06_servizi", judge: "controRicavi" },
  { code: "_ebitda", judge: "calendario" },
];

/** Il denominatore del confronto per i costi. */
const RICAVI_CODE = "ce01_ricavi_vendite";

type RapportoDef = {
  key: string;
  label: string;
  numerator: string;
  denominator: string;
  /** Un'incidenza che SCENDE è un miglioramento (vale per i costi). */
  lowerIsBetter: boolean;
};

export const HIGHLIGHT_RATIO_DEFS: RapportoDef[] = [
  {
    key: "ebitda_margin",
    label: "EBITDA margin",
    numerator: "_ebitda",
    denominator: "ce01_ricavi_vendite",
    lowerIsBetter: false,
  },
  {
    key: "materie_su_ricavi",
    label: "Materie / Ricavi",
    numerator: "ce05_materie_prime",
    denominator: "ce01_ricavi_vendite",
    lowerIsBetter: true,
  },
  {
    key: "servizi_su_ricavi",
    label: "Servizi / Ricavi",
    numerator: "ce06_servizi",
    denominator: "ce01_ricavi_vendite",
    lowerIsBetter: true,
  },
];

/**
 * Un `pct_of_reference` è leggibile solo con un riferimento **positivo**:
 * divide per il valore dell'anno storico, quindi sotto zero cambia segno e
 * ogni verdetto si rovescia.
 *
 * Su un EBITDA storico di −100.000: una perdita che si riduce a −30.000 dà
 * 30% e sembrerebbe «in ritardo»; una che peggiora a −150.000 dà 150% e
 * sembrerebbe in anticipo. Ed è proprio l'EBITDA la voce che finisce
 * regolarmente sotto zero — non i ricavi, per cui le quattro card storiche
 * non l'avevano mai incontrato.
 */
function ritmoLeggibile(
  item: IntraYearComparisonItem | undefined,
): item is IntraYearComparisonItem {
  return item !== undefined && item.reference_value > 0;
}

/**
 * Il termine di paragone e il verdetto di una card di flusso.
 *
 * `null` su ogni caso in cui un verdetto non si può dare — riferimento
 * assente o non positivo, ricavi non leggibili per una card di costo, e
 * **pareggio esatto**, che non è né un miglioramento né un peggioramento.
 */
function verdettoFlusso(
  item: IntraYearComparisonItem,
  def: FlussoDef,
  expectedPct: number,
  ricavi: IntraYearComparisonItem | undefined,
  hasReference: boolean,
): { benchmarkPct: number; benchmarkLabel: string; better: boolean | null } {
  const calendario = {
    benchmarkPct: expectedPct,
    benchmarkLabel: "frazione d'anno",
  };

  if (def.judge === "calendario") {
    if (!hasReference || !ritmoLeggibile(item)) {
      return { ...calendario, better: null };
    }
    if (item.pct_of_reference === expectedPct) return { ...calendario, better: null };
    // Ricavi ed EBITDA: correre più della frazione d'anno è una buona notizia.
    return { ...calendario, better: item.pct_of_reference > expectedPct };
  }

  // Costo: il paragone è il ritmo dei ricavi, e senza ricavi leggibili non
  // c'è paragone — meglio nessuna freccia che una freccia sul calendario.
  if (!hasReference || !ritmoLeggibile(item) || !ritmoLeggibile(ricavi)) {
    return {
      benchmarkPct: ricavi?.pct_of_reference ?? expectedPct,
      benchmarkLabel: "ricavi",
      better: null,
    };
  }
  const ricaviPct = ricavi.pct_of_reference;
  const base = { benchmarkPct: ricaviPct, benchmarkLabel: "ricavi" };
  if (item.pct_of_reference === ricaviPct) return { ...base, better: null };
  // Un costo che cresce MENO dei ricavi è un miglioramento.
  return { ...base, better: item.pct_of_reference < ricaviPct };
}

/**
 * Rapporto in punti percentuali, `null` sul denominatore assente.
 *
 * `null` e non zero di proposito: uno zero si legge come «margine nullo», che
 * è un fatto; un denominatore mancante è «non lo so», che non lo è.
 */
function ratio(numerator: number, denominator: number): number | null {
  if (!Number.isFinite(numerator) || !Number.isFinite(denominator)) return null;
  if (denominator === 0) return null;
  return (numerator / denominator) * 100;
}

/**
 * @param items le voci di CE **già arricchite** con la riga sintetica
 *   `_ebitda` (`buildIncomeItemsWithEbitda`): l'EBITDA non è una voce di
 *   bilancio, e senza quella riga le card che lo usano non hanno una fonte.
 */
export function buildConfrontoHighlights(
  comparison: Pick<IntraYearComparison, "period_months" | "has_reference">,
  items: IntraYearComparisonItem[],
): Highlight[] {
  const byCode = new Map(items.map((i) => [i.code, i]));
  const expectedPct = (comparison.period_months / 12) * 100;

  const ricavi = byCode.get(RICAVI_CODE);

  const flussi: Highlight[] = [];
  for (const def of HIGHLIGHT_FLOW_DEFS) {
    const item = byCode.get(def.code);
    if (!item) continue;
    const { benchmarkPct, benchmarkLabel, better } = verdettoFlusso(
      item,
      def,
      expectedPct,
      ricavi,
      comparison.has_reference,
    );
    flussi.push({
      kind: "flusso",
      code: def.code,
      label: item.label,
      value: item.partial_value,
      pctOfReference: item.pct_of_reference,
      expectedPct,
      benchmarkPct,
      benchmarkLabel,
      annualized: item.annualized_value,
      better,
    });
  }

  const rapporti: Highlight[] = HIGHLIGHT_RATIO_DEFS.map((def) => {
    const num = byCode.get(def.numerator);
    const den = byCode.get(def.denominator);
    const value =
      num && den ? ratio(num.partial_value, den.partial_value) : null;
    const reference =
      comparison.has_reference && num && den
        ? ratio(num.reference_value, den.reference_value)
        : null;
    const deltaPp = value !== null && reference !== null ? value - reference : null;
    return {
      kind: "rapporto" as const,
      key: def.key,
      label: def.label,
      value,
      reference,
      deltaPp,
      // `deltaPp === 0` cade nel ramo `null`: invariato non è un verdetto.
      improved:
        deltaPp === null || deltaPp === 0
          ? null
          : def.lowerIsBetter
            ? deltaPp < 0
            : deltaPp > 0,
    };
  });

  // Cinque di flusso poi tre di rapporto: due righe da quattro. Una riga da
  // otto rende ogni card illeggibile sotto i 1400px, e in stampa va fuori
  // misura.
  return [...flussi, ...rapporti];
}
