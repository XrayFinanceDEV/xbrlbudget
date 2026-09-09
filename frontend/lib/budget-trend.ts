// Historical-trend helpers for the budget assumptions Auto-Generator.
// calculateTrend / TREND_ITEMS moved verbatim from app/budget/page.tsx;
// blendedRate is the blend formula from the same file, extracted so both
// AutoGeneratorCard (interactive) and trendAssumptions (batch) share it.
import type { BalanceSheet, IncomeStatement } from "@/types/api";

export type HistoricalData = Record<number, { income: IncomeStatement; balance: BalanceSheet }>;

export function calculateTrend(
  historicalData: HistoricalData,
  year1: number,
  year2: number,
  getValue: (income: IncomeStatement) => number
): number | null {
  const d1 = historicalData[year1];
  const d2 = historicalData[year2];
  if (!d1?.income || !d2?.income) return null;
  const v1 = getValue(d1.income);
  const v2 = getValue(d2.income);
  if (v1 === 0) return null;
  return ((v2 - v1) / Math.abs(v1)) * 100;
}

export const TREND_ITEMS: {
  label: string;
  fields: string[];
  getValue: (i: IncomeStatement) => number;
}[] = [
  { label: "Ricavi", fields: ["revenue_growth_pct"], getValue: (i) => parseFloat(i.ce01_ricavi_vendite) },
  { label: "Altri ricavi", fields: ["other_revenue_growth_pct"], getValue: (i) => parseFloat(i.ce04_altri_ricavi) },
  { label: "Materie prime", fields: ["variable_materials_growth_pct", "fixed_materials_growth_pct"], getValue: (i) => Math.abs(parseFloat(i.ce05_materie_prime)) },
  { label: "Servizi", fields: ["variable_services_growth_pct", "fixed_services_growth_pct"], getValue: (i) => Math.abs(parseFloat(i.ce06_servizi)) },
  { label: "Godimento beni", fields: ["rent_growth_pct"], getValue: (i) => Math.abs(parseFloat(i.ce07_godimento_beni)) },
  { label: "Personale", fields: ["personnel_growth_pct"], getValue: (i) => Math.abs(parseFloat(i.ce08_costi_personale)) },
  { label: "Oneri diversi", fields: ["other_costs_growth_pct"], getValue: (i) => Math.abs(parseFloat(i.ce12_oneri_diversi)) },
];

/** Tasso smussato per l'anno all'indice `index` di un piano di `n` anni:
 *  parte dalla media fra tendenza e inflazione, converge linearmente
 *  all'inflazione entro l'ultimo anno. `trend === null` -> parte dall'inflazione. */
export function blendedRate(trend: number | null, inflation: number, index: number, n: number): number {
  const blended = trend !== null ? (trend + inflation) / 2 : inflation;
  if (n === 1) return Math.round(blended * 100) / 100;
  const weight = index / (n - 1);
  return Math.round((blended * (1 - weight) + inflation * weight) * 100) / 100;
}

/**
 * Si puo' precompilare uno scenario nuovo dalla tendenza storica?
 *
 * Il cancello guarda la PRESENZA DEI DATI, non l'ampiezza dell'elenco degli
 * anni. `historicalYears` deriva dal prop `years` (`GET /companies/{id}/years`)
 * ed e' gia' pieno al primo render, mentre `historical` arriva da 2xN richieste
 * in serie che chiamano `setHistoricalData` una volta sola alla fine: chi
 * guardava `historicalYears.length >= 2` faceva partire il seed con
 * `historical` ancora vuoto — `trendAssumptions` senza dati scrive l'inflazione
 * su ogni campo — e il flag one-shot impediva per sempre la ripetizione. Lo
 * scenario nasceva cosi' con tutte le voci al 2%, e il percorso reale (la
 * Stampa crea lo scenario senza ipotesi e apre il wizard su `isNew`) passa
 * esattamente di li'.
 *
 * Servono i DUE anni che `trendAssumptions` legge davvero: gli ultimi due
 * dell'elenco. Uno solo — o nessuno — non e' una tendenza.
 */
export function shouldSeedTrend(
  isNew: boolean,
  historicalYears: number[],
  historical: HistoricalData,
): boolean {
  if (!isNew || historicalYears.length < 2) return false;
  const year1 = historicalYears[historicalYears.length - 2];
  const year2 = historicalYears[historicalYears.length - 1];
  return Boolean(historical[year1]?.income && historical[year2]?.income);
}

/** trendAssumptions: TREND_ITEMS x forecastYears, ogni campo scritto con blendedRate. */
export function trendAssumptions(
  historicalYears: number[],
  forecastYears: number[],
  historicalData: HistoricalData,
  inflation: number
): Record<number, Record<string, number>> {
  const hasTwoYears = historicalYears.length >= 2;
  const year1 = hasTwoYears ? historicalYears[historicalYears.length - 2] : 0;
  const year2 = hasTwoYears ? historicalYears[historicalYears.length - 1] : 0;
  const n = forecastYears.length;

  const out: Record<number, Record<string, number>> = {};
  for (const year of forecastYears) out[year] = {};

  for (const item of TREND_ITEMS) {
    const trend = hasTwoYears ? calculateTrend(historicalData, year1, year2, item.getValue) : null;
    forecastYears.forEach((year, i) => {
      const rate = blendedRate(trend, inflation, i, n);
      for (const field of item.fields) out[year][field] = rate;
    });
  }

  return out;
}
