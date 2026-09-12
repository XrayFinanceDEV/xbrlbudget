"use client";

/**
 * L'avviso che i numeri del previsionale a schermo sono di una generazione
 * PRECEDENTE alle ipotesi salvate.
 *
 * Succede perche' `PUT /scenarios/{id}/assumptions` risponde 200 anche a una
 * generazione respinta (CLAUDE.md › «Invarianti e trappole › Previsionale»):
 * le ipotesi restano salvate, il previsionale no, e senza questo avviso le
 * cinque viste continuano a disegnare i numeri di prima come se fossero
 * aggiornati.
 *
 * Qui non si decide nulla: il verdetto sta in `lib/budget-stale.ts`, che ha la
 * sua suite in `environment: node` (jsdom non e' installato). Questo
 * componente rende soltanto.
 */
import { AlertTriangle } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { forecastStaleFromAnalysis } from "@/lib/budget-stale";
import { cn } from "@/lib/utils";
import type { ScenarioAnalysis } from "@/types/api";

export function ForecastStaleBanner({
  analysis,
  className,
}: {
  analysis: ScenarioAnalysis | null | undefined;
  className?: string;
}) {
  if (!forecastStaleFromAnalysis(analysis)) return null;

  return (
    <Alert
      className={cn(
        "border-amber-500/50 bg-amber-50 text-amber-900 [&>svg]:text-amber-600",
        "dark:border-amber-500 dark:bg-amber-950/40 dark:text-amber-100 dark:[&>svg]:text-amber-400",
        className,
      )}
    >
      <AlertTriangle className="h-4 w-4" />
      <AlertTitle>Previsionale non aggiornato</AlertTitle>
      <AlertDescription>
        I numeri qui sotto vengono da una generazione <strong>precedente</strong> alle
        ipotesi salvate: l&apos;ultimo salvataggio non ha prodotto un nuovo
        previsionale. Per allinearli, torna alle ipotesi e rigenera il
        previsionale.
      </AlertDescription>
    </Alert>
  );
}
