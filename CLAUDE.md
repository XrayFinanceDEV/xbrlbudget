# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**XBRL Budget** is an Italian GAAP compliant financial analysis and credit rating system. It analyzes Italian company financial statements, calculates comprehensive financial ratios, and provides credit risk assessments using Altman Z-Score and FGPMI rating models. Includes **intra-year analysis** (situazione infrannuale) for projecting partial-year financials to 12 months.

**Key Domain:** Italian accounting (OIC - Organismo Italiano di Contabilità) with specialized XBRL import for Italian taxonomies.

**Architecture:** The project contains two applications:
- **Modern Stack (Production)**: FastAPI REST API + Next.js 15 frontend
- **Legacy App (Deprecated)**: Streamlit web application in `/legacy` directory

Both applications share the same core modules (`database/`, `calculations/`, `importers/`) and SQLite database.

**Multi-tenancy:** App is embedded as an iframe in Formula Finance. Supabase JWT auth identifies users; all data is scoped per `user_id` on the `Company` model (max 50 companies per user).

## Quick Reference

**Project Root:** `/home/peter/DEV/budget/`

**Key Directories:**
- `backend/` - FastAPI REST API (uses shared modules from root)
- `frontend/` - Next.js 15 React frontend (TypeScript, API client only)
- `database/` - **SHARED** SQLAlchemy ORM models + query helpers (used by both apps)
- `calculations/` - **SHARED** Financial calculators (ratios, Altman, FGPMI, forecasting)
- `importers/` - **SHARED** XBRL, CSV, and PDF parsers
- `pdf_service/` - PDF report generation (EM-Score, Italian text, report builder)
- `data/` - **SHARED** Taxonomy mappings, rating tables, sector definitions
- `config.py` - **SHARED** Configuration constants
- `tests/` - Test scripts (DB, calculations, XBRL, FGPMI, CSV)
- `docs/` - Reference docs, guides, PDF samples
- `legacy/` - Old Streamlit app (deprecated, preserved for reference)
- `financial_analysis.db` - **SHARED** SQLite database in project root

**Run Modern Stack:**
```bash
# Terminal 1: Backend (dev mode — no JWT required)
cd backend && source venv/bin/activate
DEV_USER_ID=dev-user-001 uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# Terminal 2: Frontend
cd frontend && npm run dev
```

**API Workflow — Budget (3 calls):**
```bash
# 1. INPUT: Upload data → POST /api/v1/import/{xbrl|csv|pdf}
# 2. ASSUMPTIONS: Create scenario + bulk assumptions → PUT /scenarios/{id}/assumptions
# 3. OUTPUT: Get complete analysis → GET /scenarios/{id}/analysis
```

**API Workflow — Infrannuale (5 calls + optional promote + optional AI comments):**
```bash
# 1. INPUT: Upload partial-year data → POST /api/v1/import/{pdf|xbrl} (with period_months)
# 2. RETTIFICHE (optional): Adjust imported BS/IS with double-entry postings
#    GET  /api/v1/companies/{id}/years/{year}/adjustable  (seeds original snapshot + returns rettifiche_log)
#    PUT  /api/v1/companies/{id}/years/{year}/adjustments (persists BS/IS + rettifiche_log, max 20 entries)
# 3. SCENARIO: Create infrannuale scenario → POST /companies/{id}/scenarios (scenario_type="infrannuale")
# 4. COMPARE: Get partial vs reference comparison → GET /scenarios/{id}/comparison
# 5. PROJECT: Save overrides + project to 12M → PUT /scenarios/{id}/assumptions (auto_generate=true)
# 6. OUTPUT: Get complete analysis → GET /scenarios/{id}/analysis
# 7. AI COMMENTS (optional, Stampa tab): 6 editable narrative comments
#    GET  /scenarios/{id}/infrannuale/ai-comments   (stored dict)
#    POST /scenarios/{id}/infrannuale/ai-comments   (body=ctx → Haiku generate + save)
#    PUT  /scenarios/{id}/infrannuale/ai-comments   (body=dict → save user edits)
# 8. PROMOTE (optional): Copy projection to FinancialYear → POST /scenarios/{id}/promote
#    → Enables using projected year as base year for a subsequent budget scenario
```

**Important:** Backend imports shared modules from project root via `sys.path` manipulation in `backend/app/main.py`. No code duplication - single source of truth for all business logic.

## Development Commands

### Backend Setup
```bash
cd backend
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Initialize database (first time, from project root)
cd .. && python -c "from database.db import init_db; init_db()"
```

