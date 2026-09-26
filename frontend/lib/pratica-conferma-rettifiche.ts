import type { AdjustableFinancialYear, RettificaEntry } from "@/types/api";
import { RETTIFICHE_MAX } from "@/lib/pratica-rettifiche-rules";
import { chiusuraAutomatica, scartoQuadratura } from "@/lib/pratica-quadratura";

type DatiConferma = Pick<AdjustableFinancialYear, "balance_sheet" | "income_statement" | "rettifiche_log">;

export type ConfermaPreparata =
  | { kind: "already_confirmed" }
  | { kind: "limit" }
  | { kind: "save"; values?: Record<string, number>; log: RettificaEntry[]; closedAmount: number | null };

/** Prepara la conferma sui valori PERSISTITI, non sulla copia locale che può
 * avere già assorbito uno scarto in memoria. Funziona anche se il marker di
 * conferma esiste: una rettifica successiva può aver riaperto la quadratura. */
export function preparaConfermaRettifiche(data: DatiConferma, year: number, periodMonths: number | undefined): ConfermaPreparata {
  const values = { ...data.balance_sheet, ...data.income_statement };
  const log = data.rettifiche_log ?? [];
  const chiusura = chiusuraAutomatica(scartoQuadratura(values));
  if (chiusura && log.filter((entry) => entry.entry_type !== "confirm").length >= RETTIFICHE_MAX) {
    return { kind: "limit" };
  }
  const confirmed = log.some((entry) => entry.entry_type === "confirm");
  if (confirmed && !chiusura) return { kind: "already_confirmed" };

  const nextLog = [...log];
  let corrected: Record<string, number> | undefined;
  if (chiusura) {
    corrected = { ...values };
    corrected[chiusura.field] = Math.round(((corrected[chiusura.field] ?? 0) + chiusura.delta) * 100) / 100;
    // La destinazione passiva è un dettaglio: l'aggregato deve muoversi dello
    // stesso importo, altrimenti il motore rileva ancora lo sbilancio.
    if (chiusura.field === "sp16g_altri_debiti_breve") {
      corrected.sp16_debiti_breve = Math.round(((corrected.sp16_debiti_breve ?? 0) + chiusura.delta) * 100) / 100;
    }
    nextLog.push({
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      edited_field: chiusura.field,
      edited_label: chiusura.label,
      edit_delta: chiusura.delta,
      counterpart_field: "_correzione_import",
      counterpart_label: "Correzione importazione",
      counterpart_delta: 0,
      explanation: chiusura.explanation,
      created_at: new Date().toISOString(),
    });
  }
  if (!confirmed) nextLog.push({
    id: `confirm-${year}-${periodMonths ?? 12}`,
    entry_type: "confirm",
    edited_field: "",
    edited_label: "Rettifiche confermate",
    edit_delta: 0,
    counterpart_field: "",
    counterpart_label: "",
    counterpart_delta: 0,
    created_at: new Date().toISOString(),
  });
  return { kind: "save", values: corrected, log: nextLog, closedAmount: chiusura ? Math.abs(chiusura.delta) : null };
}
