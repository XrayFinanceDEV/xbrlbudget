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
# 2. RETTIFICHE (optional): Adjust imported BS/IS with double-entry postings.
#    Called once PER YEAR — the partial year AND the historical reference year each get their own
#    tab, their own journal and their own 20-entry cap (period_months omitted = full year).
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

## Invarianti e trappole

Le regole che, se ignorate, producono un danno **silenzioso**: il dato risulta sbagliato e
nessun controllo se ne accorge. Il resto della documentazione spiega i meccanismi; qui c'è solo
ciò che non si può non sapere. Ogni voce dice la regola e **cosa si rompe** a violarla.

> Raccolte dall'[inventario dello snellimento](docs/superpowers/2026-08-14-inventario-claude-md.md),
> che per ciascuna porta la prova nel codice. Coprono **l'import**, l'unico blocco finora passato
> al setaccio: l'assenza di una regola su frontend o previsionale non significa che non esista.

### Contabilità
- **La colonna è la verità sul lato; la descrizione decide la voce.** Mai il contrario:
  `ERARIO C/`, `DEPOSITI BANCARI`, `FORNITORI C/ANTICIPI` cambiano lato attivo/passivo per
  colonna. Ribaltare il lato per descrizione è stato tentato e revertito: regrediva file puliti.
- **Diagnose, never fabricate.** Un divario si misura e si dichiara, non si tappa.
  `enforce_ce_sp_identity`, `reconcile_ivcee_balance` e il parser best-effort **non modificano
  nulla**: espongono `_ce_sp_difference`, `_declared_assets_difference`, `_plug_residual`, e la
  correzione la fa l'utente in Rettifiche. Non cercare un bug dentro un plug che non esiste — per
  molto tempo questo file ne ha descritti di inesistenti, ed è il guasto che ha motivato lo
  snellimento.
- **Debito senza scadenza dichiarata → a breve**, per prudenza: anticipare una scadenza peggiora
  gli indici di liquidità, non li abbellisce, e l'utente lo sposta in Rettifiche. Vale per ogni
  estrattore. Attenzione: `sp16` e `sp17` stanno **entrambi nel passivo**, quindi il pareggio non
  vede l'appiattimento — lo vedono CCN, current ratio e il circolante di Altman.
- **Un errore dentro un aggregato è accettato**: l'utente lo rifinisce in Rettifiche. Un errore
  che **attraversa** un aggregato o un confine di KPI no — cambia un numero su cui si decide.

### Estrazione e classificazione
- **Mai dedurre la parentela fra conti dal prefisso o dalla lunghezza del codice.** I piani dei
  conti sono specifici del gestionale: AGO stampa mastri a 8 cifre con figli a 9, nessuno prefisso
  dell'altro, e `c.startswith(code)` no-oppa in silenzio. La profondità genera ipotesi; il **totale
  stampato dal documento** decide. Nessun totale ⇒ scansione dichiarata non verificata, mai data
  per buona. Corollario: si sommano i mastri **oppure** le foglie, mai entrambi.
- **Per classificare una voce di CE usare `situazione_contabile_parser._resolve_ce_field(desc,
  direction)`, mai `iv_cee_hierarchy.resolve(side=…)`**: su un nodo CE `side` non filtra nulla
  (`Node.side` è popolato solo per lo SP), un costo può risolversi su un ricavo e il risultato si
  sposta di **2×** il suo importo.
- **Un secchio di ripiego è neutro solo dentro il proprio insieme.** `ce06` è neutro fra i costi
  della produzione, ma su una riga letta nella colonna RICAVI è un costo, e sposta il risultato di
  2× il proprio importo. Il ripiego si sceglie per direzione (a destra `ce04`).
- **Un plug inventa massa ed è vietato; un fallback etichetta massa davvero letta ed è ammesso.**
  Non sono la stessa cosa, e la differenza è tutta qui.
- **`TIER0_FIELDS` non è mai una destinazione di ripiego** (immobilizzazioni nette, patrimonio
  netto, debiti verso banche, `ce09`): `ce09` è l'unico confine di KPI dentro i costi operativi
  (`EBITDA = EBIT + ce09`), gli altri spostano un totale e rompono PFN, ROI, indipendenza
  finanziaria e i due modelli di rating in un colpo.
- **La massa non riconosciuta va in un sotto-campo esplicito** (`ce06`, `sp16g`), mai su un
  aggregato: `projection_common.base_bank_debt` assegna alle BANCHE qualunque scarto fra
  `sp16`/`sp17` e la somma dei loro dettagli, e il residuo diventa debito bancario fantasma con
  tanto di piano di rimborso.
- **`data/iv_cee_tree.json` è solo di livello legale, per scelta.** Aggiungere alias di
  sotto-conto sembra un miglioramento ovvio e raddoppia gli importi nell'aggregazione piatta delle
  route A/B, dove padre e figlio verrebbero sommati entrambi. Nessun cancello vede quell'inflazione.
- **L'LLM IV-CEE è l'estrattore sbagliato per una situazione contabile.** `extract_pdf_with_llm`
  legge lo schema di legge, non un elenco di conti: su una contrapposte restituisce un'estrazione
  sbilanciata che diventa il generico «Balance sheet does not balance». È l'ultima risorsa **solo**
  quando il deterministico esce davvero vuoto. Ricablarlo come fallback di route C è una tentazione
  ricorrente; l'estrattore giusto per le liste CoGe è il pass CoGe dedicato.

### Quadratura, diagnostica e verdetti
- **Attivo = Passivo = 0 non è una quadratura.** Un'estrazione vuota ha sbilancio zero: senza il
  controllo `is_empty` risulterebbe il bilancio più pulito del corpus.
- **Un difetto che quadra si corregge a monte, non aggiungendo un controllo a valle.** Un bilancio
  letto dall'anno sbagliato è internamente coerente: quadra, e nessun gate lo vede.
- **Un verdetto negativo vuole una contraddizione, non un controllo assente.** Vale in
  `reliability.assess` (`UNRELIABLE` mai per assenza: un controllo mancante dà `DERIVED`), nel
  cancello del riscatto vision (`residual_measured`) e nel gate infrannuale. Un controllo che manca
  è «non lo so», e «non lo so» non blocca.
- **Un estrattore dichiara sempre le proprie chiavi diagnostiche, anche a zero**
  (`_unclassified_mass`, `_plug_residual`): a valle una chiave **assente vale zero**, quindi tacere
  equivale a dichiararsi pulito. Vale per chiunque scriva un estrattore nuovo.
- **Una correzione che tocca più campi si applica tutta o niente**, e in caso di errore ripristina
  lo stato di partenza. Il netting dei contro-conti lo fa: un fallimento a metà lascerebbe un foglio
  mezzo nettato **privo** dei marcatori `_contra_*`, e l'assenza di quei marcatori viene letta a
  valle come «su questa route non gira nessuna scansione» — cioè un foglio corrotto declassato in
  silenzio a foglio normale.
- **L'estrazione LLM non è deterministica** (route A/B e pass CoGe): lo stesso file può dare due
  esiti diversi a otto minuti di distanza. Un sospetto di regressione si conferma sul percorso di
  produzione e su più esecuzioni, mai su una sola.

