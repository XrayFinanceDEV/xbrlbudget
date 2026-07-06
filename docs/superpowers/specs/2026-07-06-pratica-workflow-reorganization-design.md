# Pratica — workflow/UX reorganization

**Date:** 2026-07-06
**Status:** Design approved (pending written-spec review)
**Area:** frontend journey + light backend enablers — Project 3 of the 2026-07-06 reorganization
(see `docs/superpowers/2026-07-06-project-analysis.md` §3; mockups approved by the user:
claude.ai artifact "Pratica — mockup nuovo workflow", version "tre-workflow")

## Problem

The full user journey costs ~40–55 interactions with 8 manual navigation decisions and 2 shell
switches (`infrannuale` wizard stepper vs flat top nav). Structural causes, measured in the
project analysis:

1. **No shared scenario state** — 6 pages each hold a local `selectedScenario` and auto-pick;
   with >1 scenario the user re-selects on every page.
2. **The promote cliff** — `infrannuale/page.tsx:5205-5210` destroys wizard state on
   `router.push("/budget")`; no budget scenario is pre-created; the user rebuilds context by hand.
3. **Dead ends** — `/import` success is a toast; budget save returns to the scenario list;
   nothing points at `/cashflow` or `/report`.
4. **Duplicate surfaces** — 2 import UIs, 2 company lists, 3 CE-editing idioms.
5. **The IV-CEE row layout is hand-maintained in 4 places** (infrannuale consts,
   forecast/balance 81 literal rows, forecast/income 49 rows, report sections); adding one field
   = 3–4 coordinated edits (documented as a manual checklist in CLAUDE.md).
6. `infrannuale/page.tsx` is 5,566 lines, bypasses react-query, holds ~30 `useState`s, and its
   scenario list fires O(companies) API calls.

## Goals

1. One guided shell — the **Pratica** — covering the entire journey, with three distinct
   workflow types, URL-addressable steps, reliable resume.
2. Kill the promote cliff: promote auto-creates the linked draft budget scenario and the stepper
   advances in place.
3. One source of truth for the IV-CEE statement layout, consumed by every view.
4. Decompose the two monolith pages into focused modules.
5. Ship in three phases (C → B → A), each leaving the app fully working.

## Non-goals

- No changes to calculation engines, analysis/cashflow/report endpoints, AI-comments flows.
- No visual redesign (shadcn/slate look stays); no i18n changes.
- Project 2 (assumptions form internals) composes into the Budget step unchanged.
- The legacy Streamlit app is untouched.

## Concept

### The Pratica

A *pratica* is one continuous engagement for a company: a chain of scenarios linked by a new
nullable column **`BudgetScenario.source_scenario_id`** (set by promote; additive migration).
A scenario without an incoming link is the head of its pratica. Legacy scenarios (no links)
each render as independent pratiche — no data backfill needed.

### Three workflow types (chooser on "Nuova pratica")

| # | Type | Steps |
|---|------|-------|
| 1 | **Infrannuale da bilancino** (complete) | Import bilancino → Rettifiche → Confronto → Proiezione → Report Infra → Budget → Previsionale → Rendiconto → Report (9) |
| 2 | **Budget da bilancio ufficiale** | Import bilancio → *(Rettifiche, optional)* → Budget → Previsionale → Rendiconto → Report (5+1) |
| 3 | **Budget startup** | Setup startup → Budget → Previsionale → Rendiconto → Report (5) |

The type is **stored**: a second new nullable column **`BudgetScenario.workflow_type`**
(`"infrannuale" | "bilancio" | "startup"`), set by the chooser at pratica creation (and by
promote on the draft budget scenario, copied from the head). Legacy rows (`NULL`) fall back to a
derivation: `scenario_type == "infrannuale"` → 1, otherwise → 2 (startup pratiche created
before this feature render as workflow 2 — acceptable). The stepper renders only the chosen
type's steps.

**Workflow 2 optional Rettifiche:** the step is always reachable but visually secondary
("facoltativo"); immediately after an import that returned warnings (e.g. `BILANCIO NON
QUADRATO`), the shell routes to it instead of Budget — warnings are read from the import
response (transient; no persistence added).

### URL scheme

`/pratica/[scenarioId]/[step]` where `step` ∈ {`import`, `setup` (workflow 3 only),
`rettifiche`, `confronto`, `proiezione`, `report-infra`, `budget`, `previsionale`,
`rendiconto`, `report`} (plus `/pratica/nuova` for the chooser). `scenarioId` is the pratica **head**; the shell resolves the
chain (head + promoted budget scenario) and maps budget-phase steps onto the linked scenario.
Refresh, deep links, and resume all work because every step is a route; the ~30-`useState`
wizard memory is replaced by URL + react-query + server state (rettifiche and scenario data
already persist server-side).

Step gating reuses the current wizard's `enabled` semantics (a step is reachable when its
prerequisite data exists server-side, e.g. Confronto requires the imported year, Previsionale
requires a generated forecast). The furthest-enabled step is where "Riprendi" lands.

