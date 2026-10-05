/**
 * Le decisioni del passo 5 «Capitale circolante» (spec 2026-09-08 §4.5,
 * task-13-brief.md).
 *
 * Sta in `lib/` per lo stesso motivo di `budget-costi-step.ts` (Task 12): nessun jsdom
 * in questo repo, quindi ogni decisione — quale giorno "auto" mostrare, quale importo base ha una
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
import type { BalanceSheet, ForecastPreviewResponse, ForecastPreviewYear, IncomeStatement, SpIndexingDriver } from "@/types/api";

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
  dio_pf: number | null;
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
    dio_pf: computeAutoDays("dio_pf", baseInc ?? undefined, baseBs ?? undefined),
    dpo: computeAutoDays("dpo", baseInc ?? undefined, baseBs ?? undefined),
  };
}

const dayLabel = (n: number | null): string => (n === null ? "n/d" : `${n} gg`);
const autoPlaceholder = (n: number | null) => () => (n === null ? "auto" : `auto ${n}`);

/** L'etichetta di ciascuno dei tre giorni medi, in un posto solo: le righe
 *  della tabella e gli avvisi devono chiamarli allo stesso modo.
 *
 *  `dio` (lotto 1 fix rilievi, rilievo I2 della revisione finale, 2026-09-26): dal B01 questo
 *  campo e' i giorni delle sole MATERIE PRIME sul loro consumo (`ce05+ce10`), non piu' un giorno
 *  di rotazione di tutto il magazzino sui ricavi — l'etichetta "(DIO)" da sola lo presenta ancora
 *  come prima. */
const GIORNI_LABELS: Record<string, string> = {
  dso: "Giorni incasso clienti (DSO)",
  dio: "Giorni materie prime e semilavorati (sul consumo)",
  dio_pf: "Giorni prodotti finiti e merci (sui ricavi)",
  dpo: "Giorni pagamento fornitori (DPO)",
};

/** Oltre un anno di giacenza il motore scarta il giorno dedotto e riporta il saldo. */
const SOGLIA_GIORNI = 365;

/** Il segnaposto promette solo cio' che il motore applica: oltre soglia resta «auto». */
const autoPlaceholderMagazzino = (n: number | null) => () =>
  (n === null || n > SOGLIA_GIORNI ? "auto" : `auto ${n}`);

/** La nota sotto la casella: il giorno storico del gruppo, anche degenere. */
function notaStorico(n: number | null, baseYear: number | undefined, base: string): string | undefined {
  if (n === null) return undefined;
  const anno = baseYear === undefined ? "" : ` ${baseYear}`;
  const testo = `Storico${anno}: ${n} gg ${base}`;
  return n > SOGLIA_GIORNI
    ? `${testo} — oltre la soglia: senza un valore il motore riporta il saldo`
    : testo;
}

/** Le quattro righe "Giorni medi": DSO, DIO materie, DIO prodotti finiti, DPO. */
export function giorniMediRows(auto: GiorniMedi, baseYear?: number): CircolanteTableRow[] {
  return [
    { field: "dso_days", label: GIORNI_LABELS.dso, baseLabel: dayLabel(auto.dso), placeholder: autoPlaceholder(auto.dso) },
    { field: "dio_days", label: GIORNI_LABELS.dio, baseLabel: dayLabel(auto.dio),
      sub: notaStorico(auto.dio, baseYear, "sul consumo"), placeholder: autoPlaceholderMagazzino(auto.dio) },
    { field: "dio_pf_days", label: GIORNI_LABELS.dio_pf, baseLabel: dayLabel(auto.dio_pf),
      sub: notaStorico(auto.dio_pf, baseYear, "sui ricavi"), placeholder: autoPlaceholderMagazzino(auto.dio_pf) },
    { field: "dpo_days", label: GIORNI_LABELS.dpo, baseLabel: dayLabel(auto.dpo), placeholder: autoPlaceholder(auto.dpo) },
  ];
}

/**
 * Gli avvisi del motore sul magazzino, anno per anno, dall'elenco STRUTTURATO
 * (`details.avviso_rimanenze`): niente filtro sul testo di `details.avvisi`, che
 * mescola imposte e debiti di altri passi. Una chiave assente vale «nessun avviso».
 */
export function avvisiMagazzino(years: ForecastPreviewYear[]): string[] {
  const etichetta: Record<string, string> = {
    materie_semilavorati: "materie prime e semilavorati",
    prodotti_finiti: "prodotti finiti e merci",
  };
  const out: string[] = [];
  for (const y of years) {
    for (const v of y.details?.avviso_rimanenze ?? []) {
      const natura = v.gruppo === "materie_semilavorati"
        ? (v.variazione < 0 ? "di costo" : "di minor costo")
        : (v.variazione > 0 ? "di ricavo" : "di minor ricavo");
      out.push(
        `Nel ${y.year} i giorni inseriti per ${etichetta[v.gruppo] ?? v.gruppo} (${Math.round(v.giorni)} gg) ` +
        `portano il magazzino da ${euro(v.apertura)} a ${euro(v.chiusura)}: ` +
        `${euro(Math.abs(v.variazione))} ${natura} a conto economico.`,
      );
    }
  }
  return out;
}

