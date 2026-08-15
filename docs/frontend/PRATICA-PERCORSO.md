# Il percorso «Pratica» — due workflow, tre fasi, un solo punto di avanzamento

> Le regole che, violate, corrompono un dato **senza che nessun controllo se ne accorga** stanno
> in `CLAUDE.md` § «Invarianti e trappole». Qui c'è come funziona.

Una **pratica** è il lavoro su un'azienda dall'anagrafica al report: importare un bilancio,
correggerlo, confrontarlo con l'anno di riferimento, proiettarlo, e infine costruirci sopra un
previsionale. Prima esisteva una nav piatta di tab indipendenti, dove l'ordine dei passaggi era
una convenzione a memoria dell'utente; oggi è un percorso con uno **stato persistito**, uno
**stepper** che mostra dove si è, e **un solo** bottone di avanzamento.

## 1. I due workflow

Le due card di «Nuova pratica» sulla home (`app/page.tsx:228-273`):

| Card | Workflow | Dove parte |
|---|---|---|
| **Da bilancio** | `"bilancio"` | `/pratica` — bilancio ufficiale o bilancio di verifica infrannuale |
| **Startup** | `"startup"` | `/budget` in `startupMode` — business plan senza bilancio storico |

Erano tre. La terza, «Budget da bilancio ufficiale, senza rettifiche», è stata rimossa perché era
esattamente la via che lasciava un bilancio di verifica **saltare le Rettifiche** e propagare i
suoi errori in Confronto, Proiezione, Indicatori e nei due modelli di rating. `/infrannuale`, la
vecchia rotta del wizard, è oggi un `redirect()` a `/pratica` (`app/infrannuale/page.tsx`).

Altri due ingressi, entrambi in `app/page.tsx`: `startForCompany` (avvia una pratica `bilancio`
già puntata su un'azienda esistente) e `resume` (riapre una pratica da uno scenario già creato —
vedi §4 per il caso «scenario budget legacy»).

Spec: `docs/superpowers/specs/2026-08-08-percorso-unico-pratica-design.md`. Piano:
`docs/superpowers/plans/2026-08-08-percorso-unico-pratica.md`. Registro di esecuzione, con ogni
deviazione dal piano — quasi tutte trovate provando in browser, non in review:
`.superpowers/sdd/2026-08-08-percorso-unico-pratica/progress.md`.

## 2. Lo stato della pratica

`contexts/PraticaContext.tsx` tiene la pratica attiva, persistita in `localStorage` sotto
`xbrl_pratica`:

| Campo | Che cos'è |
|---|---|
| `workflow` | `"bilancio"` \| `"startup"` |
| `companyId` | l'azienda; `null` finché non la si sceglie o crea in Anagrafiche |
| `fiscalYear`, `periodMonths` | l'anno importato e il suo periodo (12 = annuale) |
| `infrannualeScenarioId` | lo scenario infrannuale, creato all'import |
| `budgetScenarioId` | lo scenario budget, creato dal ponte verso il previsionale |
| `analysisStep` | la tab attiva dentro `/pratica` |
| `rettificheConfirmed` | `{ storico, verifica }` — **una cache**, vedi sotto |

Tre proprietà da non perdere di vista:

- **Si legge dopo il mount, in un `useEffect`.** Leggere `localStorage` nell'inizializzatore di
  `useState` fa renderizzare a server e client due markup diversi, e Next sbaglia l'idratazione.
- **Si scrive in un `useEffect` su `[pratica]`**, non dentro un updater di `setState`
  (`reactStrictMode` invoca gli updater due volte in sviluppo). Quell'effetto è **autoritativo per
  entrambi i casi**: scrive quando la pratica c'è, **rimuove** quando è `null`. Se la rimozione
  stesse altrove, un effetto in un componente figlio — `AppContext` è montato più in basso — che
  chiama `exitPratica()` nello stesso commit vedrebbe questo effetto rieseguirsi ancora chiuso sul
  vecchio valore e riscriverebbe la entry appena cancellata.
