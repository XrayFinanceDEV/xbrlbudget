# Percorso unico "Pratica" — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ridurre i percorsi di una nuova pratica da tre a due (Da bilancio / Startup), rendere le Rettifiche uno step obbligato del percorso da bilancio, e mostrare l'intero workflow in un unico stepper condiviso dall'anagrafica al report.

**Architecture:** Tutto il lavoro è frontend tranne un ritocco additivo allo schema Pydantic del log rettifiche. Un nuovo `PraticaContext` (persistito in `localStorage`) tiene la pratica attiva; un modello puro degli step (`lib/pratica-steps.ts`) decide quali voci mostrare e quali sono raggiungibili; `<PraticaStepper>` lo rende e sostituisce `<Navigation>` quando una pratica è attiva. Il wizard `/infrannuale` si sposta su `/pratica` e diventa il percorso unico da bilancio.

**Tech Stack:** Next.js 15 (App Router) + React 19, TypeScript, Tailwind v3, shadcn/ui (new-york, slate), lucide-react, sonner. Backend FastAPI + Pydantic v2, test con pytest.

**Spec:** `docs/superpowers/specs/2026-08-08-percorso-unico-pratica-design.md`

## Global Constraints

- **Nessuna modifica a `database/models.py` né alle migrazioni.** L'unica modifica backend consentita è additiva sullo schema Pydantic e sul conteggio del cap.
- **Solo componenti shadcn/ui.** Niente tabelle/bottoni HTML grezzi, niente emoji: icone `lucide-react`.
- **Colori semantici** (`text-foreground`, `bg-card`, `border-border`, `text-muted-foreground`); niente hex hardcoded.
- **Testo UI in italiano**, formattazione numerica europea.
- **`localStorage` va letto in `useEffect`, mai nell'inizializzatore di `useState`** — altrimenti Next sbaglia l'idratazione. Pattern di riferimento: `contexts/AppContext.tsx:47-63`.
- **Barre di navigazione sempre `print:hidden`.**
- Il gate frontend di ogni task è `cd frontend && npx tsc --noEmit && npm run build`. Non esiste un test runner JavaScript nel progetto e **questo piano non ne introduce uno**: la verifica comportamentale è la Task 11.
- Comandi backend dalla root del progetto con `backend/venv/bin/python`.
- Commit su `main` direttamente (convenzione del progetto), messaggi in italiano.

---

## File Structure

**Nuovi**

| File | Responsabilità |
|---|---|
| `frontend/contexts/PraticaContext.tsx` | Stato della pratica attiva + persistenza `localStorage`. Nessuna logica di step. |
| `frontend/lib/pratica-steps.ts` | Modello **puro** degli step: definizioni, quali mostrare, quali abilitare. Nessun React, nessun import di componenti. |
| `frontend/components/PraticaStepper.tsx` | Rende il modello degli step; instrada (`setAnalysisStep` per le tab, `router.push` per le rotte). |
| `frontend/components/pratica/AnagraficheStep.tsx` | Form dati azienda (crea/modifica) — primo step del percorso da bilancio. |
| `frontend/app/pratica/page.tsx` | Il wizard, spostato da `app/infrannuale/page.tsx`. |
| `tests/test_rettifiche_confirm.py` | Test del marker di conferma e del cap. |

**Modificati:** `frontend/app/layout.tsx`, `frontend/app/page.tsx`, `frontend/app/infrannuale/page.tsx` (→ redirect), `frontend/app/budget/page.tsx`, `frontend/components/Navigation.tsx`, `frontend/hooks/use-rettifiche-year.ts`, `frontend/types/api.ts`, `backend/app/schemas/adjustments.py`, `backend/app/api/v1/financial_years.py`, `CLAUDE.md`.

**Eliminato:** `frontend/components/budget/HistoricalBalanceDetailEditor.tsx`.

---

### Task 1: Marker di conferma nel log rettifiche (backend)

Il gate delle Rettifiche deve sopravvivere al refresh. Lo persistiamo come voce speciale nel `rettifiche_log` già esistente (colonna JSON su `FinancialYear`), evitando qualsiasi migrazione. Serve un campo opzionale sullo schema e un cap che non conti le conferme come rettifiche.

**Files:**
- Modify: `backend/app/schemas/adjustments.py:8-18`
- Modify: `backend/app/api/v1/financial_years.py:351`, `:522-529`
- Modify: `frontend/types/api.ts:879-889`
- Test: `tests/test_rettifiche_confirm.py`

**Interfaces:**
- Consumes: niente (primo task).
- Produces:
  - `RettificaEntry.entry_type: Optional[str] = None` (Pydantic) e `entry_type?: string | null` (TS).
  - `backend.app.api.v1.financial_years._countable_log_entries(log: List[RettificaEntry]) -> int`.
  - Convenzione: una voce con `entry_type == "confirm"` è un marker, non una rettifica.

- [ ] **Step 1: Scrivere il test che fallisce**

Crea `tests/test_rettifiche_confirm.py`:

```python
"""Il marker di conferma delle Rettifiche vive nel rettifiche_log senza consumare il cap."""
import backend.app.main  # noqa: F401  — inserisce la project root in sys.path

from backend.app.api.v1.financial_years import (
    RETTIFICHE_LOG_MAX,
    _countable_log_entries,
)
from backend.app.schemas.adjustments import RettificaEntry


def _rettifica(idx: int) -> RettificaEntry:
    return RettificaEntry(
        id=f"r{idx}",
        edited_field="sp09_disponibilita_liquide",
        edited_label="Disponibilità liquide",
        edit_delta=100.0,
        counterpart_field="sp16g_altri_debiti_breve",
        counterpart_label="Altri debiti",
        counterpart_delta=100.0,
        created_at="2026-08-08T10:00:00",
    )


def _confirm() -> RettificaEntry:
    return RettificaEntry(
        id="confirm-2025",
        entry_type="confirm",
        edited_field="",
        edited_label="Rettifiche confermate",
        edit_delta=0.0,
        counterpart_field="",
        counterpart_label="",
        counterpart_delta=0.0,
        created_at="2026-08-08T10:05:00",
    )


def test_entry_type_defaults_to_none():
    """Le voci esistenti non hanno entry_type: il campo è additivo e opzionale."""
    assert _rettifica(1).entry_type is None


def test_confirm_marker_round_trips():
    """Il marker sopravvive a model_dump/validate: è così che viene persistito."""
    dumped = _confirm().model_dump()
    assert dumped["entry_type"] == "confirm"
    assert RettificaEntry(**dumped).entry_type == "confirm"


def test_confirm_does_not_consume_the_cap():
    """Con 20 rettifiche + 1 conferma il log resta accettabile."""
    log = [_rettifica(i) for i in range(RETTIFICHE_LOG_MAX)] + [_confirm()]
    assert _countable_log_entries(log) == RETTIFICHE_LOG_MAX


def test_real_entries_are_counted():
    log = [_rettifica(i) for i in range(RETTIFICHE_LOG_MAX + 1)]
    assert _countable_log_entries(log) == RETTIFICHE_LOG_MAX + 1
```

