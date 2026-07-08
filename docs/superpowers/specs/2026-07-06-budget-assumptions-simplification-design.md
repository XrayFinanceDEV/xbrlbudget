# Budget assumptions simplification

**Date:** 2026-07-06
**Status:** Implemented (see docs/superpowers/plans/2026-07-06-budget-assumptions-simplification.md)
**Area:** `frontend/app/budget/page.tsx` (+ light plumbing hygiene) — Project 2 of the 2026-07-06 reorganization (see `docs/superpowers/2026-07-06-project-analysis.md` §2)

## Problem

Creating/editing a budget scenario exposes ~27 always-visible numeric rows per forecast year
(~81 inputs for a 3-year scenario; ~180 editable cells with the detail accordions open) across
three tabs (`ScenarioForm`, `budget/page.tsx:719`, tabs `:999-1013`). Most of that input mass is
noise:

- The **variable/fixed split** (6 fields: 4 growth + 2 percentage) is mathematically irrelevant
  when the two growth rates are equal (`forecast_engine.py:220-242`) — and the frontend already
  defaults the split percentage to 0 (`page.tsx:891-892`), i.e. all-variable.
- The **tax rate input is silently ignored** for most companies: the engine prefers the base-year
  effective rate whenever plausible (`forecast_engine.py:374-390`).
- **DSO/DIO/DPO auto-derive** from the base year when left empty (`forecast_engine.py:487-505`).
- **5 dead DB fields** have zero engine reads: `receivables_short_growth_pct`,
  `payables_short_growth_pct`, `interest_rate_receivables`, `interest_rate_payables`, legacy
  `investments`. The AutoGenerator's "Crediti/Debiti breve" row writes two of them
  (`page.tsx:1316`) — a visual no-op.
- The 19 **CE-override rows** (absolute €) duplicate the `/forecast/income` click-to-edit editor
  (same DB columns, better idiom), and scenario creation **pre-fills 12 carry-forward overrides
  with base-year values** (`page.tsx:898-909`) — functional no-ops stored non-NULL.
- The engine is **default-safe by construction**: growth 0 = carry-forward, NULL days/schedules =
  auto-derived/constant, NULL override = engine calc. An empty assumptions row already produces a
  valid steady-state forecast — so hiding fields costs nothing.

Two plumbing inconsistencies ride along:

- `/budget` saves via the **per-year** POST/PUT endpoints plus a separate `POST /generate`
  (`page.tsx:395,966,974,983`), while infrannuale uses the **bulk PUT** — two divergent write
  paths for the same table.
- CLAUDE.md claims the budget page passes `clear_overrides=true` on Ricalcola/Salva; the code
  passes `false` (`page.tsx:107,406,983`) — doc/code drift over behavior that silently decides
  whether the user's manual P&L edits survive.

## Goals

1. Reduce the always-visible input surface to the ~9 high-sensitivity row groups (≈33 cells for
   3 years) with everything else under one "Avanzate" accordion.
2. One write path: bulk PUT with `auto_generate=true`, preserving CE overrides made on
   `/forecast/income`.
3. Make override-clearing an explicit user choice, never a side effect.
4. Remove dead fields from the UI/types/AutoGenerator; stop storing no-op overrides.
5. **Zero backend-schema and zero engine change.** The infrannuale flow, the
   `assumptions_service` kwargs block, and the `/forecast/income` PATCH flow are untouched.

## Non-goals

- No DB column drops (migrations are add-only; dead columns stay, ignored).
- No change to `BudgetAssumptions` semantics — hiding, not removing, capability.
- No redesign of `/forecast/income` editing or of the infrannuale Proiezione tab.
- Startup mode (`StartupSetup`, `page.tsx:318-593`) keeps its own flow unchanged.
- Navigation/journey changes (dead-end saves, next-step CTAs) belong to Project 3.

## Design

### 1. Form structure

`ScenarioForm` goes from 3 tabs to **2 tabs**:

- **"Informazioni"** — unchanged (nome, descrizione, anno base, durata 3/5).
- **"Ipotesi"** — one table, rows × forecast-year columns (historical columns stay read-only on
  the left, as today). Always-visible rows:

