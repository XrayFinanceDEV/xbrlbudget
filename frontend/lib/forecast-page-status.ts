/**
 * CE Prev., SP Prev. e Report leggono tutte `useAnalysis` (`hooks/use-queries.ts`) e
 * restavano su "Caricamento..." senza alcun segnale quando `/analysis` falliva: il
 * `detail` del backend veniva scartato in favore di una stringa fissa, e non c'era modo
 * di ritentare se non un refresh completo della pagina (rilievo 3 del collaudo del lotto
 * 2, `.superpowers/sdd/2026-09-08-scadenziamento-pregresso/task-10-report-parte1.md`
 * righe 354-377).
 *
 * Le tre pagine derivano il proprio stato da qui, e rendono l'errore con
 * `components/budget/ForecastLoadError.tsx`: nessuna delle due decide da sola. Come
 * `lib/budget-stale.ts`, questo modulo resta puro e testabile in `environment: node` —
 * jsdom non e' installato in questo progetto, quindi il componente non ha una sua suite,
 * solo questa.
 */
import { getErrorMessage } from "@/lib/utils";

export type ForecastPageStatus = "caricamento" | "errore" | "pronto";

/**
 * Tentativi e attesa espliciti per `useAnalysis`: prima erano solo il default globale
 * di `components/providers.tsx` (mai testato per questa query in particolare), e un
 * cambiamento futuro di quel default avrebbe allungato la finestra di caricamento
 * apparente senza che nessuna suite se ne accorgesse.
 */
export const ANALYSIS_RETRY_COUNT = 1;
export const ANALYSIS_RETRY_DELAY_MS = 1000;

export function forecastPageStatus(loading: boolean, error: unknown): ForecastPageStatus {
  if (loading) return "caricamento";
  if (error) return "errore";
  return "pronto";
}

/**
 * Il messaggio da mostrare per un errore di caricamento previsionale.
 *
 * Un errore Axios con `.response` e' arrivato dal server: il `detail` vince
 * (`getErrorMessage`). Senza `.response` non c'e' stato alcun corpo da leggere — rete
 * giu', timeout, o (prima del Task 1 di questo lotto) un 500 che il browser bloccava
 * come CORS: in quel caso `error.message` sarebbe la stringa inglese di axios ("Network
 * Error"), quindi si usa un testo italiano fisso invece di propagarla.
 */
export function forecastLoadErrorMessage(error: unknown): string {
  const hasResponse =
    typeof error === "object" &&
    error !== null &&
    "response" in error &&
    (error as { response?: unknown }).response != null;
  if (!hasResponse) {
    return "Il server non ha risposto. Controlla la connessione e riprova.";
  }
  return getErrorMessage(error, "Impossibile caricare i dati previsionali.");
}
