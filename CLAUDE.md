# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**XBRL Budget** is an Italian GAAP compliant financial analysis and credit rating system. It analyzes Italian company financial statements, calculates comprehensive financial ratios, and provides credit risk assessments using Altman Z-Score and FGPMI rating models.

**Key Domain:** Italian accounting (OIC - Organismo Italiano di Contabilità) with specialized XBRL import for Italian taxonomies.

**Architecture:** The project contains two applications:
- **Modern Stack (Production)**: FastAPI REST API + Next.js 15 frontend
- **Legacy App (Deprecated)**: Streamlit web application in `/legacy` directory

Both applications share the same core modules (`database/`, `calculations/`, `importers/`) and SQLite database.

## Quick Reference

**Project Root:** `/home/peter/DEV/budget/`

**Key Directories:**
- `backend/` - FastAPI REST API (uses shared modules from root)
- `frontend/` - Next.js 15 React frontend (TypeScript, API client only)
- `database/` - **SHARED** SQLAlchemy ORM models (837 lines, used by both apps)
- `calculations/` - **SHARED** Financial calculators (ratios, Altman, FGPMI, forecasting)
- `importers/` - **SHARED** XBRL and CSV parsers
- `data/` - **SHARED** Taxonomy mappings, rating tables, sector definitions
- `config.py` - **SHARED** Configuration constants
- `legacy/` - Old Streamlit app (deprecated, preserved for reference)
- `financial_analysis.db` - **SHARED** SQLite database in project root

**Run Modern Stack:**
```bash
# Terminal 1: Backend
cd backend && source venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# Terminal 2: Frontend
cd frontend && npm run dev
```

**Important:** Backend imports shared modules from project root via `sys.path` manipulation in `backend/app/main.py`. No code duplication - single source of truth for all business logic.

## Development Commands

### Modern Stack (FastAPI + Next.js) - **RECOMMENDED**

#### Backend Setup
```bash
cd backend
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

# Initialize database (first time only - from project root)
cd ..
python -c "from database.db import init_db; init_db()"
```

#### Running Backend API
```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# API available at:
# - http://localhost:8000/api/v1
# - http://localhost:8000/docs (Swagger UI)
```

#### Frontend Setup
```bash
cd frontend
npm install
# or: pnpm install / yarn install
```

#### Running Frontend
```bash
cd frontend
npm run dev
# or: pnpm dev / yarn dev

# Frontend available at: http://localhost:3000
```

### Legacy App (Streamlit) - **DEPRECATED**

```bash
cd legacy
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r ../requirements.txt

# Run Streamlit app
streamlit run app.py

# Application will be available at http://localhost:8501
```

**Note:** The Streamlit app is maintained for reference only. All new development should use the FastAPI + Next.js stack.

## Application Features

### Modern Frontend (Next.js) - Primary Interface

**Pages/Routes** (in `frontend/app/`):
1. **Home** (`/`) - Dashboard with company overview
2. **Import** (`/import`) - XBRL/CSV data import interface
3. **Budget** (`/budget`) - Budget scenario creation and assumptions input
4. **Analysis** (`/analysis`) - Financial ratios, Altman Z-Score, FGPMI Rating
5. **Cash Flow** (`/cashflow`) - Cash Flow Statement (indirect method)
6. **Forecast - Income** (`/forecast/income`) - Income Statement projections
7. **Forecast - Balance** (`/forecast/balance`) - Balance Sheet projections
8. **Forecast - Reclassified** (`/forecast/reclassified`) - Reclassified indicators with charts

**Global State** (via `AppContext.tsx`):
- Selected company and year
- Available companies list
- Financial data caching

### Legacy App (Streamlit) - Horizontal Tab Navigation

Located in `/legacy/app.py`. Uses **horizontal tabs** at the top for navigation.

**Top Selection Bar**:
- Company selector, Year selector, Sector display, P.IVA display

**Main Tabs**: Same features as modern frontend but in Streamlit UI

### Testing

```bash
cd legacy

# Run individual test files (no pytest runner configured)
python test_db.py                 # Database models and relationships
python test_calculations.py       # Financial ratios, Altman, working capital
python test_fgpmi.py              # FGPMI rating model
python test_csv_import.py         # CSV importer (TEBE format)
python test_xbrl_import.py        # XBRL parser
python test_bkps_xbrl.py          # Real XBRL data validation

# Tests use drop_all() and init_db() to reset database state
```

