/**
 * Le decisioni del passo 7 «Imposte» (spec 2026-09-08 §4.7, ridotto il
 * 2026-09-15 all'aliquota e al pagamento dell'anno in corso — saldo,
 * rateizzato e rate dei debiti tributari si scadenziano al passo 5
 * «Patrimoniale pregresso», Task 13b/16): la lettura/scrittura dell'aliquota
 * forzata (un solo input, scritto su tutti gli anni con `updateAll`) e la
 * composizione dell'anteprima. Niente di questo si decide dentro
 * `StepImposte.tsx`.
 *
 * Le imposte NON si ricalcolano qui: le produce il motore
 * (`calculations/forecast_engine.py`), `rowsImposte` le legge dal CE che il
 * motore ha gia' scritto.
 */
import type {
  BalanceSheet, ForecastPreviewResponse, ForecastPreviewYear, IncomeStatement,
  Pregresso, PregressoTributari,
} from "@/types/api";
import type { AssumptionsMap } from "@/lib/budget-horizon";
import { euro, num, numOrNull } from "@/lib/budget-format";
import { openingMasses } from "@/lib/budget-pregresso-circolante";
import { rowsImposte, rowsImposteSaldoAcconto, type PreviewRow } from "@/lib/budget-preview-rows";
import type { YearCellOff } from "@/lib/budget-year-cell";

/**
 * L'aliquota reale del progetto: IRES + IRAP, non il `24` (sola IRES) di
 * default nello schema Pydantic (CLAUDE.md § Tax rate; `lib/budget-horizon.ts`
 * la scrive gia' cosi' su un'ipotesi nuova). La colonna `tax_rate` e' NOT
 * NULL: una casella lasciata vuota non puo' scrivere `null` come le altre
 * percentuali nullable, scrive questo valore esplicitamente.
 */
export const DEFAULT_TAX_RATE = 27.9;

export interface SingleYearValue {
  /** Il valore da mostrare: quello del primo anno previsto (`null` = non impostato). */
  value: number | null;
  /** Almeno un anno ne ha uno diverso: scrivere di nuovo li allinea tutti. */
  uneven: boolean;
}

/**
 * Legge un campo scritto con `updateAll` (stesso valore su ogni anno di
 * piano): si mostra quello del primo anno previsto, e si dichiara se gli
 * altri non concordano piu' — puo' succedere se un valore e' stato cambiato
 * altrove, anno per anno.
 *
 * Spostata qui da `lib/budget-pregresso-step.ts` (Task 16, cancellato con
 * `StepPregressoNuovo.tsx`): questo modulo ne resta l'unico chiamante di
 * produzione (`taxRateValue`, sotto).
 */
export function singleYearValue(assumptions: AssumptionsMap, years: number[], field: string): SingleYearValue {
  const vals = years.map((y) => {
    const raw = (assumptions[y] as Record<string, unknown> | undefined)?.[field];
    return raw === null || raw === undefined ? null : num(raw);
  });
  const value = vals.length > 0 ? vals[0] : null;
  return { value, uneven: vals.some((v) => v !== value) };
}

/** Il valore del campo `tax_rate`, con lo stesso schema "primo anno previsto
 *  + disallineamento" di `singleYearValue`. */
export function taxRateValue(assumptions: AssumptionsMap, years: number[]): SingleYearValue {
  return singleYearValue(assumptions, years, "tax_rate");
}

/**
 * Che cosa mostrare nella casella dell'aliquota forzata: vuota quando il
 * valore e' il default 27,9 (cosi' la casella si legge come "non forzata",
 * anche se la colonna non ammette `null`), altrimenti il numero salvato.
 */
export function taxRateInputDisplay(v: SingleYearValue): number | "" {
  return v.value === null || v.value === DEFAULT_TAX_RATE ? "" : v.value;
}

/**
 * Il segnaposto della casella dell'aliquota forzata.
 *
 * Era `auto ${DEFAULT_TAX_RATE}` in una casella larga 80 px, e a schermo si
 * leggeva «auto :» — un troncamento che sembra un errore di rendering. Il
 * segnaposto quindi non ripete piu' il numero (che sta nella riga sotto la
 * casella e, quando il piano lo usa davvero, nella riga «Aliquota usata dal
 * piano»), e la casella e' stata allargata perche' ci stia anche un valore
 * digitato di quattro cifre e una virgola.
 *
 * Sta qui, e con la sua prova, perche' e' la lunghezza a essere il difetto:
 * un ripensamento che ci rimettesse dentro il 27,9 tornerebbe a troncare.
 */
export const TAX_RATE_PLACEHOLDER = "auto";

export interface SpTributariRow extends YearCellOff {
  field: string;
  label: string;
  sub: string;
  baseLabel: string;
}

