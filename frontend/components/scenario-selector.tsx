"use client";

import { Label } from "@/components/ui/label";
import type { BudgetScenario } from "@/types/api";

interface ScenarioSelectorProps {
  scenarios: BudgetScenario[];
  selectedScenario: BudgetScenario | null;
  onSelect: (scenario: BudgetScenario | null) => void;
  label?: string;
}

export function ScenarioSelector({
  scenarios,
  selectedScenario,
  onSelect,
  label = "Scenario Budget:",
}: ScenarioSelectorProps) {
  return (
    <div className="flex items-center gap-3">
      <Label className="text-sm font-medium whitespace-nowrap">{label}</Label>
      <select
        value={selectedScenario?.id || ""}
        onChange={(e) => {
          const scenario = scenarios.find((s) => s.id === Number(e.target.value));
          onSelect(scenario || null);
        }}
        className="flex h-9 w-full max-w-md rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
      >
        {scenarios.map((scenario) => (
          <option key={scenario.id} value={scenario.id}>
            {scenario.name} - Anno Base: {scenario.base_year}
            {scenario.is_active ? " (Attivo)" : ""}
          </option>
        ))}
      </select>
    </div>
  );
}
