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
  refreshCompanies: () => Promise<void>;
  refreshYears: () => Promise<void>;
}

const AppContext = createContext<AppContextType | undefined>(undefined);

export function AppProvider({ children }: { children: React.ReactNode }) {
  const { isLoading: authLoading, isAuthenticated } = useAuth();
  const authLoadingRef = useRef(authLoading);
  authLoadingRef.current = authLoading;
  const [companies, setCompanies] = useState<Company[]>([]);
  const [selectedCompanyId, setSelectedCompanyId] = useState<number | null>(null);
  const [years, setYears] = useState<number[]>([]);
  const [selectedYear, setSelectedYear] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Ref to read current selectedCompanyId without adding it as a dependency
  const selectedCompanyIdRef = useRef(selectedCompanyId);
  selectedCompanyIdRef.current = selectedCompanyId;

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
      } else if (!currentId && data.length > 0) {
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
