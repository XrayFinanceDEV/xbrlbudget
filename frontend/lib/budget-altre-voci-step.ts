/**
 * Le decisioni del passo 4 «Altre voci CE» (spec 2026-09-08 §4.4, task-13-brief.md).
 *
 * Sta in `lib/` e non dentro il componente per lo stesso motivo di
 * `budget-costi-step.ts` (Task 12): qui i componenti non sono collaudabili
 * (nessun jsdom, e non va aggiunto), quindi tutto cio' che *decide* qualcosa —
 * quali anni mostrare, che valore va sotto "Ammortamenti"/"Oneri finanziari",
 * su quale aliquota cade il fallback — vive qui con la sua suite in
 * `environment: node`, e `StepAltreVociCE.tsx` si limita a renderlo.
 *
 * Un solo motore di proiezione, e sta in Python: le tre righe "calcolate dal
 * piano" sono lettura pura di numeri che il motore ha gia' restituito
 * (`ce09_ammortamenti`, `ce15_oneri_finanziari` dell'ultimo anno
 * dell'anteprima), mai un ricalcolo.
 *
 * L'unica formula che NON viene dal motore e' l'aliquota effettiva
 * dell'anno base: la calcola `computeEffectiveTaxRate`
 * (components/budget/assumption-rows.ts, che a sua volta usa `ceAggregates`
 * di lib/budget-preview-rows.ts). Questo modulo non puo' importarla — `lib/`
 * non importa da `components/` — quindi il componente la calcola e passa
 * qui solo il numero (o `null`) da formattare.
 */
import type { AssumptionsMap } from "@/lib/budget-horizon";
import { formatCurrency, formatPercentage } from "@/lib/formatters";
import { rowsAltreVociCe, type PreviewRow } from "@/lib/budget-preview-rows";
import type { ForecastPreviewResponse, IncomeStatement } from "@/types/api";

const num = (v: unknown): number => {
  const n = typeof v === "number" ? v : parseFloat(String(v ?? ""));
  return Number.isFinite(n) ? n : 0;
};

/** `null`/assente restano `null`: zero vero e assenza non sono la stessa cosa. */
const numOrNull = (v: unknown): number | null => {
  if (v === null || v === undefined || v === "") return null;
  const n = typeof v === "number" ? v : parseFloat(String(v));
  return Number.isFinite(n) ? n : null;
};

const euro = (v: number | null): string => (v === null ? "—" : formatCurrency(v));

/** L'aliquota reale del motore (CLAUDE.md: 27,9 = IRES + IRAP, non il 24 di
 *  schema) quando quella effettiva dell'anno base non e' derivabile. */
const DEFAULT_TAX_RATE_PCT = 27.9;

/** Default di schema di `depreciation_rate` (database/models.py:649) per un
 *  anno che il passo 6 non ha ancora idratato. */
const DEFAULT_DEPRECIATION_RATE_PCT = 20;

/**
 * Riga della tabella "Voci minori", forma strutturalmente compatibile con
 * `YearInputRow` di `components/budget/wizard/YearInputTable` — dichiarata
 * qui perche' `lib/` non importa da `components/` (stesso schema di
 * `CostiTableRow` in budget-costi-step.ts).
 */
export interface AltreVociTableRow {
  field: string;
  label: string;
  baseLabel: string;
}

/** La sola riga della card "Voci minori · variazione %": `other_costs_growth_pct`
 *  su ce12. Anno base assente ⇒ "—", mai "€ 0". */
export function altreVociTableRows(baseInc: IncomeStatement | undefined | null): AltreVociTableRow[] {
  const base = baseInc ? numOrNull((baseInc as unknown as Record<string, unknown>).ce12_oneri_diversi) : null;
  return [{ field: "other_costs_growth_pct", label: "Altri costi (oneri diversi)", baseLabel: euro(base) }];
}

export interface BaseToLast {
  base: number | null;
  /** null finche' l'anteprima non ha ancora un ultimo anno. */
  last: number | null;
}

/** Il valore di un campo del CE nell'anno base e nell'ultimo anno
 *  dell'anteprima: pura lettura, nessuna formula. */