### Previsionale
- **Un verdetto di inaffidabilità blocca il previsionale, mai il salvataggio.** Le Rettifiche
  lavorano su un `FinancialYear` già persistito: un file non salvato sarebbe incorreggibile per
  sempre.
- **Chi chiama l'endpoint bulk delle assumptions deve leggere `forecast_generated`, non l'HTTP
  200.** Un previsionale rifiutato torna comunque 200, con la ragione in `message`, nessun
  `ForecastYear` scritto e `forecast_years: []`. Ignorarlo dipinge una colonna Proiezione vuota
  sotto un toast verde. → `docs/import/REGOLE-IMPORT-05-INFRANNUALE.md` §6

### Ambiente
- **MinerU non va mai sul VPS.** La sua immagine è `FROM vllm/vllm-openai` (gigabyte, orientata
  GPU) e sta dietro il compose profile `mineru`, che la esclude da **ogni** comando compose —
  `build` compreso — perché il `Jenkinsfile` esegue `docker compose build --no-cache --parallel`
  sullo staging. `MINERU_OCR_ENABLED` è `false` di default per la stessa ragione. Toglierlo dal
  profile trascina vLLM sul server. → `docs/import/REGOLE-IMPORT-02-ESTRAZIONE.md` §5-bis

## Critical Implementation Notes

### XBRL Import
- Supports taxonomies 2011-01-04 through 2018-11-04
- Values in full euros (not thousands)
- Parser detects schema type (Ordinario/Abbreviato/Micro)
- Enhanced parser (`xbrl_parser_enhanced.py`) includes hierarchical debt reconciliation

### Import PDF (Claude LLM)

Ogni PDF è classificato da `bilancio_classifier.classify_bilancio` PRIMA di scegliere un
estrattore, e la route decide con quali regole il file viene aperto. Tre macro-aree coprono il
96% dei casi reali: **A/B** — schema di legge IV-CEE, estrattore LLM (Haiku) ancorato ai totali
di voce; **C** — situazione contabile / sezioni contrapposte, dove il CoGe-LLM e il parser
deterministico girano **entrambi** e vince il candidato più vicino al totale che il documento
stampa; **XBRL nativo / non supportato**, che esce con un errore onesto. Dall'estrazione in poi
il sistema **misura e dichiara, non corregge**: un divario diventa un avviso e una riga da
sistemare in Rettifiche, mai un importo inventato.

Gli invarianti che governano tutte e tre le rotte stanno in «Invarianti e trappole», sopra.

| Domanda | Pagina |
|---|---|
| Devi orientarti nella serie, o sapere quali disallineamenti sono già noti? | [REGOLE-IMPORT-00-INDICE](docs/import/REGOLE-IMPORT-00-INDICE.md) |
| Come si decide che cosa è un documento e a quale estrattore va? | [REGOLE-IMPORT-01-ROUTING](docs/import/REGOLE-IMPORT-01-ROUTING.md) |
| Come si estrae, quando entra l'LLM, quanto costa, come si sceglie fra due candidati? | [REGOLE-IMPORT-02-ESTRAZIONE](docs/import/REGOLE-IMPORT-02-ESTRAZIONE.md) |
| Una riga di conto in che voce di legge va, un fondo si netta, e dove finisce ciò che non si è saputo classificare? | [REGOLE-IMPORT-03-SPACCHETTATURE-NETTING](docs/import/REGOLE-IMPORT-03-SPACCHETTATURE-NETTING.md) |
| Un bilancio non quadra o è stato rifiutato, e non capisci perché? | [REGOLE-IMPORT-04-QUADRATURE](docs/import/REGOLE-IMPORT-04-QUADRATURE.md) |
| Che cosa si può annualizzare di un periodo parziale, e che cosa blocca una proiezione? | [REGOLE-IMPORT-05-INFRANNUALE](docs/import/REGOLE-IMPORT-05-INFRANNUALE.md) |
| Che cosa finisce sul DB, con quale stato, e come si risale a chi ha prodotto un numero? | [REGOLE-IMPORT-06-PERSISTENZA](docs/import/REGOLE-IMPORT-06-PERSISTENZA.md) |
| Questo file reale in che area cade, e quale gestionale lo ha stampato? | [IMPORT-ROUTING-TAXONOMY](docs/import/IMPORT-ROUTING-TAXONOMY.md) |
| Devi correggere un import che sbaglia su un file preciso? | [FIXING-IMPORT](docs/FIXING-IMPORT.md) |

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
  - BS working capital: turnover ratios from reference year applied to projected P&L.
    A ratio implying **over a year of stock is DEGENERATE** (`_turnover_ratio` → `None`) and the
    observed partial-year stock is carried instead, with a `degenerate_turnover_ratio` diagnostic —
    `_safe_divide` guards a zero denominator, not a negligible one. **The same guard exists on both
    sides** (`lib/pratica-turnover.ts` mirrors the engine); they must stay in agreement, or the
    screen and the persisted record show two different balance sheets.
    → `docs/import/REGOLE-IMPORT-05-INFRANNUALE.md` §5
  - Equity: capital constant, reserves absorb prior year profit, current year from projection
  - Cash as plug (same as budget engine)
  - Taxes: recalculated on projected pre-tax profit
- Output stored as ForecastYear (compatible with existing `/analysis` endpoint)
- **Promote** (`POST /scenarios/{id}/promote`): Copies ForecastYear BS/IS into a new FinancialYear (period_months=NULL)
  - Enables using the projected year as base year for a subsequent budget scenario
  - Dynamic column copy via `__table__.columns` intersection (handles missing fields gracefully)
  - REPLACES an existing full-year FinancialYear for that company+year (re-promote); deletes it with cascade before creating the new record — a manually imported full year for the same year is overwritten
  - Quadratura gate: refuses to promote a projection that is not `semantic_valid` per `check_quadratura` — **not** a €5 threshold (`promote_service.py:46-57`; see `docs/import/REGOLE-IMPORT-04-QUADRATURE.md` §11)
  - Service: `backend/app/services/promote_service.py`
- Frontend wizard: Import → Rettifiche → Comparison → Projection (editable) → Results → Promote to Budget

### Rettifiche (BS/IS Adjustments Journal)
Journal of double-entry corrections applied to the imported financials before comparison/projection.

**Two sub-tabs, one per year (2026-08-07).** A trial balance almost always arrives with its historical
reference year (30.06.2026 + 31.12.2025), and **both need rettifiche** — the historical year is the base
the Confronto, Proiezione and Indicatori compute growth against, so an uncorrected misclassification
there propagates everywhere. The Rettifiche step holds a shadcn `Tabs` with *Rettifiche Storico
{refYear}* (default) and *Rettifiche Bil. di verifica {n}M {year}*.

- **No backend work was needed:** `GET /companies/{id}/years/{year}/adjustable` and `PUT .../adjustments`
  already take `year` + optional `period_months` (`_find_fy`), and the importer already persists a
  dual-column PDF's prior year as `period_months=None`. The Importazione step already guarantees the
  reference year exists (`handleImportRefYear`) or was explicitly skipped (`handleSkipRefYear`).
