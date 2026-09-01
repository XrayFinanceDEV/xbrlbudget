# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**XBRL Budget** — Italian GAAP (OIC) financial analysis and credit rating: ratios, Altman Z-Score,
FGPMI rating, plus **intra-year analysis** (a partial period projected to 12 months).

Two apps share the same SQLite database and the same modules (`database/`, `calculations/`,
`importers/`, `data/`, `config.py`): **FastAPI + Next.js 15** in production, and the Streamlit app in
`legacy/` (deprecated, reference only — new work goes to the modern stack).

**Multi-tenancy:** the app runs inside a Formula Finance iframe. A Supabase JWT identifies the user;
every row hangs off `Company.user_id` (max 50 companies per user).

## Quick Reference

**Project root:** the owner works on Windows (`C:\DEV\xbrlbudget-main\xbrlbudget`,
`venv\Scripts\activate`); the POSIX commands below are the exact equivalent.

**Where things are:** `backend/` (FastAPI) · `frontend/` (Next.js 15 + TypeScript, API client only) ·
`database/` (ORM models + query helpers) · `calculations/` (ratios, Altman, FGPMI, forecast,
infrannuale) · `importers/` (XBRL/CSV/PDF) · `pdf_service/` (report PDF + EM-Score) · `data/`
(taxonomy mappings, rating tables, sectors) · `config.py` · `tests/` · `docs/` · `legacy/` ·
`financial_analysis.db` (SQLite, project root). Everything outside `backend/` and `frontend/` is
**shared** — one copy, no duplication.

**Run (dev):**
```bash
cd backend && source venv/bin/activate          # Windows: venv\Scripts\activate
DEV_USER_ID=dev-user-001 uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
cd frontend && npm run dev                      # http://localhost:3000
```

**Budget workflow:** import → `POST /companies/{id}/scenarios` → `PUT /scenarios/{id}/assumptions`
(bulk, every year at once, `auto_generate=true`) → `GET /scenarios/{id}/analysis`. Optional:
`PATCH /scenarios/{id}/ce-override` and `POST /scenarios/{id}/generate?clear_overrides=true`.

**Infrannuale workflow:** import with `period_months` → rettifiche **once per year**
(`GET`/`PUT /companies/{id}/years/{year}/adjustable|adjustments` — the partial year and its
reference year each have their own journal and their own 20-entry cap; `period_months` omitted =
full year) → scenario `scenario_type="infrannuale"` → `GET /scenarios/{id}/comparison` →
`PUT /scenarios/{id}/assumptions` → `GET /scenarios/{id}/analysis`. Optional: the six AI comments
(`GET|POST|PUT /scenarios/{id}/infrannuale/ai-comments`) and `POST /scenarios/{id}/promote`.

**Commands:**

```bash
# First-time setup
cd backend && python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt
cd .. && python -c "from database.db import init_db; init_db()"
cd frontend && npm install

# Backend in production mode (JWT required, no DEV_USER_ID)
SUPABASE_JWT_SECRET=<secret> uvicorn app.main:app --host 127.0.0.1 --port 8000
# API: http://localhost:8000/api/v1 · Swagger: http://localhost:8000/docs

# Tests
cd tests && python test_db.py    # also test_calculations.py, test_fgpmi.py, test_xbrl_import.py
cd frontend && npm test          # Vitest: lib/pratica-*, ivcee-catalog-parity, tailwind-content

# Reset the database (DELETES everything)
python -c "from database.db import drop_all, init_db; drop_all(); init_db()"
```

## Architecture

### API — INPUT → ASSUMPTIONS → OUTPUT

The router exposes 62 routes. The workflow above uses the ones that matter; the rest are legacy or
per-year detail. Two things about them are worth knowing:

- **Import endpoints are four, not three:** `POST /api/v1/import/{xbrl|csv|pdf|pdf-ocr}`. XBRL = 6
  taxonomies; CSV = TEBE format; PDF = PyMuPDF + Claude Haiku (**not** Docling — that path is dead
  code with no caller left); `pdf-ocr` = MinerU, off on the VPS. All but `csv` take `period_months`
  (1-11 = partial year). `GET /import/capabilities` exists and is deliberately not wired to the UI.
  Admin side: `GET /admin/uploads[/{id}[/download]]`, `X-Admin-Key` header, never called by the iframe.
