# Pratica Workflow Reorganization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One guided "Pratica" shell covering three workflow types (infrannuale completo / budget da bilancio ufficiale / budget startup) with URL-addressable steps, a fixed promote handoff, and a single source of truth for the IV-CEE statement layout.

**Architecture:** Three phases, each shipping working software. Phase C: dead-end CTAs, one import surface, "Aziende & Pratiche" home. Phase B: shared `ivcee-layout` + statement components, merged `/forecast`, monolith decomposition. Phase A: `/pratica/[scenarioId]/[step]` shell composing the Phase-B components, promote auto-creating the linked draft scenario.

**Spec:** `docs/superpowers/specs/2026-07-06-pratica-workflow-reorganization-design.md` (read it before any task). Approved mockups: claude.ai artifact "Pratica — mockup nuovo workflow" (version "tre-workflow").

**Tech Stack:** Next.js 15 App Router + React 19 + TypeScript + shadcn/ui + react-query; FastAPI + SQLAlchemy + SQLite backend.

## Global Constraints

- Phases must land in order C → B → A; within a phase, tasks in order. Every task ends with a clean `cd /home/peter/DEV/budget/frontend && npm run build` and its own commit (directly on `main`; push only when the user says so — pushing triggers Jenkins).
- Behavior-preserving extraction rule (Phase B): a migrated view must render pixel-equivalent output for the same scenario — verify by screenshot comparison before/after (playwright-frontend-tester agent or manual).
- shadcn/ui only, semantic colors, lucide-react icons, Italian UI copy, no emojis (CLAUDE.md).
- Backend: no new routers; extend existing endpoints only. All new columns are additive (`migrate_db.py` pattern). Every endpoint keeps `user_id: str = Depends(get_current_user_id)` scoping.
- Line numbers cited below were verified 2026-07-06; re-anchor by content if drifted (especially if Project 2's plan landed first, which rewrites parts of `budget/page.tsx` — its `ScenariosList`/`StartupSetup` extractions in B6 then apply to the updated file).
- When a task deletes code, the build must prove nothing else referenced it.

---

# PHASE C — Quick wins

### Task C1: Next-step CTAs at every dead end

**Files:**
- Modify: `frontend/app/import/page.tsx` (success handlers around `:80, :97, :118`), `frontend/app/budget/page.tsx` (`handleScenarioSaved` `:122-126`), `frontend/app/forecast/income/page.tsx` (batch-save success, near the `patchCeOverrides` call `:158-160`), `frontend/app/cashflow/page.tsx` (page header area)

**Interfaces:**
- Consumes: `useRouter` from `next/navigation`, `toast` from sonner (both already used in these files).
- Produces: forward navigation affordances; no API changes.

- [ ] **Step 1: Import success CTA**

In `import/page.tsx`, add at the top of the component: `const router = useRouter();` (import from `next/navigation` if missing). Add a success-state block under the import form (state `lastImportOk: boolean`, set true in each of the three success handlers that today only `toast.success`):

```tsx
{lastImportOk && (
  <Alert className="mt-4">
    <CheckCircle2 className="h-4 w-4" />
    <AlertDescription className="flex items-center justify-between gap-4">
      <span>Importazione completata. Prosegui creando uno scenario di budget.</span>
      <Button size="sm" onClick={() => router.push("/budget")}>
        Crea scenario <ArrowRight className="h-4 w-4" />
      </Button>
    </AlertDescription>
  </Alert>
)}
```

(Import `CheckCircle2`, `ArrowRight` from lucide-react; `Alert`/`Button` are already used in the file.)

- [ ] **Step 2: Budget save forwards to Previsionale**

In `budget/page.tsx` `handleScenarioSaved` (`:122-126`), replace the body:

```tsx
  const handleScenarioSaved = () => {
    setEditingScenario(null);
    setActiveTab("list");
    if (selectedCompanyId) invalidateScenarios(selectedCompanyId);
    toast.success("Vai al CE Previsionale per rifinire le voci", {
      action: { label: "CE Previsionale", onClick: () => router.push("/forecast/income") },
    });
  };
```

Add `const router = useRouter();` to `BudgetPage` (import from `next/navigation`).

- [ ] **Step 3: Forecast-income save forwards to Rendiconto; cashflow forwards to Report**

In `forecast/income/page.tsx`, in the batch-save success path (after `invalidateAnalysis`), change the success toast to:

```tsx
      toast.success("Previsionale aggiornato", {
        action: { label: "Vai al Rendiconto", onClick: () => router.push("/cashflow") },
      });
```

In `cashflow/page.tsx`, add a header-row button (next to the existing page header / scenario picker):

```tsx
<Button variant="outline" size="sm" onClick={() => router.push("/report")}>
  Vai al Report <ArrowRight className="h-4 w-4" />
</Button>
```

Add `useRouter` imports where missing.

- [ ] **Step 4: Build + manual click-through**

`npm run build` clean; dev-server: import a file → CTA appears → budget save → toast action lands on `/forecast/income` with the same scenario auto-picked → save → Rendiconto → Report.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/import/page.tsx frontend/app/budget/page.tsx frontend/app/forecast/income/page.tsx frontend/app/cashflow/page.tsx
git commit -m "Pratica C1: CTA 'prossimo passo' su import, budget, previsionale e rendiconto"
```

---

### Task C2: One import surface — `ImportPanel`

**Files:**
- Create: `frontend/components/import/ImportPanel.tsx`
- Modify: `frontend/app/import/page.tsx` (becomes a thin wrapper), `frontend/app/infrannuale/page.tsx` (import tab renders the panel)

**Interfaces:**
- Produces: `<ImportPanel periodMonths={number|null} fixedCompanyId={number|null} onSuccess={(r: ImportResult) => void} />` where `ImportResult` is the existing import response type from `lib/api.ts`. When `periodMonths` is set, the panel locks the type to PDF/XBRL and passes `period_months`; when `fixedCompanyId` is set, the company-mode chooser is hidden.

- [ ] **Step 1: Extract the panel**

Move the whole form body of `import/page.tsx` (the 3-tab XBRL/CSV/PDF chooser `:149-153`, file input, anno fiscale, company create-vs-update mode, submit handlers) into `ImportPanel.tsx` as-is, parameterized by the three props above. The three submit handlers keep calling `importXBRL/importCSV/importPDF` from `lib/api.ts`, threading `periodMonths` into `importPDF`/`importXBRL` when set. On success call `onSuccess(result)` **and** keep the existing toasts.

`import/page.tsx` becomes: page header + `<ImportPanel periodMonths={null} fixedCompanyId={null} onSuccess={() => setLastImportOk(true)} />` (keeping Task C1's CTA).

- [ ] **Step 2: Wizard reuses it**

In `infrannuale/page.tsx`, locate the import step's form JSX (inside `InfraannualePage`, rendered for `activeTab === "import"` — search for the `importPDF(` call at ~`:2825` region and the surrounding form). Replace the wizard's own file/anno/mesi/company form with:

```tsx
<ImportPanel
  periodMonths={periodMonths}
  fixedCompanyId={selectedCompany?.id ?? null}
  onSuccess={(result) => handleImportSuccess(result)}
/>
```

where `handleImportSuccess` is the existing post-import logic (company sync at `:2893`, scenario creation via `createScenarioAndAdvance` `:2825-2839`) refactored to take the import result. The `periodMonths` selector (1–11 months) stays in the wizard above the panel — it is journey state, not import-form state.

- [ ] **Step 3: Build + verify both surfaces**

`npm run build`; manual: full-year import from `/import` works; partial-year import from the wizard still creates the scenario and advances to Rettifiche.

- [ ] **Step 4: Commit**

```bash
git add frontend/components/import/ImportPanel.tsx frontend/app/import/page.tsx frontend/app/infrannuale/page.tsx
git commit -m "Pratica C2: superficie di import unica (ImportPanel riusato da /import e wizard infrannuale)"
```

---

### Task C3: "Aziende & Pratiche" home + `GET /companies?include=scenarios`

**Files:**
- Modify: `backend/app/api/v1/companies.py` (`list_companies` `:24-35`), `backend/app/schemas/company.py`, `frontend/lib/api.ts`, `frontend/types/api.ts`, `frontend/app/page.tsx` (rewrite), `frontend/app/aziende/page.tsx` (redirect stub)

**Interfaces:**
- Produces: `GET /companies?include=scenarios` → `Company[]` where each company gains `scenarios: ScenarioSummary[]`; `ScenarioSummary = { id, name, scenario_type, base_year, period_months, is_active, has_forecast, created_at }`. Frontend: `getCompaniesWithScenarios()` in `lib/api.ts`. The home page at `/`.

- [ ] **Step 1: Backend — extend the endpoint**

In `backend/app/schemas/company.py` add:

```python
class ScenarioSummary(BaseModel):
    id: int
    name: str
    scenario_type: str
    base_year: int
    period_months: Optional[int] = None
    is_active: int
    has_forecast: bool
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CompanyWithScenarios(Company):
    scenarios: List[ScenarioSummary] = []
```

In `companies.py` `list_companies`, add `include: Optional[str] = None` query param; when `include == "scenarios"`:

```python
    if include == "scenarios":
        companies = (
            db.query(models.Company)
            .options(joinedload(models.Company.budget_scenarios)
                     .joinedload(models.BudgetScenario.forecast_years))
            .filter(models.Company.user_id == user_id)
            .offset(skip).limit(limit).all()
        )
        out = []
        for c in companies:
            item = schemas.CompanyWithScenarios.model_validate(c, from_attributes=True)
            item.scenarios = [
                schemas.ScenarioSummary(
                    id=s.id, name=s.name, scenario_type=s.scenario_type,
                    base_year=s.base_year, period_months=s.period_months,
                    is_active=s.is_active, has_forecast=len(s.forecast_years) > 0,
                    created_at=s.created_at,
                )
                for s in sorted(c.budget_scenarios, key=lambda s: s.created_at or 0, reverse=True)
            ]
            out.append(item)
        return out
```

Change the route's `response_model` to `List[schemas.CompanyWithScenarios]` (plain calls return an empty `scenarios` list — backward compatible). Import `joinedload` from `sqlalchemy.orm` and `Optional/List/datetime` as needed. Verify with Swagger (`/docs`) that a company with scenarios returns the summaries.

- [ ] **Step 2: Frontend home**

`lib/api.ts`: add `getCompaniesWithScenarios = () => api.get("/companies", { params: { include: "scenarios" } })` typed with the new `CompanyWithScenarios` interface added to `types/api.ts`.

Rewrite `frontend/app/page.tsx`: page header "Aziende & Pratiche"; react-query fetch of `getCompaniesWithScenarios()`; one `Card` per company (name, sector, edit/delete actions ported from `aziende/page.tsx`), each scenario rendered as a pratica row:

```tsx
{company.scenarios.map((s) => (
  <div key={s.id} className="flex items-center gap-3 border-t border-dashed border-border py-2 text-sm">
    <Badge variant={s.has_forecast ? "default" : "secondary"}>
      {s.has_forecast ? "in corso" : "bozza"}
    </Badge>
    <span className="font-medium">{s.name}</span>
    <span className="text-xs text-muted-foreground">
      {s.scenario_type === "infrannuale" ? `Infrannuale ${s.period_months ?? ""}M` : "Budget"} · base {s.base_year}
    </span>
    <span className="flex-1" />
    <Button size="sm" onClick={() => resume(company.id, s)}>Riprendi</Button>
  </div>
))}
```

`resume(companyId, s)`: set `selectedCompanyId` in AppContext, then `router.push(s.scenario_type === "infrannuale" ? "/infrannuale" : "/budget")` (Phase A upgrades this to `/pratica/...`). "Nuova pratica" button → keeps today's fork behavior: two buttons "Infrannuale" → `/infrannuale`, "Budget/Startup" → `/import` (Phase A replaces with the chooser). Company create form ported from `aziende/page.tsx`.

`aziende/page.tsx` becomes a redirect stub:

```tsx
import { redirect } from "next/navigation";
export default function AziendePage() { redirect("/"); }
```

Update `Navigation.tsx` `MAIN_TABS` (`:26-42`): "Aziende" entry points to `/`; remove the now-dead `/aziende` entry; keep nav hidden-on-`/` rule (`:50`) REMOVED so the nav shows on the new home (the home is now a full page, not a fork screen).

- [ ] **Step 3: Build + verify**

`npm run build`; manual: home lists companies with pratiche in ONE network call; Riprendi lands on the right page with company preselected; company CRUD works; `/aziende` redirects.

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/v1/companies.py backend/app/schemas/company.py frontend/lib/api.ts frontend/types/api.ts frontend/app/page.tsx frontend/app/aziende/page.tsx frontend/components/Navigation.tsx
git commit -m "Pratica C3: home Aziende & Pratiche + GET /companies?include=scenarios (una chiamata, Riprendi)"
```

---

### Task C4: `ScenarioSelector` everywhere

**Files:**
- Modify: `frontend/app/analysis/page.tsx` (`:789` raw `<select>`), `frontend/app/cashflow/page.tsx` (`:94, :223` raw `<select>`s)

- [ ] **Step 1: Swap the raw selects**

Replace each raw `<select>` with the existing `ScenarioSelector` component (used by the forecast pages — check its props there and thread the same `scenarios`, `value`, `onChange`). Keep the pages' local state wiring identical.

- [ ] **Step 2: Build, verify visually, commit**

```bash
cd /home/peter/DEV/budget/frontend && npm run build
git add frontend/app/analysis/page.tsx frontend/app/cashflow/page.tsx
git commit -m "Pratica C4: ScenarioSelector uniforme su Indici e Rendiconto"
```

---

# PHASE B — Shared foundations

### Task B1: `lib/ivcee-layout.ts` — the single row-schema source

**Files:**
- Create: `frontend/lib/ivcee-layout.ts`

**Interfaces:**
- Produces:
  - `type StatementRow = { code: string; label: string; indent: 0|1|2; computed?: boolean; isTotal?: boolean; alwaysShow?: boolean; group?: string }`
  - `BS_ROWS: StatementRow[]` — the full IV-CEE balance-sheet row list (attivo + PN + debiti groups)
  - `CE_ROWS: StatementRow[]` — the full P&L row list incl. EBITDA/EBIT computed rows
  - `DEBT_GROUPS: { key: string; label: string; entro: string; oltre: string }[]` — the 7 creditor groups
  - `computeAggregates(values: Record<string, number>): Record<string, number>` — derived fields (sp04, sp12 from sub-fields, EBITDA, EBIT, totals)
  - `visibleRows(rows: StatementRow[], columns: Record<string, number>[], opts: { showAll?: boolean }): StatementRow[]` — the zero-filter with `alwaysShow` pinning

- [ ] **Step 1: Port the canonical content**

The content ALREADY EXISTS in four places; this task consolidates, it does not invent. Canonical sources, in priority order:
1. `frontend/app/forecast/balance/page.tsx:462-690` — the 81 BS row literals (labels, order, indent, computed flags);
2. `frontend/app/forecast/income/page.tsx:533-741` — the 49 CE row literals;
3. `frontend/app/infrannuale/page.tsx:1276-1408` — `RETTIFICHE_BS_ATTIVO`, `RETTIFICHE_BS_PN`, `DEBT_GROUPS`, `CE_A..CE_E` (cross-check: any row present here but missing in 1/2 gets added, flagged in the commit message);
4. `ALWAYS_SHOW_CODES` and the zero-filter semantics documented in CLAUDE.md "Shared BS/IS Layout".

Port them into `BS_ROWS`/`CE_ROWS` preserving order and labels exactly. `computeAggregates` ports the existing aggregate math from `buildBalanceItemsWithTotals` (`infrannuale/page.tsx:507`) and `buildIncomeItemsWithEbitda` (`:754`) — sp04 = Σ sp04a..e, sp12 = Σ sp12a..h, EBITDA/EBIT formulas, total_debt.

- [ ] **Step 2: Parity assertion script**

Add a throwaway check executed with `npx tsx` (or a temporary page): import `BS_ROWS`/`CE_ROWS`, assert row-code sets equal the literal arrays still in the two forecast pages (copy those arrays into the script for comparison). Run it, fix diffs, delete the script. Record the diff (rows present only in infrannuale) in the commit message.

- [ ] **Step 3: Build + commit**

```bash
cd /home/peter/DEV/budget/frontend && npm run build
git add frontend/lib/ivcee-layout.ts
git commit -m "Pratica B1: ivcee-layout.ts — schema righe SP/CE unico (fonte: forecast pages + consts infrannuale)"
```

---

### Task B2: Statement components + migrate the two forecast tables

**Files:**
- Create: `frontend/components/statements/BalanceStatementTable.tsx`, `frontend/components/statements/IncomeStatementTable.tsx`
- Modify: `frontend/app/forecast/balance/page.tsx`, `frontend/app/forecast/income/page.tsx`

**Interfaces:**
- Produces:
  ```tsx
  type StatementColumn = { key: string; label: string; values: Record<string, number>; editable?: boolean };
  type EditStrategy =
    | { mode: "readonly" }
    | { mode: "override"; pending: Record<string, number|null>; onEdit: (columnKey: string, code: string, value: number|null) => void; persisted?: Record<string, Set<string>> };
  <BalanceStatementTable columns={StatementColumn[]} edit={EditStrategy} showAll?: boolean />
  <IncomeStatementTable  columns={StatementColumn[]} edit={EditStrategy} showAll?: boolean />
  ```
  Both render from `BS_ROWS`/`CE_ROWS` + `computeAggregates` + `visibleRows`. `override` mode reproduces forecast/income's click-to-edit cell (yellow pending highlight, blue persisted underline) as an internal `EditableCell` (port it from `forecast/income/page.tsx:431`).

- [ ] **Step 1: Build the two components**

Implement per the interface: header row from `columns`, body rows from the layout module, editable cells only when `column.editable && edit.mode === "override"` and the row is not computed. Keep the exact CSS classes used today in the forecast tables (copy them — parity requirement).

- [ ] **Step 2: Migrate `/forecast/balance` and `/forecast/income`**

Replace the literal row-map JSX (`balance:462-690`, `income:533-741`) with the components; the pages keep their data fetching, `pendingEdits` state, `FIELD_TO_OVERRIDE` map, and batch-save button — they pass state down via the `override` strategy. Delete the local row arrays and `EditableCell`.

- [ ] **Step 3: Parity check + commit**

Screenshot both pages on the same scenario before and after (playwright-frontend-tester or manual); rows, order, indentation, edit behavior identical. `npm run build`.

```bash
git add frontend/components/statements/ frontend/app/forecast/balance/page.tsx frontend/app/forecast/income/page.tsx
git commit -m "Pratica B2: componenti BalanceStatementTable/IncomeStatementTable; forecast SP+CE migrati (parita visiva)"
```

---

### Task B3: Merge `/forecast/*` into one page with tabs

**Files:**
- Create: `frontend/app/forecast/page.tsx`
- Modify: `frontend/app/forecast/income/page.tsx`, `.../balance/page.tsx`, `.../reclassified/page.tsx` (become redirect stubs), `frontend/components/Navigation.tsx`

- [ ] **Step 1: Compose the merged page**

`forecast/page.tsx`: shared header (PageHeader + `ScenarioSelector`), `Tabs` with `ce` / `sp` / `riclassificato`, `?tab=` search-param controlled. Move the three pages' content bodies (they are now thin after B2) into tab panels; the reclassified body moves as-is. One `useScenarios` + one `useAnalysis` + one `useReclassifiedData` (lazy: fetch reclassified only when its tab activates).

- [ ] **Step 2: Redirects + nav**

The three old pages become `redirect("/forecast?tab=ce")` (`sp`, `riclassificato` respectively). `Navigation.tsx` FORECAST_TABS dropdown collapses to a single "Previsionale" tab pointing at `/forecast`.

- [ ] **Step 3: Build + verify + commit**

Verify: all three tabs render; CE edits + batch save + Rendiconto CTA still work; old URLs redirect.

```bash
git add frontend/app/forecast/ frontend/components/Navigation.tsx
git commit -m "Pratica B3: /forecast unificato a tab (CE, SP, Riclassificato) con redirect dalle vecchie rotte"
```

---

### Task B4: Extract pure libs from `infrannuale/page.tsx`

**Files:**
- Create: `frontend/lib/indicators.ts`, `frontend/lib/rettifiche-rules.ts`
- Modify: `frontend/app/infrannuale/page.tsx` (imports only)

- [ ] **Step 1: Move, don't rewrite**

To `lib/indicators.ts`: `computeIndicators` (`:268`), `scoreIndicator`/`linearScore`/`invertedScore` (`:383+`), `INDICATOR_DEFS` (`:438`), `computeCrisisRating` (`:469`) and the formatters they use (`:106-267` — move only those the moved functions reference; leave view formatters in place). All are pure — export them; the page imports back.

To `lib/rettifiche-rules.ts`: `PROPOSAL_RULES` (`:953`), `COUNTERPART_GROUPS` + `allowedCounterpartCategories` + `NON_POSTABLE_FIELDS` (`:1161-1275`), `recalcAggregates`, `reconcileSubfields` (`:2675-2752`). Export; import back.

- [ ] **Step 2: Build (proves no hidden coupling) + commit**

```bash
cd /home/peter/DEV/budget/frontend && npm run build
git add frontend/lib/indicators.ts frontend/lib/rettifiche-rules.ts frontend/app/infrannuale/page.tsx
git commit -m "Pratica B4: estrazione lib pure (indicators, rettifiche-rules) da infrannuale/page.tsx"
```

---

### Task B5: Extract infrannuale step components

**Files:**
- Create: `frontend/components/infrannuale/RettificheTab.tsx`, `ComparisonTable.tsx`, `ProjectionTable.tsx`, `IndicatoriTable.tsx`, `StampaContent.tsx`, `ExtraAccountingAlerts.tsx`
- Modify: `frontend/app/infrannuale/page.tsx`

- [ ] **Step 1: Move each component to its file**

They are already self-contained function components with explicit props — move verbatim: `RettificheTab` (`:1449-2674`), `ComparisonTable` (`:4222+`), `ProjectionTable` (`:4442+`), `ExtraAccountingAlerts` (`:4707+`), `IndicatoriTable` (`:4758+`), `StampaContent` (`:4938-5566`). Each new file imports what it needs from `lib/indicators.ts`, `lib/rettifiche-rules.ts`, `lib/ivcee-layout.ts` (where B4/B1 moved things) and shadcn. Keep `buildBalanceItemsWithTotals`/`buildIncomeItemsWithEbitda` (`:507-953`) in a small `frontend/components/infrannuale/build-items.ts` since Comparison/Projection/Stampa all use them.

- [ ] **Step 2: Build + wizard smoke + commit**

`npm run build`; run one full infrannuale journey in dev (import → rettifiche edit → confronto → proiezione → stampa) to confirm identical behavior. Expected: `infrannuale/page.tsx` drops to roughly the `InfraannualePage` shell (~1,500 lines).

```bash
git add frontend/components/infrannuale/ frontend/app/infrannuale/page.tsx
git commit -m "Pratica B5: step infrannuale estratti in componenti (Rettifiche, Confronto, Proiezione, Indicatori, Stampa)"
```

---

### Task B6: Extract budget page components

**Files:**
- Create: `frontend/components/budget/StartupSetup.tsx`, `frontend/components/budget/ScenariosList.tsx`, `frontend/components/budget/AutoGeneratorCard.tsx`
- Modify: `frontend/app/budget/page.tsx`

- [ ] **Step 1: Move verbatim**

`StartupSetup` (`:318-593` + its `StartupDriver` types/`buildStartupAssumption` `:258-317`), `ScenariosList` (`:594-718`), `AutoGeneratorCard` (`:1269-1420` + `calculateTrend`/`TREND_ITEMS` `:1240-1267`). If Project 2's plan already landed, these ranges have shifted — extract by symbol name. Imports fixed; page imports back.

- [ ] **Step 2: Build + commit**

```bash
cd /home/peter/DEV/budget/frontend && npm run build
git add frontend/components/budget/ frontend/app/budget/page.tsx
git commit -m "Pratica B6: estrazione componenti budget (StartupSetup, ScenariosList, AutoGeneratorCard)"
```

---

### Task B7: Migrate Confronto + Proiezione onto the shared statement components

**Files:**
- Modify: `frontend/components/infrannuale/ComparisonTable.tsx`, `ProjectionTable.tsx`

- [ ] **Step 1: Confronto → readonly strategy**

`ComparisonTable` renders via `<BalanceStatementTable>`/`<IncomeStatementTable>` with columns = partial / annualized / reference / Δ% (Δ% as a computed extra column — extend `StatementColumn` with `render?: (code) => ReactNode` if needed) and `edit={{mode:"readonly"}}`. Per-year `reconcileSubfields` stays applied by the caller (CLAUDE.md gotcha: never overwrite `annualized_value` supplied by Proiezione).

- [ ] **Step 2: Proiezione → override strategy**

`ProjectionTable` uses the CE component with `edit={{mode:"override", ...}}` wired to `EDITABLE_CE_CODES` (`infrannuale` consts) and its existing override state. `PROJ_COST_CODES_ALL` consistency (must include `ce11b`) now comes from the shared layout — assert it in code.

- [ ] **Step 3: Parity screenshots + build + commit**

Same-scenario before/after screenshots for both tabs; identical rows/numbers.

```bash
git add frontend/components/infrannuale/ComparisonTable.tsx frontend/components/infrannuale/ProjectionTable.tsx
git commit -m "Pratica B7: Confronto e Proiezione sui componenti statement condivisi (parita verificata)"
```

---

### Task B8: Migrate Rettifiche onto the shared components (rettifica strategy)

**Files:**
- Modify: `frontend/components/statements/BalanceStatementTable.tsx`, `IncomeStatementTable.tsx` (add the strategy), `frontend/components/infrannuale/RettificheTab.tsx`

- [ ] **Step 1: Add the `rettifica` edit strategy**

```tsx
| { mode: "rettifica"; corrections: Record<string, number>; onProposal: (code: string, newValue: number) => void; editableCodes: Set<string> }
```

Cells render inputs (always visible — Rettifiche shows every editable row per CLAUDE.md); blur/Enter with a changed value calls `onProposal(code, value)`. The proposal dialog, journal, counterpart picker and persistence STAY in `RettificheTab` — the table only reports the edit intent.

- [ ] **Step 2: Migrate + full rettifiche regression**

RettificheTab renders the two shared tables with the strategy. Manual regression of the whole per-edit flow: edit → proposal dialog with filtered counterparts → confirm → journal entry → delete entry → reset → 20-entry cap toast. Screenshot parity.

- [ ] **Step 3: Build + commit**

```bash
git add frontend/components/statements/ frontend/components/infrannuale/RettificheTab.tsx
git commit -m "Pratica B8: Rettifiche sulla tabella condivisa (strategia rettifica, dialog e journal invariati)"
```

---

# PHASE A — The Pratica shell

### Task A1: DB columns + migration + schemas

**Files:**
- Modify: `database/models.py` (`BudgetScenario`, after `period_months` `:560`), `migrate_db.py` (MIGRATIONS dict), `backend/app/schemas/budget.py` (scenario schemas), `frontend/types/api.ts`

**Interfaces:**
- Produces: `BudgetScenario.source_scenario_id: Optional[int]`, `BudgetScenario.workflow_type: Optional[str]` on model, wire schemas, and TS types.

- [ ] **Step 1: Model + migration**

In `models.py` inside `BudgetScenario` after the `period_months` column:

```python
    # Pratica chain: the infrannuale scenario this budget scenario was promoted
    # from (NULL = head of its own pratica). See spec 2026-07-06-pratica-*.
    source_scenario_id = Column(Integer, nullable=True, index=True)
    # Pratica workflow type chosen at creation: "infrannuale" | "bilancio" | "startup".
    # NULL (legacy) -> derived: scenario_type infrannuale -> 1, else -> 2.
    workflow_type = Column(String(20), nullable=True)
```

In `migrate_db.py` MIGRATIONS add:

```python
    "budget_scenarios": [
        ("source_scenario_id", "INTEGER"),
        ("workflow_type", "VARCHAR(20)"),
    ],
```

(If a `budget_scenarios` key already exists, append the two tuples.) Run `python migrate_db.py` against the dev DB and verify with `sqlite3 financial_analysis.db "PRAGMA table_info(budget_scenarios)"`.

- [ ] **Step 2: Schemas + types**

`backend/app/schemas/budget.py`: add both fields (Optional) to the scenario Create/Read schemas. `frontend/types/api.ts`: add `source_scenario_id?: number | null; workflow_type?: "infrannuale" | "bilancio" | "startup" | null` to `BudgetScenario` and to C3's `ScenarioSummary`. Also extend C3's backend `ScenarioSummary` with the two fields (home needs them for chain grouping in A5).

- [ ] **Step 3: Backend smoke + commit**

Create a scenario via Swagger with `workflow_type: "bilancio"` → persisted and returned.

```bash
git add database/models.py migrate_db.py backend/app/schemas/budget.py backend/app/schemas/company.py backend/app/api/v1/companies.py frontend/types/api.ts
git commit -m "Pratica A1: colonne source_scenario_id + workflow_type (migrazione additiva, schemi, tipi)"
```

---

### Task A2: Promote creates the linked draft budget scenario

**Files:**
- Modify: `backend/app/services/promote_service.py` (`promote_projection_to_financial_year`), `backend/app/api/v1/budget_scenarios.py` (promote endpoint `:408`), `frontend/lib/api.ts` (`promoteProjection` return type)

**Interfaces:**
- Produces: promote response gains `budget_scenario: { id, name, base_year, workflow_type, source_scenario_id }`. Idempotent: an existing linked scenario is returned, not duplicated.

- [ ] **Step 1: Service change**

In `promote_projection_to_financial_year`, before the final `db.commit()` (currently `:80`), add:

```python
    # 7. Pratica handoff: ensure the linked draft budget scenario exists so the
    # shell can advance seamlessly (spec: promote kills the cliff). Idempotent.
    draft = db.query(BudgetScenario).filter(
        BudgetScenario.source_scenario_id == scenario_id
    ).first()
    if not draft:
        n_years = 3
        draft = BudgetScenario(
            company_id=company_id,
            name=f"Budget {target_year + 1}-{target_year + n_years}",
            base_year=target_year,
            scenario_type="budget",
            workflow_type=scenario.workflow_type or "infrannuale",
            source_scenario_id=scenario_id,
            description="Creato automaticamente dalla proiezione infrannuale",
        )
        db.add(draft)
        db.flush()
```

and extend the return dict:

```python
        "budget_scenario": {
            "id": draft.id, "name": draft.name, "base_year": draft.base_year,
            "workflow_type": draft.workflow_type,
            "source_scenario_id": draft.source_scenario_id,
        },
```

- [ ] **Step 2: Endpoint + client**

The promote endpoint already returns the service dict — verify its `response_model` (if any) tolerates the new key; loosen to include `budget_scenario: Optional[dict]` if a schema exists. `lib/api.ts` `promoteProjection` return type gains `budget_scenario?: { id: number; name: string; base_year: number }`.

- [ ] **Step 3: Backend test + commit**

Extend `tests/` with `tests/verify_pratica_backend.py` (same urllib pattern as `tests/verify_assumptions_simplification.py`): seed company+partial year+infrannuale scenario+assumptions+projection via API, promote, assert `budget_scenario.source_scenario_id == scenario_id`; promote again → same `budget_scenario.id` (idempotent). Run it against the dev backend.

```bash
git add backend/app/services/promote_service.py backend/app/api/v1/budget_scenarios.py frontend/lib/api.ts tests/verify_pratica_backend.py
git commit -m "Pratica A2: promote crea/riusa lo scenario budget collegato (bozza) e lo restituisce"
```

---

### Task A3: Pratica domain lib (chain, steps, gating)

**Files:**
- Create: `frontend/lib/pratica.ts`

**Interfaces:**
- Produces:
  ```ts
  export type WorkflowType = "infrannuale" | "bilancio" | "startup";
  export type StepId = "import" | "setup" | "rettifiche" | "confronto" | "proiezione"
                     | "report-infra" | "budget" | "previsionale" | "rendiconto" | "report";
  export const STEPS_BY_TYPE: Record<WorkflowType, StepId[]>;
  export function workflowTypeOf(s: BudgetScenario): WorkflowType;
  export function chainOf(head: BudgetScenario, all: BudgetScenario[]): { head: BudgetScenario; budget?: BudgetScenario };
  export function scenarioForStep(chain: Chain, step: StepId): BudgetScenario;
  export type StepState = "done" | "enabled" | "locked";
  export function stepStates(chain: Chain, probe: PraticaProbe): Record<StepId, StepState>;
  export function furthestStep(states: Record<StepId, StepState>): StepId;
  ```

- [ ] **Step 1: Implement**

```ts
export const STEPS_BY_TYPE: Record<WorkflowType, StepId[]> = {
  infrannuale: ["import", "rettifiche", "confronto", "proiezione", "report-infra",
                "budget", "previsionale", "rendiconto", "report"],
  bilancio:    ["import", "rettifiche", "budget", "previsionale", "rendiconto", "report"],
  startup:     ["setup", "budget", "previsionale", "rendiconto", "report"],
};
// bilancio's "rettifiche" is optional: rendered secondary, never blocks "budget".

export function workflowTypeOf(s: { workflow_type?: string | null; scenario_type: string }): WorkflowType {
  if (s.workflow_type === "infrannuale" || s.workflow_type === "bilancio" || s.workflow_type === "startup")
    return s.workflow_type;
  return s.scenario_type === "infrannuale" ? "infrannuale" : "bilancio"; // legacy fallback (spec)
}

export function chainOf(head: BudgetScenario, all: BudgetScenario[]) {
  const budget = all.find((s) => s.source_scenario_id === head.id);
  return { head, budget };
}

export function scenarioForStep(chain: { head: BudgetScenario; budget?: BudgetScenario }, step: StepId) {
  const budgetSteps: StepId[] = ["budget", "previsionale", "rendiconto", "report"];
  if (budgetSteps.includes(step) && chain.head.scenario_type === "infrannuale")
    return chain.budget ?? chain.head;
  return chain.head;
}
```

`PraticaProbe` is the server-state snapshot the gating needs: `{ hasImportedYear: boolean; hasComparison: boolean; hasProjection: boolean; hasBudgetScenario: boolean; hasBudgetForecast: boolean }` — computed by the shell from react-query data (company years for the scenario's period, forecast presence from `has_forecast` / analysis fetch). `stepStates` maps: `import/setup` done when `hasImportedYear`; `rettifiche/confronto` enabled when import done; `proiezione` enabled when comparison viewed data exists (`hasImportedYear`, mirroring today's wizard gating — comparison is a read, not a mutation); `report-infra` enabled when `hasProjection`; `budget` enabled when `hasBudgetScenario` (infrannuale) or always (bilancio/startup after import/setup); `previsionale/rendiconto/report` enabled when `hasBudgetForecast`. `done` = its own completion signal (the next milestone exists). `furthestStep` = last non-locked step with `done` predecessor, else first enabled.

- [ ] **Step 2: Build + commit**

```bash
cd /home/peter/DEV/budget/frontend && npm run build
git add frontend/lib/pratica.ts
git commit -m "Pratica A3: dominio pratica (catena, passi per workflow, gating, riprendi)"
```

---

### Task A4: The shell — `/pratica/nuova` + `/pratica/[scenarioId]/[step]`

**Files:**
- Create: `frontend/app/pratica/nuova/page.tsx`, `frontend/app/pratica/[scenarioId]/[step]/page.tsx`, `frontend/components/pratica/PraticaShell.tsx`, `frontend/components/pratica/Stepper.tsx`

**Interfaces:**
- Consumes: everything from A3, the Phase-B step components, `ImportPanel` (C2), `StartupSetup`/`ScenarioForm` pieces (B6 / Project 2), the merged forecast tabs (B3), cashflow + report page bodies.
- Produces: the working shell for all three workflows.

- [ ] **Step 1: Stepper component**

```tsx
// frontend/components/pratica/Stepper.tsx
"use client";
import Link from "next/link";
import { Check } from "lucide-react";
import { STEP_LABELS, StepId, StepState } from "@/lib/pratica";

export function Stepper({ scenarioId, steps, states, current }: {
  scenarioId: number; steps: StepId[];
  states: Record<StepId, StepState>; current: StepId;
}) {
  return (
    <nav className="flex items-center gap-1 overflow-x-auto border-b border-border pb-3 mb-4">
      {steps.map((step, i) => {
        const st = states[step];
        const cls =
          step === current ? "bg-primary/10 text-primary"
          : st === "done" ? "text-green-700 dark:text-green-400"
          : st === "locked" ? "text-muted-foreground opacity-50 pointer-events-none"
          : "text-muted-foreground";
        return (
          <span key={step} className="flex items-center gap-1">
            {i > 0 && <span className="text-border px-0.5">—</span>}
            <Link href={`/pratica/${scenarioId}/${step}`}
                  className={`flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-semibold whitespace-nowrap ${cls}`}>
              <span className="flex h-4 w-4 items-center justify-center rounded-full border text-[9px]">
                {st === "done" ? <Check className="h-3 w-3" /> : i + 1}
              </span>
              {STEP_LABELS[step]}
            </Link>
          </span>
        );
      })}
    </nav>
  );
}
```

Add `STEP_LABELS: Record<StepId, string>` to `lib/pratica.ts` (Import / Setup / Rettifiche / Confronto / Proiezione / Report Infra / Budget / Previsionale / Rendiconto / Report — "Rettifiche (facoltativo)" for workflow bilancio, computed by the shell).

- [ ] **Step 2: Shell + step routing**

`PraticaShell.tsx`: fetches the head scenario + company scenarios (react-query), computes chain/type/states (A3), renders header (company · pratica name · status pill), `<Stepper>`, the step body, and a footer with prev/next buttons (`next` disabled while the next step is locked). Step body dispatch:

| StepId | Renders (existing components) |
|---|---|
| `import` | `ImportPanel` (periodMonths from head scenario for infrannuale) |
| `setup` | `StartupSetup` |
| `rettifiche` | `RettificheTab` |
| `confronto` | `ComparisonTable` (+ fetch comparison) |
| `proiezione` | `ProjectionTable` |
| `report-infra` | `IndicatoriTable` + `StampaContent` (with "Conferma e passa al Budget" → `promoteProjection` → on success `router.push(…/budget)`, using A2's returned `budget_scenario`) |
| `budget` | `ScenarioForm` (scenario = chain.budget, preloaded) |
| `previsionale` | the `/forecast` tab content bodies (B3), scenario pinned from chain |
| `rendiconto` | cashflow page body, scenario pinned |
| `report` | report page body, scenario pinned |

For `previsionale`/`rendiconto`/`report`, extract each page's body into a component the page AND the shell both render (same pattern as C2) — pages keep their own scenario pickers, shell passes the pinned scenario as a prop.

`app/pratica/[scenarioId]/[step]/page.tsx` parses params, validates `step` against the workflow's steps (invalid/locked → redirect to `furthestStep`), renders `<PraticaShell head={…} step={…} />`. Inside a pratica NO scenario selector is rendered.

- [ ] **Step 3: Chooser**

`app/pratica/nuova/page.tsx`: three `Card` choices (per mockup M2: Workflow 1 · 9 passi / Workflow 2 · 5 passi / Workflow 3 · 5 passi with the approved copy), a company picker (existing companies + "nuova azienda" via the ImportPanel's create-mode). Selecting: workflow 1 → creates nothing yet, routes to a transient import screen that (as the wizard does today) imports with `period_months` then creates the infrannuale scenario (`workflow_type: "infrannuale"`) and lands on `/pratica/{id}/rettifiche`; workflow 2 → import full-year, then create budget scenario (`workflow_type: "bilancio"`) → `/pratica/{id}/budget` (or `/rettifiche` when the import response carried warnings — pass them via router state); workflow 3 → create via `StartupSetup` (`workflow_type: "startup"`) → `/pratica/{id}/budget`. Home's "Nuova pratica" button now points here.

- [ ] **Step 4: Build + three-journey smoke + commit**

`npm run build`; dev smoke of each workflow start-to-Report (full assertions come in A6).

```bash
git add frontend/app/pratica/ frontend/components/pratica/ frontend/lib/pratica.ts
git commit -m "Pratica A4: shell /pratica/[id]/[passo] con stepper, chooser 3 workflow, promote senza cliff"
```

---

### Task A5: Home chain-aware + redirects + wizard deletion

**Files:**
- Modify: `frontend/app/page.tsx`, `frontend/app/infrannuale/page.tsx` (→ redirect), `frontend/contexts/AppContext.tsx` (startupMode note), `frontend/components/Navigation.tsx`

- [ ] **Step 1: Home upgrade**

Group scenarios into pratiche with `chainOf` (a scenario with `source_scenario_id` pointing to a listed head folds into that head's row — render as "Infrannuale 6M 2025 → Budget 2026–2028"). Riprendi → `/pratica/{head.id}/{furthestStep}` (compute with A3 from `has_forecast` + summary fields; fall back to the first step when unknown). "Nuova pratica" → `/pratica/nuova`.

- [ ] **Step 2: Retire the wizard**

`infrannuale/page.tsx` becomes:

```tsx
import { redirect } from "next/navigation";
export default function InfrannualePage() { redirect("/"); }
```

Delete the now-unreferenced `InfraannualePage` shell code (the step components live in `components/infrannuale/` since B5). `Navigation.tsx`: remove the hide-on-`/infrannuale` rule; nav shows on pratica routes too (the shell renders under it).

- [ ] **Step 3: Build + full grep for dead references + commit**

`npm run build`; `grep -rn "infrannuale/page\|/infrannuale\"" frontend/app frontend/components` — remaining links must point to `/pratica`.

```bash
git add frontend/app/page.tsx frontend/app/infrannuale/page.tsx frontend/components/Navigation.tsx frontend/contexts/AppContext.tsx
git commit -m "Pratica A5: home consapevole della catena, wizard /infrannuale ritirato (redirect), nav unificata"
```

---

### Task A6: Backend hardening + end-to-end verification + docs

**Files:**
- Modify: `backend/app/api/v1/financial_years.py` (PUT `/adjustments` `:331`), `backend/app/api/v1/imports.py`, `CLAUDE.md`, spec status
- Modify: `tests/verify_pratica_backend.py` (extend)

- [ ] **Step 1: Balance check on adjustments**

In `update_adjustments` (`financial_years.py:331`), after applying the incoming BS values and before commit:

```python
    # Reject clearly unbalanced saves (spec: >5 EUR tolerance — the client
    # reconciles sub-5-euro import rounding into sp09 before saving).
    attivo = balance_sheet.total_assets or Decimal("0")
    passivo = balance_sheet.total_liabilities_equity or Decimal("0")
    if abs(attivo - passivo) > Decimal("5"):
        raise HTTPException(
            status_code=400,
            detail=(f"Bilancio non quadrato: attivo {attivo} != passivo {passivo}. "
                    f"Le rettifiche devono essere in partita doppia."),
        )
```

(Use the model's computed totals properties; check their exact names in `database/models.py` — `total_assets` exists per the analysis; find the passivo counterpart, e.g. `total_liabilities_equity`, by grepping the model's `@property` list, and adjust.)

- [ ] **Step 2: Explicit snapshot at import**

In `imports.py`, after each successful import that created/updated a `FinancialYear` (all three endpoints), call a small helper (place it in `backend/app/services/` next to the existing services or reuse the snapshot code from `financial_years.py:307-310` by extracting it into `database/queries.py` as `ensure_original_snapshots(db, fy)`) so `original_bs_snapshot`/`original_is_snapshot` are written at import time. The lazy GET fallback stays.

- [ ] **Step 3: Extend the backend verification script**

Add to `tests/verify_pratica_backend.py`: `include=scenarios` shape assertion (fields incl. `source_scenario_id`, `workflow_type`, `has_forecast`); adjustments 400 on an intentionally unbalanced PUT; snapshot present right after import (GET `/adjustable` returns `rettifiche_log == []` and the original snapshot without triggering creation — verify via a fresh import + direct DB read or a second GET idempotence check). Run it green.

- [ ] **Step 4: Playwright journeys (the Phase-A acceptance gate)**

Dispatch the playwright-frontend-tester agent (or run manually) with the three scripted journeys from the spec:
1. Workflow 1: nuova pratica → import bilancino (use `docs/examples/bilancio cee infra periodo.pdf` or a known partial-year fixture) → rettifica 1 voce → confronto → proiezione → report infra → promote → budget (ipotesi essenziali) → previsionale → rendiconto → report. Assert: stepper states advance; refresh at `proiezione` stays at `proiezione`; home shows the pratica "in corso" then "completata"; promote produced `source_scenario_id` (API check).
2. Workflow 2: nuova pratica → import `docs/examples/DEPI-SRLU-IV-CEE.pdf` → budget → previsionale → rendiconto → report.
3. Workflow 3: startup setup → budget → previsionale → rendiconto → report.

Record pass/fail per assertion in the task output; fix and re-run until green.

- [ ] **Step 5: Docs + spec status + commit**

CLAUDE.md: add a "Pratica shell" section (URL scheme, 3 workflow types, chain columns, promote handoff, browse mode) and update the Frontend Pages list (home, /pratica, /forecast merged, /infrannuale retired). Spec status → `Implemented (see docs/superpowers/plans/2026-07-06-pratica-workflow-reorganization.md)`.

```bash
git add backend/app/api/v1/financial_years.py backend/app/api/v1/imports.py database/queries.py tests/verify_pratica_backend.py CLAUDE.md docs/superpowers/specs/2026-07-06-pratica-workflow-reorganization-design.md
git commit -m "Pratica A6: hardening backend (quadratura rettifiche, snapshot su import), verifiche end-to-end, docs"
```