- **`frontend/hooks/use-rettifiche-year.ts`** holds load/save/reset/corrections for ONE `FinancialYear`;
  the page instantiates it twice — `storico` (`fiscalYear - 1`, `periodMonths` **undefined** = full year)
  and `verifica` (`fiscalYear`, `periodMonths < 12 ? periodMonths : undefined`). `RettificheTab` is
  **unmodified and rendered twice**: it is prop-driven, `hasRef` hides the reference column when
  `referenceYearData` is `null`, and `periodEndDate` derives 31/12/{refYear} from `(year, 12)`.
- **⚠️ Never put the whole `verifica`/`storico` object in a `useEffect` dependency array.** The hook
  returns a fresh object literal every render, so an object-keyed effect re-fires on every re-render —
  including the one its own `setLoading(true)` causes — and issues a duplicate `GET /adjustable`.
  Depend on the individual fields (`storico.data`, `storico.load`, …). The `exhaustive-deps` lint
  warnings on those effects are intentional.
- **⚠️ The hook resets on identity change** (`[companyId, year, periodMonths]`). Without it, going back
  to Importazione, switching the period 9 → 12 and returning would keep the 9-month sheet loaded while
  the save target became the full-year record — writing partial values into the **wrong
  `FinancialYear`**. The backend cannot catch this: it resolves exactly the record it is asked for and
  the sheet balances. Remember a partial and a full-year record deliberately coexist for the same
  company+year.
- **`referenceYearData`** (the read-only Storico column inside the Bil. di verifica tab) is a `useMemo`
  over `storico.data`, not its own fetch — so a correction on one tab moves the column on the other.
- **Downstream invalidation:** a save or reset on **either** year clears `comparison`, `projectedBS` and
  `analysis`, and toasts *"ricalcola la proiezione"* only when a projection already existed. Nothing is
  recomputed silently — the user goes back through Confronto → Proiezione. The "did a projection exist?"
  test reads a **ref**, never a `setState` updater: `reactStrictMode` double-invokes updaters in dev, so
  a toast inside one fires twice.
- **No historical year** (import skipped → pure-annualization mode): the Storico trigger is disabled with
  an explanatory card and the sub-tab defaults to Bil. di verifica. A 404 sets `exists = false` — a
  legitimate state, not an error.
- Spec + plan: `docs/superpowers/specs/2026-08-07-rettifiche-storico-design.md`,
  `docs/superpowers/plans/2026-08-07-rettifiche-storico.md`.

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
  - `frontend/components/pratica/RettificheTab.tsx` — `RettificheTab` component, `recalcAggregates`, the two-tab render block (moved from `app/infrannuale/page.tsx`, see "Il percorso unico Pratica" below)
  - `frontend/lib/pratica-rettifiche-rules.ts` — `PROPOSAL_RULES`, `COUNTERPART_GROUPS`, `DEBT_GROUPS`
  - `frontend/lib/ivcee-catalog.ts` — le etichette (`labelOf`), il rientro (`isDettaglio`) e `COUNTERPART_OPTIONS`
  - `frontend/lib/pratica-reconcile.ts` — `reconcileSubfields`
  - `frontend/hooks/use-rettifiche-year.ts` — per-year load/save/reset/corrections, one instance per tab; imports `reconcileSubfields` directly

**Etichette dal catalogo (2026-08-11).** Ogni riga di Rettifiche rende ora `labelOf(field)`, la grafia
**autonoma** del catalogo. Il cambiamento visibile è sulle sotto-righe dei debiti: mostrano
`Debiti vs fornitori (entro)` invece di `entro 12 mesi`. La forma breve funziona solo sotto
un'intestazione che la spieghi — nel prospetto del Confronto c'è, nel giornale delle rettifiche no.
Il **rientro** delle sotto-voci non si legge più dai due spazi iniziali di un'etichetta: lo dichiara
il catalogo (`isDettaglio`). Non è `depthOf(code) > 0`: sulle 78 righe passate a `renderSection`,
la profondità ne selezionerebbe 42 contro 32 — le 10 di scarto sono `sp12a..h` e `ce17a/b`, che hanno
un padre nel catalogo ma portano già la propria lettera di schema (`A.II)`, `18)`) e restano a filo.
Il confronto è pinnato in `ivcee-catalog-parity.test.ts`.

Le **intestazioni di raggruppamento** dello schema art. 2424 (`B) Immobilizzazioni`,
`C) Attivo circolante`, `A) Patrimonio netto`) sono righe di **resa** dichiarate dentro
`RettificheTab.tsx`, non voci del catalogo: non hanno codice, non sono editabili e non compaiono in
`VOCI`. Un'intestazione si stampa sopra la prima riga **visibile** del proprio gruppo, così un gruppo
interamente filtrato non lascia un'intestazione orfana.

**Struttura (2026-08-10):** `RettificheTab` vive in `frontend/components/pratica/RettificheTab.tsx`; le sue regole di partita doppia e il layout righe stanno in `frontend/lib/pratica-rettifiche-rules.ts`. La vecchia nota parlava di ~15 costanti condivise con le tab Confronto e Proiezione: verificate una per una, l'unica davvero condivisa era `DETAIL_PARENTS` (ora in `lib/pratica-codes.ts`, usata da tutti e tre — `RettificheTab`, `ComparisonTable`, `ProjectionTable` — per decidere quando mostrare una riga di dettaglio). Non è servito alcun modulo ponte.

### Il percorso unico "Pratica" (2026-08-08)
Two workflows for a new pratica, down from three: **Da bilancio** (`/pratica`) and **Startup**
(`/budget` in `startupMode`). The removed third card was "Budget da bilancio ufficiale, no
rettifiche" — precisely the path that let a trial balance skip Rettifiche and propagate its errors
into Confronto, Proiezione, Indicatori and the rating models. `/infrannuale` is now a `redirect()`
to `/pratica`; the wizard itself (import → Rettifiche → Confronto → Proiezione → Indicatori →
Stampa, described in the Rettifiche section above) moved file-for-file to `app/pratica/page.tsx`
with no behaviour change in that move itself — the functional changes below came after.
Spec: `docs/superpowers/specs/2026-08-08-percorso-unico-pratica-design.md`. Plan:
`docs/superpowers/plans/2026-08-08-percorso-unico-pratica.md`. Execution ledger (every deviation
from the plan, found in browser testing rather than in review):
`.superpowers/sdd/2026-08-08-percorso-unico-pratica/progress.md`.

- **`contexts/PraticaContext.tsx`** — the active pratica (`workflow`, `companyId`, `fiscalYear`,
  `periodMonths`, `infrannualeScenarioId`, `budgetScenarioId`, `analysisStep`,
  `rettificheConfirmed`), persisted in `localStorage` (`xbrl_pratica`) with the same pattern as
  `startupMode`: read in a `useEffect`, never in the `useState` initializer, or Next mis-hydrates.
  `PraticaProvider` is mounted ABOVE `AppProvider` in `app/layout.tsx` — that ordering is what lets
  `AppContext` itself call `usePratica()` (see below).

