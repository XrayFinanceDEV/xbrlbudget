# Budget Assumptions Simplification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce the `/budget` scenario form from ~81 always-visible inputs (3-year scenario) to ~9 essential row groups + one "Avanzate" accordion, switch saves to the bulk PUT endpoint, and remove dead-field/no-op-override noise — zero backend change.

**Architecture:** A config-driven `AssumptionsGrid` component (rows defined as data in `assumption-rows.ts`) replaces the two hand-rolled ~1,100-line tables (`CEAssumptionsTable`, `SPAssumptionsTable`). `ScenarioForm` goes to 2 tabs (Informazioni / Ipotesi); the Ipotesi tab renders the essential grid + a 4-section Avanzate accordion built from the same component. Saves collapse to one `bulkUpsertAssumptions` call with full-row hydration.

**Spec:** `docs/superpowers/specs/2026-07-06-budget-assumptions-simplification-design.md` (read it before starting any task).

**Tech Stack:** Next.js 15 + React 19 + TypeScript, shadcn/ui, existing `frontend/lib/api.ts` client. Verification: `npm run build` (no FE unit-test infra exists) + a backend API round-trip script.

## Global Constraints

- **No backend file changes** (except the verification script under `tests/`). No new endpoints. No DB/schema change.
- shadcn/ui components only, semantic colors (`text-foreground`, `bg-card`, …), lucide-react icons, no emojis (CLAUDE.md).
- UI copy in Italian.
- Dead fields (`receivables_short_growth_pct`, `payables_short_growth_pct`, `interest_rate_receivables`, `interest_rate_payables`, legacy `investments`) keep round-tripping through hydration (stored values preserved) but get **no UI input anywhere**.
- The dual-write collapse (Materie/Servizi % → both `variable_*` and `fixed_*` growth) is engine-identical only if BOTH fields are written on every essential edit — never write one without the other from the essential rows.
- `IntraYearEngine` reads `fixed_*_percentage` and the split growths — they must stay writable in Avanzate and be sent on every bulk save.
- Verification commands: `cd /home/peter/DEV/budget/frontend && npm run build` after every task; commit per task. Commit directly to `main`; push only at the end or on user request (push triggers the Jenkins build).
- Existing helpers to reuse in `budget/page.tsx`: `fmtPct`, `getHistoricalCEValue`, `formatCurrency`, `getErrorMessage`, `updateAssumption` callback signature `(year, field, value: number | boolean | null)`.

---

### Task 1: Row-definition module (`assumption-rows.ts`)

**Files:**
- Create: `frontend/components/budget/assumption-rows.ts`

**Interfaces:**
- Produces (consumed by Tasks 2–3):
  - `type AssumptionRowDef = { key: string; label: string; tooltip?: string; kind: "pct" | "eur" | "years" | "days" | "bool"; fields: string[]; historicalField?: string; divergenceField?: string; nullable?: boolean; autoPlaceholder?: "dso" | "dio" | "dpo"; step?: string; min?: number; max?: number }`
  - `ESSENTIAL_ROWS: AssumptionRowDef[]` (the 9 spec row groups, 11 rows)
  - `ADVANCED_GROUPS: { title: string; rows: AssumptionRowDef[] }[]` (4 sections)
  - `computeEffectiveTaxRate(income: IncomeStatement): number | null`
  - `computeAutoDays(kind: "dso" | "dio" | "dpo", income: IncomeStatement | undefined, balance: BalanceSheet | undefined): number | null`

- [ ] **Step 1: Create the module**

Create `frontend/components/budget/assumption-rows.ts`:

```typescript
// Config-driven row definitions for the budget assumptions form.
// Spec: docs/superpowers/specs/2026-07-06-budget-assumptions-simplification-design.md
// A row with fields.length > 1 DUAL-WRITES the same value into every listed
// column (Materie/Servizi %: variable == fixed growth makes the fixed/variable
// split mathematically irrelevant — see forecast_engine.py:220-242).
import type { BalanceSheet, IncomeStatement } from "@/types/api";

export type AssumptionRowDef = {
  key: string;
  label: string;
  tooltip?: string;
  kind: "pct" | "eur" | "years" | "days" | "bool";
  /** columns written; >1 = dual-write the same value into each */
  fields: string[];
  /** CE/BS field rendered in the read-only historical columns */
  historicalField?: string;
  /** when set: show a "personalizzato in Avanzate" badge if
   *  assumptions[divergenceField] !== assumptions[fields[0]] */
  divergenceField?: string;
  /** empty input maps to null instead of 0 (auto/constant semantics) */
  nullable?: boolean;
  /** placeholder shows the auto-derived base-year value */
  autoPlaceholder?: "dso" | "dio" | "dpo";
  step?: string;
  min?: number;
  max?: number;
};

const pct = (over: Partial<AssumptionRowDef>): AssumptionRowDef =>
  ({ kind: "pct", step: "0.1", min: -100, max: 100, ...over } as AssumptionRowDef);

export const ESSENTIAL_ROWS: AssumptionRowDef[] = [
  pct({ key: "ricavi", label: "Ricavi %", historicalField: "ce01_ricavi_vendite",
        fields: ["revenue_growth_pct"],
        tooltip: "Variazione % dei ricavi rispetto all'anno precedente di piano" }),
  pct({ key: "materie", label: "Materie prime %", historicalField: "ce05_materie_prime",
        fields: ["variable_materials_growth_pct", "fixed_materials_growth_pct"],
        divergenceField: "fixed_materials_growth_pct",
        tooltip: "Variazione % dei costi per materie. Quote variabile/fissa distinte in Avanzate" }),
  pct({ key: "servizi", label: "Servizi %", historicalField: "ce06_servizi",
        fields: ["variable_services_growth_pct", "fixed_services_growth_pct"],
        divergenceField: "fixed_services_growth_pct",
        tooltip: "Variazione % dei costi per servizi. Quote variabile/fissa distinte in Avanzate" }),
  pct({ key: "personale", label: "Personale %", historicalField: "ce08_costi_personale",
        fields: ["personnel_growth_pct"] }),
  pct({ key: "altri-costi", label: "Altri costi (oneri diversi) %",
        historicalField: "ce12_oneri_diversi", fields: ["other_costs_growth_pct"] }),
  { key: "capex-mat", label: "Investimenti materiali €", kind: "eur",
    fields: ["tangible_investments"], min: 0, step: "1000" },
  { key: "capex-imm", label: "Investimenti immateriali €", kind: "eur",
    fields: ["intangible_investments"], min: 0, step: "1000" },
  { key: "rimborso-banche", label: "Rimborso debiti bancari (anni)", kind: "years",
    fields: ["existing_debt_repayment_years"], nullable: true, min: 0, max: 30,
    tooltip: "Anni di rimborso del debito bancario esistente. Vuoto = debito costante" },
  { key: "fin-importo", label: "Nuovo finanziamento €", kind: "eur",
    fields: ["financing_amount"], min: 0, step: "1000" },
  { key: "fin-durata", label: "Nuovo finanziamento: durata (anni)", kind: "years",
    fields: ["financing_duration_years"], min: 0, max: 30 },
  pct({ key: "fin-tasso", label: "Nuovo finanziamento: tasso %",
        fields: ["financing_interest_rate"], min: 0, max: 30 }),
];

export const ADVANCED_GROUPS: { title: string; rows: AssumptionRowDef[] }[] = [
  {
    title: "Ricavi e costi — dettaglio",
    rows: [
      pct({ key: "altri-ricavi", label: "Altri ricavi %",
            historicalField: "ce04_altri_ricavi", fields: ["other_revenue_growth_pct"] }),
      pct({ key: "affitti", label: "Godimento beni di terzi %",
            historicalField: "ce07_godimento_beni", fields: ["rent_growth_pct"] }),
      pct({ key: "quota-fissa-mat", label: "% quota fissa materie",
            fields: ["fixed_materials_percentage"], min: 0, max: 100, step: "1",
            tooltip: "Quota di costi materie che NON scala col variabile. Rilevante solo se le due crescite divergono" }),
      pct({ key: "quota-fissa-serv", label: "% quota fissa servizi",
            fields: ["fixed_services_percentage"], min: 0, max: 100, step: "1" }),
      pct({ key: "var-materie", label: "Var. % costi variabili materie",
            fields: ["variable_materials_growth_pct"] }),
      pct({ key: "fix-materie", label: "Var. % costi fissi materie",
            fields: ["fixed_materials_growth_pct"] }),
      pct({ key: "var-servizi", label: "Var. % costi variabili servizi",
            fields: ["variable_services_growth_pct"] }),
      pct({ key: "fix-servizi", label: "Var. % costi fissi servizi",
            fields: ["fixed_services_growth_pct"] }),
    ],
  },
  {
    title: "Capitale circolante",
    rows: [
      { key: "dso", label: "Giorni incasso clienti (DSO)", kind: "days",
        fields: ["dso_days"], nullable: true, autoPlaceholder: "dso", min: 0, max: 365 },
      { key: "dio", label: "Giorni rotazione magazzino (DIO)", kind: "days",
        fields: ["dio_days"], nullable: true, autoPlaceholder: "dio", min: 0, max: 365 },
      { key: "dpo", label: "Giorni pagamento fornitori (DPO)", kind: "days",
        fields: ["dpo_days"], nullable: true, autoPlaceholder: "dpo", min: 0, max: 365 },
      pct({ key: "crediti-oltre", label: "Crediti oltre 12 mesi %",
            fields: ["receivables_long_growth_pct"] }),
    ],
  },
  {
    title: "Stato patrimoniale",
    rows: [
      pct({ key: "sp01", label: "Crediti verso soci %", fields: ["sp01_growth_pct"], nullable: true }),
      pct({ key: "sp04", label: "Immobilizzazioni finanziarie %", fields: ["sp04_growth_pct"], nullable: true }),
      pct({ key: "sp08", label: "Attività finanziarie %", fields: ["sp08_growth_pct"], nullable: true }),
      pct({ key: "sp10", label: "Ratei e risconti attivi %", fields: ["sp10_growth_pct"], nullable: true }),
      pct({ key: "sp14", label: "Fondi per rischi e oneri %", fields: ["sp14_growth_pct"], nullable: true }),
      pct({ key: "sp16e", label: "Debiti tributari entro %", fields: ["sp16e_growth_pct"], nullable: true }),
      pct({ key: "sp16f", label: "Debiti previdenziali entro %", fields: ["sp16f_growth_pct"], nullable: true }),
      pct({ key: "sp16g", label: "Altri debiti entro %", fields: ["sp16g_growth_pct"], nullable: true }),
      pct({ key: "sp17d", label: "Debiti tributari oltre %", fields: ["sp17d_growth_pct"], nullable: true }),
      pct({ key: "sp17e", label: "Debiti previdenziali oltre %", fields: ["sp17e_growth_pct"], nullable: true }),
      pct({ key: "sp17f", label: "Altri debiti oltre %", fields: ["sp17f_growth_pct"], nullable: true }),
      pct({ key: "sp17g", label: "Altri debiti oltre (residuali) %", fields: ["sp17g_growth_pct"], nullable: true }),
      pct({ key: "sp18", label: "Ratei e risconti passivi %", fields: ["sp18_growth_pct"], nullable: true }),
      { key: "cessioni-nbv", label: "Cessioni: valore contabile netto €", kind: "eur",
        fields: ["asset_disposal_nbv"], nullable: true, min: 0, step: "1000" },
      { key: "cessioni-prezzo", label: "Cessioni: corrispettivo €", kind: "eur",
        fields: ["asset_disposal_proceeds"], nullable: true, min: 0, step: "1000" },
      { key: "altri-finanz", label: "Rimborso altri finanziatori (anni)", kind: "years",
        fields: ["altri_finanz_repayment_years"], nullable: true, min: 0, max: 30 },
      pct({ key: "amm-mat", label: "Ammortamento nuovi investimenti materiali %",
            fields: ["depreciation_rate"], min: 0, max: 100, step: "1" }),
      pct({ key: "amm-imm", label: "Ammortamento nuovi investimenti immateriali %",
            fields: ["depreciation_rate_intangible"], min: 0, max: 100, step: "1" }),
      { key: "tfr-inps", label: "TFR versato a INPS/fondi (accantonamento sospeso)",
        kind: "bool", fields: ["tfr_accrual_suspended"] },
      { key: "cash-sweep", label: "Cash sweep (usa cassa in eccesso per rimborsare debito)",
        kind: "bool", fields: ["cash_sweep_enabled"] },
      { key: "cash-sweep-min", label: "Cash sweep: cassa minima €", kind: "eur",
        fields: ["cash_sweep_min_cash"], nullable: true, min: 0, step: "1000" },
    ],
  },
  {
    title: "Fiscale",
    rows: [
      pct({ key: "tax", label: "Aliquota fiscale % (override)",
            fields: ["tax_rate"], min: 0, max: 100,
            tooltip: "Il motore usa l'aliquota EFFETTIVA dell'anno base quando plausibile; questo valore è il fallback" }),
    ],
  },
];

const num = (v: string | number | null | undefined): number =>
  typeof v === "number" ? v : parseFloat(String(v ?? "0")) || 0;

/** Effective base-year tax rate (ce20 / PBT), or null when not derivable.
 *  Mirrors the engine's preference (forecast_engine.py:374-390). */
export function computeEffectiveTaxRate(income: IncomeStatement): number | null {
  const vp = num(income.ce01_ricavi_vendite) + num(income.ce02_variazioni_rimanenze)
    + num(income.ce03_lavori_interni) + num(income.ce03a_incrementi_immobilizzazioni)
    + num(income.ce04_altri_ricavi);
  const costs = num(income.ce05_materie_prime) + num(income.ce06_servizi)
    + num(income.ce07_godimento_beni) + num(income.ce08_costi_personale)
    + num(income.ce09_ammortamenti) + num(income.ce10_var_rimanenze_mat_prime)
    + num(income.ce11_accantonamenti) + num(income.ce12_oneri_diversi);
  const fin = num(income.ce13_proventi_partecipazioni) + num(income.ce14_altri_proventi_finanziari)
    - num(income.ce15_oneri_finanziari) + num(income.ce16_utili_perdite_cambi)
    + num(income.ce17_rettifiche_attivita_fin)
    + num(income.ce18_proventi_straordinari) - num(income.ce19_oneri_straordinari);
  const pbt = vp - costs + fin;
  const tax = num(income.ce20_imposte);
  if (pbt <= 0 || tax <= 0) return null;
  const rate = (tax / pbt) * 100;
  return rate > 0 && rate <= 60 ? Math.round(rate * 10) / 10 : null;
}

/** Auto-derived turnover days from the base year — same formulas the engine
 *  applies when the field is NULL (forecast_engine.py:487-505). */
export function computeAutoDays(
  kind: "dso" | "dio" | "dpo",
  income: IncomeStatement | undefined,
  balance: BalanceSheet | undefined,
): number | null {
  if (!income || !balance) return null;
  const revenue = num(income.ce01_ricavi_vendite);
  const purchases = num(income.ce05_materie_prime) + num(income.ce06_servizi);
  let numerator = 0;
  let denominator = 0;
  if (kind === "dso") { numerator = num(balance.sp06_crediti_breve); denominator = revenue; }
  if (kind === "dio") { numerator = num(balance.sp05_rimanenze); denominator = revenue; }
  if (kind === "dpo") { numerator = num(balance.sp16d_debiti_fornitori_breve); denominator = purchases; }
  if (denominator <= 0) return null;
  return Math.round((numerator / denominator) * 360);
}
```

