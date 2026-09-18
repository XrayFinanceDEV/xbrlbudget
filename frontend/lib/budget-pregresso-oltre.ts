/**
 * Le decisioni del passo 5 «Patrimoniale pregresso» (spec 2026-09-15 §4.5)
 * sulla parte che il previsonale NON chiude da sola: i saldi a breve, che si
 * liquidano nel primo anno di piano per regola del proprietario, e la parte
 * OLTRE i 12 mesi, che l'utente scadenzi a mano anno per anno.
 *
 * Il modello e la validazione restano in `lib/budget-pregresso-circolante.ts`
 * (`openingMasses`, `openingMassLong`, `validatePregresso`): qui non se ne
 * riscrive nulla, si compone — le masse a breve e oltre sono LETTE da lì, mai
 * ricalcolate una seconda volta (due formule che divergono su `sp07` al netto
 * delle quote fiscali sono il rilievo 1 del giro di correzione del task 7).
 *
 * I debiti tributari rateizzati sono qui da decisione del proprietario del
 * 2026-09-15 (spec §3, §9.1, Task 13b): il piano — saldo, rateizzato, rate,
 * acconto — resta il modello di `lib/budget-imposte-step.ts` (`tributariPlan`,
 * `tributariPlanOrDefault`, `withRate`, invariati), qui si compone solo la
 * riga «oltre 12 mesi» che scadenzia il rateizzato, come le altre quattro. Il
 * passo 7 «Imposte» tiene aliquota, differenze temporanee, via manuale e
 * acconto — non tocca `amounts`.
 *
 * Sta in `lib/` per il motivo solito di questo repo: nessun jsdom, quindi
 * ogni decisione vive qui con la sua suite `environment: node` e
 * `steps/StepPatrimonialePregresso.tsx` rende soltanto.
 *
 * Modulo puro: nessun import da `app/` o da `components/`.
 */
import type { BalanceSheet, Pregresso, PregressoPlan, PregressoTributari } from "@/types/api";
import { openingMassLong, openingMasses } from "@/lib/budget-pregresso-circolante";
import { tributariOpening, tributariPlan, tributariPlanOrDefault, withRate } from "@/lib/budget-imposte-step";
import { baseBankDebt } from "@/lib/base-bank-debt";
import { num } from "@/lib/budget-format";

const cents = (v: number) => Math.round(v * 100) / 100;

/** I saldi che questo passo scadenzia OLTRE l'esercizio con la stessa forma
 *  di riga (`OltreRow`). `debiti_tributari` non c'e': ha il suo tipo
 *  (`TributariOltreRow`) perche' l'apertura della riga e' il rateizzato del
 *  piano tributario, non una massa letta dal bilancio — vedi
 *  `tributariOltreRow` piu' sotto. */
export type OltreKey = "crediti_commerciali" | "altri_debiti" | "debiti_fornitori" | "debiti_previdenziali";

/** L'ordine delle righe della card (spec §4.5): i due saldi che hanno SEMPRE
 *  una riga per primi, poi gli altri due, che una riga la hanno solo con
 *  massa oltre. `budget-pregresso-flussi.ts` prende da qui la chiave. */
export const OLTRE_KEYS: readonly OltreKey[] = [
  "crediti_commerciali", "altri_debiti", "debiti_fornitori", "debiti_previdenziali",
];

export const OLTRE_LABELS: Record<OltreKey, string> = {
  crediti_commerciali: "Crediti oltre 12 mesi",
  altri_debiti: "Altri debiti oltre 12 mesi",
  debiti_fornitori: "Debiti fornitori oltre 12 mesi",
  debiti_previdenziali: "Debiti previdenziali oltre 12 mesi",
};

/** Il verso del flusso: un credito si incassa, un debito si paga. Decide il
 *  segno dell'anteprima e il colore del chip a schermo. */
export const OLTRE_DIREZIONI: Record<OltreKey, "in" | "out"> = {
  crediti_commerciali: "in",
  altri_debiti: "out",
  debiti_fornitori: "out",
  debiti_previdenziali: "out",
};

