# Report finale della pratica

**Data:** 2026-09-13

**Stato:** proposta pronta per revisione

**Area:** report, pratica infrannuale, budget, commenti AI

**Milestone:** M1 — report finale web e contratto dati

**Spec collegata:** [Report PDF con Typst](2026-09-13-report-pdf-typst-design.md)

## 1. Obiettivo

Trasformare `/report` nel documento conclusivo dell'intera pratica, non nella sola
visualizzazione dei risultati del budget.

Il report deve permettere a chi legge di ricostruire, nello stesso ordine logico:

1. da quali dati contabili è partita la pratica;
2. quali rettifiche sono state apportate;
3. come è stata costruita la chiusura di fine anno, quando la pratica parte da un
   infrannuale;
4. quali ipotesi alimentano il previsionale;
5. quali risultati economici, patrimoniali e finanziari ne derivano;
6. quali rischi, anomalie e punti da verificare rimangono aperti.

Il risultato di questo milestone è una pagina web leggibile e commentabile e,
soprattutto, un modello dati canonico e versionato. Lo stesso modello sarà l'unica
fonte ammessa per il successivo PDF Typst.

## 2. Problema attuale

La pagina `/report` oggi è un buon report analitico del budget: mostra bilanci,
cash flow, indicatori, composizioni, margini, scoring, break-even e commenti AI.
Non racconta però l'intera pratica.

Le informazioni necessarie esistono, ma sono distribuite:

- il log delle rettifiche è nel bilancio storico;
- la proiezione dell'infrannuale e i relativi commenti sono nello step `Stampa`
  della pratica;
- le ipotesi sono persistite sullo scenario budget e ora sono divise in sette
  sezioni;
- risultati e indicatori arrivano dal servizio di analisi;
- gli alert extra-contabili dell'infrannuale sono ancora stato locale del client;
- i commenti del report budget e quelli dell'infrannuale hanno contratti e regole
  di freschezza differenti.

La conseguenza è che il lettore vede i risultati, ma non la catena decisionale che
li ha prodotti. Inoltre un eventuale renderer PDF sarebbe costretto a ricostruire
la pratica da più endpoint, con il rischio di divergere dalla pagina web.

`docs/budget/FINAL-REPORT-PDF.md` rimane una utile analisi del report storico di
circa quaranta pagine, ma non è il contratto funzionale di questo milestone.

## 3. Principi di progetto

### 3.1 Un solo modello, due renderer

Il backend costruisce un `FinalReportModel` completo. React e, nel milestone M2,
Typst si limitano a rappresentarlo.

Nei renderer non sono ammesse:

- formule finanziarie;
- ricostruzioni della catena degli scenari;
- classificazioni autonome delle rettifiche o delle ipotesi;
- regole diverse di freschezza o pubblicabilità.

### 3.2 Il report racconta una pratica, non un singolo scenario

Lo scenario budget rimane la chiave di ingresso, ma il backend deve risalire alla
sua origine e costruire il percorso effettivo. Sono supportati tre casi:

| Percorso | Contenuto specifico |
|---|---|
| infrannuale → chiusura → budget | rettifiche, proiezione a fine anno e budget |
| bilancio annuale → budget | rettifiche e budget; nessuna sezione infrannuale |
| startup → budget | dati iniziali e budget; nessuna falsa rettifica storica |

Le sezioni non applicabili sono omesse, non mostrate vuote.

### 3.3 Anteprima viva e documento finale sono stati distinti

La pagina web è sempre consultabile e riflette lo stato corrente. Quando le fonti
sono incomplete o non allineate, mostra chiaramente `BOZZA` e le cause.

La pubblicazione del PDF finale, definita in M2, usa invece uno snapshot immutabile
del modello e rispetta un gate di prontezza. Il report web deve già esporre lo
stesso gate e spiegare ciò che blocca la finalizzazione.

### 3.4 I commenti aiutano la lettura, non certificano i numeri

I commenti possono essere generati dall'AI e poi modificati dall'utente. Devono
essere riconoscibili, aggiornabili e marcati come obsoleti quando cambiano i dati
che li alimentano. I numeri e i controlli deterministici rimangono la fonte
autorevole.

## 4. Prerequisito: collegamento esplicito della catena

`BudgetScenario` possiede già `source_scenario_id` e `workflow_type`, ma il flusso
di promozione corrente non li valorizza in modo affidabile. Prima di assemblare il
report occorre completare questa persistenza.