/**
 * Gli anni sui quali la via manuale e' DAVVERO accesa: quelli in cui
 * `sp06e_growth_pct` o `sp16e_growth_pct` sono valorizzati su QUELL'anno.
 *
 * Misurato sul motore, non dedotto: `forecast_engine.py` decide
 * `manual_tax_position` da quei due soli campi (`getattr(...) is not None`),
 * **per anno** (`forecast_engine.py:2038-2041`) — quindi **uno zero e' un
 * valore**, non un'assenza, e un piano misto (2027 automatico, 2028 manuale)
 * non accende la via sul 2027 anche se `manualTaxPosition` (sotto) e' `true`
 * perche' governa il 2028. Serve la lista, non solo il booleano: e' cosi' che
 * `spTributariRows` decide QUALI celle di `sp17e_growth_pct` restano vive
 * (fix1 R2 — prima la via era un booleano unico su tutto il piano, e la
 * cella dell'anno automatico restava compilabile senza muovere nulla).
 */
export function manualTaxYears(assumptions: AssumptionsMap, years: number[]): number[] {
  return years.filter((y) => {
    const a = assumptions[y] as Record<string, unknown> | undefined;
    return (a?.sp06e_growth_pct ?? null) !== null || (a?.sp16e_growth_pct ?? null) !== null;
  });
}

/** La via MANUALE governa ALMENO un anno del piano: decide se la riga
 *  `sp17e_growth_pct` compare affatto (vedi `manualTaxYears` per la
 *  granularita' per anno, che decide quali SUE celle restano vive). */
export function manualTaxPosition(assumptions: AssumptionsMap, years: number[]): boolean {
  return manualTaxYears(assumptions, years).length > 0;
}

const SP16E_SUB =
  "valorizzarla passa alla via manuale: i debiti tributari crescono di percentuale e il piano qui sopra viene ignorato";
const SP17E_SUB = "governa il debito oltre l'esercizio soltanto sulla via manuale";

/**
 * Perche' «Debiti tributari oltre %» non e' a schermo sulla via automatica.
 *
 * Non e' una semplificazione: `sp17e_growth_pct` compare UNA sola volta in
 * `calculations/forecast_engine.py`, dentro il ramo `if manual_tax_position:`,
 * e non e' fra i campi che quel ramo lo accendono. Sulla via automatica quindi
 * l'utente lo imposta e non succede nulla, **senza errore** — la classe di
 * difetto peggiore che questo repo conosca. Il controllo sparisce, e questa
 * riga dice come farlo tornare.
 *
 * «qui sopra», non «qui sotto»: in `StepImposte.tsx` la `YearInputTable` con
 * la riga «Debiti tributari entro %» viene resa PRIMA di questa nota, quindi
 * quella riga sta sopra la nota, non sotto (fix1 R4). E l'etichetta del passo
 * Circolante e' «Crediti tributari», senza «%» (`budget-circolante-step.ts`).
 */
export const SP17E_NOTA_AUTOMATICA =
  "«Debiti tributari oltre %» non compare finché il piano governa i tributari: il debito oltre l'esercizio " +
  "è il residuo delle rate, e una percentuale di crescita non lo muoverebbe. Torna valorizzando «Debiti " +
  "tributari entro %» qui sopra, o «Crediti tributari» al passo Circolante.";

/** Il motivo per cui la cella `sp17e_growth_pct` di UN anno automatico resta
 *  inerte su un piano MISTO (qualche anno manuale, altri no): stesso
 *  contenuto di `SP17E_NOTA_AUTOMATICA`, mostrato come `title` sulla singola
 *  cella invece che come riga sotto la tabella (fix1 R2). */
export const SP17E_NOTA_ANNO_AUTOMATICO = SP17E_NOTA_AUTOMATICA;

/** L'avviso della via manuale, dentro l'accordion: valorizzare una di quelle
 *  percentuali fa ignorare saldo, rate e acconti dichiarati sopra. */
export const MANUAL_TAX_AVVISO =
  "Con una di queste percentuali valorizzata il motore muove i debiti tributari per crescita e ignora il " +
  "piano di saldo, rate e acconti: sono due vie alternative, non due ipotesi che si sommano.";

/** Il motore l'ha davvero ignorato, e lo dichiara: `pregresso_ignored`. Non e'
 *  la stessa cosa della previsione fatta sulle ipotesi — questo e' misurato. */
export const PREGRESSO_IGNORED_AVVISO =
  "Il motore ha ignorato il piano dei debiti tributari: è attiva la via manuale.";

/**
 * Le righe della via manuale dentro «Posizione tributaria manuale». A
 * differenza delle voci del passo 6 (finanziamento e investimenti nuovi, senza
 * analogo nell'anno base), `sp16e`/`sp17e` ESISTONO gia' nel bilancio base — la
 * colonna base porta l'importo vero, non un trattino.
 *
 * `sp16e_growth_pct` c'e' sempre: e' l'interruttore della via manuale, quindi
 * governa qualcosa anche quando la via e' spenta. `sp17e_growth_pct` no: si
 * mostra solo a via accesa (vedi `SP17E_NOTA_AUTOMATICA`).
 */
