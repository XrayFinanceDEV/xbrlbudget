/**
 * Le decisioni del passo 6 «Patrimoniale piano» (spec 2026-09-15 §4.6): ciò
 * che il previsionale GENERA — voci minori, fondo TFR con le sue
 * liquidazioni, nuovi finanziamenti (uno o più, con nome), debito/cassa/PFN
 * — a differenza del passo 5 «Patrimoniale pregresso», che chiude ciò che
 * c'è già.
 *
 * Stesso schema di `lib/budget-circolante-step.ts`: un componente in questo
 * repo non è collaudabile (nessun jsdom), quindi ogni decisione vive qui,
 * provata in `environment: node`, e `StepPatrimonialePiano.tsx` si limita a
 * renderla. Un solo motore di proiezione, e sta in Python: debito, cassa,
 * PFN, TFR e fidi/anticipi si leggono da ciò che il motore ha già
 * restituito nei `details` di `POST /preview` — qui non si ricalcola nulla.
 */
import { formatNumber } from "@/lib/formatters";
import type { AssumptionsMap } from "@/lib/budget-horizon";
import { baseBankDebt } from "@/lib/base-bank-debt";
import { ceAggregates, type PreviewCell, type PreviewRow, type PreviewRowKind } from "@/lib/budget-preview-rows";
import { spIndexingOf } from "@/lib/budget-circolante-step";
import { num } from "@/lib/budget-format";
import type {
  BalanceSheet, FinancingLoanInput, ForecastPreviewResponse, ForecastPreviewYear, IncomeStatement, SpIndexingDriver,
} from "@/types/api";

const mkRow = (key: string, label: string, kind: PreviewRowKind, base: PreviewCell, years: PreviewCell[]): PreviewRow =>
  ({ key, label, kind, base, years });

// ── Fondo TFR (spec §5.4) ───────────────────────────────────────────────

export interface TfrRiga {
  year: number;
  /** `null` quando l'anteprima non ha prodotto quest'anno (il motore si è
   *  fermato prima): un accantonamento non calcolato non è uno zero. */
  accantonamento: number | null;
  /** L'importo digitato dall'utente (`tfr_payments`): SEMPRE dalla mappa
   *  delle ipotesi, mai dai `details`, perché un anno non prodotto non ha
   *  `details` da cui leggerlo. */
  liquidazione: number;
  chiusura: number | null;
  /** La liquidazione supera fondo + accantonamento: il motore rifiuta. */
  oltre: boolean;
  sospeso: boolean;
}

/** Un anno non prodotto è «oltre il fondo» SOLO se il motore si è fermato
 *  proprio lì per questo motivo (l'errore nomina l'anno e inizia per
 *  «Liquidazioni TFR»): un anno non prodotto per un'altra ragione (un
 *  fabbisogno scoperto altrove, un tetto dei fidi) non lo è. */
function tfrOltreDalErrore(data: ForecastPreviewResponse | null, year: number): boolean {
  const err = data?.error;
  return err != null && err.year === year && /^Liquidazioni TFR/.test(err.message);
}

export function tfrRighe(assumptions: AssumptionsMap, years: number[], data: ForecastPreviewResponse | null): TfrRiga[] {
  const prodotti = new Map((data?.forecast_years ?? []).map((y) => [y.year, y]));
  return years.map((year) => {
    const liquidazione = num((assumptions[year] as Record<string, unknown> | undefined)?.tfr_payments);
    const prodotto = prodotti.get(year);
    if (!prodotto) {
      return { year, accantonamento: null, chiusura: null, liquidazione, oltre: tfrOltreDalErrore(data, year), sospeso: false };
    }
    const t = prodotto.details.tfr;
    const oltre = liquidazione > num(t.apertura) + num(t.accantonamento) + 0.005;
    return { year, accantonamento: num(t.accantonamento), chiusura: num(t.chiusura), liquidazione, oltre, sospeso: t.sospeso };
  });
}

// ── Nuovi finanziamenti (spec §4.6) ─────────────────────────────────────