/** Crediti e altri debiti hanno una riga anche con massa oltre a zero: il
 *  primo perche' l'inesigibile e la casella «non incassati» si dichiarano
 *  comunque, il secondo perche' e' il secchio di ripiego di tutto il passivo
 *  circolante e l'utente deve poterlo scadenziare anche quando l'anno base
 *  non lo mostra. Fornitori e previdenziali, no: senza parte oltre non c'e'
 *  nulla da scadenziare a mano. */
const RIGA_SEMPRE: readonly OltreKey[] = ["crediti_commerciali", "altri_debiti"];

/**
 * La parte del saldo che rientra (o si paga) ENTRO l'esercizio successivo.
 *
 * Mai una formula a se': la differenza `openingMasses − openingMassLong` e'
 * l'unica lettura possibile perche' sono li' che vivono le due masse, e per i
 * crediti `openingMasses` scorpora gia' i crediti tributari e le imposte
 * anticipate (`creditiComponents`). Riscriverla qui (o in `budget-pregresso-
 * flussi.ts`) farebbe divergere le caselle di questo passo dall'anteprima.
 */
export function massaBreve(baseBs: BalanceSheet | undefined | null, key: OltreKey): number {
  if (!baseBs) return 0;
  return cents(openingMasses(baseBs)[key] - openingMassLong(baseBs, key));
}

/** La parte OLTRE l'esercizio: `openingMassLong` cosi' com'e', niente di suo. */
export function massaOltre(baseBs: BalanceSheet | undefined | null, key: OltreKey): number {
  return baseBs ? cents(openingMassLong(baseBs, key)) : 0;
}

/** Il ripiego perche' `pianoBase` vuole un oggetto, non `undefined`: l'identita'
 *  di `pianoBase` si misura anche su questo, quindi dev'essere una costante di
 *  modulo e non un `{}` letterale (che a ogni render sarebbe nuovo). */
export const PREGRESSO_VUOTO: Pregresso = {};

/** Il piano di partenza di UN saldo: apertura = le due masse, `amounts[0]` =
 *  la massa a breve (regola del proprietario: i saldi a breve si liquidano
 *  nel primo anno), zero negli anni successivi finche' l'utente non scadenzi
 *  la parte oltre.
 *
 *  E' la stessa funzione che usa `pianoBase` e la usano i due scrittori:
 *  `opening` NON puo' essere uno zero qualsiasi, perche' `validatePregresso`
 *  la confronta con `openingMasses` e un'apertura falsa e' un errore che
 *  blocca il salvataggio senza che l'utente possa correggerlo da qui. */
function pianoDiPartenza(baseBs: BalanceSheet, years: number[], key: OltreKey): PregressoPlan {
  const breve = massaBreve(baseBs, key);
  const n = Math.max(1, years.length);
  return {
    opening: cents(breve + massaOltre(baseBs, key)),
    // Un importo per anno di piano, il primo gia' riempito dal breve: la forma
    // che `runoff_schedule` si aspetta, e che `validatePregresso` confronta
    // contro l'orizzonte.
    amounts: [breve, ...new Array<number>(n - 1).fill(0)],
    writeoff: null,
    // Il flag vive SOLO sui crediti: su un debito «non incassato» non
    // significa nulla, e lo schema del motore lo legge solo li'.
    ...(key === "crediti_commerciali" ? { non_incassato: false } : {}),
  };
}

/** Il piano tributario di partenza (spec §4.5, decisione del proprietario del
 *  2026-09-15, Task 13b): saldo = debito a breve (`sp16e`, cio' che scade
 *  entro l'esercizio si paga nel primo anno di piano, come le altre voci di
 *  questo passo), rateizzato = debito oltre (`sp17e`), rate tutte a zero
 *  finche' l'utente non le scadenzia, acconto al 100% (il default del
 *  kernel). E' la STESSA lettura del bilancio che fa `pianoDiPartenza` per le
 *  altre voci: chi vuole un'altra ripartizione fra saldo e rateizzato la
 *  corregge in Rettifiche fra `sp16e` e `sp17e`, non qui. */
