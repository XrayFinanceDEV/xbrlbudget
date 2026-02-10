"use client";

import React, { createContext, useContext, useState, useEffect } from "react";
import { getCompanies, getCompanyYears } from "@/lib/api";
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
}

const AppContext = createContext<AppContextType | undefined>(undefined);

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [selectedCompanyId, setSelectedCompanyId] = useState<number | null>(null);
  const [years, setYears] = useState<number[]>([]);
  const [selectedYear, setSelectedYear] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load companies function
  const loadCompanies = async () => {
    try {
      const data = await getCompanies();
      setCompanies(prevCompanies => {
        // If currently selected company was deleted, clear selection
        setSelectedCompanyId(prevId => {
          if (prevId && !data.find(c => c.id === prevId)) {
            return null;
          }
          // If no company is selected and companies exist, select the first one
          if (!prevId && data.length > 0) {
            return data[0].id;
          }
          return prevId;
        });
        return data;
      });
    } catch (err) {
      console.error("Error loading companies:", err);
      setError("Impossibile caricare le aziende");
    }
  };

  // Load companies on mount
  useEffect(() => {
    loadCompanies();
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
        setYears(data);
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

  const selectedCompany = companies.find((c) => c.id === selectedCompanyId) || null;

  return (
    <AppContext.Provider
      value={{
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
      }}
    >
      {children}
    </AppContext.Provider>
  );
}

export function useApp() {
  const context = useContext(AppContext);
  if (context === undefined) {
    throw new Error("useApp must be used within an AppProvider");
  }
  return context;
}
