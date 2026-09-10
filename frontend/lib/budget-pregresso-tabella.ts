/**
 * Le decisioni della TABELLA del pregresso di circolante (passo 6 del wizard
 * ipotesi, task-7-brief.md): che cosa mostra ogni cella, che cosa scrive un
 * tocco, e — la cosa che nessun'altra schermata dice — che cosa accadra' alla
 * voce che si sta scadenziando.
 *
 * Il modello e la validazione stanno in `lib/budget-pregresso-circolante.ts`
 * (masse di apertura, `validatePregresso`, le conversioni importo/percentuale,
 * `withAmount`, `residualAfter`): qui non se ne riscrive nulla, si compone.
 *
 * Sta in `lib/` per lo stesso motivo di `budget-costi-step.ts` e
 * `budget-pregresso-step.ts`: in questo repo non c'e' jsdom e non va aggiunto,
 * quindi ogni decisione vive qui con la sua suite `environment: node`, e
 * `components/budget/wizard/PregressoTable.tsx` si limita a renderla.
 *
 * Modulo puro: nessun import da `app/` o da `components/`.
 */
import type { BalanceSheet, ForecastPreviewYear, Pregresso, PregressoKey, PregressoPlan } from "@/types/api";
import { euro } from "@/lib/budget-format";
import {
  PREGRESSO_LABELS,
  amountToPct,
  isPlanEmpty,
  openingMassLong,
  openingMasses,
  pctToAmount,
  residualAfter,
  withAmount,
} from "@/lib/budget-pregresso-circolante";

/** L'importo canonico e' l'euro; la percentuale e' una VISTA sulla stessa
 *  cella (spec §3.5), e cio' che si scrive nel piano resta sempre un euro. */
export type PregressoMode = "eur" | "pct";

/** Le due liste per anno di un piano: gli incassi/pagamenti e — sui soli
 *  crediti — l'inesigibile. */
export type PregressoTarget = "amounts" | "writeoff";

/**
 * Che cosa fa il PREVISIONALE con la voce, una volta scadenziato il pregresso.
 *
 * - `rigenera`: il piano la fa nascere da un driver di volume, quindi
 *   scadenziare il pregresso ne cambia la composizione, non la fa sparire.
 * - `estingue`: il piano non la genera affatto — la porta a zero e ce la
 *   lascia, per tutti gli anni. E' il comportamento voluto, ed e' anche la
 *   sorpresa: due voci che si dichiarano allo stesso modo si comportano in
 *   modo opposto.
 * - `imposte`: la voce si rigenera, ma dalle IMPOSTE dell'anno, non da un
 *   driver di volume — e' il caso dei tributari, che si scadenziano al passo 7
 *   e dove il piano governa il solo rateizzato.
 */
export type PregressoDestino = "rigenera" | "estingue" | "imposte";

/**
 * Misurato su `calculations/forecast_engine.py` (task-7-brief.md, verificato di
 * nuovo su questa base): il piano genera da un driver **solo** crediti
 * commerciali (`ricavi × DSO / 360`), rimanenze e debiti fornitori
 * (`acquisti × DPO / 360`); previdenziali e altri debiti passano invece da
 * `_net_of_pregresso`, che scorpora dall'ancora l'intera massa dichiarata — il
 * generato vale allora zero, e il saldo resta il solo residuo del piano.
 *
 * Nota: per i previdenziali questo vale ANCHE con l'interruttore «scalano col
 * costo del personale» acceso. Quel ramo ancora la formula all'anno base
 * (`_net_of_pregresso(_base(sp16f), …, from_base=True) × fattore`), e la
 * massa scorporata e' la stessa: `base − base = 0`. L'aggancio non rigenera
 * cio' che il piano ha dichiarato.
 */
const DESTINI: Record<PregressoKey, PregressoDestino> = {
  crediti_commerciali: "rigenera",
  debiti_fornitori: "rigenera",
  debiti_tributari: "imposte",
  debiti_previdenziali: "estingue",
  altri_debiti: "estingue",
};