- **Prefer extending `/analysis` to adding an endpoint — but that intent is not a description of the
  code.** The reclassified statement and the detailed cashflow have live endpoints of their own
  (`GET /scenarios/{id}/reclassified`, `/detailed-cashflow`, called by `/forecast/reclassified` and
  `/cashflow`), and the Indici page reads `GET /companies/{id}/years/{year}/calculations/complete`.
  One call per page is the target, not the current state. The only routes with **no caller at all**
  are `GET /companies/{id}/years/{year}/calculations/{altman|fgpmi|ratios}`: their wrappers still sit
  in `frontend/lib/api.ts`; use `/analysis` rather than reviving them.

### Authentication & Multi-Tenancy

The iframe parent sends a Supabase JWT by `postMessage`; the frontend puts it on every request as
`Authorization: Bearer`, the backend decodes it, takes `user_id` from `sub`, and scopes every query
by it. **Every** route depends on `get_current_user_id`, and another user's company answers **404**,
not 403. Files: `backend/app/core/auth.py` (`get_current_user_id()`, JWT or `DEV_USER_ID` fallback),
`backend/app/core/ownership.py` (`validate_company_owned_by_user`, `check_company_limit`),
`frontend/contexts/AuthContext.tsx` + `frontend/lib/api.ts` (listener, Bearer injection, 401
re-auth; in dev a 1s timeout stops the spinner so unauthenticated calls run). Env:
`SUPABASE_JWT_SECRET` (HS256, production) · `DEV_USER_ID` · `MAX_COMPANIES_PER_USER` (default 50).
Protocol and deployment: [docs/deployment/IFRAME_INTEGRATION.md](docs/deployment/IFRAME_INTEGRATION.md).

### Shared modules and calculators

`backend/app/main.py` puts the project root on `sys.path`, so backend code imports the shared modules
directly (`from database.models import Company`, `from calculations.ratios import
FinancialRatiosCalculator`, …). One copy each, used by backend, legacy Streamlit and the test
scripts. The calculators layer up inside `calculations/` — `base.py` (safe_divide, rounding) →
`ratios.py` → `altman.py` / `rating_fgpmi.py` → `forecast_engine.py` (budget) and
`intra_year_engine.py` (infrannuale) — and take ORM objects, not dicts, working in `Decimal`.

### Database schema

`financial_analysis.db` in the project root (`DATABASE_PATH` overrides the location).

- `Company` (name, tax_id, sector 1-6, `user_id`; unique on `(user_id, tax_id)`) → `FinancialYear` →
  `BalanceSheet` (sp01-sp18, art. 2424) + `IncomeStatement` (ce01-ce20, art. 2425)
- `BudgetScenario` (`scenario_type`, `base_year`, `period_months`, AI comments) → `BudgetAssumptions`
  (growth percentages + 32 `ce*_override` columns + the `sp_overrides` JSON bag) → `ForecastYear` →
  `ForecastBalanceSheet` / `ForecastIncomeStatement`
- `UploadedFile` — one row per import (see «Upload Tracking»)
- Every relationship is `cascade="all, delete-orphan"`: deleting a company deletes everything below it.

**`period_months`: `NULL` or `12` means full year**, 1-11 means partial. Several importers
historically wrote `12`, so every "full year" query must accept **both** — filtering on `IS NULL`
alone loses the base year and the Previsionale page renders empty; `pdf_importer` normalizes
`>= 12 → None` on write, and `get_fy_partial` excludes `12`. A partial record and a full-year one
**coexist on purpose** for the same company+year: pick with `database/queries.py`
(`get_fy_prefer_full`, `get_fy_partial`), and match on `period_months` before deleting or updating,
or the wrong record goes.

## Key Conventions

- **Codes:** balance sheet `sp01-sp18`, P&L `ce01-ce20`; DB columns carry the full Italian name
  (`sp03_immob_materiali`, `ce01_ricavi_vendite`). Aggregates: `TA` (total assets), `CN` (equity),
  `MOL` (EBITDA), `RO` (EBIT). Calculators return NamedTuples.
- **Money is `Decimal`, never `float`.** Divide with `BaseCalculator.safe_divide()`, round with
  `round_decimal()` (`config.DECIMAL_PLACES`). Percentages are absolute (25.5 = 25,5%), not 0.255.
