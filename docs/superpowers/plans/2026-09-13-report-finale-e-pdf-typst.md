# Report finale e PDF Typst — piano di implementazione

> **Per gli agenti:** ogni dispatch deve contenere un task autosufficiente con
> Target, Change, Constraints, Ownership e Observable acceptance. Gli agenti non
> devono assumere di aver letto questo piano per intero.

**Data:** 2026-09-13

**Stato:** M1 integrato; spike M2 prodotto in worktree dedicati; requisiti del
dossier consolidati il 2026-09-15. Gate tecnico/riproduzione indipendente da chiudere.

**Goal:** completare prima il report finale web dell'intera pratica e il suo
contratto dati canonico, poi generare dallo stesso snapshot un PDF server-side
con Typst, senza Playwright o Chromium.

**Spec:**

- `docs/superpowers/specs/2026-09-13-report-finale-pratica-design.md`
- `docs/superpowers/specs/2026-09-13-report-pdf-typst-design.md`
- `docs/superpowers/specs/2026-09-15-report-budget-dossier-design.md`

**Base verificata durante la pianificazione:** `main` a `e09449b`.

## 1. Esito atteso

Il lavoro produce due milestone separatamente collaudabili:

- **M1 — Report finale:** un endpoint restituisce un `FinalReportModel v1`
  completo e `/report` lo rappresenta per i percorsi infrannuale, bilancio e
  startup;
- **M2 — PDF Typst:** il backend congela quel modello e genera un PDF bozza o
  finale, riproducibile e validato, senza eseguire calcoli nel template.

M2 estende il contratto M1 al v2 per produrre il dossier concordato. Il titolo
è neutrale (`Report Budget 2027 - 2029` nell’esempio); gli Allegati sono completi
e ogni pagina ha un commento. La precedente sospensione estetica è superata
dalla richiesta di consolidare le specifiche. Restano i gate tecnici e i nuovi
prerequisiti di contratto/layout descritti sotto.

## 2. Decisioni fissate dal piano

Queste decisioni evitano che gli agenti risolvano lo stesso problema in modi
incompatibili:

1. `FinalReportModel` è assemblato dal backend e consumato senza calcoli sia da
   React sia da Typst.
2. Il percorso è registrato con i valori esistenti `infrannuale`, `bilancio` e
   `startup`.
3. `source_scenario_id` collega il budget alla sorgente solo quando una vera
   proiezione infrannuale, con `period_months` tra 1 e 11, ha prodotto la chiusura.
   Il percorso bilancio a 12 mesi non finge una promozione. Il `FinancialYear`
   prodotto dalla promozione registra a sua volta `promoted_from_scenario_id`,
   così una successiva promozione non può rendere falsa la provenienza del dato.
   Entrambi i campi dello scenario sono derivati e scritti dal backend: il client
   non può scegliere liberamente una sorgente o un workflow.
4. Gli alert extra-contabili vengono persistiti sullo scenario sorgente come
   JSON validato, con timestamp. Il report non legge stato locale React.
5. Ogni riga `BudgetAssumptions` registra i campi forniti esplicitamente
   dall'utente. Per i dati precedenti alla migrazione la provenienza è
   `legacy_unknown` e produce un warning: non viene dedotta confrontando il valore
   con il default.
6. I sei blocchi narrativi del report vengono persistiti in un nuovo contenitore
   versionato; le colonne legacy restano leggibili durante la migrazione e non
   vengono eliminate in M1.
7. Il `GET final-report` non genera commenti e non modifica il database.
8. Il PDF finale richiede `readiness == ready`; il PDF bozza è consentito con
   watermark e diagnostica.
9. M2 conserva inizialmente i metadati dell'artefatto e gli hash, non il file PDF
   né l'intero JSON. Un archivio documentale resta un milestone successivo.
10. L'endpoint PDF è sincrono finché le misure dello spike non dimostrano la
   necessità di una coda.
11. Il vecchio `pdf_service/` ReportLab non viene esteso né usato come fonte dati
    per il nuovo report. La sua eventuale rimozione richiede un inventario dei
    caller e un task separato.

## 3. Strategia degli agenti

### 3.1 Modelli e ruoli

| Ruolo | Uso principale |
|---|---|
| Pi con Qwen 3.8 | coding delimitato, funzioni pure, componenti, template, fixture e prima review |
| GPT-5.6 Terra high | contratti, migrazioni, integrazione, sicurezza, review dei punti ad alto rischio |
| Coordinatore | crea i task, controlla confini, integra esiti e decide i gate; non corregge silenziosamente i rilievi di review |

Prima di ogni dispatch Pi, il modello mostrato/configurato nella sessione Pi deve
essere Qwen 3.8. La review di pianificazione ha verificato
`qwen3.8-flash-next`; questo è il default operativo finché il proprietario non
sceglie un'altra variante 3.8. Se Orca riusa un terminale e non espone il modello
nel receipt, la verifica viene fatta nell'interfaccia/configurazione Pi e
registrata nel rapporto del task. Per Terra si verifica che `launch.effective` riporti
`gpt-5.6-terra` con effort `high`.

### 3.2 Limite di concorrenza

- massimo **due agenti Pi attivi contemporaneamente**;
- Terra può lavorare in parallelo ai due Pi solo su file non sovrapposti;
- due agenti non modificano mai lo stesso file nella stessa ondata;
- le review sono ondate distinte dal coding: due implementazioni Pi possono
  correre insieme, poi Pi-A revisiona Pi-B e Pi-B revisiona Pi-A;
- un reviewer è read-only; le correzioni diventano un nuovo dispatch al relativo
  implementer o a un owner esplicitamente nominato.

### 3.3 Review minima

Ogni task Pi attraversa:

1. implementazione e test dell'autore;
2. prima review indipendente dell'altro Pi/Qwen;
3. fix dei rilievi accettati da parte dell'owner del codice;
4. review Terra high se il task tocca uno dei gate elencati sotto;
5. merge sull'integration branch soltanto dopo evidenza dei test.

Terra high è obbligatorio per:

- schema o migrazione del database;
- catena sorgente/promozione e multi-tenancy;
- `FinalReportModel`, canonicalizzazione e hash;
- readiness e parità con il motore;
- migrazione o freschezza dei commenti;
- avvio del processo Typst, sandbox, timeout e limiti;
- endpoint finale e integrazione di ciascun milestone.

## 4. Branch e worktree

Prima del coding:

1. committare per nome le due spec e questo piano in un commit documentale;
2. creare `feat/report-finale-m1` dalla revisione di `main` che contiene il commit;
3. creare con Orca un child worktree per ciascun task di coding;
4. creare i task paralleli dalla stessa testa dell'integration branch;
5. riportare i commit verificati su `feat/report-finale-m1` nell'ordine indicato;
6. aprire `feat/report-pdf-typst` dalla testa approvata di M1.

