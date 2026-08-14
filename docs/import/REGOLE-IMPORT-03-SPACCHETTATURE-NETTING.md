# 03 — Spacchettature, scomposizione e netting

> Torna all'[indice](REGOLE-IMPORT-00-INDICE.md).
> Motore: `importers/situazione_contabile_parser.py` (~4.800 righe), più gli overlay in
> `pdf_importer.py` e `iv_cee_hierarchy.py`.

Questa è la parte del sistema dove si passa da "righe di un elenco conti" a "voci di uno schema
di legge". È anche la parte dove si può sbagliare più silenziosamente: un errore qui produce un
bilancio che **quadra ed è falso**.

## 1. I parser di route C, in ordine di prova

Il primo che riconosce il formato vince (`extract_situazione_contabile`).

| # | Parser | Condizione di attivazione |
|---|---|---|
| 1 | **verifica-segno** | firma specifica; se il testo manca, si tenta l'OCR locale e si accetta solo se anche il testo OCR ha la stessa firma |
| 2 | **AGO / ERP 8 cifre** | "BILANCIO DI VERIFIC" + ≥10 codici a 8 cifre + <5 codici DEPI |
| 3 | **Contrapposte 8 cifre** | "TOTALE A PAREGGIO" + intestazioni ATTIVITA/PASSIVITA + ≥5 codici 8 cifre |
| 4 | **TeamSystem** | "TEAMSYSTEM" + "STATO PATRIMONIALE" + ≥10 codici `XX/YYYY/YYYY` |
| 5 | **Single-column 6 cifre** | "SITUAZIONE CONTABILE" + "TOTALE A PAREGGIO" + "STATO PATRIMONIALE" + <5 DEPI + ≥10 codici a 6 cifre |
| 6 | **Best-effort contrapposte** | non è una situazione contabile riconosciuta, ma il file *è* a sezioni contrapposte |
| 7 | **DEPI flat** | fallback finale |

**Rete di sicurezza**: se dopo tutto il totale attivo è zero e il file è a sezioni contrapposte,
si ritenta il best-effort e lo si tiene **solo se non è vuoto**. È puramente additivo.

**Divieto notevole**: i DEPI a sezioni contrapposte sono **esplicitamente rifiutati** dal
riconoscitore e deferiti all'LLM, perché il parser deterministico non sa riconciliarne i
contro-conti per segno.

## 2. Ricostruzione delle righe

### Come si trova la colonna (il "gutter")

Nei layout a sezioni contrapposte la colonna decide il significato, quindi trovare il confine è
critico. La regola **non è "prendi il gap più largo"**: intestazioni e piè di pagina a destra
creano spazi vuoti spuri che tagliano il documento fra i codici e gli importi, fondendo le due
colonne e facendo bookare i costi come ricavi negativi.

Invece: ogni candidato confine viene **validato operativamente**, rieseguendo la raccolta delle
righe. Vince quello che **massimizza il bilanciamento delle righe con descrizione sui due lati**;
a parità, il più vicino al centro robusto della pagina. Se nessuno è valido → si usa il centro.

### Il secondo passaggio, per le righe senza codice

Alcune verifiche a due colonne sono pulitissime e non hanno codice conto: la riga è
`descrizione importo` e basta ("Cassa 179,90 | Fornitori 296.099,94", budget_367). La raccolta
normale, che pretende un codice in testa, non trova **nulla**. Solo allora — e solo allora, così i
file con codice non possono regredire — la raccolta viene ripetuta in modalità **senza codice**:
ogni riga riceve un codice sintetico che non è prefisso di nessun altro, il gutter si cerca fra le
divisioni possibili scegliendo la più bilanciata, e ciascuna colonna viene troncata al proprio
primo `TOTALE` di sezione — altrimenti su un dump compatto SP+CE in una pagina i conti economici
finirebbero bookati come debiti.

### Ricomposizione degli importi spezzati

Su text-layer corrotti un importo arriva a frammenti. Si concatena e:

