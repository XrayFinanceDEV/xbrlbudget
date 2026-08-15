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

7. **ADMIN / UPLOAD TRACKING (3 endpoints)**: `GET /admin/uploads`, `/{id}`, `/{id}/download` —
   solo per chi mantiene il servizio, autenticati per header, mai chiamati dall'iframe.
   Vedi «Upload Tracking» più sotto.

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
> **import**, **Rettifiche**, **percorso Pratica**, **layout SP/CE**, **tab Proiezione/Stampa**,
> **upload tracking** e **API del previsionale**. Restano da setacciare le sezioni generali
> (`Quick Reference`, `Architecture`, `Development Workflow`, `Common Tasks`): l'assenza qui di
> una regola che le riguardi non significa che non esista.

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
  200.** Un previsionale rifiutato torna comunque 200, con `success: true` e la ragione in
  `message`. Non fidarsi nemmeno di `forecast_years`: nella risposta di fallimento contiene gli
  anni delle **ipotesi salvate**, non degli anni prodotti — a restare vuoto è
  `analysis.forecast_years` della `GET` successiva. Ignorarlo dipinge una colonna Proiezione
  vuota sotto un toast verde. `PATCH /ce-override` e `POST /generate`, sullo stesso motore e
  sullo stesso errore, rispondono invece 4xx/5xx.
  → `docs/import/REGOLE-IMPORT-05-INFRANNUALE.md` §6, `docs/budget/API-PREVISIONALE.md` §1
- **Un override vince sulla percentuale di crescita, e sopravvive al salvataggio.** «Salva e
  Calcola Previsionale» non ne azzera nessuno: si può cambiare `revenue_growth_pct` quanto si
  vuole e vedere il previsionale non muoversi. Solo la casella *«Azzera le modifiche manuali del
  CE previsionale»* del dialogo Ricalcola li cancella — e cancella le sole colonne il cui nome
  finisce per `_override`: `sp_overrides` (il sacco JSON scritto da `/forecast/balance`) **non
  viene toccato**.
- **`sp_overrides` clampa a zero i valori negativi** (tranne `sp13_utile_perdita` e
  `sp12h_riserva_neg_azioni_proprie`) e **ignora in silenzio** una chiave che non esiste nel
  risultato: un override negativo, o scritto male, non dà errore — dà uno zero.
- **Promuovere una proiezione CANCELLA il `FinancialYear` annuale già esistente** per quella
  azienda e quell'anno (`period_months` `NULL` o `12`), con BS e IS in cascata: anche se era
  stato importato a mano. La cancellazione è dentro la stessa transazione della copia, quindi un
  fallimento la annulla; un promote riuscito no.

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
- **Aggiungere una voce a SP o CE non è un'operazione a un file solo.** Serve il codice negli
  elenchi, il padre, l'etichetta e la riga del Confronto: saltarne uno produce una voce che non
  compare da nessuna parte, senza alcun errore. La tabella completa è nella sezione «Layout SP/CE»
  qui sotto — una versione precedente di questo file diceva che bastava il catalogo, ed era falsa.
- **Una sotto-voce nuova va aggiunta anche a `reconcileSubfields`.** Se entra in un aggregato
  riconciliato (`sp04`, `sp05`, `sp06`, `sp07`, `sp12`, `sp16`, `sp17`, `ce08`, `ce09`) ma non nella
  lista dei dettagli di quell'aggregato, il suo importo viene contato **due volte**: il secchio
  «altri» riassorbe il divario. Gli aggregati continuano a quadrare e il foglio pareggia; sbagliano
  solo le righe di dettaglio, cioè quelle che l'utente legge.
- **I due spazi iniziali di un'etichetta di prospetto sono comportamento, non estetica.**
  `/forecast/balance` e `report-appendices` leggono `label.startsWith("  ")` per decidere il rientro
  **e** se nascondere la riga di dettaglio; le etichette del catalogo sono `trim()`ate.
  Armonizzare i prospetti a `labelOf` farebbe sparire quelle righe senza un solo errore.
- **`aggregate()` del catalogo IV-CEE somma le FOGLIE.** Sul `BalanceSheet` che arriva da
  `/analysis`, già aggregato dal backend con le sotto-voci a zero, restituisce **0** su `sp04`,
  `sp06` e `sp07`: sostituire una somma scritta a mano con `aggregate()` azzera immobilizzazioni e
  crediti nel grafico stampato, in silenzio.
