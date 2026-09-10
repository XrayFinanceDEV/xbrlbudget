/**
 * Le decisioni del passo 5 «Capitale circolante» (spec 2026-09-08 §4.5,
 * task-13-brief.md).
 *
 * Sta in `lib/` per lo stesso motivo di `budget-costi-step.ts` (Task 12) e
 * `budget-altre-voci-step.ts` (Task 13): nessun jsdom in questo repo, quindi
 * ogni decisione — quale giorno "auto" mostrare, quale importo base ha una
 * voce minore, con quale anno leggere gli interruttori — vive qui con la
 * sua suite `environment: node`, e `StepCircolante.tsx` si limita a
 * renderlo.
 *
 * I tre campi giorni sono annullabili: vuoto significa "usa il valore
 * derivato dall'anno base" (`computeAutoDays`, gia' in lib/budget-turnover.ts
 * — QUELLA funzione, mai una formula nuova: il segnaposto `auto:` prometteva
 * 122 giorni dove il motore ne applicava 116, ed e' il difetto per cui
 * `computeAutoDays` esiste). Un solo motore di proiezione, e sta in Python:
 * l'anteprima del circolante e' lettura pura di `rowsCircolante`, mai un
 * ricalcolo qui.
 */
import { computeAutoDays } from "@/lib/budget-turnover";
import type { AssumptionsMap } from "@/lib/budget-horizon";
import { euro, numOrNull } from "@/lib/budget-format";
import { rowsCircolante, type PreviewRow } from "@/lib/budget-preview-rows";
import type { YearCellOff } from "@/lib/budget-year-cell";
import type { BalanceSheet, ForecastPreviewResponse, IncomeStatement, SpIndexingDriver } from "@/types/api";

/**
 * Riga della tabella, forma strutturalmente compatibile con `YearInputRow`
 * di `components/budget/wizard/YearInputTable` — dichiarata qui perche'
 * `lib/` non importa da `components/` (stesso schema di `CostiTableRow`).
 */
export interface CircolanteTableRow extends YearCellOff {
  field: string;
  label: string;
  /** Seconda riga sotto l'etichetta, resa da `YearInputTable`. */
  sub?: string;
  baseLabel: string;
  placeholder?: (year: number) => string;
}

export interface GiorniMedi {
  dso: number | null;
  dio: number | null;
  dpo: number | null;
}

/** I tre giorni "auto" derivati dall'anno base — la stessa `computeAutoDays`
 *  del motore, mai una formula propria. `null` quando l'anno base manca o
 *  il denominatore e' zero: in quel caso il campo resta senza placeholder,
 *  non con "auto 0". */
export function giorniMediAuto(
  baseInc: IncomeStatement | undefined | null,
  baseBs: BalanceSheet | undefined | null,
): GiorniMedi {
  return {
    dso: computeAutoDays("dso", baseInc ?? undefined, baseBs ?? undefined),
    dio: computeAutoDays("dio", baseInc ?? undefined, baseBs ?? undefined),
    dpo: computeAutoDays("dpo", baseInc ?? undefined, baseBs ?? undefined),
  };
}

const dayLabel = (n: number | null): string => (n === null ? "n/d" : `${n} gg`);
const autoPlaceholder = (n: number | null) => () => (n === null ? "auto" : `auto ${n}`);

/** Le tre righe "Giorni medi": DSO, DIO, DPO. */
export function giorniMediRows(auto: GiorniMedi): CircolanteTableRow[] {
  return [
    { field: "dso_days", label: "Giorni incasso clienti (DSO)", baseLabel: dayLabel(auto.dso), placeholder: autoPlaceholder(auto.dso) },
    { field: "dio_days", label: "Giorni rotazione magazzino (DIO)", baseLabel: dayLabel(auto.dio), placeholder: autoPlaceholder(auto.dio) },
    { field: "dpo_days", label: "Giorni pagamento fornitori (DPO)", baseLabel: dayLabel(auto.dpo), placeholder: autoPlaceholder(auto.dpo) },
  ];
}

/**
 * Le 14 voci minori dell'attivo e del passivo, con il codice SP, l'importo base
 * e chi le governa.
 *
 * `code` e' `null` sulle voci che nessun driver puo' agganciare, e `governata`
 * dice PERCHE': i tributari e le imposte anticipate seguono la posizione
 * fiscale, i crediti oltre 12 mesi seguono la propria percentuale e il piano di
 * scadenziamento dei crediti commerciali. Il motore ignorerebbe comunque una
 * chiave su quelle voci — e lo dichiarerebbe in `indicizzazione_ignorata` —
 * quindi l'interfaccia non la offre affatto, invece di lasciarla scegliere e
 * poi buttarla via.
 */
