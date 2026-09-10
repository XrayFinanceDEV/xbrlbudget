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

import type { BudgetAssumptions, BudgetAssumptionsCreate, Pregresso, PregressoKey, PregressoPlan } from "@/types/api";
import { isPlanEmpty, normalizePregresso } from "@/lib/budget-pregresso-circolante";

export type AssumptionsMap = Record<number, Partial<BudgetAssumptionsCreate>>;

/**
 * Gli interruttori che il wizard scrive su TUTTI gli anni con `updateAll`.
 * Un'unione sola: la funzione che li legge e' una sola (`boolAssumption`), e
 * prima di questo fix ne esistevano due copie verbatim — in
 * `budget-circolante-step.ts` e in `budget-pregresso-step.ts` — che
 * differivano solo per quali campi accettavano.
 */
export type BoolAssumptionField =
  | "previdenza_scales_with_personnel"
  | "tfr_accrual_suspended"
  | "cash_sweep_enabled"
  | "overdraft_allowed";

/**
 * Un interruttore e' un'ipotesi PER ANNO — il motore la applica riga per
 * riga — ma il checkbox e' uno solo: si mostra quello del primo anno
 * previsto (stesso criterio di `fixedShareOf` in budget-costi-step.ts).
 * Assente ⇒ `false`, il default del motore (database/models.py).
 */
export function boolAssumption(
  assumptions: AssumptionsMap,
  forecastYears: number[],
  field: BoolAssumptionField,
): boolean {
  return Boolean(assumptions[forecastYears[0]]?.[field]);
}

/** Gli anni previsti: `numYears` anni **dopo** l'anno base. */
export function forecastYearsFor(baseYear: number, numYears: number): number[] {
  const n = Math.max(0, Math.floor(numYears) || 0);
  return Array.from({ length: n }, (_, i) => baseYear + i + 1);
}

/**
 * La mappa idratata delle ipotesi salvate, campo per campo: da
 * `BudgetAssumptions` (quello che il server restituisce) a
 * `Partial<BudgetAssumptionsCreate>` (quello che il bulk endpoint rimanda
 * indietro), con `scenario_id` riscritto sullo scenario corrente.
 *
 * Funzione pura e senza rete — per questo è il posto più pericoloso del
 * lotto: un campo dimenticato qui sparisce **in silenzio** al primo «Salva e
 * Calcola Previsionale», perché il bulk è delete-all + reinsert e la riga
 * rimandata indietro sostituisce quella salvata. `budget-horizon.test.ts`
 * congela l'elenco delle chiavi prodotte apposta per questo: se un campo
 * sparisce (o se ne aggiunge uno senza aggiornare il test nello stesso
 * commit), la suite fallisce invece di lasciarlo sparire senza errore.
 *
 * Estratta verbatim da `use-scenario-assumptions.ts` (Task 7); i commenti
 * storici sui singoli campi restano qui, dove ora vive la logica che
 * spiegano.
 */
