/**
 * Modulo puro dello scadenziamento del pregresso di CIRCOLANTE (spec
 * 2026-09-08 §3): come l'utente dichiara la chiusura dei saldi di
 * circolante gia' a bilancio (crediti commerciali, debiti fornitori,
 * tributari, previdenziali, altri debiti) sull'orizzonte di piano.
 * Costruisce le masse di apertura dal bilancio base, valida un piano
 * dichiarato e offre le conversioni importo/percentuale e rata-uguale che i
 * due passi del wizard useranno.
 *
 * Meta' dello stesso passo 6 del wizard di `lib/budget-pregresso-step.ts`,
 * che governa l'altra meta' — il pregresso del debito BANCARIO. I due nomi
 * ora si distinguono: questo e' il circolante, quello e' il debito.
 *
 * Modulo puro: nessun import da `app/` o da `components/`.
 */
import type { BalanceSheet, Pregresso, PregressoKey, PregressoPlan, PregressoTributari } from "@/types/api";
import { num } from "@/lib/budget-format";

const cents = (v: number) => Math.round(v * 100) / 100;

export const PREGRESSO_LABELS: Record<PregressoKey, string> = {
  crediti_commerciali: "Crediti commerciali",
  debiti_fornitori: "Debiti verso fornitori",
  debiti_tributari: "Debiti tributari",
  debiti_previdenziali: "Debiti previdenziali",
  altri_debiti: "Altri debiti",
};

/** I crediti commerciali sono l'unica voce la cui parte OLTRE l'esercizio non
 *  e' un solo campo: come il lato breve, `sp07` va al netto delle quote
 *  tributarie/imposte anticipate. Estratta una volta, cosi' `openingMasses` e
 *  `openingMassLong` non possono divergere su questa sottrazione (rilievo 1,
 *  giro di correzione 1: la nota di destino ha bisogno della STESSA massa
 *  lunga, non di una seconda formula). */
function creditiComponents(b: Record<string, unknown>): { short: number; long: number } {
  return {
    short: num(b.sp06_crediti_breve) - num(b.sp06e_crediti_tributari_breve) - num(b.sp06f_imposte_anticipate_breve),
    long: num(b.sp07_crediti_lungo) - num(b.sp07e_crediti_tributari_lungo) - num(b.sp07f_imposte_anticipate_lungo),
  };
}

/** Le masse di apertura per ciascuna voce di pregresso, spec §3.1: dal
 *  bilancio base, al netto delle sottovoci tributarie/imposte anticipate sui
 *  crediti (che hanno un proprio scadenziamento altrove, non in questo). */
export function openingMasses(bs: BalanceSheet): Record<PregressoKey, number> {
  const b = bs as unknown as Record<string, unknown>;
  const cred = creditiComponents(b);
  return {
    crediti_commerciali: cents(cred.short + cred.long),
    debiti_fornitori: cents(num(b.sp16d_debiti_fornitori_breve) + num(b.sp17d_debiti_fornitori_lungo)),
    debiti_tributari: cents(num(b.sp16e_debiti_tributari_breve) + num(b.sp17e_debiti_tributari_lungo)),
    debiti_previdenziali: cents(num(b.sp16f_debiti_previdenza_breve) + num(b.sp17f_debiti_previdenza_lungo)),
    altri_debiti: cents(num(b.sp16g_altri_debiti_breve) + num(b.sp17g_altri_debiti_lungo)),
  };
}

/** La parte OLTRE l'esercizio della massa di apertura di una voce — la stessa
 *  scomposizione di `openingMasses`, mai una seconda formula: per i crediti
 *  e' `sp07` al netto delle quote fiscali, esattamente come il lato breve.
 *  Serve alla tabella (rilievo 1) per dire, riga per riga, se la parte lunga
 *  di un saldo che "si rigenera" e' davvero coperta dal driver o no. */
export function openingMassLong(bs: BalanceSheet, key: PregressoKey): number {
  const b = bs as unknown as Record<string, unknown>;
  switch (key) {
    case "crediti_commerciali": return cents(creditiComponents(b).long);
    case "debiti_fornitori": return cents(num(b.sp17d_debiti_fornitori_lungo));
    case "debiti_tributari": return cents(num(b.sp17e_debiti_tributari_lungo));
    case "debiti_previdenziali": return cents(num(b.sp17f_debiti_previdenza_lungo));
    case "altri_debiti": return cents(num(b.sp17g_altri_debiti_lungo));
  }
}

/** Un piano i cui importi e le cui svalutazioni sono tutti zero (o assenti)
 *  non e' una scadenza dichiarata: vale "nessun piano", la regola del repo
 *  "debito senza scadenza dichiarata → a breve" (CLAUDE.md § Contabilità)
 *  applicata al punto in cui il piano nasce — e deve poter morire (rilievo 2,
 *  giro di correzione 1). Un piano con almeno un importo non nullo resta un
 *  piano, anche se altri anni sono a zero. */