Quando una chiusura infrannuale viene promossa a budget:

- `source_scenario_id` identifica lo scenario che ha prodotto la chiusura;
- il `FinancialYear` annuale creato dalla promozione registra
  `promoted_from_scenario_id`, così il dato contabile e il budget dichiarano la
  stessa provenienza anche dopo una nuova promozione;
- `workflow_type` registra il percorso con i valori già esposti dal contratto
  (`infrannuale`, `bilancio` o `startup`);
- il legame è restituito dalle API di scenario;
- l'operazione è idempotente: ripetere la promozione non crea catene concorrenti.

La provenienza è decisa dal backend, non accettata come autorità dal client. La
creazione di un budget deriva workflow e sorgente dal `FinancialYear` di base: la
promozione vi scrive lo scenario sorgente, mentre il percorso startup marca e
valida esplicitamente l'anno di apertura. Un valore arbitrario inviato dal client
non può collegare scenari appartenenti a pratiche o aziende diverse.

Per gli scenari legacy senza collegamento, l'assembler può applicare un fallback
deterministico e conservativo basato su azienda, anno base e metadati disponibili.
Il fallback deve produrre un warning `legacy_chain_inferred` e non deve modificare
silenziosamente il database.

Se esistono più origini compatibili, il report rimane consultabile ma non è
finalizzabile finché il collegamento non viene risolto.

Gli alert extra-contabili che oggi vivono soltanto nello stato React della pratica
devono essere persistiti nello scenario sorgente oppure in un'entità esplicitamente
collegata. Nessun dato esclusivamente client-side può far parte del report finale.

## 5. Contratto API

### 5.1 Endpoint

```http
GET /api/v1/companies/{company_id}/scenarios/{budget_scenario_id}/final-report
```

L'endpoint:

- richiede autenticazione e verifica l'appartenenza sia dello scenario budget sia
  delle sue fonti all'azienda e all'utente;
- restituisce il modello già assemblato, senza chiamate aggiuntive necessarie al
  rendering;
- non modifica dati e non genera commenti AI;
- usa un `response_model` esplicito;
- restituisce `404` per una risorsa non accessibile, evitando di rivelarne
  l'esistenza;
- restituisce `409` solo quando la catena è intrinsecamente ambigua e il modello
  non può essere costruito. Dati incompleti ma rappresentabili producono invece
  un report `draft` con diagnostica.

### 5.2 Versionamento

Il payload contiene `schema_version`, inizialmente `1`. Le modifiche additive
mantengono la versione; rimozioni o cambi semantici richiedono una nuova versione.

Il frontend deve rifiutare esplicitamente una versione maggiore di quella
supportata, invece di renderizzare parzialmente un documento sconosciuto.

### 5.3 Struttura del `FinalReportModel`

Il nome definitivo delle classi Pydantic può seguire le convenzioni del progetto,
ma il contratto deve coprire questi blocchi:

```text
FinalReportModel
├── schema_version, generated_at, model_hash
├── company
├── practice
│   ├── workflow_type
│   ├── budget_scenario
│   ├── source_scenario
│   └── periods
├── source_revisions
├── readiness
├── source_data_quality
├── adjustments
├── infrannual_closing?          # solo percorso infrannuale
├── assumption_sections
├── forecast
│   ├── income_statements
│   ├── balance_sheets
│   ├── cashflows
│   └── calculations
├── diagnostics
├── chart_series
└── narrative
```

`model_hash` è l'hash stabile del contenuto economico e narrativo, con esclusione
dei campi volatili come `generated_at`. Serve per freschezza, audit e futura
generazione del PDF.

### 5.4 Revisioni delle fonti

`source_revisions` rende osservabile da cosa deriva il documento. Include almeno:

- identificativo e revisione del bilancio storico;
- revisione del log rettifiche;
- identificativo e revisione dello scenario infrannuale, se presente;
- data di aggiornamento delle ipotesi budget;
- data di aggiornamento del forecast persistito;
- revisione dei commenti;
- versione del motore o del contratto di calcolo, se disponibile.

L'implementazione può partire dai timestamp esistenti, ma non deve inventare una
precisione che il database non possiede. Dove la revisione non è disponibile il
campo è `null` e viene emesso un warning diagnostico.

## 6. Contenuto editoriale

### 6.1 Ordine delle sezioni

Il report usa questo indice stabile:

1. **Copertina e perimetro** — azienda, scenario, periodo storico, orizzonte di
   previsione, data e stato del documento.
