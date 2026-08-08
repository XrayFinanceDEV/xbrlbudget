"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

export type PraticaWorkflow = "bilancio" | "startup";

export interface PraticaState {
  workflow: PraticaWorkflow;
  companyId: number | null;
  /** Anno del bilancio importato (percorso "bilancio"); null per una startup. */
  fiscalYear: number | null;
  /** 1-12; 12 = bilancio annuale. null per una startup. */
  periodMonths: number | null;
  infrannualeScenarioId: number | null;
  budgetScenarioId: number | null;
  /** Tab attiva della fase ANALISI dentro /pratica. */
  analysisStep: string;
  /**
   * Cache per lo stepper. La verità resta il rettifiche_log sul server, riletto
   * al mount del wizard: questo evita che lo stepper sfarfalli al primo render.
   */
  rettificheConfirmed: { storico: boolean; verifica: boolean };
}

interface PraticaContextType {
  pratica: PraticaState | null;
  startPratica: (init: Partial<PraticaState> & { workflow: PraticaWorkflow }) => void;
  updatePratica: (patch: Partial<PraticaState>) => void;
  setAnalysisStep: (step: string) => void;
  exitPratica: () => void;
}

const PRATICA_KEY = "xbrl_pratica";

const PraticaContext = createContext<PraticaContextType | undefined>(undefined);

const DEFAULTS: Omit<PraticaState, "workflow"> = {
  companyId: null,
  fiscalYear: null,
  periodMonths: null,
  infrannualeScenarioId: null,
  budgetScenarioId: null,
  analysisStep: "anagrafiche",
  rettificheConfirmed: { storico: false, verifica: false },
};

export function PraticaProvider({ children }: { children: React.ReactNode }) {
  const [pratica, setPratica] = useState<PraticaState | null>(null);

  // Letto DOPO il mount: leggerlo nell'inizializzatore di useState romperebbe
  // l'idratazione di Next (server e client renderebbero markup diversi).
  useEffect(() => {
    try {
      const raw = localStorage.getItem(PRATICA_KEY);
      if (raw) setPratica({ ...DEFAULTS, ...JSON.parse(raw) } as PraticaState);
    } catch {
      /* localStorage non disponibile o JSON corrotto */
    }
  }, []);

  // La scrittura/rimozione su localStorage è interamente a carico dell'
  // useEffect su [pratica] sotto (ora gestisce anche il caso null): qui
  // aggiorniamo solo lo stato in memoria.
  const persist = useCallback((next: PraticaState | null) => {
    setPratica(next);
  }, []);

  const startPratica = useCallback<PraticaContextType["startPratica"]>(
    (init) => persist({ ...DEFAULTS, ...init }),
    [persist],
  );

  // Il write su localStorage NON deve stare dentro l'updater di setState:
  // reactStrictMode (next.config.ts) invoca due volte l'updater in dev, quindi
  // scriverebbe due volte — innocuo qui, ma è un pattern sbagliato in generale
  // (l'updater deve restare puro). Persistiamo invece in un useEffect su
  // [pratica], sotto.
  const updatePratica = useCallback<PraticaContextType["updatePratica"]>(
    (patch) =>
      setPratica((prev) => {
        if (!prev) {
          // Errore di programmazione, non un caso utente da segnalare: nessuna
          // pratica attiva su cui applicare la patch. Visibile in sviluppo
          // invece di sparire silenziosamente.
          console.warn("updatePratica: nessuna pratica attiva, patch ignorata", patch);
          return prev;
        }
        return { ...prev, ...patch };
      }),
    [],
  );

  // Persiste ogni cambio di stato (startPratica passa da `persist` sopra, ma
  // updatePratica e qualunque futuro setPratica diretto passano tutti di qui).
  // Autoritativo per ENTRAMBI i casi: scrive quando `pratica` è valorizzata,
  // rimuove quando è null — altrimenti un effetto in un componente FIGLIO
  // (AppContext gira dopo, essendo montato più in basso) che chiama
  // exitPratica() nello stesso commit vedrebbe questo effetto rieseguirsi
  // ancora chiuso sul vecchio valore non-null e riscriverebbe la entry appena
  // rimossa (localStorage sopravviverebbe al reload finché l'effetto in
  // AppContext non la ripulisce di nuovo al giro successivo).
  useEffect(() => {
    try {
      if (pratica) localStorage.setItem(PRATICA_KEY, JSON.stringify(pratica));
      else localStorage.removeItem(PRATICA_KEY);
    } catch {
      /* localStorage non disponibile */
    }
  }, [pratica]);

  const setAnalysisStep = useCallback(
    (step: string) => updatePratica({ analysisStep: step }),
    [updatePratica],
  );

  const exitPratica = useCallback(() => persist(null), [persist]);

  const value = useMemo<PraticaContextType>(
    () => ({ pratica, startPratica, updatePratica, setAnalysisStep, exitPratica }),
    [pratica, startPratica, updatePratica, setAnalysisStep, exitPratica],
  );

  return <PraticaContext.Provider value={value}>{children}</PraticaContext.Provider>;
}

export function usePratica() {
  const context = useContext(PraticaContext);
  if (context === undefined) {
    throw new Error("usePratica deve essere usato dentro un PraticaProvider");
  }
  return context;
}
