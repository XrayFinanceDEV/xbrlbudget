/**
 * Formattazione condivisa della slice A del report finale (copertina/perimetro,
 * fonti, rettifiche, chiusura infrannuale).
 *
 * È solo presentazione: nessun calcolo, nessun hook, nessuna chiamata API.
 * Gli importi arrivano dal `FinalReportModel` come `DecimalString` e vengono
 * mostrati così come sono: l'unico lavoro qui è il separatore italiano, il
 * simbolo e il segno.
 *
 * Convenzioni (design §§6, 8):
 * - un valore mancante (`null`/`undefined`) è sempre `—` (MISSING_VALUE), mai
 *   `0,00`: assenza e zero non si confondono;
 * - un valore non parsabile viene sputato fuori tal quale: nasconderlo dietro
 *   un trattino sarebbe una bugia più grande di un formato storto;
 * - le etichette di stato non sono mai affidate solo al colore: chi le rende
 *   aggiunge sempre icona e testo.
 */

import type {
  DecimalString,
  DiagnosticSeverity,
  Readiness,
  SourceDataQuality,
  SourceRevision,
  WorkflowType,
} from "@/types/final-report";

/** Il trattino lungo è «non presente», e vale solo per l'assenza. */
export const MISSING_VALUE = "—";

const euros = new Intl.NumberFormat("it-IT", {
  style: "currency",
  currency: "EUR",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
  // `useGrouping: true`, non l'`"auto"` di default: l'auto di CLDR non separa
  // le migliaia sotto le 5 cifre (1200 esce «1200,00 €»), e in un documento
  // contabile una cifra tonda e una millesimata devono somigliarsi.
  useGrouping: true,
});

const numbers = new Intl.NumberFormat("it-IT", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
  useGrouping: true,
});

function toNumber(value: DecimalString | null | undefined): number | null {
  if (value === null || value === undefined) return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

/**
 * Euro con formattazione italiana (`1.234.567,89 €`). Non converte nulla:
 * formatta la stringa decimale del modello, al centesimo com'è persistita.
 */
export function formatEuro(value: DecimalString | null | undefined): string {
  const n = toNumber(value);
  if (n === null) return value === null || value === undefined ? MISSING_VALUE : String(value);
  return euros.format(n);
}

/**
 * Delta di rettifica con segno contabile esplicito: `+` sul positivo, `-` su
 * quello che Intl porta già negativo, `0,00` senza segno sullo zero, `—`
 * sull'assenza. Il segno è nel testo, non nel colore della cella.
 */
export function formatSignedEuro(value: DecimalString | null | undefined): string {
  const n = toNumber(value);
  if (n === null) return value === null || value === undefined ? MISSING_VALUE : String(value);
  if (n > 0) return `+${euros.format(n)}`;
  return euros.format(n);
}

/** Numero puro (giorni, indici) senza simbolo di valuta. */
export function formatNumber(value: DecimalString | null | undefined): string {
  const n = toNumber(value);
  if (n === null) return value === null || value === undefined ? MISSING_VALUE : String(value);
  return numbers.format(n);
}

const DATE_RE = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?/;

/**
 * `2026-09-30` → `30/09/2026`. Spezza la stringa ISO senza costruirci un
 * `Date`: un fuso orario applicato a una data secca sposterebbe il giorno.
 * Una stringa che non somiglia a una data esce com'è entrata (onesta).
 */
export function formatDateItalian(value: string | null | undefined): string {
  if (value === null || value === undefined) return MISSING_VALUE;
  const m = DATE_RE.exec(value);
  if (!m) return value;
  return `${m[3]}/${m[2]}/${m[1]}`;
}

/**
 * `2026-09-01T08:00:00Z` → `01/09/2026 08:00Z`. Il suffisso del fuso resta
 * quello dichiarato dall'ISO: tradurre l'ora nel fuso locale ri-daterebbe in
 * silenzio un marchio di audit.
 */
export function formatDateTimeItalian(value: string | null | undefined): string {
  if (value === null || value === undefined) return MISSING_VALUE;
  const m = DATE_RE.exec(value);
  if (!m || m[4] === undefined) return formatDateItalian(value);
  const tz = /(?:Z|[+-]\d{2}:\d{2})$/.exec(value)?.[0] ?? "";
  return `${m[3]}/${m[2]}/${m[1]} ${m[4]}:${m[5]}${tz}`;
}

export const WORKFLOW_LABELS: Record<WorkflowType, string> = {
  infrannuale: "Percorso infrannuale",
  bilancio: "Percorso da bilancio",
  startup: "Percorso startup",
};

export const SOURCE_LABELS: Record<SourceRevision["source"], string> = {
  historical_financial_year: "Bilancio storico",
  adjustments: "Log rettifiche",
  source_scenario: "Scenario sorgente infrannuale",
  budget_assumptions: "Ipotesi budget",
  forecast: "Previsionale persistita",
  narrative: "Commenti",
  calculation_engine: "Motore di calcolo",
};

export const READINESS_LABELS: Record<Readiness["status"], string> = {
  ready: "Definitivo",
  draft: "Bozza",
  blocked: "Bloccato",
};

export const QUALITY_LABELS: Record<SourceDataQuality["status"], string> = {
  complete: "Completo",
  partial: "Parziale",
  legacy: "Dati legacy",
};

export const SEVERITY_LABELS: Record<DiagnosticSeverity, string> = {
  info: "Notizia",
  warning: "Avviso",
  error: "Errore",
};

/** Etichetta onesta dei mesi di periodo: `null`/`12` sono entrambi anno pieno. */
export function periodMonthsLabel(months: number | null | undefined): string {
  if (months === null || months === undefined || months === 12) return "Anno pieno (12 mesi)";
  return `${months} mesi su 12`;
}
