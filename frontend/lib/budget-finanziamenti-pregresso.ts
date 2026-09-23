/**
 * Passo 5 (II) — «Debiti verso banche» e «Altri finanziatori» (spec 2026-09-15 §4.5, §5.1-§5.3).
 *
 * Modulo puro: separa i contratti pregressi (`opening_residual > 0`) dai prestiti nuovi
 * (`amount > 0`), scadenzia il capitale rimborsato anno per anno (`repayments`), e calcola i
 * tre controlli che il passo mostra sotto le due tabelle — non bloccanti a schermo (il motore
 * decide se rifiutare il salvataggio, non questo file). Nessuna chiamata di rete, nessuno stato:
 * i componenti leggono `p.assumptions[firstYear].financing_loans`/`other_lenders`, chiamano
 * queste funzioni, e scrivono con `p.updateFinancingLoans`/`updateOtherLenders`.
 *
 * **Il formato dei controlli.** `quadra` (banche) e il controllo degli altri finanziatori
 * misurano lo STESSO scostamento: `differenza = massa_del_bilancio − massa_dichiarata`, e sono
 * SIMMETRICI — `|differenza| <= 0,01` (la soglia del motore, vedi `TOLLERANZA_MOTORE`) → «quadra»,
 * altrimenti `esito = "differenza {differenza} €"`, al centesimo quando l'importo non è tondo.
 * Il segno di `differenza` non si tocca a mano: `eur0` lo mostra così com'è (positivo = carenza,
 * negativo = sforamento), con lo stesso `Intl.NumberFormat` di `formatNumber`
 * (`lib/formatters.ts`) — sullo stesso runtime producono lo stesso carattere per il segno meno
 * (misurato: trattino ASCII U+002D, non il meno tipografico U+2212). Un motivo, non solo un
 * capriccio simmetrico: `assemble_financing` (`calculations/projection_common.py`) rifiuta un
 * piano dove `fidi + Σ residui` si scosta dal debito bancario dell'anno base di oltre 0,01, IN
 * ENTRAMBE LE DIREZIONI — un client che chiama «quadra» uno sforamento mostrerebbe verde su un
 * piano che il server rifiuta comunque. Una prima versione di questo file (revisione del
 * coordinatore su 5dceddb) trattava lo sforamento come innocuo, seguendo alla lettera un banco di
 * test con un `bs` internamente incoerente (fidi 90.000 € + residui 640.000 € contro un debito
 * bancario dichiarato di 640.000 €, che già di per sé non tornava): l'oracolo era sbagliato, non
 * la regola — corretto qui e nel test.
 */
import type { BalanceSheet, FinancingLoanInput, OtherLenderInput } from "@/types/api";
import { baseBankDebt } from "@/lib/base-bank-debt";
import { num } from "@/lib/budget-format";

/** Etichette per leggere report storici che contengono ancora la vecchia regola. */
export const ETICHETTE_REGOLA_FIDI: Readonly<Record<string, string>> = {
  costante: "Costanti",
  ricavi: "Seguono i ricavi",
};

/** Una riga scadenziabile: un contratto bancario pregresso o un altro finanziatore. */
export interface Scadenziabile {
  name?: string | null;
  opening_residual: number;
  interest_rate: number;
  repayments?: number[] | null;
}

export interface ContrattoRow {
  index: number;
  name: string;
  residuo: number;
  tasso: number;
  rimborsi: number[];
  resta: number;
  stato: "chiuso" | "resta aperto" | "nessun rimborso nel piano" | "oltre il residuo";
}

export interface Controllo {
  ok: boolean;
  testo: string;
  esito: string;
  /** `massa_del_bilancio − massa_dichiarata`, il numero su cui `ok` decide: serve al passo per
   *  offrire la chiusura di uno scarto da arrotondamento (`chiusuraResidui`). */
  differenza: number;
}