Nessun agente lavora direttamente su `main` e nessun agente esegue push. Merge e
push finali richiedono una decisione esplicita del proprietario.

I task branch consigliati sono `agent/m1-<task-id>-<slug>` e
`agent/m2-<task-id>-<slug>`. Una review non crea un branch di correzione finché
non esiste un rilievo accettato.

Gli untracked già presenti (`.pi/`, `.superpowers/`, `p2-put-assumptions.txt`)
restano fuori da ogni commit. Si usa `git add` con percorsi espliciti, mai
`git add -A` o `git add .`.

## 5. Vincoli globali

- denaro in `Decimal`, mai in `float` nel dominio Python;
- percentuali assolute, coerenti con il resto del progetto;
- nessuna formula finanziaria duplicata fuori dai servizi canonici;
- ogni route verifica azienda, scenario e sorgenti tramite `user_id`; una risorsa
  altrui restituisce `404`, non `403`;
- `period_months` nullo o 12 significa annuale; 1–11 significa infrannuale;
- `entry_type == "confirm"` non è una rettifica economica;
- i `DEAD_FIELDS` del wizard non appaiono come driver attivi;
- il caricamento del report non chiama l'AI;
- dati sensibili, JSON del report e sorgente Typst non entrano nei log;
- il template PDF non riceve markup, path, URL o asset arbitrari dall'utente;
- documentazione e test cambiano nello stesso commit del comportamento descritto.
- il frontend non ha `jsdom` o Testing Library: le decisioni testabili restano in
  moduli puri sotto `frontend/lib/`; non si aggiunge una nuova infrastruttura di
  test componenti dentro un task di report.

### Terminatori di riga

Questi file sono CRLF e una patch non deve normalizzarli interamente:

- `database/models.py`;
- `backend/app/api/v1/budget_scenarios.py`;
- `backend/app/api/v1/reports.py`;
- `frontend/lib/api.ts`;
- `frontend/types/api.ts`;
- `frontend/app/report/page.tsx`;
- `frontend/components/pratica/StampaContent.tsx`;
- `frontend/app/pratica/page.tsx`.

`backend/app/services/promote_service.py` ha terminatori misti: ogni task controlla
`git diff --stat` e il diff effettivo prima del commit. Anche
`backend/app/api/v1/financial_years.py` e
`backend/app/schemas/financial_year.py` sono misti. `Jenkinsfile` e
`Dockerfile.backend` sono CRLF. Una riscrittura estesa è un errore, non una
formattazione.

## 6. Grafo generale

```text
D0 documenti e decisioni
  │
  ▼
M1-00 gate di regressione
  │
  ▼
M1-01 persistenza condivisa
  │
  ├──► M1-02 catena/promozione ─┐
  └──► M1-03 alert persistiti ──┤  (serializzati per i file condivisi)
                                ▼
                         M1-04 contratto + fixture
                                │
                  ┌─────────────┴─────────────┐
                  ▼                           ▼
          M1-05A catena/rettifiche   M1-05B ipotesi/grafici
                  └─────────────┬─────────────┘
                                ▼
                    M1-06 assembler + GET
                                │
                  ┌─────────────┴─────────────┐
                  ▼                           ▼
            M1-07 narrazione          M1-08 componenti web
                  └─────────────┬─────────────┘
                                ▼
                    M1-09 integrazione web
                                │
                                ▼
                     M1-10 collaudo finale
                                │
                                ▼
                       M1 APPROVATO

M1-04 ──► M2-00A toolchain ──► M2-00 spike ──► GATE TYPST
M1-10 ──► M2-00B contratto/assembler v2 ─────────────┐
                                                  │
GATE TYPST ──► M2-01 runtime ──► M2-02A base/font/piano
                                      │
                                      ▼
                               M2-03 grafici dossier
                                      │
                                      ▼
                         M2-00C note + client v2
                                      │
                                      ▼
                         M2-02 template definitivo
                                      │
                                      ▼
                           M2-04 harness semantico
                                      │
                                      ▼
                           M2-05 API snapshot/PDF
                                      │
                                      ▼
                        M2-06 UI PDF e packaging
                                      │
                                      ▼
                           M2-07 collaudo finale
```

`M1-02` e `M1-03` sono mostrati come rami logici, ma non si implementano nello
stesso momento: entrambi toccano i confini scenario/API/client. La parallelizzazione
vera in M1 inizia con `M1-05A/B`.

## 7. Milestone M1 — report finale

### D0 — Congelare documenti e base

**Owner:** coordinatore

**Size:** XS

**Files:** le due spec e questo piano.

**Change:** verificare le decisioni di §2, registrare l'approvazione e
creare il commit documentale. Non contiene codice.

**Acceptance:**

- `git diff --check` pulito sui tre documenti;
- stato del repository annotato;
- commit composto solo dai tre file documentali;
- integration branch creato dalla revisione approvata.

### M1-00 — Gate di regressione ripetibile

**Owner coding:** Pi-A/Qwen

**Prima review:** Pi-B/Qwen

**Size:** S

**Depends on:** D0

**Files principali:** nuovo `scripts/verify_report_gate.sh`, `Jenkinsfile` e
documentazione minima del comando.

**Change:** codificare in un solo script i comandi backend, Vitest, TypeScript e
build usati ai gate M1/M2, preservandone gli exit code e stampando i conteggi.
Aggiungere una stage `Test` a Jenkins prima del deploy, oppure registrare nel
commit una decisione esplicita e motivata se l'ambiente Jenkins non può ancora
eseguire una parte del gate. L'health check da solo non è un test di regressione.

Lo script non installa dipendenze, non usa database di produzione e consente una
modalità mirata per i task più piccoli; soltanto i gate di integrazione eseguono
la suite completa.

**Acceptance:**

- un fallimento pytest, Vitest, typecheck o build rende lo script non-zero;
- la pipeline non prosegue al deploy dopo un gate fallito;
- il comando completo riproduce la baseline di §7 M1-10;
- nessun segreto o file cliente viene letto o stampato.

### M1-01 — Fondazione di persistenza

**Owner:** Terra high

**Size:** L

**Depends on:** M1-00

**Files principali:**

- `database/models.py`;
- `migrate_db.py`;
- `backend/app/schemas/budget.py`;
- nuovi schemi strettamente necessari per alert e narrazione;
- nuovi test della migrazione.

**Change:** aggiungere in un solo task tutte le modifiche condivise al database:

- JSON validato e timestamp degli alert extra-contabili;
- `FinancialYear.promoted_from_scenario_id`, nullable e indicizzato, scritto solo
  dalla promozione verificata;
- `FinancialYear.workflow_origin`, con valori controllati per distinguere almeno
  bilancio importato/manuale, apertura startup e proiezione promossa;
- elenco JSON dei campi assumption forniti esplicitamente per ogni anno;
- contenitore versionato dei sei blocchi narrativi, timestamp e hash delle fonti;
- eventuali constraint applicativi necessari per `workflow_type` e sorgente;
- migrazione SQLite idempotente e compatibile con database esistenti.

