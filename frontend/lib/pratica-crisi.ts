import type { ColonnaCrisi, LivelloRatingCrisi, RatingCrisi } from "@/types/api";
import type { IndicatorSet } from "@/lib/pratica-indicators";

/**
 * Gli indicatori della crisi d'impresa si calcolano sul server
 * (`calculations/crisi_impresa.py`, `GET .../infrannuale/crisi`): lo leggono
 * la tab Indicatori, la Stampa e il report PDF intermedio. Qui resta solo la
 * traduzione della risposta in ciò che le due viste rendono.
 */

/** Classi Tailwind del codice di rating, per livello di rischio. */
export const RATING_COLOR: Record<LivelloRatingCrisi, string> = {
  verde: "text-green-600 dark:text-green-400",
  giallo: "text-yellow-600 dark:text-yellow-400",
  arancio: "text-orange-600 dark:text-orange-400",
  rosso: "text-red-600 dark:text-red-400",
};

export type VistaColonnaCrisi = {
  indicatori: IndicatorSet;
  punteggi: Record<string, number>;
  rating: RatingCrisi;
};

/**
 * La colonna come la rende una vista, con il rating del numero di segnali
 * extracontabili che la pagina ha IN QUESTO MOMENTO — anche non ancora
 * salvati: il server manda il rating per ogni conteggio possibile, così le
 * bande restano in un posto solo e lo schermo reagisce a ogni casella.
 * Lo storico si chiede sempre con 0: i segnali sono del periodo in corso.
 */
export function vistaColonna(
  colonna: ColonnaCrisi | null,
  segnali: number,
): VistaColonnaCrisi | null {
  if (!colonna) return null;
  const ultimo = colonna.rating_per_segnali.length - 1;
  const indice = Math.max(0, Math.min(segnali, ultimo));
  return {
    indicatori: colonna.indicatori as unknown as IndicatorSet,
    punteggi: colonna.punteggi,
    rating: colonna.rating_per_segnali[indice],
  };
}