/**
 * I giorni medi DEDOTTI che il motore ha scartato, anno per anno
 * (`details['degenerate_turnover_ratio']`): una rotazione che implica piu' di
 * un anno di giacenza e' degenere, e in quell'anno il motore **riporta il
 * saldo dell'anno base invece di scalarlo**.
 *
 * Senza questo avviso l'utente legge un giorno medio in tabella e non sa che
 * quel giorno non e' stato applicato. Misurato al Task 14: il `dpo = 3.600` del
 * fixture `holding` fa scattare davvero la guardia, non e' un caso di
 * laboratorio.
 *
 * Una chiave assente vale zero — nessun avviso — non «non lo so»: e' il motore
 * a dichiararla sempre.
 */
export function degenerateDaysAvvisi(data: ForecastPreviewResponse | null): string[] {
  const anni: Record<string, number[]> = {};
  for (const y of data?.forecast_years ?? []) {
    for (const kind of y.details?.degenerate_turnover_ratio ?? []) {
      (anni[kind] ??= []).push(y.year);
    }
  }
  return Object.entries(anni).map(([kind, years]) =>
    `${GIORNI_LABELS[kind] ?? kind}: il valore dedotto dall'anno base è fuori scala (oltre un anno di rotazione), ` +
    `quindi ${years.length === 1 ? "nel" : "negli anni"} ${years.join(", ")} il motore ha riportato il saldo ` +
    "dell'anno base invece di scalarlo.",
  );
}

/**
 * Le 15 voci minori dell'attivo e del passivo, con il codice SP, l'importo base
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
  // Le imposte anticipate sono COSTANTI (commercialista, 2026-09-18): non
  // passano dal conto economico e non hanno una percentuale; si cambiano solo
  // a mano nello SP previsionale, con effetto sulla cassa. Entrambe le
  // righe sono quindi di sola lettura (`inerte`).
  { field: "sp06f", label: "Imposte anticipate entro", baseField: "sp06f_imposte_anticipate_breve",
    code: null, governata: "a mano nello SP previsionale: costanti, effetto sulla cassa", inerte: true },
  { field: "sp07f", label: "Imposte anticipate oltre", baseField: "sp07f_imposte_anticipate_lungo",
    code: null, governata: "a mano nello SP previsionale: costanti, effetto sulla cassa", inerte: true },
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
  balanceField: string;
  /** Saldo storico, usato per separare le voci a zero senza leggere l'etichetta formattata. */
  baseAmount: number | null;
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

/** Le 15 voci minori: importo base, driver scelto e frase di andamento.
 *
 * A06 (lotto 3 fix rilievi, 2026-09-26, decisione del proprietario): la
 * casella «Debiti previdenziali scalano col costo del personale» e' sparita
 * dal wizard — sp16f/sp17f sono voci agganciabili come le altre voci minori, col
 * driver `personale` gia' fra i tre di `sp_indexing`. Non c'e' piu' un doppio
 * comando da arbitrare qui.
 */
export function minorFieldsRows(
  baseBs: BalanceSheet | undefined | null,
  indexing: Record<string, SpIndexingDriver> = {},
  pianiPregresso: readonly string[] = [],
): MinorFieldRow[] {
  const b = (k: string) => euro(baseBs ? numOrNull((baseBs as unknown as Record<string, unknown>)[k]) : null);
  return MINOR_FIELDS.map((v) => {
    // Ruling 17: con un piano la voce si estingue, e nessun driver la governa.
    const conPiano = Boolean(v.code && pianiPregresso.includes(PIANO_DI[v.code] ?? ""));
    const driver = v.code && !conPiano ? indexing[v.code] ?? null : null;
    const andamento = conPiano
      ? "Governata dal piano di scadenziamento"
      : v.governata
        ? `Governata ${v.governata}`
        : driver
          ? `Cresce con ${DRIVER_LABELS[driver]}`
          : "Costante per tutto il piano, salvo variazione %";
    // Con un piano il motore scrive `base − massa` (che vale zero) o il residuo
    // del runoff: la percentuale e' inerte tanto quanto il driver.
    const inerte = Boolean(driver) || conPiano || v.inerte === true;
    return {
      field: v.field, label: v.label, baseLabel: b(v.baseField), balanceField: v.baseField,
      baseAmount: baseBs ? numOrNull((baseBs as unknown as Record<string, unknown>)[v.baseField]) : null,
      code: conPiano ? null : v.code, driver, andamento,
      agganciata: Boolean(driver),
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
  /** I giorni medi dedotti che il motore ha scartato: il saldo base e' stato
   *  riportato, non scalato. Vuoto quando non scatta nulla. */
  degenerateDays: string[];
}

const EMPTY_PREVIEW: CircolantePreview = { years: [], rows: [], degenerateDays: [] };

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
  return {
    years: previewYears.map((y) => y.year),
    rows: rowsCircolante(baseBs, baseInc, previewYears),
    degenerateDays: degenerateDaysAvvisi(data),
  };
}