| # | Row (label) | Writes → `BudgetAssumptions` |
|---|---|---|
| 1 | Ricavi % | `revenue_growth_pct` |
| 2 | Materie % | `variable_materials_growth_pct` **and** `fixed_materials_growth_pct` (same value) |
| 3 | Servizi % | `variable_services_growth_pct` **and** `fixed_services_growth_pct` (same value) |
| 4 | Personale % | `personnel_growth_pct` |
| 5 | Altri costi % | `other_costs_growth_pct` |
| 6 | Investimenti materiali € | `tangible_investments` |
| 7 | Investimenti immateriali € | `intangible_investments` |
| 8 | Rimborso banche (anni) | `existing_debt_repayment_years` |
| 9 | Nuovo finanziamento: importo € / durata anni / tasso % | `financing_amount` / `financing_duration_years` / `financing_interest_rate` |

The dual-write on rows 2–3 is engine-identical to a single "materials/services growth" because
the split percentage only matters when the two growth rates diverge
(`forecast_engine.py:220-242`); `IntraYearEngine` reads the same pairs (`:362-375`), so the
collapse is valid for both engines.

### 2. "Avanzate" accordion

One accordion below the essential table, grouped in four sections (fields keep their existing
input components and write the same columns as today):

- **Ricavi e costi — dettaglio:** Altri ricavi % (`other_revenue_growth_pct`), Affitti %
  (`rent_growth_pct`), the variable/fixed split — both `fixed_*_percentage` and the four split
  growth fields, shown ONLY here. Editing a split growth field decouples it from the essential
  row (see display rule below).
- **Capitale circolante:** DSO / DIO / DPO with the auto-derived base-year value as placeholder
  (existing behavior), plus Crediti oltre % (`receivables_long_growth_pct`) — engine-live but
  today only settable via the AutoGenerator.
- **Stato patrimoniale:** the SP-growth rows (`sp01, sp04, sp08, sp10, sp14, sp16e, sp16f,
  sp16g, sp17d, sp17e, sp17f, sp17g, sp18`), Cessioni (NBV / corrispettivo), Altri finanziatori
  rimborso anni (`altri_finanz_repayment_years`), TFR a INPS (checkbox), Cash sweep (checkbox +
  cassa minima), Ammortamento % materiali/immateriali.
- **Fiscale:** the effective tax rate **displayed as computed** — *"auto: aliquota effettiva da
  anno base ≈ X%"* (X = base-year `ce20/PBT`, computed client-side from the analysis data) —
  with an optional override input writing `tax_rate`. The input stays writable because the
  engine falls back to it when the base-year rate is implausible (`forecast_engine.py:374-390`)
  and the infrannuale flow uses `tax_rate` as its ce20 channel.

**Removed from the form entirely:** the 19 CE-override rows ("DETTAGLIO CONTO ECONOMICO",
`page.tsx:1955-2018`) — absolute P&L edits live on `/forecast/income` only. A short hint with a
link replaces them: *"Per modificare singole voci di CE previsionale vai a CE Previsionale."*

**Divergence display rule (rows 2–3):** when a loaded scenario has `variable_* != fixed_*`
growth (set in Avanzate or by legacy data), the essential cell shows the **variable** value plus
a "personalizzato in Avanzate" badge/tooltip; typing in the essential cell overwrites **both**
fields (re-collapse). No hidden state: the Avanzate split fields always show the true values.

### 3. Save path

- Replace the per-year POST/PUT loop + `POST /generate` (`page.tsx:960-986`) with **one call**:
  `PUT /scenarios/{id}/assumptions` (bulk, `budget_scenarios.py:609`) with `auto_generate=true`,
  via the existing `api.bulkUpsertAssumptions`.
- Because bulk = delete-all + reinsert (`assumptions_service.py:95-97`), the form must **send
  complete rows**: it hydrates every field of the existing assumption rows on load (it already
  fetches them) and merges the user's edits into that full object before sending. This is what
  preserves CE overrides created on `/forecast/income` across an assumptions save.
- **Override clearing becomes explicit:** "Salva e Calcola Previsionale" never clears overrides
  (matches current code behavior; the doc drift resolves in favor of the code). "Ricalcola"
  gains a checkbox *"Azzera le modifiche manuali del CE previsionale"* (default unchecked) that
  maps to `POST /generate?clear_overrides=true`; unchecked, Ricalcola calls plain
  `POST /generate`. CLAUDE.md is updated to the actual semantics.
- The per-year endpoints stay in the backend (other consumers/tests may use them) — only the
  budget page stops calling them.

### 4. Hygiene (rides along, no schema change)

