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
 * - `altrove`: la voce non si governa qui (i tributari seguono la posizione
 *   fiscale, al passo 7).
 */
export type PregressoDestino = "rigenera" | "estingue" | "altrove";

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
  debiti_tributari: "altrove",
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
  altrove: "Segue la posizione fiscale: si regola al passo Imposte.",
};

/** La via d'uscita, detta per esteso: chi vuole rimettere a bilancio un debito
 *  che il piano non rigenera lo scrive a mano in SP Prev. */
export const PREGRESSO_VIA_USCITA =
  "Per rimettere a bilancio una voce che il piano non rigenera si inserisce l'importo a mano in SP Prev. " +
  "(override dello stato patrimoniale previsto): da lì alleggerisce anche il fabbisogno di cassa.";

export function destinoOf(key: PregressoKey): PregressoDestino {
  return DESTINI[key];
}

/** Le masse di apertura del bilancio base, o tutte a zero quando l'anno base
 *  non c'e' ancora. Senza anno base la tabella non si rende affatto (il passo
 *  lo dice); serve perche' la forma del valore non cambi mentre i dati
 *  arrivano. */
export function massesOf(baseBs: BalanceSheet | undefined | null): Record<PregressoKey, number> {
  return baseBs
    ? openingMasses(baseBs)
    : { crediti_commerciali: 0, debiti_fornitori: 0, debiti_tributari: 0, debiti_previdenziali: 0, altri_debiti: 0 };
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

/** Le righe della tabella, nell'ordine di `keys`. */
export function pregressoRighe(
  keys: readonly PregressoKey[],
  masses: Record<PregressoKey, number>,
  pregresso: Pregresso,
): PregressoRiga[] {
  return keys.map((key) => {
    const destino = destinoOf(key);
    return {
      key,
      label: PREGRESSO_LABELS[key],
      mass: masses[key] ?? 0,
      destino,
      destinoNota: DESTINO_NOTE[destino],
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

/** Nuovo piano con l'inesigibile dell'anno `yearIndex` sostituito — il gemello
 *  di `withAmount` sulla lista `writeoff`, immutabile allo stesso modo. */
function withWriteoff(plan: PregressoPlan, yearIndex: number, amount: number): PregressoPlan {
  const writeoff = [...(plan.writeoff ?? [])];
  while (writeoff.length <= yearIndex) writeoff.push(0);
  writeoff[yearIndex] = Math.round(amount * 100) / 100;
  return { ...plan, writeoff };
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
  return { ...pregresso, [key]: next };
}

/** Il residuo dopo l'ultimo anno di piano. Senza piano il residuo e' TUTTA la
 *  massa: nulla e' stato scadenziato, e mostrare zero direbbe il contrario. */
export function residualCell(plan: PregressoPlan | null, mass: number, lastIndex: number): number {
  return plan ? residualAfter(plan, lastIndex) : mass;
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
