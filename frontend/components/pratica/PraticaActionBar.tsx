"use client";

import { usePathname, useRouter } from "next/navigation";
import { ArrowLeft, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { usePratica } from "@/contexts/PraticaContext";
import { usePraticaAction } from "@/contexts/PraticaActionContext";
import {
  buildPraticaSteps,
  currentStepId,
  firstEnabledStep,
  gateReason,
  nextStep,
  praticaGates,
  prevStep,
  type PraticaStep,
} from "@/lib/pratica-steps";

export function PraticaActionBar() {
  const pathname = usePathname();
  const router = useRouter();
  const { pratica, setAnalysisStep, exitPratica } = usePratica();
  const { action, runAction } = usePraticaAction();

  if (!pratica || pathname === "/") return null;

  const gates = praticaGates(pratica);
  const steps = buildPraticaSteps(pratica, gates);
  const currentId = currentStepId(pathname, pratica.analysisStep);
  const current = steps.find((s) => s.id === currentId) ?? null;

  const go = (step: PraticaStep) => {
    if (!step.enabled) return;
    if (step.kind === "tab") {
      setAnalysisStep(step.id);
      if (!pathname.startsWith("/pratica")) router.push("/pratica");
      return;
    }
    if (step.route) router.push(step.route);
  };

  const back = prevStep(steps, currentId);
  const next = nextStep(steps, currentId);

  // Cosa mostra il bottone primario, in ordine di precedenza.
  let label: string;
  let disabled: boolean;
  let reason: string | null;
  let run: () => void;

  const rescue = current && !current.enabled ? firstEnabledStep(steps, current.phase) : null;

  if (rescue) {
    // Lo step corrente non è (più) raggiungibile: può succedere rientrando su
    // un analysisStep persistito dopo un "Ripristina originale". Non si propone
    // un avanzamento da uno step morto, si torna indietro.
    label = `Torna a ${rescue.label}`;
    disabled = false;
    reason = "Questo passaggio non è più disponibile";
    run = () => go(rescue);
  } else if (action) {
    label = action.label;
    disabled = action.disabled;
    reason = action.reason;
    run = runAction;
  } else if (next) {
    label = `Avanti: ${next.label}`;
    disabled = !next.enabled;
    reason = gateReason(next, gates, pratica);
    run = () => go(next);
  } else {
    label = "Chiudi la pratica";
    disabled = false;
    reason = null;
    run = () => {
      exitPratica();
      router.push("/");
    };
  }

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
        {/* Non `disabled && reason`: nel ramo rescue il bottone è ABILITATO e
            il motivo è l'unica cosa che spiega perché sei stato dirottato. Chi
            registra un'azione mette `reason` non nullo solo quando disabilita. */}
        {reason && <p className="truncate text-sm text-muted-foreground">{reason}</p>}
        <Button onClick={run} disabled={disabled}>
          {label}
          <ArrowRight className="h-4 w-4 ml-2" />
        </Button>
      </div>
    </div>
  );
}
