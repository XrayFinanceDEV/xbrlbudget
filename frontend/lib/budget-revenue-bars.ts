/**
 * Geometria delle barre del mini-grafico ricavi di `StepFatturato` (Task 11
 * §2): solo scala e altezza, nessuna cifra nuova — i valori sono quelli
 * gia' mostrati altrove nel passo (base + `p.preview.data.forecast_years`).
 * L'unica aritmetica lecita nel client ricapitola ciò che è già a schermo, e
 * per questo sta qui in `lib/`, mai dentro il componente SVG.
 */
import type { ForecastPreviewYear } from "@/types/api";
import { num } from "@/lib/budget-format";

export interface RevenueBarGeometry { value: number; height: number; y: number; isBase: boolean }

const VIEWPORT_HEIGHT = 56;

/**
 * Un rettangolo per valore (base compresa), altezza proporzionale sulla
 * scala `[min*0.9, max*1.05]` del brief. Con un solo valore, o un intervallo
 * degenere (tutti i valori uguali), la scala avrebbe ampiezza zero: la barra
 * riempie allora tutta l'altezza invece di sparire per una divisione per
 * zero.
 */
export function revenueBarGeometry(base: number, years: ForecastPreviewYear[]): RevenueBarGeometry[] {
  const values = [base, ...years.map((y) => num(y.income_statement.ce01_ricavi_vendite))];
  const min = Math.min(...values) * 0.9;
  const max = Math.max(...values) * 1.05;
  const span = max - min;
  return values.map((value, i) => {
    const height = span > 0 ? ((value - min) / span) * VIEWPORT_HEIGHT : VIEWPORT_HEIGHT;
    return { value, height, y: VIEWPORT_HEIGHT - height, isBase: i === 0 };
  });
}
