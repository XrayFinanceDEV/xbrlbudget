"use client";

import { useCallback, useRef, useState } from "react";
import { toast } from "sonner";
import { downloadFinalReportPdf } from "@/lib/api";
import {
  FinalReportDownloadError,
  createDownloadGuardState,
  isRetryableDownloadStatus,
  saveBlobAsFile,
  withDownloadGuard,
  type FinalReportDocumentState,
  type FinalReportDownloadSink,
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
  const guardRef = useRef(createDownloadGuardState());

  const download = useCallback(
    async (companyId: number, scenarioId: number, documentState: FinalReportDocumentState) => {
      const outcome = await withDownloadGuard<DownloadOutcome>(guardRef.current, async () => {
        setDownloading(true);
        try {
          const { blob, filename } = await downloadFinalReportPdf(companyId, scenarioId, { documentState });
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
          ? { action: { label: "Riprova", onClick: () => download(companyId, scenarioId, documentState) } }
          : undefined
      );
    },
    []
  );

  return { download, downloading };
}