### Running Backend
```bash
cd backend && source venv/bin/activate

# Dev mode (no JWT required, uses fallback user_id):
DEV_USER_ID=dev-user-001 uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# Production mode (requires Supabase JWT):
SUPABASE_JWT_SECRET=your-jwt-secret uvicorn app.main:app --host 127.0.0.1 --port 8000

# API: http://localhost:8000/api/v1
# Docs: http://localhost:8000/docs
```

### Frontend Setup & Run
```bash
cd frontend
npm install
npm run dev  # http://localhost:3000
```

### Testing
```bash
cd tests
python test_db.py                 # Database models
python test_calculations.py       # Financial ratios, Altman
python test_fgpmi.py              # FGPMI rating
python test_xbrl_import.py        # XBRL parser
```

### Database Operations
```bash
# Reset database (WARNING: deletes all data)
python -c "from database.db import drop_all, init_db; drop_all(); init_db()"
```

## Architecture

### Simplified API Design

**Pattern:** INPUT → ASSUMPTIONS → OUTPUT

1. **INPUT (3 endpoints)**: Data import
   - `POST /api/v1/import/xbrl` - Italian XBRL files (6 taxonomies). Optional `period_months` for partial year.
   - `POST /api/v1/import/csv` - CSV files (TEBE format)
   - `POST /api/v1/import/pdf` - PDF balance sheets (Docling AI). Optional `period_months` for partial year.

2. **ASSUMPTIONS (2 endpoints)**: Budget scenarios
   - `POST /companies/{id}/scenarios` - Create scenario (`scenario_type`: "budget" or "infrannuale")
   - `PUT /scenarios/{id}/assumptions` - Bulk upsert all years (auto_generate=true)

3. **OUTPUT (1 endpoint)**: Complete analysis
   - `GET /scenarios/{id}/analysis` - Returns historical + forecast + all calculations

4. **INTRA-YEAR (2 endpoints)**: Partial-year comparison + promote
   - `GET /scenarios/{id}/comparison` - Compare partial year vs reference full year (infrannuale only)
   - `POST /scenarios/{id}/promote` - Copy infrannuale projection to a full-year FinancialYear (enables budget base year)

5. **MANAGEMENT (2 endpoints)**: Basic CRUD
   - `GET /companies` - List companies
   - `GET /companies/{id}/scenarios` - List scenarios

6. **ADMIN / UPLOAD TRACKING (3 endpoints)**: Developer-only, header-auth
   - `GET /admin/uploads` - Filter by user_id / file_type / status / date range
   - `GET /admin/uploads/{id}` - Full record including error_traceback
   - `GET /admin/uploads/{id}/download` - Stream the original file
   - Gated by `X-Admin-Key` header matching `ADMIN_API_KEY` env var. Not used by the iframe frontend.

**Key Simplification:** 1 comprehensive API call replaces 10+ granular endpoints

### Authentication & Multi-Tenancy

**Architecture:** App embedded as iframe in Formula Finance → parent sends Supabase JWT via `postMessage` → frontend stores token → all API calls include `Authorization: Bearer <token>` → backend validates JWT, extracts `user_id` from `sub` claim → all queries scoped by `user_id`.

**Key Files:**
- `backend/app/core/auth.py` — `get_current_user_id()` FastAPI dependency (JWT decode or DEV_USER_ID fallback)
- `backend/app/core/ownership.py` — `validate_company_owned_by_user()`, `check_company_limit()`
- `frontend/contexts/AuthContext.tsx` — postMessage listener, token state, syncs to API client
- `frontend/lib/api.ts` — Axios interceptors for Bearer token injection + 401 re-auth

**Config (env vars):**
- `SUPABASE_JWT_SECRET` — Supabase JWT secret (HS256). Required in production.
- `DEV_USER_ID` — Bypass JWT in dev mode. Set to any string (e.g., `dev-user-001`).
- `MAX_COMPANIES_PER_USER` — Company limit per user (default: 50).

**PostMessage Protocol:**
| Direction | Message | When |
|-----------|---------|------|
| Child → Parent | `{ type: 'REQUEST_AUTH_TOKEN' }` | On iframe load |
| Parent → Child | `{ type: 'AUTH_TOKEN', token: 'jwt...' }` | On request + token refresh |
| Parent → Child | `{ type: 'AUTH_LOGOUT' }` | On user logout |

**Dev mode:** When `DEV_USER_ID` is set and no JWT provided, backend uses that value as user_id. Frontend auth timeout (1s) stops loading spinner, allowing unauthenticated API calls.

**All API endpoints** require authentication. Every route has `user_id: str = Depends(get_current_user_id)`. Companies are filtered by `user_id`; accessing another user's company returns 404.

### Shared Module Architecture

