/** Decisione pura per gli errori della riidratazione di /pratica. */
export type PraticaRehydrationFailure = "not_found" | "transient";

export function praticaRehydrationFailure(
  error: unknown,
): PraticaRehydrationFailure {
  const status =
    typeof error === "object" && error !== null
      ? (error as { response?: { status?: unknown } }).response?.status
      : undefined;
  return status === 404 ? "not_found" : "transient";
}
