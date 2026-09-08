/**
 * Le decisioni del passo 5 «Capitale circolante» (spec 2026-09-08 §4.5,
 * task-13-brief.md).
 *
 * Sta in `lib/` per lo stesso motivo di `budget-costi-step.ts` (Task 12) e
 * `budget-altre-voci-step.ts` (Task 13): nessun jsdom in questo repo, quindi
 * ogni decisione — quale giorno "auto" mostrare, quale importo base ha una
 * voce minore, con quale anno leggere gli interruttori — vive qui con la
 * sua suite `environment: node`, e `StepCircolante.tsx` si limita a
 * renderlo.
 *
 * I tre campi giorni sono annullabili: vuoto significa "usa il valore
 * derivato dall'anno base" (`computeAutoDays`, gia' in lib/budget-turnover.ts
 * — QUELLA funzione, mai una formula nuova: il segnaposto `auto:` prometteva
 * 122 giorni dove il motore ne applicava 116, ed e' il difetto per cui
 * `computeAutoDays` esiste). Un solo motore di proiezione, e sta in Python:
 * l'anteprima del circolante e' lettura pura di `rowsCircolante`, mai un
 * ricalcolo qui.
 */
import { computeAutoDays } from "@/lib/budget-turnover";
import type { AssumptionsMap } from "@/lib/budget-horizon";
import { formatCurrency } from "@/lib/formatters";
import { rowsCircolante, type PreviewRow } from "@/lib/budget-preview-rows";
import type { BalanceSheet, ForecastPreviewResponse, IncomeStatement } from "@/types/api";

/** `null`/assente restano `null`: zero vero e assenza non sono la stessa cosa. */
const numOrNull = (v: unknown): number | null => {
  if (v === null || v === undefined || v === "") return null;
  const n = typeof v === "number" ? v : parseFloat(String(v));
  return Number.isFinite(n) ? n : null;
};

const euro = (v: number | null): string => (v === null ? "—" : formatCurrency(v));

/**
 * Riga della tabella, forma strutturalmente compatibile con `YearInputRow`
 * di `components/budget/wizard/YearInputTable` — dichiarata qui perche'
 * `lib/` non importa da `components/` (stesso schema di `CostiTableRow`).
 */
export interface CircolanteTableRow {
  field: string;
  label: string;
  baseLabel: string;
  placeholder?: (year: number) => string;
}

export interface GiorniMedi {
  dso: number | null;
  dio: number | null;
  dpo: number | null;
}

/** I tre giorni "auto" derivati dall'anno base — la stessa `computeAutoDays`
 *  del motore, mai una formula propria. `null` quando l'anno base manca o
 *  il denominatore e' zero: in quel caso il campo resta senza placeholder,
 *  non con "auto 0". */
export function giorniMediAuto(
  baseInc: IncomeStatement | undefined | null,
  baseBs: BalanceSheet | undefined | null,
): GiorniMedi {
  return {
    dso: computeAutoDays("dso", baseInc ?? undefined, baseBs ?? undefined),
    dio: computeAutoDays("dio", baseInc ?? undefined, baseBs ?? undefined),
    dpo: computeAutoDays("dpo", baseInc ?? undefined, baseBs ?? undefined),
  };
}

const dayLabel = (n: number | null): string => (n === null ? "n/d" : `${n} gg`);
const autoPlaceholder = (n: number | null) => () => (n === null ? "auto" : `auto ${n}`);

/** Le tre righe "Giorni medi": DSO, DIO, DPO. */
export function giorniMediRows(auto: GiorniMedi): CircolanteTableRow[] {
  return [
    { field: "dso_days", label: "Giorni incasso clienti (DSO)", baseLabel: dayLabel(auto.dso), placeholder: autoPlaceholder(auto.dso) },
    { field: "dio_days", label: "Giorni rotazione magazzino (DIO)", baseLabel: dayLabel(auto.dio), placeholder: autoPlaceholder(auto.dio) },
    { field: "dpo_days", label: "Giorni pagamento fornitori (DPO)", baseLabel: dayLabel(auto.dpo), placeholder: autoPlaceholder(auto.dpo) },
  ];
}