- **`rettificheConfirmed` è una cache dello stepper, non la verità.** La verità è il
  `rettifiche_log` sul server, riletto al mount del wizard; la cache serve solo a non far
  sfarfallare lo stepper al primo render.

> ⚠️ L'effetto che riallinea la cache dal server (`app/pratica/page.tsx:210-223`) porta una
> guardia da non rimuovere: **non scrivere prima che l'anno sia risolto** (`data !== null` oppure
> 404 con `exists === false`). Gli hook `useRettificheYear` caricano **solo** sulla tab Rettifiche,
> quindi su un mount qualunque — per esempio rientrando su `/pratica` dallo stepper dopo essere
> stati su `/budget` — sono ancora a `confirmed: false` mentre il context ha già un valore buono da
> `localStorage`. Senza la guardia l'effetto scriveva `false` a ogni mount e cancellava una
> conferma legittima; e da quando `blockedStep()` legge la stessa cache per il render gate (§4),
> questo diventava un **falso blocco** su Confronto/Proiezione/Indicatori/Stampa per un utente che
> aveva confermato.

### Chi altro consuma il context

`AppContext` chiama `usePratica()` — legale solo perché `PraticaProvider` sta **sopra**
`AppProvider` in `app/layout.tsx`. Tre comportamenti, tutti nati da bug osservati in browser, non
progettati a monte (`contexts/AppContext.tsx:92-162`):

1. **L'auto-selezione della prima azienda si ferma** mentre una pratica è attiva
   (`praticaActiveRef`). Senza, il `refreshCompanies()` al mount di `/pratica` disfaceva il
   `setSelectedCompanyId(null)` che la card «Da bilancio» fa apposta: `AnagraficheStep` si apriva
   in modalità EDIT su un'azienda a caso e «Salva e prosegui» la rinominava in silenzio.
2. **La selezione globale segue `pratica.companyId`**, così `/budget` raggiunto dal ponte del
   previsionale elenca gli scenari dell'azienda della pratica e non di quella che `AppContext`
   aveva selezionato prima.
3. **Una pratica che punta a un'azienda cancellata si auto-chiude** (FINDING 5, review finale
   2026-08-08), altrimenti stepper e wizard finiscono in un vicolo cieco su ogni pagina. Con due
   guardie: solo dopo il primo caricamento riuscito (`companiesLoaded`) e solo se l'ultimo
   caricamento **non è fallito** (`lastLoadSucceededRef`) — un errore di rete transitorio lascia
   `companies` stale, e senza la seconda guardia una pratica appena avviata veniva chiusa.

Tutti e tre gli effetti dipendono dallo **scalare** `pratica?.companyId`, mai dall'oggetto
`pratica`: l'oggetto cambia identità a ogni `updatePratica`, quindi un effetto che lo osserva
riparte anche quando il campo che gli interessa non si è mosso.

## 3. Le tre fasi

`lib/pratica-steps.ts` è il modulo **puro** (nessun React) che decide tutto:
`buildPraticaSteps(pratica, gates)` restituisce gli step ordinati del workflow corrente, ciascuno
con una `phase` (`"dati" | "analisi" | "previsionale"`, `PHASE_ORDER`), un `group` (`"azione"` fa
avanzare la pratica, `"vista"` è di sola lettura e si visita in qualsiasi ordine) e un `kind`
(`"tab"` = tab dentro `/pratica`, `"route"` = pagina Next a sé stante). Lo stesso modulo possiede
`praticaGates`, `currentStepId`, `nextStep`/`prevStep`, `phaseStatus`, `gateReason`, `rescueStep`
e `blockedStep`.

Workflow **bilancio**:

| Fase | Step | `kind` | `group` | Abilitato quando |
|---|---|---|---|---|
| DATI | Anagrafiche | tab | azione | sempre |
| DATI | Import | tab | azione | `companyId !== null` |
| DATI | Rettifiche | tab | azione | `gates.imported` |
| ANALISI | Confronto | tab | azione | `imported && rettificheOk` |
| ANALISI | Proiezione | tab | azione | `rettificheOk && comparisonReady` — **lo step non esiste** se `periodMonths === 12` |
| ANALISI | Indicatori | tab | vista | `rettificheOk && comparisonReady` |
| ANALISI | Stampa | tab | vista | `rettificheOk && (annuale ? comparisonReady : projectionReady)` |
| PREVISIONALE | Budget → `/budget` | route | azione | `gates.budgetScenario` |
| PREVISIONALE | Indici → `/analysis` | route | vista | `gates.forecastReady` |
| PREVISIONALE | CE Prev. → `/forecast/income` | route | vista | `gates.forecastReady` |
| PREVISIONALE | SP Prev. → `/forecast/balance` | route | vista | `gates.forecastReady` |
| PREVISIONALE | Riclassificato → `/forecast/reclassified` | route | vista | `gates.forecastReady` |
| PREVISIONALE | Rendiconto → `/cashflow` | route | vista | `gates.forecastReady` |
| PREVISIONALE | Report → `/report` | route | vista | `gates.forecastReady` |

Un bilancio già annuale non si proietta a 12 mesi: per questo la Proiezione **manca dall'elenco**
invece di comparire disabilitata, e la Stampa cambia prerequisito di conseguenza.

Workflow **startup**: nessuna fase ANALISI — non c'è nulla da importare. Un solo step DATI,
«Anagrafiche», che è il form del business plan **su `/budget`** (`kind: "route"`), poi i sette step
PREVISIONALE, con Budget sempre abilitato.

## 4. I gate: chi sblocca cosa, e che cosa il gate non è

`praticaGates(pratica)` è l'**unica** derivazione dei gate, condivisa da stepper e barra azioni:
due derivazioni parallele divergerebbero. Legge solo lo stato persistito —

```
imported        = fiscalYear !== null
rettificheOk    = rettificheConfirmed.verifica && rettificheConfirmed.storico
comparisonReady = infrannualeScenarioId !== null
projectionReady = infrannualeScenarioId !== null
budgetScenario  = budgetScenarioId !== null
forecastReady   = budgetScenarioId !== null
```

`rettificheConfirmed.storico` vale `true` anche quando la scheda storico **non esiste** (import
senza anno di raffronto): è il wizard a scriverlo così.

**Il gate delle rettifiche è in AND su tutti e quattro gli step ANALISI**, non solo sul Confronto.
Una versione precedente ne copriva solo `comparison`: uno scenario già creato all'import
(`infrannualeScenarioId` valorizzato) bastava da solo a sbloccare Proiezione, Indicatori e Stampa
anche a rettifiche non confermate, o dopo un «Ripristina originale». Corretto nel commit `71d3303`.

**Nessuno dei sette step PREVISIONALE lo AND direttamente**: si reggono su
`budgetScenario`/`forecastReady`. Nel percorso nuovo il vincolo tiene comunque, per via transitiva
— `budgetScenarioId` viene valorizzato solo dal ponte verso il budget, raggiungibile solo oltre le
Rettifiche. Ma una pratica **ripresa da uno scenario budget legacy** (`budgetScenarioId`
valorizzato, `infrannualeScenarioId` `null`: la fase ANALISI non è mai stata percorsa) non ha
alcuno stato di rettifiche su cui gattare, e nemmeno un `rettifiche_log` da riaprire. Per quel caso
`isLegacyBudgetResume` (`lib/pratica-steps.ts:208-213`) **restituisce la sola fase PREVISIONALE**
— quindi nasconde ANALISI *e* DATI — invece di renderla abilitata-ma-morta (FINDING 4, review
finale 2026-08-08). Attenzione a non confondere quello stato con una pratica nuova fra Anagrafiche
e Import, che ha anch'essa `infrannualeScenarioId === null` ma `budgetScenarioId === null`: lì i
primi step restano raggiungibili.

