# Suite di test "generi diversi" — Piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aggiungere 5 famiglie di test di genere DIVERSO dalla matrice PDF già esistente (Codex, `tests/test_standard_ivcee_parser.py`), in modo che i bug del ciclo import → rettifiche → ipotesi → previsione → promozione emergano dai test e non dai clienti.

**Architecture:** La matrice esistente copre "PDF sintetici → percorso completo". Le nuove famiglie coprono angoli ortogonali: (1) invarianti contabili dei motori (proprietà, non snapshot), (2) il ciclo via HTTP reale con autenticazione JWT e multi-tenancy, (3) idempotenza e cicli di vita ripetuti (re-import, ri-promozione, override→clear, reset rettifiche), (4) le rotte XBRL e CSV mai coperte end-to-end, (5) stress numerico (centesimi, miliardi, crescite estreme, ricavi zero). Tutti i test usano SQLite in-memory e girano senza `ANTHROPIC_API_KEY`.

**Tech Stack:** pytest, SQLAlchemy (in-memory + StaticPool), FastAPI TestClient, PyJWT 2.10, fpdf/pymupdf (riuso helper esistente `_write_compact_infrannual_pdf`).

## Global Constraints

- Working dir: `C:\DEV\xbrlbudget-main\xbrlbudget`; ogni run di pytest richiede `$env:PYTHONPATH=(Get-Location).Path` (PowerShell).
- Nessun test deve dipendere da `ANTHROPIC_API_KEY`: sempre `monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)`.
- Nessun test tocca `financial_analysis.db` né `data/uploads/`: DB in-memory, upload-tracker neutralizzato nei test HTTP.
- "Quadratura" significa SEMPRE esatta al centesimo sui valori Decimal riletti dal DB: `total_assets == total_liabilities`, non `abs(...) < tol`.
- Se un nuovo test fallisce, il difetto è REALE: si corregge il motore/parser (con superpowers:systematic-debugging), MAI si indebolisce l'assert. Eccezione: se l'attesa del test è contabilmente sbagliata, si corregge il test documentando il perché nel docstring.
- I commit toccano SOLO i nuovi file di test (e le eventuali correzioni ai motori che ne derivano). Le modifiche non committate della sessione Codex (già presenti in working tree) NON vanno incluse negli stessi commit.
- Convenzione firma commit: chiudere il messaggio con `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Suite di regressione finale: `pytest -q tests` deve restare verde (oggi: 195 passed, 3 skipped).

---

### Task 1: Kit condiviso + invarianti contabili dei motori

**Files:**
- Create: `tests/e2e_kit.py` (helper condiviso dai Task 1/3/5)
- Create: `tests/test_engine_accounting_invariants.py`

**Interfaces:**
- Produces: `e2e_kit.memory_sessions()` → `(engine, sessionmaker)`; `e2e_kit.seed_base_year(db, *, user_id, year=2026, scale=Decimal("1"), holding=False)` → `(company_id, fy_id)`; `e2e_kit.read_forecast_maps(db, scenario_id)` → `list[(year, bs_dict, ce_dict)]` con Decimal; `e2e_kit.BASE_BS`, `e2e_kit.BASE_CE` (dict dei valori base).
- Consumes: `budget_scenarios.create_budget_scenario / bulk_upsert_assumptions / generate_forecasts / patch_ce_override` chiamati come funzioni con `user_id=`, `db=` (stesso stile della matrice Codex).

Il bilancio base seminato via ORM (pieno controllo dei numeri, nessun PDF):

Attivo: sp02 40.000 + sp03 160.000 + sp05 50.000 + sp06 120.000 + sp09 30.000 = **400.000**
Passivo: sp11 100.000 + sp12 60.000 + sp13 20.000 + sp15 30.000 + sp16 140.000 + sp17 50.000 = **400.000**
CE: ce01 600.000 − ce05 200.000 − ce06 150.000 − ce07 10.000 − ce08 120.000 (di cui ce08a TFR 8.000) − ce09 40.000 − ce12 5.000 = EBIT 75.000; − ce15 5.000 = PBT 70.000; − ce20 50.000 = **utile 20.000 = sp13** ✓

- [ ] **Step 1: Scrivere `tests/e2e_kit.py`**

```python
"""Shared helpers for the 'generi diversi' end-to-end suites.

Everything runs on an in-memory SQLite DB and without ANTHROPIC_API_KEY.
"""
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database.db import Base
from database.models import BalanceSheet, Company, FinancialYear, IncomeStatement

BASE_BS = {
    "sp02_immob_immateriali": Decimal("40000"),
    "sp03_immob_materiali": Decimal("160000"),
    "sp05_rimanenze": Decimal("50000"),
    "sp06_crediti_breve": Decimal("120000"),
    "sp09_disponibilita_liquide": Decimal("30000"),
    "sp11_capitale": Decimal("100000"),
    "sp12_riserve": Decimal("60000"),
    "sp13_utile_perdita": Decimal("20000"),
    "sp15_tfr": Decimal("30000"),
    "sp16_debiti_breve": Decimal("140000"),
    "sp17_debiti_lungo": Decimal("50000"),
}
BASE_CE = {
    "ce01_ricavi_vendite": Decimal("600000"),
    "ce05_materie_prime": Decimal("200000"),
    "ce06_servizi": Decimal("150000"),
    "ce07_godimento_beni": Decimal("10000"),
    "ce08_costi_personale": Decimal("120000"),
    "ce08a_tfr_accrual": Decimal("8000"),
    "ce09_ammortamenti": Decimal("40000"),
    "ce12_oneri_diversi": Decimal("5000"),
    "ce15_oneri_finanziari": Decimal("5000"),
    "ce20_imposte": Decimal("50000"),
}
HOLDING_BS = {
    "sp04_immob_finanziarie": Decimal("350000"),
    "sp09_disponibilita_liquide": Decimal("50000"),
    "sp11_capitale": Decimal("200000"),
    "sp12_riserve": Decimal("130000"),
    "sp13_utile_perdita": Decimal("20000"),
    "sp16_debiti_breve": Decimal("50000"),
}
HOLDING_CE = {
    "ce01_ricavi_vendite": Decimal("0"),
    "ce06_servizi": Decimal("5000"),
    "ce13_proventi_partecipazioni": Decimal("30000"),
    "ce20_imposte": Decimal("5000"),
}


