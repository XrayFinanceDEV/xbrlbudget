# Ricognizione import: AMBIENTA, TM BUSINESS GROUP, FORMETAL

Data: 20 settembre 2026. Analisi del codice corrente, dei sei PDF in `inbox/import-test` e del database locale, aperto in sola lettura. Nessuna modifica all'importatore o ai bilanci.

## Esito

La perdita dei dettagli è principalmente un problema della pipeline: selezione delle pagine, schema di risposta, riduzione dei conti ai mastri, recuperi diversi per percorso e scelta del candidato in base alle quadrature. Non è possibile attribuirla genericamente alle capacità del modello.

Le prove più nette:

- TM 2025 e 2026: il recupero deterministico `_hier_reconstruct` legge i mastri di primo livello e restituisce soltanto l'aggregato dei debiti. Il risultato riprodotto coincide con gli aggregati conservati prima delle rettifiche. Le rimanenze analitiche sono presenti nei PDF, ma vengono perse.
- TM: lo stesso recupero classifica come debito il mastro «RISULTATI DELL'ESERCIZIO», senza leggere il figlio «RISULTATI PORTATI A NUOVO». Si perde anche la corretta separazione tra patrimonio netto e debiti, pur mantenendo entrambe le quadrature.
- FORMETAL 2025: le tabelle della nota integrativa alle pagine 13 e 18–19 contengono i dettagli. Il selettore passa allo SP soltanto pagina 2; al CE pagine 3–4. Le tabelle non arrivano al modello.
- `BalanceSheetExtraction` contiene `sp05_rimanenze`, ma nessuno dei cinque sottocampi delle rimanenze. L'LLM non dispone di un campo strutturato per restituirli; alcuni recuperi deterministici successivi suppliscono, soltanto su determinati layout.
- Il frontend riempie i dettagli assenti con destinazioni convenzionali: i debiti in «altri debiti», le rimanenze senza alcun dettaglio in «materie prime». Questi valori visualizzati non sono necessariamente classificazioni lette dal documento.

## Metodo e limiti

Sono stati verificati:

1. Accessibilità del backend (`/docs`: HTTP 200), struttura del codice e schema del database.
2. Testo e struttura dei PDF; visualizzazione delle tre pagine del depositato AMBIENTA, che è un PDF a immagini.
3. Corrispondenza SHA-256 fra cinque file e i record `FinancialYear` locali.
4. Snapshot salvati prima della prima rettifica, distinti dai valori attualmente modificati.
5. Riesecuzione in memoria dei parser deterministici dei tre documenti a sezioni contrapposte; verifica del percorso di recupero TM con una sonda temporanea in memoria.
6. Selezione delle pagine FORMETAL e AMBIENTA, schema strutturato LLM e recupero dei dettagli di AMBIENTA.
7. Quadrature ricalcolate sugli snapshot TM 2025/2026 e FORMETAL 2025.

Non sono state effettuate nuove chiamate LLM né reimportazioni. Non sono disponibili in questa analisi le risposte grezze delle chiamate LLM storiche. La corrispondenza del parser deterministico con gli snapshot dimostra la riproducibilità del difetto; non sostituisce un log completo della selezione dei candidati durante l'importazione storica.

Gli snapshot `original_bs_snapshot` sono acquisiti dall'endpoint Rettifiche prima della prima modifica: sono quindi evidenza dei dati precedenti alle rettifiche, non una traccia completa delle fasi intermedie dell'import.

| File | Percorso verificato | Record associati tramite hash |
|---|---|---|
| Bilancio di verifica al 30.06.2026.pdf, AMBIENTA | B1, IVCEE con dettaglio | 443: giugno 2026; 444: comparativo 2025 |
| TM-BUSINESS_589_bilancio 2026.pdf | C, contrapposte con codici puntati | 470: maggio 2026 |
| TM-BUSINESS_590_bilancio 2025.pdf | C, contrapposte con codici puntati | 471: 2025 |
| FORMETAL-TEST-30-04-26.pdf | C, sezioni contrapposte | 477: aprile 2026 |
| FORMETAL_701_Bilancio xbrl 31-12-2025.pdf | A1, facsimile XBRL in PDF | 478: 2025; 479: 2024 |
| BILANCIO DEPOSITATO AMBIENTA.pdf | Tre pagine a immagini; serve percorso OCR/vision | Nessun `FinancialYear` corrente con questo hash |

Il classificatore chiamato direttamente sul testo vuoto del depositato AMBIENTA restituisce `UNSUPPORTED`; questo non dimostra un rifiuto dell'import completo, che esegue prima il recupero OCR sui PDF a immagini.

