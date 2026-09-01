"use client";

import { usePathname, useRouter } from "next/navigation";
import { usePratica } from "@/contexts/PraticaContext";
import { usePraticaAction } from "@/contexts/PraticaActionContext";
import {
  buildPraticaSteps,
  currentStepId,
  gateReason,
  nextStep,
  praticaGates,
  prevStep,
  rescueStep,
  type PraticaStep,
} from "@/lib/pratica-steps";

export type PraticaPrimaryAction = {
  /** `null` = nessun primario da mostrare. In NESSUNO dei due punti. */
  label: string | null;
  disabled: boolean;
  reason: string | null;
  run: () => void;
};

export type PraticaPrimary = {
  primary: PraticaPrimaryAction;
  /** Lo step precedente, per il solo «Indietro» della barra in fondo. */
  back: PraticaStep | null;
  go: (step: PraticaStep) => void;
} | null;

/**
 * L'azione per proseguire nel percorso pratica: **una sola definizione**, resa
 * in due punti — la barra in fondo (`PraticaActionBar`) e l'intestazione in
 * alto a destra (`PraticaStepper`, che è montato anche sulle rotte
 * PREVISIONALE).
 *
 * Sta in un hook e non duplicata perché qui vivono gate, azione registrata
 * dallo step, recupero da uno step non più raggiungibile e motivi del blocco:
 * due copie di quelle regole divergerebbero, ed è esattamente la classe di
 * difetto che il catalogo IV-CEE ha appena finito di eliminare per le
 * etichette.
 *
 * Restituisce `null` fuori da una pratica e sulla home.
 */
export function usePraticaPrimaryAction(): PraticaPrimary {
  const pathname = usePathname();
  const router = useRouter();
  const { pratica, setAnalysisStep, exitPratica } = usePratica();
  const { action, runAction } = usePraticaAction();

  if (!pratica || pathname === "/") return null;

  const gates = praticaGates(pratica);
  const steps = buildPraticaSteps(pratica, gates);
  const currentId = currentStepId(pathname, pratica.analysisStep, pratica);
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

  // Cosa mostra il bottone primario, in ordine di precedenza. `null` = nessun
  // primario (rotta non mappata, nessuna azione registrata): restano solo
  // Indietro e lo stepper.
  let label: string | null;
  let disabled: boolean;
  let reason: string | null;
  let run: () => void;

  // `rescueStep` cerca sull'INTERO percorso, non nella sola fase corrente: un
  // "Ripristina originale" azzera rettificheOk, che è in AND su tutti e
  // quattro gli step della fase ANALISI, quindi la fase intera risulta
  // bloccata e un rescue ristretto alla fase non troverebbe mai nulla.
  // Condivisa con `blockedStep` (il render gate del wizard) apposta: le due
  // non possono proporre due destinazioni diverse per lo stesso step
  // bloccato (FINDING 2, review finale). `rescueStep` restituisce `null`
  // fuori dal wizard (rotte PREVISIONALE, nessuno step `kind: "tab"`
  // abilitato) — lì si ricade sul primo step abilitato di qualsiasi tipo,
  // altrimenti la barra resterebbe senza rescue proprio dove serve di più.
  const rescue =
    current && !current.enabled
      ? rescueStep(steps) ?? steps.find((s) => s.enabled) ?? null
      : null;

  if (rescue) {
    // Lo step corrente non è (più) raggiungibile: può succedere rientrando su
    // un analysisStep persistito dopo un "Ripristina originale". Non si propone
    // un avanzamento da uno step morto, si torna al primo step abilitato del
    // percorso.
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
  } else if (current !== null) {
    // Solo qui siamo davvero sull'ultimo step del percorso: current e next
    // esistono entrambi e non c'è altro dopo. Se `current` è null (rotta non
    // mappata, es. /import dentro una pratica) non mostriamo alcun primario:
    // "Chiudi la pratica" come default accidentale su una rotta ignota
    // sarebbe un'azione distruttiva non richiesta.
    label = "Chiudi la pratica";
    disabled = false;
    reason = null;
    run = () => {
      exitPratica();
      router.push("/");
    };
  } else {
    // `current` è null: rotta non riconosciuta da currentStepId (es. /import
    // dentro una pratica). Nessun primario da proporre.
    label = null;
    disabled = true;
    reason = null;
    run = () => {};
  }

  return { primary: { label, disabled, reason, run }, back, go };
}

/**
 * Il motivo va mostrato anche a bottone ABILITATO.
 *
 * Non è `disabled && reason`: nel ramo rescue il bottone è abilitato e il
 * motivo è l'unica cosa che spiega perché sei stato dirottato. Chi registra
 * un'azione mette `reason` non nullo solo quando disabilita. La regola sta
 * qui perché la applicano entrambi i punti di resa.
 */
export function shouldShowReason(primary: PraticaPrimaryAction): boolean {
  return primary.label !== null && primary.reason !== null;
}
