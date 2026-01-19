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
- **Legacy Web App** (Streamlit) - Deprecated, use for reference only

## Caratteristiche

### Gestione Dati
- ✅ Creazione e modifica aziende
- ✅ Gestione multi-anno (fino a 5 anni)
- ✅ Importazione da XBRL (formato italiano - tassonomie 2011-2018)
- ✅ Importazione da CSV (TEBE)
- ✅ Inserimento manuale bilanci (Stato Patrimoniale + Conto Economico)

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

## 🎯 API REST (FastAPI)

### Endpoints Disponibili

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

#### Financial Analysis & Calculations
```
GET /companies/{id}/years/{year}/calculations/ratios          # All financial ratios
GET /companies/{id}/years/{year}/calculations/summary         # Summary metrics
GET /companies/{id}/years/{year}/calculations/altman          # Altman Z-Score
GET /companies/{id}/years/{year}/calculations/fgpmi           # FGPMI Rating
GET /companies/{id}/years/{year}/calculations/complete        # Complete analysis
GET /companies/{id}/years/{year}/calculations/ratios/liquidity      # Liquidity only
GET /companies/{id}/years/{year}/calculations/ratios/profitability  # Profitability only
GET /companies/{id}/years/{year}/calculations/ratios/solvency       # Solvency only
```

#### Data Import
```
POST /import/xbrl                              # Upload XBRL file (Italian GAAP)
POST /import/csv                               # Upload CSV file (TEBE format)
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

4. **Setup Legacy Streamlit (Deprecated)**
   ```bash
   # Only if you need to access legacy features
   python3 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -r requirements.txt

   # Inizializza database
   python -c "from database.db import init_db; init_db()"
   ```

## Utilizzo

### 🚀 Avvio Completo (Backend + Frontend)

#### 1. Avvia Backend API
```bash
cd backend
source venv/bin/activate  # On Windows: venv\Scripts\activate
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
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
NEXT_PUBLIC_API_URL=http://localhost:8000
```

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
curl -X POST http://localhost:8000/api/v1/import/xbrl?create_company=true \
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
source .venv/bin/activate
streamlit run app.py
```

L'applicazione sarà disponibile su `http://localhost:8501`

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

### Backend (FastAPI)
```
backend/
├── app/
│   ├── main.py                     # FastAPI application
│   ├── api/v1/
│   │   ├── companies.py            # Company endpoints
│   │   ├── financial_years.py      # Financial data endpoints
│   │   ├── calculations.py         # Analysis endpoints
│   │   └── imports.py              # Data import endpoints
│   ├── schemas/                    # Pydantic models
│   │   ├── company.py
│   │   ├── financial_year.py
│   │   ├── balance_sheet.py
│   │   ├── income_statement.py
│   │   ├── budget.py
│   │   ├── calculations.py
│   │   └── imports.py              # Import response schemas
│   ├── services/                   # Business logic
│   │   └── calculation_service.py
│   └── core/
│       ├── config.py               # Pydantic Settings
│       ├── database.py             # DB session management
│       └── decimal_encoder.py      # JSON serialization
├── database/                       # ✓ Shared with Streamlit
│   ├── models.py                   # SQLAlchemy models
│   └── db.py
├── calculations/                   # ✓ Shared with Streamlit
│   ├── base.py                     # Base calculator
│   ├── ratios.py                   # Financial ratios
│   ├── altman.py                   # Altman Z-Score
│   ├── rating_fgpmi.py             # FGPMI Rating
│   └── forecast_engine.py          # Budget forecasting
├── importers/                      # ✓ Shared with Streamlit
│   ├── xbrl_parser.py              # XBRL importer
│   └── csv_importer.py             # CSV importer
├── data/                           # ✓ Shared with Streamlit
│   ├── sectors.json
│   ├── rating_tables.json
│   └── taxonomy_mapping.json
└── requirements.txt                # FastAPI dependencies
```

### Next.js Frontend (Recommended)
```
frontend/
├── app/
│   ├── layout.tsx                  # Root layout with providers
│   ├── page.tsx                    # Home/Dashboard page
│   ├── companies/                  # Company management
│   ├── analysis/                   # Financial analysis pages
│   └── import/                     # Data import UI
├── components/                     # React components
│   ├── ui/                         # shadcn/ui components
│   ├── navigation/                 # Navigation components
│   └── charts/                     # Chart components (Recharts)
├── lib/
│   ├── api.ts                      # API client (fetch wrapper)
│   └── utils.ts                    # Utility functions
├── types/
│   └── api.ts                      # TypeScript types for API
├── package.json                    # Node dependencies
├── next.config.ts                  # Next.js configuration
├── tailwind.config.ts              # Tailwind CSS config
└── tsconfig.json                   # TypeScript config
```

