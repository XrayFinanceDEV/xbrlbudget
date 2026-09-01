# Review tester — Lotto 2: navigazione e scopribilità

**Data:** 2026-08-31
**Stato:** Design approvato, **con una decisione aperta** (§D6, da confermare prima di
implementare I4)
**Area:** frontend. `components/pratica/PraticaActionBar.tsx`,
`contexts/PraticaActionContext.tsx`, `app/pratica/page.tsx`, `app/budget/page.tsx`,
`components/pratica/StampaContent.tsx`. **Nessuna modifica a DB, motori o endpoint.**
**Origine:** `inbox/eccezioni1.md`.
**Serie:** 02 di 04. Da eseguire **dopo** la 01.

## Problema

Quattro osservazioni del tester dicono la stessa cosa da quattro punti diversi: **le cose che
si possono fare non si vedono**. Una di esse riguarda una funzione che esiste da mesi e che il
tester ha chiesto come se mancasse — il caso peggiore, perché costa una riga di review e un
giro di chiarimenti per qualcosa di già costruito.

### 2.1 «C'è solo il bottone piccolo in basso a destra, è poco intuitivo»

Il primario del percorso vive in `PraticaActionBar` (`components/pratica/PraticaActionBar.tsx`),
una barra `sticky bottom-0`. La scelta di `sticky` (e non `fixed`) è deliberata e documentata
nel file: resta nel flusso, quindi non copre mai l'ultima riga delle tabelle lunghe.

Il problema non è la barra: è che a **primo impatto**, in cima a una pagina, non c'è nulla che
dica come si va avanti. Parole del tester: «perché i clienti così non lo vedono».

### 2.2 «Non è intuitivo vedere che si possono cliccare i due anni in maniera separata»

`app/pratica/page.tsx:1419-1427`: due `TabsTrigger` piatti, «Rettifiche Storico {anno−1}» e
«Rettifiche Bil. di verifica {anno}». Non portano **alcuno stato**: guardandoli non si capisce
né che sono due lavori distinti, né quale dei due è già stato confermato — benché lo stato
esista già nel context (`pratica.rettificheConfirmed.storico` / `.verifica`, letto da
`praticaGates` in `lib/pratica-steps.ts:63-65`).

Ed entrambe **vanno confermate** per proseguire: `rettificheOk` è un AND sui due campi. Un
utente che ne conferma una sola resta bloccato senza vedere perché.

### 2.3 «Deve essere prevista la possibilità di indicare i singoli finanziamenti che compongono il debito esistente verso le banche»

**La funzione esiste già ed è completa.** Verificato:

- la UI accetta un residuo iniziale per contratto — `FinancingLoansGrid`
  (`frontend/app/budget/page.tsx:1324`), campo `opening_residual`, abilitato solo sul primo
  anno di piano;
- il motore, quando almeno un residuo è valorizzato, **sostituisce** il piano forfettario
  `existing_debt_repayment_years` con lo scadenzario dettagliato
  (`calculations/forecast_engine.py:420-429`, flag `use_detailed_existing_schedule`);
- ogni contratto porta durata, tasso, preammortamento e quota balloon propri.

Due cose l'hanno resa invisibile:

1. **Il titolo dice il contrario.** «Finanziamenti aggiuntivi» si legge come «nuovi
   finanziamenti», che è esattamente ciò che il tester ha creduto fosse l'unica possibilità.
2. **Il vincolo è tutto-o-niente e non è dichiarato in UI.** Se la somma dei residui iniziali
   non pareggia il debito bancario dell'anno base **al centesimo**, il backend solleva
   `"The sum of financing opening residuals must equal base-year bank debt"`
   (`calculations/forecast_engine.py:424-428`). Il debito di riferimento è calcolato da
   `base_bank_debt` (`calculations/projection_common.py:47`), che **assegna alle banche anche
   gli scarti positivi fra aggregato e dettagli** di `sp16`/`sp17` — quindi non è un numero che
   l'utente possa ricostruire a mente guardando il bilancio.

### 2.4 «La frase è scritta troppo piccola»

`app/budget/page.tsx:1248`: `<p className="text-xs text-muted-foreground">` per l'unico
rimando al CE Previsionale, che è il posto dove si modificano le singole voci in valore
assoluto. Il tester lo definisce «ottimo, ma scritto troppo piccolo» — cioè: la funzione più
utile della pagina è annunciata col carattere più piccolo della pagina.

## Decisioni prese

