/**
 * Le decisioni del passo 7 «Imposte» (spec 2026-09-08 §4.7), l'ultimo del
 * percorso: la lettura/scrittura dell'aliquota forzata (un solo input,
 * scritto su tutti gli anni con `updateAll`) e la composizione
 * dell'anteprima. Stesso schema di `lib/budget-pregresso-step.ts` (Task 12):
 * niente di questo si decide dentro `StepImposte.tsx`.
 *
 * Le imposte NON si ricalcolano qui: le produce il motore
 * (`calculations/forecast_engine.py`), `rowsImposte` le legge dal CE che il
 * motore ha gia' scritto.
 */
import type { BalanceSheet, ForecastPreviewResponse, IncomeStatement } from "@/types/api";
import type { AssumptionsMap } from "@/lib/budget-horizon";
import { formatCurrency } from "@/lib/formatters";
import { singleYearValue, type SingleYearValue } from "@/lib/budget-pregresso-step";
import { rowsImposte, type PreviewRow } from "@/lib/budget-preview-rows";

/** `null`/assente restano `null`: zero vero e assenza non sono la stessa cosa. */
const numOrNull = (v: unknown): number | null => {
  if (v === null || v === undefined || v === "") return null;
  const n = typeof v === "number" ? v : parseFloat(String(v));
  return Number.isFinite(n) ? n : null;
};

const euro = (v: number | null): string => (v === null ? "—" : formatCurrency(v));

/**
 * L'aliquota reale del progetto: IRES + IRAP, non il `24` (sola IRES) di
 * default nello schema Pydantic (CLAUDE.md § Tax rate; `lib/budget-horizon.ts`
 * la scrive gia' cosi' su un'ipotesi nuova). La colonna `tax_rate` e' NOT
 * NULL: una casella lasciata vuota non puo' scrivere `null` come le altre
 * percentuali nullable, scrive questo valore esplicitamente.
 */
export const DEFAULT_TAX_RATE = 27.9;

/** Il valore del campo `tax_rate`, con lo stesso schema "primo anno previsto
 *  + disallineamento" di `singleYearValue`. */
export function taxRateValue(assumptions: AssumptionsMap, years: number[]): SingleYearValue {
  return singleYearValue(assumptions, years, "tax_rate");
}

/**
 * Che cosa mostrare nella casella dell'aliquota forzata: vuota quando il
 * valore e' il default 27,9 (cosi' la casella si legge come "non forzata",
 * anche se la colonna non ammette `null`), altrimenti il numero salvato.
 */
export function taxRateInputDisplay(v: SingleYearValue): number | "" {
  return v.value === null || v.value === DEFAULT_TAX_RATE ? "" : v.value;
}

export interface SpTributariRow {
  field: string;
  label: string;
  baseLabel: string;
}

/**
 * Le due righe della card «Pagamento dei debiti tributari»: a differenza
 * delle voci del passo 6 (finanziamento e investimenti nuovi, senza analogo
 * nell'anno base), `sp16e`/`sp17e` ESISTONO gia' nel bilancio base — la
 * colonna base porta l'importo vero, non un trattino.
 */
export function spTributariRows(baseBs: BalanceSheet | undefined | null): SpTributariRow[] {
  const bs = baseBs as unknown as Record<string, unknown> | null | undefined;
  const b = (field: string): number | null => (bs ? numOrNull(bs[field]) : null);
  return [
    { field: "sp16e_growth_pct", label: "Debiti tributari entro %", baseLabel: euro(b("sp16e_debiti_tributari_breve")) },
    { field: "sp17e_growth_pct", label: "Debiti tributari oltre %", baseLabel: euro(b("sp17e_debiti_tributari_lungo")) },
  ];
}

export interface ImpostePreview {
  /** Gli anni che il motore ha davvero prodotto, non quelli richiesti. */
  years: number[];
  rows: PreviewRow[];
}

const EMPTY_PREVIEW: ImpostePreview = { years: [], rows: [] };

/**
 * Dalla risposta del motore a tutto cio' che l'anteprima del passo rende.
 * Senza anno base o senza risposta non c'e' anteprima: nessuna riga, non
 * righe a zero. Gli anni sono quelli che il motore ha davvero prodotto — se
 * si e' fermato a meta' (fabbisogno scoperto al passo 6) la 200 porta gli
 * anni validi ed e' su quelli che le imposte si mostrano.
 */
export function impostePreview(
  baseInc: IncomeStatement | undefined | null,
  data: ForecastPreviewResponse | null
): ImpostePreview {
  if (!baseInc || !data) return EMPTY_PREVIEW;
  const previewYears = data.forecast_years ?? [];
  return { years: previewYears.map((y) => y.year), rows: rowsImposte(baseInc, previewYears) };
}
