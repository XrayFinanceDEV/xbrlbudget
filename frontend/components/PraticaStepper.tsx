"use client";

import { usePathname, useRouter } from "next/navigation";
import { ArrowRight, Check, LogOut } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  shouldShowReason,
  usePraticaPrimaryAction,
} from "@/hooks/use-pratica-primary-action";
import { useApp } from "@/contexts/AppContext";
import { usePratica } from "@/contexts/PraticaContext";
import {
  buildPraticaSteps,
  currentStepId,
  firstEnabledStep,
  gateReason,
  phaseStatus,
  praticaGates,
  PHASE_LABELS,
  PHASE_ORDER,
  type PraticaPhase,
  type PraticaStep,
} from "@/lib/pratica-steps";

export function PraticaStepper() {
  const pathname = usePathname();
  const router = useRouter();
  const { companies } = useApp();
  const { pratica, setAnalysisStep, exitPratica } = usePratica();
  // STESSA definizione del primario che rende la barra in fondo: gate,
  // azione registrata, rescue e motivi del blocco stanno in un punto solo.
  const primaryState = usePraticaPrimaryAction();

  // La home è la pagina di uscita: là comanda la nav normale.
  if (!pratica || pathname === "/") return null;

  const gates = praticaGates(pratica);
  const steps = buildPraticaSteps(pratica, gates);
  const active = currentStepId(pathname, pratica.analysisStep, pratica);
  const activePhase: PraticaPhase =
    steps.find((s) => s.id === active)?.phase ?? steps[0]?.phase ?? "dati";

  const go = (step: PraticaStep) => {
    if (!step.enabled) return;
    if (step.kind === "tab") {
      setAnalysisStep(step.id);
      if (!pathname.startsWith("/pratica")) router.push("/pratica");
      return;
    }
    if (step.route) router.push(step.route);
  };

  const company = companies.find((c) => c.id === pratica.companyId);
  const periodo =
    pratica.fiscalYear === null
      ? null
      : pratica.periodMonths !== null && pratica.periodMonths < 12
      ? `Bil. di verifica ${pratica.periodMonths}M ${pratica.fiscalYear}`
      : `Bilancio ${pratica.fiscalYear}`;

  const phaseSteps = steps.filter((s) => s.phase === activePhase);
  const azioni = phaseSteps.filter((s) => s.group === "azione");
  const viste = phaseSteps.filter((s) => s.group === "vista");

  return (
    <TooltipProvider delayDuration={200}>
      <div className="border-b border-border bg-background print:hidden">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          {/* Riga 1: identità della pratica, fasi, uscita */}
          <div className="flex items-center gap-4 py-2">
            <div className="min-w-0 shrink">
              <p className="truncate text-sm font-semibold text-foreground">
                {company?.name ?? "Nuova pratica"}
              </p>
              {periodo && (
                <p className="truncate text-xs text-muted-foreground">{periodo}</p>
              )}
            </div>

            <nav className="flex items-center gap-1 overflow-x-auto" aria-label="Fasi della pratica">
              {PHASE_ORDER.map((phase, i) => {
                const own = steps.filter((s) => s.phase === phase);
                if (own.length === 0) return null;
                const status = phaseStatus(steps, phase, active);
                const target = firstEnabledStep(steps, phase);
                const locked = status === "locked" || target === null;
                const reason = locked && own[0] ? gateReason(own[0], gates, pratica) : null;

                const chip = (
                  <Button
                    variant={status === "active" ? "default" : "ghost"}
                    size="sm"
                    onClick={() => target && go(target)}
                    disabled={locked}
                    aria-current={status === "active" ? "step" : undefined}
                    className={cn(
                      "h-7 shrink-0 gap-1.5 rounded-full px-3 text-xs font-semibold uppercase tracking-wide",
                      status === "done" && "text-foreground",
                      status === "todo" && "text-muted-foreground",
                      locked && "text-muted-foreground",
                    )}
                  >
                    {status === "done" ? (
                      <Check className="h-3 w-3" />
                    ) : (
                      <span
                        className={cn(
                          "h-2 w-2 rounded-full border",
                          status === "active"
                            ? "border-primary-foreground bg-primary-foreground"
                            : "border-current",
                        )}
                      />
                    )}
                    {i + 1} {PHASE_LABELS[phase]}
                  </Button>
                );

                return (
                  <div key={phase} className="flex items-center gap-1">
                    {i > 0 && <span className="h-px w-4 shrink-0 bg-border" />}
                    {reason ? (
                      <Tooltip>
                        {/* span: un button disabilitato non emette eventi puntatore */}
                        <TooltipTrigger asChild><span>{chip}</span></TooltipTrigger>
                        <TooltipContent>{reason}</TooltipContent>
                      </Tooltip>
                    ) : (
                      chip
                    )}
                  </div>
                );
              })}
            </nav>

            <span className="flex-1" />

            {/*
              Il primario, in taglia piena e allineato a destra. Il tester non
              trovava quello in fondo — «c'è solo il bottone piccolo in basso a
              destra, i clienti così non lo vedono» — e a primo impatto, in
              cima a una pagina, non c'era nulla che dicesse come si va avanti.
              La barra in fondo resta: dopo una tabella lunga è quella che serve.

              Il motivo si mostra anche a bottone ABILITATO (`shouldShowReason`,
              non `disabled && reason`): nel ramo rescue il bottone è abilitato
              e il motivo è l'unica cosa che spiega il dirottamento.
            */}
            {primaryState && primaryState.primary.label !== null && (
              <div className="flex shrink-0 items-center gap-2">
                {shouldShowReason(primaryState.primary) && (
                  <p className="hidden max-w-xs truncate text-xs text-muted-foreground lg:block">
                    {primaryState.primary.reason}
                  </p>
                )}
                <Button
                  onClick={primaryState.primary.run}
                  disabled={primaryState.primary.disabled}
                  className="shrink-0"
                >
                  {primaryState.primary.label}
                  <ArrowRight className="h-4 w-4 ml-2" />
                </Button>
              </div>
            )}

            <Button
              variant="ghost"
              size="sm"
              className="shrink-0 text-muted-foreground"
              onClick={() => {
                exitPratica();
                router.push("/");
              }}
            >
              <LogOut className="h-4 w-4 mr-1" /> Esci dalla pratica
            </Button>
          </div>

          {/* Riga 2: gli step della sola fase attiva, azioni ┊ viste */}
          <nav
            className="flex items-center gap-1 overflow-x-auto"
            aria-label={`Passaggi: ${PHASE_LABELS[activePhase]}`}
          >
            {azioni.map((step) => (
              <StepTab key={step.id} step={step} active={active === step.id} onClick={() => go(step)} />
            ))}
            {azioni.length > 0 && viste.length > 0 && (
              <span className="mx-2 h-5 w-px shrink-0 bg-border" aria-hidden />
            )}
            {viste.map((step) => (
              <StepTab key={step.id} step={step} active={active === step.id} onClick={() => go(step)} />
            ))}
          </nav>
        </div>
      </div>
    </TooltipProvider>
  );
}

function StepTab({
  step,
  active,
  onClick,
}: {
  step: PraticaStep;
  active: boolean;
  onClick: () => void;
}) {
  return (
    // shadcn Button con override: la resa "tab" (bordo inferiore, nessuno
    // sfondo) non è una variante nativa, ma il vincolo di progetto vieta un
    // <button> grezzo. `disabled:opacity-50` del Button fa da sé il grigio
    // degli step non ancora raggiungibili.
    <Button
      variant="ghost"
      onClick={onClick}
      disabled={!step.enabled}
      aria-current={active ? "page" : undefined}
      className={cn(
        "h-auto whitespace-nowrap rounded-none border-b-2 px-3 py-2.5 text-sm font-medium hover:bg-transparent",
        active
          ? "border-primary text-foreground"
          : "border-transparent text-muted-foreground hover:border-border hover:text-foreground",
      )}
    >
      {step.label}
    </Button>
  );
}
