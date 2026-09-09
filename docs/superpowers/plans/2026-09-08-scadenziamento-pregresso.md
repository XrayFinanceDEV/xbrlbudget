# Scadenziamento del pregresso (lotto 2) — piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Il motore budget separa i saldi del circolante che esistono già (e come si chiudono) da quelli che il piano genera, e paga le imposte a saldo più acconto.

**Architecture:** Due kernel puri in `projection_common.py` (`runoff_schedule`, `tax_settlement_saldo_acconto`), un piano `pregresso` in JSON sulla riga del primo anno di `BudgetAssumptions`, validato contro le masse di apertura del bilancio base; in `_calculate_balance_sheet` ogni saldo con piano diventa generato + residuo, classificato a breve o oltre per scadenza; l'inesigibile va in `ce09d`. Tutto passa dai `details` dell'anteprima del lotto 1, e i passi 6 e 7 del wizard accendono i controlli lasciati spenti.

**Tech Stack:** come il lotto 1. Migrazione additiva con `migrate_db.py`.

**Spec:** `docs/superpowers/specs/2026-09-08-scadenziamento-pregresso-design.md`. **Prerequisito:** il lotto 1 (`2026-09-08-percorso-ipotesi-budget.md`) mergiato: `compute_forecast`, `details`, `build_assumption_row`, il wizard e `useScenarioAssumptions`.

## Global Constraints

- `projection_common.tax_closing_position` **non cambia**: la usa l'infrannuale. `intra_year_engine.py` non si tocca (spec §9).
- Senza piano, i quattro saldi non tributari producono **gli stessi numeri di oggi** al centesimo (spec §2); le imposte cambiano per costruzione e la spec lo dichiara.
- Superare la massa di apertura è un **errore**, mai un troncamento (spec §4).
- `pregresso` vive **solo** sulla riga del primo anno di piano (spec §3.5); la massa di apertura dichiarata deve coincidere con il bilancio base (±0,01).
- `details` sempre dichiarati, anche a zero (CLAUDE.md › Invarianti).
- Soldi in `Decimal`; quantizzazione al centesimo nel punto in cui il lotto 1 già la fa.
- Frontend: `lib/budget-*` puro, nessun import da `app/`/`components/`; euro canonico nel JSON, percentuale come vista.
- Branch dedicato `feat/scadenziamento-pregresso`, partendo da `main` dopo il merge del lotto 1. Commit prima di dispacciare agenti.
- Comandi: backend `cd /home/peter/DEV/budget && backend/venv/bin/python -m pytest <file> -v`; frontend `cd frontend && npx vitest run <pattern>`, `npx tsc --noEmit`.

## Ondate ed esecuzione parallela

```
Ondata A (parallela):  1 · 2 · 3 · 4
Ondata B (sequenziale, stesso file): 5 (dopo 1,3) → 6 (dopo 2,3,5)
Ondata C (parallela):  7 (dopo 4,5) · 8 (dopo 4,6)
Ondata D:              9 (haiku) · 10 (collaudatore)
```

| Task | Modello | Perché |
|---|---|---|
| 3, 9 | haiku | colonna, migrazione, schema, tipi; testo |
| 1, 2, 4, 7, 8 | sonnet | kernel puri con test; modulo puro TS; due passi del wizard |
| 5, 6 | opus | il motore: parità al centesimo e la nuova posizione tributaria |
| 10 | collaudatore | browser reale |

---

## File map

- Modify `calculations/projection_common.py` — `RunoffYear`, `runoff_schedule()`, `TaxYear`, `tax_settlement_saldo_acconto()`, `pregresso_opening_masses()`.
- Modify `calculations/forecast_engine.py` — `validate_pregresso()`, lettura del piano in `compute_forecast`, `_calculate_balance_sheet` (quattro saldi + imposte), `_calculate_income_statement` (`ce09d`), `details.pregresso` / `details.imposte` / `details.pregresso_ignored`.
- Modify `database/models.py` (`pregresso = Column(JSON, nullable=True)`), `migrate_db.py`, `backend/app/schemas/budget.py` (`PregressoInput` e sotto-modelli, campo su Base/Update), `backend/app/services/assumptions_service.py` (`build_assumption_row`: `pregresso=jsonable_encoder(...)`).
- Create `tests/test_projection_common_runoff.py`, `tests/test_budget_pregresso.py`.
- Frontend: `types/api.ts` (tipi `Pregresso*`, `details` estesi), `lib/budget-pregresso.ts` (+ test), `lib/budget-preview-rows.ts` (+ righe nuove nei test), `hooks/use-scenario-assumptions.ts` (idrata `pregresso`), `components/budget/wizard/steps/StepPregressoNuovo.tsx`, `steps/StepImposte.tsx`, `components/budget/wizard/PregressoTable.tsx`.

---

## Ondata A

### Task 1: Kernel `runoff_schedule`

**Modello:** sonnet · **Ondata:** A

**Files:**
- Modify: `calculations/projection_common.py` (in fondo)
- Test: `tests/test_projection_common_runoff.py`

**Interfaces:**
- Produces:

```python
@dataclass(frozen=True)
class RunoffYear:
    opening: Decimal; closed: Decimal; writeoff: Decimal
    residual: Decimal; residual_short: Decimal; residual_long: Decimal

def validate_runoff(opening, amounts, writeoff, horizon, label) -> None      # ValueError con messaggi in italiano
def runoff_schedule(opening, amounts, writeoff, year_index, horizon) -> RunoffYear
```