```
Project Root
├── backend/           # FastAPI REST API (imports shared modules)
│   └── app/core/
│       ├── auth.py        # JWT validation + dev mode fallback
│       └── ownership.py   # Company ownership + limit checks
├── frontend/          # Next.js 15 React frontend
│   └── contexts/
│       ├── AuthContext.tsx # postMessage JWT listener
│       └── AppContext.tsx  # Global state (waits for auth)
├── database/          # SHARED: SQLAlchemy ORM models
├── calculations/      # SHARED: Financial calculators
├── importers/         # SHARED: XBRL/CSV/PDF parsers
├── pdf_service/       # PDF report generation + EM-Score
├── data/              # SHARED: Taxonomy/rating configs
├── config.py          # SHARED: Constants
├── tests/             # Test scripts
├── docs/              # Reference docs & guides
└── legacy/            # Streamlit (deprecated)
```

**Backend Import Pattern:**
```python
# backend/app/main.py sets up sys.path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

# Then anywhere in backend:
from database.models import Company, BalanceSheet
from database.queries import get_fy_prefer_full, get_fy_partial  # Safe FinancialYear lookups
from calculations.ratios import FinancialRatiosCalculator
from importers.xbrl_parser_enhanced import import_xbrl_file_enhanced
from app.core.auth import get_current_user_id  # Auth dependency
from app.core.ownership import validate_company_owned_by_user  # Ownership check
```

### Database Schema

**Location:** `/home/peter/DEV/budget/financial_analysis.db` (shared by all apps)

**Core Models:**
- `Company` - Master data (name, tax_id, sector 1-6, user_id). Composite unique on (user_id, tax_id).
- `FinancialYear` - Links company to financial statements for a year. `period_months` (NULL=full year, 1-11=partial)
- `BalanceSheet` - sp01-sp18 (Italian civil code art. 2424) + hierarchical debts
- `IncomeStatement` - ce01-ce20 (Italian civil code art. 2425)

**Forecasting Models:**
- `BudgetScenario` - Scenario metadata (name, base_year). `scenario_type`: "budget" | "infrannuale". `period_months` for partial year.
- `BudgetAssumptions` - Growth percentages per forecast year
- `ForecastYear` - Links scenario to forecasted statements
- `ForecastBalanceSheet`, `ForecastIncomeStatement` - Projected financials

**FinancialYear coexistence:** A company+year can have both a partial-year record (`period_months` 1-11) and a promoted full-year record (`period_months` NULL). All queries use `database/queries.py` helpers (`get_fy_prefer_full`, `get_fy_partial`) to select the correct record. Importers match by `period_months` when deleting/updating to avoid clobbering the wrong record.

**Relationships:** All use cascade="all, delete-orphan" (deleting company removes all child records)

### Calculator Architecture

**Layered design** (each layer builds on lower layers):

1. **Base** (`calculations/base.py`) - safe_divide, rounding, Excel-like functions
2. **Ratios** (`calculations/ratios.py`) - Liquidity, solvency, profitability, activity
3. **Risk Models** (`calculations/altman.py`, `rating_fgpmi.py`) - Use ratios + raw financials
4. **Forecasting** (`calculations/forecast_engine.py`) - 3-5 year budget projections
5. **Intra-Year** (`calculations/intra_year_engine.py`) - Partial-year → 12-month projection

**Important:** Calculators work with SQLAlchemy ORM objects, not dicts. Use Decimal for all monetary calculations.

## Key Conventions

### Naming Conventions
- **Italian codes**: Balance sheet = `sp01-sp18`, Income statement = `ce01-ce20`
- **Aggregates**: `TA` (Total Assets), `CN` (Equity), `MOL` (EBITDA), `RO` (EBIT)
- **Database columns**: Full Italian names (e.g., `sp03_immob_materiali`, `ce01_ricavi_vendite`)
- **Calculator results**: Return NamedTuples (WorkingCapitalMetrics, LiquidityRatios, etc.)

### Financial Calculations
- **Always use Decimal**: Import from decimal module, never use float for money
- **Zero-division protection**: Use `BaseCalculator.safe_divide()` (returns default value)
- **Rounding**: Use `BaseCalculator.round_decimal()` with config.DECIMAL_PLACES
- **Percentage format**: Stored as absolute values (25.5 = 25.5%), not decimals (0.255)

### Italian Accounting Standards (OIC)
- **Balance Sheet must balance**: Assets = Equity + Liabilities (tolerance: €0.01)
- **Working Capital (CCN)**: Current Assets - Current Liabilities
- **EBITDA (MOL)**: EBIT + Depreciation + Amortization
- **EBIT (RO)**: Operating Revenue - Operating Costs (before financial items)
- **Tax Rate**: 24% IRES (Italian corporate tax) used in forecasting