| # | Decisione | Perché |
|---|---|---|
| D1 | Il primario si **duplica** in alto a destra; la barra in fondo resta invariata | «Non lo vedono» è un problema di primo impatto; ma dopo una tabella lunga il bottone in fondo è quello che serve. Toglierlo risolve una lamentela creandone la simmetrica |
| D2 | La logica del primario si estrae in un **hook**, resa due volte | `PraticaActionBar` è oggi l'unico punto che conosce gate, rescue e motivi del blocco. Due copie di quelle regole divergerebbero, ed è la classe di difetto che il catalogo IV-CEE ha appena finito di eliminare per le etichette |
| D3 | Le due tab Rettifiche portano uno **stato visibile** «da confermare / confermata» | L'informazione esiste già nel context: manca solo di essere mostrata |
| D4 | La card diventa **«Finanziamenti — esistenti e nuovi»**, con il debito bancario dell'anno base e il residuo ancora da coprire mostrati **live** | La funzione c'è: quello che manca è dire che c'è, e dire quando la somma non torna **prima** che il backend risponda con un errore |
| D5 | La frase sul CE Previsionale si ingrandisce e si stacca dal fondo pagina | Un rimando è utile quanto è visibile |
| **D6** | **APERTA** — dove vive «Prosegui al Budget» | vedi sotto |

### D6 — decisione aperta

Il tester scrive: «non ha senso che per passare al budget bisogna per forza stampare
l'infrannuale e fare i commenti AI». **Ha ragione a metà, e la metà giusta conta.**

I commenti AI **non** sono obbligatori: sono un bottone separato in cima alla Stampa. Ma
l'azione «Prosegui al Budget» — quella che esegue il promote e crea lo scenario budget — è
registrata **solo** dentro `StampaContent` (`components/pratica/StampaContent.tsx:336`,
`usePrimaryAction`). Non esiste altra strada la prima volta: `buildPraticaSteps` abilita lo
step `budget` solo con `gates.budgetScenario`, cioè solo quando quello scenario esiste già
(`lib/pratica-steps.ts:69`, `:116`).

**Raccomandazione:** rendere l'azione disponibile anche dallo step **Indicatori**, lasciandola
dov'è sulla Stampa. Non spostarla: la Stampa resta il posto naturale per chi segue il percorso
per intero.

**Perché serve un tuo assenso esplicito prima di toccarla.** `promote` è **distruttivo**:
cancella il `FinancialYear` annuale già esistente per quell'azienda e quell'anno, con SP e CE
in cascata, anche se era stato importato a mano (CLAUDE.md, «Invarianti › Previsionale»). La
cancellazione sta nella stessa transazione della copia, quindi un fallimento la annulla — ma un
promote riuscito no. Rendere quell'azione raggiungibile da un secondo punto significa renderla
raggiungibile **prima** che l'utente abbia visto l'output: è una scelta di prodotto, non un fix.

## Interventi

### I1 — Primario duplicato in alto

`components/pratica/PraticaActionBar.tsx` → estrarre in `usePraticaPrimaryAction()` tutto il
blocco che oggi calcola `label` / `disabled` / `reason` / `run` (`:47-105`), **senza cambiarne
una regola**: rescue, azione registrata, avanzamento, chiusura pratica, rotta non mappata.

`PraticaActionBar` diventa un consumatore dell'hook. Il secondo consumatore è
l'intestazione del wizard (`app/pratica/page.tsx`) e delle rotte PREVISIONALE, che rende lo
stesso primario in taglia grande, allineato a destra.

Vincoli da rispettare:
- il ramo **rescue** rende il bottone *abilitato* con un `reason` non nullo: la condizione che
  oggi decide se mostrare il motivo non è `disabled && reason` (commento a `:117-119`), e va
  portata identica anche in alto;
- quando `label` è `null` (rotta non riconosciuta, es. `/import` dentro una pratica) **nessuno
  dei due punti** mostra un primario;
- `print:hidden` sul duplicato, come sulla barra.

### I2 — Stato sulle tab Rettifiche

`app/pratica/page.tsx:1419-1427`. Su ciascun `TabsTrigger`, accanto all'etichetta, un indicatore
dello stato letto da `pratica.rettificheConfirmed`: confermata (spunta) / da confermare.

Le due tab restano abilitate secondo la regola attuale (`storico` è disabilitata quando
`!storico.exists`, cioè import senza anno di raffronto). **Non trasformare l'indicatore in un
gate**: `praticaGates` scrive `rettificheOk` con `storico` a `true` anche quando la scheda
storico non esiste — è il wizard a scriverlo così di proposito (`lib/pratica-steps.ts:63-65`).
Una spunta calcolata in modo indipendente da quel campo direbbe il falso su quel caso.

Aggiungere sopra le tab una riga che dichiara quante schede restano da confermare, così il
motivo del blocco è leggibile senza arrivare in fondo alla pagina.