1. se corrisponde esattamente al formato italiano → confidenza **esatta**;
2. altrimenti si ripara: si elimina il separatore delle migliaia esposto come cifra isolata
   (**solo** nella forma `3+sep+3+sep+2`), si mappano i glifi confusi (`D/O/Q`→0, `B`→8), e si
   ricostruisce la punteggiatura **dallo stream di cifre** — gli importi italiani hanno sempre
   due decimali. Confidenza **riparata**.

Il suffisso numerico si estende a ritroso finché i token sono numerici (con al massimo 2
lettere, così "BOLLO" non entra) **e si interrompe a un gap oltre i 16 punti**, così un marcatore
di pagina staccato non finisce dentro l'importo.

### Cosa viene scartato

- **Metadati anagrafici** (VIA, PIAZZA, CODICE FISCALE, P.IVA, REA). Regressione nota che
  motiva la regola: "VIA ROMA 162" diventava €1,62 e una partita IVA diventava €19.675.904,96.
- **Riporti** ("A RIPORTO", "SEGUE", "PROGRESSIVO").
- **Righe di controllo** (TOTALE, PAREGGIO, utile): separate e **mai** riclassificate — sono
  evidenza, non massa.
- **Appendici fiscali** ("RIDETERMINAZIONE", "REDDITO IMPONIBILE", "VARIAZIONI IN AUMENTO").
- **Appendici "Dettaglio ratei/risconti"**: portano l'intestazione "Conti Patrimoniali" ma
  **rilistano** frammenti già totalizzati; scansionarle raddoppia la massa (budget_210
  ristampava il fondo ricerca-sviluppo su due pagine). Il match è sul titolo specifico e non
  colpisce mai un prospetto vero.

### Orientamento fisico costi/ricavi

**Non ci si fida dell'ordine testuale delle intestazioni.** L'estrattore può emettere "RICAVI
COSTI" mentre i costi sono fisicamente a sinistra (budget_405). Si contano invece le descrizioni
già classificate su ciascun lato e si confronta l'ipotesi diretta con quella scambiata.

Per **attivo/passivo** invece la regola è opposta e assoluta:

> **La colonna è la verità.** Una riga "BANC…" sull'attivo è cassa, non un credito verso banche.
> Non è ammesso ribaltare il lato in base alla descrizione. È stato tentato ed è stato revertito.

## 3. Netting dei fondi ammortamento

### La regola contabile, e l'errore che previene

Un fondo ammortamento è un **contro-attivo**: va sottratto dall'immobilizzazione, mai iscritto
al passivo. Ma la quota di ammortamento **dell'esercizio** è un costo del Conto Economico, e
**non va mai nettata**: farlo doppia il conteggio (il costo ha già ridotto il risultato) e
produce un valore netto contabile falso.

La distinzione è difesa su **tre livelli indipendenti**:

1. **Strutturale**: la scansione dei contro-conti legge **solo le pagine di Stato
   Patrimoniale**; in modalità OCR il testo viene tagliato all'intestazione "CONTO ECONOMICO".
2. **Lessicale**: un fondo richiede *insieme* un token di ammortamento (`AMMORT`, `AMM.TO`, …)
   **e** un token di fondo (`FOND`, `F.DO`, `F/`). Una quota di CE ("AMM.TO IMPIANTI") non ha
   il secondo e quindi non è mai un fondo.
3. **Prompt**, per il CoGe-LLM: il discriminante affidabile è **la sezione in cui il conto
   compare**, non la sua ortografia — perché il prefisso "Fondo" può essere corrotto dall'OCR
   ("roNDO AMM.TO", "FONDa").

### Split immateriali / materiali

Chi porta un marcatore immateriale va agli immateriali; **tutto il resto va ai materiali per
default** (i caption tangibili non portano marcatori distintivi).

Due trappole codificate:

