"use client";

import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { getAdjustableFinancialYear, saveAdjustments } from "@/lib/api";
import { getErrorMessage } from "@/lib/utils";
import type { AdjustableFinancialYear, RettificaEntry } from "@/types/api";

export interface RettificheYear {
  data: AdjustableFinancialYear | null;
  corrections: Record<string, number>;
  setCorrections: React.Dispatch<React.SetStateAction<Record<string, number>>>;
  loading: boolean;
  saving: boolean;
  applied: boolean;
  /** false only when the year has no FinancialYear at all (404). */
  exists: boolean;
  /** L'utente ha premuto "Conferma e prosegui" su questo anno. */
  confirmed: boolean;
  /** Persiste il marker di conferma. Idempotente. */
  confirm: () => Promise<void>;
  load: () => Promise<void>;
  save: (finalCorrections?: Record<string, number>, finalLog?: RettificaEntry[]) => Promise<void>;
  reset: () => Promise<void>;
  clear: () => void;
}

/**
 * Rettifiche state for ONE FinancialYear.
 *
 * @param periodMonths undefined = full 12-month year; 1-11 = partial period.
 * @param reconcile    reconcileSubfields, injected to avoid importing from a route module.
 * @param onSaved      invalidation callback, fired after a successful save or reset.
 */
export function useRettificheYear(
  companyId: number | null,
  year: number,
  periodMonths: number | undefined,
  reconcile: (data: Record<string, number>) => void,
  onSaved: () => void,
): RettificheYear {
  const [data, setData] = useState<AdjustableFinancialYear | null>(null);
  const [corrections, setCorrections] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [applied, setApplied] = useState(false);
  const [exists, setExists] = useState(true);
  const [confirmed, setConfirmed] = useState(false);

  // Identity change (different company, year or period) invalidates the loaded
  // sheet: keeping it would let a save post the previous record's values to the
  // new one — and a partial and a full-year record can coexist for the same year.
  useEffect(() => {
    setData(null);
    setCorrections({});
    setApplied(false);
    setExists(true);
    setConfirmed(false);
  }, [companyId, year, periodMonths]);

  const load = useCallback(async () => {
    if (companyId === null) return;
    setLoading(true);
    try {
      const result = await getAdjustableFinancialYear(companyId, year, periodMonths);
      setData(result);
      setExists(true);
      // Seed from SAVED values (they already include previously applied
      // rettifiche); original_* is used only for delta display and proposals.
      const initial: Record<string, number> = {};
      for (const [k, v] of Object.entries(result.balance_sheet)) initial[k] = v;
      for (const [k, v] of Object.entries(result.income_statement)) initial[k] = v;
      reconcile(initial);
      setCorrections(initial);
      const hasExisting =
        result.original_balance_sheet &&
        Object.keys(result.balance_sheet).some((k) => {
          const saved = result.balance_sheet[k] ?? 0;
          const orig = result.original_balance_sheet![k] ?? 0;
          return Math.abs(saved - orig) > 0.01;
        });
      setApplied(!!hasExisting);
      setConfirmed(
        (result.rettifiche_log ?? []).some((e) => e.entry_type === "confirm"),
      );
    } catch (error: unknown) {
      const status = (error as { response?: { status?: number } })?.response?.status;
      if (status === 404) {
        // Legitimate state, not an error: the year was never imported.
        setExists(false);
        setData(null);
        setCorrections({});
        setApplied(false);
      } else {
        toast.error(getErrorMessage(error, "Errore nel caricamento dati"));
      }
    } finally {
      setLoading(false);
    }
  }, [companyId, year, periodMonths, reconcile]);

  const save = useCallback(
    async (finalCorrections?: Record<string, number>, finalLog?: RettificaEntry[]) => {
      if (companyId === null || !data) return;
      setSaving(true);
      try {
        const corr = finalCorrections ?? corrections;
        const bs: Record<string, number> = {};
        const is_: Record<string, number> = {};
        for (const k of Object.keys(data.balance_sheet)) bs[k] = corr[k] ?? data.balance_sheet[k];
        for (const k of Object.keys(data.income_statement)) is_[k] = corr[k] ?? data.income_statement[k];
        const result = await saveAdjustments(companyId, year, bs, is_, periodMonths, finalLog);
        setData(result);
        setApplied(true);
        onSaved();
      } catch (error: unknown) {
        toast.error(getErrorMessage(error, "Errore nel salvataggio"));
      } finally {
        setSaving(false);
      }
    },
    [companyId, year, periodMonths, data, corrections, onSaved],
  );

  const reset = useCallback(async () => {
    if (companyId === null || !data?.original_balance_sheet || !data?.original_income_statement) return;
    setSaving(true);
    try {
      const result = await saveAdjustments(
        companyId,
        year,
        data.original_balance_sheet,
        data.original_income_statement,
        periodMonths,
        [], // clear the rettifiche log on reset
      );
      setData(result);
      const initial: Record<string, number> = {};
      for (const [k, v] of Object.entries(result.balance_sheet)) initial[k] = v;
      for (const [k, v] of Object.entries(result.income_statement)) initial[k] = v;
      reconcile(initial);
      setCorrections(initial);
      setApplied(false);
      setConfirmed(false);
      onSaved();
      toast.success("Rettifiche annullate — ripristinati i valori originali");
    } catch {
      toast.error("Errore nel ripristino");
    } finally {
      setSaving(false);
    }
  }, [companyId, year, periodMonths, data, reconcile, onSaved]);

  const clear = useCallback(() => {
    setData(null);
    setCorrections({});
    setApplied(false);
    setExists(true);
  }, []);

  const confirm = useCallback(async () => {
    if (companyId === null || !data) return;
    const log = data.rettifiche_log ?? [];
    // Idempotente: una seconda conferma non aggiunge una riga né consuma il cap.
    if (log.some((e) => e.entry_type === "confirm")) {
      setConfirmed(true);
      return;
    }
    const marker: RettificaEntry = {
      id: `confirm-${year}-${periodMonths ?? 12}`,
      entry_type: "confirm",
      edited_field: "",
      edited_label: "Rettifiche confermate",
      edit_delta: 0,
      counterpart_field: "",
      counterpart_label: "",
      counterpart_delta: 0,
      created_at: new Date().toISOString(),
    };
    await save(undefined, [...log, marker]);
    setConfirmed(true);
  }, [companyId, data, year, periodMonths, save]);

  return { data, corrections, setCorrections, loading, saving, applied, confirmed, exists, load, save, reset, confirm, clear };
}