function tributariDiPartenza(baseBs: BalanceSheet, years: number[]): PregressoTributari {
  const b = baseBs as unknown as Record<string, unknown>;
  const saldo = cents(num(b.sp16e_debiti_tributari_breve));
  const rateizzato = cents(num(b.sp17e_debiti_tributari_lungo));
  const n = Math.max(1, years.length);
  return {
    opening: cents(saldo + rateizzato),
    saldo,
    rateizzato,
    amounts: new Array<number>(n).fill(0),
    acconto_pct: 100,
  };
}

/**
 * Un piano salvato porta la massa di apertura del bilancio base di QUEL
 * momento. Se poi una rettifica cambia il bilancio base, il motore rifiuta il
 * piano («Il saldo di apertura di … è cambiato: rivedi lo scadenziamento») e
 * da questo passo non c'era modo di rimediare: ogni casella ricopiava
 * l'apertura vecchia (TM BUSINESS GROUP, 2026-09-18). Qui il piano si
 * riallinea al bilancio di oggi, conservando cio' che l'utente ha deciso:
 * - saldi con riga «oltre»: nuova apertura, e nel primo anno il breve di oggi
 *   piu' la quota oltre gia' scadenziata; gli anni successivi e l'inesigibile
 *   restano. La quota oltre del primo anno si misura contro il breve di
 *   allora, cioe' l'apertura salvata meno la massa oltre di oggi.
 * - tributari: rateizzato e rate restano, il saldo assorbe la differenza —
 *   solo se non diventa negativo; altrimenti il piano resta com'e' e la
 *   validazione del passo dice perche'.
 * Nulla da riallineare ⇒ restituisce l'oggetto ricevuto (identita', vedi sotto).
 */
export function riallineaAperture(baseBs: BalanceSheet, pregresso: Pregresso): Pregresso {
  const masses = openingMasses(baseBs);
  const patch: Pregresso = {};
  for (const key of OLTRE_KEYS) {
    const plan = pregresso[key] as PregressoPlan | null | undefined;
    if (plan == null || Math.abs(num(plan.opening) - masses[key]) <= 0.01) continue;
    const breveAllora = num(plan.opening) - massaOltre(baseBs, key);
    const oltrePrimoAnno = Math.max(0, num(plan.amounts[0]) - breveAllora);
    const amounts = plan.amounts.length ? [...plan.amounts] : [0];
    amounts[0] = cents(massaBreve(baseBs, key) + oltrePrimoAnno);
    (patch as Record<string, unknown>)[key] = { ...plan, opening: masses[key], amounts };
  }
  const trib = tributariPlan(pregresso);
  if (trib && Math.abs(num(trib.opening) - masses.debiti_tributari) > 0.01) {
    const saldo = cents(masses.debiti_tributari - num(trib.rateizzato));
    if (saldo >= 0) patch.debiti_tributari = { ...trib, opening: masses.debiti_tributari, saldo };
  }
  return Object.keys(patch).length ? { ...pregresso, ...patch } : pregresso;
}

/**
 * Il piano di base che il wizard compone all'apertura del passo: `amounts[0]`
 * = la massa a breve dell'anno base (regola del proprietario: i saldi a breve
 * si liquidano nel primo anno), zero negli anni successivi finche' l'utente
 * non scadenzi la parte oltre.
 *
 * Scritto SEMPRE per crediti e fornitori (il motore li rigenera dal driver,
 * quindi il pregresso va chiuso esplicitamente); per previdenziali e altri
 * debiti SOLO se c'e' massa oltre, perche' con un piano il motore li ESTINGUE
 * (`_net_of_pregresso`, Ruling 17): senza una parte oltre da scadenziare,
 * restare in via automatica e' cio' che l'utente vede al passo 6.
 *
 * Per i tributari (Task 13b): SOLO se manca e `sp17e > 0` — con `sp17e = 0`
 * non c'e' nulla da rateizzare e il motore paga tutto il tributario come
 * saldo nel primo anno, come oggi, senza bisogno di un piano. Un piano gia'
 * salvato (anche dal vecchio passo 7, anche con un saldo diverso da `sp16e`)
 * si rispetta cosi' com'e': identita', mai ricreato.
 *
 * **Identita' quando non c'e' nulla da aggiungere**: se ogni saldo che vuole
 * un piano ce l'ha gia', restituisce l'oggetto ricevuto com'e'. E' cio' che
 * rende legittimo l'effetto del passo 5 che scrive `pianoBase(...)` solo se
 * `!== salvato`: senza quella garanzia l'effetto si ri-innescherebbe da solo
 * (CLAUDE.md, «un effetto non dipende mai da cio' che lui stesso scrive»).
 */
