/**
 * Modulo puro per il download del PDF finale del report (M2-06A).
 *
 * Regola CLAUDE.md «Frontend»: `lib/` non importa mai da `app/` o da
 * `components/`. Tutto ciò che si può testare in `environment: node` vive
 * qui — nome file dagli header, mappa dei messaggi d'errore per stato HTTP,
 * guardia contro il doppio click. Il `fetch` vero e la manipolazione del DOM
 * (`URL.createObjectURL`, l'`<a download>`) restano nell'hook React
 * (`hooks/use-final-report-download.ts`), che è solo un innesto sottile e
 * usa il sink iniettato qui sotto per restare testabile senza DOM.
 */

export type FinalReportDocumentState = "draft" | "final";

const FALLBACK_FILENAME = "Report Budget.pdf";

/**
 * Estrae il nome file da `Content-Disposition`, preferendo `filename*`
 * (RFC 5987/6266, `UTF-8''<percent-encoded>`) su `filename` ASCII. Senza
 * header, senza nessuno dei due token, o con una codifica percent non
 * valida, ricade sul nome di default.
 */
export function resolveDownloadFilename(contentDisposition?: string | null): string {
  if (!contentDisposition) return FALLBACK_FILENAME;

  const starMatch = /filename\*\s*=\s*([^;]+)/i.exec(contentDisposition);
  if (starMatch) {
    const raw = starMatch[1].trim().replace(/^"+|"+$/g, "");
    const separatorIndex = raw.indexOf("''");
    if (separatorIndex !== -1) {
      const encoded = raw.slice(separatorIndex + 2).trim();
      if (encoded) {
        try {
          const decoded = decodeURIComponent(encoded);
          if (decoded) return decoded;
        } catch {
          // Percent-encoding non valido: si prova col token ASCII sotto.
        }
      }
    }
  }

  const plainMatch = /filename\s*=\s*"?([^";]+)"?/i.exec(contentDisposition);
  if (plainMatch) {
    const value = plainMatch[1].trim();
    if (value) return value;
  }

  return FALLBACK_FILENAME;
}

/** Messaggi di ripiego per stato HTTP, usati solo quando il server non manda un `detail`. */
export const FINAL_REPORT_DOWNLOAD_ERROR_MESSAGES: Record<number, string> = {
  404: "Azienda o scenario non trovato.",
  409: "Il documento non è pronto per il download: prepara il piano editoriale o attendi che il report sia pronto.",
  422: "Il report non si impagina: correggi i contenuti e riprova.",
  503: "Il servizio di generazione del PDF non è disponibile in questo momento.",
  504: "La generazione del PDF ha impiegato troppo tempo.",
  500: "Errore interno durante la generazione del PDF.",
};

/**
 * Il messaggio da mostrare in toast: il `detail` del server quando c'è
 * (è già in italiano, per contratto — vedi M2-05), altrimenti la mappa per
 * stato qui sopra, altrimenti il messaggio generico del 500.
 */
export function resolveDownloadErrorMessage(status: number, detail?: string | null): string {
  const trimmed = typeof detail === "string" ? detail.trim() : "";
  if (trimmed) return trimmed;
  return FINAL_REPORT_DOWNLOAD_ERROR_MESSAGES[status] ?? FINAL_REPORT_DOWNLOAD_ERROR_MESSAGES[500];
}

/** 503 (renderer occupato/non disponibile) e 504 (timeout) meritano un «Riprova». */
export function isRetryableDownloadStatus(status: number): boolean {
  return status === 503 || status === 504;
}

/** Errore tipizzato lanciato da `downloadFinalReportPdf` (`lib/api.ts`). */
export class FinalReportDownloadError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "FinalReportDownloadError";
    this.status = status;
  }
}

/** Operazioni DOM iniettate, per restare testabili in `environment: node`. */
export interface FinalReportDownloadSink {
  createObjectURL: (blob: Blob) => string;
  revokeObjectURL: (url: string) => void;
  triggerAnchorDownload: (url: string, filename: string) => void;
}

/** Salva un blob come file scaricato tramite il sink iniettato. */
export function saveBlobAsFile(blob: Blob, filename: string, sink: FinalReportDownloadSink): void {
  const url = sink.createObjectURL(blob);
  try {
    sink.triggerAnchorDownload(url, filename);
  } finally {
    sink.revokeObjectURL(url);
  }
}

/** Stato mutabile minimo della guardia anti-doppio-click. */
export interface DownloadGuardState {
  pending: boolean;
}

export function createDownloadGuardState(): DownloadGuardState {
  return { pending: false };
}

/**
 * Esegue `task` solo se nessun'altra chiamata è già in volo su questo
 * `guard`; una seconda chiamata ravvicinata è un no-op che risolve `null`
 * invece di partire una seconda richiesta.
 */