- Il riconoscimento è **prefix-agnostico**: deve funzionare su `F.DO AMM.TO` *e* su
  `FONDO AMM.TO`. Le vecchie regole vincolate a "F.DO" mandavano LICENZE, CONSULENZE e COSTI
  RICERCA nei materiali (budget_210).
- Nella tabella delle regole **`IMMAT` deve precedere `MATER`**, perché "IMMATERIALI" contiene
  la sottostringa "MATER".

### Fondo svalutazione: quando si netta e quando no

Regola introdotta il 2026-07-14 (budget_210/211, "FONDO SVALUTAZIONE MARCHI"). Un fondo
svalutazione si netta con l'ammortamento **solo se tutte** queste condizioni valgono:

1. contiene "SVALUT";
2. contiene un token di fondo;
3. **non** contiene nessuno fra `CREDIT`, `RIMANENZ`, `MAGAZZIN`, `TITOL`, `PARTECIP` — quelle
   svalutazioni riducono **altre** voci (crediti, rimanenze, titoli, partecipazioni) e restano
   fuori dal netting immobilizzazioni;
4. ha un riferimento **positivo** a un'immobilizzazione. Così un "fondo svalutazione" nudo non
   viene mai nettato per sbaglio.

### Il problema del doppio conteggio padre/figlio

> **Si sommano i mastri oppure le foglie, mai entrambi.**

Un mastro viene scartato quando i suoi figli **diretti** sommano al suo importo entro
`max(€2; 1%)`. Il vincolo "diretti" è essenziale: confrontare contro *tutti* i discendenti
raddoppierebbe su alberi a tre livelli (mastro → intermedio → foglia), e la radice non verrebbe
mai scartata (budget_343/348).

**Ma la parentela non si deduce dal codice.** La regola storica confrontava i prefissi
(`c.startswith(code)`), e su un piano dei conti con famiglie **disgiunte** non deduplica nulla in
silenzio: AGO stampa mastri a 8 cifre (`13095000`) e figli a 9 (`101080000`), e nessuno dei due è
prefisso dell'altro, quindi venivano sommati entrambi. Su `613_2024` questo sovra-leggeva l'attivo
di 41.613,46 (**0,836%**), appena oltre il gate dello 0,5%: il netting diventava un no-op e 2,25 M
di fondi ammortamento restavano fra i debiti con l'attivo lordo — **su un foglio che quadrava**, e
quindi con ogni controllo a valle soddisfatto.

Oggi si enumerano più **partizioni candidate** (tutte le righe; il dedup storico per prefisso; una
per ciascuna profondità osservata) e si tiene quella che riconcilia a un totale **che il documento
ha stampato**, con tolleranza `max(€50; 0,5%)`. La profondità del codice è solo un generatore di
ipotesi: il totale stampato è il giudice. Senza totale dichiarato, o se nessuna partizione
riconcilia, si torna al comportamento storico ma marcato `reconciled=False` — così il chiamante
**sa** che la scansione non è verificata invece di fidarsene.

Due dettagli che sembrano cosmetici e non lo sono:

- la selezione restituisce la **regola vincente**, non la sua etichetta. Un'etichetta verrebbe
  risolta di nuovo sulle righe che le vengono passate, e potrebbe ricadere in silenzio sul dedup
  per prefisso sul lato passivo;
- la usano **entrambi** i consumatori di route C: il netting *e* l'ancora con cui si sceglie fra
  CoGe-LLM e deterministico (pagina 02 §4). Sbagliarla lì non produce un warning: produce **dati
  diversi persistiti**.

Test: `tests/test_dedup_partition.py`.

Regola gemella nella riclassificazione: si emette **una riga al livello più grossolano la cui
descrizione mappa a una voce IV-CEE specifica**, e si scende nei figli solo se la descrizione
del nodo è generica. Un padre classificato *sta per* la somma dei suoi figli.

**Collisione di codici**: due conti distinti che normalizzano alla stessa stringa di cifre
vengono **sommati, mai sovrascritti**. Il vecchio comportamento perdeva massa e gonfiava il
residuo (budget_343/348/342).

