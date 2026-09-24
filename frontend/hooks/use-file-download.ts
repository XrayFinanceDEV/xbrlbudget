"use client";

import { useCallback, useRef, useState } from "react";
import { toast } from "sonner";
import {
  FinalReportDownloadError,
  createDownloadGuardState,
  isRetryableDownloadStatus,
  saveBlobAsFile,
  withDownloadGuard,
  type FinalReportDownloadSink,
} from "@/lib/final-report-download";
import { getErrorMessage } from "@/lib/utils";

type Fetcher = () => Promise<{ blob: Blob; filename: string }>;

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
 * Scarica un file prodotto dal server (PDF o Word dei report): guardia contro
 * il doppio click, toast d'errore con la mappa dei report e «Riprova» su
 * 503/504. Il formato lo decide il `fetcher`, non l'hook.
 */
export function useFileDownload() {
  const [downloading, setDownloading] = useState(false);
  const guardRef = useRef(createDownloadGuardState());

  const download = useCallback(async (fetcher: Fetcher, errorFallback: string): Promise<void> => {
    const outcome = await withDownloadGuard(guardRef.current, async () => {
      setDownloading(true);
      try {
        const { blob, filename } = await fetcher();
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
    toast.error(getErrorMessage(outcome, errorFallback), status !== null && isRetryableDownloadStatus(status)
      ? { action: { label: "Riprova", onClick: () => void download(fetcher, errorFallback) } }
      : undefined);
  }, []);

  return { download, downloading };
}