export interface NuovoFinanziamento { year: number; index: number; loan: FinancingLoanInput }

/** I nuovi finanziamenti dichiarati su ciascun anno di piano: solo le righe
 *  con `amount > 0` (un residuo pregresso senza erogazione non è "nuovo"),
 *  con l'indice originale nella lista `financing_loans` di QUELL'anno — lo
 *  stesso indice che `p.updateFinancingLoans` si aspetta per sostituire la
 *  riga giusta. */
export function nuoviFinanziamenti(assumptions: AssumptionsMap, years: number[]): NuovoFinanziamento[] {
  const out: NuovoFinanziamento[] = [];
  for (const year of years) {
    const loans = ((assumptions[year] as Record<string, unknown> | undefined)?.financing_loans ?? null) as
      FinancingLoanInput[] | null;
    (loans ?? []).forEach((loan, index) => {
      if (num(loan.amount) > 0) out.push({ year, index, loan });
    });
  }
  return out;
}

/** Un euro «piatto», senza decimali — E senza lo spazio insecabile che
 *  `Intl.NumberFormat('it-IT', {style: 'currency', ...})` mette prima del
 *  simbolo: un riepilogo confrontato per uguaglianza esatta (il test di
 *  questo modulo, e prima ancora l'occhio dell'utente) non deve dipendere
 *  da un carattere invisibile. */
const eur0 = (v: number): string => `${formatNumber(v, 0)} €`;

/** «500.000 € · 2027 · rata 100.000 €/anno dal 2029»: la rata capitale
 *  ordinaria (`amount / (durata − preammortamento)`, minimo un anno) e
 *  l'anno in cui comincia (`year + preammortamento + 1`). */
export function riepilogoNuovo(loan: FinancingLoanInput, year: number): string {
  const durata = num(loan.duration_years) || 1;
  const grazia = num(loan.grace_years);
  const rata = num(loan.amount) / Math.max(1, durata - grazia);
  const dal = year + grazia + 1;
  return `${eur0(num(loan.amount))} · ${year} · rata ${eur0(rata)}/anno dal ${dal}`;
}

/** Il primo anno di piano SENZA un nuovo finanziamento già dichiarato,
 *  altrimenti il primo anno del piano (ogni anno è già occupato: «+ Aggiungi
 *  finanziamento» propone comunque un anno, l'utente lo cambia dal `Select`). */
export function annoLibero(years: number[], esistenti: readonly NuovoFinanziamento[]): number {
  const occupati = new Set(esistenti.map((n) => n.year));
  return years.find((y) => !occupati.has(y)) ?? years[0];
}

/** Il finanziamento proposto da «+ Aggiungi finanziamento»: nome generico,
 *  200.000 €, 5 anni, nessun preammortamento, 4,5%. */
export function nuovoPrestito(year: number): FinancingLoanInput {
  void year; // riservato: l'anno di erogazione lo decide il chiamante (`updateFinancingLoans`), non questo importo.
  return { name: "Nuovo finanziamento", amount: 200000, opening_residual: 0, duration_years: 5, grace_years: 0, interest_rate: 4.5, balloon_pct: 0 };
}

/** Un solo campo di un contratto NUOVO, sull'anno in cui è già scritto: chi
 *  cambia l'anno di erogazione (il `Select`) non passa da qui — sposta
 *  l'intera riga fra due liste con `p.updateFinancingLoans` due volte. */
export function withNuovoCampo(
  loans: FinancingLoanInput[], index: number, field: keyof FinancingLoanInput, value: string | number | null,
): FinancingLoanInput[] {
  return loans.map((loan, i) => (i === index ? { ...loan, [field]: value } : loan));
}

// ── Cassa e scoperto (spec §4.6, aggiornata il 2026-09-15) ─────────────

