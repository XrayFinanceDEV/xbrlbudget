"use client";

/**
 * La card di uno scenario salvato PRIMA del giro di rilievi del 14/09 (spec
 * 2026-09-15 §4.8, `migraScenario`): due colonne, ciò che il modulo puro
 * ha già ricalcolato a sinistra, ciò che serve dall'utente a destra — con un
 * rimando al passo giusto per ogni voce di «da integrare».
 *
 * Presentazionale: nessuna decisione qui, tutto il testo arriva da
 * `EsitoMigrazione` (`lib/budget-migrazione.ts`, provato in `environment:
 * node`). Sparisce dopo il primo salvataggio riuscito — la mappa migrata,
 * sporca, e' gia' quella su cui gira l'anteprima.
 */
import type { JSX } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { WIZARD_STEPS, type WizardStepKey } from "@/lib/budget-wizard-steps";
import type { EsitoMigrazione } from "@/lib/budget-migrazione";

function stepNumber(step: WizardStepKey): number {
  return WIZARD_STEPS.find((w) => w.key === step)?.n ?? 0;
}

export function MigrazioneCard({
  esito,
  onGo,
}: {
  esito: EsitoMigrazione;
  onGo: (step: WizardStepKey) => void;
}): JSX.Element {
  return (
    <Card className="mt-4 grid gap-0 border-amber-300 p-4 md:grid-cols-2 dark:border-amber-700">
      <div className="border-b pb-3 md:border-b-0 md:border-r md:pb-0 md:pr-4">
        <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Ricalcolato · All&apos;apertura
        </h3>
        <ul className="list-disc space-y-1 pl-4 text-sm">
          {esito.ricalcolato.map((testo, i) => (
            <li key={i}>{testo}</li>
          ))}
        </ul>
      </div>
      <div className="pt-3 md:pl-4 md:pt-0">
        <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Da integrare · Serve il tuo intervento
        </h3>
        <ul className="space-y-1.5 text-sm">
          {esito.daIntegrare.map((d, i) => (
            <li key={i} className="flex items-start justify-between gap-3">
              <span>{d.testo}</span>
              <Button
                variant="link"
                size="sm"
                className="h-auto shrink-0 whitespace-nowrap p-0"
                onClick={() => onGo(d.step)}
              >
                Passo {stepNumber(d.step)}
              </Button>
            </li>
          ))}
        </ul>
      </div>
    </Card>
  );
}