### Home — "Aziende & Pratiche"

Replaces the fork home, `/aziende`, and the wizard's aziende step: one list of companies, each
with its pratiche (type, status pill: bozza / in corso / completata, per-step progress, and
**Riprendi**). Company CRUD (create/edit/delete) lives here as today on `/aziende`.
Backed by extending **`GET /companies?include=scenarios`** (one call replaces the O(companies)
loop at `infrannuale/page.tsx:3436-3454`). Status is derived from the chain: completata when
the (budget) scenario has a generated forecast and the user reached Report; in corso otherwise;
bozza when only the import/setup exists.

### Promote handoff (the cliff fix)

"Conferma e passa al Budget" (Report Infra step) calls `POST /promote`, which — in addition to
today's FinancialYear copy — **creates the draft budget scenario** (`base_year` = promoted
year, `name` = "Budget {y+1}–{y+n}", `scenario_type` = "budget",
`source_scenario_id` = infrannuale scenario id) and returns it in the response. The shell
advances to `/pratica/{head}/budget` with the draft pre-selected. Re-promote reuses the
existing linked scenario if present (no duplicate drafts).

### Navigation coexistence

The Pratica shell is the primary mode. The flat top nav stays as secondary "browse" mode:
its pages (analysis, cashflow, report, forecast, budget list) keep working standalone with
their own scenario pickers for jumping into old data. Old routes redirect:
`/` → home (new), `/aziende` → home, `/infrannuale` → home (or the matching pratica when a
scenario query param is present), `/forecast/income|balance|reclassified` → `/forecast?tab=…`.

## Phasing

### Phase C — quick wins (days)

1. **Next-step CTAs:** import success → "Crea pratica →" (pre-Phase-A: → scenario creation);
   budget "Salva e Calcola" → "Vai al CE Previsionale"; forecast save → "Vai al Rendiconto";
   cashflow → "Vai al Report".
2. **One import surface:** extract the `/import` form into `components/import/ImportPanel.tsx`
   (props: `periodMonths?`, `companyMode`, `onSuccess(result)`); `/import` and the infrannuale
   wizard both render it.
3. **Home "Aziende & Pratiche"** + `GET /companies?include=scenarios` (extends the existing
   endpoint — no new route); `/aziende` becomes a redirect.
4. `ScenarioSelector` replaces the raw `<select>`s in analysis (`:789`) and cashflow (`:94`).

### Phase B — shared foundations (1–2 weeks, mechanical, behavior-preserving)

1. **`frontend/lib/ivcee-layout.ts`** — the single row-schema source for SP + CE: row defs
   (`{ code, label, indent, computed, isTotal, alwaysShow }`), derived-aggregate rules,
   zero-filter/always-show policies, debt creditor groups. Content consolidated from the 4
   existing copies (CLAUDE.md "Shared BS/IS Layout" is the checklist of what must survive).
2. **`<BalanceStatementTable>` / `<IncomeStatementTable>`** (`frontend/components/statements/`)
   with a pluggable edit strategy: `readonly | override-edit (click-to-edit cell, pending
   highlight) | rettifica (blur → double-entry proposal dialog)`. Consumers migrated one view
   at a time: forecast/balance, forecast/income, report sections, then infrannuale Rettifiche /
   Confronto / Proiezione. Per-year `reconcileSubfields` stays a pure lib function applied by
   callers.
3. **Merge `/forecast/*` into one `/forecast` page with tabs** (CE / SP / Riclassificato) —
   they already share `useAnalysis`; old routes redirect.
4. **Decompose the monoliths** (extraction only, no behavior change):
   - from `infrannuale/page.tsx`: `lib/indicators.ts` (scoring, `computeIndicators`,
     `computeCrisisRating`), `lib/rettifiche-rules.ts` (`PROPOSAL_RULES`, counterpart
     categories, `recalcAggregates`, `reconcileSubfields`), `components/infrannuale/
     RettificheTab.tsx`, `ComparisonTable.tsx`, `ProjectionTable.tsx`, `IndicatoriTable.tsx`,
     `StampaContent.tsx`;
   - from `budget/page.tsx`: `components/budget/StartupSetup.tsx`, `ScenariosList.tsx`,
     `AutoGeneratorCard.tsx` (composing with Project 2's `AssumptionsGrid` if already landed).

### Phase A — the shell (the redesign)

1. **Routes** `/pratica/nuova` (chooser) and `/pratica/[scenarioId]/[step]/page.tsx` — a thin
   shell (header: azienda + pratica + stato; stepper; footer prev/next) that composes the
   Phase-B step components. Steps fetch via react-query keyed on scenario/company.
2. **Scenario in URL kills re-selection:** inside a pratica no page shows a scenario picker.
   Browse-mode pages keep theirs.
3. **Promote handoff** (backend + shell wiring as in Concept).
4. **Resume**: home's Riprendi computes the furthest-enabled step from the chain state (same
   gating functions the stepper uses).
