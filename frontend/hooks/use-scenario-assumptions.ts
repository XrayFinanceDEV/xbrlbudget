"use client";

/**
 * La mappa idratata delle ipotesi di uno scenario budget: stato, idratazione
 * dal server, orizzonte di piano e i callback di aggiornamento.
 *
 * Estratto verbatim da `ScenarioForm` in `app/budget/page.tsx` (ora
 * `ScenarioFormStartup`) perché il wizard a sette passi possa consumarla
 * senza duplicarla. I commenti storici restano qui — spiegano perché
 * l'idratazione fissa l'orizzonte UNA volta, perché il secondo effetto (i
 * default degli anni scoperti) non dipende mai da `forecastYears` in modo
 * che si ri-inneschi da solo, e perché l'orizzonte segue l'ULTIMO anno
 * salvato e non il numero di righe.
 */
import { useState, useEffect, useMemo, useCallback } from "react";
import { getBudgetAssumptions, getIncomeStatement, getBalanceSheet } from "@/lib/api";
import {
  baseYearNote,
  forecastYearsFor,
  withDefaultsForYears,
  type AssumptionsMap,
} from "@/lib/budget-horizon";
import type { HistoricalData } from "@/lib/budget-trend";
import type {
  BudgetScenario,
  FinancingLoanInput,
  TemporaryDifferenceInput,
} from "@/types/api";
import { toast } from "sonner";

export interface ScenarioAssumptionsState {
  baseYear: number;
  notaAnnoBase: string | null;
  numYears: number;
  setNumYears: (n: number) => void;
  forecastYears: number[];
  historicalYears: number[];
  historicalData: HistoricalData;
  assumptions: AssumptionsMap;
  setAssumptions: React.Dispatch<React.SetStateAction<AssumptionsMap>>;
  idratato: boolean;
  isNew: boolean; // isNew = nessuna ipotesi salvata
  updateAssumption: (year: number, field: string, value: number | boolean | null) => void;
  updateAll: (field: string, value: number | boolean | null) => void; // tutti i forecastYears
  updateFinancingLoans: (year: number, loans: FinancingLoanInput[]) => void;
  updateTemporaryDifferences: (year: number, lines: TemporaryDifferenceInput[]) => void;
}

