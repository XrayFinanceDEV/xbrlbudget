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

**Project Root:** `C:\DEV\xbrlbudget-main\xbrlbudget` (Windows). On the original author's machine it was `/home/peter/DEV/budget/`; paths below using POSIX (`source venv/bin/activate`, `/home/peter/...`) are illustrative — use Windows equivalents (`venv\Scripts\activate`).

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

**API Workflow — Budget (3 calls + optional CE overrides):**
```bash
# 1. INPUT: Upload data → POST /api/v1/import/{xbrl|csv|pdf}
# 2. ASSUMPTIONS: Create scenario + bulk assumptions → PUT /scenarios/{id}/assumptions
# 3. OUTPUT: Get complete analysis → GET /scenarios/{id}/analysis
# 4. CE OVERRIDES (optional): Edit forecast P&L values directly from /forecast/income
#    PATCH /scenarios/{id}/ce-override  (batch overrides → regenerate forecast)
#    POST  /scenarios/{id}/generate?clear_overrides=true  (reset all overrides → regenerate)
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

5. **CE OVERRIDES (2 endpoints)**: Direct forecast P&L editing from `/forecast/income`
   - `PATCH /scenarios/{id}/ce-override` - Batch-update CE overrides + regenerate forecast
   - `POST /scenarios/{id}/generate?clear_overrides=true` - Reset all overrides + regenerate

6. **MANAGEMENT (2 endpoints)**: Basic CRUD
   - `GET /companies` - List companies
   - `GET /companies/{id}/scenarios` - List scenarios

7. **ADMIN / UPLOAD TRACKING (3 endpoints)**: Developer-only, header-auth
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

**Location:** `financial_analysis.db` in the project root (shared by all apps)

**Core Models:**
- `Company` - Master data (name, tax_id, sector 1-6, user_id). Composite unique on (user_id, tax_id).
- `FinancialYear` - Links company to financial statements for a year. `period_months` (**NULL or 12 = full year**, 1-11 = partial). Some importers historically wrote `12`; `pdf_importer` now normalizes `>= 12 → None` on write, and every "full-year" query accepts `NULL` **or** `12` (see coexistence note below).
- `BalanceSheet` - sp01-sp18 (Italian civil code art. 2424) + hierarchical debts
- `IncomeStatement` - ce01-ce20 (Italian civil code art. 2425)

**Forecasting Models:**
- `BudgetScenario` - Scenario metadata (name, base_year). `scenario_type`: "budget" | "infrannuale". `period_months` for partial year.
- `BudgetAssumptions` - Growth percentages per forecast year
- `ForecastYear` - Links scenario to forecasted statements
- `ForecastBalanceSheet`, `ForecastIncomeStatement` - Projected financials

**FinancialYear coexistence:** A company+year can have both a partial-year record (`period_months` 1-11) and a promoted full-year record (`period_months` NULL). All queries use `database/queries.py` helpers (`get_fy_prefer_full`, `get_fy_partial`) to select the correct record. Importers match by `period_months` when deleting/updating to avoid clobbering the wrong record.

**`period_months` full-year convention (NULL or 12):** Several imports historically saved `12` instead of `NULL` for annual statements. "Historical year" queries that filtered only `period_months IS NULL` excluded those records → the **Previsionale page rendered empty** (no base year found). Fixed on both sides: **write** — `pdf_importer` normalizes `period_months >= 12 → None`; **read** — every full-year query accepts `NULL` **or** `12` (`analysis_service`, `calculation_service`, `budget_scenarios`, `promote_service`, `financial_years`, `queries.get_fy_prefer_full`); `get_fy_partial` excludes `12`.

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
- **Routing-first:** every PDF is classified by `bilancio_classifier.classify_bilancio` BEFORE
  picking an extractor (see the Macro-area router subsection below). The classifier replaces the old
  binary `is_trial_balance` check.
- Uses PyMuPDF text extraction + Claude Haiku 4.5 for structured extraction (IV-CEE routes)
- **Reading order** (`reading_order_text` / `_stream_order_is_scrambled`, `pdf_extractor_llm.py`):
  `page.get_text()` returns content-stream order, NOT visual reading order. Some generators draw a
  comparative statement bottom-up or emit the second amount column as a detached block, so labels
  bind to the WRONG column: the prior year gets imported as the current one (a "Bilancio
  riclassificato / Fascicolo" read its 2024 column as 2025 — profit +17.305 instead of the real
  −127.995 loss) and a detail amount is attributed to the legal item that precedes it in the stream
  (C.17 "altri" financial charges booked to D.18 Rivalutazioni, +27.777 on the CE result). Only the
  second failure is visible (blocked as "Utile CE != sp13"); **the wrong-year one balances
  perfectly**, which is why it is fixed upstream instead of at the gates. A page is re-read
  coordinate-sorted (`get_text(sort=True)`) ONLY when its stream order is demonstrably broken —
  more than 25% backward vertical jumps between consecutive blocks, min 6 blocks. Well-formed pages
  keep byte-identical text (212 of 249 corpus files unchanged), so prompts tuned on that text do not
  move. Applied in `extract_relevant_pages._page_text` and `_extract_full_text`, AFTER
  `_detached_value_page_texts` and `_filter_difference_columns` (both already coordinate-based).
  Tests: `tests/test_reading_order.py`. Rules: `docs/import/REGOLE-IMPORT-02-ESTRAZIONE.md` §2.
- Processing time: 3-10 seconds per PDF
- Supports Bilancio Micro, Abbreviato, Ordinario (IV CEE format)
- Supports "Stampa dettaglio voci" format (ERP detail reports with account-level GL entries)
- Supports "Situazione Contabile" trial balance format (CoGe LLM extractor primary, deterministic parser fallback)
- Pre-filters: Zucchetti, Datev/Koinos, Stampa dettaglio voci, Dylog separator noise
- Post-extraction validators: crediti, debiti split, equity consistency, ce20_imposte cross-check
- Maps extracted tables to sp01-sp18, ce01-ce20
- Both single-year and dual-year (both columns) extraction modes

#### Macro-area router (`importers/bilancio_classifier.py`)
Runs FIRST in `pdf_importer.import_pdf_balance_sheet` (on the text of the first ~14 pages) and decides
the extraction **route** — so each file is opened with the right rules and Assets=Liab+Equity does not
break. Replaces the old binary `is_trial_balance`. Full taxonomy + per-file mapping in
**`docs/import/IMPORT-ROUTING-TAXONOMY.md`** (77 unique docs analyzed; the 3 macro-areas cover 96% of real cases).

`classify_bilancio(file_path, text)` → `Classification(macro_area, subcategory, route, gestionale,
confidence, signals, reason)`. Three macro-areas + OTHER, each mapped to a route:
- **A** — synthetic IV-CEE (legal voci only, no CoGe account codes) → `ROUTE_IVCEE` (LLM extractor).
- **B** — same IV-CEE skeleton but exploded into sub-accounts (account codes present) → `ROUTE_IVCEE`
  (LLM, anchored on the declared **voce totals**; detail sub-accounts are ignored).
- **C** — sezioni contrapposte / situazione contabile (CoGe accounts Dare/Avere or Saldo, no legal
  schema) → `ROUTE_TRIAL`. **Primary extractor: a dedicated CoGe LLM pass**
  (`pdf_extractor_llm.extract_trial_balance_with_llm`) that reads Dare/Avere account balances and
  classifies general-ledger accounts into sp01–18 / ce01–20; the deterministic
  `situazione_contabile_parser` (balance via pareggio) is the **fallback** (no api_key, LLM failure, or
  empty LLM sheet). See the "CoGe LLM extractor" subsection below.
- **OTHER** — native `.xbrl`/`.xml` → `ROUTE_XBRL` (use the XBRL importer, not the PDF branch);
  CE-only / non-bilancio / over-aggregated → `ROUTE_UNSUPPORTED` (**honest error, never a silent plug**).

Decision logic (`compute_signals` + ordered rules):
- **Signals** are text markers (`itcc-ci-`, "TOTALE A PAREGGIO", "BILANCIO DI VERIFICA", "situazione
  contabile", "valore della produzione"), CoGe-code density (DEPI `XX/YY/ZZZ`, 8-digit, TeamSystem,
  dotted, BILAGRA `NNN.NNNNN`, single-column 6-digit), dotted CEE-path codes (`B.II.1.a`), and the
  coordinate detector `is_contrapposte_file` — all robust to letter-spaced headers via a no-spaces variant.
- **B beats C:** a file with the legal skeleton that *also* carries account codes (e.g. budget_313/314)
  routes to B (IV-CEE), NOT to the empty trial-balance parser — provided the strong C markers
  (pareggio/verifica/contrapposte) are absent.
- **C LLM-first with deterministic fallback:** `pdf_importer` runs the dedicated CoGe LLM extractor
  (`extract_trial_balance_with_llm`) FIRST when `api_key` is set; only if it is unavailable, errors, or
  returns an empty sheet (`totale_attivo==0`) does it fall back to the deterministic
  `situazione_contabile_parser`. That parser, when it in turn returns empty, still falls back to the
  IV-CEE LLM (`force_llm=True`). A no-key environment runs the deterministic parser as before (no
  regression). The deterministic plug-masking flag (`SC_PLUG_REJECT_PCT` = 20%, see the quadratura
  engine) still scales the `BILANCIO NON QUADRATO` warning severity on either route.
- `is_trial_balance = (classification.route == ROUTE_TRIAL)`. The result dict carries `macro_area` +
  `macro_subcategory` (logged + returned) so new formats surface as an area, not as a crash.

#### CoGe LLM extractor for trial balances (`importers/pdf_extractor_llm.py`)
`extract_trial_balance_with_llm(file_path)` is the route-C PRIMARY extractor. Unlike
`extract_pdf_with_llm` (which reads the legal IV-CEE schema), it sends the FULL trial-balance text
(`_extract_full_text`, no SP/CE section windowing — trial balances have no IV-CEE headers to anchor on)
and runs two Claude Haiku passes with **CoGe-specific system prompts**:
- `TRIAL_BALANCE_SP_SYSTEM_PROMPT` — teaches the Dare/Avere sign convention (Dare = asset/cost balance,
  Avere = liability/equity/revenue balance), contra-account **netting** (fondo ammortamento / fondo
  svalutazione crediti subtracted from the gross asset, never booked to passivo), the description→sp01–18
  mapping, and that the **year's result is implicit** (no result account → it is the Attivo-vs-Passivo gap).
- `TRIAL_BALANCE_CE_SYSTEM_PROMPT` — classifies economic accounts into ce01–20, all costs reported positive.

Output reuses the same `BalanceSheetExtraction`/`IncomeStatementExtraction` schemas (full DB field names),
then post-processes: `_normalize_ce_signs`, `_validate_crediti`/`_validate_debiti` (breakdown→aggregate
reconciliation), `_validate_ce10_against_bs`/`_validate_ce_imposte`, and finally
**`_balance_trial_via_result`** which enforces the pareggio identity by deriving `sp13` as
`totale_attivo − (passivo + PN excluding the result)` and recomputing the totals — so the sheet always
ties (`validate_balance` passes), mirroring the deterministic parser's pareggio. Scanned/image trial
balances are handled via `_extract_with_llm_vision` with the same CoGe prompts. Single-year only (trial
balances are rarely comparative); `prior_bs_data`/`prior_ce_data` stay `None`.

#### Trial-balance / Situazione Contabile parsers (`importers/situazione_contabile_parser.py`)
Deterministic, no LLM (now the route-C FALLBACK after the CoGe LLM extractor above).
`is_situazione_contabile(text)` + the coordinate-based
`is_contrapposte_file(path)` route a PDF to the right sub-parser inside
`extract_situazione_contabile`:
- **DEPI** `XX/YY/ZZZ` (incl. flat detail-only trial balances) and 2-part `XX/YYYY` + `XX/****`
- **AGO/ERP** 8-digit codes (`parse_entries_ago`)
- **Single-column** 6-digit "Saldo" layout (`parse_entries_single_column`)
- **TeamSystem** `XX/YYYY/YYYY` (`parse_entries_teamsystem`)
- **Contrapposte 8-digit** physical 2-column (`parse_entries_contrapposte_8digit`, coordinate split)
- **Verifica contrapposte PER SEGNO** (`is_bilancio_verifica_segno` + `parse_bilancio_verifica_segno`,
  tried FIRST inside `extract_situazione_contabile`): a "Bilancio di verifica" where accounts are placed
  in the Attività/Passività columns by the SIGN of their balance and the SAME account appears on BOTH
  sides (e.g. "Disponibilità liquide" = active banks in Attivo AND overdraft in Passivo). Splits the two
  columns by COORDINATE (gutter = x of the 2nd "Conto"/"Codice" header), classifies the 2-digit MASTRI by
  NATURE (description, side-aware — never by column), nets fondi ammortamento off sp02/sp03 (descriptions
  are PDF-truncated → match short substrings like `IMMATER`/`FORNITOR`/`ERARI`), separates overdraft-banks
  (sp16a) from cash (sp09), breaks debts into fornitori/banche/tributari/previdenza/altri, routes the
  result account to PN (portati a nuovo sp12g / prior result sp12e), and derives sp13 from the CE. SELF-
  VALIDATES attivo==passivo (raises `ValueError` → existing fallback, zero regression). Emits short
  aggregate keys + full-name sub-fields (sp06a, sp16a/d/e/f/g) that survive `_map_sc_keys`, plus
  `_skip_declared_reconcile=True` so `pdf_importer` skips the declared-result reconcile (which would
  mistake a prior-year "RISULTATO D'ESERCIZIO" equity account for the period result and inflate cash).
- **Generic contrapposte (best-effort)** for heterogeneous 2-column dumps (`extract_contrapposte_best_effort`):
  splits columns at the right-code-cluster x, and reconciles **mastri/subtotali to IV-CEE by description**
  (`_be_reclassify` descends the code hierarchy and stops at the coarsest level that maps to an IV-CEE
  field — no per-gestionale chart-of-accounts mapping). Fondi ammortamento are netted off assets, the
  current-year result is taken from the declared pareggio gap, and any residual from imperfect parsing is
  plugged into sp09/sp16 with a `BILANCIO NON QUADRATO` warning for manual correction in **Rettifiche**.
  - **Typed debiti split (2026-06-25):** the best-effort passivo classifier (`cl_pas`) now resolves each
    debt mastro's OIC creditor type via `_debt_type` (banche/altri-finanz/obbligazioni/fornitori/tributari/
    previdenza/altri) and emits the typed sub-field (sp16a..g, full DB name) ALONGSIDE the aggregate sp16 —
    instead of collapsing every debt into the aggregate, which the UI then renders entirely under "Altri
    debiti" (AITEC PROVVISORIO: 10.3M all in altri). The aggregate is unchanged (Σ typed == sp16) so the
    pareggio is untouched; sub-fields are display-only. `_debt_type` also routes bank financings
    ("FINANZIAMENTO <banca>", "FINANZ.<banca>", SBF) to banche, with soci/altri-finanziatori checked first.
  - **Gross/net anchoring** (`netted_contra`): when fondi ammortamento / svalutazione crediti are listed as
    separate PASSIVO accounts (gross presentation), the declared TOTALE ATTIVO / pareggio is GROSS. The
    netted contra mass is accumulated and subtracted from `iv_total`, so the IV-CEE NET total matches the
    netted asset/passivo sums (plug ~ 0 instead of ~ fondi). No-op when fondi sit on the asset side. This was
    the dominant cause of "QUADRATURA MASCHERATA" on gross-presentation trial balances.
  - **Code-collision aggregation** (`_be_reclassify`): two distinct accounts whose codes normalise to the
    same digit string are SUMMED, not overwritten (the old `info[c] = (d, a)` silently dropped the earlier
    amount, unbalancing the sheet and inflating the plug).
  - **Code-less second pass** (`_be_collect_side(codeless=True)` + `_be_split_codeless`): clean two-column
    trial balances whose rows are pure `description amount` with NO leading account code (e.g. budget_367:
    "Cassa 179,90 | Fornitori 296.099,94") collect zero rows in the code-required pass. Retried code-less
    ONLY when the normal pass found nothing (zero regression on coded files): each code-less row gets a
    unique non-prefixing synthetic code, the gutter is found by scanning for the most balanced split, and
    each column is truncated at its first section `TOTALE` so compact single-page SP+CE dumps don't book CE
    accounts as debts.
- **Empty→best-effort routing safety net** (`extract_situazione_contabile`): a structured/DEPI sub-parser
  that comes up EMPTY (`totale_attivo == 0`) on a file that is physically a 2-column contrapposte
  (`is_contrapposte_file`) has misrouted — `is_situazione_contabile()` matched a marker and shadowed the
  best-effort route, but no structured parser actually reads the layout (e.g. AITEC PROVVISORIO/BILANCINO,
  dotted `NNN.NNNNN` codes). The result is retried via `extract_contrapposte_best_effort` and kept only when
  non-empty. Purely additive (triggers only on an otherwise-empty result), so it cannot regress files the
  structured parsers already extract. Fixes the "Balance sheet does not balance / Failed to extract data"
  error on provvisori/infrannuali that the IV-CEE LLM fallback could not read.
- **Dotted-hierarchical mastri rescue** (`is_dotted_hierarchical` + `_hier_reconstruct`, hooked into the tail
  of `extract_contrapposte_best_effort`): the Sistemi/DEPI **"BILANCIO 4 SEZIONI"** family (codes `03.01.07`
  or `3 / 15 / 102`) lists every IV-CEE voce as a LEVEL-1 mastro WITH its correct subtotal, then dotted
  children. The generic best-effort normalises the code to digits and the deepest detail rows — printed with
  a TRUNCATED single-digit code (a finance instalment shown as `23`) — collide with a mastro number and
  inflate it → big sp09/sp16 plug ("QUADRATURA MASCHERATA"). The rescue anchors instead on the level-1 mastri
  taken in **document order** (a no-separator code is a mastro only when its OWN dotted children `code.` follow
  it before the next no-separator code, which rejects the truncated leaves), nets fondi ammortamento at any
  depth (`_is_fondo_amm`, incl. the aggregate "FONDI AMMORTAMENTO IMMOBILIZ" the rule table misses), and lets
  the current-year result emerge as the attivo/passivo gap (= ricavi − costi). It runs ONLY when the
  best-effort result is masked (plug > 1%) AND the file is dotted-hierarchical, and its output is kept ONLY
  when it self-validates: gross attivo (`att_sum + netted`) reconciles to the declared TOTALE ATTIVO within
  0.5% AND the SP gap equals the CE result within 0.5% — otherwise it returns `None` and the masked
  best-effort result stands unchanged (so it can never regress a file already balanced). Recovered the
  "ver_definitiva" 4-sezioni provvisori (budget_343/348) to clean quadratura; the slash-gross siblings
  (405/338) correctly fall back. Measured on the deterministic corpus the
  quadratura rate went 17→19 / 28 with zero regressions (`Test/_quadratura_harness.py`).
- **Unconsolidated prior-year result (2026-07-27)** (`_is_prior_result_caption` + `_hier_prior_result`,
  called from the SP-pages loop of `_hier_reconstruct`): a trial balance frequently does NOT consolidate
  the previous year's result into the capital/reserve accounts — it is printed as its OWN row, typically
  **code-less**, in the SP footer beside the totals ("Utile esercizio precedente 68.228,65"). `_hier_collect`
  keeps only rows carrying a leading account code, so that amount was dropped from the passivo side; the SP
  gap then over-stated the period result by exactly the prior-year amount and the rescue's CE cross-check
  rejected an otherwise EXACT reconstruction (budget_342: gate 1 delta 0,00, gate 2 off by 68.228,65 →
  fell back to a 60%-masked best-effort → hard "non supera i controlli contabili" import failure). The
  amount now lands in `sp12` (utili/perdite portati a nuovo). Only **code-less** rows are collected — a
  coded prior result already sits inside a level-1 mastro (e.g. "23 CAPITALE E RISERVE") and would double-
  count. Sign follows the caption (perdita → negative) and the column (attivo side → negative, a debit
  balance). The CURRENT period result ("Utile del periodo", "Utile d'esercizio") is explicitly NOT matched:
  it stays the balancing figure derived from the Attivo/Passivo gap. Row clustering uses
  `_be_cluster_physical_rows` because the caption and its amount sit on different baselines (~2 pt apart).
  Still behind both self-validation gates, so it cannot apply wrong values to a file that already balances.
  Tests: `tests/test_prior_result_in_pn.py`.

#### Balance hardening (anti-masking)
- `pdf_mapper.validate_balance` fails when `totale_attivo == 0` or when the aggregate sub-totals
  (sp01–sp10 / sp11–sp18 incl. sp13) do not reconstruct the declared totals — no more false positives
  on empty/plugged extractions.
- LLM correctors in `pdf_extractor_llm.py` no longer apply negative or oversized plugs silently: they cap
  the correction, never drive a field below zero, and emit `BILANCIO NON QUADRATO` instead of hiding the gap.
- Dual-year extraction discards a fabricated prior year when the PDF has a single amount column.
- `ce03_lavori_interni` is included in the Valore della Produzione (both years); extracted imposte are not
  overwritten to force the profit cross-check.
- **Malformed Haiku column tolerance** (`pdf_extractor_llm._coerce_year_blob`): with the nested two-year
  tool schema, Haiku sometimes serialises a whole `current_year`/`prior_year` column as a JSON-ish *string*
  using Italian number formatting (`1.234.567,89`). A `field_validator(mode="before")` `json.loads` it,
  retrying after normalising Italian numbers — so one bad column no longer fails the entire import.
- **Broad SP-window end anchors** (`SP_END_KEYWORDS`): the SP page range closes on any "Totale … passivo/
  passività" variant ("Totale STATO PATRIMONIALE passivo", "Totale passivo e patrimonio netto", …), not just
  the literal "totale passivo" — a too-narrow match truncated the SP window before the passivo pages and
  broke the balance.
- **Zeroed-leading-section guard** (`find_section_pages`): draft "provvisorio" exports that render the IV-CEE
  schema with every amount at `0,00` up front, then the real figures later, would lock detection onto the
  zero copy (→ empty BS). When the selected SP pages carry negligible amount mass vs the largest data page,
  the SP/CE windows slide forward to a genuine second copy that re-states the SP header AND carries real
  amounts. Deliberately does NOT relocate to a headerless number-only dump — those fail honestly instead.

#### IV-CEE detail-line reconciler (`_reconcile_pn_detail` / `_reconcile_personale_detail`, `pdf_extractor_llm.py`)
Clean IV-CEE statements print every legal sub-line verbatim, but the LLM only captures the AGGREGATES
(`sp12_riserve`, `ce08_costi_personale`). Two deterministic post-LLM passes (text-path only, hooked into
BOTH the single-year and the dual-year extractors) re-read the explicit lines and fill the sub-fields:
- `_reconcile_pn_detail` reads the patrimonio-netto reserve rows **A.II–A.X → sp12a..h** and recomputes
  `sp12_riserve` as their ALGEBRAIC sum — recovering a dropped NEGATIVE reserve ("A.VIII utili (perdite)
  portati a nuovo"), which otherwise inflates equity and gets MASKED into cash by the balance reconcile
  (e.g. LIO 2025 cash 106.156 → 150.156). Applied ONLY when `sp11+Σsp12*+sp13` reconciles to the printed
  "Totale patrimonio netto" (anti-masking); note `_validate_equity` REFUSES the same correction because it
  yields negative reserves, so this deterministic pass — anchored on the printed lines — is what fixes it.
- `_reconcile_personale_detail` reads **B.9 a/b/c/e → ce08b** salari / **ce08c** oneri / **ce08a** TFR /
  **ce08d** altri (gated on "Totale costi per il personale"), fixing the merged salari+oneri the LLM emits.
  The CE cost line "c) trattamento di fine rapporto" is disambiguated from the SP fund line "C) Trattamento
  di fine rapporto di lavoro subordinato" (sp15) via a `(?!\s+di\s+lavoro)` lookahead.
No-op on layouts without the explicit legal lines / when the control-total gate fails (zero regression).
`pdf_importer._create_income_statement` now persists ce08b/c/d (DB columns that existed but weren't written).
- **Gestionale-format coverage (2026-06-25):** `_PN_DETAIL_SPECS`/`_PN_TOTAL_SPECS` accept an optional `A.`
  legal-path prefix; the numeral may be followed by a `)`/`-` separator **OR just whitespace**
  (`(?:\s*[-–)]\s*|\s+)`, so `IV   Riserva legale` with no separator is matched — budget_315); the required
  whitespace still disambiguates V/VI/VII/VIII. The PN control total also matches `A) Patrimonio netto`
  (header carrying the subtotal) and `A TOTALE PATRIMONIO NETTO`. `_values_for_label` skips ONE interposed
  `Totale <voce>` line so the voce amount stays reachable when a pre-filter (Zucchetti) reorders the detail
  block below its "Totale" line. Recovers the dropped NEGATIVE reserve (`A.VIII` Utili portati a nuovo) on
  FLUIVER (budget_340/341), Zucchetti holdings (budget_331) and the BERTELLI provvisorio (budget_315) — same
  masking class as LIO 2025. Still gated by the declared-PN reconcile, so it can never apply wrong values to
  a balanced file. **Monocolumn fix:** `extract_pdf_both_years_with_llm` no longer RETURNS early on a
  monocolumn PDF (`_prior_column_is_absent`) — it empties the prior dicts but lets the Step 5-7 validators +
  `_reconcile_pn_detail` still run on the CURRENT column, so a monocolumn provvisorio (budget_315) gets its
  reserve recovered on the dual-year path too (the single-year `extract_pdf_with_llm` already did).
- **Crediti scoping (anti double-count):** the SP prompt now scopes sp06/sp07 to **C.II Attivo circolante
  only**, explicitly excluding **B.III.2 crediti immobilizzati** (which belong to sp04). Counting a B.III.2
  credito in sp07 too double-counted it and unbalanced the sheet by that amount (budget_315).
- **Zeroed CURRENT column (`extract_pdf_both_years_with_llm` Step 4c):** draft exports that render the
  current-year column at `0,00` with the real figures only in the PRIOR column (budget_314 "anno corrente
  azzerato") would import as VUOTO. When current `totale_attivo ~ 0` and prior is valued, the prior column
  is promoted to current. Symmetric to and mutually exclusive with the Step 4b monocolumn guard.

#### CE↔SP identity enforcement (`enforce_ce_sp_identity`, `importers/iv_cee_hierarchy.py`)
The year's result is ONE number: it appears as `sp13` in the balance sheet AND as the last line of
the income statement. SP and CE are extracted separately and can diverge → the app's "Verifica CE↔SP"
fails. `enforce_ce_sp_identity(bs, ce, prefer=…, declared=…)` runs in `pdf_importer.import_pdf_balance_sheet`
**after every route's block and BEFORE `validate_balance`** (route C, route A/B, AND native XBRL — the
`utile_CE` rebuilt from CE tags can diverge from the tagged `sp13`, e.g. budget_361/404). It forces
`utile_CE == sp13` with direction decided by route + an arbiter:
- **Default** `prefer="sp13"`: trust `sp13` (anchored to pareggio; on route C already = declared result)
  and align the CE — plug into `ce12_oneri_diversi` if the CE is too high / `ce04_altri_ricavi` if too low —
  with a `_ce_sp_plug` flag.
- **Arbiter = declared result** (`declared=…`): whichever of `sp13`/`utile_CE` is closest to the declared
  Utile/Perdita wins.
  - declared confirms the **CE** → `sp13` held the **prior** year's result: move it to `utile_CE` and route
    the difference into reserves (`sp12`) — total PN and Attivo=Passivo unchanged (relabel within PN only).
    Cap 10% of passivo, reserves stay non-negative, else fall back to aligning the CE.
  - declared confirms **`sp13`** → the CE is wrong (sign/parse bug, e.g. budget_402/413) → align the CE,
    `sp13` is NOT touched.
- No-op when they already coincide. Guarantees CE↔SP on every file without corrupting a correct `sp13`.

#### IV-CEE leveling + quadratura engine (`importers/iv_cee_hierarchy.py`)
Shared stage DOWNSTREAM of the 4 macro-area routes (A/B/C/OTHER stay separate — this is NOT a
router). One canonical taxonomy + one quadratura check for every bilancio, not per-file patches.
- **`data/iv_cee_tree.json`** — canonical IV-CEE statement tree (art. 2424/2425). Each node:
  `path/level (1=letters,2=roman,3=arabic,4=a/b/c)/side/db_field/aliases/is_legal_leaf/is_total/netting`.
  Legal leaves cover all sp01–18 + ce01–20. Deliberately LEGAL-LEVEL only (no chart-of-accounts
  sub-conto aliases — that would double-count in flat A/B aggregation).
- **`resolve(desc, side)`** — shared description→IV-CEE-node classifier (conservative: `None` when
  unsure, so `_be_reclassify` descends instead of misrouting). **Do NOT use it to override the
  attivo/passivo SIDE** of a trial-balance line: the COLUMN is ground truth; ambiguous accounts
  (`ERARIO C/`, `DEPOSITI BANCARI`=overdraft, `FORNITORI C/ANTICIPI`, `INAIL C/`) flip side by
  column, not description (tried + reverted — regressed clean files).
- **`check_quadratura(bs, ce)`** — Attivo==Passivo + CE utile==sp13 cross-check + **anti-masking**:
  reads `bs['_plug_residual']` (exposed by the best-effort contrapposte parser, survives `_map_sc_keys`);
  `masked=True` when the plug exceeds 1% of total (the balance only ties because the unclassified
  residual was swept into sp09/sp16). `is_empty=True` when `totale_attivo ~ 0` — an empty extraction is a
  FAILURE, not a pass (without this, att==pas==0 gives sbilancio 0 → falsely "quadra", which hid the empty
  extractions of misrouted contrapposte files). `quadra` requires `not is_empty and not masked`. Used as a
  unified diagnostic in `pdf_importer` for ALL routes and as the harness's pass/fail signal.
- **Route-C extractor selection by completeness (2026-06-25):** `pdf_importer` runs BOTH the CoGe LLM and
  the deterministic best-effort parser and keeps the better candidate. The score is now PRIMARILY the gap
  between each candidate's `totale_attivo` and the **declared control total** (`_declared_control_totals`
  pareggio/passivo/attivo), with `_plug_residual` only as the tiebreaker. Reason: `_plug_residual` alone is
  blind to under-extraction — the CoGe LLM (Haiku) can stochastically DROP a block of accounts and then
  force-balance via sp13 (residual ~0 → looks clean) while its total falls well short of the printed TOTALE
  (AITEC PROVVISORIO: CoGe 9.92M vs declared 12.65M, so the deterministic parser, which anchors to the
  printed total AND now splits debiti, correctly wins). The gap is ignored below 2% of the declared total so
  ordinary noise still defers to the residual tiebreaker; when no declared total is found, behaviour is the
  old residual-only selection (no regression).
- **Contra-netting overlay (2026-07-06)** (`situazione_contabile_parser.net_contra_accounts`,
  called in `pdf_importer` route C after `overlay_debt_typing`): deterministic post-extraction
  netting of fondi ammortamento (+ offsettable IVA, both-sides-only) on the CHOSEN candidate.
  Re-scans the SP pages (coordinate mode; OCR-text fallback), dedupes mastro/dettaglio, then
  OVERWRITES sp02/sp03 with net values and removes from the debt buckets exactly the passivo
  excess over the new attivo (capped at the fondi mass) — idempotent on an already-net sheet.
  Two gates or no-op: netted > 1% of declared total AND scan gross attivo ≈ declared total
  (0.5%). The declared anchor passed to `_reconcile_trial_to_declared` is reduced by the netted
  mass (printed totals are GROSS on these files) so the reconcile cannot re-inflate it as a
  false plug. Tests: `tests/test_contra_netting.py`; corpus check: `tests/run_contra_regression.py`.
- **Trial-balance import is never hard-blocked** (`pdf_importer`): a readable route-C situazione
  contabile ALWAYS imports. The route now tries the dedicated **CoGe LLM extractor first**
  (`extract_trial_balance_with_llm`, which DOES read CoGe account lists); when that is unavailable or
  empty, the deterministic best-effort parser plugs to balance (validate_balance passes), so a non-empty
  result is imported with a `BILANCIO NON QUADRATO` flag scaled to the plug (`SC_PLUG_REJECT_PCT` now
  only sets the warning severity "parziale" vs "prevalentemente stimata"), for correction in Rettifiche —
  NOT rejected. NOTE: the distinction is between the two LLM passes — the **IV-CEE** LLM
  (`extract_pdf_with_llm`, `force_llm=True`) is the WRONG fallback for a trial balance (it reads
  legal-schema bilanci, not CoGe account lists) and on a contrapposte file returns an unbalanced
  extraction → the generic "Balance sheet does not balance / Failed to extract data" hard error; so the
  IV-CEE LLM is the last resort ONLY when the deterministic parse is genuinely EMPTY (no Stato
  Patrimoniale at all). The new CoGe LLM pass is purpose-built for CoGe lists and is the preferred
  primary. This is what makes every readable trial balance open instead of erroring.
- **`Test/_quadratura_harness.py`** — measures the quadratura rate over a corpus (deterministic routes
  by default; `--llm` to include A/B). Baseline tool for before/after of any import change.
  **CAVEAT (do NOT confuse with "does it import?"):** the harness runs `extract → check_quadratura` but
  NOT the two production stages `pdf_importer` runs right after extraction — `reconcile_ivcee_balance`
  (anchors to the declared Totale attivo, plugs the small source rounding → Rettifiche flag) and
  `enforce_ce_sp_identity`. So a harness "NO" is NOT "won't import": many route-A/B files the harness
  marks NO actually IMPORT in the app (e.g. budget_152/254/289/336). The harness is authoritative only
  for **masking** (plug > 1% on route C). To answer "does this PDF import?", run the full production path
  (extract → `reconcile_ivcee_balance` → `enforce_ce_sp_identity` → `validate_balance`). Also: route-A/B
  LLM extraction is **non-deterministic**, so harness SI/NO can flip between runs on the same file (LLM
  noise, not a regression) — confirm suspected regressions on the production path, not a single harness run.
- **"Formato non supportato" messaging** (`pdf_importer._is_aggregated_summary`): at the `validate_balance`
  failure point, a document with NO legal IV-CEE substructure (no roman-numeral sub-items, no "esigibili
  entro/oltre", no account codes) — an over-aggregated / AI-generated riepilogo, NOT an art. 2424/2425
  schema (budget_133/135/137/150) — raises a clear "Formato non supportato" error instead of the cryptic
  "does not balance". Gated on the balance failure, so it can NEVER reclassify a file that imports; real
  schemas that simply don't tie at source keep the "BILANCIO NON QUADRATO" honest-fail / Rettifiche path.
- `situazione_contabile_parser._be_split` picks the column gutter that BALANCES description-bearing
  rows on both sides (centre as tiebreaker), not the widest gap (which sliced the passivo column).

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
- **CE overrides**: Every CE field (31 total) can be overridden with an absolute EUR value. Override takes precedence over growth-% calculation. `None` = use engine calculation.
- **Auto-derived turnover days**: When DSO/DIO/DPO not explicitly set in assumptions, derived from base year ratios (e.g., `DSO = base_sp06 / base_revenue * 360`). Working capital always scales proportionally with revenue/cost changes — including when revenue is changed via CE override.
- **Override clearing**: `POST /generate?clear_overrides=true` nulls all `*_override` columns on all assumption rows before regenerating. Uses dynamic `__table__.columns` introspection. It is triggered ONLY by the budget page "Ricalcola" dialog when the user ticks *"Azzera le modifiche manuali del CE previsionale"* (default off). "Salva e Calcola Previsionale" **never** clears overrides — it saves via the bulk PUT (`auto_generate=true`) sending full hydrated rows, so overrides made on `/forecast/income` survive the save.

### Editable Forecast Income Statement (CE Overrides)
User can manually edit any P&L line in forecast year columns on `/forecast/income`. Edits are collected locally, then batch-saved with "Aggiorna Previsionale". The BS adapts automatically: more revenue → more receivables (via DSO), more costs → more payables (via DPO), cash as plug.

- **Override fields**: 31 `ce*_override` columns on `BudgetAssumptions` — one per editable CE field (ce01–ce20 plus sub-fields ce08a–d, ce09a–d, ce11b, ce17a/b). Nullable; `NULL` = use engine calculation.
- **Batch endpoint**: `PATCH /scenarios/{id}/ce-override` accepts `{ overrides: [{ forecast_year, field, value }] }`. Applies all overrides to the assumptions rows, then regenerates forecast once.
- **Frontend flow**: Click forecast cell → inline input → blur/Enter saves to `pendingEdits` state (yellow highlight) → "Aggiorna Previsionale" button appears → click sends all pending edits via batch endpoint → analysis cache invalidated → table refreshes.
- **Clearing overrides**: Empty a cell's input to send `null` (reverts to engine value). From `/budget`, "Salva e Calcola" saves via bulk PUT and **preserves** overrides; only the "Ricalcola" dialog's *"Azzera le modifiche manuali del CE previsionale"* checkbox wipes all overrides via `POST /generate?clear_overrides=true`.
- **Visual indicators**: Pending edits = yellow background + yellow underline. Server-persisted overrides = blue underline. Override status read from `assumptions` object in analysis response.
- **Key files:**
  - `database/models.py` — `BudgetAssumptions.ce*_override` columns
  - `backend/app/schemas/budget.py` — Pydantic schemas for all override fields
  - `backend/app/api/v1/budget_scenarios.py` — `PATCH /ce-override`, `POST /generate?clear_overrides=true`
  - `calculations/forecast_engine.py` — Override checks in `_calculate_income_statement`, auto-derived DSO/DIO/DPO in `_calculate_balance_sheet`
  - `frontend/app/forecast/income/page.tsx` — `FIELD_TO_OVERRIDE` map, `EditableCell`, `pendingEdits` state, batch save
  - `frontend/app/budget/page.tsx` — `ScenarioForm` (2 tab: Informazioni / Ipotesi) renders a config-driven `AssumptionsGrid` (`components/budget/AssumptionsGrid.tsx` + `assumption-rows.ts`): ~11 essential rows + an "Avanzate" accordion; "Salva e Calcola" → `bulkUpsertAssumptions(auto_generate=true)`; Ricalcola dialog → `generateForecast(clearOverrides)` only when the azzera checkbox is ticked
  - `frontend/lib/api.ts` — `patchCeOverrides()`, `generateForecast(clearOverrides)`

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
  - REPLACES an existing full-year FinancialYear for that company+year (re-promote); deletes it with cascade before creating the new record — a manually imported full year for the same year is overwritten
  - Quadratura gate: refuses to promote a projection whose BS is unbalanced (attivo−passivo > €5)
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

# CE Override: Edit individual forecast P&L values after generation
PATCH /scenarios/{id}/ce-override
{
  "overrides": [
    {"forecast_year": 2026, "field": "ce01_override", "value": 1750000},
    {"forecast_year": 2026, "field": "ce08_override", "value": 230000},
    {"forecast_year": 2027, "field": "ce01_override", "value": 1820000}
  ]
}
# Applies overrides to assumptions, regenerates forecast once
# Returns: {success: true, applied: 3}

# Regenerate with override reset (used by budget page Ricalcola / Salva buttons)
POST /scenarios/{id}/generate?clear_overrides=true
# Nulls all *_override columns, then regenerates from growth percentages
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

  // (Optional) Edit forecast P&L values directly on /forecast/income
  await api.patchCeOverrides(companyId, scenarioId, [
    { forecast_year: 2026, field: "ce01_override", value: 1750000 },
    { forecast_year: 2026, field: "ce08_override", value: 230000 },
  ])
  // BS auto-adapts: more revenue → more receivables, more costs → more payables

  // Regenerate from budget page resets all manual edits
  await api.generateForecast(companyId, scenarioId, true)  // clear_overrides=true
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
- `/forecast/income` - Forecast P&L (editable: click forecast cells → batch save → BS auto-adapts)
- `/forecast/balance`, `/forecast/reclassified` - Forecast BS views (read-only, adapts to CE overrides)
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
