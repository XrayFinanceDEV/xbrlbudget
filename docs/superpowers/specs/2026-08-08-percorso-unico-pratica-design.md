# Percorso unico "Pratica" — due workflow, rettifiche obbligatorie, stepper condiviso

**Data:** 2026-08-08
**Stato:** Design approvato (in attesa di review della spec scritta)
**Area:** frontend journey — nessuna modifica a DB, motori di calcolo o endpoint
**Precedente:** `docs/superpowers/specs/2026-07-06-pratica-workflow-reorganization-design.md`
(questo design ne sostituisce la Phase A con una versione molto più contenuta, e ne riduce i
workflow da 3 a 2)

**Nota 2026-08-08 (decisione presa durante l'implementazione, Task 4 del piano):** questo
documento, nella sua stesura originale, elencava la fase PREVISIONALE con **quattro** voci
(`Budget › CE Previsionale › Rendiconto › Report`). In fase di implementazione, sostituire la nav
piatta con lo stepper ha reso `/forecast/balance` e `/forecast/reclassified` — pagine esistenti,
prima raggiungibili dal dropdown "Previsionale" della nav — irraggiungibili dall'interno di una
pratica, perché quel dropdown sparisce insieme al resto della nav piatta quando lo stepper è
attivo. Emerso come finding Important nella review del Task 4, l'utente ha deciso di aggiungere
entrambi gli step invece di lasciarli isolati. La fase PREVISIONALE ha quindi **sei** voci:
`Budget › CE Prev. › SP Prev. › Riclassificato › Rendiconto › Report`. Le sezioni sotto sono state
aggiornate di conseguenza; questo paragrafo resta a futura memoria della decisione. Dettagli:
`.superpowers/sdd/2026-08-08-percorso-unico-pratica/progress.md` ("Task 4: DECISIONE UTENTE").

## Problema

1. **Troppe strade per la stessa cosa.** "Nuova pratica" offre 3 card
   (`frontend/app/page.tsx:191-237`): *Budget da bilancio*, *Infrannuale*, *Startup*. Le prime
   due portano allo stesso risultato — un budget costruito su dati importati — ma per percorsi
   diversi e con garanzie diverse.
2. **Si può importare un bilancio senza passare dalle rettifiche.** La card *Budget da bilancio*
   va su `/import` e poi su `/budget`. I bilanci di verifica arrivano quasi sempre sporchi
   (fondi non nettati, debiti non tipizzati, sbilanci di arrotondamento): saltare le rettifiche
   propaga l'errore su confronto, proiezione, indicatori e rating.
3. **Le rettifiche disponibili da `/budget` sono monche.** `HistoricalBalanceDetailEditor`
   (`app/budget/page.tsx:1214`) permette solo di ripartire un aggregato sui suoi dettagli, con
   destinazioni fisse (`ALLOCATION_TARGETS`). Non ha partita doppia, né journal, né reset, né la
   scheda storico — tutte cose che `RettificheTab` in `app/infrannuale/page.tsx` ha.
   Due implementazioni divergenti della stessa funzione.
4. **Il percorso non si vede.** Dentro `/infrannuale` c'è uno stepper a 7 voci
   (`app/infrannuale/page.tsx:3651`); appena si passa al budget subentra la nav piatta
   (`components/Navigation.tsx`) e l'utente perde il filo. Le due barre non si parlano.
5. **Il "promote cliff".** `app/infrannuale/page.tsx:5498-5502` fa `promoteProjection` e poi
   `router.push("/budget")` senza creare lo scenario budget: l'utente ricostruisce il contesto
   a mano.

## Obiettivi

1. Due soli percorsi per una nuova pratica: **Da bilancio** e **Startup**.
2. Le **Rettifiche** sono uno step obbligato del percorso Da bilancio, con conferma esplicita
   che sopravvive al refresh.
3. Un **unico stepper** che racconta il percorso dall'anagrafica al report, visibile anche sulle
   pagine di previsionale e analisi.
4. Il passaggio Analisi → Budget avviene senza far ricostruire nulla all'utente.

## Non obiettivi

- Nessuna modifica a `database/models.py`, alle migrazioni, ai motori di calcolo, agli endpoint.
  In particolare **non** si introducono `source_scenario_id` / `workflow_type` (previsti dallo
  spec di luglio): la pratica attiva vive nel client.
- Nessun cambio di rotte in stile `/pratica/[scenarioId]/[step]`.
- Nessuna decomposizione di `app/infrannuale/page.tsx` (5.858 righe) né di `app/budget/page.tsx`.
  Resta il follow-up già noto.
- Nessun redesign visivo: shadcn/slate invariato.

## I due percorsi

### 1. Da bilancio (`/pratica`, ex `/infrannuale`)

Il wizard smette di essere "l'analisi infrannuale" e diventa **l'unico percorso da bilancio**.
Il periodo importato decide quanti step vengono mostrati.

| Step | 1-11 mesi | 12 mesi |
|---|---|---|
| Anagrafiche | ✔ | ✔ |
| Importazione | ✔ | ✔ |
| Rettifiche | ✔ **obbligatorio** | ✔ **obbligatorio** |
| Confronto | ✔ | ✔ |
| Proiezione | ✔ | — |
| Indicatori | ✔ | ✔ |
| Stampa | ✔ | ✔ |
| Budget e oltre | `promote` + crea scenario | crea scenario, **niente `promote`** |

Il ramo a 12 mesi esiste già nel codice (`periodMonths !== 12` filtra la Proiezione a
`app/infrannuale/page.tsx:3656`; `saveProjection12M` a `:3477`). Cambia solo la coda: a 12 mesi
**non si chiama `promoteProjection`**, perché l'anno importato è già un `FinancialYear` completo
e riscriverlo con una copia ricalcolata dal motore è un rischio senza contropartita.

### 2. Startup (`/budget` in `startupMode`)

Invariato nella sostanza: `Anagrafiche › Budget › CE Prev. › SP Prev. › Riclassificato ›
Rendiconto › Report` (sei voci PREVISIONALE, non quattro — vedi la nota 2026-08-08 in testa a
questo documento). Cambia solo l'ingresso (una delle due card della home) e il fatto che ora è
coperto dallo stepper condiviso.

Il workflow startup **non passa da `/pratica`**: lo step *Anagrafiche* della sua barra è il form
"Nuovo business plan startup" già presente in `app/budget/page.tsx:482+` (nome, descrizione,
capitale sociale), che raccoglie proprio l'identità della startup. Lo stepper vi punta con
`router.push("/budget")` e la pagina mostra quel form finché lo scenario non esiste; una volta
creato, lo step attivo diventa *Budget*. Nessun componente nuovo per questo ramo.

## Home `/`

Le tre card di "Nuova pratica" diventano due:

| Card | Destinazione |
|---|---|
| **Da bilancio** — bilancio ufficiale o bilancio di verifica infrannuale | `startupMode=false` → `/pratica` |
| **Startup** — business plan senza storico | `startupMode=true`, azienda deselezionata → `/budget` |

Sparisce la card *Budget da bilancio*: è precisamente il percorso senza rettifiche che va chiuso.
Entrambe le card popolano il `PraticaContext` prima di navigare.

L'elenco aziende con le pratiche e il bottone **Riprendi** resta. `resume()`
(`app/page.tsx:169-172`) popola il `PraticaContext` a partire dallo scenario e poi naviga:
`scenario_type === "infrannuale"` → `workflow: "bilancio"` e `/pratica`; altrimenti →
`workflow: "startup"` se `startupMode` era stato salvato per quello scenario, `"bilancio"` in
caso contrario, e `/budget` con `budgetScenarioId` già valorizzato. Uno scenario budget legacy
riaperto mostra quindi la sola fase PREVISIONALE della barra, con gli step ANALISI disabilitati:
i suoi dati d'origine non sono ricostruibili e fingere il contrario sarebbe peggio.

## Lo step Anagrafiche

Nuovo primo step del wizard, sostituisce lo step *Aziende* attuale
(`app/infrannuale/page.tsx`, `activeTab === "aziende"`), che duplica la home e carica gli scenari
di tutte le aziende con `O(n)` chiamate API.

Contiene i dati dell'azienda della pratica — nome, P.IVA, settore — modificabili
(`updateCompany`). Se la pratica parte senza azienda selezionata è il form di creazione
(`createCompany`), che diventa il primo passo naturale. Nessun elenco aziende: la scelta è già
avvenuta sulla home.

## Il gate Rettifiche

Lo step Rettifiche guadagna in fondo un bottone **"Conferma e prosegui"**. Finché non è premuto,
Confronto e successivi restano disabilitati nello stepper.

**Persistenza senza nuove colonne.** La conferma è una voce nel `rettifiche_log` già esistente
(`FinancialYear.rettifiche_log`, JSON array), della forma
`{ type: "confirm", ts: "<ISO>", by: "user" }`. Vantaggi: nessuna migrazione, e il log è già
letto al mount da `hooks/use-rettifiche-year.ts`, quindi la conferma sopravvive al refresh
senza codice nuovo di caricamento.

Vincoli da rispettare:

- Il cap di 20 voci (`RETTIFICHE_LOG_MAX` in `backend/app/api/v1/financial_years.py`) conta
  anche questa voce. La conferma è **idempotente**: se una voce `confirm` è già presente non se
  ne aggiunge un'altra. Le voci `confirm` sono inoltre **escluse dal conteggio client-side**
  contro `RETTIFICHE_MAX`, così una conferma non consuma una rettifica dell'utente.
- Il pannello journal e il dialogo Riepilogo **filtrano** le voci `type === "confirm"`: non sono
  rettifiche e non devono comparire come righe con delete.
- Il **reset** (che rimanda `original_*_snapshot` + log vuoto) azzera anche la conferma: dopo un
  reset l'utente riconferma.

**Per anno.** Con le due schede (Storico + Bilancio di verifica) servono entrambe le conferme.
Se la scheda Storico non esiste (import senza anno di raffronto, `storico.exists === false`)
si richiede solo quella della verifica.

**Non bloccante sullo sbilancio.** Se il bilancio non quadra resta l'avviso attuale con il
bottone "Chiudi sbilancio", ma la conferma è comunque possibile — coerente con le commit
`c29b4cf`, `eb597bb`, `9a16676`, `78fcbac` che hanno reso l'import sbilanciato non bloccante.

## Il ponte verso il Budget

Sostituisce il blocco di `app/infrannuale/page.tsx:5490-5510`. Un'unica azione
**"Prosegui al Budget"**, con due rami:

- **periodo < 12 mesi:** `promoteProjection(companyId, scenarioId)` (come oggi) → `baseYear` =
  anno proiettato.
- **periodo = 12 mesi:** nessun `promote` → `baseYear` = anno importato.

Poi, in entrambi i casi:

1. `createBudgetScenario(companyId, { name: "Budget {baseYear+1}–{baseYear+3}", base_year:
   baseYear, scenario_type: "budget" })`.
2. **Riuso, non duplicazione:** prima di creare, cerca tra gli scenari dell'azienda uno con
   `scenario_type === "budget"` e lo stesso `base_year`; se c'è lo riusa. Copre il doppio click
   e l'utente che torna indietro e ripassa.
3. Scrive `budgetScenarioId` nel `PraticaContext`, poi `router.push("/budget")`, che apre
   sull'elenco scenari (`activeTab === "list"`) — non direttamente sull'editor ipotesi. Lo
   scenario giusto è comunque già selezionato/creato in `PraticaContext`, pronto per essere
   aperto dall'elenco.
   **[Corretto 2026-08-08, FINDING 9]:** verificato contro `app/budget/page.tsx` — `activeTab`
   parte da `"list"`, non da un tab di modifica.

## Lo stepper condiviso

### `PraticaContext`

Nuovo context accanto ad `AppContext`, con lo stato della pratica attiva:

```ts
type PraticaState = {
  workflow: "bilancio" | "startup";
  companyId: number | null;
  fiscalYear: number | null;
  periodMonths: number | null;      // 1-12
  infrannualeScenarioId: number | null;
  budgetScenarioId: number | null;
  rettificheConfirmed: { storico: boolean; verifica: boolean };
} | null;
```

Persistito in `localStorage` con lo stesso pattern di `startupMode`
(`contexts/AppContext.tsx:47-63`): stato iniziale `null`, lettura in `useEffect` al mount, mai
nell'inizializzatore di `useState` — altrimenti Next sbaglia l'idratazione. `PraticaProvider`
va **sopra** `AppProvider` in `app/layout.tsx`.

`rettificheConfirmed` nel context è una cache per lo stepper; la **verità** resta il
`rettifiche_log` sul server, riletto al mount del wizard.

### `<PraticaStepper>`

Renderizzato **dentro** `<Navigation>` (non al posto suo in `app/layout.tsx`): `Navigation`
ritorna `<PraticaStepper />` invece della nav piatta quando `pratica !== null` e la rotta non è
`/`, mai insieme. Fuori dalla pratica la nav attuale resta invariata (modalità "browse" sui dati
vecchi).
**[Corretto 2026-08-08, FINDING 9]:** verificato contro `components/Navigation.tsx` — il punto di
composizione è `Navigation`, non `app/layout.tsx`.

Due fasi in un'unica barra, separate da un divisore:

```
ANALISI         Anagrafiche › Import › Rettifiche › Confronto › [Proiezione] › Indicatori › Stampa
PREVISIONALE │  Budget › CE Prev. › SP Prev. › Riclassificato › Rendiconto › Report
```

- La fase ANALISI non compare nel workflow **startup**: la barra è
  `Anagrafiche › Budget › CE Prev. › SP Prev. › Riclassificato › Rendiconto › Report`.
- **Proiezione** compare solo con `periodMonths < 12`.
- Gli step della fase ANALISI sono tab interne a `/pratica` → cliccarli fa `setAnalysisStep`.
  Quelli della fase PREVISIONALE sono rotte reali → cliccarli fa `router.push`. La distinzione
  vive in una tabella di definizione degli step (`kind: "tab" | "route"`), non in `if` sparsi.
  Da una rotta della fase PREVISIONALE, cliccare uno step ANALISI chiama `setAnalysisStep(id)`
  (scrive `analysisStep` nel `PraticaContext`, persistito in `localStorage`) e poi
  `router.push("/pratica")` **solo se non si è già lì**; il wizard legge `pratica.analysisStep`
  al render e apre quella tab. **Non esiste** un contratto URL `/pratica?step=<id>` — non c'è
  query string coinvolta.
  **[Corretto 2026-08-08, FINDING 9]:** verificato contro `components/PraticaStepper.tsx`
  (funzione `go`).
- Gli step già superati sono cliccabili; quelli non raggiungibili sono disabilitati, con lo
  stesso stile già usato (`text-muted-foreground/40 cursor-not-allowed`).
- Gli step della fase PREVISIONALE si abilitano quando `budgetScenarioId !== null`;
  CE Previsionale / Rendiconto / Report quando esiste un forecast generato.
- In coda alla barra un bottone **"Esci dalla pratica"** azzera il context e torna a `/`.
- `overflow-x-auto` come oggi; etichette corte ("Import", "CE Prev.", "Rendiconto").
- `print:hidden`, come le barre attuali.

## Cosa perde `/budget`

- **Via `HistoricalBalanceDetailEditor`** (`app/budget/page.tsx:84,1214` +
  `components/budget/HistoricalBalanceDetailEditor.tsx`, eliminato). Le rettifiche vere sono a
  monte e obbligatorie; mantenere due implementazioni divergenti è il problema che si sta
  chiudendo. `lib/ivcee-balance-catalog.ts` resta se usato altrove, altrimenti va con lui.
- **Via la creazione manuale di scenario "da bilancio"**: resta la creazione in `startupMode`
  e la modifica/eliminazione degli scenari esistenti.
- `/budget` resta l'editor ipotesi + elenco scenari, raggiunto dal percorso.

## Cosa perde la nav

`MAIN_TABS` in `components/Navigation.tsx` perde la voce **Importazione**: l'import vive dentro
il percorso. `/import` resta come rotta funzionante (non referenziata dalla nav) per non
rompere link salvati.

La riga `if (pathname.startsWith("/infrannuale")) return null;` diventa `/pratica`, ma è resa
ridondante dalla regola generale "stepper *oppure* nav, mai entrambi".

## Rotte

- `/infrannuale` → **redirect** a `/pratica` (preserva i link salvati).
- `/pratica` → il wizard; la tab attiva viene da `pratica.analysisStep` nel `PraticaContext`
  (`localStorage`), non da una query string — vedi la nota sopra sotto `<PraticaStepper>`.
  **[Corretto 2026-08-08, FINDING 9]:** non esiste `?step=<id>`.
- `/aziende`, `/import` → invariate, non più referenziate dalla nav.

## Casi limite

- **Pratica attiva e utente che va su `/`**: la home resta accessibile; lo stepper è nascosto
  su `/` (è la pagina di uscita). `setStartupMode(false)` all'atterraggio su `/` resta com'è.
- **Refresh su `/budget` con pratica attiva**: il context si riprende da `localStorage`, lo
  stepper si ridisegna, lo scenario budget è già selezionato.
- **Pratica che punta a un'azienda o a uno scenario cancellati**: al mount, se
  `companyId` non è tra le `companies` di `AppContext`, il context si azzera e torna la nav
  normale. Nessun errore all'utente.
- **Due tab del browser sulla stessa app**: `localStorage` è condiviso, l'ultima scrittura
  vince. Accettato — è già il comportamento di `startupMode`.
- **Doppio click su "Prosegui al Budget"**: il bottone si disabilita durante l'operazione e il
  riuso dello scenario per `base_year` rende l'azione idempotente.
- **Import senza anno di raffronto** (`handleSkipRefYear`): il percorso prosegue, la scheda
  Storico è disabilitata e non richiede conferma; il Confronto gira in modalità sola
  annualizzazione, già supportata.
- **Reset delle rettifiche dopo aver superato lo step**: il gate torna chiuso e gli step
  successivi si ridisabilitano, coerente con l'invalidazione downstream già esistente
  (`comparison`, `projectedBS`, `analysis` azzerati).

## Verifica

- `npm run build` (frontend) dopo ogni gruppo di modifiche — è il gate minimo, il progetto non
  ha test frontend.
- **Percorso 1 (bilancino 9M)**, con playwright: home → Da bilancio → Anagrafiche → import PDF
  9M → Rettifiche (Confronto disabilitato) → conferma su entrambe le schede → Confronto →
  Proiezione → Indicatori → Stampa → Prosegui al Budget → `/budget` si apre con azienda e
  scenario budget selezionati e `base_year` = anno proiettato.
- **Percorso 2 (bilancio annuale 12M)**: stesso flusso senza lo step Proiezione; verificare via
  API che il `FinancialYear` dell'anno importato **non** sia stato riscritto (confrontare
  `updated_at` / i valori SP prima e dopo il passaggio al budget) e che lo scenario budget abbia
  `base_year` = anno importato.
