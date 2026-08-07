# Rettifiche su due anni (Storico + Bilancio di verifica) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user apply Rettifiche to the historical reference year as well as the partial trial balance, as two sub-tabs inside the existing Rettifiche wizard step.

**Architecture:** Per-year state (load / save / reset / corrections) moves out of `app/infrannuale/page.tsx` into a `useRettificheYear` hook, instantiated twice — once for `fiscalYear - 1` (full year) and once for `fiscalYear` (partial). The existing `RettificheTab` component is rendered twice with no changes to it: it is already prop-driven, `hasRef` already hides the reference column, and `periodEndDate` already derives the right date from `(year, 12)`. No backend changes: `GET/PUT /companies/{id}/years/{year}/adjust*` already take `year` + optional `period_months`.

**Tech Stack:** Next.js 15, React 19, TypeScript, shadcn/ui (`components/ui/tabs.tsx` already present), sonner for toasts.

**Spec:** `docs/superpowers/specs/2026-08-07-rettifiche-storico-design.md`

## Global Constraints

- **No backend changes.** `financial_years.py` and the API client stay as they are.
- **`RettificheTab` (page.tsx:1523-2860) is not modified.** If a task seems to need a change there, stop and re-read the spec.
- **No test runner exists** in `frontend/` (`package.json` has only dev/build/start/lint). Every task's verification gate is `npx tsc --noEmit` **and** `npm run build`, both from `frontend/`, plus the stated manual check. Do not add Vitest — that was explicitly deferred.
- **Line endings:** `frontend/app/infrannuale/page.tsx` is CRLF. After editing, run `file frontend/app/infrannuale/page.tsx` and `git diff --stat` — if the diff is far larger than the lines you touched, the editor normalised the file; restore with `git checkout` and re-apply preserving CRLF.
- **Italian UI copy.** No emojis; lucide-react icons only.
- Existing behaviour for the partial year must not change until Task 3.
- Commit after every task (directly to `main` — this repo does not use feature branches).

---

### Task 1: Extract `useRettificheYear` and wire the partial year to it

Pure refactor. Behaviour must be byte-for-byte identical afterwards; only the location of the code changes.

**Files:**
- Create: `frontend/hooks/use-rettifiche-year.ts`
- Modify: `frontend/app/infrannuale/page.tsx` (state block ~2867-2873; `loadAdjustable` ~3161-3225; `handleResumeScenario` ~3511-3515; render block ~3997-4067)

**Interfaces:**
- Consumes: `getAdjustableFinancialYear`, `saveAdjustments` from `@/lib/api`; `getErrorMessage` from `@/lib/utils`; `AdjustableFinancialYear`, `RettificaEntry` from `@/types/api`.
- Produces: `useRettificheYear(companyId, year, periodMonths, reconcile, onSaved) => RettificheYear`. Tasks 2-4 rely on the exact field names in `RettificheYear` below.

