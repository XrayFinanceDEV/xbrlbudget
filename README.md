# 📊 XBRL Budget - Financial Analysis Application

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-15-black.svg)](https://nextjs.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

Sistema completo di analisi finanziaria per bilanci italiani secondo i principi contabili OIC (Organismo Italiano di Contabilità).

**🇮🇹 Italian GAAP Compliant Financial Analysis & Credit Rating System**

**🚀 Modern Full-Stack Architecture:**
- **Backend API** (FastAPI) - Production-ready REST API with comprehensive financial analysis
- **Frontend UI** (Next.js 15) - Modern React-based interface with TypeScript
- **Legacy Web App** (Streamlit) - Located in `/legacy` folder, deprecated but preserved for reference

## Caratteristiche

### Gestione Dati
- ✅ Creazione e modifica aziende
- ✅ Selezione settore (6 settori) durante l'importazione e dalla pagina Aziende
- ✅ Gestione multi-anno (fino a 5 anni)
- ✅ Importazione da XBRL (formato italiano - tassonomie 2011-2018)
- ✅ Importazione da CSV (TEBE)
- ✅ Inserimento manuale bilanci (Stato Patrimoniale + Conto Economico)
- ✅ **Multi-tenancy**: Autenticazione Supabase JWT, dati isolati per utente (max 50 aziende)

### Analisi Finanziaria
- ✅ **Indici di Liquidità**: Current Ratio, Quick Ratio, Acid Test
- ✅ **Indici di Solvibilità**: Autonomia, Leverage, Debt/Equity
- ✅ **Indici di Redditività**: ROE, ROI, ROS, ROD, EBITDA Margin
- ✅ **Indici di Rotazione**: Asset Turnover, giorni magazzino/crediti/debiti
- ✅ **Capitale Circolante**: CCN, CCLN, MS, MT

### Modelli di Valutazione
- ✅ **Altman Z-Score**: Previsione rischio insolvenza con modelli settoriali
  - Modello manifatturiero (5 componenti)
  - Modello servizi (4 componenti)
- ✅ **Rating FGPMI**: Rating creditizio PMI (13 classi da AAA a B-)
  - 7 indicatori settoriali (V1-V7)
  - 5 modelli di settore
  - Bonus fatturato

### Budget & Forecasting
- ✅ **Budget Scenarios**: Creazione scenari di budget multipli
- ✅ **3-Year Forecasts**: Proiezioni finanziarie triennali
- ✅ **Assumptions Management**: Gestione ipotesi crescita per categoria
- ✅ **Cash Flow Analysis**: Rendiconto finanziario (metodo indiretto)

## 🔐 Authentication & Multi-Tenancy

The app is designed to be embedded as an iframe inside **Formula Finance**. Authentication is handled via Supabase JWT tokens passed from the parent app — no separate login required.

### How It Works

1. **Parent app** (Formula Finance) authenticates users via Supabase
2. **Parent sends JWT** to iframe via `postMessage` (`{ type: 'AUTH_TOKEN', token: '...' }`)
3. **Frontend stores token** and includes it as `Authorization: Bearer <token>` on all API calls
4. **Backend validates JWT** (HS256), extracts `user_id` from `sub` claim
5. **All data is scoped** per user — each user sees only their companies (max 50)

### Configuration

| Environment Variable | Description | Required |
|---------------------|-------------|----------|
| `SUPABASE_JWT_SECRET` | Supabase JWT secret for HS256 verification | Production |
| `DEV_USER_ID` | Bypass JWT auth with a fixed user_id | Dev only |
| `MAX_COMPANIES_PER_USER` | Company limit per user (default: 50) | Optional |

### Dev Mode

For local development without Formula Finance, set `DEV_USER_ID`:

```bash
# No JWT required — all API calls use "dev-user-001" as user_id
DEV_USER_ID=dev-user-001 uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### Production Mode

```bash
SUPABASE_JWT_SECRET=your-supabase-jwt-secret uvicorn app.main:app --host 0.0.0.0 --port 8000
```

All API endpoints require authentication. Unauthenticated requests return `401 Unauthorized`.

### API Authentication

Include the JWT token in all API requests:

```bash
curl -H "Authorization: Bearer <supabase-jwt-token>" \
  http://localhost:8000/api/v1/companies
```

### PostMessage Protocol (iframe ↔ parent)

| Direction | Message | When |
|-----------|---------|------|
| Child → Parent | `{ type: 'REQUEST_AUTH_TOKEN' }` | On iframe load |
| Parent → Child | `{ type: 'AUTH_TOKEN', token: 'jwt...' }` | On request + token refresh |
| Parent → Child | `{ type: 'AUTH_LOGOUT' }` | On user logout |

---

## 🎯 API REST (FastAPI)

### Simplified API Workflow

**The API follows a 3-phase pattern: INPUT → ASSUMPTIONS → OUTPUT**

Questo elimina la necessità di fare 15+ chiamate API - solo **3 chiamate totali**!

#### Phase 1: INPUT - Data Import (3 endpoints)
```bash
POST /api/v1/import/xbrl    # Italian XBRL files (6 taxonomies supported)
POST /api/v1/import/csv     # CSV files (TEBE format)
POST /api/v1/import/pdf     # PDF balance sheets (Claude AI extraction)
```

#### Phase 2: ASSUMPTIONS - Budget Scenarios (2 endpoints)
```bash
# Create scenario
POST /api/v1/companies/{id}/scenarios
{
  "name": "Budget 2025-2027",
  "base_year": 2024,
  "projection_years": 3
}

# Bulk upsert assumptions (all years at once!)
PUT /api/v1/companies/{id}/scenarios/{scenario_id}/assumptions
{
  "assumptions": [
    {"forecast_year": 2025, "revenue_growth_pct": 5.0, ...},
    {"forecast_year": 2026, "revenue_growth_pct": 4.0, ...},
    {"forecast_year": 2027, "revenue_growth_pct": 3.5, ...}
  ],
  "auto_generate": true  # Genera automaticamente il forecast!
}
```

#### Phase 3: OUTPUT - Complete Analysis (1 comprehensive endpoint) ⭐

```bash
GET /api/v1/companies/{id}/scenarios/{scenario_id}/analysis
```

**Questo endpoint restituisce TUTTO in una singola risposta:**
- ✅ Dati storici (base_year - 1 e base_year)
- ✅ Dati previsionali (3 o 5 anni con assumptions)
- ✅ Tutti i calcoli per ogni anno (Altman, FGPMI, ratios)
- ✅ Rendiconto finanziario multi-anno

**Query Parameters:**
- `include_historical=true` - Include anni storici (default: true)
- `include_forecast=true` - Include anni previsionali (default: true)
- `include_calculations=true` - Include calcoli (default: true)

---

### Detailed Endpoint Reference

**Base URL:** `http://localhost:8000/api/v1`

#### Companies & Financial Data
```
GET    /companies                              # List all companies
POST   /companies                              # Create company
GET    /companies/{id}                         # Get company details
PUT    /companies/{id}                         # Update company
DELETE /companies/{id}                         # Delete company
GET    /companies/{id}/years                   # List years for company
POST   /companies/{id}/years                   # Create financial year
GET    /companies/{id}/years/{year}/balance-sheet      # Get balance sheet
PUT    /companies/{id}/years/{year}/balance-sheet      # Update balance sheet
GET    /companies/{id}/years/{year}/income-statement   # Get income statement
PUT    /companies/{id}/years/{year}/income-statement   # Update income statement
```

#### Budget Scenarios & Forecasting
```
GET    /companies/{id}/scenarios               # List scenarios
POST   /companies/{id}/scenarios               # Create scenario
GET    /companies/{id}/scenarios/{sid}         # Get scenario
PUT    /companies/{id}/scenarios/{sid}         # Update scenario
DELETE /companies/{id}/scenarios/{sid}         # Delete scenario

# Bulk assumptions (RECOMMENDED - sostituisce chiamate multiple)
PUT    /companies/{id}/scenarios/{sid}/assumptions  # Upsert all years at once
```

#### Financial Analysis & Calculations

**⭐ RECOMMENDED: Use comprehensive endpoint**
```
GET /companies/{id}/scenarios/{sid}/analysis   # Complete analysis (ALL data in one call)
```

**Legacy individual endpoints** (deprecated, use /analysis instead):
```
GET /companies/{id}/years/{year}/calculations/ratios          # All financial ratios
GET /companies/{id}/years/{year}/calculations/summary         # Summary metrics
GET /companies/{id}/years/{year}/calculations/altman          # Altman Z-Score
GET /companies/{id}/years/{year}/calculations/fgpmi           # FGPMI Rating
GET /companies/{id}/years/{year}/calculations/complete        # Complete analysis
```

#### Data Import
```
POST /import/xbrl                              # Upload XBRL file (Italian GAAP)
POST /import/csv                               # Upload CSV file (TEBE format)
POST /import/pdf                               # Upload PDF file (Claude AI extraction)
```

#### Interactive API Documentation
- **Swagger UI:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`

### Data Import Features

#### XBRL Import (`POST /api/v1/import/xbrl`)

**Supported Features:**
- ✅ All 6 Italian XBRL taxonomies (2011-01-04 through 2018-11-04)
- ✅ Automatic taxonomy version detection
- ✅ Support for Ordinario, Abbreviato, and Micro balance sheet schemas
- ✅ Automatic company creation or update
- ✅ Multi-year import (all contexts in file)
- ✅ File validation (type, size max 50MB)
- ✅ Comprehensive error handling

**Parameters:**
- `file` (required): XBRL file (.xbrl or .xml)
- `company_id` (optional): Existing company ID
- `create_company` (optional, default: true): Create company from XBRL entity info
- `sector` (optional, 1-6): Company sector for new company creation (default: 1 Industria)

**Response includes:**
- Taxonomy version detected
- Years imported
- Company ID and name
- Financial year IDs created
- Import statistics

#### CSV Import (`POST /api/v1/import/csv`)

**Supported Features:**
- ✅ TEBE format (semicolon-delimited)
- ✅ Automatic year detection from CSV
- ✅ Balance sheet type detection (Ordinario/Abbreviato/Micro)
- ✅ Support for up to 2 years per file
- ✅ Account description mapping to internal codes

**Parameters:**
- `file` (required): CSV file
- `company_id` (required): Company ID to import for
- `year1` (optional): Most recent year (auto-detected if not provided)
- `year2` (optional): Previous year (auto-detected if not provided)

**Response includes:**
- Balance sheet type detected
- Years imported
- Rows processed
- Fields imported (balance sheet and income statement separately)

#### PDF Import (`POST /api/v1/import/pdf`) - 🆕 NEW

**Supported Features:**
- ✅ Automatic table extraction using PyMuPDF + Claude Haiku
- ✅ Support for Bilancio Micro, Abbreviato, Ordinario (IV CEE format)
- ✅ Intelligent mapping to Italian GAAP schema (sp01-sp18, ce01-ce20)
- ✅ Automatic company creation or update
- ✅ File validation (type, size max 50MB)
- ✅ First run downloads AI models (~2GB), cached for subsequent imports

**Parameters:**
- `file` (required): PDF file (.pdf)
- `fiscal_year` (required): Fiscal year of the balance sheet
- `company_id` (optional): Existing company ID
- `company_name` (optional): Company name (required if creating new company)
- `create_company` (optional, default: true): Create company if not exists
- `sector` (optional, 1-6): Company sector for new company creation (default: 3 Servizi)

**Response includes:**
- Company ID and name
- Financial year ID created
- Balance sheet and income statement IDs
- Fields imported
- Extraction quality metrics

**Processing Time:** 3-10 seconds per PDF (first run: +model download time)

**Note:** Requires `ANTHROPIC_API_KEY` environment variable.

### Complete Analysis Response Structure

Il endpoint `/companies/{id}/scenarios/{sid}/analysis` restituisce una risposta completa con questa struttura:

```json
{
  "scenario": {
    "id": 1,
    "name": "Budget 2025-2027",
    "base_year": 2024,
    "projection_years": 3,
    "company": {
      "id": 123,
      "name": "Acme SpA",
      "tax_id": "IT12345678901",
      "sector": 1
    }
  },
  "historical_years": [
    {
      "year": 2023,
      "balance_sheet": {
        "sp01_crediti_soci": 0.0,
        "sp02_immob_immateriali": 15000.0,
        // ... all sp01-sp18 fields
        "total_assets": 1000000.0,
        "total_equity": 300000.0,
        "total_debt": 700000.0
      },
      "income_statement": {
        "ce01_ricavi_vendite": 800000.0,
        // ... all ce01-ce20 fields
        "revenue": 800000.0,
        "ebitda": 110000.0,
        "ebit": 95000.0,
        "net_profit": 45000.0
      }
    },
    { "year": 2024, /* ... same structure */ }
  ],
  "forecast_years": [
    {
      "year": 2025,
      "assumptions": {
        "revenue_growth_pct": 5.0,
        "material_cost_growth_pct": 3.0,
        "capex_tangible": 50000.0,
        // ... all assumptions
      },
      "balance_sheet": { /* ... same as historical */ },
      "income_statement": { /* ... same as historical */ }
    },
    // ... years 2026, 2027
  ],
  "calculations": {
    "by_year": {
      "2023": {
        "altman": {
          "z_score": 2.85,
          "classification": "gray_zone",
          "components": {"A": 0.35, "B": 0.45, "C": 0.95, "D": 0.60, "E": 0.50}
        },
        "fgpmi": {
          "rating_code": "BB+",
          "total_score": 65,
          "max_score": 100,
          "rating_description": "Buono"
        },
        "ratios": {
          "working_capital": {"ccln": 300000, "ccn": 300000},
          "liquidity": {"current_ratio": 2.5, "quick_ratio": 1.8},
          "solvency": {"autonomy_index": 30.0, "debt_to_equity": 2.33},
          "profitability": {"roe": 15.0, "roi": 9.5, "ros": 11.9},
          "activity": {"asset_turnover": 0.80, "receivables_days": 45}
        }
      },
      // ... all years (2023-2027)
    },
    "cashflow": {
      "years": [
        {
          "year": 2024,
          "base_year": 2023,
          "operating": {"net_profit": 50000, "depreciation": 15000, "total": 51000},
          "investing": {"capex_tangible": -30000, "total": -35000},
          "financing": {"debt_change": 10000, "total": 5000},
          "net_cashflow": 21000,
          "ratios": {"ocf_margin": 6.4, "free_cashflow": 16000}
        },
        // ... all years
      ]
    }
  }
}
```

**Vantaggi:**
- ✅ Una singola chiamata API invece di 10+ chiamate separate
- ✅ Tutti i dati necessari per le pagine di analisi/forecast in una risposta
- ✅ Struttura coerente tra anni storici e previsionali
- ✅ Cache una volta, usa ovunque nel frontend
- ✅ Calcoli pre-computati sul backend (nessun calcolo lato client)

---

### API Response Examples

#### Financial Ratios
```json
{
  "working_capital": {"ccln": 650000.0, "ccn": 250000.0, ...},
  "liquidity": {"current_ratio": 1.625, "quick_ratio": 1.175, ...},
  "solvency": {"autonomy_index": 0.3707, "debt_to_equity": 1.5116, ...},
  "profitability": {"roe": 0.186, "roi": 0.1207, "ebitda_margin": 0.1533, ...},
  "activity": {"asset_turnover": 1.2931, "inventory_turnover_days": 43.0, ...}
}
```

#### Altman Z-Score
```json
{
  "z_score": 2.28,
  "classification": "gray_zone",
  "interpretation_it": "Zona d'Ombra (1.23 < Z < 2.9)...",
  "components": {"A": 0.2155, "B": 0.2155, "C": 0.1207, "D": 0.6615, "E": 1.2931},
  "model_type": "manufacturing"
}
```

#### FGPMI Rating
```json
{
  "rating_code": "AAA",
  "rating_class": 1,
  "total_score": 97,
  "max_score": 105,
  "rating_description": "Eccellente",
  "risk_level": "Minimo",
  "revenue_bonus": 5,
  "indicators": {...}
}
```

#### XBRL Import
```json
{
  "success": true,
  "taxonomy_version": "2018-11-04",
  "years": [2024, 2023],
  "company_id": 1,
  "company_name": "Azienda Esempio S.r.l.",
  "tax_id": "12345678901",
  "financial_year_ids": [1, 2],
  "contexts_found": 2,
  "years_imported": 2,
  "company_created": true
}
```

#### CSV Import
```json
{
  "success": true,
  "balance_sheet_type": "ORDINARIO",
  "years": [2024, 2023],
  "rows_processed": 45,
  "balance_sheet_fields_imported": 18,
  "income_statement_fields_imported": 20,
  "financial_year_ids": [1, 2]
}
```

## Installazione

### Requisiti
- Python 3.11+
- pip

### Setup

1. **Clona il repository**
   ```bash
   git clone git@github.com:XrayFinanceDEV/xbrlbudget.git
   cd xbrlbudget
   ```

2. **Setup Backend API (Required)**
   ```bash
   cd backend
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt

   # Inizializza database
   python -c "from app.core.database import init_db; init_db()"
   ```

3. **Setup Frontend (Next.js 15)**
   ```bash
   cd frontend
   npm install
   # or
   pnpm install
   # or
   yarn install
   ```

4. **Setup Legacy Streamlit (Optional - Deprecated)**
   ```bash
   # Only if you need to access legacy Streamlit app
   cd legacy
   python3 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -r ../requirements.txt

   # Inizializza database (from project root)
   cd ..
   python -c "from database.db import init_db; init_db()"
   ```

## Docker Deployment

Deploy the full stack (backend + frontend + nginx) with a single command.

### Quick Start

```bash
# 1. Copy and edit environment config
cp .env.docker .env
# Edit .env — set SUPABASE_JWT_SECRET for production, or DEV_USER_ID for testing

# 2. Build and start
docker compose build
docker compose up -d

# 3. Verify
curl http://localhost/health          # → {"status": "ok"}
open http://localhost                  # → Next.js app
open http://localhost/docs             # → Swagger UI
```

### Architecture

```
Internet → Nginx (:80)
              ├── /                    → Frontend (Next.js, :3000)
              └── /api/, /docs, /health → Backend (FastAPI, :8000)
```

Three services: **nginx** (reverse proxy), **backend** (FastAPI + shared modules), **frontend** (Next.js standalone). SQLite database persisted via Docker volume.

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SUPABASE_JWT_SECRET` | Supabase JWT secret (HS256) | Required in prod |
| `DEV_USER_ID` | Bypass JWT auth (any string) | - |
| `ANTHROPIC_API_KEY` | Claude API key for PDF extraction | - |
| `ADMIN_API_KEY` | Secret for `/admin/uploads/*` endpoints (see Upload Tracking) | - |
| `UPLOAD_ROOT` | Override uploaded-file storage dir | `data/uploads` |
| `UPLOAD_RETENTION_DAYS` | Cleanup retention for uploaded files | 90 |
| `ALLOWED_ORIGINS` | Extra CORS origins (comma-separated) | - |
| `MAX_COMPANIES_PER_USER` | Company limit per user | 50 |
| `PORT` | External port | 80 |

### Common Operations

```bash
# View logs
docker compose logs -f

# Restart after .env changes
docker compose down && docker compose up -d

# Rebuild after code changes
docker compose build && docker compose up -d

# Stop and remove data (database)
docker compose down -v
```

### Volumes

| Volume | Contents |
|--------|----------|
| `db-data` | SQLite database + uploaded input files (`/app/data/` includes `uploads/`) — persists across restarts |

---

## Upload Tracking & Admin Debug

Every file uploaded via `/api/v1/import/{xbrl,csv,pdf}` is persisted to disk and recorded in the `uploaded_files` table. This lets the developer reproduce user-reported problems (wrong numbers, wrong signs, misclassified accounts, hard parser crashes) by retrieving the exact input that caused the issue.

### Storage
- Files saved to `data/uploads/{user_id}/{YYYY-MM}/{timestamp}_{uuid}.{ext}` (Docker: `/app/data/uploads/...`, inside the `db-data` volume)
- DB row holds: `filename`, `file_type`, `file_size`, `status` (`pending`/`success`/`error`), `error_message`, `error_traceback`, `uploaded_at`, `company_id`
- Tracker writes the row **before** the parser runs, so even a parser crash is captured
- Retention: **90 days** (configurable via `UPLOAD_RETENTION_DAYS`). Run the cleanup script daily:
  ```cron
  0 3 * * *  cd /app && python scripts/cleanup_uploads.py >> /var/log/upload_cleanup.log 2>&1
  ```

### Admin endpoints
All gated by the header `X-Admin-Key: <ADMIN_API_KEY>`. Not reachable from the iframe — intended for curl/browser debugging.

```bash
# 1. List a user's uploads, newest first
curl -H "X-Admin-Key: $ADMIN_API_KEY" \
  "https://host/api/v1/admin/uploads?user_id=abc-123&file_type=pdf&limit=20"

# 2. Inspect one (includes full error traceback)
curl -H "X-Admin-Key: $ADMIN_API_KEY" https://host/api/v1/admin/uploads/42

# 3. Download the original file
curl -H "X-Admin-Key: $ADMIN_API_KEY" \
  https://host/api/v1/admin/uploads/42/download -o original.pdf
```

Supported filters: `user_id`, `file_type` (`xbrl`/`csv`/`pdf`), `status`, `company_id`, `since`, `until`, `limit` (max 500).

### Jenkins wiring
1. Add Jenkins credential (Secret text, ID `budget-admin-api-key`)
2. `Jenkinsfile` already exports it to `.env.docker` on every build
3. Container reads it via `env_file` in `docker-compose.yml`

---

## Utilizzo

### Avvio Completo (Backend + Frontend)

#### 1. Avvia Backend API
```bash
cd backend
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Dev mode (no JWT required):
DEV_USER_ID=dev-user-001 uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# Production mode (requires Supabase JWT):
SUPABASE_JWT_SECRET=your-secret uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Il backend sarà disponibile su:
- **API:** `http://localhost:8000/api/v1`
- **Swagger UI:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`

#### 2. Avvia Frontend Next.js (in un nuovo terminale)
```bash
cd frontend
npm run dev
# or
pnpm dev
# or
yarn dev
```

Il frontend sarà disponibile su `http://localhost:3000`

**Configurazione:** Assicurati che il file `frontend/.env.local` contenga:
```
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
```

> La variabile è la base **completa**, `/api/v1` incluso — `lib/api.ts` la passa a
> `axios.create({ baseURL })` così com'è. Senza il suffisso ogni chiamata finisce su
> `/companies` invece di `/api/v1/companies` e risponde 404.

#### Esempi di Utilizzo API

**Creare un'azienda:**
```bash
curl -X POST http://localhost:8000/api/v1/companies \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Acme SpA",
    "tax_id": "IT12345678901",
    "sector": 1
  }'
```

**Ottenere analisi completa:**
```bash
curl http://localhost:8000/api/v1/companies/1/years/2024/calculations/complete
```

**Calcolare Altman Z-Score:**
```bash
curl http://localhost:8000/api/v1/companies/1/years/2024/calculations/altman
```

**Importare dati da XBRL:**
```bash
curl -X POST "http://localhost:8000/api/v1/import/xbrl?create_company=true&sector=2" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@bilancio.xbrl"
```

**Importare dati da CSV:**
```bash
curl -X POST http://localhost:8000/api/v1/import/csv?company_id=1 \
  -H "Content-Type: multipart/form-data" \
  -F "file=@bilancio.csv"
```

### 🎨 Streamlit Web App (⚠️ LEGACY - Deprecated)

> **Note:** The Streamlit interface is deprecated and maintained for reference only.
> Please use the **Next.js frontend** for new development.

#### Avvio Applicazione Legacy
```bash
cd legacy
source .venv/bin/activate
streamlit run app.py
```

L'applicazione sarà disponibile su `http://localhost:8501`

**Nota:** Eseguire dalla directory `/legacy`

### Import Dati

#### Da XBRL
```python
from importers.xbrl_parser import import_xbrl_file

result = import_xbrl_file(
    file_path="bilancio.xbrl",
    create_company=True
)
```

#### Da CSV (TEBE)
```python
from importers.csv_importer import import_csv_file

result = import_csv_file(
    file_path="bilancio.csv",
    company_id=1,
    year1=2024,
    year2=2023
)
```

### Calcolo Indici

```python
from database.db import SessionLocal
from database.models import FinancialYear
from calculations.ratios import FinancialRatiosCalculator
from calculations.altman import AltmanCalculator
from calculations.rating_fgpmi import FGPMICalculator

db = SessionLocal()
fy = db.query(FinancialYear).filter(FinancialYear.year == 2024).first()

# Indici finanziari
calc = FinancialRatiosCalculator(fy.balance_sheet, fy.income_statement)
liquidity = calc.calculate_liquidity_ratios()
profitability = calc.calculate_profitability_ratios()

# Altman Z-Score
altman = AltmanCalculator(fy.balance_sheet, fy.income_statement, sector=1)
z_score = altman.calculate()

# Rating FGPMI
fgpmi = FGPMICalculator(fy.balance_sheet, fy.income_statement, sector=1)
rating = fgpmi.calculate()
```

## Struttura Progetto

```
budget/
├── backend/                        # 🚀 FastAPI Backend (Modern)
│   ├── app/
│   │   ├── main.py                 # FastAPI application entry point
│   │   ├── api/v1/
│   │   │   ├── companies.py        # Company CRUD endpoints
│   │   │   ├── financial_years.py  # Financial data endpoints
│   │   │   ├── calculations.py     # Analysis & ratios endpoints
│   │   │   ├── budget_scenarios.py # Budget & forecasting endpoints
│   │   │   └── imports.py          # XBRL/CSV import endpoints
│   │   ├── schemas/                # Pydantic request/response models
│   │   ├── services/               # Business logic layer
│   │   │   └── calculation_service.py
│   │   ├── calculations/           # Backend-specific calculations
│   │   │   ├── cashflow.py         # Cash flow statement
│   │   │   └── cashflow_detailed.py
│   │   └── core/
│   │       ├── config.py           # Pydantic Settings
│   │       ├── database.py         # DB dependency injection
│   │       ├── decimal_encoder.py  # JSON Decimal serialization
│   │       ├── auth.py             # JWT validation + dev mode fallback
│   │       └── ownership.py        # Company ownership + limit checks
│   └── requirements.txt
│
├── frontend/                       # 🎨 Next.js Frontend (Modern)
│   ├── app/
│   │   ├── layout.tsx              # Root layout with providers
│   │   ├── page.tsx                # Home/Dashboard
│   │   ├── import/page.tsx         # XBRL/CSV import UI
│   │   ├── budget/page.tsx         # Budget assumptions
│   │   ├── analysis/page.tsx       # Financial analysis
│   │   ├── cashflow/page.tsx       # Cash flow statement
│   │   └── forecast/               # Budget forecast pages
│   ├── components/                 # Reusable React components
│   ├── contexts/
│   │   ├── AuthContext.tsx         # JWT auth via postMessage from parent iframe
│   │   └── AppContext.tsx          # Global state (companies, years)
│   ├── lib/
│   │   └── api.ts                  # Axios API client
│   ├── types/
│   │   └── api.ts                  # TypeScript API interfaces
│   ├── package.json
│   └── tsconfig.json
│
├── database/                       # 🗄️ SHARED: SQLAlchemy ORM Models
│   ├── models.py                   # All database models
│   └── db.py                       # Engine, session, Base
│
├── calculations/                   # 🧮 SHARED: Financial Calculators
│   ├── base.py                     # Base calculator utilities
│   ├── ratios.py                   # Financial ratios
│   ├── altman.py                   # Altman Z-Score
│   ├── rating_fgpmi.py             # FGPMI Rating model
│   └── forecast_engine.py          # 3-year budget projections
│
├── importers/                      # 📥 SHARED: Data Import Parsers
│   ├── xbrl_parser.py              # Italian XBRL parser
│   ├── xbrl_parser_enhanced.py     # Enhanced XBRL with hierarchical debts
│   └── csv_importer.py             # TEBE CSV format importer
│
├── data/                           # 📊 SHARED: Configuration Data
│   ├── taxonomy_mapping.json       # XBRL taxonomy mappings (2011-2018)
│   ├── taxonomy_mapping_v2.json    # Enhanced mappings with debt breakdown
│   ├── rating_tables.json          # FGPMI rating thresholds per sector
│   └── sectors.json                # Sector definitions
│
├── legacy/                         # 📦 LEGACY: Streamlit App (Deprecated)
│   ├── app.py                      # Streamlit entry point
│   ├── ui/pages/                   # Streamlit pages
│   ├── reports/                    # Report generation
│   ├── tests/                      # Test suite
│   ├── vba/                        # VBA-related files
│   ├── sample_data/                # Sample XBRL/CSV files
│   ├── test_*.py                   # Individual test files
│   ├── debug_*.py                  # Debug scripts
│   └── migrate_*.py                # Database migration scripts
│
├── docs/                           # 📚 Documentation (see docs/INDEX.md for the map)
│   ├── import/                     # 📥 Import pipeline: overview + routing/balancing/quadratura
│   ├── taxonomy/                   # IV-CEE schema + XBRL mapping
│   ├── budget/                     # Forecasting + report
│   └── deployment/                 # Deploy, prod config, iframe integration
├── archive/                        # Superseded/historical docs (not maintained)
├── config.py                       # 🔧 SHARED: Configuration constants
├── requirements.txt                # Python dependencies (legacy)
├── README.md
├── CLAUDE.md                       # AI assistant instructions
└── financial_analysis.db           # SQLite database
```

> **Documentation map:** [`docs/INDEX.md`](docs/INDEX.md) lists every current
> document and its scope. The authoritative sources are this `README.md`,
> [`CLAUDE.md`](CLAUDE.md) (architecture/dev guide), and
> [`docs/import/IMPORT-OVERVIEW.md`](docs/import/IMPORT-OVERVIEW.md) (import pipeline). Older notes that no
> longer match the code live in [`archive/`](archive/).

### Architecture Overview

**Modern Stack (Production):**
```
Next.js Frontend (Port 3000)
        ↓ HTTP API calls
FastAPI Backend (Port 8000)
        ↓ imports
Shared Modules (database/, calculations/, importers/)
        ↓
SQLite Database (financial_analysis.db)
```

**Legacy Stack (Deprecated):**
```
Streamlit App (Port 8501) → legacy/app.py
        ↓ imports
Shared Modules (database/, calculations/, importers/)
        ↓
SQLite Database (same database)
```

**Key Architecture Principles:**
- ✅ **Single Source of Truth**: Shared modules (`database/`, `calculations/`, `importers/`, `config.py`, `data/`) used by both modern and legacy apps
- ✅ **No Code Duplication**: Backend imports directly from root shared modules (via `sys.path`)
- ✅ **API-First**: Frontend is pure TypeScript/React with zero Python dependencies, communicates via REST API only
- ✅ **Clean Separation**: Modern stack in `/backend` and `/frontend`, legacy preserved in `/legacy`
- ✅ **Same Database**: Both applications use the same SQLite database for data continuity
- ✅ **Multi-Tenant**: All data scoped per `user_id` via Supabase JWT auth (max 50 companies per user)

## Settori Supportati

| # | Settore | Descrizione |
|---|---------|-------------|
| 1 | **Industria** | Industria, Alberghi (Proprietari), Agricoltura, Pesca |
| 2 | **Commercio** | Commercio |
| 3 | **Servizi** | Servizi (diversi da Autotrasporti) e Alberghi (Locatari) |
| 4 | **Autotrasporti** | Autotrasporti |
| 5 | **Immobiliare** | Immobiliare |
| 6 | **Edilizia** | Edilizia |

Il settore determina i coefficienti dell'Altman Z-Score (modello a 5 o 4 componenti) e le soglie del Rating FGPMI. Il settore viene selezionato durante l'importazione e puo essere modificato dalla pagina Aziende.

## Testing

```bash
# Test database
python test_db.py

# Test calculations
python test_calculations.py

# Test FGPMI rating
python test_fgpmi.py

# Test CSV import
python test_csv_import.py

# Test XBRL import
python test_xbrl_import.py

# Test real XBRL data
python test_bkps_xbrl.py
```

## Tassonomie XBRL Supportate

- 2018-11-04 (latest)
- 2017-07-06
- 2016-11-14
- 2015-12-14
- 2014-11-17
- 2011-01-04

## Pagine Web

### 🏠 Home
Dashboard iniziale con statistiche e azioni rapide

### 🏢 Dati Impresa
Creazione e modifica anagrafica aziende

### 📥 Importazione Dati
Import da XBRL o CSV (TEBE)

### 📊 Stato Patrimoniale
Visualizzazione e modifica SP con verifica bilanciamento

### 💰 Conto Economico
Visualizzazione e modifica CE con calcolo automatico margini

### 📈 Indici Finanziari
Analisi completa con 5 categorie:
- Capitale Circolante (CCN, CCLN, MS, MT)
- Liquidità (Current, Quick, Acid Test)
- Solvibilità (Autonomia, Debt/Equity, Leverage)
- Redditività (ROE, ROI, ROS, ROD)
- Rotazione (Asset Turnover, giorni)

### ⚖️ Altman Z-Score
Valutazione rischio insolvenza con:
- Gauge chart interattivo
- Componenti dettagliate
- Trend storico
- Interpretazione

### ⭐ Rating FGPMI
Rating creditizio PMI con:
- Scala visiva 13 classi (AAA → B-)
- 7 indicatori dettagliati
- Trend storico
- Analisi rischio

### 📉 Dashboard
Panoramica completa con grafici interattivi:
- Andamento economico
- Andamento patrimoniale
- Indicatori chiave
- Valutazioni correnti

## Database

SQLite locale (`financial_analysis.db`)

**Modelli:**
- `Company`: Anagrafica aziende (con `user_id` per multi-tenancy, composite unique su user_id + tax_id)
- `FinancialYear`: Anni fiscali
- `BalanceSheet`: Stato Patrimoniale (22 voci)
- `IncomeStatement`: Conto Economico (20 voci)

## Export

- CSV per indici finanziari
- Report testuali per Altman e FGPMI
- Grafici interattivi (Plotly)

## Note

- Tutti i calcoli seguono i principi contabili italiani (OIC)
- Formule Altman Z-Score calibrate per settore
- Rating FGPMI secondo modello Fondo di Garanzia
- Supporto multi-anno con confronti temporali

## 📸 Screenshots

Coming soon: Dashboard, Altman Z-Score, FGPMI Rating views

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the project
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🏢 Developed By

**Xray Finance DEV**
- GitHub: [@XrayFinanceDEV](https://github.com/XrayFinanceDEV)
- Repository: [xbrlbudget](https://github.com/XrayFinanceDEV/xbrlbudget)

## 📧 Support

For issues and questions:
- Open an issue on [GitHub Issues](https://github.com/XrayFinanceDEV/xbrlbudget/issues)
- Contact: [GitHub Discussions](https://github.com/XrayFinanceDEV/xbrlbudget/discussions)

## 🙏 Acknowledgments

- Italian GAAP (OIC) standards
- XBRL International taxonomy
- Altman Z-Score research
- FGPMI (Fondo di Garanzia per le PMI) rating model

## 🤔 Quale Stack Utilizzare?

### 💡 Raccomandato: **FastAPI + Next.js 15**
La combinazione moderna e production-ready:
- ✅ **Backend FastAPI**: REST API scalabile, documentata, type-safe
- ✅ **Frontend Next.js 15**: React moderno con TypeScript, Server Components, ottimizzazioni automatiche
- ✅ **Separazione frontend/backend**: Deployment indipendente, scalabilità orizzontale
- ✅ **Developer Experience**: Hot reload, TypeScript end-to-end, API auto-documentate
- ✅ **Performance**: Static generation, ISR, API routes ottimizzati

### 📦 Solo Backend API
Usa **solo FastAPI** quando:
- ✅ Stai costruendo integrazioni con sistemi esistenti
- ✅ Hai già un frontend personalizzato (React, Vue, Angular, mobile app)
- ✅ Necessiti solo di API per analisi finanziaria programmatica
- ✅ Vuoi microservizi specializzati


**Migration Path:** Se stai usando Streamlit, considera di migrare al nuovo stack FastAPI + Next.js per beneficiare di:
- Interfaccia utente moderna e responsive
- Migliore performance e SEO
- Deployment separato e scalabile
- Manutenibilità a lungo termine

## 🚧 Development Status

### ✅ Backend API (Complete)
- ✅ REST API with complete CRUD operations
- ✅ All financial calculations (ratios, Altman, FGPMI)
- ✅ **Data import endpoints (XBRL/CSV/PDF upload via API)**
  - Multipart file upload with validation
  - Support for all 6 Italian XBRL taxonomies (2011-2018)
  - CSV import in TEBE format
  - PDF import via PyMuPDF + Claude Haiku
  - Automatic company creation from XBRL/PDF
  - Comprehensive error handling
- ✅ **Authentication & Multi-Tenancy**
  - Supabase JWT validation (HS256)
  - Dev mode bypass via `DEV_USER_ID`
  - Per-user data isolation (all endpoints scoped by user_id)
  - Company limit enforcement (max 50 per user)
- ✅ Interactive API documentation (Swagger UI)
- ✅ 85% code reuse from existing calculators
- ✅ Pydantic schemas for type safety
- ✅ Service layer architecture

### 🚀 Next.js Frontend (In Progress)
- ✅ Next.js 15 with App Router
- ✅ TypeScript configuration
- ✅ Tailwind CSS + shadcn/ui components
- ✅ API client setup
- ✅ Dashboard with company management (editable sector)
- ✅ Import page with sector selection (XBRL, CSV, PDF)
- ✅ Financial analysis pages
- ✅ Budget assumptions management
- ✅ Forecast pages (Income, Balance, Reclassified)
- ✅ Cash flow statement (Italian GAAP)
- 🔄 Import UI with drag-and-drop

### ⚠️ Streamlit Web App (Deprecated)
- ✅ Fully functional but deprecated
- ⚠️ No longer actively maintained
- 🔄 Features being migrated to Next.js frontend

**Recommendation:** Use **FastAPI + Next.js** stack. Streamlit is legacy and will not receive new features.

---

**Version:** 2.4.0 (Multi-Tenancy & Auth)
**Released:** February 2026
**Python:** 3.11+
**Backend:** FastAPI 0.115+ with XBRL/CSV/PDF Import + JWT Auth
**Frontend:** Next.js 15 with TypeScript + shadcn/ui | Streamlit 1.40+ (Deprecated)
**Made with ❤️ in Italy 🇮🇹**

### What's New in 2.4.0
- ✨ **Supabase JWT authentication** via iframe postMessage protocol
- ✨ **Multi-tenancy**: All data scoped per user_id (max 50 companies per user)
- ✨ **Dev mode**: `DEV_USER_ID` env var bypasses JWT for local development
- ✨ **Company ownership validation** on all API endpoints (404 for unauthorized access)

### Version 2.3.0 (Previous)
- ✨ **Sector selection** during XBRL/PDF import (6 sectors)
- ✨ **Editable sector** on Home page company table
- ✨ Sector affects Altman Z-Score model and FGPMI rating thresholds

### Version 2.2.0 (Previous)
- 🚀 **Next.js 15 frontend** with TypeScript and Tailwind CSS
- 🎨 **shadcn/ui redesign** - all pages migrated to shadcn components
- ⚠️ **Streamlit marked as legacy** - no new features planned
- ✨ Modern React-based UI with App Router
- ✨ TypeScript end-to-end type safety

### Version 2.1.0 (Previous)
- ✨ XBRL file upload API endpoint
- ✨ CSV file upload API endpoint (TEBE format)
- ✨ Multipart file handling with validation
- ✨ Automatic taxonomy detection
- ✨ Comprehensive import error handling