/** Le 14 voci minori dell'attivo e del passivo: ciascuna segue una propria
 *  crescita %, non una rotazione — nessun giorno, solo l'importo base. */
export function minorFieldsRows(baseBs: BalanceSheet | undefined | null): CircolanteTableRow[] {
  const b = (k: string) => euro(baseBs ? numOrNull((baseBs as unknown as Record<string, unknown>)[k]) : null);
  return [
    { field: "receivables_long_growth_pct", label: "Crediti oltre 12 mesi", baseLabel: b("sp07_crediti_lungo") },
    { field: "sp01_growth_pct", label: "Crediti verso soci", baseLabel: b("sp01_crediti_soci") },
    { field: "sp04_growth_pct", label: "Immobilizzazioni finanziarie", baseLabel: b("sp04_immob_finanziarie") },
    { field: "sp06e_growth_pct", label: "Crediti tributari", baseLabel: b("sp06e_crediti_tributari_breve") },
    { field: "sp06f_growth_pct", label: "Imposte anticipate", baseLabel: b("sp06f_imposte_anticipate_breve") },
    { field: "sp08_growth_pct", label: "Attività finanziarie", baseLabel: b("sp08_attivita_finanziarie") },
    { field: "sp10_growth_pct", label: "Ratei e risconti attivi", baseLabel: b("sp10_ratei_risconti_attivi") },
    { field: "sp14_growth_pct", label: "Fondi per rischi e oneri", baseLabel: b("sp14_fondi_rischi") },
    { field: "sp16f_growth_pct", label: "Debiti previdenziali entro", baseLabel: b("sp16f_debiti_previdenza_breve") },
    { field: "sp16g_growth_pct", label: "Altri debiti entro", baseLabel: b("sp16g_altri_debiti_breve") },
    { field: "sp17d_growth_pct", label: "Debiti fornitori oltre", baseLabel: b("sp17d_debiti_fornitori_lungo") },
    { field: "sp17f_growth_pct", label: "Debiti previdenziali oltre", baseLabel: b("sp17f_debiti_previdenza_lungo") },
    { field: "sp17g_growth_pct", label: "Altri debiti oltre", baseLabel: b("sp17g_altri_debiti_lungo") },
    { field: "sp18_growth_pct", label: "Ratei e risconti passivi", baseLabel: b("sp18_ratei_risconti_passivi") },
  ];
}

export type BoolAssumptionField = "previdenza_scales_with_personnel" | "tfr_accrual_suspended";

/**
 * Un interruttore e' un'ipotesi PER ANNO — il motore la applica riga per
 * riga — ma il checkbox e' uno solo: si mostra quello del primo anno
 * previsto (stesso criterio di `fixedShareOf` in budget-costi-step.ts).
 * Assente ⇒ `false`, il default del motore (database/models.py).
 */
export function boolAssumption(assumptions: AssumptionsMap, forecastYears: number[], field: BoolAssumptionField): boolean {
  return Boolean(assumptions[forecastYears[0]]?.[field]);
}

export interface CircolantePreview {
  /** Gli anni che il motore ha davvero prodotto, non quelli richiesti. */
  years: number[];
  rows: PreviewRow[];
}

const EMPTY_PREVIEW: CircolantePreview = { years: [], rows: [] };

/** Dalla risposta del motore alle righe dell'anteprima. Senza anno base
 *  (SP o CE) o senza risposta non c'e' anteprima: nessuna riga, non righe
 *  a zero. */
export function circolantePreview(
  baseBs: BalanceSheet | undefined | null,
  baseInc: IncomeStatement | undefined | null,
  data: ForecastPreviewResponse | null,
): CircolantePreview {
  if (!baseBs || !baseInc || !data) return EMPTY_PREVIEW;
  const previewYears = data.forecast_years ?? [];
  return { years: previewYears.map((y) => y.year), rows: rowsCircolante(baseBs, baseInc, previewYears) };
}