export function pianoBase(baseBs: BalanceSheet | undefined | null, years: number[], pregresso: Pregresso): Pregresso {
  if (!baseBs) return pregresso;
  pregresso = riallineaAperture(baseBs, pregresso);
  const missing = OLTRE_KEYS.filter((key) => {
    const vuolePiano = key === "crediti_commerciali" || key === "debiti_fornitori" || massaOltre(baseBs, key) > 0;
    return vuolePiano && (pregresso[key] as PregressoPlan | null | undefined) == null;
  });
  const vuoleTributari =
    tributariPlan(pregresso) == null && cents(num((baseBs as unknown as Record<string, unknown>).sp17e_debiti_tributari_lungo)) > 0;
  if (missing.length === 0 && !vuoleTributari) return pregresso;
  const piani: Record<string, PregressoPlan> = {};
  for (const key of missing) piani[key] = pianoDiPartenza(baseBs, years, key);
  return {
    ...pregresso,
    ...piani,
    ...(vuoleTributari ? { debiti_tributari: tributariDiPartenza(baseBs, years) } : {}),
  };
}

/** Che cosa il previsonale fara' della parte oltre di questo saldo: la nota
 *  che la card scrive sotto l'etichetta della riga. Sta qui, e non sul
 *  `OltreRow`, perche' la forma della riga e' quella dell'interfaccia del
 *  piano e questa e' una costante per saldo. */
export const OLTRE_NOTA: Record<OltreKey, string> = {
  crediti_commerciali:
    "Il lato a breve si rigenera dai giorni medi; la parte oltre no: cio' che scadenzi qui va a zero e ci resta.",
  debiti_fornitori:
    "Il lato a breve si rigenera dai giorni di pagamento; la parte oltre no: cio' che scadenzi qui va a zero e ci resta.",
  debiti_previdenziali:
    "Non si rigenera: cio' che scadenzi qui va a zero e ci resta per tutto il piano.",
  altri_debiti:
    "Non si rigenera: cio' che scadenzi qui va a zero e ci resta per tutto il piano.",
};

/**
 * La riga «oltre 12 mesi» di un saldo: gli importi che l'utente scadenzi, al
 * netto della massa a breve che il piano chiude da sola nel primo anno.
 *
 * `amounts[i]` e' `plan.amounts[i] − (i === 0 ? massaBreve : 0)`, mai
 * negativo: il primo anno del piano porta gia' dentro di se' il breve, e
 * mostrare quel breve in una riga che parla d'altro raddoppierebbe il numero
 * a schermo. `null` = casella mai toccata (stessa regola di `cellValue` in
 * `budget-pregresso-tabella.ts`), non zero.
 */
export interface OltreRow {
  key: OltreKey;
  label: string;
  dir: "in" | "out";
  /** La sola massa oltre 12 mesi, non l'apertura intera del saldo. */
  opening: number;
  amounts: (number | null)[];
  /** Quanto della massa oltre non e' ancora scadenzato. Mai negativo. */
  resta: number;
  stato: "chiuso" | "resta aperto" | "nessun movimento nel piano" | "oltre il saldo" | "oltre il piano";
  /** La casella «non incassati nel piano» dei crediti (spec §4.5, decisione 6). */
  nonIncassato: boolean;
  /** Le caselle di questa riga sono spente: le scrive solo `nonIncassato`. */
  disabled: boolean;
}

/** La scritta della colonna «resta»: tre stati neutri (nessun blocco, nessun
 *  avviso: decisione 7) piu' i due che un avviso lo sono davvero. */
export const OLTRE_STATI: Record<OltreRow["stato"], string> = {
  chiuso: "chiuso",
  "resta aperto": "resta aperto",
  "nessun movimento nel piano": "nessun movimento nel piano",
  "oltre il saldo": "oltre il saldo",
  "oltre il piano": "oltre il piano",
};