**Residuo dei figli**: se i figli raccolti non riconciliano al subtotale del mastro, lo
scarto viene bookato sotto la voce generica del padre — così il subtotale dichiarato è
preservato. È un no-op quando riconciliano.

### I due gate del netting, e il no-op che li segue

Il netting si applica **solo se**:

- **Gate 1**: la massa da nettare supera l'**1%** del totale dichiarato;
- **Gate 2**: il lordo scansionato riconcilia col totale dichiarato entro lo **0,5%**.

Se il gate 2 fallisce si può ancora procedere in **modalità ancorata**, ma solo se: i fondi non
stanno già sul lato attivo (un documento già netto li lista lì, e nettarli di nuovo sarebbe un
doppio netting), ogni massa sta sotto il proprio subtotale stampato, **e** l'evidenza è
affidabile — con uno standard asimmetrico per fonte:

| Fonte | Requisito |
|---|---|
| Text-layer (cattura completa) | basta **un** subtotale stampato |
| OCR scansionato (cattura parziale e stocastica) | servono **tutti e tre**: il grand-total, entrambi i subtotali, e fondi immateriali non nulli |

Se nulla di tutto ciò regge → **no-op**, e l'utente corregge in Rettifiche. Il principio
dichiarato: *mai scrivere un valore netto sbagliato*.

L'ancora dichiarata usa il **TOTALE ATTIVO** prima del pareggio: il pareggio può includere una
perdita parcheggiata sull'attivo e sovrastimerebbe l'ancora (budget_330).

### Compensazione IVA

Si compensa `min(IVA credito, IVA debito)`; la posizione erario netta resta sul lato maggiore.

A differenza della sovrascrittura di immobilizzazioni (idempotente), questo è un **delta**, e
quindi si applica **solo** se il totale è ancora alla magnitudine lorda dichiarata — prova che
nulla è stato già collassato. Un foglio già netto salta il delta.

### Rimozione dei fondi dai debiti, invariante rispetto al bilancio

Si rimuove **esattamente l'eccesso del passivo sul nuovo attivo, cappato alla massa dei fondi**.
La formulazione è scelta perché dà:

- **zero** se l'estrattore aveva già nettato (idempotenza);
- **tutta la massa** se il documento era lordo.

Ordine di prelievo: altri debiti (dove atterrano i fondi misclassificati) → tributari → altri a
lungo, ciascuno specchiato sull'aggregato. Floor a zero ovunque.

### Immobilizzazione netta negativa: vietata

Il netto è sempre clampato a zero. Un fondo non può eccedere il proprio lordo: un netto negativo
è **sempre** una misclassificazione (budget_330/365/435), e un attivo negativo non è mai un
valore IV-CEE valido.

Specularmente, la riduzione dell'ancora è cappata ai lordi presenti: un fondo senza il suo
asset non deve restringere l'ancora.

### L'applicazione è atomica

Il netting scrive su più campi (sp02, sp03, i secchi dei debiti). La fase di scrittura fotografa
il foglio prima della prima modifica e, se qualcosa solleva, **lo ripristina per intero** e si
dichiara `detected > 0 / applied == 0`. Senza questo, un errore a metà lasciava un foglio **mezzo
nettato** che non portava nessuno dei marcatori `_contra_*` — e il motore di affidabilità
(pagina 04 §9) legge quell'assenza come "su questa route non gira nessuna scansione", cioè
declassa in silenzio un foglio corrotto a foglio normale.

## 3-bis. Le grafie: una forma canonica per ogni didascalia

> Motore: `importers/label_semantics.py`, dizionario `data/label_dictionary.json`.