- Remove the 5 dead fields from: the form UI, `frontend/types/api.ts` surfaces where cosmetic,
  and the AutoGenerator row "Crediti/Debiti breve" (`page.tsx:1316`) — that row is deleted
  (its two target columns are dead; `receivables_long_growth_pct` moves to Avanzate as above).
  Backend schemas keep accepting the fields (they're persisted-but-ignored) so old clients and
  stored rows stay valid.
- Scenario creation stops pre-filling the 12 carry-forward CE overrides with base-year values
  (`page.tsx:898-909`) — new scenarios start with all overrides NULL. Existing scenarios with
  stored no-op overrides are untouched (harmless; visible on `/forecast/income` as blue-underline
  overrides, clearable there or via Ricalcola+checkbox).
- The AutoGenerator card stays opt-in (default hidden, as today) and writes only live fields;
  its trend-blend math is unchanged.

### 5. Constraints honored

- `assumptions_service.py:105-188` literal kwargs block: untouched — every field the form sends
  already exists in that list.
- `IntraYearEngine` coupling: `fixed_*_percentage` and the split growth columns remain writable
  (Avanzate) and are still sent on every bulk save with their loaded values.
- No new endpoints (project convention). No component library changes (shadcn/ui as today).

## Edge cases

- **Legacy scenario with var≠fixed growth:** divergence display rule above; saving without
  touching the essential cell preserves the divergent values (full-row hydration).
- **Legacy scenario with stored no-op overrides:** unaffected by this project; they keep being
  sent back on bulk saves (full-row hydration) so behavior is identical pre/post.
- **Scenario with dead-field values stored:** values keep round-tripping through the bulk save
  (hydration sends them back); they're just no longer editable/visible.
- **Bulk save failure inside forecast generation:** the backend returns `success: true` with a
  message even when generation fails (`assumptions_service.py:210-217`, known bug logged in the
  project analysis). The frontend must check `forecast_generated === true` and toast the failure
  message otherwise — do not rely on `success` alone.
- **Duration change (3→5 years):** bulk PUT handles it natively (delete-all + reinsert of the
  years sent) — simpler than today's per-year create/update reconciliation.

## Testing / verification

1. `cd frontend && npm run build` — type-check + build clean.
2. Scripted API round-trip (dev backend, `DEV_USER_ID`): create company+year via
   `POST /financial-years` seed → create scenario → bulk PUT with **only essential fields
   valued** (splits equal, everything else defaults) → `GET /assumptions` asserts
   `variable_materials_growth_pct == fixed_materials_growth_pct`, dead fields at defaults,
   overrides NULL → `GET /analysis` asserts `forecast_years` present.
3. Override-preservation check: PATCH a CE override via `/ce-override`, then bulk-save
   assumptions from the form path, then `GET /assumptions` asserts the override survived.
4. Manual/playwright pass: create scenario (essential only), open Avanzate, set a split
   divergence, verify the badge + re-collapse behavior, run Ricalcola with and without the
   azzera checkbox.

## Files touched

- `frontend/app/budget/page.tsx` — `ScenarioForm` restructure (2 tabs, essential table,
  Avanzate accordion, divergence rule), save-path switch, AutoGenerator row removal, no-op
  override prefill removal. Expect a net size REDUCTION (CE-override rows deleted).
- `frontend/lib/api.ts` — ensure `bulkUpsertAssumptions` is used by the budget page; no new
  endpoints.
- `frontend/types/api.ts` — dead fields stay in the wire interfaces (optional, for round-trip
  compatibility with stored rows) but any UI label maps / form-model constants referencing them
  are deleted.
- `CLAUDE.md` — update the budget workflow section (2-tab form, bulk save, explicit
  clear-overrides semantics).
- No backend files change. (If the frontend's `forecast_generated` check surfaces the
  `success:true`-on-failure bug in practice, fixing `assumptions_service.py:210-217` to return
  an error status is a 5-line follow-up — out of scope here, tracked in the project analysis.)

## Out of scope (follow-ups)

- Dropping the 5 dead DB columns (needs a table-rebuild migration strategy).
- Promoting the AutoGenerator to default-on prefill (approach B) — revisit after this lands.
- Startup-style absolute-driver wizard for existing companies (approach C).
- Journey/navigation fixes (dead-end saves, next-step CTAs) — Project 3.
- Backend `success:true`-on-generation-failure fix (`assumptions_service.py:210-217`).