Non rimuovere o rinominare le colonne AI legacy.

**Acceptance:**

- migrazione eseguita due volte su un database temporaneo senza errore;
- apertura di un database legacy simulato;
- round-trip JSON valido;
- valori `workflow_type` sconosciuti rifiutati dallo schema/API;
- test mirati verdi e diff senza normalizzazioni.

**Review:** prima review Pi/Qwen read-only; seconda review Terra diversa dal
momento di implementazione o un nuovo turno Terra focalizzato sul diff.

### M1-02 — Catena della pratica e promozione

**Owner coding:** Pi-A/Qwen

**Prima review:** Pi-B/Qwen

**Seconda review:** Terra high obbligatoria

**Size:** L

**Depends on:** M1-01

**Files principali:**

- `backend/app/services/promote_service.py`;
- `backend/app/api/v1/budget_scenarios.py`;
- `backend/app/api/v1/financial_years.py`;
- `backend/app/schemas/budget.py` e `backend/app/schemas/financial_year.py`;
- `frontend/components/pratica/StampaContent.tsx`;
- `frontend/app/budget/page.tsx`;
- `frontend/app/pratica/page.tsx` soltanto per il call site di creazione;
- test di lifecycle/promozione.

**Change:** rendere il backend l'unico choke point che decide la provenienza:

- la promozione 1–11 mesi scrive la sorgente e l'origine sul `FinancialYear`;
- creando il budget da quell'esercizio, il server deriva
  `workflow_type=infrannuale` e `source_scenario_id` dalla provenienza persistita;
- un esercizio a 12 mesi importato/manuale produce `workflow_type=bilancio` e
  nessuna falsa origine promossa;
- il percorso startup marca l'anno di apertura con un intent validato e il server
  deriva `workflow_type=startup` dopo aver verificato la struttura di apertura;
- `BudgetScenarioCreate` non accetta come autorità un `source_scenario_id` o
  `workflow_type` arbitrario inviato dal client;
- il riuso cerca una corrispondenza di azienda, base, workflow e sorgente, non un
  generico budget dello stesso anno;
- sorgente e destinazione devono appartenere alla stessa azienda/utente;
- doppio click e nuova promozione non creano catene concorrenti.

Non cambiare i valori contabili copiati dalla promozione.

**Acceptance:**

- estensione di `tests/test_lifecycle_repeat.py` e/o nuovo test mirato;
- test su 1–11 mesi, 12 mesi e startup;
- test di sorgente appartenente a un'altra azienda;
- test che i quattro call site di creazione scenario producano il workflow
  corretto e che un'origine arbitraria inviata dal client sia rifiutata;
- test che una seconda promozione aggiorni in modo coerente esercizio e
  provenienza senza lasciare un budget legato al dato di un'altra sorgente;
- test di re-promozione e riuso;
- `tests/test_quadratura_gates.py` e
  `tests/test_intra_year_end_to_end_periods.py` verdi;
- typecheck dei file frontend coinvolti.

### M1-03 — Persistenza degli alert extra-contabili

**Owner coding:** Pi-B/Qwen

**Prima review:** Pi-A/Qwen

**Seconda review:** Terra high per ownership e schema

**Size:** S

**Depends on:** M1-02, per evitare conflitti nei file condivisi

**Files principali:**

- endpoint dedicato nel router scenario o report, secondo il contratto M1-01;
- servizio puro di validazione/persistenza;
- `frontend/components/pratica/ExtraAccountingAlerts.tsx`;
- `frontend/app/pratica/page.tsx`;
- `frontend/lib/api.ts` e `frontend/types/api.ts`;
- test API e test della funzione client pura.

**Change:** caricare e salvare gli alert sullo scenario sorgente. Le chiavi
ammesse sono enumerate lato backend; chiavi arbitrarie e valori non booleani sono
rifiutati. Il client mostra lo stato persistito dopo refresh e debounce/salva in
modo esplicito senza affidarsi soltanto al componente di stampa.

**Acceptance:**

- refresh e nuova sessione conservano gli alert;
- scenario altrui restituisce `404`;
- chiave sconosciuta restituisce `422`;
- il report futuro può leggere gli alert senza input dal browser;
- nessun cambiamento agli indicatori contabili;
- test frontend e typecheck verdi.

### M1-04 — Contratto `FinalReportModel v1` e fixture

**Owner:** Terra high

**Prima review:** Pi/Qwen

**Size:** L

**Depends on:** M1-02, M1-03

**Files principali:**

- nuovo `backend/app/schemas/final_report.py`;
- tipi dedicati in `frontend/types/`;
- fixture JSON per infrannuale, bilancio e startup;
- catalogo autorevole delle ipotesi e relativo test di parità con il wizard;
- test di contratto backend/frontend.

**Change:** tradurre la spec in schemi espliciti. Fissare:

- sezioni e discriminated union per i tre workflow;
- rappresentazione dei `Decimal`;
- identità, revisioni, diagnostica e readiness;
- rettifiche, chiusura, sette gruppi di ipotesi e forecast;
- provenienza `legacy_unknown` quando un vecchio record non permette di distinguere
  input utente e default;
- serie dei sei grafici;
- sei blocchi narrativi;
- regole di canonicalizzazione di `source_hash` e `model_hash`;
- esclusione di `generated_at` e di ogni campo volatile dall'hash economico.

Le fixture diventano il confine fra backend, React e Typst. Dopo il merge, un
cambio breaking richiede decisione Terra e aggiornamento coordinato dei consumer.

**Acceptance:**

- serializzazione deterministica con valori nulli, negativi e anni multipli;
- hash identico a contenuto identico e diverso dopo una modifica materiale;
- schema sconosciuto rifiutato dal client;
- fixture validate da Pydantic e TypeScript;
- nessun campo finanziario tipizzato come testo generico se ha struttura nota.

### M1-05A — Catena, rettifiche e chiusura come funzioni di dominio

**Owner coding:** Pi-A/Qwen

**Prima review:** Pi-B/Qwen

**Seconda review:** Terra high

**Size:** M

**Depends on:** M1-04

**Ownership esclusiva:** nuovi moduli di risoluzione catena, rettifiche e chiusura;
non modifica router, schema condiviso o `analysis_service.py`.

**Change:** implementare funzioni pure o servizi piccoli per:

- risolvere sorgente esplicita e fallback legacy univoco;
- dichiarare ambiguità senza correggere il database;
- filtrare `confirm` dai movimenti economici;
- riconciliare prima/rettifiche/dopo;
- distinguere progressivo osservato, automatico, override e chiusura usata;
- tradurre alert persistiti nel modello.

**Acceptance:** test unitari sui tre workflow, fallback univoco/ambiguo,
riconciliazione dei segni e conferme escluse. Riutilizzare le regole già coperte da
`tests/test_rettifiche_confirm.py`.

