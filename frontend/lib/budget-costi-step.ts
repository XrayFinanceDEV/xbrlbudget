/**
 * Le decisioni del passo 3 «Costi» (spec 2026-09-15 §4.3, giro di rilievi del 14/09).
 *
 * Sta in `lib/` e non dentro il componente perche' qui i componenti non sono
 * collaudabili (nessun jsdom, e non va aggiunto): tutto cio' che *decide*
 * qualcosa — quale quota fissa mostrare quando gli anni non concordano, quali
 * righe si spengono, quali anni seguono ancora l'inflazione — vive qui con la
 * sua suite in `environment: node`, e `StepCosti.tsx` si limita a renderlo.
 *
 * Un solo motore di proiezione, e sta in Python: il pareggio (`lib/budget-pareggio.ts`)
 * e il CE fino all'ante imposte (`rowsCeAnteImposte`, `lib/budget-preview-rows.ts`)
 * leggono solo cio' che il motore ha gia' dichiarato in `details`. La parte variabile
 * segue i ricavi finche' l'utente non imposta una crescita diversa per anno.
 */
import type { IncomeStatement } from "@/types/api";
import type { AssumptionsMap } from "@/lib/budget-horizon";
import type { YearCellOff } from "@/lib/budget-year-cell";
import { euro, num, numOrNull } from "@/lib/budget-format";

/** Il default del motore per `fixed_*_percentage` (backend/app/schemas/budget.py). */
export const FIXED_SHARE_DEFAULT = 40;

export type FixedShareField = "fixed_materials_percentage" | "fixed_services_percentage";
export type SplitOverrideField = "ce05_override" | "ce06_override";

export interface FixedShare {
  /** La quota da mostrare: quella del primo anno previsto. */
  value: number;
  /** Almeno un anno ne ha una diversa: lo slider, muovendosi, li allinea. */
  uneven: boolean;
}

/**
 * La quota fissa e' un'ipotesi PER ANNO — il motore la applica riga per riga —
 * ma lo slider e' uno solo. Si mostra quella del primo anno previsto e si
 * dichiara se gli altri non concordano; un anno senza valore vale il default
 * del motore, non zero.
 */
export function fixedShareOf(
  assumptions: AssumptionsMap,
  years: number[],
  field: FixedShareField
): FixedShare {
  const vals = years.map((y) => {
    const raw = assumptions[y]?.[field];
    return raw === null || raw === undefined ? FIXED_SHARE_DEFAULT : num(raw);
  });
  const value = vals.length > 0 ? vals[0] : FIXED_SHARE_DEFAULT;
  return { value, uneven: vals.some((v) => v !== value) };
}

/**
 * GLI ANNI in cui un override assoluto di CE Prev. sostituisce la voce
 * intera: la ripartizione fisso/variabile che il motore dichiarava non c'e'
 * piu' e ne' lo slider ne' le percentuali di crescita mordono su quegli anni.
 *
 * La granularita' e' l'ANNO e non la riga. Un override a zero e' un override
 * vero (voce azzerata); `null` e assente non forzano nulla.
 */
export function forcedSplitYears(
  assumptions: AssumptionsMap,
  years: number[],
  field: SplitOverrideField
): number[] {
  return years.filter((y) => {
    const v = assumptions[y]?.[field];
    return v !== null && v !== undefined && v !== ("" as unknown);
  });
}

const FORCED_NOTE = "forzato in CE Prev.";

/** «2027» · «2027 e 2029» · «2027, 2028 e 2029». */
function listaAnni(years: number[]): string {
  if (years.length <= 1) return years.map(String).join("");
  return `${years.slice(0, -1).join(", ")} e ${years[years.length - 1]}`;
}

/**
 * L'avviso «forzato in CE Prev.», che dice ANCHE dove e' vero.
 *
 * Senza anni forzati non c'e' avviso (`null`): un badge che si accende
 * ovunque non distingue piu' niente. Quando invece tutti gli anni previsti
 * sono forzati elencarli non aggiunge nulla, e l'avviso resta secco.
 */
export function forcedNote(forcedYears: number[], allYears: number[]): string | null {
  if (forcedYears.length === 0) return null;
  if (allYears.length > 0 && forcedYears.length === allYears.length) return FORCED_NOTE;
  return `${FORCED_NOTE} nel ${listaAnni(forcedYears)}`;
}

/** Il `title` della casella inerte per un override di CE Prev.: sta sull'anno,
 *  quindi non lo ripete. */
const FORCED_CELL_NOTE =
  "Forzato in CE Prev.: in quest'anno la voce è un importo assoluto, quindi questa " +
  "percentuale non ha effetto. Si azzera dal dialogo Ricalcola.";

/** Il `title` della riga «… · fissa» quando la quota fissa e' a 0%: non resta parte
 *  fissa su cui la percentuale possa mordere. */
const OFF_NOTE_FISSA = "Con la quota fissa a 0% non resta parte fissa: questa percentuale non ha effetto.";
const OFF_NOTE_VARIABILE = "Con la quota variabile a 0% questa percentuale non ha effetto.";