/** Il regime esplicito di fidi e anticipi (spec §5.2): `bank_lines_amount`
 *  non nullo sulla riga del primo anno di piano — sempre vero dopo il passo
 *  5. In quel regime la casella «Concedi lo scoperto» e il suo tetto non si
 *  mostrano più: il riutilizzo dei fidi (§5.2-bis) prende il loro posto, e
 *  il piano non si ferma mai per fabbisogno scoperto. */
export function regimeEsplicito(assumptions: AssumptionsMap, firstYear: number): boolean {
  const raw = (assumptions[firstYear] as Record<string, unknown> | undefined)?.bank_lines_amount;
  return raw !== null && raw !== undefined;
}

/** Gli avvisi dei fidi che il motore dichiara (`details.avviso_fidi`), un
 *  anno alla volta: solo gli anni che ne hanno uno, mai una riga vuota. Una
 *  chiave assente (uno scenario ancora senza il motore che la scrive) vale
 *  zero, cioè nessun avviso — non «non lo so». */
export function avvisiFidi(years: ForecastPreviewYear[]): string[] {
  return years
    .map((y) => y.details.avviso_fidi)
    .filter((m): m is string => typeof m === "string" && m.length > 0);
}

// ── Debito, cassa e PFN (spec §4.6) ─────────────────────────────────────

/** Il debito finanziario totale del bilancio (banche + altri finanziatori +
 *  obbligazioni, breve e lungo): stessa somma di `finDebt` in
 *  `lib/budget-preview-rows.ts` (non esportata di là — è una recapitolazione
 *  di campi già a schermo, non un secondo motore). */
const finDebt = (bs: Record<string, unknown>): number =>
  num(bs.sp16a_debiti_banche_breve) + num(bs.sp17a_debiti_banche_lungo)
  + num(bs.sp16b_debiti_altri_finanz_breve) + num(bs.sp17b_debiti_altri_finanz_lungo)
  + num(bs.sp16c_debiti_obbligazioni_breve) + num(bs.sp17c_debiti_obbligazioni_lungo);

const altriFinanz = (bs: Record<string, unknown>): number =>
  num(bs.sp16b_debiti_altri_finanz_breve) + num(bs.sp17b_debiti_altri_finanz_lungo);

const immobNette = (bs: Record<string, unknown>): number =>
  num(bs.sp02_immob_immateriali) + num(bs.sp03_immob_materiali);

const cassaDi = (bs: Record<string, unknown>): number => num(bs.sp09_disponibilita_liquide);

/**
 * Una riga per componente del debito bancario, una per ogni nuovo
 * finanziamento con il proprio nome — la card «Debito, cassa e PFN» del
 * passo 6. `fidiBase` arriva da fuori (`assumptions[firstYear].bank_lines_amount`)
 * perché non è un saldo di bilancio: è la parte del debito bancario base che
 * il passo 5 ha dichiarato «fidi», non uno SP. `baseInc` è opzionale — serve
 * solo al rapporto PFN/MOL della colonna base, e senza il CE dell'anno base
 * (il componente non lo passa sempre) quella colonna resta senza nota,
 * mai un multiplo inventato.
 */
