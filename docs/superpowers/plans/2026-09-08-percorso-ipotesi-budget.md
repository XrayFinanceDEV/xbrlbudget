# Percorso ipotesi budget (lotto 1) — piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sostituire la tab «Ipotesi» del budget con sette passi ordinati, ciascuno con un'anteprima delle righe che muove, calcolata dal motore Python via un endpoint che non scrive nulla.

**Architecture:** Il motore separa calcolo e persistenza (`compute_forecast` + `generate_forecast`) e dichiara sette `details` per anno; un servizio di anteprima costruisce righe transitorie di `BudgetAssumptions` con lo stesso mapping del bulk e chiama il calcolo senza toccare la sessione. Il frontend tiene la mappa idratata di oggi in un hook condiviso, e il wizard è una guida orizzontale + sette componenti di passo + un pannello di anteprima alimentato da un hook con debounce e annullamento. Tutto ciò che deriva un numero sta in Python; i moduli `lib/budget-*` fanno solo somme, percentuali e formattazione e sono testati in `environment: node`.

**Tech Stack:** FastAPI + SQLAlchemy + pytest (backend, `backend/venv`); Next.js 15 + TypeScript + shadcn/ui + Vitest (frontend). Nessuna dipendenza nuova: lo slider è un `<input type="range">` nativo.

**Spec:** `docs/superpowers/specs/2026-09-08-percorso-ipotesi-budget-design.md` (leggerla prima di ogni task; il prototipo `2026-09-08-percorso-ipotesi-budget-prototipo.html` accanto mostra il risultato atteso).

## Global Constraints

- Nessun campo nuovo in `BudgetAssumptions`, nessuna migrazione (spec §3).
- Nessun secondo motore in TypeScript: `lib/budget-preview-rows.ts` somma e formatta, non deriva (spec §7). Se serve un numero che il motore non dà, si aggiunge una chiave a `details`.
- `POST /preview` non scrive mai: nessun `db.add`, `commit`, potatura (spec §5.1).
- `PUT bulk`, `PATCH ce-override`, `POST generate` non cambiano comportamento (spec §5.2).
- Il payload del salvataggio viene sempre dalla mappa idratata intera, mai costruito da zero (spec §6, delete-all + reinsert lato server).
- `lib/budget-*` non importa mai da `app/` o `components/` (solo `import type`).
- Stato persistito letto in `useEffect`, mai nell'inizializzatore di `useState`; nessun oggetto letterale intero nelle dipendenze degli effetti (CLAUDE.md › Frontend).
- UI in italiano, numeri in formato europeo, icone lucide-react, niente emoji.
- Percentuali assolute (25,5 = 25,5%), soldi in `Decimal` lato Python.
- Il codice va su un branch dedicato (`feat/percorso-ipotesi-budget`), commit frequenti; `git diff --stat` prima di ogni commit (terminatori di riga).
- Comandi di test: backend `cd /home/peter/DEV/budget && backend/venv/bin/python -m pytest <file> -v`; frontend `cd /home/peter/DEV/budget/frontend && npx vitest run <pattern>`; typecheck `npx tsc --noEmit`.
- `uvicorn --reload` non ricarica `calculations/`: dopo ogni modifica al motore riavviare il server per il collaudo a mano.

## Ondate ed esecuzione parallela

I task senza frecce fra loro possono correre in parallelo su agenti diversi. Ogni task lavora su file propri; l'unico file conteso è `frontend/app/budget/page.tsx`, toccato solo dai task 7 (ondata A) e 15 (ondata C), mai insieme.

```
Ondata A (parallela):  1 · 2 · 3 · 4 · 5 · 6 · 7 · 8
Ondata B (parallela):  9 (dopo 1,2) · 10 (dopo 3,5) · 11,12,13,14 (dopo 3,4,6,8)
Ondata C:              15 (dopo tutti i precedenti)
Ondata D:              16 (haiku) · 17 (collaudatore) — dopo 15
```

| Task | Modello consigliato | Perché |
|---|---|---|
| 1, 3, 5, 16 | haiku | estrazione meccanica, tipi, modulo puro da 60 righe, testo |
| 4, 6, 7, 8, 9, 10, 11, 13, 14 | sonnet | codice nuovo su contratto chiaro |
| 2, 12, 15 | opus | refactor del motore con parità al centesimo; il passo più ricco; l'assemblaggio con salvataggio e navigazione |
| 17 | collaudatore (agente del repo) | browser reale contro i dev server |

**Prima di dispacciare qualunque agente: commit del lavoro in corso.** Il repo non ha isolamento per worktree e un checkout di un sottoagente ha già mangiato modifiche vive (memoria «commit before dispatching subagents»). Il branch corrente `fix/vseg-riserve-rimanenze` ha modifiche non committate all'importer: questo piano parte da `main` su un branch nuovo.

---

## File map

**Backend**
- Modify `calculations/forecast_engine.py` — `ForecastSource`, `ForecastYearResult`, `ForecastError`, `ForecastComputation`, `load_forecast_source()`, `ForecastEngine.assemble_financing()`, `ForecastEngine.compute_forecast()`, `generate_forecast()` ridotto a lettura → calcolo → persistenza; parametro `details` nei due calcolatori.
- Modify `backend/app/services/assumptions_service.py` — `build_assumption_row(scenario_id, data)` estratta dal loop del bulk.
- Create `backend/app/services/forecast_preview_service.py` — `preview_forecast(db, scenario_id, assumptions_list)`.
- Modify `backend/app/schemas/forecast.py` — `ForecastPreviewYear`, `ForecastPreviewError`, `ForecastPreviewResponse`.
- Modify `backend/app/api/v1/budget_scenarios.py` — route `POST /companies/{company_id}/scenarios/{scenario_id}/preview`.
- Create `tests/test_forecast_compute.py`, `tests/test_forecast_preview.py`, `tests/test_build_assumption_row.py`.

**Frontend, moduli puri (`environment: node`)**
- Modify `types/api.ts` — tipi della risposta di anteprima.
- Create `lib/budget-wizard-steps.ts` (+ test) — i sette passi, i gruppi, campo → passo, etichette del primario.
- Create `lib/budget-preview-rows.ts` (+ test) — dalla risposta alle righe di ogni passo.
- Create `lib/budget-preview-queue.ts` (+ test) — sequenza e debounce, senza React.
- Create `lib/budget-field-rules.ts` (+ test) — min/max/step/nullable per campo, estratti da `assumption-rows.ts`.
- Create `lib/budget-trend.ts` (+ test) — `calculateTrend`, `TREND_ITEMS`, `blendedRate`, `trendAssumptions`, spostati da `page.tsx`.

