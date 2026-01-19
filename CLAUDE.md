# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**XBRL Budget** is an Italian GAAP compliant financial analysis and credit rating system built with Python and Streamlit. It analyzes Italian company financial statements, calculates comprehensive financial ratios, and provides credit risk assessments using Altman Z-Score and FGPMI rating models.

**Key Domain:** Italian accounting (OIC - Organismo Italiano di Contabilità) with specialized XBRL import for Italian taxonomies.

## Development Commands

### Environment Setup
```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Initialize database (first time only)
python -c "from database.db import init_db; init_db()"
```

### Running the Application
```bash
# Start Streamlit web application
streamlit run app.py

# Application will be available at http://localhost:8501
```

## Navigation Structure

The application uses **horizontal tabs** at the top for navigation. **No sidebar** is displayed.

**Top Selection Bar** (horizontal layout):
- Company selector (dropdown with all companies)
- Year selector (fiscal years for selected company)
- Sector display (metric)
- P.IVA display (metric)

**Main Tabs**:
1. **Home** - Dashboard with statistics and quick overview
2. **Importazione Dati** - Import XBRL/CSV data
3. **Input Ipotesi** - Budget scenario creation and assumptions input
4. **CE Previsionale** - Income Statement forecast view (historical vs budget)
5. **SP Previsionale** - Balance Sheet forecast view (historical vs budget)
6. **Previsionale Riclassificato** - Reclassified financial indicators with charts
7. **Indici** - Combined financial analysis (Ratios + Altman Z-Score + FGPMI Rating)
8. **Rendiconto Finanziario** - Cash Flow Statement with indirect method calculation

### Testing
```bash
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
python -c "from database.db import drop_all, init_db; drop_all(); init_db()"

# Database migration (if schema changes)
python migrate_db.py
```

## Architecture

### Multi-Layer Calculator Architecture

The system uses a **layered calculation architecture** where each module builds on lower layers:

1. **Base Layer** (`calculations/base.py`): Common utilities (safe_divide, rounding, Excel-like functions)
2. **Financial Ratios** (`calculations/ratios.py`): Liquidity, solvency, profitability, activity ratios
3. **Risk Models** (`calculations/altman.py`, `calculations/rating_fgpmi.py`): Use ratios + raw financials
4. **Forecasting Engine** (`calculations/forecast_engine.py`): Generates 3-year projections based on assumptions

**Important:** Calculators work with **SQLAlchemy ORM objects** (BalanceSheet, IncomeStatement), not dictionaries. They use `Decimal` for all monetary calculations to avoid floating-point precision issues.

### Data Flow

```
XBRL/CSV Import → Database (SQLite) → Calculator Layer → Streamlit UI → Charts/Tables
     ↓                ↓                       ↓
Taxonomy Mapping   ORM Models        Decimal-based math
(data/*.json)    (database/models.py)  (calculations/*.py)
```

**Critical Path:**
1. **Import**: XBRL Parser (`importers/xbrl_parser.py`) or CSV Importer → Creates Company/FinancialYear/BalanceSheet/IncomeStatement
2. **Calculation**: Instantiate calculator with ORM objects → Call calculate() → Returns NamedTuple results
3. **Display**: Streamlit pages (`ui/pages/*.py`) fetch data from database → Pass to calculators → Render with Plotly charts

### Database Schema

**Core Models** (`database/models.py`):
- `Company`: Master data (name, tax_id, sector 1-6)
- `FinancialYear`: Container linking company to financial statements for a specific year
- `BalanceSheet`: 22 line items (sp01-sp18), follows Italian civil code art. 2424
- `IncomeStatement`: 20 line items (ce01-ce20), follows Italian civil code art. 2425

**Forecasting Models** (for 3-year budget projections):
- `BudgetScenario`: Scenario metadata (name, base year, active flag)
- `BudgetAssumptions`: Growth percentages per year (revenue, costs, investments)
- `ForecastYear`: Links scenario to forecast financial statements
- `ForecastBalanceSheet`, `ForecastIncomeStatement`: Projected financials

**Key Relationships:**
- One Company → Many FinancialYears
- One FinancialYear → One BalanceSheet + One IncomeStatement
- All use cascade="all, delete-orphan" (deleting company removes all child records)

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

### Streamlit Session State
- `st.session_state.db`: Cached database session (initialized once via @st.cache_resource)
- `st.session_state.selected_company_id`: Currently selected company
- `st.session_state.selected_year`: Currently selected fiscal year

**Pattern**: Sidebar handles company/year selection, pages read from session_state, call database queries, pass results to calculators.

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
1. Add calculation method to `FinancialRatiosCalculator` class
2. Add to appropriate NamedTuple (LiquidityRatios, SolvencyRatios, etc.)
3. Update `ui/pages/ratios.py` to display new metric
4. Add test case in `test_calculations.py`

### Supporting a New XBRL Taxonomy Version
1. Add version to `config.SUPPORTED_TAXONOMIES`
2. Update `data/taxonomy_mapping.json` with new tag mappings
3. Add row counts to `config.TAXONOMY_ROW_COUNTS` if schema structure changed
4. Test with sample file in `test_xbrl_import.py`

### Extending Database Schema
1. Modify models in `database/models.py`
2. Create migration script or use `migrate_db.py` template
3. Update any affected calculators
4. Reset database for development: `drop_all()` + `init_db()`

### Creating a New Page
1. Create file in `ui/pages/` (e.g., `new_feature.py`)
2. Implement `show()` function that uses `st.session_state` for context
3. Add page to navigation list in `app.py` (line 123-138)
4. Follow existing patterns: fetch data → calculate → display with columns/charts

## Technical Constraints

- **SQLite database**: Single-file, no concurrent writes (use transactions carefully)
- **Decimal precision**: All monetary values use Numeric(15, 2) - max 9,999,999,999,999.99
- **Streamlit caching**: Use `@st.cache_resource` for database, `@st.cache_data` for calculations
- **Italian locale**: UI text is in Italian, number formatting uses European conventions
- **No user authentication**: Single-user application (add authentication layer if multi-tenant needed)
