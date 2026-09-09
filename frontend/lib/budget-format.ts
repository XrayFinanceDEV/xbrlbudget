/**
 * La casa unica degli helper numerici e di formattazione del percorso ipotesi.
 *
 * I 34 moduli `lib/budget-*` sono nati in parallelo, e ognuno si era riscritto
 * il proprio `num`/`numOrNull`/`euro`/`pct1`/`pctOf`: otto copie di `num` in
 * **due** varianti che non coincidevano, sei di `euro`, due di `pctOf` con
 * firme diverse. Due copie che divergono su un caso limite fanno mostrare due
 * numeri diversi per la stessa voce in due punti dello stesso passo, e nessun
 * controllo se ne accorge. Da qui in poi si importa da questo modulo.
 *
 * Modulo puro: nessun import da `app/` o da `components/`.
 */
import { formatCurrency, formatNumber, formatPercentage } from "@/lib/formatters";

/**
 * Il numero dietro un valore che arriva dall'API (`Decimal` serializzato come
 * numero o come stringa), oppure `0`.
 *
 * Delle due varianti che il lotto aveva prodotto vince questa, con la guardia
 * `Number.isFinite`: l'altra — `typeof v === "number" ? v : parseFloat(...) || 0`
 * — restituiva `NaN` per un `NaN` gia' numerico e `Infinity` per un infinito,
 * cioe' propagava il guasto dentro somme e percentuali invece di fermarlo.
 * Sul resto dei casi (stringa, `null`, `undefined`, testo non numerico) le due
 * varianti coincidono, quindi nessun chiamante cambia comportamento su un dato
 * reale.
 */
export const num = (v: unknown): number => {
  const n = typeof v === "number" ? v : parseFloat(String(v ?? ""));
  return Number.isFinite(n) ? n : 0;
};

/** `null`/assente restano `null`: uno zero vero e uno zero di ripiego non sono
 *  la stessa cosa (`lib/budget-costi-step.ts`, dove la regola e' nata). */
export const numOrNull = (v: unknown): number | null => {
  if (v === null || v === undefined || v === "") return null;
  const n = typeof v === "number" ? v : parseFloat(String(v));
  return Number.isFinite(n) ? n : null;
};

/** Importo in euro, o il trattino dell'assenza. */
export const euro = (v: number | null): string => (v === null ? "—" : formatCurrency(v));

/**
 * Percentuale a UN decimale, la sola precisione del wizard (`describeCell`
 * usava il default a due e nello stesso pannello si leggeva «40,00%» sopra e
 * «60,5%» due centimetri sotto).
 *
 * `formatPercentage` vuole una frazione: le percentuali del progetto sono
 * assolute (25,5 = 25,5%), quindi si divide per 100 qui, una volta sola.
 */
export const pct1 = (v: number | null): string => (v === null ? "—" : formatPercentage(v / 100, 1));

/**
 * Giorni (DSO/DIO/DPO applicati) a UN decimale, formato italiano. Il valore
 * che il motore ha applicato arriva grezzo nei `details` (`compute_forecast`
 * li lascia cosi' apposta, `calculations/forecast_engine.py:536-546`): senza
 * questo formattatore lo si mostra a 14 cifre decimali. Diverso dal
 * segnaposto «auto: N» di `computeAutoDays` (`lib/budget-turnover.ts`), che
 * chiude con `Math.round()` — quello e' un suggerimento da digitare, questo
 * e' il valore applicato, e arrotondarlo all'intero direbbe che la
 * rotazione usata e' un'altra.
 */
export const days1 = (v: number | null): string => (v === null ? "—" : formatNumber(v, 1));

/** L'incidenza di `v` su `den`, in percentuale assoluta. Denominatore nullo,
 *  assente o zero ⇒ `null`: non c'e' incidenza da dichiarare, e non e' zero. */
export const pctOf = (v: number | null, den: number | null | undefined): number | null =>
  v === null || den === null || den === undefined || den === 0 ? null : (v / den) * 100;