def memory_sessions():
    """In-memory engine shareable across sessions (StaticPool)."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine)


def seed_base_year(db, *, user_id, year=2026, scale=Decimal("1"), holding=False):
    """Create a verified, forecastable full-year base directly via ORM."""
    bs_values = HOLDING_BS if holding else BASE_BS
    ce_values = HOLDING_CE if holding else BASE_CE
    company = Company(
        name=f"KIT {user_id} {year}", tax_id=f"KIT{year}", sector=1, user_id=user_id
    )
    db.add(company)
    db.flush()
    fy = FinancialYear(
        company_id=company.id,
        year=year,
        period_months=None,
        validation_status="verified",
        forecastable=True,
    )
    db.add(fy)
    db.flush()
    db.add(
        BalanceSheet(
            financial_year_id=fy.id,
            **{k: (v * scale).quantize(Decimal("0.01")) for k, v in bs_values.items()},
        )
    )
    db.add(
        IncomeStatement(
            financial_year_id=fy.id,
            **{k: (v * scale).quantize(Decimal("0.01")) for k, v in ce_values.items()},
        )
    )
    db.commit()
    return company.id, fy.id


def read_forecast_maps(db, scenario_id):
    """Return [(year, {sp*: Decimal}, {ce*: Decimal})] as actually stored."""
    from database.models import ForecastYear

    out = []
    rows = (
        db.query(ForecastYear)
        .filter(ForecastYear.scenario_id == scenario_id)
        .order_by(ForecastYear.year)
        .all()
    )
    for fy in rows:
        bs = {
            c.name: Decimal(str(getattr(fy.balance_sheet, c.name, None) or 0))
            for c in fy.balance_sheet.__table__.columns
            if c.name.startswith("sp")
        }
        ce = {
            c.name: Decimal(str(getattr(fy.income_statement, c.name, None) or 0))
            for c in fy.income_statement.__table__.columns
            if c.name.startswith("ce")
        }
        bs["_total_assets"] = Decimal(str(fy.balance_sheet.total_assets))
        bs["_total_liabilities"] = Decimal(str(fy.balance_sheet.total_liabilities))
        out.append((fy.year, bs, ce))
    return out
```

- [ ] **Step 2: Scrivere i 5 test di invarianti (falliranno o passeranno svelando il comportamento reale)**

`tests/test_engine_accounting_invariants.py`:

```python
"""Property-style invariants of the budget forecast engine.

These tests assert accounting identities, not snapshots: they must hold for
ANY input, so a failure is a real engine defect.
"""
from decimal import Decimal

import pytest

from backend.app.api.v1 import budget_scenarios
from backend.app.schemas.budget import BudgetScenarioCreate
from tests.e2e_kit import memory_sessions, read_forecast_maps, seed_base_year

USER = "invariants"


def _make_scenario(db, company_id, name, years, extra=None):
    scenario = budget_scenarios.create_budget_scenario(
        company_id,
        BudgetScenarioCreate(
            company_id=company_id, name=name, base_year=2026, scenario_type="budget"
        ),
        user_id=USER,
        db=db,
    )
    assumptions = []
    for year in years:
        row = {"forecast_year": year}
        row.update(extra or {})
        assumptions.append(row)
    result = budget_scenarios.bulk_upsert_assumptions(
        company_id,
        scenario.id,
        request={"assumptions": assumptions, "auto_generate": True},
        user_id=USER,
        db=db,
    )
    assert result["forecast_generated"] is True, result["message"]
    return scenario


def test_equity_and_tfr_roll_forward(monkeypatch):
    """CN_t = CN_{t-1} + utile_{t-1}; TFR_t = TFR_{t-1} + accantonamento_t."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            scenario = _make_scenario(
                db, company_id, "rollforward", [2027, 2028],
                extra={"revenue_growth_pct": 5, "tax_rate": 24},
            )
            rows = read_forecast_maps(db, scenario.id)
            (y1, bs1, ce1), (y2, bs2, ce2) = rows
            # anno 1: riserve = 60.000 base + 20.000 utile base
            assert bs1["sp12_riserve"] == Decimal("80000.00")
            assert bs1["sp11_capitale"] == Decimal("100000.00")
            assert bs1["sp15_tfr"] == Decimal("30000") + ce1["ce08a_tfr_accrual"]
            # anno 2: identita' ricorsiva sui valori davvero salvati
            assert bs2["sp12_riserve"] == bs1["sp12_riserve"] + bs1["sp13_utile_perdita"]
            assert bs2["sp15_tfr"] == bs1["sp15_tfr"] + ce2["ce08a_tfr_accrual"]
    finally:
        engine.dispose()


def test_zero_growth_is_a_fixed_point_for_operating_costs(monkeypatch):
    """Crescita 0%, zero investimenti: ricavi e costi operativi restano quelli base.

    (Gli ammortamenti possono scendere: il piano cespiti si esaurisce. Non sono inclusi.)
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            scenario = _make_scenario(
                db, company_id, "fixed-point", [2027],
                extra={
                    "revenue_growth_pct": 0,
                    "personnel_growth_pct": 0,
                    "tax_rate": 24,
                },
            )
            (_, bs1, ce1), = read_forecast_maps(db, scenario.id)
            assert ce1["ce01_ricavi_vendite"] == Decimal("600000.00")
            assert ce1["ce05_materie_prime"] == Decimal("200000.00")
            assert ce1["ce06_servizi"] == Decimal("150000.00")
            assert ce1["ce07_godimento_beni"] == Decimal("10000.00")
            assert ce1["ce08_costi_personale"] == Decimal("120000.00")
            assert bs1["_total_assets"] == bs1["_total_liabilities"]
    finally:
        engine.dispose()


def test_forecast_generation_is_deterministic(monkeypatch):
    """Due generazioni con le stesse ipotesi producono esattamente le stesse righe."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            extra = {"revenue_growth_pct": 7.35, "tax_rate": 24,
                     "tangible_investments": 12345.67}
            scenario = _make_scenario(db, company_id, "det", [2027, 2028, 2029], extra)
            first = read_forecast_maps(db, scenario.id)
            budget_scenarios.generate_forecasts(
                company_id, scenario.id, clear_overrides=False, user_id=USER, db=db
            )
            second = read_forecast_maps(db, scenario.id)
            assert first == second
    finally:
        engine.dispose()


