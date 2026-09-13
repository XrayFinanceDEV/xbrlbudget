"use client";

import { AlertTriangle, CircleAlert } from "lucide-react";
import type { ForecastDiagnostic } from "@/types/api";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { diagnosticAmount, hasDiagnosticErrors } from "@/lib/forecast-diagnostics";

export function ForecastDiagnostics({ diagnostics }: { diagnostics: ForecastDiagnostic[] }) {
  if (diagnostics.length === 0) return null;

  const hasErrors = hasDiagnosticErrors(diagnostics);
  const Icon = hasErrors ? CircleAlert : AlertTriangle;

  return (
    <Alert variant={hasErrors ? "destructive" : "default"}>
      <Icon className="h-4 w-4" />
      <AlertTitle>
        {hasErrors ? "Proiezione con criticità da risolvere" : "Verifiche richieste sulla proiezione"}
      </AlertTitle>
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
