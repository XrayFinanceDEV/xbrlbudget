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
import { useState, useEffect, useMemo, useCallback, useRef } from "react";
import { getBudgetAssumptions, getIncomeStatement, getBalanceSheet } from "@/lib/api";
import {
  baseYearNote,
  forecastYearsFor,
  withAliquotaProposta,
  withDefaultsForYears,
  withPregresso,
  withOtherLenders,
  withPregressoTrimmedToHorizon,
  withRevenueGrowth,
  hydrateAssumptions,
  horizonFromSavedRows,
  type AssumptionsMap,
} from "@/lib/budget-horizon";
import { applicaInflazioneAlleAuto, withInflazione } from "@/lib/budget-inflazione";
import { isScenarioPrecedente, migraScenario, type EsitoMigrazione } from "@/lib/budget-migrazione";
import type { HistoricalData } from "@/lib/budget-trend";
import type {
  BudgetScenario,
  FinancingLoanInput,
  OtherLenderInput,
  Pregresso,
  SpIndexingDriver,
  TemporaryDifferenceInput,
} from "@/types/api";
import { toast } from "sonner";
import { useAliquotaProposta } from "@/hooks/use-queries";

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
  // `string` (Task 14, revisione: `bank_lines_rule` e' la prima voce del
  // wizard che scrive un enum testuale — le altre sono tutte scalari
  // numeriche o booleane) e' allargato solo qui e nella firma gemella di
  // `StepProps.update` (components/budget/wizard/types.ts): a runtime la
  // funzione sotto scrive `[field]: value` senza controllare il tipo, quindi
  // nessun comportamento cambia per i chiamanti esistenti.
  updateAssumption: (year: number, field: string, value: number | boolean | string | null) => void;
  updateAll: (field: string, value: number | boolean | null) => void; // tutti i forecastYears
  updateFinancingLoans: (year: number, loans: FinancingLoanInput[]) => void;
  updateTemporaryDifferences: (year: number, lines: TemporaryDifferenceInput[]) => void;
  /** Aggancia una voce minore dello SP a un driver di volume su tutti gli anni
   *  di piano; `null` la slega. */
  updateSpIndexing: (code: string, driver: SpIndexingDriver | null) => void;
  /** Il setter tipizzato del piano di pregresso (conflitto B della revisione
   *  del task 7): scrive SEMPRE nel primo anno di piano (`withPregresso`,
   *  `lib/budget-horizon.ts`), mai su un anno scelto dal chiamante — `update`
   *  e' tornato scalare apposta, e non accetta piu' un oggetto. */
  updatePregresso: (next: Pregresso | null) => void;
  /** Gli altri finanziatori per anno (Task 8): scrive SEMPRE nel primo anno
   *  di piano, come `updatePregresso` — stessa regola, stessa forma. */
  updateOtherLenders: (next: OtherLenderInput[] | null) => void;
  /**
   * L'esito della migrazione in memoria di uno scenario salvato PRIMA del
   * giro di rilievi del 14/09 (Task 9, `lib/budget-migrazione.ts`), o `null`
   * se lo scenario non è precedente o la card è già stata chiusa. La mappa
   * migrata (sporca) è già quella idratata in `assumptions`: questo campo
   * serve solo a mostrare la card e i badge.
   */
  migrazione: EsitoMigrazione | null;
  /** Chiude la card di migrazione — chiamato dopo un salvataggio riuscito:
   *  la mappa migrata è ormai persistita, non più «sporca». */
  chiudiMigrazione: () => void;
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

  // Migrazione degli scenari salvati PRIMA del giro di rilievi del 14/09
  // (Task 9, spec §4.8). `migrazione` e' lo stato mostrato (card + badge);
  // i due ref sotto sono la parte che NON deve entrare in un array di
  // dipendenze — un oggetto letterale come `migrazione` ci rientrerebbe a
  // ogni render, e un ref coi dati grezzi da migrare evita di dover
  // ricalcolare `isScenarioPrecedente` nell'effetto che aspetta il bilancio
  // base.
  const [migrazione, setMigrazione] = useState<EsitoMigrazione | null>(null);
  // I dati grezzi di UNA migrazione in attesa del bilancio base, che arriva
  // da `historicalData` — un effetto separato, non ancora atterrato quando
  // l'idratazione stessa finisce. `null` quando non c'e' nulla in attesa.
  const pendingMigrazione = useRef<{
    scenarioId: number;
    map: AssumptionsMap;
    forecastYears: number[];
    baseYear: number;
  } | null>(null);
  // L'id dello scenario per cui la migrazione (o la sua assenza) e' gia'
  // stata decisa: impedisce all'effetto sotto di ripartire da solo quando
  // `historicalData` si aggiorna per un motivo che non c'entra (es. un altro
  // anno storico che finisce di caricare).
  const migratoPer = useRef<number | null>(null);

  // Idratazione: legge le ipotesi salvate e fissa l'orizzonte UNA volta sola.
  // NON dipende da `forecastYears`: dipenderci significa che scrivere
  // `numYears` fa ripartire l'effetto che riscrive `numYears`, ed e' la ragione
  // per cui il campo «Numero di anni da prevedere» tornava indietro da solo
  // dopo ~230 ms — il piano a 5 anni non era impostabile da nessuna schermata.
  useEffect(() => {
    if (scenarioId === null) {
      // Scenario nuovo: la mappa la riempie di default l'effetto qui sotto.
      // Non c'e' nulla da migrare — `defaultAssumption` scrive gia'
      // `inflation_pct: 2`, la firma di uno scenario nato dopo questo lotto.
      pendingMigrazione.current = null;
      migratoPer.current = null;
      setMigrazione(null);
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
      const nextForecastYears = forecastYearsFor(baseYear, nextNumYears);
      // Uno scenario salvato PRIMA del giro di rilievi del 14/09 (Task 9,
      // spec §4.8): la firma e' l'inflazione assente sul primo anno. La
      // migrazione vera (`migraScenario`) ha bisogno del bilancio base, che
      // arriva da `historicalData` — un effetto separato, quasi certamente
      // non ancora atterrato in questo istante. Si registra qui SOLO
      // l'intenzione (dati grezzi in un ref); l'effetto sotto la esegue
      // appena il bilancio c'e', una volta sola per scenario.
      if (isScenarioPrecedente(assumptionsMap, nextForecastYears)) {
        pendingMigrazione.current = { scenarioId, map: assumptionsMap, forecastYears: nextForecastYears, baseYear };
        migratoPer.current = null;
        // Provvisorio: la card resta chiusa finche' l'effetto sotto non
        // produce l'esito vero, cosi' non si mostra la migrazione di uno
        // scenario diverso mentre se ne apre uno nuovo.
        setMigrazione(null);
      } else {
        pendingMigrazione.current = null;
        migratoPer.current = scenarioId;
        setMigrazione(null);
      }
      // Il bulk salva le ipotesi anche a generazione fallita: un piano di
      // pregresso piu' lungo dell'orizzonte puo' arrivare gia' cosi' dal
      // server. Si accorcia qui, PRIMA del primo render, o la tabella nasce
      // gia' bloccata (rilievo 3 della revisione del task 7). Se lo scenario
      // e' precedente, questa e' solo la mappa PROVVISORIA (non migrata):
      // l'effetto sotto la sostituisce con `esito.map` appena puo' girare.
      setAssumptions(
        withPregressoTrimmedToHorizon(
          withDefaultsForYears(assumptionsMap, nextForecastYears, scenarioId),
          nextForecastYears
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
  // Non si ri-innesca da solo: `withDefaultsForYears` (e, in coda,
  // `withPregressoTrimmedToHorizon`) restituiscono la mappa ricevuta quando
  // non c'e' nulla da aggiungere o accorciare, quindi React esce
  // dall'aggiornamento — stesso invariante di CLAUDE.md sulle due funzioni.
  //
  // L'accorciamento del pregresso vive anche qui, non solo all'idratazione
  // (rilievo 3): l'utente puo' toccare un anno lontano e poi riportare
  // l'orizzonte indietro nella STESSA sessione, senza un giro sul server in
  // mezzo.
  useEffect(() => {
    if (!idratato) return;
    setAssumptions((prev) =>
      applicaInflazioneAlleAuto(
        withPregressoTrimmedToHorizon(
          withDefaultsForYears(prev, forecastYears, scenarioId ?? undefined),
          forecastYears
        ),
        forecastYears
      )
    );
  }, [idratato, forecastYears, scenarioId]);

  // Esegue la migrazione VERA (Task 9, spec §4.8) appena il bilancio base e'
  // arrivato in `historicalData` — un effetto separato da quello di
  // idratazione, che puo' atterrare dopo. Il cancello e' `migratoPer.current`
  // (l'id dello scenario gia' deciso), non `historicalData` in se': quello
  // si aggiorna anche per anni storici che non c'entrano nulla con la
  // migrazione, e ripartire ogni volta rifarebbe il lavoro (innocuo, ma
  // inutile) o — se l'utente avesse gia' chiuso la card — la riaprirebbe da
  // sola. Non dipende da `migrazione`, ne' dai due ref: sono lo stato che
  // questo stesso effetto scrive, e un ref non fa comunque ripartire nulla.
  useEffect(() => {
    if (!idratato) return;
    const pending = pendingMigrazione.current;
    if (!pending) return;
    if (migratoPer.current === pending.scenarioId) return;
    const baseBs = historicalData[pending.baseYear]?.balance as unknown as Record<string, unknown> | undefined;
    // Il bilancio base non e' ancora atterrato: si riprova al prossimo
    // aggiornamento di `historicalData` (`loadHistoricalData` lo scrive una
    // volta sola, a fine giro, ma finche' non lo fa questo resta `undefined`).
    if (!baseBs) return;
    const esito = migraScenario(pending.map, pending.forecastYears, baseBs, pending.baseYear);
    setAssumptions(
      withPregressoTrimmedToHorizon(
        withDefaultsForYears(esito.map, pending.forecastYears, pending.scenarioId),
        pending.forecastYears
      )
    );
    setMigrazione(esito);
    migratoPer.current = pending.scenarioId;
    pendingMigrazione.current = null;
  }, [idratato, historicalData]);

  /** Chiude la card di migrazione — la mappa migrata (sporca) diventa
   *  persistita al primo salvataggio riuscito, e non c'e' piu' nulla da
   *  segnalare. Non tocca `migratoPer`: la migrazione resta «gia' fatta»
   *  per questo scenario, non deve ripartire riaprendo la card da sola. */
  const chiudiMigrazione = useCallback(() => setMigrazione(null), []);

  const updateAssumption = useCallback((year: number, field: string, value: number | boolean | string | null) => {
    // I ricavi trascinano la parte variabile di materie e servizi (spec
    // 2026-09-15 §4.2, Task 10): il motore non cambia, le due percentuali
    // seguono i ricavi per costruzione — la regola sta in `withRevenueGrowth`
    // (lib/budget-horizon.ts), con la sua prova, non qui.
    if (field === "revenue_growth_pct") {
      setAssumptions((prev) => withRevenueGrowth(prev, year, value as number | null));
      return;
    }
    setAssumptions((prev) => ({
      ...prev,
      [year]: {
        ...prev[year],
        [field]: value,
      },
    }));
  }, []);

  /** Il piano di pregresso (Task 7, giro di correzione 1): scrive SEMPRE nel
   *  PRIMO anno di piano, mai in quello scelto dal chiamante — la regola sta
   *  in `withPregresso` (`lib/budget-horizon.ts`), con la sua prova, non qui
   *  (conflitto A della revisione). */
  const updatePregresso = useCallback((next: Pregresso | null) => {
    setAssumptions((prev) => withPregresso(prev, forecastYears, next));
  }, [forecastYears]);

  /** Gli altri finanziatori (Task 8): scrive SEMPRE nel PRIMO anno di piano
   *  — la regola sta in `withOtherLenders` (`lib/budget-horizon.ts`), con la
   *  sua prova, non qui, sullo stesso precedente di `updatePregresso`. */
  const updateOtherLenders = useCallback((next: OtherLenderInput[] | null) => {
    setAssumptions((prev) => withOtherLenders(prev, forecastYears, next));
  }, [forecastYears]);

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

  // Uno scenario NUOVO nasce con l'aliquota proposta dall'ultimo consuntivo
  // depositato (commercialista, 2026-09-18), una volta sola per scenario: da
  // li' in poi e' dell'utente. Uno scenario salvato tiene la sua.
  const aliquotaProposta = useAliquotaProposta(companyId, baseYear);
  const propostaApplicataPer = useRef<string | null>(null);
  // Uno scalare, non la mappa: l'effetto scrive la mappa e non deve ripartire
  // per questo. Serve a non scrivere la proposta prima che i default del
  // primo anno esistano (andrebbe persa, e la chiave la segnerebbe applicata).
  const righePronte = forecastYears.length > 0 && forecastYears.every((y) => assumptions[y] !== undefined);
  useEffect(() => {
    if (!isNew || !righePronte || !aliquotaProposta.data) return;
    const chiave = `${scenarioId}:${baseYear}`;
    if (propostaApplicataPer.current === chiave) return;
    propostaApplicataPer.current = chiave;
    const aliquota = aliquotaProposta.data.aliquota;
    setAssumptions((prev) => withAliquotaProposta(prev, forecastYears, aliquota));
    // `forecastYears` non e' una dipendenza: l'aliquota si scrive una volta,
    // e gli anni aggiunti dopo la ereditano da `withDefaultsForYears`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isNew, righePronte, aliquotaProposta.data, scenarioId, baseYear]);
  const updateAll = useCallback((field: string, value: number | boolean | null) => {
    // L'inflazione attesa si scrive su ogni anno E riallinea le caselle
    // automatiche della parte fissa (spec 2026-09-15 §4.1, §4.3, Task 10) —
    // la regola sta in `withInflazione` (lib/budget-inflazione.ts), con la
    // sua prova, non qui. Il valore passa cosi' com'e' (anche `null`):
    // `withInflazione` lo riporta a `INFLAZIONE_PREDEFINITA` invece di
    // scrivere un `inflation_pct` nullo, che `isScenarioPrecedente`
    // (lib/budget-migrazione.ts) leggerebbe come firma di uno scenario
    // precedente al lotto (giro di correzione 1).
    if (field === "inflation_pct") {
      setAssumptions((prev) => withInflazione(prev, forecastYears, value as number | null));
      return;
    }
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
    updatePregresso,
    updateOtherLenders,
    migrazione,
    chiudiMigrazione,
  };
}
