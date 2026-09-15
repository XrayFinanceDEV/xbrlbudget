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
 * Sta in `lib/` per il motivo solito di questo repo: nessun jsdom, quindi
 * ogni decisione vive qui con la sua suite `environment: node` e
 * `steps/StepPatrimonialePregresso.tsx` rende soltanto.
 *
 * Modulo puro: nessun import da `app/` o da `components/`.
 */
import type { BalanceSheet, Pregresso, PregressoPlan } from "@/types/api";
import { openingMassLong, openingMasses } from "@/lib/budget-pregresso-circolante";
import { baseBankDebt } from "@/lib/base-bank-debt";
import { num } from "@/lib/budget-format";

const cents = (v: number) => Math.round(v * 100) / 100;

/** I saldi che questo passo scadenzia OLTRE l'esercizio. `debiti_tributari`
 *  non c'e': il rateizzato si scadenzia al passo 7 («Imposte»), dove vive
 *  accanto a saldo e acconti (`impostePreview`). */
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
 * **Identita' quando non c'e' nulla da aggiungere**: se ogni saldo che vuole
 * un piano ce l'ha gia', restituisce l'oggetto ricevuto com'e'. E' cio' che
 * rende legittimo l'effetto del passo 5 che scrive `pianoBase(...)` solo se
 * `!== salvato`: senza quella garanzia l'effetto si ri-innescherebbe da solo
 * (CLAUDE.md, «un effetto non dipende mai da cio' che lui stesso scrive»).
 */
export function pianoBase(baseBs: BalanceSheet | undefined | null, years: number[], pregresso: Pregresso): Pregresso {
  if (!baseBs) return pregresso;
  const missing = OLTRE_KEYS.filter((key) => {
    const vuolePiano = key === "crediti_commerciali" || key === "debiti_fornitori" || massaOltre(baseBs, key) > 0;
    return vuolePiano && (pregresso[key] as PregressoPlan | null | undefined) == null;
  });
  if (missing.length === 0) return pregresso;
  const piani: Record<string, PregressoPlan> = {};
  for (const key of missing) piani[key] = pianoDiPartenza(baseBs, years, key);
  return { ...pregresso, ...piani };
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
export const FORNITORI_AVVISO_RIGA = "Non risultano debiti verso fornitori: controllare le riclassifiche dei debiti.";

export function breveRows(
  baseBs: BalanceSheet | undefined | null, baseYear: number, fornitoriAvviso: string | null,
): BreveRow[] {
  const b = (key: OltreKey) => massaBreve(baseBs, key);
  const bs = (baseBs ?? {}) as unknown as Record<string, unknown>;
  const y1 = baseYear + 1;
  return [
    { label: "Crediti verso clienti", importo: b("crediti_commerciali"), dir: "in", small: `incassati nel ${y1}` },
    {
      label: "Debiti verso fornitori", importo: b("debiti_fornitori"), dir: "out", small: `pagati nel ${y1}`,
      ...(fornitoriAvviso ? { alert: fornitoriAvviso } : {}),
    },
    { label: "Debiti tributari a breve", importo: cents(num(bs.sp16e_debiti_tributari_breve)), dir: "out", small: `saldo pagato nel ${y1}` },
    { label: "Debiti previdenziali", importo: b("debiti_previdenziali"), dir: "out", small: `pagati nel ${y1}` },
    { label: "Altri debiti a breve", importo: b("altri_debiti"), dir: "out", small: `pagati nel ${y1}` },
    {
      label: "Debiti verso banche e altri finanziatori",
      importo: cents(baseBankDebt(bs) + num(bs.sp16b_debiti_altri_finanz_breve) + num(bs.sp17b_debiti_altri_finanz_lungo)),
      small: "non si chiudono per regola: fidi e anticipi si rinnovano, i finanziamenti li scadenzi qui sotto",
    },
  ];
}
