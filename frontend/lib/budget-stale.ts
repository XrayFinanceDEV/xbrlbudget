/**
 * Il previsionale a schermo e' piu' vecchio delle ipotesi salvate?
 *
 * `PUT /scenarios/{id}/assumptions` risponde **200 con `success: true`** anche
 * quando la generazione viene respinta (CLAUDE.md › «Invarianti e trappole ›
 * Previsionale»): le ipotesi restano salvate, il `ForecastYear` no, e le viste
 * che leggono `/analysis` continuano a mostrare i numeri della generazione
 * PRECEDENTE senza un segnale. Lo stesso vale, per costruzione, quando si
 * salva con `auto_generate=false`.
 *
 * La decisione sta qui, in un modulo puro con la sua suite in
 * `environment: node`, e il componente rende soltanto: `jsdom` non e'
 * installato, e un banner che decide dentro il JSX non sarebbe provabile.
 *
 * Il verdetto lo produce il backend confrontando due `updated_at`; qui lo si
 * ricalcola dagli stessi due timestamp invece di leggere `forecast_stale`
 * perche' la vista deve reggere anche una risposta che quei campi non li
 * porta: un backend che tace non deve poter dichiarare «stantio», ne'
 * costringere la vista a fidarsi di una bandiera che non puo' verificare.
 */
import type { ScenarioAnalysis } from "@/types/api";

export interface ForecastStaleFacts {
  /** `assumptions_updated_at` di `/analysis`, ISO. */
  assumptionsUpdatedAt: string | null | undefined;
  /** `forecast_updated_at` di `/analysis`, ISO. */
  forecastUpdatedAt: string | null | undefined;
  /** Quanti anni di previsionale la vista sta per rendere. */
  forecastYearsCount: number;
}

/** ISO → millisecondi, oppure `null` se non c'e' un istante da leggere.
 *
 *  Il ramo `NaN` e' una normalizzazione, non una decisione: un confronto con
 *  `NaN` e' gia' `false` in ogni verso, quindi toglierlo non cambia il
 *  verdetto e nessun test puo' ucciderlo (verificato per mutazione). Resta
 *  perche' fa passare dal solo guardiano esplicito — `=== null` — anche il
 *  caso illeggibile, invece di appoggiarsi alla semantica di `NaN`. */
function instante(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  return Number.isNaN(t) ? null : t;
}

/**
 * `true` solo su una contraddizione misurata: ci sono anni di previsionale,
 * entrambi i timestamp sono leggibili, e le ipotesi sono **piu' recenti**.
 *
 * Le due astensioni sono deliberate:
 *
 * - **Nessun anno di previsionale ⇒ `false`**: non c'e' niente di stantio da
 *   mostrare, la vista e' vuota e il vuoto si vede da solo.
 * - **Un timestamp mancante o illeggibile ⇒ `false`**: un verdetto negativo
 *   vuole una contraddizione, non un controllo assente.
 *
 * Il confronto e' **stretto**: la parita' e' «allineato». I due timestamp
 * nascono da `datetime.utcnow()` e la generazione scrive dopo le ipotesi,
 * quindi un pareggio e' un caso di misura, non di disallineamento.
 */
export function isForecastStale(facts: ForecastStaleFacts): boolean {
  if (!(facts.forecastYearsCount > 0)) return false;
  const ipotesi = instante(facts.assumptionsUpdatedAt);
  const previsionale = instante(facts.forecastUpdatedAt);
  if (ipotesi === null || previsionale === null) return false;
  return ipotesi > previsionale;
}

/** Lo stesso verdetto, letto direttamente dalla risposta di `/analysis`. */
export function forecastStaleFromAnalysis(
  analysis: ScenarioAnalysis | null | undefined,
): boolean {
  if (!analysis) return false;
  return isForecastStale({
    assumptionsUpdatedAt: analysis.assumptions_updated_at,
    forecastUpdatedAt: analysis.forecast_updated_at,
    forecastYearsCount: analysis.forecast_years?.length ?? 0,
  });
}