- **OIC:** assets = equity + liabilities (tolerance €0.01, `config.py:235`) · CCN = current assets −
  current liabilities · MOL = RO + ammortamenti · RO is before financial items.
- **Tax rate: the `24` in the schema is not what runs.** `24` (IRES only) is the Pydantic default
  (`backend/app/schemas/budget.py:148`) and **no screen sends it**: every caller sends **27,9**
  (IRES + IRAP — `STARTUP_TAX_RATE_PCT`, `frontend/app/budget/page.tsx:321`, plus three literals).
  A `ce20_override` overrides the rate altogether.
- **Sectors** (`config.Sector`, 1-6): Industria · Commercio · Servizi · Autotrasporti · Immobiliare ·
  Edilizia. Sector **1** uses the 5-component Altman model, sectors **2-6** the 4-component one; the
  sector also picks the FGPMI thresholds (`data/rating_tables.json`).

## Invarianti e trappole

Le regole che, se ignorate, producono un danno **silenzioso**: il dato risulta sbagliato e
nessun controllo se ne accorge. Il resto della documentazione spiega i meccanismi; qui c'è solo
ciò che non si può non sapere. Ogni voce dice la regola e **cosa si rompe** a violarla.

> Raccolte dall'[inventario dello snellimento](docs/superpowers/2026-08-14-inventario-claude-md.md),
> che per ciascuna porta la prova nel codice. Ogni blocco del file è ormai passato al setaccio,
> sezioni generali comprese (Task 7): le regole trovate lì sono rimaste **nella loro sezione**
> — `period_months`, l'aliquota reale, il plug di cassa dell'infrannuale — perché si leggono
> insieme al resto della sezione, non da sole.

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
- **Il reintegro dal text layer resta lecito solo finché chiude al centesimo.** `close_gaps`
  ripesca dal testo la riga che spiega un divario misurato contro il totale stampato: è massa
  già letta, quindi un fallback. Concedergli una tolleranza — anche piccola, anche «come quella
  del cancello» — lo trasforma in un plug che attribuisce a un conto vero un importo che nessuno
  ha letto, e il foglio quadra lo stesso. → `docs/import/REGOLE-IMPORT-02-ESTRAZIONE.md` §4-bis
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
- **Un effetto non dipende mai da ciò che lui stesso scrive, nemmeno attraverso una `useMemo`.**
  Il campo «Numero di anni da prevedere» aveva `forecastYears` (una `useMemo` su `numYears`) fra le
  dipendenze dell'effetto che si chiudeva con `setNumYears(data.length || 3)`: il valore tornava
  indietro dopo ~230 ms, senza un errore, e il piano a 5 anni non era impostabile da nessuna
  schermata. Le due cose vanno separate — l'idratazione fissa l'orizzonte **una volta**, un secondo
  effetto reagisce all'orizzonte senza toccarlo, e la sua funzione pura restituisce lo stato
  **ricevuto** quando non c'è nulla da aggiungere (`lib/budget-horizon.ts`), così React esce
  dall'aggiornamento e l'effetto non riparte.
- **Accorciare l'orizzonte di un piano non basta a cancellare gli anni in più.** La generazione fa
  l'upsert dei soli anni che hanno un'ipotesi, quindi da 5 anni a 3 restano due anni fantasma coi
  numeri del salvataggio precedente, che /analysis, il rendiconto e il report continuano a mostrare.
  `prune_out_of_plan_forecast_years` li toglie, e va chiamata in **due** punti: dentro
  `generate_forecast` (per `POST /generate`) e nel servizio delle assumptions **dentro la stessa
  transazione del salvataggio**, prima del commit — perché con `auto_generate=false` il motore non
  gira affatto, e se la generazione fallisce la sua transazione viene annullata mentre le ipotesi
  restano salvate; dopo il commit, invece, una `DELETE` fallita darebbe un 500 «errore nel
  salvataggio» su ipotesi già persistite. Un elenco di anni vuoto non cancella nulla: è assenza di
  informazione, non un piano a zero anni.
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
  sullo staging. Per la stessa ragione `MINERU_OCR_ENABLED` è `false` di default **nel compose**
  (`${MINERU_OCR_ENABLED:-false}`); il default dello schema Python è invece `True`, quindi un
  `uvicorn` avviato a mano ha l'OCR **acceso**. Togliere il servizio dal profile trascina vLLM sul
  server. → `docs/import/REGOLE-IMPORT-02-ESTRAZIONE.md` §5-bis