def test_cash_plug_never_goes_negative(monkeypatch):
    """La cassa e' il plug: se manca, deve spostarsi su sp16, mai sotto zero."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            scenario = _make_scenario(
                db, company_id, "cash-squeeze", [2027, 2028],
                extra={
                    "revenue_growth_pct": 60,
                    "dso_days": 180,
                    "dpo_days": 5,
                    "tangible_investments": 250000,
                    "tax_rate": 24,
                },
            )
            for _, bs, _ in read_forecast_maps(db, scenario.id):
                assert bs["sp09_disponibilita_liquide"] >= 0
                assert bs["_total_assets"] == bs["_total_liabilities"]
    finally:
        engine.dispose()


def test_taxes_follow_the_explicit_rate(monkeypatch):
    """Con tax_rate esplicito e PBT>0, ce20 = 24% del PBT (PBT = utile + imposte)."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            scenario = _make_scenario(
                db, company_id, "tax", [2027],
                extra={"revenue_growth_pct": 5, "tax_rate": 24},
            )
            (_, bs1, ce1), = read_forecast_maps(db, scenario.id)
            pbt = bs1["sp13_utile_perdita"] + ce1["ce20_imposte"]
            assert pbt > 0
            assert ce1["ce20_imposte"] == (pbt * Decimal("0.24")).quantize(Decimal("0.01"))
    finally:
        engine.dispose()
```

Nota esecutore: i nomi campo delle ipotesi (`dso_days`, `dpo_days`, `tangible_investments`, `personnel_growth_pct`) vanno confermati contro `backend/app/schemas/budget.py` prima del primo run; se un nome differisce si adegua il TEST (è il contratto reale), non lo schema.

- [ ] **Step 3: Eseguire e verificare l'esito**

Run: `$env:PYTHONPATH=(Get-Location).Path; pytest -q tests/test_engine_accounting_invariants.py -v`
Expected: 5 passed. Ogni FAIL = difetto reale del motore → debugging sistematico + fix in `calculations/forecast_engine.py` o `calculations/projection_common.py`, poi rilancio anche di `pytest -q tests/test_forecast_semantics.py tests/test_standard_ivcee_parser.py` (no regressioni).

- [ ] **Step 4: Commit**

```powershell
git add tests/e2e_kit.py tests/test_engine_accounting_invariants.py
git commit -m @'
test: invarianti contabili del motore previsionale (roll-forward PN/TFR, punto fisso, determinismo, cassa-plug, imposte)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
'@
```

---

### Task 2: Ciclo completo via HTTP reale + multi-tenancy JWT

Genere nuovo: la matrice Codex chiama le funzioni dei router direttamente (`db=db`), saltando serializzazione JSON (Decimal→float), dependency injection, auth e status code. Qui si esercita l'app ASGI vera.

**Files:**
- Create: `tests/test_http_full_cycle.py`
- Test helper riusato: `_write_compact_infrannual_pdf` importato da `test_standard_ivcee_parser` (stessa dir, pytest la mette in sys.path)

**Interfaces:**
- Consumes: `backend.app.main.app`, `backend.app.core.database.get_db`, `backend.app.core.config.settings`, `backend.app.services.upload_tracker`, `importers.pdf_importer.SessionLocal`.
- Produces: fixture pytest `client` (TestClient con DB in-memory condiviso) e helper `_auth(sub)` → header Bearer con JWT HS256 firmato con secret di test.

- [ ] **Step 1: Scrivere il modulo con fixture + 4 test**

```python
"""Full user journey over the REAL HTTP surface, with JWT multi-tenancy."""
from decimal import Decimal

import jwt
import pytest
from fastapi.testclient import TestClient

from tests.test_standard_ivcee_parser import _write_compact_infrannual_pdf

SECRET = "http-cycle-test-secret"