`reconcile` is passed **in** rather than imported: `reconcileSubfields` lives at `page.tsx:2749` as a module-level function of a route file, and importing from a route module into a hook would invert the dependency. Extracting it to a shared module is out of scope (see the spec's "Fuori ambito").

- [ ] **Step 1: Create the hook file**

`frontend/hooks/use-rettifiche-year.ts`:

```ts
"use client";

import { useCallback, useState } from "react";
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

  return { data, corrections, setCorrections, loading, saving, applied, exists, load, save, reset, clear };
}
```

Two deliberate differences from the code being replaced, both required by later tasks:

1. `saveAdjustments` is called with `periodMonths` directly. The old call sites passed `periodMonths < 12 ? periodMonths : undefined`; that normalisation moves to the **call site** in Step 2, so the hook can be given `undefined` for the full year.
2. A 404 sets `exists = false` instead of raising the "Dati per l'anno … non trovati" toast. That toast is re-added at the call site in Step 2 so the partial year keeps today's message.

- [ ] **Step 2: Wire the partial year to the hook in `page.tsx`**

Make `reconcileSubfields` referentially stable for the hook's `useCallback` deps. It is already a module-level `function` declaration at `page.tsx:2749`, so its identity is stable across renders — pass it directly, no wrapper needed.

Replace the six state declarations at `page.tsx:2867-2873`:

```ts
  // Step 1b: Rettifiche (Adjustments)
  const [adjustableData, setAdjustableData] = useState<AdjustableFinancialYear | null>(null);
  const [referenceYearData, setReferenceYearData] = useState<Record<string, number> | null>(null);
  const [corrections, setCorrections] = useState<Record<string, number>>({});
  const [loadingAdjustable, setLoadingAdjustable] = useState(false);
  const [savingAdjustments, setSavingAdjustments] = useState(false);
  const [adjustmentsApplied, setAdjustmentsApplied] = useState(false);
```

with:

```ts
  // Step 1b: Rettifiche (Adjustments) — one hook per FinancialYear.
  const [referenceYearData, setReferenceYearData] = useState<Record<string, number> | null>(null);
  const invalidateDownstream = useCallback(() => {
    setComparison(null); // reload the comparison against the corrected data
  }, []);
  const verifica = useRettificheYear(
    importResult?.companyId ?? null,
    fiscalYear,
    periodMonths < 12 ? periodMonths : undefined,
    reconcileSubfields,
    invalidateDownstream,
  );
```

`invalidateDownstream` is intentionally minimal here — Task 4 fills it in. Keeping it a one-liner now preserves today's behaviour exactly.

Delete `loadAdjustable` (`page.tsx:3161-3219`) and replace the effect at `3221-3225` with:

```ts
  useEffect(() => {
    if (activeTab === "rettifiche" && !verifica.data && importResult) {
      verifica.load();
      // Reference year: still fetched separately here; Task 2 replaces this.
      getAdjustableFinancialYear(importResult.companyId, fiscalYear - 1)
        .then((refData) => {
          const refMerged: Record<string, number> = {
            ...refData.balance_sheet,
            ...refData.income_statement,
          };
          reconcileSubfields(refMerged);
          setReferenceYearData(refMerged);
        })
        .catch(() => setReferenceYearData(null));
    }
  }, [activeTab, verifica, importResult, fiscalYear]);
```

Re-add the 404 message the hook no longer raises, right after `verifica.load()` is defined — as an effect keyed on `verifica.exists`:

```ts
  useEffect(() => {
    if (activeTab === "rettifiche" && !verifica.exists) {
      toast.error(
        `Dati per l'anno ${fiscalYear} non trovati. Verificare l'anno fiscale inserito.`
      );
    }
  }, [activeTab, verifica.exists, fiscalYear]);
```

In `handleResumeScenario` (`page.tsx:3511-3515`), replace:

```ts
    setAdjustableData(null);
    setReferenceYearData(null);
    setCorrections({});
    setAdjustmentsApplied(false);
```

with:

```ts
    verifica.clear();
    setReferenceYearData(null);
```

In the render block (`page.tsx:3997-4067`), replace the whole `<RettificheTab … />` element with:

```tsx
        {activeTab === "rettifiche" && <RettificheTab
          adjustableData={verifica.data}
          referenceYearData={referenceYearData}
          referenceYear={fiscalYear - 1}
          periodMonths={periodMonths}
          fiscalYear={fiscalYear}
          corrections={verifica.corrections}
          setCorrections={verifica.setCorrections}
          loading={verifica.loading}
          saving={verifica.saving}
          adjustmentsApplied={verifica.applied}
          onSave={verifica.save}
          onReset={verifica.reset}
          onNext={() => setActiveTab("comparison")}
        />}
```

Add the import at the top of `page.tsx`:

```ts
import { useRettificheYear } from "@/hooks/use-rettifiche-year";
```

Remove now-unused imports (`saveAdjustments` if no longer referenced in `page.tsx`; keep `getAdjustableFinancialYear`, still used for the reference year).

- [ ] **Step 3: Verify the refactor compiles and builds**

```bash
cd frontend && npx tsc --noEmit && npm run build
```

Expected: both exit 0. If `tsc` reports `savingAdjustments`/`adjustableData` as undefined, a call site was missed — search `page.tsx` for the old names and replace them with the `verifica.*` equivalents.

- [ ] **Step 4: Verify behaviour is unchanged**

On `localhost:3000/infrannuale`, open an existing infrannuale scenario, go to Rettifiche: the table loads, an edit opens the double-entry dialog, confirming persists, the journal lists the entry, Reset restores. Identical to before.

- [ ] **Step 5: Check line endings, then commit**

```bash
cd /home/peter/DEV/budget
git diff --stat   # page.tsx should show ~80 changed lines, NOT ~5000
git add frontend/hooks/use-rettifiche-year.ts frontend/app/infrannuale/page.tsx
git commit -m "refactor(infrannuale): estrae useRettificheYear dallo step Rettifiche"
```

---

### Task 2: Second hook instance for the historical year

Still no UI change: the historical year gets its own hook and the read-only reference column starts coming from it.

**Files:**
- Modify: `frontend/app/infrannuale/page.tsx`

**Interfaces:**
- Consumes: `useRettificheYear` from Task 1.
- Produces: a `storico: RettificheYear` binding used by Tasks 3 and 4.

- [ ] **Step 1: Add the storico instance and derive `referenceYearData` from it**

Next to the `verifica` instance, add:

```ts
  const storico = useRettificheYear(
    importResult?.companyId ?? null,
    fiscalYear - 1,
    undefined,               // full 12-month year
    reconcileSubfields,
    invalidateDownstream,
  );
```

Delete the `referenceYearData` state and its setter, and derive it instead:

```ts
  // Read-only "Storico" column inside the Bilancio di verifica tab. Derived from
  // the storico hook so a correction on one tab moves the column on the other
  // with no refetch. Bilancio abbreviato imports populate only aggregates, so
  // reconcileSubfields plugs the gap into the "altri" sub-fields — otherwise the
  // column shows a total with every detail row empty.
  const referenceYearData = useMemo(() => {
    if (!storico.data) return null;
    const merged: Record<string, number> = {
      ...storico.data.balance_sheet,
      ...storico.data.income_statement,
    };
    reconcileSubfields(merged);
    return merged;
  }, [storico.data]);
```

Add `useMemo` to the React import if it is not already there.

- [ ] **Step 2: Load both years when the step opens**

Replace the effect written in Task 1 Step 2 with:

```ts
  useEffect(() => {
    if (activeTab !== "rettifiche" || !importResult) return;
    if (!verifica.data) verifica.load();
    if (!storico.data && storico.exists) storico.load();
  }, [activeTab, verifica, storico, importResult]);
```

In `handleResumeScenario`, replace `setReferenceYearData(null)` with `storico.clear()`.

- [ ] **Step 3: Verify**

```bash
cd frontend && npx tsc --noEmit && npm run build
```

Expected: exit 0. Then on `/infrannuale`, open Rettifiche on a scenario **that has a historical year**: the `{refYear}` column still shows the same values as before this task. On a scenario **without** one, the column is absent and no error toast appears (previously the `.catch(() => null)` swallowed it; now `exists` does).

- [ ] **Step 4: Commit**

```bash
git add frontend/app/infrannuale/page.tsx
git commit -m "refactor(infrannuale): la colonna storico deriva dal proprio hook rettifiche"
```

---

### Task 3: The two sub-tabs

**Files:**
- Modify: `frontend/app/infrannuale/page.tsx` (render block for `activeTab === "rettifiche"`)

**Interfaces:**
- Consumes: `storico` and `verifica` from Tasks 1-2.
- Produces: no new exports.

- [ ] **Step 1: Add the sub-tabs**

Import the shadcn tabs primitives (`frontend/components/ui/tabs.tsx` already exists):

```ts
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
```

Replace the `activeTab === "rettifiche"` render block with:

```tsx
        {activeTab === "rettifiche" && <Tabs defaultValue="storico" className="space-y-4">
          <TabsList>
            <TabsTrigger value="storico" disabled={!storico.exists}>
              Rettifiche Storico {fiscalYear - 1}
            </TabsTrigger>
            <TabsTrigger value="verifica">
              Rettifiche Bil. di verifica {periodMonths < 12 ? `${periodMonths}M ` : ""}{fiscalYear}
            </TabsTrigger>
          </TabsList>

          <TabsContent value="storico">
            {storico.exists ? (
              <RettificheTab
                adjustableData={storico.data}
                referenceYearData={null}
                referenceYear={fiscalYear - 2}
                periodMonths={12}
                fiscalYear={fiscalYear - 1}
                corrections={storico.corrections}
                setCorrections={storico.setCorrections}
                loading={storico.loading}
                saving={storico.saving}
                adjustmentsApplied={storico.applied}
                onSave={storico.save}
                onReset={storico.reset}
                onNext={() => setSubTab("verifica")}
              />
            ) : (
              <Card>
                <CardContent className="py-12 text-center text-muted-foreground">
                  Nessun bilancio storico caricato per il {fiscalYear - 1}. La proiezione
                  gira in annualizzazione pura sui dati del periodo.
                </CardContent>
              </Card>
            )}
          </TabsContent>

          <TabsContent value="verifica">
            <RettificheTab
              adjustableData={verifica.data}
              referenceYearData={referenceYearData}
              referenceYear={fiscalYear - 1}
              periodMonths={periodMonths}
              fiscalYear={fiscalYear}
              corrections={verifica.corrections}
              setCorrections={verifica.setCorrections}
              loading={verifica.loading}
              saving={verifica.saving}
              adjustmentsApplied={verifica.applied}
              onSave={verifica.save}
              onReset={verifica.reset}
              onNext={() => setActiveTab("comparison")}
            />
          </TabsContent>
        </Tabs>}
```

`referenceYear={fiscalYear - 2}` on the storico tab is never read — `RettificheTab` only uses it inside `hasRef` branches, and `hasRef` is false when `referenceYearData` is `null` — but the prop is required by `RettificheTabProps`.

`onNext` on the storico tab must switch the sub-tab, which needs the `Tabs` to be controlled. Add the state next to the other step state:

```ts
  const [subTab, setSubTab] = useState<"storico" | "verifica">("storico");
```

and make the `Tabs` controlled:

```tsx
        {activeTab === "rettifiche" && <Tabs value={subTab} onValueChange={(v) => setSubTab(v as "storico" | "verifica")} className="space-y-4">
```

- [ ] **Step 2: Default to the tab that can actually be used**

When there is no historical year, `defaultValue="storico"` would open a disabled tab. Add:

```ts
  useEffect(() => {
    if (!storico.exists) setSubTab("verifica");
  }, [storico.exists]);
```

- [ ] **Step 3: Verify**

```bash
cd frontend && npx tsc --noEmit && npm run build
```

Expected: exit 0. Then on `/infrannuale` → Rettifiche:
- with a historical year: two enabled tabs, Storico open first, its date column reads `31/12/{fiscalYear-1}` and it has no reference column; editing a value opens the same double-entry dialog and persists; the Bil. di verifica tab is unchanged;
- without one: the Storico trigger is disabled, Bil. di verifica is open, and the explanatory card is visible when the disabled trigger is inspected.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/infrannuale/page.tsx
git commit -m "feat(infrannuale): rettifiche su due schede — storico e bilancio di verifica"
```

---

### Task 4: Shared downstream invalidation

**Files:**
- Modify: `frontend/app/infrannuale/page.tsx` (`invalidateDownstream`)

**Interfaces:**
- Consumes: `setComparison`, `setAnalysis`, `setProjectedBS` (existing page state).
- Produces: no new exports.

- [ ] **Step 1: Fill in `invalidateDownstream`**

Replace the placeholder from Task 1 with:

```ts
  // A rettifica on EITHER year invalidates everything computed from it: the
  // comparison, the projection and the analysis. Nothing is recomputed silently
  // — the user goes back through Confronto → Proiezione. The warning fires only
  // when a projection already exists, so a first pass isn't nagged.
  const invalidateDownstream = useCallback(() => {
    setComparison(null);
    setProjectedBS((prev) => {
      if (prev) {
        toast.warning("Bilancio modificato — ricalcola la proiezione");
      }
      return null;
    });
    setAnalysis(null);
  }, []);
```

The toast is emitted from inside the `setProjectedBS` updater so the "did a projection exist?" test reads the current value without adding `projectedBS` to the dependency array (which would re-create the callback on every projection change and re-run the hooks' `useCallback`s).

- [ ] **Step 2: Verify**

```bash
cd frontend && npx tsc --noEmit && npm run build
```

Expected: exit 0. Then on `/infrannuale`, with a scenario that already has a projection: apply a rettifica on the Storico tab → warning toast appears; navigate to Confronto → it reloads rather than showing stale data; Proiezione and Indicatori recompute. Repeat on the Bil. di verifica tab → same behaviour. On a fresh scenario with no projection yet, saving a rettifica shows **no** warning.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/infrannuale/page.tsx
git commit -m "fix(infrannuale): una rettifica su qualsiasi anno invalida confronto, proiezione e analisi"
```

---

## Self-review

**Spec coverage.** Spec §1 (hook) → Task 1. §2 (two instances, derived `referenceYearData`, sub-tabs, disabled state) → Tasks 2-3. §3 (invalidation for both years, conditional warning) → Task 4. §4 edge cases: the 20-entry cap and the server-side balance check need no code (per-`FinancialYear`, server-enforced); `reset` per tab is inherent to one hook per year. §5 verification is folded into each task's gate. "Fuori ambito" (extracting `RettificheTab`) is enforced by a Global Constraint.

**Placeholders.** `invalidateDownstream` is deliberately a one-liner in Task 1 and completed in Task 4 — Task 1 states this explicitly and Task 4 shows the full replacement, so no step is left vague.

**Type consistency.** `RettificheYear` field names (`data`, `corrections`, `setCorrections`, `loading`, `saving`, `applied`, `exists`, `load`, `save`, `reset`, `clear`) are used identically in Tasks 1-4. `save`'s signature matches `RettificheTabProps.onSave` (`(finalCorrections?, finalLog?) => Promise<void>`) so it can be passed straight through; `reset` matches `onReset` (`() => Promise<void>`).
