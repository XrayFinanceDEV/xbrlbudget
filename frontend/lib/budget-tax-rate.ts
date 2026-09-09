/**
 * L'aliquota che il piano usera' davvero, e da dove viene.
 *
 * Perche' esiste: prima di questo modulo la stessa domanda aveva due
 * risposte. Sul caso «aliquota effettiva dell'anno base non derivabile» il
 * passo 4 mostrava `27,9%` come se fosse un calcolo (`effectiveTaxRateLabel`
 * sostituiva il `null` col default e formattava), mentre il passo 7 mostrava
 * `—`; e nessuno dei due teneva conto di un `tax_rate` forzato dall'utente.
 * Ora entrambi i passi rendono da qui, quindi non possono piu' discordare.
 * E' lo stesso rimedio gia' applicato in questo lotto a `ceAggregates` e a
 * `computeAutoDays`.
 *
 * Il dominio, verificato sul motore
 * (`calculations/forecast_engine.py:_tax_components`): `tax_rate` e' un
 * FALLBACK. Se l'anno base ha un'aliquota effettiva derivabile (imposte > 0,
 * utile ante imposte > 0, rapporto <= 60%) il motore usa quella e ignora il
 * valore forzato; solo quando l'effettiva non e' derivabile guarda
 * `tax_rate`, che nello schema e' NOT NULL e vale 27,9 (IRES + IRAP) su
 * un'ipotesi nuova.
 *
 * Invariante: un default non si presenta MAI come un valore calcolato.
 * `label` porta la provenienza attaccata a ogni aliquota che non sia
 * l'effettiva dell'anno base.
 *
 * Un solo motore di proiezione, e sta in Python: qui non si calcola nessuna
 * imposta, si dichiara solo QUALE aliquota il motore applichera' e perche'.
 */
import type { AssumptionsMap } from "@/lib/budget-horizon";
import { formatPercentage } from "@/lib/formatters";
import { DEFAULT_TAX_RATE, taxRateValue } from "@/lib/budget-imposte-step";

export type TaxRateSource = "effettiva" | "forzata" | "predefinita";

export interface PlanTaxRate {
  /** L'aliquota in percentuale assoluta (27,9 = 27,9%). */
  ratePct: number;
  source: TaxRateSource;
  /** Solo la percentuale formattata: "25,0%". */
  value: string;
  /** La provenienza in chiaro, mai vuota. */
  sourceLabel: string;
  /** Valore + provenienza quando NON e' l'effettiva dell'anno base: cosi' un
   *  default non puo' passare per un calcolo. */
  label: string;
  /** L'aliquota forzata che il motore ignorera' perche' l'effettiva vince,
   *  oppure `null`. */
  ignoredForcedPct: number | null;
  /** La spiegazione da mostrare accanto al valore, o `null` quando non c'e'
   *  nulla da spiegare (aliquota effettiva, nessun valore forzato). */
  nota: string | null;
}

const pct1 = (v: number): string => formatPercentage(v / 100, 1);

/**
 * L'aliquota davvero FORZATA dall'utente, o `null`.
 *
 * La colonna `tax_rate` e' NOT NULL: un'ipotesi non forzata porta comunque il
 * 27,9 di default. Vale quindi come "non forzata" tanto l'assenza quanto il
 * default — la stessa lettura che fa `taxRateInputDisplay` per lasciare la
 * casella vuota, e tenerle d'accordo e' il punto.
 */
function forcedTaxRate(assumptions: AssumptionsMap, forecastYears: number[]): number | null {
  const v = taxRateValue(assumptions, forecastYears);
  return v.value === null || v.value === DEFAULT_TAX_RATE ? null : v.value;
}

/**
 * L'aliquota che il piano usera', la sua provenienza e le etichette da
 * mostrare. `effectiveRatePct` e' l'aliquota effettiva dell'anno base
 * (`computeEffectiveTaxRate`, `components/budget/assumption-rows.ts`), gia'
 * `null` quando l'anno base e' in perdita, ha imposte a zero o esprime
 * un'aliquota implicita oltre il 60% — questo modulo sta in `lib/` e non puo'
 * importarla, quindi la riceve.
 */
export function planTaxRate(
  effectiveRatePct: number | null,
  assumptions: AssumptionsMap,
  forecastYears: number[],
): PlanTaxRate {
  const forced = forcedTaxRate(assumptions, forecastYears);

  if (effectiveRatePct !== null) {
    return {
      ratePct: effectiveRatePct,
      source: "effettiva",
      value: pct1(effectiveRatePct),
      sourceLabel: "effettiva dell'anno base",
      label: pct1(effectiveRatePct),
      ignoredForcedPct: forced,
      nota:
        forced === null
          ? null
          : `L'aliquota forzata (${pct1(forced)}) non viene usata: quando l'anno base ha un'aliquota effettiva, il motore applica quella.`,
    };
  }

  if (forced !== null) {
    return {
      ratePct: forced,
      source: "forzata",
      value: pct1(forced),
      sourceLabel: "forzata nelle ipotesi",
      label: `${pct1(forced)} · forzata nelle ipotesi`,
      ignoredForcedPct: null,
      nota: "L'anno base non esprime un'aliquota effettiva: il piano usa il valore forzato qui sotto.",
    };
  }

  return {
    ratePct: DEFAULT_TAX_RATE,
    source: "predefinita",
    value: pct1(DEFAULT_TAX_RATE),
    sourceLabel: "predefinita, non calcolata",
    label: `${pct1(DEFAULT_TAX_RATE)} · predefinita, non calcolata`,
    ignoredForcedPct: null,
    nota: `L'anno base non esprime un'aliquota effettiva e nessun valore e' stato forzato: il piano usa il predefinito ${pct1(DEFAULT_TAX_RATE)} (IRES + IRAP).`,
  };
}