### M1-05B — Ipotesi e serie dei grafici

**Owner coding:** Pi-B/Qwen

**Prima review:** Pi-A/Qwen

**Seconda review:** Terra high per parità dati

**Size:** M

**Depends on:** M1-04

**Ownership esclusiva:** nuovi moduli di classificazione ipotesi e costruzione
serie; non modifica router, schema condiviso o componenti React.

**Change:**

- mappare ogni ipotesi nelle sette sezioni del wizard;
- classificare `user`, `automatic`, `default`, `override`, `ignored`;
- restituire `legacy_unknown` e una diagnostica per i record che non hanno la
  provenienza persistita;
- escludere i `DEAD_FIELDS` dai driver attivi;
- preservare strutture di prestiti, pregresso e differenze temporanee;
- costruire le sei serie dai dati già calcolati, senza nuove formule di dominio.

Il catalogo dei campi ha una fonte autorevole lato backend e un test di parità con
`frontend/lib/budget-wizard-steps.ts`: Qwen non crea una seconda lista non
verificata. `investments` è un caso condizionale legacy: non è un driver attivo,
ma se valorizzato senza gli split può bloccare il motore e deve apparire in
diagnostica, non essere classificato come campo inerte.

**Acceptance:** copertura esatta dei campi senza duplicati, fixture 1/3/5 anni,
null/negativi, provenance nuova/legacy e parità con il wizard e
`analysis_service`.

### Review wave M1-05

Dopo il settlement di entrambi i task:

- Pi-A revisiona solo il diff di M1-05B;
- Pi-B revisiona solo il diff di M1-05A;
- ciascuno esegue i test mirati del collega;
- i fix tornano all'owner originale;
- Terra approva la semantica prima dei merge, nell'ordine M1-05A poi M1-05B.

Questa è la prima ondata con due Pi in parallelo; non se ne avvia un terzo.

### M1-06 — Assembler, readiness e endpoint GET

**Owner:** Terra high

**Prima review:** Pi/Qwen

**Size:** L

**Depends on:** M1-05A, M1-05B

**Files principali:**

- nuovo `backend/app/services/final_report_service.py`;
- `backend/app/api/v1/reports.py`;
- `backend/app/schemas/final_report.py` solo per correzioni additive concordate;
- nuovi test `tests/test_final_report_*.py`.

**Change:** assemblare con una sola query logica il modello completo e aggiungere:

- ownership transitiva di tutte le sorgenti;
- revisioni e hash;
- readiness `ready/draft/blocked` con codici strutturati;
- forecast stale/anni mancanti/quadratura/catena ambigua;
- riuso di `get_complete_analysis`, senza copiare formule;
- `GET /api/v1/companies/{company_id}/scenarios/{scenario_id}/final-report`.

Correggere nello stesso task l'eventuale debolezza di ownership delle route report
esistenti emersa durante la review, con test di non regressione.

**Acceptance:**

- `404` per scenario o sorgente altrui;
- `409` solo per catena non rappresentabile;
- incompletezza rappresentabile restituita come draft/blocked;
- parità dei principali numeri con `/analysis`;
- hash e diagnostica deterministici;
- endpoint non scrive e non chiama l'AI;
- test `forecast_stale`, quadratura e rettifiche verdi.

### M1-07 — Narrazione unificata e migrazione compatibile

**Owner:** Terra high

**Prima review:** Pi/Qwen

**Size:** L

**Depends on:** M1-06

**Files principali:**

- `backend/app/services/ai_comments_service.py`;
- `backend/app/api/v1/reports.py`;
- persistenza introdotta in M1-01;
- API client e componenti commenti solo nel perimetro assegnato;
- test legacy e freschezza.

**Change:** introdurre i sei ID stabili, provenienza, timestamp e source hash;
generare il contesto AI dal modello canonico; migrare o leggere le vecchie 11+6
voci senza sovrascrivere testo utente. Le route legacy possono rimanere durante
una finestra di compatibilità, ma la nuova pagina usa il contratto unificato.

**Acceptance:**

- `GET final-report` non genera commenti;
- generazione esplicita e salvataggio separati;
- testo utente mai sovrascritto automaticamente;
- modifica materiale rende il blocco stale;
- testo legacy non mappabile resta recuperabile;
- `tests/test_infrannuale_comments_stale.py` e nuovi test verdi.

### M1-08A — Componenti origine, rettifiche e chiusura

**Owner coding:** Pi-A/Qwen

**Prima review:** Pi-B/Qwen

**Size:** M

**Depends on:** M1-06

**Ownership esclusiva:** nuovi file sotto `frontend/components/final-report/` per
copertina/perimetro, qualità fonti, rettifiche e chiusura. Non modifica
`frontend/app/report/page.tsx`.

**Acceptance:** rendering condizionale dei tre workflow, tabelle accessibili,
segno/importi italiani, nessun hook/API dentro i componenti e test della logica
pura.

### M1-08B — Componenti ipotesi, readiness e diagnostica

**Owner coding:** Pi-B/Qwen

**Prima review:** Pi-A/Qwen

**Size:** M

**Depends on:** M1-06

**Ownership esclusiva:** nuovi file distinti sotto
`frontend/components/final-report/`. Non modifica `frontend/app/report/page.tsx`.

**Acceptance:** sette sezioni, tabelle nidificate, badge di origine, banner
bozza/bloccato e motivi non affidati solo al colore; schema sconosciuto gestito in
modo esplicito.

### Review wave M1-08

Stesso schema incrociato di M1-05. Terra revisiona in particolare la corrispondenza
fra sezioni del modello e sezioni visibili. I componenti non vengono collegati alla
pagina finché entrambi i diff non sono approvati.

### M1-09 — Integrazione di `/report`

**Owner:** Terra high

**Prima review:** Pi/Qwen

**Size:** L

**Depends on:** M1-07, M1-08A, M1-08B

**Files principali:**

- `frontend/app/report/page.tsx`;
- `frontend/components/report/report-types.ts` e TOC;
- adapter dei componenti analitici esistenti;
- `frontend/lib/api.ts`, hook e tipi già congelati;
- `frontend/lib/report-order.test.ts`.

**Change:** sostituire il caricamento frammentato con il nuovo endpoint,
riordinare il report secondo le dodici sezioni, collegare commenti e diagnostica,
e conservare i componenti analitici esistenti solo dietro adapter puri.

La stampa browser resta etichettata come anteprima fino a M2.

**Acceptance:**

- un solo caricamento di dominio per la pagina;
- sezioni/TOC/ancore nello stesso ordine;
- percorsi infrannuale, bilancio e startup;
- loading/error/retry/schema non supportato;
- modifica ipotesi → stale → rigenerazione forecast → ready;
- `npx vitest run`, `npx tsc --noEmit` e build puliti.

### M1-10 — Collaudo e gate di milestone

**Owner:** Terra high

