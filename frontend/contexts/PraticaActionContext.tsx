"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

/** Ciò che la barra deve DISEGNARE: solo primitivi, così l'identità è stabile. */
export interface PrimaryActionView {
  label: string;
  disabled: boolean;
  reason: string | null;
}

interface PraticaActionContextType {
  action: PrimaryActionView | null;
  runAction: () => void;
  register: (token: symbol, view: PrimaryActionView, run: () => void) => void;
  unregister: (token: symbol) => void;
}

const PraticaActionContext = createContext<PraticaActionContextType | undefined>(
  undefined,
);

export function PraticaActionProvider({ children }: { children: React.ReactNode }) {
  const [action, setAction] = useState<PrimaryActionView | null>(null);
  const runRef = useRef<(() => void) | null>(null);
  // Chi possiede l'azione ora. Un cambio pagina può smontare il vecchio step
  // DOPO che il nuovo si è registrato: senza token, la cleanup del vecchio
  // cancellerebbe l'azione appena registrata dal nuovo.
  const ownerRef = useRef<symbol | null>(null);

  const register = useCallback(
    (token: symbol, view: PrimaryActionView, run: () => void) => {
      ownerRef.current = token;
      runRef.current = run;
      setAction((prev) =>
        prev &&
        prev.label === view.label &&
        prev.disabled === view.disabled &&
        prev.reason === view.reason
          ? prev // stessa vista: nessun re-render inutile
          : view,
      );
    },
    [],
  );

  const unregister = useCallback((token: symbol) => {
    if (ownerRef.current !== token) return;
    ownerRef.current = null;
    runRef.current = null;
    setAction(null);
  }, []);

  const runAction = useCallback(() => {
    runRef.current?.();
  }, []);

  const value = useMemo<PraticaActionContextType>(
    () => ({ action, runAction, register, unregister }),
    [action, runAction, register, unregister],
  );

  return (
    <PraticaActionContext.Provider value={value}>{children}</PraticaActionContext.Provider>
  );
}

export function usePraticaAction() {
  const ctx = useContext(PraticaActionContext);
  if (ctx === undefined) {
    throw new Error("usePraticaAction deve essere usato dentro un PraticaActionProvider");
  }
  return ctx;
}

/**
 * Registra l'azione primaria dello step corrente nella barra in basso.
 *
 * `onClick` è tenuto in un ref aggiornato a ogni render e NON è una dipendenza
 * dell'effetto: passare l'handler (una funzione nuova a ogni render) come
 * dipendenza rifarebbe partire la registrazione a ogni ciclo. Stessa ragione
 * per cui `use-rettifiche-year` non va mai messo intero in un dependency array.
 */
export function usePrimaryAction(opts: {
  /** `null` = questo step non ha un'azione propria: la barra usa il fallback. */
  label: string | null;
  onClick: () => void | Promise<void>;
  disabled?: boolean;
  reason?: string | null;
}) {
  const { register, unregister } = usePraticaAction();
  const { label, disabled = false, reason = null } = opts;

  const onClickRef = useRef(opts.onClick);
  onClickRef.current = opts.onClick;

  const tokenRef = useRef<symbol | null>(null);
  if (tokenRef.current === null) tokenRef.current = Symbol("primary-action");
  const token = tokenRef.current;

  useEffect(() => {
    if (label === null) return;
    register(token, { label, disabled, reason }, () => {
      void onClickRef.current();
    });
    return () => unregister(token);
  }, [token, label, disabled, reason, register, unregister]);
}
