"use client";

import { useState } from "react";
import { AlertTriangle, CircleAlert, X } from "lucide-react";
import type { ForecastDiagnostic } from "@/types/api";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  diagnosticAmount,
  diagnosticsLabel,
  diagnosticsSignature,
  hasDiagnosticErrors,
} from "@/lib/forecast-diagnostics";

export function ForecastDiagnostics({ diagnostics }: { diagnostics: ForecastDiagnostic[] }) {
  // La chiusura è legata a QUESTE verifiche (vedi diagnosticsSignature): una
  // proiezione nuova che ne porta altre si rimostra da sola.
  const [chiusaPer, setChiusaPer] = useState<string | null>(null);
  const firma = diagnosticsSignature(diagnostics);

  if (diagnostics.length === 0) return null;

  const hasErrors = hasDiagnosticErrors(diagnostics);
  const Icon = hasErrors ? CircleAlert : AlertTriangle;

  if (chiusaPer === firma) {
    return (
      <Button
        variant="ghost"
        size="sm"
        className="text-muted-foreground"
        onClick={() => setChiusaPer(null)}
      >
        <Icon className="h-4 w-4 mr-1.5" />
        {hasErrors ? "Criticità da risolvere" : "Verifiche sulla proiezione"}
        {` · ${diagnosticsLabel(diagnostics)}`}
      </Button>
    );
  }

  return (
    <Alert variant={hasErrors ? "destructive" : "default"} className="relative">
      <Icon className="h-4 w-4" />
      <AlertTitle className="pr-8">
        {hasErrors ? "Proiezione con criticità da risolvere" : "Verifiche richieste sulla proiezione"}
      </AlertTitle>
      <Button
        variant="ghost"
        size="icon"
        className="absolute right-2 top-2 h-7 w-7"
        aria-label="Chiudi le verifiche"
        onClick={() => setChiusaPer(firma)}
      >
        <X className="h-4 w-4" />
      </Button>
      <AlertDescription>
        <ul className="mt-2 space-y-2 list-disc pl-5">
          {diagnostics.map((diagnostic, index) => {
            const amount = diagnosticAmount(diagnostic);
            return (
              <li key={`${diagnostic.code}-${index}`}>
                <span>{diagnostic.message}</span>
                {amount && <span className="font-medium"> Importo: {amount}.</span>}
                <span className="ml-1 text-xs opacity-75">({diagnostic.code})</span>
              </li>
            );
          })}
        </ul>
      </AlertDescription>
    </Alert>
  );
}