/** La soglia del MOTORE: `assemble_financing` (`calculations/forecast_engine.py`) rifiuta il
 *  piano quando `fidi + Σ residui` si scosta dal debito bancario dell'anno base di più di 0,01 €.
 *  Il client misurava a meno di 1 € e diceva «quadra» su uno scarto di 42 centesimi che il motore
 *  rifiutava: il passo mostrava verde a sinistra e il rifiuto del motore a destra, sulla stessa
 *  schermata, e non c'era modo di uscirne perché tutti gli importi erano resi all'euro — i
 *  centesimi che il cancello misura non si vedevano da nessuna parte (segnalato dal proprietario
 *  il 2026-09-16, su un bilancio da 960.937,42 €). Stessa classe della tolleranza doppia delle
 *  Rettifiche: due soglie che si contraddicono bloccano l'utente senza dirgli perché. */
export const TOLLERANZA_MOTORE = 0.01;

/** Fino a due euro uno scarto è arrotondamento, non una scelta di piano: la card offre di
 *  chiuderlo con un clic, dichiarando su quale contratto lo posa. È la stessa scala che il
 *  proprietario ha scelto per la chiusura automatica delle Rettifiche. */
export const SOGLIA_CHIUSURA_RESIDUI = 2;

type FonteBilancio = Partial<BalanceSheet> | Record<string, unknown> | null | undefined;

const v = (bs: FonteBilancio, field: string): number => num((bs as Record<string, unknown> | null | undefined)?.[field]);
const sum = (arr: readonly number[]): number => arr.reduce((acc, x) => acc + x, 0);
const eur0 = (x: number): string => new Intl.NumberFormat("it-IT", { maximumFractionDigits: 0 }).format(Math.round(x));

/** All'euro quando l'importo è tondo, al centesimo quando non lo è. I controlli di questa card
 *  si giocano sul centesimo (vedi `TOLLERANZA_MOTORE`): renderli sempre all'euro nascondeva
 *  proprio la cifra da correggere — «450.000 + 510.937 = 960.937» tornava a occhio mentre il
 *  bilancio diceva 960.937,42. Gli importi tondi restano tondi: nessun «,00» ovunque. */
const eurAuto = (x: number): string => {
  const cents = Math.round(x * 100);
  const decimali = cents % 100 === 0 ? 0 : 2;
  return new Intl.NumberFormat("it-IT", { minimumFractionDigits: decimali, maximumFractionDigits: decimali })
    .format(cents / 100);
};

/**
 * Finanziamenti e altri finanziatori tornati dal server, con numeri veri al posto delle stringhe.
 *
 * Stessa causa di `normalizePregresso` (`lib/budget-pregresso-circolante.ts`, dove è spiegata
 * per esteso): Pydantic v2 serializza i `Decimal` come STRINGA, e `GET /assumptions` restituisce
 * `opening_residual: "510937.42"` e `repayments: ["45000", …]` benché il tipo prometta `number`.
 * Quella correzione copriva il solo `pregresso`. Qui `sum` concatenava le rate — la colonna
 * «Resta» di AMBIENTA mostrava -450.004.499.534.063 € — e `fidi + residui` dava NaN. Il guasto si
 * vede solo dopo un ricaricamento: i valori digitati nella sessione sono già numeri.
 *
 * Va chiamata in `hydrateAssumptions`, una volta sola. `null` resta `null` (un prestito nuovo
 * senza scadenziario non diventa una lista di zeri), e così `duration_years` assente.
 */
export function normalizeFinancingLoans(loans: FinancingLoanInput[] | null | undefined): FinancingLoanInput[] | null {
  if (!loans) return null;
  return loans.map((l) => ({
    ...l,
    amount: num(l.amount),
    opening_residual: num(l.opening_residual),
    interest_rate: num(l.interest_rate),
    grace_years: num(l.grace_years),
    balloon_pct: num(l.balloon_pct),
    duration_years: l.duration_years == null ? l.duration_years : num(l.duration_years),
    repayments: l.repayments == null ? l.repayments : l.repayments.map(num),
  }));
}

/** Come `normalizeFinancingLoans`, per gli altri finanziatori. */
export function normalizeOtherLenders(lenders: OtherLenderInput[] | null | undefined): OtherLenderInput[] | null {
  if (!lenders) return null;
  return lenders.map((l) => ({
    ...l,
    opening_residual: num(l.opening_residual),
    interest_rate: num(l.interest_rate),
    repayments: (l.repayments ?? []).map(num),
  }));
}

