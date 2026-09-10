/**
 * Le decisioni del passo 7 «Imposte» (spec 2026-09-08 §4.7), l'ultimo del
 * percorso: la lettura/scrittura dell'aliquota forzata (un solo input,
 * scritto su tutti gli anni con `updateAll`) e la composizione
 * dell'anteprima. Stesso schema di `lib/budget-pregresso-step.ts` (Task 12):
 * niente di questo si decide dentro `StepImposte.tsx`.
 *
 * Le imposte NON si ricalcolano qui: le produce il motore
 * (`calculations/forecast_engine.py`), `rowsImposte` le legge dal CE che il
 * motore ha gia' scritto.
 */
import type {
  BalanceSheet, ForecastPreviewResponse, ForecastPreviewYear, IncomeStatement,
  Pregresso, PregressoKey, PregressoTributari,
} from "@/types/api";
import type { AssumptionsMap } from "@/lib/budget-horizon";
import { euro, numOrNull } from "@/lib/budget-format";
import { equalInstalments, openingMasses } from "@/lib/budget-pregresso-circolante";
import { singleYearValue, type SingleYearValue } from "@/lib/budget-pregresso-step";
import { rowsImposte, rowsImposteSaldoAcconto, type PreviewRow } from "@/lib/budget-preview-rows";

/**
 * L'aliquota reale del progetto: IRES + IRAP, non il `24` (sola IRES) di
 * default nello schema Pydantic (CLAUDE.md § Tax rate; `lib/budget-horizon.ts`
 * la scrive gia' cosi' su un'ipotesi nuova). La colonna `tax_rate` e' NOT
 * NULL: una casella lasciata vuota non puo' scrivere `null` come le altre
 * percentuali nullable, scrive questo valore esplicitamente.
 */
export const DEFAULT_TAX_RATE = 27.9;

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

export interface SpTributariRow {
  field: string;
  label: string;
  sub: string;
  baseLabel: string;
}

/**
 * La via MANUALE: `sp06e_growth_pct` **oppure** `sp16e_growth_pct` valorizzata
 * su un anno qualsiasi del piano.
 *
 * Misurato sul motore, non dedotto: `forecast_engine.py` costruisce
 * `manual_tax_position` da quei due soli campi (`getattr(...) is not None`),
 * quindi **uno zero e' un valore**, non un'assenza — chi scrive `0` passa alla
 * via manuale. La via e' per anno: se un anno solo ce l'ha, quel controllo
 * governa qualcosa e resta a schermo.
 */
export function manualTaxPosition(assumptions: AssumptionsMap, years: number[]): boolean {
  return years.some((y) => {
    const a = assumptions[y] as Record<string, unknown> | undefined;
    return (a?.sp06e_growth_pct ?? null) !== null || (a?.sp16e_growth_pct ?? null) !== null;
  });
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
 */
export const SP17E_NOTA_AUTOMATICA =
  "«Debiti tributari oltre %» non compare finché il piano governa i tributari: il debito oltre l'esercizio " +
  "è il residuo delle rate, e una percentuale di crescita non lo muoverebbe. Torna valorizzando «Debiti " +
  "tributari entro %» qui sotto, o «Crediti tributari %» al passo Circolante.";

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
export function spTributariRows(baseBs: BalanceSheet | undefined | null, manual: boolean): SpTributariRow[] {
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
    });
  }
  return rows;
}

// ── Il piano di pagamento: saldo, rateizzato, rate, acconto ─────────────────
// Il modello e la validazione stanno in `lib/budget-pregresso-circolante.ts`
// (`openingMasses`, `equalInstalments`, `validatePregresso`): qui non se ne
// riscrive nulla, si compone. Tutto immutabile — nessuna funzione muta cio'
// che riceve.

const cents = (v: number) => Math.round(v * 100) / 100;

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