function statoOltre(mass: number, somma: number, nonIncassato: boolean): OltreRow["stato"] {
  if (nonIncassato) return "oltre il piano";
  if (somma > mass + 0.5) return "oltre il saldo";
  if (mass - somma < 0.5) return "chiuso";
  if (somma < 0.5) return "nessun movimento nel piano";
  return "resta aperto";
}

export function oltreRows(
  baseBs: BalanceSheet | undefined | null, pregresso: Pregresso, years: number[],
): OltreRow[] {
  if (!baseBs) return [];
  return OLTRE_KEYS
    .filter((key) => RIGA_SEMPRE.includes(key) || massaOltre(baseBs, key) > 0)
    .map((key) => {
      const plan = pregresso[key] as PregressoPlan | null | undefined;
      const breve = massaBreve(baseBs, key);
      const mass = massaOltre(baseBs, key);
      const nonIncassato = key === "crediti_commerciali" && plan?.non_incassato === true;
      const amounts = years.map((_, i) => {
        const written = plan?.amounts[i];
        if (written === null || written === undefined) return null;
        return cents(Math.max(0, num(written) - (i === 0 ? breve : 0)));
      });
      const somma = amounts.reduce<number>((a, v) => a + (v ?? 0), 0);
      return {
        key,
        label: OLTRE_LABELS[key],
        dir: OLTRE_DIREZIONI[key],
        opening: mass,
        amounts,
        resta: cents(Math.max(0, mass - somma)),
        stato: statoOltre(mass, somma, nonIncassato),
        nonIncassato,
        disabled: nonIncassato,
      };
    });
}

/** Nuovo piano con l'anno `i` della parte oltre portato a `value`: la massa a
 *  breve del primo anno resta dov'e' e la casella le si aggiunge, perche' e'
 *  quella la somma che il motore legge (spec §4.5). `null` scrive uno zero:
 *  cancellare una cella deve togliere quell'incasso dal piano. */
export function withOltreAmount(
  baseBs: BalanceSheet | undefined | null, pregresso: Pregresso, years: number[],
  key: OltreKey, i: number, value: number | null,
): Pregresso {
  const p = pianoBase(baseBs, years, pregresso);
  const plan = (p[key] as PregressoPlan | undefined) ?? pianoDiPartenza(baseBs ?? ({} as BalanceSheet), years, key);
  const amounts = [...plan.amounts];
  while (amounts.length <= i) amounts.push(0);
  amounts[i] = cents((i === 0 ? massaBreve(baseBs, key) : 0) + (value ?? 0));
  return { ...p, [key]: { ...plan, amounts } };
}

/**
 * La casella «non incassati nel piano (es. infragruppo)» (decisione 6): azzera
 * la parte oltre su ogni anno e scrive il flag, che lo schema del motore
 * accetta, persiste e dichiara (`details['pregresso'][key].non_incassato`).
 *
 * Lo zero non e' decorativo: un piano a zero sulla parte oltre lascia il
 * residuo aperto per costruzione, quindi «non incassare» e' gia' il
 * comportamento del motore — il flag serve a dirlo a schermo, non a
 * comandarlo (spec §5.5).
 */
export function withNonIncassato(
  baseBs: BalanceSheet | undefined | null, pregresso: Pregresso, years: number[], on: boolean,
): Pregresso {
  const key: OltreKey = "crediti_commerciali";
  const p = pianoBase(baseBs, years, pregresso);
  const plan = (p[key] as PregressoPlan | undefined) ?? pianoDiPartenza(baseBs ?? ({} as BalanceSheet), years, key);
  const amounts = on
    ? plan.amounts.map((_, i) => cents(i === 0 ? massaBreve(baseBs, key) : 0))
    : plan.amounts;
  return { ...p, [key]: { ...plan, amounts, non_incassato: on } };
}

/**
 * La riga «Debiti tributari rateizzati» in coda alla tabella «Altre voci
 * oltre 12 mesi» (spec §4.5, decisione del proprietario del 2026-09-15, Task
 * 13b). Ha il suo tipo, non `OltreRow`, perche' l'apertura di QUESTA riga e'
 * il rateizzato del piano tributario (`plan.rateizzato`), mai la massa
 * `sp17e` letta dal bilancio: un piano salvato dal vecchio passo 7 puo' avere
 * un saldo diverso da `sp16e` (l'utente lo ha corretto li'), e la riga deve
 * riflettere QUEL piano, non ricalcolarne uno nuovo dal bilancio.
 */
