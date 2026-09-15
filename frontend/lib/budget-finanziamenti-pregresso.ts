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
 * misurano lo STESSO scostamento: `differenza = massa_del_bilancio − massa_dichiarata`. Un
 * `differenza` negativo (l'utente ha dichiarato PIÙ di quanto il bilancio registra: qui
 * `differenza < 1`) resta «quadra» — il motore rifiuta solo un residuo dei contratti che non
 * copre il debito bancario dell'anno base (`base-bank-debt.ts:statoResidui`), mai il contrario;
 * questo file segue la stessa asimmetria, misurata sul banco di test del task (fidi 90.000 € +
 * residui 640.000 € contro un debito bancario di 640.000 € risulta «quadra» anche se la somma
 * dichiarata eccede il bilancio di 90.000 €). Solo una CARENZA (`differenza ≥ 1`) è segnalata.
 */
import type { BalanceSheet, FinancingLoanInput, OtherLenderInput } from "@/types/api";
import { baseBankDebt } from "@/lib/base-bank-debt";
import { num } from "@/lib/budget-format";

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
}

type FonteBilancio = Partial<BalanceSheet> | Record<string, unknown> | null | undefined;

const v = (bs: FonteBilancio, field: string): number => num((bs as Record<string, unknown> | null | undefined)?.[field]);
const sum = (arr: readonly number[]): number => arr.reduce((acc, x) => acc + x, 0);
const eur0 = (x: number): string => new Intl.NumberFormat("it-IT", { maximumFractionDigits: 0 }).format(Math.round(x));

/** Riempie `repayments` di zeri fino a `horizon` e tronca oltre — mai muta l'array d'origine. */
function padTrunc(repayments: number[] | null | undefined, horizon: number): number[] {
  const out = repayments ? [...repayments] : [];
  while (out.length < horizon) out.push(0);
  return out.slice(0, horizon);
}

const residuoDi = (item: Pick<Scadenziabile, "opening_residual">): number => Number(item.opening_residual) || 0;
const sommaResidui = (items: readonly Pick<Scadenziabile, "opening_residual">[]): number => sum(items.map(residuoDi));

/** I contratti bancari già in bilancio: `opening_residual > 0` (il pregresso descrive un
 *  residuo già iscritto, mai un importo da erogare — spec §5.1). */
export function contrattiPregressi(loans: FinancingLoanInput[] | null | undefined): FinancingLoanInput[] {
  return (loans ?? []).filter((l) => (Number(l.opening_residual) || 0) > 0);
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
  const ok = differenza < 1;
  return { ok, testo, esito: ok ? "quadra" : `differenza ${eur0(differenza)} €` };
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
      testo: `Fidi e anticipi (${eur0(fidi)} €) superano i debiti a breve del bilancio (${eur0(sp16a)} €)`,
      esito: "da correggere",
    }
    : null;

  const quadra = quadraCheck(
    debitoBancario,
    fidi + residui,
    `Fidi ${eur0(fidi)} € + residui dei finanziamenti ${eur0(residui)} € · debiti verso banche nel bilancio: ${eur0(debitoBancario)} €`,
  );

  const rep1 = sum(items.map((item) => Math.min(residuoDi(item), Number(item.repayments?.[0]) || 0)));
  const quota = Math.max(0, quotaMutui(baseBs, fidi));
  const dRata = rep1 - quota;
  const rata: Controllo = Math.abs(dRata) < 1
    ? {
      ok: true,
      testo: `Rimborsi ${baseYear + 1} dei finanziamenti: ${eur0(rep1)} € · quota dei mutui entro 12 mesi: ${eur0(quota)} €`,
      esito: "coerente",
    }
    : dRata < 0
      ? { ok: true, testo: `Rimborsi ${baseYear + 1} dei finanziamenti: ${eur0(rep1)} € · quota dei mutui entro 12 mesi: ${eur0(quota)} €`, esito: `nel ${baseYear + 1} ne scadono ${eur0(-dRata)} € in più` }
      : { ok: true, testo: `Rimborsi ${baseYear + 1} dei finanziamenti: ${eur0(rep1)} € · quota dei mutui entro 12 mesi: ${eur0(quota)} €`, esito: `${eur0(dRata)} € oltre la quota a breve` };

  return { fidiOltre, quadra, rata };
}

/** Somma dei residui degli altri finanziatori contro `sp16b + sp17b` dell'anno base. */
export function controlloAltri(baseBs: FonteBilancio, items: readonly Scadenziabile[]): Controllo {
  const target = v(baseBs, "sp16b_debiti_altri_finanz_breve") + v(baseBs, "sp17b_debiti_altri_finanz_lungo");
  const residui = sommaResidui(items);
  return quadraCheck(
    target,
    residui,
    `Residui degli altri finanziatori: ${eur0(residui)} € · altri finanziatori nel bilancio: ${eur0(target)} €`,
  );
}
