/**
 * Il punto di pareggio sul MOL (spec 2026-09-15 §4.3, decisione 4): lettura pura di
 * `details.pareggio`, che il motore dichiara anno per anno. Qui non si calcola nulla di
 * finanziario: solo la geometria del mini grafico e le frasi della formula.
 *
 * `details` e' nidificato in `Decimal` nel motore (regole comuni del lotto «rilievi»):
 * l'anteprima converte in float solo il primo livello di `details`, quindi ogni chiave di
 * `details.pareggio` puo' arrivare qui come numero o come stringa, a seconda di come
 * l'endpoint la serializza. Si legge sempre con `numOrNull` (mai con un cast, mai
 * assumendo che sia gia' un numero): la stessa regola di `lib/budget-costi-step.ts`.
 */
import type { ForecastPreviewYear, PareggioDetail } from "@/types/api";
import { num, numOrNull } from "@/lib/budget-format";
import type { PreviewRow } from "@/lib/budget-preview-rows";

const ND_NOTE = "Non definito: materie prime o servizi forzati in CE Prev.";

/** Importo arrotondato all'euro, senza simbolo: `formatCurrency` (lib/formatters) non
 *  accetta opzioni, quindi qui si formatta a mano con la stessa localizzazione it-IT. */
const eur0 = (v: number) => new Intl.NumberFormat("it-IT", { maximumFractionDigits: 0 }).format(Math.round(v));
/** Percentuale a un decimale, it-IT — `v` e' una percentuale assoluta (65 = 65%). */
const pct1 = (v: number) =>
  new Intl.NumberFormat("it-IT", { style: "percent", minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(v / 100);

export interface PareggioBarra {
  year: number;
  ricaviPct: number;
  pareggioPct: number;
  margineDaPct: number;
  margineAPct: number;
  ok: boolean;
  margine: number | null;
  marginePct: number | null;
  nd: boolean;
}

/** `details.pareggio`, ma con ogni chiave gia' passata da `numOrNull`: da qui in poi il
 *  resto del modulo lavora su numeri veri, mai su cio' che il JSON ha consegnato. */
interface PareggioNumeri {
  costiVariabili: number | null;
  costiFissi: number | null;
  costiFissiOperativi: number | null;
  margineContribuzionePct: number | null;
  fatturatoPareggio: number | null;
  margineSicurezza: number | null;
  margineSicurezzaPct: number | null;
}

function leggiPareggio(p: PareggioDetail | undefined | null): PareggioNumeri | null {
  if (!p) return null;
  return {
    costiVariabili: numOrNull(p.costi_variabili),
    costiFissi: numOrNull(p.costi_fissi),
    costiFissiOperativi: numOrNull(p.costi_fissi_operativi),
    margineContribuzionePct: numOrNull(p.margine_contribuzione_pct),
    fatturatoPareggio: numOrNull(p.fatturato_pareggio),
    margineSicurezza: numOrNull(p.margine_sicurezza),
    margineSicurezzaPct: numOrNull(p.margine_sicurezza_pct),
  };
}

const ricaviOf = (y: ForecastPreviewYear): number => num((y.income_statement as Record<string, unknown>).ce01_ricavi_vendite);

/**
 * Una riga per anno: la traccia dei ricavi, la tacca del pareggio, il segmento del
 * margine di sicurezza (verde se sopra il pareggio, tratteggiato rosso se sotto), tutto
 * sulla stessa scala — il massimo fra ricavi e pareggio del piano, con un margine del 4%.
 * Un anno `nd` (parte fissa/variabile non definita, override di CE Prev.) non ha una
 * tacca da disegnare: resta a 0, e la tabella sotto lo dichiara con la sua nota.
 */
export function pareggioBarre(years: ForecastPreviewYear[]): PareggioBarra[] {
  const ricavi = years.map(ricaviOf);
  const letti = years.map((y) => leggiPareggio(y.details?.pareggio));
  const bep = letti.map((p) => p?.fatturatoPareggio ?? null);
  const scala = Math.max(0, ...ricavi, ...bep.map((b) => b ?? 0)) * 1.04;
  const x = (v: number) => (scala > 0 ? Math.max(0, Math.min(100, (v / scala) * 100)) : 0);
  return years.map((y, i) => {
    const p = letti[i];
    const nd = !p || p.fatturatoPareggio === null;
    const r = x(ricavi[i]);
    const b = nd ? 0 : x(bep[i] as number);
    const ok = !nd && (p!.margineSicurezza ?? 0) >= 0;
    return {
      year: y.year,
      ricaviPct: r,
      pareggioPct: b,
      margineDaPct: ok ? b : r,
      margineAPct: ok ? r : b,
      ok,
      margine: nd ? null : p!.margineSicurezza,
      marginePct: nd ? null : p!.margineSicurezzaPct,
      nd,
    };
  });
}

/** La formula dell'anno 1, con i numeri veri sostituiti dentro il testo — sempre
 *  quell'anno: e' il primo anno di piano che rappresenta il modo in cui si calcola,
 *  non un anno scelto dall'utente. `null` quando l'anno non ha un pareggio definito. */
export function pareggioFormula(
  first: ForecastPreviewYear | undefined,
): { anno: number; righe: { testo: string; calcolo: string }[] } | null {
  const p = first ? leggiPareggio(first.details?.pareggio) : null;
  if (!first || !p || p.fatturatoPareggio === null || p.costiVariabili === null
    || p.costiFissi === null || p.costiFissiOperativi === null) {
    return null;
  }
  const inc = first.income_statement as Record<string, unknown>;
  const rev = num(inc.ce01_ricavi_vendite), altri = num(inc.ce04_altri_ricavi);
  const mdc = p.margineContribuzionePct ?? 0, bep = p.fatturatoPareggio;
  const margSicPct = p.margineSicurezzaPct ?? 0;
  return {
    anno: first.year,
    righe: [
      {
        testo: "Margine di contribuzione % = (ricavi − costi variabili) / ricavi",
        calcolo: `(${eur0(rev)} − ${eur0(p.costiVariabili)}) / ${eur0(rev)} = ${pct1(mdc)}`,
      },
      {
        testo: "Costi fissi operativi = costi fissi − altri ricavi",
        calcolo: `${eur0(p.costiFissi)} − ${eur0(altri)} = ${eur0(p.costiFissiOperativi)}`,
      },
      {
        testo: "Fatturato di pareggio sul MOL = costi fissi / margine %",
        calcolo: `${eur0(p.costiFissiOperativi)} / ${pct1(mdc)} = ${eur0(bep)}`,
      },
      {
        testo: "Margine di sicurezza = (ricavi − pareggio) / ricavi",
        calcolo: `(${eur0(rev)} − ${eur0(bep)}) / ${eur0(rev)} = ${pct1(margSicPct)}`,
      },
    ],
  };
}

/** La tabella sotto il mini grafico: ricavi, margine di contribuzione %, pareggio sul
 *  MOL, margine di sicurezza in % e in €. Un anno `nd` porta la nota su ogni cella,
 *  invece di una colonna di trattini senza spiegazione. */
export function rowsPareggio(years: ForecastPreviewYear[]): PreviewRow[] {
  const letti = years.map((y) => leggiPareggio(y.details?.pareggio));
  const cell = (f: (p: PareggioNumeri) => number | null, pct = false) =>
    letti.map((p) => {
      const nd = !p || p.fatturatoPareggio === null;
      if (nd) return { value: null, note: ND_NOTE };
      return pct ? { value: null, pct: f(p!) } : { value: f(p!) };
    });
  const none = { value: null };
  return [
    {
      key: "ricavi", label: "Ricavi del piano", kind: "sub", base: none,
      years: years.map((y) => ({ value: ricaviOf(y) })),
    },
    { key: "mdc", label: "Margine di contribuzione", kind: "sub", base: none, years: cell((p) => p.margineContribuzionePct, true) },
    { key: "pareggio", label: "Pareggio sul MOL", kind: "kpi", base: none, years: cell((p) => p.fatturatoPareggio) },
    { key: "margine-pct", label: "margine di sicurezza %", kind: "sub", base: none, years: cell((p) => p.margineSicurezzaPct, true) },
    { key: "margine", label: "margine di sicurezza €", kind: "sub", base: none, years: cell((p) => p.margineSicurezza) },
  ];
}