/** Il `title` della cella «azzurra»: segue l'inflazione del passo 1 finche' non la si
 *  scrive a mano (spec §4.3, decisione 2). */
export const AUTO_NOTE =
  "Segue l'inflazione del passo 1: cambia se la cambi lì. Scrivi un valore per fissarlo; " +
  "svuota la casella per tornare all'inflazione.";
export const VARIABLE_AUTO_NOTE =
  "0 = segue la crescita dei ricavi. Un valore negativo riduce la crescita del costo, " +
  "uno positivo la aumenta. Svuota la casella per tornare a 0.";

export interface CostiBase {
  mat: number | null;
  serv: number | null;
  pers: number | null;
  god: number | null;
  /** Oneri diversi di gestione (ce12): entra qui perche' la riga «Oneri diversi di
   *  gestione» si e' spostata in questo passo — prima viveva in «Altre voci CE». */
  od: number | null;
}

/** Le cinque voci dell'anno base. Anno base assente ⇒ `null`, mai zero. */
export function costiBase(baseInc: IncomeStatement | undefined | null): CostiBase {
  if (!baseInc) return { mat: null, serv: null, pers: null, god: null, od: null };
  const i = baseInc as unknown as Record<string, unknown>;
  return {
    mat: numOrNull(i.ce05_materie_prime) ?? 0,
    serv: numOrNull(i.ce06_servizi) ?? 0,
    pers: numOrNull(i.ce08_costi_personale) ?? 0,
    god: numOrNull(i.ce07_godimento_beni) ?? 0,
    od: numOrNull(i.ce12_oneri_diversi) ?? 0,
  };
}

/** La parte fissa e la parte variabile dell'anno base secondo la quota digitata. */
export function splitBaseAmount(
  amount: number | null,
  share: number
): { fixed: number | null; variable: number | null } {
  if (amount === null) return { fixed: null, variable: null };
  const fixed = (amount * share) / 100;
  return { fixed, variable: amount - fixed };
}

/**
 * Se un valore scritto in una casella della «Parte fissa» torna
 * all'inflazione o resta un numero suo.
 *
 * Vuoto (`null`) ⇒ automatico: la casella segue l'inflazione del passo 1
 * finche' l'utente non ci scrive sopra. Un valore esplicito, ANCHE UNO ZERO,
 * e' una scelta dell'utente e smette di seguire l'inflazione — uno zero
 * scritto a mano non e' la stessa cosa di una casella vuota.
 */
export function fixedGrowthChange(raw: number | null, inflazione: number): { value: number; auto: boolean } {
  return raw === null ? { value: inflazione, auto: true } : { value: raw, auto: false };
}

/** Gli anni in cui la casella «Parte fissa» e' ancora in automatico
 *  (`fixed_*_growth_auto === true`), nell'ordine del piano. */
export function autoYearsOf(
  map: AssumptionsMap,
  years: number[],
  field: "fixed_materials_growth_auto" | "fixed_services_growth_auto"
): number[] {
  return years.filter((y) => map[y]?.[field] === true);
}

/** La quota variabile e' automatica quando cresce come i ricavi dello stesso anno. */
export function variableAutoYearsOf(
  map: AssumptionsMap,
  years: number[],
  field: "variable_materials_growth_pct" | "variable_services_growth_pct"
): number[] {
  return years.filter((y) => {
    const marker = map[y]?.[field === "variable_materials_growth_pct"
      ? "variable_materials_growth_auto" : "variable_services_growth_auto"];
    if (marker !== null && marker !== undefined) return marker;
    const revenue = num(map[y]?.revenue_growth_pct ?? 0);
    const variable = map[y]?.[field];
    return variable == null || num(variable) === revenue;
  });
}

/** Lo scostamento in punti si somma alla crescita dei ricavi e diventa il driver del motore. */
export function variableGrowthChange(deviation: number | null, revenue: number): number {
  return Math.max(-100, Math.min(100, revenue + (deviation ?? 0)));
}

export function variableGrowthDeviation(growth: number | null | undefined, revenue: number): string {
  return String(Math.round(((growth ?? revenue) - revenue) * 100) / 100);
}

/**
 * Le righe della tabella. Forma strutturalmente compatibile con
 * `YearInputRow | YearInputGroup` di `components/budget/wizard/YearInputTable`
 * — dichiarata qui perche' `lib/` non importa da `components/`.
 */
export type CostiTableRow =
  | { group: string; swatch?: "fixed" | "variable"; sub?: string }
  | ({
      field: string;
      label: string;
      sub?: string;
      baseLabel: string;
      autoYears?: number[];
      autoNote?: string;
    } & YearCellOff);

/** Gli anni previsti, e quelli in cui CE Prev. forza le due voci. */
export interface ForcedSplit {
  years: number[];
  materials: number[];
  services: number[];
}