export function rowsDebitoCassaPfn(
  baseBs: BalanceSheet, fidiBase: number | null, years: ForecastPreviewYear[], baseInc?: IncomeStatement | null,
): PreviewRow[] {
  const bb = baseBs as unknown as Record<string, unknown>;
  const bankBase = baseBankDebt(bb);
  const contrattiBase = bankBase - (fidiBase ?? 0);

  const fidiDi = (y: ForecastPreviewYear) => y.details.debito_bancario.fidi;
  const contrattiDi = (y: ForecastPreviewYear) => y.details.debito_bancario.contratti ?? [];
  const contrattiPregressi = (y: ForecastPreviewYear) => contrattiDi(y).filter((c) => num(c.residuo_iniziale) > 0);
  const contrattiNuovi = (y: ForecastPreviewYear) => contrattiDi(y).filter((c) => num(c.residuo_iniziale) === 0);

  const rows: PreviewRow[] = [];
  rows.push(mkRow("fidi", "Fidi e anticipi", "value",
    { value: fidiBase }, years.map((y) => { const f = fidiDi(y); return { value: f ? num(f.residuo) : null }; })));

  const rimborsoSweepPerAnno = years.map((y) => { const f = fidiDi(y); return f ? num(f.rimborso_sweep) : 0; });
  if (rimborsoSweepPerAnno.some((v) => v > 0)) {
    rows.push(mkRow("sweep", "ridotti con la cassa in eccesso", "sub",
      { value: null }, rimborsoSweepPerAnno.map((v) => ({ value: v > 0 ? -v : 0 }))));
  }

  rows.push(mkRow("contratti", "Finanziamenti bancari esistenti", "value",
    { value: contrattiBase },
    years.map((y) => ({ value: contrattiPregressi(y).reduce((s, c) => s + num(c.breve) + num(c.lungo), 0) }))));

  // Un contratto nuovo puo' comparire su un anno e non sugli altri (erogato
  // in un anno, estinto o non ancora prodotto negli altri): si raccoglie
  // l'indice -> nome dal primo anno che lo dichiara, e si legge il suo
  // importo anno per anno (zero dove il contratto non c'e' ancora).
  const nomeDiIndice = new Map<number, string>();
  for (const y of years) {
    for (const c of contrattiNuovi(y)) {
      if (!nomeDiIndice.has(c.indice)) nomeDiIndice.set(c.indice, c.nome || "Nuovo finanziamento");
    }
  }
  for (const [indice, nome] of [...nomeDiIndice.entries()].sort((a, b) => a[0] - b[0])) {
    rows.push(mkRow(`nuovo-${indice}`, nome, "value", { value: 0 },
      years.map((y) => {
        const c = contrattiNuovi(y).find((c) => c.indice === indice);
        return { value: c ? num(c.breve) + num(c.lungo) : 0 };
      })));
  }

  rows.push(mkRow("scoperto", "Scoperto di conto corrente generato dal piano", "value",
    { value: null }, years.map((y) => ({ value: num(y.details.scoperto_residuo) }))));

  rows.push(mkRow("altri", "Altri finanziatori", "value",
    { value: altriFinanz(bb) }, years.map((y) => ({ value: altriFinanz(y.balance_sheet as unknown as Record<string, unknown>) }))));

  rows.push(mkRow("tfr-liq", "Fondo TFR · liquidazioni nell'anno", "sub",
    { value: null }, years.map((y) => ({ value: -num(y.details.tfr.liquidazioni) }))));

  rows.push(mkRow("immob", "Immobilizzazioni nette", "value",
    { value: immobNette(bb) }, years.map((y) => ({ value: immobNette(y.balance_sheet as unknown as Record<string, unknown>) }))));

  rows.push(mkRow("cassa", "Cassa", "kpi",
    { value: cassaDi(bb) }, years.map((y) => ({ value: cassaDi(y.balance_sheet as unknown as Record<string, unknown>) }))));

  rows.push(mkRow("pfn", "Posizione finanziaria netta", "total",
    { value: finDebt(bb) - cassaDi(bb) },
    years.map((y) => {
      const bs = y.balance_sheet as unknown as Record<string, unknown>;
      return { value: finDebt(bs) - cassaDi(bs) };
    })));

  // Un multiplo («2,4×»), non una percentuale: `PreviewCell.pct` passa da
  // `pct1`, che assume la convenzione «percentuale assoluta» del resto del
  // progetto (25,5 = 25,5%) e avrebbe mostrato un rapporto di 2,4 come
  // «2,4%». Il testo va quindi in `note`, con `value` e `pct` entrambi
  // assenti — un MOL a zero (o un anno base senza CE) non produce un
  // rapporto, non uno zero inventato.
  const multiplo = (pfn: number, mol: number | null): string | undefined =>
    mol !== null && mol !== 0 ? `${formatNumber(pfn / mol, 1)}×` : undefined;
  const molBase = baseInc ? ceAggregates(baseInc as unknown as Record<string, unknown>).mol : null;
  rows.push(mkRow("pfn-mol", "PFN / MOL", "sub",
    { value: null, note: multiplo(finDebt(bb) - cassaDi(bb), molBase) },
    years.map((y) => {
      const bs = y.balance_sheet as unknown as Record<string, unknown>;
      const pfn = finDebt(bs) - cassaDi(bs);
      const mol = ceAggregates(y.income_statement as unknown as Record<string, unknown>).mol;
      return { value: null, note: multiplo(pfn, mol) };
    })));

  return rows;
}