## Flusso attuale

```text
PDF → classificazione A/B/C
    ├─ A/B: tentativo IVCEE deterministico validato
    │       altrimenti LLM SP/CE sulle pagine selezionate
    │       + recuperi deterministici di righe, scadenze, dettagli
    └─ C: candidato CoGe LLM + candidato deterministico
            → scelta per distanza dai totali e residuo
            → eventuale integrazione tipizzazione debiti
            → netting e riconciliazioni
        ↓
controlli SP, CE↔SP, gerarchie, affidabilità → persistenza
        ↓
frontend: completamento dei sottocampi mancanti → visualizzazione/Rettifiche
```

L'orchestratore è [pdf_importer.py](../../importers/pdf_importer.py), funzione `import_pdf_balance_sheet`, riga 679. I percorsi A/B possono terminare con un candidato deterministico validato prima di chiamare l'LLM, righe 946–977. Nei file A/B testati qui, la chiamata autonoma a `extract_standard_ivcee_balances` non restituisce uno SP utilizzabile.

Nella route C la scelta avviene sullo SP complessivo: `_completeness_gap` misura lo scarto dal totale dichiarato, poi si usa il residuo. Non esiste qui un criterio che premi il recupero dei sottoconti documentati. Un candidato aritmeticamente buono può sostituire integralmente un candidato più analitico.

La persistenza PDF attuale non è il principale collo di bottiglia: `_create_balance_sheet`, riga 653, salva tutti i campi `sp*` presenti nel modello ORM. I dettagli esistono nel database, ma devono arrivare valorizzati fino a quel punto.

## TM BUSINESS GROUP: due difetti distinti

### Dettagli disponibili e non importati

Entrambi i PDF riportano a pagina 1:

| Rimanenze | Importo |
|---|---:|
| Materie prime, sussidiarie e consumo | €21.250,00 |
| Merci | €170.000,00 |
| Lavori in corso su ordinazione | €40.000,00 |
| Totale | €231.250,00 |

Gli snapshot dei record 470 e 471 conservano `sp05_rimanenze = 231250` e nessun dettaglio non nullo. Non manca la fonte: manca la discesa dal mastro alle voci che ne spiegano la composizione.

Anche i debiti sono leggibili e riconciliabili per natura:

| Natura del debito, indipendentemente dalla scadenza | 2025 | Maggio 2026 |
|---|---:|---:|
| Finanziamenti bancari | €268.242,15 | €349.991,50 |
| Finanziamenti soci | €2.455,95 | €6.455,95 |
| Debiti commerciali | €133.144,56 | €310.448,41 |
| Conti erariali passivi | €1.971,81 | €23.113,67 |
| Enti previdenziali | €14.300,34 | €18.817,63 |
| Altri debiti | €27.118,02 | €28.547,26 |
| Somma delle voci | €447.232,83 | €737.374,42 |

Nel 2025 i debiti commerciali comprendono anche €19.426,09 di fatture da ricevere. I sottoconti dei fornitori comprendono un saldo negativo: occorre conservarne il segno e non sommare i valori assoluti.

La natura bancaria/soci è documentata; la dicitura «medio/lungo termine» non fornisce da sola il piano della quota esigibile entro l'esercizio successivo. Classificazione per natura e attribuzione delle scadenze devono poter avere gradi di completezza diversi.

### Patrimonio netto trasferito nei debiti

La riesecuzione del parser restituisce:

| Dato | 2025 | Maggio 2026 |
|---|---:|---:|
| `sp16` restituito dal parser e conservato nello snapshot | €843.052,22 | €1.173.248,99 |
| Debiti ricostruiti dalle voci sopra | €447.232,83 | €737.374,42 |
| Differenza | €395.819,39 | €435.874,57 |
| «RISULTATI PORTATI A NUOVO» nel PDF | €395.819,39 | €435.874,57 |

La sonda sul percorso `_hier_reconstruct` conferma che esso viene attivato e restituisce un risultato su entrambi i file. Il mastro «RISULTATI DELL'ESERCIZIO» viene classificato da `_classify_sp_passivo` come `sp16`; il figlio che chiarisce «PORTATI A NUOVO» non viene usato. Anche «CAPITALE E RISERVE», €12.000, viene conservato interamente nelle riserve, perdendo la separazione €10.000 capitale / €2.000 riserva legale.

Gli snapshot hanno `Attivo − Passivo = 0` e risultato CE coerente con SP, ma gerarchie incomplete. Il sistema li segnala da rivedere: non è corretto dire che li dichiari integralmente validi. Tuttavia la quadratura non può individuare da sola il trasferimento da patrimonio netto a debiti.