Una voce di legge ha **un** significato e **N** grafie per gestionale: `I. immateriali`,
`I - Immobilizzazioni immateriali`, `B.I IMMOBILIZZAZIONI IMMATERIALI`. L'LLM, che legge il
documento intero, i sinonimi li regge. A rompersi sono i **cancelli deterministici** che stanno
intorno — le ancore di sezione, i totali di controllo dichiarati, il netting dei fondi, il
riclassificatore delle contrapposte — perché sono loro a decidere se **accettare** l'output. Quando
uno di essi non riconosce una grafia, a essere rifiutata è un'estrazione **corretta**.

Coesistevano sei forme normali reciprocamente incompatibili, e una era un difetto vivo: quella del
router, che cercava marcatori non accentati su testo accentato (vedi pagina 01 §2). `normalize_label`
è ora la forma canonica unica: idempotente, e **non inventa parole** (`I. immateriali` →
`immateriali`; espandere alla voce completa è compito del dizionario). Il path civilistico
(`B.II.1.a`) non è rumore: viene estratto in `path_hint` e usato per disambiguare.

Il dizionario ha tre spazi target — **voce**, **marcatore**, **conto** — misurati su un corpus di
72 documenti: prima di questo lavoro i marcatori erano irrisolti al **100%**, i conti al 63%, le
grafie legali al 42%.

Il consumatore che conta di più è `_is_fondo_amm`, che ora riconosce `F.di ammor.to`, `Fdo amm`,
`Fondo amm.` attraverso la forma contigua `fondo ammortamento`. Quella funzione governa **tutto**
il netting di route C: un fondo non riconosciuto non viene sottratto dall'immobilizzazione,
l'attivo resta lordo, e oltre l'1% l'import viene rifiutato. I costi di Conto Economico
("Ammortamento immobilizzazioni immateriali", "Quota ammortamento esercizio") restano
deliberatamente **fuori**: sono costi, non fondi, e nettarli doppia il conteggio (§3).

Test: `tests/test_label_semantics_normalize.py`, `tests/test_label_semantics_spaces.py`,
`tests/test_fondo_amm_grafie.py`, `tests/test_classifier_accenti.py`.

## 4. Tipizzazione dei debiti

### L'ordine delle regole è la regola

Primo match vince, e l'ordine non è negoziabile:

| # | Riconosce | Va in | Perché in questa posizione |
|---|---|---|---|
| 1 | obbligazioni | obbligazioni | — |
| 2 | **altri finanziatori**, soci c/finanziamento, factor | altri finanziatori | **prima delle banche**: la regola generica "FINANZ" ruberebbe "FINANZIATORI" e "SOCI C/FINANZIAMENTO", che sono D.5 e non D.4 |
| 3 | banche, mutui, c/c, scoperti, SBF, anticipi su fatture | banche | include il debito bancario a breve anche quando il nome non porta "BANC" |
| 4 | fornitori, fatture da ricevere | fornitori | — |
| 5 | tributari, erario, IVA, F24, ritenute | tributari | — |
| 6 | previdenza, INPS, INAIL | previdenza | — |
| 7 | *(default)* | altri | acconti, clienti c/, conti terzi |

### Entro / oltre

Dai suffissi `(EE)`/`(OE)` (convenzione AGO) oppure dalle parole ENTRO/OLTRE. **Senza alcun
marcatore, tutto è a breve.** Il parser a colonna unica usa l'unica regola basata sul codice del
file: i prefissi `430`/`440`/`442` marcano il lungo termine.

### Additività garantita

Il residuo fra aggregato e somma dei tipi finisce sempre negli "altri"; se negativo, clamp a
zero. **Invariante fondamentale: i sotto-campi non cambiano mai un aggregato**, quindi non
possono mai cambiare la quadratura.

### L'overlay di tipizzazione

Quando vince l'LLM, che è forte sui totali ma può scaricare l'intera massa dei debiti negli
"altri", si innestano le **proporzioni** del parser deterministico: **il totale è preservato,
cambia solo la ripartizione**.

Conservativo per costruzione: no-op se il vincitore è già tipizzato sensatamente (meno del 60%
negli "altri"), o se il donatore non è significativamente migliore (margine 20%).