export interface TributariOltreRow {
  key: "debiti_tributari";
  label: "Debiti tributari rateizzati";
  dir: "out";
  /** Il rateizzato del piano (`plan.rateizzato`), non l'apertura intera
   *  (saldo + rateizzato): e' cio' che questa riga scadenzia. */
  opening: number;
  /** `plan.amounts[i]` cosi' com'e', nessuno scarto di breve: il saldo non
   *  entra mai nel runoff (`forecast_engine.py` scadenzia il solo
   *  `rateizzato`), quindi non c'e' nulla da sottrarre come per le altre
   *  righe. `null` = anno mai scritto nel piano (l'array e' piu' corto
   *  dell'orizzonte), non zero. */
  amounts: (number | null)[];
  resta: number;
  /** Gli stessi cinque stati di `OltreRow`, mai «oltre il piano»: quello
   *  stato esiste solo per la casella «non incassati» dei crediti, che sui
   *  tributari non ha senso. */
  stato: OltreRow["stato"];
}

/**
 * La riga dei tributari rateizzati, letta dal piano dello stesso `Pregresso`
 * che governa le altre quattro voci di questo passo — `tributariPlan` di
 * `lib/budget-imposte-step.ts`, non riscritto qui.
 *
 * `null` quando non c'e' nulla da scadenziare: senza un piano salvato E senza
 * debito oltre l'esercizio (`sp17e = 0`) la riga non ha ragione di esistere —
 * `pianoBase` non ne crea uno in quel caso, e mostrare una riga a zero
 * sarebbe una scadenza dichiarata che nessuno ha dichiarato.
 */
export function tributariOltreRow(
  baseBs: BalanceSheet | undefined | null, pregresso: Pregresso, years: number[],
): TributariOltreRow | null {
  const plan = tributariPlan(pregresso);
  if (!plan) return null;
  const amounts = years.map((_, i) => (plan.amounts[i] === undefined ? null : cents(num(plan.amounts[i]))));
  const somma = amounts.reduce<number>((a, v) => a + (v ?? 0), 0);
  return {
    key: "debiti_tributari",
    label: "Debiti tributari rateizzati",
    dir: "out",
    opening: cents(plan.rateizzato),
    amounts,
    resta: cents(Math.max(0, plan.rateizzato - somma)),
    // `nonIncassato` non esiste per i tributari: sempre `false`, quindi mai
    // «oltre il piano» — lo stesso `statoOltre` delle altre quattro righe.
    stato: statoOltre(plan.rateizzato, somma, false),
  };
}

/**
 * Nuovo piano tributario con la rata dell'anno `i` portata a `value` (Task
 * 13b): parte da `pianoBase` (crea il piano se manca e c'e' massa da
 * rateizzare), completa `amounts` alla lunghezza degli anni di piano con
 * zeri, scrive `amounts[i]` e passa per `withRate` — che tocca le sole rate:
 * saldo, rateizzato e acconto restano quelli del piano (dichiarati al passo 7
 * finche' il Task 16 non li porta anche loro qui).
 *
 * `null` scrive uno zero, come `withOltreAmount`: cancellare una cella toglie
 * quella rata dal piano, non lascia il vecchio importo.
 */
export function withTributariAmount(
  baseBs: BalanceSheet | undefined | null, pregresso: Pregresso, years: number[], i: number, value: number | null,
): Pregresso {
  const p = pianoBase(baseBs, years, pregresso);
  const plan = tributariPlanOrDefault(p, tributariOpening(baseBs));
  const amounts = [...plan.amounts];
  while (amounts.length <= Math.max(i, years.length - 1)) amounts.push(0);
  amounts[i] = cents(value ?? 0);
  return withRate(p, plan.opening, amounts);
}

