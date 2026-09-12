/**
 * Le decisioni del passo 6 «Pregresso e nuovo» (spec 2026-09-08 §4.6): i
 * saldi dell'anno base mostrati accanto agli input di scadenziamento del
 * debito esistente, la lettura/scrittura dei campi scritti con `updateAll`
 * (stesso valore su ogni anno) e la composizione dell'anteprima.
 *
 * Segue lo schema di `lib/budget-costi-step.ts` (Task 12): un componente non
 * e' collaudabile in questo repo (nessun jsdom, e non va aggiunto), quindi
 * ogni decisione — quale valore mostrare quando gli anni non concordano piu',
 * quali anni ha davvero prodotto il motore — vive qui con la sua suite in
 * `environment: node`, e `StepPregressoNuovo.tsx` si limita a renderla.
 *
 * Un solo motore di proiezione, e sta in Python: il debito, la cassa e la
 * PFN previsti NON si ricalcolano qui, si leggono da `rowsPregressoNuovo`,
 * che a sua volta legge solo cio' che il motore ha gia' restituito.
 */
import type { BalanceSheet, ForecastPreviewResponse } from "@/types/api";
import type { AssumptionsMap } from "@/lib/budget-horizon";
import { baseBankDebt } from "@/lib/base-bank-debt";
import { rowsPregressoNuovo, rowsPregressoRunoff, unfundedFromError, type PreviewRow } from "@/lib/budget-preview-rows";
import { writeoffIgnoredAvvisi, writeoffIgnoredByYear, type TabellaPregressoKey } from "@/lib/budget-pregresso-tabella";
import { num } from "@/lib/budget-format";

export interface PregressoBase {
  /** Debito bancario totale, formula del motore (`lib/base-bank-debt`). */
  bankDebt: number | null;
  /** Di cui a breve (`sp16a`), la sola cifra che il motore legge riga per riga. */
  bankDebtShort: number | null;
  altriFinanziatori: number | null;
  creditiClienti: number | null;
  debitiTributari: number | null;
}

const EMPTY_BASE: PregressoBase = {
  bankDebt: null, bankDebtShort: null, altriFinanziatori: null, creditiClienti: null, debitiTributari: null,
};

/**
 * I saldi al 31/12/{baseYear} usati dal passo. Anno base assente ⇒ tutto
 * `null` — uno zero vero (bilancio senza altri finanziatori) e uno zero di
 * ripiego (nessun bilancio caricato) non sono la stessa cosa.
 *
 * `bankDebt` NON e' `sp16a + sp17a`: e' `baseBankDebt`, la stessa formula
 * contro cui il motore valida i residui iniziali in `FinancingLoansGrid`
 * (`lib/base-bank-debt.ts`) — replicarla diversamente qui mostrerebbe come
 * coperto un piano che il server rifiuta.
 */
export function pregressoBase(baseBs: BalanceSheet | undefined | null): PregressoBase {
  if (!baseBs) return EMPTY_BASE;
  const bs = baseBs as unknown as Record<string, unknown>;
  return {
    bankDebt: baseBankDebt(bs),
    bankDebtShort: num(bs.sp16a_debiti_banche_breve),
    altriFinanziatori: num(bs.sp16b_debiti_altri_finanz_breve) + num(bs.sp17b_debiti_altri_finanz_lungo),
    creditiClienti: num(bs.sp06_crediti_breve) - num(bs.sp06e_crediti_tributari_breve) - num(bs.sp06f_imposte_anticipate_breve),
    debitiTributari: num(bs.sp16e_debiti_tributari_breve) + num(bs.sp17e_debiti_tributari_lungo),
  };
}

export interface SingleYearValue {
  /** Il valore da mostrare: quello del primo anno previsto (`null` = non impostato). */
  value: number | null;
  /** Almeno un anno ne ha uno diverso: scrivere di nuovo li allinea tutti. */
  uneven: boolean;
}

/**
 * Legge un campo scritto con `updateAll` (stesso valore su ogni anno di
 * piano): si mostra quello del primo anno previsto, e si dichiara se gli
 * altri non concordano piu' — puo' succedere se un valore e' stato cambiato
 * altrove, anno per anno.
 */
export function singleYearValue(assumptions: AssumptionsMap, years: number[], field: string): SingleYearValue {
  const vals = years.map((y) => {
    const raw = (assumptions[y] as Record<string, unknown> | undefined)?.[field];
    return raw === null || raw === undefined ? null : num(raw);
  });
  const value = vals.length > 0 ? vals[0] : null;
  return { value, uneven: vals.some((v) => v !== value) };
}

/** L'interruttore per anno vive in `lib/budget-horizon.ts`, con `AssumptionsMap`:
 *  qui si ri-esporta perche' il passo 6 legga tutto dal proprio modulo. */
export { boolAssumption, type BoolAssumptionField } from "@/lib/budget-horizon";

export interface PregressoPreview {
  /** Gli anni che il motore ha davvero prodotto, non quelli richiesti. */
  years: number[];
  rows: PreviewRow[];
  unfunded: { year: number; amount: number } | null;
  /** Gli anni in cui un inesigibile scadenziato NON e' stato scaricato perche'
   *  un override del CE impediva di rilevarne il costo: il credito e' rimasto
   *  a bilancio, e va detto. Vuoto quando non c'e' nulla da dire. */
  writeoffIgnored: string[];
  /** Lo stesso avviso, indicizzato sull'anno invece che elencato in una
   *  frase: la tabella lo usa per marcare la cella «di cui inesigibile»
   *  invece di lasciarlo solo nell'anteprima (rilievo 6, giro di correzione
   *  1). Stessa lettura di `writeoffIgnored`, nessun ricalcolo. */
  writeoffIgnoredByYear: Record<number, string>;
}

const EMPTY_PREVIEW: PregressoPreview = {
  years: [], rows: [], unfunded: null, writeoffIgnored: [], writeoffIgnoredByYear: {},
};

/**
 * Dalla risposta del motore a tutto cio' che l'anteprima del passo rende.
 * Senza anno base o senza risposta non c'e' anteprima: nessuna riga, non
 * righe a zero. Se il motore si e' fermato a meta' (fabbisogno scoperto) la
 * 200 porta comunque gli anni validi in `forecast_years`: sono quelli che si
 * mostrano, mai le colonne richieste riempite di vuoto.
 */
export function pregressoPreview(
  baseBs: BalanceSheet | undefined | null,
  data: ForecastPreviewResponse | null,
  keys: readonly TabellaPregressoKey[] = [],
): PregressoPreview {
  if (!baseBs || !data) return EMPTY_PREVIEW;
  const previewYears = data.forecast_years ?? [];
  return {
    years: previewYears.map((y) => y.year),
    // Debito/cassa/PFN, poi il pregresso scadenziato: due letture dello stesso
    // `forecast_years`, nessun ricalcolo.
    rows: [...rowsPregressoNuovo(baseBs, previewYears), ...rowsPregressoRunoff(previewYears, keys)],
    unfunded: unfundedFromError(data.error),
    writeoffIgnored: writeoffIgnoredAvvisi(previewYears),
    writeoffIgnoredByYear: writeoffIgnoredByYear(previewYears),
  };
}
