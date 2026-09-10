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
  hydrateAssumptions,
  horizonFromSavedRows,
  type AssumptionsMap,
} from "@/lib/budget-horizon";
import type { HistoricalData } from "@/lib/budget-trend";
import type {
  BudgetScenario,
  FinancingLoanInput,
  SpIndexingDriver,
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
  updateAssumption: (year: number, field: string, value: number | boolean | null | object) => void;
  updateAll: (field: string, value: number | boolean | null) => void; // tutti i forecastYears
  updateFinancingLoans: (year: number, loans: FinancingLoanInput[]) => void;
  updateTemporaryDifferences: (year: number, lines: TemporaryDifferenceInput[]) => void;
  /** Aggancia una voce minore dello SP a un driver di volume su tutti gli anni
   *  di piano; `null` la slega. */
  updateSpIndexing: (code: string, driver: SpIndexingDriver | null) => void;
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
      // La mappa idratata e l'orizzonte dalle righe salvate sono due funzioni
      // pure senza rete, in `lib/budget-horizon.ts` con la loro suite: un
      // campo perso da `hydrateAssumptions` o un orizzonte contato per righe
      // invece che per distanza da `horizonFromSavedRows` sbaglierebbero in
      // silenzio, senza che nulla qui se ne accorga.
      const assumptionsMap = hydrateAssumptions(data, scenarioId);
      const existingYears = new Set<number>(data.map((a) => a.forecast_year));
      // I default degli anni scoperti vanno messi QUI: questo `setAssumptions`
      // sostituisce la mappa che l'effetto dei default aveva gia' riempito al
      // mount, e senza riunirli il salvataggio manderebbe zero righe.
      const nextNumYears = horizonFromSavedRows(data, baseYear);
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

  // `object` per le ipotesi strutturate scritte per anno (il piano `pregresso`
  // del passo 6): la mappa e' `Partial<BudgetAssumptionsCreate>`, che quel
  // campo lo dichiara gia'.
  const updateAssumption = useCallback((year: number, field: string, value: number | boolean | null | object) => {
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

  /**
   * L'aggancio di una voce minore dello SP a un driver di volume (Task 15).
   * Scrive TUTTI gli anni di piano: il modello e' per anno — il motore legge
   * `sp_indexing` riga per riga — ma la scelta e' una sola, come per gli
   * interruttori e come per la quota fissa dei costi. Passare `null` toglie
   * la chiave invece di lasciarla a un valore vuoto: al motore una chiave
   * assente significa «costante», che e' esattamente cio' che l'utente ha
   * appena chiesto.
   */
  const updateSpIndexing = useCallback((code: string, driver: SpIndexingDriver | null) => {
    setAssumptions((prev) => {
      const next = { ...prev };
      for (const y of forecastYears) {
        const { [code]: _tolto, ...resto } = next[y]?.sp_indexing ?? {};
        const mappa = driver ? { ...resto, [code]: driver } : resto;
        next[y] = {
          ...(next[y] ?? {}),
          sp_indexing: Object.keys(mappa).length > 0 ? mappa : null,
        };
      }
      return next;
    });
  }, [forecastYears]);

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
    updateSpIndexing,
  };
}