export function hydrateAssumptions(
  rows: BudgetAssumptions[],
  scenarioId: number
): AssumptionsMap {
  const out: AssumptionsMap = {};
  rows.forEach((a) => {
    out[a.forecast_year] = {
      scenario_id: scenarioId,
      forecast_year: a.forecast_year,
      revenue_growth_pct: a.revenue_growth_pct,
      other_revenue_growth_pct: a.other_revenue_growth_pct,
      variable_materials_growth_pct: a.variable_materials_growth_pct,
      fixed_materials_growth_pct: a.fixed_materials_growth_pct,
      variable_services_growth_pct: a.variable_services_growth_pct,
      fixed_services_growth_pct: a.fixed_services_growth_pct,
      rent_growth_pct: a.rent_growth_pct,
      personnel_growth_pct: a.personnel_growth_pct,
      other_costs_growth_pct: a.other_costs_growth_pct,
      investments: a.investments,
      intangible_investments: a.intangible_investments,
      tangible_investments: a.tangible_investments,
      asset_disposal_nbv: a.asset_disposal_nbv,
      asset_disposal_proceeds: a.asset_disposal_proceeds,
      dso_days: a.dso_days,
      dio_days: a.dio_days,
      dpo_days: a.dpo_days,
      existing_debt_repayment_years: a.existing_debt_repayment_years,
      altri_finanz_repayment_years: a.altri_finanz_repayment_years,
      cash_sweep_enabled: a.cash_sweep_enabled ?? false,
      cash_sweep_min_cash: a.cash_sweep_min_cash,
      overdraft_allowed: a.overdraft_allowed ?? false,
      overdraft_limit: a.overdraft_limit ?? null,
      tfr_accrual_suspended: a.tfr_accrual_suspended ?? false,
      previdenza_scales_with_personnel: a.previdenza_scales_with_personnel ?? false,
      receivables_short_growth_pct: a.receivables_short_growth_pct,
      receivables_long_growth_pct: a.receivables_long_growth_pct,
      payables_short_growth_pct: a.payables_short_growth_pct,
      tax_rate: a.tax_rate,
      tax_advances_paid: a.tax_advances_paid ?? 0,
      tax_temporary_differences: a.tax_temporary_differences ?? null,
      fixed_materials_percentage: a.fixed_materials_percentage,
      fixed_services_percentage: a.fixed_services_percentage,
      depreciation_rate: a.depreciation_rate,
      depreciation_rate_intangible: a.depreciation_rate_intangible,
      financing_amount: a.financing_amount,
      financing_duration_years: a.financing_duration_years,
      financing_interest_rate: a.financing_interest_rate,
      financing_loans: a.financing_loans ?? null,
      // `normalizePregresso`, non `a.pregresso ?? null`: la colonna torna dal
      // server con i `Decimal` serializzati come stringa (rilievo 5, giro di
      // correzione 1 — vedi il commento su `normalizePregresso`), e un
      // passaggio diretto li porterebbe cosi' nella mappa idratata.
      pregresso: normalizePregresso(a.pregresso),
      sp01_growth_pct: a.sp01_growth_pct,
      sp04_growth_pct: a.sp04_growth_pct,
      sp06e_growth_pct: a.sp06e_growth_pct,
      sp06f_growth_pct: a.sp06f_growth_pct,
      sp08_growth_pct: a.sp08_growth_pct,
      sp10_growth_pct: a.sp10_growth_pct,
      sp14_growth_pct: a.sp14_growth_pct,
      sp16e_growth_pct: a.sp16e_growth_pct,
      sp16f_growth_pct: a.sp16f_growth_pct,
      sp16g_growth_pct: a.sp16g_growth_pct,
      sp17d_growth_pct: a.sp17d_growth_pct,
      sp17e_growth_pct: a.sp17e_growth_pct,
      sp17f_growth_pct: a.sp17f_growth_pct,
      sp17g_growth_pct: a.sp17g_growth_pct,
      sp18_growth_pct: a.sp18_growth_pct,
      sp_indexing: a.sp_indexing ?? null,
      sp_overrides: a.sp_overrides ?? null,
      ce01_override: a.ce01_override,
      ce05_override: a.ce05_override,
      ce06_override: a.ce06_override,
      ce07_override: a.ce07_override,
      ce08_override: a.ce08_override,
      ce02_override: a.ce02_override,
      ce03_override: a.ce03_override,
      ce03a_override: a.ce03a_override,
      ce10_override: a.ce10_override,
      ce11_override: a.ce11_override,
      ce13_override: a.ce13_override,
      ce14_override: a.ce14_override,
      ce15_override: a.ce15_override,
      ce16_override: a.ce16_override,
      ce17_override: a.ce17_override,
      ce18_override: a.ce18_override,
      ce19_override: a.ce19_override,
      // Overrides editable ONLY on /forecast/income — must be hydrated here too,
      // otherwise "Salva e Calcola" (server-side delete+reinsert) drops them and
      // the user's manual P&L edits are wiped, contradicting the documented
      // "overrides survive the save" guarantee.
      ce04_override: a.ce04_override,
      ce08a_override: a.ce08a_override,
      ce08b_override: a.ce08b_override,
      ce08c_override: a.ce08c_override,
      ce08d_override: a.ce08d_override,
      ce09_override: a.ce09_override,
      ce09a_override: a.ce09a_override,
      ce09b_override: a.ce09b_override,
      ce09c_override: a.ce09c_override,
      ce09d_override: a.ce09d_override,
      ce11b_override: a.ce11b_override,
      ce12_override: a.ce12_override,
      ce17a_override: a.ce17a_override,
      ce17b_override: a.ce17b_override,
      ce20_override: a.ce20_override,
    };
  });
  return out;
}

/**
 * L'orizzonte di piano dalle ipotesi salvate: l'ULTIMO anno salvato meno
 * l'anno base, non il numero di righe. Su uno scenario le cui ipotesi non
 * partono da `base_year + 1` — la disallineatura descritta nel commento su
 * `baseYear` in `use-scenario-assumptions.ts` — contare le righe accorcia il
 * piano, e il salvataggio successivo butterebbe via l'ultimo anno.
 *
 * Senza righe salvate resta il default di prodotto, tre anni. Il minimo
 * restituito è 1: anche una riga degenere il cui `forecast_year` coincide con
 * l'anno base (che non dovrebbe succedere, ma non deve produrre un piano a
 * zero anni) risale a 1.
 */
