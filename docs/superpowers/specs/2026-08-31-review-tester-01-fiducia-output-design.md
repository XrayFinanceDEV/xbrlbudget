# Review tester — Lotto 1: fiducia nell'output

**Data:** 2026-08-31
**Stato:** Design approvato (intervista di grilling del 31/08, tutte le decisioni chiuse)
**Area:** frontend. `app/pratica/page.tsx`, `components/pratica/StampaContent.tsx`,
`app/forecast/balance/page.tsx`, `contexts/AppContext.tsx`, `app/page.tsx`. **Nessuna
modifica a DB, motori di calcolo o endpoint.**
**Origine:** `inbox/eccezioni1.md`, review del tester + 3 mockup + 2 PDF di prova.
**Serie:** 01 di 04. Ordine di esecuzione: **01 → 02 → 03 → 04**.

## Problema

Il tester ha consegnato 17 osservazioni su infrannuale e budget. Tre di esse — più una quarta
emersa dall'intervista — non sono richieste di funzioni: sono punti in cui **il prodotto
sembra rotto**. Vanno per prime perché finché ci sono, ogni altra aggiunta si legge sopra un
output di cui il cliente non si fida.

### 1.1 «Ha squadrato (attivo – passivo = 1 €)»

Riprodotto nel codice, causa certa.

`calculateProjectedBS` (`app/pratica/page.tsx:716`) calcola il plug di cassa in piena
precisione: `sp09 = totalLiabilities - totalAssetNoCash` (`:797`), quindi in aritmetica esatta
Attivo = Passivo. Subito dopo però **ogni riga viene arrotondata da sola**:

```
annualized_value: Math.round(projValues[item.code] ?? partialVal(item.code))   // :820
```

e `buildBalanceItemsWithTotals` (`lib/pratica-statement-rows.ts:6`) costruisce i totali
sommando i valori **già arrotondati** (`sumCodes`, `:67`). Attivo e Passivo accumulano
diciotto errori di arrotondamento indipendenti: la differenza cade fra −1 € e +1 €.

**Il backend fa già la cosa giusta.** `ForecastEngine._normalize_balance_sheet_cents`
(`calculations/forecast_engine.py:83`) arrotonda le righe e **poi ricalcola la cassa dagli
aggregati arrotondati**, ed è chiamato anche dal motore infrannuale
(`calculations/intra_year_engine.py:576`). Il `ForecastYear` salvato quadra al centesimo.

Quindi il difetto **non è un dato sbagliato**: è lo schermo che mostra un bilancio diverso da
quello persistito. È la stessa classe di guasto che CLAUDE.md già presidia per il guard sui
turnover («lo schermo e il record persistito raccontano due bilanci diversi»), qui su un
percorso che nessuno aveva ancora coperto.

### 1.2 «Ogni tanto nella stampa taglia a metà le tabelle o i grafici»

`components/pratica/StampaContent.tsx` non contiene **una sola** regola `break-inside` o
`break-before` — verificato per grep sull'intero file. I suoi blocchi sono `<div>` e `<Table>`
nudi.

`/report` invece è protetto: `app/globals.css:204` dichiara `.report-section { break-inside:
avoid }`, e ogni blocco del report è avvolto in quella classe (`app/report/page.tsx:196` e
seguenti). La Stampa dell'infrannuale non usa quella classe e non ne ha una propria.

L'unica protezione che oggi la raggiunge è `tr { break-inside: avoid }` (globals.css, dentro
`@media print`): salva la singola riga, **non** la tabella né la card che la contiene. Vale la
regola già scritta in CLAUDE.md: «`globals.css` protegge `.recharts-wrapper`, non la card
attorno».

### 1.3 «Non ci sono punti e virgole tra le centinaia e le migliaia»

Su **SP Previsionale** ogni cella modificabile è un `<input type="number">` permanente
(`app/forecast/balance/page.tsx:654`): mostra `1247893`, sempre, anche quando non la stai
scrivendo. Il browser non ammette separatori dentro un `type="number"`.

Su **CE Previsionale** il comportamento è già quello giusto: a riposo la cella mostra
`formatCurrency(displayValue)` (`app/forecast/income/page.tsx:522`), e diventa grezza solo
mentre la scrivi (`startEdit`, `:456`). Le due pagine gemelle si comportano in modo diverso.

### 1.4 «Nell'area iniziale “azienda e pratiche” non compaiono aziende»

In intervista il tester ha precisato: **appaiono, ma non subito — a volte serve ricaricare la
pagina.** Questo esclude la lettura «manca il selettore» e indica una corsa. Trovata:

`AppContext` aspetta l'autenticazione prima di caricare
(`contexts/AppContext.tsx:121-125`, più la guardia `authLoadingRef` in `loadCompanies`,
`:92-93`). **La home no**: `app/page.tsx:89` definisce un `load` proprio, `useCallback(…, [])`,
lanciato al mount da `useEffect` (`:101-102`) senza guardare `authLoading`.

