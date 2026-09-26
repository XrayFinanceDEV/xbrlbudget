import type { WizardStepKey } from "@/lib/budget-wizard-steps";

const BEFORE_PREGRESSO = new Set<WizardStepKey>(["fatturato", "costi", "circolante"]);

/** Nei passi economici l'anteprima usa solo le ipotesi già affrontate.
 * Una lista di altri finanziatori senza la divisione dei fidi, rimasta anche
 * da un tentativo di salvataggio, non deve bloccare il Fatturato. Le righe
 * originali restano intatte per il salvataggio e per Patrimoniale pregresso. */
export function previewRowsForStep(rows: Record<string, unknown>[], step: WizardStepKey): Record<string, unknown>[] {
  if (!BEFORE_PREGRESSO.has(step) || rows.length === 0) return rows;
  const first = rows[0];
  if (!Array.isArray(first.other_lenders) || first.other_lenders.length === 0 || first.bank_lines_amount != null) {
    return rows;
  }
  return [{ ...first, other_lenders: null }, ...rows.slice(1)];
}