### Database Operations

```bash
# Reset database (WARNING: deletes all data)
# Run from project root
python -c "from database.db import drop_all, init_db; drop_all(); init_db()"

# Database migration (if schema changes)
cd legacy
python migrate_db.py
```

**Database Location:** `/home/peter/DEV/budget/financial_analysis.db` (project root)
- Shared by both modern and legacy applications
- Uses absolute path configuration to ensure consistency

## Architecture

### Project Structure

```
budget/
├── backend/                    # FastAPI Backend (Modern)
│   └── app/
│       ├── main.py             # FastAPI entry point
│       ├── api/v1/             # REST API endpoints
│       ├── schemas/            # Pydantic request/response models
│       ├── services/           # Business logic layer
│       ├── calculations/       # Backend-specific calculations (cashflow)
│       └── core/               # FastAPI config, database dependency injection
│
├── frontend/                   # Next.js Frontend (Modern)
│   ├── app/                    # Next.js pages (App Router)
│   ├── components/             # React components
│   ├── contexts/               # Global state (AppContext)
│   ├── lib/api.ts              # Axios API client
│   └── types/api.ts            # TypeScript interfaces
│
├── database/                   # SHARED: SQLAlchemy ORM Models
│   ├── models.py               # All database models (837 lines)
│   └── db.py                   # Engine, session, Base, init_db()
│
├── calculations/               # SHARED: Financial Calculators
│   ├── base.py                 # Base calculator utilities
│   ├── ratios.py               # Financial ratios
│   ├── altman.py               # Altman Z-Score
│   ├── rating_fgpmi.py         # FGPMI Rating model
│   └── forecast_engine.py      # 3-year budget projections
│
├── importers/                  # SHARED: Data Import Parsers
│   ├── xbrl_parser.py          # Italian XBRL parser
│   ├── xbrl_parser_enhanced.py # Enhanced with hierarchical debts
│   └── csv_importer.py         # TEBE CSV format importer
│
├── data/                       # SHARED: Configuration Data
│   ├── taxonomy_mapping.json   # XBRL taxonomy mappings (2011-2018)
│   ├── taxonomy_mapping_v2.json # Enhanced mappings
│   ├── rating_tables.json      # FGPMI rating thresholds per sector
│   └── sectors.json            # Sector definitions
│
├── config.py                   # SHARED: Configuration constants
├── financial_analysis.db       # SHARED: SQLite database (root)
│
└── legacy/                     # Legacy Streamlit App (Deprecated)
    ├── app.py                  # Streamlit entry point
    ├── ui/pages/               # Streamlit pages
    ├── reports/                # Report generation
    ├── tests/                  # Test suite
    └── sample_data/            # Sample XBRL/CSV files
```

### Multi-Layer Calculator Architecture

The system uses a **layered calculation architecture** where each module builds on lower layers:

1. **Base Layer** (`calculations/base.py`): Common utilities (safe_divide, rounding, Excel-like functions)
2. **Financial Ratios** (`calculations/ratios.py`): Liquidity, solvency, profitability, activity ratios
3. **Risk Models** (`calculations/altman.py`, `calculations/rating_fgpmi.py`): Use ratios + raw financials
4. **Forecasting Engine** (`calculations/forecast_engine.py`): Generates 3-year projections based on assumptions

**Important:** Calculators work with **SQLAlchemy ORM objects** (BalanceSheet, IncomeStatement), not dictionaries. They use `Decimal` for all monetary calculations to avoid floating-point precision issues.

### Data Flow

**Modern Stack (FastAPI + Next.js):**
```
XBRL/CSV File
    ↓
Next.js Frontend (Upload)
    ↓ HTTP POST
FastAPI Backend (/api/v1/import)
    ↓
Importers (xbrl_parser.py, csv_importer.py)
    ↓
Database Models (database/models.py)
    ↓
SQLite Database (financial_analysis.db)
    ↓
Calculators (calculations/*.py)
    ↓ JSON Response
Next.js Frontend (Display)
```