Dentro l'iframe il token arriva per `postMessage` con una finestra fino a **5 secondi**
(`contexts/AuthContext.tsx`, `isInIframe ? 5000 : 1000`). La chiamata della home parte senza
`Authorization`; l'interceptor chiede un token nuovo al parent (`lib/api.ts:43`) — ma **niente
rilancia il `load()` della home**. La lista resta vuota finché non ricarichi e vinci la corsa.

Aggravante: l'errore muore in un `console.error` (`app/page.tsx:95`) e la pagina mostra
«Nessuna azienda presente. Crea la prima azienda o avvia una nuova pratica» (`:319`) — cioè
**invita** a creare il duplicato che il tester ha creato.

Sweep sulle altre otto pagine con `useEffect`: tutte pescano da `selectedCompanyId`, che viene
da `AppContext` ed è già protetto. **La home è l'unica scoperta.**

## Decisioni prese

| # | Decisione | Perché |
|---|---|---|
| D1 | L'€1 si chiude arrotondando **prima** tutte le voci tranne il plug, e ricavando il plug come **residuo dei valori arrotondati** | È la stessa strategia che il backend applica già in `_normalize_balance_sheet_cents`: schermo e record convergono per costruzione, non per fortuna |
| D2 | La verifica della stampa si fa **generando il PDF**, prima e dopo, su un bilancio vero | `emulateMedia` dà le misure giuste ma non impagina: non mostra mai un salto sbagliato (CLAUDE.md, «Technical Constraints») |
| D3 | Il file di prova del tester si importa **a due vie** — parser deterministico del progetto **e** pass LLM — e i due esiti si confrontano, prima di toccare la proiezione | Un €1 su dati di partenza sbagliati sarebbe la diagnosi giusta sul difetto sbagliato |
| D4 | Separatori: **formattato a riposo, grezzo in modifica** (opzione b) | Allinea SP Prev. al comportamento che CE Prev. ha già; risolve il problema vero, che è *leggere* i numeri |
| D5 | La corsa si chiude in modo **strutturale**: `AppContext` diventa l'unica fonte dell'elenco aziende e include **sempre** gli scenari; la home smette di avere un fetch proprio | Un gate minimo sulla home avrebbe lasciato in piedi due percorsi di caricamento, cioè la condizione che ha prodotto la corsa |

## Interventi

### I1 — Plug di cassa come residuo degli arrotondati

`app/pratica/page.tsx`, dentro `calculateProjectedBS` (`:716`-`:824`).

Oggi l'ordine è: calcola in float → plug esatto → arrotonda tutto. Va invertito sul plug:

1. arrotondare tutte le voci **tranne** `sp09_disponibilita_liquide` (e `sp16_debiti_breve`
   quando assorbe il plug negativo);
2. ricalcolare `totalAssetNoCash` e `totalLiabilities` **sui valori arrotondati**;
3. `sp09` = differenza fra i due totali arrotondati — quindi intero per costruzione;
4. se `sp09 < 0`, azzerarlo e sommarne il valore assoluto a `sp16` **già arrotondato**, così
   anche il ramo negativo chiude a zero.

Il ramo negativo va coperto esplicitamente: oggi (`:799-802`) `sp16` viene aumentato **prima**
dell'arrotondamento, quindi l'errore si sposta ma non sparisce.

**Attenzione (regressione possibile):** `sp16` alimenta il grafico dei margini e gli indicatori
di liquidità. Spostare l'assorbimento del plug dopo l'arrotondamento cambia `sp16` di al massimo
1 €: irrilevante nei numeri, ma va verificato che nessun test congelato lo inchiodi al valore
attuale.

**Nota di confine.** Questo intervento tocca **solo l'anteprima**. Non va replicato lato
backend: là il problema non esiste, e `_normalize_balance_sheet_cents` è già la fonte autorevole.

### I2 — Regole di salto pagina per la Stampa infrannuale

`components/pratica/StampaContent.tsx` + `app/globals.css`.

Introdurre una classe dedicata — **non** riusare `.report-section`, che appartiene a `/report`
e ne condivide il ciclo di vita — e applicarla a ciascun blocco autonomo della Stampa: le
quattro tabelle di prospetto (CE e SP, confronto e proiezione), il blocco indicatori, la card
dei grafici, la legenda.

Regole minime, dentro `@media print`:
- `break-inside: avoid` sul blocco;
- `break-after: avoid` sull'intestazione, perché un titolo non resti orfano in fondo alla pagina;
- sulle tabelle lunghe, dove `break-inside: avoid` costringerebbe a saltare pagine quasi vuote,
  vale invece `thead { display: table-header-group }` così l'intestazione si ripete sulla pagina
  successiva.

**Quali blocchi vadano protetti e quali spezzati si decide guardando il PDF**, non a tavolino:
una tabella di 40 righe protetta con `break-inside: avoid` produce una pagina bianca. È per
questo che D2 impone il PDF prima/dopo.

### I3 — Separatori su SP Previsionale

`app/forecast/balance/page.tsx:654`.

