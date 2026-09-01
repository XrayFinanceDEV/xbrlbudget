# Review tester — Lotto 4: home e ingresso nel percorso

**Data:** 2026-08-31
**Stato:** Design approvato, **con una decisione aperta** (§D5, da confermare prima di
implementare)
**Area:** frontend. `app/page.tsx`, `components/pratica/AnagraficheStep.tsx`,
`contexts/PraticaContext.tsx`. **Nessuna modifica a DB, motori o endpoint.**
**Origine:** `inbox/eccezioni1.md` + intervista del 31/08.
**Serie:** 04 di 04, **ultimo**. Dipende dalla 01: la home non ha più un fetch proprio.

## Problema

Il tester ha scritto: «nell'area iniziale *azienda e pratiche* non compaiono aziende, devo
creare una nuova azienda per andare a lavorare su una azienda esistente».

Metà di quella frase è un bug di caricamento, ed è chiusa nella **spec 01** (corsa fra il fetch
della home e l'arrivo del token). L'altra metà resta, ed è di forma: **la home offre cinque modi
di iniziare, quasi tutti equivalenti**, e il tester ne ha imboccato uno che porta a creare un
duplicato.

Oggi (`app/page.tsx`) le azioni visibili sono:

| dove | azione | riga |
|---|---|---|
| intestazione | «Nuova azienda» | `:219` |
| intestazione | «Nuova pratica» → due card, Da bilancio / Startup | `:222` |
| card azienda | «Nuova pratica» per **quella** azienda | `:178` (`startForCompany`) |
| card azienda | modifica anagrafica in linea | `:131`, `:138` |
| card azienda | elimina azienda | `:157` |
| riga pratica | «Riprendi» | `:196` (`resume`) |

Il difetto non è che siano troppe: è che tre di esse (**Nuova azienda**, **Nuova pratica**
globale, **Nuova pratica** per azienda) aprono percorsi quasi identici e il risultato dipende da
quale hai scelto. La «Nuova pratica» globale entra in Anagrafiche con `companyId: null`, e
`AnagraficheStep` in quel ramo è un form di **sola creazione** (documentato a `:34`: «Non è un
elenco aziende — la scelta è già avvenuta sulla home»). Chi entra da lì **non può** scegliere
un'azienda esistente: può solo crearne una.

## Decisioni prese

| # | Decisione | Perché |
|---|---|---|
| D1 | La home diventa un **elenco di pratiche raggruppate per azienda**, a tendina: si clicca l'azienda, si aprono le sue pratiche, si sceglie quella o se ne crea una nuova | È la forma che il proprietario ha chiesto: l'azienda resta il raggruppamento, ma l'oggetto che si sceglie è la **pratica** |
| D2 | Tendina sulla home, **non** una pagina in più | Una pagina intermedia sarebbe un indice che rimanda a un indice |
| D3 | «Nuova azienda» la crea **ed entra subito** nella sua prima pratica | Nessuno crea un'azienda per guardarla; è già il comportamento del form Anagrafiche in creazione, cambia solo il punto d'ingresso |
| D4 | Rinomina ed elimina restano, dietro un menù discreto (⋯) sulla riga dell'azienda; **le aziende senza pratiche compaiono come gruppo vuoto** | Non sono modi di *iniziare un lavoro*, sono manutenzione: dietro un ⋯ non competono con «Riprendi» e «Nuova pratica». Vedi §Il vincolo delle 50 |
| D5 | **APERTA** — dove si sceglie fra pratica *da bilancio* e *startup* | vedi sotto |
| D6 | **Il selettore azienda in Anagrafiche non si fa** | Con la tendina l'azienda è sempre scelta prima di entrare: il form non deve più offrirla. Era previsto nella spec 02, cade qui |

### Il vincolo delle 50

`deleteCompany` è chiamata da **un solo punto in tutta l'app**: `app/page.tsx:157`. Non esiste
altra strada per eliminare un'azienda — verificato per grep sull'intero frontend.

`MAX_COMPANIES_PER_USER` vale 50 e `check_company_limit` lo fa rispettare lato server
(`backend/app/core/ownership.py`). Se la home perde l'eliminazione, un utente che crea
un'azienda per errore non ha più modo di toglierla, e le cinquanta caselle si riempiono senza
uscita.

Si somma un secondo effetto, meno evidente: un elenco costruito **sulle pratiche** non mostra
un'azienda che non ne ha. Quell'azienda diventerebbe **insieme invisibile e ineliminabile**, pur
occupando una casella. È il motivo per cui D4 impone i gruppi vuoti: un'azienda senza pratiche
si vede, e da lì la si può eliminare o farle la prima pratica.

### D5 — decisione aperta

Il percorso ha **due workflow**: `bilancio` (import di un bilancio) e `startup` (business plan
senza storico), oggi scelti dalle due card che compaiono sotto «Nuova pratica» (`:247-270`).
Non sono la stessa cosa: `startup` porta su `/budget` in `startupMode`, salta l'intera fase
ANALISI e usa un form diverso (`lib/pratica-steps.ts:183-195`).

«Non devono esserci altre opzioni» si può leggere come «via anche questa scelta». Ma la scelta
**è la pratica**, non un modo alternativo di arrivarci: sopprimerla significherebbe indovinare
il workflow al posto dell'utente.

**Raccomandazione:** «Nuova pratica» sotto un'azienda chiede il tipo con una scelta a due voci,
inline nella tendina — non due card a tutta larghezza come oggi. Resta una sola azione visibile
(«Nuova pratica»); il tipo è un attributo che si sceglie dopo averla chiesta.

## Interventi

### I1 — La home a tendina

`app/page.tsx`, riscrittura della sezione elenco (`:312-424`).

Struttura per ciascuna azienda:
- **riga chiusa**: nome, settore, P.IVA, quante pratiche, e il menù ⋯ (Rinomina, Elimina);
- **aperta**: una riga per pratica — stato (bozza / in corso), nome, tipo e anno base,
  «Riprendi» — e in coda **«Nuova pratica»**;
- **gruppo senza pratiche**: la riga si apre su un solo «Nuova pratica».

In intestazione resta **«Nuova azienda»**, che crea ed entra (D3).

Spariscono: la card «Nuova pratica» globale con le due card sotto (`:228-270`) e il bottone
«Nuova pratica» duplicato dentro la card azienda (`:363-365`).

L'elenco arriva da `AppContext` — dopo la spec 01 è l'unica fonte e include già gli scenari.
La home **non deve** reintrodurre un fetch proprio: è quello che ha causato la corsa.

### I2 — Manutenzione dietro il ⋯

**Rinomina** riusa la modifica in linea che già esiste (`:131`, `:138`,
`handleStartEdit`/`handleSaveEdit`), invocata dal menù invece che da un'icona sempre visibile.

**Elimina** riusa `handleDelete` (`:157`) e **conserva il dialogo di conferma attuale**, che
nomina la conseguenza per esteso: «Eliminare X e tutti i dati associati (bilanci, scenari,
previsioni)?». Quel testo non va abbreviato: la cancellazione è in cascata su tutto ciò che
sta sotto l'azienda (`cascade="all, delete-orphan"` su ogni relazione).

### I3 — Ingresso nel percorso

Tre punti d'ingresso, tutti con l'azienda **già decisa**:

| da | che cosa fa |
|---|---|
| «Riprendi» su una pratica | invariato: `resume` (`:196`) |
| «Nuova pratica» sotto un'azienda | `startForCompany` (`:178`) — già esiste e già passa il `companyId` |
| «Nuova azienda» | crea, poi entra come `startForCompany` sull'azienda appena creata |

**Non toccare la sequenza che `resume` implementa** (`:196-217`): distingue scenario
infrannuale e budget, e apre `/pratica` o `/budget` di conseguenza. Il commento sopra spiega il
caso legacy — uno scenario budget senza `infrannualeScenarioId` non ha una fase ANALISI
ricostruibile, e lo stepper la nasconde del tutto invece di mostrarla abilitata-ma-rotta.

### I4 — L'auto-selezione che non va disfatta

`AppContext.loadCompanies` contiene una regola non ovvia (`contexts/AppContext.tsx:104-111`):
se non c'è selezione e **non c'è una pratica attiva**, seleziona `companies[0]`. La guardia
`praticaActiveRef` esiste perché senza di essa un `refreshCompanies()` disfaceva il
`setSelectedCompanyId(null)` che la home esegue prima di avviare una pratica nuova — e
`AnagraficheStep` si apriva in modalità **modifica** su un'azienda a caso, che «Salva e
prosegui» poi rinominava in silenzio.

Nel nuovo ingresso l'azienda è sempre nota, quindi `setSelectedCompanyId(null)` non serve più
in nessuno dei tre percorsi. **Il caso resta però da provare** (V4): la regola di
auto-selezione è ancora lì, e una home che chiama `refreshCompanies()` al momento sbagliato la
riattiva.

### I5 — Anagrafiche resta com'è

Nessuna modifica a `components/pratica/AnagraficheStep.tsx`. Continua a distinguere creazione e
modifica da `pratica.companyId`, e la semina difensiva (`seededId`, che impedisce di salvare
prima che i dati siano atterrati e che azzerava il settore Altman/FGPMI) resta identica.

## Verifica

| # | Che cosa | Come si prova |
|---|---|---|
| V1 | Un solo modo di iniziare | Dalla home si arriva al percorso **solo** con Riprendi, Nuova pratica sotto un'azienda, Nuova azienda. Nessun altro bottone apre il wizard |
| V2 | Le aziende senza pratiche esistono | Creata un'azienda e abbandonata: compare come gruppo vuoto, e da lì si elimina |
| V3 | Il tetto non intrappola | Con 50 aziende, l'eliminazione è raggiungibile in due click da qualunque gruppo, vuoto compreso |
| V4 | Nessuna rinomina silenziosa | Aprendo una pratica **nuova** su un'azienda esistente, il form Anagrafiche mostra **quella** azienda; salvando non se ne rinomina un'altra. È la regressione che `praticaActiveRef` presidia |
| V5 | Riprendi invariato | Uno scenario infrannuale riapre `/pratica` su Rettifiche; uno budget legacy apre `/budget` con la fase ANALISI nascosta |
| V6 | Nessuna corsa reintrodotta | Nell'iframe a freddo: le aziende compaiono al primo caricamento, senza F5 (regressione della spec 01) |
| V7 | Nessuna regressione | `cd frontend && npm test` verde |

## Che cosa questo lotto NON fa

- Non tocca i gate del percorso (`lib/pratica-steps.ts`): che cosa sia raggiungibile e quando
  non cambia.
- Non aggiunge il selettore azienda in Anagrafiche (D6): la tendina lo rende superfluo.
- Non implementa D5 senza conferma.
- Non tocca le ipotesi budget: **outstanding**.
