"use client";

import { useCallback, useRef, useState } from "react";
import { toast } from "sonner";
import { downloadFinalReportPdf } from "@/lib/api";
import {
  FinalReportDownloadError,
  PREVIEW_BLOCKED_MESSAGE,
  closePreviewTabOnError,
  createDownloadGuardState,
  nextInlinePreviewUrl,
  isRetryableDownloadStatus,
  saveBlobAsFile,
  showPdfPreview,
  withDownloadGuard,
  type FinalReportDocumentState,
  type FinalReportDownloadSink,
  type FinalReportPreviewSink,
  type FinalReportPreviewTab,
  type ReportModel,
} from "@/lib/final-report-download";
import { getErrorMessage } from "@/lib/utils";

/** Sink DOM vero, usato solo qui: la logica testabile resta in `lib/final-report-download.ts`. */
const browserSink: FinalReportDownloadSink = {
  createObjectURL: (blob) => URL.createObjectURL(blob),
  revokeObjectURL: (url) => URL.revokeObjectURL(url),
  triggerAnchorDownload: (url, filename) => {
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
  },
};

/**
 * `scheduleRevoke` è una funzione libera che chiama `setTimeout` come
 * identificatore globale al suo interno — mai `obj.setTimeout(...)`, che
 * lancerebbe «Illegal invocation» nel browser (trappola nota del progetto).
 */
const previewSink: FinalReportPreviewSink = {
  ...browserSink,
  scheduleRevoke: (callback, delayMs) => {
    setTimeout(callback, delayMs);
  },
};

type DownloadOutcome = { ok: true } | { ok: false; error: unknown; status: number | null };

/**
 * Scarica il PDF finale del report (M2-06A): richiesta autenticata via
 * `lib/api.ts`, salvataggio via blob/URL temporaneo, un solo toast d'errore
 * con «Riprova» su 503/504. Il doppio click è protetto da
 * `withDownloadGuard` — un secondo click mentre la richiesta è in volo è un
 * no-op silenzioso, non una seconda `fetch`.
 */
export function useFinalReportDownload() {
  const [downloading, setDownloading] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  // Anteprima mostrata DENTRO la pagina `/report`: l'URL oggetto del PDF
  // corrente, che sostituisce la resa web del dossier come vista principale.
  const [inlineUrl, setInlineUrl] = useState<string | null>(null);
  // Stesso guard per download e anteprima: le due richieste PDF non devono
  // poter partire insieme (regola del brief M2-06A/anteprima-pdf).
  const guardRef = useRef(createDownloadGuardState());

  const download = useCallback(
    async (
      companyId: number,
      scenarioId: number,
      documentState: FinalReportDocumentState,
      model: ReportModel = "dossier",
    ) => {
      const outcome = await withDownloadGuard<DownloadOutcome>(guardRef.current, async () => {
        setDownloading(true);
        try {
          const { blob, filename } = await downloadFinalReportPdf(companyId, scenarioId, { documentState, model });
          saveBlobAsFile(blob, filename, browserSink);
          return { ok: true };
        } catch (error) {
          const status = error instanceof FinalReportDownloadError ? error.status : null;
          return { ok: false, error, status };
        } finally {
          setDownloading(false);
        }
      });

      if (outcome === null || outcome.ok) return;

      const message = getErrorMessage(outcome.error, "Impossibile scaricare il PDF del report");
      const retryable = outcome.status !== null && isRetryableDownloadStatus(outcome.status);
      toast.error(
        message,
        retryable
          ? { action: { label: "Riprova", onClick: () => download(companyId, scenarioId, documentState, model) } }
          : undefined
      );
    },
    []
  );

  /**
   * Apre il PDF in una nuova scheda invece di scaricarlo («Anteprima PDF»).
   * La scheda va aperta in modo **sincrono nel click**, prima del `fetch`
   * asincrono, o il popup blocker la intercetta.
   */
  const preview = useCallback(
    async (
      companyId: number,
      scenarioId: number,
      documentState: FinalReportDocumentState,
      model: ReportModel = "dossier",
    ) => {
      const rawTab = typeof window !== "undefined" ? window.open("", "_blank") : null;
      const tab: FinalReportPreviewTab | null = rawTab
        ? {
            navigate: (url) => {
              rawTab.location.href = url;
            },
            close: () => rawTab.close(),
          }
        : null;

      const outcome = await withDownloadGuard<DownloadOutcome>(guardRef.current, async () => {
        setPreviewing(true);
        try {
          const { blob, filename } = await downloadFinalReportPdf(companyId, scenarioId, { documentState, model });
          const result = showPdfPreview(tab, blob, filename, previewSink);
          if (!result.opened) {
            toast.info(PREVIEW_BLOCKED_MESSAGE);
          }
          return { ok: true };
        } catch (error) {
          closePreviewTabOnError(tab);
          const status = error instanceof FinalReportDownloadError ? error.status : null;
          return { ok: false, error, status };
        } finally {
          setPreviewing(false);
        }
      });

      if (outcome === null) {
        // Guard occupato (download/anteprima già in volo): la scheda
        // preaperta non serve, va chiusa per non restare vuota.
        closePreviewTabOnError(tab);
        return;
      }
      if (outcome.ok) return;

      const message = getErrorMessage(outcome.error, "Impossibile preparare l'anteprima del PDF");
      const retryable = outcome.status !== null && isRetryableDownloadStatus(outcome.status);
      toast.error(
        message,
        retryable
          ? { action: { label: "Riprova", onClick: () => preview(companyId, scenarioId, documentState, model) } }
          : undefined
      );
    },
    []
  );

  /**
   * Carica il PDF e lo tiene come URL oggetto da mostrare in pagina
   * (`<iframe>`) invece di aprirlo in una scheda: nessuna finestra da
   * preaprire, quindi nessun popup blocker da assecondare. Lo stesso guard
   * del download e dell'anteprima in scheda: una sola richiesta PDF per volta.
   */
  const loadInline = useCallback(
    async (
      companyId: number,
      scenarioId: number,
      documentState: FinalReportDocumentState,
      model: ReportModel = "dossier",
    ) => {
      const outcome = await withDownloadGuard<DownloadOutcome>(guardRef.current, async () => {
        setPreviewing(true);
        try {
          const { blob } = await downloadFinalReportPdf(companyId, scenarioId, { documentState, model });
          setInlineUrl((previous) => nextInlinePreviewUrl(previous, blob, previewSink));
          return { ok: true };
        } catch (error) {
          const status = error instanceof FinalReportDownloadError ? error.status : null;
          return { ok: false, error, status };
        } finally {
          setPreviewing(false);
        }
      });

      if (outcome === null || outcome.ok) return;
      const message = getErrorMessage(outcome.error, "Impossibile preparare l'anteprima del PDF");
      const retryable = outcome.status !== null && isRetryableDownloadStatus(outcome.status);
      toast.error(
        message,
        retryable
          ? { action: { label: "Riprova", onClick: () => loadInline(companyId, scenarioId, documentState, model) } }
          : undefined
      );
    },
    []
  );

  const clearInline = useCallback(() => {
    setInlineUrl((previous) => nextInlinePreviewUrl(previous, null, previewSink));
  }, []);

  return { download, downloading, preview, previewing, loadInline, clearInline, inlineUrl };
}
