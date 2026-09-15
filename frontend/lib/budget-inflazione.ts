/**
 * L'inflazione attesa del passo 1 e le caselle «automatiche» della parte fissa del passo 3
 * (spec 2026-09-15 §4.1, §4.3, decisione 2). Modulo puro.
 *
 * Una casella e' automatica (`fixed_*_growth_auto`) finche' l'utente non la scrive: segue
 * l'inflazione, e cambia con lei. Il motore legge SOLO `fixed_*_growth_pct`: il flag e' un
 * marcatore del client, persistito perche' lo scenario si riapra come era.
 *
 * `INFLAZIONE_PREDEFINITA` vive qui: `budget-migrazione.ts` (Task 9) la importa da qui invece
 * di tenerne una copia propria — un solo valore, mai due definizioni che potrebbero divergere.
 */
import type { AssumptionsMap } from "@/lib/budget-horizon";
import { calculateTrend, type HistoricalData } from "@/lib/budget-trend";
import { num } from "@/lib/budget-format";

export const INFLAZIONE_PREDEFINITA = 2;

export function inflazioneOf(map: AssumptionsMap, years: number[]): number {
  const raw = years[0] !== undefined ? map[years[0]]?.inflation_pct : null;
  return raw === null || raw === undefined ? INFLAZIONE_PREDEFINITA : num(raw);
}

export function applicaInflazioneAlleAuto(map: AssumptionsMap, years: number[]): AssumptionsMap {
  const infl = inflazioneOf(map, years);
  let out: AssumptionsMap | null = null;
  for (const y of years) {
    const r = map[y];
    if (!r) continue;
    const patch: Record<string, unknown> = {};
    if (r.fixed_materials_growth_auto && num(r.fixed_materials_growth_pct ?? 0) !== infl) patch.fixed_materials_growth_pct = infl;
    if (r.fixed_services_growth_auto && num(r.fixed_services_growth_pct ?? 0) !== infl) patch.fixed_services_growth_pct = infl;
    if (Object.keys(patch).length === 0) continue;
    out ??= { ...map };
    out[y] = { ...r, ...patch };
  }
  return out ?? map;
}

export function withInflazione(map: AssumptionsMap, years: number[], v: number): AssumptionsMap {
  const out: AssumptionsMap = { ...map };
  for (const y of years) if (out[y]) out[y] = { ...out[y], inflation_pct: v };
  return applicaInflazioneAlleAuto(out, years);
}

export function trendRicaviNota(historicalYears: number[], historical: HistoricalData): string | null {
  if (historicalYears.length < 2) return null;
  const y1 = historicalYears[historicalYears.length - 2], y2 = historicalYears[historicalYears.length - 1];
  const t = calculateTrend(historical, y1, y2, (i) => parseFloat(i.ce01_ricavi_vendite));
  if (t === null) return null;
  const pct = `${t >= 0 ? "+" : ""}${t.toLocaleString("it-IT", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%`;
  return `Per riferimento: tendenza storica ${y1}-${y2} dei ricavi ${pct} annuo. Non viene applicata.`;
}