**A three-phase model replaced the earlier flat step list (2026-08-09).** `lib/pratica-steps.ts`
is the pure, React-free module that decides everything: `buildPraticaSteps(pratica, gates)` returns
the ordered `PraticaStep[]` for the current workflow, each tagged with a `phase`
(`"dati" | "analisi" | "previsionale"`, `PHASE_ORDER`) and a `group` (`"azione"` advances the
pratica, `"vista"` is read-only and can be visited in any order). `kind: "tab"` steps are tabs
inside `/pratica` (`setAnalysisStep` + `router.push("/pratica")` if not already there); `kind:
"route"` steps are real Next pages (`router.push(step.route)`). It also owns `praticaGates`
(the single gate derivation, shared by the stepper and the action bar so they can't diverge),
`currentStepId`, `nextStep`/`prevStep`, `phaseStatus` (chip state: `done`/`active`/`todo`/`locked`)
and `gateReason` (the tooltip text for a locked step). **This module has its own test suite,
`lib/pratica-steps.test.ts` (19 cases) — the first frontend test in the project, run with `npm test`
(Vitest) from `frontend/`.**

The three phases, for the `bilancio` workflow:
- **DATI** (tabs inside `/pratica`): Anagrafiche · Import · Rettifiche.
- **ANALISI** (tabs inside `/pratica`): Confronto · Proiezione (only when `periodMonths !== 12` —
  an already-annual bilancio is not projected to 12 months) · Indicatori · Stampa.
- **PREVISIONALE** (real routes): Budget · Indici · CE Prev. · SP Prev. · Riclassificato ·
  Rendiconto · Report — **seven** steps. `Indici` (`/analysis`) is new versus the previous flat-nav
  model, where it was unreachable from inside a pratica (see the superseded note below).

All PREVISIONALE steps but Budget are gated on `gates.forecastReady` (`budgetScenarioId !== null`);
Budget itself gates on `gates.budgetScenario` for the `bilancio` workflow and is always enabled for
`startup`.

- **`components/PraticaStepper.tsx`**, rendered by `components/Navigation.tsx` instead of the flat
  nav whenever `pratica !== null` and the path is not `/` (never both bars together). It renders
  TWO rows: phase chips (`PHASE_ORDER`, status from `phaseStatus`, a `Tooltip` with `gateReason`
  when locked) and, below, only the steps of the active phase (`azione` steps first, then a
  separator, then `vista` steps) — so the sub-bar is always short regardless of how many read-only
  views a phase has. Outside a pratica the flat nav is unchanged, minus the Importazione tab
  (`/import` still works as a route, just unlinked).
- **`components/pratica/PraticaActionBar.tsx` + `contexts/PraticaActionContext.tsx`** — the single
  point of advancement, rendered below the page content (sticky, not fixed, so it never overlaps a
  long table). A page registers its own primary action with `usePrimaryAction({ label, onClick,
  disabled, reason })`; passing `label: null` means "this step has no action of its own" and the
  bar falls back to `"Avanti: <next.label>"`, derived from `nextStep`/`gateReason` in
  `pratica-steps.ts`. Of the seven PREVISIONALE steps only Budget registers an action; the other
  six (Indici, CE Prev., SP Prev., Riclassificato, Rendiconto, Report) are read-only views that
  register nothing and rely entirely on the fallback. The old per-tab inline CTAs (8 of them,
  scattered across `app/pratica/page.tsx` and `app/budget/page.tsx`) were removed as those steps
  were migrated; **`/budget`'s Save button is
  the only survivor**, because `/budget` is also reachable outside a pratica (nav flat, voce
  "Scenari") where the action bar does not render at all — there the page registers
  `label: pratica ? "Salva e Calcola Previsionale" : null` (so inside a pratica the bar drives it)
  **and** keeps its own `<Button>` rendered only when `!pratica` (so outside a pratica saving still
  works). The "Ricalcola" button and its confirmation dialog are a distinct secondary action (with
  the "azzera modifiche manuali CE" checkbox) and were left exactly where they were.

**Moduli della pratica (2026-08-10).** `app/pratica/page.tsx` è sceso da 6.019 a 1.810 righe. Le
funzioni pure stanno in `lib/pratica-format.ts` (formattazione), `lib/pratica-codes.ts` (tabelle di
codici IV-CEE, `DETAIL_PARENTS`, `EXTRA_ALERT_DEFS`), `lib/pratica-reconcile.ts`
(`reconcileSubfields`), `lib/pratica-indicators.ts` (indicatori, scoring, `computeCrisisRating`) e
`lib/pratica-statement-rows.ts` (costruzione righe SP/CE); i componenti in `components/pratica/`.
Regola: `lib/pratica-*` non importa mai da `app/` o `components/`. Tre suite di caratterizzazione
(`lib/pratica-reconcile.test.ts`, `lib/pratica-indicators.test.ts`,
`lib/pratica-statement-rows.test.ts`) fissano il comportamento dei calcoli — fissano quello
**attuale**, non lo giudicano corretto.

**Quanto queste suite proteggono davvero è misurato, non presunto (mutation harness, 2026-08-10
final review).** Sul totale delle tre suite la mutation coverage misurata è **18% (11/61)**: la
maggior parte delle mutazioni introdotte nell'implementazione sopravvive ai test invariata. Per
`lib/pratica-indicators.ts` in particolare è **3/29** — quasi non funzionale come rete di
regressione: `computeIndicators`'s test asserisce per VALORE solo `_ebitda_raw` e `ebitda_margin`;
gli altri 17 campi di `IndicatorSet` sono verificati solo con `Number.isFinite(...)`, che nessuna
mutazione aritmetica (segno scambiato, operando sbagliato, soglia spostata) può violare — il test
passa comunque. Due asserzioni deboli in quella suite sono state corrette in questa review
(mutation-proof ora): `scoreDotColor` fissa le stringhe colore esatte invece di limitarsi a "sono
diverse a coppie", e `computeCrisisRating`'s test sui segnali extracontabili fissa i due codici
concreti (A3 → C3) invece di limitarsi a "sono diversi". Il resto della suite resta com'era.
**Non leggere questa nota come "gli indicatori sono coperti":** rafforzarla — valori distinti e
non-zero per ogni codice nominato in ogni array sommato, asserzioni per valore esatto al posto di
`Number.isFinite` — è un follow-up noto e deliberatamente non fatto in questa review (fuori
perimetro insieme al bug `sp07_crediti_lungo` mancante da `totalAssets`, anch'esso lasciato al
proprietario del progetto).

**`sp07_crediti_lungo` mancante da `totalAssets` — corretto (2026-08-10).** Il bug appena
descritto come "lasciato al proprietario del progetto" è stato risolto: `computeIndicators`
(`lib/pratica-indicators.ts`) escludeva correttamente `sp07_crediti_lungo` (crediti esigibili
oltre l'esercizio successivo) da `currentAssets` — non è attivo circolante — ma non lo
riaggiungeva mai a `totalAssets`, disallineandosi da `ATTIVO_CODES` (`lib/pratica-codes.ts`) e da
`attivoKeys` (`lib/pratica-reconcile.ts`), che lo includono entrambi. L'effetto: su un'azienda con
crediti a lungo termine significativi, il totale attivo risultava sottostimato, e quindi
`indipendenza` (equity/TA) e `roi` (EBIT/TA) risultavano SOVRASTIMATI — la direzione sbagliata per
uno strumento di rischio creditizio. Fix: `sp07_crediti_lungo` è ora sommato a `totalAssets` (non
a `currentAssets`, che resta invariato per costruzione), con un commento nel codice che spiega
l'asimmetria. La suite di caratterizzazione esistente NON avrebbe intercettato questo bug (misura
mutation coverage 3/29 su questo file, vedi sopra); non lo avrebbe nemmeno intercettato una sua
reintroduzione — il suo fixture `BS_SANA` non contiene affatto `sp07_crediti_lungo` e asserisce
solo `_ebitda_raw`/`ebitda_margin` per valore. Sono stati aggiunti due test mirati che pinnano
esattamente questo comportamento: `indipendenza` e `roi` per valore esatto su un fixture con
`sp07_crediti_lungo` non nullo, più un confronto che il `current_ratio` resta invariato in
presenza/assenza di `sp07` (pinna la metà "non va in `currentAssets`" della regola). Questo
corregge una singola omissione — non rende la suite degli indicatori adeguata nel complesso; la
mutation coverage bassa descritta sopra resta un problema aperto per tutti gli altri campi.

**Superseded note, kept for history:** an earlier version of this section said "PREVISIONALE has
SIX steps, not four" — `/analysis` (Indici) was still unreachable from inside a pratica at that
time; that gap is what the `previsionale` list above now closes.

**The Rettifiche gate ANDs `gates.rettificheOk` into every ANALISI step past Rettifiche** — not,
as an earlier version of this note claimed, into every step of the pratica: Confronto, Proiezione,
Indicatori and Stampa in `pratica-steps.ts` all require `gates.rettificheOk && …`. An earlier
version gated only `comparison`, which meant a scenario already created at import time
(`infrannualeScenarioId` set) was on its own enough to unlock Proiezione/Indicatori/Stampa in the
stepper even with rettifiche unconfirmed, or after a "Ripristina originale" — fixed in commit
`71d3303`. **None of the seven PREVISIONALE steps AND `gates.rettificheOk` directly** — they gate on
`gates.budgetScenario`/`gates.forecastReady` (`budgetScenarioId !== null`) instead. In the
new-pratica ("bilancio") flow the rettifiche gate still holds transitively, because
`budgetScenarioId` is only ever set by the promote step, which is reachable only past Rettifiche;
but a pratica **resumed from a legacy budget scenario** (`budgetScenarioId` set,
`infrannualeScenarioId` null — no ANALISI phase was ever gone through) has no rettifiche state to
gate on at all. `pratica-steps.ts`'s `isLegacyBudgetResume` check hides the whole ANALISI phase for
that case instead of rendering it enabled-but-dead (FINDING 4, 2026-08-08 final review — see
`app/page.tsx`'s `resume()`). Two sub-tabs (Storico + Bilancio di verifica,
see the Rettifiche section above) each need their own confirmation: `useRettificheYear` exposes
`confirmed: boolean` and `confirm(): Promise<boolean>`, backed by a `{ entry_type: "confirm" }`
marker appended to the same `rettifiche_log` (no migration) — idempotent, excluded from the
journal/Riepilogo UI and from the server's 20-entry cap (`_countable_log_entries` in
`backend/app/api/v1/financial_years.py`). `handleConfirmRettifiche` in `app/pratica/page.tsx` is
the SINGLE path both the "Conferma e vai al Confronto" primary action bar button and the Riepilogo dialog's own button call —
an earlier version let the dialog's button reach Confronto through a separate `onNext` that
bypassed the gate entirely (Task 7 review, Critical finding).