/** Le quattro voci che questa tabella scadenzia. I tributari NON ci sono: si
 *  regolano al passo 7, dove il piano dei rateizzati vive accanto a saldo e
 *  acconti. */
export const TABELLA_KEYS: readonly PregressoKey[] = [
  "crediti_commerciali", "debiti_fornitori", "debiti_previdenziali", "altri_debiti",
];

/** Il solo saldo su cui il motore legge una lista `writeoff`
 *  (`_suppress_unrecordable_writeoffs` guarda `crediti_commerciali`). */
const WRITEOFF_KEYS: readonly PregressoKey[] = ["crediti_commerciali"];

const DESTINO_NOTE: Record<PregressoDestino, string> = {
  rigenera:
    "Si rigenera: il previsionale ne crea di nuovi dal volume d'affari, quindi qui decidi solo quando rientra il pregresso.",
  estingue:
    "Non si rigenera: il previsionale non ne crea di nuovi, quindi ciò che scadenzi qui va a zero e ci resta per tutto il piano.",
  imposte:
    "Si rigenera dalle imposte: ogni anno di piano genera il proprio debito tributario, quindi qui si scadenzia il solo rateizzato già a bilancio.",
};

/**
 * La nota di destino, condizionata alla massa OLTRE l'esercizio (rilievo 1,
 * giro di correzione 1). Fornitori e crediti sono "rigenera", ma il motore
 * rigenera dal driver (giorni medi) **solo il lato a breve**: il lato oltre,
 * una volta scadenziato, diventa `residual_long` e ci resta — la sua
 * percentuale di crescita smette di applicarsi (`forecast_engine.py:1780-1794`,
 * `:2086-2093`, misurato nella revisione del task 7).
 *
 * `"Si rigenera"` senza condizioni resta vera SOLO quando non c'e' massa
 * oltre l'esercizio da scadenziare (`massLong` a zero): e' il caso comune, e
 * la frase originale del task 7 torna quella. Con massa lunga la nota lo dice
 * esplicitamente, cifra in euro compresa — un utente che scadenzia
 * `debiti_fornitori` deve leggere che `sp17d` si estingue, non che "si
 * rigenera" come il resto della riga.
 *
 * `estingue` e `imposte` non hanno bisogno di questa condizione: sono vere su
 * tutta la massa, breve e lunga, per costruzione (brief, tabella).
 */
function destinoNotaFor(destino: PregressoDestino, massLong: number): string {
  if (destino === "rigenera" && massLong > 0) {
    return "Il lato a breve si rigenera dai giorni medi; la parte oltre l'esercizio " +
      `(${euro(massLong)}) si estingue con questo piano e smette di crescere alla sua percentuale.`;
  }
  return DESTINO_NOTE[destino];
}

/** Le masse di apertura tutte a zero, per il ripiego di `pregressoRighe`
 *  quando il chiamante non ha (ancora) una massa lunga da passare. */
const ZERO_MASSES: Record<PregressoKey, number> = {
  crediti_commerciali: 0, debiti_fornitori: 0, debiti_tributari: 0, debiti_previdenziali: 0, altri_debiti: 0,
};

/** La via d'uscita, detta per esteso: chi vuole rimettere a bilancio un debito
 *  che il piano non rigenera lo scrive a mano in SP Prev. */
export const PREGRESSO_VIA_USCITA =
  "Per rimettere a bilancio una voce che il piano non rigenera si inserisce l'importo a mano in SP Prev. " +
  "(override dello stato patrimoniale previsto): da lì alleggerisce anche il fabbisogno di cassa.";

export function destinoOf(key: PregressoKey): PregressoDestino {
  return DESTINI[key];
}