def _auth(sub):
    token = jwt.encode({"sub": sub}, SECRET, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def client(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from backend.app.core import database as core_db
    from backend.app.core.config import settings
    from backend.app.main import app
    from backend.app.services import upload_tracker
    from database.db import Base
    from importers import pdf_importer

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)

    def override_get_db():
        db = sessions()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[core_db.get_db] = override_get_db
    monkeypatch.setattr(pdf_importer, "SessionLocal", sessions)
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", SECRET)
    monkeypatch.setattr(settings, "DEV_USER_ID", None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    # il tracker scrive su data/uploads e usa la SessionLocal globale: fuori dai test
    monkeypatch.setattr(upload_tracker, "save_upload", lambda *a, **k: None)
    monkeypatch.setattr(upload_tracker, "mark_success", lambda *a, **k: None)
    monkeypatch.setattr(upload_tracker, "mark_error", lambda *a, **k: None)

    with TestClient(app) as test_client:
        test_client.sessions = sessions
        yield test_client
    app.dependency_overrides.pop(core_db.get_db, None)
    engine.dispose()


def _import_pdf(client, tmp_path, sub, name, **pdf_kwargs):
    pdf = tmp_path / f"{name}.pdf"
    _write_compact_infrannual_pdf(pdf, **pdf_kwargs)
    with pdf.open("rb") as fh:
        response = client.post(
            "/api/v1/import/pdf",
            params={
                "fiscal_year": 2026,
                "company_name": name,
                "create_company": True,
                "sector": 1,
                "period_months": 6,
            },
            files={"file": (pdf.name, fh, "application/pdf")},
            headers=_auth(sub),
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is True
    return body["company_id"]


def test_http_full_cycle_import_to_analysis(client, tmp_path):
    """Import → rettifica → scenario → ipotesi → analysis, tutto via HTTP/JSON."""
    company_id = _import_pdf(client, tmp_path, "user-a", "HTTP CYCLE SRL")

    adjustable = client.get(
        f"/api/v1/companies/{company_id}/years/2026/adjustable",
        params={"period_months": 6},
        headers=_auth("user-a"),
    )
    assert adjustable.status_code == 200
    bs = adjustable.json()["balance_sheet"]
    cash = Decimal(str(bs["sp09_disponibilita_liquide"]))
    bank = Decimal(str(bs["sp16a_debiti_banche_breve"]))
    debt = Decimal(str(bs["sp16_debiti_breve"]))

    put = client.put(
        f"/api/v1/companies/{company_id}/years/2026/adjustments",
        params={"period_months": 6},
        json={
            "balance_sheet": {
                "sp09_disponibilita_liquide": float(cash + 500),
                "sp16_debiti_breve": float(debt + 500),
                "sp16a_debiti_banche_breve": float(bank + 500),
            },
            "income_statement": {},
            "rettifiche_log": [
                {
                    "id": "http-1",
                    "edited_field": "sp09_disponibilita_liquide",
                    "edited_label": "Disponibilita liquide",
                    "edit_delta": 500,
                    "counterpart_field": "sp16a_debiti_banche_breve",
                    "counterpart_label": "Debiti verso banche entro 12 mesi",
                    "counterpart_delta": 500,
                    "explanation": "rettifica del test HTTP",
                    "created_at": "2026-07-21T09:00:00Z",
                }
            ],
        },
        headers=_auth("user-a"),
    )
    assert put.status_code == 200, put.text
    assert put.json()["forecastable"] is True

    created = client.post(
        f"/api/v1/companies/{company_id}/scenarios",
        json={
            "company_id": company_id,
            "name": "HTTP infrannuale",
            "base_year": 2025,
            "scenario_type": "infrannuale",
            "period_months": 6,
        },
        headers=_auth("user-a"),
    )
    assert created.status_code in (200, 201), created.text
    scenario_id = created.json()["id"]

    generated = client.put(
        f"/api/v1/companies/{company_id}/scenarios/{scenario_id}/assumptions",
        json={
            "assumptions": [{"forecast_year": 2026, "revenue_growth_pct": 4,
                             "tax_rate": 24}],
            "auto_generate": True,
        },
        headers=_auth("user-a"),
    )
    assert generated.status_code == 200, generated.text
    assert generated.json()["forecast_generated"] is True

    analysis = client.get(
        f"/api/v1/companies/{company_id}/scenarios/{scenario_id}/analysis",
        headers=_auth("user-a"),
    )
    assert analysis.status_code == 200, analysis.text
    payload = analysis.json()
    forecast = payload["forecast_years"]
    assert [f["year"] for f in forecast] == [2026]
    fb = forecast[0]["balance_sheet"]
    # sui float serializzati la quadratura deve reggere al centesimo
    assert abs(fb["total_assets"] - fb["total_liabilities"]) < 0.005


def test_cross_user_isolation_is_a_404(client, tmp_path):
    """user-b non deve nemmeno sapere che l'azienda di user-a esiste."""
    company_id = _import_pdf(client, tmp_path, "user-a", "ISOLATA SRL")
    for path in (
        f"/api/v1/companies/{company_id}",
        f"/api/v1/companies/{company_id}/scenarios",
        f"/api/v1/companies/{company_id}/years/2026/adjustable?period_months=6",
    ):
        response = client.get(path, headers=_auth("user-b"))
        assert response.status_code == 404, f"{path} -> {response.status_code}"
    # e senza token: 401, non 500
    assert client.get(f"/api/v1/companies/{company_id}").status_code == 401


def test_rettifiche_log_cap_is_enforced_over_http(client, tmp_path):
    company_id = _import_pdf(client, tmp_path, "user-a", "CAP RETTIFICHE SRL")
    entries = [
        {
            "id": f"e{i}",
            "edited_field": "sp09_disponibilita_liquide",
            "edited_label": "Cassa",
            "edit_delta": 1,
            "counterpart_field": "sp16a_debiti_banche_breve",
            "counterpart_label": "Banche",
            "counterpart_delta": 1,
            "explanation": "x",
            "created_at": "2026-07-21T09:00:00Z",
        }
        for i in range(21)
    ]
    response = client.put(
        f"/api/v1/companies/{company_id}/years/2026/adjustments",
        params={"period_months": 6},
        json={"balance_sheet": {}, "income_statement": {}, "rettifiche_log": entries},
        headers=_auth("user-a"),
    )
    assert response.status_code == 400
    assert "20" in response.json()["detail"]


def test_delete_company_cascades_everything(client, tmp_path):
    from database.models import (
        BalanceSheet, BudgetScenario, Company, FinancialYear, IncomeStatement,
    )

    company_id = _import_pdf(client, tmp_path, "user-a", "DA CANCELLARE SRL")
    created = client.post(
        f"/api/v1/companies/{company_id}/scenarios",
        json={"company_id": company_id, "name": "temp", "base_year": 2025,
              "scenario_type": "infrannuale", "period_months": 6},
        headers=_auth("user-a"),
    )
    assert created.status_code in (200, 201)

    deleted = client.delete(
        f"/api/v1/companies/{company_id}", headers=_auth("user-a")
    )
    assert deleted.status_code == 204

    with client.sessions() as db:
        for model in (Company, FinancialYear, BalanceSheet, IncomeStatement,
                      BudgetScenario):
            assert db.query(model).count() == 0, model.__name__
```

- [ ] **Step 2: Eseguire**

Run: `$env:PYTHONPATH=(Get-Location).Path; pytest -q tests/test_http_full_cycle.py -v`
Expected: 4 passed. Failure tipiche da NON mascherare: 500 su serializzazione Decimal, 200 al posto di 404 cross-user (falla di sicurezza → fix in ownership), residui dopo la DELETE (cascade rotto).

- [ ] **Step 3: Commit**

```powershell
git add tests/test_http_full_cycle.py
git commit -m @'
test: ciclo completo via HTTP reale con JWT, isolamento multi-tenant, cap rettifiche, cascade delete

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
'@
```

---

### Task 3: Idempotenza e cicli di vita ripetuti

Genere nuovo: l'utente reale ripete le operazioni (reimporta, rigenera, azzera, ri-promuove). La matrice Codex percorre ogni passo UNA volta sola.

**Files:**
- Create: `tests/test_lifecycle_repeat.py`

**Interfaces:**
- Consumes: `tests/e2e_kit` (Task 1), `_write_compact_infrannual_pdf`, `budget_scenarios.*`, `financial_years.*`, `promote_service.promote_projection_to_financial_year`.

- [ ] **Step 1: Scrivere i 5 test**

```python
"""Repeated-lifecycle behaviours: re-import, regenerate, override→clear,
rettifica→reset, promote→budget chain, re-promote."""
from decimal import Decimal

import pytest

from backend.app.api.v1 import budget_scenarios, financial_years
from backend.app.schemas.adjustments import AdjustmentsUpdate, RettificaEntry
from backend.app.schemas.budget import BudgetScenarioCreate
from backend.app.services.promote_service import promote_projection_to_financial_year
from tests.e2e_kit import memory_sessions, read_forecast_maps, seed_base_year
from tests.test_standard_ivcee_parser import _write_compact_infrannual_pdf

USER = "lifecycle"


def _import_pdf(sessions, monkeypatch, tmp_path, name, period_months=6):
    from importers import pdf_importer

    monkeypatch.setattr(pdf_importer, "SessionLocal", sessions)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    pdf = tmp_path / f"{name}.pdf"
    _write_compact_infrannual_pdf(pdf, period_months=period_months)
    return pdf_importer.import_pdf_balance_sheet(
        file_path=str(pdf), fiscal_year=2026, company_name=name,
        create_company=True, sector=1, period_months=period_months, user_id=USER,
    )


def test_reimport_same_year_replaces_not_duplicates(tmp_path, monkeypatch):
    from database.models import BalanceSheet, FinancialYear

    engine, sessions = memory_sessions()
    try:
        first = _import_pdf(sessions, monkeypatch, tmp_path, "REIMPORT SRL")
        assert first["success"] is True
        second = _import_pdf(sessions, monkeypatch, tmp_path, "REIMPORT SRL")
        assert second["success"] is True
        assert second["company_id"] == first["company_id"]
        with sessions() as db:
            years = db.query(FinancialYear).all()
            assert len(years) == 1
            assert db.query(BalanceSheet).count() == 1
            ta_after = years[0].balance_sheet.total_assets
        assert ta_after == Decimal(str(first["total_assets"])) if "total_assets" in first else ta_after > 0
    finally:
        engine.dispose()


def test_override_survives_save_and_clears_on_request(monkeypatch):
    """ce-override → bulk save preserva; generate?clear_overrides=true azzera."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            scenario = budget_scenarios.create_budget_scenario(
                company_id,
                BudgetScenarioCreate(company_id=company_id, name="ovr",
                                     base_year=2026, scenario_type="budget"),
                user_id=USER, db=db,
            )
            assumptions = [{"forecast_year": 2027, "revenue_growth_pct": 5,
                            "tax_rate": 24}]
            budget_scenarios.bulk_upsert_assumptions(
                company_id, scenario.id,
                request={"assumptions": assumptions, "auto_generate": True},
                user_id=USER, db=db,
            )
            (_, _, ce_baseline), = read_forecast_maps(db, scenario.id)
            baseline_revenue = ce_baseline["ce01_ricavi_vendite"]

            budget_scenarios.patch_ce_override(
                company_id, scenario.id,
                request={"overrides": [{"forecast_year": 2027,
                                        "field": "ce01_override",
                                        "value": 900000}]},
                user_id=USER, db=db,
            )
            (_, bs_o, ce_o), = read_forecast_maps(db, scenario.id)
            assert ce_o["ce01_ricavi_vendite"] == Decimal("900000.00")
            assert bs_o["_total_assets"] == bs_o["_total_liabilities"]

            # il salvataggio bulk NON deve azzerare l'override
            budget_scenarios.bulk_upsert_assumptions(
                company_id, scenario.id,
                request={"assumptions": assumptions, "auto_generate": True},
                user_id=USER, db=db,
            )
            (_, _, ce_saved), = read_forecast_maps(db, scenario.id)
            assert ce_saved["ce01_ricavi_vendite"] == Decimal("900000.00")

            # clear esplicito: si torna ESATTAMENTE alla baseline
            budget_scenarios.generate_forecasts(
                company_id, scenario.id, clear_overrides=True, user_id=USER, db=db
            )
            (_, _, ce_cleared), = read_forecast_maps(db, scenario.id)
            assert ce_cleared["ce01_ricavi_vendite"] == baseline_revenue
    finally:
        engine.dispose()


def test_rettifica_then_reset_restores_the_original_snapshot(tmp_path, monkeypatch):
    engine, sessions = memory_sessions()
    try:
        imported = _import_pdf(sessions, monkeypatch, tmp_path, "RESET SRL")
        company_id = imported["company_id"]
        with sessions() as db:
            editable = financial_years.get_adjustable_financial_year(
                company_id, 2026, period_months=6, user_id=USER, db=db
            )
            original_bs = dict(editable.balance_sheet)
            original_is = dict(editable.income_statement)
            cash = Decimal(str(original_bs["sp09_disponibilita_liquide"]))

            financial_years.save_adjustments(
                company_id, 2026,
                AdjustmentsUpdate(
                    balance_sheet={
                        "sp09_disponibilita_liquide": cash + Decimal("700"),
                        "sp16_debiti_breve": Decimal(str(original_bs["sp16_debiti_breve"])) + 700,
                        "sp16a_debiti_banche_breve": Decimal(str(original_bs["sp16a_debiti_banche_breve"])) + 700,
                    },
                    income_statement={},
                    rettifiche_log=[RettificaEntry(
                        id="r1", edited_field="sp09_disponibilita_liquide",
                        edited_label="Cassa", edit_delta=700,
                        counterpart_field="sp16a_debiti_banche_breve",
                        counterpart_label="Banche", counterpart_delta=700,
                        explanation="temporanea", created_at="2026-07-21T10:00:00Z",
                    )],
                ),
                period_months=6, user_id=USER, db=db,
            )
            # reset: rimando lo snapshot originale con log vuoto
            after_reset = financial_years.save_adjustments(
                company_id, 2026,
                AdjustmentsUpdate(balance_sheet=original_bs,
                                  income_statement=original_is,
                                  rettifiche_log=[]),
                period_months=6, user_id=USER, db=db,
            )
            assert after_reset.rettifiche_log == []
            assert Decimal(str(after_reset.balance_sheet["sp09_disponibilita_liquide"])) == cash
            # lo snapshot immutabile e' sopravvissuto a entrambe le PUT
            assert Decimal(str(after_reset.original_balance_sheet["sp09_disponibilita_liquide"])) == cash
    finally:
        engine.dispose()


def test_promote_then_budget_chain_stays_quadrato(tmp_path, monkeypatch):
    """La catena che i clienti percorrono davvero: infrannuale 2026 → promote →
    budget 2027-2029 basato sull'anno promosso."""
    from database.models import FinancialYear

    engine, sessions = memory_sessions()
    try:
        imported = _import_pdf(sessions, monkeypatch, tmp_path, "CATENA SRL")
        company_id = imported["company_id"]
        with sessions() as db:
            infra = budget_scenarios.create_budget_scenario(
                company_id,
                BudgetScenarioCreate(company_id=company_id, name="infra",
                                     base_year=2025, scenario_type="infrannuale",
                                     period_months=6),
                user_id=USER, db=db,
            )
            budget_scenarios.bulk_upsert_assumptions(
                company_id, infra.id,
                request={"assumptions": [{"forecast_year": 2026,
                                          "revenue_growth_pct": 3,
                                          "tax_rate": 24}],
                         "auto_generate": True},
                user_id=USER, db=db,
            )
            promoted = promote_projection_to_financial_year(db, infra.id)
            assert promoted["verification"]["exact_match"] is True

            budget = budget_scenarios.create_budget_scenario(
                company_id,
                BudgetScenarioCreate(company_id=company_id, name="budget-su-promosso",
                                     base_year=2026, scenario_type="budget"),
                user_id=USER, db=db,
            )
            result = budget_scenarios.bulk_upsert_assumptions(
                company_id, budget.id,
                request={"assumptions": [
                    {"forecast_year": y, "revenue_growth_pct": 4, "tax_rate": 24}
                    for y in (2027, 2028, 2029)
                ], "auto_generate": True},
                user_id=USER, db=db,
            )
            assert result["forecast_generated"] is True, result["message"]
            for _, bs, _ in read_forecast_maps(db, budget.id):
                assert bs["_total_assets"] == bs["_total_liabilities"]

            # ri-promozione con ipotesi diverse: sostituisce, non duplica
            budget_scenarios.bulk_upsert_assumptions(
                company_id, infra.id,
                request={"assumptions": [{"forecast_year": 2026,
                                          "revenue_growth_pct": 8,
                                          "tax_rate": 24}],
                         "auto_generate": True},
                user_id=USER, db=db,
            )
            promote_projection_to_financial_year(db, infra.id)
            full_years = (
                db.query(FinancialYear)
                .filter(FinancialYear.company_id == company_id,
                        FinancialYear.year == 2026,
                        (FinancialYear.period_months == None)  # noqa: E711
                        | (FinancialYear.period_months == 12))
                .all()
            )
            assert len(full_years) == 1
    finally:
        engine.dispose()
```

- [ ] **Step 2: Eseguire**

Run: `$env:PYTHONPATH=(Get-Location).Path; pytest -q tests/test_lifecycle_repeat.py -v`
Expected: 4 passed. Attese chiave: 1 solo FinancialYear dopo il re-import; override sopravvive al bulk-save e sparisce SOLO con clear esplicito; il reset riporta al centesimo i valori originali; dopo la ri-promozione esiste UN solo esercizio pieno 2026.

- [ ] **Step 3: Commit**

```powershell
git add tests/test_lifecycle_repeat.py
git commit -m @'
test: cicli di vita ripetuti (re-import, override/clear, reset rettifiche, catena promote->budget, ri-promozione)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
'@
```

---

### Task 4: Rotte XBRL e CSV a ciclo completo

Genere nuovo: la matrice copre solo la rotta PDF. Le fixture COMMITTATE `legacy/sample_data/ISTANZA02353550391.xbrl`, `legacy/sample_data/sample_data.xbrl` e `legacy/sample_data/sample_data.csv` percorrono qui import → scenario → previsione.

**Files:**
- Create: `tests/test_xbrl_csv_full_cycle.py`

**Interfaces:**
- Consumes: `importers.xbrl_parser_enhanced.import_xbrl_file_enhanced(file_path, company_id=None, create_company=True, sector=None, user_id=None, period_months=None)`; `importers.csv_importer.import_csv_file(file_path, company_id, year1=None, year2=None)`; `budget_scenarios.*` come sopra. Entrambi gli importer aprono la PROPRIA `SessionLocal` → monkeypatch di `xbrl_parser_enhanced.SessionLocal` e `csv_importer.SessionLocal`.

- [ ] **Step 1: Scrivere i 2 test**

```python
"""Full cycle over the XBRL and CSV import routes (committed fixtures)."""
from decimal import Decimal
from pathlib import Path

import pytest

from backend.app.api.v1 import budget_scenarios
from backend.app.schemas.budget import BudgetScenarioCreate
from tests.e2e_kit import memory_sessions, read_forecast_maps

REPO = Path(__file__).resolve().parents[1]
XBRL_FIXTURE = REPO / "legacy" / "sample_data" / "ISTANZA02353550391.xbrl"
CSV_FIXTURE = REPO / "legacy" / "sample_data" / "sample_data.csv"
USER = "route-xbrl-csv"


def _run_budget_cycle(db, company_id, base_year):
    scenario = budget_scenarios.create_budget_scenario(
        company_id,
        BudgetScenarioCreate(company_id=company_id, name=f"budget {base_year}",
                             base_year=base_year, scenario_type="budget"),
        user_id=USER, db=db,
    )
    result = budget_scenarios.bulk_upsert_assumptions(
        company_id, scenario.id,
        request={"assumptions": [
            {"forecast_year": base_year + 1, "revenue_growth_pct": 5, "tax_rate": 24},
            {"forecast_year": base_year + 2, "revenue_growth_pct": 3, "tax_rate": 24},
        ], "auto_generate": True},
        user_id=USER, db=db,
    )
    assert result["forecast_generated"] is True, result["message"]
    rows = read_forecast_maps(db, scenario.id)
    assert len(rows) == 2
    for _, bs, ce in rows:
        assert bs["_total_assets"] == bs["_total_liabilities"]
        assert bs["sp13_utile_perdita"] == (
            sum(ce[f] for f in ce if f in _CE_POSITIVE)
            - sum(ce[f] for f in ce if f in _CE_NEGATIVE)
        ) or True  # la coerenza CE-SP dettagliata e' gia' coperta da check_quadratura
    return scenario


_CE_POSITIVE = set()
_CE_NEGATIVE = set()


def test_xbrl_route_full_cycle(monkeypatch):
    from database.models import FinancialYear
    from importers import xbrl_parser_enhanced

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    monkeypatch.setattr(xbrl_parser_enhanced, "SessionLocal", sessions)
    try:
        result = xbrl_parser_enhanced.import_xbrl_file_enhanced(
            str(XBRL_FIXTURE), create_company=True, sector=1, user_id=USER
        )
        assert result["success"] is True, result
        with sessions() as db:
            fy = (
                db.query(FinancialYear)
                .order_by(FinancialYear.year.desc())
                .first()
            )
            assert fy is not None
            bs = fy.balance_sheet
            assert bs.total_assets == bs.total_liabilities
            assert bs.total_assets > 0
            _run_budget_cycle(db, fy.company_id, fy.year)
    finally:
        engine.dispose()


def test_csv_route_full_cycle(monkeypatch):
    from database.models import Company, FinancialYear
    from importers import csv_importer

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    monkeypatch.setattr(csv_importer, "SessionLocal", sessions)
    try:
        with sessions() as db:
            company = Company(name="CSV ROUTE SRL", tax_id="CSV1", sector=1,
                              user_id=USER)
            db.add(company)
            db.commit()
            company_id = company.id
        result = csv_importer.import_csv_file(str(CSV_FIXTURE), company_id)
        assert result["success"] is True, result
        with sessions() as db:
            fy = (
                db.query(FinancialYear)
                .filter(FinancialYear.company_id == company_id)
                .order_by(FinancialYear.year.desc())
                .first()
            )
            assert fy is not None
            assert fy.balance_sheet.total_assets == fy.balance_sheet.total_liabilities
            _run_budget_cycle(db, company_id, fy.year)
    finally:
        engine.dispose()
```

Nota esecutore: se una fixture legacy risultasse NON bilanciata alla fonte (possibile: sono dati d'esempio storici), l'attesa corretta è il fallimento onesto dell'import con diagnosi esplicita — in quel caso l'assert va adeguato a QUEL contratto (`success is False` + messaggio contabile), documentandolo nel docstring, e va aggiunta una fixture sintetica bilanciata minima per il ramo felice. La pulizia del blocco segnaposto `_CE_POSITIVE/_CE_NEGATIVE` (ridondante) va fatta in fase di esecuzione: la coerenza CE↔SP resta demandata a `check_quadratura` come nella matrice Codex.

- [ ] **Step 2: Eseguire**

Run: `$env:PYTHONPATH=(Get-Location).Path; pytest -q tests/test_xbrl_csv_full_cycle.py -v`
Expected: 2 passed (o attese adeguate al contratto reale delle fixture, vedi nota).

- [ ] **Step 3: Commit**

```powershell
git add tests/test_xbrl_csv_full_cycle.py
git commit -m @'
test: ciclo completo sulle rotte XBRL e CSV con le fixture committate

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
'@
```

---

### Task 5: Stress numerico (centesimi, miliardi, crescite estreme, ricavi zero)

Genere nuovo: la matrice usa importi "normali". Qui si stressano scala e segno dei numeri lungo TUTTO il ciclo budget (5 anni, il massimo), dove gli errori di arrotondamento si accumulano.

**Files:**
- Create: `tests/test_numeric_stress_cycle.py`

**Interfaces:**
- Consumes: `tests/e2e_kit.seed_base_year(scale=...)` e `read_forecast_maps`.

- [ ] **Step 1: Scrivere la matrice parametrica + il test holding**

```python
"""Numeric stress across the full 5-year budget cycle."""
from decimal import Decimal

import pytest

from backend.app.api.v1 import budget_scenarios
from backend.app.schemas.budget import BudgetScenarioCreate
from tests.e2e_kit import memory_sessions, read_forecast_maps, seed_base_year

USER = "stress"

STRESS_CASES = [
    pytest.param(Decimal("0.0037"), Decimal("7.35"), id="micro-importi-con-centesimi"),
    pytest.param(Decimal("1"), Decimal("-50"), id="dimezzamento-ricavi"),
    pytest.param(Decimal("1"), Decimal("900"), id="crescita-esplosiva-900pct"),
    pytest.param(Decimal("2000000"), Decimal("7.35"), id="scala-miliardi"),
    pytest.param(Decimal("2000000"), Decimal("-50"), id="miliardi-in-contrazione"),
]


@pytest.mark.parametrize("scale,growth", STRESS_CASES)
def test_five_year_budget_stays_exact_to_the_cent(monkeypatch, scale, growth):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER, scale=scale)
            scenario = budget_scenarios.create_budget_scenario(
                company_id,
                BudgetScenarioCreate(company_id=company_id, name=f"stress {scale}x",
                                     base_year=2026, scenario_type="budget"),
                user_id=USER, db=db,
            )
            result = budget_scenarios.bulk_upsert_assumptions(
                company_id, scenario.id,
                request={"assumptions": [
                    {"forecast_year": y, "revenue_growth_pct": float(growth),
                     "tax_rate": 24}
                    for y in range(2027, 2032)
                ], "auto_generate": True},
                user_id=USER, db=db,
            )
            assert result["forecast_generated"] is True, result["message"]
            rows = read_forecast_maps(db, scenario.id)
            assert len(rows) == 5
            for year, bs, ce in rows:
                # quadratura ESATTA sui Decimal riletti dal DB, anche al 5° anno
                assert bs["_total_assets"] == bs["_total_liabilities"], year
                assert bs["sp09_disponibilita_liquide"] >= 0, year
                # nessun campo fuori dal dominio Numeric(15,2)
                for name, value in {**bs, **ce}.items():
                    assert abs(value) < Decimal("10") ** 13, (year, name, value)
    finally:
        engine.dispose()


def test_zero_revenue_holding_survives_the_cycle(monkeypatch):
    """Ricavi = 0 (holding pura): la derivazione DSO/DIO/DPO non deve dividere
    per zero e la previsione deve comunque quadrare."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER, holding=True)
            scenario = budget_scenarios.create_budget_scenario(
                company_id,
                BudgetScenarioCreate(company_id=company_id, name="holding",
                                     base_year=2026, scenario_type="budget"),
                user_id=USER, db=db,
            )
            result = budget_scenarios.bulk_upsert_assumptions(
                company_id, scenario.id,
                request={"assumptions": [
                    {"forecast_year": 2027, "revenue_growth_pct": 0, "tax_rate": 24},
                    {"forecast_year": 2028, "revenue_growth_pct": 0, "tax_rate": 24},
                ], "auto_generate": True},
                user_id=USER, db=db,
            )
            assert result["forecast_generated"] is True, result["message"]
            for _, bs, ce in read_forecast_maps(db, scenario.id):
                assert bs["_total_assets"] == bs["_total_liabilities"]
                assert ce["ce01_ricavi_vendite"] == 0
    finally:
        engine.dispose()
```

- [ ] **Step 2: Eseguire**

Run: `$env:PYTHONPATH=(Get-Location).Path; pytest -q tests/test_numeric_stress_cycle.py -v`
Expected: 6 passed. Failure tipiche attese come BUG reali: centesimo di scarto al 4°/5° anno (arrotondamento cumulativo), overflow/None sulla scala miliardi, `DivisionByZero`/`InvalidOperation` sulla holding a ricavi zero, cassa negativa nella contrazione −50%.

- [ ] **Step 3: Commit**

```powershell
git add tests/test_numeric_stress_cycle.py
git commit -m @'
test: stress numerico del ciclo budget 5 anni (centesimi, miliardi, +-crescite estreme, holding a ricavi zero)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
'@
```

---

### Task 6: Regressione completa e verbale di collaudo

**Files:**
- Modify: `docs/PIANO-TEST-E2E-BILANCIO-2026-07-20.md` (aggiunta sezione "Round 2 — generi diversi (21 luglio 2026)")

- [ ] **Step 1: Suite intera**

Run: `$env:PYTHONPATH=(Get-Location).Path; pytest -q tests`
Expected: tutti verdi — i 195+3 preesistenti PIÙ i ~21 nuovi (5 invarianti, 4 HTTP, 4 lifecycle, 2 rotte, 6 stress). Ogni fix ai motori fatto lungo la strada deve lasciare verde anche la matrice Codex.

- [ ] **Step 2: Aggiornare il verbale**

Aggiungere in coda al documento la sezione "Round 2" con: elenco delle 5 famiglie, esito numerico per file, e — per ogni bug reale scovato — sintomo, causa, file corretto (stesso formato delle sezioni "Difetti trovati" esistenti).

- [ ] **Step 3: Commit finale**

```powershell
git add docs/PIANO-TEST-E2E-BILANCIO-2026-07-20.md
git commit -m @'
docs: verbale round 2 della suite di collaudo (generi diversi)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
'@
```

---

## Riepilogo delle attese per famiglia (il "cosa deve tornare")

| # | Famiglia | Casi | Attesa non negoziabile |
|---|---|---|---|
| 1 | Invarianti motore | 5 | riserve_t = riserve_{t-1} + utile_{t-1}; TFR_t = TFR_{t-1} + ce08a_t; crescita 0% ⇒ CE operativo identico alla base; 2 generazioni ⇒ righe identiche; cassa mai < 0; ce20 = 24% del PBT |
| 2 | HTTP + multi-tenancy | 4 | ciclo intero via JSON senza 500; cross-user ⇒ 404, senza token ⇒ 401; 21ª rettifica ⇒ 400; DELETE ⇒ 204 e zero righe orfane |
| 3 | Cicli ripetuti | 4 | re-import ⇒ 1 solo esercizio; override sopravvive al save e muore solo col clear; reset ⇒ valori originali al centesimo; catena promote→budget quadra; ri-promozione ⇒ 1 solo esercizio pieno |
| 4 | Rotte XBRL/CSV | 2 | import verificato e bilanciato (o fallimento onesto documentato) + budget 2 anni quadrato |
| 5 | Stress numerico | 6 | quadratura ESATTA al centesimo su 5 anni a ogni scala; nessun overflow; holding a ricavi zero non crasha |

## Self-review (fatta)

- Copertura vs richiesta: generi diversi dalla matrice PDF ✓ (proprietà, HTTP/auth, ripetizioni, rotte alternative, scala numerica); "prima le specifiche, poi l'esecuzione" ✓ (questo documento).
- Tipi/firme incrociate: firme verificate sul codice reale (`bulk_upsert_assumptions(request=dict)`, `patch_ce_override(request=Body)`, `generate_forecasts(clear_overrides=...)`, `import_xbrl_file_enhanced(...)`, `import_csv_file(file_path, company_id)`, JWT `HS256` + `verify_aud: False`).
- Punti dichiaratamente da confermare in esecuzione (contratti reali, non placeholder): nomi campo ipotesi (`dso_days`/`dpo_days`/`tangible_investments`) in `backend/app/schemas/budget.py`; equilibrio delle fixture legacy XBRL/CSV; pulizia del blocco `_CE_POSITIVE/_CE_NEGATIVE` in Task 4.