**Frontend, React**
- Create `hooks/use-scenario-assumptions.ts` — la mappa idratata e i suoi update, spostati da `ScenarioForm`.
- Create `hooks/use-forecast-preview.ts` — chiama `previewForecast` con debounce e `AbortController`.
- Modify `lib/api.ts` — `previewForecast()`.
- Create `components/budget/wizard/types.ts`, `YearInputTable.tsx`, `WizardRail.tsx`, `PreviewPanel.tsx`, `BudgetWizard.tsx`, `steps/StepScenario.tsx`, `steps/StepFatturato.tsx`, `steps/StepCosti.tsx`, `steps/StepAltreVociCE.tsx`, `steps/StepCircolante.tsx`, `steps/StepPregressoNuovo.tsx`, `steps/StepImposte.tsx`.
- Modify `app/budget/page.tsx` — `ScenarioForm` → `ScenarioFormStartup` (usa l'hook), `BudgetWizard` per gli scenari da bilancio; `FinancingLoansGrid` e `TaxTemporaryDifferencesGrid` esportati da un file proprio per essere riusati.

---

## Ondata A

### Task 1: `build_assumption_row` — un solo mapping per bulk e anteprima

**Modello:** haiku · **Ondata:** A

**Files:**
- Modify: `backend/app/services/assumptions_service.py:96-200` (il `models.BudgetAssumptions(...)` dentro il loop)
- Test: `tests/test_build_assumption_row.py`

**Interfaces:**
- Produces: `build_assumption_row(scenario_id: int, data: Dict[str, Any]) -> models.BudgetAssumptions` — istanza **transitoria**, non aggiunta a nessuna sessione; ogni colonna valorizzata con gli stessi default del bulk di oggi.

- [ ] **Step 1: Scrivere il test che fallisce**

```python
# tests/test_build_assumption_row.py
from decimal import Decimal

from backend.app.services.assumptions_service import build_assumption_row
from database import models


def test_row_is_transient_and_carries_every_column_default():
    row = build_assumption_row(7, {"forecast_year": 2027, "revenue_growth_pct": 5})
    assert isinstance(row, models.BudgetAssumptions)
    assert row.scenario_id == 7 and row.forecast_year == 2027
    assert row.revenue_growth_pct == 5
    # default del bulk, non dello schema: 27.9, 40, 20
    assert row.tax_rate == 27.9
    assert row.fixed_materials_percentage == 40.0
    assert row.depreciation_rate == 20.0
    assert row.financing_amount == 0.0            # null -> 0
    assert row.cash_sweep_enabled is False
    assert row.ce05_override is None
    # nessuna colonna e' rimasta None fra quelle NOT NULL del modello
    for col in models.BudgetAssumptions.__table__.columns:
        if not col.nullable and col.name not in ("id", "created_at", "updated_at"):
            assert getattr(row, col.name) is not None, col.name


def test_json_fields_are_encoded_like_the_bulk():
    row = build_assumption_row(7, {
        "forecast_year": 2027,
        "financing_loans": [{"amount": Decimal("1000"), "duration_years": 5}],
        "sp_overrides": {"sp09_disponibilita_liquide": Decimal("12.5")},
    })
    assert row.financing_loans == [{"amount": 1000.0, "duration_years": 5}]
    assert row.sp_overrides == {"sp09_disponibilita_liquide": 12.5}
```

- [ ] **Step 2: Eseguirlo e vederlo fallire**

Run: `cd /home/peter/DEV/budget && backend/venv/bin/python -m pytest tests/test_build_assumption_row.py -v`
Expected: FAIL, `ImportError: cannot import name 'build_assumption_row'`

- [ ] **Step 3: Estrarre la funzione**

In `assumptions_service.py`, sopra `bulk_upsert_assumptions`, aggiungere:

```python
def build_assumption_row(scenario_id: int, data: Dict[str, Any]) -> models.BudgetAssumptions:
    """Una riga di ipotesi dal dict del client, con i default del bulk.

    L'istanza e' TRANSITORIA: chi la vuole persistere la aggiunge alla sessione
    (bulk); l'anteprima la passa al motore e basta. Bulk e anteprima passano
    di qui, cosi' un campo aggiunto a uno non puo' mancare all'altro.
    """
    return models.BudgetAssumptions(
        scenario_id=scenario_id,
        forecast_year=data.get("forecast_year"),
        # ... QUI il corpo identico, riga per riga, del models.BudgetAssumptions(...)
        # che oggi sta nel loop (assumptions_service.py:96-200), con
        # `assumption_data` rinominato `data`. Nessun default cambia.
    )
```

Nel loop del bulk sostituire il blocco con:

```python
    for assumption_data in assumptions_list:
        db_assumption = build_assumption_row(scenario_id, assumption_data)
        db.add(db_assumption)
        assumptions_saved += 1
        forecast_years_list.append(assumption_data["forecast_year"])
```

- [ ] **Step 4: Verificare**

Run: `backend/venv/bin/python -m pytest tests/test_build_assumption_row.py tests/test_engine_accounting_invariants.py tests/test_budget_remediation_plan.py -v`
Expected: tutto PASS (il bulk non ha cambiato comportamento).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/assumptions_service.py tests/test_build_assumption_row.py
git commit -m "refactor(budget): build_assumption_row, un solo mapping per bulk e anteprima"
```

---

### Task 2: Motore — `compute_forecast` separato dalla persistenza, con `details`

**Modello:** opus · **Ondata:** A

**Files:**
- Modify: `calculations/forecast_engine.py:366-568` (`generate_forecast`), `:609-680` (`_calculate_income_statement`, firma e blocco ce05/ce06), `:864-880` (`_calculate_balance_sheet`, firma), `:943-957` (DSO), `:960-970` (DIO), `:1055-1065` (DPO)
- Test: `tests/test_forecast_compute.py`

**Interfaces:**
- Produces (module level in `calculations/forecast_engine.py`):

```python
@dataclass
class ForecastSource:
    scenario: BudgetScenario
    base_fy: FinancialYear
    base_bs: BalanceSheet
    base_inc: IncomeStatement

@dataclass
class ForecastYearResult:
    year: int
    income_statement: Dict[str, Decimal]
    balance_sheet: Dict[str, Decimal]
    details: Dict[str, Any]

@dataclass
class ForecastError:
    year: Optional[int]
    message: str

@dataclass
class ForecastComputation:
    years: List[ForecastYearResult]
    error: Optional[ForecastError] = None

def load_forecast_source(db, scenario_id: int) -> ForecastSource   # alza ValueError come oggi
class ForecastEngine:
    def assemble_financing(self, assumptions, base_bs) -> Tuple[List[dict], bool]  # alza ValueError
    def compute_forecast(self, source: ForecastSource, assumptions: List[BudgetAssumptions], *, stop_on_error: bool = True) -> ForecastComputation
    def generate_forecast(self, scenario_id: int) -> Dict   # invariato all'esterno
```

- `details` per anno, sempre presenti: `ce05_fixed`, `ce05_variable`, `ce06_fixed`, `ce06_variable` (`None` con override), `dso_applied`, `dio_applied`, `dpo_applied` (Decimal).

- [ ] **Step 1: Test di parità e di dettagli**

```python
# tests/test_forecast_compute.py
from decimal import Decimal

from backend.app.api.v1 import budget_scenarios
from backend.app.schemas.budget import BudgetScenarioCreate
from calculations.forecast_engine import ForecastEngine, load_forecast_source
from database import models
from tests.e2e_kit import memory_sessions, read_forecast_maps, seed_base_year

USER = "compute"


def _scenario(db, company_id, extra):
    sc = budget_scenarios.create_budget_scenario(
        company_id,
        BudgetScenarioCreate(company_id=company_id, name="c", base_year=2026, scenario_type="budget"),
        user_id=USER, db=db,
    )
    rows = [dict(forecast_year=y, **extra) for y in (2027, 2028, 2029)]
    res = budget_scenarios.bulk_upsert_assumptions(
        company_id, sc.id, request={"assumptions": rows, "auto_generate": True}, user_id=USER, db=db,
    )
    assert res["forecast_generated"] is True, res["message"]
    return sc


def test_compute_matches_persisted_forecast_to_the_cent(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            sc = _scenario(db, company_id, {"revenue_growth_pct": 5, "tangible_investments": 10000})
            persisted = read_forecast_maps(db, sc.id)
            source = load_forecast_source(db, sc.id)
            rows = (db.query(models.BudgetAssumptions)
                      .filter(models.BudgetAssumptions.scenario_id == sc.id)
                      .order_by(models.BudgetAssumptions.forecast_year).all())
            comp = ForecastEngine(db).compute_forecast(source, rows)
            assert comp.error is None
            assert [y.year for y in comp.years] == [y for y, _, _ in persisted]
            for computed, (_, bs, ce) in zip(comp.years, persisted):
                for k, v in computed.balance_sheet.items():
                    assert Decimal(str(v)).quantize(Decimal("0.01")) == bs[k], k
                for k, v in computed.income_statement.items():
                    assert Decimal(str(v)).quantize(Decimal("0.01")) == ce[k], k
    finally:
        engine.dispose()


def test_details_are_declared_and_sum_to_the_line(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            sc = _scenario(db, company_id, {"fixed_materials_percentage": 30,
                                            "variable_materials_growth_pct": 10,
                                            "fixed_materials_growth_pct": 2})
            source = load_forecast_source(db, sc.id)
            rows = (db.query(models.BudgetAssumptions)
                      .filter(models.BudgetAssumptions.scenario_id == sc.id)
                      .order_by(models.BudgetAssumptions.forecast_year).all())
            comp = ForecastEngine(db).compute_forecast(source, rows)
            for y in comp.years:
                d = y.details
                for key in ("ce05_fixed", "ce05_variable", "ce06_fixed", "ce06_variable",
                            "dso_applied", "dio_applied", "dpo_applied"):
                    assert key in d, key
                assert (d["ce05_fixed"] + d["ce05_variable"]).quantize(Decimal("0.01")) == \
                    y.income_statement["ce05_materie_prime"].quantize(Decimal("0.01"))
            # anno 1: 200.000 base -> 30% fisso +2%, 70% variabile +10%
            assert comp.years[0].details["ce05_fixed"] == Decimal("61200.00")
            assert comp.years[0].details["ce05_variable"] == Decimal("154000.00")
    finally:
        engine.dispose()


def test_override_blanks_the_split_and_stop_on_error_false_keeps_partial_years(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            sc = _scenario(db, company_id, {"ce05_override": 150000})
            source = load_forecast_source(db, sc.id)
            rows = (db.query(models.BudgetAssumptions)
                      .filter(models.BudgetAssumptions.scenario_id == sc.id)
                      .order_by(models.BudgetAssumptions.forecast_year).all())
            comp = ForecastEngine(db).compute_forecast(source, rows)
            assert comp.years[0].details["ce05_fixed"] is None
            assert comp.years[0].details["ce05_variable"] is None
            # investimenti fuori scala nel 2028: l'anno 2027 resta, 2028 e' l'errore
            rows[1].tangible_investments = Decimal("5000000")
            partial = ForecastEngine(db).compute_forecast(source, rows, stop_on_error=False)
            assert [y.year for y in partial.years] == [2027]
            assert partial.error.year == 2028
            assert "Unfunded financing requirement" in partial.error.message
    finally:
        engine.dispose()
```

- [ ] **Step 2: Eseguire, vedere fallire**

Run: `backend/venv/bin/python -m pytest tests/test_forecast_compute.py -v`
Expected: FAIL, `ImportError: cannot import name 'load_forecast_source'`

- [ ] **Step 3: Le dataclass e `load_forecast_source`**

In cima a `forecast_engine.py` (dopo gli import), aggiungere `from dataclasses import dataclass, field` e le quattro dataclass dell'interfaccia. Poi, a livello di modulo:

```python
def load_forecast_source(db, scenario_id: int) -> ForecastSource:
    """Scenario, anno base e i due prospetti, con gli stessi controlli di
    generate_forecast: scenario assente, base assente o incompleto, gate
    semantico dell'infrannuale, ricavi base negativi. Alza ValueError."""
    scenario = db.query(BudgetScenario).filter(BudgetScenario.id == scenario_id).first()
    if not scenario:
        raise ValueError(f"Budget scenario {scenario_id} not found")
    from database.queries import get_fy_prefer_full
    base_fy = get_fy_prefer_full(db, scenario.company_id, scenario.base_year)
    if not base_fy or not base_fy.balance_sheet or not base_fy.income_statement:
        raise ValueError(f"Base year {scenario.base_year} data not found or incomplete")
    from calculations.intra_year_engine import IntraYearEngine
    IntraYearEngine(db)._validate_forecast_source(base_fy, "Base source")
    base_inc = base_fy.income_statement
    if (base_inc.ce01_ricavi_vendite or Decimal('0')) < 0:
        raise ValueError(
            f"Anno base {scenario.base_year}: ricavi delle vendite negativi "
            f"({base_inc.ce01_ricavi_vendite:.0f} €) — estrazione del bilancio non valida. "
            f"Correggi i ricavi in Rettifiche (o re-importa il bilancio) prima di generare il previsionale."
        )
    return ForecastSource(scenario=scenario, base_fy=base_fy,
                          base_bs=base_fy.balance_sheet, base_inc=base_inc)
```

(È il blocco `:376-412` spostato tale e quale; cancellarlo da `generate_forecast`.)

- [ ] **Step 4: `assemble_financing` e `compute_forecast`**

Spostare il blocco `:435-476` (assemblaggio dei `financing_loans` e controllo dei residui) in un metodo:

```python
    def assemble_financing(self, assumptions, base_bs):
        """(financing_loans, use_detailed_existing_schedule) — alza ValueError
        su opening_residual fuori dal primo anno o residui != debito base."""
        financing_loans = []
        detailed_opening_total = Decimal('0')
        first_forecast_year = assumptions[0].forecast_year
        # ... corpo identico a :440-466 ...
        use_detailed_existing_schedule = detailed_opening_total > 0
        if use_detailed_existing_schedule:
            getter = lambda field: getattr(base_bs, field, None) or Decimal('0')
            base_bank_total = base_bank_debt(getter)
            if abs(base_bank_total - detailed_opening_total) > Decimal('0.01'):
                raise ValueError(
                    "The sum of financing opening residuals must equal base-year "
                    f"bank debt ({detailed_opening_total} != {base_bank_total})"
                )
        return financing_loans, use_detailed_existing_schedule
```

Poi il calcolo, senza alcuna scrittura:

```python
    def compute_forecast(self, source, assumptions, *, stop_on_error=True) -> ForecastComputation:
        """Il ciclo di generate_forecast senza persistenza. Con stop_on_error=False
        l'errore del motore ferma il ciclo e resta in `error`, gli anni gia'
        calcolati in `years`; con True (default) alza come oggi."""
        if not assumptions:
            raise ValueError(f"No assumptions found for scenario {source.scenario.id}")
        try:
            financing_loans, use_detailed = self.assemble_financing(assumptions, source.base_bs)
        except ValueError as e:
            if stop_on_error:
                raise
            return ForecastComputation(years=[], error=ForecastError(year=None, message=str(e)))

        results: List[ForecastYearResult] = []
        prev_inc = source.base_inc
        prev_bs = source.base_bs
        for assumption in assumptions:
            details: Dict[str, Any] = {}
            try:
                forecast_inc = self._calculate_income_statement(
                    base_inc=source.base_inc, assumption=assumption,
                    previous_inc=prev_inc, previous_bs=prev_bs,
                    financing_loans=financing_loans, details=details,
                )
                forecast_inc = self._normalize_income_statement_cents(forecast_inc)
                forecast_bs = self._calculate_balance_sheet(
                    base_bs=source.base_bs, base_inc=source.base_inc,
                    forecast_inc=forecast_inc, assumption=assumption, previous_bs=prev_bs,
                    year_offset=assumption.forecast_year - source.scenario.base_year,
                    financing_loans=financing_loans,
                    use_detailed_existing_schedule=use_detailed, details=details,
                )
                forecast_bs = self._normalize_balance_sheet_cents(forecast_bs)
            except ValueError as e:
                if stop_on_error:
                    raise
                return ForecastComputation(
                    years=results, error=ForecastError(year=assumption.forecast_year, message=str(e)))
            results.append(ForecastYearResult(
                year=assumption.forecast_year, income_statement=forecast_inc,
                balance_sheet=forecast_bs, details=details))
            prev_inc = _DictView(forecast_inc)
            prev_bs = _DictView(forecast_bs)
        return ForecastComputation(years=results)
```

**Attenzione al passaggio dell'anno precedente.** Oggi `previous_inc`/`previous_bs` sono gli **oggetti ORM** appena scritti (`forecast_years[-1]['income_statement']`) e i calcolatori li leggono con `getattr(obj, field)`. Nel calcolo puro non c'è l'ORM: `_DictView` è un adattatore minimo da aggiungere nel modulo:

```python
class _DictView:
    """getattr(view, 'sp09_...') su un dict del motore: previous_* senza ORM."""
    __slots__ = ("_d",)
    def __init__(self, d): self._d = d
    def __getattr__(self, name):
        try:
            return self._d[name]
        except KeyError:
            raise AttributeError(name)
```

Verificare che i calcolatori leggano solo chiavi presenti nei dict (le colonne `sp*`/`ce*` e le proprietà calcolate come `total_assets`, se usate: cercarle con `grep -n "previous_bs\.\|_prev(" calculations/forecast_engine.py`; se una proprietà del modello ORM viene letta, aggiungerla al dict prodotto dal calcolatore, non all'adattatore).

- [ ] **Step 5: `generate_forecast` ridotto**

```python
    def generate_forecast(self, scenario_id: int) -> Dict:
        source = load_forecast_source(self.db, scenario_id)
        assumptions = self.db.query(BudgetAssumptions).filter(
            BudgetAssumptions.scenario_id == scenario_id
        ).order_by(BudgetAssumptions.forecast_year).all()
        if not assumptions:
            raise ValueError(f"No assumptions found for scenario {scenario_id}")
        prune_out_of_plan_forecast_years(self.db, scenario_id, [a.forecast_year for a in assumptions])

        computation = self.compute_forecast(source, assumptions, stop_on_error=True)

        forecast_years = []
        for result in computation.years:
            fy = self.db.query(ForecastYear).filter(
                ForecastYear.scenario_id == scenario_id, ForecastYear.year == result.year).first()
            if not fy:
                fy = ForecastYear(scenario_id=scenario_id, year=result.year)
                self.db.add(fy); self.db.flush()
            # ... il blocco di upsert di :519-546 tale e quale, con result.balance_sheet
            #     al posto di forecast_bs e result.income_statement al posto di forecast_inc ...
            forecast_years.append({'year': result.year, 'forecast_year_obj': fy,
                                   'balance_sheet': existing_bs, 'income_statement': existing_inc})
        self.db.commit()
        return {
            'success': True, 'scenario_id': scenario_id, 'scenario_name': source.scenario.name,
            'base_year': source.scenario.base_year,
            'forecast_years': [fy['year'] for fy in forecast_years],
            'years_generated': len(forecast_years),
        }
```

- [ ] **Step 6: I `details` nei calcolatori**

`_calculate_income_statement(..., financing_loans=None, details=None)`: nel blocco materie (`:645-653`) e servizi (`:659-667`) registrare i due addendi dopo la crescita:

```python
        if assumption.ce05_override is not None:
            ce05 = assumption.ce05_override
            ce05_fixed_part = ce05_variable_part = None
        else:
            ...
            ce05_fixed_part = fixed_materials * (Decimal('1') + assumption.fixed_materials_growth_pct / Decimal('100'))
            ce05_variable_part = variable_materials * (Decimal('1') + assumption.variable_materials_growth_pct / Decimal('100'))
            ce05 = ce05_variable_part + ce05_fixed_part
        # idem per ce06 -> ce06_fixed_part / ce06_variable_part
        if details is not None:
            details['ce05_fixed'] = ce05_fixed_part
            details['ce05_variable'] = ce05_variable_part
            details['ce06_fixed'] = ce06_fixed_part
            details['ce06_variable'] = ce06_variable_part
```

`_calculate_balance_sheet(..., use_detailed_existing_schedule=False, details=None)`: subito dopo il calcolo di `dso` (`:957`), `dio` e `dpo` (`:1064`):

```python
        if details is not None:
            details['dso_applied'] = dso
        # ... details['dio_applied'] = dio ... details['dpo_applied'] = dpo
```

Le quattro chiavi di ce05/ce06 vanno **quantizzate al centesimo** insieme al resto: aggiungere in `compute_forecast`, dopo `_normalize_income_statement_cents`, `for k in ('ce05_fixed','ce05_variable','ce06_fixed','ce06_variable'): if details.get(k) is not None: details[k] = details[k].quantize(Decimal('0.01'))`.

- [ ] **Step 7: Verificare parità e suite esistenti**

Run: `backend/venv/bin/python -m pytest tests/test_forecast_compute.py tests/test_engine_accounting_invariants.py tests/test_budget_remediation_plan.py tests/test_numeric_stress_cycle.py tests/test_forecast_semantics.py tests/test_http_full_cycle.py -v`
Expected: tutto PASS. Se `test_compute_matches_persisted_forecast_to_the_cent` fallisce su una chiave, il calcolatore leggeva una proprietà ORM dal `previous_*` (Step 4): sistemare lì, non nel test.

- [ ] **Step 8: Commit**

```bash
git add calculations/forecast_engine.py tests/test_forecast_compute.py
git commit -m "refactor(engine): compute_forecast separato dalla persistenza, con details dichiarati"
```

---

### Task 3: Tipi dell'anteprima e `lib/budget-wizard-steps.ts`

**Modello:** haiku · **Ondata:** A

**Files:**
- Modify: `frontend/types/api.ts` (in fondo)
- Create: `frontend/lib/budget-wizard-steps.ts`, `frontend/lib/budget-wizard-steps.test.ts`

**Interfaces:**
- Produces (types):

```ts
export interface ForecastYearDetails {
  ce05_fixed: number | null; ce05_variable: number | null;
  ce06_fixed: number | null; ce06_variable: number | null;
  dso_applied: number; dio_applied: number; dpo_applied: number;
}
export interface ForecastPreviewYear {
  year: number;
  income_statement: Record<string, number>;
  balance_sheet: Record<string, number>;
  details: ForecastYearDetails;
}
export interface ForecastPreviewError { year: number | null; message: string }
export interface ForecastPreviewResponse {
  scenario_id: number; base_year: number;
  forecast_years: ForecastPreviewYear[];
  error: ForecastPreviewError | null;
}
```

- Produces (lib):

```ts
export type WizardStepKey = "scenario" | "fatturato" | "costi" | "altre-voci-ce" | "circolante" | "pregresso-nuovo" | "imposte";
export interface WizardStep { n: number; key: WizardStepKey; title: string; subtitle: string; group: "Impostazione" | "Conto economico" | "Stato patrimoniale" }
export const WIZARD_STEPS: readonly WizardStep[];
export const STEP_FIELDS: Record<WizardStepKey, readonly string[]>;
export const DEAD_FIELDS: readonly string[];
export function primaryLabel(step: WizardStepKey): string;          // "Avanti" | "Salva e calcola previsionale"
export function stepForErrorMessage(message: string): WizardStepKey; // "Unfunded" -> "pregresso-nuovo", altrimenti "imposte"
export function stepStorageKey(scenarioId: number): string;         // `budget-wizard-step:${id}`
export function nextStep(step: WizardStepKey): WizardStepKey | null;
export function prevStep(step: WizardStepKey): WizardStepKey | null;
```

- [ ] **Step 1: Test**

```ts
// frontend/lib/budget-wizard-steps.test.ts
import { describe, expect, it } from "vitest";
import {
  DEAD_FIELDS, STEP_FIELDS, WIZARD_STEPS, nextStep, prevStep,
  primaryLabel, stepForErrorMessage, stepStorageKey,
} from "./budget-wizard-steps";

describe("budget-wizard-steps", () => {
  it("ha sette passi numerati in ordine, in tre gruppi", () => {
    expect(WIZARD_STEPS.map((s) => s.n)).toEqual([1, 2, 3, 4, 5, 6, 7]);
    expect(WIZARD_STEPS.map((s) => s.group)).toEqual([
      "Impostazione", "Conto economico", "Conto economico", "Conto economico",
      "Stato patrimoniale", "Stato patrimoniale", "Stato patrimoniale",
    ]);
  });
  it("ogni campo esposto appartiene a un solo passo e i campi morti a nessuno", () => {
    const seen = new Map<string, string>();
    for (const [step, fields] of Object.entries(STEP_FIELDS)) {
      for (const f of fields) {
        expect(seen.has(f), `${f} in ${seen.get(f)} e ${step}`).toBe(false);
        seen.set(f, step);
      }
    }
    for (const dead of DEAD_FIELDS) expect(seen.has(dead)).toBe(false);
    expect(seen.get("revenue_growth_pct")).toBe("fatturato");
    expect(seen.get("fixed_materials_percentage")).toBe("costi");
    expect(seen.get("sp16e_growth_pct")).toBe("imposte");
    expect(seen.get("existing_debt_repayment_years")).toBe("pregresso-nuovo");
  });
  it("etichetta del primario e navigazione", () => {
    expect(primaryLabel("costi")).toBe("Avanti");
    expect(primaryLabel("imposte")).toBe("Salva e calcola previsionale");
    expect(nextStep("scenario")).toBe("fatturato");
    expect(nextStep("imposte")).toBeNull();
    expect(prevStep("scenario")).toBeNull();
    expect(stepForErrorMessage("Unfunded financing requirement 84,120.00: add ...")).toBe("pregresso-nuovo");
    expect(stepForErrorMessage("altro")).toBe("imposte");
    expect(stepStorageKey(12)).toBe("budget-wizard-step:12");
  });
});
```

- [ ] **Step 2: Eseguire, vedere fallire**

Run: `cd /home/peter/DEV/budget/frontend && npx vitest run lib/budget-wizard-steps`
Expected: FAIL, modulo non trovato.

- [ ] **Step 3: Implementare**

Aggiungere i quattro tipi a `types/api.ts`. Poi:

```ts
// frontend/lib/budget-wizard-steps.ts
/** I sette passi del percorso ipotesi (spec 2026-09-08 §4). Modulo puro. */
export type WizardStepKey =
  | "scenario" | "fatturato" | "costi" | "altre-voci-ce"
  | "circolante" | "pregresso-nuovo" | "imposte";

export interface WizardStep {
  n: number; key: WizardStepKey; title: string; subtitle: string;
  group: "Impostazione" | "Conto economico" | "Stato patrimoniale";
}

export const WIZARD_STEPS: readonly WizardStep[] = [
  { n: 1, key: "scenario", title: "Scenario", subtitle: "nome, anno base, orizzonte", group: "Impostazione" },
  { n: 2, key: "fatturato", title: "Fatturato", subtitle: "ricavi e altri ricavi", group: "Conto economico" },
  { n: 3, key: "costi", title: "Costi principali", subtitle: "quota fissa e variabile", group: "Conto economico" },
  { n: 4, key: "altre-voci-ce", title: "Altre voci CE", subtitle: "voci minori e automatiche", group: "Conto economico" },
  { n: 5, key: "circolante", title: "Capitale circolante", subtitle: "giorni medi", group: "Stato patrimoniale" },
  { n: 6, key: "pregresso-nuovo", title: "Pregresso e nuovo", subtitle: "debiti, finanziamenti, investimenti", group: "Stato patrimoniale" },
  { n: 7, key: "imposte", title: "Imposte", subtitle: "aliquota e pagamento", group: "Stato patrimoniale" },
];

export const STEP_FIELDS: Record<WizardStepKey, readonly string[]> = {
  scenario: [],
  fatturato: ["revenue_growth_pct", "other_revenue_growth_pct"],
  costi: [
    "fixed_materials_percentage", "fixed_services_percentage",
    "variable_materials_growth_pct", "variable_services_growth_pct",
    "fixed_materials_growth_pct", "fixed_services_growth_pct",
    "personnel_growth_pct", "rent_growth_pct",
  ],
  "altre-voci-ce": ["other_costs_growth_pct"],
  circolante: [
    "dso_days", "dio_days", "dpo_days", "receivables_long_growth_pct",
    "sp01_growth_pct", "sp04_growth_pct", "sp06e_growth_pct", "sp06f_growth_pct",
    "sp08_growth_pct", "sp10_growth_pct", "sp14_growth_pct", "sp16f_growth_pct",
    "sp16g_growth_pct", "sp17d_growth_pct", "sp17f_growth_pct", "sp17g_growth_pct",
    "sp18_growth_pct", "previdenza_scales_with_personnel", "tfr_accrual_suspended",
  ],
  "pregresso-nuovo": [
    "existing_debt_repayment_years", "altri_finanz_repayment_years", "financing_loans",
    "financing_amount", "financing_duration_years", "financing_interest_rate",
    "tangible_investments", "intangible_investments",
    "depreciation_rate", "depreciation_rate_intangible",
    "asset_disposal_nbv", "asset_disposal_proceeds", "cash_sweep_enabled", "cash_sweep_min_cash",
  ],
  imposte: ["tax_rate", "tax_advances_paid", "tax_temporary_differences", "sp16e_growth_pct", "sp17e_growth_pct"],
};

/** Colonne che il motore non legge: idratate e rispedite, mai mostrate. */
export const DEAD_FIELDS = [
  "investments", "receivables_short_growth_pct", "payables_short_growth_pct",
  "interest_rate_receivables", "interest_rate_payables",
] as const;

export function primaryLabel(step: WizardStepKey): string {
  return step === "imposte" ? "Salva e calcola previsionale" : "Avanti";
}
export function stepForErrorMessage(message: string): WizardStepKey {
  return /unfunded financing requirement/i.test(message) ? "pregresso-nuovo" : "imposte";
}
export function stepStorageKey(scenarioId: number): string {
  return `budget-wizard-step:${scenarioId}`;
}
const ORDER = WIZARD_STEPS.map((s) => s.key);
export function nextStep(step: WizardStepKey): WizardStepKey | null {
  const i = ORDER.indexOf(step);
  return i >= 0 && i < ORDER.length - 1 ? ORDER[i + 1] : null;
}
export function prevStep(step: WizardStepKey): WizardStepKey | null {
  const i = ORDER.indexOf(step);
  return i > 0 ? ORDER[i - 1] : null;
}
```

- [ ] **Step 4: Verificare**

Run: `npx vitest run lib/budget-wizard-steps && npx tsc --noEmit`
Expected: PASS, nessun errore di tipo.

- [ ] **Step 5: Commit**

```bash
git add frontend/types/api.ts frontend/lib/budget-wizard-steps.ts frontend/lib/budget-wizard-steps.test.ts
git commit -m "feat(budget): tipi dell'anteprima e modulo puro dei sette passi"
```

---

### Task 4: `lib/budget-preview-rows.ts` — dalla risposta alle righe di ogni passo

**Modello:** sonnet · **Ondata:** A (usa i tipi del Task 3: se non è ancora in main, dichiararli localmente identici e riconciliare al merge)

**Files:**
- Create: `frontend/lib/budget-preview-rows.ts`, `frontend/lib/budget-preview-rows.test.ts`

**Interfaces:**
- Consumes: `ForecastPreviewYear`, `ForecastPreviewError` (Task 3), `IncomeStatement`, `BalanceSheet` da `@/types/api`.
- Produces:

```ts
export interface PreviewCell { value: number | null; pct?: number | null; days?: number | null; note?: string }
export type PreviewRowKind = "value" | "sub" | "total" | "kpi";
export interface PreviewRow { key: string; label: string; kind: PreviewRowKind; base: PreviewCell; years: PreviewCell[] }
export function rowsFatturato(baseInc: IncomeStatement, years: ForecastPreviewYear[]): PreviewRow[]
export function rowsCosti(baseInc: IncomeStatement, fixedShare: { materials: number; services: number }, years: ForecastPreviewYear[]): PreviewRow[]
export function rowsAltreVociCe(baseInc: IncomeStatement, years: ForecastPreviewYear[]): PreviewRow[]
export function rowsCircolante(baseBs: BalanceSheet, baseInc: IncomeStatement, years: ForecastPreviewYear[]): PreviewRow[]
export function rowsPregressoNuovo(baseBs: BalanceSheet, years: ForecastPreviewYear[]): PreviewRow[]
export function rowsImposte(baseInc: IncomeStatement, years: ForecastPreviewYear[]): PreviewRow[]
export function unfundedFromError(error: ForecastPreviewError | null): { year: number; amount: number } | null
```

Regola del modulo: **somme di chiavi già presenti, percentuali e differenze**. Niente DSO, niente rotazioni, niente imposte ricalcolate. `pct` è sempre «in % dei ricavi delle vendite dell'anno» salvo dove indicato.

- [ ] **Step 1: Test**

```ts
// frontend/lib/budget-preview-rows.test.ts
import { describe, expect, it } from "vitest";
import type { BalanceSheet, ForecastPreviewYear, IncomeStatement } from "@/types/api";
import {
  rowsCosti, rowsFatturato, rowsImposte, rowsPregressoNuovo, unfundedFromError,
} from "./budget-preview-rows";

const baseInc = {
  ce01_ricavi_vendite: "1000", ce04_altri_ricavi: "50", ce05_materie_prime: "400",
  ce06_servizi: "200", ce07_godimento_beni: "30", ce08_costi_personale: "150",
  ce12_oneri_diversi: "20", ce09_ammortamenti: "40", ce15_oneri_finanziari: "10", ce20_imposte: "30",
} as unknown as IncomeStatement;

const year = (y: number, over: Partial<Record<string, number>> = {}): ForecastPreviewYear => ({
  year: y,
  income_statement: {
    ce01_ricavi_vendite: 1100, ce04_altri_ricavi: 50, ce05_materie_prime: 430, ce06_servizi: 210,
    ce07_godimento_beni: 30, ce08_costi_personale: 155, ce12_oneri_diversi: 20, ce09_ammortamenti: 40,
    ce15_oneri_finanziari: 10, ce20_imposte: 33, ...over,
  },
  balance_sheet: { sp16d_debiti_fornitori_breve: 140, sp09_disponibilita_liquide: 80,
    sp16a_debiti_banche_breve: 20, sp17a_debiti_banche_lungo: 100, sp17b_debiti_altri_finanz_lungo: 0,
    sp16b_debiti_altri_finanz_breve: 0, sp16c_debiti_obbligazioni_breve: 0, sp17c_debiti_obbligazioni_lungo: 0,
    sp16e_debiti_tributari_breve: 33 },
  details: { ce05_fixed: 130, ce05_variable: 300, ce06_fixed: 120, ce06_variable: 90,
    dso_applied: 60, dio_applied: 45, dpo_applied: 78 },
});

describe("rowsFatturato", () => {
  it("ricavi con variazione % sull'anno precedente e cumulata sul base", () => {
    const rows = rowsFatturato(baseInc, [year(2027), year(2028, { ce01_ricavi_vendite: 1210 })]);
    const ricavi = rows.find((r) => r.key === "ce01")!;
    expect(ricavi.base.value).toBe(1000);
    expect(ricavi.years[0]).toMatchObject({ value: 1100, pct: 10 });
    expect(ricavi.years[1]).toMatchObject({ value: 1210, pct: 10 });
    expect(rows.find((r) => r.key === "cumulata")!.years[1].pct).toBeCloseTo(21, 5);
  });
});

describe("rowsCosti", () => {
  it("totale = somma delle quattro voci, fissi + variabili = materie + servizi, % sui ricavi", () => {
    const rows = rowsCosti(baseInc, { materials: 32.5, services: 60 }, [year(2027)]);
    const tot = rows.find((r) => r.key === "principali")!;
    expect(tot.years[0].value).toBe(430 + 210 + 30 + 155);
    expect(tot.years[0].pct).toBeCloseTo((825 / 1100) * 100, 6);
    expect(rows.find((r) => r.key === "fissi")!.years[0].value).toBe(130 + 120 + 155 + 30);
    expect(rows.find((r) => r.key === "variabili")!.years[0].value).toBe(300 + 90);
    // base: quote dallo slider
    expect(rows.find((r) => r.key === "fissi")!.base.value).toBe(400 * 0.325 + 200 * 0.6 + 150 + 30);
    expect(rows.find((r) => r.key === "mol")!.years[0].value).toBe(1100 + 50 - 825 - 20);
  });
  it("con override i componenti sono null e la riga lo dice", () => {
    const y = year(2027); y.details.ce05_fixed = null; y.details.ce05_variable = null;
    const rows = rowsCosti(baseInc, { materials: 40, services: 40 }, [y]);
    expect(rows.find((r) => r.key === "fissi")!.years[0].value).toBeNull();
    expect(rows.find((r) => r.key === "fissi")!.years[0].note).toBe("forzato in CE Prev.");
  });
});

describe("rowsImposte / rowsPregressoNuovo / unfundedFromError", () => {
  it("imposte e utile netto", () => {
    const rows = rowsImposte(baseInc, [year(2027)]);
    expect(rows.find((r) => r.key === "ce20")!.years[0].value).toBe(-33);
  });
  it("PFN = debiti finanziari - cassa", () => {
    const rows = rowsPregressoNuovo({ sp09_disponibilita_liquide: "50", sp16a_debiti_banche_breve: "30",
      sp17a_debiti_banche_lungo: "120" } as unknown as BalanceSheet, [year(2027)]);
    expect(rows.find((r) => r.key === "pfn")!.years[0].value).toBe(20 + 100 - 80);
  });
  it("estrae anno e importo dal messaggio del motore", () => {
    expect(unfundedFromError({ year: 2028, message: "Unfunded financing requirement 84,120.50: add ..." }))
      .toEqual({ year: 2028, amount: 84120.5 });
    expect(unfundedFromError({ year: null, message: "altro" })).toBeNull();
  });
});
```

- [ ] **Step 2: Eseguire, vedere fallire**

Run: `npx vitest run lib/budget-preview-rows` → FAIL, modulo non trovato.

- [ ] **Step 3: Implementare**

```ts
// frontend/lib/budget-preview-rows.ts
/**
 * Dalla risposta di POST /preview alle righe dell'anteprima di ogni passo.
 * Solo somme, differenze e percentuali di numeri che il motore ha gia'
 * restituito: qui non si deriva nulla (spec 2026-09-08 §7).
 */
import type { BalanceSheet, ForecastPreviewError, ForecastPreviewYear, IncomeStatement } from "@/types/api";

export interface PreviewCell { value: number | null; pct?: number | null; days?: number | null; note?: string }
export type PreviewRowKind = "value" | "sub" | "total" | "kpi";
export interface PreviewRow { key: string; label: string; kind: PreviewRowKind; base: PreviewCell; years: PreviewCell[] }

const num = (v: unknown): number => (typeof v === "number" ? v : parseFloat(String(v ?? "0")) || 0);
const pctOf = (v: number | null, den: number): number | null => (v === null || den === 0 ? null : (v / den) * 100);
const row = (key: string, label: string, kind: PreviewRowKind, base: PreviewCell, years: PreviewCell[]): PreviewRow =>
  ({ key, label, kind, base, years });

export function rowsFatturato(baseInc: IncomeStatement, years: ForecastPreviewYear[]): PreviewRow[] {
  const b01 = num(baseInc.ce01_ricavi_vendite), b04 = num(baseInc.ce04_altri_ricavi);
  let prev01 = b01, prev04 = b04;
  const r01: PreviewCell[] = [], d01: PreviewCell[] = [], r04: PreviewCell[] = [], vp: PreviewCell[] = [], cum: PreviewCell[] = [];
  for (const y of years) {
    const v01 = num(y.income_statement.ce01_ricavi_vendite), v04 = num(y.income_statement.ce04_altri_ricavi);
    r01.push({ value: v01, pct: prev01 ? ((v01 - prev01) / prev01) * 100 : null });
    d01.push({ value: v01 - prev01 });
    r04.push({ value: v04, pct: prev04 ? ((v04 - prev04) / prev04) * 100 : null });
    vp.push({ value: v01 + v04 });
    cum.push({ value: null, pct: b01 ? ((v01 - b01) / b01) * 100 : null });
    prev01 = v01; prev04 = v04;
  }
  return [
    row("ce01", "Ricavi delle vendite", "kpi", { value: b01 }, r01),
    row("delta", "variazione assoluta", "sub", { value: null }, d01),
    row("ce04", "Altri ricavi e proventi", "value", { value: b04 }, r04),
    row("vp", "Valore della produzione", "total", { value: b01 + b04 }, vp),
    row("cumulata", "crescita cumulata sul base", "sub", { value: null }, cum),
  ];
}

export function rowsCosti(
  baseInc: IncomeStatement, fixedShare: { materials: number; services: number }, years: ForecastPreviewYear[],
): PreviewRow[] {
  const b = {
    rev: num(baseInc.ce01_ricavi_vendite), other: num(baseInc.ce04_altri_ricavi),
    mat: num(baseInc.ce05_materie_prime), serv: num(baseInc.ce06_servizi),
    god: num(baseInc.ce07_godimento_beni), pers: num(baseInc.ce08_costi_personale), alt: num(baseInc.ce12_oneri_diversi),
  };
  const bFixed = b.mat * fixedShare.materials / 100 + b.serv * fixedShare.services / 100 + b.pers + b.god;
  const bVar = b.mat + b.serv - (b.mat * fixedShare.materials / 100 + b.serv * fixedShare.services / 100);
  const bMain = b.mat + b.serv + b.god + b.pers;
  const cell = (v: number | null, rev: number, note?: string): PreviewCell => ({ value: v, pct: pctOf(v, rev), ...(note ? { note } : {}) });
  const cols = years.map((y) => {
    const i = y.income_statement, d = y.details;
    const rev = num(i.ce01_ricavi_vendite);
    const mat = num(i.ce05_materie_prime), serv = num(i.ce06_servizi), god = num(i.ce07_godimento_beni), pers = num(i.ce08_costi_personale);
    const main = mat + serv + god + pers;
    const split = d.ce05_fixed !== null && d.ce06_fixed !== null && d.ce05_variable !== null && d.ce06_variable !== null;
    const fixed = split ? d.ce05_fixed! + d.ce06_fixed! + pers + god : null;
    const variable = split ? d.ce05_variable! + d.ce06_variable! : null;
    const note = split ? undefined : "forzato in CE Prev.";
    return {
      rev: { value: rev } as PreviewCell,
      main: cell(main, rev), fixed: cell(fixed, rev, note), variable: cell(variable, rev, note),
      mat: cell(mat, rev), serv: cell(serv, rev), pers: cell(pers, rev), god: cell(god, rev),
      mol: cell(rev + num(i.ce04_altri_ricavi) - main - num(i.ce12_oneri_diversi), rev),
      forn: { value: num(y.balance_sheet.sp16d_debiti_fornitori_breve), days: d.dpo_applied } as PreviewCell,
    };
  });
  const pick = (k: keyof (typeof cols)[number]) => cols.map((c) => c[k]);
  return [
    row("ricavi", "Ricavi delle vendite", "sub", { value: b.rev }, pick("rev")),
    row("principali", "Costi principali", "total", cell(bMain, b.rev), pick("main")),
    row("fissi", "di cui fissi", "sub", cell(bFixed, b.rev), pick("fixed")),
    row("variabili", "di cui variabili", "sub", cell(bVar, b.rev), pick("variable")),
    row("ce05", "Materie prime", "value", cell(b.mat, b.rev), pick("mat")),
    row("ce06", "Servizi", "value", cell(b.serv, b.rev), pick("serv")),
    row("ce08", "Personale", "value", cell(b.pers, b.rev), pick("pers")),
    row("ce07", "Godimento beni di terzi", "value", cell(b.god, b.rev), pick("god")),
    row("mol", "MOL stimato", "kpi", cell(b.rev + b.other - bMain - b.alt, b.rev), pick("mol")),
    row("fornitori", "Debiti verso fornitori stimati", "value", { value: null }, pick("forn")),
  ];
}

export function rowsAltreVociCe(baseInc: IncomeStatement, years: ForecastPreviewYear[]): PreviewRow[] {
  const g = (i: Record<string, unknown>, k: string) => num(i[k]);
  const mk = (i: Record<string, unknown>) => {
    const vp = g(i, "ce01_ricavi_vendite") + g(i, "ce04_altri_ricavi");
    const main = g(i, "ce05_materie_prime") + g(i, "ce06_servizi") + g(i, "ce07_godimento_beni") + g(i, "ce08_costi_personale");
    const alt = g(i, "ce12_oneri_diversi"), amm = g(i, "ce09_ammortamenti"), of = g(i, "ce15_oneri_finanziari");
    const mol = vp - main - alt, ro = mol - amm;
    return { vp, main: -main, alt: -alt, mol, amm: -amm, ro, of: -of, ebt: ro - of, rev: g(i, "ce01_ricavi_vendite") };
  };
  const b = mk(baseInc as unknown as Record<string, unknown>);
  const ys = years.map((y) => mk(y.income_statement));
  const r = (key: keyof typeof b, label: string, kind: PreviewRowKind, withPct = false): PreviewRow =>
    row(key, label, kind, { value: b[key], ...(withPct ? { pct: pctOf(b[key], b.rev) } : {}) },
      ys.map((c) => ({ value: c[key], ...(withPct ? { pct: pctOf(c[key], c.rev) } : {}) })));
  return [
    r("vp", "Valore della produzione", "value"), r("main", "Costi principali", "sub"),
    r("alt", "Oneri diversi di gestione", "sub"), r("mol", "MOL", "kpi", true),
    r("amm", "Ammortamenti", "sub"), r("ro", "Risultato operativo", "kpi"),
    r("of", "Oneri finanziari", "sub"), r("ebt", "Risultato ante imposte", "total"),
  ];
}

export function rowsCircolante(baseBs: BalanceSheet, baseInc: IncomeStatement, years: ForecastPreviewYear[]): PreviewRow[] {
  const bCred = num(baseBs.sp06_crediti_breve) - num(baseBs.sp06e_crediti_tributari_breve) - num(baseBs.sp06f_imposte_anticipate_breve);
  const bMag = num(baseBs.sp05_rimanenze), bForn = num(baseBs.sp16d_debiti_fornitori_breve), bRev = num(baseInc.ce01_ricavi_vendite);
  const bCcn = bCred + bMag - bForn;
  let prevCcn = bCcn;
  const cells = years.map((y) => {
    const bs = y.balance_sheet, d = y.details;
    const cred = num(bs.sp06_crediti_breve) - num(bs.sp06e_crediti_tributari_breve) - num(bs.sp06f_imposte_anticipate_breve);
    const mag = num(bs.sp05_rimanenze), forn = num(bs.sp16d_debiti_fornitori_breve), rev = num(y.income_statement.ce01_ricavi_vendite);
    const ccn = cred + mag - forn;
    const out = { cred: { value: cred, days: d.dso_applied }, mag: { value: mag, days: d.dio_applied },
      forn: { value: -forn, days: d.dpo_applied }, ccn: { value: ccn }, pct: { value: null, pct: pctOf(ccn, rev) },
      cash: { value: -(ccn - prevCcn) } };
    prevCcn = ccn;
    return out;
  });
  const pick = (k: keyof (typeof cells)[number]) => cells.map((c) => c[k] as PreviewCell);
  return [
    row("crediti", "Crediti commerciali", "value", { value: bCred }, pick("cred")),
    row("rimanenze", "Rimanenze", "value", { value: bMag }, pick("mag")),
    row("fornitori", "Debiti verso fornitori", "value", { value: -bForn }, pick("forn")),
    row("ccn", "Capitale circolante commerciale", "total", { value: bCcn }, pick("ccn")),
    row("ccn-pct", "in % dei ricavi", "sub", { value: null, pct: pctOf(bCcn, bRev) }, pick("pct")),
    row("cassa", "assorbimento di cassa nell'anno", "sub", { value: null }, pick("cash")),
  ];
}

const finDebt = (bs: Record<string, unknown>) =>
  num(bs.sp16a_debiti_banche_breve) + num(bs.sp17a_debiti_banche_lungo) + num(bs.sp16b_debiti_altri_finanz_breve)
  + num(bs.sp17b_debiti_altri_finanz_lungo) + num(bs.sp16c_debiti_obbligazioni_breve) + num(bs.sp17c_debiti_obbligazioni_lungo);

export function rowsPregressoNuovo(baseBs: BalanceSheet, years: ForecastPreviewYear[]): PreviewRow[] {
  const bb = baseBs as unknown as Record<string, unknown>;
  const mk = (bs: Record<string, unknown>) => {
    const bank = num(bs.sp16a_debiti_banche_breve) + num(bs.sp17a_debiti_banche_lungo);
    const altri = num(bs.sp16b_debiti_altri_finanz_breve) + num(bs.sp17b_debiti_altri_finanz_lungo);
    const cash = num(bs.sp09_disponibilita_liquide);
    const immob = num(bs.sp02_immob_immateriali) + num(bs.sp03_immob_materiali);
    return { bank, altri, immob, cash, pfn: finDebt(bs) - cash };
  };
  const b = mk(bb), ys = years.map((y) => mk(y.balance_sheet));
  const r = (key: keyof typeof b, label: string, kind: PreviewRowKind): PreviewRow =>
    row(key, label, kind, { value: b[key] }, ys.map((c) => ({ value: c[key] })));
  return [
    r("bank", "Debiti bancari", "value"), r("altri", "Altri finanziatori", "value"),
    r("immob", "Immobilizzazioni nette", "value"), r("cash", "Cassa", "kpi"),
    r("pfn", "Posizione finanziaria netta", "total"),
  ];
}

export function rowsImposte(baseInc: IncomeStatement, years: ForecastPreviewYear[]): PreviewRow[] {
  const g = (i: Record<string, unknown>, k: string) => num(i[k]);
  const mk = (i: Record<string, unknown>, bs?: Record<string, unknown>) => {
    const vp = g(i, "ce01_ricavi_vendite") + g(i, "ce04_altri_ricavi");
    const costs = g(i, "ce05_materie_prime") + g(i, "ce06_servizi") + g(i, "ce07_godimento_beni")
      + g(i, "ce08_costi_personale") + g(i, "ce12_oneri_diversi") + g(i, "ce09_ammortamenti") + g(i, "ce15_oneri_finanziari");
    const ebt = vp - costs, tax = g(i, "ce20_imposte");
    return { ebt, tax: -tax, net: ebt - tax, trib: bs ? num(bs.sp16e_debiti_tributari_breve) : null };
  };
  const b = mk(baseInc as unknown as Record<string, unknown>), ys = years.map((y) => mk(y.income_statement, y.balance_sheet));
  const r = (key: keyof typeof b, label: string, kind: PreviewRowKind): PreviewRow =>
    row(key === "tax" ? "ce20" : key, label, kind, { value: b[key] }, ys.map((c) => ({ value: c[key] })));
  return [r("ebt", "Risultato ante imposte", "value"), r("tax", "Imposte", "sub"),
    r("net", "Utile netto", "kpi"), r("trib", "Debiti tributari a fine anno", "value")];
}

export function unfundedFromError(error: ForecastPreviewError | null): { year: number; amount: number } | null {
  if (!error || error.year === null) return null;
  const m = /Unfunded financing requirement ([\d,]+\.\d{2})/i.exec(error.message);
  if (!m) return null;
  return { year: error.year, amount: parseFloat(m[1].replace(/,/g, "")) };
}
```

Nota su `rowsImposte`: il risultato ante imposte è **ricapitolato** dalle righe del CE che il motore ha già scritto (stessa formula canonica di `computeEffectiveTaxRate` in `assumption-rows.ts:150-174`, compresi ce13/14/16/17 se presenti: aggiungerli al `costs` con il segno giusto copiando quella funzione, così le due non divergono). È aritmetica sullo schermo, non derivazione.

- [ ] **Step 4: Verificare**

Run: `npx vitest run lib/budget-preview-rows && npx tsc --noEmit` → PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/budget-preview-rows.ts frontend/lib/budget-preview-rows.test.ts
git commit -m "feat(budget): righe dell'anteprima per passo, modulo puro"
```

---

### Task 5: `lib/budget-preview-queue.ts` — sequenza e debounce senza React

**Modello:** haiku · **Ondata:** A

**Files:**
- Create: `frontend/lib/budget-preview-queue.ts`, `frontend/lib/budget-preview-queue.test.ts`

**Interfaces:**
- Produces:

```ts
export class PreviewSequencer { next(): number; isCurrent(seq: number): boolean }
export function createDebouncedRunner<T>(run: (payload: T, signal: AbortSignal) => void, delayMs: number,
  timers?: { setTimeout: typeof setTimeout; clearTimeout: typeof clearTimeout }): { push(payload: T): void; cancel(): void }
```

`push` annulla il timer precedente e l'`AbortController` della chiamata in volo; dopo `delayMs` chiama `run` con un nuovo `signal`. `cancel` ferma tutto (usato allo smontaggio).

- [ ] **Step 1: Test**

```ts
// frontend/lib/budget-preview-queue.test.ts
import { describe, expect, it, vi } from "vitest";
import { PreviewSequencer, createDebouncedRunner } from "./budget-preview-queue";

describe("PreviewSequencer", () => {
  it("solo l'ultimo numero e' corrente", () => {
    const s = new PreviewSequencer();
    const a = s.next(), b = s.next();
    expect(s.isCurrent(a)).toBe(false);
    expect(s.isCurrent(b)).toBe(true);
  });
});

describe("createDebouncedRunner", () => {
  it("coalesce le chiamate entro il ritardo e annulla quella in volo", () => {
    vi.useFakeTimers();
    const run = vi.fn<(p: number, s: AbortSignal) => void>();
    const runner = createDebouncedRunner(run, 400);
    runner.push(1); runner.push(2);
    vi.advanceTimersByTime(399);
    expect(run).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(run).toHaveBeenCalledTimes(1);
    expect(run.mock.calls[0][0]).toBe(2);
    const firstSignal = run.mock.calls[0][1];
    runner.push(3);
    vi.advanceTimersByTime(400);
    expect(firstSignal.aborted).toBe(true);
    expect(run).toHaveBeenCalledTimes(2);
    runner.cancel();
    expect(run.mock.calls[1][1].aborted).toBe(true);
    vi.useRealTimers();
  });
});
```

- [ ] **Step 2: Eseguire, vedere fallire** — `npx vitest run lib/budget-preview-queue` → FAIL.

- [ ] **Step 3: Implementare**

```ts
// frontend/lib/budget-preview-queue.ts
/** Debounce + annullamento per l'anteprima, senza React: testabile in node. */
export class PreviewSequencer {
  private seq = 0;
  next(): number { return ++this.seq; }
  isCurrent(seq: number): boolean { return seq === this.seq; }
}

export function createDebouncedRunner<T>(
  run: (payload: T, signal: AbortSignal) => void,
  delayMs: number,
  timers: { setTimeout: typeof setTimeout; clearTimeout: typeof clearTimeout } = { setTimeout, clearTimeout },
): { push(payload: T): void; cancel(): void } {
  let timer: ReturnType<typeof setTimeout> | null = null;
  let controller: AbortController | null = null;
  const cancel = () => {
    if (timer !== null) { timers.clearTimeout(timer); timer = null; }
    if (controller) { controller.abort(); controller = null; }
  };
  return {
    push(payload: T) {
      cancel();
      timer = timers.setTimeout(() => {
        timer = null;
        controller = new AbortController();
        run(payload, controller.signal);
      }, delayMs);
    },
    cancel,
  };
}
```

- [ ] **Step 4: Verificare** — `npx vitest run lib/budget-preview-queue` → PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/budget-preview-queue.ts frontend/lib/budget-preview-queue.test.ts
git commit -m "feat(budget): debounce e annullamento dell'anteprima, modulo puro"
```

---

### Task 6: `lib/budget-field-rules.ts` e `lib/budget-trend.ts`

**Modello:** sonnet · **Ondata:** A

**Files:**
- Create: `frontend/lib/budget-field-rules.ts` (+ test), `frontend/lib/budget-trend.ts` (+ test)
- Modify: `frontend/components/budget/assumption-rows.ts` (importa le regole invece di ripeterle), `frontend/app/budget/page.tsx:1906-1935` (rimuove `calculateTrend`, `TREND_ITEMS`; li importa)

**Interfaces:**
- Produces:

```ts
// budget-field-rules.ts
export interface FieldRule { kind: "pct" | "eur" | "years" | "days" | "bool"; min?: number; max?: number; step?: string; nullable?: boolean }
export const FIELD_RULES: Record<string, FieldRule>;   // una voce per ogni campo di STEP_FIELDS (Task 3) piu' i dual-write dello startup
export function parseFieldValue(field: string, raw: string): number | null   // "" -> null se nullable, altrimenti 0; virgola accettata; clamp min/max
// budget-trend.ts
export type HistoricalData = Record<number, { income: IncomeStatement; balance: BalanceSheet }>;
export function calculateTrend(historicalData: HistoricalData, year1: number, year2: number, getValue: (i: IncomeStatement) => number): number | null;
export const TREND_ITEMS: { label: string; fields: string[]; getValue: (i: IncomeStatement) => number }[];
export function blendedRate(trend: number | null, inflation: number, index: number, n: number): number;  // la formula di page.tsx:1961-1972, copiata
export function trendAssumptions(historicalYears: number[], forecastYears: number[], historicalData: HistoricalData, inflation: number): Record<number, Record<string, number>>;
```

- [ ] **Step 1: Test**

```ts
// frontend/lib/budget-field-rules.test.ts
import { describe, expect, it } from "vitest";
import { FIELD_RULES, parseFieldValue } from "./budget-field-rules";
import { STEP_FIELDS } from "./budget-wizard-steps";

describe("budget-field-rules", () => {
  it("ogni campo scalare dei passi ha una regola", () => {
    const json = new Set(["financing_loans", "tax_temporary_differences"]);
    for (const fields of Object.values(STEP_FIELDS))
      for (const f of fields) if (!json.has(f)) expect(FIELD_RULES[f], f).toBeDefined();
  });
  it("parse: virgola, vuoto, clamp", () => {
    expect(parseFieldValue("revenue_growth_pct", "12,5")).toBe(12.5);
    expect(parseFieldValue("dso_days", "")).toBeNull();
    expect(parseFieldValue("revenue_growth_pct", "")).toBe(0);
    expect(parseFieldValue("fixed_materials_percentage", "140")).toBe(100);
    expect(parseFieldValue("tangible_investments", "-5")).toBe(0);
  });
});
```

```ts
// frontend/lib/budget-trend.test.ts
import { describe, expect, it } from "vitest";
import type { IncomeStatement } from "@/types/api";
import { blendedRate, calculateTrend, trendAssumptions } from "./budget-trend";

const inc = (v: number) => ({ income: { ce01_ricavi_vendite: String(v), ce04_altri_ricavi: "0", ce05_materie_prime: "0",
  ce06_servizi: "0", ce07_godimento_beni: "0", ce08_costi_personale: "0", ce12_oneri_diversi: "0" } as unknown as IncomeStatement,
  balance: {} as never });

describe("budget-trend", () => {
  it("tendenza = variazione % fra i due ultimi anni", () => {
    const h = { 2024: inc(100), 2025: inc(110) };
    expect(calculateTrend(h, 2024, 2025, (i) => parseFloat(i.ce01_ricavi_vendite))).toBeCloseTo(10);
    expect(calculateTrend(h, 2023, 2025, (i) => parseFloat(i.ce01_ricavi_vendite))).toBeNull();
  });
  it("il tasso smussato parte dalla media e converge all'inflazione", () => {
    expect(blendedRate(10, 2, 0, 3)).toBeCloseTo(blendedRate(10, 2, 0, 3)); // stabile
    expect(blendedRate(10, 2, 2, 3)).toBeLessThan(blendedRate(10, 2, 0, 3));
    expect(blendedRate(null, 2, 0, 3)).toBe(2);
  });
  it("trendAssumptions scrive ogni campo delle TREND_ITEMS per ogni anno", () => {
    const out = trendAssumptions([2024, 2025], [2026, 2027], { 2024: inc(100), 2025: inc(110) }, 2);
    expect(Object.keys(out)).toEqual(["2026", "2027"]);
    expect(out[2026].revenue_growth_pct).toBeGreaterThan(2);
    expect(out[2026].variable_materials_growth_pct).toBeDefined();
  });
});
```

- [ ] **Step 2: Eseguire, vedere fallire** — `npx vitest run lib/budget-field-rules lib/budget-trend` → FAIL.

- [ ] **Step 3: Implementare**

`budget-field-rules.ts`: costruire `FIELD_RULES` dalle definizioni oggi sparse in `assumption-rows.ts` (`kind`, `min`, `max`, `step`, `nullable` di ogni riga di `ESSENTIAL_ROWS` e `ADVANCED_GROUPS`, una voce per ogni `fields[i]`), più `other_revenue_growth_pct`, `sp16e/sp17e_growth_pct` (già presenti). `parseFieldValue`:

```ts
export function parseFieldValue(field: string, raw: string): number | null {
  const rule = FIELD_RULES[field] ?? { kind: "pct" };
  const t = raw.trim();
  if (t === "") return rule.nullable ? null : 0;
  const n = parseFloat(t.replace(",", "."));
  if (Number.isNaN(n)) return rule.nullable ? null : 0;
  const lo = rule.min ?? -Infinity, hi = rule.max ?? Infinity;
  return Math.min(hi, Math.max(lo, n));
}
```

Poi `assumption-rows.ts` importa `FIELD_RULES` e le usa nelle sue definizioni (`...FIELD_RULES["revenue_growth_pct"]`) invece di ripetere min/max/step: le regole restano una.

`budget-trend.ts`: spostare `calculateTrend` e `TREND_ITEMS` da `page.tsx:1906-1935` **tali e quali**; `blendedRate` è la formula del blend di `page.tsx:1961-1972` estratta in una funzione pura (copiarla riga per riga; il test la fissa solo per monotonia e per il caso `trend === null`). `trendAssumptions` itera `TREND_ITEMS` × `forecastYears` e scrive `blendedRate(trend, inflation, index, n)` in ogni `fields[i]`. In `page.tsx` sostituire le definizioni con `import { calculateTrend, TREND_ITEMS, blendedRate } from "@/lib/budget-trend"` e usare `blendedRate` dentro `AutoGeneratorCard`.

- [ ] **Step 4: Verificare** — `npx vitest run lib/ && npx tsc --noEmit` → tutto PASS (anche le suite esistenti).

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/budget-field-rules.ts frontend/lib/budget-field-rules.test.ts frontend/lib/budget-trend.ts frontend/lib/budget-trend.test.ts frontend/components/budget/assumption-rows.ts frontend/app/budget/page.tsx
git commit -m "refactor(budget): regole per campo e tendenza storica in moduli puri"
```

---

### Task 7: `hooks/use-scenario-assumptions.ts` — la mappa idratata esce da `ScenarioForm`

**Modello:** sonnet · **Ondata:** A (tocca `page.tsx`: nessun altro task dell'ondata A lo tocca, tranne il Task 6 su righe diverse, `:1906-1972`; se i due agenti sono in parallelo, il Task 7 fa il rebase)

**Files:**
- Create: `frontend/hooks/use-scenario-assumptions.ts`
- Modify: `frontend/app/budget/page.tsx:856-1148` (`ScenarioForm`), rinominato `ScenarioFormStartup`
- Create: `frontend/components/budget/FinancingLoansGrid.tsx`, `frontend/components/budget/TaxTemporaryDifferencesGrid.tsx` (spostati da `page.tsx:1476-1735` e `:1737-1845`, esportati)

**Interfaces:**
- Produces:

```ts
export interface ScenarioAssumptionsState {
  baseYear: number; notaAnnoBase: string | null;
  numYears: number; setNumYears: (n: number) => void; forecastYears: number[];
  historicalYears: number[]; historicalData: HistoricalData;
  assumptions: AssumptionsMap; setAssumptions: React.Dispatch<React.SetStateAction<AssumptionsMap>>;
  idratato: boolean; isNew: boolean;                      // isNew = nessuna ipotesi salvata
  updateAssumption: (year: number, field: string, value: number | boolean | null) => void;
  updateAll: (field: string, value: number | boolean | null) => void;   // tutti i forecastYears
  updateFinancingLoans: (year: number, loans: FinancingLoanInput[]) => void;
  updateTemporaryDifferences: (year: number, lines: TemporaryDifferenceInput[]) => void;
}
export function useScenarioAssumptions(args: { companyId: number; years: number[]; scenario: BudgetScenario | null }): ScenarioAssumptionsState;
```

- [ ] **Step 1: Spostare, non riscrivere**

Creare l'hook portando dentro, **verbatim**, da `ScenarioForm`: `baseYear`/`notaAnnoBase`/`forecastYears` (`:884-903`), il loader di `historicalData` (`:912-931`), lo stato `assumptions`/`existingAssumptionYears`/`idratato` e l'effetto di idratazione con la mappa completa dei campi (`:932-1099`), l'effetto dei default per gli anni scoperti, e i tre callback `updateAssumption`/`updateFinancingLoans`/`updateTemporaryDifferences` (`:1120-1148`). Aggiungere:

```ts
  const isNew = idratato && existingAssumptionYears.size === 0;
  const updateAll = useCallback((field: string, value: number | boolean | null) => {
    setAssumptions((prev) => {
      const next = { ...prev };
      for (const y of forecastYears) next[y] = { ...(next[y] ?? {}), [field]: value };
      return next;
    });
  }, [forecastYears]);
```

`ScenarioForm` diventa `ScenarioFormStartup`, chiama l'hook e usa i suoi valori al posto degli stati locali; **il resto del corpo non cambia**. Spostare `FinancingLoansGrid` e `TaxTemporaryDifferencesGrid` nei loro file con `export function`, importarli in `page.tsx`.

- [ ] **Step 2: Verificare che nulla sia cambiato**

Run: `npx tsc --noEmit && npx vitest run lib/` → PASS. Poi, con i dev server accesi (`DEV_USER_ID=dev-user-001 uvicorn ...` da `backend/`, `npm run dev`), aprire uno scenario esistente in `/budget`, modificare una percentuale, «Salva e Calcola Previsionale», verificare che il toast sia verde e che `/forecast/income` mostri i numeri attesi. In startupMode: creare una startup dal wizard e verificare che il form si apra con le sue righe.

- [ ] **Step 3: Commit**

```bash
git add frontend/hooks/use-scenario-assumptions.ts frontend/components/budget/FinancingLoansGrid.tsx frontend/components/budget/TaxTemporaryDifferencesGrid.tsx frontend/app/budget/page.tsx
git commit -m "refactor(budget): la mappa idratata delle ipotesi in un hook; le due griglie in file propri"
```

---

### Task 8: Componenti condivisi del wizard — `types.ts`, `YearInputTable`, `WizardRail`, `PreviewPanel`

**Modello:** sonnet · **Ondata:** A

**Files:**
- Create: `frontend/components/budget/wizard/types.ts`, `YearInputTable.tsx`, `WizardRail.tsx`, `PreviewPanel.tsx`

**Interfaces:**
- Produces:

```ts
// types.ts
export interface PreviewState { data: ForecastPreviewResponse | null; error: string | null; loading: boolean }
export interface StepProps {
  companyId: number; scenarioId: number | null; baseYear: number; forecastYears: number[];
  assumptions: AssumptionsMap; historical: HistoricalData; historicalYears: number[];
  preview: PreviewState;
  update: (year: number, field: string, value: number | boolean | null) => void;
  updateAll: (field: string, value: number | boolean | null) => void;
  updateFinancingLoans: (year: number, loans: FinancingLoanInput[]) => void;
  updateTemporaryDifferences: (year: number, lines: TemporaryDifferenceInput[]) => void;
}
// YearInputTable.tsx
export interface YearInputRow { field: string; label: string; sub?: string; baseLabel: string; off?: boolean; placeholder?: (year: number) => string; group?: never }
export interface YearInputGroup { group: string; swatch?: "fixed" | "variable" }
export function YearInputTable(props: { rows: (YearInputRow | YearInputGroup)[]; forecastYears: number[]; baseYear: number; assumptions: AssumptionsMap; update: StepProps["update"] }): JSX.Element
// WizardRail.tsx
export function WizardRail(props: { active: WizardStepKey; visited: Set<WizardStepKey>; horizon: number; baseYear: number; onGo: (k: WizardStepKey) => void }): JSX.Element
// PreviewPanel.tsx
export function PreviewPanel(props: { title: string; baseYear: number; years: number[]; rows: PreviewRow[]; loading: boolean; error: string | null; children?: React.ReactNode }): JSX.Element
```

- [ ] **Step 1: `types.ts`** — come sopra, con gli import di tipo da `@/types/api`, `@/lib/budget-horizon` (`AssumptionsMap`), `@/lib/budget-trend` (`HistoricalData`).

- [ ] **Step 2: `YearInputTable`**

Una `<table>` shadcn-style (`components/ui/table` non serve: usare `<table className="w-full text-sm">` come in `AssumptionsGrid.tsx`): intestazione `Voce | {baseYear} | anno…`; per una riga-gruppo una `<tr>` con `colSpan` e un quadratino colorato (`bg-blue-500` per `fixed`, `bg-amber-500` per `variable`); per una riga-campo la `baseLabel` in grigio e un `<Input type="number" inputMode="decimal">` per anno, valore da `assumptions[year]?.[field]`, `onChange` → `update(year, field, parseFieldValue(field, e.target.value))` (Task 6). Righe `off` con `opacity-40` e input `disabled`. Placeholder da `placeholder?.(year)`.

- [ ] **Step 3: `WizardRail`**

La guida orizzontale della spec §4.0: un `<nav aria-label="Passi delle ipotesi">` con `Card` che contiene, per ciascun gruppo di `WIZARD_STEPS`, un'etichetta `text-[10px] uppercase tracking-wider text-muted-foreground` e sotto i pulsanti dei passi (numero in un cerchio da 20px: attivo `border-primary text-primary bg-primary/10`, visitato `bg-green-600 text-white` con `<Check>` di lucide, altrimenti `border-border text-muted-foreground`; sottolineatura di 2px `bg-primary` sotto l'attivo). A destra, separato da un bordo, `Orizzonte {horizon} anni · {baseYear+1} – {baseYear+horizon}`. `overflow-x-auto` sul contenitore. Ogni pulsante ha `aria-current="step"` se attivo e chiama `onGo(key)`.

- [ ] **Step 4: `PreviewPanel`**

`Card` con `border-border/80`, `sticky top-4` (il chiamante decide la colonna). Intestazione: pallino verde `h-2 w-2 rounded-full bg-green-500` + titolo; se `loading` un `<Loader2 className="animate-spin">` piccolo a destra. Corpo: tabella `rows` → intestazione `"" | base | years…`; per riga: `kind` → classi (`sub`: `text-muted-foreground text-xs pl-4`; `total`: `font-semibold border-t bg-muted/40`; `kpi`: `font-semibold`); cella: `formatCurrency(value)` (da `@/lib/formatters`), sotto in `text-[11px] text-muted-foreground` la `pct` formattata `formatPercent` o `{days} gg`; `value === null` → «—» con `title={note}` e la `note` in corsivo se presente. Se `error`, una riga `bg-destructive/10 text-destructive` sotto la tabella con il messaggio. `children` va sotto la tabella (usato dal passo 3 per la barra fissi/variabili e dal 6 per l'avviso).

- [ ] **Step 5: Verificare** — `npx tsc --noEmit` → PASS. Nessun test automatico su questi componenti: sono presentazionali e li copre il collaudo (Task 17).

- [ ] **Step 6: Commit**

```bash
git add frontend/components/budget/wizard/
git commit -m "feat(budget): componenti condivisi del wizard: tabella per anno, guida, pannello di anteprima"
```

---

## Ondata B

### Task 9: Servizio, schema e route `POST /preview`

**Modello:** sonnet · **Ondata:** B (dopo 1 e 2)

**Files:**
- Create: `backend/app/services/forecast_preview_service.py`
- Modify: `backend/app/schemas/forecast.py` (in fondo), `backend/app/api/v1/budget_scenarios.py` (dopo la route `generate_forecasts`, `:979`)
- Test: `tests/test_forecast_preview.py`

**Interfaces:**
- Consumes: `build_assumption_row` (Task 1); `load_forecast_source`, `ForecastEngine.compute_forecast` (Task 2).
- Produces: `preview_forecast(db, scenario_id: int, assumptions_list: List[dict]) -> dict` con la forma della spec §5.1; route `POST /companies/{company_id}/scenarios/{scenario_id}/preview`, `response_model=ForecastPreviewResponse`.

- [ ] **Step 1: Test**

```python
# tests/test_forecast_preview.py
from decimal import Decimal

import pytest
from fastapi import HTTPException

from backend.app.api.v1 import budget_scenarios
from backend.app.schemas.budget import BudgetScenarioCreate
from database import models
from tests.e2e_kit import memory_sessions, read_forecast_maps, seed_base_year

USER = "preview"


def _saved_scenario(db, company_id):
    sc = budget_scenarios.create_budget_scenario(
        company_id, BudgetScenarioCreate(company_id=company_id, name="p", base_year=2026, scenario_type="budget"),
        user_id=USER, db=db)
    rows = [{"forecast_year": y, "revenue_growth_pct": 5} for y in (2027, 2028)]
    res = budget_scenarios.bulk_upsert_assumptions(
        company_id, sc.id, request={"assumptions": rows, "auto_generate": True}, user_id=USER, db=db)
    assert res["forecast_generated"] is True
    return sc, rows


def _counts(db):
    return tuple(db.query(m).count() for m in (
        models.BudgetAssumptions, models.ForecastYear, models.ForecastBalanceSheet, models.ForecastIncomeStatement))


def test_preview_of_saved_rows_equals_persisted_and_writes_nothing(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            sc, rows = _saved_scenario(db, company_id)
            before = _counts(db)
            saved_pct = [a.revenue_growth_pct for a in db.query(models.BudgetAssumptions).order_by(models.BudgetAssumptions.forecast_year)]
            out = budget_scenarios.preview_forecast_route(
                company_id, sc.id, request={"assumptions": [dict(r, revenue_growth_pct=40) for r in rows]},
                user_id=USER, db=db)
            assert out["error"] is None
            assert [y["year"] for y in out["forecast_years"]] == [2027, 2028]
            assert _counts(db) == before
            assert [a.revenue_growth_pct for a in db.query(models.BudgetAssumptions).order_by(models.BudgetAssumptions.forecast_year)] == saved_pct
            # con le righe salvate, l'anteprima coincide col persistito
            same = budget_scenarios.preview_forecast_route(
                company_id, sc.id, request={"assumptions": rows}, user_id=USER, db=db)
            for y, (_, bs, ce) in zip(same["forecast_years"], read_forecast_maps(db, sc.id)):
                assert Decimal(str(y["balance_sheet"]["sp09_disponibilita_liquide"])) == bs["sp09_disponibilita_liquide"]
                assert Decimal(str(y["income_statement"]["ce01_ricavi_vendite"])) == ce["ce01_ricavi_vendite"]
            for key in ("ce05_fixed", "ce05_variable", "ce06_fixed", "ce06_variable", "dso_applied", "dio_applied", "dpo_applied"):
                assert key in same["forecast_years"][0]["details"]
    finally:
        engine.dispose()


def test_unfunded_requirement_returns_200_with_partial_years(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            sc, rows = _saved_scenario(db, company_id)
            rows[1]["tangible_investments"] = 5_000_000
            out = budget_scenarios.preview_forecast_route(
                company_id, sc.id, request={"assumptions": rows}, user_id=USER, db=db)
            assert [y["year"] for y in out["forecast_years"]] == [2027]
            assert out["error"]["year"] == 2028
            assert "Unfunded financing requirement" in out["error"]["message"]
    finally:
        engine.dispose()


def test_bad_input_is_400_and_foreign_scenario_is_404(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            sc, rows = _saved_scenario(db, company_id)
            with pytest.raises(HTTPException) as e:
                budget_scenarios.preview_forecast_route(
                    company_id, sc.id, request={"assumptions": [{"forecast_year": 2026}]}, user_id=USER, db=db)
            assert e.value.status_code == 400
            with pytest.raises(HTTPException) as e:
                budget_scenarios.preview_forecast_route(
                    company_id, sc.id, request={"assumptions": rows}, user_id="someone-else", db=db)
            assert e.value.status_code == 404
    finally:
        engine.dispose()
```

- [ ] **Step 2: Eseguire, vedere fallire** — `backend/venv/bin/python -m pytest tests/test_forecast_preview.py -v` → FAIL, `preview_forecast_route` assente.

- [ ] **Step 3: Servizio**

```python
# backend/app/services/forecast_preview_service.py
"""Anteprima del previsionale: stesse righe del bulk, stesso motore, nessuna scrittura."""
from decimal import Decimal
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.services.assumptions_service import build_assumption_row
from calculations.forecast_engine import ForecastEngine, load_forecast_source


def _validate(assumptions_list: List[Dict[str, Any]], base_year: int) -> None:
    if not assumptions_list:
        raise ValueError("At least one assumption record is required")
    years = []
    for a in assumptions_list:
        if "forecast_year" not in a:
            raise ValueError("Each assumption must have a forecast_year")
        if a["forecast_year"] <= base_year:
            raise ValueError(f"Forecast year {a['forecast_year']} must be greater than base year {base_year}")
        years.append(a["forecast_year"])
    if len(years) != len(set(years)):
        raise ValueError("Duplicate forecast years found in assumptions list")


def _floats(d: Dict[str, Any]) -> Dict[str, Any]:
    return {k: (float(v) if isinstance(v, Decimal) else v) for k, v in d.items()}


def preview_forecast(db: Session, scenario_id: int, assumptions_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    source = load_forecast_source(db, scenario_id)          # ValueError -> 400 nella route
    _validate(assumptions_list, source.scenario.base_year)
    rows = sorted(
        (build_assumption_row(scenario_id, a) for a in assumptions_list),
        key=lambda r: r.forecast_year,
    )
    # Le righe sono transitorie: MAI db.add. Il motore le legge con getattr.
    computation = ForecastEngine(db).compute_forecast(source, rows, stop_on_error=False)
    return {
        "scenario_id": scenario_id,
        "base_year": source.scenario.base_year,
        "forecast_years": [
            {"year": y.year, "income_statement": _floats(y.income_statement),
             "balance_sheet": _floats(y.balance_sheet), "details": _floats(y.details)}
            for y in computation.years
        ],
        "error": None if computation.error is None
                 else {"year": computation.error.year, "message": computation.error.message},
    }
```

- [ ] **Step 4: Schema e route**

In `schemas/forecast.py`:

```python
class ForecastPreviewError(BaseModel):
    year: Optional[int] = None
    message: str

class ForecastPreviewYear(BaseModel):
    year: int
    income_statement: Dict[str, Any]
    balance_sheet: Dict[str, Any]
    details: Dict[str, Any]

class ForecastPreviewResponse(BaseModel):
    scenario_id: int
    base_year: int
    forecast_years: List[ForecastPreviewYear]
    error: Optional[ForecastPreviewError] = None
```

In `budget_scenarios.py`, dopo `generate_forecasts`:

```python
@router.post(
    "/companies/{company_id}/scenarios/{scenario_id}/preview",
    response_model=forecast_schemas.ForecastPreviewResponse,
    summary="Anteprima del previsionale dalle ipotesi nel corpo, senza salvare",
)
def preview_forecast_route(
    company_id: int,
    scenario_id: int,
    request: Any = Body(...),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Stesso corpo del bulk (`{"assumptions": [...]}`), nessuna scrittura.
    Risponde 200 anche se il motore si ferma: leggere `error`, non lo status."""
    from app.services import forecast_preview_service
    validate_scenario_belongs_to_company(scenario_id, company_id, user_id, db)
    request_data = request if isinstance(request, dict) else request.model_dump()
    try:
        return forecast_preview_service.preview_forecast(
            db, scenario_id, request_data.get("assumptions", []))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
```

`validate_scenario_belongs_to_company` alza già 404 per l'azienda altrui (`validate_company_owned_by_user`).

- [ ] **Step 5: Verificare** — `backend/venv/bin/python -m pytest tests/test_forecast_preview.py tests/test_forecast_compute.py tests/test_http_full_cycle.py -v` → PASS. Poi a mano: server su, `curl -X POST localhost:8000/api/v1/companies/1/scenarios/1/preview -H 'Content-Type: application/json' -d '{"assumptions":[{"forecast_year":2026,"revenue_growth_pct":5}]}'` (con `DEV_USER_ID`) e leggere la risposta.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/forecast_preview_service.py backend/app/schemas/forecast.py backend/app/api/v1/budget_scenarios.py tests/test_forecast_preview.py
git commit -m "feat(api): POST /scenarios/{id}/preview, anteprima del previsionale senza scrittura"
```

---

### Task 10: `previewForecast` in `lib/api.ts` e `hooks/use-forecast-preview.ts`

**Modello:** sonnet · **Ondata:** B (dopo 3 e 5)

**Files:**
- Modify: `frontend/lib/api.ts` (dopo `bulkUpsertAssumptions`, `:686`)
- Create: `frontend/hooks/use-forecast-preview.ts`

**Interfaces:**
- Produces:

```ts
export const previewForecast = async (companyId: number, scenarioId: number,
  rows: Record<string, unknown>[], signal?: AbortSignal): Promise<ForecastPreviewResponse>
export function useForecastPreview(args: { companyId: number; scenarioId: number | null;
  rows: Record<string, unknown>[] | null; enabled: boolean }): PreviewState
```

- [ ] **Step 1: `lib/api.ts`**

```ts
// Anteprima: stesso corpo del bulk, nessuna scrittura lato server. `signal`
// annulla la chiamata precedente quando l'utente continua a digitare.
export const previewForecast = async (
  companyId: number,
  scenarioId: number,
  rows: Record<string, unknown>[],
  signal?: AbortSignal
): Promise<import('@/types/api').ForecastPreviewResponse> => {
  const { data } = await api.post<import('@/types/api').ForecastPreviewResponse>(
    `/companies/${companyId}/scenarios/${scenarioId}/preview`,
    { assumptions: rows },
    { signal }
  );
  return data;
};
```

- [ ] **Step 2: L'hook**

```ts
// frontend/hooks/use-forecast-preview.ts
"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import axios from "axios";
import { previewForecast } from "@/lib/api";
import { PreviewSequencer, createDebouncedRunner } from "@/lib/budget-preview-queue";
import { getErrorMessage } from "@/lib/utils";
import type { PreviewState } from "@/components/budget/wizard/types";

const DELAY_MS = 400;

export function useForecastPreview({ companyId, scenarioId, rows, enabled }: {
  companyId: number; scenarioId: number | null; rows: Record<string, unknown>[] | null; enabled: boolean;
}): PreviewState {
  const [state, setState] = useState<PreviewState>({ data: null, error: null, loading: false });
  const seq = useRef(new PreviewSequencer());
  const runner = useMemo(() => createDebouncedRunner<Record<string, unknown>[]>((payload, signal) => {
    if (scenarioId === null) return;
    const mine = seq.current.next();
    setState((s) => ({ ...s, loading: true }));
    previewForecast(companyId, scenarioId, payload, signal)
      .then((data) => { if (seq.current.isCurrent(mine)) setState({ data, error: null, loading: false }); })
      .catch((err) => {
        if (axios.isCancel(err) || !seq.current.isCurrent(mine)) return;
        setState((s) => ({ ...s, error: getErrorMessage(err, "Anteprima non disponibile"), loading: false }));
      });
  }, DELAY_MS), [companyId, scenarioId]);

  // `rows` cambia identita' a ogni modifica: e' il segnale voluto. Serializzato
  // per non ripartire quando la mappa e' identica ma l'oggetto e' nuovo.
  const key = rows ? JSON.stringify(rows) : null;
  useEffect(() => {
    if (!enabled || !rows || scenarioId === null) return;
    runner.push(rows);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, enabled, scenarioId, runner]);
  useEffect(() => () => runner.cancel(), [runner]);
  return state;
}
```

- [ ] **Step 3: Verificare** — `npx tsc --noEmit` → PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/api.ts frontend/hooks/use-forecast-preview.ts
git commit -m "feat(budget): client dell'anteprima con debounce e annullamento"
```

---

### Task 11: `StepScenario` e `StepFatturato`

**Modello:** sonnet · **Ondata:** B (dopo 3, 4, 6, 8)

**Files:**
- Create: `frontend/components/budget/wizard/steps/StepScenario.tsx`, `steps/StepFatturato.tsx`

**Interfaces:**
- Consumes: `StepProps`, `YearInputTable`, `PreviewPanel` (Task 8); `rowsFatturato` (Task 4); `trendAssumptions`, `TREND_ITEMS`, `calculateTrend`, `blendedRate` (Task 6); `baseYearNote`, `forecastYearsFor` (`lib/budget-horizon`).
- Produces: `StepScenario(props: StepProps & { name; setName; description; setDescription; isActive; setIsActive; numYears; setNumYears; notaAnnoBase; isNew; inflation; setInflation })`, `StepFatturato(props: StepProps)`.

- [ ] **Step 1: `StepScenario`**

Colonna sinistra, due `Card`:
1. «Informazioni»: `Input` nome, `Input` disabilitato «{baseYear} · bilancio annuale importato» + `notaAnnoBase` sotto, `Textarea` descrizione, `Checkbox` «Scenario attivo», e l'orizzonte: due `Button variant={numYears===3?"default":"outline"}` «3 anni» / «5 anni» più un `Input type="number" min=1 max=5` per gli altri valori (stessa logica anti-rimbalzo di `page.tsx:1308-1338`: testo locale mentre ha il fuoco). Nota sotto: «Le ipotesi degli anni oltre l'orizzonte restano salvate ma non producono proiezione».
2. «Punto di partenza»: `Input` inflazione (`inflation`), tabella delle `TREND_ITEMS` con `calculateTrend` sugli ultimi due `historicalYears` e i tassi `blendedRate` per anno (la tabella dell'attuale `AutoGeneratorCard`). Comportamento della spec §4.1:

```tsx
  // Scenario nuovo: precompila UNA volta, appena idratato.
  const seeded = useRef(false);
  useEffect(() => {
    if (!isNew || seeded.current || historicalYears.length < 2) return;
    seeded.current = true;
    const t = trendAssumptions(historicalYears, forecastYears, historical, inflation);
    for (const [year, fields] of Object.entries(t))
      for (const [f, v] of Object.entries(fields)) update(Number(year), f, v);
  }, [isNew, historicalYears, forecastYears, historical, inflation, update]);
```

Pulsante «Riparti dalla tendenza» (`AlertDialog` di conferma che elenca le righe delle `TREND_ITEMS` che cambieranno) → stessa applicazione. Anteprima a destra: `PreviewPanel` titolo «Bilancio {baseYear} · anno base» con righe costruite dagli `historicalYears` (ricavi, incidenza % di ce05/ce06/ce08, MOL = ce01+ce04−ce05−ce06−ce07−ce08−ce12, giorni `computeAutoDays` per dso/dio/dpo): qui `years` sono gli anni storici e non c'è chiamata di anteprima.

- [ ] **Step 2: `StepFatturato`**

```tsx
export function StepFatturato(p: StepProps) {
  const baseInc = p.historical[p.baseYear]?.income;
  const rows = useMemo(() => (baseInc && p.preview.data ? rowsFatturato(baseInc, p.preview.data.forecast_years) : []),
    [baseInc, p.preview.data]);
  return (
    <div className="grid gap-5 lg:grid-cols-[1.15fr_1fr] items-start">
      <Card>
        <CardHeader><CardTitle className="text-base">Variazione % sull'anno precedente</CardTitle></CardHeader>
        <CardContent>
          <YearInputTable forecastYears={p.forecastYears} baseYear={p.baseYear} assumptions={p.assumptions} update={p.update}
            rows={[
              { field: "revenue_growth_pct", label: "Ricavi delle vendite", baseLabel: formatCurrency(num(baseInc?.ce01_ricavi_vendite)) },
              { field: "other_revenue_growth_pct", label: "Altri ricavi e proventi", baseLabel: formatCurrency(num(baseInc?.ce04_altri_ricavi)) },
            ]} />
          <p className="mt-2 text-xs text-muted-foreground">Le percentuali si applicano all'anno precedente, non al {p.baseYear}.</p>
        </CardContent>
      </Card>
      <div className="lg:sticky lg:top-4">
        <PreviewPanel title="Ricavi proiettati" baseYear={p.baseYear} years={p.forecastYears} rows={rows}
          loading={p.preview.loading} error={p.preview.error}>
          <RevenueBars base={num(baseInc?.ce01_ricavi_vendite)} years={p.preview.data?.forecast_years ?? []} />
        </PreviewPanel>
      </div>
    </div>
  );
}
```

`RevenueBars`: un `<svg viewBox="0 0 400 56" preserveAspectRatio="none">` con un `<rect>` per valore (base in `fill-muted-foreground/60`, anni in `fill-primary`), altezza proporzionale su `min*0.9 … max*1.05`. Nessuna libreria.

- [ ] **Step 3: Verificare** — `npx tsc --noEmit` → PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/components/budget/wizard/steps/StepScenario.tsx frontend/components/budget/wizard/steps/StepFatturato.tsx
git commit -m "feat(budget): passi Scenario e Fatturato del wizard"
```

---

### Task 12: `StepCosti` — slider della quota fissa e tabella a due gruppi

**Modello:** opus · **Ondata:** B (dopo 3, 4, 6, 8)

**Files:**
- Create: `frontend/components/budget/wizard/steps/StepCosti.tsx`

**Interfaces:**
- Consumes: `StepProps`, `YearInputTable`, `PreviewPanel`, `rowsCosti`, `parseFieldValue`.

- [ ] **Step 1: Lo slider scrive tutti gli anni**

```tsx
function fixedShareOf(assumptions: AssumptionsMap, years: number[], field: "fixed_materials_percentage" | "fixed_services_percentage") {
  const vals = years.map((y) => num(assumptions[y]?.[field] ?? 40));
  return { value: vals[0] ?? 40, uneven: vals.some((v) => v !== vals[0]) };
}

function SplitSlider({ label, baseAmount, field, share, uneven, onChange }: {
  label: string; baseAmount: number; field: string; share: number; uneven: boolean; onChange: (v: number) => void;
}) {
  const fixed = baseAmount * share / 100, variable = baseAmount - fixed;
  return (
    <div className="py-3 border-b last:border-b-0">
      <div className="flex items-baseline justify-between gap-3">
        <span className="font-medium">{label}</span>
        <span className="text-muted-foreground tabular-nums">{formatCurrency(baseAmount)}</span>
      </div>
      <div className="mt-1.5 grid grid-cols-[1fr_92px] items-center gap-3">
        <input type="range" min={0} max={100} step={5} value={share} aria-label={`Quota fissa ${label}`}
          className="w-full accent-blue-500" onChange={(e) => onChange(Number(e.target.value))} />
        <div className="flex items-center gap-1">
          <Input type="number" min={0} max={100} className="w-16 text-right" value={share}
            onChange={(e) => onChange(parseFieldValue(field, e.target.value) ?? 0)} />
          <span className="text-[11px] text-muted-foreground">% fissa</span>
        </div>
      </div>
      <div className="mt-2 flex h-7 overflow-hidden rounded text-xs font-medium">
        <div className="flex items-center justify-center bg-blue-100 text-blue-900 dark:bg-blue-900 dark:text-blue-100" style={{ flex: share }}>
          {share > 12 && `Fissa · ${formatCurrency(fixed)}`}
        </div>
        <div className="flex items-center justify-center bg-amber-100 text-amber-900 dark:bg-amber-900 dark:text-amber-100" style={{ flex: 100 - share }}>
          {share < 88 && `Variabile · ${formatCurrency(variable)}`}
        </div>
      </div>
      {uneven && <p className="mt-1 text-xs text-amber-700 dark:text-amber-300">Valori diversi per anno: muovendo lo slider li allinei.</p>}
    </div>
  );
}
```

Nel componente: `onChange={(v) => p.updateAll("fixed_materials_percentage", v)}` (spec §4.3: tutti gli anni).

- [ ] **Step 2: La tabella a due gruppi**

```tsx
const mat = fixedShareOf(p.assumptions, p.forecastYears, "fixed_materials_percentage");
const serv = fixedShareOf(p.assumptions, p.forecastYears, "fixed_services_percentage");
const bMat = num(baseInc?.ce05_materie_prime), bServ = num(baseInc?.ce06_servizi);
const rows = [
  { group: "Costi variabili", swatch: "variable" as const },
  { field: "variable_materials_growth_pct", label: "Materie prime · parte variabile", baseLabel: formatCurrency(bMat * (1 - mat.value / 100)), off: mat.value >= 100 },
  { field: "variable_services_growth_pct", label: "Servizi · parte variabile", baseLabel: formatCurrency(bServ * (1 - serv.value / 100)), off: serv.value >= 100 },
  { group: "Costi fissi", swatch: "fixed" as const },
  { field: "fixed_materials_growth_pct", label: "Materie prime · parte fissa", baseLabel: formatCurrency(bMat * mat.value / 100), off: mat.value <= 0 },
  { field: "fixed_services_growth_pct", label: "Servizi · parte fissa", baseLabel: formatCurrency(bServ * serv.value / 100), off: serv.value <= 0 },
  { field: "personnel_growth_pct", label: "Personale", baseLabel: formatCurrency(num(baseInc?.ce08_costi_personale)) },
  { field: "rent_growth_pct", label: "Godimento beni di terzi", baseLabel: formatCurrency(num(baseInc?.ce07_godimento_beni)) },
];
```

Sopra la tabella: legenda («quota fissa · segue l'inflazione», «quota variabile · segue i ricavi») e il pulsante `variant="ghost" size="sm"` «Allinea le variabili ai ricavi»:

```tsx
const alignToRevenue = () => {
  for (const y of p.forecastYears) {
    const g = num(p.assumptions[y]?.revenue_growth_pct ?? 0);
    p.update(y, "variable_materials_growth_pct", g);
    p.update(y, "variable_services_growth_pct", g);
  }
};
```

Badge «forzato in CE Prev.» accanto all'etichetta di Materie/Servizi quando `p.assumptions[y]?.ce05_override != null` per un qualunque anno (spec §6).

- [ ] **Step 3: L'anteprima**

`PreviewPanel` «Costi principali e margine» con `rowsCosti(baseInc, { materials: mat.value, services: serv.value }, years)`, e come `children`:
- la barra impilata per anno: per ogni anno un `div` flex con due segmenti (`bg-blue-500` per `fissi.value`, `bg-amber-500` per `variabili.value`) e sotto «peso dei fissi: {base%} → {ultimo%}» (calcolato dalle righe `fissi`/`principali`, base e ultimo anno);
- un separatore, l'eyebrow «CON I GIORNI DI PAGAMENTO FERMI AL {baseYear} ({dpo} GG)» dove `dpo` è `details.dpo_applied` del primo anno, e la nota «I giorni medi si regolano al passo 5, Capitale circolante. Qui restano quelli dell'ultimo bilancio per non mescolare le ipotesi». La riga «Debiti verso fornitori stimati» è già nelle righe: `PreviewPanel` la rende in coda; passare `rows.filter(r => r.key !== "fornitori")` alla tabella e rendere quella riga da sola sotto l'eyebrow.

- [ ] **Step 4: Verificare** — `npx tsc --noEmit` → PASS; a mano (dopo il Task 15) slider a 0 e 100 spengono le righe giuste.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/budget/wizard/steps/StepCosti.tsx
git commit -m "feat(budget): passo Costi principali con quota fissa e variabile"
```

---

### Task 13: `StepAltreVociCE` e `StepCircolante`

**Modello:** sonnet · **Ondata:** B (dopo 3, 4, 6, 8)

**Files:**
- Create: `steps/StepAltreVociCE.tsx`, `steps/StepCircolante.tsx`

- [ ] **Step 1: `StepAltreVociCE`**

Sinistra: `Card` «Voci minori · variazione %» con `YearInputTable` di una riga (`other_costs_growth_pct`, baseLabel ce12). `Card` «Calcolate dal piano» con `Badge variant="secondary"` «automatico» e tre righe `label / small / valore`: ammortamenti («quote sul {baseYear} più il {depreciation_rate}% dei nuovi investimenti (passo 6)», valore «{ce09 base} → {ce09 ultimo anno dall'anteprima}»), oneri finanziari («sul debito del passo 6», «{ce15 base} → {ce15 ultimo}»), imposte («aliquota del passo 7», `computeEffectiveTaxRate(baseInc)` formattata o «27,9%»). Nota: «Un valore forzato a mano nel CE previsionale vince sempre su queste regole, e resta finché non lo azzeri dal dialogo Ricalcola». Destra: `PreviewPanel` «Conto economico sintetico» con `rowsAltreVociCe`.

- [ ] **Step 2: `StepCircolante`**

Sinistra: `Card` «Giorni medi» con `YearInputTable` di tre righe (`dso_days`/`dio_days`/`dpo_days`, `baseLabel` «{n} gg» da `computeAutoDays(kind, baseInc, baseBs)`, `placeholder: () => \`auto ${n}\``). Nota: «I giorni del {baseYear} sono calcolati sui soli crediti e debiti commerciali, su 360 giorni. Le voci non commerciali (tributari, imposte anticipate) non seguono i ricavi». `Card` «Voci minori dell'attivo e del passivo · variazione %» con `Accordion` (`components/ui/accordion`) chiuso, «Mostra tutte», e dentro `YearInputTable` con le righe: `receivables_long_growth_pct` «Crediti oltre 12 mesi», `sp01_growth_pct` «Crediti verso soci», `sp04_growth_pct` «Immobilizzazioni finanziarie», `sp06e_growth_pct` «Crediti tributari», `sp06f_growth_pct` «Imposte anticipate», `sp08_growth_pct` «Attività finanziarie», `sp10_growth_pct` «Ratei e risconti attivi», `sp14_growth_pct` «Fondi per rischi e oneri», `sp16f_growth_pct` «Debiti previdenziali entro», `sp16g_growth_pct` «Altri debiti entro», `sp17d_growth_pct` «Debiti fornitori oltre», `sp17f_growth_pct` «Debiti previdenziali oltre», `sp17g_growth_pct` «Altri debiti oltre», `sp18_growth_pct` «Ratei e risconti passivi` (baseLabel = importo base della voce, `formatCurrency`), e sotto due `Checkbox`: `previdenza_scales_with_personnel` «Debiti previdenziali scalano col costo del personale», `tfr_accrual_suspended` «TFR versato a INPS/fondi (accantonamento sospeso)» → `p.updateAll(field, checked)`. Destra: `PreviewPanel` «Circolante proiettato» con `rowsCircolante`.

- [ ] **Step 3: Verificare e commit** — `npx tsc --noEmit`; poi:

```bash
git add frontend/components/budget/wizard/steps/StepAltreVociCE.tsx frontend/components/budget/wizard/steps/StepCircolante.tsx
git commit -m "feat(budget): passi Altre voci CE e Capitale circolante"
```

---

### Task 14: `StepPregressoNuovo` e `StepImposte`

**Modello:** sonnet · **Ondata:** B (dopo 3, 4, 6, 7, 8)

**Files:**
- Create: `steps/StepPregressoNuovo.tsx`, `steps/StepImposte.tsx`

**Interfaces:**
- Consumes: `FinancingLoansGrid`, `TaxTemporaryDifferencesGrid` (Task 7, con le loro props attuali: `forecastYears`, `assumptions`, `onUpdate`, `baseYear`, `baseBalance`); `baseBankDebt` (`lib/base-bank-debt`); `rowsPregressoNuovo`, `rowsImposte`, `unfundedFromError`; `computeEffectiveTaxRate` (`components/budget/assumption-rows`).

- [ ] **Step 1: `StepPregressoNuovo`** — layout `grid gap-5 lg:grid-cols-2`.

Colonna sinistra, `Card` «Scadenziamento del pregresso» (`CardDescription` «saldi al 31/12/{baseYear}»), righe `flex justify-between`:
- «Debiti bancari esistenti» / small `{baseBankDebt(baseBs)} · di cui {sp16a} a breve` / `rimborso in <Input number existing_debt_repayment_years> anni` (scrive tutti gli anni: `updateAll`, il motore lo legge da ogni riga);
- «Altri finanziatori» / `{sp16b+sp17b}` / `altri_finanz_repayment_years` idem;
- «Crediti verso clienti al {baseYear}» / `{sp06−sp06e−sp06f}` / `<Badge variant="outline">lotto 2</Badge>` + `Select disabled` «entro l'anno»;
- «Debiti tributari» / `{sp16e+sp17e}` / `<Badge variant="outline">lotto 2</Badge>` + testo «si regola al passo 7».
- Nota: «Con un piano dettagliato in Finanziamenti la durata generica del rimborso viene ignorata: vale il piano».
Sotto, `<FinancingLoansGrid forecastYears baseYear assumptions onUpdate={p.updateFinancingLoans} baseBalance={baseBs} />`.

Colonna destra, `Card` «Generato dal previsionale»: eyebrow «Nuovo finanziamento» + `YearInputTable` con `financing_amount` «Importo €», `financing_duration_years` «Durata (anni)», `financing_interest_rate` «Tasso %» (baseLabel «—»); separatore; eyebrow «Nuovi investimenti» + `YearInputTable` con `tangible_investments`, `intangible_investments`; `Accordion` «Mostra tutte» con `depreciation_rate` «Ammortamento nuovi investimenti materiali %», `depreciation_rate_intangible`, `asset_disposal_nbv` «Cessioni: valore contabile netto €», `asset_disposal_proceeds` «Cessioni: corrispettivo €», `cash_sweep_min_cash` «Cash sweep: cassa minima €», e `Checkbox` `cash_sweep_enabled`. Sotto, `PreviewPanel` «Debito, cassa e PFN» con `rowsPregressoNuovo` e come `children` l'avviso:

```tsx
const unfunded = unfundedFromError(p.preview.data?.error ?? null);
{unfunded
  ? <div className="mt-3 flex gap-2 rounded-md bg-destructive/10 p-3 text-sm text-destructive"><AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
      <div><b>Fabbisogno scoperto nel {unfunded.year}: {formatCurrency(unfunded.amount)}.</b> Il previsionale non verrà generato finché non lo copri: un nuovo finanziamento, meno investimenti, o un rimborso più lungo del pregresso.</div></div>
  : p.preview.data && <div className="mt-3 flex gap-2 rounded-md bg-muted p-3 text-sm"><Check className="h-4 w-4 shrink-0 mt-0.5" /> La cassa resta positiva in tutti gli anni: nessun fabbisogno da coprire.</div>}
```

- [ ] **Step 2: `StepImposte`**

Sinistra: `Card` «Aliquota» con tre righe: «Aliquota effettiva {baseYear}» / small «imposte / utile ante imposte» / `{computeEffectiveTaxRate(baseInc)}%` + `Badge` «usata dal piano»; «Aliquota forzata» / small «vuota = usa l'effettiva» / `Input number` legato a `tax_rate` di tutti gli anni (`updateAll`; valore vuoto → **27.9**, perché la colonna è NOT NULL e 27,9 è il default che ogni schermata manda, CLAUDE.md › Tax rate; la UI mostra vuoto quando il valore è 27.9); «Acconti versati nell'anno» / `YearInputTable` con `tax_advances_paid`. `Card` «Differenze temporanee» con `<TaxTemporaryDifferencesGrid forecastYears assumptions onUpdate={p.updateTemporaryDifferences} />`. `Card` «Pagamento dei debiti tributari» con `Badge` «lotto 2»: `YearInputTable` con `sp16e_growth_pct` «Debiti tributari entro %», `sp17e_growth_pct` «Debiti tributari oltre %»; due righe `Select disabled` «Correnti · anno successivo», «Rateizzati · 3 rate annuali» con badge; nota «Oggi il motore muove la posizione tributaria come precedente + imposte dell'anno − acconti. La divisione fra correnti e rateizzati entra con l'estensione del motore».
Destra: `PreviewPanel` «Imposte e risultato netto» con `rowsImposte`. Sotto la card, il testo del passo finale: «È l'ultimo passo: il previsionale completo si legge e si ritocca nelle tab CE Prev. e SP Prev.».

- [ ] **Step 3: Verificare e commit** — `npx tsc --noEmit`; poi:

```bash
git add frontend/components/budget/wizard/steps/StepPregressoNuovo.tsx frontend/components/budget/wizard/steps/StepImposte.tsx
git commit -m "feat(budget): passi Pregresso e nuovo, Imposte"
```

---

## Ondata C

### Task 15: `BudgetWizard` e il cablaggio in `/budget`

**Modello:** opus · **Ondata:** C (dopo tutti)

**Files:**
- Create: `frontend/components/budget/wizard/BudgetWizard.tsx`
- Modify: `frontend/app/budget/page.tsx:281-304` (render), e le righe di `handleScenarioSaved` `:148-155`

**Interfaces:**
- Consumes: tutto quanto sopra. `useScenarioAssumptions` (Task 7), `useForecastPreview` (Task 10), `WizardRail`, i sette passi, `usePrimaryAction`, `primaryLabel`/`nextStep`/`prevStep`/`stepStorageKey`/`stepForErrorMessage` (Task 3), `bulkUpsertAssumptions`, `updateBudgetScenario`, `useInvalidateScenarios`, `useInvalidateAnalysis`, `useRouter`.
- Produces: `BudgetWizard(props: { companyId: number; years: number[]; scenario: BudgetScenario; onCancel: () => void })`.

- [ ] **Step 1: Stato e navigazione**

```tsx
"use client";
export function BudgetWizard({ companyId, years, scenario, onCancel }: Props) {
  const router = useRouter();
  const { pratica } = usePratica();
  const invalidateScenarios = useInvalidateScenarios();
  const invalidateAnalysis = useInvalidateAnalysis();
  const s = useScenarioAssumptions({ companyId, years, scenario });
  const [name, setName] = useState(scenario.name);
  const [description, setDescription] = useState(scenario.description ?? "");
  const [isActive, setIsActive] = useState(scenario.is_active === 1);
  const [inflation, setInflation] = useState(2);
  const [step, setStep] = useState<WizardStepKey>("scenario");
  const [visited, setVisited] = useState<Set<WizardStepKey>>(new Set(["scenario"]));
  const [saving, setSaving] = useState(false);

  // Passo ricordato per scenario: letto in un effetto, mai nell'inizializzatore.
  useEffect(() => {
    try {
      const raw = localStorage.getItem(stepStorageKey(scenario.id));
      if (raw && WIZARD_STEPS.some((w) => w.key === raw)) setStep(raw as WizardStepKey);
    } catch { /* storage non disponibile */ }
  }, [scenario.id]);
  useEffect(() => {
    try { localStorage.setItem(stepStorageKey(scenario.id), step); } catch { /* idem */ }
    setVisited((v) => (v.has(step) ? v : new Set(v).add(step)));
    window.scrollTo({ top: 0 });
  }, [step, scenario.id]);
```

- [ ] **Step 2: Righe per l'anteprima e per il salvataggio — sempre dalla mappa idratata**

```tsx
  const rows = useMemo(
    () => (s.idratato ? s.forecastYears.filter((y) => s.assumptions[y]).map((y) => ({
      ...s.assumptions[y], scenario_id: scenario.id, forecast_year: y })) : null),
    [s.idratato, s.forecastYears, s.assumptions, scenario.id],
  );
  const preview = useForecastPreview({ companyId, scenarioId: scenario.id, rows, enabled: step !== "scenario" });
```

- [ ] **Step 3: Salvataggio (spec §4.7 e §6)**

```tsx
  const save = useCallback(async () => {
    if (!s.idratato || !rows) { toast.error("Ipotesi non ancora caricate: attendi, o ricarica la pagina"); return; }
    if (!name.trim()) { toast.error("Il nome dello scenario è obbligatorio"); return; }
    setSaving(true);
    try {
      await updateBudgetScenario(companyId, scenario.id, { name, description, is_active: isActive ? 1 : 0 });
      const result = await bulkUpsertAssumptions(companyId, scenario.id, { assumptions: rows, auto_generate: true });
      if (result.forecast_generated === false) {
        // 200 con previsionale rifiutato: la ragione e' in message (CLAUDE.md).
        const msg = result.message ?? "Previsionale non generato";
        toast.error(msg);
        setStep(stepForErrorMessage(msg));
        return;
      }
      invalidateScenarios(companyId);
      invalidateAnalysis(companyId, scenario.id);
      toast.success("Previsionale calcolato");
      router.push("/forecast/income");
    } catch (err) {
      toast.error(getErrorMessage(err, "Impossibile salvare le ipotesi"));
    } finally {
      setSaving(false);
    }
  }, [s.idratato, rows, name, description, isActive, companyId, scenario.id, invalidateScenarios, invalidateAnalysis, router]);

  const goNext = useCallback(() => { const n = nextStep(step); if (n) setStep(n); else void save(); }, [step, save]);
  usePrimaryAction({
    label: pratica ? primaryLabel(step) : null,
    onClick: goNext,
    disabled: saving || !s.idratato,
    reason: saving ? "Calcolo in corso" : !s.idratato ? "Lettura delle ipotesi salvate in corso" : null,
  });
```

Controllare la firma di `useInvalidateAnalysis` in `hooks/use-queries.ts` e adeguare la chiamata.

- [ ] **Step 4: Render**

```tsx
  const stepProps: StepProps = { companyId, scenarioId: scenario.id, baseYear: s.baseYear, forecastYears: s.forecastYears,
    assumptions: s.assumptions, historical: s.historicalData, historicalYears: s.historicalYears, preview,
    update: s.updateAssumption, updateAll: s.updateAll, updateFinancingLoans: s.updateFinancingLoans,
    updateTemporaryDifferences: s.updateTemporaryDifferences };
  const active = WIZARD_STEPS.find((w) => w.key === step)!;
  return (
    <div className="pb-24">
      <WizardRail active={step} visited={visited} horizon={s.numYears} baseYear={s.baseYear} onGo={setStep} />
      <div className="mb-4"><h1 className="text-xl font-semibold">{active.title}</h1><p className="text-sm text-muted-foreground">{LEAD[step]}</p></div>
      {step === "scenario" && <StepScenario {...stepProps} name={name} setName={setName} description={description} setDescription={setDescription}
        isActive={isActive} setIsActive={setIsActive} numYears={s.numYears} setNumYears={s.setNumYears} notaAnnoBase={s.notaAnnoBase}
        isNew={s.isNew} inflation={inflation} setInflation={setInflation} />}
      {step === "fatturato" && <StepFatturato {...stepProps} />}
      {step === "costi" && <StepCosti {...stepProps} />}
      {step === "altre-voci-ce" && <StepAltreVociCE {...stepProps} />}
      {step === "circolante" && <StepCircolante {...stepProps} />}
      {step === "pregresso-nuovo" && <StepPregressoNuovo {...stepProps} />}
      {step === "imposte" && <StepImposte {...stepProps} />}
      <div className="fixed inset-x-0 bottom-0 z-10 flex items-center gap-3 border-t bg-background px-6 py-2.5">
        <span className="mr-auto text-xs text-muted-foreground">
          {step === "imposte" ? <>Passo 7 di 7 · dopo il calcolo vai in <b>CE Prev.</b> e <b>SP Prev.</b> per i correttivi finali</> : `Passo ${active.n} di 7 · ${active.title}`}
        </span>
        <Button variant="outline" onClick={onCancel}>Annulla</Button>
        <Button variant="outline" disabled={!prevStep(step)} onClick={() => { const p = prevStep(step); if (p) setStep(p); }}>Indietro</Button>
        <Button onClick={goNext} disabled={saving || !s.idratato}>{saving ? <Loader2 className="h-4 w-4 animate-spin" /> : primaryLabel(step)}</Button>
      </div>
    </div>
  );
}
```

`LEAD` è la mappa passo → sottotitolo, testi del prototipo (`docs/superpowers/specs/2026-09-08-percorso-ipotesi-budget-prototipo.html`, i `<p class="lead">`).

- [ ] **Step 5: Cablaggio in `page.tsx`**

Nel ramo di modifica (`:291-303`):

```tsx
      ) : startupMode ? (
        <ScenarioFormStartup ...props di oggi... />
      ) : editingScenario ? (
        <BudgetWizard companyId={selectedCompanyId} years={years} scenario={editingScenario}
          onCancel={() => { setEditingScenario(null); setActiveTab("list"); }} />
      ) : null}
```

`editingScenario` è sempre valorizzato fuori dallo startup (la creazione manuale è disattivata: `:274-280`), quindi `BudgetWizard` riceve uno `scenario` non nullo. `handleScenarioSaved` resta per lo startup.

- [ ] **Step 6: Verificare**

`npx tsc --noEmit && npx vitest run` → PASS. A mano, con i server accesi e il backend **riavviato** (motore modificato): aprire una pratica con scenario, entrare in Budget, percorrere i sette passi, cambiare i ricavi al passo 2 e vedere la tabella muoversi entro mezzo secondo; passo 3 slider; passo 6 investimenti fuori scala → avviso rosso; passo 7 «Salva e calcola previsionale» → atterraggio su CE Prev. con i numeri dell'anteprima. Riaprire: il passo ricordato è quello lasciato. Fare un override su CE Prev., tornare, salvare: l'override sopravvive (badge al passo 3).

- [ ] **Step 7: Commit**

```bash
git add frontend/components/budget/wizard/BudgetWizard.tsx frontend/app/budget/page.tsx
git commit -m "feat(budget): il percorso a sette passi sostituisce la tab Ipotesi per gli scenari da bilancio"
```

---

## Ondata D

### Task 16: Documentazione

**Modello:** haiku · **Ondata:** D

**Files:**
- Modify: `CLAUDE.md` (Quick Reference › Budget workflow; Invarianti › Previsionale), `docs/budget/API-PREVISIONALE.md`, `docs/frontend/PRATICA-PERCORSO.md`, `docs/superpowers/specs/2026-08-31-ipotesi-budget-mockup.md` (stato), `.claude/agents/collaudatore.md`

- [ ] **Step 1: CLAUDE.md** — nel workflow budget aggiungere `POST /scenarios/{id}/preview` (anteprima, non scrive) fra le assumptions e l'analysis; in «Invarianti › Previsionale» due voci:
  - «**`POST /preview` non scrive nulla e risponde 200 anche a un piano che si ferma**: leggere `error`, non lo status. Gli anni in `forecast_years` sono quelli calcolati prima dell'errore.»
  - «**Lo slider della quota fissa scrive tutti gli anni di piano** (`fixed_*_percentage`): il modello è per anno, l'interfaccia no. Uno scenario con valori diversi fra anni mostra un avviso e viene allineato al primo tocco.»
- [ ] **Step 2: API-PREVISIONALE.md** — sezione «Anteprima» con corpo, risposta (copiare l'esempio dalla spec §5.1), le sette chiavi di `details`, e la frase «bulk e anteprima condividono `build_assumption_row`».
- [ ] **Step 3: PRATICA-PERCORSO.md** — la vista Budget descritta come sette passi con la tabella campo → passo (da `STEP_FIELDS`).
- [ ] **Step 4: mockup 2026-08-31** — stato «superato dalla spec 2026-09-08». **collaudatore.md** — fra i terreni: il percorso a sette passi e la corrispondenza fra anteprima e CE Prev./SP Prev. dopo il salvataggio.
- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md docs/budget/API-PREVISIONALE.md docs/frontend/PRATICA-PERCORSO.md docs/superpowers/specs/2026-08-31-ipotesi-budget-mockup.md .claude/agents/collaudatore.md
git commit -m "docs(budget): anteprima del previsionale e percorso a sette passi"
```

---

### Task 17: Collaudo con browser reale

**Modello:** agente `collaudatore` · **Ondata:** D

- [ ] **Step 1:** Dev server accesi (backend da `backend/` con `DEV_USER_ID=dev-user-001`, riavviato dopo le modifiche a `calculations/`; frontend `npm run dev`). Dispacciare il collaudatore con il perimetro della spec §8 «A mano»: scenario esistente riaperto → stessi valori; salva senza modifiche → `ForecastYear` identico (confronto via `/analysis` prima/dopo); slider 0/100; fabbisogno scoperto al passo 6 e ritorno al passo 6 dal salvataggio; override su CE Prev. sopravvive; passo ricordato al refresh; layout a 1100px.
- [ ] **Step 2:** Per ogni rilievo riproducibile: correggere, test se il difetto è in un modulo puro, commit `fix(budget): …`.
- [ ] **Step 3:** Merge del branch su `main` (finishing-a-development-branch).
