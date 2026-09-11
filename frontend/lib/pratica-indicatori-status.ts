/**
 * Indicatori dell'infrannuale (tab «Indicatori» del percorso Pratica): tre stati
 * distinti, non due. `app/pratica/page.tsx` collassava "lettura fallita" e "proiezione
 * non ancora generata" sullo stesso messaggio ("Genera prima la proiezione nel
 * passaggio 3."), perche' in entrambi i casi `analysis` restava `null` — un errore di
 * rete veniva riletto come "l'utente non ha ancora fatto il passo 3" (rilievo 4 del
 * collaudo del lotto 2,
 * `.superpowers/sdd/2026-09-08-scadenziamento-pregresso/task-10-report-parte1.md`
 * righe 380-403).
 *
 * `GET /analysis` risponde 200 con `forecast_years: []` quando non e' stata ancora
 * generata alcuna proiezione (non solleva, `backend/app/services/analysis_service.py:99`):
 * la distinzione fra "non generato" e "letto ma vuoto" e' quindi la lunghezza di
 * `forecast_years`, non l'assenza di `analysis`.
 */
import type { IntraYearComparison, ScenarioAnalysis } from "@/types/api";

export type PraticaIndicatoriStatus = "caricamento" | "errore" | "non_generato" | "pronto";

export function praticaIndicatoriStatus(input: {
  loading: boolean;
  error: unknown;
  analysis: ScenarioAnalysis | null;
  comparison: IntraYearComparison | null;
}): PraticaIndicatoriStatus {
  if (input.loading) return "caricamento";
  if (input.error) return "errore";
  if (input.analysis && input.comparison && (input.analysis.forecast_years?.length ?? 0) > 0) {
    return "pronto";
  }
  return "non_generato";
}