- **Percorso 3 (startup)**: home → Startup → Anagrafiche → Budget → CE Previsionale → Report,
  con lo stepper a 7 voci (Anagrafiche + le sei della fase PREVISIONALE) e senza la fase ANALISI.
- **Persistenza del gate**: confermate le rettifiche, `F5`; gli step restano sbloccati.
  Poi reset delle rettifiche → gli step si richiudono.
- **Uscita**: "Esci dalla pratica" → `/`, riappare la nav normale senza Importazione.
- File di prova disponibili in `docs/examples/` (PDF bilanci e bilancini reali).

## File toccati

**Nuovi**
- `frontend/contexts/PraticaContext.tsx`
- `frontend/components/PraticaStepper.tsx`
- `frontend/components/pratica/AnagraficheStep.tsx`
- `frontend/app/pratica/page.tsx` — il wizard, spostato da `app/infrannuale/page.tsx` e poi
  modificato: step Anagrafiche al posto dello step Aziende, gate rettifiche, ponte al budget

**Modificati**
- `frontend/app/infrannuale/page.tsx` — ridotto a redirect verso `/pratica`
- `frontend/app/layout.tsx` — `PraticaProvider` + stepper/nav mutuamente esclusivi
- `frontend/app/page.tsx` — due card, `resume()` popola il context e instrada per workflow
- `frontend/hooks/use-rettifiche-year.ts` — lettura/scrittura della voce `confirm`
- `frontend/app/budget/page.tsx` — via `HistoricalBalanceDetailEditor` e la creazione manuale
- `frontend/components/Navigation.tsx` — via la tab Importazione
- `CLAUDE.md` — sezione sul percorso unico

**Eliminati**
- `frontend/components/budget/HistoricalBalanceDetailEditor.tsx`

## Follow-up fuori scope

- Decomposizione di `app/pratica/page.tsx` (il monolite da 5.858 righe) e di `app/budget/page.tsx`.
- `frontend/lib/ivcee-layout.ts` come sorgente unica del layout IV-CEE (Phase B dello spec di
  luglio).
- Step indirizzabili via URL con `source_scenario_id` sul DB (Phase A dello spec di luglio):
  superata da questo design, da riprendere solo se il `localStorage` si rivelasse insufficiente.
