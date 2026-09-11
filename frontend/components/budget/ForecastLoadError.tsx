"use client";

/**
 * Stato d'errore comune a CE Prev., SP Prev., Report e (dal task successivo di questo
 * lotto) alla tab Indicatori dell'infrannuale: un messaggio leggibile — mai lo spinner
 * che resta a schermo per sempre — e un modo di ritentare la stessa lettura, senza un
 * refresh completo della pagina.
 *
 * Come `ForecastStaleBanner`, rende soltanto: la decisione del messaggio sta in
 * `lib/forecast-page-status.ts` (`forecastLoadErrorMessage`), pura e testata in
 * `environment: node` — questo componente non ha una sua suite, jsdom non e' installato
 * in questo progetto.
 */
import { AlertCircle, RefreshCw } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { forecastLoadErrorMessage } from "@/lib/forecast-page-status";

export function ForecastLoadError({
  error,
  onRetry,
  className,
}: {
  error: unknown;
  onRetry: () => void;
  className?: string;
}) {
  return (
    <Alert variant="destructive" className={className}>
      <AlertCircle className="h-4 w-4" />
      <AlertTitle>Errore</AlertTitle>
      <AlertDescription className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <span>{forecastLoadErrorMessage(error)}</span>
        <Button variant="outline" size="sm" onClick={onRetry} className="self-start sm:self-auto">
          <RefreshCw className="h-4 w-4 mr-2" />
          Riprova
        </Button>
      </AlertDescription>
    </Alert>
  );
}
