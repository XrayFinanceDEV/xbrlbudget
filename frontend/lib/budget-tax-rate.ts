/**
 * L'aliquota che il piano usera' davvero, e da dove viene.
 *
 * Dal 2026-09-18 (commercialista) la regola e' semplice, e verificata sul
 * motore (`calculations/forecast_engine.py:_tax_components`):
 *
 * 1. **`ce20_override`**: se c'e', quell'importo E' l'imposta totale
 *    dell'anno e **nessuna aliquota viene applicata**.
 * 2. **`tax_rate`**, cosi' com'e'. Il wizard lo propone dall'aliquota
 *    effettiva dell'ultimo bilancio annuale DEPOSITATO (mai un anno promosso
 *    dall'infrannuale), con ripiego sul 27,9 (IRES + IRAP) quando non e'
 *    derivabile — `GET /companies/{id}/years/{anno}/aliquota-proposta`, che
 *    tiene la regola in un posto solo. L'utente la tiene o la cambia.
 *
 * Prima l'aliquota effettiva dell'anno BASE vinceva in silenzio su quella
 * scritta: con un anno base promosso era l'aliquota della proiezione.
 *
 * Invariante: un'etichetta non dichiara MAI qualcosa che il motore non fa.
 * Qui non si calcola nessuna imposta, si dichiara solo QUALE aliquota il
 * motore applichera' e perche'.
 */
import type { AssumptionsMap } from "@/lib/budget-horizon";
import { pct1 } from "@/lib/budget-format";
import { DEFAULT_TAX_RATE, taxRateValue } from "@/lib/budget-imposte-step";

export type TaxRateSource = "proposta" | "scelta" | "sostituita";

/** La proposta del server: l'aliquota effettiva dell'ultimo consuntivo
 *  depositato e il suo anno, `anno: null` quando non derivabile (27,9). */
export interface AliquotaProposta {
  aliquota: number;
  anno: number | null;
}

export interface PlanTaxRate {
  /** L'aliquota in percentuale assoluta (27,9 = 27,9%), oppure `null` quando
   *  il motore non ne applica nessuna perche' l'imposta e' forzata a importo
   *  su **tutti** gli anni previsti. */
  ratePct: number | null;
  source: TaxRateSource;
  /** Solo la percentuale formattata: "25,0%". "—" quando non c'e' aliquota. */
  value: string;
  /** La provenienza in chiaro, mai vuota. */
  sourceLabel: string;
  /** Valore + provenienza. */
  label: string;
  /** Gli anni previsti su cui `ce20_override` sostituisce l'aliquota con un
   *  importo, e quanti sono in tutto. */
  overriddenYears: number[];
  totalYears: number;
  /** La spiegazione da mostrare accanto al valore, o `null`. */
  nota: string | null;
  /** L'aliquota del piano e' diversa dalla proposta: il passo offre di
   *  tornarci. `false` anche quando la proposta non e' ancora arrivata. */
  diversaDallaProposta: boolean;
}

/** La provenienza della proposta, in chiaro. */
export function propostaLabel(proposta: AliquotaProposta | null): string {
  if (!proposta) return "in caricamento";
  return proposta.anno !== null
    ? `effettiva del bilancio ${proposta.anno}`
    : `predefinita ${pct1(DEFAULT_TAX_RATE)} (IRES + IRAP): nessun bilancio depositato la esprime`;
}

/** Gli anni previsti su cui `ce20_override` sostituisce l'aliquota con un
 *  importo. `0` e' un override vero (imposte azzerate), non un'assenza. */
function overriddenTaxYears(assumptions: AssumptionsMap, forecastYears: number[]): number[] {
  return forecastYears.filter((y) => {
    const v = (assumptions[y] as Record<string, unknown> | undefined)?.ce20_override;
    return v !== null && v !== undefined && v !== "";
  });
}

/** Stessa cifra a un decimale: la proposta arriva a due decimali, la casella ne mostra uno. */
const stessa = (a: number, b: number) => Math.abs(a - b) < 0.05;

/**
 * L'aliquota che il piano usera', la sua provenienza e le etichette da
 * mostrare. `proposta` e' quella del server (`null` finche' non arriva).
 */
export function planTaxRate(
  proposta: AliquotaProposta | null,
  assumptions: AssumptionsMap,
  forecastYears: number[],
): PlanTaxRate {
  const scritta = taxRateValue(assumptions, forecastYears).value ?? DEFAULT_TAX_RATE;
  const overridden = overriddenTaxYears(assumptions, forecastYears);
  const totalYears = forecastYears.length;
  const daProposta = proposta !== null && stessa(scritta, proposta.aliquota);
  const sotto = daProposta
    ? { source: "proposta" as const, sourceLabel: `proposta · ${propostaLabel(proposta)}` }
    : { source: "scelta" as const, sourceLabel: "scelta nelle ipotesi" };
  const diversaDallaProposta = proposta !== null && !daProposta;

  // `ce20_override` batte tutto: su quegli anni il motore prende l'importo
  // come imposta totale e non applica NESSUNA aliquota.
  if (overridden.length > 0) {
    const tutti = overridden.length === totalYears;
    // «1 anni su 2» in un'interfaccia italiana e' un errore che l'utente legge.
    const anni = overridden.length === 1 ? "1 anno" : `${overridden.length} anni`;
    const quanti = tutti
      ? "su tutti gli anni previsti"
      : `su ${anni} su ${totalYears} (${overridden.join(", ")})`;
    const value = tutti ? "—" : pct1(scritta);
    const sourceLabel = tutti
      ? "sostituita da un importo forzato"
      : `sostituita in ${anni} su ${totalYears}`;
    return {
      ratePct: tutti ? null : scritta,
      source: "sostituita",
      value,
      sourceLabel,
      label: `${value} · ${sourceLabel}`,
      overriddenYears: overridden,
      totalYears,
      nota: tutti
        ? "Le imposte sono forzate a importo nel CE previsionale: il motore usa quell'importo e non applica nessuna aliquota. Si azzera dal dialogo Ricalcola."
        : `Le imposte sono forzate a importo nel CE previsionale ${quanti}: li' il motore usa quell'importo e non applica nessuna aliquota. Negli altri anni resta l'aliquota del piano, ${pct1(scritta)}.`,
      diversaDallaProposta,
    };
  }

  return {
    ratePct: scritta,
    source: sotto.source,
    value: pct1(scritta),
    sourceLabel: sotto.sourceLabel,
    label: `${pct1(scritta)} · ${sotto.sourceLabel}`,
    overriddenYears: [],
    totalYears,
    nota: diversaDallaProposta
      ? `Il piano usa ${pct1(scritta)}, non la proposta ${pct1(proposta!.aliquota)} (${propostaLabel(proposta)}).`
      : null,
    diversaDallaProposta,
  };
}