## Critical Implementation Notes

### XBRL Import
Six taxonomies (2011-01-04 → 2018-11-04), values in full euros, not thousands. The parser tells
Ordinario / Abbreviato / Micro apart by row count (`config.TAXONOMY_ROW_COUNTS`);
`importers/xbrl_parser_enhanced.py` adds the hierarchical debt reconciliation.

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
Seven indicators (`V1`-`V7`) on sector-specific thresholds, plus a revenue bonus of **+5 points**
above €500K, mapped onto **13 classes, AAA → BB-** (not B-). All of it is table-driven:
`data/rating_tables.json`.

### Forecasting Engine (Budget)
Base year + up to 5 forecast years (the scenario form takes 1-5, the Startup form offers 3 or 5),
generated by the bulk assumptions endpoint with `auto_generate=true`. Costs are split
variable/fixed — the fixed share defaults to 40% and is editable per assumption row. **Cash is the
plug** (`sp09_disponibilita_liquide`); when the plug goes negative it becomes short-term debt
(`sp16_debiti_breve`). DSO/DIO/DPO that are not set explicitly are derived from the base year on 360
days (from *commercial* receivables and payables, not the aggregates), and working capital scales
with projected revenue and costs, CE overrides included.
Every CE line (32 `ce*_override` columns, from `/forecast/income`) and every BS line (the
`sp_overrides` JSON bag, from `/forecast/balance`) can be forced to an absolute value that beats the
growth percentage. → [docs/budget/API-PREVISIONALE.md](docs/budget/API-PREVISIONALE.md)

### Intra-Year Engine (Infrannuale)
Projects a partial year (say 9 months) to a full 12 months, against a reference full year
(`base_year` = the previous one). Output is a `ForecastYear`, so `/analysis` reads it unchanged.

- **Comparison** (`get_comparison`): line by line, partial vs reference. P&L annualized as
  `partial × 12 / period_months`; BS values are point-in-time and are **not** annualized.
- **Projection** (`generate_projection`): one forecast year, growth percentages applied to the
  reference year (the frontend derives them from the user's overrides). Depreciation is always
  annualized, never grown; taxes are recomputed on projected pre-tax profit.
  → `docs/import/REGOLE-IMPORT-05-INFRANNUALE.md` §3-§4
- **This engine is not the budget engine on two points that change the balance sheet.** Capital and
  reserves are taken from the partial year **as they are** — a prior-year result is never moved into
  reserves, because that needs a shareholders' resolution (`calculations/intra_year_engine.py:1101-1104`; the
  docstring at `:1014` still says otherwise and is wrong). And cash plugs **upward only**: a negative
  residual is clamped to zero and raised as an `unfunded_financing_requirement` diagnostic
  (`:1199-1211`), where the budget engine would have turned it into short-term debt.
- **Working capital** comes from the reference year's turnover ratios. A ratio implying **more than a
  year of stock is DEGENERATE** (`_turnover_ratio` → `None`): the observed partial-year stock is
  carried instead, with a `degenerate_turnover_ratio` diagnostic — `_safe_divide` guards a zero
  denominator, not a negligible one. **The same guard exists on both sides**
  (`frontend/lib/pratica-turnover.ts` mirrors the engine) and they must agree, or the screen and the
  saved record show two different balance sheets. → `docs/import/REGOLE-IMPORT-05-INFRANNUALE.md` §5
- **Promote** (`POST /scenarios/{id}/promote`, `backend/app/services/promote_service.py`): copies the
  projection into a full-year `FinancialYear` that can then be a budget base year. Two semantic gates
  (`check_quadratura(...).semantic_valid`, **not** a euro threshold) and a destructive replacement of
  the existing annual year — see «Invarianti e trappole › Previsionale» and
  [docs/budget/API-PREVISIONALE.md](docs/budget/API-PREVISIONALE.md) §5.

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

- **A new ratio:** method on `FinancialRatiosCalculator` (`calculations/ratios.py`) → its NamedTuple
  → `backend/app/schemas/calculations.py` → `frontend/types/api.ts`. `/analysis` then carries it.
- **A new endpoint:** don't, if it can go into `/analysis`. If it must exist, put the route in
  `backend/app/api/v1/*.py`, the logic in `backend/app/services/`, then `frontend/lib/api.ts` +
  `types/api.ts`.