- [ ] **Step 2: Eseguire il test e verificare che fallisca**

Dalla root del progetto:

```bash
backend/venv/bin/python -m pytest tests/test_rettifiche_confirm.py -v
```

Atteso: FAIL — `ImportError: cannot import name '_countable_log_entries'`.

- [ ] **Step 3: Aggiungere `entry_type` allo schema Pydantic**

In `backend/app/schemas/adjustments.py`, dentro `class RettificaEntry`, subito dopo `id: str`:

```python
class RettificaEntry(BaseModel):
    """One per-edit double-entry rettifica, tracked for the log panel.

    entry_type == "confirm" marks the user's explicit "Conferma e prosegui" on the
    Rettifiche step: bookkeeping, not a rettifica. It is persisted in the same log
    so the gate survives a refresh without adding a column.
    """
    id: str
    entry_type: Optional[str] = None
    edited_field: str
```

(il resto della classe resta invariato)

- [ ] **Step 4: Aggiungere l'helper e usarlo nel cap**

In `backend/app/api/v1/financial_years.py`, subito dopo `RETTIFICHE_LOG_MAX = 20` (riga 351):

```python
RETTIFICHE_LOG_MAX = 20


def _countable_log_entries(log) -> int:
    """Quante voci del log contano contro il cap.

    I marker di conferma (entry_type == "confirm") sono contabilità interna del
    gate Rettifiche, non correzioni dell'utente: non devono rubargli una riga.
    """
    return sum(1 for e in log if getattr(e, "entry_type", None) != "confirm")
```

Poi sostituisci il controllo alle righe 523-528 con:

```python
    if payload.rettifiche_log is not None:
        if _countable_log_entries(payload.rettifiche_log) > RETTIFICHE_LOG_MAX:
            raise HTTPException(
                status_code=400,
                detail=f"Massimo {RETTIFICHE_LOG_MAX} rettifiche consentite",
            )
        fy.rettifiche_log = json.dumps([e.model_dump() for e in payload.rettifiche_log])
```

- [ ] **Step 5: Eseguire il test e verificare che passi**

```bash
backend/venv/bin/python -m pytest tests/test_rettifiche_confirm.py -v
```

Atteso: 4 passed.

- [ ] **Step 6: Rispecchiare il campo nel tipo TypeScript**

In `frontend/types/api.ts`, in `interface RettificaEntry` (riga 879), dopo `id: string;`:

```ts
export interface RettificaEntry {
  id: string;
  /** "confirm" = marker del gate Rettifiche, non una rettifica dell'utente. */
  entry_type?: string | null;
  edited_field: string;
```

- [ ] **Step 7: Verificare che il frontend compili**

```bash
cd frontend && npx tsc --noEmit
```

Atteso: nessun errore.

- [ ] **Step 8: Commit**

```bash
git add tests/test_rettifiche_confirm.py backend/app/schemas/adjustments.py \
        backend/app/api/v1/financial_years.py frontend/types/api.ts
git commit -m "feat(rettifiche): entry_type sul log, le conferme non consumano il cap"
```

---

### Task 2: `PraticaContext`

Lo stato della pratica attiva, condiviso tra il wizard e le pagine del previsionale. Solo stato e persistenza: nessuna logica di step (vive nella Task 3).

**Files:**
- Create: `frontend/contexts/PraticaContext.tsx`
- Modify: `frontend/app/layout.tsx`

**Interfaces:**
- Consumes: niente.
- Produces:
  - `type PraticaWorkflow = "bilancio" | "startup"`
  - `interface PraticaState { workflow; companyId; fiscalYear; periodMonths; infrannualeScenarioId; budgetScenarioId; analysisStep; rettificheConfirmed: { storico: boolean; verifica: boolean } }`
  - `usePratica(): { pratica: PraticaState | null; startPratica(init): void; updatePratica(patch): void; setAnalysisStep(step: string): void; exitPratica(): void }`

- [ ] **Step 1: Creare il context**

Crea `frontend/contexts/PraticaContext.tsx`:

```tsx
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

  const persist = useCallback((next: PraticaState | null) => {
    setPratica(next);
    try {
      if (next) localStorage.setItem(PRATICA_KEY, JSON.stringify(next));
      else localStorage.removeItem(PRATICA_KEY);
    } catch {
      /* localStorage non disponibile */
    }
  }, []);

  const startPratica = useCallback<PraticaContextType["startPratica"]>(
    (init) => persist({ ...DEFAULTS, ...init }),
    [persist],
  );

  const updatePratica = useCallback<PraticaContextType["updatePratica"]>(
    (patch) =>
      setPratica((prev) => {
        if (!prev) return prev;
        const next = { ...prev, ...patch };
        try {
          localStorage.setItem(PRATICA_KEY, JSON.stringify(next));
        } catch {
          /* localStorage non disponibile */
        }
        return next;
      }),
    [],
  );

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
```

- [ ] **Step 2: Montare il provider nel layout**

In `frontend/app/layout.tsx`, aggiungi l'import accanto agli altri context:

```tsx
import { PraticaProvider } from "@/contexts/PraticaContext";
```

e avvolgi `AppProvider` (il provider della pratica sta **sopra**, così `AppProvider` e i suoi consumatori possono leggerlo):

```tsx
          <AuthProvider>
          <PraticaProvider>
          <AppProvider>
```

chiudendo simmetricamente dopo `</AppProvider>`:

```tsx
          </AppProvider>
          </PraticaProvider>
          </AuthProvider>
```

- [ ] **Step 3: Verificare la build**

```bash
cd frontend && npx tsc --noEmit && npm run build
```

Atteso: build completata senza errori.

- [ ] **Step 4: Commit**

```bash
git add frontend/contexts/PraticaContext.tsx frontend/app/layout.tsx
git commit -m "feat(pratica): PraticaContext con stato persistito della pratica attiva"
```

---

### Task 3: Modello degli step

Logica pura, senza React: quali step esistono per un workflow, quali sono raggiungibili, dove portano. Isolarla qui evita che le condizioni si sparpaglino tra stepper, wizard e pagine.

**Files:**
- Create: `frontend/lib/pratica-steps.ts`

**Interfaces:**
- Consumes: `PraticaState`, `PraticaWorkflow` da `@/contexts/PraticaContext`.
- Produces:
  - `interface PraticaStep { id: string; label: string; phase: "analisi" | "previsionale"; kind: "tab" | "route"; route?: string; enabled: boolean }`
  - `interface PraticaGates { imported: boolean; rettificheOk: boolean; comparisonReady: boolean; projectionReady: boolean; budgetScenario: boolean; forecastReady: boolean }`
  - `buildPraticaSteps(pratica: PraticaState, gates: PraticaGates): PraticaStep[]`
  - `ANALYSIS_STEP_IDS: readonly string[]`

