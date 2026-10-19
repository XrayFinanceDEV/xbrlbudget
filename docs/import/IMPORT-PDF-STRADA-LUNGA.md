# Import PDF: la strada corta e la strada lunga

Perché un PDF a volte si importa in pochi secondi e a volte in 6–10 minuti (con il frontend in
timeout), e che cosa fare perché succeda il meno possibile. Analisi del 2026-10-16 sul caso
SGH S.R.L., `BILANCIO E NOTA INTEGRATIVA.PDF` (9 pagine, bilancio micro reso da XBRL).

## Le due strade

L'import di un PDF prova più modi di leggere il bilancio, **dal più veloce al più lento**, e si
ferma al primo che funziona (`importers/pdf_importer.py`, `_llm_extract`):

1. **Lettori a regole, senza IA** — leggono il testo del PDF con regole fisse e verificano che i
   totali stampati tornino. Meno di un secondo.
   - PDF reso da XBRL (`xbrl_reso_parser`): il layout standard del deposito in Camera di
     Commercio, quello con "Nota integrativa XBRL al ..." in ogni pagina. Il nome dice da dove
     nasce il layout, ma legge il **PDF**, non il file `.xbrl`.
   - schema di legge con il percorso nell'etichetta (`schema_etichette_parser`);
   - schema IV-CEE standard (`standard_ivcee_parser`);
   - schema con il dettaglio dei conti e situazione contabile (otto famiglie di formato);
   - dal 2026-10-16, dopo i precedenti: le prove incrociate fra fonti
     (`extract_deterministic_source_candidates`) e il lettore generico dello schema di legge di
     qualunque gestionale (`schema_legge_generico`). Questi due lettori non stanno in
     `_llm_extract`: li prova `tentativo()` in `import_snello/deterministico.py`, dopo i sei
     precedenti, e dopo di loro un terzo, `prospetto_sintetico` (2026-10-19, prospetti di due pagine
     con le voci di legge appiattite).
2. **Qwen sul gx10**, solo se i lettori a regole falliscono: prima la lettura delle macro-voci
   (`macro_analysis`), poi l'estrazione LLM di Stato patrimoniale e Conto economico
   (`pdf_extractor_llm`).

La **strada corta** è il punto 1, la **strada lunga** il punto 2.

## Il caso misurato

| | Codice vecchio (strada lunga) | Codice nuovo (strada corta) |
|---|---|---|
| Tempo totale | **376 s** (~6 min) | **12 s** |
| Chiamate a Qwen | 15 | 2 (solo arricchimento dettagli) |
| Lettore usato | LLM | `xbrl_reso` deterministico |

Il lettore a regole non riconosceva il file perché l'intestazione ("SGH S.R.L.") e il piè di
pagina ("Nota integrativa XBRL al 31/12/2025 — Pag. N") ripetuti su ogni pagina si mescolavano
alle righe del prospetto. La correzione in `xbrl_reso_parser.py` (`_ripetute`) riconosce le righe
di margine **dalla ripetizione su più pagine**, non dal testo: vale per qualunque gestionale, non
solo per questo file.

### Dove si perdeva il tempo sulla strada lunga

| Fase | Chiamate | Tempo |
|---|---|---|
| Lettura macro-voci (2 blocchi di pagine) | 2 | **200 s**, ~100 s l'una (risposte lunghe) |
| → fallisce ("MACROVOCI DA VERIFICARE") | | |
| Estrazione SP + CE, anno corrente e precedente | 4 | 54 s |
| **La stessa estrazione ripetuta altre 2 volte, identica** | 8 | 109 s |
| Arricchimento dettagli | 1 | 6 s |
| **Totale** | **15** | **376 s** |

- La lettura delle macro-voci costa più di metà del tempo e poi fallisce comunque.
- L'estrazione viene ripetuta 3 volte con domande identiche: Qwen gira a temperatura 0, quindi
  ridà la stessa risposta. Le due ripetizioni costano quasi 2 minuti senza aggiungere nulla.

### Perché il frontend andava in timeout anche dopo la correzione

- Il backend acceso era partito **prima** della correzione: `uvicorn --reload` guarda solo
  `backend/`, non `importers/`, quindi il processo continuava a usare il codice vecchio. Dopo una
  modifica a `importers/` il backend va **riavviato**.