/**
 * La nota `mode: "legacy"` dell'anteprima (`rowsPregressoRunoff`,
 * `lib/budget-preview-rows.ts`): il saldo per cui NESSUN piano e' stato
 * dichiarato, quindi il motore usa le formule di sempre. Prima del giro di
 * correzione 1 era una frase sola per tutti e cinque i saldi — «nessun piano:
 * tutto nel primo anno» — vera per fornitori e crediti (un driver di volume
 * li rigenera comunque, ed e' l'ipotesi implicita di spec §3.1), ma non per
 * previdenziali e altri debiti: senza driver il motore fa `prev × (1+%)`
 * (misurato di nuovo su questa base, `mode: legacy`: `sp16g` cresce anno su
 * anno, non si azzera — vedi task-7-fix1-report.md §Rilievo 4). Dire "tutto
 * nel primo anno" su quei due sarebbe la stessa fabbricazione che CLAUDE.md
 * vieta altrove ("diagnose, never fabricate"): il testo si completa per
 * chiave con cio' che la voce fa davvero, non si lascia uguale per tutte.
 *
 * `destinoOf` decide anche qui: `rigenera`/`imposte` mantengono la chiusura
 * nel primo anno (un driver — di volume o fiscale — sostituisce comunque il
 * vecchio saldo), `estingue` no.
 */
const LEGACY_NOTE_BY_DESTINO: Record<PregressoDestino, string> = {
  rigenera: "nessun piano: tutto nel primo anno, poi si rigenera dal volume d'affari",
  estingue: "nessun piano: non si chiude — cresce ogni anno della percentuale impostata",
  imposte: "nessun piano: tutto nel primo anno, poi si rigenera dalle imposte dell'anno",
};

export function legacyNoteFor(key: PregressoKey): string {
  return LEGACY_NOTE_BY_DESTINO[destinoOf(key)];
}

/** Le masse di apertura del bilancio base, o tutte a zero quando l'anno base
 *  non c'e' ancora. Senza anno base la tabella non si rende affatto (il passo
 *  lo dice); serve perche' la forma del valore non cambi mentre i dati
 *  arrivano. */
export function massesOf(baseBs: BalanceSheet | undefined | null): Record<PregressoKey, number> {
  return baseBs ? openingMasses(baseBs) : ZERO_MASSES;
}

/** Le masse OLTRE l'esercizio, stesso ripiego di `massesOf` senza anno base:
 *  serve solo alla nota di destino (`destinoNotaFor`), mai alla validazione o
 *  al residuo — quelle restano sulla massa intera. */
export function massesLongOf(baseBs: BalanceSheet | undefined | null): Record<PregressoKey, number> {
  if (!baseBs) return ZERO_MASSES;
  const keys = Object.keys(PREGRESSO_LABELS) as PregressoKey[];
  return Object.fromEntries(keys.map((k) => [k, openingMassLong(baseBs, k)])) as Record<PregressoKey, number>;
}

export interface PregressoRiga {
  key: PregressoKey;
  label: string;
  /** La massa di apertura dal bilancio base. */
  mass: number;
  destino: PregressoDestino;
  /** La frase da mostrare sotto l'etichetta. */
  destinoNota: string;
  /** La voce accetta un piano di inesigibile. */
  writeoff: boolean;
  /** Il piano gia' dichiarato, `null` finche' nessuno l'ha toccato: un piano
   *  assente e un piano a zero non sono la stessa cosa (senza piano il motore
   *  usa le formule di sempre, `mode: legacy`). */
  plan: PregressoPlan | null;
}

/** Le righe della tabella, nell'ordine di `keys`.
 *
 * `massesLong` e' facoltativa (default: tutte a zero) perche' il passo 7
 * (tributari) non ne ha una da passare — la sua nota e' `imposte`, indifferente
 * alla massa lunga — e non deve costruirne una finta solo per compilare. */
export function pregressoRighe(
  keys: readonly PregressoKey[],
  masses: Record<PregressoKey, number>,
  pregresso: Pregresso,
  massesLong: Record<PregressoKey, number> = ZERO_MASSES,
): PregressoRiga[] {
  return keys.map((key) => {
    const destino = destinoOf(key);
    return {
      key,
      label: PREGRESSO_LABELS[key],
      mass: masses[key] ?? 0,
      destino,
      destinoNota: destinoNotaFor(destino, massesLong[key] ?? 0),
      writeoff: WRITEOFF_KEYS.includes(key),
      plan: (pregresso[key] as PregressoPlan | null | undefined) ?? null,
    };
  });
}