2. **Sintesi esecutiva** — risultati principali, messaggi chiave, rischi e punti
   che richiedono decisione.
3. **Origine e qualità dei dati** — percorso della pratica, fonti, completezza,
   warning e stato dei controlli.
4. **Rettifiche apportate** — effetto delle rettifiche sui valori di partenza.
5. **Dall'infrannuale alla chiusura** — solo per il percorso infrannuale: confronto
   tra progressivo, proiezione e chiusura attesa.
6. **Ipotesi del budget** — driver per sezione e anno, con origine dell'ipotesi.
7. **Conto economico previsionale** — evoluzione di ricavi, margini e risultato.
8. **Stato patrimoniale previsionale** — struttura degli impieghi e delle fonti.
9. **Flussi di cassa e sostenibilità finanziaria** — generazione/assorbimento di
   cassa, debito, PFN e coperture.
10. **Indicatori e rischi** — indicatori economici, finanziari e di crisi.
11. **Diagnostica e punti da verificare** — errori bloccanti, warning e segnali
    extra-contabili.
12. **Appendici e metodologia** — prospetti completi, matrice completa delle
    ipotesi, definizioni e note.

Le sezioni hanno identificatori tecnici stabili, separati dalle etichette italiane,
per non rompere commenti, ancore e template quando cambia un titolo.

### 6.2 Rettifiche

La sezione mostra soltanto eventi economici effettivi. Le voci del log con
`entry_type == "confirm"` attestano lo stato del processo ma non sono sommate alle
rettifiche.

Per ogni rettifica vengono esposti:

- voce modificata e contropartita;
- delta con segno contabile coerente;
- motivazione;
- data;
- effetto netto sui principali aggregati, calcolato dal backend.

La sezione termina con una riconciliazione `prima → rettifiche → dopo`. Le righe
complete restano in appendice; il corpo evidenzia soltanto gli aggregati materiali.

### 6.3 Chiusura infrannuale

Quando applicabile, la sezione confronta:

- valore progressivo alla data infrannuale;
- eventuale valore comparabile;
- proiezione automatica a fine esercizio;
- override dell'utente;
- valore finale usato come base del budget.

Deve essere sempre distinguibile ciò che è osservato da ciò che è stimato. Gli
alert extra-contabili persistiti e i commenti approvati completano il quadro, ma
non modificano autonomamente i calcoli.

### 6.4 Ipotesi del budget

Le ipotesi seguono esattamente le sette sezioni del wizard:

1. scenario;
2. fatturato;
3. costi;
4. altre voci di conto economico;
5. circolante;
6. pregresso e nuovo;
7. imposte.

Nel corpo del report compaiono i driver attivi e materiali, anno per anno. La
matrice completa è in appendice. Ogni valore dichiara la propria origine:

- `user`: inserito direttamente;
- `automatic`: derivato da una regola documentata;
- `default`: valore proposto e non modificato;
- `override`: sostituzione esplicita di un valore calcolato;
- `ignored`: presente nel payload ma non usato nel percorso corrente.
- `legacy_unknown`: record precedente al tracciamento della provenienza, per il
  quale non è possibile distinguere in modo affidabile input utente e default.

Per i nuovi salvataggi, il backend persiste per ogni anno l'elenco dei campi
forniti esplicitamente. Non è ammesso dedurre `user` o `default` confrontando il
valore col default: un utente può aver confermato intenzionalmente proprio quel
valore. `legacy_unknown` produce una diagnostica non bloccante.

Prestiti, debiti pregressi e differenze temporanee sono tabelle nidificate, non
campi serializzati in testo. I campi classificati come `DEAD_FIELDS` dal wizard
non devono essere presentati come driver attivi. La classificazione ha una fonte
autorevole lato backend e un test di parità col wizard, invece di due liste
indipendenti. Il campo legacy `investments` richiede un trattamento specifico:
non è un driver attivo, ma può bloccare la generazione se valorizzato senza gli
split e deve quindi comparire in diagnostica.

### 6.5 Grafici

Il corpo usa pochi grafici orientati alle decisioni. La prima versione comprende:

1. ricavi, EBITDA e risultato netto;
2. EBITDA margin ed EBIT margin;
3. flussi operativi, di investimento e finanziari con cassa finale;
4. cassa, debito finanziario e PFN;
5. DSO, DIO e DPO;
6. DSCR e indicatori di copertura disponibili.

Ogni grafico ha:

- titolo descrittivo;
- unità e periodo;
- legenda non affidata soltanto al colore;
- dati tabellari accessibili;
- un commento associato alla sezione, non generato nel componente grafico.

`chart_series` contiene valori, categorie, unità e formattazione semantica. React e
Typst possono avere una resa visiva diversa, ma devono consumare le stesse serie.

## 7. Narrazione e commenti

I commenti oggi separati tra report budget e stampa infrannuale confluiscono in
blocchi narrativi con identificatori stabili:

| ID | Contenuto |
|---|---|
| `executive_summary` | quadro complessivo e conclusioni |
| `adjustments_and_closing` | rettifiche e, se presente, chiusura infrannuale |
| `budget_assumptions` | ipotesi principali e loro sensibilità |
| `economic_outlook` | ricavi, margini e risultato |
| `financial_outlook` | patrimonio, cassa, debito e sostenibilità |
| `risks_and_actions` | criticità, verifiche e azioni suggerite |

Ogni blocco contiene testo, provenienza (`ai`, `user`, `migrated`), data di
aggiornamento, hash delle fonti e stato di freschezza.

La generazione AI:

- è un'azione esplicita e separata dal `GET` del report;
- riceve dal backend un contesto derivato dal `FinalReportModel`, non un payload
  ricomposto dal browser;
- non viene eseguita durante la stampa o la generazione PDF;
- non sovrascrive senza conferma un testo modificato dall'utente;
- conserva il testo precedente quando diventa obsoleto e mostra il motivo.

I commenti legacy sono migrati o letti in compatibilità quando la corrispondenza è
univoca. Testi non mappabili non vengono concatenati automaticamente: restano
recuperabili per una revisione manuale.

## 8. Stato, diagnostica e gate di finalizzazione

`readiness` contiene uno stato complessivo (`ready`, `draft`, `blocked`) e una
lista strutturata di motivi con codice, severità, sezione e messaggio leggibile.

Bloccano il documento finale almeno:

- forecast marcato come obsoleto;
- anni richiesti mancanti o forecast non persistito;
- catena della pratica assente o ambigua quando necessaria;
- rettifiche obbligatorie non confermate;
- mancata quadratura o violazioni dei controlli contabili bloccanti;
- fonti appartenenti ad aziende diverse;
- versione del modello non supportata.

Rimangono warning non bloccanti, salvo diversa regola già presente nel dominio:

- commenti AI obsoleti o mancanti;
- ipotesi rimaste ai default;
- segnali extra-contabili;
- indicatori fuori soglia;
- revisione di una fonte non disponibile per dati legacy.

La pagina non usa solo il colore: mostra sempre icona, etichetta e spiegazione.

## 9. Interfaccia `/report`

La pagina corrente viene evoluta, non duplicata. Il selettore continua a scegliere
lo scenario budget e il caricamento passa al nuovo endpoint.

Comportamenti richiesti:

- indice laterale o iniziale con ancore alle sezioni;
- banner persistente per `BOZZA` o `BLOCCATO`;
- sintesi leggibile a schermo prima dei prospetti completi;
- apertura progressiva delle appendici;
- tabelle ampie utilizzabili su desktop e stampabili senza dipendere dallo scroll;
- stati loading, errore, scenario non collegato e nessun dato espliciti;
- azione “Rigenera commenti” distinta da “Esporta PDF”;
- nessuna chiamata AI automatica al caricamento;
- la stampa browser esistente può restare temporaneamente come anteprima, ma non
  è il formato PDF ufficiale del prodotto.

I componenti analitici esistenti vengono riusati quando accettano dati già
preparati. Quelli che oggi incorporano calcoli o accedono direttamente a hook/API
devono essere separati in presentazione pura e adapter.

## 10. Implementazione backend

Introdurre un servizio assembler dedicato, responsabile di:

1. autorizzare e caricare lo scenario budget;
2. risolvere la catena della pratica;
3. acquisire rettifiche e chiusura infrannuale;
4. acquisire ipotesi e forecast persistito;
5. riusare i risultati canonici del servizio di analisi;
6. classificare ipotesi e diagnostica;
7. costruire le serie dei grafici;
8. calcolare revisioni, freschezza, readiness e `model_hash`;
9. allegare la narrazione persistita senza generarne di nuova.

Il servizio non deve replicare le formule di `analysis_service`, del motore di
forecast o dei controlli di quadratura. Quando una trasformazione serve a entrambi
i report, va estratta in una funzione di dominio condivisa e testata.

## 11. Verifica