### Streamlit Web App (⚠️ Deprecated)
```
budget/
├── app.py                          # Streamlit main app (LEGACY)
├── config.py                       # Configuration
├── requirements.txt                # Streamlit dependencies
├── ui/
│   └── pages/                      # Streamlit pages (DEPRECATED)
│       ├── dashboard.py
│       ├── importazione.py
│       ├── budget.py
│       ├── balance_sheet.py
│       ├── income_statement.py
│       ├── ratios.py
│       ├── altman.py
│       └── rating.py
└── [database, calculations, importers, data]  # Shared with backend
```

**Key Architecture Points:**
- 🔄 **85% Code Reuse**: Database models, calculators, and importers are shared between backend and legacy Streamlit
- 🎯 **Single Source of Truth**: Same calculation logic across all interfaces
- 📊 **Modern Stack**: FastAPI backend + Next.js frontend for production use
- ⚠️ **Legacy Support**: Streamlit maintained for reference but no new features

## Settori Supportati

1. **Industria** (Manufacturing)
2. **Commercio** (Commerce)
3. **Servizi** (Services)
4. **Autotrasporti** (Transport)
5. **Immobiliare** (Real Estate)
6. **Edilizia** (Construction)

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
- `Company`: Anagrafica aziende
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

### ⚠️ Legacy: **Streamlit Web App** (Deprecated)
- ❌ **Non raccomandato per nuovi progetti**
- 🔧 Mantenuto solo per compatibilità e riferimento
- 🚀 Migra al nuovo stack Next.js per funzionalità moderne

**Migration Path:** Se stai usando Streamlit, considera di migrare al nuovo stack FastAPI + Next.js per beneficiare di:
- Interfaccia utente moderna e responsive
- Migliore performance e SEO
- Deployment separato e scalabile
- Manutenibilità a lungo termine

## 🚧 Development Status

### ✅ Backend API (Complete)
- ✅ REST API with complete CRUD operations
- ✅ All financial calculations (ratios, Altman, FGPMI)
- ✅ **Data import endpoints (XBRL/CSV upload via API)**
  - Multipart file upload with validation
  - Support for all 6 Italian XBRL taxonomies (2011-2018)
  - CSV import in TEBE format
  - Automatic company creation from XBRL
  - Comprehensive error handling
- ✅ Interactive API documentation (Swagger UI)
- ✅ 85% code reuse from existing calculators
- ✅ Pydantic schemas for type safety
- ✅ Service layer architecture

### 🚀 Next.js Frontend (In Progress)
- ✅ Next.js 15 with App Router
- ✅ TypeScript configuration
- ✅ Tailwind CSS styling
- ✅ API client setup
- ✅ Dashboard page (basic implementation)
- 🔄 Company management pages
- 🔄 Financial analysis pages
- 🔄 Import UI with drag-and-drop
- 🔄 Budget management interface

### ⚠️ Streamlit Web App (Deprecated)
- ✅ Fully functional but deprecated
- ⚠️ No longer actively maintained
- 🔄 Features being migrated to Next.js frontend

**Recommendation:** Use **FastAPI + Next.js** stack. Streamlit is legacy and will not receive new features.

---

**Version:** 2.2.0 (Next.js Frontend)
**Released:** January 2026
**Python:** 3.11+
**Backend:** FastAPI 0.115+ with XBRL/CSV Import
**Frontend:** Next.js 15 with TypeScript (In Progress) | Streamlit 1.40+ (Deprecated)
**Made with ❤️ in Italy 🇮🇹**

### What's New in 2.2.0
- 🚀 **Next.js 15 frontend** with TypeScript and Tailwind CSS
- ⚠️ **Streamlit marked as legacy** - no new features planned
- ✨ Modern React-based UI with App Router
- ✨ TypeScript end-to-end type safety
- 🎨 Tailwind CSS for responsive design
- 📱 Mobile-first approach
- 🔄 Features being migrated from Streamlit to Next.js

### Version 2.1.0 (Previous)
- ✨ XBRL file upload API endpoint
- ✨ CSV file upload API endpoint (TEBE format)
- ✨ Multipart file handling with validation
- ✨ Automatic taxonomy detection
- ✨ Comprehensive import error handling