// ── Voci minori: regola nel piano, altri crediti e debiti (spec §4.6) ──

/** L'etichetta breve di ciascun driver dentro «segue …» — diversa da
 *  `DRIVER_LABELS` di `lib/budget-circolante-step.ts` (quella e' pensata per
 *  «Cresce con {label}» e porta la parentesi «gli acquisti (materie e
 *  servizi)»; qui il testo e' quello letterale della spec, «segue gli
 *  acquisti»). */
const REGOLA_DRIVER: Record<SpIndexingDriver, string> = {
  ricavi: "i ricavi", acquisti: "gli acquisti", personale: "il personale",
};

/** Le sette voci minori che compaiono nella card «Altri crediti e debiti del
 *  piano»: il codice corto (per il driver, `sp_indexing`/`spIndexingOf`),
 *  il nome pieno del campo SP (chiave del risultato e riga di
 *  `rowsAltriCreditiDebiti`) e — quando esiste — il campo `sp*_growth_pct`.
 *  `sp06g` (crediti diversi, sotto-riga del DSO) e `sp06e` (crediti
 *  tributari, governati dalla posizione fiscale) non hanno un driver in
 *  `sp_indexing`: un piano di volume su di loro non esiste nel motore. */
const VOCI_MINORI_PIANO: readonly { code?: string; baseField: string; growthField?: string; previdenza?: boolean }[] = [
  { baseField: "sp06g_crediti_altri_breve" },
  { code: "sp10", baseField: "sp10_ratei_risconti_attivi", growthField: "sp10_growth_pct" },
  { baseField: "sp06e_crediti_tributari_breve", growthField: "sp06e_growth_pct" },
  { code: "sp16f", baseField: "sp16f_debiti_previdenza_breve", growthField: "sp16f_growth_pct", previdenza: true },
  { code: "sp16g", baseField: "sp16g_altri_debiti_breve", growthField: "sp16g_growth_pct" },
  { code: "sp14", baseField: "sp14_fondi_rischi", growthField: "sp14_growth_pct" },
  { code: "sp18", baseField: "sp18_ratei_risconti_passivi", growthField: "sp18_growth_pct" },
];

/** La regola che il piano applica a ciascuna delle sette voci minori, nella
 *  parola dell'utente: «costante», «variazione +X,X%», «segue …». Legge il
 *  driver dalla riga del PRIMO anno di piano (`spIndexingOf`, stesso
 *  criterio di `boolAssumption`): un'ipotesi per anno, ma la scelta e' una
 *  sola. */
export function regoleVociMinori(assumptions: AssumptionsMap, years: number[]): Record<string, string> {
  const firstYear = years[0];
  const indexing = spIndexingOf(assumptions, years);
  const riga = assumptions[firstYear] as Record<string, unknown> | undefined;
  const previdenzaSuPersonale = Boolean(riga?.previdenza_scales_with_personnel);
  const out: Record<string, string> = {};
  for (const v of VOCI_MINORI_PIANO) {
    const driver: SpIndexingDriver | null = v.previdenza && previdenzaSuPersonale
      ? "personale"
      : v.code ? indexing[v.code] ?? null : null;
    const crescita = v.growthField ? num(riga?.[v.growthField]) : 0;
    out[v.baseField] = driver
      ? `segue ${REGOLA_DRIVER[driver]}`
      : crescita !== 0
        ? `variazione ${crescita > 0 ? "+" : ""}${formatNumber(crescita, 1)}%`
        : "costante";
  }
  return out;
}