### Sector-Specific Logic

**Sectors** (config.py Sector enum):
1. INDUSTRIA (Manufacturing) - 5-component Altman model
2. COMMERCIO (Commerce/Retail) - 4-component Altman model
3. SERVIZI (Services)
4. AUTOTRASPORTI (Transport)
5. IMMOBILIARE (Real Estate)
6. EDILIZIA (Construction)

Sector determines Altman coefficients and FGPMI thresholds (from `data/rating_tables.json`)

## Critical Implementation Notes

### XBRL Import
- Supports taxonomies 2011-01-04 through 2018-11-04
- Values in full euros (not thousands)
- Parser detects schema type (Ordinario/Abbreviato/Micro)
- Enhanced parser (`xbrl_parser_enhanced.py`) includes hierarchical debt reconciliation

### PDF Import (Claude LLM)
- Uses PyMuPDF text extraction + Claude Haiku 4.5 for structured extraction
- Processing time: 3-10 seconds per PDF
- Supports Bilancio Micro, Abbreviato, Ordinario (IV CEE format)
- Supports "Stampa dettaglio voci" format (ERP detail reports with account-level GL entries)
- Supports "Situazione Contabile" trial balance format (deterministic parser, no LLM)
- Pre-filters: Zucchetti, Datev/Koinos, Stampa dettaglio voci, Dylog separator noise
- Post-extraction validators: crediti, debiti split, equity consistency, ce20_imposte cross-check
- Maps extracted tables to sp01-sp18, ce01-ce20
- Both single-year and dual-year (both columns) extraction modes

### FGPMI Rating Model
- Complex multi-table lookup (7 indicators, sector-specific thresholds)
- Revenue bonus: +2 points if revenue > €500K
- Rating classes: 13 classes (AAA → B-)
- Data: `data/rating_tables.json`

### Forecasting Engine (Budget)
- Base year + 3 or 5 forecast years
- Cost split: Variable (60%) vs Fixed (40%)
- Cash as plug: Balances by adjusting sp09_disponibilita_liquide
- Negative cash: Increases short-term debt (sp16_debiti_breve)
- Triggered by: bulk assumptions endpoint with `auto_generate=true`

### Intra-Year Engine (Infrannuale)
- Projects partial-year financials (e.g., 9 months) to a full 12-month year
- Requires: partial year data + reference full year (base_year = previous year)
- **Comparison** (`get_comparison`): Line-by-line partial vs reference with % and annualized values
  - P&L items: annualized = partial_value * (12 / period_months)
  - BS items: point-in-time values (no annualization)
- **Projection** (`generate_projection`): Single forecast year using growth rates vs reference
  - Revenue/costs: growth % applied to reference year values (frontend pre-calculates from user overrides)
  - Materials/services: split variable/fixed with separate growth rates
  - Depreciation: annualize partial + new investment depreciation
  - BS working capital: turnover ratios from reference year applied to projected P&L
  - Equity: capital constant, reserves absorb prior year profit, current year from projection
  - Cash as plug (same as budget engine)
  - Taxes: recalculated on projected pre-tax profit
- Output stored as ForecastYear (compatible with existing `/analysis` endpoint)
- **Promote** (`POST /scenarios/{id}/promote`): Copies ForecastYear BS/IS into a new FinancialYear (period_months=NULL)
  - Enables using the projected year as base year for a subsequent budget scenario
  - Dynamic column copy via `__table__.columns` intersection (handles missing fields gracefully)
  - Fails if a full-year FinancialYear already exists for that company+year
  - Service: `backend/app/services/promote_service.py`
- Frontend wizard: Import → Rettifiche → Comparison → Projection (editable) → Results → Promote to Budget

### Rettifiche (BS/IS Adjustments Journal)
Journal of double-entry corrections applied to the imported partial-year financials before comparison/projection.