Riferimenti in [situazione_contabile_parser.py](../../importers/situazione_contabile_parser.py):

- `_be_reclassify`, riga 3252: si ferma al livello più aggregato che sa classificare; scende nei figli solo se il padre è generico.
- `_hier_lvl1`, riga 3456: seleziona i mastri di primo livello.
- `_hier_reconstruct`, riga 4293: ricostruisce da quei mastri; nel ramo passivo, salvo alcune categorie speciali, accumula in `sp16` (riga 4385).
- Attivazione del recupero gerarchico, riga 5056: se il tentativo precedente ha un residuo materiale e il documento ha gerarchia puntata.
- `classify_passivo`, riga 4629: il percorso generico ordinario ha già una tipizzazione dei debiti. Il recupero gerarchico utilizza un percorso diverso e perde quel beneficio.

## FORMETAL 2025: la nota integrativa contiene la risposta

Il file fornito è un PDF generato da XBRL, non un'istanza XML/XBRL nativa. Percorre quindi l'importatore PDF.

`find_section_pages` restituisce SP = pagina 2 e CE = pagine 3–4. La tabella «Variazioni e scadenza dei debiti», pagine 18–19, resta fuori da `extract_relevant_pages`. La ricerca nel testo effettivamente selezionato conferma l'assenza sia del titolo sia dell'importo bancario di €710.247.

| Voce della nota | Entro l'esercizio successivo | Oltre |
|---|---:|---:|
| Soci per finanziamenti | €34.450 | €0 |
| Banche | €710.247 | €459.080 |
| Fornitori | €364.665 | €0 |
| Tributari | €16.709 | €0 |
| Previdenza e sicurezza sociale | €31.961 | €0 |
| Altri debiti | €97.624 | €0 |
| Totale | €1.255.656 | €459.080 |

La somma è €1.714.736 e riconcilia al prospetto. Lo snapshot 478 conserva correttamente i due totali per scadenza, ma nessuna delle categorie di dettaglio non nulla.

A pagina 13 la tabella delle rimanenze permette inoltre di leggere:

- Fine 2025: materie prime €79.135; prodotti finiti e merci zero.
- Inizio 2025: materie prime €70.835; prodotti finiti e merci €53.415; totale €124.250, coincidente con il comparativo 2024.

Le colonne «inizio», «variazione», «fine», «entro», «oltre» hanno significati diversi: un estrattore dedicato alla nota deve interpretarli esplicitamente, collegando anche le tabelle spezzate fra due pagine. La presenza di una colonna iniziale non consente di trasferire al 2024 le scadenze finali del 2025.

Nei valori attualmente rettificati, i finanziamenti soci sono stati collocati nel lungo; la tabella originale li indica nel breve. Questa osservazione serve soltanto a distinguere fonte, importazione e rettifiche: i dati attuali non sono stati modificati.

Per FORMETAL aprile 2026 il parser deterministico restituisce già debiti suddivisi per natura, inclusi banche, fornitori, tributi e previdenza. Le rimanenze restano invece solo aggregate a €79.135. Non tutti i percorsi C hanno quindi lo stesso difetto.

## AMBIENTA: recupero parziale e fonti diverse

Nel riclassificato di giugno 2026, pagina 2, le rimanenze sono esplicitamente tutte materie prime: €287.526,55 correnti e €286.094,89 comparative. Lo snapshot 443 contiene già il dettaglio corrente e varie categorie dei debiti. Lo snapshot 444 conserva il totale rimanenze comparativo, ma non il relativo sottocampo.

Il codice spiega questa asimmetria: nel percorso a due anni `_recover_printed_fixed_asset_details`, che copre anche le rimanenze, viene applicato a `current_bs`, non a `prior_bs` ([pdf_extractor_llm.py](../../importers/pdf_extractor_llm.py), riga 4969). È un limite verificabile del percorso, coerente con i dati osservati.

Il depositato AMBIENTA allegato è un altro caso: contiene solo tre pagine a immagini, benché il piè di pagina indichi «di 21». Sono frontespizio, SP e CE abbreviati; manca la nota integrativa. I dettagli di debiti e rimanenze non sono presenti in quelle tre pagine.

I record correnti 443/444 derivano entrambi, per hash, dal riclassificato di giugno, non da questo depositato. Inoltre i due documenti espongono valori 2025 diversi: ad esempio totale attivo €2.161.054 nel depositato contro €2.170.417,20 nella colonna comparativa del riclassificato. Un futuro arricchimento fra documenti deve controllare anche versione e riconciliazione, oltre ad azienda e anno.

## Cause trasversali

### 1. Contratto LLM incompleto