- `frontend/lib/api.ts` (`importPDF`) aspetta al massimo **300 s**; `/import/pdf-ocr` 1.260 s.
- `backend/app/api/v1/imports.py` (`upload_pdf`) chiama `import_pdf_balance_sheet` direttamente
  dentro una funzione `async`, senza `run_in_threadpool` (la rotta OCR invece lo fa): durante
  l'import tutto il backend resta fermo, anche per le altre richieste.
- Il backend finisce comunque e salva: un import "in timeout" a schermo risulta spesso
  `success` in `uploaded_files`.

### Come si diagnostica senza log su file

Il backend scrive solo sulla console di `avvia-backend.ps1`. Fonti alternative:
- tabella `uploaded_files`: `uploaded_at` (UTC) = inizio, `status` = esito;
- `financial_years.created_at` = fine del salvataggio;
- `/metrics` di vLLM sul gx10 (porta 18300): numero di richieste, token, latenze;
- riprodurre fuori dal server con `DATABASE_PATH` su una copia del DB, cronometrando
  `llm_provider._invia`.

## La misura sul corpus (2026-10-16 e 17)

Il punto 1 qui sotto è stato fatto: i lettori a regole girano da soli, senza rete, su tutti i PDF
distinti di `Test/` (175; 161 nella prima misura) e si confronta ogni file con la fotografia
precedente. Gli strumenti sono in `docs/import/handoff-2026-10-16/strumenti/`
(`snello_driver.py`, `confronta.py`).

| Passo | PDF letti a regole |
|---|---|
| Prima del 16/10 | 96 su 161 |
| Merge del lavoro del 16/10 (default snello, prove incrociate, regole delle situazioni contabili) | 123 su 175 |
| Lettore generico dello schema di legge (`gen_M`, 14 schemi) | 136 |
| 413, 115, sangae6 e 382 (regole di `gen_A`/`gen_B`/`gen_C` e due nuove) | 140 |
| kps (prospetto Micro Infocamere) e SANTORO 394 | 142 |
| 1337 (reso XBRL, riga di fondo pagina) | **143 su 175** |

A ogni passo nessun file adottato prima è stato perso e nessun valore è cambiato, con una
eccezione voluta: il 253 passa da un tappo di 3 € su `ce06` a una lettura esatta. Il confronto è
sui valori di SP e CE, non sul solo esito.

### Le famiglie risolte

Ogni regola è generale, scritta sul comportamento del documento e non su un file:

- **Costi stampati col segno del loro effetto** ("Totale (B) -33.155.832", "17) interessi
  -11.460"): una seconda lettura, tentata solo se la letterale non chiude, che gira i costi e si
  adotta solo se *ogni* controllo torna (413, 115).
- **Dettaglio dei conti sotto la voce.** Una riga a zero non può togliere dettaglio con massa:
  con i segni liberi lo zero "si compone" con qualunque mastro e i suoi conti. La prova coi segni
  scarta due righe uguali di segno opposto, perché si annullano (un mastro e la sua foglia).
  Prima perdevano "Altri 4.800" e le imposte differite (sangae6).
- **Importi senza didascalia dopo una voce senza importo.** Se le sorelle già stampate sommano
  agli importi, chiudono il padre e non appartengono alla voce sopra (382: "a) vari 191",
  "b) contributi", "191").
- **Prospetti Infocamere Micro.** Il numero di pagina in coda a un piede non è un importo; un
  trattino in coda alla riga è una cella vuota, non l'intervallo di "(18 - 19)"; una voce a soli
  trattini seguita dalla sua sotto-voce è un'intestazione; "a/b/c)" che somma le lettere
  successive si toglie (kps).
- **Reso XBRL: un piede ripetuto non è una riga.** L'ultima riga della pagina, dentro la fascia
  del piede, con le celle che si ripetono in altre pagine, veniva scartata come piede: il totale
  della voce risultava 0 contro 975.890 stampato (1337). Un blocco di margine con didascalia e
  importo è una riga del prospetto.
- **Situazioni contabili.** Separatore delle colonne, pagina SP+CE divisa al titolo "Conto
  economico", "utile in corso di formazione" come risultato, sinonimi del CE come ultima risorsa,
  fondo sotto un mastro-cespite (9 file in più: 229, 243, 367, 405, 588, 696, 697, 702, 703).

### Che cosa resta sulla strada lunga (32 file)

| Causa | N. | Che cosa serve |
|---|---|---|
| Non sono bilanci (un'email, una distinta di bollo) | 2 | niente: il rifiuto è giusto |
| Solo conto economico | 2 | niente: il parser lo dichiara |
| Scansioni senza testo | 3 | MinerU |
| Conti disegnati come grafica (mastri e importi vettoriali) | 5 | MinerU |
| Artefatti di 1-2 pagine, non bilanci | 5 | niente |
| Documenti che si contraddicono | 8 | niente: restano rifiuti. Il 314 va tenuto tale: leggerlo salverebbe i numeri di un anno diverso da quello scelto |
| Da lavorare | 7 | vedi sotto |

Da lavorare: due bilanci di verifica (667, 376) che il parser delle situazioni contabili non
legge; un AGO (614) con le cifre sporche nel testo ("_3_.81_4_,_5_3_") che il parser scambia per un
documento senza stato patrimoniale; uno schema Infocamere "esteso con scostamento" (1341) con gli
importi prima dell'etichetta; tre situazioni contabili oltre soglia (674, 676, 1327) non ancora
esaminate. L'`except Exception` che inghiotte la causa in `import_snello/deterministico.py`
(riga 380) rende i casi di errore indiagnosticabili senza richiamare il parser a mano.

## Che cosa fare perché altri PDF non prendano la strada lunga

### 1. Allargare i lettori a regole (meno PDF sulla strada lunga)

Non correggere un file alla volta, ma **misurare**:
1. far girare **solo** i lettori a regole su tutti i PDF di `Test/` (meno di 1 s a file, nessuna
   chiamata a Qwen);
2. elencare i PDF che finirebbero sulla strada lunga e raggrupparli per causa;
3. correggere le cause più frequenti, in modo generale (come `_ripetute`).

### 2. Accorciare la strada lunga (per chi ci finisce comunque)

- macro-voci: limitarne il tempo, o saltarle quando i lettori a regole hanno già trovato i totali;
- un solo tentativo di estrazione, o un secondo con una domanda **diversa**: a temperatura 0
  ripetere la stessa domanda non serve;
- chiamate SP e CE in parallelo (il gx10 regge 6 richieste insieme, `GX10_CONCORRENZA`).

Stima sul caso misurato: da ~6 min a ~1–1,5 min.

### 3. Non far andare in timeout il frontend

- alzare il timeout di `importPDF` (come `/import/pdf-ocr`);
- `run_in_threadpool` attorno a `import_pdf_balance_sheet` in `upload_pdf`;
- meglio: import in background con avanzamento (il backend risponde subito, il frontend chiede a
  che punto è).

### 4. Quando c'è l'XBRL, usare l'XBRL

Per i bilanci depositati il file `.xbrl` ha già i numeri strutturati: zero Qwen, zero errori di
lettura. Quando il PDF riporta "Nota integrativa XBRL", suggerire all'utente di caricare l'XBRL.

## Difetti trovati nella stessa analisi (non ancora corretti)

- **"2025" letto come importo.** Sul PDF SGH l'arricchimento dettagli (Qwen) legge la nota
  *"debiti verso soci per finanziamenti al 31/12/2025 pari ad euro 118.796"* e scrive **2.025** su
  `sp17b` (l'anno della data) invece di 118.796; il resto va su `sp17g`. Il totale quadra, ma PFN,
  ROD e indebitamento risultano migliori del vero. Un importo uguale all'anno della data nella
  stessa frase non andrebbe accettato.
- **Reimport XBRL sopra un anno già importato.** `xbrl_parser_enhanced.import_to_database` su un
  `BalanceSheet` esistente sovrascrive solo i campi che l'XBRL compila: le sotto-voci scritte dal
  PDF restano (dettagli doppi: `sp06a` + `sp06g`, `sp17b` + `sp17g`) e `original_bs_snapshot` resta
  quello del PDF, così la tab Rettifiche mostra una rettifica mai fatta.
- **Politica divergente sui crediti senza dettaglio:** l'XBRL micro li mette in `sp06a` (clienti),
  il PDF in `sp06g` (altri crediti).
