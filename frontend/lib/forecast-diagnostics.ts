import type { ForecastDiagnostic } from "@/types/api";

export function hasDiagnosticErrors(diagnostics: ForecastDiagnostic[]): boolean {
  return diagnostics.some((diagnostic) => diagnostic.severity === "error");
}

/**
 * L'identità dell'elenco di verifiche mostrato. La card si può chiudere, e la
 * chiusura vale per QUESTE verifiche: una proiezione nuova che ne porta altre
 * (o le stesse con importi diversi) torna a mostrarsi da sola. Una chiusura che
 * sopravvive a un ricalcolo nasconderebbe un avviso che l'utente non ha mai
 * letto — e su questa card passano anche le criticità bloccanti.
 */
export function diagnosticsSignature(diagnostics: ForecastDiagnostic[]): string {
  return JSON.stringify(diagnostics.map((d) => [d.code, d.message]));
}

/** «1 verifica» / «3 verifiche»: il numero si legge anche a card chiusa. */
export function diagnosticsLabel(diagnostics: ForecastDiagnostic[]): string {
  const n = diagnostics.length;
  return n === 1 ? "1 verifica richiesta" : `${n} verifiche richieste`;
}

export function diagnosticAmount(diagnostic: ForecastDiagnostic): string | null {
  if (diagnostic.amount === undefined || diagnostic.amount === null) return null;
  const amount = Number(diagnostic.amount);
  if (!Number.isFinite(amount)) return String(diagnostic.amount);
  return new Intl.NumberFormat("it-IT", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount);
}