const listOf = (plan: PregressoPlan, target: PregressoTarget): number[] =>
  (target === "amounts" ? plan.amounts : plan.writeoff) ?? [];

/**
 * Il valore da mostrare nella cella dell'anno `yearIndex`.
 *
 * `null` — cioe' cella VUOTA — quando non c'e' piano o quando quell'anno non
 * e' mai stato toccato: uno zero scritto dall'utente e un anno mai compilato
 * non sono la stessa cosa, e riempire di zeri una tabella di cinque colonne la
 * rende illeggibile.
 *
 * In `pct` si mostra l'incidenza sulla massa di apertura, arrotondata a due
 * decimali perche' il campo resti digitabile; l'importo scritto nel piano
 * resta l'euro.
 */
export function cellValue(
  plan: PregressoPlan | null,
  yearIndex: number,
  mode: PregressoMode,
  target: PregressoTarget,
): number | null {
  if (!plan) return null;
  const list = listOf(plan, target);
  if (yearIndex >= list.length) return null;
  const amount = list[yearIndex];
  if (mode === "eur") return amount;
  const pct = amountToPct(amount, plan.opening);
  return pct === null ? null : Math.round(pct * 100) / 100;
}

/** Nuovo piano con l'inesigibile dell'anno `yearIndex` sostituito — passa da
 *  `withAmount` (rilievo 7, giro di correzione 1): prima ripeteva a mano lo
 *  stesso arrotondamento sulla lista `writeoff`, due copie che un cambio a
 *  una sola avrebbe fatto divergere. */
function withWriteoff(plan: PregressoPlan, yearIndex: number, amount: number): PregressoPlan {
  return withAmount(plan, yearIndex, amount, "writeoff");
}

/**
 * Scrive una cella e restituisce un `Pregresso` nuovo. Immutabile: non muta
 * nulla di cio' che riceve.
 *
 * Il piano nasce al PRIMO TOCCO con l'apertura del bilancio base (spec §3.5):
 * dichiarare un'apertura diversa da quella e' l'errore che `validatePregresso`
 * riconosce, quindi non c'e' modo di crearne uno gia' sbagliato.
 *
 * Un campo svuotato (`null`) scrive uno ZERO, non lascia il vecchio importo:
 * cancellare una cella deve togliere quell'incasso dal piano.
 *
 * Se il risultato e' un piano tutto a zero — importi E svalutazioni, vedi
 * `isPlanEmpty` — la scrittura torna a `null` invece di lasciare
 * `{opening, amounts:[0]}` (rilievo 2, giro di correzione 1): un piano che non
 * paga nulla non e' una scadenza dichiarata, ed e' la regola del repo "debito
 * senza scadenza dichiarata → a breve" applicata a se stessa — senza questo,
 * l'utente che tocca e poi svuota una cella non ha modo di tornare a "nessun
 * piano", e il residuo sparisce tutto oltre l'esercizio anche se non ha mai
 * scadenziato nulla.
 */
export function withCell(
  pregresso: Pregresso,
  key: PregressoKey,
  masses: Record<PregressoKey, number>,
  yearIndex: number,
  value: number | null,
  mode: PregressoMode,
  target: PregressoTarget,
): Pregresso {
  const current = (pregresso[key] as PregressoPlan | null | undefined) ?? null;
  const plan: PregressoPlan = current ?? { opening: masses[key] ?? 0, amounts: [] };
  const amount = mode === "pct" ? pctToAmount(value ?? 0, plan.opening) : value ?? 0;
  const next = target === "amounts" ? withAmount(plan, yearIndex, amount) : withWriteoff(plan, yearIndex, amount);
  return { ...pregresso, [key]: isPlanEmpty(next) ? null : next };
}

/** Il residuo dopo l'ultimo anno di piano. Senza piano il residuo e' ZERO
 *  (rilievo 4, giro di correzione 1): non e' che non resti nulla da
 *  scadenziare, e' che senza piano la spec (§3.1, §3.5, §6) e il motore
 *  chiudono tutta la massa nel primo anno — mostrare la massa intera nella
 *  colonna Residuo diceva l'opposto di cio' che l'anteprima (`rowsPregressoRunoff`,
 *  nota "legacy") gia' affermava sulla stessa riga. */
