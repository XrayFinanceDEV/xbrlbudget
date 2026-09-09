/**
 * Le decisioni del passo 3 «Costi principali» (spec 2026-09-08 §4.3).
 *
 * Sta in `lib/` e non dentro il componente perche' qui i componenti non sono
 * collaudabili (nessun jsdom, e non va aggiunto): tutto cio' che *decide*
 * qualcosa — quale quota fissa mostrare quando gli anni non concordano, quali
 * righe si spengono, che cosa vale il peso dei fissi — vive qui con la sua
 * suite in `environment: node`, e `StepCosti.tsx` si limita a renderlo.
 *
 * Un solo motore di proiezione, e sta in Python: la ripartizione fisso/
 * variabile degli anni previsti NON viene ricalcolata qui dallo slider, si
 * legge dalle righe che `rowsCosti` ha ricavato dai `details` del motore.
 * L'unica colonna in cui lo slider entra nell'aritmetica e' quella dell'anno
 * base, che il motore non calcola affatto: e' l'illustrazione di come la
 * quota digitata taglia l'ultimo bilancio.
 */
import type { ForecastPreviewResponse, IncomeStatement } from "@/types/api";
import type { AssumptionsMap } from "@/lib/budget-horizon";
import type { YearCellOff } from "@/lib/budget-year-cell";
import { rowsCosti, type PreviewRow } from "@/lib/budget-preview-rows";
import { euro, num, numOrNull, pctOf } from "@/lib/budget-format";

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
 * La granularita' e' l'ANNO e non la riga. Prima questa funzione rispondeva
 * `true`/`false` con un `some(...)`: un `ce05_override` sul solo 2025
 * accendeva il badge «forzato in CE Prev.» su tutte le righe collegate e su
 * tutti gli anni, mentre l'anteprima — che marca cella per cella — mostrava
 * il valore forzato sul solo 2025. L'utente leggeva un avviso acceso anche
 * dove la casella funziona, e digitava senza alcun segnale in quella dove
 * non serve a niente.
 *
 * Un override a zero e' un override vero (voce azzerata); `null` e assente
 * non forzano nulla.
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

/** Il `title` della casella inerte: sta sull'anno, quindi non lo ripete. */
const FORCED_CELL_NOTE =
  "Forzato in CE Prev.: in quest'anno la voce è un importo assoluto, quindi questa " +
  "percentuale non ha effetto. Si azzera dal dialogo Ricalcola.";

/** Il `title` della riga che la quota all'estremo ha annullato: una casella
 *  spenta senza il suo perche' e' lo stesso difetto un gradino piu' in la'. */
const OFF_NOTE = {
  variabile: "Con la quota fissa al 100% non resta parte variabile: questa percentuale non ha effetto.",
  fissa: "Con la quota fissa a 0% non resta parte fissa: questa percentuale non ha effetto.",
};

export interface CostiBase {
  mat: number | null;
  serv: number | null;
  pers: number | null;
  god: number | null;
}

