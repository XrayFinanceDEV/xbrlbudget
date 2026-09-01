"use client";

import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useMemo,
  useCallback,
  useRef,
} from "react";
import { getCompaniesWithScenarios, getCompanyYears } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { usePratica } from "@/contexts/PraticaContext";
import type { Company, CompanyWithScenarios } from "@/types/api";

interface AppContextType {
  // Sempre CON gli scenari: è l'unica fonte dell'elenco aziende in tutta
  // l'app (la home non ne ha più uno proprio). `CompanyWithScenarios`
  // ESTENDE `Company`, quindi i consumatori che leggono solo i campi
  // anagrafici non cambiano di una riga.
  companies: CompanyWithScenarios[];
  selectedCompanyId: number | null;
  setSelectedCompanyId: (id: number | null) => void;
  years: number[];
  selectedYear: number | null;
  setSelectedYear: (year: number | null) => void;
  selectedCompany: Company | null;
  loading: boolean;
  error: string | null;
  // Un caricamento dell'elenco è andato a buon fine almeno una volta.
  companiesLoaded: boolean;
  // Messaggio dell'ULTIMO caricamento fallito, `null` quando l'ultimo è
  // riuscito. Serve alla home per dire il vero invece di mostrare l'invito
  // a creare la prima azienda: quel messaggio vale solo per il caso
  // «caricamento riuscito, zero aziende».
  companiesError: string | null;
  startupMode: boolean;
  setStartupMode: (v: boolean) => void;
  refreshCompanies: () => Promise<void>;
  refreshYears: () => Promise<void>;
}

const STARTUP_MODE_KEY = "xbrl_startup_mode";

const AppContext = createContext<AppContextType | undefined>(undefined);