export function isPlanEmpty(plan: PregressoPlan): boolean {
  const allZero = (xs: number[] | null | undefined) => (xs ?? []).every((v) => v === 0);
  return allZero(plan.amounts) && allZero(plan.writeoff);
}

/** Quanto resta della massa di apertura dopo gli importi (e gli eventuali
 *  writeoff) fino all'anno `yearIndex` incluso. Mai negativo. */
export function residualAfter(plan: PregressoPlan, yearIndex: number): number {
  const sum = (xs: number[] | null | undefined) => (xs ?? []).slice(0, yearIndex + 1).reduce((a, b) => a + b, 0);
  return cents(Math.max(0, plan.opening - sum(plan.amounts) - sum(plan.writeoff)));
}

/** L'incidenza di un importo sulla massa di apertura, in percentuale
 *  assoluta (25,5 = 25,5%). Apertura nulla o assente ⇒ nessuna incidenza. */
export function amountToPct(amount: number, opening: number): number | null {
  return opening ? (amount / opening) * 100 : null;
}

/** L'importo corrispondente a una percentuale assoluta della massa di
 *  apertura, arrotondato al centesimo. */
export function pctToAmount(pct: number, opening: number): number {
  return cents((opening * pct) / 100);
}

/** `n` rate uguali che sommano esattamente `total`: i centesimi residui
 *  dell'arrotondamento vanno tutti sull'ultima rata, mai distribuiti. */
export function equalInstalments(total: number, n: number): number[] {
  if (n <= 0) return [];
  const base = Math.floor((total / n) * 100) / 100;
  const out = Array<number>(n).fill(base);
  out[n - 1] = cents(total - base * (n - 1));
  return out;
}

/** Nuovo piano con l'importo dell'anno `yearIndex` sostituito. Immutabile:
 *  non muta `plan`, e allunga l'array con zeri se `yearIndex` cade oltre la
 *  lunghezza attuale.
 *
 * `field` sceglie la lista: `"amounts"` (il default, gli incassi/pagamenti) o
 * `"writeoff"` (l'inesigibile, il solo campo dei crediti). Prima del giro di
 * correzione 1 `withWriteoff` (`lib/budget-pregresso-tabella.ts`) ripeteva
 * questa stessa funzione a mano sulla lista `writeoff`: due copie
 * dell'arrotondamento che potevano divergere cambiandone solo una
 * (rilievo 7). */
export function withAmount(
  plan: PregressoPlan, yearIndex: number, amount: number, field: "amounts" | "writeoff" = "amounts",
): PregressoPlan {
  const list = [...((field === "amounts" ? plan.amounts : plan.writeoff) ?? [])];
  while (list.length <= yearIndex) list.push(0);
  list[yearIndex] = cents(amount);
  return field === "amounts" ? { ...plan, amounts: list } : { ...plan, writeoff: list };
}

/** Coerce un piano non-tributario ai numeri veri (vedi `normalizePregresso`
 *  per il perche'). `writeoff` resta `null`/`undefined` quando tale: un piano
 *  senza inesigibile e uno con inesigibile zero non sono la stessa cosa. */
function normalizePlan(plan: PregressoPlan): PregressoPlan {
  return {
    opening: num(plan.opening),
    amounts: (plan.amounts ?? []).map(num),
    writeoff: plan.writeoff ? plan.writeoff.map(num) : plan.writeoff,
  };
}

/** Stessa coercizione di `normalizePlan`, piu' le tre chiavi che solo il
 *  piano tributario ha. */
function normalizeTributari(plan: PregressoTributari): PregressoTributari {
  return {
    ...normalizePlan(plan),
    saldo: num(plan.saldo),
    rateizzato: num(plan.rateizzato),
    acconto_pct: num(plan.acconto_pct),
  };
}