const MINOR_FIELDS: readonly {
  field: string; label: string; baseField: string;
  code: string | null; governata?: string; inerte?: boolean;
}[] = [
  { field: "receivables_long_growth_pct", label: "Crediti oltre 12 mesi", baseField: "sp07_crediti_lungo",
    code: null, governata: "dalla propria variazione % e dal piano dei crediti" },
  { field: "sp01_growth_pct", label: "Crediti verso soci", baseField: "sp01_crediti_soci", code: "sp01" },
  { field: "sp04_growth_pct", label: "Immobilizzazioni finanziarie", baseField: "sp04_immob_finanziarie", code: "sp04" },
  { field: "sp06e_growth_pct", label: "Crediti tributari", baseField: "sp06e_crediti_tributari_breve",
    code: null, governata: "dalla posizione tributaria" },
  { field: "sp06f_growth_pct", label: "Imposte anticipate entro", baseField: "sp06f_imposte_anticipate_breve",
    code: null, governata: "dalla posizione fiscale" },
  // La meta' OLTRE della stessa coppia. Non ha una `sp*_growth_pct` propria — la
  // scrive il kernel del deferred, oppure segue `receivables_long_growth_pct` —
  // quindi la riga e' di sola lettura (`inerte`). Mostrarne una e non l'altra
  // faceva sembrare che l'esclusione valesse per meta' della coppia.
  { field: "sp07f", label: "Imposte anticipate oltre", baseField: "sp07f_imposte_anticipate_lungo",
    code: null, governata: "dalla posizione fiscale", inerte: true },
  { field: "sp08_growth_pct", label: "Attività finanziarie", baseField: "sp08_attivita_finanziarie", code: "sp08" },
  { field: "sp10_growth_pct", label: "Ratei e risconti attivi", baseField: "sp10_ratei_risconti_attivi", code: "sp10" },
  { field: "sp14_growth_pct", label: "Fondi per rischi e oneri", baseField: "sp14_fondi_rischi", code: "sp14" },
  { field: "sp16f_growth_pct", label: "Debiti previdenziali entro", baseField: "sp16f_debiti_previdenza_breve", code: "sp16f" },
  { field: "sp16g_growth_pct", label: "Altri debiti entro", baseField: "sp16g_altri_debiti_breve", code: "sp16g" },
  { field: "sp17d_growth_pct", label: "Debiti fornitori oltre", baseField: "sp17d_debiti_fornitori_lungo", code: "sp17d" },
  { field: "sp17f_growth_pct", label: "Debiti previdenziali oltre", baseField: "sp17f_debiti_previdenza_lungo", code: "sp17f" },
  { field: "sp17g_growth_pct", label: "Altri debiti oltre", baseField: "sp17g_altri_debiti_lungo", code: "sp17g" },
  { field: "sp18_growth_pct", label: "Ratei e risconti passivi", baseField: "sp18_ratei_risconti_passivi", code: "sp18" },
];

/** L'etichetta di ciascun driver dentro la frase «Cresce con …». */
export const DRIVER_LABELS: Record<SpIndexingDriver, string> = {
  ricavi: "i ricavi",
  acquisti: "gli acquisti (materie e servizi)",
  personale: "il costo del personale",
};

export const DRIVERS: readonly SpIndexingDriver[] = ["ricavi", "acquisti", "personale"];

/**
 * Il saldo di pregresso che scadenzia ciascuna voce (Ruling 17). Dichiarare un
 * piano significa «questo saldo lo sto estinguendo», dichiarare un driver
 * significa «questo saldo si rigenera col volume»: due affermazioni
 * contraddittorie sulla stessa voce. Il motore ignora la chiave e lo dichiara in
 * `indicizzazione_ignorata`, ma il contratto chiede che l'interfaccia lo
 * IMPEDISCA — perche' un selettore vivo che afferma «Cresce con i ricavi» mentre
 * il motore sta estinguendo la voce e' peggio del divieto: e' una bugia a schermo.
 */
const PIANO_DI: Record<string, string> = {
  sp16f: "debiti_previdenziali", sp17f: "debiti_previdenziali",
  sp16g: "altri_debiti", sp17g: "altri_debiti",
  sp17d: "debiti_fornitori",
};

/** I saldi che hanno davvero un piano di scadenziamento in questo scenario.
 *  Il piano vive SOLO sulla riga del primo anno, come il motore pretende. */
export function pianiPregressoOf(
  assumptions: AssumptionsMap,
  forecastYears: number[],
): string[] {
  const piano = assumptions[forecastYears[0]]?.pregresso;
  if (!piano) return [];
  return Object.entries(piano)
    .filter(([, v]) => v != null)
    .map(([k]) => k);
}

