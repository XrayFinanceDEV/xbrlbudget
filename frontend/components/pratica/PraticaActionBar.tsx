"use client";

import { ArrowLeft, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  shouldShowReason,
  usePraticaPrimaryAction,
} from "@/hooks/use-pratica-primary-action";

/**
 * La barra in fondo. Resta anche ora che il primario è duplicato in alto
 * (`PraticaStepper`): dopo una tabella lunga è questa che serve, e toglierla
 * risolverebbe una lamentela creandone la simmetrica.
 *
 * Le regole del primario non vivono più qui — stanno in
 * `usePraticaPrimaryAction`, resa in due punti da un'unica definizione.
 */
export function PraticaActionBar() {
  const state = usePraticaPrimaryAction();
  if (!state) return null;

  const { primary, back, go } = state;

  return (
    // sticky (non fixed): resta in flusso, quindi non copre mai l'ultima riga
    // delle tabelle lunghe e non serve compensare con padding sul contenuto.
    <div className="sticky bottom-0 z-30 border-t border-border bg-background/95 backdrop-blur print:hidden">
      <div className="max-w-7xl mx-auto flex items-center gap-4 px-4 py-3 sm:px-6 lg:px-8">
        {back ? (
          <Button variant="ghost" size="sm" disabled={!back.enabled} onClick={() => go(back)}>
            <ArrowLeft className="h-4 w-4 mr-1" />
            {back.label}
          </Button>
        ) : (
          <span />
        )}
        <span className="flex-1" />
        {primary.label !== null && (
          <>
            {shouldShowReason(primary) && (
              <p className="truncate text-sm text-muted-foreground">{primary.reason}</p>
            )}
            <Button onClick={primary.run} disabled={primary.disabled}>
              {primary.label}
              <ArrowRight className="h-4 w-4 ml-2" />
            </Button>
          </>
        )}
      </div>
    </div>
  );
}