/** Riempie `repayments` di zeri fino a `horizon` e tronca oltre — mai muta l'array d'origine. */
function padTrunc(repayments: number[] | null | undefined, horizon: number): number[] {
  const out = repayments ? [...repayments] : [];
  while (out.length < horizon) out.push(0);
  return out.slice(0, horizon);
}

const residuoDi = (item: Pick<Scadenziabile, "opening_residual">): number => Number(item.opening_residual) || 0;
const sommaResidui = (items: readonly Pick<Scadenziabile, "opening_residual">[]): number => sum(items.map(residuoDi));

/** I contratti bancari già in bilancio: ogni riga che non eroga nulla (`amount` = 0; il
 *  pregresso descrive un residuo già iscritto, mai un importo da erogare — spec §5.1).
 *  Anche una riga ancora a residuo zero: è quella che «+ Aggiungi finanziamento» ha appena
 *  creato, e filtrarla sul residuo la faceva sparire al clic (collaudo di fine lotto, R6).
 *  Le righe vuote non partono verso il server: le toglie `assumptionRowsForSave`. */
export function contrattiPregressi(loans: FinancingLoanInput[] | null | undefined): FinancingLoanInput[] {
  return (loans ?? []).filter((l) => !((Number(l.amount) || 0) > 0));
}

/** I prestiti nuovi (da erogare): `amount > 0`, con durata/preammortamento come oggi. */
export function prestitiNuovi(loans: FinancingLoanInput[] | null | undefined): FinancingLoanInput[] {
  return (loans ?? []).filter((l) => (Number(l.amount) || 0) > 0);
}

/** «chiuso» sotto 0,5 € residui, «oltre il residuo» sopra 0,5 € di sforamento, «nessun
 *  rimborso nel piano» quando la somma dei rimborsi è sotto 0,5 € (e il residuo non è già
 *  chiuso), altrimenti «resta aperto». L'ordine dei controlli conta: un residuo a zero senza
 *  rimborsi è «chiuso», non «nessun rimborso nel piano». */
export function restaStato(residuo: number, rimborsi: number[]): ContrattoRow["stato"] {
  const rimborsato = sum(rimborsi);
  const resta = residuo - rimborsato;
  if (rimborsato > residuo + 0.5) return "oltre il residuo";
  if (resta < 0.5) return "chiuso";
  if (rimborsato < 0.5) return "nessun rimborso nel piano";
  return "resta aperto";
}

/** Le righe della tabella «Scadenzia i finanziamenti»/«Altri finanziatori»: `repayments`
 *  riempiti di zeri fino all'orizzonte del piano e troncati oltre. */
export function contrattoRows(items: readonly Scadenziabile[], horizon: number): ContrattoRow[] {
  return items.map((item, index) => {
    const residuo = residuoDi(item);
    const rimborsi = padTrunc(item.repayments, horizon);
    return {
      index,
      name: item.name ?? "",
      residuo,
      tasso: Number(item.interest_rate) || 0,
      rimborsi,
      resta: residuo - sum(rimborsi),
      stato: restaStato(residuo, rimborsi),
    };
  });
}

/** Scrive `repayments[i] = value ?? 0` su una copia riempita/troncata a `horizon`; un indice
 *  fuori dall'orizzonte (per esempio `i === horizon`) non tocca nulla, perché la copia non ha
 *  quella posizione. */
export function withRimborso<T extends Scadenziabile>(items: T[], k: number, i: number, value: number | null, horizon: number): T[] {
  return items.map((item, idx) => {
    if (idx !== k) return item;
    const rimborsi = padTrunc(item.repayments, horizon);
    if (i >= 0 && i < horizon) rimborsi[i] = value ?? 0;
    return { ...item, repayments: rimborsi };
  });
}

/** Scrive `name`/`opening_residual`/`interest_rate` sulla riga `k`, senza toccare le altre. */
export function withCampo<T extends Scadenziabile>(
  items: T[],
  k: number,
  field: "name" | "opening_residual" | "interest_rate",
  value: string | number | null,
): T[] {
  return items.map((item, idx) => (idx === k ? ({ ...item, [field]: value } as T) : item));
}

/** «Finanziamento A», «Finanziamento B», … — vuoto, tasso di default 4%, rimborsi a zero
 *  su tutto l'orizzonte. */
