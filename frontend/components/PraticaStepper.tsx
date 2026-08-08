"use client";

import { usePathname, useRouter } from "next/navigation";
import { LogOut } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { usePratica } from "@/contexts/PraticaContext";
import { buildPraticaSteps, type PraticaGates, type PraticaStep } from "@/lib/pratica-steps";

/**
 * Quale step è attivo, dedotto dalla rotta corrente (fase PREVISIONALE) o
 * dalla tab del wizard (fase ANALISI).
 */
function currentStepId(pathname: string, analysisStep: string): string {
  if (pathname.startsWith("/pratica")) return analysisStep;
  if (pathname.startsWith("/forecast")) return "ce-previsionale";
  if (pathname.startsWith("/cashflow")) return "rendiconto";
  if (pathname.startsWith("/report")) return "report";
  if (pathname.startsWith("/budget")) return "budget";
  return "";
}

export function PraticaStepper() {
  const pathname = usePathname();
  const router = useRouter();
  const { pratica, setAnalysisStep, exitPratica } = usePratica();

  // La home è la pagina di uscita: là comanda la nav normale.
  if (!pratica || pathname === "/") return null;

  // I gate derivano da ciò che è già stato raggiunto e persistito nel context.
  // Il wizard li affina in locale; qui bastano per decidere cosa è cliccabile.
  const gates: PraticaGates = {
    imported: pratica.fiscalYear !== null,
    // storico è true anche quando la scheda storico non esiste (import senza anno
    // di raffronto): è il wizard a scriverlo così, vedi Task 7 Step 4.
    rettificheOk:
      pratica.rettificheConfirmed.verifica && pratica.rettificheConfirmed.storico,
    comparisonReady: pratica.infrannualeScenarioId !== null,
    projectionReady: pratica.infrannualeScenarioId !== null,
    budgetScenario: pratica.budgetScenarioId !== null,
    forecastReady: pratica.budgetScenarioId !== null,
  };

  const steps = buildPraticaSteps(pratica, gates);
  const active = currentStepId(pathname, pratica.analysisStep);

  const go = (step: PraticaStep) => {
    if (!step.enabled) return;
    if (step.kind === "tab") {
      setAnalysisStep(step.id);
      if (!pathname.startsWith("/pratica")) router.push("/pratica");
      return;
    }
    if (step.route) router.push(step.route);
  };

  const phases: Array<{ key: "analisi" | "previsionale"; label: string }> = [
    { key: "analisi", label: "Analisi" },
    { key: "previsionale", label: "Previsionale" },
  ];

  return (
    <div className="border-b border-border bg-background print:hidden">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <nav className="flex items-center gap-1 overflow-x-auto" aria-label="Percorso pratica">
          {phases.map((phase, phaseIdx) => {
            const phaseSteps = steps.filter((s) => s.phase === phase.key);
            if (phaseSteps.length === 0) return null;
            return (
              <div key={phase.key} className="flex items-center gap-1">
                {phaseIdx > 0 && <div className="mx-2 h-6 w-px shrink-0 bg-border" />}
                <span className="shrink-0 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                  {phase.label}
                </span>
                {phaseSteps.map((step) => (
                  <button
                    key={step.id}
                    onClick={() => go(step)}
                    disabled={!step.enabled}
                    className={cn(
                      "flex items-center gap-1.5 whitespace-nowrap px-3 py-3 text-sm font-medium border-b-2 transition-colors",
                      active === step.id
                        ? "border-primary text-foreground"
                        : step.enabled
                        ? "border-transparent text-muted-foreground hover:text-foreground hover:border-border"
                        : "border-transparent text-muted-foreground/40 cursor-not-allowed",
                    )}
                  >
                    {step.label}
                  </button>
                ))}
              </div>
            );
          })}
          <span className="flex-1" />
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
        </nav>
      </div>
    </div>
  );
}