/** Le quattro voci dell'anno base. Anno base assente ⇒ `null`, mai zero. */
export function costiBase(baseInc: IncomeStatement | undefined | null): CostiBase {
  if (!baseInc) return { mat: null, serv: null, pers: null, god: null };
  const i = baseInc as unknown as Record<string, unknown>;
  return {
    mat: numOrNull(i.ce05_materie_prime) ?? 0,
    serv: numOrNull(i.ce06_servizi) ?? 0,
    pers: numOrNull(i.ce08_costi_personale) ?? 0,
    god: numOrNull(i.ce07_godimento_beni) ?? 0,
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
 * Le righe della tabella. Forma strutturalmente compatibile con
 * `YearInputRow | YearInputGroup` di `components/budget/wizard/YearInputTable`
 * — dichiarata qui perche' `lib/` non importa da `components/`.
 */
export type CostiTableRow =
  | { group: string; swatch?: "fixed" | "variable" }
  | ({ field: string; label: string; sub?: string; baseLabel: string } & YearCellOff);

/** Gli anni previsti, e quelli in cui CE Prev. forza le due voci. */
export interface ForcedSplit {
  years: number[];
  materials: number[];
  services: number[];
}

/**
 * Tre gruppi: la quota fissa, poi le variabili, poi le fisse.
 *
 * Le due righe della quota fissa esistono perche' la quota e' un'ipotesi PER
 * ANNO e il motore la applica riga per riga: lo slider la scrive su tutti gli
 * anni insieme (`updateAll`), queste due righe la correggono anno per anno
 * (`update`). Senza di esse un valore differenziato a mano sarebbe modificabile
 * solo dallo slider, cioe' appiattito da un gesto che l'utente non legge come
 * distruttivo. La colonna dell'anno base resta «—»: una quota e' un'ipotesi sul
 * futuro, l'anno base non ne ha una.
 *
 * Una riga si spegne quando la quota la annulla — a quota 100 la parte variabile
 * non esiste, a quota 0 la parte fissa — perche' la sua percentuale di crescita
 * non avrebbe niente su cui mordere. Ma **mai quando gli anni discordano**:
 * `off` e' un flag di RIGA e `YearInputTable` lo traduce in `disabled` su OGNI
 * colonna, quindi con quota 100 sul primo anno e 40 sul secondo si renderebbe
 * indigitabile un campo che sul secondo anno il motore usa eccome. Qui la quota
 * che si conosce e' solo quella del primo anno: un controllo che non sa non
 * blocca.
 *
 * L'override di CE Prev. invece si sa per anno, e si spegne per anno
 * (`offYears`): la casella dell'anno forzato diventa inerte con il suo
 * perche', quelle degli altri anni restano vive. Prima non si spegneva nulla
 * e l'unico segnale — il badge — era acceso su tutti gli anni: si digitava un
 * numero senza effetto mentre l'anteprima non si muoveva.
 */
export function costiTableRows(
  base: CostiBase,
  mat: FixedShare,
  serv: FixedShare,
  forced: ForcedSplit
): CostiTableRow[] {
  const matSplit = splitBaseAmount(base.mat, mat.value);
  const servSplit = splitBaseAmount(base.serv, serv.value);
  const matNote = forcedNote(forced.materials, forced.years) ?? undefined;
  const servNote = forcedNote(forced.services, forced.years) ?? undefined;
  const matForced = { offYears: forced.materials, offYearsNote: FORCED_CELL_NOTE };
  const servForced = { offYears: forced.services, offYearsNote: FORCED_CELL_NOTE };
  return [
    { group: "Quota fissa, anno per anno" },
    {
      field: "fixed_materials_percentage",
      label: "Materie prime · quota fissa (%)",
      sub: matNote,
      baseLabel: "—",
      ...matForced,
    },
    {
      field: "fixed_services_percentage",
      label: "Servizi · quota fissa (%)",
      sub: servNote,
      baseLabel: "—",
      ...servForced,
    },
    { group: "Costi variabili", swatch: "variable" },
    {
      field: "variable_materials_growth_pct",
      label: "Materie prime · parte variabile",
      sub: matNote,
      baseLabel: euro(matSplit.variable),
      off: mat.value >= 100 && !mat.uneven,
      offNote: OFF_NOTE.variabile,
      ...matForced,
    },
    {
      field: "variable_services_growth_pct",
      label: "Servizi · parte variabile",
      sub: servNote,
      baseLabel: euro(servSplit.variable),
      off: serv.value >= 100 && !serv.uneven,
      offNote: OFF_NOTE.variabile,
      ...servForced,
    },
    { group: "Costi fissi", swatch: "fixed" },
    {
      field: "fixed_materials_growth_pct",
      label: "Materie prime · parte fissa",
      sub: matNote,
      baseLabel: euro(matSplit.fixed),
      off: mat.value <= 0 && !mat.uneven,
      offNote: OFF_NOTE.fissa,
      ...matForced,
    },
    {
      field: "fixed_services_growth_pct",
      label: "Servizi · parte fissa",
      sub: servNote,
      baseLabel: euro(servSplit.fixed),
      off: serv.value <= 0 && !serv.uneven,
      offNote: OFF_NOTE.fissa,
      ...servForced,
    },
    { field: "personnel_growth_pct", label: "Personale", baseLabel: euro(base.pers) },
    { field: "rent_growth_pct", label: "Godimento beni di terzi", baseLabel: euro(base.god) },
  ];
}

export interface AssumptionWrite {
  year: number;
  field: "variable_materials_growth_pct" | "variable_services_growth_pct";
  value: number;
}

/**
 * «Allinea le variabili ai ricavi»: le due parti variabili prendono, anno per
 * anno, la crescita dei ricavi di QUELL'anno — non una sola cifra per tutti,
 * perche' la crescita dei ricavi puo' cambiare lungo il piano. Un anno senza
 * crescita dichiarata vale 0: qui lo zero e' il valore che il motore userebbe.
 */
export function alignVariablesToRevenue(
  assumptions: AssumptionsMap,
  years: number[]
): AssumptionWrite[] {
  const out: AssumptionWrite[] = [];
  for (const year of years) {
    const value = num(assumptions[year]?.revenue_growth_pct ?? 0);
    out.push({ year, field: "variable_materials_growth_pct", value });
    out.push({ year, field: "variable_services_growth_pct", value });
  }
  return out;
}

export interface CostiSplitBar {
  year: number;
  fixed: number | null;
  variable: number | null;
  /** Larghezze per la barra impilata: mai negative, cosi' `flex` resta sensato. */
  fixedFlex: number;
  variableFlex: number;
}

export interface CostiPreview {
  /** Gli anni che il motore ha davvero prodotto, non quelli richiesti. */
  years: number[];
  /** Le righe della tabella dell'anteprima: senza «Debiti verso fornitori». */
  tableRows: PreviewRow[];
  /** La riga dei fornitori, resa da sola sotto l'occhiello dei giorni. */
  fornitori: PreviewRow | null;
  /** `details.dpo_applied` del primo anno previsto. */
  dpo: number | null;
  bars: CostiSplitBar[];
  /** Peso dei fissi sui costi principali: anno base e ultimo anno previsto. */
  weight: { base: number | null; last: number | null };
}

const EMPTY_PREVIEW: CostiPreview = {
  years: [],
  tableRows: [],
  fornitori: null,
  dpo: null,
  bars: [],
  weight: { base: null, last: null },
};

/**
 * Dalla risposta del motore a tutto cio' che l'anteprima del passo rende.
 *
 * Senza anno base o senza risposta non c'e' anteprima: nessuna riga, non righe
 * a zero. Gli anni sono quelli che il motore ha prodotto — se si e' fermato a
 * meta' (fabbisogno scoperto) la 200 porta gli anni validi e sono quelli che si
 * mostrano, mai le colonne richieste riempite di vuoto.
 */
export function costiPreview(
  baseInc: IncomeStatement | undefined | null,
  fixedShare: { materials: number; services: number },
  data: ForecastPreviewResponse | null
): CostiPreview {
  if (!baseInc || !data) return EMPTY_PREVIEW;

  const previewYears = data.forecast_years ?? [];
  const years = previewYears.map((y) => y.year);
  const rows = rowsCosti(baseInc, fixedShare, previewYears);
  const byKey = (key: string) => rows.find((r) => r.key === key) ?? null;
  const fissi = byKey("fissi"), variabili = byKey("variabili"), principali = byKey("principali");

  const bars: CostiSplitBar[] = years.map((year, i) => {
    const fixed = fissi?.years[i]?.value ?? null;
    const variable = variabili?.years[i]?.value ?? null;
    return {
      year,
      fixed,
      variable,
      fixedFlex: Math.max(0, fixed ?? 0),
      variableFlex: Math.max(0, variable ?? 0),
    };
  });

  const last = years.length - 1;
  return {
    years,
    tableRows: rows.filter((r) => r.key !== "fornitori"),
    fornitori: byKey("fornitori"),
    dpo: previewYears[0]?.details?.dpo_applied ?? null,
    bars,
    weight: {
      base: pctOf(fissi?.base.value ?? null, principali?.base.value ?? null),
      last: last >= 0 ? pctOf(fissi?.years[last]?.value ?? null, principali?.years[last]?.value ?? null) : null,
    },
  };
}