Portare la cella al modello già in uso su `app/forecast/income/page.tsx`: a riposo uno `<span>`
(o un input di sola lettura) con `formatCurrency`, in modifica un input grezzo, con commit su
`blur` e su `Enter` ed escape su `Escape`.

Il parsing esiste già ed è riusabile: `app/forecast/income/page.tsx:476` toglie punti e spazi e
converte la virgola decimale. **Non riscriverlo**: estrarlo, o duplicarlo esattamente. Due
parser di numeri italiani che divergono sono un modo silenzioso di scrivere un importo diverso
da quello digitato.

Conservare il comportamento attuale su cui il resto della pagina conta: campo svuotato =
rimozione dell'override (oggi `raw === "" ? null : Number(raw)`), non zero. È la differenza fra
«torna al valore calcolato» e «forza a zero», e `sp_overrides` **clampa a zero i negativi e
ignora in silenzio le chiavi sconosciute** (CLAUDE.md): un errore qui non dà errore, dà uno zero.

### I4 — Una sola fonte per l'elenco aziende

`contexts/AppContext.tsx` + `app/page.tsx`.

1. `loadCompanies` (`contexts/AppContext.tsx:92`) chiama `getCompaniesWithScenarios()` invece di
   `getCompanies()`. Il tipo si allarga da `Company[]` a `CompanyWithScenarios[]`, che
   **estende** `Company` (`types/api.ts:26`): i 13 altri consumatori non cambiano di una riga.
2. Il costo è nullo: il backend serve `?include=scenarios` con un `joinedload` in **una sola
   query** (`backend/app/api/v1/companies.py:39-62`), e il tetto è 50 aziende per utente.
3. `app/page.tsx` elimina il proprio `load`/`useEffect` (`:89`, `:101-102`) e legge
   `companies` dal context. La guardia `authLoadingRef` di `loadCompanies` (`:92-93`) copre
   allora anche la home, e la corsa non può ripresentarsi.
4. **Stato di errore onesto:** quando l'ultimo caricamento è fallito
   (`lastLoadSucceededRef === false`, già tracciato in `AppContext`), la home mostra l'errore e
   un «Riprova» — **mai** «Nessuna azienda presente» (`:319`). Quel messaggio resta solo per il
   caso vero: caricamento riuscito, zero aziende.

**Attenzione all'auto-selezione.** `loadCompanies` contiene una regola non ovvia (`:104-111`):
se non c'è selezione e non c'è una pratica attiva, seleziona `companies[0]`. Il commento spiega
che la guardia `praticaActiveRef` esiste perché senza di essa un `refreshCompanies()` disfaceva
il `setSelectedCompanyId(null)` che la home esegue prima di avviare una pratica nuova. **Quella
logica non va toccata in questo lotto**: la home che smette di fare fetch proprio non la
riguarda, ma il rifacimento della home (spec 04) sì.

## Verifica

**Premessa — import a due vie (D3).** Il file `inbox/Bilancio di verifica al 30.06.2026.pdf` va
importato con il percorso deterministico del progetto **e** con il pass LLM, e i due esiti
confrontati fra loro e con i totali stampati sul documento. Se divergono, si ferma tutto e si
apre un lotto a parte: la proiezione non si giudica su una base incerta.
→ `docs/import/REGOLE-IMPORT-02-ESTRAZIONE.md`, `docs/FIXING-IMPORT.md`

Poi, su quella pratica:

| # | Che cosa | Come si prova |
|---|---|---|
| V1 | L'€1 è chiuso | «Calcola proiezione SP»: Totale Attivo − Totale Passivo = **0** esatto, letto a schermo. Ripetere con un caso a plug negativo (cassa proiettata sotto zero → assorbita in `sp16`) |
| V2 | Schermo e record coincidono | Dopo il salvataggio, i valori di `/analysis` e quelli dell'anteprima Proiezione coincidono voce per voce |
| V3 | La stampa non taglia | **PDF generato**, prima e dopo, allegato al commit. Nessuna tabella e nessun grafico spezzato; nessuna pagina quasi vuota introdotta dal fix |
| V4 | Separatori | Su SP Prev. i valori si leggono `1.247.893` a riposo; cliccando si scrive grezzo; svuotando il campo l'override sparisce e torna il calcolato |
| V5 | Nessuna corsa | Nell'iframe, a freddo (cache pulita): la home mostra le aziende **al primo caricamento**, senza F5. Con backend spento: messaggio d'errore e «Riprova», **mai** «Nessuna azienda presente» |
| V6 | Nessuna regressione | `cd frontend && npm test` verde |

## Che cosa questo lotto NON fa

- Non riorganizza la home (spec 04) — qui cambia solo **da dove arrivano i dati**, non come
  sono disposti.
- Non tocca il motore infrannuale né il previsionale: il `ForecastYear` salvato era ed è
  corretto.
- Non aggiunge indicatori, grafici o card (spec 03).
- Non tocca le ipotesi del budget: la riprogettazione è **outstanding** per decisione del 31/08.
