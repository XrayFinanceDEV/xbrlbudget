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
> che per ciascuna porta la prova nel codice. Coprono i blocchi finora passati al setaccio —
> **import**, **Rettifiche** e **percorso Pratica**: l'assenza di una regola sul layout SP/CE o sul
> previsionale non significa che non esista.

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

### Frontend
- **`PraticaProvider` sta SOPRA `AppProvider`** in `app/layout.tsx`. È quell'ordine a rendere
  legale la `usePratica()` che `AppContext` chiama per cedere alla pratica il possesso della
  selezione azienda; invertirlo fa lanciare il context al mount e l'app non parte.
- **Lo stato persistito si legge in un `useEffect`, mai nell'inizializzatore di `useState`** (Next
  sbaglia l'idratazione), **e si scrive in un `useEffect` su `[pratica]`**, mai dentro un updater
  di `setState` (`reactStrictMode` invoca gli updater due volte in sviluppo). Quell'effetto è
  autoritativo anche per la **rimozione**: separarla farebbe riscrivere la entry appena cancellata
  da un `exitPratica()` di un componente figlio nello stesso commit.
- **Il gate del percorso non è un confine di autorizzazione.** `blockedStep` e lo stepper leggono
  la stessa cache in `localStorage`, non il server: se la cache dice «confermato» e il server dice
  il contrario, si passa. È deliberato (essere più severi produrrebbe falsi blocchi) e va tenuto a
  mente prima di appoggiarci sopra qualcosa che debba davvero reggere.
- **`lib/pratica-*` non importa mai da `app/` o da `components/`.** È ciò che tiene quei moduli
  testabili in `environment: node` e senza cicli di import; l'unica dipendenza verso l'alto
  ammessa è un `import type`.
- **Un salvataggio che il server ha rifiutato non si applica mai localmente.**
  `useRettificheYear.save()` e `.reset()` restituiscono `false` (toast già mostrato), e ogni
  chiamante che muta giornale o stato deve uscire su `false`. Prima di questa regola un 400 del
  backend compariva nel giornale come una rettifica riuscita.
- **La guardia su `PUT /adjustments` è relativa, non assoluta**: rifiuta ciò che **peggiora**
  sbilancio, identità CE↔`sp13` o coerenza aggregati/dettagli, non ciò che è già sbagliato.
  Renderla assoluta renderebbe incorreggibile per sempre ogni import già sbilanciato — che è
  esattamente il file per cui le Rettifiche esistono.
- **`original_*_snapshot` è catturato grezzo dal server**, prima che `reconcileSubfields` giri lato
  client. Su un import per soli aggregati (abbreviato) rimandarlo tale e quale **allarga** il
  divario aggregati/dettagli e la guardia lo respinge: `reset()` deve riconciliare una **copia**
  (mai mutare `data.original_*`, riletto a ogni ripristino successivo) prima di inviare.
- **Un delta registrato su un campo aggregato viene cancellato in silenzio.** `recalcAggregates`
  ricostruisce `sp04`, `sp05`, `sp06`, `sp07`, `sp12`, `sp16`, `sp17`, `ce08`, `ce09`, `ce17` dai
  sotto-campi e `sp13` dal CE: per questo stanno in `NON_POSTABLE_FIELDS`. Toglierne uno produce
  rettifiche che spariscono senza errore.
- **Lo stato di un foglio caricato si azzera al cambio di identità** (`[companyId, year,
  periodMonths]`). Senza, si scrivono i valori di un periodo dentro il `FinancialYear` di un altro:
  il backend risolve esattamente il record che gli è stato chiesto, il foglio quadra, e nessun
  controllo se ne accorge — un record parziale e uno annuale **coesistono di proposito** per lo
  stesso anno.
- **Un hook che restituisce un oggetto letterale non va mai messo intero in un array di dipendenze
  `useEffect`**: l'identità cambia a ogni render, l'effetto si ri-innesca da solo — anche per il
  `setLoading` che lui stesso ha provocato — e raddoppia le chiamate di rete. Dipendere dai singoli
  campi (`storico.data`, `storico.load`, …); gli `eslint-disable` su quegli effetti sono deliberati.
  Vale anche per l'oggetto `pratica`: cambia identità a **ogni** `updatePratica`, quindi un effetto
  che lo osserva intero riparte pure quando il campo che gli interessa non si è mosso — si dipende
  dagli scalari (`pratica?.companyId`).

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