**Legacy Stack (Streamlit):**
```
XBRL/CSV Import → Database (SQLite) → Calculator Layer → Streamlit UI → Charts/Tables
     ↓                ↓                       ↓
Taxonomy Mapping   ORM Models        Decimal-based math
(data/*.json)    (database/models.py)  (calculations/*.py)
```

**Critical Path (Both Applications):**
1. **Import**: XBRL Parser (`importers/xbrl_parser.py`) or CSV Importer → Creates Company/FinancialYear/BalanceSheet/IncomeStatement
2. **Calculation**: Instantiate calculator with ORM objects → Call calculate() → Returns NamedTuple results
3. **Display**:
   - Modern: Backend serializes to JSON → Frontend renders with Recharts
   - Legacy: Streamlit pages (`legacy/ui/pages/*.py`) fetch data → Render with Plotly charts

**Shared Module Import Pattern:**
- Backend: Uses `sys.path.insert(0, project_root)` in `backend/app/main.py` to import shared modules
- Legacy: Imports shared modules directly (runs from project root)
- Database: Both use `database.db` which configures absolute path to root database file

### Database Schema

**Location:** `/home/peter/DEV/budget/financial_analysis.db` (project root, shared by all apps)

**Core Models** (`database/models.py` - 837 lines):
- `Company`: Master data (name, tax_id, sector 1-6)
- `FinancialYear`: Container linking company to financial statements for a specific year
- `BalanceSheet`: Balance sheet with detailed debt breakdown
  - Standard fields: sp01-sp18 (follows Italian civil code art. 2424)
  - Hierarchical debts: sp16a-g (banks, financial, bonds, suppliers, tax, social security, other)
  - Split by maturity: short-term (breve) and long-term (lungo)
- `IncomeStatement`: 20 line items (ce01-ce20), follows Italian civil code art. 2425

**Forecasting Models** (for 3-year budget projections):
- `BudgetScenario`: Scenario metadata (name, base year, active flag)
- `BudgetAssumptions`: Growth percentages per year (revenue, costs, investments)
- `ForecastYear`: Links scenario to forecast financial statements
- `ForecastBalanceSheet`, `ForecastIncomeStatement`: Projected financials (same structure as historical)

**Key Relationships:**
- One Company → Many FinancialYears
- One FinancialYear → One BalanceSheet + One IncomeStatement
- One BudgetScenario → Many ForecastYears
- One ForecastYear → One ForecastBalanceSheet + One ForecastIncomeStatement
- All use cascade="all, delete-orphan" (deleting company removes all child records)

**Database Access:**
- Backend: `from database.db import Base, engine, SessionLocal, init_db, drop_all`
- Legacy: Same imports (both use absolute path configuration)

### Sector-Specific Logic

The application implements **sector-specific formulas** for Italian industries:

**Sectors** (config.py Sector enum):
1. INDUSTRIA (Manufacturing, Hotels-owners, Agriculture, Fishing)
2. COMMERCIO (Commerce/Retail)
3. SERVIZI (Services, Hotels-lessees)
4. AUTOTRASPORTI (Transport)
5. IMMOBILIARE (Real Estate)
6. EDILIZIA (Construction)

**Sector determines:**
- Altman Z-Score coefficients (Manufacturing uses 5-component model, others use 4-component)
- FGPMI indicator thresholds (stored in `data/rating_tables.json`, loaded per sector)
- Default ratio interpretation benchmarks

### XBRL Taxonomy Mapping

**Supported Taxonomies**: 2011-01-04 through 2018-11-04 (Italian XBRL standards)

**Critical Files:**
- `data/taxonomy_mapping.json`: Maps XBRL tags → internal codes (sp01-sp18, ce01-ce20)
- `importers/xbrl_parser.py`: Detects taxonomy version, extracts values, handles different balance sheet types (Ordinario/Abbreviato/Micro)

**Pattern Recognition**: Parser detects schema type by row count (config.TAXONOMY_ROW_COUNTS), then applies appropriate mapping.

## Key Conventions