/**
 * `automaticYears` sono gli anni del piano NON coperti da `manualTaxYears`:
 * su un piano misto, `sp17e_growth_pct` resta a schermo (perche' governa
 * qualcosa da qualche parte) ma le sue celle sugli anni automatici sono
 * inerti — la stessa granularita' per anno del motore, non un booleano unico
 * su tutto il piano (fix1 R2).
 */
export function spTributariRows(
  baseBs: BalanceSheet | undefined | null, manual: boolean, automaticYears: number[] = [],
): SpTributariRow[] {
  const bs = baseBs as unknown as Record<string, unknown> | null | undefined;
  const b = (field: string): number | null => (bs ? numOrNull(bs[field]) : null);
  const rows: SpTributariRow[] = [
    {
      field: "sp16e_growth_pct", label: "Debiti tributari entro %", sub: SP16E_SUB,
      baseLabel: euro(b("sp16e_debiti_tributari_breve")),
    },
  ];
  if (manual) {
    rows.push({
      field: "sp17e_growth_pct", label: "Debiti tributari oltre %", sub: SP17E_SUB,
      baseLabel: euro(b("sp17e_debiti_tributari_lungo")),
      ...(automaticYears.length > 0
        ? { offYears: automaticYears, offYearsNote: SP17E_NOTA_ANNO_AUTOMATICO }
        : {}),
    });
  }
  return rows;
}

// ── Il piano di pagamento tributario: saldo, rateizzato, rate, acconto ──────
// Saldo, rateizzato e rate si scadenziano al passo 5 «Patrimoniale
// pregresso» (`lib/budget-pregresso-oltre.ts`, Task 13b/16): qui resta solo
// l'acconto, che il passo 7 tiene perche' governa l'anno in corso, non il
// pregresso. `tributariPlan`, `tributariPlanOrDefault`, `withRate` e
// `tributariOpening` restano esportati da qui perche' e' `budget-pregresso-
// oltre.ts` a consumarli — spostarli avrebbe rotto quel modulo, o
// duplicato la stessa lettura del piano in due posti. Il modello e la
// validazione stanno in `lib/budget-pregresso-circolante.ts`
// (`openingMasses`, `validatePregresso`): qui non se ne riscrive nulla, si
// compone. Tutto immutabile — nessuna funzione muta cio' che riceve.

/** Il default del kernel (`tax_settlement_saldo_acconto`): senza dichiarazione
 *  l'acconto vale il 100% dell'imposta dell'anno prima. */
export const DEFAULT_ACCONTO_PCT = 100;

/** La massa tributaria di apertura del bilancio base (`sp16e + sp17e`), la
 *  stessa di `openingMasses`. Senza bilancio base e' zero: la forma del valore
 *  non cambia mentre i dati arrivano. */
export function tributariOpening(baseBs: BalanceSheet | undefined | null): number {
  return baseBs ? openingMasses(baseBs).debiti_tributari : 0;
}

/** Il piano dichiarato, `null` finche' nessuno l'ha toccato: un piano assente e
 *  un piano a zero non sono la stessa cosa (senza piano il motore paga tutto il
 *  tributario di apertura come saldo nel primo anno). */
export function tributariPlan(pregresso: Pregresso): PregressoTributari | null {
  return (pregresso.debiti_tributari as PregressoTributari | null | undefined) ?? null;
}

/**
 * Il piano che c'e', o quello di partenza — creato al PRIMO TOCCO, mai al
 * mount: tutto saldo, nulla rateizzato, acconto al 100%. E' la lettura piu'
 * prudente dell'apertura, e coincide con cio' che il motore fa senza piano.
 */
export function tributariPlanOrDefault(pregresso: Pregresso, opening: number): PregressoTributari {
  return tributariPlan(pregresso) ?? {
    opening, saldo: opening, rateizzato: 0, amounts: [], acconto_pct: DEFAULT_ACCONTO_PCT,
  };
}

const conPiano = (pregresso: Pregresso, plan: PregressoTributari): Pregresso =>
  ({ ...pregresso, debiti_tributari: plan });

/** Le rate dichiarate, scritte dalla card «Altre voci oltre 12 mesi» del
 *  passo 5 (`lib/budget-pregresso-oltre.ts`), senza toccare saldo, rateizzato
 *  e acconto — quei due campi restano di competenza di quella card, questo
 *  scrive solo `amounts`. */
export function withRate(pregresso: Pregresso, opening: number, amounts: number[]): Pregresso {
  return conPiano(pregresso, { ...tributariPlanOrDefault(pregresso, opening), amounts });
}