`BalanceSheetExtraction`, [pdf_extractor_llm.py](../../importers/pdf_extractor_llm.py), riga 86, espone soltanto il totale rimanenze. Il modello strutturato include invece categorie analitiche dei debiti e crediti. Anche altre famiglie analitiche dipendono da recuperi successivi.

Il modello configurato in `config.py`, riga 213, è `claude-haiku-4-5-20251001`. Cambiare modello non risolve pagine escluse, campi assenti o dati eliminati dal candidato vincente.

### 2. Anti-duplicazione ottenuta perdendo informazione

Evitare di sommare contemporaneamente mastro e figli è necessario. Tuttavia non richiede di eliminare i figli: il mastro può controllare il totale, mentre i figli ne spiegano la composizione. Oggi vari percorsi risolvono il rischio fermandosi al padre.

Nei percorsi A/B esistono inoltre prefiltri che eliminano righe contabili di dettaglio per alcuni formati: `_preprocess_stampa_dettaglio`, `_preprocess_zucchetti`, `_preprocess_datev_koinos`. Non sono tutti attivi sui sei file, ma costituiscono un vincolo architetturale da considerare.

### 3. Recupero dei dettagli limitato e spesso indivisibile

`_recover_printed_fixed_asset_details`, riga 1459, cerca specifici codici e geometrie sulle sole pagine SP. Richiede che i dettagli letti ricostruiscano tutto il totale, con tolleranza €0,01; se anche un solo sottocampo è già valorizzato, salta la famiglia. Non realizza un arricchimento generale e progressivo dei dettagli parziali.

### 4. Scelta di un intero candidato senza misura della copertura analitica

In [pdf_importer.py](../../importers/pdf_importer.py), riga 1316, l'ordinamento usa distanza dal totale e residuo. Dopo la scelta, `overlay_debt_typing` viene chiamato soltanto quando vince il candidato non deterministico.

L'integrazione esistente usa inoltre proporzioni del candidato donatore, non importi con prove puntuali. Si attiva se la quota «altri» del vincitore supera il 60% e il donatore è sufficientemente migliore. Se i sottocampi sono tutti zero, `altri / totale = 0` e il controllo interpreta il caso come già sufficientemente tipizzato. Se vince il deterministico senza dettagli, non si attiva affatto. Riferimento: [situazione_contabile_parser.py](../../importers/situazione_contabile_parser.py), riga 921.

### 5. «Altri» può essere un completamento del frontend

[pratica-reconcile.ts](../../frontend/lib/pratica-reconcile.ts), riga 4, calcola `totale − somma dettagli` e lo assegna a una destinazione convenzionale. Per i debiti è «altri debiti»; per le rimanenze prive di dettaglio è «materie prime».

[pratica-statement-rows.ts](../../frontend/lib/pratica-statement-rows.ts), riga 6, applica il completamento prima di visualizzare le righe. Anche Rettifiche usa questa funzione. Questo spiega perché l'utente vede «tutto in altri» mentre nello snapshot può esserci soltanto l'aggregato, con tutti i sottocampi a zero.

Una politica affine esiste in `reconcile_source_detail`, [iv_cee_hierarchy.py](../../importers/iv_cee_hierarchy.py), riga 423, richiamata da XBRL nativo, CSV e MinerU. Non è corretto attribuire tutte le assegnazioni al ramo PDF standard.

La convenzione senza dettagli per rimanenze/clienti è documentata nel repository come decisione del proprietario del 18 settembre e coperta da test. Il problema da affrontare è applicarla a una fonte che contiene dettagli non recuperati, e rendere distinguibile un valore convenzionale da un valore letto.

### 6. Mancano traccia e metriche sufficienti della perdita

Il risultato persistito non conserva una prova per ogni importo con pagina, riga, colonna, padre, periodo e motivo di scelta/scarto. Il solo hash del documento non spiega quale passaggio abbia perso una voce.

Nella verifica per hash, cinque dei sei documenti non risultano nel manifest `tests/corpus/manifest.json`; soltanto FORMETAL aprile 2026 risulta presente. Nessuno dei sei hash risulta in `tests/fixtures/import_baseline.json`. Questo non esclude altri test sullo stesso formato, ma significa che queste esatte fonti non hanno una copertura uniforme nei due inventari controllati.

Esistono già test di dettaglio, gerarchia e classificazione: non manca ogni controllo. Occorre però una verità attesa per questi file che verifichi gli importi e la natura delle singole voci, oltre alle quadrature e alle convenzioni di riempimento.

## Proposta architetturale da discutere

La modifica centrale è separare l'acquisizione delle prove dalla costruzione del bilancio riclassificato.

