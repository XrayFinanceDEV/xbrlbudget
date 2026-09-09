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
 * (`calculations/forecast_engine.py:_tax_components`), in ordine di
 * precedenza:
 *
 * 1. **`ce20_override`** (`:723-726`): se c'e', quell'importo E' l'imposta
 *    totale dell'anno e **nessuna aliquota viene applicata**. Si imposta da
 *    `/forecast/income` e sopravvive al salvataggio (CLAUDE.md: «Un
 *    `ce20_override` overrides the rate altogether»).
 * 2. **Aliquota effettiva dell'anno base**: se derivabile (imposte > 0,
 *    utile ante imposte > 0, rapporto <= 60%) il motore usa quella e ignora
 *    il valore forzato.
 * 3. **`tax_rate`**: e' un FALLBACK, letto solo quando l'effettiva non e'
 *    derivabile. Nello schema e' NOT NULL e vale 27,9 (IRES + IRAP) su
 *    un'ipotesi nuova, quindi «uguale al default» qui significa «non
 *    forzata».
 *
 * Invariante: un'etichetta non dichiara MAI qualcosa che il motore non fa —
 * ne' un default presentato come un calcolo, ne' un'aliquota su un anno in
 * cui il motore non ne applica nessuna. `label` porta la provenienza
 * attaccata a tutto ciò che non e' l'effettiva dell'anno base.
 *
 * Un solo motore di proiezione, e sta in Python: qui non si calcola nessuna
 * imposta, si dichiara solo QUALE aliquota il motore applichera' e perche'.
 */
import type { AssumptionsMap } from "@/lib/budget-horizon";
import { formatPercentage } from "@/lib/formatters";
import { DEFAULT_TAX_RATE, taxRateValue } from "@/lib/budget-imposte-step";

export type TaxRateSource = "effettiva" | "forzata" | "predefinita" | "sostituita";

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
  /** Valore + provenienza quando NON e' l'effettiva dell'anno base: cosi' un
   *  default non puo' passare per un calcolo. */
  label: string;
  /** L'aliquota forzata che il motore ignorera' perche' l'effettiva vince,
   *  oppure `null`. */
  ignoredForcedPct: number | null;
  /** Gli anni previsti su cui `ce20_override` sostituisce l'aliquota con un
   *  importo, e quanti sono in tutto. */
  overriddenYears: number[];
  totalYears: number;
  /** La spiegazione da mostrare accanto al valore, o `null` quando non c'e'
   *  nulla da spiegare (aliquota effettiva, nessun valore forzato). */
  nota: string | null;
  /**
   * La riga «Aliquota usata dal piano» dice qualcosa che le righe sopra non
   * dicono gia'.
   *
   * Nel caso comune — effettiva derivabile, nulla di forzato, nessun
   * override — «Aliquota effettiva 2024 · 25,0% [usata dal piano]» e
   * «Aliquota usata dal piano · 25,0% [effettiva dell'anno base]» sono la
   * stessa frase due volte: li' la riga si nasconde e basta il badge della
   * prima. La scelta sta qui e non come condizione nel JSX perche' qui e'
   * collaudabile.
   */
  addsInformation: boolean;
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

/** Gli anni previsti su cui `ce20_override` sostituisce l'aliquota con un
 *  importo. `0` e' un override vero (imposte azzerate), non un'assenza. */
function overriddenTaxYears(assumptions: AssumptionsMap, forecastYears: number[]): number[] {
  return forecastYears.filter((y) => {
    const v = (assumptions[y] as Record<string, unknown> | undefined)?.ce20_override;
    return v !== null && v !== undefined && v !== "";
  });
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
  const overridden = overriddenTaxYears(assumptions, forecastYears);
  const totalYears = forecastYears.length;

  // L'aliquota sottostante: quella che il motore applicherebbe — e che
  // applica davvero sugli anni SENZA `ce20_override`.
  const sotto =
    effectiveRatePct !== null
      ? { ratePct: effectiveRatePct, source: "effettiva" as const, sourceLabel: "effettiva dell'anno base" }
      : forced !== null
      ? { ratePct: forced, source: "forzata" as const, sourceLabel: "forzata nelle ipotesi" }
      : { ratePct: DEFAULT_TAX_RATE, source: "predefinita" as const, sourceLabel: "predefinita, non calcolata" };

  const ignoredForcedPct = effectiveRatePct !== null ? forced : null;

  // 1. `ce20_override` batte tutto: su quegli anni il motore prende l'importo
  //    come imposta totale e non applica NESSUNA aliquota. Dichiarare qui
  //    un'aliquota sarebbe affermare una cosa che il motore non fa.
  if (overridden.length > 0) {
    const tutti = overridden.length === totalYears;
    const quanti = tutti
      ? "su tutti gli anni previsti"
      : `su ${overridden.length} anni su ${totalYears} (${overridden.join(", ")})`;
    const value = tutti ? "—" : pct1(sotto.ratePct);
    const sourceLabel = tutti
      ? "sostituita da un importo forzato"
      : `sostituita in ${overridden.length} anni su ${totalYears}`;
    return {
      ratePct: tutti ? null : sotto.ratePct,
      source: "sostituita",
      value,
      sourceLabel,
      label: `${value} · ${sourceLabel}`,
      ignoredForcedPct,
      overriddenYears: overridden,
      totalYears,
      nota: tutti
        ? "Le imposte sono forzate a importo nel CE previsionale: il motore usa quell'importo e non applica nessuna aliquota. Si azzera dal dialogo Ricalcola."
        : `Le imposte sono forzate a importo nel CE previsionale ${quanti}: li' il motore usa quell'importo e non applica nessuna aliquota. Negli altri anni resta l'aliquota ${sotto.sourceLabel}.`,
      addsInformation: true,
    };
  }

  // 2. L'effettiva dell'anno base vince, anche su un'aliquota forzata.
  if (sotto.source === "effettiva") {
    return {
      ratePct: sotto.ratePct,
      source: "effettiva",
      value: pct1(sotto.ratePct),
      sourceLabel: sotto.sourceLabel,
      label: pct1(sotto.ratePct),
      ignoredForcedPct,
      overriddenYears: [],
      totalYears,
      nota:
        ignoredForcedPct === null
          ? null
          : `L'aliquota forzata (${pct1(ignoredForcedPct)}) non viene usata: quando l'anno base ha un'aliquota effettiva, il motore applica quella.`,
      // Nel caso comune la riga ripeterebbe parola per parola quella
      // dell'aliquota effettiva: si nasconde.
      addsInformation: ignoredForcedPct !== null,
    };
  }

  // 3. Il fallback: `tax_rate` forzato, o il predefinito di schema.
  const nota =
    sotto.source === "forzata"
      ? "L'anno base non esprime un'aliquota effettiva: il piano usa il valore forzato qui sotto."
      : `L'anno base non esprime un'aliquota effettiva e nessun valore e' stato forzato: il piano usa il predefinito ${pct1(DEFAULT_TAX_RATE)} (IRES + IRAP).`;
  return {
    ratePct: sotto.ratePct,
    source: sotto.source,
    value: pct1(sotto.ratePct),
    sourceLabel: sotto.sourceLabel,
    label: `${pct1(sotto.ratePct)} · ${sotto.sourceLabel}`,
    ignoredForcedPct: null,
    overriddenYears: [],
    totalYears,
    nota,
    addsInformation: true,
  };
}