/**
 * Coerce OGNI campo numerico di un `Pregresso` idratato dal server a un vero
 * `number` (rilievo 5, giro di correzione 1).
 *
 * Il perche': la colonna `BudgetAssumptions.pregresso` e' un bag JSON di
 * `Decimal` (`backend/app/schemas/budget.py`, `PregressoPlanInput`/
 * `PregressoTributariInput`). FastAPI, per rispondere, chiama
 * `jsonable_encoder` su un modello Pydantic v2 — che per un `BaseModel` passa
 * da `model_dump(mode="json")`, e Pydantic v2 serializza `Decimal` in quella
 * modalita' come STRINGA (per non perdere precisione), non come numero: il
 * tipo TypeScript `Pregresso`/`PregressoPlan` promette `number`, ma
 * `GET /assumptions` restituisce `"6451277.6"`, non `6451277.6`.
 *
 * Senza questa coercizione, `residualAfter` e `validatePregresso` sommano gli
 * importi con `+`: `0 + "6451277.6"` e' concatenazione di stringhe
 * (`"06451277.6"`), non addizione, e la sottrazione successiva produce NaN
 * (due punti decimali nella stringa concatenata) oppure — quando la
 * concatenazione resta un intero valido — un numero enorme che
 * `Math.max(0, …)` clampa silenziosamente a zero. Duplicato osservato dal
 * collaudo: «Residuo crediti commerciali» mostrava NaN €, «Residuo rate»
 * mostrava 0 € invece di 26.441 €, e `validatePregresso` sollevava una falsa
 * «le rate superano il rateizzato» — tutti e tre PRIMA di questa funzione,
 * tutti e tre scomparsi dopo.
 *
 * Va chiamata una volta sola, in `hydrateAssumptions`: da li' in poi ogni
 * lettura del pregresso (tabella, anteprima, validazione) vede numeri veri.
 */
export function normalizePregresso(pregresso: Pregresso | null | undefined): Pregresso | null {
  if (!pregresso) return null;
  const out: Pregresso = {};
  if (pregresso.crediti_commerciali) out.crediti_commerciali = normalizePlan(pregresso.crediti_commerciali);
  if (pregresso.debiti_fornitori) out.debiti_fornitori = normalizePlan(pregresso.debiti_fornitori);
  if (pregresso.debiti_tributari) out.debiti_tributari = normalizeTributari(pregresso.debiti_tributari);
  if (pregresso.debiti_previdenziali) out.debiti_previdenziali = normalizePlan(pregresso.debiti_previdenziali);
  if (pregresso.altri_debiti) out.altri_debiti = normalizePlan(pregresso.altri_debiti);
  return out;
}

/**
 * Valida un piano di pregresso dichiarato contro le masse di apertura del
 * bilancio base e l'orizzonte di piano. Diagnostica, non corregge: restituisce
 * i messaggi (italiano, rivolti all'utente) invece di troncare in silenzio.
 * Superare la massa di apertura e' sempre un errore.
 */
export function validatePregresso(p: Pregresso, masses: Record<PregressoKey, number>, horizon: number): string[] {
  const errs: string[] = [];
  for (const key of Object.keys(PREGRESSO_LABELS) as PregressoKey[]) {
    const plan = p[key];
    if (!plan) continue;
    const label = PREGRESSO_LABELS[key];

    if (Math.abs(plan.opening - masses[key]) > 0.01) {
      errs.push(`${label}: il saldo di apertura dichiarato (${plan.opening}) non coincide col bilancio base (${masses[key]})`);
    }
    if (plan.amounts.length > horizon || (plan.writeoff ?? []).length > horizon) {
      errs.push(`${label}: il piano va oltre l'orizzonte di ${horizon} anni`);
    }
    if ([...plan.amounts, ...(plan.writeoff ?? [])].some((v) => v < 0)) {
      errs.push(`${label}: un importo è negativo`);
    }

    const total = plan.amounts.reduce((a, b) => a + b, 0) + (plan.writeoff ?? []).reduce((a, b) => a + b, 0);

    if (key === "debiti_tributari") {
      const t = plan as PregressoTributari;
      // Il saldo si digita e il rateizzato si deduce (`withSaldo`): un saldo
      // oltre l'apertura non viene troncato, quindi il rateizzato esce
      // negativo — e la somma torna lo stesso, cioe' il controllo qui sotto
      // non lo vedrebbe. Lo schema del server ha `ge=0` su entrambi: senza
      // questa riga il rifiuto arriverebbe come un 422 illeggibile.
      if (t.saldo < 0 || t.rateizzato < 0) {
        errs.push(`${label}: saldo e rateizzato non possono essere negativi — il saldo supera il debito di apertura`);
      }
      // Stessi limiti del server (`PregressoTributariInput.acconto_pct`,
      // `backend/app/schemas/budget.py`: `ge=0, le=200`), letti li' e non
      // dedotti: senza questo controllo il client non segnala nulla e il
      // server risponde con un 422 illeggibile — lo stesso difetto che il
      // controllo dei negativi qui sopra chiude sul saldo/rateizzato (fix1 R3).
      if (t.acconto_pct < 0 || t.acconto_pct > 200) {
        errs.push(`${label}: l'acconto deve stare fra 0% e 200%`);
      }
      if (Math.abs(t.saldo + t.rateizzato - t.opening) > 0.01) {
        errs.push(`${label}: saldo + rateizzato deve essere uguale al saldo di apertura`);
      }
      if (total - t.rateizzato > 0.01) {
        errs.push(`${label}: le rate superano il rateizzato`);
      }
    } else if (total - plan.opening > 0.01) {
      errs.push(`${label}: gli importi superano il saldo di apertura`);
    }
  }
  return errs;
}