export async function withDownloadGuard<T>(
  guard: DownloadGuardState,
  task: () => Promise<T>
): Promise<T | null> {
  if (guard.pending) return null;
  guard.pending = true;
  try {
    return await task();
  } finally {
    guard.pending = false;
  }
}

/**
 * Anteprima PDF (sostituisce «Anteprima stampa» / `window.print()` su
 * `/report`): il PDF si apre in una nuova scheda invece di scaricarsi.
 */

/** Scheda del browser preaperta, astratta per restare testabile senza DOM reale. */
export interface FinalReportPreviewTab {
  navigate: (url: string) => void;
  close: () => void;
}

/**
 * Il sink del download più `scheduleRevoke`, iniettato per pianificare la
 * revoca ritardata dell'object URL. **Non** avvolgere `setTimeout` come
 * metodo di un oggetto e chiamarlo così (`sink.setTimeout(...)`): nel
 * browser lancia «Illegal invocation» perché perde il ricevitore atteso, ed
 * `environment: node` non lo vede (trappola nota del progetto). Il valore
 * iniettato qui deve essere una funzione libera che al suo interno chiama
 * `setTimeout` come identificatore globale, non come proprietà di un
 * oggetto.
 */
export interface FinalReportPreviewSink extends FinalReportDownloadSink {
  scheduleRevoke: (callback: () => void, delayMs: number) => void;
}

/** Ritardo, in ms, prima di revocare l'object URL della scheda di anteprima. */
export const PREVIEW_REVOKE_DELAY_MS = 60_000;

/** Toast informativo mostrato quando il popup blocker impedisce l'apertura della scheda. */
export const PREVIEW_BLOCKED_MESSAGE =
  "Il browser ha bloccato l'apertura della scheda: il PDF è stato scaricato.";

export type PreviewOutcome = { opened: true } | { opened: false; fallbackToDownload: true };

/**
 * Mostra il PDF nella scheda preaperta (`tab`, creata in modo sincrono nel
 * click con `window.open("", "_blank")` prima del `fetch`, per non farsi
 * bloccare dal popup blocker). Se `tab` è `null` — popup bloccato — ripiega
 * sul download dello stesso blob. L'object URL viene revocato dopo
 * `revokeDelayMs`, mai subito, o la scheda resta vuota.
 */
export function showPdfPreview(
  tab: FinalReportPreviewTab | null,
  blob: Blob,
  filename: string,
  sink: FinalReportPreviewSink,
  revokeDelayMs: number = PREVIEW_REVOKE_DELAY_MS
): PreviewOutcome {
  if (!tab) {
    saveBlobAsFile(blob, filename, sink);
    return { opened: false, fallbackToDownload: true };
  }

  const url = sink.createObjectURL(blob);
  tab.navigate(url);
  sink.scheduleRevoke(() => sink.revokeObjectURL(url), revokeDelayMs);
  return { opened: true };
}

/** Chiude la scheda preaperta su errore: non deve restarne una vuota aperta. */
export function closePreviewTabOnError(tab: FinalReportPreviewTab | null): void {
  tab?.close();
}

/**
 * Anteprima INLINE: l'URL oggetto del PDF mostrato dentro la pagina
 * `/report`, al posto della vista web del dossier.
 *
 * Un URL oggetto resta allocato finché non lo si revoca: sostituirlo senza
 * revocare il precedente lascia in memoria un PDF intero a ogni rigenerazione.
 * Qui la sostituzione è una funzione sola — revoca il vecchio, crea il nuovo
 * (o `null` per chiudere l'anteprima) — così il componente non deve
 * ricordarsene a ogni chiamata. `revokeObjectURL` che fallisce (URL già
 * revocato, ambiente senza supporto) non impedisce la creazione del nuovo:
 * un'anteprima che non si apre sarebbe un danno peggiore di un URL non
 * liberato.
 */
export function nextInlinePreviewUrl(
  previous: string | null,
  blob: Blob | null,
  sink: FinalReportDownloadSink
): string | null {
  if (previous) {
    try {
      sink.revokeObjectURL(previous);
    } catch {
      // niente: vedi il commento sopra.
    }
  }
  return blob ? sink.createObjectURL(blob) : null;
}

/** Quale PDF si stampa da /report: il Business plan (ReportLab) o il dossier (Typst). */
export type ReportModel = "dossier" | "business_plan";

export const REPORT_MODELS: { value: ReportModel; label: string }[] = [
  { value: "business_plan", label: "Business plan" },
  // Il dossier Typst è staccato da /report (2026-09-24): rotte e codice restano, e tornerà come prodotto più
  // avanzato. Rimetterlo qui riaccende il selettore «Modello», che compare solo con più di un modello.
];

export function reportPdfPath(model: ReportModel): string {
  return model === "business_plan" ? "business-plan/pdf" : "final-report/pdf";
}

/** Il Word esiste solo per il Business plan: il dossier Typst resta PDF (spec 2026-09-24). */
export function wordAvailable(model: ReportModel): boolean {
  return model === "business_plan";
}
