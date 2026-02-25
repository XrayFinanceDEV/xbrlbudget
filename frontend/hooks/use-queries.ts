"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getBudgetScenarios,
  getScenarioAnalysis,
  getDetailedCashFlow,
  getForecastReclassifiedData,
  getIntraYearComparison,
  getMultiYearRatios,
  getCompleteAnalysis,
} from "@/lib/api";
import type { BudgetScenario } from "@/types/api";

// Query key factory — centralizes all cache keys
export const queryKeys = {
  completeAnalysis: (companyId: number, year: number) =>
    ["companies", companyId, "years", year, "analysis"] as const,
  scenarios: (companyId: number) =>
    ["companies", companyId, "scenarios"] as const,
  analysis: (companyId: number, scenarioId: number) =>
    ["companies", companyId, "scenarios", scenarioId, "analysis"] as const,
  detailedCashflow: (companyId: number, scenarioId: number) =>
    ["companies", companyId, "scenarios", scenarioId, "cashflow"] as const,
  reclassified: (companyId: number, scenarioId: number) =>
    ["companies", companyId, "scenarios", scenarioId, "reclassified"] as const,
  intraYearComparison: (companyId: number, scenarioId: number) =>
    ["companies", companyId, "scenarios", scenarioId, "comparison"] as const,
  multiYearRatios: (companyId: number, scenarioId: number) =>
    ["companies", companyId, "scenarios", scenarioId, "ratios"] as const,
};

// Budget scenarios only (filters out infrannuale)
export function useScenarios(companyId: number | null) {
  return useQuery({
    queryKey: queryKeys.scenarios(companyId!),
    queryFn: () => getBudgetScenarios(companyId!),
    enabled: !!companyId,
    select: (data) =>
      data.filter(
        (s: BudgetScenario) => s.scenario_type !== "infrannuale"
      ),
  });
}

// All scenarios including infrannuale
export function useAllScenarios(companyId: number | null) {
  return useQuery({
    queryKey: queryKeys.scenarios(companyId!),
    queryFn: () => getBudgetScenarios(companyId!),
    enabled: !!companyId,
  });
}

// Pick active or first scenario from a list
export function getPreferredScenario(
  scenarios: BudgetScenario[] | undefined
): BudgetScenario | null {
  if (!scenarios?.length) return null;
  return (
    scenarios.find((s) => s.is_active === 1) ??
    scenarios[0]
  );
}

// Comprehensive scenario analysis
export function useAnalysis(
  companyId: number | null,
  scenarioId: number | null
) {
  return useQuery({
    queryKey: queryKeys.analysis(companyId!, scenarioId!),
    queryFn: () => getScenarioAnalysis(companyId!, scenarioId!),
    enabled: !!companyId && !!scenarioId,
  });
}

// Detailed Italian GAAP cashflow
export function useDetailedCashflow(
  companyId: number | null,
  scenarioId: number | null
) {
  return useQuery({
    queryKey: queryKeys.detailedCashflow(companyId!, scenarioId!),
    queryFn: () => getDetailedCashFlow(companyId!, scenarioId!),
    enabled: !!companyId && !!scenarioId,
  });
}

// Reclassified forecast data
export function useReclassifiedData(
  companyId: number | null,
  scenarioId: number | null
) {
  return useQuery({
    queryKey: queryKeys.reclassified(companyId!, scenarioId!),
    queryFn: () => getForecastReclassifiedData(companyId!, scenarioId!),
    enabled: !!companyId && !!scenarioId,
  });
}

// Intra-year comparison
export function useIntraYearComparison(
  companyId: number | null,
  scenarioId: number | null
) {
  return useQuery({
    queryKey: queryKeys.intraYearComparison(companyId!, scenarioId!),
    queryFn: () => getIntraYearComparison(companyId!, scenarioId!),
    enabled: !!companyId && !!scenarioId,
  });
}

// Multi-year ratios (used by analysis page)
export function useMultiYearRatios(
  companyId: number | null,
  scenarioId: number | null
) {
  return useQuery({
    queryKey: queryKeys.multiYearRatios(companyId!, scenarioId!),
    queryFn: () => getMultiYearRatios(companyId!, scenarioId!),
    enabled: !!companyId && !!scenarioId,
  });
}

// Single-year complete analysis (historical year)
export function useCompleteAnalysis(
  companyId: number | null,
  year: number | null
) {
  return useQuery({
    queryKey: queryKeys.completeAnalysis(companyId!, year!),
    queryFn: () => getCompleteAnalysis(companyId!, year!),
    enabled: !!companyId && !!year,
  });
}

// Cache invalidation helpers — use after mutations (save assumptions, delete, promote)
export function useInvalidateAnalysis() {
  const qc = useQueryClient();
  return (companyId: number, scenarioId: number) => {
    qc.invalidateQueries({
      queryKey: queryKeys.analysis(companyId, scenarioId),
    });
    qc.invalidateQueries({
      queryKey: queryKeys.detailedCashflow(companyId, scenarioId),
    });
    qc.invalidateQueries({
      queryKey: queryKeys.reclassified(companyId, scenarioId),
    });
    qc.invalidateQueries({
      queryKey: queryKeys.multiYearRatios(companyId, scenarioId),
    });
  };
}

export function useInvalidateScenarios() {
  const qc = useQueryClient();
  return (companyId: number) => {
    qc.invalidateQueries({
      queryKey: queryKeys.scenarios(companyId),
    });
  };
}
