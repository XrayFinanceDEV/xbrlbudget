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
import { getCompanies, getCompanyYears } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { usePratica } from "@/contexts/PraticaContext";
import type { Company } from "@/types/api";

interface AppContextType {
  companies: Company[];
  selectedCompanyId: number | null;
  setSelectedCompanyId: (id: number | null) => void;
  years: number[];
  selectedYear: number | null;
  setSelectedYear: (year: number | null) => void;
  selectedCompany: Company | null;
  loading: boolean;
  error: string | null;
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
  const { pratica } = usePratica();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [selectedCompanyId, setSelectedCompanyId] = useState<number | null>(null);
  const [years, setYears] = useState<number[]>([]);
  const [selectedYear, setSelectedYear] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  // Stable loadCompanies — no dependencies, reads current selection via ref
  // Skips API call if auth is still loading (prevents 401 in iframe mode)
  const loadCompanies = useCallback(async () => {
    if (authLoadingRef.current) return;
    try {
      const data = await getCompanies();
      setCompanies(data);

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