**`reset()` must reconcile the snapshot before sending it, mirroring `load()`.**
`FinancialYear.original_bs_snapshot`/`original_is_snapshot` are captured server-side RAW, before
the frontend-only `reconcileSubfields` ever runs. On an aggregate-only import (bilancio abbreviato
— the common shape) the raw snapshot's detail sub-fields are zero while the currently persisted
state already went through `reconcile()` at load time; posting the raw snapshot as-is widens the
aggregate/detail gap and the backend's anti-regression guard deterministically rejects it with 400
— which made "Ripristina originale" a dead button on exactly the imports that most need it. Fixed
in `9d7079b`: `reset()` now merges BS+IS, runs the same `reconcile()` over a COPY (never mutating
`data.original_*`, which is re-read on every subsequent reset), and only then splits and posts it.

**A save or reset the server rejects must never be committed locally.** `useRettificheYear.save()`
and `.reset()` return `Promise<boolean>` (`false` on any thrown error, toast already shown by the
hook); every journal-mutating call site in `app/pratica/page.tsx` (`confirmActiveEdit`,
`deleteLogEntry`, `handleConfirmRettifiche`) awaits the boolean and returns early on `false` instead
of updating `corrections`/`log`/`confirmed` optimistically. Before this a 400 from the backend still
rendered as a successful edit in the journal.

**`AppContext` now consumes `usePratica()`** (legal only because `PraticaProvider` sits above
`AppProvider`), for two behaviours found as real bugs in browser testing, not designed up front:
- `loadCompanies`'s auto-select-first-company fallback stands down while a pratica is active
  (`praticaActiveRef`). Without it, `/pratica`'s mount-time `refreshCompanies()` re-selected an
  unrelated existing company right after the home page's "Da bilancio" card had deliberately called
  `setSelectedCompanyId(null)` — `AnagraficheStep` opened in EDIT mode and "Salva e prosegui"
  silently renamed that company.
- The app-wide `selectedCompanyId` follows `pratica.companyId` (an effect keyed on the scalar, never
  on the `pratica` object). Without it, `/budget` reached via "Prosegui al Budget" listed the
  scenarios of whatever company `AppContext` happened to have selected before, not the pratica's.