/** La percentuale di acconto. Lo zero e' un valore vero — zero acconti — e non
 *  «non dichiarato»; una casella svuotata torna al default del kernel. */
export function withAccontoPct(pregresso: Pregresso, opening: number, pct: number | null): Pregresso {
  const plan = tributariPlanOrDefault(pregresso, opening);
  return conPiano(pregresso, { ...plan, acconto_pct: pct ?? DEFAULT_ACCONTO_PCT });
}

/** Che cosa mostra la casella dell'acconto: senza piano il 100 che il kernel
 *  applicherebbe comunque, non il vuoto — una casella vuota qui direbbe
 *  «nessun acconto», che e' il contrario di quel che succede. */
export function accontoPctValue(pregresso: Pregresso): number {
  return tributariPlan(pregresso)?.acconto_pct ?? DEFAULT_ACCONTO_PCT;
}

/**
 * Che cosa mostra una casella controllata (saldo, acconto) MENTRE l'utente
 * digita, dato il testo grezzo dell'ultimo `onChange` (`draft`; `null` =
 * nessuna digitazione in corso, per esempio subito dopo un blur) e il valore
 * che il piano ha davvero salvato.
 *
 * Una casella appena svuotata dal backspace resta VUOTA, mai il valore di
 * ripiego (100 per l'acconto): quel ripiego lo scrive `withAccontoPct` nel
 * piano SALVATO, ma se anche la casella lo mostrasse subito la digitazione si
 * romperebbe a meta' — misurato: "10" -> backspace -> "1" non arriva mai
 * alla casella vuota, perche' il valore tornava a 100 a ogni tocco e la
 * cifra successiva si sommava a quel ripiego invece che ripartire da vuoto
 * (fix1 R6).
 */
export function draftDisplay(draft: string | null, saved: number): number | "" {
  if (draft === null) return saved;
  if (draft.trim() === "") return "";
  const n = Number(draft);
  return Number.isFinite(n) ? n : "";
}

/**
 * La chiosa della casella dell'acconto: la percentuale e' il ripiego, un
 * importo esplicito per anno vince — ma solo se MAGGIORE DI ZERO
 * (`explicit_advances > ZERO` nel kernel, `projection_common.py:355`). Chi
 * scrive zero nella casella «Acconti versati nell'anno» non ottiene «zero
 * acconti»: ottiene la percentuale, perche' zero e' il valore che quella
 * casella storica usa per dire «non compilata». Il Ruling 11 lo chiamava «il
 * difetto silenzioso peggiore»: la nota deve dirlo in chiaro, non lasciarlo
 * dedurre da «se valorizzati» (fix1 C1).
 */
export const ACCONTO_CHIOSA =
  "percentuale dell'imposta dell'anno prima; un acconto per anno qui sopra, se MAGGIORE DI ZERO, la " +
  "scavalca — zero vuol dire «usa la percentuale di acconto», non «zero acconti».";

/** Il motore ha davvero ignorato il piano dei tributari, su almeno un anno:
 *  `details['pregresso_ignored']`, dichiarato sempre — anche vuoto. */
export function pregressoIgnoredTributari(years: ForecastPreviewYear[]): boolean {
  return years.some((y) => (y.details?.pregresso_ignored ?? []).includes("debiti_tributari"));
}

export interface ImpostePreview {
  /** Gli anni che il motore ha davvero prodotto, non quelli richiesti. */
  years: number[];
  rows: PreviewRow[];
  /** Il motore ha ignorato il piano dei tributari: misurato sui `details`,
   *  non dedotto dalle ipotesi. */
  pregressoIgnored: boolean;
}

const EMPTY_PREVIEW: ImpostePreview = { years: [], rows: [], pregressoIgnored: false };

/**
 * Dalla risposta del motore a tutto cio' che l'anteprima del passo rende.
 * Senza anno base o senza risposta non c'e' anteprima: nessuna riga, non
 * righe a zero. Gli anni sono quelli che il motore ha davvero prodotto — se
 * si e' fermato a meta' (fabbisogno scoperto al passo 6) la 200 porta gli
 * anni validi ed e' su quelli che le imposte si mostrano.
 */
export function impostePreview(
  baseInc: IncomeStatement | undefined | null,
  data: ForecastPreviewResponse | null
): ImpostePreview {
  if (!baseInc || !data) return EMPTY_PREVIEW;
  const previewYears = data.forecast_years ?? [];
  return {
    years: previewYears.map((y) => y.year),
    // Il CE ricapitolato, poi come quelle imposte si sono PAGATE: due letture
    // dello stesso `forecast_years`, nessun ricalcolo.
    rows: [...rowsImposte(baseInc, previewYears), ...rowsImposteSaldoAcconto(previewYears)],
    pregressoIgnored: pregressoIgnoredTributari(previewYears),
  };
}
