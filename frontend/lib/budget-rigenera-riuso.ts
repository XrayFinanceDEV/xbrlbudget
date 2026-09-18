/**
 * «Prosegui al Budget» dall'infrannuale ripromuove la proiezione — cioe'
 * RISCRIVE l'anno base — e poi riusa lo scenario budget che esiste gia'
 * (`reuse_existing`). Senza questo modulo quel budget restava calcolato sul
 * vecchio anno base: l'utente tornava sul previsionale di prima, e nessun
 * controllo lo diceva (`forecast_stale` confronta ipotesi e previsionale, non
 * l'anno base). Richiesta del proprietario, 2026-09-18.
 *
 * Qui si rigenera con le ipotesi GIA' salvate, per la stessa porta del wizard:
 * `hydrateAssumptions` → `assumptionRowsForSave` → bulk con
 * `auto_generate=true`. Una sola modifica alle ipotesi: il piano del pregresso
 * si riallinea al nuovo anno base (`riallineaAperture`), altrimenti il motore
 * lo rifiuterebbe («Il saldo di apertura … è cambiato»).
 *
 * Tre esiti, nessuno silenzioso:
 * - nessuna ipotesi: scenario nuovo, niente da rigenerare (`null`);
 * - scenario salvato prima del 14/09 (`isScenarioPrecedente`): va migrato nel
 *   wizard, che e' l'unico a saperlo fare — non si salva nulla da qui;
 * - bulk: si legge `forecast_generated`, mai l'HTTP 200 (CLAUDE.md).
 *
 * Le dipendenze di rete arrivano da fuori: modulo collaudabile in
 * `environment: node`, nessun import da `app/` o `components/`.
 */
import type { BalanceSheet, BudgetAssumptions, BulkAssumptionsResult, Pregresso } from "@/types/api";
import { assumptionRowsForSave, hydrateAssumptions } from "@/lib/budget-horizon";
import { isScenarioPrecedente } from "@/lib/budget-migrazione";
import { riallineaAperture } from "@/lib/budget-pregresso-oltre";
import { saveOutcome } from "@/lib/budget-wizard-steps";

export interface RigeneraDeps {
  getAssumptions: () => Promise<BudgetAssumptions[]>;
  getBaseBalanceSheet: () => Promise<BalanceSheet>;
  bulkSave: (rows: Record<string, unknown>[]) => Promise<BulkAssumptionsResult>;
}

export interface EsitoRigenera {
  ok: boolean;
  message: string;
}

export async function rigeneraBudgetRiusato(scenarioId: number, deps: RigeneraDeps): Promise<EsitoRigenera | null> {
  const saved = await deps.getAssumptions();
  if (saved.length === 0) return null;
  const map = hydrateAssumptions(saved, scenarioId);
  const years = Object.keys(map).map(Number).sort((a, b) => a - b);
  if (isScenarioPrecedente(map, years)) {
    return {
      ok: false,
      message: "Lo scenario budget va aggiornato nel wizard prima di ricalcolarlo: apri le ipotesi e salva.",
    };
  }
  const first = map[years[0]];
  if (first?.pregresso) {
    const baseBs = await deps.getBaseBalanceSheet();
    map[years[0]] = { ...first, pregresso: riallineaAperture(baseBs, first.pregresso as Pregresso) };
  }
  const esito = saveOutcome(await deps.bulkSave(assumptionRowsForSave(map, years, scenarioId)));
  return esito.ok
    ? { ok: true, message: "Previsionale ricalcolato sul nuovo anno base" }
    : { ok: false, message: esito.message };
}