- [ ] **Step 2: Type-check**

Run: `cd /home/peter/DEV/budget/frontend && npm run build`
Expected: build succeeds. If `sp16d_debiti_fornitori_breve` or any CE field name mismatches `types/api.ts`, fix the name against `frontend/types/api.ts` (grep for it) — the DB field names are authoritative.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/budget/assumption-rows.ts
git commit -m "Budget semplificazione 1/6: definizioni righe ipotesi (essenziali + Avanzate) config-driven"
```

---

### Task 2: Generic `AssumptionsGrid` component

**Files:**
- Create: `frontend/components/budget/AssumptionsGrid.tsx`

**Interfaces:**
- Consumes: `AssumptionRowDef`, `computeAutoDays` (Task 1); `BudgetAssumptionsCreate` from `types/api`.
- Produces: `<AssumptionsGrid rows historicalYears forecastYears historicalData assumptions onUpdate />` — used by Task 3 for both the essential table and every Avanzate section.

- [ ] **Step 1: Create the component**

Create `frontend/components/budget/AssumptionsGrid.tsx`:

```tsx
"use client";

// Generic assumptions table: rows are data (AssumptionRowDef), columns are
// read-only historical years + editable forecast years. Replaces the
// hand-rolled CEAssumptionsTable/SPAssumptionsTable row JSX.
import { Info } from "lucide-react";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import type { BalanceSheet, BudgetAssumptionsCreate, IncomeStatement } from "@/types/api";
import { AssumptionRowDef, computeAutoDays } from "./assumption-rows";