5. **Startup integration:** `StartupSetup` becomes workflow 3's "Setup" step; the `startupMode`
   AppContext flag survives for browse mode but the pratica shell derives it from the chain.
6. `/infrannuale` route becomes a redirect; the wizard shell code is deleted.

## Backend touches (all small, no new routers)

- `database/models.py`: `BudgetScenario.source_scenario_id` (nullable Integer FK-like, indexed)
  and `BudgetScenario.workflow_type` (nullable String); `migrate_db.py`: additive `ALTER TABLE`
  for both.
- `backend/app/api/v1/companies.py`: `include=scenarios` query param on `GET /companies`
  (eager-load scenarios per company, id/name/type/base_year/source_scenario_id/has_forecast).
- `backend/app/services/promote_service.py` + `budget_scenarios.py` promote endpoint: create the
  linked draft scenario when `source_scenario_id` chain has none; response gains
  `budget_scenario: {…}`.
- Pydantic schemas + `frontend/types/api.ts` mirrors.
- **Opportunistic hardening** (flagged as reorg tripwires in the analysis):
  - `PUT /adjustments` rejects saves whose BS imbalance exceeds €5 (client reconciles ≤€5
    rounding into sp09 before saving today, so legitimate saves are unaffected) → 400 with a
    clear Italian message.
  - Import endpoints create `original_*_snapshot` explicitly after a successful import; the
    lazy GET-side-effect in `/adjustable` stays as fallback for pre-existing years.

## Edge cases

- **Legacy scenarios** (no `source_scenario_id`): each is its own pratica; infrannuale ones
  whose promoted budget scenario predates the link render as two separate pratiche (acceptable;
  no backfill).
- **Deleting a scenario mid-chain:** deleting the head cascades normally; the linked budget
  scenario survives with a dangling `source_scenario_id` → treated as its own pratica head
  (resolver ignores links to missing ids).
- **Multiple pratiche per company:** unlimited; home lists them newest-first.
- **Workflow-2 import with warnings:** shell routes to the optional Rettifiche step and shows
  the warnings; skipping is allowed.
- **Concurrent promote double-click:** promote is idempotent — existing linked scenario is
  returned, not duplicated.
- **Browse-mode deep link to a step page without pratica context:** step pages are only mounted
  under `/pratica/...`; browse mode uses the existing standalone pages.

## Testing / verification

- **Phase C:** `npm run build`; manual: each CTA lands on the right page with scenario
  preserved; home lists companies+pratiche with one network call.
- **Phase B:** visual parity — for each migrated view, before/after screenshot comparison on
  the same scenario (playwright-frontend-tester agent); `npm run build` per extraction; the
  CLAUDE.md "add a field in 4 places" checklist collapses to 1 place (prove it by adding a
  no-op field in dev and reverting).
- **Phase A:** scripted playwright journey per workflow type: (1) import bilancino →…→ report;
  (2) import bilancio ufficiale → budget →…→ report; (3) startup setup →…→ report. Plus:
  refresh mid-journey resumes at the same step; Riprendi from home lands on the furthest step;
  promote produces the linked draft (assert `source_scenario_id` via API).
- Backend: extend `tests/` with a script asserting the promote-creates-draft contract and the
  `include=scenarios` shape (stdlib urllib pattern, like `tests/verify_assumptions_simplification.py`).

## Files touched (summary)

- **New:** `frontend/app/pratica/**`, `frontend/lib/ivcee-layout.ts`,
  `frontend/lib/indicators.ts`, `frontend/lib/rettifiche-rules.ts`,
  `frontend/components/statements/*`, `frontend/components/infrannuale/*`,
  `frontend/components/import/ImportPanel.tsx`, `frontend/components/budget/*` (Phase-B
  extractions), backend verification script.
- **Modified:** `frontend/app/page.tsx` (home), `frontend/app/import/page.tsx`,
  `frontend/app/forecast/*` (merge), `frontend/app/budget/page.tsx` (extractions + CTA),
  `frontend/app/analysis|cashflow/page.tsx` (selector + CTA), `frontend/components/Navigation.tsx`,
  `frontend/contexts/AppContext.tsx`, `frontend/lib/api.ts`, `frontend/types/api.ts`,
  `database/models.py`, `migrate_db.py`, `backend/app/api/v1/companies.py`,
  `backend/app/api/v1/budget_scenarios.py`, `backend/app/services/promote_service.py`,
  `backend/app/api/v1/financial_years.py` (balance check), `backend/app/api/v1/imports.py`
  (snapshot), `CLAUDE.md`.
- **Deleted (Phase A):** `frontend/app/infrannuale/page.tsx` wizard shell (steps live on as
  components), `frontend/app/aziende/page.tsx` (redirect stub remains).

## Out of scope (follow-ups)

- Consolidating the 4 deprecated-but-live calculation endpoints onto `/analysis`.
- Server-side recompute of infrannuale growth % (stays client-side).
- Unifying the two AI-comments persistence patterns.
- PDF report generation changes.