export function nuovoContratto(n: number, horizon: number): FinancingLoanInput {
  return {
    name: `Finanziamento ${String.fromCharCode(64 + n)}`,
    amount: 0,
    opening_residual: 0,
    interest_rate: 4,
    grace_years: 0,
    balloon_pct: 0,
    duration_years: null,
    repayments: new Array(horizon).fill(0),
  };
}

/** «Finanziatore 1», «Finanziatore 2», … — vuoto, tasso 0%. */
export function nuovoFinanziatore(n: number, horizon: number): OtherLenderInput {
  return {
    name: `Finanziatore ${n}`,
    opening_residual: 0,
    interest_rate: 0,
    repayments: new Array(horizon).fill(0),
  };
}

/** Un solo finanziamento: somma dei residui, tasso medio ponderato sui residui (un decimale),
 *  rimborsi sommati anno per anno. «Per fare in fretta»: uno scadenziario invece di N. */
export function unisciContratti(items: FinancingLoanInput[], horizon: number): FinancingLoanInput[] {
  if (items.length === 0) return [];
  const residuoTot = sommaResidui(items);
  const tassoMedio = residuoTot > 0
    ? Math.round((sum(items.map((l) => residuoDi(l) * (Number(l.interest_rate) || 0))) / residuoTot) * 10) / 10
    : 0;
  const repayments = new Array(horizon).fill(0);
  for (const item of items) {
    padTrunc(item.repayments, horizon).forEach((r, i) => { repayments[i] += r; });
  }
  return [{
    name: "Debiti verso banche",
    amount: 0,
    opening_residual: residuoTot,
    duration_years: null,
    repayments,
    interest_rate: tassoMedio,
    grace_years: 0,
    balloon_pct: 0,
  }];
}

/** La quota dei mutui entro 12 mesi: `sp16a` dell'anno base meno i fidi dichiarati — è la
 *  rata del primo anno dei finanziamenti scadenziati sotto (negativa quando i fidi superano
 *  `sp16a`: la card la mostra in rosso, e `fidiOltre` la segnala). */
export function quotaMutui(baseBs: FonteBilancio, fidi: number): number {
  return v(baseBs, "sp16a_debiti_banche_breve") - fidi;
}

function quadraCheck(target: number, dichiarato: number, testo: string): Controllo {
  const differenza = target - dichiarato;
  const ok = Math.abs(differenza) <= TOLLERANZA_MOTORE;
  return { ok, testo, esito: ok ? "quadra" : `differenza ${eurAuto(differenza)} €`, differenza };
}

/**
 * Su quale contratto posare uno scarto da arrotondamento, e quanto — `null` quando non si
 * applica: scarto già dentro la tolleranza del motore, oltre i due euro (lì è una scelta di
 * piano, la fa l'utente), nessun contratto su cui posarlo, o un residuo che diventerebbe
 * negativo.
 *
 * Il bersaglio è il contratto con il residuo più alto: è quello su cui un centesimo si perde,
 * e sceglierlo a caso renderebbe il pulsante imprevedibile. Il nome torna insieme all'importo
 * perché la card lo dice prima di scrivere — una chiusura silenziosa qui riscriverebbe un dato
 * che l'utente ha dichiarato.
 */
export function chiusuraResidui(
  items: readonly Scadenziabile[],
  differenza: number,
): { indice: number; nome: string; importo: number } | null {
  // Uno scarto non misurabile non si «chiude»: il pulsante diceva «Togli NaN €».
  if (!Number.isFinite(differenza)) return null;
  if (Math.abs(differenza) <= TOLLERANZA_MOTORE) return null;
  if (Math.abs(differenza) > SOGLIA_CHIUSURA_RESIDUI) return null;
  if (items.length === 0) return null;
  let indice = 0;
  items.forEach((item, i) => {
    if (residuoDi(item) > residuoDi(items[indice])) indice = i;
  });
  // Al centesimo: è l'importo che finisce dentro un campo, non una misura descrittiva, e
  // `differenza` arriva da una sottrazione in virgola mobile (0,4200000000419095 sul caso reale).
  const importo = Math.round(differenza * 100) / 100;
  if (residuoDi(items[indice]) + importo < 0) return null;
  return { indice, nome: items[indice].name || `Finanziamento ${indice + 1}`, importo };
}