export function AppProvider({ children }: { children: React.ReactNode }) {
  const { isLoading: authLoading, isAuthenticated } = useAuth();
  const authLoadingRef = useRef(authLoading);
  authLoadingRef.current = authLoading;
  // PraticaProvider is mounted ABOVE AppProvider (see app/layout.tsx), so this
  // is legal. A pratica owns the company selection while it is active — see
  // praticaActiveRef below and the sync effect after loadCompanies.
  const { pratica, exitPratica } = usePratica();
  const [companies, setCompanies] = useState<CompanyWithScenarios[]>([]);
  const [companiesLoaded, setCompaniesLoaded] = useState(false);
  const [selectedCompanyId, setSelectedCompanyId] = useState<number | null>(null);
  const [years, setYears] = useState<number[]>([]);
  const [selectedYear, setSelectedYear] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [companiesError, setCompaniesError] = useState<string | null>(null);

  // Startup mode: simplified budget flow (no import/companies tabs, reduced variables).
  // Persisted so it survives navigation between pages within a startup session.
  const [startupMode, setStartupModeState] = useState(false);
  useEffect(() => {
    try {
      setStartupModeState(localStorage.getItem(STARTUP_MODE_KEY) === "1");
    } catch {
      /* localStorage unavailable */
    }
  }, []);
  const setStartupMode = useCallback((v: boolean) => {
    setStartupModeState(v);
    try {
      localStorage.setItem(STARTUP_MODE_KEY, v ? "1" : "0");
    } catch {
      /* localStorage unavailable */
    }
  }, []);

  // Ref to read current selectedCompanyId without adding it as a dependency
  const selectedCompanyIdRef = useRef(selectedCompanyId);
  selectedCompanyIdRef.current = selectedCompanyId;

  // Ref to read "is a pratica active" without adding `pratica` (a fresh object
  // every render) as a dependency of loadCompanies below.
  const praticaActiveRef = useRef(pratica !== null);
  praticaActiveRef.current = pratica !== null;

  // Tracks whether the MOST RECENT loadCompanies() call actually succeeded.
  // `companiesLoaded` only says "a load has completed at least once" and stays
  // true forever after the first success, so a later transient failure (the
  // catch block below leaves `companies` untouched) is invisible to it. The
  // deletion-detection effect (FINDING 5, below) needs the freshness signal
  // too, or it compares a just-set `pratica.companyId` against a stale
  // `companies` array and wrongly concludes the company was deleted.
  const lastLoadSucceededRef = useRef(false);

  // Stable loadCompanies — no dependencies, reads current selection via ref
  // Skips API call if auth is still loading (prevents 401 in iframe mode)
  const loadCompanies = useCallback(async () => {
    if (authLoadingRef.current) return;
    try {
      // `?include=scenarios`: una sola query lato server (joinedload), e il
      // tetto è 50 aziende per utente — il costo dell'inclusione è nullo.
      const data = await getCompaniesWithScenarios();
      setCompanies(data);
      setCompaniesLoaded(true);
      setCompaniesError(null);
      lastLoadSucceededRef.current = true;

      // Fix selection if needed (outside of setCompanies callback)
      const currentId = selectedCompanyIdRef.current;
      if (currentId && !data.find((c) => c.id === currentId)) {
        setSelectedCompanyId(null);
      } else if (!currentId && data.length > 0 && !praticaActiveRef.current) {
        // Auto-select stands down while a pratica is active: a pratica owns
        // the selection (see the companyId sync effect below). Without this
        // guard, /pratica's mount-time refreshCompanies() undoes the
        // deliberate setSelectedCompanyId(null) the home page's "Da bilancio"
        // card performs before starting a new pratica — silently re-pointing
        // AnagraficheStep at an unrelated existing company.
        setSelectedCompanyId(data[0].id);
      }
    } catch (err) {
      console.error("Error loading companies:", err);
      setError("Impossibile caricare le aziende");
      // Distinto da `error` (condiviso con il caricamento anni) perché la
      // home ci appende sopra un ramo di UI: senza, un fallimento si
      // presenterebbe come «Nessuna azienda presente», cioè un invito a
      // creare il duplicato che l'azienda già ha.
      setCompaniesError("Impossibile caricare le aziende");
      lastLoadSucceededRef.current = false;
    }
  }, []);

  // Load companies after auth resolves
  useEffect(() => {
    if (!authLoading) {
      loadCompanies();
    }
  }, [authLoading, loadCompanies]);

  // FIX 2: while a pratica is active and points at a company, the app-wide
  // selection follows it — so ordinary pages reached via the pratica bridge
  // (e.g. /budget after "Prosegui al Budget") show the SAME company instead
  // of whatever AppContext happened to have selected before. Depends only on
  // the scalar companyId (never the `pratica` object, which is a fresh
  // reference every render) so it can't loop, and it is a no-op outside a
  // pratica (pratica === null) or once the two are already in sync.
  useEffect(() => {
    if (pratica && pratica.companyId !== null && pratica.companyId !== selectedCompanyIdRef.current) {
      setSelectedCompanyId(pratica.companyId);
    }
  }, [pratica?.companyId]);

  // FINDING 5 (2026-08-08 final review): a pratica pointing at a company that
  // no longer exists (deleted from another tab, or from /aziende in this one)
  // must self-clear instead of leaving the stepper and the wizard dead-ending
  // on every page (spec :264-266). Gated on `companiesLoaded` so the very
  // first render — before loadCompanies has resolved and `companies` is still
  // `[]` — never mistakes "not loaded yet" for "deleted". Also gated on
  // `lastLoadSucceededRef`: a transient loadCompanies() failure leaves
  // `companies` stale (and `companiesLoaded` was already true from an earlier
  // successful load), so without this a fresh `pratica.companyId` set right
  // after a failed refresh would look "not in the list" and wrongly exit the
  // pratica the user just started (see N3, 2026-08-08 residual review).
  useEffect(() => {
    if (!companiesLoaded || !pratica || pratica.companyId === null) return;
    if (!lastLoadSucceededRef.current) return;
    if (!companies.some((c) => c.id === pratica.companyId)) {
      exitPratica();
    }
    // Deliberatamente su `pratica?.companyId`, non sull'oggetto `pratica`
    // intero (un riferimento nuovo a ogni render): dipendere da `pratica`
    // rifarebbe scattare l'effetto ad ogni updatePratica, anche quando
    // companyId non cambia (vedi il pattern gemello sopra, effetto FIX 2).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companiesLoaded, companies, pratica?.companyId, exitPratica]);

  // Reload years for the currently selected company
  const refreshYears = useCallback(async () => {
    const companyId = selectedCompanyIdRef.current;
    if (!companyId) return;
    try {
      const data = await getCompanyYears(companyId);
      setYears((prev) => {
        const same =
          prev.length === data.length && prev.every((y, i) => y === data[i]);
        return same ? prev : data;
      });
    } catch (err) {
      console.error("Error refreshing years:", err);
    }
  }, []);

  // Load years when company changes
  useEffect(() => {
    if (!selectedCompanyId) {
      setYears([]);
      setSelectedYear(null);
      return;
    }

    const loadYears = async () => {
      try {
        setSelectedYear(null);
        const data = await getCompanyYears(selectedCompanyId);
        setYears((prev) => {
          const same =
            prev.length === data.length && prev.every((y, i) => y === data[i]);
          return same ? prev : data;
        });
        if (data.length > 0) {
          setSelectedYear(data[0]);
        }
      } catch (err) {
        console.error("Error loading years:", err);
        setError("Impossibile caricare gli anni");
      }
    };
    loadYears();
  }, [selectedCompanyId]);

  const selectedCompany = useMemo(
    () => companies.find((c) => c.id === selectedCompanyId) ?? null,
    [companies, selectedCompanyId]
  );

  // Memoize context value to prevent all consumers re-rendering on unrelated changes
  const contextValue = useMemo<AppContextType>(
    () => ({
      companies,
      selectedCompanyId,
      setSelectedCompanyId,
      years,
      selectedYear,
      setSelectedYear,
      selectedCompany,
      loading,
      error,
      companiesLoaded,
      companiesError,
      startupMode,
      setStartupMode,
      refreshCompanies: loadCompanies,
      refreshYears,
    }),
    [
      companies,
      selectedCompanyId,
      years,
      selectedYear,
      selectedCompany,
      loading,
      error,
      companiesLoaded,
      companiesError,
      startupMode,
      setStartupMode,
      loadCompanies,
      refreshYears,
    ]
  );

  return (
    <AppContext.Provider value={contextValue}>{children}</AppContext.Provider>
  );
}

export function useApp() {
  const context = useContext(AppContext);
  if (context === undefined) {
    throw new Error("useApp must be used within an AppProvider");
  }
  return context;
}