const ATTIVO_MINORE = [
  { key: "sp06g", baseField: "sp06g_crediti_altri_breve", label: "Altri crediti a breve" },
  { key: "sp10", baseField: "sp10_ratei_risconti_attivi", label: "Ratei e risconti attivi" },
  { key: "sp06e", baseField: "sp06e_crediti_tributari_breve", label: "Crediti tributari · dalle imposte, passo 7" },
] as const;

const PASSIVO_MINORE = [
  { key: "sp16f", baseField: "sp16f_debiti_previdenza_breve", label: "Debiti previdenziali entro" },
  { key: "sp16g", baseField: "sp16g_altri_debiti_breve", label: "Altri debiti entro" },
  { key: "sp14", baseField: "sp14_fondi_rischi", label: "Fondi per rischi e oneri" },
  { key: "sp18", baseField: "sp18_ratei_risconti_passivi", label: "Ratei e risconti passivi" },
] as const;

const somma = (bs: Record<string, unknown>, campi: readonly { baseField: string }[]): number =>
  campi.reduce((acc, c) => acc + num(bs[c.baseField]), 0);

/**
 * La card «Altri crediti e debiti del piano»: crediti/attività, debiti/fondi,
 * i due totali, e l'effetto sulla cassa nell'anno — `(Δ passivo − Δ attivo)`
 * sull'anno precedente (l'anno base per la prima colonna prodotta). Ogni
 * riga porta la sua regola (`regoleVociMinori`) come nota.
 */
export function rowsAltriCreditiDebiti(
  baseBs: BalanceSheet, years: ForecastPreviewYear[], regole: Record<string, string>,
): PreviewRow[] {
  const bb = baseBs as unknown as Record<string, unknown>;
  const rows: PreviewRow[] = [];
  const empty = (): PreviewCell[] => years.map(() => ({ value: null }));

  rows.push(mkRow("h-attivo", "Crediti e attività", "total", { value: null }, empty()));
  for (const f of ATTIVO_MINORE) {
    rows.push(mkRow(f.key, f.label, "value", { value: num(bb[f.baseField]) },
      years.map((y) => ({ value: num((y.balance_sheet as unknown as Record<string, unknown>)[f.baseField]), note: regole[f.baseField] }))));
  }
  rows.push(mkRow("tot-attivo", "Totale", "total", { value: somma(bb, ATTIVO_MINORE) },
    years.map((y) => ({ value: somma(y.balance_sheet as unknown as Record<string, unknown>, ATTIVO_MINORE) }))));

  rows.push(mkRow("h-passivo", "Debiti e fondi", "total", { value: null }, empty()));
  for (const f of PASSIVO_MINORE) {
    rows.push(mkRow(f.key, f.label, "value", { value: num(bb[f.baseField]) },
      years.map((y) => ({ value: num((y.balance_sheet as unknown as Record<string, unknown>)[f.baseField]), note: regole[f.baseField] }))));
  }
  rows.push(mkRow("tot-passivo", "Totale", "total", { value: somma(bb, PASSIVO_MINORE) },
    years.map((y) => ({ value: somma(y.balance_sheet as unknown as Record<string, unknown>, PASSIVO_MINORE) }))));

  let prevAttivo = somma(bb, ATTIVO_MINORE);
  let prevPassivo = somma(bb, PASSIVO_MINORE);
  const cassaCells: PreviewCell[] = years.map((y) => {
    const bs = y.balance_sheet as unknown as Record<string, unknown>;
    const attivo = somma(bs, ATTIVO_MINORE), passivo = somma(bs, PASSIVO_MINORE);
    const cassa = (passivo - prevPassivo) - (attivo - prevAttivo);
    prevAttivo = attivo; prevPassivo = passivo;
    return { value: cassa };
  });
  rows.push(mkRow("cassa", "Effetto sulla cassa nell'anno · + libera · − assorbe", "kpi", { value: null }, cassaCells));

  return rows;
}