### Il rollup degli aggregati debiti — solo route A/B

`sp16`/`sp17` sono **totali derivati dallo schema**: l'art. 2424 elenca ogni sotto-tipo con lo
split entro/oltre ma **non stampa** un "totale debiti a breve". Non essendo mai una riga di
fonte, riallinearli ai dettagli non introduce importi inventati.

**Solo i debiti** vengono rollati. Crediti e riserve no: i loro dettagli possono essere parziali,
e rollarli fabbricherebbe.

**Guardia auto-validante**: la modifica si tiene **solo se lo sbilancio non cresce**. L'LLM può
sbagliare da entrambi i lati — aggregato buono con dettagli sovra-estratti, o il contrario. Un
rollup cieco risolveva budget_585 sul 2024 e ne rompeva il 2025 di circa 127.000 euro.

## 5. Da dove esce il risultato d'esercizio

Ogni parser lo deriva diversamente, e vale la pena saperlo perché spiega molti sintomi:

| Parser | Fonte del risultato |
|---|---|
| DEPI | riga di livello massimo, segno dalla sezione |
| AGO | **ricalcolato** come ricavi − costi (più affidabile delle etichette stampate) |
| Single-column | footer dichiarato, fallback sul gap dei totali |
| Contrapposte 8 cifre | gap fra i totali dichiarati: positivo → perdita all'attivo |
| Best-effort | tre controlli indipendenti; se concordano entro il 5% si usa il dichiarato, altrimenti il gap |
| verifica-segno | ricavi − costi dal CE |

**Regola trasversale**: un conto di patrimonio netto chiamato "UTILE/PERDITA/RISULTATO
D'ESERCIZIO" **non è** il risultato corrente — è quasi sempre quello dell'anno precedente non
ancora destinato. Viene ri-etichettato come riserva. È esattamente il tranello che ha prodotto
il bug budget_211.

## 6. Il flag di autorità

Alcuni parser si dichiarano **autorevoli** e saltano la riconciliazione al dichiarato. Tre
casi, tutti con la stessa motivazione: il lettore generico dei totali dichiarati
*peggiorerebbe* un risultato già corretto.

- **verifica-segno**: questo layout booka il risultato dell'anno *precedente* in un conto di
  patrimonio netto, che il lettore generico scambierebbe per il risultato del periodo,
  sovrascrivendo `sp13` e gonfiando la cassa.
- **ricostruzione gerarchica**: su prospetti a colonne rettificate il lettore generico
  scambierebbe la prima colonna (pre-rettifica) per un anno comparativo.
- **best-effort su testo corrotto**, solo quando i controlli concordano entro il 5%.

## 7. Il rescue gerarchico "4 sezioni"

Si attiva solo se **entrambe**: il residuo supera l'1% (risultato mascherato) **e** il documento
ha una gerarchia di codici puntati.

**Il problema**: le righe di dettaglio più profonde sono stampate con un codice **troncato a una
cifra** (una rata di finanziamento mostrata come `23`), che collide con un numero di mastro e lo
gonfia.

**La soluzione**: un codice senza separatore è un mastro **solo quando i suoi figli puntati lo
seguono prima del prossimo codice senza separatore**, in ordine di documento. Questo rigetta le
foglie profonde troncate.

**Tenuto solo se auto-validante** — entrambe: il lordo riconcilia col TOTALE ATTIVITA dichiarato
entro `max(€50; 0,5%)`, **e** il gap dello SP coincide col risultato del CE. Altrimenti si
restituisce nulla e il best-effort resta invariato: **il rescue non può mai peggiorare un file
già bilanciato**.

Qui è **vietato usare il pareggio** come ancora: su una perdita include la perdita parcheggiata
sull'attivo, mentre i mastri lordi riconciliano correttamente al TOTALE ATTIVITA (343/348).

### Il risultato dell'anno precedente non consolidato

