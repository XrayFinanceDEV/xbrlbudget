/**
 * Rapporti di rotazione del capitale circolante per la proiezione infrannuale.
 *
 * Gemello di `_turnover_ratio` in `calculations/intra_year_engine.py`: le due
 * formule DEVONO restare d'accordo, perché la Proiezione mostra il calcolo del
 * frontend mentre il promote a budget valida quello persistito dal backend.
 * Quando divergevano si otteneva la situazione peggiore possibile — a schermo
 * il bilancio "quadrava" (il plug di cassa scaricava lo sbilancio sui debiti a
 * breve) e il promote lo rifiutava, senza che nulla spiegasse la differenza.
 */

/** Oltre un anno di giacenza il rapporto descrive il denominatore, non l'azienda. */
export const MAX_TURNOVER_RATIO = 1; // 365 giorni

/**
 * Rapporto giacenza/base dell'anno di riferimento, oppure `null` quando è
 * DEGENERE: il denominatore è troppo piccolo per spiegare la giacenza.
 *
 * Il caso reale: AIC SRL fattura su `ce04_altri_ricavi` e porta
 * `ce01_ricavi_vendite` = 100,92 € contro 1.035.249,26 € di crediti. Il
 * rapporto vale 10.258x — 3,7 milioni di giorni — e i crediti proiettati
 * diventavano 166,68 M su un attivo reale di 1,5 M.
 */
export function turnoverRatio(stock: number, base: number): number | null {
  if (!Number.isFinite(stock) || !Number.isFinite(base)) return null;
  if (base <= 0) return null;
  const ratio = stock / base;
  if (ratio > MAX_TURNOVER_RATIO) return null;
  return ratio;
}

/**
 * Scala la giacenza col rapporto di riferimento; se il rapporto è degenere
 * riporta la giacenza infrannuale OSSERVATA invece di moltiplicare.
 * Misurare, mai fabbricare.
 */
export function scaledOrCarried(
  refStock: number,
  refBase: number,
  projectedBase: number,
  partialStock: number,
): number {
  const ratio = turnoverRatio(refStock, refBase);
  return ratio === null ? partialStock : projectedBase * ratio;
}
