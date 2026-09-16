# Report PDF server-side con Typst

**Data:** 2026-09-13

**Stato:** requisiti editoriali consolidati il 2026-09-15; gate tecnico Typst invariato

**Area:** report, export, infrastruttura backend

**Milestone:** M2 — PDF ufficiale stampabile

**Dipendenze:** [Report finale della pratica](2026-09-13-report-finale-pratica-design.md) · [Dossier Report Budget](2026-09-15-report-budget-dossier-design.md)

## 1. Obiettivo

Generare dal backend un PDF professionale, riproducibile e stampabile del report
finale, senza browser headless, Playwright o Chromium.

Typst è il candidato principale perché offre impaginazione editoriale, tabelle,
grafica vettoriale e compilazione diretta in PDF. L'adozione definitiva è però
subordinata a uno spike misurabile: questa spec definisce sia la prova sia
l'architettura da realizzare se il gate viene superato.

## 2. Relazione con il milestone M1

M2 non ricostruisce la pratica e non introduce un secondo modello di report.
Consuma il `FinalReportModel` versionato definito da M1, esteso al v2 per il
dossier prima del template di produzione. Le fixture v1 dello spike restano
valide come regressione tecnica, ma non esauriscono i requisiti editoriali v2.

```text
fonti della pratica
        │
        ▼
FinalReportAssembler ───────► FinalReportModel v2
                                  │            │
                                  ▼            ▼
                            React /report   Typst → PDF
```

Il PDF può avere una composizione grafica diversa dalla pagina web, ma valori,
sezioni, diagnostica, commenti e serie devono provenire dallo stesso snapshot.

M2 può iniziare con lo spike e con il prototipo del template, ma l'endpoint di
produzione non viene completato prima che il contratto M1 sia stabile.

## 3. Perché non riusare la stampa browser

Il progetto dispone di `window.print()` e di uno script opzionale basato su
Playwright. Sono utili per sviluppo e anteprima, ma non offrono un artefatto
server-side controllato senza dipendenze da browser.

Il PDF ufficiale richiede:

- stessa resa in ogni ambiente;
- controllo di font, margini, salti pagina, intestazioni e numerazione;
- generazione autenticata dal backend;
- metadati e hash collegati allo snapshot;
- assenza di Chromium nell'immagine di produzione;
- esecuzione offline e dipendenze bloccate a versioni note.

L'export HTML di Typst non è un'alternativa alla pagina React: la documentazione
ufficiale lo dichiara ancora sperimentale e incompleto. Typst viene quindi usato
esclusivamente come renderer PDF.

Riferimenti tecnici:

- [PDF in Typst](https://typst.app/docs/reference/pdf/)
- [HTML in Typst](https://typst.app/docs/reference/html/)
- [SVG in Typst](https://typst.app/docs/reference/svg/)

## 4. Gate 0: spike tecnico

Prima di integrare il compilatore nel backend va prodotto un prototipo usa-e-getta
ma ripetibile. Lo spike confronta:

1. primitive native Typst con un piccolo layer grafico interno;
2. [CeTZ-Plot](https://typst.app/universe/package/cetz-plot/);
3. [Primaviz](https://typst.app/universe/package/primaviz).

La preferenza iniziale dello spike è mantenere in casa i sei grafici M1 necessari
e usare CeTZ-Plot se riduce davvero il codice. Primaviz va adottato solo se la prova
ne conferma stabilità, compatibilità e facilità di distribuzione offline; la sua
maggiore ampiezza funzionale non è di per sé un requisito.

### 4.1 Fixture dello spike

Il prototipo deve compilare almeno:

- report a uno, tre e cinque anni;
- numeri negativi, zeri, null e serie parziali;
- etichette italiane lunghe e ragioni sociali lunghe;
- molte rettifiche su più pagine;
- tabelle con più prestiti, scadenziamenti e differenze temporanee;
- percorso infrannuale completo;
- percorso annuale senza sezione infrannuale;
- startup con storico minimo;
- commenti brevi, lunghi e assenti.

### 4.2 Misure

Per ogni alternativa si registrano:

- fedeltà semantica dei sei grafici M1;
- leggibilità in scala di grigi e stampa A4;
- comportamento di tabelle e salti pagina;
- tempo di compilazione a caldo e a freddo;
- picco di memoria e dimensione del PDF;
- disponibilità offline delle dipendenze;
- versione minima di Typst e compatibilità tra pacchetti;
- licenza e manutenzione del pacchetto;
- testo estraibile dal PDF;
- supporto pratico per PDF/A e metadati;
- qualità degli errori prodotti dal compilatore.

### 4.3 Esito del gate

Typst viene adottato se:

- tutte le fixture generano PDF validi e leggibili;
- nessun grafico richiede rasterizzazione per essere corretto;
- la compilazione rientra nei limiti operativi concordati;
- font e pacchetti possono essere distribuiti offline e con versioni fissate;
- il testo dei prospetti è estraibile;
- i salti pagina non richiedono correzioni manuali per il singolo cliente.

Se il gate fallisce, lo spike documenta i difetti e si rivaluta il renderer. Non si
introduce silenziosamente Playwright come fallback di produzione.

## 5. Architettura

### 5.1 Flusso di generazione

1. l'utente richiede l'esportazione di uno scenario;
2. il backend autentica utente, azienda e scenario;
3. il `FinalReportAssembler` costruisce il modello corrente;
4. il gate di readiness decide se è possibile produrre un documento finale;
5. il backend congela JSON, hash e revisioni delle fonti;
6. il renderer crea una directory temporanea controllata;
7. il template Typst interno legge il JSON validato;
8. il processo `typst compile` produce il PDF;
9. il backend verifica il file e lo restituisce;
10. la directory temporanea viene eliminata anche in caso di errore.

Il renderer non accede al database, non chiama l'AI e non contiene formule di
bilancio.

### 5.2 Componenti

```text
FinalReportPdfService
├── FinalReportAssembler       # definito in M1
├── SnapshotSerializer         # JSON canonico + hash
├── TypstRenderer              # processo, timeout, errori
├── TemplateBundle             # template, font, asset, pacchetti fissati
└── PdfValidator               # firma, dimensione, pagine, metadati minimi
```

`TypstRenderer` è dietro un'interfaccia piccola, così i test possono usare un fake
e un futuro cambio di renderer non tocca il dominio del report.

### 5.3 Distribuzione del compilatore

Il binario Typst non è attualmente installato nell'ambiente di sviluppo del
repository. Va aggiunto all'immagine backend con versione e checksum fissati.

Requisiti di packaging:

- stessa versione in sviluppo, CI e produzione;
- immagine finale senza toolchain non necessaria;
- font distribuiti legalmente e inclusi nell'immagine;
- pacchetti Typst vendorizzati o cache precompilata e verificata;
- compilazione possibile con rete disabilitata;
- comando di health check che verifichi versione del compilatore e presenza degli
  asset, senza generare report reali.

Non è ammesso scaricare pacchetti o font durante una richiesta utente.

## 6. Contratto HTTP

### 6.1 Generazione sincrona iniziale

```http
POST /api/v1/companies/{company_id}/scenarios/{budget_scenario_id}/final-report/pdf
Content-Type: application/json

{
  "document_state": "final",
  "pdf_profile": "standard"
}
```

Per il primo rilascio la risposta è sincrona e restituisce `application/pdf` con
`Content-Disposition: attachment`. Una coda asincrona viene introdotta solo se le
misure reali mostrano che durata o concorrenza non sono compatibili con una normale
richiesta HTTP.

Header di risposta utili:

- `ETag`: hash dell'artefatto PDF;
- `X-Report-Model-Hash`: hash dello snapshot sorgente;
- `X-Report-Schema-Version`: versione del modello.

I nomi degli header possono essere adeguati alle convenzioni del progetto, ma i tre
dati devono rimanere osservabili.

### 6.2 Bozza e finale

`document_state` accetta:

- `draft`: può essere generato anche con warning o blocchi rappresentabili e porta
  watermark `BOZZA` su ogni pagina;
- `final`: richiede `readiness.status == "ready"`; in caso contrario risponde `409`
  con i codici strutturati dei blocchi e non produce un PDF.

La UI offre per default “Scarica PDF finale” quando il report è pronto e “Scarica
bozza” negli altri casi. Nessuna delle due azioni rigenera il forecast o i commenti.

### 6.3 Errori

| Stato | Caso |
|---|---|
| `404` | azienda/scenario non accessibile |
| `409` | richiesta finale con readiness non pronta |
| `422` | profilo o opzioni non supportate |
| `503` | renderer non installato o temporaneamente saturo |
| `504` | timeout di compilazione |
| `500` | errore interno di template o validazione del PDF |

Gli errori di compilazione sono tradotti in categorie stabili. La risposta non
espone path locali, sorgente Typst o dati finanziari.

## 7. Snapshot e riproducibilità

La generazione usa una copia immutabile del `FinalReportModel`, identificata da:

- `schema_version`;
- `model_hash`;
- `generated_at` del documento;
- revisioni delle fonti;
- versione del template;
- versione del compilatore;
- versione dei pacchetti grafici;
- profilo PDF richiesto.

Nel primo rilascio è obbligatorio persistere almeno i metadati dell'artefatto e il
suo hash. La conservazione del file o dell'intero JSON è una decisione di prodotto
e retention da chiudere prima del Lotto D. Se il file non viene conservato, la UI
deve parlare di “rigenerazione” e non di download dello stesso documento.

Due compilazioni dello stesso snapshot dovrebbero avere contenuto equivalente. Se
timestamp o identificativi interni impediscono l'uguaglianza byte-per-byte, i test
distinguono hash dello snapshot, hash del PDF e equivalenza del contenuto estratto.

## 8. Template editoriale

### 8.1 Struttura

Il template segue esattamente l'indice definito in M1 e include:

- copertina con titolo neutrale `Report Budget {inizio} - {fine}`;
- stato `BOZZA` o `FINALE`;
- indice;
- titoli numerati;
- intestazione con azienda e scenario;
- piè di pagina con data, hash abbreviato e numero pagina;
- corpo narrativo;
- grafici vettoriali;
- tabelle sintetiche;
- sezione Allegati con prospetti completi e metodologia;
- una nota breve pertinente su ogni pagina, anche sulle continuazioni.

Le sezioni opzionali sono decise dal modello, non da query o logica finanziaria nel
template.

### 8.2 Regole tipografiche

- formato A4 verticale; orizzontale solo per appendici che non restano leggibili;
- margini adatti a stampa e rilegatura;
- font incorporati e numeri tabellari;
- intestazioni di tabella ripetute a ogni pagina;
- una riga logica non viene spezzata se può passare intera alla pagina successiva;
- titoli non restano isolati a fondo pagina;
- importi allineati, con unità esplicita e formato italiano coerente;
- valori negativi e nulli sono semanticamente distinti;
- colori con contrasto adeguato e resa verificata in scala di grigi.

### 8.3 Grafici

I grafici consumano soltanto `chart_series` del modello. Il layer grafico espone
componenti limitati e testabili per:

- linea o barre combinate per risultati economici;
- linee percentuali per margini;
- barre divergenti per flussi di cassa;
- linea/barre per cassa, debito e PFN;
- linee per giorni di circolante;
- linea con soglie per DSCR/coperture.

Ogni grafico include titolo, periodo, unità, legenda e, dove utile, etichette sui
valori. Il colore non è mai l'unico modo per distinguere le serie. Sotto il grafico
può comparire una tabella compatta o un rinvio alla relativa appendice.

Non si tenta la parità pixel con i componenti React. È richiesta la parità di dati
e significato.

### 8.4 Commenti

Il template stampa soltanto i blocchi narrativi già presenti nello snapshot. Non
chiama modelli AI e non genera testi. Provenienza e stato di freschezza sono
riportati nelle note del documento quando rilevanti.

### 8.5 Riferimento estetico concordato — 2026-09-15

Il riferimento fornito dall'utente è il dossier CR in
`/home/peter/DEV/formulafinance/back_sideprojects/Redesign/cr-print/report/out/report_screen.html`
e nel PDF associato `Report-CR-Dossier.pdf`. È un riferimento visivo di sviluppo,
non una dipendenza di compilazione. La versione stampata del report finale deve
essere molto simile a questo dossier per composizione, gerarchia e trattamento
dei dati, adattandone il contenuto all'intera pratica di bilancio e piano.

Elementi da riprendere:

- copertina con fascia blu petrolio, titolo neutrale, identità aziendale,
  quattro KPI pertinenti, metadati e indice;
- IBM Plex Sans con pesi regolari, medi e semibold, incorporati nel bundle;
- palette di riferimento: blu petrolio `#003049`, azzurro `#669BBC`, testo
  `#1B1F24`, grigio `#5E6B78`, divisori `#D5DDE4` e `#E4E9EE`;
- pagine A4 con intestazione discreta, numerazione e piè di pagina coerenti;
- titolo della sezione, breve introduzione, colonna KPI laterale e area principale
  per grafici e confronti, seguite da tabelle e commenti pertinenti;
- tabelle con righe sottili, importi allineati, totali evidenziati e poche cornici;
- sintesi nel corpo e prospetti completi nelle appendici, secondo l'indice M1.

Il layout deve conservare questa impostazione anche quando commenti e tabelle
richiedono più pagine. La somiglianza non impone diciotto pagine né la riduzione
dei caratteri per far rientrare dati variabili in una pagina fissa. La leggibilità
in stampa e in scala di grigi rimane un criterio di accettazione.

La catena editoriale da rendere evidente è:

| Sezione | Evidenza da rappresentare | Commento nello snapshot |
|---|---|---|
| Sintesi esecutiva | principali risultati, rischi e decisioni del piano | `executive_summary` |
| Dati di partenza | bilancio infrannuale alla data di riferimento, fonti e qualità | note e diagnostica delle fonti disponibili |
| Rettifiche | valori prima, delta, valori dopo e motivazioni | `adjustments_and_closing` e motivazioni delle rettifiche |
| Chiusura infrannuale | progressivo, proiezione automatica, override e chiusura attesa | `adjustments_and_closing` |
| Ipotesi del piano | driver per anno, origine e ipotesi operative e finanziarie | `budget_assumptions` |
| Conto economico proiettato | ricavi, margini e risultato nei periodi del piano | `economic_outlook` |
| Patrimonio e flussi di cassa proiettati | impieghi, fonti, circolante, cassa, debito e coperture | `financial_outlook` |
| Rischi e verifiche | indicatori, diagnostica e punti aperti | `risks_and_actions` |

I commenti sono collocati vicino alle evidenze della rispettiva sezione, non
raccolti soltanto in un capitolo finale. La tabella indica la pertinenza dei
blocchi esistenti; non introduce nuovi campi narrativi né autorizza a duplicare o
riscrivere automaticamente un blocco condiviso. Un commento assente non viene
sostituito con testo inventato. Si applicano le regole di freschezza e readiness
già definite.

Dati osservati, rettificati, stimati a fine esercizio e previsionali devono essere
distinti da etichette, periodi e legende esplicite. Gli altri workflow continuano
a omettere le sezioni non applicabili secondo il modello M1.

Il titolo di copertina è sempre neutrale e deterministico: `Report Budget 2027 -
2029` nell’esempio, con gli anni derivati dal piano. Non è generato dall’AI e non
contiene conclusioni su margini o debito. Le osservazioni restano nella sintesi
e nei commenti. I titoli delle sezioni possono essere descrittivi; eventuali
titoli interpretativi provengono soltanto da testo presente nello snapshot.
Lo scoring C3, gli indicatori e le conclusioni del dossier CR non sono contenuti
da trasferire al report di bilancio. Grafici, KPI e confronti provengono dal
`FinalReportModel`; il template non calcola o deduce valutazioni finanziarie.

Il dossier e l’anteprima aggiornati sono il riferimento editoriale concordato.
La richiesta del 2026-09-15 autorizza a consolidare le specifiche per arrivare al
report di produzione: la precedente sospensione estetica è superata. Rimangono
i prerequisiti tecnici e di contratto del piano; non occorre una nuova conferma
estetica. Il PDF Chromium dell’anteprima non sostituisce il renderer Typst.

### 8.6 Indicatori approfonditi e Allegati — 2026-09-15

L'utente richiede un dossier meno stringato, con grafici degli indicatori già
presenti nella stampa infrannuale e nel report analitico. Le dodici sezioni
logiche M1 possono svilupparsi su più pagine e sottosezioni.

Il corpo approfondisce liquidità, margini strutturali, redditività, autonomia,
copertura, giorni del circolante, composizioni e pareggio quando disponibili.
Le fonti di copertura sono `pratica-indicators.ts` (`INDICATOR_DEFS`),
`report-ratios.tsx`, `report-structural`, `report-composition`, `report-break-even`
e `report-scoring`. Sono ammessi confronti a punti collegati, barre divergenti,
piccoli grafici affiancati e composizioni al 100%, con commenti pertinenti.
Unità e periodi rimangono espliciti; le convenzioni del DSCR della pratica e la
diversa durata dei periodi infrannuali/annuali non vengono nascoste.

La sezione **Allegati** deve contenere i prospetti completi già rappresentati
nel report, con indice e rinvii, tutti visibili in stampa:

- conto economico e stato patrimoniale, con sottovoci e subtotali disponibili;
- rendiconto completo e riconciliazione della cassa;
- registro rettifiche, contropartite e motivazioni;
- matrice ipotesi, finanziamenti, pregresso e differenze temporanee;
- tabella completa degli indicatori e componenti di scoring/pareggio disponibili;
- metodologia, definizioni e note sulle fonti.

Il dettaglio segue `INCOME_STATEMENT_ROWS` e `BALANCE_STATEMENT_ROWS` del catalogo
IV-CEE e la struttura di `report-cashflow`. Non basta rinviare alle tabelle
sintetiche nel corpo. Le continuazioni mantengono il contesto della voce padre.
Prima del template si verifica la copertura del modello M1, incluse unità e
metodologie: le lacune si risolvono nell'assembler/contratto. Valori e subtotali
arrivano dallo stesso snapshot; il renderer non li ricostruisce con formule.
Dati assenti non diventano zero e dettagli indisponibili sono dichiarati.

L'artifact v3 illustra i requisiti con dati dimostrativi; il suo numero di pagine
non vincola i report effettivi.

### 8.7 Un commento per ogni pagina — 2026-09-15

L'utente richiede un commento, anche breve, su ogni pagina del documento, inclusi
copertina, pagine di continuazione dei prospetti, Allegati e metodologia. Il
commento deve riguardare i dati o lo scopo della pagina, senza ripetere un lungo
testo di sezione su tutte le sue pagine. Indicativamente contiene due o tre frasi;
il corpo analitico può mantenere commenti più articolati.

Il prodotto attuale genera sei blocchi tematici su richiesta e non garantisce
questa copertura. La direttiva successiva richiede quindi di estendere il
contratto narrativo con note brevi per i contenuti e le parti dei prospetti,
con identificatori stabili, provenienza, revisione e stato di freschezza. I sei
blocchi principali rimangono la relazione di sintesi; le nuove note non devono
essere una duplicazione automatica di questi testi.

La generazione usa il modello canonico e il contesto pertinente al contenuto;
le note vengono salvate e sono modificabili dall'utente con protezione dei testi
manuali, come i blocchi principali. Il numero fisico di pagina non è l'identità
persistita del commento: il piano editoriale associa le note ai contenuti che
verranno impaginati. Il renderer riserva spazio al commento su ogni pagina,
incluse le continuazioni delle tabelle, e non chiama l'AI durante l'export.

Per copertina, metodologia e Allegati il commento può essere una nota di lettura
fondata sul perimetro e sul prospetto, senza formulare valutazioni finanziarie
non supportate. I testi mancanti non autorizzano il renderer a inventare una
conclusione. La copertura dei commenti è verificata nel PDF effettivamente
impaginato, insieme alla presenza delle righe dei prospetti e all'assenza di
sovrapposizioni o ritagli.

L'anteprima v4 applica questa disposizione a tutte le sue 33 pagine con commenti
dimostrativi scritti nel generatore. Non usa l'AI e non rappresenta ancora
l'estensione dell'API di produzione.

### 8.8 Titolo neutrale e contratto operativo del dossier

La [spec Dossier Report Budget](2026-09-15-report-budget-dossier-design.md)
consolida titolo, modello v2, Allegati, indicatori, paginazione e commenti.
È il riferimento operativo per le sezioni 8.5–8.7: la copertina non usa più una
conclusione finanziaria come titolo. Gli anni sono i periodi del budget; azienda,
scenario, periodo infrannuale e stato restano metadati separati.

## 9. Profilo PDF e accessibilità

Il profilo iniziale `standard` produce un PDF ricercabile con:

- titolo, autore applicativo, oggetto e parole chiave;
- testo selezionabile ed estraibile;
- segnalibri o struttura equivalente, se supportata in modo stabile;
- lingua italiana dichiarata;
- font incorporati;
- descrizioni o equivalenti testuali per i grafici;
- etichette e pattern che non dipendono dal colore.

Typst documenta supporto a versioni PDF, Tagged PDF, PDF/UA e profili PDF/A. Il
profilo `archival`, candidato PDF/A-2u, viene reso disponibile solo se lo spike e la
validazione automatica confermano la conformità dell'intero documento, inclusi
font, immagini e metadati. Non basta passare un'opzione al compilatore per dichiarare
conforme il risultato.

## 10. Sicurezza e limiti operativi

Il servizio tratta dati finanziari sensibili e avvia un processo esterno. Deve:

- verificare ownership prima di costruire lo snapshot;
- accettare soltanto opzioni enumerate;
- non accettare template, markup Typst, path, URL o font forniti dall'utente;
- usare una root Typst controllata e una directory temporanea per richiesta;
- impedire accessi del template fuori dal bundle autorizzato;
- eseguire senza rete;
- applicare timeout, limite di memoria, dimensione massima dell'input e dell'output;
- limitare la concorrenza delle compilazioni;
- eliminare sempre file intermedi;
- non includere il JSON completo nei log o nei messaggi d'errore.

I log strutturati contengono soltanto identificativi tecnici necessari, hash del
modello, versioni, durata, numero pagine, dimensione e categoria dell'errore.

I limiti numerici iniziali vengono scelti dopo lo spike usando il caso peggiore
misurato più un margine dichiarato; non vanno inventati prima delle misure.

## 11. Gestione degli asset

Template, componenti, font, logo e pacchetti sono parte versionata del backend o di
un bundle dedicato incluso nell'immagine. Ogni modifica al bundle incrementa
`template_version`.

Il template non scarica immagini remote. Un logo aziendale futuro deve passare da
un servizio di asset validato per formato, dimensione e ownership e deve essere
materializzato nella directory temporanea con un nome generato dal server.

## 12. Verifica

### 12.1 Test del renderer

- comando costruito senza input non controllato;
- timeout, processo terminato e cleanup;
- errore del compilatore tradotto nella categoria corretta;
- assenza del binario gestita come servizio indisponibile;
- limiti di input/output e concorrenza;
- compilazione senza accesso alla rete;
- versione attesa di compilatore, font e pacchetti.

### 12.2 Test del documento

Per le fixture infrannuale, annuale e startup:

- firma `%PDF` e file non vuoto;
- numero di pagine entro una fascia motivata;
- metadati e hash presenti;
- estrazione testuale con titoli, azienda, anni e valori campione;
- tutte le sezioni richieste e nessuna sezione non applicabile;
- header delle tabelle ripetuti;
- nessuna pagina vuota inattesa;
- grafici presenti in forma vettoriale o comunque non rasterizzati senza motivo;
- watermark solo per la bozza;
- rifiuto del finale quando readiness non è `ready`.

Golden test visuali rasterizzati possono coprire poche pagine stabili, con soglie
tolleranti e revisione esplicita. Non devono essere l'unica verifica: testo e dati
vanno assertiti semanticamente.

### 12.3 Parità web/PDF

Un test sul medesimo `FinalReportModel` confronta almeno:

- identità della pratica e periodi;
- totali delle rettifiche;
- principali ipotesi;
- ricavi, EBITDA, risultato netto;
- cassa, debito, PFN e cash flow;
- indicatori principali;
- blocchi narrativi e diagnostica.

Il confronto avviene sui dati dei due renderer o sul testo estratto, non tramite
screenshot pixel-perfect.

### 12.4 CI e container

- build dell'immagine con versioni fissate;
- prova a freddo in container senza cache di rete;
- smoke test di compilazione;
- scansione delle dipendenze e verifica checksum;
- misurazione di tempo, memoria e dimensione PDF sul fixture più grande.

## 13. Osservabilità

Metriche minime:

- richieste, successi e fallimenti per categoria;
- durata p50/p95/p99;
- attesa per limite di concorrenza;
- timeout;
- dimensione e pagine del PDF;
- versione di template e compilatore;
- generazioni `draft` e `final`.

Non si usano etichette metriche ad alta cardinalità come azienda o scenario. Gli
identificativi possono comparire nei log autorizzati secondo la policy applicativa.

## 14. Piano di consegna

### Lotto 0 — spike e decisione

- installare localmente una versione fissata di Typst;
- realizzare le fixture limite;
- confrontare primitive native, CeTZ-Plot e Primaviz;
- misurare resa, prestazioni, offline e PDF/A;
- registrare una decisione tecnica con libreria scelta e limiti iniziali.

### Lotto A — runtime

- aggiungere binario, font e pacchetti all'immagine backend;
- implementare interfaccia e processo del renderer;
- introdurre timeout, cleanup, limiti e health check;
- aggiungere test isolati del processo.

### Lotto A2 — contratto e piano editoriale

- completare modello v2, prospetti estesi, indicatori e compatibilità v1;
- fissare font/componenti e pianificare pagine e parti dei prospetti;
- estendere note brevi e commenti senza chiamare l’AI durante l’export.

### Lotto B — template

- creare copertina con titolo neutrale, indice, header/footer e stili;
- implementare sezioni narrative e tabelle;
- gestire sezioni condizionali e Allegati completi;
- rispettare il piano editoriale e riservare spazio a un commento per pagina;
- aggiungere metadati e watermark.

### Lotto C — grafici

- implementare i componenti grafici scelti nello spike;
- coprire null, negativi, scale e serie parziali;
- verificare accessibilità e stampa in scala di grigi.

### Lotto D — API e interfaccia

- esporre l'endpoint autenticato;
- persistere i metadati dell'artefatto;
- aggiungere azioni bozza/finale in `/report`;
- mostrare blocchi di readiness senza avviare compilazioni destinate a fallire.

### Lotto E — collaudo e operazioni

- completare parità web/PDF e fixture dei tre percorsi;
- validare cold start, concorrenza e assenza di rete;
- documentare installazione, metriche, errori e procedura di aggiornamento;
- verificare il profilo archival e abilitarlo solo se conforme.

## 15. Criteri di accettazione

Il milestone è completato quando:

1. il backend genera un PDF scaricabile senza Playwright, Chromium o browser;
2. l'unico input di dominio è un `FinalReportModel` supportato e congelato;
3. i tre percorsi di pratica producono documenti corretti e le sezioni opzionali
   sono gestite;
4. numeri, commenti, diagnostica e grafici sono semanticamente allineati al report
   web;
5. il finale è bloccato quando il report non è pronto e la bozza è marcata su ogni
   pagina;
6. font, template, pacchetti e compilatore sono versionati e funzionano offline;
7. timeout, concorrenza, cleanup, ownership e sanitizzazione sono coperti da test;
8. il PDF è ricercabile, stampabile, corredato di metadati e supera la validazione
   automatica concordata;
9. la pipeline containerizzata supera lo smoke test a freddo;
10. metriche e log permettono di diagnosticare i fallimenti senza esporre il
    contenuto finanziario;
11. la copertina mostra il titolo neutrale corretto per uno, tre e cinque anni;
12. indicatori e Allegati conservano tutte le righe disponibili del modello;
13. ogni pagina contiene il proprio commento, senza duplicazioni automatiche,
    testi ritagliati o righe dei prospetti perdute.

## 16. Fuori perimetro

- export HTML tramite Typst;
- replica pixel-perfect della pagina React;
- template caricati o modificati dagli utenti;
- editor visuale del documento;
- calcoli finanziari nel template;
- generazione dei commenti AI durante l'export;
- browser headless come fallback automatico;
- coda asincrona e archivio documentale, salvo evidenza prodotta dalle misure o una
  successiva decisione di retention;
- firma digitale o conservazione sostitutiva;
- dichiarazione PDF/A senza validazione formale.

## 17. Decisioni da chiudere dopo lo spike

Lo spike deve produrre una risposta esplicita a questi punti:

1. primitive interne, CeTZ-Plot o Primaviz;
2. versione fissata di Typst e strategia di aggiornamento;
3. font e licenze da distribuire;
4. limiti di tempo, memoria, concorrenza e dimensione;
5. profilo PDF standard e reale fattibilità di PDF/A-2u;
6. conservazione del PDF, dello snapshot o dei soli metadati;
7. soglia oltre la quale passare dalla risposta sincrona a una coda.

Queste sono decisioni implementative misurabili. Non cambiano il principio centrale:
il PDF è una rappresentazione immutabile dello stesso modello canonico usato da
`/report`.