Una verifica spesso **non** consolida il risultato dell'esercizio precedente nei conti di capitale
e riserve: lo stampa come riga a sé, tipicamente **senza codice conto**, nel footer dello Stato
Patrimoniale accanto ai totali ("Utile esercizio precedente 68.228,65"). La raccolta tiene solo le
righe con un codice in testa, quindi quell'importo spariva dal passivo: il gap dello SP
sovrastimava il risultato di periodo **esattamente di quella cifra**, e il secondo cancello di
auto-validazione rigettava una ricostruzione per il resto **esatta** (budget_342: primo cancello
scarto 0,00, secondo fuori di 68.228,65 → ripiego su un best-effort mascherato al 60% → import
fallito con "non supera i controlli contabili").

Ora quell'importo finisce in `sp12` (utili/perdite portati a nuovo). Tre vincoli:

- si raccolgono **solo** le righe senza codice: una riga con codice sta già dentro un mastro di
  livello 1 (es. "23 CAPITALE E RISERVE") e verrebbe contata due volte;
- il segno segue la didascalia (perdita → negativo) e la colonna (lato attivo → negativo, è un
  saldo Dare);
- il risultato **corrente** ("Utile del periodo", "Utile d'esercizio") non è mai agganciato: resta
  la figura di pareggio derivata dal gap Attivo/Passivo.

Le righe si raggruppano per posizione fisica, perché didascalia e importo stanno su due linee di
base diverse (~2 pt). Il tutto resta dietro entrambi i cancelli di auto-validazione, quindi non può
applicare valori sbagliati a un file che già quadra. Test: `tests/test_prior_result_in_pn.py`.

## 8. I quindici divieti

Raccolti perché sono la spina dorsale del sistema. Ognuno esiste per un bug reale.

1. **Mai un plug**: nessuna riga mancante diventa cassa o debito per far quadrare.
2. **Mai fabbricare uno SP** da un documento solo economico → errore esplicito.
3. **Mai un'immobilizzazione netta negativa** → clamp a zero.
4. **Mai nettare le quote di ammortamento del CE** sulle immobilizzazioni.
5. **Mai nettare svalutazioni di crediti/rimanenze/titoli/partecipazioni** sulle immobilizzazioni.
6. **Mai ribaltare il lato attivo/passivo per descrizione** — la colonna è la verità.
7. **Mai sommare mastri e foglie insieme**.
8. **Mai sovrascrivere su collisione di codici** — sommare.
9. **Mai ridurre l'ancora due volte per gli stessi fondi**.
10. **Mai applicare il delta IVA** su un foglio già netto.
11. **Mai scrivere un netting da OCR non corroborato** — no-op, e Rettifiche.
12. **Mai rifiutare un bilancio di verifica leggibile** — si importa sempre, con flag non bloccante.
13. **Mai far arbitrare i totali dichiarati** su testo corrotto.
14. **I sotto-campi non alterano mai un aggregato**.
15. **Mai trattare attivo = passivo = 0 come una quadratura**.

## 8-bis. Dove può finire la massa che non si è saputa classificare

> Implementata in `situazione_contabile_parser` (`TIER0_FIELDS`, `FALLBACK_FIELDS`,
> `fallback_field`, `fallback_bucket`); la soglia di materialità vive in `importers/reliability.py`.
> Questa sezione descrive **il codice**, non la proposta: `SCHEMA-RICONOSCIMENTO-CLASSIFICAZIONE-NETTING.md`
> Parte III/IV la presenta ancora come opzione da valutare, perché è anteriore all'implementazione.

Il divieto 1 (*mai un plug*) non vieta di **etichettare**. La distinzione è tutta qui:

> **Un plug INVENTA massa ed è vietato. Un fallback ETICHETTA massa che è stata davvero letta ed
> è ammesso.**