**The wizard rehydrates after a refresh.** Wizard progress (`importResult`, `scenario`,
`fiscalYear`, `periodMonths`, …) lives in local `useState` and does not survive F5; only the
`PraticaContext` (localStorage-backed) does. A `useRef`-guarded effect in `app/pratica/page.tsx`
runs the rehydration exactly once: if the persisted `analysisStep` is past Import, it re-fetches the
company and the infrannuale scenario and repopulates the four local states, letting the existing
auto-load effects (Rettifiche/Confronto/Analisi) take it from there. When the context lacks enough
data (`companyId`/`infrannualeScenarioId` missing) or the fetch fails, the honest fallback is an
Italian `Alert` ("Pratica da riaprire" — riparti dall'importazione o riapri la pratica dalla home)
and a reset to the Import step — never a blank `<main>`.

**Two follow-ups the ledger records as deferred, not fixed:**
- **Il gate è applicato anche al render (2026-08-10).** `blockedStep()` in `lib/pratica-steps.ts`
  decide se lo step corrente è raggiungibile, e una guardia unica in `app/pratica/page.tsx` avvolge
  i sette rami `activeTab`. Due comportamenti deliberati: uno step **sconosciuto non blocca** (i
  workflow ne omettono di proposito — bloccare creerebbe vicoli ciechi), e il controllo legge **la
  stessa cache dello stepper**, senza interrogare il server. Quindi se la cache dice "confermato" e
  il server dice il contrario, si passa: **non è un confine di autorizzazione** e non chiude un
  exploit noto (nessuna delle review del 2026-08-08 era riuscita a costruirne uno). Il guadagno è
  che l'invariante non dipende più dal fatto che ogni sito di navigazione se la ricordi.
- **`app/pratica/page.tsx` non è più da 5.900 righe** (ora 1.810, vedi "Moduli della pratica" sopra),
  ma la decomposizione del componente wizard stesso in tab-componenti resta esplicitamente non
  fatta — quanto estratto finora sono funzioni pure e i componenti già a foglio (Rettifiche,
  Confronto, Proiezione, Indicatori, Stampa); il corpo del wizard (stato, effetti di caricamento,
  i sette rami `activeTab`) vive ancora tutto in `app/pratica/page.tsx`.

### Shared BS/IS Layout (Rettifiche, Confronto, /forecast/balance, /forecast/income)
All four financial-statement views render the same IV-CEE-format layout to keep schemas comparable.
Per aggiungere una sotto-voce, l'elenco dei file da toccare è la tabella «Aggiungere una
sotto-voce tocca QUATTRO file» qui sotto. Sostituisce l'elenco puntato che stava qui prima
del catalogo, ora inservibile: due delle sue quattro voci non esistono più (le mappe
`relabel` dentro `pratica-statement-rows.ts`, e gli array `rows` di
`app/forecast/balance/page.tsx` e `app/forecast/income/page.tsx`, che oggi leggono
`BALANCE_STATEMENT_ROWS` / `INCOME_STATEMENT_ROWS` dal catalogo).

**Catalogo IV-CEE unico (2026-08-10).** Le righe dei prospetti SP/CE vivono in
`frontend/lib/ivcee-catalog.ts`. Ogni voce porta il codice, il padre,
la sezione, l'ordine e **due etichette**: `label` (autonoma, auto-esplicativa — giornale
rettifiche, selettore contropartita, dialoghi, e ogni riga di Rettifiche) e `shortLabel`
(contestuale, breve — righe di tabella che stanno sotto l'intestazione del proprio
aggregato). `labelOf(code, "contestuale")` cade sull'autonoma quando la breve non c'è.
Quello che le viste consumano davvero è `labelOf` (Confronto/Proiezione/Stampa via
`pratica-statement-rows.ts`, e ogni riga di Rettifiche), più `isDettaglio` e
`COUNTERPART_OPTIONS` (Rettifiche) e i due elenchi di righe qui sotto. Gli accessori che
camminano l'albero — `sectionRows`, `childrenOf`, `subtree`, `voce`, `aggregate` — **esistono
ma oggi nessuna vista li chiama**: `childrenOf` è usato dal catalogo stesso per costruire il
blocco debiti di `BALANCE_STATEMENT_ROWS`, e `aggregate` compare in una sola riga di codice
applicativo, il commento di `report-composition.tsx` che **vieta** di usarlo (somma le foglie,
e su un `BalanceSheet` già aggregato dal backend restituisce 0 — vedi il `describe`
"report-composition" nel test di parità). Le regole di **resa** (filtro degli zeri,
editabilità, totali) restano di ciascuna vista; il **rientro** no, l'ha il catalogo
(`Voce.dettaglio` / `isDettaglio`, vedi la sezione Rettifiche).

**Aggiungere una sotto-voce tocca QUATTRO file, non uno.** Fino al 2026-08-11 questa
sezione (e il messaggio del commit `d044e06`) diceva che bastava toccare
`ivcee-catalog.ts` — «le sei viste la ricevono per costruzione». È falso, ed è
esattamente il genere di documentazione contro cui mette in guardia l'apertura di questo
file: descriveva un'API che il codice non offre. Per aggiungere, poniamo, `sp05f_nuova`:

| File | Perché |
|---|---|
| `frontend/lib/pratica-rettifiche-rules.ts` | `ALL_CODES` si costruisce da `RETTIFICHE_BS_*` / `DEBT_GROUPS` / `CE_*`. Un codice che non è in quegli elenchi **non entra in `VOCI`**: la sola etichetta non produce nulla. |
| `frontend/lib/pratica-codes.ts` | `parentOf` legge `DETAIL_PARENTS`. Se manca, la voce è trattata come di primo livello → `topLevelOrder` → `indexOf` → `-1`, e il test «nessuna voce resta senza ordine» diventa rosso. |
| `frontend/lib/ivcee-catalog.ts` | l'etichetta, più la riga in `BALANCE_STATEMENT_ROWS` (o `INCOME_STATEMENT_ROWS`). |
| `frontend/lib/pratica-statement-rows.ts` | l'elenco righe del Confronto è ancora una sequenza scritta a mano di chiamate `labeled("...")`: nessuno lo deriva dal catalogo. |

Il consolidamento **c'è stato**, e va misurato per quello che è: prima erano cinque file e
una decina di punti di modifica, e **tre** di quei punti erano tre mappe di etichette
diverse. Bilancio onesto allo stato attuale — le **etichette** sono passate da tre fonti a
una (più i letterali dei prospetti, vedi il paragrafo sotto); gli **elenchi di codici**
sono ancora sparsi su tre file; le **proiezioni dell'albero** (`childrenOf`, `subtree`,
`aggregate`, `sectionRows`) sono costruite ma nessuna vista le consuma.

Lo stesso file porta anche i **due elenchi di righe già impaginate**,
`BALANCE_STATEMENT_ROWS` (letto da `/forecast/balance` e da `report-appendices`) e
`INCOME_STATEMENT_ROWS` (letto da `/forecast/income`): non è solo la tassonomia, è
tassonomia **e** prospetti. Le tre grafie da cui le etichette sono derivate
(`GRAFIA_RETTIFICHE`, `GRAFIA_SELETTORE`, `CONFRONTO_RELABEL`) sono **private al
modulo** dal 2026-08-11 — erano due export di `pratica-rettifiche-rules.ts`
(`RETTIFICHE_LABELS`, `COUNTERPART_PICKER_LABELS`) e una mappa interna a
`pratica-statement-rows.ts`, cioè tre posti da cui si poteva ribattezzare una voce
senza passare dal catalogo. `pratica-rettifiche-rules.ts` conserva la **politica**
(`PROPOSAL_RULES`, `NON_POSTABLE_FIELDS`, `fieldCategory`, `COUNTERPART_GROUPS`, gli
elenchi di righe `RETTIFICHE_BS_*` / `CE_A`–`CE_E` / `DEBT_GROUPS`); `COUNTERPART_OPTIONS`
è passato al catalogo perché era l'ultimo consumatore delle due mappe, e la direzione
opposta (rules → catalogo) chiuderebbe un ciclo di import fatale al caricamento.

