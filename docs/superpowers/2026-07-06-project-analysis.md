# Project analysis — XBRL Budget (2026-07-06)

Synthesis of four parallel deep-dives (importers, forecast engine/assumptions, frontend UX,
backend/API) run to ground three planned projects, in order:

1. **Contra-netting overlay** (import fix) — spec exists: `specs/2026-07-06-contra-netting-overlay-design.md`
2. **Budget assumptions simplification** — to be brainstormed/specced
3. **Workflow/UX reorganization** — to be brainstormed/specced

---

## 1. Importers — state and readiness for the contra-netting spec

**Verdict: the spec is implementable as written.** Every anchor it cites exists at the cited
line: `pdf_importer.py:429` (`_dc0` declared-totals fetch), `:445` (winner selection),
`:453-457` (`overlay_debt_typing`), `:467-477` (declared reconcile), `:532-543`
(`enforce_ce_sp_identity`), `:547` (`validate_balance`). Helpers verified:
`_is_fondo_amm` (`situazione_contabile_parser.py:2449`), `_classify_sp_attivo` (`:480`),
`overlay_debt_typing` (`:609`), `_declared_control_totals` (`pdf_extractor_llm.py:2160`),
`_reconcile_trial_to_declared` (`pdf_extractor_llm.py:2235`).

**Planning inputs beyond the spec:**

- **The regression harness does not exist in this tree.** `Test/` is gitignored
  (confidential client bilanci); `tests/debug/` holds only 6 untracked raw PDFs with no
  runner. → `tests/test_contra_netting.py` must ship its own thin corpus runner
  (extract → reconcile → `validate_balance` loop over `tests/debug/` + `docs/examples/612/613`).
- **Exact patch point for spec step 5**: `_reconcile_trial_to_declared`'s total-coverage
  fallback (`pdf_extractor_llm.py:2313-2325`) compares NET extracted totals to GROSS declared
  totals → must reduce the anchor by `_contra_netted` or it manufactures a false
  `_plug_residual` (spurious "QUADRATURA MASCHERATA"). The result-anchored branch
  (`:2286-2311`) is invariant under symmetric netting — safe.
- **`_classify_sp_attivo` returns tags** (`gross_sp02/03/04`), defaulting unknown lines to
  `sp06` — the self-validation gate must sum the full attivo scan, not just the two tags.
- **Scan-order pattern**: check `_is_fondo_amm` before classification (as `_hier_reconstruct`
  `:2492-2503` already does).
- **Adjacent small bug worth fixing while wiring**: `_declared_control_totals` is fetched 3×
  in route C (`:429`, `:472`, `:535`); the `:535` call omits `text=ocr_text`, so the CE↔SP
  arbiter loses its declared anchor on scanned PDFs.
- Netting logic already lives in ≥4 places (build_iv_cee accumulators, best-effort
  `netted_contra`, `_hier_reconstruct`, verifica-per-segno); `net_contra_accounts` is the 5th
  → consolidation is a named follow-up, not in scope.
- Evidence PDFs (`docs/examples/612/613`, `Edile-rating-basso.pdf`) and `tests/debug/` are
  untracked — test fixtures must be committed (or fetched) as part of the plan.

**Tech-debt map (route C):** `situazione_contabile_parser.py` 3,310 LOC / 79 defs,
8 sub-parsers with overlapping heuristics; `pdf_extractor_llm.py` 3,095 LOC / 57 defs;
`import_pdf_balance_sheet` is a ~590-line function. Open issues list in
`docs/import/IMPORT-QUADRATURA-ENGINE.md §7` (budget_405 interleaved gross/fondi, budget_395
DEPI contrapposte, "355-class" zeroed schema…). Route-C test coverage is thin (2 test files).

---

## 2. Budget assumptions — complexity inventory

`BudgetAssumptions` = ~90 columns (`database/models.py:591-725`). The `/budget` page
(`ScenarioForm`, 3 tabs) exposes **27 always-visible numeric rows × N years (81 inputs for
3 years) + 6 checkboxes; ~180 editable cells with detail accordions open.**

**Facts that make simplification cheap:**

- **The model is default-safe by construction**: growth % = 0 → carry-forward; NULL
  days/schedules → auto-derived from base year (DSO/DIO/DPO at `forecast_engine.py:487-505`);
  NULL override → engine calc. An empty row already yields a valid steady-state forecast.
- **The variable/fixed split (6 fields) is mathematically irrelevant** when var growth ==
  fixed growth (`forecast_engine.py:220-242`) — a single materials % + services % is exactly
  equivalent. Frontend already defaults the split to 0% fixed (all-variable).
