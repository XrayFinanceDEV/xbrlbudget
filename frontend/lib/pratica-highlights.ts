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
  /** La frazione d'anno trascorsa, in %: il termine di paragone. */
  expectedPct: number;
  annualized: number;
  /** `null` senza anno di riferimento: nessun paragone, nessuna freccia. */
  ahead: boolean | null;
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
   * `null` quando non c'è riferimento, o un denominatore è zero.
   */
  improved: boolean | null;
};

export type Highlight = HighlightFlusso | HighlightRapporto;

/** Le quattro card di flusso storiche, nell'ordine in cui erano scritte a mano. */
export const HIGHLIGHT_FLOW_CODES = [
  "ce01_ricavi_vendite",
  "ce08_costi_personale",
  "ce05_materie_prime",
  "ce06_servizi",
] as const;

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

  const flussi: Highlight[] = [];
  for (const code of [...HIGHLIGHT_FLOW_CODES, "_ebitda"]) {
    const item = byCode.get(code);
    if (!item) continue;
    flussi.push({
      kind: "flusso",
      code,
      label: item.label,
      value: item.partial_value,
      pctOfReference: item.pct_of_reference,
      expectedPct,
      annualized: item.annualized_value,
      ahead: comparison.has_reference ? item.pct_of_reference > expectedPct : null,
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
      improved:
        deltaPp === null
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