**Prima review di completezza:** Pi/Qwen, read-only

**Size:** M

**Depends on:** M1-09

**Change:** nessuna nuova funzione salvo fix dispatchati agli owner. Eseguire
collaudo dei tre workflow, controllare parità API/UI e aggiornare documentazione
utente/API nello stesso lotto dei fix finali.

**Gate:**

```bash
env -u ANTHROPIC_API_KEY backend/venv/bin/python -m pytest tests -q \
  --ignore=tests/corpus -p no:cacheprovider -W ignore::DeprecationWarning

cd frontend
npx vitest run
npx tsc --noEmit
npm run build
```

Il numero dei test viene misurato prima del primo task e confrontato nello stesso
ambiente; il criterio è zero nuovi fallimenti, non una cifra storica fissata.

**Baseline misurata durante la review di pianificazione sul commit `e09449b`:**
il comando backend esatto sopra ha prodotto `1095 passed, 9 skipped, 9 warnings`
in 185,21 s; Vitest ha prodotto `748 passed` in 49 file e
`npx tsc --noEmit` termina con codice 0.
Ogni integration branch rimisura comunque la propria baseline se la testa di
`main` cambia prima dell'avvio.

M1 è approvato soltanto se:

- i tre fixture e i tre percorsi reali sono coperti;
- parità finanziaria, ownership e readiness sono verdi;
- nessun dato del report dipende da stato client-only;
- il modello serializzato basta a un renderer offline;
- Terra registra review senza blocker aperti.

## 8. Milestone M2 — PDF Typst

### M2-00A — Toolchain riproducibile per lo spike

**Owner coding:** Pi-A/Qwen

**Prima review/riproduzione:** Pi-B/Qwen

**Size:** S

**Depends on:** M1-04

**Files principali:** manifest/versione/checksum sotto una directory tool dedicata
e script di installazione/verifica per sviluppo. Nessun binario non revisionabile
viene aggiunto senza una decisione esplicita.

**Change:** fissare la versione di Typst prima di misurare lo spike, verificare il
checksum dell'artefatto e documentare come Pi-B ricrea lo stesso ambiente. Il
packaging definitivo nel container resta M2-06B, ma runtime, template e grafici
non possono essere sviluppati contro un `typst` preso casualmente dal sistema.

**Acceptance:** versione e checksum osservabili, installazione in directory
controllata, Pi-B ottiene la stessa `typst --version` e lo script fallisce con un
artefatto alterato.

### M2-00 — Spike Typst e decision gate

**Owner coding:** Pi-A/Qwen

**Prima review/riproduzione:** Pi-B/Qwen

**Decisione:** Terra high

**Size:** L

**Depends on:** M2-00A

**Ownership:** directory di spike dedicata e documentazione della decisione; non
modifica `pdf_service/` né route di produzione.

**Change:** confrontare primitive native, CeTZ-Plot e Primaviz sulle fixture M1 a
1/3/5 anni, valori nulli/negativi, testi lunghi e tabelle multipagina. Misurare
tempo, memoria, dimensione, testo estraibile, grafica vettoriale, funzionamento
offline, licenze e fattibilità PDF/A.

**Acceptance:**

- Pi-B riproduce il risultato in ambiente pulito;
- matrice comparativa e output campione versionabili senza dati cliente;
- versione Typst e checksum proposti;
- nessun download durante la compilazione offline;
- Terra sceglie libreria/primitive oppure chiude il gate come fallito.

Se il gate fallisce, M2 si ferma. Playwright non diventa un fallback implicito.

### M2-00B — Contratto e assembler del dossier v2

**Owner:** coordinatore; review del contratto prima dell'integrazione.

**Esecuzione 2026-09-15:** sviluppo del coordinatore, supporto e review Terra;
nessun agente Pi. Contratto/assembler, getter v2 e fixture dedicati implementati.
Review circoscritta del contratto superata; evidenze e limiti in
[M2-00B](../../testing/M2-00B-dossier-contract.md). Impaginazione, metriche e
commenti per pagina restano nei task successivi. Il gate tecnico Typst rimane
separato e non è approvato da questa consegna.

**Depends on:** M1-10 integrato. Non richiede di riaprire i task M1 conclusi.

**Ownership:** schemi report, assembler, contratti/fixture, negoziazione della
versione API e tipi dedicati; non modifica runtime o componenti Typst.

**Change:** introdurre `FinalReportModel v2` secondo la spec del dossier:
identità neutrale del documento, prospetti completi, gerarchie/subtotali già
calcolati, catalogo indicatori con unità/metodologie e serie aggiuntive. Definire
anche i tipi del piano editoriale e delle note per il successivo planner.
Mantenere lettura e fixture v1; il nuovo client richiederà esplicitamente v2.

**Acceptance:** tre workflow, titolo su anni effettivi di budget, tutte le righe
applicabili dei prospetti preservate, parità con analisi e fonti persistite,
null/zero distinti, nessuna formula finanziaria trasferita al renderer, test di
versione/auth/ownership. Il catalogo non è fissato ai conteggi dell'anteprima.

### M2-02A — Base del dossier, font e piano editoriale

**Owner:** implementatore template; review della composizione prima delle note.

**Depends on:** M2-00B e M2-01 con gate tecnico superato.

**Ownership:** bundle base Typst, font, stili, metriche e planner; non modifica
servizi finanziari, API AI o generatore dei dati.

**Change:** copertina neutrale, stili del dossier, IBM Plex Sans distribuito con
licenza/checksum, tabelle estese e metriche dello spazio dei commenti. Definire
pagine/parti con ID di contenuto, hash layout e riferimenti a righe e note. I
componenti grafici di M2-03 hanno dimensioni dichiarate e precedono il
congelamento del piano completo usato da M2-00C.

**Acceptance:** pianificazione deterministica, testi/nomi lunghi, font offline,
spazio per note su copertina e continuazioni, nessuna riga persa, contesto della
voce padre e header ripetuti. Cambi di font/layout invalidano l'hash del piano.

### M2-00C — Note per pagina e integrazione web v2

**Owner:** implementatore narrazione/client; review di persistenza e freschezza.

**Depends on:** M2-00B, M2-02A e M2-03.

**Ownership:** persistenza note, contesto AI, operazioni di preparazione/
generazione/salvataggio e client `/report` v2; non modifica formule o grafici Typst.

**Change:** aggiungere note brevi per i contenuti del piano, oltre ai sei blocchi
principali. Note di lettura neutrale dal backend con provenienza `automatic`;
AI soltanto su richiesta e da contesti canonici. Proteggere testi manuali,
controllare revisione/fonti e validare i limiti di impaginazione. Adattare titolo,
indicatori e Allegati della pagina web al v2, con stampa dei prospetti per intero.

