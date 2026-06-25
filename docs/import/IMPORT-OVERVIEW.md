# Importazione bilanci — descrizione completa e dettagliata

> Documento **autosufficiente**: spiega dall'inizio alla fine **come un bilancio viene
> importato e analizzato**, con **tutte le regole di ogni route**, **perché** sono fatte così,
> i parametri configurabili e i file coinvolti. Non è un indice: incorpora il contenuto dei
> documenti di lavoro (`Test/IMPORT-ROUTING-TAXONOMY.md`, `Test/IMPORT-BALANCING-SCHEME.md`,
> `Test/IMPORT-QUADRATURA-ENGINE.md`) e della sezione *PDF Import* di `CLAUDE.md`.
>
> Aggiornato alle modifiche delle sessioni 2026-06-15 / 2026-06-17.

---

## Indice

1. [Il problema e i due principi guida](#1-il-problema-e-i-due-principi-guida)
2. [Sequenza runtime completa](#2-sequenza-runtime-completa)
3. [L0 — Il router per macro-area](#3-l0--il-router-per-macro-area)
4. [Le route in dettaglio (sottocategorie + estrattori)](#4-le-route-in-dettaglio)
5. [LLM vs deterministico — regole e prompt](#5-llm-vs-deterministico)
6. [I livelli di quadratura L1→L5 + CE↔SP](#6-i-livelli-di-quadratura)
7. [Il motore IV-CEE condiviso](#7-il-motore-iv-cee-condiviso)
8. [Pipeline di quadratura per route](#8-pipeline-di-quadratura-per-route)
9. [Hardening anti-masking (catalogo)](#9-hardening-anti-masking)
10. [`period_months` e coesistenza dei record](#10-period_months)
11. [Dopo l'import: analisi e previsionale](#11-dopo-limport)
12. [Parametri configurabili](#12-parametri-configurabili)
13. [Strumenti di test](#13-strumenti-di-test)
14. [Mappa file](#14-mappa-file)

---

## 1. Il problema e i due principi guida

Un PDF è solo testo/immagini. L'import deve trasformarlo in numeri strutturati secondo lo
schema italiano: `sp01–sp18` per lo stato patrimoniale (art. 2424 c.c.) e `ce01–ce20` per il
conto economico (art. 2425 c.c.).

La difficoltà è che **lo stesso bilancio può arrivare in forme molto diverse**: lo schema di
legge "pulito", lo stesso schema esploso nei sottoconti, oppure un elenco grezzo di conti di
contabilità generale (CoGe) con Dare/Avere. Se provi a leggere tutti allo stesso modo, sbagli:
i totali non si agganciano, le colonne vengono lette male e `Attivo = Passivo + PN` salta.

Due principi guidano l'intero sistema:

1. **Routing-first.** Si decide la *tipologia* del file **prima** di estrarre, e lo si apre con
   le regole giuste per quella tipologia. Niente patch per-singolo-file: un nuovo formato ricade
   nella sua macro-area (e, al peggio, nel fallback di quella macro-area) senza rompere gli altri
   rami.
2. **Quadrare ≠ corretto.** Far tornare `Attivo = Passivo` è facile (basta tappare la differenza
   in una voce); ma se l'estrazione ha *perso* dei conti, il bilancio "quadra" con numeri falsi.
   Per questo il sistema riconcilia ai **totali dichiarati** dal documento e, quando tappa, lo
   **segnala** ("BILANCIO NON QUADRATO" / "QUADRATURA MASCHERATA") invece di nasconderlo.

```
PDF ─▶ [L0 ROUTER] ─▶ rotta (A/B · C · OTHER) ─▶ ESTRATTORE della rotta ─▶
       [L1→L5 quadratura della rotta] ─▶ [enforce_ce_sp_identity: CE↔SP] ─▶
       [MOTORE IV-CEE: leveling + check_quadratura + anti-masking] ─▶
       BalanceSheet + IncomeStatement nel DB ─▶ (analisi / previsionale)
```

---

## 2. Sequenza runtime completa
`importers/pdf_importer.import_pdf_balance_sheet`

1. **Estrazione testo** (PyMuPDF) delle prime ~14 pagine come campione per la classificazione.
2. **L0 — Classificazione** (`bilancio_classifier.classify_bilancio`): restituisce
   `Classification(macro_area, subcategory, route, gestionale, confidence, signals, reason)`.
   È il cuore del routing-first: qui si decide *come* leggere il file.
3. **Dispatch per rotta** (vedi §3/§4):
   - `ROUTE_XBRL` → non è nemmeno il ramo PDF: si usa il parser XBRL nativo.
   - `ROUTE_UNSUPPORTED` → **errore onesto** (solo-CE / non-bilancio / troppo aggregato).
   - `ROUTE_IVCEE` (aree A e B) → estrattore **LLM IV-CEE** (`extract_pdf_with_llm`).
   - `ROUTE_TRIAL` (area C) → **LLM CoGe** prima (`extract_trial_balance_with_llm`),
     **deterministico** in fallback (`extract_situazione_contabile`).
4. **Quadratura della rotta** (L1→L5, §6) sull'estrazione scelta.
5. **`enforce_ce_sp_identity`** — forza `utile_CE == sp13` su **ogni** route, PRIMA di
   `validate_balance` (L2-bis, §6).
6. **`validate_balance`** (`pdf_mapper`) — gate `Attivo = Passivo + PN`, e fallisce anche se
   `totale_attivo == 0` o se i sub-totali non ricostruiscono i totali dichiarati.
7. **Normalizzazione `period_months`**: `>= 12 ⇒ None` (anno intero). Vedi §10.
8. **Upsert** del `FinancialYear` + `BalanceSheet` + `IncomeStatement`, con match per tipo
   (parziale vs intero) per non sovrascrivere il record sbagliato quando coesistono.
9. **Motore IV-CEE condiviso** (`iv_cee_hierarchy`): porta le voci ai livelli di legge e lancia
   `check_quadratura` come diagnostica **unica** per tutte le rotte (§7).
10. **Tracciamento upload** (`uploaded_files`): salva i byte grezzi + esito *prima* del parsing,
    così anche un crash del parser resta tracciato per il debug.

---

## 3. L0 — Il router per macro-area
`importers/bilancio_classifier.py`

Il router lavora sul testo, **prima** di estrarre. Le 3 aree A/B/C coprono il **96%** dei casi
reali (su 77 documenti unici analizzati); OTHER è il 4% fuori perimetro.

### Le aree in una riga

- **A — sintetico IV-CEE** (44%): solo **voci di legge** (lettere A/B/C/D, numeri romani, voci
  numerate). Nessun codice di conto. È il bilancio "pulito" depositato.
- **B — dettagliato IV-CEE** (27%): **stesso scheletro di A**, ma ogni macrovoce è **esplosa nei
  sottoconti** di mastro (codici conto presenti). Il *totale di voce* è comunque leggibile.
- **C — sezioni contrapposte / situazione contabile** (24%): **elenco di conti** CoGe
  (mastro/conto/sottoconto) con **Dare/Avere o Saldo**, **senza** schema di legge. È il bilancio
  di verifica, da riclassificare per descrizione.
- **OTHER** (3%): `.xbrl`/`.xml` nativo (va al parser XBRL), oppure documenti che non sono
  prospetti importabili (solo CE, email, riepiloghi troppo aggregati).

### I segnali (`compute_signals`)

Marcatori testuali e densità di codici, resi robusti a header lettera-spaziati e numeri
italiani (esiste sempre una variante "senza spazi"):

| Segnale | A | B | C |
|---|:--:|:--:|:--:|
| Scheletro di legge ("Valore della produzione", "Totale immobilizzazioni", romani) | ✅ | ✅ | ❌ |
| Codici conto CoGe (`XX/YY/ZZZ`, 6–8 cifre, `NNN.NNNNN`, dotted) | ❌ | ✅ | ✅ |
| Path-CEE puntati come prefisso riga (`B.II.1.a`, `C.II.5 bis`) | ❌ | ✅ (spesso) | ❌ |
| "TOTALE A PAREGGIO" / "BILANCIO DI VERIFICA" / "SITUAZIONE CONTABILE" | ❌ | raro | ✅ (forte) |
| "Conforme alla tassonomia itcc-ci-…" / "Generato automaticamente" | ✅ (forte) | ❌ | ❌ |
| Rilevatore di coordinate `is_contrapposte_file` (2 colonne fisiche) | ❌ | ❌ | ✅ |

I codici riconosciuti per la densità CoGe: DEPI `XX/YY/ZZZ`, 8-digit, TeamSystem `XX/YYYY/ZZZZ`,
dotted `10.05.001`, BILAGRA `NNN.NNNNN`, single-column 6-digit.

### Ordine di decisione (dal segnale più forte al fallback)

```
0.  ext ∈ {.xbrl,.xml}                          → OTHER/XBRL  → parser XBRL nativo
1.  testo estratto < soglia (PDF scansionato)    → OCR/LLM vision (o errore se vuoto)
2.  marker forte C:
      "TOTALE A PAREGGIO" | "BILANCIO DI VERIFICA" | "SITUAZIONE CONTABILE"
      | (alta densità codici CoGe AND assenza scheletro di legge)
      | is_contrapposte_file                      → C  → ROUTE_TRIAL
3.  scheletro di legge presente AND codici conto presenti
      (path-CEE puntati | "dettaglio sottoconti" | header AGO XBRL)
                                                  → B  → ROUTE_IVCEE (ancorato ai totali di voce)
4.  scheletro di legge presente AND nessun codice conto
      (bonus: "Conforme alla tassonomia itcc-…", "art. 2435-bis/ter")
                                                  → A  → ROUTE_IVCEE
5.  nessuno scheletro AND nessun set di conti, oppure solo CE
                                                  → OTHER → ROUTE_UNSUPPORTED (errore onesto)
```

### Le due regole d'ordine che evitano gli errori tipici

- **B batte C.** Un bilancio "dettagliato" ha *sia* lo scheletro di legge *sia* i codici conto.
  Se decidessi solo su "ci sono codici conto → situazione contabile", lo manderesti al parser
  trial-balance, che cerca colonne Dare/Avere e **non le trova** (qui ci sono i totali di legge) →
  estrazione vuota o sbagliata. Quindi: **se c'è lo scheletro di legge va a B (IV-CEE)**, a meno
  che ci siano i marker *forti* di C (pareggio / verifica / contrapposte). Esempi: budget_313/314
  (DEPI ma con scheletro) → B, non al parser vuoto.
- **Onestà su OTHER.** Un documento con contenuto economico ma **nessun** marker patrimoniale
  (`ce_present and not sp_present`) è un export del solo conto economico ⇒ `UNSUPPORTED`, **non**
  un finto "bilancio non quadra". Trappola tipica: un "TOTALE A PAREGGIO" che è in realtà il
  pareggio del CE (= totale ricavi).

Il risultato `is_trial_balance = (route == ROUTE_TRIAL)`. Il dict di ritorno porta `macro_area`
+ `macro_subcategory` (loggati e restituiti) così i nuovi formati emergono come **area**, non
come crash.

---

## 4. Le route in dettaglio
Dentro ciascuna macro-area un **sub-router** sceglie per *layout fisico* e *codifica gestionale*.

### Area A — sintetico IV-CEE
Estrattore: **LLM IV-CEE** (`extract_pdf_with_llm`, Haiku 4.5), single-year corrente + dual-year
per il precedente. Sottocategorie:

- **A1 · Facsimile di deposito XBRL→PDF** — marker `Conforme alla tassonomia itcc-ci-2018-11-04`,
  `Generato automaticamente`. Il caso più frequente e affidabile; spesso include la Nota
  Integrativa (da ignorare). Dual-year.
- **A2 · Civilistico abbreviato / micro da gestionale** — `forma abbreviata art. 2435-bis`,
  `Stato patrimoniale micro` (art. 2435-ter). Solo voci di legge; mono-colonna (provvisori) o
  dual-year.
- **A3 · CEE sintetico riclassificato con scostamenti** — layout gestionale (TeamSystem/Sistemi)
  con colonne `anno / anno / Differenza / Scost.%`, solo aggregati di voce.
- **A4 · Bilancio ottico Cerved** — pagine di indicatori Cerved + prospetto IV-CEE micro
  incorporato.
- **A5 · Riepiloghi ultra-aggregati / output AI** *(borderline OTHER)* — "schema IV Direttiva
  CEE", solo macro-totali, spesso non quadrano: bassa confidenza, da validare con cura.

### Area B — dettagliato IV-CEE
Stesso estrattore LLM IV-CEE, **ancorato ai totali di voce dichiarati**: i sottoconti di
dettaglio sono **ignorati** (sommarli in un'aggregazione piatta li conterebbe due volte).
Sottocategorie:

- **B1 · "Situazione contabile riclassificata dettagliata" con codici-PATH CEE** — i sottoconti
  portano il **codice CEE come prefisso** (`B.II.1.a)`): aggregabili per prefisso fermandosi al
  livello di legge. Famiglia coerente (147/152/176/182/209/282/283/319/320…).
- **B2 · "con dettaglio sottoconti / conti"** — la voce di legge mostra il **totale**, seguito
  dai sottoconti CoGe a 6-7 cifre: si legge il **totale di voce**, si ignorano i sottoconti
  (305/324/340/313/314 + export **Genya**).
- **B3 · Bilancio XBRL esteso AGO Infinity (Zucchetti)** — `BILANCIO SCHEMA XBRL`, header
  `AGO - 10.x`, codici `6-digit+3`, con `Totale …` di legge espliciti (207/297/331).
- **B4 · Abbreviato con dettaglio conti per descrizione / flag A·P·R·C** — senza codici CEE
  puntati: mapping più euristico (171/289). È l'area con più casi `maybe`.

### Area C — verifica a sezioni contrapposte
Primario: **LLM CoGe** (`extract_trial_balance_with_llm`). Fallback: parser **deterministico**
`extract_situazione_contabile`. Due assi indipendenti: **layout fisico** × **codifica gestionale**.

*Per layout:*
- **C1 · Sezioni contrapposte fisiche** — due colonne affiancate Attività│Passività e
  Costi│Ricavi (Dare/Avere). Richiede **split per coordinate x** (188 FastReport `.frx`, 249
  SAMAC, 338 Pandoro, 281 DEPI, 330 8-digit, 210/213/215 BILAGRA).
- **C2 · Colonna unica "Saldo"** — SP poi CE in sequenza, un solo importo per conto (229/238/243
  MBS·CARP 6-digit, 169 e BILANCIO-TEST DEPI a saldo).

*Per codifica gestionale:* DEPI `XX/YY/ZZZ` (Sistemi) · TeamSystem `XX/YYYY/ZZZZ` · 8-digit ·
dotted `10.05.001` · BILAGRA `NNN.NNNNN` · single-column 6-digit.

*Casi speciali C:*
- **C4 · Solo Conto Economico (manca lo SP)** — `PROSPETTO ECONOMICO per competenza` (196/335).
  **Non ricostruibile** → errore onesto, non plug.
- **C5 · Ditta individuale / professionista** — DEPI a saldi senza PN societario (131/132
  Oprandi): attenzione alla mappatura del PN.

#### I sub-parser deterministici (`situazione_contabile_parser.py`)
`is_situazione_contabile(text)` + il coordinate-based `is_contrapposte_file(path)` instradano a:
- **DEPI** `XX/YY/ZZZ` (incl. detail-only flat) e 2-part `XX/YYYY` + `XX/****`
- **AGO/ERP** 8-digit (`parse_entries_ago`)
- **Single-column** 6-digit "Saldo" (`parse_entries_single_column`)
- **TeamSystem** `XX/YYYY/YYYY` (`parse_entries_teamsystem`)
- **Contrapposte 8-digit** fisiche 2-colonne (`parse_entries_contrapposte_8digit`, split per
  coordinate)
- **Generic contrapposte best-effort** (`extract_contrapposte_best_effort`) per dump 2-colonne
  eterogenei: divide le colonne all'x del cluster-codici a destra e riconcilia mastri/subtotali a
  IV-CEE **per descrizione** (`_be_reclassify` scende la gerarchia di codice e si ferma al livello
  più grezzo che mappa a una voce IV-CEE — nessuna chart-of-accounts per-gestionale). Fondi
  ammortamento nettati dagli assets; risultato d'esercizio dal gap di pareggio; residuo plug in
  sp09/sp16 con flag `BILANCIO NON QUADRATO`. Sotto-meccanismi:
  - **Gross/net anchoring** (`netted_contra`): fondi listati come account PASSIVO (presentazione
    lorda) → la massa nettata viene accumulata e sottratta da `iv_total` così il NET IV-CEE
    combacia (plug ~ 0). Era la causa dominante di "QUADRATURA MASCHERATA" sui lordi.
  - **Code-collision aggregation**: due account il cui codice normalizza alla stessa stringa
    vengono **sommati**, non sovrascritti (l'overwrite droppava silenziosamente un importo).
  - **Code-less second pass** (`_be_split_codeless`): trial balance puliti `descrizione importo`
    senza codice (es. budget_367) — ritentati code-less solo quando il pass normale trova zero
    righe (zero regressione sui file con codice).
- **Empty→best-effort safety net**: un sub-parser strutturato/DEPI che esce VUOTO
  (`totale_attivo == 0`) su un file fisicamente contrapposte → era misroutato; viene ritentato via
  best-effort e tenuto solo se non-vuoto (puramente additivo).
- **Dotted-hierarchical rescue** (`is_dotted_hierarchical` + `_hier_reconstruct`): la famiglia
  Sistemi/DEPI "BILANCIO 4 SEZIONI" (`03.01.07` o `3/15/102`) lista ogni voce IV-CEE come mastro
  LIVELLO-1 col suo subtotale, poi figli dotted. La rescue àncora sui mastri di livello-1 in
  **ordine documento**, netta i fondi a qualsiasi profondità, e fa emergere il risultato come gap.
  Gira **solo** se il best-effort è mascherato (plug > 1%) E il file è dotted-hierarchical, e
  l'output è tenuto **solo** se si auto-valida (gross attivo riconcilia al TOTALE ATTIVO ±0,5% E
  gap SP = risultato CE ±0,5%); altrimenti torna `None` e il best-effort mascherato resta (non può
  regredire un file già bilanciato).

### OTHER
- File **XBRL nativo** (`.xbrl`/`.xml`) → parser XBRL (`xbrl_parser_enhanced.import_to_database`),
  non il ramo PDF.
- Documenti **non-bilancio** (email, verbali) o **riepiloghi troppo aggregati** → errore esplicito.

> La mappatura completa per-file (77 documenti unici, colonne layout/codifica/parsing-det/
> confidence) è prodotta automaticamente dagli script di §13 e archiviata in
> `Test/IMPORT-ROUTING-TAXONOMY.md`.

---

## 5. LLM vs deterministico

| Rotta | Primario | Fallback | Perché così |
|---|---|---|---|
| **A / B** (IV-CEE) | **LLM** `extract_pdf_with_llm` (Haiku 4.5) | — | lo schema di legge va *interpretato* (sinonimi di voce, layout vari): l'LLM legge le voci e ne àncora i **totali** |
| **C** (trial balance) | **LLM CoGe** `extract_trial_balance_with_llm` (se c'è la chiave API) | **deterministico** `extract_situazione_contabile` | un elenco CoGe richiede regole specifiche (sotto): l'LLM CoGe le conosce; il deterministico quadra via pareggio senza costo |
| C → ultima spiaggia | — | LLM IV-CEE `force_llm=True`, **solo** se il deterministico esce **vuoto** | l'LLM IV-CEE è l'estrattore *sbagliato* per una contrapposte, quindi è l'ultima risorsa |
| **OTHER** | parser **XBRL** nativo | — | il dato è già strutturato, niente LLM |

### Perché A/B usano l'LLM
Lo schema di legge è leggibile ma non rigido: le descrizioni delle voci variano di deposito in
deposito, il layout può essere a una o due colonne, con o senza sottoconti. L'LLM mappa le
descrizioni alle voci `sp/ce` e — punto chiave per B — si **àncora ai totali di voce
dichiarati**, ignorando i sottoconti di dettaglio.

### Perché C ha bisogno di un LLM "CoGe" dedicato
Una situazione contabile è un **elenco piatto** di conti con saldi Dare/Avere e **nessuno**
schema di legge a cui agganciarsi. `extract_trial_balance_with_llm` invia l'**intero** testo
(`_extract_full_text`, niente finestratura SP/CE: i trial balance non hanno header IV-CEE su cui
ancorare) e fa due pass Haiku con prompt CoGe-specifici:
- **`TRIAL_BALANCE_SP_SYSTEM_PROMPT`** — insegna: la convenzione dei segni (Dare = attività/costo,
  Avere = passività/PN/ricavo); il **netting** delle contropartite (fondo ammortamento / fondo
  svalutazione crediti sottratti dall'attivo lordo, **mai** bookati a passivo); il mapping
  descrizione→sp01–18; che il **risultato è implicito** (nessun conto utile → è il gap
  Attivo−Passivo).
- **`TRIAL_BALANCE_CE_SYSTEM_PROMPT`** — classifica gli economici in ce01–20, tutti i costi
  positivi.

Output sugli stessi schemi `BalanceSheetExtraction`/`IncomeStatementExtraction`, poi
post-processing: `_normalize_ce_signs`, `_validate_crediti`/`_validate_debiti`
(breakdown→aggregato), `_validate_ce10_against_bs`/`_validate_ce_imposte`, e infine
**`_balance_trial_via_result`** che impone il pareggio derivando `sp13 = totale_attivo −
(passivo + PN escluso risultato)` e ricalcola i totali. Trial balance scansionati →
`_extract_with_llm_vision` con gli stessi prompt CoGe. Single-year (i trial balance sono
raramente comparativi): `prior_bs_data`/`prior_ce_data` restano `None`.

In `pdf_importer` la scelta C è **LLM-first con confronto**: si estrae con l'LLM CoGe E con il
deterministico, e si tiene il candidato con **scarto di quadratura minore** (`_plug_residual`).

### Completezza dell'estrazione CoGe (non-determinismo)
L'LLM, su liste lunghe, **droppa conti in modo non deterministico** (provato: file
byte-identici 343/348, uno completo, uno corto). Mitigazioni:
1. Il **totale dichiarato** è iniettato nel prompt SP come ancora di completezza.
2. Il pass SP è **ritentato** fino a `_COGE_SP_MAX_ATTEMPTS = 3`, tenendo la pescata col
   `_plug_residual` minore; stop anticipato quando il residuo è < 2% del totale.
3. Prompt SP: regole esplicite di *completezza* e *mastro+figli*.

### Nota costo
L'unico passo che usa l'API Anthropic (`ANTHROPIC_API_KEY` in `backend/.env`, **non**
l'abbonamento) è l'**estrazione LLM**, **una volta per file**. Tutto ciò che viene dopo (ratios,
rating, previsionale) è **puro calcolo locale**: gratuito e ripetibile.

---

## 6. I livelli di quadratura
Schema unico per ogni bilancio, applicato risalendo i livelli. Il livello-chiave è **L2**.

| Livello | Cosa fa | Ragionamento |
|---|---|---|
| **L0 — Rotta** | macro-area (§3), decisa prima di estrarre | leggere il file con le regole giuste fin dall'inizio |
| **L1 — Pareggio** | `Attivo = Passivo + PN`; il risultato `sp13` è il *gap* quando non è stampato (`_balance_trial_via_result`) | identità contabile di base |
| **L2 — Riconciliazione ai totali DICHIARATI** ★ | confronta i sub-totali estratti con i **totali di controllo** stampati (`TOTALE A PAREGGIO`, `TOTALE ATTIVITA'`, `UTILE D'ESERCIZIO`) | è qui che si distingue "quadra" da "corretto" |
| **L2-bis — Quadratura CE↔SP** ★ | `enforce_ce_sp_identity` forza `utile_CE == sp13` su OGNI route | il risultato è un solo numero, in SP (sp13) e in CE (ultima riga) |
| **L3 — Segno e lato** | la **colonna** è verità sul lato (Dare/Avere); costi positivi, ricavi in Avere | non spostare un conto per il nome |
| **L4 — Lordo→netto** | fondi amm.to / sval. nettati dall'attivo lordo, anche se stampati in colonna passivo | non gonfiare entrambi i lati con le poste rettificative |
| **L5 — Aggregazione ai conti di legge** | sottoconti CoGe → voce di legge; layout mastro+figli puntati: prendi il **subtotale del mastro UNA volta**, ignora i figli | doppio conteggio se sommi entrambi; perdi "altri" se sommi solo i figli |

### L2 — il dettaglio (anti-masking)
Ogni verifica stampa i propri **totali di controllo**. Sono la verità.
- `_declared_control_totals(file_path)` li legge (robusto a header lettera-spaziati e numeri
  italiani).
- `_reconcile_trial_to_declared()`: confronta `sp13` derivato col **risultato dichiarato**. Se
  differiscono oltre tolleranza (max €50 / 0,5%): la massa mancante è stata persa su un lato →
  la **riporta** sul lato corto (sp16 se passivo corto, sp09 se attivo corto), **rimette sp13 =
  risultato dichiarato**, e la espone come `bs['_plug_residual']`.
- `check_quadratura` legge `_plug_residual` e alza `masked=True` (> 1% del totale) → warning
  "QUADRATURA MASCHERATA … correggere in Rettifiche".

> **La trappola del pareggio forzato (perché serve L2).** Se l'estrattore perde €500k di conti su
> un lato, forzando `sp13` ad assorbire la differenza `Attivo = Passivo` **torna lo stesso** — ma
> `sp13` (l'utile) è ora **falso**. Il bilancio "quadra" ed è sbagliato. L2 legge i totali
> dichiarati e confronta. "Quadra" ≠ "corretto".

### L2-bis — CE↔SP (valida su OGNI route)
SP e CE sono estratti separatamente e l'utile può divergere → la "Verifica CE↔SP" dell'app
fallirebbe. `enforce_ce_sp_identity` (eseguito in `pdf_importer` DOPO il blocco di ogni route e
PRIMA di `validate_balance`) forza `utile_CE == sp13` con direzione **decisa per route + arbitro**:
- **Default**: ci si fida di **sp13** (ancorato al pareggio; su route C è già = risultato
  dichiarato) e si allinea il CE (plug in `ce12_oneri_diversi` se troppo alto / `ce04_altri_ricavi`
  se troppo basso) + flag `_ce_sp_plug`.
- **Arbitro = Utile/Perdita DICHIARATO** (`declared`): vince tra `sp13` e `utile_CE` quello più
  vicino al dichiarato.
  - dichiarato conferma il **CE** → lo `sp13` aveva l'utile dell'esercizio **PRECEDENTE**: lo si
    porta a `utile_CE` e la differenza va nelle **riserve** (`sp12`) — PN totale e Attivo=Passivo
    invariati (solo ri-etichettatura nel PN). Cap 10% del passivo + riserve non negative,
    altrimenti ripiega sull'allineamento del CE.
  - dichiarato conferma lo **sp13** → il CE è errato (bug segno/parsing, es. budget_402/413) → si
    allinea il CE, **sp13 NON viene toccato**.

No-op quando già coincidono. Garantisce CE↔SP senza corrompere uno `sp13` corretto.

---

## 7. Il motore IV-CEE condiviso
`importers/iv_cee_hierarchy.py`

Le 4 macro-aree restano **separate** (ognuna col suo estrattore), ma confluiscono in un unico
stadio a valle. **Non è un router**: è il punto dove ogni rotta, dopo aver estratto *a modo suo*,
passa per la **stessa** classificazione di legge e lo **stesso** controllo di quadratura. Una sola
tassonomia, una sola quadratura, quattro estrattori distinti.

### `data/iv_cee_tree.json` — albero canonico di legge (art. 2424/2425)
Ogni nodo:

| campo | significato |
|---|---|
| `path` | percorso di legge (`B.II`, `C.II.1`, `PD.7`, `A.1`…) |
| `level` | 1 = lettere A/B/C/D · 2 = romani · 3 = arabi · 4 = a/b/c (+bis/ter) |
| `side` | `attivo`/`passivo` (solo SP; disambigua A/B/C/D che sui due lati significano cose diverse) |
| `db_field` | foglia legale → campo DB (`sp01`–`sp18`, `ce01`–`ce20`) |
| `is_legal_leaf` | la voce mappa a un campo DB (qui si quadra) |
| `is_total` | nodo-totale di sezione (per riconciliazione, NON sommato) |
| `netting` | fondi amm.to/sval. → si nettano dall'attivo lordo |
| `aliases` | sinonimi normalizzati per il match descrizione |

Copre **tutti** i 18 SP + 20 CE. È **volutamente solo livello di legge** (niente alias di
sotto-conti, che in aggregazione *flat* A/B causerebbero doppio conteggio — i sotto-conti li
gestisce la discesa gerarchica del ramo C).

### Funzioni
- `normalize(text)` — lowercase, accenti rimossi, punteggiatura→spazio.
- `resolve(desc, side, statement)` — classificatore condiviso descrizione→nodo. Prudente: torna
  `None` se incerto (la discesa scende nei figli invece di misroutare). Match: alias esatto →
  alias più lungo contenuto. **Non** va usato per ribaltare il *lato* attivo/passivo di una riga
  trial-balance: lì la **colonna è ground truth** (vedi L3 e il learning revertito in §9).
- `classify_for_reclassify(desc)` — adattatore `(db_field, specific)` per `_be_reclassify`.
- `aggregate_flat(items)` — aggrega voci già a livello di legge (A/B/XBRL): somma le foglie, salta
  i nodi-totale, applica scadenza entro/oltre a crediti/debiti.
- `check_quadratura(bs, ce)` — vedi sotto.

### `check_quadratura(bs, ce)` — il giudice unico
Verifica:
1. **Attivo == Passivo** (±0,01) sui 18 aggregati SP.
2. **Utile CE == sp13** — cross-check che `validate_balance` NON faceva.
3. **Anti-masking**: legge `bs['_plug_residual']`; se il plug supera `_MASK_PCT = 1%` del totale →
   `masked=True` (quadra solo per costruzione, composizione inaffidabile). `is_empty=True` se
   `totale_attivo ~ 0` (un'estrazione vuota è un **fallimento**, non un "quadra a zero").

`quadra` richiede `not is_empty and not masked`. Ritorna `Quadratura(totale_attivo,
totale_passivo, sbilancio, quadra, utile_ce, sp13, utile_match, plug_residual, masked, warnings)`.
È la diagnostica unificata per **tutte** le rotte in `pdf_importer` e il segnale pass/fail
dell'harness.

---

## 8. Pipeline di quadratura per route
Entrambe le quadrature — **Attivo=Passivo** E **CE↔SP** — su OGNI route, prima di `validate_balance`.

**Route C (verifica / situazione contabile)**
1. Estrai con CoGe-LLM **e** parser deterministico → tieni il candidato col `_plug_residual` minore.
2. `_reconcile_trial_to_declared` sul candidato → **sp13 = utile dichiarato**, residuo sul lato
   corto (L1+L2).
3. `enforce_ce_sp_identity(prefer="sp13", declared=…)` → CE↔SP (sp13 autorevole, allinea il CE)
   (L2-bis).
4. `validate_balance` (gate Attivo=Passivo).

**Route A/B (IV-CEE)**
1. `_llm_extract` (single-year corrente + dual-year per il precedente).
2. `reconcile_ivcee_balance` → se quasi quadrata, tampona il piccolo lato corto sul `TOTALE ATTIVO`
   dichiarato (L1) — risolve budget_352 sul percorso dual-year.
3. `enforce_ce_sp_identity(prefer="sp13", declared=…)` → CE↔SP con arbitro (L2-bis).
4. `validate_balance`.

**OTHER / XBRL nativo** (`.xbrl`/`.xml`): `xbrl_parser_enhanced.import_to_database`. I valori sono
tassati (esatti) → Attivo=Passivo già quadrato; ma anche qui `enforce_ce_sp_identity(prefer="sp13")`
dopo il mapping, perché lo `utile_CE` ricostruito dai tag può divergere dallo `sp13` taggato
(budget_361/404) → CE↔SP anche su XBRL. CE-only / non-bilancio → errore onesto.

---

## 9. Hardening anti-masking
Catalogo dei fix generali (di categoria, non per-file) che impediscono al sistema di "quadrare con
numeri falsi".

- `pdf_mapper.validate_balance` fallisce se `totale_attivo == 0` o se i sub-totali (sp01–10 /
  sp11–18 incl. sp13) non ricostruiscono i totali dichiarati — niente falsi positivi su estrazioni
  vuote/plugged.
- I correttori LLM in `pdf_extractor_llm.py` non applicano plug negativi o sovradimensionati in
  silenzio: cappano la correzione, mai sotto zero, ed emettono `BILANCIO NON QUADRATO`.
- Dual-year: si scarta un anno precedente fabbricato quando il PDF ha una sola colonna importi.
- `ce03_lavori_interni` incluso nel Valore della Produzione (entrambi gli anni); le imposte
  estratte non vengono sovrascritte per forzare il cross-check di utile.
- **Malformed Haiku column tolerance** (`_coerce_year_blob`): se Haiku serializza un'intera colonna
  come *stringa* JSON-ish con numeri italiani (`1.234.567,89`), un `field_validator(mode="before")`
  fa `json.loads` (ritentando dopo normalizzazione) → una colonna malformata non fa fallire l'import.
- **Broad SP-window end anchors** (`SP_END_KEYWORDS`): la finestra SP chiude su qualsiasi variante
  "Totale … passivo/passività" ("Totale STATO PATRIMONIALE passivo", "…e patrimonio netto"), non
  solo il letterale "totale passivo" (es. 352).
- **Zeroed-leading-section guard** (`find_section_pages`): i provvisori che rendono lo schema IV-CEE
  con tutti gli importi a `0,00` in testa e i valori reali dopo — la finestra SP/CE scivola a una
  **vera seconda copia con header**; i blocchi di soli numeri (es. 355) falliscono onestamente.
- `_be_split` sceglie il gutter che **bilancia le righe con descrizione** su entrambi i lati
  (centro come spareggio), non il gap più largo (che tagliava la colonna passivo → masking
  343/348/405).
- **Gate `SC_PLUG_REJECT_PCT = 0.20`** in `pdf_importer`: best-effort con plug > 20% del totale →
  rifiutato (fallback LLM/onesto); sotto → import con flag `BILANCIO NON QUADRATO` per Rettifiche.

**Learning REVERTITO (non ritentare).** Far sovrascrivere il *lato* attivo/passivo dalla descrizione
dell'albero (`resolve`) per togliere il default "sconosciuto → sp16" è **sbagliato**: la COLONNA è
la verità sul lato; conti ambigui (`ERARIO C/`, `DEPOSITI BANCARI`=scoperto c/c, `FORNITORI
C/ANTICIPI`, `INAIL C/`, `FONDI AMM.TO`) cambiano lato per colonna, non per descrizione → ha
regredito un file pulito (375 SI→MASK). La vera causa del default-sp16 dannoso era un bug di
`_be_split` (colonna già sbagliata).

---

## 10. `period_months`
**Convenzione**: `FinancialYear.period_months` = `NULL` **o** `12` ⇒ anno intero; `1–11` ⇒
parziale (infrannuale).

**Il bug che ha motivato la modifica.** Diversi import salvavano `12` (invece di `NULL`) per i
bilanci annuali. Le query "anno storico" filtravano solo `period_months IS NULL`, escludendo quei
record → la pagina **Previsionale risultava vuota** (nessun anno base trovato).

**La correzione, su due fronti:**
- **Scrittura**: `pdf_importer` normalizza `period_months >= 12 → None`.
- **Lettura**: tutte le query "anno intero" accettano `NULL **o** 12` (`analysis_service`,
  `calculation_service`, `budget_scenarios`, `promote_service`, `queries.get_fy_prefer_full`);
  `get_fy_partial` esclude il 12.

**Coesistenza dei record**: un company+year può avere sia un record parziale (`period_months` 1–11)
sia un record full-year promosso (`NULL`). Tutte le query usano gli helper di `database/queries.py`
(`get_fy_prefer_full`, `get_fy_partial`); gli importer fanno il match per `period_months` quando
cancellano/aggiornano per non sovrascrivere il record sbagliato.

---

## 11. Dopo l'import
Importato il bilancio base, l'analisi (ratios, Altman, FGPMI) e il previsionale sono **calcolo
locale**, nessun LLM. `calculations/forecast_engine.py` proietta l'anno base applicando le
assunzioni: variabili **economiche** (crescita % ricavi/costi) e **patrimoniali** (investimenti,
dismissioni cespiti, nuovi finanziamenti, rimborsi).

### Guardia ricavi negativi
Il motore moltiplica: `ricavo_previsto = ricavo_base × (1 + crescita%)`. Se il ricavo base è
**negativo** (es. −5,2M, impossibile per A.1 "ricavi delle vendite"), "+15%" lo rende **−6M**: più
negativo. Lo scenario "ottimo" produrrebbe il risultato peggiore → la direzione si **inverte**.
Per questo, se l'anno base ha `ce01_ricavi_vendite < 0`, il motore **si rifiuta** di generare con
un errore chiaro che rimanda a Rettifiche, invece di sfornare numeri spazzatura. È la filosofia
"errore onesto" dell'import, applicata al previsionale.

### Il caso reale: non-determinismo dell'estrazione
Lo **stesso PDF** (`budget_405…PROGETTO DI BILANCIO`) importato due volte a 8 minuti di distanza:

| Import | `ce01` (ricavi) | Esito |
|---|--:|---|
| copia A | **−5.221.145** | estrazione rotta |
| copia B | **+5.208.856** | estrazione corretta |

Stesso file, stesso parser, output diverso (l'utile 91.267 e lo SP erano identici e corretti in
entrambi: a sbagliare era il *segno dei ricavi* nel CE). Conclusione: **l'estrazione LLM non è
deterministica**. La guardia del previsionale è la difesa **a valle**; la difesa **alla radice** da
valutare è un validatore all'import che rifiuti subito un'estrazione con `ce01 < 0` (forzando un
nuovo tentativo, che di norma riesce).

---

## 12. Parametri configurabili

| Parametro | File | Default | Effetto |
|---|---|---|---|
| `SC_PLUG_REJECT_PCT` | `importers/pdf_importer.py` | `0.20` | sopra → rifiuta best-effort (LLM/onesto); sotto → import con flag Rettifiche |
| `_MASK_PCT` | `importers/iv_cee_hierarchy.py` | `0.01` | soglia diagnostica `masked` in `check_quadratura` |
| `_COGE_SP_MAX_ATTEMPTS` | `importers/pdf_extractor_llm.py` | `3` | ritentativi del pass SP CoGe (tiene il `_plug_residual` minore) |
| `ANTHROPIC_API_KEY` | `backend/.env` | — | senza chiave: route C usa il deterministico; A/B falliscono se richiedono LLM |

---

## 13. Strumenti di test

| Strumento | Cosa misura | Costo |
|---|---|---|
| `Test/_quadratura_harness.py` | tasso di quadratura dell'**estrazione** sul corpus (`area\|route\|mode\|quadra\|plug\|note`) | deterministico gratis (`--llm` per A/B) |
| `Test/_full_diagnostic.py` | per-file: rotta, `validate_balance`, quadra/masked/vuoto, plug (`Test/june_sample --llm`) | LLM se `--llm` |
| `Test/_budget_scenarios_loop.py` | il **previsionale** su 1 PDF: 5 profili PESSIMO→OTTIMO, variabili economiche **e** patrimoniali | import 1 volta (LLM), poi gratis |
| `Test/_budget_loop_db.py` | stessa verifica su **tutti i bilanci già nel DB** | **zero** (nessun import) |
| `Test/_budget_loop_batch.py` | batch sui PDF di una cartella (DB isolato per fan-out) | import LLM = costo API |
| `Test/_ce_sp_ivcee2.py` / `Test/_repro_real2.py` | CE↔SP per route (IV-CEE / C end-to-end) | LLM |

Riproducibilità della tassonomia: `Test/_classify_dump.py` (dedup per hash, segnali, verdetti
parser → `Test/_analysis/index.json`), `Test/_analysis/consolidate.py`, `Test/_analysis/gen_doc.py`.

Il loop del previsionale verifica, per ogni anno e scenario: che ogni variazione si rifletta col
valore atteso, che il Valore della Produzione includa tutte le componenti, che lo SP quadri, che
`sp13 = utile CE`, che le imposte siano coerenti, e — tra scenari — che utile/ricavi crescano da
PESSIMO a OTTIMO. Classifica `INVALID_BASE` i bilanci con dato base non valido (es. ricavi
negativi), distinguendoli da un fallimento del motore.

---

## 14. Mappa file

| File | Ruolo |
|---|---|
| `importers/bilancio_classifier.py` | **L0 router** — `classify_bilancio`, `compute_signals`, costanti `ROUTE_*` |
| `importers/pdf_importer.py` | orchestrazione import + dispatch per rotta + quadrature per route + `period_months` |
| `importers/pdf_extractor_llm.py` | LLM IV-CEE (`extract_pdf_with_llm`) e LLM CoGe (`extract_trial_balance_with_llm`) + prompt CoGe |
| `importers/situazione_contabile_parser.py` | parser deterministico area C (fallback) + `is_contrapposte_file` + best-effort |
| `importers/iv_cee_hierarchy.py` | motore condiviso: albero, `resolve`, `aggregate_flat`, `check_quadratura` |
| `importers/pdf_mapper.py` | mapping voci → `sp/ce`, `validate_balance` |
| `importers/xbrl_parser_enhanced.py` | parser XBRL nativo (rotta OTHER) |
| `calculations/forecast_engine.py` | previsionale + guardia ricavi negativi |
| `data/iv_cee_tree.json` | tassonomia IV-CEE canonica |
| `database/queries.py` | `get_fy_prefer_full` / `get_fy_partial` (coesistenza record annuale/parziale) |

> **Documenti di lavoro** (storia, changelog di sessione, censimento per-file): `Test/IMPORT-ROUTING-TAXONOMY.md`
> (77 doc, mappatura completa), `Test/IMPORT-BALANCING-SCHEME.md`, `Test/IMPORT-QUADRATURA-ENGINE.md`.