### Il gate vale anche in fase di render, ma non è autorizzazione

I rami `activeTab === …` del wizard non consultano i gate, quindi l'invariante dipendeva dal fatto
che **ogni** sito di navigazione se la ricordasse. `blockedStep(pratica, stepId)` la riporta in un
posto solo, e una guardia unica in `app/pratica/page.tsx:1086` avvolge i sette rami.

Due comportamenti deliberati, da non «correggere»:

1. **Uno step sconosciuto non blocca.** `buildPraticaSteps` ne omette apposta in certi workflow
   (startup, resume legacy): bloccare sull'assenza creerebbe vicoli ciechi nuovi.
2. **Si legge la stessa cache che legge lo stepper, senza interrogare il server.** Essere più
   severi produrrebbe falsi blocchi (gli hook `useRettificheYear` caricano solo sulla tab
   Rettifiche, altrove la verità del server non è disponibile). Conseguenza dichiarata: se la cache
   dice «confermato» e il server dice il contrario, **si passa**. Non è un confine di
   autorizzazione, e non chiude alcun exploit noto — nessuna delle review del 2026-08-08 era
   riuscita a costruirne uno. Il guadagno è un altro: l'invariante non dipende più dalla memoria di
   chi aggiunge una navigazione.

`rescueStep` — dove riportare l'utente quando lo step corrente non è raggiungibile — è
condiviso apposta fra `blockedStep` e la barra azioni (FINDING 2, review finale), così le due non
possono proporre due destinazioni diverse per lo stesso step bloccato. Cerca **l'ultima tab
abilitata dell'intero percorso**, non della sola fase: un «Ripristina originale» azzera
`rettificheOk`, che è in AND su tutta la fase ANALISI, e un rescue ristretto alla fase non
troverebbe mai nulla.

## 5. Lo stepper e la barra azioni

**`components/PraticaStepper.tsx`** è reso da `components/Navigation.tsx:52` al posto della nav
piatta ogni volta che `pratica !== null` e il percorso non è `/` — **mai le due barre insieme**;
la home resta la pagina di uscita, e là comanda la nav normale. Due righe:

1. identità della pratica (azienda e periodo), i chip di fase (`PHASE_ORDER`, stato da
   `phaseStatus`, un `Tooltip` con `gateReason` quando la fase è bloccata) e «Esci dalla pratica»;
2. **solo gli step della fase attiva**: prima gli `azione`, un separatore, poi le `vista`. È
   questo che tiene la sotto-barra corta comunque cresca il numero di viste di sola lettura.

Fuori da una pratica la nav piatta è quella di sempre — «Aziende & Pratiche», «Scenari», il menu
«Previsionale» e le tre voci di analisi — **meno la voce Importazione**: `/import` esiste ancora
come rotta, semplicemente non è più linkata.

**`components/pratica/PraticaActionBar.tsx` + `contexts/PraticaActionContext.tsx`** sono il punto
unico di avanzamento. La barra è resa sotto il contenuto della pagina, `sticky` e **non** `fixed`:
resta nel flusso, quindi non copre mai l'ultima riga di una tabella lunga.

Cosa mostra il bottone primario, in ordine di precedenza:

| # | Condizione | Bottone |
|---|---|---|
| 1 | lo step corrente non è (più) raggiungibile | «Torna a `<rescue.label>`», abilitato, col motivo accanto |
| 2 | la pagina ha registrato un'azione | l'azione registrata |
| 3 | esiste uno step successivo | «Avanti: `<next.label>`», disabilitato col `gateReason` se il prossimo è chiuso |
| 4 | si è davvero sull'ultimo step | «Chiudi la pratica» |
| 5 | rotta non mappata da `currentStepId` (es. `/import` dentro una pratica) | nessun primario |

