/**
 * Lo stato patrimoniale proiettato della tab Proiezione, letto dal motore.
 *
 * Qui non si proietta nulla. Rotazioni, quote residue di ammortamento, imposte,
 * rimborso del debito e plug di cassa vivono in un solo posto —
 * `calculations/intra_year_engine.py` — e questo modulo si limita a dare alle
 * voci del Confronto i valori che quel motore ha prodotto e persistito.
 *
 * Fino al 2026-09-02 esisteva qui un secondo motore in TypeScript
 * (`computeProjectedBS`) che ricalcolava la proiezione lato client. Aveva
 * divergito da quello Python su quattro punti — plug negativo, base dei debiti
 * a breve, quote residue, granularità — così la tab Proiezione e le tab
 * Indicatori e Stampa mostravano tre bilanci diversi della stessa azienda
 * (#22, #39, #40, #41). Un secondo motore ri-diverge alla prima modifica del
 * primo: la regola è che l'aritmetica che ricapitola ciò che è già a schermo
 * sta nel client, e tutto ciò che DERIVA uno stato patrimoniale da un conto
 * economico sta nel motore Python.
 *
 * Modulo puro: nessun import da `app/` o `components/`, così resta provabile in
 * `environment: node`.
 */

import type { IntraYearComparisonItem } from "@/types/api";

/**
 * Le voci di SP proiettate, prese dal forecast che ha calcolato il motore.
 *
 * `forecastBS` è `analysis.forecast_years[0].balance_sheet`, cioè il
 * `ForecastYear` che `IntraYearEngine.generate_projection` ha persistito: la
 * stessa fonte che le tab Indicatori e Stampa leggono da sempre. Restituisce
 * `null` quando quel forecast non c'è, perché una proiezione non generata non
 * si dipinge: `annualized_value` sarebbe un numero che nessun motore ha
 * prodotto.
 */
export function projectedItemsFromForecast(
  balanceItems: IntraYearComparisonItem[],
  forecastBS: Record<string, number> | null | undefined,
): IntraYearComparisonItem[] | null {
  if (!forecastBS || Object.keys(forecastBS).length === 0) return null;
  return balanceItems.map((item) => ({
    ...item,
    // Il motore proietta anche i sotto-campi; se una voce non arriva la si
    // porta avanti dal parziale, invece di mostrarla a zero.
    annualized_value: Math.round(forecastBS[item.code] ?? item.partial_value),
  }));
}