- [ ] **Step 1: Creare il modello**

Crea `frontend/lib/pratica-steps.ts`:

```ts
import type { PraticaState } from "@/contexts/PraticaContext";

export type PraticaPhase = "analisi" | "previsionale";

export interface PraticaStep {
  id: string;
  label: string;
  phase: PraticaPhase;
  /** "tab" = tab interna di /pratica; "route" = pagina Next a sé stante. */
  kind: "tab" | "route";
  route?: string;
  enabled: boolean;
}

/**
 * Condizioni di sblocco, calcolate da chi conosce i dati (il wizard o la
 * pagina che monta lo stepper) e passate qui già risolte in booleani.
 */
export interface PraticaGates {
  /** Esiste un bilancio importato per la pratica. */
  imported: boolean;
  /** Tutte le schede Rettifiche richieste sono state confermate. */
  rettificheOk: boolean;
  /** Il confronto è stato caricato. */
  comparisonReady: boolean;
  /** La proiezione è stata calcolata (solo periodo < 12 mesi). */
  projectionReady: boolean;
  /** Esiste lo scenario budget della pratica. */
  budgetScenario: boolean;
  /** Il previsionale è stato generato. */
  forecastReady: boolean;
}

export const ANALYSIS_STEP_IDS = [
  "anagrafiche",
  "import",
  "rettifiche",
  "comparison",
  "projection",
  "results",
  "stampa",
] as const;

/**
 * Gli step della pratica, nell'ordine in cui vanno mostrati.
 *
 * Percorso "bilancio": fase ANALISI dentro /pratica, poi fase PREVISIONALE su
 * rotte reali. Lo step "projection" compare solo con periodo < 12 mesi, perché
 * un bilancio già annuale non va proiettato a 12 mesi.
 *
 * Percorso "startup": nessuna fase ANALISI (non c'è nulla da importare); lo
 * step "anagrafiche" è il form business plan su /budget.
 */
export function buildPraticaSteps(
  pratica: PraticaState,
  gates: PraticaGates,
): PraticaStep[] {
  const previsionale: PraticaStep[] = [
    {
      id: "budget",
      label: "Budget",
      phase: "previsionale",
      kind: "route",
      route: "/budget",
      enabled: pratica.workflow === "startup" ? true : gates.budgetScenario,
    },
    {
      id: "ce-previsionale",
      label: "CE Prev.",
      phase: "previsionale",
      kind: "route",
      route: "/forecast/income",
      enabled: gates.forecastReady,
    },
    {
      id: "rendiconto",
      label: "Rendiconto",
      phase: "previsionale",
      kind: "route",
      route: "/cashflow",
      enabled: gates.forecastReady,
    },
    {
      id: "report",
      label: "Report",
      phase: "previsionale",
      kind: "route",
      route: "/report",
      enabled: gates.forecastReady,
    },
  ];

  if (pratica.workflow === "startup") {
    return [
      {
        id: "anagrafiche",
        label: "Anagrafiche",
        phase: "previsionale",
        kind: "route",
        route: "/budget",
        enabled: true,
      },
      ...previsionale,
    ];
  }

  const isAnnual = pratica.periodMonths === 12;

  const analisi: PraticaStep[] = [
    { id: "anagrafiche", label: "Anagrafiche", phase: "analisi", kind: "tab", enabled: true },
    { id: "import", label: "Import", phase: "analisi", kind: "tab", enabled: pratica.companyId !== null },
    { id: "rettifiche", label: "Rettifiche", phase: "analisi", kind: "tab", enabled: gates.imported },
    { id: "comparison", label: "Confronto", phase: "analisi", kind: "tab", enabled: gates.imported && gates.rettificheOk },
    ...(isAnnual
      ? []
      : [
          {
            id: "projection",
            label: "Proiezione",
            phase: "analisi" as const,
            kind: "tab" as const,
            enabled: gates.comparisonReady,
          },
        ]),
    { id: "results", label: "Indicatori", phase: "analisi", kind: "tab", enabled: gates.comparisonReady },
    {
      id: "stampa",
      label: "Stampa",
      phase: "analisi",
      kind: "tab",
      enabled: isAnnual ? gates.comparisonReady : gates.projectionReady,
    },
  ];

  return [...analisi, ...previsionale];
}
```

- [ ] **Step 2: Verificare la compilazione**

```bash
cd frontend && npx tsc --noEmit
```

Atteso: nessun errore.

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/pratica-steps.ts
git commit -m "feat(pratica): modello puro degli step del percorso"
```

---

### Task 4: `PraticaStepper` e mutua esclusione con la nav

**Files:**
- Create: `frontend/components/PraticaStepper.tsx`
- Modify: `frontend/app/layout.tsx`
- Modify: `frontend/components/Navigation.tsx:26-31`, `:48-50`

**Interfaces:**
- Consumes: `usePratica()`, `buildPraticaSteps`, `PraticaGates`.
- Produces: `<PraticaStepper />` (nessuna prop: legge context e gates dal server state via `useApp`/`usePratica`). Monta la propria barra solo quando `pratica !== null` e il pathname non è `/`.

- [ ] **Step 1: Creare lo stepper**

Crea `frontend/components/PraticaStepper.tsx`:

```tsx
"use client";

import { usePathname, useRouter } from "next/navigation";
import { LogOut } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { usePratica } from "@/contexts/PraticaContext";
import { buildPraticaSteps, type PraticaGates, type PraticaStep } from "@/lib/pratica-steps";

/**
 * Quale step è attivo, dedotto dalla rotta corrente (fase PREVISIONALE) o
 * dalla tab del wizard (fase ANALISI).
 */
function currentStepId(pathname: string, analysisStep: string): string {
  if (pathname.startsWith("/pratica")) return analysisStep;
  if (pathname.startsWith("/forecast")) return "ce-previsionale";
  if (pathname.startsWith("/cashflow")) return "rendiconto";
  if (pathname.startsWith("/report")) return "report";
  if (pathname.startsWith("/budget")) return "budget";
  return "";
}

