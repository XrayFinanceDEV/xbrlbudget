"use client";

import { useCallback, useRef, useState } from "react";
import { toast } from "sonner";
import { downloadInfrannualePdf } from "@/lib/api";
import {
  FinalReportDownloadError,
  createDownloadGuardState,
  isRetryableDownloadStatus,
  saveBlobAsFile,
  withDownloadGuard,
  type FinalReportDownloadSink,
} from "@/lib/final-report-download";
import { getErrorMessage } from "@/lib/utils";

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
 * Scarica il report infrannuale (ReportLab) della tab Stampa. Stessa guardia
 * contro il doppio click e stessa mappa d'errore del report finale
 * (`use-final-report-download.ts`); «Riprova» su 503/504.
 */
export function useInfrannualeDownload() {
  const [downloading, setDownloading] = useState(false);
  const guardRef = useRef(createDownloadGuardState());

  const download = useCallback(
    async (companyId: number, scenarioId: number): Promise<void> => {
      const outcome = await withDownloadGuard(guardRef.current, async () => {
        setDownloading(true);
        try {
          const { blob, filename } = await downloadInfrannualePdf(companyId, scenarioId);
          saveBlobAsFile(blob, filename, browserSink);
          return null;
        } catch (error) {
          return error;
        } finally {
          setDownloading(false);
        }
      });
      if (!outcome) return;
      const status = outcome instanceof FinalReportDownloadError ? outcome.status : null;
      toast.error(getErrorMessage(outcome), status !== null && isRetryableDownloadStatus(status)
        ? { action: { label: "Riprova", onClick: () => void download(companyId, scenarioId) } }
        : undefined);
    },
    [],
  );

  return { download, downloading };
}