```text
Documento completo
  → inventario di prospetti, conti, tabelle della nota e relativi periodi
  → righe con importi, segni, coordinate, gerarchia e significato delle colonne
  → classificazione delle righe e collegamento ai totali di controllo
  → arricchimento progressivo delle famiglie incomplete
  → controlli aritmetici, semantici e di copertura
  → dati riclassificati + provenienza + residui espliciti
```

### Totali di controllo e dettagli coesistenti

Conservare il totale stampato come vincolo. Cercare i dettagli nel prospetto, nei sottoconti e nella nota, senza aggiungerli una seconda volta al totale. Quando i dati di controllo sono contraddetti dalla fonte, segnalare il conflitto: la conservazione del totale non deve cristallizzare un errore come quello del patrimonio netto TM.

L'unità di lavoro deve essere la singola famiglia contabile, non un intero candidato da accettare o scartare. Il layout serve a leggere le righe; la classificazione e la gestione dei residui devono essere comuni ai vari lettori.

### Recupero parziale conservativo

Se un totale debiti di 100 è documentato e sono riconosciuti fornitori 60 e banche 25, conservare 60 e 25 e lasciare 15 da classificare. Condizioni: stesso periodo e perimetro, importi non sovrapposti, segni corretti e distinzione tra saldi e movimenti.

Separare almeno concettualmente:

- «Altri debiti» esplicitamente documentati.
- Debiti di natura ancora non identificata.
- Natura identificata ma scadenza non documentata.
- Valore collocato secondo una convenzione operativa.

Si può mantenere una destinazione contabile compatibile con l'interfaccia esistente, ma occorrono metadati e un'indicazione visibile. Per le rimanenze il residuo ignoto non prova che si tratti di acconti o materie prime. Le convenzioni già concordate possono restare riconoscibili come tali.

Se la somma dei dettagli supera il padre, cercare duplicazioni, segni, colonne o periodi errati; non creare automaticamente un residuo negativo per farla tornare.

### Nota integrativa come fonte strutturata

Scansionare l'intero documento per identificare tabelle rilevanti, poi estrarle per famiglia. L'LLM deve poter interpretare contesto e intestazioni; le somme e i vincoli restano deterministici. Gestire esplicitamente tabella multipagina, saldi iniziali/finali, movimenti, natura e scadenze.

FORMETAL fornisce un primo caso completo e controllabile: la tabella dei debiti ricostruisce esattamente il prospetto e può arricchirlo senza cambiare i totali. La lettura degli anni va resa simmetrica, limitando il dettaglio comparativo a ciò che le colonne documentano davvero.

### Una misura di qualità distinta dalla quadratura

Per ogni famiglia registrare:

- Importo coperto da dettagli documentati e percentuale rispetto al totale.
- Numero di voci della fonte riconosciute, escluse o ancora irrisolte.
- Importo convenzionale o non classificato.
- Copertura separata per natura e scadenza.
- Conflitti fra fonti e motivazione delle decisioni.

Una quadratura corretta non deve interrompere il recupero quando la fonte contiene ancora dettaglio utilizzabile. Viceversa, una fonte abbreviata senza nota deve poter risultare «completa rispetto alla fonte, con dettaglio non disponibile».

### Piano di miglioramento verificabile

1. Costruire una base attesa per i sei file, con pagine e importi verificati; separare originali, rettifiche e convenzioni. Includere TM patrimonio netto, rimanenze e debiti, FORMETAL nota, AMBIENTA corrente/comparativo e documento incompleto.
2. Definire il formato comune delle prove e dei residui; adattare progressivamente gli estrattori già presenti. Rendere il contratto di dettaglio coerente con il catalogo e l'ORM.
3. Correggere il percorso gerarchico TM e introdurre un arricchimento delle famiglie indipendente dal candidato vincente. Riutilizzare le regole di classificazione invece di duplicarle fra fallback.
4. Aggiungere il lettore delle tabelle di nota e applicare gli stessi arricchimenti agli anni supportati dalla fonte.
5. Verificare su un database isolato sia le quadrature sia l'accuratezza dei dettagli; confrontare la copertura prima/dopo sul corpus. Solo successivamente valutare se un modello diverso migliori i casi rimasti difficili.

Criteri iniziali di accettazione: TM conserva le tre componenti delle rimanenze e il patrimonio netto documentato; FORMETAL 2025 recupera le sei categorie dei debiti e le scadenze della nota; AMBIENTA applica il recupero anche al comparativo; nessun dettaglio viene inventato per il depositato AMBIENTA privo della nota; gli altri casi mantengono segni, periodi, totali e dettagli già corretti.