- **Persistence:** `FinancialYear.original_bs_snapshot` + `original_is_snapshot` (pre-rettifiche JSON) and `FinancialYear.rettifiche_log` (JSON array of per-edit entries). Snapshot is created on first GET to `/adjustable`, so `BalanceSheet`/`IncomeStatement` always reflect the *current* corrected state while `original_*_snapshot` is immutable.
- **Per-edit flow:** typing a new value into any BS/CE input updates a local `pendingEdits` map. On blur / Enter, a single-row proposal dialog opens with a suggested double-entry counterpart (from `PROPOSAL_RULES`) pre-filled. Confirming appends a `RettificaEntry` to the log, applies both deltas to `corrections`, and persists via `PUT /adjustments`. Cancelling reverts.
- **Counterpart picker** (`COUNTERPART_GROUPS` + `allowedCounterpartCategories`): the dropdown is filtered by double-entry category based on the edited field and sign — e.g. Debito↑ shows only Costi/Oneri + Attivo; Credito↑ shows only Ricavi/Proventi + Passivo. Aggregate/computed fields (`sp04`, `sp05`, `sp06`, `sp07`, `sp12`, `sp13`, `sp16`, `sp17`, `ce08`, `ce09`, `ce17`) are excluded via `NON_POSTABLE_FIELDS` because `recalcAggregates` would overwrite any direct delta.
- **Journal panel** lists every confirmed entry with a per-row delete (reverses both deltas, filters log, persists). Hard cap of **20 entries** (`RETTIFICHE_MAX`) — enforced both client-side (toast + block) and server-side (400 error on `/adjustments`).
- **Auto-reconciliation:** `reconcileSubfields(original)` (frontend) plugs small (≤ 5 €) Attivo-vs-Passivo imbalances from import rounding into `sp09_disponibilita_liquide` on load; subsequent rettifiche preserve balance because they're always double-entry.
- **Hydration:** on tab mount, `corrections` is seeded from `adjustableData.balance_sheet`/`income_statement` (post-rettifiche) and `log` from `adjustableData.rettifiche_log`. Reopening the tab shows the persisted journal.
- **Reset** (`onReset`): sends `original_*_snapshot` back as BS/IS + empty log to `PUT /adjustments` — wipes all corrections and the journal.
- Key files:
  - `database/models.py` — `FinancialYear.rettifiche_log` column
  - `backend/app/schemas/adjustments.py` — `RettificaEntry`, `AdjustableFinancialYear.rettifiche_log`, `AdjustmentsUpdate.rettifiche_log`
  - `backend/app/api/v1/financial_years.py` — `RETTIFICHE_LOG_MAX = 20`, GET `/adjustable`, PUT `/adjustments`
  - `frontend/app/infrannuale/page.tsx` — `RettificheTab` component, `PROPOSAL_RULES`, `COUNTERPART_GROUPS`, `DEBT_GROUPS`, `recalcAggregates`, `reconcileSubfields`

### Shared BS/IS Layout (Rettifiche, Confronto, /forecast/balance, /forecast/income)
All four financial-statement views render the same IV-CEE-format layout to keep schemas comparable. When adding a new BS/IS sub-field, add rows in all of:
- `frontend/app/infrannuale/page.tsx` — `RETTIFICHE_BS_ATTIVO` / `RETTIFICHE_BS_PN`, `CE_A`–`CE_E`, and the `relabel` map inside `buildBalanceItemsWithTotals` / `buildIncomeItemsWithEbitda` (Confronto)
- `frontend/app/forecast/balance/page.tsx` — the `rows` array in `BalanceSheetTable`
- `frontend/app/forecast/income/page.tsx` — the `rows` array in `IncomeStatementTable`

Detail blocks shared across all views:
- **Immob. finanziarie (sp04):** sp04a_partecipazioni, sp04b/c_crediti_immob_breve/lungo, sp04d_altri_titoli, sp04e_strumenti_derivati_attivi. Aggregate `sp04_immob_finanziarie` is computed from sub-fields.
- **Crediti (sp06/sp07):** a through g per entro/oltre (clienti, controllate, collegate, controllanti, tributari, imposte anticipate, altri).
- **Patrimonio netto (sp12):** sp12a (sovrapprezzo) through sp12h (riserva neg. azioni proprie), with sp12g (utili portati) before sp13 and sp12h after. Aggregate `sp12_riserve` is computed from sub-fields.
- **Debiti (sp16/sp17):** 7 creditor-typed groups (`_debt_banche`, `_debt_altri_finanz`, `_debt_obbligazioni`, `_debt_fornitori`, `_debt_tributari`, `_debt_previdenza`, `_debt_altri`), each rendered as a synthetic total row followed by entro (sp16x) and oltre (sp17x) sub-rows. Group headers are pinned into `ALWAYS_SHOW_CODES` so the full OIC art. 2424 structure shows even when a group is zero; sub-rows follow the standard "hide when all years zero" filter in Confronto/forecast, but are always visible in Rettifiche so they remain editable. Aggregates `sp16_debiti_breve`/`sp17_debiti_lungo` and `total_debt` are computed.
- **P&L:** ce08a–d (personale: TFR, salari, oneri sociali, altri), ce09a–d (ammortamenti/svalutazioni), ce17a/b (rivalutazioni/svalutazioni). EBITDA + EBIT rows shown in all three pages.