**Le etichette dei prospetti sono una TERZA superficie di naming, non ancora unificata.**
Le righe di `BALANCE_STATEMENT_ROWS` / `INCOME_STATEMENT_ROWS` portano un testo proprio,
distinto sia dalla grafia autonoma sia dalla contestuale del catalogo: 66 delle 97 righe
che citano una voce non coincidono con nessuna delle due. `sp04b` è `"2) Crediti entro 12
mesi"` nel prospetto, `"Crediti immobilizzati (entro)"` autonoma e `"2) Crediti (entro es.
successivo)"` contestuale — tre nomi per una voce; `ce20_imposte` è numerata `22)` nel
prospetto e `20)` nel catalogo. Nulla di ciò è una regressione (i testi sono arrivati
verbatim dalle viste), ma il ramo li ha spostati **dentro** il file che dichiara di essere
l'unica fonte del nome di una voce, senza armonizzarli. Dal 2026-08-11 sono almeno
**congelati** (`ATTESI_PROSPETTO_LABELS`, 108 coppie): prima nessun test li leggeva, perché
`rowKey` usa `r.field ?? "computed:" + r.label` e quindi delle righe che portano un campo
fissava il codice, non il testo. Un futuro «armonizziamo tutto a `labelOf`» ora si vede.

`frontend/lib/ivcee-catalog-parity.test.ts` fissa, per ogni vista, l'elenco dei codici
resi e il loro ordine. Se cambia, una vista ha perso o riordinato una riga: quegli
elenchi non vanno aggiornati per far passare il test. Fissa inoltre, con natura diversa,
**il testo di ogni etichetta** (`ATTESI_CONFRONTO_LABELS`, 87 grafie contestuali;
`ATTESI_LABELS_AUTONOME`, tutte e 100 le autonome; `ATTESI_PROSPETTO_LABELS`, le 108 righe
di prospetto che portano un campo): lì un cambiamento deliberato è
legittimo e si aggiorna la riga nello stesso commit che cambia il testo — quello che non
è legittimo è aggiornarla per far tornare verde la suite senza sapere perché il testo si
è mosso.

**L'ordine di resa di Rettifiche è dichiarato una volta sola** (2026-08-11):
`RETTIFICHE_RENDER_SECTIONS` (gli elenchi passati a `renderSection`, in ordine) e
`RETTIFICHE_RENDER_ORDER` (ogni codice reso, debiti compresi) in
`pratica-rettifiche-rules.ts`. Li consumano il componente **e** i due test. Prima ognuno
dei tre lo riscriveva a mano, e il rifacimento del test di parità aveva **perso**
`sp18_ratei_risconti_passivi`: pinnava 91 codici dove la vista ne rende 92, quindi non si
sarebbe accorto della sparizione di sp18. **Limite noto:** questo fissa quali elenchi e in
che ordine, non che il JSX li renda in quell'ordine — il componente interfoglia
intestazioni, totali e il blocco debiti fra le chiamate, quindi una riga persa o aggiunta
non può più sfuggire, una sezione spostata nel JSX sì.

Detail blocks shared across all views:
- **Immob. finanziarie (sp04):** sp04a_partecipazioni, sp04b/c_crediti_immob_breve/lungo, sp04d_altri_titoli, sp04e_strumenti_derivati_attivi. Aggregate `sp04_immob_finanziarie` is computed from sub-fields.
- **Crediti (sp06/sp07):** a through g per entro/oltre (clienti, controllate, collegate, controllanti, tributari, imposte anticipate, altri).
- **Patrimonio netto (sp12):** sp12a (sovrapprezzo) through sp12h (riserva neg. azioni proprie), with sp12g (utili portati) before sp13 and sp12h after. Aggregate `sp12_riserve` is computed from sub-fields.
- **Debiti (sp16/sp17):** 7 creditor-typed groups (`_debt_banche`, `_debt_altri_finanz`, `_debt_obbligazioni`, `_debt_fornitori`, `_debt_tributari`, `_debt_previdenza`, `_debt_altri`), each rendered as a synthetic total row followed by entro (sp16x) and oltre (sp17x) sub-rows. Group headers are pinned into `ALWAYS_SHOW_CODES` so the full OIC art. 2424 structure shows even when a group is zero; sub-rows follow the standard "hide when all years zero" filter in Confronto/forecast, but are always visible in Rettifiche so they remain editable. Aggregates `sp16_debiti_breve`/`sp17_debiti_lungo` and `total_debt` are computed.
- **P&L:** ce08a–d (personale: TFR, salari, oneri sociali, altri), ce09a–d (ammortamenti/svalutazioni), ce17a/b (rivalutazioni/svalutazioni). EBITDA + EBIT rows shown in all three pages.

**Per-year sub-field reconciliation (Confronto tab):** Bilancio abbreviato imports often populate only parent aggregates (e.g. `sp16_debiti_breve`) leaving detail sub-fields at 0. `buildBalanceItemsWithTotals` applies `reconcileSubfields` to each year column (partial/reference/prior) independently, so the gap is plugged into the "altri" bucket (`sp04a`, `sp05e`, `sp06g`, `sp07g`, `sp12e`, `sp16g`, `sp17g`) before rows are built. This mirrors the Rettifiche load-time reconciliation and prevents detail rows from being hidden by the zero-filter.

**Two known warts, left untouched deliberately (2026-08-10 — found while decomposing `page.tsx`, not fixed as part of that move):**
- `buildBalanceItemsWithTotals` maps over the CALLER's `rawItems`, so a reconciliation plug computed for a code the caller never sent is silently dropped — it exists in the internal reconciled map but its row never renders. The caller must include the detail rows (even as zeros) in `rawItems` for a plug to be visible.
- `buildIncomeItemsWithEbitda`'s `periodMonths` parameter is effectively dead: `const factor = 12 / periodMonths` (`lib/pratica-statement-rows.ts:257`) is computed and never read anywhere in the function, so the output does not actually vary with it. Annualisation of CE rows comes entirely from the caller-supplied `annualized_value`, not from this parameter. Two more locals in the same function are dead for the same reason: `partialRevenue` and `refRevenue` (`lib/pratica-statement-rows.ts:337-338`) are computed and never read either.

**Recap dialog (Riepilogo Rettifiche):** aggregate rows that were updated indirectly by `recalcAggregates` (any field in `NON_POSTABLE_FIELDS`) render in muted-gray italic with a tooltip explaining they are derived totals, so the user doesn't mistake them for duplicated postings.

### Projection Tab (Proiezione P&L editable overrides)
Expanded `EDITABLE_CE_CODES` to cover **22 CE fields** (ce01–ce20 plus ce08/09/11/17 sub-fields), so the user can override almost every projected P&L line directly in the Proiezione table.