export interface MinorFieldRow extends CircolanteTableRow {
  /** Il codice SP, `null` quando nessun driver puo' agganciare la voce. */
  code: string | null;
  /** Il driver scelto per questa voce, `null` se nessuno. */
  driver: SpIndexingDriver | null;
  /**
   * La frase che dice che cosa fa questa voce nel piano — la cosa che oggi non
   * dice nessuno. La sorpresa vera non e' l'assenza dell'indicizzazione: e' che
   * una voce lasciata vuota resti FERMA per tutto il piano senza un segnale.
   */
  andamento: string;
  /** La voce si muove con un driver di volume — dal `sp_indexing` o
   *  dall'interruttore previdenza/personale. Decide l'icona, che percio' non
   *  si decide nel componente. */
  agganciata: boolean;
}

/**
 * L'aggancio per anno e' un'ipotesi come le altre — il motore la legge riga per
 * riga — ma la scelta e' una sola: si legge quella del primo anno previsto,
 * stesso criterio di `boolAssumption`.
 */
export function spIndexingOf(
  assumptions: AssumptionsMap,
  forecastYears: number[],
): Record<string, SpIndexingDriver> {
  const raw = assumptions[forecastYears[0]]?.sp_indexing;
  return raw ?? {};
}

/** Le 14 voci minori: importo base, driver scelto e frase di andamento. */
export function minorFieldsRows(
  baseBs: BalanceSheet | undefined | null,
  indexing: Record<string, SpIndexingDriver> = {},
  previdenzaSuPersonale = false,
  pianiPregresso: readonly string[] = [],
): MinorFieldRow[] {
  const b = (k: string) => euro(baseBs ? numOrNull((baseBs as unknown as Record<string, unknown>)[k]) : null);
  return MINOR_FIELDS.map((v) => {
    // L'interruttore E' gia' l'indicizzazione di sp16f/sp17f al costo del
    // personale: con quello acceso il motore ignora una chiave su quelle due
    // voci, quindi l'interfaccia mostra l'aggancio che vale davvero.
    const switchOwned = previdenzaSuPersonale && (v.code === "sp16f" || v.code === "sp17f");
    // Ruling 17: con un piano la voce si estingue, e nessun driver la governa.
    const conPiano = Boolean(v.code && pianiPregresso.includes(PIANO_DI[v.code] ?? ""));
    const driver = v.code && !switchOwned && !conPiano ? indexing[v.code] ?? null : null;
    const andamento = conPiano
      ? "Governata dal piano di scadenziamento"
      : v.governata
        ? `Governata ${v.governata}`
        : switchOwned
          ? `Cresce con ${DRIVER_LABELS.personale}`
          : driver
            ? `Cresce con ${DRIVER_LABELS[driver]}`
            : "Costante per tutto il piano, salvo variazione %";
    // Con un piano il motore scrive `base − massa` (che vale zero) o il residuo
    // del runoff: la percentuale e' inerte tanto quanto il driver.
    const inerte = Boolean(driver) || switchOwned || conPiano || v.inerte === true;
    return {
      field: v.field, label: v.label, baseLabel: b(v.baseField),
      code: switchOwned || conPiano ? null : v.code, driver, andamento,
      agganciata: Boolean(driver) || switchOwned,
      sub: andamento,
      // Un driver (o un piano) vince sulla percentuale: la casella resterebbe
      // viva senza alcun effetto, ed e' esattamente il difetto da cui nasce
      // `lib/budget-year-cell.ts`.
      ...(inerte
        ? { off: true, offNote: `${andamento}: la variazione % non viene applicata` }
        : {}),
    };
  });
}

/** L'interruttore per anno vive in `lib/budget-horizon.ts`, con `AssumptionsMap`:
 *  qui si ri-esporta perche' il passo 5 legga tutto dal proprio modulo. */
export { boolAssumption, type BoolAssumptionField } from "@/lib/budget-horizon";

export interface CircolantePreview {
  /** Gli anni che il motore ha davvero prodotto, non quelli richiesti. */
  years: number[];
  rows: PreviewRow[];
}

const EMPTY_PREVIEW: CircolantePreview = { years: [], rows: [] };

/** Dalla risposta del motore alle righe dell'anteprima. Senza anno base
 *  (SP o CE) o senza risposta non c'e' anteprima: nessuna riga, non righe
 *  a zero. */
export function circolantePreview(
  baseBs: BalanceSheet | undefined | null,
  baseInc: IncomeStatement | undefined | null,
  data: ForecastPreviewResponse | null,
): CircolantePreview {
  if (!baseBs || !baseInc || !data) return EMPTY_PREVIEW;
  const previewYears = data.forecast_years ?? [];
  return { years: previewYears.map((y) => y.year), rows: rowsCircolante(baseBs, baseInc, previewYears) };
}