- **I commenti AI dell'infrannuale hanno un'allowlist di sei chiavi.** `save_infrannuale_comments`
  tiene `overall`, `ce_confronto`, `sp_confronto`, `ce_proiezione`, `sp_proiezione`, `indicatori`
  e **scarta il resto senza dirlo**, restituendo comunque `{"success": true}`: un settimo
  commento aggiunto lato client si salva «con successo» e sparisce al ricaricamento.
- **Gli elenchi di codici congelati in `ivcee-catalog-parity.test.ts` non si aggiornano per far
  tornare verde la suite.** Se cambiano, una vista ha perso o riordinato una riga: è quello il
  difetto. L'unica eccezione è una riga aggiunta di proposito, che si aggiorna nello stesso commit.
  Gli elenchi di **etichette** sono un'altra cosa: lì un cambiamento deliberato è legittimo, purché
  si sappia perché il testo si è mosso.

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
- **Overrides**: ogni riga di CE (32 colonne `ce*_override`) e ogni voce di SP (il sacco JSON
  `sp_overrides`) può essere forzata a un valore assoluto, che vince sulla percentuale di
  crescita. Modificabili da `/forecast/income` e `/forecast/balance`.
- **Giorni di rotazione**: DSO/DIO/DPO non impostati si derivano dall'anno base (360 giorni), e
  il circolante scala con ricavi e costi previsionali, override compresi.

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
- **Promote** (`POST /scenarios/{id}/promote`, `backend/app/services/promote_service.py`): copia la
  proiezione in un `FinancialYear` annuale, che può poi fare da anno base a uno scenario budget.
  Due cancelli semantici (`check_quadratura(...).semantic_valid`, **non** una soglia in euro) e
  una sostituzione distruttiva dell'anno annuale esistente — vedi «Invarianti e trappole ›
  Previsionale» e [docs/budget/API-PREVISIONALE.md](docs/budget/API-PREVISIONALE.md) §5
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

### Layout SP/CE (Rettifiche · Confronto · /forecast/balance · /forecast/income)

Nome, padre, sezione e ordine di ogni voce vengono dal catalogo `frontend/lib/ivcee-catalog.ts`; le
righe rese sono quattro elenchi distinti su sette viste. **Aggiungere una sotto-voce tocca quattro
file sempre, sei quando entra in un aggregato riconciliato o in un elenco congelato dai test** —
saltarne uno produce una voce che non compare da nessuna parte, senza alcun errore:

| File | Che cosa |
|---|---|
| `lib/pratica-rettifiche-rules.ts` | il codice in `RETTIFICHE_BS_*` / `DEBT_GROUPS` / `CE_*`: fuori di lì non è editabile e non entra in `VOCI` |
| `lib/pratica-codes.ts` | il padre in `DETAIL_PARENTS`, o il codice in `ATTIVO_CODES`/`PASSIVO_CODES` se è di primo livello |
| `lib/ivcee-catalog.ts` | l'etichetta, più la riga in `BALANCE_STATEMENT_ROWS` / `INCOME_STATEMENT_ROWS` |
| `lib/pratica-statement-rows.ts` | la riga del Confronto, che è ancora scritta a mano |
| *+ `lib/pratica-reconcile.ts`* | se la voce entra in un aggregato riconciliato, o il suo importo viene contato due volte in silenzio (poi gli elenchi congelati di `ivcee-catalog-parity.test.ts`) |

**Devi aggiungere una voce a SP o CE, o una vista rende una riga diversa dalle altre?** → [docs/frontend/LAYOUT-SP-CE.md](docs/frontend/LAYOUT-SP-CE.md)

### Tab Proiezione, tab Stampa, grafici Indicatori

La Proiezione rende 22 righe di CE modificabili a mano e ne ricalcola i sottototali; da lì
`calculateProjectedBS` costruisce lo SP proiettato e salva le ipotesi. La Stampa porta sei
commenti generati da Haiku e poi editabili. I due grafici degli indicatori sono un componente
solo (`components/pratica/IndicatoriCharts.tsx`), reso sia dalla tab sia dalla Stampa.

**Come si comportano gli override della Proiezione, o i commenti AI della Stampa?**
→ [docs/frontend/PRATICA-PERCORSO.md](docs/frontend/PRATICA-PERCORSO.md) §11-§12
**Un grafico degli Indicatori è sbagliato, o la Stampa impagina male?**
→ [docs/frontend/INDICATORI-E-STAMPA.md](docs/frontend/INDICATORI-E-STAMPA.md)

### Upload Tracking

