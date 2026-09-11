/**
 * Le righe da mostrare quando il bulk delle ipotesi risponde 422 (lotto 3A, Task 7b).
 *
 * `PUT /scenarios/{id}/assumptions` valida ogni riga PRIMA di scrivere (Task 7a) e, se qualcosa non va, risponde
 * 422 con `detail.errori`: un elenco `{forecast_year, campo, messaggio}` gia' in italiano. Un 422 senza quell'elenco
 * (la validazione di FastAPI sul corpo) non e' nostro e torna `null`: il chiamante ricade su `getErrorMessage`.
 * Modulo puro: nessun import da `app/` o `components/`.
 */
export interface ErroreCampoIpotesi {
  forecast_year: number | null;
  campo: string;
  messaggio: string;
}

function eErroreCampo(voce: unknown): voce is ErroreCampoIpotesi {
  return !!voce && typeof voce === "object"
    && typeof (voce as ErroreCampoIpotesi).campo === "string"
    && typeof (voce as ErroreCampoIpotesi).messaggio === "string";
}

export function righeErroriIpotesi(error: unknown): string[] | null {
  const risposta = (error as { response?: { status?: number; data?: { detail?: unknown } } } | undefined)?.response;
  if (!risposta || risposta.status !== 422) return null;
  const detail = risposta.data?.detail as { errori?: unknown } | undefined;
  if (!detail || !Array.isArray(detail.errori)) return null;
  const righe = detail.errori.filter(eErroreCampo).map((e) =>
    typeof e.forecast_year === "number" ? `${e.forecast_year} · ${e.campo}: ${e.messaggio}` : `${e.campo}: ${e.messaggio}`);
  return righe.length > 0 ? righe : null;
}