export function PraticaStepper() {
  const pathname = usePathname();
  const router = useRouter();
  const { pratica, setAnalysisStep, exitPratica } = usePratica();

  // La home è la pagina di uscita: là comanda la nav normale.
  if (!pratica || pathname === "/") return null;

  // I gate derivano da ciò che è già stato raggiunto e persistito nel context.
  // Il wizard li affina in locale; qui bastano per decidere cosa è cliccabile.
  const gates: PraticaGates = {
    imported: pratica.fiscalYear !== null,
    // storico è true anche quando la scheda storico non esiste (import senza anno
    // di raffronto): è il wizard a scriverlo così, vedi Task 7 Step 4.
    rettificheOk:
      pratica.rettificheConfirmed.verifica && pratica.rettificheConfirmed.storico,
    comparisonReady: pratica.infrannualeScenarioId !== null,
    projectionReady: pratica.infrannualeScenarioId !== null,
    budgetScenario: pratica.budgetScenarioId !== null,
    forecastReady: pratica.budgetScenarioId !== null,
  };

  const steps = buildPraticaSteps(pratica, gates);
  const active = currentStepId(pathname, pratica.analysisStep);

  const go = (step: PraticaStep) => {
    if (!step.enabled) return;
    if (step.kind === "tab") {
      setAnalysisStep(step.id);
      if (!pathname.startsWith("/pratica")) router.push("/pratica");
      return;
    }
    if (step.route) router.push(step.route);
  };

  const phases: Array<{ key: "analisi" | "previsionale"; label: string }> = [
    { key: "analisi", label: "Analisi" },
    { key: "previsionale", label: "Previsionale" },
  ];

  return (
    <div className="border-b border-border bg-background print:hidden">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <nav className="flex items-center gap-1 overflow-x-auto" aria-label="Percorso pratica">
          {phases.map((phase, phaseIdx) => {
            const phaseSteps = steps.filter((s) => s.phase === phase.key);
            if (phaseSteps.length === 0) return null;
            return (
              <div key={phase.key} className="flex items-center gap-1">
                {phaseIdx > 0 && <div className="mx-2 h-6 w-px shrink-0 bg-border" />}
                <span className="shrink-0 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                  {phase.label}
                </span>
                {phaseSteps.map((step) => (
                  <button
                    key={step.id}
                    onClick={() => go(step)}
                    disabled={!step.enabled}
                    className={cn(
                      "flex items-center gap-1.5 whitespace-nowrap px-3 py-3 text-sm font-medium border-b-2 transition-colors",
                      active === step.id
                        ? "border-primary text-foreground"
                        : step.enabled
                        ? "border-transparent text-muted-foreground hover:text-foreground hover:border-border"
                        : "border-transparent text-muted-foreground/40 cursor-not-allowed",
                    )}
                  >
                    {step.label}
                  </button>
                ))}
              </div>
            );
          })}
          <span className="flex-1" />
          <Button
            variant="ghost"
            size="sm"
            className="shrink-0 text-muted-foreground"
            onClick={() => {
              exitPratica();
              router.push("/");
            }}
          >
            <LogOut className="h-4 w-4 mr-1" /> Esci dalla pratica
          </Button>
        </nav>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Rendere stepper e nav mutuamente esclusivi**

In `frontend/app/layout.tsx` non si può leggere il context (è un server component). Crea quindi il selettore dentro `Navigation`: in `frontend/components/Navigation.tsx`, aggiungi in cima agli import:

```tsx
import { usePratica } from "@/contexts/PraticaContext";
import { PraticaStepper } from "@/components/PraticaStepper";
```

e sostituisci il blocco alle righe 48-50:

```tsx
  // La home "Aziende & Pratiche" è una pagina intera, quindi la nav resta.
  // Dentro una pratica comanda lo stepper: mai due barre insieme.
  if (pratica && pathname !== "/") return <PraticaStepper />;
```

aggiungendo `const { pratica } = usePratica();` accanto a `const { startupMode } = useApp();`. Rimuovi la vecchia riga `if (pathname.startsWith("/infrannuale")) return null;` — resa ridondante da questa regola.

- [ ] **Step 3: Togliere la tab Importazione dalla nav**

In `frontend/components/Navigation.tsx`, `MAIN_TABS` (righe 26-31) perde la voce Importazione — l'import vive dentro il percorso. `/import` resta come rotta funzionante:

```tsx
const MAIN_TABS = [
  { href: "/", label: "Aziende & Pratiche", icon: Building2, match: (path: string) => path === "/" || path.startsWith("/aziende") },
  { href: "/budget", label: "Scenari", icon: FileSpreadsheet, match: (path: string) => path.startsWith("/budget") },
];
```

Rimuovi l'import ora inutilizzato di `Upload` da `lucide-react` e il filtro `tab.href !== "/import"` nella riga di `startupMode`, che diventa:

```tsx
  const mainTabs = startupMode
    ? MAIN_TABS.filter((tab) => tab.href !== "/")
    : MAIN_TABS;
```

- [ ] **Step 4: Verificare la build**

```bash
cd frontend && npx tsc --noEmit && npm run build
```

Atteso: build completata, nessun warning di import inutilizzati (`Upload`).

- [ ] **Step 5: Commit**

```bash
git add frontend/components/PraticaStepper.tsx frontend/components/Navigation.tsx
git commit -m "feat(pratica): stepper condiviso al posto della nav dentro una pratica"
```

---

### Task 5: Spostare il wizard su `/pratica`

Spostamento e ricablaggio, **nessun cambiamento di comportamento**. Le modifiche funzionali arrivano dalle Task 6-8.

**Files:**
- Create: `frontend/app/pratica/page.tsx` (via `git mv`)
- Modify: `frontend/app/infrannuale/page.tsx` (nuovo, redirect)
- Modify: `frontend/app/page.tsx:171`

**Interfaces:**
- Consumes: `usePratica()` (Task 2).
- Produces: la rotta `/pratica`; la tab attiva del wizard è `pratica.analysisStep`, non più uno `useState` locale.

- [ ] **Step 1: Spostare il file**

```bash
cd /home/peter/DEV/budget
mkdir -p frontend/app/pratica
git mv frontend/app/infrannuale/page.tsx frontend/app/pratica/page.tsx
```

- [ ] **Step 2: Creare il redirect**

Crea `frontend/app/infrannuale/page.tsx`:

```tsx
import { redirect } from "next/navigation";

/** La vecchia rotta del wizard infrannuale: ora è il percorso unico /pratica. */
export default function InfrannualeRedirect() {
  redirect("/pratica");
}
```

- [ ] **Step 3: Portare la tab attiva nel context**

In `frontend/app/pratica/page.tsx`, sostituisci la riga 2902:

```tsx
  const [activeTab, setActiveTab] = useState("aziende");
```

con la lettura dal context (aggiungi `import { usePratica } from "@/contexts/PraticaContext";` in cima al file):

```tsx
  const { pratica, updatePratica, setAnalysisStep } = usePratica();
  const activeTab = pratica?.analysisStep ?? "anagrafiche";
  const setActiveTab = setAnalysisStep;
```

Tutte le altre 26 occorrenze di `activeTab`/`setActiveTab` restano invariate: le firme combaciano.

- [ ] **Step 4: Rimuovere la barra interna del wizard**

La barra step è ora fornita dal layout. In `frontend/app/pratica/page.tsx` elimina il blocco `{/* Infrannuale Navigation Bar */}` (il `<div className="border-b border-border bg-background print:hidden">` che mappa `STEPS`, subito dopo `return (`) e la costante `STEPS` che lo alimenta (riga 3651). Rimuovi gli import di icone rimasti inutilizzati che `npx tsc --noEmit` segnalerà.

- [ ] **Step 5: Aggiornare il riferimento nella home**

In `frontend/app/page.tsx`, riga 171:

```tsx
    router.push(s.scenario_type === "infrannuale" ? "/pratica" : "/budget");
```

- [ ] **Step 6: Verificare la build**

```bash
cd frontend && npx tsc --noEmit && npm run build
```

Atteso: build completata. `/infrannuale` e `/pratica` compaiono entrambe nell'elenco delle rotte.

- [ ] **Step 7: Commit**

```bash
git add -A frontend/app/pratica frontend/app/infrannuale frontend/app/page.tsx
git commit -m "refactor(pratica): il wizard si sposta su /pratica, tab attiva nel context"
```

---

### Task 6: Step Anagrafiche

Sostituisce lo step *Aziende*, che duplica la home e carica gli scenari di tutte le aziende con una chiamata per azienda.

**Files:**
- Create: `frontend/components/pratica/AnagraficheStep.tsx`
- Modify: `frontend/app/pratica/page.tsx` (blocco `activeTab === "aziende"`)

**Interfaces:**
- Consumes: `createCompany`, `updateCompany` da `@/lib/api`; `useApp()`; `usePratica()`.
- Produces: `<AnagraficheStep onReady={(companyId: number) => void} />` — chiama `onReady` dopo che l'azienda esiste ed è selezionata.

- [ ] **Step 1: Creare il componente**

Crea `frontend/components/pratica/AnagraficheStep.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { ArrowRight, Building2, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useApp } from "@/contexts/AppContext";
import { createCompany, updateCompany } from "@/lib/api";
import { getErrorMessage } from "@/lib/utils";

const SECTOR_OPTIONS: Record<number, string> = {
  1: "Industria, Alberghi (Proprietari), Agricoltura, Pesca",
  2: "Commercio",
  3: "Servizi (diversi da Autotrasporti) e Alberghi (Locatari)",
  4: "Autotrasporti",
  5: "Immobiliare",
  6: "Edilizia",
};

/**
 * Primo step del percorso da bilancio: i dati dell'azienda della pratica.
 * Non è un elenco aziende — la scelta è già avvenuta sulla home.
 */
export function AnagraficheStep({ onReady }: { onReady: (companyId: number) => void }) {
  const { selectedCompany, selectedCompanyId, setSelectedCompanyId, refreshCompanies } = useApp();

  const [name, setName] = useState("");
  const [taxId, setTaxId] = useState("");
  const [sector, setSector] = useState(1);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setName(selectedCompany?.name ?? "");
    setTaxId(selectedCompany?.tax_id ?? "");
    setSector(selectedCompany?.sector ?? 1);
  }, [selectedCompany]);

  const isNew = selectedCompanyId === null;

  const handleSave = async () => {
    if (!name.trim()) {
      toast.error("Il nome dell'azienda è obbligatorio");
      return;
    }
    setSaving(true);
    try {
      let companyId = selectedCompanyId;
      if (isNew) {
        const company = await createCompany({
          name: name.trim(),
          tax_id: taxId.trim() || undefined,
          sector,
        });
        companyId = company.id;
        setSelectedCompanyId(company.id);
      } else {
        await updateCompany(selectedCompanyId!, {
          name: name.trim(),
          tax_id: taxId.trim() || undefined,
          sector,
        });
      }
      await refreshCompanies();
      toast.success(isNew ? "Azienda creata" : "Anagrafica aggiornata");
      if (companyId !== null) onReady(companyId);
    } catch (err: unknown) {
      toast.error(getErrorMessage(err, "Errore nel salvataggio dell'anagrafica"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Building2 className="h-5 w-5" /> Anagrafica azienda
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="space-y-1">
            <Label htmlFor="anag-nome">Nome *</Label>
            <Input
              id="anag-nome"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="es. ROSSI S.R.L."
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="anag-piva">Partita IVA</Label>
            <Input
              id="anag-piva"
              value={taxId}
              onChange={(e) => setTaxId(e.target.value)}
              placeholder="es. 12345678901"
            />
          </div>
          <div className="space-y-1">
            <Label>Settore *</Label>
            <Select value={sector.toString()} onValueChange={(v) => setSector(parseInt(v))}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {Object.entries(SECTOR_OPTIONS).map(([value, label]) => (
                  <SelectItem key={value} value={value}>{value}. {label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        <div className="flex justify-end">
          <Button onClick={handleSave} disabled={saving}>
            {saving ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : null}
            Salva e prosegui <ArrowRight className="h-4 w-4 ml-1" />
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 2: Sostituire lo step Aziende nel wizard**

In `frontend/app/pratica/page.tsx`, aggiungi l'import:

```tsx
import { AnagraficheStep } from "@/components/pratica/AnagraficheStep";
```

Sostituisci l'intero blocco `{activeTab === "aziende" && ( … )}` (dal commento `{/* STEP 0: AZIENDE */}` fino alla sua chiusura) con:

```tsx
        {/* STEP 0: ANAGRAFICHE */}
        {activeTab === "anagrafiche" && (
          <AnagraficheStep
            onReady={(companyId) => {
              updatePratica({ companyId });
              setActiveTab("import");
            }}
          />
        )}
```

Elimina lo stato e gli effetti che alimentavano solo quel blocco — in particolare `existingScenarios` e l'effetto `loadExisting` che cicla su tutte le aziende (righe ~3630-3649). `npx tsc --noEmit` segnalerà ciò che resta orfano.

- [ ] **Step 3: Verificare la build**

```bash
cd frontend && npx tsc --noEmit && npm run build
```

Atteso: build completata.

- [ ] **Step 4: Commit**

```bash
git add frontend/components/pratica/AnagraficheStep.tsx frontend/app/pratica/page.tsx
git commit -m "feat(pratica): step Anagrafiche al posto dello step Aziende"
```

---

### Task 7: Gate Rettifiche

**Files:**
- Modify: `frontend/hooks/use-rettifiche-year.ts`
- Modify: `frontend/app/pratica/page.tsx` (`RettificheTab`, blocco `activeTab === "rettifiche"`)

**Interfaces:**
- Consumes: `RettificaEntry.entry_type` (Task 1); `usePratica()`.
- Produces: su `RettificheYear` due membri nuovi — `confirmed: boolean` e `confirm: () => Promise<void>`.

- [ ] **Step 1: Esporre `confirmed` e `confirm` dall'hook**

In `frontend/hooks/use-rettifiche-year.ts`, aggiungi all'interfaccia `RettificheYear` (dopo `applied`):

```ts
  /** L'utente ha premuto "Conferma e prosegui" su questo anno. */
  confirmed: boolean;
  /** Persiste il marker di conferma. Idempotente. */
  confirm: () => Promise<void>;
```

Aggiungi lo stato accanto agli altri `useState`:

```ts
  const [confirmed, setConfirmed] = useState(false);
```

Nell'effetto di invalidazione per identità (`useEffect` su `[companyId, year, periodMonths]`) e in `clear()`, aggiungi `setConfirmed(false);`.

In `load()`, dopo `setApplied(!!hasExisting);`:

```ts
      setConfirmed(
        (result.rettifiche_log ?? []).some((e) => e.entry_type === "confirm"),
      );
```

In `reset()`, dopo `setApplied(false);`, aggiungi `setConfirmed(false);` — il reset azzera il log, quindi anche la conferma.

Aggiungi il metodo prima del `return`:

```ts
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
```

e includili nel valore di ritorno:

```ts
  return { data, corrections, setCorrections, loading, saving, applied, confirmed, exists, load, save, reset, confirm, clear };
```

- [ ] **Step 2: Nascondere i marker dal journal**

In `frontend/app/pratica/page.tsx`, dove `RettificheTab` idrata il journal dal log salvato, filtra i marker. Cerca l'assegnazione che legge `adjustableData.rettifiche_log` (o `data.rettifiche_log`) dentro `RettificheTab` e avvolgila:

```tsx
  const visibleLog = (data?.rettifiche_log ?? []).filter((e) => e.entry_type !== "confirm");
```

Usa `visibleLog` per il pannello journal, per il dialogo Riepilogo e per il confronto con `RETTIFICHE_MAX`, così una conferma non conta come rettifica lato client.

- [ ] **Step 3: Aggiungere il bottone di conferma**

In fondo al blocco `activeTab === "rettifiche"` di `frontend/app/pratica/page.tsx`, sotto le due schede, aggiungi:

```tsx
        <div className="mt-6 flex items-center justify-between gap-4 rounded-lg border border-border bg-card p-4">
          <p className="text-sm text-muted-foreground">
            {allRettificheConfirmed
              ? "Rettifiche confermate. Puoi proseguire con il confronto."
              : "Conferma le rettifiche per sbloccare gli step successivi. Se il bilancio non quadra puoi confermare lo stesso: l'avviso resta."}
          </p>
          <Button
            onClick={async () => {
              await verifica.confirm();
              if (storico.exists) await storico.confirm();
              updatePratica({
                // Senza scheda storico non c'è nulla da confermare: vale true,
                // altrimenti il gate resterebbe chiuso per sempre.
                rettificheConfirmed: { verifica: true, storico: true },
              });
              setActiveTab("comparison");
            }}
            disabled={verifica.saving || storico.saving || allRettificheConfirmed}
          >
            Conferma e prosegui <ArrowRight className="h-4 w-4 ml-1" />
          </Button>
        </div>
```

con, accanto agli altri derivati del componente:

```tsx
  const allRettificheConfirmed = verifica.confirmed && (!storico.exists || storico.confirmed);
```

- [ ] **Step 4: Sincronizzare il context con il server**

Il context è una cache; la verità è il log. Aggiungi nel wizard un effetto che riallinea lo stepper quando i dati arrivano:

```tsx
  useEffect(() => {
    updatePratica({
      rettificheConfirmed: {
        verifica: verifica.confirmed,
        storico: storico.exists ? storico.confirmed : true,
      },
    });
    // updatePratica è stabile; dipendere dall'oggetto verifica/storico
    // rifarebbe scattare l'effetto a ogni render (vedi CLAUDE.md, Rettifiche).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [verifica.confirmed, storico.confirmed, storico.exists]);
```

- [ ] **Step 5: Verificare la build**

```bash
cd frontend && npx tsc --noEmit && npm run build
```

Atteso: build completata.

- [ ] **Step 6: Commit**

```bash
git add frontend/hooks/use-rettifiche-year.ts frontend/app/pratica/page.tsx
git commit -m "feat(pratica): le rettifiche vanno confermate per sbloccare gli step successivi"
```

---

### Task 8: Il ponte verso il Budget

**Files:**
- Modify: `frontend/app/pratica/page.tsx` (blocco del bottone promote, ~riga 5490-5510 del file originale)

**Interfaces:**
- Consumes: `promoteProjection`, `createBudgetScenario`, `getBudgetScenarios` da `@/lib/api`; `usePratica()`.
- Produces: `budgetScenarioId` valorizzato nel `PraticaContext` prima della navigazione a `/budget`.

- [ ] **Step 1: Sostituire l'handler**

In `frontend/app/pratica/page.tsx`, dentro `StampaContent`, sostituisci l'`onClick` del bottone di promote con:

```tsx
            onClick={async () => {
              setPromoting(true);
              try {
                const isAnnual = periodMonths === 12;
                let baseYear: number;
                if (isAnnual) {
                  // L'anno importato è già un FinancialYear completo: riscriverlo
                  // con una copia ricalcolata dal motore sarebbe un rischio inutile.
                  baseYear = fiscalYear;
                } else {
                  if (onBeforePromote) await onBeforePromote();
                  await promoteProjection(companyId, scenarioId);
                  baseYear = fiscalYear;
                }

                // Riuso, non duplicazione: doppio click o ritorno sui propri passi
                // non devono generare due scenari budget per lo stesso anno base.
                const existing = await getBudgetScenarios(companyId);
                const reusable = existing.find(
                  (s) => s.scenario_type !== "infrannuale" && s.base_year === baseYear,
                );
                const budget =
                  reusable ??
                  (await createBudgetScenario(companyId, {
                    company_id: companyId,
                    name: `Budget ${baseYear + 1}–${baseYear + 3}`,
                    base_year: baseYear,
                    scenario_type: "budget",
                  }));

                updatePratica({ budgetScenarioId: budget.id });
                await refreshCompanies();
                await refreshYears();
                toast.success(
                  reusable
                    ? "Scenario budget esistente riaperto"
                    : "Scenario budget creato",
                );
                router.push("/budget");
              } catch (err: unknown) {
                toast.error(getErrorMessage(err, "Errore nel passaggio al budget"));
              } finally {
                setPromoting(false);
              }
            }}
```

L'etichetta del bottone diventa `"Prosegui al Budget"` in entrambi i rami (sostituisce il ternario `periodMonths === 12 ? … : …`).

- [ ] **Step 2: Passare al componente ciò che gli serve**

`StampaContent` riceve già `companyId`, `scenarioId`, `periodMonths`, `onBeforePromote`. Aggiungi `fiscalYear: number` alle sue props e passalo dal chiamante (`fiscalYear={fiscalYear}`). Aggiungi gli import mancanti in cima al file: `createBudgetScenario`, `getBudgetScenarios` da `@/lib/api`, e `usePratica` se non già presente; dentro `StampaContent` aggiungi `const { updatePratica } = usePratica();`.

Se `getBudgetScenarios` non esiste con questo nome in `frontend/lib/api.ts`, usa la funzione già presente che elenca gli scenari di un'azienda (`GET /companies/{id}/scenarios`) — verificane il nome esatto con `grep -n "scenarios" frontend/lib/api.ts` e adegua la chiamata.

- [ ] **Step 3: Verificare la build**

```bash
cd frontend && npx tsc --noEmit && npm run build
```

Atteso: build completata.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/pratica/page.tsx
git commit -m "feat(pratica): il passaggio al budget crea (o riusa) lo scenario, niente promote a 12 mesi"
```

---

### Task 9: Home con due percorsi

**Files:**
- Modify: `frontend/app/page.tsx:191-237` (le card), `:169-172` (`resume`)

**Interfaces:**
- Consumes: `usePratica()`, `buildPraticaSteps` non serve qui.
- Produces: niente per i task successivi.

- [ ] **Step 1: Ridurre le card da tre a due**

In `frontend/app/page.tsx`, aggiungi `import { usePratica } from "@/contexts/PraticaContext";` e `const { startPratica } = usePratica();` nel componente. Sostituisci l'intero blocco `{showNewPratica && ( … )}` con:

```tsx
      {showNewPratica && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
          <Card className="cursor-pointer transition-colors hover:border-primary/50"
            onClick={() => {
              setStartupMode(false);
              // companyId resta null: l'azienda si sceglie o si crea nello step Anagrafiche.
              startPratica({ workflow: "bilancio", companyId: null, analysisStep: "anagrafiche" });
              router.push("/pratica");
            }}>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <CalendarRange className="h-5 w-5 text-primary" /> Da bilancio
              </CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-muted-foreground">
              Bilancio ufficiale o bilancio di verifica infrannuale. Import, rettifiche,
              confronto e budget in un unico percorso.
              <Button variant="outline" size="sm" className="mt-3 w-full">
                Avvia percorso <ArrowRight className="h-4 w-4" />
              </Button>
            </CardContent>
          </Card>
          <Card className="cursor-pointer transition-colors hover:border-primary/50"
            onClick={() => {
              setStartupMode(true);
              setSelectedCompanyId(null);
              startPratica({ workflow: "startup", companyId: null, analysisStep: "anagrafiche" });
              router.push("/budget");
            }}>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Rocket className="h-5 w-5 text-primary" /> Startup
              </CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-muted-foreground">
              Business plan senza bilancio storico.
              <Button variant="outline" size="sm" className="mt-3 w-full">
                Crea business plan <ArrowRight className="h-4 w-4" />
              </Button>
            </CardContent>
          </Card>
        </div>
      )}
```

Definisci `const selectedCompanyIdOrNull = null;` **no** — passa semplicemente `companyId: null`: la scelta dell'azienda avviene nello step Anagrafiche. Sostituisci quindi quella riga con `startPratica({ workflow: "bilancio", companyId: null, analysisStep: "anagrafiche" })`.

Rimuovi l'import ora inutilizzato di `CalendarClock` da `lucide-react`.

Nota: `tsconfig.json` ha `strict: true` ma **non** `noUnusedLocals`, quindi una variabile inutilizzata non fa fallire `tsc`. La segnalerà `next lint`: rimuovila comunque.

- [ ] **Step 2: `resume` popola il context**

Sostituisci `resume` (righe 169-172) con:

```tsx
  // Riprendi una pratica: popola il context, poi apri il posto giusto.
  // Uno scenario budget legacy non ha una fase ANALISI ricostruibile: si apre
  // direttamente sul budget, con gli step di analisi disabilitati.
  const resume = (companyId: number, s: ScenarioSummary) => {
    setSelectedCompanyId(companyId);
    const isInfra = s.scenario_type === "infrannuale";
    startPratica({
      workflow: "bilancio",
      companyId,
      fiscalYear: isInfra ? s.base_year + 1 : s.base_year,
      periodMonths: isInfra ? s.period_months ?? 12 : 12,
      infrannualeScenarioId: isInfra ? s.id : null,
      budgetScenarioId: isInfra ? null : s.id,
      analysisStep: isInfra ? "rettifiche" : "anagrafiche",
    });
    router.push(isInfra ? "/pratica" : "/budget");
  };
```

- [ ] **Step 3: Verificare la build**

```bash
cd frontend && npx tsc --noEmit && npm run build
```

Atteso: build completata.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/page.tsx
git commit -m "feat(home): due soli percorsi per una nuova pratica"
```

---

### Task 10: Pulizia di `/budget`

`/budget` smette di essere un ingresso e perde la versione monca delle rettifiche.

**Files:**
- Modify: `frontend/app/budget/page.tsx:84`, `:1214`, `:203`
- Delete: `frontend/components/budget/HistoricalBalanceDetailEditor.tsx`

**Interfaces:**
- Consumes: niente.
- Produces: niente.

- [ ] **Step 1: Rimuovere l'editor ridotto**

In `frontend/app/budget/page.tsx` elimina l'import di riga 84 e l'uso di riga 1214:

```tsx
import { HistoricalBalanceDetailEditor } from "@/components/budget/HistoricalBalanceDetailEditor";
```

```tsx
              <HistoricalBalanceDetailEditor companyId={companyId} year={baseYear} />
```

Poi:

```bash
git rm frontend/components/budget/HistoricalBalanceDetailEditor.tsx
```

- [ ] **Step 2: Verificare se il catalogo resta usato**

```bash
cd frontend && grep -rn "ivcee-balance-catalog" --include=*.ts --include=*.tsx .
```

Se l'unico riferimento era il file appena eliminato, rimuovi anche `frontend/lib/ivcee-balance-catalog.ts` con `git rm`. Se altri file lo usano, lascialo.

- [ ] **Step 3: Reindirizzare il messaggio di anno mancante**

Riga 203, il testo "Nessun anno fiscale trovato. Importa prima i dati del bilancio." non deve più mandare l'utente a un import fuori percorso. Sostituiscilo con:

```tsx
            Nessun anno fiscale trovato. Avvia una pratica dalla home per importare
            un bilancio.
```

- [ ] **Step 4: Togliere la creazione manuale di scenario fuori dal percorso**

`/budget` non è più un ingresso: lo scenario budget lo crea il percorso (Task 8). Il bottone
"Nuovo Scenario" resta però utile **dentro** una pratica, per aggiungere un secondo scenario a un
anno base già importato e rettificato — lì il rischio che si voleva chiudere (budget su dati non
rettificati) non esiste. Lo si nasconde quindi solo fuori dalla pratica.

In `frontend/app/budget/page.tsx` aggiungi `import { usePratica } from "@/contexts/PraticaContext";`
e `const { pratica } = usePratica();` nel componente. Poi, nel blocco alle righe 228-250, sostituisci
il ramo non-startup:

```tsx
            ) : pratica ? (
              <Button onClick={() => setActiveTab("info")}>
                <Plus className="h-4 w-4" />
                Nuovo Scenario
              </Button>
            ) : null}
```

- [ ] **Step 5: Verificare la build**

```bash
cd frontend && npx tsc --noEmit && npm run build
```

Atteso: build completata, nessun riferimento residuo a `HistoricalBalanceDetailEditor`.

- [ ] **Step 6: Commit**

```bash
git add -A frontend/app/budget/page.tsx frontend/components/budget frontend/lib
git commit -m "refactor(budget): via l'editor rettifiche ridotto, le rettifiche vere sono nel percorso"
```

---

### Task 11: Verifica end-to-end e documentazione

Nessun test automatico frontend esiste: questa task è il vero gate comportamentale del piano.

**Files:**
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: tutto il lavoro precedente.
- Produces: niente.

- [ ] **Step 1: Avviare backend e frontend**

Terminale 1, dalla root:

```bash
cd backend && source venv/bin/activate && \
  DEV_USER_ID=dev-user-001 uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Terminale 2:

```bash
cd frontend && npm run dev
```

- [ ] **Step 2: Percorso 1 — bilancino infrannuale**

Con l'agente `playwright-frontend-tester` (o a mano) su `http://localhost:3000`, usando un PDF di `docs/examples/` con periodo parziale:

1. Home → "Nuova pratica" → **Da bilancio** → lo stepper compare al posto della nav.
2. Anagrafiche: crea l'azienda → si passa a Import.
3. Import: carica il PDF con periodo 9 mesi.
4. **Verifica che "Confronto" sia disabilitato** nello stepper.
5. Rettifiche: conferma → gli step si sbloccano e si apre Confronto.
6. Confronto → Proiezione → Indicatori → Stampa → "Prosegui al Budget".
7. **Verifica** che `/budget` si apra con l'azienda selezionata e lo scenario `Budget {y+1}–{y+3}` presente, e che la barra mostri "Budget" attivo nella fase PREVISIONALE.

- [ ] **Step 3: Percorso 2 — bilancio annuale**

Stesso flusso con periodo 12 mesi. **Verifiche specifiche:**

- Lo step "Proiezione" **non compare** nello stepper.
- Prima di premere "Prosegui al Budget", annota i valori dell'anno importato:

```bash
curl -s "http://localhost:8000/api/v1/companies/{ID}/years/{ANNO}/adjustable" | head -c 400
```

Dopo il passaggio al budget, ripeti la stessa chiamata: **i valori devono essere identici** (nessun `promote` ha riscritto il `FinancialYear`).

- Lo scenario budget creato ha `base_year` = anno importato:

```bash
curl -s "http://localhost:8000/api/v1/companies/{ID}/scenarios" | head -c 400
```

- [ ] **Step 4: Percorso 3 — startup**

Home → **Startup** → lo stepper mostra 5 voci senza la fase ANALISI → crea il business plan → Budget → CE Previsionale → Report.

- [ ] **Step 5: Persistenza del gate e uscita**

1. Nel percorso 1, dopo aver confermato le rettifiche, premi `F5`: gli step restano sbloccati.
2. Torna su Rettifiche e premi il reset: gli step successivi si richiudono.
3. Premi "Esci dalla pratica": si torna a `/`, riappare la nav normale **senza** la tab Importazione.

- [ ] **Step 6: Aggiornare CLAUDE.md**

Nella sezione "Frontend Pages" sostituisci la voce `/infrannuale` con:

```markdown
- `/pratica` - Percorso unico da bilancio (Anagrafiche → Import → Rettifiche → Confronto → [Proiezione] → Indicatori → Stampa → Budget). `/infrannuale` reindirizza qui.
```

Aggiungi dopo la sezione "Rettifiche (BS/IS Adjustments Journal)" una sottosezione:

```markdown
#### Il percorso unico "Pratica" (2026-08-08)
Due soli workflow per una nuova pratica: **Da bilancio** (`/pratica`) e **Startup** (`/budget` in
`startupMode`). Il percorso "budget da bilancio ufficiale senza rettifiche" è stato rimosso: i
bilanci di verifica arrivano quasi sempre sporchi e saltare le rettifiche propaga l'errore su
confronto, proiezione, indicatori e rating.

- **`contexts/PraticaContext.tsx`** — pratica attiva persistita in `localStorage` (stesso pattern
  di `startupMode`: lettura in `useEffect`, mai nell'inizializzatore di `useState`, o Next sbaglia
  l'idratazione). `PraticaProvider` sta SOPRA `AppProvider`.
- **`lib/pratica-steps.ts`** — modello puro degli step. `kind: "tab"` = tab interna a `/pratica`;
  `kind: "route"` = pagina Next. Lo step "projection" non esiste con `periodMonths === 12`.
- **`components/PraticaStepper.tsx`** — reso da `Navigation`, che ritorna lo stepper INVECE della
  nav quando una pratica è attiva e il pathname non è `/`. Mai due barre.
- **Gate Rettifiche:** una voce `{ entry_type: "confirm" }` nel `rettifiche_log` già esistente —
  nessuna colonna, nessuna migrazione. È idempotente, è esclusa dal journal e dal dialogo
  Riepilogo, e `_countable_log_entries` la esclude dal cap di 20 lato server. Il reset la azzera.
- **Ponte al budget:** a periodo < 12 mesi si fa `promote` come prima; **a 12 mesi no** — l'anno
  importato è già un `FinancialYear` completo. In entrambi i casi lo scenario budget viene creato
  o RIUSATO per `base_year`, così doppio click e ritorni sui propri passi non duplicano nulla.
- `HistoricalBalanceDetailEditor` è stato eliminato: era una seconda implementazione monca delle
  rettifiche, raggiungibile da `/budget`.
```

- [ ] **Step 7: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: CLAUDE.md allineato al percorso unico Pratica"
```

---

## Note per chi esegue

- **`app/pratica/page.tsx` è un monolite da ~5.800 righe.** Le Task 5-8 ci lavorano dentro. Lavora per ricerca mirata (`grep -n`), non leggendo il file intero, e verifica ogni modifica con `npx tsc --noEmit` prima di passare alla successiva.
- **Mai mettere l'oggetto `verifica`/`storico` in una dependency array di `useEffect`** — l'hook restituisce un oggetto nuovo a ogni render e l'effetto si riattiverebbe all'infinito. Dipendi dai singoli campi. È documentato in CLAUDE.md, sezione Rettifiche.
- I numeri di riga citati sono quelli di `78fcbac` e si spostano man mano che il piano procede: usali come indizio, non come coordinate assolute.