### I3 — «Finanziamenti — esistenti e nuovi»

`app/budget/page.tsx:1324` (`FinancingLoansGrid`).

1. **Titolo e testo.** «Finanziamenti — esistenti e nuovi». Il sottotitolo spiega le due
   colonne: *residuo iniziale* = quota di debito bancario **già in essere** all'anno base
   (ammesso solo nel primo anno); *nuova erogazione* = finanziamento acceso in quell'anno.
2. **Debito da coprire, live.** Sopra le righe: il debito bancario dell'anno base, la somma dei
   residui inseriti e la differenza. Il numero di riferimento **deve essere lo stesso** che
   userà il motore: `base_bank_debt` (`calculations/projection_common.py:47`), che include gli
   scarti aggregato/dettagli. Ricalcolarlo lato client con una formula «ovvia» (solo `sp16a` +
   `sp17a`) darebbe un numero diverso da quello contro cui il backend valida, e l'utente
   vedrebbe «coperto» un piano che il server rifiuta.
   → esporlo dall'API o replicarne **esattamente** la formula, dichiarando nel codice quale
   delle due si è scelta e perché.
3. **Avviso prima dell'errore.** Finché la differenza non è zero, un avviso non bloccante:
   «i residui non coprono il debito bancario dell'anno base — il previsionale verrà rifiutato».
   Non bloccare l'input: si compila una riga alla volta, e a metà compilazione lo scarto è
   normale.
4. **Coerenza con la riga forfettaria.** `ESSENTIAL_ROWS` contiene ancora «Rimborso debiti
   bancari (anni)» (`components/budget/assumption-rows.ts`, chiave `rimborso-banche`), che il
   motore **ignora** non appena esiste un residuo dettagliato. Va detto in UI, altrimenti
   restano due comandi visibili per la stessa cosa e uno dei due non fa nulla, in silenzio.

### I4 — «Prosegui al Budget» anche da Indicatori — *subordinato a D6*

Da implementare **solo dopo conferma esplicita**. L'azione è già incapsulata in `handlePromote`
(`components/pratica/StampaContent.tsx:305-357`), quindi tecnicamente si tratta di registrarla
come primario anche sullo step `results`. Il riuso dello scenario esistente c'è già
(`:323-333`: doppio click o ritorno sui propri passi non generano due scenari).

Se confermata, aggiungere una conferma esplicita che nomini la conseguenza distruttiva quando
esiste già un `FinancialYear` annuale per quell'anno.

### I5 — Frase sul CE Previsionale

`app/budget/page.tsx:1248`. Da `text-xs text-muted-foreground` a un blocco riconoscibile:
testo a taglia piena, un riquadro leggero, e il link reso come tale. Il contenuto non cambia.

## Verifica

| # | Che cosa | Come si prova |
|---|---|---|
| V1 | Il primario è coerente nei due punti | Su ogni step del percorso, alto e basso mostrano **la stessa** etichetta e lo stesso stato. Provare i tre rami: avanzamento normale, azione registrata (es. «Salva e prosegui» di Anagrafiche), rescue dopo un «Ripristina originale» |
| V2 | Nessun primario dove non deve esserci | Su `/import` dentro una pratica: nessun bottone, né sopra né sotto |
| V3 | Le tab dicono lo stato | Confermando una sola delle due schede, la tab confermata lo mostra e la riga sopra dichiara che ne resta una |
| V4 | Import senza anno di raffronto | La tab storico resta disabilitata e **non** appare «da confermare»: il percorso prosegue |
| V5 | Finanziamenti | Con un residuo che non pareggia: avviso in UI **prima** di salvare. Pareggiando al centesimo: il previsionale si genera e lo scadenzario dettagliato sostituisce il rimborso forfettario |
| V6 | Il numero di riferimento è quello del motore | Su un bilancio abbreviato (dettagli a zero, scarto tutto nell'aggregato) il debito mostrato coincide con quello contro cui il backend valida |
| V7 | Nessuna regressione | `cd frontend && npm test` verde — in particolare `lib/pratica-steps.test.ts` |

## Che cosa questo lotto NON fa

- Non rifà la home (spec 04).
- **Non aggiunge il selettore azienda in Anagrafiche**: era previsto qui, ma la decisione del
  31/08 sull'ingresso a tendina lo rende superfluo — l'azienda si sceglie sempre prima di
  entrare nel percorso. Il pezzo si sposta, e sparisce, nella spec 04.
- Non tocca la struttura delle ipotesi budget (economiche/patrimoniali, fisso/variabile,
  dual-write): **outstanding** per decisione del 31/08.
- Non implementa I4 senza il tuo assenso su D6.