- **`tax_rate` input is silently ignored** for most companies: the engine prefers the
  base-year effective rate (`forecast_engine.py:374-390`). It must stay *writable* (the
  infrannuale flow uses it as the ce20-override channel) but need not be shown.
- **5 dead columns**: `receivables_short_growth_pct`, `payables_short_growth_pct`,
  `interest_rate_receivables`, `interest_rate_payables`, legacy `investments` — zero engine
  hits. The AutoGenerator's "Crediti/Debiti breve" row writes two of them (visual no-op bug,
  `budget/page.tsx:1316`).
- The 19 CE-override rows on `/budget` duplicate the nicer `/forecast/income` inline editor.
- New-scenario defaults pre-populate 12 carry-forward overrides with base-year values
  (`budget/page.tsx:898-909`) — functional no-ops stored non-NULL (interacts with
  `clear_overrides`).

**High-sensitivity core (front-and-center candidates):** revenue %, materials %, services %,
personnel %, other-costs %, CAPEX € (tangible+intangible), bank repayment years, new
financing €. DSO/DIO/DPO already auto-derive.

**Constraints (must not break):**

- `IntraYearEngine` reads the same row but only a subset (incl. both `fixed_*_percentage` at
  `intra_year_engine.py:362-375`, flat `tax_rate`, `ce14/ce15_override` only) — hide fields in
  UI, don't drop columns.
- The infrannuale frontend converts absolute edits → growth % client-side and writes the same
  columns; ce17 = client-side net; ce20 → `tax_rate` translation.
- `assumptions_service.py:105-188` is a literal kwargs block — any field not listed is
  **silently dropped** on bulk save; bulk = delete-all + reinsert (unsent overrides are wiped).
- Two divergent write paths exist: budget page uses per-year POST/PUT + `/generate`
  (`budget/page.tsx:395,966,974,983`); infrannuale uses bulk PUT. Docs claim bulk everywhere —
  false. Budget page also calls `generateForecast(clearOverrides=false)` — CLAUDE.md claims
  `true` (doc drift; verify intended behavior in project 2).

**Recommended direction (from analysis; to be validated in brainstorm):**
A. "Essential 8 + Avanzate accordion" — pure UI reshuffle, zero backend change (81 → ~24
visible inputs). B. Promote the existing `AutoGeneratorCard` trend-blend to default-on
(one inflation input). C. Startup-style 4-driver wizard generalized to existing companies
(`StartupSetup` proves the pattern, `budget/page.tsx:265-591`). Sequence: A now, B assist,
C later. All frontend-only.

---

## 3. Frontend UX — the 7-step journey

**Measured tedium: ~40-55 interactions, 8 manual navigation decisions, 2 shell switches**
(the infrannuale wizard has its own stepper and hides the global nav; everything after
promote lives in flat tabs).

**Structural failures:**

1. **No shared scenario state.** `AppContext` holds company/year only; 6 pages each keep a
   local `selectedScenario` and auto-pick "preferred" — with >1 scenario the user re-selects
   on every page.
2. **The promote cliff** (`infrannuale/page.tsx:5205-5210`): wizard state destroyed on
   `router.push("/budget")`; no draft budget scenario is pre-created from the promoted year;
   user rebuilds context manually.
3. **Dead ends everywhere**: `/import` success = toast; budget "Salva e Calcola" returns to
   the scenario list instead of forwarding to `/forecast/income`; nothing points to
   `/cashflow` or `/report`.
4. **Duplicate surfaces**: 2 import UIs, 2 company lists, **3 CE-editing idioms** (budget
   growth-% table, infrannuale Proiezione overrides, forecast/income click-to-edit).
5. **IV-CEE row layout hand-maintained in 4 places** (infrannuale consts, forecast/balance 81
   literal rows, forecast/income 49 rows, report sections) — every new field = 3-4 edits.
6. infrannuale/page.tsx (5,566 lines) bypasses react-query entirely; wizard scenario list does
   O(companies) API calls (`:3436-3454`).

**Decomposition map for infrannuale/page.tsx** (extractable units, see UX report for lines):
`lib/indicators.ts` (pure scoring), shared IV-CEE layout module, `lib/rettifiche-rules.ts`,
`RettificheTab` (~1,226 lines), wizard shell + per-step components (~1,467 lines),
`ComparisonTable`/`ProjectionTable`/`IndicatoriTable`, `StampaContent` (~628, overlaps
`components/report/*`).

