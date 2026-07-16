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

## 9. Test di riferimento

- `tests/test_contra_netting.py` — il file di riferimento (668 righe): dedup padre/figlio,
  classificazione dei contro-conti in 8 varianti, split immateriali/materiali, i casi reali
  210/211/613, la modalità OCR, e **cinque no-op** (già netto, senza fondi, scan che non
  riconcilia, senza dichiarati, IVA a un lato solo).
- `tests/test_debiti_rollup.py` — la guardia auto-validante e la non-mutazione dell'input.
- `tests/test_prod_route_c.py` — ground truth campo per campo. La premessa è esplicita:
  *la quadratura da sola non basta, budget_395 quadra con residuo zero e ha `sp02`/`sp03`
  entrambi sbagliati*.