- **A schema change:** `database/models.py` → a migration script (dev: `drop_all(); init_db()`) →
  the affected calculators → `backend/app/schemas/` → `frontend/types/api.ts`.
- **A new page:** file under `frontend/app/`, `useAppContext()` for the selected company/scenario,
  and the UI rules in «Technical Constraints» below.
- **A new SP/CE line:** four files, six in some cases — see «Layout SP/CE» above. Missing one gives a
  line that appears nowhere, with no error.
- **Working on shared modules** (`database/`, `calculations/`, `importers/`): one edit reaches both
  apps — and `uvicorn --reload` does **not** reload them. Restart, or the fix "doesn't work".

## Technical Constraints

- **SQLite**: single file, no concurrent writes — be careful with transactions.
- **MinerU never on the VPS**: see «Invarianti e trappole › Ambiente».
- **Decimals**: monetary columns are `Numeric(15, 2)` — max 9.999.999.999.999,99. Backend serializes
  through `DecimalJSONResponse` (Decimal → float).
- **Italian locale**: UI in Italian, European number formatting. No emojis — lucide-react icons.
- **CORS**: localhost:3000-3002 (Next.js), 8000, 8501 (Streamlit legacy), the Netlify origin, plus
  whatever `ALLOWED_ORIGINS` adds (comma-separated).
- **Frontend**: shadcn/ui (new-york, slate base) + Tailwind v3 + next-themes + Recharts. Altman and
  FGPMI status colors are explicit green/yellow/red with `dark:` variants.
- **Tailwind `content`**: a class name in a file the `content` globs do not scan is **never
  generated** — no error, just an unstyled element. `lib/`, `hooks/` and `contexts/` are in the globs
  because `lib/pratica-indicators.ts` returns class names; `lib/tailwind-content.test.ts` pins it.
  Grepping the CSS for `.bg-green-500` also matches `.bg-green-500\/10`, so check the exact rule or
  the browser. → `docs/frontend/TAILWIND-E-CLASSI.md`
- **Print/PDF**: checking a print layout means **generating the PDF** — `emulateMedia` gives the
  right measurements but does not paginate, so it never shows a bad page break. A chart needs
  `print:break-inside-avoid` on its Card: `globals.css` protects `.recharts-wrapper`, not the card
  around it. → `docs/frontend/INDICATORI-E-STAMPA.md`

## Frontend pages

`/` (home: aziende & pratiche) · `/pratica` (the whole percorso da bilancio; `/infrannuale`
and `/aziende` redirect here) · `/budget` (scenario assumptions, and the Startup workflow) ·
`/forecast/income` (**editable** P&L: cells → batch save → BS adapts) · `/forecast/balance`
(**editable**: cells write `sp_overrides`, not `*_override` columns) · `/forecast/reclassified`
(read-only) · `/analysis` (Indici) · `/cashflow` (rendiconto) · `/report` (11 sections, mirrors the
PDF) · `/import` (works, but unlinked from the nav — the pratica Import step is the normal way in).

---

## Mappa della documentazione

Ogni riga è la **domanda** a cui quella pagina risponde. Se la tua domanda non è qui, il posto
giusto è il codice, non `/docs`.

| Domanda | Dove |
|---|---|
| Come funziona l'API, con esempi di chiamata? | [README.md](README.md) |
| Che cosa c'è in `/docs`, e che cosa è superato? | [docs/INDEX.md](docs/INDEX.md) |
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

> Ogni blocco che doveva avere una pagina propria ce l'ha, e le sezioni generali sono state
> compresse: lo snellimento
> ([2026-08-14-claude-md-snellito](docs/superpowers/plans/2026-08-14-claude-md-snellito.md)) è
> concluso. Il file resta **sopra** le 500 righe volute dalla spec, e l'inventario spiega dove
> vanno le 568: due terzi sono la sezione invarianti, la mappa e i sette rimandi — cioè il
> prodotto del lavoro, non il residuo da tagliare.

## Agent skills

### Issue tracker

Le issue vivono su GitHub (`XrayFinanceDEV/xbrlbudget`), via `gh` CLI.
See `docs/agents/issue-tracker.md`.

### Triage labels

Le cinque label canoniche, con i nomi di default. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context. See `docs/agents/domain.md`.
