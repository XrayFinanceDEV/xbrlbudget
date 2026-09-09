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

/** Le masse di apertura per ciascuna voce di pregresso, spec §3.1: dal
 *  bilancio base, al netto delle sottovoci tributarie/imposte anticipate sui
 *  crediti (che hanno un proprio scadenziamento altrove, non in questo). */
export function openingMasses(bs: BalanceSheet): Record<PregressoKey, number> {
  const b = bs as unknown as Record<string, unknown>;
  return {
    crediti_commerciali: cents(
      num(b.sp06_crediti_breve) - num(b.sp06e_crediti_tributari_breve) - num(b.sp06f_imposte_anticipate_breve) +
      num(b.sp07_crediti_lungo) - num(b.sp07e_crediti_tributari_lungo) - num(b.sp07f_imposte_anticipate_lungo)
    ),
    debiti_fornitori: cents(num(b.sp16d_debiti_fornitori_breve) + num(b.sp17d_debiti_fornitori_lungo)),
    debiti_tributari: cents(num(b.sp16e_debiti_tributari_breve) + num(b.sp17e_debiti_tributari_lungo)),
    debiti_previdenziali: cents(num(b.sp16f_debiti_previdenza_breve) + num(b.sp17f_debiti_previdenza_lungo)),
    altri_debiti: cents(num(b.sp16g_altri_debiti_breve) + num(b.sp17g_altri_debiti_lungo)),
  };
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
 *  non muta `plan`, e allunga l'array di importi con zeri se `yearIndex`
 *  cade oltre la lunghezza attuale. */
export function withAmount(plan: PregressoPlan, yearIndex: number, amount: number): PregressoPlan {
  const amounts = [...plan.amounts];
  while (amounts.length <= yearIndex) amounts.push(0);
  amounts[yearIndex] = cents(amount);
  return { ...plan, amounts };
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