**Per-year sub-field reconciliation (Confronto tab):** Bilancio abbreviato imports often populate only parent aggregates (e.g. `sp16_debiti_breve`) leaving detail sub-fields at 0. `buildBalanceItemsWithTotals` applies `reconcileSubfields` to each year column (partial/reference/prior) independently, so the gap is plugged into the "altri" bucket (`sp04a`, `sp05e`, `sp06g`, `sp07g`, `sp12e`, `sp16g`, `sp17g`) before rows are built. This mirrors the Rettifiche load-time reconciliation and prevents detail rows from being hidden by the zero-filter.

**Recap dialog (Riepilogo Rettifiche):** aggregate rows that were updated indirectly by `recalcAggregates` (any field in `NON_POSTABLE_FIELDS`) render in muted-gray italic with a tooltip explaining they are derived totals, so the user doesn't mistake them for duplicated postings.

### Projection Tab (Proiezione P&L editable overrides)
Expanded `EDITABLE_CE_CODES` to cover **22 CE fields** (ce01–ce20 plus ce08/09/11/17 sub-fields), so the user can override almost every projected P&L line directly in the Proiezione table.

- **Backend override plumbing:** `calculateProjectedBS` sends the full set of override fields the backend schema supports (`ce02_override`, `ce03_override`, `ce10_override`, `ce11_override`, `ce13_override` through `ce19_override`). For ce17 the picker exposes `ce17a` and `ce17b` separately; the backend stores the net (`ce17a − ce17b`) in `ce17_override`. For `ce20_imposte`, the override is translated to an effective `tax_rate` (`ce20 / PBT × 100`) so the forecast engine reproduces it.
- **Consistency:** `ProjectionTable`'s `PROJ_COST_CODES_ALL` includes `ce11b_altri_accantonamenti` (matches `calculateProjectedBS`'s `EBITDA_COST_CODES`), and `projRettifiche` is derived from `pv("ce17a") − pv("ce17b")` so edits flow into PBT → net profit. BS `sp13` now always agrees with the P&L utile displayed above it.
- **Gotcha:** `buildBalanceItemsWithTotals` must NOT overwrite `annualized_value` when called from `calculateProjectedBS` — the Projection tab writes projected BS values into that field. Only `partial_value`, `reference_value`, `prior_value` are reconciled per year.

### Infrannuale AI Comments (Stampa tab)
Editable AI-generated commentary rendered above each table in the Stampa tab. Six comments total: **overall** (before the first table) + one per section (`ce_confronto`, `sp_confronto`, `ce_proiezione`, `sp_proiezione`, `indicatori`).

- **Persistence:** `BudgetScenario.ai_comments_infrannuale` — single TEXT column storing a JSON dict. Six keys only (extra keys are stripped on save). Reset/regenerate replaces the whole dict.
- **Generation:** `ai_comments_service.generate_infrannuale_comments(ctx)` calls Claude Haiku with a structured tool (Pydantic `InfrannualeComments`) so output is shape-validated. The frontend builds `ctx` locally (scenario, `income_map`, `balance_map`, `indicators` per column, `ratings`) and POSTs it to the backend — keeps the compute on the client and the LLM call server-side only. Missing `ANTHROPIC_API_KEY` returns an empty dict (toast: "chiave API mancante").
- **Endpoints** (scenario-scoped):
  - `GET /companies/{id}/scenarios/{scenario_id}/infrannuale/ai-comments` — return stored
  - `POST .../infrannuale/ai-comments` — generate via Haiku + save + return
  - `PUT .../infrannuale/ai-comments` — save user edits (no LLM call)
- **UI:** in `StampaContent`, each `CommentBlock` is a shadcn `Textarea` bound to `aiComments[key]`; `onChange` updates local state, `onBlur` persists via `saveInfrannualeAIComments`. Empty blocks are hidden in print (`print:hidden`) so the PDF stays clean.
- **Key files:**
  - `database/models.py` — `BudgetScenario.ai_comments_infrannuale`
  - `backend/app/services/ai_comments_service.py` — `InfrannualeComments`, `generate_infrannuale_comments`, `get/save_infrannuale_comments`
  - `backend/app/api/v1/budget_scenarios.py` — 3 endpoints under `/infrannuale/ai-comments`
  - `frontend/lib/api.ts` — `InfrannualeAIComments` + `get/generate/saveInfrannualeAIComments`
  - `frontend/app/infrannuale/page.tsx` — `StampaContent` state, `buildAICtx()`, `CommentBlock`