**Acceptance:** copertura di ogni pagina prevista anche senza provider AI,
provenienza/freschezza verificabili, nessuna generazione AI su GET/export,
nessuna sovrascrittura manuale o troncamento, conflitti di revisioni espliciti,
fixture dei tre workflow e compatibilità v1. Un piano modificato non riutilizza
silenziosamente note riferite a una diversa parte di prospetto.

**Stato 2026-09-15:** implementato in M2-00C con coordinatore e agenti Terra.
Piano persistito con CAS, note automatiche per ogni pagina fisica, override
utente/AI, archivio e riassociazione esplicita. Fit Typst nativo con stessi
font/lingua/spazio del footer. Client `/report` v2 con Allegati completi e bozze
separate per azienda/pratica/piano. Compatibilità v1 conservata; AI soltanto su
richiesta e da contesti canonici strutturati. Dettagli e verifiche in
`docs/testing/M2-00C-editorial-notes.md`. Segue M2-02 per il template definitivo;
packaging/container ed export ufficiale restano nei moduli successivi.

### M2-01 — Runtime e sandbox del compilatore

**Owner coding:** Pi-A/Qwen

**Prima review:** Pi-B/Qwen

**Seconda review:** Terra high obbligatoria

**Size:** L

**Depends on:** gate M2-00 superato

**Files principali:** nuovo package renderer backend, test di processo e asset
fissati. `Dockerfile.backend` viene integrato solo dopo la review del package.

**Change:** interfaccia `TypstRenderer`, directory temporanea, root controllata,
timeout, cleanup, limite input/output/concorrenza, error categories e PDF validator.
Nessun input può diventare markup o path Typst.

**Acceptance:** success/error/timeout/assenza binario/cleanup, rete disabilitata,
nessun dato sensibile nei log, processo terminato sul timeout e test di concorrenza.

### M2-02 — Template editoriale base

**Owner coding:** Pi-B/Qwen

**Prima review:** Pi-A/Qwen

**Seconda review:** Terra per conformità al modello

**Size:** L

**Depends on:** M2-00B, M2-02A, M2-03 e M2-00C, oltre al gate tecnico.

**Ownership:** template definitivo e fixture di rendering. Consuma modello v2,
piano e note; non modifica runtime, dati finanziari o generazione AI.

**Change:** completare il dossier di produzione: titolo neutrale, dodici sezioni
logiche, indicatori approfonditi, Allegati completi e commento pertinente su ogni
pagina. Font, tabelle e grafici seguono il riferimento concordato. Il numero di
pagine è determinato dai contenuti, non dalle 33 pagine del campione.

**Acceptance:** tre workflow e orizzonti 1/3/5 anni, titolo corretto, parità dei
prospetti con lo snapshot, ogni pagina del piano con la propria nota, nessun
ritaglio/duplicazione involontaria, header e contesto ripetuti nelle continuazioni,
font incorporati, scala di grigi leggibile e watermark su ogni pagina di bozza.

### Review della base e del template

Runtime e base/font/planner sono revisionati prima di grafici e note. La review
del template definitivo avviene dopo l’integrazione di modello v2, grafici e note.
Le modifiche ai file condivisi del contratto e dell’API rimangono serializzate.

### M2-03 — Grafici Typst

**Owner coding:** Pi-A/Qwen

**Prima review:** Pi-B/Qwen

**Size:** M

**Depends on:** M2-00B, M2-01 e M2-02A.

**Ownership:** componenti grafici Typst dedicati e dimensioni dichiarate al planner.

**Change:** conservare i sei grafici M1 e implementare gli approfondimenti v2
di liquidità, margini, redditività, coperture, circolante, composizioni e pareggio/
scoring disponibili. Consumare soltanto serie e metadati canonici. Dichiarare
dimensioni e metriche usate dal piano editoriale prima della generazione delle note.

**Acceptance:** nessuna formula finanziaria, grafica vettoriale, fixture 1/3/5
anni, dati estratti coerenti e resa A4 leggibile.

### M2-04 — Harness PDF semantico e golden limitati

**Owner coding:** Pi-B/Qwen

**Prima review:** Pi-A/Qwen

**Size:** M

**Depends on:** M2-01, M2-02

**Ownership:** nuovi test/harness; non modifica i componenti grafici M2-03.

**Change:** validazione `%PDF`, metadata, titolo neutrale, page count, `pdftotext`,
sezioni condizionali, watermark e pochi golden raster stabili. Confrontare tutte
le righe applicabili degli Allegati con il modello e verificare il testo della
nota assegnata a ogni pagina fisica. Il test semantico è autorevole; lo screenshot
non è l’unico oracolo.

**Acceptance:** esecuzione locale e containerizzata, errori leggibili, fixture dei
tre workflow e test che fallisce davvero quando manca una sezione o un valore.

### Review wave M2-03/04

Review incrociata dei due Pi e poi gate Terra sulla parità con il modello. Non si
correggono nel template differenze originate dall'assembler: il bug torna a M1.

### M2-05 — Snapshot, metadati ed endpoint PDF

**Owner:** Terra high

**Prima review:** Pi/Qwen

**Size:** L

**Depends on:** M1-10, M2-00B, M2-00C, M2-02, M2-03 e M2-04

**Files principali:** servizio PDF, `backend/app/api/v1/reports.py`, persistenza
metadati, schemi request/error e test auth/API.

**Change:** congelare il modello, invocare il renderer e servire:

```http
POST /api/v1/companies/{company_id}/scenarios/{scenario_id}/final-report/pdf
```

Implementare profili `draft` e `final`, `ETag`, model hash, schema/template/compiler
version, status `404/409/422/503/504/500` e metadati dell'artefatto. Nessuna
generazione AI o forecast implicita.

**Acceptance:** ownership transitiva, finale bloccato se non ready, bozza sempre
marcata, hash osservabili, errori senza path/dati, temp cleanup e test di parità
con il `GET final-report`.

### M2-06A — Download dalla pagina report

**Owner coding:** Pi-A/Qwen

**Prima review:** Pi-B/Qwen

**Size:** S

**Depends on:** M2-05

**Ownership:** client API, hook/action PDF e UI del report; non modifica Docker o
template.

**Change:** mostrare “Scarica PDF finale” solo quando ready e “Scarica bozza”
negli altri casi, gestire blob, nome file, progress, errori e retry. L'azione non
usa `window.print()` e non cambia i dati.

**Acceptance:** test funzione client, doppio click protetto, errori 409/503/504
leggibili e download con nome coerente.

### M2-06B — Packaging offline e operazioni

**Owner coding:** Pi-B/Qwen

**Prima review:** Pi-A/Qwen

**Seconda review:** Terra high obbligatoria

**Size:** M

**Depends on:** M2-05

**Ownership:** `Dockerfile.backend`, entrypoint/health check, documentazione
deployment e test container; non modifica UI.

**Change:** binario Typst con versione/checksum, font e pacchetti vendorizzati,
health check, metriche e log strutturati. Build e compilazione devono funzionare
senza rete a runtime.