Il giornale delle correzioni sul bilancio importato, step DATI › Rettifiche del percorso Pratica.
Una tab per anno (storico + bilancio di verifica), entrambe da confermare prima di proseguire.
Tre modi di proposta — rettifica e riclassifica in partita doppia, «Correggi Import» in partita
singola — con tetto di 20 voci e una guardia anti-regressione lato server.

Vive in `frontend/components/pratica/RettificheTab.tsx` e `frontend/hooks/use-rettifiche-year.ts`;
la politica di partita doppia in `frontend/lib/pratica-rettifiche-rules.ts`.

**Il giornale si comporta male, o non sai che cosa può fare da contropartita?**
→ [docs/frontend/RETTIFICHE.md](docs/frontend/RETTIFICHE.md)

### Il percorso unico "Pratica"

Due workflow: **Da bilancio** (`/pratica`) e **Startup** (`/budget` in `startupMode`);
`/infrannuale` è un `redirect()` a `/pratica`. Tre fasi: **DATI** (Anagrafiche · Import ·
Rettifiche) e **ANALISI** (Confronto · Proiezione · Indicatori · Stampa) come tab dentro
`/pratica`, **PREVISIONALE** come sette rotte reali (Budget · Indici · CE Prev. · SP Prev. ·
Riclassificato · Rendiconto · Report). Nulla oltre le Rettifiche è raggiungibile finché non sono
confermate. Fasi, step e gate vivono in `frontend/lib/pratica-steps.ts` (modulo puro, con la sua
suite); lo stato in `contexts/PraticaContext.tsx`, lo stepper in `components/PraticaStepper.tsx`,
l'unico punto di avanzamento in `components/pratica/PraticaActionBar.tsx`, il wizard in
`app/pratica/page.tsx`.

**Lo stepper blocca un passaggio, o il wizard si perde dopo un refresh?** → [docs/frontend/PRATICA-PERCORSO.md](docs/frontend/PRATICA-PERCORSO.md)

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
- `/pratica` - Percorso unico da bilancio: Anagrafiche → Import → Rettifiche → Confronto → [Proiezione] → Indicatori → Stampa → bridge to Budget. `/infrannuale` redirects here. → [docs/frontend/PRATICA-PERCORSO.md](docs/frontend/PRATICA-PERCORSO.md)
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
| Il giornale delle rettifiche si comporta male, o non sai cosa può fare da contropartita? | [docs/frontend/RETTIFICHE.md](docs/frontend/RETTIFICHE.md) |
| Lo stepper della pratica blocca un passaggio, o il wizard si perde dopo un refresh? | [docs/frontend/PRATICA-PERCORSO.md](docs/frontend/PRATICA-PERCORSO.md) |
| Un grafico degli Indicatori è sbagliato, o la Stampa impagina male? | [docs/frontend/INDICATORI-E-STAMPA.md](docs/frontend/INDICATORI-E-STAMPA.md) |
| Una classe Tailwind non produce alcuno stile e non c'è errore? | [docs/frontend/TAILWIND-E-CLASSI.md](docs/frontend/TAILWIND-E-CLASSI.md) |
| Come si incastra l'app nell'iframe di Formula Finance, JWT compreso? | [docs/deployment/IFRAME_INTEGRATION.md](docs/deployment/IFRAME_INTEGRATION.md) |
| Come si rilascia, e che cosa va configurato in produzione? | [docs/deployment/](docs/deployment/) (`README_DEPLOYMENT`, `PRODUCTION_CONFIG`, `NETLIFY_CHECKLIST`, `DEPLOYMENT_SUMMARY`) |
| Perché una scelta è stata fatta così? | `docs/superpowers/specs/` (design) e `docs/superpowers/plans/` (esecuzione) |
| La documentazione dice ancora il vero? | `/riallinea` (`.claude/skills/riallinea/`), rapporti in `docs/superpowers/allineamento/` |

> **Questa mappa è parziale, e resterà parziale finché lo snellimento non è concluso.** Il layout
> SP/CE, le tab minori, l'upload tracking e le API del budget vivono ancora dentro questo file
> invece che in una pagina propria
> (Task 4-5 di [2026-08-14-claude-md-snellito](docs/superpowers/plans/2026-08-14-claude-md-snellito.md)).