export function useScenarioAssumptions({
  companyId,
  years,
  scenario,
}: {
  companyId: number;
  years: number[];
  scenario: BudgetScenario | null;
}): ScenarioAssumptionsState {
  const [numYears, setNumYears] = useState(3);
  const [historicalData, setHistoricalData] = useState<HistoricalData>({});

  // Base year: for an EXISTING scenario it is the stored base_year (the forecast
  // horizon must stay aligned with the saved assumption years); only for a NEW
  // scenario do we default to the latest available historical year. Using
  // Math.max(...years) unconditionally misaligned the horizon when a newer year was
  // imported/promoted after the scenario was created, dropping assumption rows on save.
  const baseYear = scenario?.base_year ?? Math.max(...years);
  // La chiosa e' calcolata, non scritta: su uno scenario che non parte
  // dall'ultimo anno importato dichiara qual e' l'ultimo, invece di affermare
  // il contrario di cio' che si legge in database.
  const notaAnnoBase = baseYearNote(baseYear, years);
  const scenarioId = scenario?.id ?? null;
  const forecastYears = useMemo(
    () => forecastYearsFor(baseYear, numYears),
    [numYears, baseYear]
  );

  // Load historical data for display
  useEffect(() => {
    const loadHistoricalData = async () => {
      const data: HistoricalData = {};
      for (const year of years) {
        try {
          const [income, balance] = await Promise.all([
            getIncomeStatement(companyId, year),
            getBalanceSheet(companyId, year),
          ]);
          data[year] = { income, balance };
        } catch (err) {
          console.error(`Error loading data for year ${year}:`, err);
        }
      }
      setHistoricalData(data);
    };
    loadHistoricalData();
  }, [companyId, years]);

  // Initialize assumptions with defaults or existing values
  const [assumptions, setAssumptions] = useState<AssumptionsMap>({});
  const [existingAssumptionYears, setExistingAssumptionYears] = useState<Set<number>>(new Set());
  // Finche' le ipotesi salvate non sono atterrate, la mappa in memoria non
  // rappresenta lo scenario: salvare in quella finestra manderebbe righe a zero
  // al posto di quelle vere, e il bulk cancella e reinserisce. Il salvataggio
  // resta chiuso, e resta chiuso anche se la lettura fallisce.
  const [idratato, setIdratato] = useState(false);

  // Idratazione: legge le ipotesi salvate e fissa l'orizzonte UNA volta sola.
  // NON dipende da `forecastYears`: dipenderci significa che scrivere
  // `numYears` fa ripartire l'effetto che riscrive `numYears`, ed e' la ragione
  // per cui il campo «Numero di anni da prevedere» tornava indietro da solo
  // dopo ~230 ms — il piano a 5 anni non era impostabile da nessuna schermata.
  useEffect(() => {
    if (scenarioId === null) {
      // Scenario nuovo: la mappa la riempie di default l'effetto qui sotto.
      setExistingAssumptionYears(new Set());
      setAssumptions({});
      setIdratato(true);
      return;
    }
    let annullato = false;
    setIdratato(false);
    getBudgetAssumptions(companyId, scenarioId).then((data) => {
      if (annullato) return;
      const assumptionsMap: AssumptionsMap = {};
      const existingYears = new Set<number>();
      data.forEach((a) => {
        existingYears.add(a.forecast_year);
        assumptionsMap[a.forecast_year] = {
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
      // L'orizzonte e' l'ULTIMO anno salvato, non il numero di righe: su uno
      // scenario le cui ipotesi non partono da `base_year + 1` — la
      // disallineatura descritta a :853-856 — contare le righe accorcia il
      // piano, e il salvataggio successivo butterebbe via l'ultimo anno.
      // I default degli anni scoperti vanno messi QUI: questo `setAssumptions`
      // sostituisce la mappa che l'effetto dei default aveva gia' riempito al
      // mount, e senza riunirli il salvataggio manderebbe zero righe.
      // Senza ipotesi salvate resta il default di prodotto, tre anni.
      const ultimoSalvato = data.reduce(
        (max, a) => Math.max(max, a.forecast_year),
        baseYear
      );
      const nextNumYears = data.length === 0
        ? 3
        : Math.max(1, ultimoSalvato - baseYear);
      setAssumptions(
        withDefaultsForYears(
          assumptionsMap,
          forecastYearsFor(baseYear, nextNumYears),
          scenarioId
        )
      );
      setExistingAssumptionYears(existingYears);
      setNumYears(nextNumYears);
      setIdratato(true);
    }).catch((err) => {
      if (annullato) return;
      // Senza questo ramo un 401 in rinnovo di token o un 500 lasciavano il
      // form fermo su un piano a zeri del tutto plausibile, e il salvataggio
      // successivo cancellava le ipotesi vere.
      // Messaggio fisso, non `getErrorMessage`: su un errore di rete quello
      // restituisce «Network Error», che non dice a chi legge ne' che cosa e'
      // andato storto ne' che il salvataggio ora e' chiuso. Il dettaglio
      // tecnico resta in console.
      console.error("Error loading assumptions:", err);
      toast.error(
        "Impossibile leggere le ipotesi salvate: il salvataggio resta chiuso finché non ricarichi la pagina"
      );
    });
    return () => {
      annullato = true;
    };
  }, [scenarioId, companyId, baseYear]);

  // I default degli anni previsti che non hanno ancora una riga: questo effetto
  // reagisce all'orizzonte senza mai toccarlo. E' cio' che rende il campo
  // «Numero di anni da prevedere» un input vero — portarlo a 5 aggiunge due
  // righe neutre, e il salvataggio (`forecastYears.filter((y) => assumptions[y])`)
  // le manda tutte e cinque.
  //
  // Non si ri-innesca da solo: `withDefaultsForYears` restituisce la mappa
  // ricevuta quando non manca nulla, quindi React esce dall'aggiornamento.
  useEffect(() => {
    if (!idratato) return;
    setAssumptions((prev) =>
      withDefaultsForYears(prev, forecastYears, scenarioId ?? undefined)
    );
  }, [idratato, forecastYears, scenarioId]);

  const updateAssumption = useCallback((year: number, field: string, value: number | boolean | null) => {
    setAssumptions((prev) => ({
      ...prev,
      [year]: {
        ...prev[year],
        [field]: value,
      },
    }));
  }, []);

  const updateFinancingLoans = useCallback((year: number, loans: FinancingLoanInput[]) => {
    setAssumptions((prev) => ({
      ...prev,
      [year]: {
        ...prev[year],
        financing_loans: loans.length > 0 ? loans : null,
      },
    }));
  }, []);

  const updateTemporaryDifferences = useCallback((year: number, lines: TemporaryDifferenceInput[]) => {
    setAssumptions((prev) => ({
      ...prev,
      [year]: {
        ...prev[year],
        tax_temporary_differences: lines.length > 0 ? lines : null,
      },
    }));
  }, []);

  const isNew = idratato && existingAssumptionYears.size === 0;
  const updateAll = useCallback((field: string, value: number | boolean | null) => {
    setAssumptions((prev) => {
      const next = { ...prev };
      for (const y of forecastYears) next[y] = { ...(next[y] ?? {}), [field]: value };
      return next;
    });
  }, [forecastYears]);

  const historicalYears = [...new Set(years)].filter((y) => y <= baseYear).sort((a, b) => a - b);

  return {
    baseYear,
    notaAnnoBase,
    numYears,
    setNumYears,
    forecastYears,
    historicalYears,
    historicalData,
    assumptions,
    setAssumptions,
    idratato,
    isNew,
    updateAssumption,
    updateAll,
    updateFinancingLoans,
    updateTemporaryDifferences,
  };
}