**Acceptance:** cold start, smoke PDF, verifica versione/checksum, nessun Chromium,
limiti osservabili e immagine senza download per richiesta.

### M2-07 — Collaudo finale

**Owner:** Terra high

**Prima review di completezza:** Pi/Qwen

**Size:** M

**Depends on:** M2-06A, M2-06B

**Change:** nessuna nuova funzione salvo fix dispatchati agli owner. Eseguire suite
M1, test renderer/PDF, build container offline e collaudo dei tre workflow.

**Gate M2:**

- nessun Playwright/Chromium nel percorso di produzione;
- PDF valido, ricercabile, stampabile e semanticamente allineato al web;
- draft/final, readiness economica e copertura editoriale corretti;
- titolo neutrale, Allegati completi e commento su ogni pagina;
- timeout, concorrenza, cleanup e ownership coperti;
- versioni e hash presenti;
- cold container verde;
- review Terra senza blocker.

PDF/A-2u viene abilitato soltanto se un validatore formale lo conferma; in caso
contrario il milestone chiude con il profilo standard e una limitazione dichiarata.

## 9. Sequenza delle ondate Pi

Il limite di due agenti Pi è applicato così:

| Onda | Pi-A | Pi-B | Parallelismo |
|---|---|---|---|
| P0 | implementa M1-00 | attende/poi revisiona | 1 coding + 1 review |
| P1 | implementa M1-02 | attende/poi revisiona | 1 coding + 1 review |
| P2 | revisiona M1-03 | implementa M1-03 | 1 coding + 1 review |
| P3 | implementa M1-05A | implementa M1-05B | 2 coding |
| P4 | revisiona M1-05B | revisiona M1-05A | 2 review |
| P5 | implementa M1-08A | implementa M1-08B | 2 coding |
| P6 | revisiona M1-08B | revisiona M1-08A | 2 review |
| P7 | M2-00A e spike M2-00 | riproduce/revisiona dopo output | massimo 2 |
| P7b | revisiona contratto v2 M2-00B | supporta fixture/coverage | un owner del contratto |
| P8 | implementa M2-01 | attende runtime, poi M2-02A | dipendenze seriali |
| P9 | revisiona base/planner | implementa M2-03 dopo la review | un owner del bundle |
| P10 | implementa/revisiona M2-00C | integra template M2-02 dopo note e grafici | dipendenze seriali |
| P11 | revisiona dossier | implementa M2-04 dopo il template | 1 review + 1 harness |
| P12 | implementa M2-06A | implementa M2-06B | 2 coding |
| P13 | revisiona M2-06B | revisiona M2-06A | 2 review |

Terra può svolgere M1-04, M1-06, M1-07, M1-09, M2-05 e i gate quando non tocca
file posseduti da un Pi ancora attivo. Il coordinatore controlla questa condizione
prima di ogni dispatch.

## 10. File che impongono serializzazione

I seguenti file sono punti di integrazione e hanno un solo owner attivo per volta:

| File | Ordine previsto |
|---|---|
| `database/models.py` | M1-01; poi solo modifiche approvate da Terra |
| `migrate_db.py` | M1-01; poi metadati M2 in un task Terra dedicato |
| `backend/app/api/v1/budget_scenarios.py` | M1-02 → M1-03 se usato |
| `backend/app/api/v1/financial_years.py` | solo M1-02 per l'origine dell'anno |
| `backend/app/api/v1/reports.py` | M1-06 → M1-07 → M2-00B → M2-00C → M2-05 |
| `backend/app/services/ai_comments_service.py` | M1-07 → M2-00C |
| `frontend/lib/api.ts` | M1-03 → M1-09 → M2-00C → M2-06A |
| `frontend/types/api.ts` | M1-03; il modello report vive preferibilmente in un file dedicato |
| `frontend/components/pratica/StampaContent.tsx` | solo M1-02 |
| `frontend/app/budget/page.tsx` | solo M1-02 per i call site startup/bilancio |
| `frontend/app/pratica/page.tsx` | M1-02 call site → M1-03 alert |
| `frontend/app/report/page.tsx` | M1-09 → M2-00C → M2-06A |
| `Dockerfile.backend` | solo M2-06B dopo approvazione runtime |

Il contratto M1-04 non viene modificato in parallelo all'assembler o ai renderer.
Una richiesta di cambio sospende i consumer, passa da Terra e aggiorna tutte le
fixture nello stesso gate.

## 11. Comandi di verifica per dispatch

Ogni prompt contiene soltanto i comandi pertinenti al task. I comandi globali
restano quelli di M1-10; esempi mirati:

Nei test HTTP si importa `backend.app.main` prima di moduli `app.*`, seguendo il
fixture di `tests/test_http_full_cycle.py`: in questo repository `app.*` e
`backend.app.*` possono caricare due oggetti modulo distinti per lo stesso file,
rendendo invisibili monkeypatch e contatori applicati a un solo percorso.

```bash
# Catena, promozione, freshness e quadratura
backend/venv/bin/python -m pytest \
  tests/test_lifecycle_repeat.py \
  tests/test_intra_year_end_to_end_periods.py \
  tests/test_forecast_stale.py \
  tests/test_quadratura_gates.py -q -p no:cacheprovider

# Rettifiche e commenti
backend/venv/bin/python -m pytest \
  tests/test_rettifiche_confirm.py \
  tests/test_infrannuale_comments_stale.py -q -p no:cacheprovider

# Frontend
cd frontend
npx vitest run lib/report-order.test.ts
npx vitest run lib/budget-wizard-steps.test.ts
npx tsc --noEmit
```

Da `frontend/` si usano `lib/report-order.test.ts` e
`lib/budget-wizard-steps.test.ts`. Un agente non può interpretare “nessun test
trovato” come successo.

Per M2 il task dello spike stabilisce i comandi definitivi solo dopo aver fissato
binario e validator. Il gate deve comunque includere:

- compilazione con rete disabilitata;
- estrazione testo dal PDF;
- verifica metadati e pagine;
- esecuzione in cold container;
- timeout e cleanup forzati.

## 12. Report obbligatorio di ogni agente

Ogni implementer restituisce:

- commit e file modificati;
- test eseguiti con esito e durata;
- scostamenti dal task;
- rischi residui;
- conferma di non aver incluso file untracked o normalizzato file interi.

Ogni reviewer restituisce rilievi ordinati per severità con file/riga, prova e
test che dimostra il difetto. Se non trova problemi, dichiara esplicitamente i
confini verificati: “nessun rilievo” da solo non è una review sufficiente.

Il coordinatore accetta `worker_done`, assegna i fix all'owner, poi riusa o rilascia
il terminale secondo il ciclo Orca. Un timeout o una sessione non osservabile non
autorizza un retry duplicato.

## 13. Rischi principali

1. **Catena falsa o ambigua.** Mitigazione: collegamento esplicito prima del
   report, fallback legacy solo in lettura e diagnostica.