/**
 * Tre gruppi: la parte variabile segue i ricavi finche' non e' corretta a mano,
 * la parte fissa e' precompilata con l'inflazione, poi le tre ipotesi
 * manuali che restano — personale, godimento beni di terzi, oneri diversi di
 * gestione (spostata qui da «Altre voci CE»). La quota fissa resta
 * modificabile dallo slider per tutti gli anni.
 *
 * `auto` (calcolato dal chiamante con `autoYearsOf`, uno per voce) marca le
 * celle ancora automatiche: l'anteprima le rende azzurre con la loro nota,
 * indipendentemente da `offYears` — le due cose rispondono a domande diverse
 * (automatica vs. inerte per un override di CE Prev.) e possono capitare
 * insieme sulla stessa cella.
 *
 * Una riga «… · fissa» si spegne quando la quota della slider la annulla — a
 * quota 0 non resta parte fissa — ma **mai quando gli anni discordano**:
 * `off` e' un flag di RIGA e `YearInputTable` lo traduce in `disabled` su OGNI
 * colonna, quindi con quota 0 sul primo anno e 40 sul secondo si renderebbe
 * indigitabile un campo che sul secondo anno il motore usa eccome (stessa
 * regola del passo prima del giro di rilievi).
 */
export function costiTableRows(
  base: CostiBase,
  mat: FixedShare,
  serv: FixedShare,
  forced: ForcedSplit,
  auto: { materials: number[]; services: number[]; variableMaterials?: number[]; variableServices?: number[] }
): CostiTableRow[] {
  const matSplit = splitBaseAmount(base.mat, mat.value);
  const servSplit = splitBaseAmount(base.serv, serv.value);
  const matNote = forcedNote(forced.materials, forced.years) ?? undefined;
  const servNote = forcedNote(forced.services, forced.years) ?? undefined;
  const matForced = { offYears: forced.materials, offYearsNote: FORCED_CELL_NOTE };
  const servForced = { offYears: forced.services, offYearsNote: FORCED_CELL_NOTE };
  return [
    { group: "Parte variabile", swatch: "variable", sub: "scostamento dalla crescita dei ricavi (punti %) · 0 = proporzionale" },
    {
      field: "variable_materials_growth_pct",
      label: "Materie prime · variabile",
      sub: matNote,
      baseLabel: euro(matSplit.variable),
      autoYears: auto.variableMaterials,
      autoNote: VARIABLE_AUTO_NOTE,
      off: mat.value >= 100 && !mat.uneven,
      offNote: OFF_NOTE_VARIABILE,
      ...matForced,
    },
    {
      field: "variable_services_growth_pct",
      label: "Servizi · variabile",
      sub: servNote,
      baseLabel: euro(servSplit.variable),
      autoYears: auto.variableServices,
      autoNote: VARIABLE_AUTO_NOTE,
      off: serv.value >= 100 && !serv.uneven,
      offNote: OFF_NOTE_VARIABILE,
      ...servForced,
    },
    { group: "Parte fissa", swatch: "fixed", sub: "precompilata con l'inflazione del passo 1 · correggi se serve, anche a 0" },
    {
      field: "fixed_materials_growth_pct",
      label: "Materie prime · fissa",
      sub: matNote,
      baseLabel: euro(matSplit.fixed),
      autoYears: auto.materials,
      autoNote: AUTO_NOTE,
      off: mat.value <= 0 && !mat.uneven,
      offNote: OFF_NOTE_FISSA,
      ...matForced,
    },
    {
      field: "fixed_services_growth_pct",
      label: "Servizi · fissa",
      sub: servNote,
      baseLabel: euro(servSplit.fixed),
      autoYears: auto.services,
      autoNote: AUTO_NOTE,
      off: serv.value <= 0 && !serv.uneven,
      offNote: OFF_NOTE_FISSA,
      ...servForced,
    },
    { group: "Ipotesi manuali", sub: "partono da 0 · variazione % sull'anno precedente" },
    { field: "personnel_growth_pct", label: "Personale", baseLabel: euro(base.pers) },
    { field: "rent_growth_pct", label: "Godimento beni di terzi", baseLabel: euro(base.god) },
    {
      field: "other_costs_growth_pct",
      label: "Oneri diversi di gestione",
      sub: "spostata qui da «Altre voci CE»",
      baseLabel: euro(base.od),
    },
  ];
}

/** Le tre righe della card «Calcolate in altri passi»: nessun valore, solo dove
 *  trovarle — i numeri veri sono nel «Conto economico fino all'ante imposte» qui
 *  sotto e nei passi citati. Un valore forzato a mano in CE Prev. vince su queste
 *  regole finche' non lo si azzera dal dialogo Ricalcola: e' la stessa nota che il
 *  prototipo mette sotto la card (`baseYear` non entra nel testo: le tre righe non
 *  dipendono dall'anno, solo dal fatto che il passo 6/7 le calcolano). */
export function calcolateAltrove(baseYear: number): { label: string; small: string; passo: string }[] {
  void baseYear;
  return [
    { label: "Ammortamenti", small: "quote esistenti più i nuovi investimenti", passo: "passo 6" },
    { label: "Oneri finanziari", small: "mutui esistenti, nuovi finanziamenti, scoperto", passo: "passi 5 e 6" },
    { label: "Imposte", small: "aliquota effettiva o forzata", passo: "passo 7" },
  ];
}