- **Backend override plumbing:** `calculateProjectedBS` sends the full set of override fields the backend schema supports (`ce02_override`, `ce03_override`, `ce10_override`, `ce11_override`, `ce13_override` through `ce19_override`). For ce17 the picker exposes `ce17a` and `ce17b` separately; the backend stores the net (`ce17a − ce17b`) in `ce17_override`. For `ce20_imposte`, the override is translated to an effective `tax_rate` (`ce20 / PBT × 100`) so the forecast engine reproduces it.
- **Consistency:** `ProjectionTable`'s `PROJ_COST_CODES_ALL` includes `ce11b_altri_accantonamenti` (matches `calculateProjectedBS`'s `EBITDA_COST_CODES`), and `projRettifiche` is derived from `pv("ce17a") − pv("ce17b")` so edits flow into PBT → net profit. BS `sp13` now always agrees with the P&L utile displayed above it.
- **Gotcha:** `buildBalanceItemsWithTotals` must NOT overwrite `annualized_value` when called from `calculateProjectedBS` — the Projection tab writes projected BS values into that field. Only `partial_value`, `reference_value`, `prior_value` are reconciled per year.

### Indicatori charts (Indicatori tab + Stampa)
`components/pratica/IndicatoriCharts.tsx` holds both bar charts ("Incidenza economica sui ricavi",
"Equilibrio finanziario e strutturale") and is rendered by **both** views — the configs are the
same object, so they are not duplicated. Series **labels** stay with each caller (`Infrann. 9M` in
the tab, `Infrann. 9M 2026` in Stampa). `buildIndicatorChartData` (`lib/pratica-indicators.ts`) is
the pure part and the only testable one — the suite runs `environment: "node"`, no DOM; a `null`
series is **dropped, not rendered as zero**. Known limit: the percentage indicators divide by
`ce01_ricavi_vendite` alone, so a company invoicing on `ce04` yields a meaningless axis (AIC SRL:
EBITDA % 80.395,7%). → `docs/frontend/INDICATORI-E-STAMPA.md`

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
  - `frontend/app/pratica/page.tsx` — `StampaContent` state, `buildAICtx()`, `CommentBlock`

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

> ⚠️ **Leggi `forecast_generated`, non l'HTTP 200** — vedi «Invarianti e trappole › Previsionale».
> I chiamanti che già lo fanno: `/budget` e i due punti di chiamata del wizard della pratica.

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
- **MinerU non va MAI sul VPS**: vedi «Invarianti e trappole › Ambiente»
- **Decimal precision**: Numeric(15, 2) - max 9,999,999,999,999.99
- **JSON serialization**: Backend uses custom `DecimalJSONResponse` (Decimal → float)
- **Italian locale**: UI text in Italian, European number formatting
- **Authentication**: Supabase JWT via iframe postMessage (see below). Dev mode: `DEV_USER_ID` env var bypasses JWT.
- **CORS**: Allows localhost:3000-3002 (Next.js), 8501 (Streamlit), plus Formula Finance origin in production
- **Frontend UI**: shadcn/ui components only - no raw HTML tables/buttons
- **Charts**: Recharts with `ChartContainer` + CSS variable colors (blue/slate palette)
- **Status colors**: Altman/FGPMI use explicit green/yellow/red with `dark:` variants
- **No emojis**: Use lucide-react icons instead
- **Tailwind `content`**: a class name written in a file `content` does not scan is **never
  generated** — no error, just an unstyled element. `lib/`, `hooks/` and `contexts/` are in the
  globs because `lib/pratica-indicators.ts` returns class names; `lib/tailwind-content.test.ts`
  pins the invariant. Grepping the CSS for `.bg-green-500` also matches `.bg-green-500\/10`, so
  verify against the exact rule or in the browser. → `docs/frontend/TAILWIND-E-CLASSI.md`
- **Print/PDF**: verifying a print layout requires **generating the PDF** — `emulateMedia` gives
  the right measurements but does not paginate, so it never reveals a bad page break. A chart
  needs `print:break-inside-avoid` on its Card: `globals.css` protects `.recharts-wrapper`, not
  the card around it. → `docs/frontend/INDICATORI-E-STAMPA.md`

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
- `/import` - XBRL/CSV/PDF upload (not linked from the nav; the pratica wizard's Import step is the normal entry point)
- `/pratica` - Percorso unico da bilancio: Anagrafiche → Import → Rettifiche → Confronto → [Proiezione] → Indicatori → Stampa → bridge to Budget. `/infrannuale` redirects here. See "Il percorso unico Pratica" below.
- `/budget` - Scenario assumptions editor (also the Startup workflow's entry point)
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

## Mappa della documentazione

Ogni riga è la **domanda** a cui quella pagina risponde. Se la tua domanda non è qui, il posto
giusto è il codice, non `/docs`.

| Domanda | Dove |
|---|---|
| Come funziona l'API, con esempi di chiamata? | [README.md](README.md) |
| Che cosa c'è in `/docs`, e che cosa è superato? | [docs/README.md](docs/README.md) |
| **Import** — routing, estrazione, netting, quadrature, infrannuale, persistenza | la tabella nella sezione «Import PDF» qui sopra (9 pagine in `docs/import/` + `docs/FIXING-IMPORT.md`) |
| Una voce XBRL in che campo `sp`/`ce` va a finire? | [docs/taxonomy/XBRL_PCI_IV_CEE_Mapping.md](docs/taxonomy/XBRL_PCI_IV_CEE_Mapping.md), [TASSONOMIA.md](docs/taxonomy/TASSONOMIA.md) |
| Come si costruisce un budget e che cosa fa il motore di previsione? | [docs/budget/FORECASTING_GUIDE.md](docs/budget/FORECASTING_GUIDE.md) |
| Come si provano gli endpoint degli scenari? | [docs/budget/TEST_BUDGET_API.md](docs/budget/TEST_BUDGET_API.md) |
| Che cosa manca al `/report` rispetto al PDF di riferimento? | [docs/budget/FINAL-REPORT-PDF.md](docs/budget/FINAL-REPORT-PDF.md) |
| Un grafico degli Indicatori è sbagliato, o la Stampa impagina male? | [docs/frontend/INDICATORI-E-STAMPA.md](docs/frontend/INDICATORI-E-STAMPA.md) |
| Una classe Tailwind non produce alcuno stile e non c'è errore? | [docs/frontend/TAILWIND-E-CLASSI.md](docs/frontend/TAILWIND-E-CLASSI.md) |
| Come si incastra l'app nell'iframe di Formula Finance, JWT compreso? | [docs/deployment/IFRAME_INTEGRATION.md](docs/deployment/IFRAME_INTEGRATION.md) |
| Come si rilascia, e che cosa va configurato in produzione? | [docs/deployment/](docs/deployment/) (`README_DEPLOYMENT`, `PRODUCTION_CONFIG`, `NETLIFY_CHECKLIST`, `DEPLOYMENT_SUMMARY`) |
| Perché una scelta è stata fatta così? | `docs/superpowers/specs/` (design) e `docs/superpowers/plans/` (esecuzione) |
| La documentazione dice ancora il vero? | `/riallinea` (`.claude/skills/riallinea/`), rapporti in `docs/superpowers/allineamento/` |

> **Questa mappa è parziale, e resterà parziale finché lo snellimento non è concluso.** Rettifiche,
> percorso Pratica e layout SP/CE vivono ancora dentro questo file invece che in una pagina propria
> (Task 2-5 di [2026-08-14-claude-md-snellito](docs/superpowers/plans/2026-08-14-claude-md-snellito.md)).