Il caso 5 è deliberato: «Chiudi la pratica» come default accidentale su una rotta ignota sarebbe
un'azione distruttiva non richiesta.

Una pagina registra la propria azione con `usePrimaryAction({ label, onClick, disabled, reason })`.
`label: null` significa «questo step non ha un'azione propria» e la barra ricade sul caso 3.
Due dettagli del meccanismo che sembrano ornamentali e non lo sono: la registrazione è marcata da
un **token `Symbol`** (un cambio pagina può smontare il vecchio step *dopo* che il nuovo si è
registrato, e senza token la cleanup del vecchio cancellerebbe l'azione appena registrata), e
`onClick` vive in un **ref** aggiornato a ogni render invece che nelle dipendenze dell'effetto
(l'handler è una funzione nuova a ogni render: come dipendenza rifarebbe partire la registrazione
a ogni ciclo). Chi registra un `onClick` gestisce i **propri** errori: il `try/catch` +
`.catch()` nel contesto è una rete contro una unhandled rejection muta, non un posto su cui
contare per mostrare un errore all'utente.

Chi registra oggi: le tab Rettifiche / Confronto / Proiezione / Indicatori di `app/pratica/page.tsx`
(un unico `useMemo` con uno `switch` su `activeTab`), `AnagraficheStep`, `StampaContent`, e
`app/budget/page.tsx`. Le altre tab passano `label: null` e usano il fallback.

**Dei sette step PREVISIONALE solo Budget registra un'azione**; gli altri sei sono viste di sola
lettura. Le vecchie CTA inline per-tab sono state rimosse man mano che gli step venivano migrati;
**il pulsante «Salva e Calcola Previsionale» di `/budget` è l'unico sopravvissuto**, perché
`/budget` è raggiungibile anche **fuori** da una pratica (nav piatta, voce «Scenari») dove la barra
non viene resa affatto. Da lì la doppia registrazione:
`label: pratica ? "Salva e Calcola Previsionale" : null` (dentro una pratica comanda la barra) e un
`<Button>` proprio reso solo `{!pratica && …}` (fuori, si salva lo stesso). Il pulsante
«Ricalcola» e il suo dialogo di conferma — con la casella «azzera le modifiche manuali del CE
previsionale» — sono un'azione **secondaria** distinta e sono rimasti dov'erano.

## 6. La riidratazione dopo un refresh

Il progresso del wizard (`importResult`, `scenario`, `fiscalYear`, `periodMonths`) vive in
`useState` locale e **non** sopravvive a un F5; solo il `PraticaContext` (localStorage) sopravvive.
Senza rimedio, dopo il refresh lo stepper mostra uno step avanzato mentre gli auto-load restano
fermi al loro guard `!importResult || !scenario`: pagina bianca, nessun errore.

Un effetto in `app/pratica/page.tsx:359-407` tenta la riidratazione **esattamente una volta**
(guardia con `useRef`, non con soli scalari nel dep-array: un secondo tentativo potrebbe partire
mentre il primo è ancora in corso). Vale per il solo workflow `bilancio`, e solo se
`analysisStep` è oltre Import. Recupera azienda e scenario infrannuale dal server, ripopola i
quattro stati locali, e lascia che gli auto-load esistenti facciano il resto.

Quando il context non ha abbastanza dati (`companyId` o `infrannualeScenarioId` mancanti) o la
fetch fallisce, il ripiego è **onesto**: un `Alert` italiano «Pratica da riaprire» — riparti
dall'importazione o riapri la pratica dalla home — e ritorno allo step Import. Mai un `<main>`
vuoto.

## 7. I moduli, e la regola di dipendenza

`app/pratica/page.tsx` è sceso da 6.019 a ~1.810 righe (2026-08-10). Le funzioni pure stanno in
`lib/`, i componenti in `components/pratica/`:

| Modulo | Che cosa contiene |
|---|---|
| `lib/pratica-steps.ts` | fasi, step, gate, `blockedStep`, `rescueStep` — nessun React |
| `lib/pratica-format.ts` | formattazione |
| `lib/pratica-codes.ts` | tabelle di codici IV-CEE, `DETAIL_PARENTS`, `EXTRA_ALERT_DEFS` |
| `lib/pratica-reconcile.ts` | `reconcileSubfields` |
| `lib/pratica-indicators.ts` | indicatori, scoring, `computeCrisisRating`, `buildIndicatorChartData` |
| `lib/pratica-statement-rows.ts` | costruzione delle righe SP/CE |
| `lib/pratica-rettifiche-rules.ts` | la politica di partita doppia (→ `RETTIFICHE.md`) |
| `lib/pratica-turnover.ts` | `turnoverRatio` / `scaledOrCarried`, gemello lato client del motore infrannuale |

**Regola: `lib/pratica-*` non importa mai da `app/` o da `components/`.** È ciò che rende quei
moduli testabili in `environment: node` e impedisce i cicli di import. L'unica dipendenza verso
l'alto è un `import type` di `PraticaState` da `contexts/PraticaContext` in `pratica-steps.ts`:
un tipo, cancellato in compilazione.

**La decomposizione non è finita, ed è dichiarato.** Quanto estratto finora sono funzioni pure e i
componenti già a foglio (Rettifiche, Confronto, Proiezione, Indicatori, Stampa); il **corpo** del
wizard — stato, effetti di caricamento, i sette rami `activeTab` — vive ancora tutto in
`app/pratica/page.tsx`.

## 8. Quanto le suite proteggono davvero (misurato, non presunto)

`lib/pratica-steps.ts` ha la propria suite, `lib/pratica-steps.test.ts` (**29 casi** oggi; erano 19
quando fu scritta, ed era **la prima suite frontend del progetto** — ora ce ne sono dieci in
`lib/`). Si eseguono con `npm test` (Vitest) da `frontend/`.

Le tre suite di caratterizzazione dei calcoli (`pratica-reconcile.test.ts`,
`pratica-indicators.test.ts`, `pratica-statement-rows.test.ts`) fissano il comportamento
**attuale**, non lo giudicano corretto. Un mutation harness (review finale 2026-08-10) ha misurato
quanto valgono come rete:

- **18% sul totale (11 mutazioni uccise su 61):** la maggioranza delle mutazioni introdotte
  nell'implementazione sopravvive ai test invariata.
- **3/29 per `lib/pratica-indicators.ts`** — quasi non funzionale come rete di regressione. Il test
  di `computeIndicators` scorre 19 campi di `IndicatorSet` con `Number.isFinite(...)`, che nessuna
  mutazione aritmetica (segno scambiato, operando sbagliato, soglia spostata) può violare. Oggi
  cinque di quei campi sono fissati **per valore** (`_ebitda_raw`, `ebitda_margin`, `indipendenza`,
  `roi`, `current_ratio`); gli altri quattordici no.

Due asserzioni deboli sono state corrette in quella review: `scoreDotColor` fissa le stringhe
colore esatte invece di limitarsi a «sono diverse a coppie», e il test di `computeCrisisRating` sui
segnali extracontabili fissa i due codici concreti (A3 → C3) invece di «sono diversi».

**Non leggere questo come «gli indicatori sono coperti».** Rafforzare la suite — valori distinti e
non nulli per ogni codice nominato in ogni array sommato, asserzioni per valore esatto al posto di
`Number.isFinite` — è un follow-up noto e deliberatamente non fatto.

### `sp07_crediti_lungo` mancante da `totalAssets` (corretto il 2026-08-10)

`computeIndicators` escludeva correttamente `sp07_crediti_lungo` (crediti esigibili oltre
l'esercizio successivo) da `currentAssets` — non è attivo circolante — ma **non lo riaggiungeva mai
a `totalAssets`**, disallineandosi da `ATTIVO_CODES` (`lib/pratica-codes.ts`) e da `attivoKeys`
(`lib/pratica-reconcile.ts`), che lo includono entrambi. Su un'azienda con crediti a lungo termine
significativi il totale attivo risultava sottostimato, e quindi `indipendenza` (equity/TA) e `roi`
(EBIT/TA) **sovrastimati** — la direzione sbagliata per uno strumento di rischio creditizio.

Il fix somma `sp07_crediti_lungo` a `totalAssets` e lascia `currentAssets` invariato, con un
commento nel codice che spiega l'asimmetria. La suite esistente non avrebbe intercettato il bug né
una sua reintroduzione: il fixture `BS_SANA` non contiene affatto `sp07_crediti_lungo`. Sono stati
aggiunti due test mirati — `indipendenza` e `roi` per valore esatto su un fixture con `sp07` non
nullo, e un confronto che il `current_ratio` resta invariato in sua presenza (fissa la metà «non va
in `currentAssets`» della regola). Questo corregge **una** omissione; non rende adeguata la suite
degli indicatori nel complesso.

## 9. Storia — perché alcune cose sono come sono

- **«PREVISIONALE ha SEI step, non quattro»** diceva una versione precedente di questa
  documentazione: `/analysis` (Indici) era allora irraggiungibile da dentro una pratica. Sono
  sette, e quella lacuna è chiusa.
- **Il gate delle rettifiche copriva il solo Confronto** fino al commit `71d3303` (§4).
- **Il dialogo Riepilogo aveva una porta propria.** `handleConfirmRettifiche` è oggi l'**unico**
  percorso che porta al Confronto: lo chiamano sia il primario della barra («Conferma e vai al
  Confronto») sia il bottone del dialogo Riepilogo (`onNext`). Prima il secondo raggiungeva il
  Confronto per una strada separata che scavalcava il gate del tutto (review del Task 7, finding
  critico). Le due sotto-tab (Storico e Bilancio di verifica) vogliono **ciascuna** la propria
  conferma: `useRettificheYear` espone `confirmed` e `confirm()`, appoggiati a un marker
  `{ entry_type: "confirm" }` nello stesso `rettifiche_log` — nessuna migrazione, idempotente,
  escluso dal giornale, dal Riepilogo e dal tetto di 20 voci lato server.
- **I due comportamenti di `AppContext` (§2) sono stati trovati provando in browser**, non
  progettati: sono bug reali, non raffinamenti.
- **Lo spostamento a `/pratica` fu neutro.** Il wizard si è mosso file-per-file da
  `/infrannuale`, senza cambiamenti di comportamento *in quel movimento*; tutto ciò che è descritto
  qui è venuto dopo.

## 10. File chiave

| File | Che cosa contiene |
|---|---|
| `frontend/contexts/PraticaContext.tsx` | lo stato della pratica e la sua persistenza |
| `frontend/lib/pratica-steps.ts` | fasi, step, gate, `blockedStep`, `rescueStep`, `gateReason` |
| `frontend/lib/pratica-steps.test.ts` | 29 casi; l'unica suite che copre i gate |
| `frontend/components/PraticaStepper.tsx` | le due righe dello stepper |
| `frontend/components/Navigation.tsx` | sceglie fra stepper e nav piatta |
| `frontend/contexts/PraticaActionContext.tsx` | `usePrimaryAction`, il registro a token |
| `frontend/components/pratica/PraticaActionBar.tsx` | la barra unica di avanzamento |
| `frontend/app/pratica/page.tsx` | il wizard: stato, auto-load, riidratazione, i sette rami `activeTab` |
| `frontend/app/page.tsx` | le due card «Nuova pratica», `startForCompany`, `resume` |
| `frontend/app/budget/page.tsx` | il doppio ingresso: dentro e fuori da una pratica |
| `frontend/app/layout.tsx` | l'ordine dei provider (`PraticaProvider` sopra `AppProvider`) |