function baseToLastIncomeField(baseValue: unknown, previewYears: ForecastPreviewResponse["forecast_years"], field: string): BaseToLast {
  const lastYear = previewYears[previewYears.length - 1];
  return {
    base: numOrNull(baseValue),
    last: lastYear ? num((lastYear.income_statement as unknown as Record<string, unknown>)[field]) : null,
  };
}

function arrowLabel(r: BaseToLast): string {
  return r.last === null ? euro(r.base) : `${euro(r.base)} → ${euro(r.last)}`;
}

/** Etichetta dell'aliquota effettiva, o il fallback del motore (27,9%,
 *  CLAUDE.md) quando l'anno base non la rende derivabile. Le percentuali
 *  sono assolute: si divide per 100 per `formatPercentage`, come gia' fa
 *  `describeCell`. */
export function effectiveTaxRateLabel(effectiveRatePct: number | null): string {
  return formatPercentage((effectiveRatePct ?? DEFAULT_TAX_RATE_PCT) / 100, 1);
}

/**
 * La quota di ammortamento sui nuovi investimenti da mostrare in nota:
 * quella del primo anno di previsione (stesso "il primo anno rappresenta
 * tutti" di `fixedShareOf` in budget-costi-step.ts), o il default di schema
 * se quell'anno non e' ancora stato idratato dal passo 6. Un valore a 0
 * esplicito resta 0, non il default.
 */
function depreciationRateForNote(assumptions: AssumptionsMap, forecastYears: number[]): number {
  const raw = assumptions[forecastYears[0]]?.depreciation_rate;
  return raw === null || raw === undefined ? DEFAULT_DEPRECIATION_RATE_PCT : num(raw);
}

export interface CalculatedRow {
  small: string;
  value: string;
}

export interface AltreVociCalculated {
  ammortamenti: CalculatedRow;
  oneriFinanziari: CalculatedRow;
  imposte: CalculatedRow;
}

/**
 * Le tre righe della card "Calcolate dal piano". `effectiveTaxRatePct' e'
 * gia' calcolato dal chiamante (vedi il commento in testa al file sul
 * perche' questo modulo non puo' calcolarlo da solo).
 */
export function altreVociCalculated(
  baseYear: number,
  baseInc: IncomeStatement | undefined | null,
  effectiveTaxRatePct: number | null,
  assumptions: AssumptionsMap,
  forecastYears: number[],
  data: ForecastPreviewResponse | null,
): AltreVociCalculated {
  const previewYears = data?.forecast_years ?? [];
  const amm = baseToLastIncomeField(baseInc ? (baseInc as unknown as Record<string, unknown>).ce09_ammortamenti : null, previewYears, "ce09_ammortamenti");
  const oneri = baseToLastIncomeField(baseInc ? (baseInc as unknown as Record<string, unknown>).ce15_oneri_finanziari : null, previewYears, "ce15_oneri_finanziari");
  const deprRate = depreciationRateForNote(assumptions, forecastYears);
  return {
    ammortamenti: {
      small: `quote sul ${baseYear} più il ${formatPercentage(deprRate / 100, 0)} dei nuovi investimenti (passo 6)`,
      value: arrowLabel(amm),
    },
    oneriFinanziari: { small: "sul debito del passo 6", value: arrowLabel(oneri) },
    imposte: { small: "aliquota del passo 7", value: effectiveTaxRateLabel(effectiveTaxRatePct) },
  };
}

export interface AltreVociPreview {
  /** Gli anni che il motore ha davvero prodotto, non quelli richiesti:
   *  se si e' fermato a meta' la 200 porta gli anni validi, e sono quelli
   *  che si mostrano — mai colonne richieste riempite di vuoto. */
  years: number[];
  rows: PreviewRow[];
}

const EMPTY_PREVIEW: AltreVociPreview = { years: [], rows: [] };

/** Dalla risposta del motore alle righe dell'anteprima. Senza anno base o
 *  senza risposta non c'e' anteprima: nessuna riga, non righe a zero. */
export function altreVociPreview(baseInc: IncomeStatement | undefined | null, data: ForecastPreviewResponse | null): AltreVociPreview {
  if (!baseInc || !data) return EMPTY_PREVIEW;
  const previewYears = data.forecast_years ?? [];
  return { years: previewYears.map((y) => y.year), rows: rowsAltreVociCe(baseInc, previewYears) };
}