Semantica (spec §3.3): `closed` e `writeoff` sono gli importi dell'anno `year_index` (0 = primo anno); `residual` = apertura − cumulati fino a quell'anno compreso; `residual_short` = importo del piano dovuto in `year_index + 1` (0 se oltre la lista o l'orizzonte); `residual_long` = il resto.

- [ ] **Step 1: Test**

```python
# tests/test_projection_common_runoff.py
from decimal import Decimal as D

import pytest

from calculations.projection_common import runoff_schedule, validate_runoff


def test_full_plan_in_first_year_leaves_nothing():
    y0 = runoff_schedule(D("1000"), [D("1000")], [], 0, 3)
    assert (y0.closed, y0.residual, y0.residual_short, y0.residual_long) == (D("1000"), D("0"), D("0"), D("0"))
    y1 = runoff_schedule(D("1000"), [D("1000")], [], 1, 3)
    assert y1.closed == D("0") and y1.residual == D("0")


def test_eighty_twenty_moves_the_residual_to_short_then_closes():
    y0 = runoff_schedule(D("1000"), [D("800"), D("200")], [], 0, 3)
    assert y0.residual == D("200") and y0.residual_short == D("200") and y0.residual_long == D("0")
    y1 = runoff_schedule(D("1000"), [D("800"), D("200")], [], 1, 3)
    assert y1.closed == D("200") and y1.residual == D("0")


def test_short_plan_leaves_the_rest_long_and_writeoff_is_not_a_collection():
    y0 = runoff_schedule(D("1000"), [D("300")], [D("50")], 0, 3)
    assert y0.writeoff == D("50")
    assert y0.residual == D("650")
    assert y0.residual_short == D("0") and y0.residual_long == D("650")
    y2 = runoff_schedule(D("1000"), [D("300")], [D("50")], 2, 3)
    assert y2.closed == D("0") and y2.residual == D("650") and y2.residual_long == D("650")


def test_three_equal_instalments_reclassify_by_maturity():
    plan = [D("33.34"), D("33.33"), D("33.33")]
    y0 = runoff_schedule(D("100"), plan, [], 0, 3)
    assert y0.residual_short == D("33.33") and y0.residual_long == D("33.33")
    y1 = runoff_schedule(D("100"), plan, [], 1, 3)
    assert y1.residual_short == D("33.33") and y1.residual_long == D("0")


@pytest.mark.parametrize("amounts,writeoff,msg", [
    ([D("700"), D("400")], [], "supera il saldo"),
    ([D("-1")], [], "negativ"),
    ([D("1"), D("1"), D("1"), D("1")], [], "orizzonte"),
    ([D("900")], [D("200")], "supera il saldo"),
])
def test_validation_errors(amounts, writeoff, msg):
    with pytest.raises(ValueError, match=msg):
        validate_runoff(D("1000"), amounts, writeoff, 3, "crediti commerciali")
```

- [ ] **Step 2: Eseguire, vedere fallire** — `backend/venv/bin/python -m pytest tests/test_projection_common_runoff.py -v` → FAIL (import).

- [ ] **Step 3: Implementare**

```python
# calculations/projection_common.py (in fondo)
from dataclasses import dataclass

CENT = Decimal('0.01')


@dataclass(frozen=True)
class RunoffYear:
    opening: Decimal
    closed: Decimal
    writeoff: Decimal
    residual: Decimal
    residual_short: Decimal
    residual_long: Decimal


def _dec_list(values):
    return [Decimal(str(v or 0)) for v in (values or [])]


def validate_runoff(opening, amounts, writeoff, horizon, label):
    """Errori in italiano, per l'utente: negativo, oltre l'orizzonte, oltre la massa."""
    amounts, writeoff = _dec_list(amounts), _dec_list(writeoff)
    if any(a < ZERO for a in amounts) or any(w < ZERO for w in writeoff):
        raise ValueError(f"Scadenziamento di {label}: un importo è negativo")
    if len(amounts) > horizon or len(writeoff) > horizon:
        raise ValueError(f"Scadenziamento di {label}: il piano va oltre l'orizzonte di {horizon} anni")
    total = sum(amounts, ZERO) + sum(writeoff, ZERO)
    if total - Decimal(str(opening)) > CENT:
        raise ValueError(
            f"Scadenziamento di {label}: gli importi ({total:.2f}) superano il saldo di apertura ({Decimal(str(opening)):.2f})")


def runoff_schedule(opening, amounts, writeoff, year_index, horizon) -> RunoffYear:
    """Residuo del pregresso dopo l'anno `year_index` e la sua scadenza.

    `residual_short` e' l'importo dovuto nell'anno dopo (spec §3.3); tutto il
    resto e' oltre 12 mesi. Non valida: chiamare validate_runoff prima del ciclo.
    """
    opening = Decimal(str(opening))
    amounts, writeoff = _dec_list(amounts), _dec_list(writeoff)
    at = lambda lst, i: lst[i] if 0 <= i < len(lst) else ZERO
    closed = at(amounts, year_index)
    wo = at(writeoff, year_index)
    residual = opening - sum(amounts[:year_index + 1], ZERO) - sum(writeoff[:year_index + 1], ZERO)
    residual = max(ZERO, residual)
    due_next = at(amounts, year_index + 1) if year_index + 1 < horizon else ZERO
    residual_short = min(residual, due_next)
    return RunoffYear(opening=opening, closed=closed, writeoff=wo, residual=residual,
                      residual_short=residual_short, residual_long=residual - residual_short)
```

- [ ] **Step 4: Verificare** — PASS.
- [ ] **Step 5: Commit** — `git add calculations/projection_common.py tests/test_projection_common_runoff.py && git commit -m "feat(engine): kernel runoff_schedule per il pregresso"`

---

### Task 2: Kernel `tax_settlement_saldo_acconto`

**Modello:** sonnet · **Ondata:** A

**Files:**
- Modify: `calculations/projection_common.py` (dopo `tax_closing_position`, che resta)
- Test: `tests/test_projection_common_runoff.py` (stesso file, sezione imposte)

**Interfaces:**
- Produces:

```python
@dataclass(frozen=True)
class TaxYear:
    saldo_paid: Decimal; acconti_paid: Decimal; rate_paid: Decimal
    generated_debt: Decimal; generated_credit: Decimal; opening_credit_left: Decimal; cash_out: Decimal

def tax_settlement_saldo_acconto(*, opening_credit, saldo_due, rate_due, current_tax, previous_tax, acconto_pct, explicit_advances) -> TaxYear
```

- [ ] **Step 1: Test**

```python
from calculations.projection_common import tax_settlement_saldo_acconto


def test_constant_tax_with_full_advance_generates_no_debt_and_pays_the_tax():
    t = tax_settlement_saldo_acconto(opening_credit=D("0"), saldo_due=D("0"), rate_due=D("0"),
                                     current_tax=D("100"), previous_tax=D("100"), acconto_pct=D("100"), explicit_advances=None)
    assert t.acconti_paid == D("100") and t.generated_debt == D("0") and t.generated_credit == D("0")
    assert t.cash_out == D("100")


def test_falling_tax_generates_a_credit_and_rising_tax_a_debt():
    down = tax_settlement_saldo_acconto(opening_credit=D("0"), saldo_due=D("0"), rate_due=D("0"),
                                        current_tax=D("60"), previous_tax=D("100"), acconto_pct=D("100"), explicit_advances=None)
    assert down.generated_credit == D("40") and down.generated_debt == D("0")
    up = tax_settlement_saldo_acconto(opening_credit=D("0"), saldo_due=D("0"), rate_due=D("0"),
                                      current_tax=D("130"), previous_tax=D("100"), acconto_pct=D("100"), explicit_advances=None)
    assert up.generated_debt == D("30")


def test_opening_credit_offsets_the_saldo_and_explicit_advances_win():
    t = tax_settlement_saldo_acconto(opening_credit=D("25"), saldo_due=D("40"), rate_due=D("10"),
                                     current_tax=D("100"), previous_tax=D("100"), acconto_pct=D("100"), explicit_advances=D("70"))
    assert t.saldo_paid == D("15") and t.opening_credit_left == D("0")
    assert t.acconti_paid == D("70") and t.generated_debt == D("30")
    assert t.rate_paid == D("10") and t.cash_out == D("15") + D("70") + D("10")
    big = tax_settlement_saldo_acconto(opening_credit=D("100"), saldo_due=D("40"), rate_due=D("0"),
                                       current_tax=D("0"), previous_tax=D("0"), acconto_pct=D("0"), explicit_advances=None)
    assert big.saldo_paid == D("0") and big.opening_credit_left == D("60") and big.acconti_paid == D("0")
```

- [ ] **Step 2: Eseguire, vedere fallire.**

- [ ] **Step 3: Implementare**

```python
@dataclass(frozen=True)
class TaxYear:
    saldo_paid: Decimal
    acconti_paid: Decimal
    rate_paid: Decimal
    generated_debt: Decimal
    generated_credit: Decimal
    opening_credit_left: Decimal
    cash_out: Decimal


def tax_settlement_saldo_acconto(*, opening_credit, saldo_due, rate_due, current_tax,
                                 previous_tax, acconto_pct, explicit_advances) -> TaxYear:
    """Imposte a saldo + acconto (spec lotto 2 §3.2). Solo il motore budget:
    l'infrannuale continua a usare tax_closing_position."""
    d = lambda v: Decimal(str(v or 0))
    opening_credit, saldo_due, rate_due = d(opening_credit), d(saldo_due), d(rate_due)
    current_tax, previous_tax = d(current_tax), d(previous_tax)
    if explicit_advances is not None and d(explicit_advances) > ZERO:
        acconti = d(explicit_advances)
    else:
        acconti = max(ZERO, previous_tax * d(acconto_pct) / Decimal('100'))
    used = min(opening_credit, saldo_due)
    saldo_paid = saldo_due - used
    net = current_tax - acconti
    return TaxYear(
        saldo_paid=saldo_paid, acconti_paid=acconti, rate_paid=rate_due,
        generated_debt=max(ZERO, net), generated_credit=max(ZERO, -net),
        opening_credit_left=opening_credit - used,
        cash_out=saldo_paid + acconti + rate_due,
    )
```

- [ ] **Step 4: Verificare** — `pytest tests/test_projection_common_runoff.py tests/test_budget_remediation_plan.py -v` → PASS (il vecchio kernel è intatto).
- [ ] **Step 5: Commit** — `git commit -am "feat(engine): kernel tax_settlement_saldo_acconto"` (aggiungere il test).

---

### Task 3: Colonna, migrazione, schema, mapping

**Modello:** haiku · **Ondata:** A

**Files:**
- Modify: `database/models.py:656` (dopo `financing_loans`), `migrate_db.py:92` (blocco `budget_assumptions`), `backend/app/schemas/budget.py` (dopo `TemporaryDifferenceInput`, `:93`; campo in `BudgetAssumptionsBase` e `BudgetAssumptionsUpdate`), `backend/app/services/assumptions_service.py` (`build_assumption_row`), `frontend/types/api.ts`
- Test: `tests/test_budget_pregresso.py` (prima sezione: schema)

**Interfaces:**
- Produces (Pydantic):

```python
class PregressoPlanInput(BaseModel):
    opening: Decimal = Field(..., ge=0)
    amounts: List[Decimal] = Field(default_factory=list)
    writeoff: Optional[List[Decimal]] = None          # solo crediti_commerciali
class PregressoTributariInput(PregressoPlanInput):
    saldo: Decimal = Field(default=Decimal("0"), ge=0)
    rateizzato: Decimal = Field(default=Decimal("0"), ge=0)
    acconto_pct: Decimal = Field(default=Decimal("100"), ge=0, le=200)
class PregressoInput(BaseModel):
    crediti_commerciali: Optional[PregressoPlanInput] = None
    debiti_fornitori: Optional[PregressoPlanInput] = None
    debiti_tributari: Optional[PregressoTributariInput] = None
    debiti_previdenziali: Optional[PregressoPlanInput] = None
    altri_debiti: Optional[PregressoPlanInput] = None
# in BudgetAssumptionsBase e BudgetAssumptionsUpdate:
    pregresso: Optional[PregressoInput] = None
```

- Produces (TS, `types/api.ts`):

```ts
export type PregressoKey = "crediti_commerciali" | "debiti_fornitori" | "debiti_tributari" | "debiti_previdenziali" | "altri_debiti";
export interface PregressoPlan { opening: number; amounts: number[]; writeoff?: number[] | null }
export interface PregressoTributari extends PregressoPlan { saldo: number; rateizzato: number; acconto_pct: number }
export interface Pregresso { crediti_commerciali?: PregressoPlan | null; debiti_fornitori?: PregressoPlan | null;
  debiti_tributari?: PregressoTributari | null; debiti_previdenziali?: PregressoPlan | null; altri_debiti?: PregressoPlan | null }
// in BudgetAssumptions e BudgetAssumptionsCreate: pregresso?: Pregresso | null;
export interface PregressoDetail { opening: number; closed: number; writeoff: number; residual_short: number; residual_long: number; generated: number; mode: "legacy" | "runoff" }
export interface ImposteDetail { current_tax: number; saldo_paid: number; acconti_paid: number; rate_paid: number; generated_debt: number; generated_credit: number; opening_credit_left: number; mode: "saldo_acconto" | "manual" }
// in ForecastYearDetails: pregresso: Record<PregressoKey, PregressoDetail>; imposte: ImposteDetail; pregresso_ignored: PregressoKey[];
```

- [ ] **Step 1: Test dello schema e del mapping**

```python
# tests/test_budget_pregresso.py
from decimal import Decimal as D

import pytest
from pydantic import ValidationError

from backend.app.schemas.budget import BudgetAssumptionsCreate, PregressoInput
from backend.app.services.assumptions_service import build_assumption_row


def test_schema_accepts_a_plan_and_rejects_negatives():
    p = PregressoInput(crediti_commerciali={"opening": 1000, "amounts": [800, 200], "writeoff": [0, 0]},
                       debiti_tributari={"opening": 96, "saldo": 61, "rateizzato": 35, "amounts": [12, 12, 11]})
    assert p.debiti_tributari.acconto_pct == D("100")
    with pytest.raises(ValidationError):
        PregressoInput(debiti_fornitori={"opening": -1, "amounts": []})


def test_build_assumption_row_carries_pregresso_as_json():
    row = build_assumption_row(1, {"forecast_year": 2027, "pregresso": {"altri_debiti": {"opening": D("10"), "amounts": [D("10")]}}})
    assert row.pregresso == {"altri_debiti": {"opening": 10.0, "amounts": [10.0]}}
    assert build_assumption_row(1, {"forecast_year": 2027}).pregresso is None
```

- [ ] **Step 2: Eseguire, vedere fallire.**

- [ ] **Step 3: Implementare** — `models.py`: `pregresso = Column(JSON, nullable=True)  # Scadenziamento del pregresso, solo riga del primo anno (spec lotto 2)`; `migrate_db.py`: `("pregresso", "TEXT"),` in coda al blocco `budget_assumptions`; schemi come sopra; `build_assumption_row`: `pregresso=jsonable_encoder(data.get("pregresso", None)),`; tipi TS. In `frontend/hooks/use-scenario-assumptions.ts` aggiungere `pregresso: a.pregresso ?? null,` alla mappa di idratazione (accanto a `financing_loans`): senza, il salvataggio lo cancella.

- [ ] **Step 4: Verificare** — `pytest tests/test_budget_pregresso.py tests/test_build_assumption_row.py -v`; `cd frontend && npx tsc --noEmit`; `backend/venv/bin/python migrate_db.py` su una copia del DB (`DATABASE_PATH=/tmp/copia.db`) e leggere `ADD budget_assumptions.pregresso`.
- [ ] **Step 5: Commit** — `git add database/models.py migrate_db.py backend/app/schemas/budget.py backend/app/services/assumptions_service.py frontend/types/api.ts frontend/hooks/use-scenario-assumptions.ts tests/test_budget_pregresso.py && git commit -m "feat(budget): colonna pregresso, schema, mapping e tipi"`

---

### Task 4: `lib/budget-pregresso.ts`

**Modello:** sonnet · **Ondata:** A

**Files:**
- Create: `frontend/lib/budget-pregresso.ts`, `frontend/lib/budget-pregresso.test.ts`

**Interfaces:**
- Produces:

```ts
export const PREGRESSO_LABELS: Record<PregressoKey, string>;   // "Crediti commerciali", "Debiti verso fornitori", "Debiti tributari", "Debiti previdenziali", "Altri debiti"
export function openingMasses(bs: BalanceSheet): Record<PregressoKey, number>;   // spec §3.1, stessa tabella
export function residualAfter(plan: PregressoPlan, yearIndex: number): number;
export function amountToPct(amount: number, opening: number): number | null;
export function pctToAmount(pct: number, opening: number): number;               // arrotondato al centesimo
export function equalInstalments(total: number, n: number): number[];            // i centesimi sull'ultima
export function validatePregresso(p: Pregresso, masses: Record<PregressoKey, number>, horizon: number): string[];
export function withAmount(plan: PregressoPlan, yearIndex: number, amount: number): PregressoPlan;   // immutabile, allunga con zeri
```

- [ ] **Step 1: Test**

```ts
import { describe, expect, it } from "vitest";
import type { BalanceSheet } from "@/types/api";
import { equalInstalments, openingMasses, pctToAmount, residualAfter, validatePregresso, withAmount } from "./budget-pregresso";

const bs = { sp06_crediti_breve: "500", sp06e_crediti_tributari_breve: "20", sp06f_imposte_anticipate_breve: "10",
  sp07_crediti_lungo: "40", sp07e_crediti_tributari_lungo: "0", sp07f_imposte_anticipate_lungo: "0",
  sp16d_debiti_fornitori_breve: "300", sp17d_debiti_fornitori_lungo: "0", sp16e_debiti_tributari_breve: "61",
  sp17e_debiti_tributari_lungo: "35", sp16f_debiti_previdenza_breve: "41", sp17f_debiti_previdenza_lungo: "0",
  sp16g_altri_debiti_breve: "58", sp17g_altri_debiti_lungo: "0" } as unknown as BalanceSheet;

describe("budget-pregresso", () => {
  it("masse di apertura come la spec §3.1", () => {
    expect(openingMasses(bs)).toEqual({ crediti_commerciali: 510, debiti_fornitori: 300, debiti_tributari: 96,
      debiti_previdenziali: 41, altri_debiti: 58 });
  });
  it("rate uguali con i centesimi sull'ultima, residuo, percentuali", () => {
    expect(equalInstalments(100, 3)).toEqual([33.33, 33.33, 33.34]);
    expect(residualAfter({ opening: 1000, amounts: [800], writeoff: [50] }, 0)).toBe(150);
    expect(pctToAmount(33.333, 1000)).toBe(333.33);
    expect(withAmount({ opening: 100, amounts: [10] }, 2, 5)).toEqual({ opening: 100, amounts: [10, 0, 5] });
  });
  it("validazione: massa, orizzonte, tributari", () => {
    const masses = openingMasses(bs);
    expect(validatePregresso({ debiti_fornitori: { opening: 300, amounts: [200, 200] } }, masses, 3)[0]).toMatch(/supera/);
    expect(validatePregresso({ debiti_fornitori: { opening: 299, amounts: [] } }, masses, 3)[0]).toMatch(/apertura/);
    expect(validatePregresso({ altri_debiti: { opening: 58, amounts: [1, 1, 1, 1] } }, masses, 3)[0]).toMatch(/orizzonte/);
    expect(validatePregresso({ debiti_tributari: { opening: 96, saldo: 50, rateizzato: 40, amounts: [], acconto_pct: 100 } }, masses, 3)[0]).toMatch(/saldo \+ rateizzato/);
    expect(validatePregresso({ debiti_tributari: { opening: 96, saldo: 61, rateizzato: 35, amounts: [12, 12, 11], acconto_pct: 100 } }, masses, 3)).toEqual([]);
  });
});
```

- [ ] **Step 2: Eseguire, vedere fallire.**

- [ ] **Step 3: Implementare**

```ts
// frontend/lib/budget-pregresso.ts
import type { BalanceSheet, Pregresso, PregressoKey, PregressoPlan, PregressoTributari } from "@/types/api";

const num = (v: unknown): number => (typeof v === "number" ? v : parseFloat(String(v ?? "0")) || 0);
const cents = (v: number) => Math.round(v * 100) / 100;

export const PREGRESSO_LABELS: Record<PregressoKey, string> = {
  crediti_commerciali: "Crediti commerciali", debiti_fornitori: "Debiti verso fornitori",
  debiti_tributari: "Debiti tributari", debiti_previdenziali: "Debiti previdenziali", altri_debiti: "Altri debiti",
};

export function openingMasses(bs: BalanceSheet): Record<PregressoKey, number> {
  const b = bs as unknown as Record<string, unknown>;
  return {
    crediti_commerciali: cents(num(b.sp06_crediti_breve) - num(b.sp06e_crediti_tributari_breve) - num(b.sp06f_imposte_anticipate_breve)
      + num(b.sp07_crediti_lungo) - num(b.sp07e_crediti_tributari_lungo) - num(b.sp07f_imposte_anticipate_lungo)),
    debiti_fornitori: cents(num(b.sp16d_debiti_fornitori_breve) + num(b.sp17d_debiti_fornitori_lungo)),
    debiti_tributari: cents(num(b.sp16e_debiti_tributari_breve) + num(b.sp17e_debiti_tributari_lungo)),
    debiti_previdenziali: cents(num(b.sp16f_debiti_previdenza_breve) + num(b.sp17f_debiti_previdenza_lungo)),
    altri_debiti: cents(num(b.sp16g_altri_debiti_breve) + num(b.sp17g_altri_debiti_lungo)),
  };
}

export function residualAfter(plan: PregressoPlan, yearIndex: number): number {
  const sum = (xs: number[] | null | undefined) => (xs ?? []).slice(0, yearIndex + 1).reduce((a, b) => a + b, 0);
  return cents(Math.max(0, plan.opening - sum(plan.amounts) - sum(plan.writeoff)));
}
export function amountToPct(amount: number, opening: number): number | null { return opening ? (amount / opening) * 100 : null; }
export function pctToAmount(pct: number, opening: number): number { return cents(opening * pct / 100); }
export function equalInstalments(total: number, n: number): number[] {
  if (n <= 0) return [];
  const base = Math.floor((total / n) * 100) / 100;
  const out = Array(n).fill(base);
  out[n - 1] = cents(total - base * (n - 1));
  return out;
}
export function withAmount(plan: PregressoPlan, yearIndex: number, amount: number): PregressoPlan {
  const amounts = [...plan.amounts];
  while (amounts.length <= yearIndex) amounts.push(0);
  amounts[yearIndex] = cents(amount);
  return { ...plan, amounts };
}

export function validatePregresso(p: Pregresso, masses: Record<PregressoKey, number>, horizon: number): string[] {
  const errs: string[] = [];
  for (const key of Object.keys(PREGRESSO_LABELS) as PregressoKey[]) {
    const plan = p[key]; if (!plan) continue;
    const label = PREGRESSO_LABELS[key];
    if (Math.abs(plan.opening - masses[key]) > 0.01) errs.push(`${label}: il saldo di apertura dichiarato (${plan.opening}) non coincide col bilancio base (${masses[key]})`);
    if (plan.amounts.length > horizon || (plan.writeoff ?? []).length > horizon) errs.push(`${label}: il piano va oltre l'orizzonte di ${horizon} anni`);
    if ([...plan.amounts, ...(plan.writeoff ?? [])].some((v) => v < 0)) errs.push(`${label}: un importo è negativo`);
    const total = plan.amounts.reduce((a, b) => a + b, 0) + (plan.writeoff ?? []).reduce((a, b) => a + b, 0);
    if (key === "debiti_tributari") {
      const t = plan as PregressoTributari;
      if (Math.abs(t.saldo + t.rateizzato - t.opening) > 0.01) errs.push(`${label}: saldo + rateizzato deve essere uguale al saldo di apertura`);
      if (total - t.rateizzato > 0.01) errs.push(`${label}: le rate superano il rateizzato`);
    } else if (total - plan.opening > 0.01) errs.push(`${label}: gli importi superano il saldo di apertura`);
  }
  return errs;
}
```

- [ ] **Step 4: Verificare** — `npx vitest run lib/budget-pregresso && npx tsc --noEmit` → PASS.
- [ ] **Step 5: Commit** — `git add frontend/lib/budget-pregresso.ts frontend/lib/budget-pregresso.test.ts && git commit -m "feat(budget): modulo puro dello scadenziamento del pregresso"`

---

## Ondata B

### Task 5: Motore — i quattro saldi con piano, e la validazione

**Modello:** opus · **Ondata:** B (dopo 1, 3)

**Files:**
- Modify: `calculations/projection_common.py` (`pregresso_opening_masses`), `calculations/forecast_engine.py` (`compute_forecast`, `_calculate_balance_sheet`)
- Test: `tests/test_budget_pregresso.py` (sezione motore)

**Interfaces:**
- Produces:

```python
# projection_common.py
PREGRESSO_KEYS = ("crediti_commerciali", "debiti_fornitori", "debiti_tributari", "debiti_previdenziali", "altri_debiti")
PREGRESSO_LABELS = {...}   # italiano, per i messaggi
def pregresso_opening_masses(getter) -> Dict[str, Decimal]   # getter(field) -> Decimal, come base_bank_debt
# forecast_engine.py
def validate_pregresso(pregresso: Optional[dict], base_bs, horizon: int) -> dict   # normalizzato (Decimal), o {} se None; ValueError sui casi della spec §4
class ForecastEngine:
    def compute_forecast(..., )   # legge pregresso dalla PRIMA riga, alza se su un'altra, valida, lo passa ai calcolatori con year_index
    def _calculate_balance_sheet(..., pregresso=None, year_index=0, horizon=1, prev_details=None, details=None)