### Naming Conventions
- **Italian codes**: Balance sheet items = `sp01-sp18`, Income statement = `ce01-ce20`
- **Aggregates**: `TA` (Total Assets), `CN` (Equity), `MOL` (EBITDA), `RO` (EBIT) - see config.NAMED_RANGES
- **Database columns**: Use full Italian names (e.g., `sp03_immob_materiali`, `ce01_ricavi_vendite`)
- **Calculator results**: Return NamedTuples (WorkingCapitalMetrics, LiquidityRatios, AltmanResult, etc.)

### Financial Calculations
- **Always use Decimal**: Import from decimal module, never use float for money
- **Zero-division protection**: Use `BaseCalculator.safe_divide()` (returns default value)
- **Rounding**: Use `BaseCalculator.round_decimal()` with config.DECIMAL_PLACES
- **Percentage format**: Stored as absolute values (25.5 = 25.5%), not decimals (0.255)

### Italian Accounting Standards (OIC)
- **Balance Sheet must balance**: Assets = Equity + Liabilities (tolerance: €0.01)
- **Working Capital** (CCN): Current Assets - Current Liabilities
- **EBITDA** (MOL): EBIT + Depreciation + Amortization
- **EBIT** (RO): Operating Revenue - Operating Costs (before financial items)
- **Tax Rate**: 24% IRES (Italian corporate tax) used in forecasting

### State Management

**Modern Frontend (Next.js):**
- Global state managed by `AppContext.tsx` (React Context API)
- Company/year selection persisted in context
- API calls via `lib/api.ts` (Axios client)
- TypeScript interfaces in `types/api.ts`

**Legacy App (Streamlit):**
- `st.session_state.db`: Cached database session (initialized once via @st.cache_resource)
- `st.session_state.selected_company_id`: Currently selected company
- `st.session_state.selected_year`: Currently selected fiscal year
- **Pattern**: Sidebar handles company/year selection, pages read from session_state, call database queries, pass results to calculators.

## Important Implementation Notes

### XBRL Import Gotchas
- XBRL files may contain multiple contexts (dates) - parser must select correct period
- Values are in full euros (not thousands) - no scaling needed
- Taxonomy version affects tag names - use version detection before mapping
- Abbreviated/Micro schemas have fewer line items - map to closest standard item

### FGPMI Rating Model
- **Complex multi-table lookup**: Loads 7 indicator tables from JSON per sector
- **Score ranges**: Each indicator has sector-specific thresholds (excellent/good/sufficient/poor)
- **Revenue bonus**: +2 points if revenue > €500K
- **Rating classes**: 13 classes (AAA → B-), calculated from total points/max points percentage
- **Data location**: `data/rating_tables.json` contains all threshold tables

### Forecasting Engine Logic
- **Base year**: User selects historical year as baseline
- **Projection years**: Default 3 years forward
- **Cost split**: Variable (60%) vs Fixed (40%) for materials/services
- **Cash as plug**: Balance sheet balances by adjusting cash (sp09_disponibilita_liquide)
- **Negative cash**: If cash goes negative, increase short-term debt (sp16_debiti_breve)
- **Integration**: Forecast statements stored in separate tables but use same calculator classes

### CSV Import (TEBE Format)
- **Format**: Semicolon-delimited (config.CSV_DELIMITER = ";")
- **Encoding**: UTF-8 with HTML entity cleanup (`&nbsp;`, accented characters)
- **Structure**: Rows = accounts, Columns = years (up to 2 years per import)
- **Mapping**: Uses account descriptions (Italian text) to match internal codes

## Common Tasks

### Adding a New Financial Ratio
1. Add calculation method to `FinancialRatiosCalculator` class in `calculations/ratios.py`
2. Add to appropriate NamedTuple (LiquidityRatios, SolvencyRatios, etc.)
3. Update backend API:
   - Add to response schema in `backend/app/schemas/calculations.py`
   - Update `backend/app/services/calculation_service.py` if needed
4. Update frontend:
   - Add to TypeScript interfaces in `frontend/types/api.ts`
   - Display in appropriate page component (e.g., `frontend/app/analysis/page.tsx`)
5. Add test case in `legacy/test_calculations.py`

