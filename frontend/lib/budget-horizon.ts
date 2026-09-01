/**
 * Orizzonte di piano dello scenario budget: quali anni si prevedono, e quali
 * ipotesi esistono per ciascuno.
 *
 * Nasce da una trappola: nel form dello scenario il campo «Numero di anni da
 * prevedere» era un **display** dello stato salvato, non un input. L'effetto di
 * idratazione delle ipotesi aveva `forecastYears` fra le dipendenze e si
 * chiudeva con `setNumYears(data.length || 3)`: scrivere `numYears` faceva
 * ripartire l'effetto che riscriveva `numYears`, e il valore tornava indietro
 * dopo ~230 ms senza un errore. Il piano a 5 anni — la funzione che dà il nome
 * al prodotto — non era impostabile da nessuna schermata.
 *
 * La cura è separare le due cose: l'idratazione legge dal server e fissa
 * l'orizzonte **una volta**, il riempimento dei default reagisce all'orizzonte
 * senza mai toccarlo. Perché quel secondo effetto non si ri-inneschi da solo,
 * `withDefaultsForYears` restituisce la **stessa** mappa quando non manca
 * nulla: React esce dall'aggiornamento e l'effetto non riparte.
 *
 * Modulo puro: nessun import da `app/` o `components/`, così resta provabile in
 * `environment: node`.
 */

import type { BudgetAssumptionsCreate } from "@/types/api";

export type AssumptionsMap = Record<number, Partial<BudgetAssumptionsCreate>>;

/** Gli anni previsti: `numYears` anni **dopo** l'anno base. */
export function forecastYearsFor(baseYear: number, numYears: number): number[] {
  const n = Math.max(0, Math.floor(numYears) || 0);
  return Array.from({ length: n }, (_, i) => baseYear + i + 1);
}

/**
 * Riga di ipotesi neutra per un anno nuovo. I campi morti (`investments`,
 * `receivables_short/payables_short`) non si scrivono più, e gli override di CE
 * restano `NULL`: i valori assoluti del conto economico si impostano su
 * `/forecast/income`, non qui.
 *
 * `tax_rate` è **27,9** (IRES + IRAP), non il `24` di default dello schema
 * Pydantic: nessuna schermata manda 24.
 */
export function defaultAssumption(
  year: number,
  scenarioId?: number
): Partial<BudgetAssumptionsCreate> {
  return {
    ...(scenarioId === undefined ? {} : { scenario_id: scenarioId }),
    forecast_year: year,
    revenue_growth_pct: 0,
    other_revenue_growth_pct: 0,
    variable_materials_growth_pct: 0,
    fixed_materials_growth_pct: 0,
    variable_services_growth_pct: 0,
    fixed_services_growth_pct: 0,
    rent_growth_pct: 0,
    personnel_growth_pct: 0,
    other_costs_growth_pct: 0,
    intangible_investments: 0,
    tangible_investments: 0,
    asset_disposal_nbv: null,
    asset_disposal_proceeds: null,
    receivables_long_growth_pct: 0,
    dso_days: null,
    dio_days: null,
    dpo_days: null,
    existing_debt_repayment_years: null,
    altri_finanz_repayment_years: null,
    cash_sweep_enabled: false,
    cash_sweep_min_cash: null,
    tfr_accrual_suspended: false,
    previdenza_scales_with_personnel: false,
    tax_rate: 27.9,
    tax_advances_paid: 0,
    tax_temporary_differences: null,
    fixed_materials_percentage: 0,
    fixed_services_percentage: 0,
    depreciation_rate: 20,
    depreciation_rate_intangible: 20,
    financing_amount: 0,
    financing_duration_years: 5,
    financing_interest_rate: 3,
    financing_loans: null,
  };
}

/**
 * Completa la mappa delle ipotesi con un default per ogni anno previsto che non
 * ce l'ha già. Serve ad allungare l'orizzonte: il salvataggio manda solo gli
 * anni che hanno una riga (`forecastYears.filter((y) => assumptions[y])`),
 * quindi passare da 3 a 5 anni senza queste due righe salverebbe di nuovo tre
 * anni, in silenzio.
 *
 * Non rimuove nulla: gli anni finiti fuori orizzonte restano nella mappa —
 * chi torna da 5 a 3 e poi ci ripensa ritrova ciò che aveva scritto — perché a
 * filtrare è il salvataggio.
 *
 * Se non manca nessun anno restituisce la mappa **ricevuta**, identità
 * compresa: è quello che impedisce all'effetto chiamante di ri-innescarsi.
 */
export function withDefaultsForYears(
  current: AssumptionsMap,
  years: number[],
  scenarioId?: number
): AssumptionsMap {
  const missing = years.filter((year) => !current[year]);
  if (missing.length === 0) return current;

  const next: AssumptionsMap = { ...current };
  for (const year of missing) {
    next[year] = defaultAssumption(year, scenarioId);
  }
  return next;
}