### Upload Tracking (debugging user-reported import problems)
- Every `/import/{xbrl,csv,pdf}` call persists the raw bytes to `data/uploads/{user_id}/{YYYY-MM}/...` and logs a row in the `uploaded_files` table **before** parsing runs (so parser crashes are still tracked).
- DB row: `filename`, `file_type`, `file_size`, `storage_path`, `status` (pending/success/error), `error_message`, `error_traceback`, `uploaded_at`, `company_id`.
- Tracker errors are swallowed — tracking must never break the import flow.
- HTTP ownership/limit failures (`HTTPException`) are NOT marked as parser errors.
- Retention: 90 days via `scripts/cleanup_uploads.py` (daily cron). Override with `UPLOAD_RETENTION_DAYS`.
- Admin retrieval: `GET /api/v1/admin/uploads*` endpoints, gated by `X-Admin-Key` header (matches `ADMIN_API_KEY` env var).
- Key files:
  - `database/models.py` — `UploadedFile` model
  - `backend/app/services/upload_tracker.py` — `save_upload`, `mark_success`, `mark_error`
  - `backend/app/api/v1/admin.py` — admin router
  - `migrate_db.py` — `CREATE TABLE IF NOT EXISTS uploaded_files` for existing prod DBs
  - `scripts/cleanup_uploads.py` — retention cron job

### Bulk Assumptions Workflow
```python
# Budget: Multiple years
PUT /scenarios/{id}/assumptions
{
  "assumptions": [
    {"forecast_year": 2025, "revenue_growth_pct": 5.0, ...},
    {"forecast_year": 2026, "revenue_growth_pct": 4.0, ...},
    {"forecast_year": 2027, "revenue_growth_pct": 3.5, ...}
  ],
  "auto_generate": true  # Triggers ForecastEngine
}
# Returns: {success: true, forecast_generated: true, forecast_years: [2025,2026,2027]}

# Infrannuale: Single year (growth % calculated by frontend from user overrides)
PUT /scenarios/{id}/assumptions
{
  "assumptions": [
    {"forecast_year": 2025, "revenue_growth_pct": 8.3, ...}  # 1 year only
  ],
  "auto_generate": true  # Triggers IntraYearEngine (detected via scenario_type)
}
# Returns: {success: true, forecast_generated: true, forecast_years: [2025]}
```

### Promote Infrannuale → Budget Workflow
```python
# Full user flow: partial-year import → infrannuale projection → promote → budget forecast

# After infrannuale projection is generated:
POST /companies/{id}/scenarios/{scenario_id}/promote
# Returns: {success: true, financial_year_id: 123, year: 2025, company_id: 1, message: "..."}

# Now create a budget scenario using the promoted year as base:
POST /companies/{id}/scenarios
{
  "company_id": 1, "name": "Budget 2026-2028",
  "base_year": 2025,  # ← the promoted year
  "scenario_type": "budget"
}
# Proceeds with normal budget workflow (assumptions → analysis)
```

## Common Tasks

### Adding a New Financial Ratio
1. Add method to `FinancialRatiosCalculator` in `calculations/ratios.py`
2. Add to appropriate NamedTuple
3. Update `backend/app/schemas/calculations.py`
4. Update `frontend/types/api.ts`
5. Ratio automatically included in `/analysis` endpoint response

### Adding a New API Endpoint

**⚠️ IMPORTANT:** Avoid creating new endpoints. The API is intentionally simplified.

**Ask first:**
- Can it be added to `/analysis` endpoint response?
- Does it fit INPUT → ASSUMPTIONS → OUTPUT workflow?
- Will it require multiple frontend calls?