/** I tre controlli della card «Debiti verso banche»: fidi entro `sp16a`, fidi + residui dei
 *  finanziamenti contro il debito bancario del bilancio, coerenza fra i rimborsi del primo
 *  anno e la quota dei mutui entro 12 mesi. Non bloccanti a schermo — il motore decide se
 *  rifiutare al salvataggio (spec §4.5 punto 3). */
export function controlliBanche(
  baseBs: FonteBilancio,
  fidi: number,
  items: readonly Scadenziabile[],
  horizon: number,
  baseYear: number,
): { fidiOltre: Controllo | null; quadra: Controllo; rata: Controllo } {
  const sp16a = v(baseBs, "sp16a_debiti_banche_breve");
  const debitoBancario = baseBankDebt(baseBs as Parameters<typeof baseBankDebt>[0]);
  const residui = sommaResidui(items);

  const fidiOltre: Controllo | null = fidi > sp16a + 0.5
    ? {
      ok: false,
      testo: `Fidi, Anticipi Ft e Scoperti CC (${eurAuto(fidi)} €) superano i debiti a breve del bilancio (${eurAuto(sp16a)} €)`,
      esito: "da correggere",
      differenza: sp16a - fidi,
    }
    : null;

  const quadra = quadraCheck(
    debitoBancario,
    fidi + residui,
    `Fidi ${eurAuto(fidi)} € + residui dei finanziamenti ${eurAuto(residui)} € · debiti verso banche nel bilancio: ${eurAuto(debitoBancario)} €`,
  );

  const rep1 = sum(items.map((item) => Math.min(residuoDi(item), Number(item.repayments?.[0]) || 0)));
  const quota = Math.max(0, quotaMutui(baseBs, fidi));
  const dRata = rep1 - quota;
  // La riga della rata resta all'euro e con la sua tolleranza larga: non è un cancello del
  // motore, è un raffronto informativo fra due grandezze che non devono coincidere al centesimo.
  const testoRata = `Rimborsi ${baseYear + 1} dei finanziamenti: ${eur0(rep1)} € · quota dei mutui entro 12 mesi: ${eur0(quota)} €`;
  const rata: Controllo = Math.abs(dRata) < 1
    ? { ok: true, testo: testoRata, esito: "coerente", differenza: dRata }
    : dRata < 0
      ? { ok: true, testo: testoRata, esito: `nel ${baseYear + 1} ne scadono ${eur0(-dRata)} € in più`, differenza: dRata }
      : { ok: true, testo: testoRata, esito: `${eur0(dRata)} € oltre la quota a breve`, differenza: dRata };

  return { fidiOltre, quadra, rata };
}

/** Somma dei residui degli altri finanziatori contro `sp16b + sp17b` dell'anno base. */
export function controlloAltri(baseBs: FonteBilancio, items: readonly Scadenziabile[]): Controllo {
  const target = v(baseBs, "sp16b_debiti_altri_finanz_breve") + v(baseBs, "sp17b_debiti_altri_finanz_lungo");
  const residui = sommaResidui(items);
  return quadraCheck(
    target,
    residui,
    `Residui degli altri finanziatori: ${eurAuto(residui)} € · altri finanziatori nel bilancio: ${eurAuto(target)} €`,
  );
}

/**
 * Vero quando la riga del primo anno di piano ESISTE ma non ha ancora un valore per i fidi: è il
 * segnale per la scrittura una tantum (`bank_lines_amount = 0`)
 * alla prima visita del passo. Prima che la riga arrivi (ipotesi non ancora idratate) non è MAI
 * vero — `riga === undefined` torna `false` senza guardare altro — perché scrivere su una mappa
 * vuota scriverebbe 0 e "costante" PRIMA che i valori salvati (se lo scenario ne aveva già uno)
 * abbiano la possibilità di arrivare, azzerando in silenzio un fido reale (rilievo del
 * coordinatore su 5dceddb: `PregressoBancheCard` marcava l'inizializzazione come «fatta» anche a
 * riga assente).
 */
export function serveInizializzareFidi(
  riga: { bank_lines_amount?: number | null } | null | undefined,
): boolean {
  if (riga == null) return false;
  return riga.bank_lines_amount == null;
}