### 11.1 Test backend

- schema e serializzazione del modello versione 1;
- autorizzazione e isolamento tra aziende;
- risoluzione dei tre percorsi supportati;
- fallback legacy univoco e caso ambiguo;
- promozione idempotente con persistenza dei collegamenti;
- esclusione degli eventi `confirm` dai totali delle rettifiche;
- riconciliazione prima/rettifiche/dopo;
- classificazione completa delle sette sezioni di ipotesi, senza duplicati;
- assenza dei `DEAD_FIELDS` tra i driver attivi;
- parità dei valori con servizio di analisi, forecast persistito e API rettifiche;
- readiness per forecast obsoleto, anni mancanti e controlli contabili;
- hash stabile a contenuto invariato e diverso dopo una modifica materiale;
- freschezza e protezione dei commenti modificati dall'utente.

I fixture devono coprire almeno un caso infrannuale, uno annuale e uno startup,
includendo valori nulli, negativi e anni multipli.

### 11.2 Test frontend

- rendering condizionale delle sezioni per ciascun percorso;
- banner e motivi di blocco;
- matrice ipotesi e tabelle nidificate;
- presenza dei dati tabellari per ogni grafico;
- modifica e rigenerazione controllata dei commenti;
- gestione di schema non supportato e catena legacy ambigua;
- navigazione per ancore e layout responsive;
- typecheck e build di produzione.

Un collaudo browser verifica l'intero percorso: promozione infrannuale, apertura del
report, modifica di un'ipotesi, comparsa dello stato obsoleto, rigenerazione del
forecast e ritorno a `ready`.

## 12. Piano di consegna

### Lotto A — identità e contratto

- completare la persistenza di `source_scenario_id` e `workflow_type`;
- persistere gli alert extra-contabili;
- definire schemi Pydantic e tipi TypeScript del modello v1;
- aggiungere fixture dei tre percorsi.

### Lotto B — assembler

- implementare catena, rettifiche, chiusura, ipotesi e analisi;
- aggiungere revisioni, diagnostica, readiness e hash;
- esporre l'endpoint autenticato.

### Lotto C — report web

- riorganizzare `/report` secondo il nuovo indice;
- adattare i componenti esistenti al modello canonico;
- aggiungere origine dati, rettifiche, chiusura e ipotesi.

### Lotto D — narrazione

- introdurre i sei blocchi stabili;
- migrare in sicurezza i commenti esistenti;
- generare il contesto AI dal modello canonico;
- mostrare provenienza e freschezza.

### Lotto E — collaudo e documentazione

- completare test automatici e collaudo browser;
- documentare endpoint, codici diagnostici e regole di readiness;
- aggiornare la documentazione utente del percorso pratica/report.

## 13. Criteri di accettazione

Il milestone è completato quando:

1. partendo da uno scenario budget, un singolo endpoint restituisce l'intera
   pratica autorizzata e versionata;
2. i tre percorsi previsti producono un report coerente, senza sezioni fittizie;
3. rettifiche, chiusura infrannuale e sette sezioni di ipotesi sono riconciliabili
   con le rispettive fonti;
4. numeri e serie dei grafici coincidono con i servizi canonici esistenti;
5. `/report` distingue chiaramente bozza, blocco e documento pronto;
6. i commenti hanno provenienza e freschezza verificabili e non vengono
   sovrascritti automaticamente;
7. il modello può essere serializzato e consegnato a un renderer senza ulteriori
   query o calcoli finanziari;
8. test automatici e collaudo dei tre percorsi sono verdi.

## 14. Fuori perimetro

- modifiche alle formule del motore previsionale;
- nuovo motore PDF o impaginazione Typst, coperti da M2;
- editor libero del layout del report;
- internazionalizzazione generale dell'applicazione;
- ricostruzione automatica e distruttiva dei collegamenti legacy;
- analisi di sensitività o simulazioni non già presenti nei dati;
- certificazione legale o contabile del documento.

## 15. Decisioni da confermare prima dell'implementazione

La spec propone come default:

- sei blocchi narrativi unificati invece dei commenti frammentati attuali;
- blocco del PDF finale con forecast obsoleto o controlli contabili falliti;
- warning, non blocco, per commenti mancanti o obsoleti;
- fallback legacy solo in lettura e sempre dichiarato;
- persistenza degli alert extra-contabili come prerequisito.

Eventuali variazioni a queste cinque decisioni cambiano il contratto del modello e
devono essere risolte prima del Lotto B.