**Reorganization directions (to be validated in project-3 brainstorm):**
- **C — consolidate entry surfaces + "next step" CTAs** (days): one import surface, merged
  aziende+pratiche home, ~5 one-line forward buttons at dead ends.
- **B — shared statement components + merged `/forecast`** (1-2 wks, mechanical): single
  `lib/ivcee-layout.ts` + `<BalanceStatementTable>`/`<IncomeStatementTable>` with pluggable
  edit strategy; deletes ~1,000+ duplicated lines.
- **A — single "Pratica" journey shell** (the real redesign): scenario in context/URL
  (`/pratica/[scenarioId]/[step]`), one stepper Import → … → Report, promote auto-creates the
  draft budget scenario. Keep flat nav as secondary browse mode.
- Suggested sequencing C → B → A (B enables A).

---

## 4. Backend/API — constraints and tripwires

**Doc/reality drift:** endpoints documented as deprecated are LIVE (`/reclassified`,
`/detailed-cashflow`, `/ratios`, per-year `/calculations/complete` — 4 pages bypass
`/analysis`). Truly dead: per-year forecast GETs, `/forecasts`, several per-year calc
endpoints, `getFinancialYear`/`getBudgetScenario` client fns.

**Three parallel implementations** of "ratios for hist+forecast" (analysis_service,
calculation_service, inline reclassified block `budget_scenarios.py:1061-1177`) + two
near-identical namedtuple serializers with different None semantics. Engine dispatch by
`scenario_type` copy-pasted 3×. `period_months NULL|12` disjunction re-inlined in ≥6 files
despite `queries.py` helpers.

**Backend depends on frontend-computed values** (constrains any reorg):
infrannuale growth % (€→% conversion client-side — backend never sees user intent),
rettifiche double-entry deltas (server is a dumb persistence layer, **no balance check on
save**), AI-comments ctx for infrannuale (client-built; server cannot regenerate alone),
snapshot creation is a side-effect of GET `/adjustable` (skip the GET → lose the snapshot).

**Bugs found (fix opportunistically, tracked here):**
- IDOR: `calculations.py:217/236/255` (liquidity/profitability/solvency) missing ownership
  check — unused by FE but exposed.
- `budget_scenarios.py:1319` logs undefined `scenario_id` in except block.
- `financial_years.py:61-70` duplicate check ignores `period_months` (partial blocks
  full-year creation via this endpoint); DELETE `.first()` picks an arbitrary record.
- `assumptions_service.py:210-217` returns `success: true` when forecast generation failed.
- PATCH `/ce-override` commits overrides before regeneration (inconsistent state on failure).
- Bulk assumptions + ce-override take `Body(...)` as `Any` — no Pydantic validation.
- No startup guard against `DEV_USER_ID` set in production (single shared tenant).
- `ADMIN_API_KEY` compared with `!=` (non-constant-time).

**Migrations are additive-only** (`migrate_db.py`, no versioning, no drop/rename): the
assumptions simplification must abandon deprecated columns in place; UI-level simplification
is strongly preferred over schema change.

---

## 5. Cross-project implications

- **Project 1 (contra-netting)** is self-contained in `importers/` + tests. Include: commit
  test fixtures, patch `_reconcile_trial_to_declared:2313-2325`, fix the `:535` missing
  `text=ocr_text`, ship a self-sufficient corpus runner.
- **Project 2 (assumptions)** should be **frontend + service-defaults only** (no schema
  change): essential-8 view writing var==fixed with split 0, hidden tax_rate, dead fields
  removed from UI, AutoGenerator fixed and possibly promoted. Decide fate of the two write
  paths (per-year vs bulk) and of the pre-populated no-op overrides. Keep IntraYearEngine and
  infrannuale €→% flow untouched.
- **Project 3 (workflow)** should sequence C → B → A. B (shared IV-CEE components) is a
  prerequisite investment that also benefits project 2's UI (the essential/advanced tables can
  be built on the shared components). The promote cliff and scenario-in-context are the two
  highest-value UX fixes. Backend enablers worth folding in: single "companies with scenarios"
  endpoint (kills the O(N) loop), balance check on `PUT /adjustments`, explicit snapshot
  creation.
- **Ordering synergy confirmed**: 1 is independent; 2's UI work should ideally land after (or
  together with) 3's shared-components phase B — coordinate when speccing 3, or keep 2 as a
  pure reshuffle of the existing budget page (safe either way since it's UI-only).