/**
 * Scrive il saldo dell'anno precedente e ne DEDUCE il rateizzato: le due cifre
 * devono sommare l'apertura, e `validatePregresso` rifiuta un piano in cui non
 * lo fanno.
 *
 * Un saldo oltre l'apertura NON viene troncato — superare la massa dichiarata
 * e' un errore, mai un troncamento: si scrive, il rateizzato diventa negativo e
 * la validazione lo dichiara (il server lo rifiuterebbe comunque, con un 422
 * molto meno leggibile). Una casella svuotata scrive uno ZERO, cioe' mette
 * tutto a rate: non lascia il saldo di prima.
 */
export function withSaldo(pregresso: Pregresso, opening: number, saldo: number | null): Pregresso {
  const plan = tributariPlanOrDefault(pregresso, opening);
  const s = cents(saldo ?? 0);
  return conPiano(pregresso, { ...plan, opening, saldo: s, rateizzato: cents(opening - s) });
}

/** Le rate dichiarate, senza toccare saldo, rateizzato e acconto. E' la porta
 *  di ritorno della `PregressoTable`, che di un piano tributario conosce le
 *  sole `amounts`. */
export function withRate(pregresso: Pregresso, opening: number, amounts: number[]): Pregresso {
  return conPiano(pregresso, { ...tributariPlanOrDefault(pregresso, opening), amounts });
}

/** `n` rate uguali sul RATEIZZATO — non sull'apertura: il saldo si versa per
 *  intero nel primo anno di piano e non entra nel runoff. */
export function withRateUguali(pregresso: Pregresso, opening: number, n: number): Pregresso {
  const plan = tributariPlanOrDefault(pregresso, opening);
  return conPiano(pregresso, { ...plan, amounts: equalInstalments(plan.rateizzato, n) });
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

/** Il numero di rate uguali che si possono offrire: mai piu' degli anni di
 *  piano, o si creerebbe un piano che `validatePregresso` rifiuta subito. */
export function rateOptions(horizon: number): number[] {
  return [2, 3, 4, 5].filter((n) => n <= horizon);
}

/**
 * Le masse per la `PregressoTable`: quella dei tributari e' il RATEIZZATO, non
 * l'apertura — il piano delle rate scadenzia il solo rateizzato, e il motore
 * fa lo stesso (`runoff_schedule(plan_tax['rateizzato'], …)`). Le altre quattro
 * voci non entrano in questa tabella e restano a zero.
 */
export function tributariMasses(pregresso: Pregresso, opening: number): Record<PregressoKey, number> {
  return {
    crediti_commerciali: 0, debiti_fornitori: 0, debiti_previdenziali: 0, altri_debiti: 0,
    debiti_tributari: tributariPlan(pregresso)?.rateizzato ?? 0,
  };
}

/**
 * Il piano come lo LEGGE la tabella: stessa lista di rate, ma l'apertura e' il
 * rateizzato, cosi' residuo e percentuali si leggono su cio' che si sta
 * davvero scadenziando. E' una vista — il piano vero conserva la sua apertura,
 * ed e' quello che si salva.
 */
export function tributariTabella(pregresso: Pregresso, opening: number): Pregresso {
  const plan = tributariPlan(pregresso);
  return plan ? { debiti_tributari: { ...plan, opening: plan.rateizzato } } : {};
}

/** La sola chiave che la tabella del passo 7 scadenzia. Le altre quattro
 *  stanno al passo 6 (`TABELLA_KEYS`). */
export const TRIBUTARI_KEYS: readonly PregressoKey[] = ["debiti_tributari"];

/** La riga in coda alla tabella delle rate: al passo 7 non c'e' nessuna voce
 *  che si estingue, quindi la via d'uscita del passo 6 non c'entra. */
export const TRIBUTARI_TABELLA_NOTA =
  "Le rate scadenziano il solo rateizzato: il saldo esce per intero nel primo anno di piano, insieme " +
  "all'acconto. Ciò che resta dopo l'ultimo anno resta a bilancio come debito oltre l'esercizio.";

/** La chiosa della casella dell'acconto: la percentuale e' il ripiego, un
 *  importo esplicito per anno vince (`explicit_advances > 0` nel kernel). */
export const ACCONTO_CHIOSA =
  "percentuale dell'imposta dell'anno prima; gli acconti per anno qui sopra, se valorizzati, lo scavalcano.";

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
