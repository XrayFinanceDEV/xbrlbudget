"use client";

import { useCallback } from "react";
import { downloadInfrannualePdf } from "@/lib/api";
import { useFileDownload } from "@/hooks/use-file-download";

/**
 * Scarica il report infrannuale (ReportLab) della tab Stampa. Stessa guardia
 * contro il doppio click e stessa mappa d'errore del report finale
 * (`use-final-report-download.ts`); «Riprova» su 503/504.
 */
export function useInfrannualeDownload() {
  const file = useFileDownload();
  const { download: run } = file;
  const download = useCallback(
    (companyId: number, scenarioId: number) =>
      run(() => downloadInfrannualePdf(companyId, scenarioId), "Impossibile scaricare il PDF del report"),
    [run],
  );
  return { download, downloading: file.downloading };
}
