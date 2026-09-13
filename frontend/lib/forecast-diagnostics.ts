import type { ForecastDiagnostic } from "@/types/api";

export function hasDiagnosticErrors(diagnostics: ForecastDiagnostic[]): boolean {
  return diagnostics.some((diagnostic) => diagnostic.severity === "error");
}

export function diagnosticAmount(diagnostic: ForecastDiagnostic): string | null {
  if (diagnostic.amount === undefined || diagnostic.amount === null) return null;
  const amount = Number(diagnostic.amount);
  if (!Number.isFinite(amount)) return String(diagnostic.amount);
  return new Intl.NumberFormat("it-IT", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount);
}