```

- [ ] **Step 1: Test**

```python
# tests/test_budget_pregresso.py (continua)
from backend.app.api.v1 import budget_scenarios
from backend.app.schemas.budget import BudgetScenarioCreate
from calculations.forecast_engine import ForecastEngine, load_forecast_source
from database import models
from tests.e2e_kit import memory_sessions, read_forecast_maps, seed_base_year

USER = "pregresso"
# base (e2e_kit): sp06 = sp06a = 120.000; sp16 = sp16d = 140.000; ricavi 600.000; ce20 50.000


def _run(db, company_id, rows, *, expect_ok=True):
    sc = budget_scenarios.create_budget_scenario(
        company_id, BudgetScenarioCreate(company_id=company_id, name="p", base_year=2026, scenario_type="budget"),
        user_id=USER, db=db)
    res = budget_scenarios.bulk_upsert_assumptions(
        company_id, sc.id, request={"assumptions": rows, "auto_generate": True}, user_id=USER, db=db)
    if expect_ok:
        assert res["forecast_generated"] is True, res["message"]
    return sc, res


MANUAL_TAX = {"sp16e_growth_pct": 0, "sp06e_growth_pct": 0}   # via manuale: le imposte non cambiano


def test_no_plan_is_a_fixed_point_for_the_four_balances(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            rows = [dict(forecast_year=y, revenue_growth_pct=5, **MANUAL_TAX) for y in (2027, 2028, 2029)]
            sc_a, _ = _run(db, company_id, rows)
            rows_b = [dict(r) for r in rows]
            rows_b[0]["pregresso"] = None
            sc_b, _ = _run(db, company_id, rows_b)
            for (_, bs_a, ce_a), (_, bs_b, ce_b) in zip(read_forecast_maps(db, sc_a.id), read_forecast_maps(db, sc_b.id)):
                assert bs_a == bs_b and ce_a == ce_b
    finally:
        engine.dispose()


def test_receivables_eighty_twenty_keeps_twenty_percent_short_and_lowers_cash(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            base = [dict(forecast_year=y, revenue_growth_pct=0, **MANUAL_TAX) for y in (2027, 2028)]
            sc0, _ = _run(db, company_id, base)
            planned = [dict(r) for r in base]
            planned[0]["pregresso"] = {"crediti_commerciali": {"opening": 120000, "amounts": [96000, 24000]}}
            sc1, _ = _run(db, company_id, planned)
            (y0a, bs0a, _), (y1a, bs1a, _) = read_forecast_maps(db, sc0.id)
            (y0b, bs0b, _), (y1b, bs1b, _) = read_forecast_maps(db, sc1.id)
            assert bs0b["sp06_crediti_breve"] == bs0a["sp06_crediti_breve"] + D("24000.00")
            assert bs0b["sp07_crediti_lungo"] == bs0a["sp07_crediti_lungo"]
            assert bs0b["sp09_disponibilita_liquide"] == bs0a["sp09_disponibilita_liquide"] - D("24000.00")
            assert bs1b["sp06_crediti_breve"] == bs1a["sp06_crediti_breve"]
    finally:
        engine.dispose()


def test_short_plan_pushes_the_rest_long_and_writeoff_hits_ce09d(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            rows = [dict(forecast_year=y, **MANUAL_TAX) for y in (2027, 2028)]
            rows[0]["pregresso"] = {"crediti_commerciali": {"opening": 120000, "amounts": [60000], "writeoff": [5000]}}
            sc, _ = _run(db, company_id, rows)
            (_, bs0, ce0), (_, bs1, ce1) = read_forecast_maps(db, sc.id)
            assert ce0["ce09d_svalutazione_crediti"] == D("5000.00") and ce1["ce09d_svalutazione_crediti"] == D("0.00")
            assert bs0["sp07_crediti_lungo"] == D("55000.00")          # residuo, niente dovuto l'anno dopo
            assert bs0["_total_assets"] == bs0["_total_liabilities"]
    finally:
        engine.dispose()


def test_validation_errors_are_honest(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            rows = [dict(forecast_year=y, **MANUAL_TAX) for y in (2027, 2028)]
            rows[1]["pregresso"] = {"altri_debiti": {"opening": 0, "amounts": []}}
            _, res = _run(db, company_id, rows, expect_ok=False)
            assert res["forecast_generated"] is False and "primo anno" in res["message"]
            rows = [dict(forecast_year=y, **MANUAL_TAX) for y in (2027, 2028)]
            rows[0]["pregresso"] = {"debiti_fornitori": {"opening": 100, "amounts": [100]}}
            _, res = _run(db, company_id, rows, expect_ok=False)
            assert "apertura" in res["message"] and "140000" in res["message"]
            rows[0]["pregresso"] = {"debiti_fornitori": {"opening": 140000, "amounts": [100000, 100000]}}
            _, res = _run(db, company_id, rows, expect_ok=False)
            assert "supera" in res["message"]
    finally:
        engine.dispose()
```

- [ ] **Step 2: Eseguire, vedere fallire.**

- [ ] **Step 3: `pregresso_opening_masses` e `validate_pregresso`**

```python
# projection_common.py
PREGRESSO_KEYS = ("crediti_commerciali", "debiti_fornitori", "debiti_tributari", "debiti_previdenziali", "altri_debiti")
PREGRESSO_LABELS = {"crediti_commerciali": "crediti commerciali", "debiti_fornitori": "debiti verso fornitori",
                    "debiti_tributari": "debiti tributari", "debiti_previdenziali": "debiti previdenziali", "altri_debiti": "altri debiti"}

def pregresso_opening_masses(getter):
    g = lambda f: getter(f) or ZERO
    return {
        "crediti_commerciali": (g('sp06_crediti_breve') - g('sp06e_crediti_tributari_breve') - g('sp06f_imposte_anticipate_breve')
                                + g('sp07_crediti_lungo') - g('sp07e_crediti_tributari_lungo') - g('sp07f_imposte_anticipate_lungo')),
        "debiti_fornitori": g('sp16d_debiti_fornitori_breve') + g('sp17d_debiti_fornitori_lungo'),
        "debiti_tributari": g('sp16e_debiti_tributari_breve') + g('sp17e_debiti_tributari_lungo'),
        "debiti_previdenziali": g('sp16f_debiti_previdenza_breve') + g('sp17f_debiti_previdenza_lungo'),
        "altri_debiti": g('sp16g_altri_debiti_breve') + g('sp17g_altri_debiti_lungo'),
    }
```

```python
# forecast_engine.py
def validate_pregresso(pregresso, base_bs, horizon):
    """Normalizza il piano (Decimal) e alza ValueError sui casi della spec §4."""
    if not pregresso:
        return {}
    masses = pregresso_opening_masses(lambda f: getattr(base_bs, f, None))
    out = {}
    for key in PREGRESSO_KEYS:
        plan = pregresso.get(key)
        if not plan:
            continue
        label = PREGRESSO_LABELS[key]
        opening = Decimal(str(plan.get('opening') or 0))
        if abs(opening - masses[key]) > CENT:
            raise ValueError(f"Il saldo di apertura di {label} è cambiato ({opening:.2f} → {masses[key]:.2f}): rivedi lo scadenziamento")
        amounts = [Decimal(str(a or 0)) for a in plan.get('amounts') or []]
        writeoff = [Decimal(str(w or 0)) for w in plan.get('writeoff') or []] if key == "crediti_commerciali" else []
        if key == "debiti_tributari":
            saldo, rate = Decimal(str(plan.get('saldo') or 0)), Decimal(str(plan.get('rateizzato') or 0))
            if abs(saldo + rate - opening) > CENT:
                raise ValueError(f"Debiti tributari: saldo + rateizzato ({saldo + rate:.2f}) deve essere uguale al saldo di apertura ({opening:.2f})")
            validate_runoff(rate, amounts, [], horizon, label)
            out[key] = {"opening": opening, "saldo": saldo, "rateizzato": rate, "amounts": amounts,
                        "acconto_pct": Decimal(str(plan.get('acconto_pct', 100) if plan.get('acconto_pct') is not None else 100))}
        else:
            validate_runoff(opening, amounts, writeoff, horizon, label)
            out[key] = {"opening": opening, "amounts": amounts, "writeoff": writeoff}
    return out
```

In `compute_forecast`, subito dopo `assemble_financing` e nello stesso `try`:

```python
            for a in assumptions[1:]:
                if getattr(a, 'pregresso', None):
                    raise ValueError("pregresso is allowed only in the first forecast year (lo scadenziamento vale solo sulla riga del primo anno)")
            pregresso = validate_pregresso(getattr(assumptions[0], 'pregresso', None), source.base_bs, len(assumptions))
```

e nel ciclo passare `pregresso=pregresso, year_index=idx, horizon=len(assumptions), prev_details=prev_details` ai due calcolatori (il ciclo tiene `prev_details = details` a fine anno; per il primo anno `None`).

- [ ] **Step 4: I quattro saldi in `_calculate_balance_sheet`**

Per ciascun saldo la regola è la stessa; qui i crediti, gli altri tre seguono con i campi della tabella della spec §3.1.

**Crediti** (dopo `sp06 = sp06_trade + sp06e + sp06f`, `:958`, e dopo il calcolo di `sp07`, `:971-980`):

```python
        runoff = {}
        plan = pregresso.get("crediti_commerciali") if pregresso else None
        if plan:
            r = runoff_schedule(plan["opening"], plan["amounts"], plan["writeoff"], year_index, horizon)
            runoff["crediti_commerciali"] = r
            sp06_trade = sp06_trade + r.residual_short          # generato + dovuto l'anno dopo
            sp06 = sp06_trade + sp06e + sp06f
            sp07_trade_long = r.residual_long                    # il lato lungo e' TUTTO pregresso
            sp07 = sp07_trade_long + sp07e_carry + sp07f_carry   # vedi nota
```

Nota su `sp07`: oggi `sp07` è `prev × (1+%)` intero. Con piano, il lato lungo commerciale è il residuo e le quote fiscali `sp07e`/`sp07f` restano quelle del percorso attuale (con differenze temporanee `deferred['long_asset']`, altrimenti carry): separare il calcolo di `sp07` in `sp07_trade_long` (commerciale) e `sp07_fiscal` (e+f) **prima** di questo blocco, così senza piano `sp07 = sp07_trade_long_legacy + sp07_fiscal` dà lo stesso numero di oggi. L'allocazione dei sotto-campi (`:1286-1298`) usa `sp07_non_deferred` come oggi.

**Fornitori** (dopo `:1065-1068`): `sp16d = sp16d + r.residual_short`, `sp17d = r.residual_long` (la `sp17d_growth_pct` viene ignorata: `details` lo segnala con `mode`).
**Previdenziali** (dopo `:1093-1107`): `sp16f += r.residual_short`, `sp17f = r.residual_long`.
**Altri debiti** (`:1090`, `:1092`): `sp16g += r.residual_short`, `sp17g = r.residual_long`.

Per ogni saldo, `generated` nei details = il valore del lato breve **prima** dell'aggiunta del residuo.

- [ ] **Step 5: `details.pregresso` sempre dichiarato**

Alla fine del calcolatore, prima del `return`:

```python
        if details is not None:
            masses = pregresso_opening_masses(_base)
            details['pregresso'] = {}
            for key in PREGRESSO_KEYS:
                r = runoff.get(key)
                details['pregresso'][key] = {
                    'opening': masses[key], 'closed': r.closed if r else ZERO, 'writeoff': r.writeoff if r else ZERO,
                    'residual_short': r.residual_short if r else ZERO, 'residual_long': r.residual_long if r else ZERO,
                    'generated': generated.get(key, ZERO), 'mode': 'runoff' if r else 'legacy',
                }
            details.setdefault('pregresso_ignored', [])
```

(`generated` è un dict riempito dove ogni saldo viene calcolato.) Le imposte popolano la loro parte nel Task 6; **in questo task** `details['imposte']` va comunque dichiarato con `mode: 'manual'` e zeri, così il contratto vale già.

- [ ] **Step 6: `ce09d` in `_calculate_income_statement`**

Firma `(..., pregresso=None, year_index=0, details=None)`; a `:743`:

```python
        writeoff = ZERO
        plan = pregresso.get("crediti_commerciali") if pregresso else None
        if plan and year_index < len(plan["writeoff"]):
            writeoff = plan["writeoff"][year_index]
        ce09d = assumption.ce09d_override if assumption.ce09d_override is not None else base_ce09d + writeoff
```

- [ ] **Step 7: Verificare** — `pytest tests/test_budget_pregresso.py tests/test_forecast_compute.py tests/test_forecast_preview.py tests/test_engine_accounting_invariants.py tests/test_budget_remediation_plan.py tests/test_numeric_stress_cycle.py -v` → PASS. Attenzione al test `test_no_plan_is_a_fixed_point`: se fallisce, la separazione di `sp07` (Step 4) ha cambiato un arrotondamento; sistemare lì.

- [ ] **Step 8: Commit** — `git add calculations/ tests/test_budget_pregresso.py && git commit -m "feat(engine): circolante pregresso = generato + residuo, per quattro saldi"`

---

### Task 6: Motore — imposte a saldo + acconto

**Modello:** opus · **Ondata:** B (dopo 2, 3, 5; stesso file del Task 5)

**Files:**
- Modify: `calculations/forecast_engine.py` — il blocco delle imposte dentro
  `_calculate_balance_sheet` e' a **`:1244-1258`** (`tax_advances`, la chiamata a
  `tax_closing_position`, `sp06e`/`sp16e`). L'aliquota e la scomposizione stanno in
  `_tax_components` (`:718-750`). *(Il piano diceva `:1069-1091`: numero di riga di `main`
  prima del lotto 1, che ha spostato 398 righe in questo file. Quel tratto e' `_sp_growth`
  e il preambolo del circolante — il posto sbagliato. Corretto in pre-volo, 2026-09-09.)*
- Test: `tests/test_budget_pregresso.py` (sezione imposte)

- [ ] **Step 1: Test**

```python
def _tax_rows(years, extra=None):
    return [dict(forecast_year=y, revenue_growth_pct=0, tax_rate=24, **(extra or {})) for y in years]


def test_constant_tax_pays_itself_and_leaves_no_debt(monkeypatch):
    """ce20 base 50.000 con aliquota esplicita 24 su un CE piatto: acconto 100% ->
    debito generato = imposte(N) - imposte(N-1)."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            sc, _ = _run(db, company_id, _tax_rows((2027, 2028, 2029)))
            rows = read_forecast_maps(db, sc.id)
            (_, bs0, ce0), (_, bs1, ce1), (_, bs2, ce2) = rows
            # dal secondo anno in poi l'imposta e' costante: nessun debito generato
            assert bs1["sp16e_debiti_tributari_breve"] == D("0.00") or bs1["sp16e_debiti_tributari_breve"] == bs2["sp16e_debiti_tributari_breve"]
            # la cassa scende ogni anno almeno dell'imposta pagata (saldo + acconti)
            assert bs1["sp09_disponibilita_liquide"] < bs0["sp09_disponibilita_liquide"] + ce1["ce20_imposte"]
    finally:
        engine.dispose()


def test_instalments_go_short_then_long(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            # base: sp16e = 0 nel kit -> aggiungerlo: 90.000 di debito tributario, 30.000 a breve + 60.000 a lungo
            fy = db.query(models.FinancialYear).filter_by(company_id=company_id).one()
            fy.balance_sheet.sp16e_debiti_tributari_breve = D("30000"); fy.balance_sheet.sp16_debiti_breve += D("30000")
            fy.balance_sheet.sp17e_debiti_tributari_lungo = D("60000"); fy.balance_sheet.sp17_debiti_lungo += D("60000")
            fy.balance_sheet.sp09_disponibilita_liquide += D("90000"); db.commit()
            rows = _tax_rows((2027, 2028, 2029))
            rows[0]["pregresso"] = {"debiti_tributari": {"opening": 90000, "saldo": 30000, "rateizzato": 60000,
                                                          "amounts": [20000, 20000, 20000], "acconto_pct": 100}}
            sc, _ = _run(db, company_id, rows)
            (_, bs0, _), (_, bs1, _), (_, bs2, _) = read_forecast_maps(db, sc.id)
            # fine anno 1: rata 2 a breve, rata 3 oltre (piu' il debito generato a breve)
            assert bs0["sp17e_debiti_tributari_lungo"] == D("20000.00")
            assert bs0["sp16e_debiti_tributari_breve"] >= D("20000.00")
            assert bs1["sp17e_debiti_tributari_lungo"] == D("0.00")
            assert bs2["sp17e_debiti_tributari_lungo"] == D("0.00")
    finally:
        engine.dispose()


def test_manual_tax_position_ignores_the_plan_and_says_so(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            rows = _tax_rows((2027, 2028), MANUAL_TAX)
            rows[0]["pregresso"] = {"debiti_tributari": {"opening": 0, "saldo": 0, "rateizzato": 0, "amounts": []}}
            sc, _ = _run(db, company_id, rows)
            source = load_forecast_source(db, sc.id)
            orm_rows = db.query(models.BudgetAssumptions).filter_by(scenario_id=sc.id).order_by(models.BudgetAssumptions.forecast_year).all()
            comp = ForecastEngine(db).compute_forecast(source, orm_rows)
            assert comp.years[0].details["imposte"]["mode"] == "manual"
            assert comp.years[0].details["pregresso_ignored"] == ["debiti_tributari"]
    finally:
        engine.dispose()
```

- [ ] **Step 2: Eseguire, vedere fallire.**

- [ ] **Step 3: Sostituire il blocco `:1071-1089`**

```python
        plan_tax = pregresso.get("debiti_tributari") if pregresso else None
        manual_tax_position = (
            getattr(assumption, 'sp06e_growth_pct', None) is not None
            or getattr(assumption, 'sp16e_growth_pct', None) is not None
        )
        tax_year = None
        if manual_tax_position:
            sp16e = _prev('sp16e_debiti_tributari_breve') * (D('1') + _sp_growth('sp16e_growth_pct'))
            sp17e = _prev('sp17e_debiti_tributari_lungo') * (D('1') + _sp_growth('sp17e_growth_pct'))
            if plan_tax and details is not None:
                details.setdefault('pregresso_ignored', []).append("debiti_tributari")
        else:
            prev_tax_details = (prev_details or {}).get('imposte') if prev_details else None
            if year_index == 0:
                saldo_due = plan_tax["saldo"] if plan_tax else pregresso_opening_masses(_base)["debiti_tributari"]
                previous_tax = _base_inc('ce20_imposte')          # l'unico dato di imposta del consuntivo
                opening_credit = _base('sp06e_crediti_tributari_breve')
            else:
                saldo_due = prev_tax_details['generated_debt']
                previous_tax = prev_tax_details['current_tax']
                opening_credit = prev_tax_details['generated_credit'] + prev_tax_details['opening_credit_left']
            rate_plan = plan_tax["amounts"] if plan_tax else []
            rateizzato = plan_tax["rateizzato"] if plan_tax else ZERO
            r = runoff_schedule(rateizzato, rate_plan, [], year_index, horizon)
            runoff["debiti_tributari"] = r
            acconto_pct = plan_tax["acconto_pct"] if plan_tax else D('100')
            explicit = getattr(assumption, 'tax_advances_paid', None)   # 0 = non dichiarato: vedi la nota qui sotto
            tax_year = tax_settlement_saldo_acconto(
                opening_credit=opening_credit, saldo_due=saldo_due, rate_due=r.closed,
                current_tax=current_tax, previous_tax=previous_tax, acconto_pct=acconto_pct, explicit_advances=explicit)
            sp16e = tax_year.generated_debt + r.residual_short
            sp17e = r.residual_long
            sp06e = tax_year.generated_credit + tax_year.opening_credit_left
            sp06 = sp06_trade + sp06e + sp06f
```

Rimuovere il calcolo di `sp17e` a `:1091` (ora dentro i due rami). `_base_inc` è un getter sull'`IncomeStatement` base come `_base` lo è sul BS: aggiungerlo accanto, `lambda f: getattr(base_inc, f, None) or ZERO`.

`details['imposte']` (sostituisce lo stub del Task 5):

```python
        if details is not None:
            details['imposte'] = ({'current_tax': current_tax, 'saldo_paid': tax_year.saldo_paid, 'acconti_paid': tax_year.acconti_paid,
                                   'rate_paid': tax_year.rate_paid, 'generated_debt': tax_year.generated_debt,
                                   'generated_credit': tax_year.generated_credit, 'opening_credit_left': tax_year.opening_credit_left,
                                   'mode': 'saldo_acconto'}
                                  if tax_year is not None else
                                  {'current_tax': current_tax, 'saldo_paid': ZERO, 'acconti_paid': ZERO, 'rate_paid': ZERO,
                                   'generated_debt': ZERO, 'generated_credit': ZERO, 'opening_credit_left': ZERO, 'mode': 'manual'})
```

**Nota del pre-volo (2026-09-09, Ruling 11) — `tax_advances_paid = 0` significa «non
dichiarato», non «zero acconti».** La colonna e' `Numeric(15,2), default=0, nullable=False`
(`database/models.py:645`) e lo schema Pydantic ha anch'esso `default=Decimal("0")`
(`backend/app/schemas/budget.py:149`): `None` non arriva mai al kernel, quindi lo zero e'
l'unico valore che puo' voler dire «l'utente non ha detto nulla». Per questo
`tax_settlement_saldo_acconto` ricade sulla percentuale quando l'importo esplicito e' zero, e
NON va cambiato in `is not None`: renderebbe `acconto_pct` lettera morta per ogni scenario che
non ha mai toccato quel campo. **Chi vuole dichiarare zero acconti mette `acconto_pct = 0`**, che
da' esattamente zero. Conseguenza vincolante per il Task 8: il passo delle imposte espone la
**percentuale di acconto**, non una casella d'importo «acconti versati» — una casella in cui
l'utente scrive 0 e ottiene altro sarebbe il difetto silenzioso peggiore che questo repo
conosca.

Il tributario senza piano usa `saldo_due = massa intera` (tutto saldo, niente rateizzato: spec §4) e `runoff_schedule(ZERO, [], ...)`.

- [ ] **Step 4: Verificare** — le suite del Task 5 più `tests/test_intra_year_semantics.py tests/test_intra_year_plug_negativo.py tests/test_intra_year_end_to_end_periods.py tests/test_infrannuale_dual_year.py` → PASS. **`test_taxes_follow_the_explicit_rate`** e gli altri test degli invarianti che leggono `sp16e` su scenari a posizione automatica **cambiano numeri per costruzione**: verificare che ciò che affermano sia ancora vero sotto la nuova regola e aggiornare solo l'aspettativa, mai la regola, spiegando nel commit.

- [ ] **Step 5: Commit** — `git commit -am "feat(engine): imposte a saldo + acconto; il debito tributario generato si paga l'anno dopo"`

---

## Ondata C

### Task 7: Passo 6 — la tabella del pregresso

**Modello:** sonnet · **Ondata:** C (dopo 4, 5)

**Files:**
- Create: `frontend/components/budget/wizard/PregressoTable.tsx`
- Modify: `frontend/components/budget/wizard/steps/StepPregressoNuovo.tsx`, `frontend/lib/budget-preview-rows.ts` (+ test)

**Interfaces:**
- Produces: `PregressoTable(props: { keys: PregressoKey[]; masses: Record<PregressoKey, number>; pregresso: Pregresso; forecastYears: number[]; mode: "eur" | "pct"; onChange: (next: Pregresso) => void; errors: string[] })`; in `budget-preview-rows.ts`: `rowsPregressoRunoff(years: ForecastPreviewYear[], keys: PregressoKey[]): PreviewRow[]` (per saldo: `residual_short`, `residual_long`, `closed`, `writeoff` con `mode`).

- [ ] **Step 1: Il piano vive nel primo anno**

Nel passo: `const firstYear = p.forecastYears[0]; const pregresso = (p.assumptions[firstYear]?.pregresso ?? {}) as Pregresso;` e `const setPregresso = (next: Pregresso) => p.update(firstYear, "pregresso", next as never)` (allargare il tipo di `update` a `number | boolean | null | object` in `StepProps` e nell'hook). `masses = openingMasses(baseBs)`.

- [ ] **Step 2: `PregressoTable`**

Tabella: `Voce | Saldo {baseYear} | anno… | Residuo`. Per riga: `PREGRESSO_LABELS[key]`, `formatCurrency(masses[key])`, una cella per anno con `Input type="number"` (in modalità `pct` mostra `amountToPct(amount, opening)` e scrive `pctToAmount`; in `eur` l'importo), `residualAfter(plan, last)` in coda. Riga vuota → placeholder «tutto nel primo anno». Un piano viene creato al primo tocco con `{ opening: masses[key], amounts: [] }` (l'`opening` dichiarato è quello del base, spec §3.5). Sotto la riga dei crediti, un `Accordion` «di cui inesigibile» con la stessa riga su `writeoff`. Interruttore `eur | pct` in testa (`seg` come l'orizzonte). `errors` (da `validatePregresso`) sotto la tabella in `text-destructive`. Tutte le scritture passano da `withAmount` e sono immutabili.

- [ ] **Step 3: Nel passo** — la tabella con `keys = ["crediti_commerciali", "debiti_fornitori", "debiti_previdenziali", "altri_debiti"]` sostituisce le due righe «lotto 2»; la riga dei tributari resta come rimando al passo 7 (mostra `masses.debiti_tributari`). Anteprima: alla `PreviewPanel` aggiungere `rowsPregressoRunoff(years, keys)` sotto le righe di debito/cassa, con un'intestazione «Pregresso: residuo a breve · oltre».

- [ ] **Step 4: Test delle righe** — in `budget-preview-rows.test.ts`: con `details.pregresso.crediti_commerciali = { residual_short: 200, residual_long: 0, closed: 800, writeoff: 0, mode: "runoff", ... }` la riga «Crediti commerciali · residuo a breve» vale 200 e la riga con `mode: "legacy"` ha `note: "nessun piano: tutto nel primo anno"`.

- [ ] **Step 5: Verificare** — `npx vitest run lib/ && npx tsc --noEmit`; a mano con i server (backend riavviato): piano 80/20 sui crediti → l'anteprima del passo 6 mostra il residuo e la cassa scende; somma oltre il saldo → errore rosso e il salvataggio riporta il messaggio del motore.

- [ ] **Step 6: Commit** — `git add frontend/ && git commit -m "feat(budget): passo 6, scadenziamento del pregresso per quattro saldi"`

---

### Task 8: Passo 7 — pagamento dei debiti tributari

**Modello:** sonnet · **Ondata:** C (dopo 4, 6)

**Files:**
- Modify: `frontend/components/budget/wizard/steps/StepImposte.tsx`, `frontend/lib/budget-preview-rows.ts` (+ test)

**Interfaces:**
- Produces: `rowsImposteSaldoAcconto(years: ForecastPreviewYear[]): PreviewRow[]` — righe `current_tax`, `saldo_paid`, `acconti_paid`, `rate_paid`, `generated_debt`, `generated_credit` dai `details.imposte`; in `mode: "manual"` una sola riga con nota «posizione tributaria manuale».

- [ ] **Step 1: La card si accende** — «Pagamento dei debiti tributari» senza badge: saldo di apertura `masses.debiti_tributari`; `Input` «Saldo dell'anno precedente» (scrive `saldo`, e `rateizzato = opening − saldo`), «Rateizzato» in sola lettura; piano delle rate per anno (`PregressoTable` con `keys=["debiti_tributari"]`, che per questa chiave usa `rateizzato` come massa) e il pulsante «N rate uguali» (`Select` 2..5 → `equalInstalments(rateizzato, n)`); «Acconto sull'imposta dell'anno prima» `Input number` su `acconto_pct` (default 100) con la chiosa «gli acconti per anno qui sopra, se valorizzati, lo scavalcano». Default senza piano: `{ opening, saldo: opening, rateizzato: 0, amounts: [], acconto_pct: 100 }`, creato al primo tocco. Le righe `sp16e_growth_pct`/`sp17e_growth_pct` restano sotto un `Accordion` «Posizione tributaria manuale» con l'avviso che, se valorizzate, il piano viene ignorato (`details.pregresso_ignored`).

- [ ] **Step 2: Anteprima** — `rowsImposte` (lotto 1) + `rowsImposteSaldoAcconto` sotto un'intestazione «Pagamenti dell'anno».

- [ ] **Step 3: Test, verifica, commit** — test delle righe nuove nel file esistente; `npx vitest run lib/ && npx tsc --noEmit`; a mano: 3 rate → `sp17e` nell'anteprima del passo 6 e nel SP Prev. dopo il salvataggio; `git commit -am "feat(budget): passo 7, saldo, rateizzato e acconti"`.

---

## Ondata D

### Task 9: Documentazione

**Modello:** haiku

- [ ] `CLAUDE.md` › Invarianti › Previsionale: le tre voci della spec §10 (imposte a saldo + acconto; `pregresso` solo sul primo anno con massa dichiarata; con piano il lato lungo è tutto pregresso). › Forecasting Engine: «il circolante è generato + residuo del pregresso».
- [ ] `docs/budget/API-PREVISIONALE.md`: il campo `pregresso` (forma della spec §4), le validazioni, `details.pregresso` / `details.imposte` / `pregresso_ignored`.
- [ ] `docs/budget/FORECASTING_GUIDE.md`: in testa una nota «superato dal 2026-09: vedi API-PREVISIONALE.md» (riscriverlo è fuori ambito).
- [ ] `docs/frontend/PRATICA-PERCORSO.md`: passi 6 e 7 completi. `docs/superpowers/2026-09-08-nota-costruttori-sp-infrannuale.md`: invariata, già cita il lotto.
- [ ] Commit `docs(budget): scadenziamento del pregresso e imposte a saldo + acconto`.

**Aggiunta in pre-volo (2026-09-09) — l'invariante di `CLAUDE.md` sulla cassa lo riscrive il
Task 12, non questo task.** Il testo esatto da scrivere e' nello **Step 7 del Task 12**, e ci va
nello **stesso commit** del codice che lo rende vero: `CLAUDE.md` descrive il codice com'e', non
com'e' previsto che diventi, e in questo repo una riga di documentazione su otto e' gia'
sbagliata. Qui, nel Task 9, resta solo la **verifica**: rileggere quel paragrafo dopo il Task 12
e controllare che dica quello che il codice fa davvero, misurandolo.


### Task 10: Collaudo

**Modello:** collaudatore

- [ ] Server accesi (backend riavviato). Perimetro: scenario esistente senza piano → SP Prev. identico a prima **tranne** `sp16e`/`sp06e`/cassa (imposte), da spiegare nel report; crediti 80/20; fornitori con residuo oltre l'orizzonte; tributari 3 rate → `sp17e`; inesigibile → `ce09d` in CE Prev.; errore di massa → messaggio onesto sia in anteprima sia al salvataggio; rendiconto: il flusso del pregresso compare nel circolante.
- [ ] Rilievi → fix con test → commit; merge del branch.

---

## Ondata E — quattro difetti assegnati in pre-volo (2026-09-09)

Questi quattro task **non c'erano** nel piano originale. Due li aveva assegnati il proprietario a
questo lotto (spec §11); due li ha trovati il banco di sensibilità (`scripts/sensibilita_ipotesi.py`)
alla fine del lotto 1. Il perché di ciascuno sta nella scansione di pre-volo, in
`.superpowers/sdd/2026-09-08-scadenziamento-pregresso/progress.md`.

A differenza dei task 1-10, questi sono **correzioni di difetto**: il piano dà il contratto e i
test, non la trascrizione. L'implementatore legge il codice e decide la forma, dentro il contratto.

**Ordine:** il **Task 11 va prima del Task 5** — il lotto scrive `ce09d` e la normalizzazione oggi
lo sovrascrive. Gli altri tre sono indipendenti da 1-10.

---

### Task 11: Un override di dettaglio sopravvive alla normalizzazione

**Modello:** sonnet · **Ondata:** A (prima del Task 5)

**Files:**
- Modify: `calculations/forecast_engine.py` — `_normalize_income_statement_cents` (`:171-210`),
  il suo unico chiamante (`:572`), e il punto di `_calculate_income_statement` che conosce gli
  override (`ce08` a `:845-853`, `ce09` subito sotto)
- Test: `tests/test_forecast_override_residuo.py` (nuovo)

**Il difetto, misurato.** `ce08d` è onorato a `:853`
(`assumption.ce08d_override if … is not None else max(0, ce08 − a − b − c)`) e **cancellato** a
`:190-193`:

```python
residual = result[aggregate] - sum((result[field] for field in details), Decimal("0"))
result[details[-1]] += residual      # details[-1] E' ce08d
```

Senza override il residuo è zero al centesimo e la riga è innocua: è per quello che il difetto
non si vede. Con `ce08d_override` il residuo vale `ce08 − (a+b+c+d_override)` e ci finisce
sopra: l'utente scrive un numero, ne vede un altro, nessun errore. Vale identico per
`ce09d_svalutazione_crediti`, che è `details[-1]` del gruppo `ce09` — **cioè esattamente il campo
in cui questo lotto scrive l'inesigibile** (spec §3.4). Senza questa correzione il Task 5 scrive
in un campo che il passaggio successivo riscrive.

**Contratto:**

1. Il residuo di gruppo si posa sull'**ultimo dettaglio senza override esplicito**.
2. Se **tutti** i dettagli del gruppo hanno un override e l'aggregato **non** ce l'ha,
   l'aggregato viene ricalcolato come loro somma.
3. Se anche l'aggregato ha un override e i due sono in conflitto, **vince l'aggregato** (è ciò
   che accade oggi), il residuo va sull'ultimo dettaglio, e il conflitto viene **dichiarato** —
   mai taciuto — in `details['override_conflicts']` come lista di
   `{"aggregate": <campo>, "declared": <Decimal>, "details_sum": <Decimal>}`.
   Regola di casa: *diagnose, never fabricate*.
4. **Parità:** senza alcun override di dettaglio, ogni numero prodotto oggi resta identico al
   centesimo. È l'unica cosa che i test esistenti devono continuare a dimostrare.

Il normalizzatore oggi riceve solo `values` e non sa nulla degli override: passargli l'insieme
dei nomi di campo forzati è parte del task (un parametro keyword con default vuoto, così il
chiamante infrannuale — se ce n'è uno — non cambia comportamento).

- [ ] **Step 1: Test che falliscono**

Quattro casi, tutti su `compute_forecast` con un `BudgetAssumptions` staccato (il banco di
sensibilità mostra come si costruisce: `scripts/sensibilita_ipotesi.py`, `_default_di_schema`):

```python
def test_ce08d_override_sopravvive():
    # ce08d_override = 7.000 con ce08 aggregato piu' alto: la riga persistita vale 7.000
def test_ce09d_override_sopravvive():
    # stesso su ce09d_svalutazione_crediti
def test_residuo_va_sul_dettaglio_non_forzato():
    # ce08d forzato, ce08c libero: il residuo si posa su ce08c, e a+b+c+d == ce08
def test_conflitto_dichiarato():
    # ce08 e tutti e quattro i dettagli forzati e incoerenti:
    # ce08 vince, e details['override_conflicts'] contiene la riga
```

- [ ] **Step 2: Verifica che falliscano** — `backend/venv/bin/python -m pytest tests/test_forecast_override_residuo.py -v`
- [ ] **Step 3: Implementa il contratto**
- [ ] **Step 4: Verde, più `tests/test_budget_*.py` e `tests/test_forecast*.py` interi (parità)**
- [ ] **Step 5: Commit**

---

### Task 12: La cassa non esce negativa — diventa scoperto di c/c, se concesso, e sempre dichiarata

**Modello:** opus · **Ondata:** E (dopo l'ondata C — tocca anche l'anteprima del wizard)

**Files:**
- Modify: `database/models.py` (`BudgetAssumptions`: due colonne nuove), `migrate_db.py`
  (voce `"budget_assumptions"`, `:92`), `backend/app/schemas/budget.py`
  (`BudgetAssumptionsBase` e `BudgetAssumptionsUpdate`)
- Modify: `calculations/forecast_engine.py` — il cancello del plug (`:1372-1375`), il blocco che
  con la cassa in eccesso rimborsa il debito bancario (`:1378-1387`), `sp16a` (`:1209`, `:1334`,
  `:1355`), `ce15` (`:948-963`), e i `details`
- Modify: `frontend/types/api.ts`, `frontend/lib/budget-preview-rows.ts`,
  il passo «nuovi finanziamenti» del wizard, `frontend/components/budget/wizard/` (avviso)
- Test: `tests/test_forecast_scoperto.py` (nuovo), `frontend/lib/budget-preview-rows.test.ts`

**Il difetto di partenza** e' la spec §11.1: leggerlo li', con il frammento che lo misura
(`sp_overrides={"sp05_rimanenze": 5000000}` → `sp09 = −4.779.777,78` sotto
`forecast_generated: True`). `_apply_sp_overrides` clampa a zero (`:466-468`), poi
`_normalize_balance_sheet_cents(recompute_cash=True)` ricalcola `sp09 = passivo − attivo senza
cassa` **senza clamp e senza sollevare** (`:584`), e scavalca il clamp.

**Ruling del proprietario (2026-09-09), che sostituisce quello del controllore.** «La cassa
negativa non esiste in senso stretto: diventa debito bancario a breve nuovo da piano» — **ma
solo se l'utente lo concede**, e **l'utente va sempre avvertito che il piano assorbe cassa**.

Questo contraddice la lettera di `CLAUDE.md` («non diventa debito a breve — creare `sp16a` li'
nascondeva una scelta di scenario mancante»). La ragione storica di quell'invariante era il
**silenzio**, non il debito: il debito compariva senza che nessuno lo avesse chiesto. Qui la
scelta di scenario e' esplicita (una concessione dell'utente) e il debito e' dichiarato nei
`details` e mostrato in anteprima, quindi la ragione decade. **L'invariante in `CLAUDE.md` va
riscritto in questo stesso lotto** (Task 9), non lasciato a contraddire il codice.

**Contratto:**

1. Due ipotesi nuove su `BudgetAssumptions`, per anno come tutte le altre:
   `overdraft_allowed` (`Boolean`, default `False`) e `overdraft_limit`
   (`Numeric(15,2)`, `nullable=True` = concesso senza tetto). Migrazione **additiva**: uno
   scenario esistente si ritrova `overdraft_allowed = False`, cioe' il comportamento di oggi.
2. Cassa negativa con `overdraft_allowed = False` ⇒ il motore **solleva** come oggi, stesso
   messaggio, stesso testo. Nessun test esistente cambia.
3. Cassa negativa con `overdraft_allowed = True` ⇒ `sp09 = 0` e l'importo scoperto diventa
   **`sp16a_debiti_banche_breve` generato dal piano**, distinto nei `details` dal debito
   bancario pregresso (e' esattamente il confine che questo lotto esiste per tracciare).
   Se `overdraft_limit` e' valorizzato e il fabbisogno lo supera, il motore **solleva** per la
   parte eccedente, con un messaggio che dice il tetto e l'importo richiesto.
4. Vale su **entrambi** i percorsi: il plug normale (`:1372-1375`) e il ricalcolo finale dopo
   un `sp_overrides` (`:584`). Da nessuno dei due puo' uscire una cassa negativa persistita.
5. **Interessi, senza circolarita'.** Lo scoperto matura oneri finanziari al
   `financing_interest_rate` gia' presente fra le ipotesi, **calcolati su un saldo noto prima
   che il CE si chiuda** — cioe' sullo scoperto in apertura d'anno, mai su quello che l'anno
   stesso sta generando: altrimenti l'interesse cambia la cassa che determina l'interesse.
   Confluiscono in `ce15` e sono dichiarati a parte in `details['oneri_scoperto']`.
   `financing_interest_rate` assente ⇒ zero, e lo si dichiara lo stesso.
6. **Rimborso.** Lo scoperto non e' eterno: il blocco che gia' esiste a `:1378-1387` — la cassa
   in eccesso abbatte il debito bancario, prima a breve poi a lungo — lo assorbe negli anni
   successivi. Verificare che lo faccia; se non lo fa, e' parte del task.
7. **L'avviso, che e' il punto.** `details` dichiara **sempre**, anche a zero (CLAUDE.md ›
   Invarianti — una chiave assente vale zero, quindi tacere equivale a dichiararsi puliti):
   - `cassa_assorbita`: di quanto il piano riduce la cassa nell'anno (apertura − chiusura,
     zero se la cassa cresce). Si dichiara **anche quando la cassa resta positiva**: e' la cosa
     di cui l'utente va avvertito.
   - `scoperto_generato`: lo scoperto nato nell'anno. `scoperto_residuo`: quello in essere a
     fine anno. `oneri_scoperto`: gli interessi del punto 5.
   L'anteprima del wizard mostra un avviso quando `cassa_assorbita > 0` — testo in italiano,
   icona `lucide-react`, nessuna emoji — e un avviso piu' forte quando `scoperto_generato > 0`,
   che dice l'importo. Con `overdraft_allowed = False` e un fabbisogno scoperto l'anteprima
   gia' oggi mostra l'errore del motore: quel percorso non cambia.
8. **Lo scoperto e' anche uno strumento di misura, non solo una valvola** (indicazione del
   proprietario, 2026-09-09): «l'utente vuole testare un piano stressato per vedere quanta
   finanza serve con quelle ipotesi». Accendere `overdraft_allowed` senza tetto e' quindi una
   **modalita' di misura** legittima, non un ripiego, e la risposta che l'utente cerca e'
   `scoperto_generato` anno per anno. L'anteprima non si limita all'avviso: mostra il
   **fabbisogno di picco** e **l'anno in cui cade**, che sono il numero e la data che si portano
   in banca. Il motore li dichiara in `details['fabbisogno_picco']` e
   `details['fabbisogno_picco_anno']` — sempre, anche a zero.

- [ ] **Step 1: Il test che misura il difetto di oggi** — il frammento della spec §11.1
  trasformato in test: con `overdraft_allowed` non concesso, `bulk_upsert_assumptions(...)` con
  quell'override deve dare `forecast_generated is False` e la ragione in `message` (CLAUDE.md:
  il bulk risponde 200 anche a un previsionale rifiutato — si legge `forecast_generated`, non lo
  status), e **nessun** `ForecastBalanceSheet` con `sp09 < 0` deve esistere a valle.
- [ ] **Step 2: Il test dello scoperto concesso** — stesso scenario con
  `overdraft_allowed = True`: la generazione riesce, `sp09 == 0`, `sp16a` cresce esattamente
  dell'importo che prima era negativo, `details['scoperto_generato']` lo dichiara.
  Poi il tetto: `overdraft_limit` sotto il fabbisogno ⇒ solleva, e il messaggio nomina i due
  importi.
- [ ] **Step 3: Il test del giro d'anno** — anno 1 genera scoperto, anno 2 genera cassa in
  eccesso: lo scoperto si riduce, e gli oneri dell'anno 2 sono calcolati sul saldo di apertura.
- [ ] **Step 4: Il test di parita'** — uno scenario senza scoperto e senza override produce
  **gli stessi numeri di oggi al centesimo**, e `details['cassa_assorbita']` e' dichiarato.
- [ ] **Step 5: Implementa** — colonne, migrazione, schema, motore, `details`, tipi, anteprima,
  avviso, controllo nel passo «nuovi finanziamenti» del wizard.
- [ ] **Step 6: Verde** — `tests/test_budget_*.py`, `tests/test_forecast*.py`,
  `tests/test_intra*.py` (il ramo `recompute_cash=False` dell'infrannuale **non cambia in
  nulla**: Global Constraints), `npx vitest run budget-preview-rows`, `npx tsc --noEmit`
- [ ] **Step 7: `CLAUDE.md` — la correzione va nello STESSO commit del codice che la rende vera**

Nella sezione «Forecasting Engine (Budget)», sostituire il periodo che oggi dice
«It does **not** become short-term debt — creating `sp16a` there used to hide a missing
scenario choice — so the way out is an explicit financing assumption, never a retry.»
con un testo che dica queste cose, in questo ordine:

- La cassa plugga sempre e solo **verso l'alto**: un plug negativo e' un fabbisogno scoperto.
- Che cosa succede allora dipende da **una scelta esplicita dell'utente**, `overdraft_allowed`,
  che di default e' **spenta** — quindi ogni scenario esistente si comporta come prima.
- Spenta: il motore **solleva**, `Unfunded financing requirement <importo>`, e non produce nulla.
- Accesa: il fabbisogno diventa `sp16a_debiti_banche_breve` **generato dal piano**, tenuto
  distinto nei `details` dal debito bancario pregresso, con oneri finanziari calcolati sul
  saldo di **apertura** (mai su quello che l'anno stesso genera: sarebbe circolare) e un tetto
  opzionale `overdraft_limit` oltre il quale il motore torna a sollevare.
- **Perche' esiste**: un piano stressato e' una cosa che si vuole poter far girare — serve a
  misurare **quanta finanza richiedono quelle ipotesi**, e la risposta e' `scoperto_generato`
  anno per anno, con il picco in `fabbisogno_picco`.
- **Perche' il divieto c'era**: la vecchia regola vietava `sp16a` perche' compariva **muto**,
  nascondendo una scelta di scenario mai fatta. Oggi la scelta e' esplicita e l'importo e'
  dichiarato in `details` e mostrato in anteprima. Scriverlo, cosi' che nessuno ripristini il
  divieto in buona fede fra sei mesi.
- Aggiungere infine, sempre in quella sezione o nella riga di «Invarianti e trappole ›
  Previsionale» che parla di `sp_overrides`: il ricalcolo finale della cassa
  (`_normalize_balance_sheet_cents(recompute_cash=True)`) **non scavalca piu'** il clamp degli
  override — era il difetto §11.1 della spec.

Non riscrivere la sezione intera e non toccare l'invariante dell'infrannuale, che **non cambia**:
li' il plug negativo resta clampato a zero con la diagnostica `unfunded_financing_requirement`.

- [ ] **Step 8: Commit**

---

### Task 13: Un previsionale più vecchio delle ipotesi si dichiara

**Modello:** sonnet · **Ondata:** E (indipendente da 1-10)

**Files:**
- Modify: `backend/app/services/` — il servizio che compone `GET /scenarios/{id}/analysis`
- Modify: `backend/app/schemas/` — il campo nuovo sullo schema di `/analysis`
- Modify: `frontend/types/api.ts`
- Create: `frontend/components/budget/ForecastStaleBanner.tsx`
- Modify: le cinque viste che leggono `/analysis` e mostrano il previsionale — `app/forecast/income`,
  `app/forecast/balance`, `app/forecast/reclassified`, `app/cashflow`, `app/report`
- Test: `tests/test_forecast_stale.py` (nuovo), `frontend/lib/budget-stale.test.ts` (nuovo)

**Il difetto** è la spec §11.2. Il bulk risponde 200 a un previsionale rifiutato: le ipotesi
restano salvate, il `ForecastYear` no, e le cinque viste mostrano i numeri **precedenti** senza
un segnale.

**Ruling del controllore (2026-09-09) sul meccanismo: confronto di timestamp, nessuna colonna
nuova.** `BudgetAssumptions` e `ForecastYear` hanno entrambi `created_at`/`updated_at`
(`database/models.py:718-719` e `:738-739`). Il previsionale è **stantio** quando
`max(updated_at delle assumptions dello scenario) > max(updated_at dei ForecastYear dello
scenario)`. Motivo: una bandiera persistita può divergere dalla realtà, un confronto no — ed è
vero per costruzione anche sul percorso `auto_generate=false`, dove il previsionale *è*
davvero più vecchio delle ipotesi. Costo se sbaglio: un falso positivo se due scritture cadono
nello stesso microsecondo — `datetime.utcnow()` ha i microsecondi, e la generazione scrive
**dopo** le ipotesi nella stessa transazione, quindi il confronto stretto `>` regge.

**Contratto:**

1. `/analysis` dichiara **sempre** `forecast_stale: bool`, anche `false` (CLAUDE.md ›
   Invarianti: una chiave assente vale zero, quindi tacere equivale a dichiararsi puliti), più
   `assumptions_updated_at` e `forecast_updated_at` in ISO, per poter spiegare l'avviso.
2. Nessun `ForecastYear` ⇒ `forecast_stale` è `false` (non c'è niente di stantio da mostrare:
   la vista è vuota, e il vuoto si vede).
3. La decisione sta in un modulo puro `frontend/lib/budget-stale.ts` con la sua suite in
   `environment: node` — **`jsdom` non è installato e non va installato**; il componente rende
   soltanto (CLAUDE.md › Frontend: `lib/budget-*` non importa mai da `app/` o `components/`).
4. Il banner dice, in italiano: che i numeri a schermo sono di una generazione **precedente**
   alle ipotesi salvate, e che per allinearli si rigenera. Nessuna emoji, icona `lucide-react`.

- [ ] **Step 1: Test backend che fallisce** — salvare ipotesi con generazione respinta, poi
  `GET /analysis`: `forecast_stale is True`. E il caso pulito: dopo una generazione riuscita,
  `False`.
- [ ] **Step 2: Test del modulo puro** — la funzione decide su due stringhe ISO più il conteggio
  degli anni; casi: stantio, allineato, nessun previsionale, timestamp mancante.
- [ ] **Step 3: Implementa backend, tipo, modulo, componente, e le cinque viste**
- [ ] **Step 4: Verde: pytest del file nuovo, `npx vitest run budget-stale`, `npx tsc --noEmit`**
- [ ] **Step 5: Commit**

---

### Task 14: Giorni medi automatici degeneri — la guardia che il motore budget non ha

**Modello:** opus · **Ondata:** E (indipendente da 1-10)

**Files:**
- Modify: `calculations/forecast_engine.py` — `_calculate_balance_sheet`, `base_revenue` (`:1083`)
  e i tre punti che dichiarano i giorni applicati (`:1118`, `:1131`, `:1230`)
- Test: `tests/test_forecast_giorni_degeneri.py` (nuovo)

**Il difetto.** `base_revenue = base_inc.ce01_ricavi_vendite or D('1')`. Quel `or D('1')` non è
una guardia: è un denominatore inventato. Su un'azienda il cui valore della produzione sta in
`ce04` — o su un anno base con `ce01` a zero — i giorni medi automatici escono a scala
astronomica, il circolante ci si adegua, e **nessun controllo se ne accorge**: il foglio quadra
lo stesso. Il motore infrannuale la guardia ce l'ha (`_turnover_ratio → None` con diagnostica
`degenerate_turnover_ratio`, `CLAUDE.md` › Intra-Year Engine); il motore budget no.

**Ruling del controllore (2026-09-09): si aggiunge la guardia, NON si cambia che cosa conta come
ricavo.** Allargare `base_revenue` a `ce01+ce04` cambierebbe i numeri di ogni azienda con `ce04`
diverso da zero, e i Global Constraints di questo lotto impongono la parità al centesimo su ciò
che il piano non tocca. La guardia invece non scatta mai su un'azienda sana, quindi la parità
regge. Costo se sbaglio: un'azienda con giorni medi reali sopra i 365 vede il proprio saldo base
riportato invece che scalato — e un avviso che glielo dice, invece di un numero assurdo muto.

**Contratto:**

1. Un giorno medio **derivato** (non esplicito) è **degenere** quando `> 365` o `< 0`, o quando
   `ce01` dell'anno base è `<= 0`. La soglia è la stessa che usa il banco di sensibilità nel
   rilievo G1 (`scripts/sensibilita_ipotesi.py:315-324`) e la stessa nozione dell'infrannuale
   («più di un anno di magazzino»).
2. Su un giorno degenere il motore **non scala**: riporta il saldo dell'anno base per quella
   voce (crediti, rimanenze o debiti commerciali), come fa l'infrannuale.
3. Lo dichiara: `details['degenerate_turnover_ratio']` è una **lista** dei nomi dei giorni
   caduti (`'dso'`, `'dio'`, `'dpo'`), **sempre presente**, vuota quando non scatta nulla.
   `dso_applied`/`dio_applied`/`dpo_applied` restano dichiarati e riportano il giorno **davvero
   applicato**, non quello degenere.
4. Un giorno **esplicito** dell'utente non passa dalla guardia: è una scelta, non una derivazione.
5. **Parità:** su ogni scenario dei test esistenti nessun giorno è degenere, quindi ogni numero
   resta identico al centesimo.

- [ ] **Step 1: Test che fallisce** — anno base con `ce01 = 0` e ricavi in `ce04`, crediti
  commerciali a 120.000: oggi `dso_applied` esce fuori scala; dopo, `dso` è degenere, `sp06a`
  proiettato vale il saldo base, e `details['degenerate_turnover_ratio'] == ['dso']`.
- [ ] **Step 2: Test di non-degenerazione** — l'`e2e_kit` normale: la lista è **vuota** e i tre
  giorni applicati sono quelli di oggi.
- [ ] **Step 3: Implementa**
- [ ] **Step 4: Verde su `tests/test_budget_*.py` e `tests/test_forecast*.py` interi**
- [ ] **Step 5: Commit**
