"use client";

import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { getAdjustableFinancialYear, saveAdjustments } from "@/lib/api";
import { getErrorMessage } from "@/lib/utils";
import { reconcileSubfields } from "@/lib/pratica-reconcile";
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
  /**
   * Il server ha risposto (dati o 404) per QUESTA identità. `exists` da solo
   * non lo dice: parte da `true` e il reset di identità lo rialza a `true`,
   * quindi fra il cambio e la risposta vale «non lo so», non «c'è» — e una
   * schermata che legge solo `exists` pubblicizza una scheda che non esiste.
   */
  resolved: boolean;
  /** L'utente ha premuto "Conferma e prosegui" su questo anno. */
  confirmed: boolean;
  /** Persiste il marker di conferma. Idempotente. Risolve false se il salvataggio fallisce. */
  confirm: () => Promise<boolean>;
  load: () => Promise<void>;
  /** Risolve false (senza rethrow — errore già mostrato via toast) se il salvataggio fallisce. */
  save: (finalCorrections?: Record<string, number>, finalLog?: RettificaEntry[]) => Promise<boolean>;
  /** Risolve false (senza rethrow — errore già mostrato via toast) se il ripristino fallisce. */
  reset: () => Promise<boolean>;
  clear: () => void;
}

/**
 * Rettifiche state for ONE FinancialYear.
 *
 * @param periodMonths undefined = full 12-month year; 1-11 = partial period.
 * @param onSaved      invalidation callback, fired after a successful save or reset.
 */
export function useRettificheYear(
  companyId: number | null,
  year: number,
  periodMonths: number | undefined,
  onSaved: () => void,
): RettificheYear {
  const [data, setData] = useState<AdjustableFinancialYear | null>(null);
  const [corrections, setCorrections] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [applied, setApplied] = useState(false);
  const [exists, setExists] = useState(true);
  const [resolved, setResolved] = useState(false);
  const [confirmed, setConfirmed] = useState(false);

  // Identity change (different company, year or period) invalidates the loaded
  // sheet: keeping it would let a save post the previous record's values to the
  // new one — and a partial and a full-year record can coexist for the same year.
  useEffect(() => {
    setData(null);
    setCorrections({});
    setApplied(false);
    setExists(true);
    setResolved(false);
    setConfirmed(false);
  }, [companyId, year, periodMonths]);

  const load = useCallback(async () => {
    if (companyId === null) return;
    setLoading(true);
    try {
      const result = await getAdjustableFinancialYear(companyId, year, periodMonths);
      setData(result);
      setExists(true);
      setResolved(true);
      // Seed from SAVED values (they already include previously applied
      // rettifiche); original_* is used only for delta display and proposals.
      const initial: Record<string, number> = {};
      for (const [k, v] of Object.entries(result.balance_sheet)) initial[k] = v;
      for (const [k, v] of Object.entries(result.income_statement)) initial[k] = v;
      reconcileSubfields(initial);
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
        setResolved(true);
        setData(null);
        setCorrections({});
        setApplied(false);
      } else {
        toast.error(getErrorMessage(error, "Errore nel caricamento dati"));
      }
    } finally {
      setLoading(false);
    }
  }, [companyId, year, periodMonths]);

  const save = useCallback(
    async (finalCorrections?: Record<string, number>, finalLog?: RettificaEntry[]): Promise<boolean> => {
      if (companyId === null || !data) return false;
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
        return true;
      } catch (error: unknown) {
        toast.error(getErrorMessage(error, "Errore nel salvataggio"));
        return false;
      } finally {
        setSaving(false);
      }
    },
    [companyId, year, periodMonths, data, corrections, onSaved],
  );

  const reset = useCallback(async (): Promise<boolean> => {
    if (companyId === null || !data?.original_balance_sheet || !data?.original_income_statement) return false;
    setSaving(true);
    try {
      // original_*_snapshot is the RAW import (pre-reconcileSubfields): on an
      // aggregate-only import (bilancio abbreviato) its detail sub-fields are
      // zero. The currently persisted state went through reconcileSubfields()
      // at load time, so posting the raw snapshot as-is would WIDEN the
      // aggregati/dettagli gap and the server's anti-regression guard
      // legitimately rejects it (400) — reset never applied. Mirror load():
      // merge BS+IS into one flat record, reconcile that COPY (reconcileSubfields
      // mutates in place; data.original_* must stay untouched — it's re-read
      // on every subsequent reset), then split back into the two payloads.
      const merged: Record<string, number> = {
        ...data.original_balance_sheet,
        ...data.original_income_statement,
      };
      reconcileSubfields(merged);
      const bsPayload: Record<string, number> = {};
      for (const k of Object.keys(data.original_balance_sheet)) bsPayload[k] = merged[k];
      const isPayload: Record<string, number> = {};
      for (const k of Object.keys(data.original_income_statement)) isPayload[k] = merged[k];
      const result = await saveAdjustments(
        companyId,
        year,
        bsPayload,
        isPayload,
        periodMonths,
        [], // clear the rettifiche log on reset
      );
      setData(result);
      const initial: Record<string, number> = {};
      for (const [k, v] of Object.entries(result.balance_sheet)) initial[k] = v;
      for (const [k, v] of Object.entries(result.income_statement)) initial[k] = v;
      reconcileSubfields(initial);
      setCorrections(initial);
      setApplied(false);
      setConfirmed(false);
      onSaved();
      toast.success("Rettifiche annullate — ripristinati i valori originali");
      return true;
    } catch (error: unknown) {
      // Anche riconciliato, il payload può in teoria essere ancora respinto
      // dalla guardia anti-regressione del server (400) — ad es. per uno
      // sbilancio Attivo/Passivo o CE↔SP preesistente nell'import grezzo che
      // reconcileSubfields() non tocca. Qui NON tocchiamo data/corrections/applied/
      // confirmed: il ripristino non è avvenuto, quindi lo stato (e il gate a
      // valle, vedi rettificheConfirmed) deve restare quello di prima —
      // nessun rollback locale necessario perché niente è stato applicato in
      // ottimistico.
      toast.error(getErrorMessage(error, "Errore nel ripristino"));
      return false;
    } finally {
      setSaving(false);
    }
  }, [companyId, year, periodMonths, data, onSaved]);

  const clear = useCallback(() => {
    setData(null);
    setCorrections({});
    setApplied(false);
    setExists(true);
    setResolved(false);
    setConfirmed(false);
  }, []);

  const confirm = useCallback(async (): Promise<boolean> => {
    if (companyId === null || !data) return false;
    const log = data.rettifiche_log ?? [];
    // Idempotente: una seconda conferma non aggiunge una riga né consuma il cap.
    if (log.some((e) => e.entry_type === "confirm")) {
      setConfirmed(true);
      return true;
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
    const ok = await save(undefined, [...log, marker]);
    if (!ok) return false;
    setConfirmed(true);
    return true;
  }, [companyId, data, year, periodMonths, save]);

  return { data, corrections, setCorrections, loading, saving, applied, confirmed, exists, resolved, load, save, reset, confirm, clear };
}