/**
 * La card «A breve · si chiudono nel {anno 1}»: in sola lettura, perche' qui
 * non c'e' nessun piano da impostare — il breve lo chiude il primo anno di
 * piano per regola, e chi non vuole farlo rientrare riclassifica la voce
 * oltre 12 mesi in Rettifiche.
 *
 * `alert` e' la riga dei fornitori quando l'anno base non ne ha (decisione 8):
 * lo stesso avviso del passo 4, qui nella forma breve che ci sta in una
 * colonna.
 */
export interface BreveRow {
  label: string;
  importo: number;
  /** Il chip a schermo. ASSENTE dove il chip mentirebbe: l'ultima riga (le
   *  banche) non e' ne' un incasso ne' un pagamento di QUESTO passo, perche'
   *  li' il piano non c'e' ancora — si scadenzia piu' sotto. */
  dir?: "in" | "out";
  small: string;
  alert?: string;
}

/** La forma breve, per la riga: il testo lungo (con gli importi dei costi di
 *  acquisto) resta nel riquadro del passo 4. */
export const SENZA_PIANO_BREVE = "nessun piano: seguono la regola del passo 6 · Patrimoniale piano";

export const FORNITORI_AVVISO_RIGA = "Non risultano debiti verso fornitori: controllare le riclassifiche dei debiti.";

/**
 * `pregresso` e' il quarto parametro (Task 13b): quando il piano tributario
 * c'e' gia' (il caso normale una volta che `pianoBase` lo ha composto), la
 * riga mostra il suo `saldo` — che puo' differire da `sp16e` su un piano
 * salvato dal vecchio passo 7 con un'altra ripartizione — mai un importo
 * diverso da quello che il motore paga davvero. Senza piano (nessuna
 * scrittura ancora avvenuta, o `sp17e = 0`) il ripiego e' `sp16e + sp17e`:
 * la lettura di `lib/budget-imposte-step.ts` («senza piano il motore paga
 * tutto il tributario di apertura come saldo nel primo anno»), non solo
 * `sp16e` — coincidono quando `sp17e = 0`, ma la formula resta corretta anche
 * se non lo fosse.
 */
export function breveRows(
  baseBs: BalanceSheet | undefined | null, baseYear: number, fornitoriAvviso: string | null,
  pregresso?: Pregresso | null,
): BreveRow[] {
  const b = (key: OltreKey) => massaBreve(baseBs, key);
  const bs = (baseBs ?? {}) as unknown as Record<string, unknown>;
  const y1 = baseYear + 1;
  const pianoTributari = pregresso ? tributariPlan(pregresso) : null;
  const tributariBreve = pianoTributari
    ? pianoTributari.saldo
    : cents(num(bs.sp16e_debiti_tributari_breve) + num(bs.sp17e_debiti_tributari_lungo));
  return [
    { label: "Crediti verso clienti", importo: b("crediti_commerciali"), dir: "in", small: `incassati nel ${y1}` },
    {
      label: "Debiti verso fornitori", importo: b("debiti_fornitori"), dir: "out", small: `pagati nel ${y1}`,
      ...(fornitoriAvviso ? { alert: fornitoriAvviso } : {}),
    },
    { label: "Debiti tributari a breve", importo: tributariBreve, dir: "out", small: `saldo pagato nel ${y1}` },
    // Previdenziali e altri debiti hanno un piano solo con massa oltre 12 mesi (`pianoBase`):
    // senza, il motore li governa con la regola del passo 6 e NON li paga nel primo anno —
    // dirlo «pagati» contraddiceva l'anteprima dei flussi accanto (collaudo R7).
    { label: "Debiti previdenziali", importo: b("debiti_previdenziali"), dir: "out", small: pregresso?.debiti_previdenziali ? `pagati nel ${y1}` : SENZA_PIANO_BREVE },
    { label: "Altri debiti a breve", importo: b("altri_debiti"), dir: "out", small: pregresso?.altri_debiti ? `pagati nel ${y1}` : SENZA_PIANO_BREVE },
    {
      label: "Debiti verso banche e altri finanziatori",
      importo: cents(baseBankDebt(bs) + num(bs.sp16b_debiti_altri_finanz_breve) + num(bs.sp17b_debiti_altri_finanz_lungo)),
      small: "non si chiudono per regola: fidi e anticipi si rinnovano, i finanziamenti li scadenzi qui sotto",
    },
  ];
}