Ogni import (`/import/xbrl|csv|pdf|pdf-ocr`) salva i byte originali in
`{UPLOAD_ROOT|data/uploads}/{user_id}/{YYYY-MM}/` e ne registra l'esito nella tabella
`uploaded_files`; la ritenzione è di 90 giorni (`scripts/cleanup_uploads.py`, cron;
`UPLOAD_RETENTION_DAYS` per cambiarla). Si rileggono da `GET /api/v1/admin/uploads*`, protetti
dall'header `X-Admin-Key` che deve valere quanto la variabile d'ambiente `ADMIN_API_KEY` —
senza quella variabile l'API risponde 503, non 403.

**Un utente segnala un import sbagliato e ti serve il suo file?**
→ [docs/deployment/UPLOAD-TRACKING.md](docs/deployment/UPLOAD-TRACKING.md)

### API del previsionale (assumptions · override · generate · promote)

`PUT /scenarios/{id}/assumptions` (bulk, `auto_generate=true`) è la porta normale;
`PATCH /scenarios/{id}/ce-override` modifica le singole voci di CE già generate;
`POST /scenarios/{id}/generate` rigenera, e con `?clear_overrides=true` azzera prima le
modifiche manuali del CE; `POST /scenarios/{id}/promote` copia una proiezione infrannuale in
un `FinancialYear` annuale, che può poi fare da anno base a uno scenario budget.

⚠️ Le prime tre falliscono in modi diversi: solo il bulk risponde **200 a un previsionale
rifiutato** (vedi «Invarianti e trappole › Previsionale»).

**Corpi di richiesta, precedenze, e che cosa azzera che cosa?**
→ [docs/budget/API-PREVISIONALE.md](docs/budget/API-PREVISIONALE.md)

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
- `/forecast/balance` - Forecast BS (**editable**: le celle previsionali scrivono `sp_overrides`, non colonne `*_override`)
- `/forecast/reclassified` - Forecast BS riclassificato (sola lettura)
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
| Salvi le ipotesi e il previsionale non si muove, o non sai che cosa azzera un override? | [docs/budget/API-PREVISIONALE.md](docs/budget/API-PREVISIONALE.md) |
| Come si provano gli endpoint degli scenari? | [docs/budget/TEST_BUDGET_API.md](docs/budget/TEST_BUDGET_API.md) |
| Che cosa manca al `/report` rispetto al PDF di riferimento? | [docs/budget/FINAL-REPORT-PDF.md](docs/budget/FINAL-REPORT-PDF.md) |
| Il giornale delle rettifiche si comporta male, o non sai cosa può fare da contropartita? | [docs/frontend/RETTIFICHE.md](docs/frontend/RETTIFICHE.md) |
| Lo stepper della pratica blocca un passaggio, o il wizard si perde dopo un refresh? | [docs/frontend/PRATICA-PERCORSO.md](docs/frontend/PRATICA-PERCORSO.md) |
| Devi aggiungere una voce a SP o CE, o una vista rende una riga diversa dalle altre? | [docs/frontend/LAYOUT-SP-CE.md](docs/frontend/LAYOUT-SP-CE.md) |
| Un grafico degli Indicatori è sbagliato, o la Stampa impagina male? | [docs/frontend/INDICATORI-E-STAMPA.md](docs/frontend/INDICATORI-E-STAMPA.md) |
| Una classe Tailwind non produce alcuno stile e non c'è errore? | [docs/frontend/TAILWIND-E-CLASSI.md](docs/frontend/TAILWIND-E-CLASSI.md) |
| Un utente segnala un import sbagliato e ti serve il file esatto che ha caricato? | [docs/deployment/UPLOAD-TRACKING.md](docs/deployment/UPLOAD-TRACKING.md) |
| Come si incastra l'app nell'iframe di Formula Finance, JWT compreso? | [docs/deployment/IFRAME_INTEGRATION.md](docs/deployment/IFRAME_INTEGRATION.md) |
| Come si rilascia, e che cosa va configurato in produzione? | [docs/deployment/](docs/deployment/) (`README_DEPLOYMENT`, `PRODUCTION_CONFIG`, `NETLIFY_CHECKLIST`, `DEPLOYMENT_SUMMARY`) |
| Perché una scelta è stata fatta così? | `docs/superpowers/specs/` (design) e `docs/superpowers/plans/` (esecuzione) |
| La documentazione dice ancora il vero? | `/riallinea` (`.claude/skills/riallinea/`), rapporti in `docs/superpowers/allineamento/` |

> Ogni blocco che doveva avere una pagina propria ce l'ha: la mappa non è più parziale. Quel che
> resta dello snellimento
> ([2026-08-14-claude-md-snellito](docs/superpowers/plans/2026-08-14-claude-md-snellito.md),
> Task 7) è comprimere le sezioni superstiti di **questo** file, non produrre altre pagine.
