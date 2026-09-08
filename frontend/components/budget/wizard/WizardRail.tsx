"use client";

// The horizontal step guide for the wizard (spec 2026-09-08 §4.0). It sits
// *inside* the page, not as a left rail or a top bar: the app's own nav owns
// the left column and the pratica stepper owns the top, both because the app
// runs inside a Formula Finance iframe.
import type { JSX } from "react";
import { Check } from "lucide-react";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { WIZARD_STEPS, groupWizardSteps, type WizardStepKey } from "@/lib/budget-wizard-steps";

const GROUPS = groupWizardSteps(WIZARD_STEPS);

export function WizardRail(props: {
  active: WizardStepKey;
  visited: Set<WizardStepKey>;
  horizon: number;
  baseYear: number;
  onGo: (k: WizardStepKey) => void;
}): JSX.Element {
  const { active, visited, horizon, baseYear, onGo } = props;

  return (
    <nav aria-label="Passi delle ipotesi" className="overflow-x-auto">
      <Card className="flex min-w-max items-stretch gap-6 border-border/80 px-4 py-3">
        {GROUPS.map((g) => (
          <div key={g.group} className="flex flex-col gap-1.5">
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground">{g.group}</span>
            <div className="flex items-center gap-4">
              {g.steps.map((step) => {
                const isActive = step.key === active;
                const isVisited = visited.has(step.key);
                return (
                  <button
                    key={step.key}
                    type="button"
                    aria-current={isActive ? "step" : undefined}
                    onClick={() => onGo(step.key)}
                    className="relative flex flex-col items-center gap-1 px-0.5 pb-1"
                  >
                    <span
                      className={cn(
                        "flex h-5 w-5 items-center justify-center rounded-full border text-[10px] font-medium",
                        isActive
                          ? "border-primary bg-primary/10 text-primary"
                          : isVisited
                          ? "border-green-600 bg-green-600 text-white dark:border-green-500 dark:bg-green-500"
                          : "border-border text-muted-foreground"
                      )}
                    >
                      {!isActive && isVisited ? <Check className="h-3 w-3" /> : step.n}
                    </span>
                    <span className="whitespace-nowrap text-[10px] text-muted-foreground">{step.title}</span>
                    {isActive && <span className="absolute -bottom-0.5 left-0 right-0 h-0.5 bg-primary" />}
                  </button>
                );
              })}
            </div>
          </div>
        ))}
        <div className="ml-auto flex items-center whitespace-nowrap border-l border-border pl-4 text-xs text-muted-foreground">
          Orizzonte {horizon} anni · {baseYear + 1} – {baseYear + horizon}
        </div>
      </Card>
    </nav>
  );
}