export function horizonFromSavedRows(rows: BudgetAssumptions[], baseYear: number): number {
  if (rows.length === 0) return 3;
  const ultimoSalvato = rows.reduce((max, a) => Math.max(max, a.forecast_year), baseYear);
  return Math.max(1, ultimoSalvato - baseYear);
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
    overdraft_allowed: false,
    overdraft_limit: null,
    tfr_accrual_suspended: false,
    previdenza_scales_with_personnel: false,
    tax_rate: 27.9,
    tax_advances_paid: 0,
    tax_temporary_differences: null,
    // 40 e' il default del motore e della colonna (backend/app/schemas/budget.py,
    // database/models.py). Uno 0 scritto qui BATTE quel default — non lo integra —
    // e apriva i Costi di ogni scenario nuovo con lo slider a 0 % e le due righe
    // «parte fissa» gia' spente.
    fixed_materials_percentage: 40,
    fixed_services_percentage: 40,
    depreciation_rate: 20,
    depreciation_rate_intangible: 20,
    financing_amount: 0,
    financing_duration_years: 5,
    financing_interest_rate: 3,
    financing_loans: null,
    pregresso: null,
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

/**
 * Le righe da mandare a `PUT /scenarios/{id}/assumptions` — l'esatto inverso
 * di `hydrateAssumptions`, e altrettanto pericoloso: il bulk è **delete-all +
 * reinsert**, quindi una chiave che non parte da qui non viene «lasciata com'è
 * sul server», viene **cancellata**. Un campo perso qui azzera un'ipotesi
 * salvata senza un solo errore, con un toast verde sopra.
 *
 * Sta in `lib/` e non nel `useMemo` di `BudgetWizard` proprio per questo: un
 * componente non è collaudabile in questo repo (nessun jsdom, e non va
 * aggiunto), e `budget-horizon.test.ts` congela qui l'elenco delle chiavi
 * prodotte, lo stesso di `hydrateAssumptions`. Ridurre lo spread a due campi
 * — la mutazione che era passata a suite verde — ora fa fallire la suite.
 *
 * Si mandano solo gli anni che hanno un'ipotesi: un anno senza riga non è un
 * anno a zero, è un anno di cui non si sa nulla. `scenario_id` e
 * `forecast_year` sono riscritti sullo scenario e sull'anno correnti, perché
 * la mappa può portarsi dietro quelli di un'idratazione precedente.
 */
export function assumptionRowsForSave(
  assumptions: AssumptionsMap,
  forecastYears: number[],
  scenarioId: number
): Record<string, unknown>[] {
  return forecastYears
    .filter((year) => assumptions[year])
    .map((year) => ({ ...assumptions[year], scenario_id: scenarioId, forecast_year: year }));
}

/**
 * La chiosa accanto all'anno base, o `null` se non c'è niente di vero da dire.
 *
 * Era una stringa fissa — «(ultimo anno disponibile)» — stampata anche quando
 * l'azienda aveva anni più recenti: uno scenario con base 2025 su un'azienda
 * col 2026 importato affermava il contrario di ciò che si legge in database.
 * L'anno base decide da quali numeri parte l'intero piano, ed è proprio il tipo
 * di frase che convince chi legge a non controllare.
 *
 * `years` viene da `GET /companies/{id}/years`, che elenca gli anni di **ogni**
 * `FinancialYear`, i periodi parziali compresi: in una pratica infrannuale il
 * 2026 c'è come bilancio di verifica a 9 mesi, e non può fare da anno base
 * finché non viene promosso. Per questo la seconda chiosa parla di **archivio**
 * e non di disponibilità: dice che il piano non parte dai dati più recenti —
 * che è vero e utile in entrambi i casi — senza promettere che quell'anno sia
 * usabile come base.
 */
export function baseYearNote(baseYear: number, years: number[]): string | null {
  if (years.length === 0) return null;
  const ultimo = Math.max(...years);
  if (ultimo === baseYear) return "ultimo anno disponibile";
  // Anno base oltre lo storico: startup, o un anno cancellato dopo la
  // creazione dello scenario. Nessuna delle due chiose sarebbe utile.
  if (ultimo < baseYear) return null;
  return `in archivio fino al ${ultimo}`;
}

// ── Il piano di pregresso (Task 7, giro di correzione 1) ────────────────────
// Vive nelle ipotesi del PRIMO anno di piano (spec §3.5): il motore rifiuta
// un pregresso scritto altrove con "pregresso is allowed only in the first
// forecast year". Le due funzioni sotto sono le sole vie di scrittura di
// quel campo che questo modulo espone — DOVE il piano finisce, e a QUALE
// lunghezza — cosi' la regola sta in `lib/`, provata, invece di restare un
// effetto collaterale del fatto che il componente chiamante passi sempre
// `firstYear` (conflitto A della revisione del task 7).

const PREGRESSO_KEYS: readonly PregressoKey[] = [
  "crediti_commerciali", "debiti_fornitori", "debiti_tributari", "debiti_previdenziali", "altri_debiti",
];

/**
 * Scrive il piano di pregresso nella riga del PRIMO anno di piano. Un
 * orizzonte vuoto (nessun anno previsto) non scrive nulla e restituisce la
 * mappa ricevuta: non c'e' una "prima riga" su cui posarlo.
 *
 * E' anche il setter TIPIZZATO del conflitto B della revisione: `update`
 * (`StepProps`) e' tornato al suo tipo scalare, e questa e' l'unica via per
 * cui il pregresso — un oggetto, non uno scalare — entra nella mappa delle
 * ipotesi.
 */
export function withPregresso(
  assumptions: AssumptionsMap,
  forecastYears: number[],
  next: Pregresso | null,
): AssumptionsMap {
  const firstYear = forecastYears[0];
  if (firstYear === undefined) return assumptions;
  return { ...assumptions, [firstYear]: { ...assumptions[firstYear], pregresso: next } };
}

/**
 * Accorcia `amounts`/`writeoff` di ogni saldo del pregresso alla lunghezza
 * dell'orizzonte (rilievo 3, giro di correzione 1): un piano piu' lungo
 * dell'orizzonte di piano non ha colonne per i suoi anni in eccesso — non e'
 * raggiungibile ne' correggibile dalla tabella — e il motore lo rifiuta
 * intero (`validatePregresso` lo segnala, ma senza quelle colonne l'utente
 * non puo' rimediare). Puo' succedere sia scorciando l'orizzonte dopo aver
 * toccato un anno lontano, sia idratando ipotesi salvate quando il bulk ha
 * gia' persistito un piano bloccato (il bulk salva anche a generazione
 * fallita).
 *
 * Gli importi tagliati diventano residuo OLTRE l'orizzonte, che e' il loro
 * significato quando non sono piu' scadenziati: non richiede una somma
 * esplicita, la sola rimozione dall'array basta, perche' `residualAfter`
 * somma solo gli anni ancora presenti. Dopo il taglio vale la regola della
 * cella svuotata (rilievo 2): un piano tutto a zero torna `null`.
 *
 * Restituisce l'oggetto RICEVUTO, stessa identita', quando non c'e' nulla da
 * accorciare (`pregresso` nullo compreso): e' l'invariante di CLAUDE.md che
 * impedisce all'effetto chiamante di ri-innescarsi da solo.
 */
export function trimPregressoToHorizon(
  pregresso: Pregresso | null | undefined,
  horizon: number,
): Pregresso | null | undefined {
  if (!pregresso) return pregresso;
  let out = pregresso;
  for (const key of PREGRESSO_KEYS) {
    const plan = pregresso[key] as PregressoPlan | null | undefined;
    if (!plan) continue;
    const amountsOver = plan.amounts.length > horizon;
    const writeoffOver = (plan.writeoff ?? []).length > horizon;
    if (!amountsOver && !writeoffOver) continue;
    const trimmed: PregressoPlan = {
      ...plan,
      amounts: amountsOver ? plan.amounts.slice(0, horizon) : plan.amounts,
      writeoff: writeoffOver ? (plan.writeoff ?? []).slice(0, horizon) : plan.writeoff,
    };
    out = { ...out, [key]: isPlanEmpty(trimmed) ? null : trimmed };
  }
  return out;
}

/**
 * Applica `trimPregressoToHorizon` al piano vivo — quello del PRIMO anno di
 * piano — dentro la mappa delle ipotesi. Va richiamata sia al cambio di
 * orizzonte sia all'idratazione di righe salvate (rilievo 3): due punti
 * diversi, la stessa funzione, cosi' non possono divergere su come si taglia
 * un piano.
 *
 * Stessa identita' della mappa ricevuta quando non c'e' nulla da accorciare
 * — compreso un orizzonte senza un primo anno.
 */
export function withPregressoTrimmedToHorizon(
  assumptions: AssumptionsMap,
  forecastYears: number[],
): AssumptionsMap {
  const firstYear = forecastYears[0];
  if (firstYear === undefined) return assumptions;
  const row = assumptions[firstYear];
  const plan = row?.pregresso as Pregresso | null | undefined;
  const trimmed = trimPregressoToHorizon(plan, forecastYears.length);
  if (trimmed === plan) return assumptions;
  return { ...assumptions, [firstYear]: { ...row, pregresso: trimmed } };
}