### Adding a New API Endpoint (Backend)
1. Create endpoint function in appropriate router (`backend/app/api/v1/*.py`)
2. Define Pydantic schemas in `backend/app/schemas/`
3. Add business logic in `backend/app/services/` if complex
4. Update frontend API client in `frontend/lib/api.ts`
5. Update TypeScript types in `frontend/types/api.ts`
6. Test endpoint via Swagger UI at `http://localhost:8000/docs`

### Supporting a New XBRL Taxonomy Version
1. Add version to `config.SUPPORTED_TAXONOMIES`
2. Update `data/taxonomy_mapping.json` with new tag mappings
3. Add row counts to `config.TAXONOMY_ROW_COUNTS` if schema structure changed
4. Test with sample file in `legacy/test_xbrl_import.py`
5. Both backend and legacy will automatically use updated mapping

### Extending Database Schema
1. Modify models in `database/models.py` (shared by both apps)
2. Create migration script or use `legacy/migrate_db.py` template
3. Update any affected calculators in `calculations/`
4. Update Pydantic schemas in `backend/app/schemas/` to match new structure
5. Update TypeScript interfaces in `frontend/types/api.ts`
6. Reset database for development: `python -c "from database.db import drop_all, init_db; drop_all(); init_db()"`

### Creating a New Frontend Page (Next.js)
1. Create file in `frontend/app/` (e.g., `frontend/app/new-feature/page.tsx`)
2. Use `useAppContext()` hook to access global state (company, year)
3. Make API calls via `frontend/lib/api.ts`
4. Add navigation link in layout if needed
5. Follow existing patterns: fetch data → display with components → use Recharts for visualization

### Creating a New Legacy Page (Streamlit - Deprecated)
1. Create file in `legacy/ui/pages/` (e.g., `new_feature.py`)
2. Implement `show()` function that uses `st.session_state` for context
3. Add page to navigation list in `legacy/app.py`
4. Follow existing patterns: fetch data → calculate → display with columns/charts

## Technical Constraints

- **SQLite database**: Single-file at project root (`financial_analysis.db`), no concurrent writes (use transactions carefully)
  - Shared by both modern and legacy applications
  - Absolute path configured in `database/db.py` to ensure consistency
- **Decimal precision**: All monetary values use Numeric(15, 2) - max 9,999,999,999,999.99
- **JSON serialization**: Backend uses custom `DecimalJSONResponse` to convert Decimal to float in API responses
- **Caching**:
  - Legacy (Streamlit): Use `@st.cache_resource` for database, `@st.cache_data` for calculations
  - Modern (Next.js): Client-side state management via React Context
- **Italian locale**: UI text is in Italian, number formatting uses European conventions
- **No user authentication**: Single-user application (add authentication layer if multi-tenant needed)
- **CORS**: Backend allows requests from localhost:3000-3002 (Next.js), 8501 (Streamlit)

## Key File Paths

**Always use these absolute paths when referencing files:**
- Database: `/home/peter/DEV/budget/financial_analysis.db`
- Shared modules: `/home/peter/DEV/budget/{database,calculations,importers,config.py,data}/`
- Backend: `/home/peter/DEV/budget/backend/app/`
- Frontend: `/home/peter/DEV/budget/frontend/`
- Legacy: `/home/peter/DEV/budget/legacy/`

**Import Pattern for Backend:**
```python
# backend/app/main.py sets up sys.path
import sys, os
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

# Then anywhere in backend code:
from database.models import Company, BalanceSheet
from calculations.ratios import FinancialRatiosCalculator
from importers.xbrl_parser import import_xbrl_file
```

## Development Workflow

**Working on Shared Modules** (database, calculations, importers):
- Changes automatically affect both modern and legacy apps
- Test with backend: `curl http://localhost:8000/api/v1/companies`
- Test with legacy: Run test files in `legacy/` directory
- No code duplication - single source of truth

**Working on Backend API**:
- Modify files in `backend/app/`
- Backend imports shared modules from project root
- Test via Swagger UI at http://localhost:8000/docs
- Frontend automatically picks up API changes

**Working on Frontend**:
- Modify files in `frontend/`
- Frontend is pure TypeScript/React, no Python dependencies
- Communicates with backend via HTTP only
- Test at http://localhost:3000

**Working on Legacy App** (deprecated):
- Only for reference or maintenance
- All new features should be added to modern stack