**If truly needed:**
1. Extend existing comprehensive endpoints (preferred)
2. Or create in appropriate router (`backend/app/api/v1/*.py`)
3. Add business logic in `backend/app/services/` (consolidate, don't duplicate)
4. Update frontend `lib/api.ts` and `types/api.ts`

### Extending Database Schema
1. Modify `database/models.py` (shared by both apps)
2. Create migration script (or use `drop_all(); init_db()` for dev)
3. Update affected calculators in `calculations/`
4. Update Pydantic schemas in `backend/app/schemas/`
5. Update TypeScript interfaces in `frontend/types/api.ts`

### Creating a Frontend Page
1. Create file in `frontend/app/` (e.g., `new-feature/page.tsx`)
2. Use `useAppContext()` hook for global state (company/scenario selection)
3. Call `/analysis` endpoint once, cache result
4. All pages should read from same cached comprehensive response
5. Use Recharts for charts, wrapped in shadcn `ChartContainer` with `ChartConfig`
6. Use shadcn/ui components (`Card`, `Table`, `Badge`, etc.) - not raw HTML
7. Use semantic colors (`text-foreground`, `bg-card`, `border-border`) - not hardcoded hex
8. Charts use CSS variable colors: `var(--chart-1)` through `var(--chart-5)`

## Technical Constraints

- **SQLite database**: Single-file, no concurrent writes (use transactions carefully)
- **Decimal precision**: Numeric(15, 2) - max 9,999,999,999,999.99
- **JSON serialization**: Backend uses custom `DecimalJSONResponse` (Decimal → float)
- **Italian locale**: UI text in Italian, European number formatting
- **Authentication**: Supabase JWT via iframe postMessage (see below). Dev mode: `DEV_USER_ID` env var bypasses JWT.
- **CORS**: Allows localhost:3000-3002 (Next.js), 8501 (Streamlit), plus Formula Finance origin in production
- **Frontend UI**: shadcn/ui components only - no raw HTML tables/buttons
- **Charts**: Recharts with `ChartContainer` + CSS variable colors (blue/slate palette)
- **Status colors**: Altman/FGPMI use explicit green/yellow/red with `dark:` variants
- **No emojis**: Use lucide-react icons instead

## Development Workflow

**Working on Shared Modules** (database, calculations, importers):
- Changes automatically affect both modern and legacy apps
- Test with backend: `curl http://localhost:8000/api/v1/companies`
- Run test scripts: `cd tests && python test_calculations.py`
- No code duplication - single source of truth

**Working on Backend API**:
- Follow simplified API pattern (avoid granular endpoints)
- Prefer extending `/analysis` endpoint
- Test via Swagger UI at http://localhost:8000/docs

**Working on Frontend**:
- shadcn/ui (new-york style, slate base) + Tailwind CSS v3 + next-themes
- Use comprehensive endpoints (call `/analysis` once, cache result)
- All analysis pages read from same cached response
- Report page (`/report`) renders full financial analysis with 11 sections
- Typical workflow (budget):
  ```typescript
  // Budget page: Bulk save
  await api.bulkUpsertAssumptions(companyId, scenarioId, {
    assumptions: [...],  // All years
    auto_generate: true
  })

  // Analysis/Forecast/Cashflow/Report pages: Get everything once
  const analysis = await api.getScenarioAnalysis(companyId, scenarioId)
  // All data available: analysis.historical_years, .forecast_years, .calculations
  ```

- Typical workflow (infrannuale):
  ```typescript
  // 1. Import partial-year PDF/XBRL with period_months
  const importResult = await api.importPDF(file, fiscalYear, name, null, true, sector, periodMonths)

  // 2. Create infrannuale scenario (base_year = fiscalYear - 1)
  const scenario = await api.createBudgetScenario(companyId, {
    company_id: companyId, name: `Infrannuale 9M 2025`,
    base_year: 2024, scenario_type: "infrannuale", period_months: 9,
  })

  // 3. Get comparison (partial year vs reference full year)
  const comparison = await api.getIntraYearComparison(companyId, scenarioId)

  // 4. User edits projections → frontend converts to growth %, saves + generates
  await api.bulkUpsertAssumptions(companyId, scenarioId, {
    assumptions: [{ forecast_year: 2025, revenue_growth_pct: 5.0, ... }],
    auto_generate: true
  })

  // 5. Results via standard analysis endpoint
  const analysis = await api.getScenarioAnalysis(companyId, scenarioId)

  // 6. (Optional) Promote projection to full-year → enables budget
  await api.promoteProjection(companyId, scenarioId)
  // Now the projected year is a FinancialYear that can be used as budget base year
  ```

**Frontend Pages:**
- `/` - Home (company list)
- `/import` - XBRL/CSV/PDF upload
- `/infrannuale` - Intra-year analysis wizard (import partial year → compare → project → results)
- `/budget` - Scenario assumptions editor
- `/forecast/income`, `/forecast/balance`, `/forecast/reclassified` - Forecast views
- `/analysis` - Financial ratios & charts
- `/cashflow` - Cash flow statement
- `/report` - Full report preview (mirrors PDF output)

**Working on Legacy App** (deprecated):
- Only for reference or maintenance
- All new features should be added to modern stack

## API Migration Notes

### Deprecated Endpoints

**Use `/analysis` instead:**
```
❌ GET /calculations/altman
❌ GET /calculations/fgpmi
❌ GET /calculations/ratios
❌ GET /scenarios/{id}/reclassified
❌ GET /scenarios/{id}/detailed-cashflow
✅ GET /scenarios/{id}/analysis (returns ALL)
```

**Use bulk assumptions:**
```
❌ POST /assumptions (per year)
❌ PUT /assumptions/{year}
✅ PUT /assumptions (bulk, all years)
```

**Why simplified:**
- Old: 15+ API calls per workflow
- New: 3 API calls total
- Better UX, simpler code, faster performance

---

**For detailed API documentation, examples, and usage, see README.md**