type Historical = Record<number, { income: IncomeStatement; balance: BalanceSheet }>;

const INPUT_CLS =
  "w-full px-2 py-1 text-xs border border-primary/50 rounded text-center bg-card " +
  "text-foreground font-medium focus:outline-none focus:ring-2 focus:ring-primary";

function formatHistoricalCell(row: AssumptionRowDef, data?: { income: IncomeStatement }): string {
  if (!row.historicalField || !data?.income) return "—";
  const raw = (data.income as unknown as Record<string, string>)[row.historicalField];
  const v = parseFloat(raw ?? "");
  if (isNaN(v)) return "—";
  return new Intl.NumberFormat("it-IT", { maximumFractionDigits: 0 }).format(v);
}

export function AssumptionsGrid({
  rows,
  historicalYears,
  forecastYears,
  historicalData,
  assumptions,
  onUpdate,
  showHistorical = true,
}: {
  rows: AssumptionRowDef[];
  historicalYears: number[];
  forecastYears: number[];
  historicalData: Historical;
  assumptions: Record<number, Partial<BudgetAssumptionsCreate>>;
  onUpdate: (year: number, field: string, value: number | boolean | null) => void;
  showHistorical?: boolean;
}) {
  const histCols = showHistorical ? historicalYears : [];
  const baseYear = historicalYears[historicalYears.length - 1];

  const valueOf = (year: number, row: AssumptionRowDef) => {
    const v = (assumptions[year] as Record<string, unknown> | undefined)?.[row.fields[0]];
    return v === null || v === undefined ? "" : String(v);
  };

  const writeAll = (year: number, row: AssumptionRowDef, value: number | boolean | null) => {
    for (const field of row.fields) onUpdate(year, field, value);
  };

  const diverges = (year: number, row: AssumptionRowDef): boolean => {
    if (!row.divergenceField) return false;
    const a = assumptions[year] as Record<string, unknown> | undefined;
    return a !== undefined && a[row.fields[0]] !== a[row.divergenceField];
  };

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-border border border-border">
        <thead className="bg-muted">
          <tr>
            <th className="px-3 py-2 text-left text-xs font-bold text-foreground uppercase tracking-wider border-r border-border sticky left-0 bg-muted z-10" style={{ minWidth: "300px" }}>
              Ipotesi
            </th>
            {histCols.map((year) => (
              <th key={year} className="px-3 py-2 text-center text-xs font-bold text-foreground uppercase border-r border-border" style={{ minWidth: "110px" }}>
                {year}
              </th>
            ))}
            {forecastYears.map((year) => (
              <th key={year} className="px-3 py-2 text-center text-xs font-bold text-primary uppercase border-r border-border bg-primary/10" style={{ minWidth: "110px" }}>
                {year}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="bg-card divide-y divide-border">
          {rows.map((row) => (
            <tr key={row.key} className="hover:bg-muted/50">
              <td className="px-3 py-2 text-xs text-foreground border-r border-border sticky left-0 bg-card z-10">
                <div className="font-medium flex items-center gap-1">
                  {row.label}
                  {row.tooltip && (
                    <span title={row.tooltip}>
                      <Info className="h-3.5 w-3.5 text-muted-foreground cursor-help flex-shrink-0" />
                    </span>
                  )}
                </div>
              </td>
              {histCols.map((year) => (
                <td key={year} className="px-3 py-2 text-xs text-center text-muted-foreground border-r border-border bg-muted/50">
                  {formatHistoricalCell(row, historicalData[year])}
                </td>
              ))}
              {forecastYears.map((year) => (
                <td key={year} className="px-2 py-2 border-r border-border bg-primary/10">
                  {row.kind === "bool" ? (
                    <div className="flex justify-center">
                      <Checkbox
                        checked={Boolean((assumptions[year] as Record<string, unknown> | undefined)?.[row.fields[0]])}
                        onCheckedChange={(checked) => writeAll(year, row, checked === true)}
                      />
                    </div>
                  ) : (
                    <div className="relative">
                      <input
                        type="number"
                        step={row.step ?? "1"}
                        min={row.min}
                        max={row.max}
                        value={valueOf(year, row)}
                        placeholder={
                          row.autoPlaceholder
                            ? `auto: ${computeAutoDays(row.autoPlaceholder, historicalData[baseYear]?.income, historicalData[baseYear]?.balance) ?? "—"}`
                            : row.nullable ? "auto" : "0"
                        }
                        onChange={(e) => {
                          const raw = e.target.value;
                          if (raw === "") {
                            writeAll(year, row, row.nullable ? null : 0);
                          } else {
                            const v = parseFloat(raw);
                            writeAll(year, row, isNaN(v) ? (row.nullable ? null : 0) : v);
                          }
                        }}
                        className={INPUT_CLS}
                      />
                      {diverges(year, row) && (
                        <Badge
                          variant="outline"
                          className="absolute -top-2 -right-1 px-1 py-0 text-[9px]"
                          title="Le crescite variabile/fissa divergono: valori distinti in Avanzate. Digitando qui vengono riallineate."
                        >
                          A
                        </Badge>
                      )}
                    </div>
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

Run: `cd /home/peter/DEV/budget/frontend && npm run build`
Expected: build succeeds (component unused so far — that's fine).

- [ ] **Step 3: Commit**

```bash
git add frontend/components/budget/AssumptionsGrid.tsx
git commit -m "Budget semplificazione 2/6: componente AssumptionsGrid generico (righe da config, badge divergenza, placeholder auto-DSO/DIO/DPO)"
```

---

### Task 3: Restructure `ScenarioForm` — 2 tabs, essential grid + Avanzate

**Files:**
- Modify: `frontend/app/budget/page.tsx`
  - `ScenarioForm` (`:719-1153`): tab shell, defaults block, table rendering
  - Delete: `CEAssumptionsTable` (`:1523-2167`), `SPAssumptionsTable` (`:2168-2636`), `AssumptionsTableHeader` (`:1493-1521`), and the `getHistoricalCEValue`/CE-detail helpers that become unused (verify with the build)
  - `BudgetPage` (`:119`, `:153`): tab-name updates

**Interfaces:**
- Consumes: `AssumptionsGrid`, `ESSENTIAL_ROWS`, `ADVANCED_GROUPS`, `computeEffectiveTaxRate` (Tasks 1–2).
- Produces: `ScenarioForm` with `activeTab` ∈ {"info", "ipotesi"}. Save path unchanged in this task (still per-year — switched in Task 4) so the app stays working at every commit.

- [ ] **Step 1: Update tab plumbing in `BudgetPage`**

- `:119` `handleEditScenario`: keep `setActiveTab("info")` (unchanged, still valid).
- `:153` startup `onCreated`: change `setActiveTab("sp")` → `setActiveTab("ipotesi")`.

- [ ] **Step 2: Replace the `ScenarioForm` tab shell and content**

In `ScenarioForm`, add imports at the top of `page.tsx`:

```tsx
import { AssumptionsGrid } from "@/components/budget/AssumptionsGrid";
import { ADVANCED_GROUPS, ESSENTIAL_ROWS, computeEffectiveTaxRate } from "@/components/budget/assumption-rows";
import Link from "next/link";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
```

(If `components/ui/accordion.tsx` does not exist, install it first: `npx shadcn@latest add accordion`.)

Replace the `TabsList` (`:1000-1013`) with two triggers:

```tsx
        <TabsList className="mb-4">
          <TabsTrigger value="info" className="gap-1.5">
            <ClipboardList className="h-4 w-4" />
            Informazioni
          </TabsTrigger>
          <TabsTrigger value="ipotesi" className="gap-1.5">
            <FileSpreadsheet className="h-4 w-4" />
            Ipotesi
          </TabsTrigger>
        </TabsList>
```

Replace the `ce` and `sp` `TabsContent` blocks (`:1106-1134`) with ONE `ipotesi` block:

```tsx
        <TabsContent value="ipotesi">
          <div className="space-y-4">
            {startup && (
              <StartupEconomicsRecap
                baseYear={baseYear}
                forecastYears={forecastYears}
                historicalData={historicalData}
                assumptions={assumptions}
              />
            )}

            <AssumptionsGrid
              rows={startup
                ? ESSENTIAL_ROWS.filter((r) => r.kind !== "pct" || r.key.startsWith("fin-"))
                : ESSENTIAL_ROWS}
              historicalYears={historicalYears}
              forecastYears={forecastYears}
              historicalData={historicalData}
              assumptions={assumptions}
              onUpdate={updateAssumption}
            />

            <p className="text-xs text-muted-foreground">
              Per modificare singole voci del CE previsionale (valori assoluti) vai a{" "}
              <Link href="/forecast/income" className="underline text-primary">
                CE Previsionale
              </Link>
              .
            </p>

            <Accordion type="single" collapsible>
              <AccordionItem value="avanzate">
                <AccordionTrigger className="text-sm font-semibold">
                  Avanzate
                </AccordionTrigger>
                <AccordionContent className="space-y-6">
                  {ADVANCED_GROUPS.map((group) => (
                    <div key={group.title}>
                      <h4 className="text-xs font-bold uppercase text-muted-foreground mb-2">
                        {group.title}
                      </h4>
                      {group.title === "Fiscale" && (
                        <p className="text-xs text-muted-foreground mb-2">
                          {(() => {
                            const eff = historicalData[baseYear]?.income
                              ? computeEffectiveTaxRate(historicalData[baseYear].income)
                              : null;
                            return eff !== null
                              ? `Aliquota effettiva dall'anno base ${baseYear}: ≈ ${eff}% (usata automaticamente dal motore)`
                              : "Aliquota effettiva dall'anno base non derivabile: il motore usa il valore qui sotto";
                          })()}
                        </p>
                      )}
                      <AssumptionsGrid
                        rows={group.rows}
                        historicalYears={historicalYears}
                        forecastYears={forecastYears}
                        historicalData={historicalData}
                        assumptions={assumptions}
                        onUpdate={updateAssumption}
                        showHistorical={false}
                      />
                    </div>
                  ))}
                </AccordionContent>
              </AccordionItem>
            </Accordion>
          </div>
        </TabsContent>
```

Note on startup mode: the essential-grid filter keeps only the non-`pct` rows (CAPEX €, rimborso anni, finanziamento €/durata) **plus** the financing-rate row (`fin-tasso`) — CE growth rows are driven by the startup wizard's overrides and stay hidden, matching today's `!startup &&` behavior. The Avanzate accordion is available in both modes.

- [ ] **Step 3: Stop pre-filling no-op CE overrides + drop dead-field defaults**

In the new-scenario defaults block (`:857-913`): delete the 12 `ce*_override` lines (`:898-909`) and the three dead-field default lines `receivables_short_growth_pct: 0`, `payables_short_growth_pct: 0` (`:879, :881`) — keep `receivables_long_growth_pct: 0` (engine-live, now editable in Avanzate). Also delete `investments: 0` (`:874`, legacy dead) — `intangible_investments`/`tangible_investments` stay. The `baseIncome` variable (`:861`) becomes unused — remove it.

**Keep the hydration map for existing scenarios (`:785-851`) EXACTLY as is** — including dead fields and all `ce*_override` entries: full-row hydration is what preserves stored values across the bulk save (Task 4).

- [ ] **Step 4: Delete the dead table components**

Delete `AssumptionsTableHeader` (`:1493-1521`), `CEAssumptionsTable` (`:1523-2167`), `SPAssumptionsTable` (`:2168-2636`). Run the build; delete any helper that is now unused (`getHistoricalCEValue` and friends) **only if** the compiler/linter reports it unused — `StartupEconomicsRecap` and `AutoGeneratorCard` still live in this file and must keep working.

- [ ] **Step 5: Build + manual smoke**

```bash
cd /home/peter/DEV/budget/frontend && npm run build
```
Expected: clean build, page.tsx shrinks by roughly 1,100 lines.

Smoke (backend + frontend dev servers running, DEV_USER_ID set): open `/budget`, create a new scenario → Ipotesi tab shows 11 essential rows; open Avanzate → 4 groups; type 5 into "Materie prime %" and verify (React devtools or the Avanzate group) that BOTH `variable_materials_growth_pct` and `fixed_materials_growth_pct` read 5; set "Var. % costi fissi materie" to 2 in Avanzate and verify the "A" badge appears on the essential Materie cell.

- [ ] **Step 6: Commit**

```bash
git add frontend/app/budget/page.tsx
git commit -m "Budget semplificazione 3/6: ScenarioForm a 2 tab (essenziali + Avanzate), rimozione tabelle CE/SP e prefill override no-op"
```

---

### Task 4: Save path — bulk PUT + explicit override clearing

**Files:**
- Modify: `frontend/app/budget/page.tsx` — `handleSave` (`:930-993`), `handleRegenerateScenario` (`:101-115`), `ScenariosList` Ricalcola button

**Interfaces:**
- Consumes: `bulkUpsertAssumptions(companyId, scenarioId, { assumptions, auto_generate })` (`frontend/lib/api.ts:610`), existing `generateForecast(companyId, scenarioId, clearOverrides)`.
- Produces: one save call; Ricalcola dialog with the azzera checkbox.

- [ ] **Step 1: Switch `handleSave` to bulk**

Replace the per-year loop + `generateForecast` (`:959-983`) with:

```tsx
      // ONE call: bulk upsert (delete-all + reinsert server-side) + generation.
      // Rows are FULL objects (hydration map for existing scenarios includes CE
      // overrides and legacy fields) so overrides made on /forecast/income
      // survive this save. Never pass clear_overrides here.
      const rows = forecastYears
        .filter((year) => assumptions[year])
        .map((year) => ({
          ...assumptions[year],
          scenario_id: savedScenario.id,
          forecast_year: year,
        }));
      const result = await bulkUpsertAssumptions(companyId, savedScenario.id, {
        assumptions: rows,
        auto_generate: true,
      });

      // The backend returns success:true even when generation fails
      // (assumptions_service.py:210-217) — check the explicit flag.
      if (result?.forecast_generated === false) {
        toast.warning(
          result?.message ?? "Ipotesi salvate, ma il previsionale non è stato generato"
        );
      } else {
        toast.success("Scenario salvato e previsionale calcolato con successo!");
      }
      onSaved();
```

Update imports in `page.tsx`: add `bulkUpsertAssumptions`, remove `createBudgetAssumptions` and `updateBudgetAssumptions` (now unused). `getBudgetAssumptions` stays (hydration). The `existingAssumptionYears` state (`:775, :782-784, :854, :859, :964`) is now unused — delete it. Check the return type of `bulkUpsertAssumptions` in `lib/api.ts`; if it isn't typed with `forecast_generated`, extend its return type to `{ success: boolean; forecast_generated?: boolean; forecast_years?: number[]; message?: string }` (wire shape per CLAUDE.md).

- [ ] **Step 2: Ricalcola with explicit azzera checkbox**

In `BudgetPage`, add state and a confirm dialog around regeneration. Replace `handleRegenerateScenario` (`:101-115`) with:

```tsx
  const [regenScenarioId, setRegenScenarioId] = useState<number | null>(null);
  const [regenClearOverrides, setRegenClearOverrides] = useState(false);

  const handleRegenerateScenario = async () => {
    if (!selectedCompanyId || regenScenarioId === null) return;
    try {
      await generateForecast(selectedCompanyId, regenScenarioId, regenClearOverrides);
      toast.success("Previsionale ricalcolato con successo!");
      invalidateScenarios(selectedCompanyId);
      invalidateAnalysis(selectedCompanyId, regenScenarioId);
    } catch (err: unknown) {
      console.error("Error regenerating forecast:", err);
      toast.error(getErrorMessage(err, "Impossibile ricalcolare il previsionale"));
    } finally {
      setRegenScenarioId(null);
      setRegenClearOverrides(false);
    }
  };
```

Change `ScenariosList`'s `onRegenerate` wiring so the Ricalcola button calls `setRegenScenarioId(scenario.id)` instead of regenerating directly, and add an `AlertDialog` (shadcn, already used in the app) rendered in `BudgetPage`:

```tsx
      <AlertDialog open={regenScenarioId !== null} onOpenChange={(open) => !open && setRegenScenarioId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Ricalcola previsionale</AlertDialogTitle>
            <AlertDialogDescription>
              Il previsionale viene rigenerato dalle ipotesi correnti.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="flex items-center space-x-2 py-2">
            <Checkbox
              id="regen-clear"
              checked={regenClearOverrides}
              onCheckedChange={(c) => setRegenClearOverrides(c === true)}
            />
            <Label htmlFor="regen-clear" className="text-sm font-normal">
              Azzera le modifiche manuali del CE previsionale
            </Label>
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel>Annulla</AlertDialogCancel>
            <AlertDialogAction onClick={handleRegenerateScenario}>Ricalcola</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
```

(Import the `AlertDialog*` components and `Label` if not already imported in this file.)

- [ ] **Step 3: Build + smoke**

`npm run build` clean. Smoke: save a scenario (essential values only) → one network call to `PUT .../assumptions` with `auto_generate: true` followed by no `POST /generate`; Ricalcola opens the dialog; with the checkbox on, the request carries `clear_overrides=true`.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/budget/page.tsx frontend/lib/api.ts
git commit -m "Budget semplificazione 4/6: salvataggio bulk unico (auto_generate) + Ricalcola con azzeramento override esplicito"
```

---

### Task 5: AutoGenerator cleanup (dead fields out)

**Files:**
- Modify: `frontend/app/budget/page.tsx` — `AutoGeneratorCard` (`applyAutoAssumptions` `:1307-1323`, dead BS row `:1393-1402`)

- [ ] **Step 1: Remove the dead writes and the misleading row**

In `applyAutoAssumptions`, replace the BS-fields block (`:1315-1321`):

```tsx
    // BS: only receivables_long has an engine effect (sp07). The old
    // receivables_short/payables_short fields are dead (no engine reads) —
    // working capital scales via DSO/DIO/DPO instead.
    for (const year of forecastYears) {
      updateAssumption(year, "receivables_long_growth_pct", Math.round(inflationRate * 100) / 100);
    }
```

Replace the "Crediti / Debiti breve" table row (`:1393-1402`) label with `Crediti oltre 12 mesi` (same cells, same inflation display) so the table shows exactly what is applied.

- [ ] **Step 2: Build, then grep-audit the dead fields**

```bash
cd /home/peter/DEV/budget/frontend && npm run build
grep -rn "receivables_short_growth_pct\|payables_short_growth_pct\|interest_rate_receivables\|interest_rate_payables" app/ components/ | grep -v types/
```
Expected: hits ONLY in the `ScenarioForm` hydration map (`page.tsx` — intentional round-trip) — nowhere else in UI code. `types/api.ts` keeps the optional fields (wire compatibility).

- [ ] **Step 3: Commit**

```bash
git add frontend/app/budget/page.tsx
git commit -m "Budget semplificazione 5/6: AutoGenerator scrive solo campi vivi (crediti oltre); rimossa riga no-op crediti/debiti breve"
```

---

### Task 6: API round-trip verification script + docs

**Files:**
- Create: `tests/verify_assumptions_simplification.py`
- Modify: `CLAUDE.md` (budget workflow section), `docs/superpowers/specs/2026-07-06-budget-assumptions-simplification-design.md` (status)

- [ ] **Step 1: Write the verification script**

Create `tests/verify_assumptions_simplification.py` (stdlib only; needs the backend running on :8000 with `DEV_USER_ID` set):

```python
"""End-to-end API verification for the assumptions-simplification save path.

Prereq: backend running -> cd backend && DEV_USER_ID=dev-user-001 \
    venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000

Checks: bulk save with essential-only fields collapses var==fixed, leaves
overrides NULL; a /forecast/income override survives a subsequent bulk save
(full-row hydration semantics); analysis returns forecast years.
Creates a throwaway company and deletes it at the end.
"""
import json
import sys
import urllib.request

BASE = "http://127.0.0.1:8000/api/v1"


def call(method, path, body=None):
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read() or b"null")


def main():
    company = call("POST", "/companies", {"name": "VERIFY SEMPLIFICAZIONE SRL", "sector": 3})
    cid = company["id"]
    try:
        call("POST", f"/companies/{cid}/years", {"year": 2025})
        call("PUT", f"/companies/{cid}/years/2025/balance-sheet",
             {"sp09_disponibilita_liquide": 50000, "sp11_capitale": 50000})
        call("PUT", f"/companies/{cid}/years/2025/income-statement",
             {"ce01_ricavi_vendite": 500000, "ce05_materie_prime": 200000,
              "ce06_servizi": 100000, "ce08_costi_personale": 100000,
              "ce20_imposte": 10000})
        scenario = call("POST", f"/companies/{cid}/scenarios",
                        {"company_id": cid, "name": "verify", "base_year": 2025,
                         "scenario_type": "budget"})
        sid = scenario["id"]

        # essential-only bulk save: Materie% dual-written by the form as var==fixed
        rows = [{"forecast_year": y,
                 "revenue_growth_pct": 5.0,
                 "variable_materials_growth_pct": 3.0,
                 "fixed_materials_growth_pct": 3.0,
                 "variable_services_growth_pct": 2.0,
                 "fixed_services_growth_pct": 2.0,
                 "personnel_growth_pct": 1.0,
                 "other_costs_growth_pct": 1.0,
                 "tangible_investments": 10000}
                for y in (2026, 2027, 2028)]
        res = call("PUT", f"/companies/{cid}/scenarios/{sid}/assumptions",
                   {"assumptions": rows, "auto_generate": True})
        assert res.get("forecast_generated"), f"generation failed: {res}"

        saved = call("GET", f"/companies/{cid}/scenarios/{sid}/assumptions")
        assert len(saved) == 3, saved
        for a in saved:
            assert float(a["variable_materials_growth_pct"]) == float(a["fixed_materials_growth_pct"]) == 3.0
            assert a["ce01_override"] is None and a["ce15_override"] is None, \
                "no-op overrides must not be stored"
            assert float(a.get("receivables_short_growth_pct") or 0) == 0

        # override survives a re-save with hydrated rows (form behavior)
        call("PATCH", f"/companies/{cid}/scenarios/{sid}/ce-override",
             {"overrides": [{"forecast_year": 2026, "field": "ce01_override", "value": 600000}]})
        hydrated = call("GET", f"/companies/{cid}/scenarios/{sid}/assumptions")
        call("PUT", f"/companies/{cid}/scenarios/{sid}/assumptions",
             {"assumptions": hydrated, "auto_generate": True})
        after = call("GET", f"/companies/{cid}/scenarios/{sid}/assumptions")
        y26 = next(a for a in after if a["forecast_year"] == 2026)
        assert float(y26["ce01_override"]) == 600000, "override wiped by bulk save"

        analysis = call("GET", f"/companies/{cid}/scenarios/{sid}/analysis")
        assert len(analysis.get("forecast_years", [])) == 3, "analysis missing forecast years"
        print("OK: bulk save, collapse var==fixed, override preservation, analysis")
    finally:
        call("DELETE", f"/companies/{cid}")


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it**

```bash
cd /home/peter/DEV/budget/backend && DEV_USER_ID=dev-user-001 venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 &   # if not already running
cd /home/peter/DEV/budget && backend/venv/bin/python tests/verify_assumptions_simplification.py
```
Expected: `OK: bulk save, collapse var==fixed, override preservation, analysis`. If the `POST /years` + `PUT` seeding path rejects the scenario creation (base-year validation), inspect the error — the startup wizard uses this exact seeding sequence, so a failure indicates a payload typo, not a design problem.

- [ ] **Step 3: Update CLAUDE.md**

In the CLAUDE.md "Bulk Assumptions Workflow" / budget-page sections, update the description of the budget page save path: it now uses the bulk PUT with `auto_generate=true` (per-year POST/PUT no longer called by the frontend); "Salva e Calcola Previsionale" never clears overrides; "Ricalcola" shows a dialog with the explicit "Azzera le modifiche manuali del CE previsionale" checkbox mapping to `clear_overrides=true`. Also update the "Editable Forecast Income Statement" note that claimed both buttons pass `clearOverrides=true` (they never did — document the actual semantics). Mention the new form structure (2 tabs, essential rows + Avanzate) in the frontend pages list.

- [ ] **Step 4: Update spec status + commit**

Change the spec header to `**Status:** Implemented (see docs/superpowers/plans/2026-07-06-budget-assumptions-simplification.md)`.

```bash
git add tests/verify_assumptions_simplification.py CLAUDE.md docs/superpowers/specs/2026-07-06-budget-assumptions-simplification-design.md
git commit -m "Budget semplificazione 6/6: script verifica API round-trip + docs (CLAUDE.md, stato spec)"
```

- [ ] **Step 5: Final verification**

```bash
cd /home/peter/DEV/budget/frontend && npm run build
cd /home/peter/DEV/budget && backend/venv/bin/python tests/verify_assumptions_simplification.py
```
Plus a final manual pass per the spec's §Testing item 4: create scenario essential-only, Avanzate divergence badge behavior, Ricalcola with/without the azzera checkbox. Optionally dispatch the playwright-frontend-tester agent for this pass.