**Dove non può mai finire — `TIER0_FIELDS`:** `sp02`/`sp03`/`sp04` (immobilizzazioni nette),
`sp11`/`sp12`/`sp13` (patrimonio netto), `sp16a`/`sp17a` (debiti verso banche) e `ce09`. I primi
tre gruppi spostano un **totale**; `ce09` c'è perché `EBITDA = EBIT + ce09` ne fa l'unico confine
di KPI dentro i costi operativi. Un errore qui rompe insieme PFN, ROI, indipendenza finanziaria e
i due modelli di rating.

**Dove può finire — `FALLBACK_FIELDS = {'ce': 'ce06', 'bs': 'sp16g'}`:** destinazioni neutre per i
KPI, e **sempre un sotto-campo esplicito, mai un aggregato**. La ragione è specifica e non ovvia:
`calculations/projection_common.base_bank_debt` assegna alle **banche** qualunque scarto fra
`sp16`/`sp17` e la somma dei loro dettagli, quindi massa lasciata sull'aggregato diventa **debito
bancario fantasma**, con piano di rimborso e oneri finanziari proiettati sopra.

**Quando è silenzioso — la materialità:** `M = max(1.000 €; 0,1% del totale attivo)`. La
definizione canonica sta nel modulo puro `importers/reliability.py` e il parser la ri-esporta, così
la regola esiste in un posto solo. Sotto `M` il ripiego è silenzioso; sopra, l'importo si accumula
in `_unclassified_mass` invece di sparire.

Due funzioni distinte, e il motivo è pratico: `fallback_field(statement)` dà la destinazione dentro
un ciclo di classificazione, che conosce l'importo molto prima che il totale del foglio esista;
`fallback_bucket(...)` aggiunge il verdetto di materialità quando il totale è noto, e **rifiuta**
un target di tier 0.

**L'ordine di classificazione** nella ricostruzione gerarchica è: tabella di keyword → albero
IV-CEE condiviso (attraverso `_resolve_ce_field`, vincolato per direzione) → catch-all. È
puramente additivo, l'albero interviene solo dove la tabella restituisce `None`. È ciò che ha
smesso di seppellire 36.500,17 di ammortamenti nel catch-all `ce12` di budget_342: totali e `sp13`
restavano corretti, **nessun cancello scattava**, e l'EBITDA era sbagliato.

Il criterio di accettabilità che ne discende:

> L'imprecisione **dentro** un aggregato è accettata per progetto — l'utente la rifinisce in
> Rettifiche. Ciò che non è accettato è massa che **attraversa** un aggregato o un confine di KPI.

Test: `tests/test_fallback_bucket.py`, `tests/test_classification_fallback.py`.

## 9. Test di riferimento

- `tests/test_contra_netting.py` — il file di riferimento (668 righe): dedup padre/figlio,
  classificazione dei contro-conti in 8 varianti, split immateriali/materiali, i casi reali
  210/211/613, la modalità OCR, e **cinque no-op** (già netto, senza fondi, scan che non
  riconcilia, senza dichiarati, IVA a un lato solo).
- `tests/test_debiti_rollup.py` — la guardia auto-validante e la non-mutazione dell'input.
- `tests/test_prod_route_c.py` — ground truth campo per campo. La premessa è esplicita:
  *la quadratura da sola non basta, budget_395 quadra con residuo zero e ha `sp02`/`sp03`
  entrambi sbagliati*.

**L'harness di quadratura** (`Test/_quadratura_harness.py`) misura il tasso di quadratura su un
corpus: route deterministiche di default, `--llm` per includere A/B. È lo strumento di riferimento
per il prima/dopo di una modifica all'estrazione — con due avvertenze:

- **`Test/` è in `.gitignore`**: l'harness e il suo corpus sono strumenti **locali**, non fanno
  parte del repository e in un clone pulito non ci sono. Molti documenti di questa cartella li
  citano come se ci fossero;
- un "NO" dell'harness **non** significa "non importa": vedi `docs/FIXING-IMPORT.md` §0. Per
  rispondere a *"la mia modifica ha spostato qualcosa?"* la fonte versionata è la baseline di
  regressione (pagina 06 §7), non una singola esecuzione dell'harness.