export function residualCell(plan: PregressoPlan | null, lastIndex: number): number {
  return plan ? residualAfter(plan, lastIndex) : 0;
}

/**
 * Il segnaposto della cella (spec §6, brief Step 2 — "riga vuota → tutto nel
 * primo anno"). Senza piano la sola cifra vera da comunicare e' che TUTTO il
 * saldo si chiude nel primo anno di piano: lo dice nella prima colonna, dove
 * l'utente guarderebbe per scadenziarlo. Le altre celle di una riga senza
 * piano, e ogni cella di una riga CON piano, restano l'unita' di misura della
 * modalita' attiva — non c'e' nulla di speciale da dire su un anno che non e'
 * il primo quando non c'e' ancora nessuna scadenza dichiarata.
 */
export function cellPlaceholder(plan: PregressoPlan | null, yearIndex: number, mode: PregressoMode): string {
  if (!plan && yearIndex === 0) return "tutto nel primo anno";
  return mode === "pct" ? "%" : "€";
}

/** Il nome leggibile dell'override che ha vinto sull'inesigibile. */
const REASON_LABELS: Record<string, string> = {
  ce09d_override: "Svalutazione crediti (ce09d)",
  ce09_override: "Ammortamenti e svalutazioni (ce09)",
};

interface WriteoffIgnoredRaw {
  saldo?: string;
  field?: string;
  requested?: number;
  reason?: string;
}

/**
 * Gli avvisi per gli anni in cui un inesigibile scadenziato NON e' stato
 * scaricato, perche' un override dell'utente sul CE impediva di rilevarne il
 * costo. Un credito che l'utente credeva svalutato e che invece e' rimasto a
 * bilancio va detto, non lasciato dedurre.
 *
 * Una chiave assente vale zero (nessun avviso): il motore la dichiara sempre,
 * ma il tipo la promette facoltativa e una risposta piu' vecchia non la porta.
 */
export function writeoffIgnoredAvvisi(years: ForecastPreviewYear[]): string[] {
  const out: string[] = [];
  for (const y of years) {
    for (const raw of (y.details?.pregresso_writeoff_ignored ?? []) as WriteoffIgnoredRaw[]) {
      const reason = REASON_LABELS[raw.reason ?? ""] ?? raw.reason ?? "una modifica manuale del CE";
      out.push(
        `${y.year}: inesigibile di ${euro(raw.requested ?? 0)} non scaricato dai crediti — la modifica manuale su ` +
        `${reason} impedisce di rilevarne il costo in conto economico. Il credito resta a bilancio.`,
      );
    }
  }
  return out;
}

/**
 * Lo stesso avviso di `writeoffIgnoredAvvisi`, ma indicizzato sull'ANNO
 * invece che elencato in una frase (rilievo 6, giro di correzione 1): la
 * tabella lo usa per marcare la cella dove l'utente ha scritto la
 * svalutazione — "di cui inesigibile" — non solo l'anteprima a destra, dove
 * oggi e' l'unico posto in cui compare. Nessun ricalcolo: legge
 * `pregresso_writeoff_ignored` cosi' come il motore lo dichiara, la stessa
 * chiave e la stessa `REASON_LABELS`.
 *
 * Un anno assente dalla mappa vale "nessun avviso": il motore dichiara al
 * piu' una voce per anno (il solo saldo con `writeoff` e' `crediti_commerciali`).
 */
export function writeoffIgnoredByYear(years: ForecastPreviewYear[]): Record<number, string> {
  const out: Record<number, string> = {};
  for (const y of years) {
    const raw = ((y.details?.pregresso_writeoff_ignored ?? []) as WriteoffIgnoredRaw[])[0];
    if (!raw) continue;
    const reason = REASON_LABELS[raw.reason ?? ""] ?? raw.reason ?? "una modifica manuale del CE";
    out[y.year] = `${euro(raw.requested ?? 0)} non scaricato — ${reason}`;
  }
  return out;
}