2. **Divergenza dei numeri.** Mitigazione: assembler riusa `analysis_service`,
   fixture canoniche e test di parità.
3. **Migrazione distruttiva dei commenti.** Mitigazione: colonne legacy mantenute,
   mapping solo univoco e testo utente protetto.
4. **Conflitti CRLF.** Mitigazione: ownership seriale, diff stat e nessun formatter
   globale.
5. **Due renderer che classificano diversamente.** Mitigazione: sezioni, serie e
   diagnostica già nel modello.
6. **Template Typst con accesso incontrollato.** Mitigazione: bundle interno,
   root/temp controllate, no markup/path utente, timeout e rete disabilitata.
7. **Pacchetti Typst instabili.** Mitigazione: spike, versioni/checksum, bundle
   offline e possibilità di usare primitive interne.
8. **ReportLab riusato per comodità.** Mitigazione: `pdf_service/` fuori ownership
   del milestone; nessuna sua funzione alimenta il nuovo endpoint.
9. **Review che modifica direttamente il codice.** Mitigazione: reviewer read-only
   e fix dispatchato all'owner.
10. **Eccesso di parallelismo.** Mitigazione: tabella delle ondate, massimo due Pi
    e serializzazione dei file di integrazione.

## 14. Punto di arresto prima del coding

L'approvazione di questo piano autorizza soltanto il successivo avvio di D0 e
M1-00. Non implica merge o push su `main`.

Prima del primo task di coding il coordinatore deve mostrare:

- commit documentale e branch di integrazione;
- stato pulito rispetto ai file di progetto, esclusi gli untracked noti;
- receipt dei worker con modello/effort verificati;
- prompt autosufficiente di M1-00;
- baseline dei test mirati.

Si procede quindi un'ondata alla volta. M2 non entra in produzione finché M1-10
non è approvato, anche se lo spike e il template sono già pronti.

### Esecuzione M2-00 / M2-01 — 2026-09-15

Su istruzione dell’utente, implementazione diretta e reviewer Terra high, senza Pi.
M2-00A e spike integrati dopo gate indipendente: native Typst scelto, 24/24 PDF
riusciti identici byte per byte, 42 test toolchain/spike. M2-01 runtime isolato
completato, due review indipendenti Terra high approvate: 42 test di runtime;
117 test mirati complessivi. Ricevute e limiti in
`docs/testing/M2-00-TYPST-SPIKE.md` e `docs/testing/M2-01-typst-runtime.md`.
Nessun push/merge su main, nessun endpoint di export anticipato.
Prossimo task M2-02A: base, IBM Plex Sans e planner misurato; piano completo
congelato dopo dimensioni dei grafici M2-03 e prima delle note M2-00C.

### Esecuzione M2-02A, base e piano provvisorio — 2026-09-15

Base A4 verticale implementata con copertina neutra, Plex Sans statici identici
al riferimento (OFL/provenance/checksum), tre prospetti completi e spazio commento
su ogni pagina. TypstLayoutProbe misura la composizione reale in sandbox;
MeasuredBasePlan raggruppa righe/pagine con ID semantici e hash font/layout/asset.
Il risultato ha scope=base, finalized=False: non viene assegnato al contratto
editorial_plan e non dichiara readiness o copertura del dossier definitivo.
Collaudo finale: 152 test mirati; due review Terra high approvate.
Collisione valida di ID locali fra prospetti corretta con namespace di prospetto;
regressione reale e riproduzione indipendente passate. Dettaglio in
docs/testing/M2-02A-dossier-base.md.
La fase successiva è M2-03, dimensioni/componenti grafici. Segue completamento
del planner/reflow M2-02A con inventario completo, prima di M2-00C note.

### Esecuzione M2-03, grafici canonici — 2026-09-15

Implementazione diretta e review indipendente Terra high, su autorizzazione
dell’utente senza Pi. Integrati componenti vettoriali per sei grafici M1 e dieci
approfondimenti v2 materializzati; barre divergenti, linee interrotte sui null,
quattro stili colore/grigio, valori tabellari formattati da stringhe Decimal.
Soglie soltanto dai riferimenti canonici, nessuna formula finanziaria nel renderer.
Geometria `native-charts-1` congelata a 178×94 mm (plot 62 + legenda 32),
verificata anche attraverso le misure reali Typst. Review approvata dopo una
regressione che impedisce altre dimensioni anche in una revisione firmata.
Collaudo: 53 test grafici, 205 test mirati complessivi passati in 76.14s.
Ricevuta e inventario in `docs/testing/M2-03-typst-charts.md`.

La preview BOZZA ha 17 pagine e dati sintetici; il piano finale resta da comporre.
L’audit del catalogo rileva che confronto infrannuale collegato, composizioni
complete, pareggio e scoring non sono ancora serie canoniche del dossier v2.
Prima del freeze completo M2-02A, verificare ed estendere assembler/contratto
per i dati disponibili nei servizi autorevoli; non ricavarli nel template.
Seguono inventario e reflow del piano completo, poi M2-00C per i commenti.

### Esecuzione M2-02A, piano canonico completo — 2026-09-15

Completata la composizione misurata del dossier v2 corrente, con implementazione
del coordinatore, inventario/audit Terra e review indipendente Terra high.
Dodici sezioni logiche, undici per bilancio/startup; tutte le ipotesi anche
annidate, rettifiche, valori di chiusura, sedici grafici e catalogo indicatori.
Allegati CE/SP/CF completi con contesto padre e indice su pagine reali.
Confronti infrannuali consumano i periodi canonici già esistenti, con durate
esplicite e nessuna annualizzazione nel template. La fixture a sette periodi
verifica storico/osservato/rettificato/chiusura e tre anni di budget.

Il nuovo planner assegna `editorial_plan` dopo misura nel runtime isolato,
con inventory esatto e un riquadro commento per ogni pagina/continuazione.
ID semantici e hash font/layout/asset/fonti includono la definizione Python
dell’inventario; la sua modifica richiede worker ricaricato e nuovo piano.
Note manuali conservate su piano identico, riassociazione esplicita sul drift,
testi/importi troppo grandi rifiutati senza tagli. Nessuna scrittura o AI.
Il planner base rimane disponibile come risultato provvisorio separato.

Review Terra high approvata, incluso hardening dei tipi dei metadata grafici,
fingerprint inventario e limiti prima dello staging. Verifica: 235 test nella
prima suite combinata e 34 mirati finali sul codice aggiornato, 239 test distinti
complessivi. Ricevuta dei test in
`docs/testing/M2-02A-editorial-plan.md`. La composizione non è ancora il template
editoriale definitivo: segue M2-00C per copertura automatica dei commenti,
persistenza protetta e client v2, quindi M2-02 e gate di export.
Scoring/pareggio/composizioni complete restano una estensione canonica
dedicata prima del collaudo definitivo; ogni aggiunta richiede nuovo piano.
