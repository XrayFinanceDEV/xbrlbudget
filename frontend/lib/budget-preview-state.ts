import type { ForecastPreviewResponse } from "@/types/api";

/**
 * Stato dell'anteprima del previsionale. Dichiarazione UNICA: chi la
 * consumava da `components/budget/wizard/types.ts` la trova li'
 * ri-esportata (`export type { PreviewState } from "@/lib/budget-preview-state"`),
 * mai duplicata. `lib/` non importa da `components/`, quindi la
 * dichiarazione vive qui e sale.
 */
export interface PreviewState {
  data: ForecastPreviewResponse | null;
  error: string | null;
  loading: boolean;
}

/**
 * Transizione pura all'arrivo di una risposta dal server (sempre un 200:
 * `previewForecast` non risolve mai su un 400, che axios rigetta come
 * eccezione). Porta `data` INTERA — `forecast_years` E l'eventuale `error`
 * annidato — cosi' come arriva dal backend: una 200 con `error` valorizzato
 * (il motore si e' fermato a un certo anno, ma i precedenti sono validi —
 * es. fabbisogno finanziario scoperto) NON e' un guasto e non deve MAI
 * svuotare `data`. L'errore di TRASPORTO (`PreviewState.error`) e' un
 * canale separato e qui si azzera sempre.
 */
export function previewStateFromResponse(data: ForecastPreviewResponse): PreviewState {
  return { data, error: null, loading: false };
}

/**
 * Transizione pura all'arrivo di un guasto di TRASPORTO (400 vero, rete,
 * richiesta caduta — non una 200 col campo `error` valorizzato, che passa
 * da `previewStateFromResponse`). Conserva `data` precedente — l'ultima
 * anteprima valida resta a schermo — e accende `error` col messaggio gia'
 * risolto dal chiamante.
 *
 * Il messaggio arriva gia' pronto: risolverlo (`getErrorMessage`) e decidere
 * se un annullamento e' un errore da mostrare dipendono da `axios`, quindi
 * restano nell'hook — questo modulo importa solo da `@/types/api`.
 */
export function previewStateFromError(prev: PreviewState, message: string): PreviewState {
  return { ...prev, error: message, loading: false };
}
