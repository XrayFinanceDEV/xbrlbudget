# 02 — Estrazione e scelta dell'estrattore

> Torna all'[indice](REGOLE-IMPORT-00-INDICE.md).
> Motori: `importers/pdf_importer.py`, `importers/pdf_extractor_llm.py`,
> `importers/xbrl_parser_enhanced.py`, `importers/csv_importer.py`.

## 1. La pipeline in fasi

Ordine reale dei fatti per un PDF caricato (`pdf_importer.import_pdf_balance_sheet`):

| Fase | Cosa succede |
|---|---|
| 0 | **Normalizzazione periodo**: `period_months >= 12` diventa "anno pieno" (`NULL`) |
| 1 | Lettura del testo delle prime 14 pagine |
| 1-bis | **Ramo scansione**: OCR locale → OCR vision → rifiuto (vedi pagina 01 §5) |
| 2 | **Routing** (pagina 01). XBRL e UNSUPPORTED escono qui con un errore |
| 3 | **Rilevamento testo corrotto** → esclude i totali dichiarati da ogni decisione |
| 4 | **Estrazione**, biforcata per route |
| 5 | **Identità CE↔SP** — nel PDF `enforce_ce_sp_identity` registra lo scarto senza alterare CE o SP; l'XBRL nativo usa il proprio `check_quadratura` |
| 6 | **Gate strutturale** `validate_balance` → se fallisce, diagnosi motivata (pagina 04) |
| 7 | **Gate contabile** `check_quadratura` → se non quadra, import **non salvato** |
| 8 | Coerenza gerarchica (non bloccante) |
| 9 | Company: verifica proprietà o creazione |
| 10 | **Delete omogeneo**: un import parziale cancella solo parziali, un annuale solo annuali |
| 11 | Hash del file + creazione anno |
| 12 | Scrittura SP e CE (round-trip lossless, pagina 06) |
| 13 | Cross-check finale utile vs `sp13` (solo warning) |
| 14 | **Anno precedente**, con standard di ammissione più severo (§7) |
| 15 | Commit |
| 16 | Esito con metodo di estrazione e confidence |

Qualsiasi eccezione → rollback completo. **Non esistono scritture parziali.**

## 2. Il testo che arriva all'estrattore: l'ordine di lettura

> `page.get_text()` restituisce il testo nell'ordine in cui il generatore lo ha **scritto** nel
> content-stream, che non è necessariamente l'ordine in cui il documento si **legge**.

Su un prospetto comparativo questa non è una differenza estetica, è un errore contabile. Se lo
stream è invertito (righe disegnate dal basso verso l'alto) oppure la seconda colonna importi è
disegnata come blocco staccato, le etichette si legano agli importi della **colonna sbagliata**.
I danni sono due, entrambi silenziosi:

- **anno sbagliato** — la colonna dell'esercizio precedente viene importata come esercizio
  corrente. Nel "Bilancio riclassificato / Fascicolo" la colonna 2024 veniva letta come 2025:
  utile +17.305 al posto della perdita reale −127.995, attivo 1.836.998 invece di 1.758.609;
- **voce sbagliata** — un importo di dettaglio finisce sotto la voce di legge che lo *precede
  nello stream* anziché sotto la propria: gli "altri" oneri finanziari di C.17 attribuiti a
  D.18 Rivalutazioni, +27.777 sull'utile CE.

Solo il secondo caso si manifesta, come "Utile CE ≠ sp13", e viene fermato dal gate contabile
(fase 7). **Il primo, da solo, quadrerebbe perfettamente**: un bilancio dell'anno sbagliato è
internamente coerente. È la ragione per cui il difetto va risolto qui, a monte, e non lasciato
ai gate.

### La regola

Prima di inviare una pagina all'estrattore si misura se lo stream è fuori ordine: si contano i
**salti verticali all'indietro** fra blocchi consecutivi presi nell'ordine di stream. Oltre il
**25% di inversioni**, su almeno 6 blocchi, la pagina viene riletta **ordinata per coordinate**.

Il criterio è deliberatamente geometrico e conservativo — nessuna euristica sul contenuto:

- sulle pagine già in ordine il testo resta **byte-identico** a prima, perché i prompt sono
  tarati su quel testo: chi non è rotto non cambia;
- un salto all'indietro isolato è normale (colonne affiancate, note, intestazioni ripetute) e
  non attiva nulla;
- misurato sul corpus, **212 documenti su 249 non cambiano di un carattere**.

Il riordino è l'**ultima** sorgente di testo in ordine di precedenza. Restano davanti la
ricomposizione delle pagine a valori staccati e il filtro delle colonne DIFFERENZA/SCOST., che
leggono già per coordinate e sanno qualcosa di più del semplice ordine.

### I pre-filtri per gestionale

Sul testo così ottenuto agiscono alcuni pre-filtri, ciascuno legato a una **stampa** e non a
un'azienda: **Zucchetti** (le righe di sottoconto, che in quel layout portano l'importo sulla riga
*precedente*), **Datev/Koinos**, **"Stampa dettaglio voci"** (report ERP con i movimenti di
partitario sotto ogni voce) e il rumore dei separatori **Dylog**. Tolgono righe di dettaglio che
ripetono massa già totalizzata: lasciarle passare la fa contare due volte.

**Le colonne di differenza** (`_filter_difference_columns`) si tolgono per geometria: tutto ciò
che sta a destra della prima intestazione di differenza. Valgono come intestazione «Differenza…»
e «Diff.», solo **a destra** delle colonne-anno (una didascalia del CE come «Differenza tra
valore e costi» sta a sinistra e non taglia nulla), e servono una colonna percentuale («Scost.»
o «%») e almeno due colonne-anno, scritte come anno o come data («30/06/2026»). Prima si
riconoscevano solo «DIFFERENZA» + «SCOST.» con l'anno nudo, e su budget_1445 (Crystal Reports,
«Diff. %» / «Diff. Valore») il Totale Attivo dichiarato era la Diff. Valore: 2.464.126,25 contro
27.190.388,86, con attivo e passivo «in pari» sulla differenza. Il testo così ricomposto mette
l'importo della sezione sulla stessa riga della sua intestazione, quindi `_section_heading_total`
accetta anche «Stato patrimoniale attivo 1.250.311,33 1.314.938,83» (BILAQ).

## 3. Route A/B (IV-CEE): il deterministico prima, l'LLM solo se serve

1. **Parser deterministico per primo**, e gratis. Il suo output è accettato **solo se** supera
   *entrambi* `validate_balance` e `check_quadratura`. Se passa, nessuna chiamata API.
2. Altrimenti serve la chiave API, altrimenti errore.
3. **Se il documento è infrannuale** si va direttamente all'estrazione a due anni: il motore di
   confronto pretende i due anni accoppiati.
4. **Anno pieno**: l'anno corrente si prende dal pass a singolo anno (più affidabile), l'anno
   precedente dal pass a due colonne. Se il corrente single-year non quadra e quello dual sì,
   vince il dual.
5. **Retry stocastico**: fino a 3 tentativi, si ferma appena corrente e precedente quadrano
   entrambi; conserva comunque il miglior tentativo.
6. **Overlay finale**: se dopo 3 tentativi non quadra ancora, si sovrascrivono **solo gli
   aggregati patrimoniali** con quelli del parser deterministico, e **solo se il risultato
   quadra**. CE e dettagli tipizzati restano quelli dell'LLM.

**Anche il ramo testuale di route A/B può girare su Qwen locale.** `PDF_LLM_PROVIDER_IVCEE=gx10`
sposta sia l'estrattore testuale (`extract_pdf_with_llm`, `extract_pdf_both_years_with_llm`, i
punti 1-6 sopra quando serve l'LLM) sia la lettura delle macro-voci (`read_macros`) su gx10.
`PDF_LLM_PROVIDER_DETTAGLI=gx10` sposta la seconda lettura — `read_details`/`read_accounts`,
celle di dettaglio della nota integrativa e classificazione dei sottoconti — sullo stesso gx10,
indipendentemente da `PDF_LLM_PROVIDER_IVCEE`. **La vision resta su Anthropic in ogni caso**: un
PDF senza text layer, con uno dei due fornitori impostato su `gx10` e senza
`ANTHROPIC_API_KEY`, solleva un errore dichiarato invece di chiamare gx10 su un'immagine — gx10
qui legge solo testo. Il fornitore usato si persiste in
`FinancialYear.validation_report["ivcee_provider"]`/`["dettagli_provider"]`, su **ogni** route
(anche C, accanto a `coge_provider`), anno corrente e precedente.

## 4. Route C: la scelta del candidato è la regola più importante

Due candidati concorrono: il **CoGe-LLM** e il **parser deterministico**. Il deterministico gira
sempre, perché è gratuito e non può peggiorare il risultato.

**Il pass CoGe può girare su Qwen locale (gx10)**, con `PDF_LLM_PROVIDER_COGE=gx10`, invece che
su Claude Haiku. Stesso prompt e stesso schema Pydantic, usati come vincolo di decodifica invece
che come tool forzato di Anthropic. La vision resta su Anthropic in ogni caso: un PDF senza text
layer con gx10 e senza chiave Anthropic solleva un errore dichiarato, e route C tiene il candidato
deterministico. Un guasto di gx10 qualunque — rete, timeout, risposta fuori schema — è preso dal
try/except già esistente, e route C ripiega sullo stesso modo: il deterministico. Il fornitore
usato si persiste in `FinancialYear.validation_report["coge_provider"]` (anno corrente e
precedente).

Il CoGe-LLM **non** viene lanciato se l'OCR locale a coordinate ha già letto il file: sarebbe
aggiungere un candidato stocastico a una lettura deterministica riuscita.

### Perché non si sceglie guardando il residuo

Sembrerebbe naturale preferire il candidato con meno massa non classificata. **È sbagliato, e
capirlo è la chiave di tutta la route C.**

> Il residuo è **cieco alla sotto-estrazione**. Un estrattore che perde un intero blocco di
> conti e poi forza il pareggio attraverso il risultato d'esercizio produce un residuo vicino a
> zero: sembra *più pulito* del candidato corretto, e ha perso metà del bilancio.

Il caso di riferimento è AITEC PROVVISORIO: il CoGe-LLM produce un totale di 9,92 milioni
contro i 12,65 milioni **stampati dal documento**, con residuo minimo. Il deterministico, che si
ancora al totale stampato, è quello giusto.

### La regola effettiva

Si ordina per **(distanza dal totale dichiarato, poi residuo)**:

1. Si legge il totale che **il documento stampa da solo** (pareggio, o passivo, o attivo).
2. Si misura la distanza di ogni candidato da quel totale.
3. **Sotto il 2% la distanza è considerata rumore e azzerata** — così una piccola differenza di
   lettura non scavalca mai lo spareggio sul residuo.
4. A parità, vince il residuo minore.

Se il testo è corrotto, il totale dichiarato **non viene usato affatto**: sarebbe spazzatura.

### La correzione lordo→netto dell'ancora

Su un bilancio a presentazione **lorda** il pareggio stampato include i fondi ammortamento (che
compaiono su entrambi i lati) e l'eventuale perdita parcheggiata all'attivo. Confrontare un
candidato correttamente **nettato** con quell'ancora **lorda** lo penalizza e fa vincere il
candidato non nettato (budget_343/348). Quindi l'ancora viene ridotta di fondi + compensazione
IVA + perdita dichiarata, ma **solo se i fondi superano l'1%** dell'ancora stessa.

### Cosa succede dopo la scelta, nell'ordine

1. **Tipizzazione debiti in overlay** — solo se ha vinto l'LLM (pagina 03 §4).
2. **Netting fondi ammortamento** — sul candidato scelto, chiunque l'abbia prodotto (pagina 03 §3).
3. **Riconciliazione al risultato dichiarato** — saltata se il parser si dichiara autorevole.
4. **Riscatto vision della sezione che non torna** — solo con chiave API (§4-bis).
5. **Warning sul residuo** — mai bloccante.

## 4-bis. Il riscatto vision per sezione

> Motore: `importers/vision_rescue.py` + `situazione_contabile_parser.build_sp_from_vision` /
> `build_ce_from_vision`. Introdotto il 2026-08-14.

Il terzo candidato di route C non è un estrattore alternativo: è un **riscatto**, prodotto solo
su richiesta e solo per la sezione che non torna. Il caso che lo motiva è preciso: **il numero
giusto è stampato sulla pagina, ma il text layer non ci arriva**. Su budget_624 i mastri di costo
dell'ultima pagina di CE sono disegnati come *vettori* e in `page.get_text()` non esistono affatto.

**Quando scatta.** Alla **fine** della catena — dopo tipizzazione, netting e riconciliazione al
dichiarato — quando `check_quadratura` sul foglio *finito* dice vuoto, sbilanciato, mascherato, o
con utile CE diverso da `sp13`. La posizione in coda è deliberata: innescarlo prima del netting lo
farebbe scattare su un attivo ancora lordo, cioè su un divario che il netting chiude da solo.
L'innesco è **gated sulla chiave API**: senza chiave non si parte nemmeno, perché le pagine
verrebbero rese a 200 dpi per poi essere buttate.

**Che cosa legge.** Le sole pagine della sezione mancante (`situazione_contabile_parser.section_pages`),
rese a 200 dpi e rilette in vision con i due prompt CoGe distinti SP/CE. Un solo tentativo per
sezione, tetto di **8 pagine**, ogni errore non fatale: se il riscatto non riesce il foglio resta
esattamente com'era, coi suoi warning. Le due sezioni si innescano in modo indipendente, e il
riscatto del CE non tocca `sp13` come quello dell'SP non tocca il conto economico.
Costo misurato: ~4.500 token in, 1.000-2.000 out, 8-16 s per sezione.

**Solo i mastri, e la sezione si ricostruisce da zero.** I dettagli a codice più lungo la vision li
sbaglia e non servono: il mastro porta già l'intero importo della voce. La sezione riscattata
**sostituisce** quella estratta, non le si somma — sommare richiederebbe di sapere che cosa c'era
già dentro, e conta due volte un mastro (è l'errore che fece revertare il tentativo del 14/07).

**Il livello dei mastri si sceglie per riconciliazione, non per profondità** (`mastro_level_rows`).
La profondità del codice genera le ipotesi; il **totale di colonna stampato** è il giudice — la
stessa regola di `_select_dedup` (pagina 03 §3). Prendere il minimo di cifre e basta si è rotto sul
file vero: la vision trascrive i peer di uno stesso livello con un numero di cifre diverso
(`7301500` accanto a `73015005`), e il minimo scartava due mastri buoni per 46.110,67. Senza totali
leggibili, o se nessuna partizione riconcilia, resta il minimo e a decidere è il cancello.

### Il reintegro dal text layer (`close_gaps`, `find_gap_closer`)

> Aggiunto il 2026-08-15, fra la lettura e il cancello.

La vision salta a intermittenza una riga, e **la tolleranza del cancello può essere più larga
della riga saltata**: il riscatto passa allora *col buco dentro*, e quel buco diventa lo
sbilancio finale. Misurato su budget_623: colonna destra ricostruita 2.445.907,88 contro i
2.454.987,65 stampati, divario **9.079,77** = `37060000 Debiti v/istit.prev.e sicur.sociale`,
che la vision non trascrive e che il text layer di pagina 1 invece porta. La tolleranza su quel
totale vale 12.274,94, quindi il divario passava indisturbato.

Prima del cancello, per **ogni colonna** di ogni sezione riscattata, si misura il divario dal
totale letto e si cerca nel testo delle stesse pagine una riga che lo spieghi. **Non è un plug**:
non inventa massa, la ritrova in una fonte che l'aveva letta. Tre condizioni, tutte necessarie:

| # | Condizione |
|---|---|
| 1 | l'importo spiega il divario **al centesimo** — nessuna tolleranza: un centesimo di scarto e non è quella riga |
| 2 | il codice non è già fra quelli letti in vision — ripescarlo lo conterebbe due volte, l'errore del 14/07 |
| 3 | la descrizione si classifica in modo **specifico sul lato chiesto** — la colonna resta la verità sul lato, e un importo che coincide per caso con una riga dell'altro lato si scarta, mai si ribalta |

**Il classificatore dipende dalla sezione, e non è un dettaglio.** Sul CE si usa
`_resolve_ce_field(desc, direction)`, mai `classify_attivo`/`classify_passivo`: su un nodo CE il
lato non filtra nulla, un costo può risolversi su un ricavo e il risultato si sposta di **2×** il
suo importo. È lo stesso resolver, e la stessa ragione, della regola generale di pagina 03.

Se restano più candidati con codici diversi si tiene il **livello mastro** (codice più corto),
come `mastro_level_rows`; se l'ambiguità resta, si rinuncia. Rinunciare significa il
comportamento precedente, che è sempre ammissibile.

**Limite dichiarato: il reintegro chiude una riga per colonna, non una combinazione.** Se la
stessa lettura salta *due* righe, il divario è la loro somma, nessuna riga singola lo spiega, il
reintegro rinuncia e il cancello rifiuta — il file resta com'era. Su budget_623 il caso è
`139.079,77 = 130.000,00 + 9.079,77` (`31030005 Riserva contributi c/capitale` più i debiti
previdenziali). Cercare le combinazioni riaprirebbe il rischio di doppio conteggio per un
guadagno non misurato, quindi non si fa.

**Effetto misurato** (tre esecuzioni del percorso di produzione per file, dopo): budget_623
passa da «2 su 3 con 9.079,77 di sbilancio, 1 su 3 mascherato» a **3 su 3 con sbilancio 0,00**;
budget_624 resta identico. L'obiettivo 2 della spec del riscatto — dichiarato incerto quando fu
scritta — si chiude qui.

### Il cancello (`accept_rescue`)

Il riscatto si tiene solo se valgono **tutte**:

| # | Condizione |
|---|---|
| 1 | la **colonna di sinistra** ricostruita riconcilia al totale stampato entro `max(50 €; 0,5%)` |
| 2 | la **colonna di destra** fa altrettanto contro il proprio totale stampato, quando la quantità è misurabile — **saltata sul percorso CE**, che non la passa |
| 3 | l'estrazione non è vuota |
| 4 | il riscatto non spegne un'identità utile CE = `sp13` che prima reggeva |
| 5 | la quadratura risultante è **strettamente migliore**, misurata come la somma dei valori assoluti di sbilancio e residuo (sono la stessa specie di male e si sommano) |

Il cancello riceve una bandiera **`residual_measured`**: il residuo del foglio riscattato è una
*misura* solo se esisteva un'ancora di testo indipendente contro cui farla. `build_sp_from_vision`
**asserisce** `_plug_residual = 0`, non lo misura, e un controllo che manca non è un controllo
superato: in quel caso si porta avanti il residuo di prima. È la stessa regola di
`importers/reliability.py` — un verdetto vuole una contraddizione, non l'assenza di prove.
Riparare l'identità CE/SP è un miglioramento reale ma non una licenza illimitata: ha per tetto la
stessa tolleranza di riconciliazione.

**La coerenza dei totali vision NON è una condizione del cancello.** Serve solo a scegliere quale
ancora usare: `section_anchor` preferisce il totale letto in vision quando i totali vision tornano
fra loro (`attivo + perdita == passivo`, `costi + utile == ricavi`), e altrimenti ricade sulle
ancore di testo. Su un riscatto **CE** con totali incoerenti l'incoerenza in sé non scarta nulla:
restano da superare la riconciliazione sull'ancora di testo e le altre condizioni. Sul percorso
**SP** la coerenza è necessaria di fatto, ma per un motivo diverso e altrove: `pdf_importer`
rinuncia al riscatto quando `vision_result` è nullo, perché senza un'identità che torni il segno
del risultato sarebbe da indovinare — quindi una sezione SP incoerente non arriva mai al cancello.

**Perché il passivo ha bisogno della sua ancora** (condizione 2, aggiunta il 2026-08-14). Misurando
la sola colonna di sinistra, questo riscatto poteva produrre un foglio **sbagliato** invece che
incompleto: quando `net_contra_accounts` ha una scansione disponibile su quel file, una sovra-lettura
del passivo non si vede nello sbilancio, perché a valle viene **assorbita** cancellando debiti fino
alla massa dei fondi. Il foglio torna a quadrare, il residuo va a zero, il cancello vede un riscatto
perfetto — e il debito persistito resta sottostimato senza un solo avviso.

> **Su budget_623, però, quel meccanismo non può scattare, e conviene registrarlo perché è stato
> raccontato al contrario.** Su quel file `_contra_rows` **non trova nulla da leggere** — verificato
> con i totali dichiarati reali, con `text=None` e con il testo PyMuPDF — quindi
> `net_contra_accounts` esce subito con `_contra_reason='scan non disponibile'` e netta zero. Non
> c'è alcuna massa di fondi che possa assorbire una sovra-lettura: lì una lettura in eccesso del
> passivo resta un **semplice sbilancio visibile**, già catturato dalla condizione 3 del cancello.
> Una versione precedente della documentazione attribuiva a questo file 289.788,03 di fondi
> ammortamento nettati: su budget_623 il netting non parte nemmeno.

La quantità misurata dalla condizione 2 è
costruita per essere confrontabile con il totale *stampato*: `totale_passivo − utile + massa nettata`
(il risultato è esposto dal documento come riga di pareggio fuori dal totale di colonna; i fondi sono
righe della colonna destra che la ricostruzione porta in detrazione dell'attivo).

**Il segno del risultato viene dall'identità che ha validato i totali**, non dall'ordine delle
chiavi: un documento stampa spesso sia una riga "utile" sia una "perdita" (una delle due dell'anno
precedente, o una didascalia a zero), e preferire l'utile ribalta il risultato quando è il ramo
della perdita a tornare.

### Le due regole di merito della ricostruzione

**Scadenza non determinata → a breve, per prudenza.** Di norma i mastri non dicono se un debito è
entro o oltre l'esercizio (fa eccezione la verifica «Mastri», dove il mastro dichiara «ESIG.OLTRE 12M» e i
suoi conti ereditano la scadenza, `_entries_da_righe_verifica`). In assenza di un segno che li distingua i debiti vanno **a breve**: anticipare
una scadenza peggiora gli indici di liquidità e non li abbellisce, ed è l'utente a spostarli in
Rettifiche quando sa che sono a lungo. Non è un ripiego dell'estrattore vision, è la regola del
progetto (la segue anche il best-effort di route C, che pure emette solo `sp16`). La ricostruzione
alza `_source_maturity_unspecified`, che l'import espone come `SCADENZA DEBITI NON DISTINTA`:
**è una stringa di avviso, non un verdetto** — nessun cancello la legge, né qui né a valle, e non
deve leggerla, perché un import prudenzialmente a breve è valido, non sospetto.

**Il ripiego del CE si sceglie per direzione.** La destinazione neutra `ce06` (pagina 03 §8-bis) è
neutra solo *dentro* i costi della produzione: su una riga della colonna RICAVI è un costo, e la
massa non riconosciuta sposta il risultato di **2×** il proprio importo. A destra si tiene il
default del classificatore (`ce04`), che è del segno giusto. Su budget_624 ci finivano rimanenze
finali e proventi finanziari letti a destra (1.479.943,47) e il CE chiudeva a 0,00 invece che a
8.906,79.

**Immobilizzazione netta negativa: azzerata, e la correzione parla.** Quando un fondo letto supera
il proprio cespite lordo, `sp02`/`sp03`/`sp04` risulterebbero negative — mai un valore IV-CEE
valido. Vengono azzerate, ma poiché sono campi di tier 0 la correzione **logga a warning** campo e
importo e somma l'eccedenza tagliata a `_unclassified_mass`. Quella chiave è dichiarata **sempre**,
anche a zero: `reliability.assess` la legge, e una chiave assente lì vale zero — un foglio
riscattato si sarebbe dichiarato pulito solo perché il montatore vision non aveva un secchio.

Provenienza: pagina 06 §2. Test: `tests/test_vision_rescue.py` (unitari con doppio, più i due PDF
veri, gated su chiave e sulla presenza del documento), `tests/test_section_pages.py`. Il caso reale
dei due file è in `docs/FIXING-IMPORT.md` §6.

## 5. L'LLM: cosa, quanto, quando

Modello **Claude Haiku 5.5** (`claude-haiku-5-5`, `PDF_LLM_MODEL`, sovrascrivibile da ambiente;
dal 2026-10-14, prima Haiku 4.5), senza `temperature` (il modello la rifiuta con un 400), 8192 token di output, chiamato con
**tool-use forzato** e schema derivato dal modello dati: il modello non produce prosa da
parsare, riempie campi tipizzati. Retry con backoff esponenziale, massimo 2, sugli errori 500.

**Quando NON viene chiamato** (cioè quando l'import è gratuito):

- route A/B, anno pieno, e il parser deterministico quadra;
- route C con OCR locale a coordinate riuscito;
- route C senza chiave API (si usa il solo deterministico, senza regressione);
- route XBRL o UNSUPPORTED (si esce prima).

**Quante chiamate, quando viene chiamato:**

| Scenario | Chiamate |
|---|---|
| Infrannuale | 2 (SP + CE, due anni insieme) |
| Anno pieno A/B, primo tentativo pulito | 4 |
| Anno pieno A/B, caso peggiore | 12 |
| Route C con chiave API | 2 |
| PDF scansionato | +1 di OCR vision |

La giustificazione dichiarata è che l'import di un PDF è un'operazione rara e le chiamate Haiku
costano poco. In tempo: **3-10 secondi** per PDF sul percorso normale.

### I due anni

Una singola coppia di chiamate estrae entrambe le colonne. Due guardie simmetriche:

- **colonna precedente assente** → il "precedente" è un clone fabbricato: si svuota, ma **non**
  si esce (i validatori devono comunque girare sull'anno corrente);
- **colonna corrente azzerata** e precedente valorizzato → si **promuove il precedente a
  corrente**.

## 5-bis. MinerU: l'OCR opzionale, su gx10 e non sul VPS

> Motori: `importers/mineru_adapter.py`, `backend/app/services/mineru_client.py`, configurazione
> in `backend/app/core/config.py`. Endpoint dedicato: `POST /import/pdf-ocr`.

Backend OCR alternativo per i PDF scansionati che il text layer non riesce a leggere. È un
**percorso separato** da quello descritto a pagina 01 §5 (OCR locale a coordinate → OCR vision),
con un endpoint proprio.

> ⚠️ **Il container MinerU non va MAI sul VPS.** La sua immagine è
> `FROM vllm/vllm-openai`: gigabyte di layer orientati alla GPU. Il servizio sta dietro il
> **compose profile** `mineru`, che lo esclude da *ogni* comando compose — **`build` compreso** —
> se il profile non viene richiesto. È ciò che conta, perché il `Jenkinsfile` esegue
> `docker compose build --no-cache --parallel` e poi `up -d` sul VPS di staging: senza il profile
> quel build si tirava dietro vLLM.

**Sui VPS MinerU è quello di gx10** (2026-10-14): `https://kpsfinanciallab.w3pro.it:89`, un proxy
nginx con allowlist dei soli IP di staging e produzione e header obbligatorio `X-Api-Key`
(`MINERU_API_KEY`); al massimo 3 richieste concorrenti, le altre in coda. Dalla LAN dell'ufficio lo
stesso servizio risponde senza chiave su `http://192.168.1.137:18400`. Si accende dalla credenziale
Jenkins `budget-env-staging`:

```
MINERU_OCR_ENABLED=true
MINERU_BASE_URL=https://kpsfinanciallab.w3pro.it:89
MINERU_API_KEY=<chiave>
MINERU_EXPECTED_VERSION=4
```

**Dal 2026-10-26 gx10 serve MinerU 4 (4.0.12, il VLM)**, con un'API diversa da quella di prima:
`GET /v1/health` (`status: "ok"`) e `POST /v1/file_parse?tier=advanced&ocr_mode=ocr&output_formats=markdown&output_formats=middle_json&wait_timeout=…`,
PDF in multipart `files`. `advanced` è il VLM, l'unico che fa quadrare le scansioni (`MINERU_TIER`;
`flash` legge solo il text layer). Il server tiene aperta la richiesta per `wait_timeout` secondi (50,
`MINERU_WAIT_SECONDS`: sui VPS la POST passa dal proxy nginx di gx10, e un'attesa oltre il suo
timeout di lettura tornerebbe 504); un lavoro ancora in coda risponde **202** con `task_id` e il client interroga
`GET /v1/tasks/{task_id}/result` ogni 3 secondi fino al 200, entro `MINERU_TIMEOUT_SECONDS` in
tutto. La coda pesa più dell'analisi: su Unicarton 31/08/2026, 3 minuti e mezzo di attesa per 2 di
lettura. Il risultato porta `files[0].content.markdown` e `files[0].content.middle_json.pages[]`,
con il numero di pagina sulla pagina e non più su ogni blocco: `mineru_client._blocchi_da_pagine`
lo riporta alla lista piatta di blocchi con `page_idx` che l'adapter legge da sempre, quindi adapter
e lettori a valle non sono cambiati. Le rotte vecchie (`/health`, `/file_parse`) rispondono 404, e
con il client di prima ogni scansione ripiegava in silenzio sull'OCR di riserva («OCR MINERU NON
DISPONIBILE»).

`MINERU_EXPECTED_VERSION` fissa **solo i componenti che scrive** (`versione_compatibile`): `4`
accetta ogni 4.x, `4.0.12` solo quella. Un pin esatto faceva ripiegare ogni import a ogni rilascio
minore di gx10; il contratto cambia col numero maggiore. Il container locale del profile `mineru`
(immagine 3.2.0, sotto) parla ancora l'API vecchia e **non** risponde più al client.

**Sulle situazioni contabili a sezioni contrapposte niente modello** (decisione del proprietario,
2026-10-14). Se le tabelle di MinerU hanno quella forma — didascalia stato patrimoniale / conto
economico, righe a sei celle conto-descrizione-importo per lato — `importers/mineru_contrapposte.py`
le stampa su un PDF sintetico con la forma di un bilancio di verifica, e la route C lo fa leggere al
lettore deterministico di sempre (netting dei fondi, gerarchie, totali, eccedenza dell'anno prima).
Il pass CoGe su Qwen, il riscatto vision e la ricerca dei dettagli non girano; i controlli
dichiarativi a valle (totali, fondi da nettare, utile) leggono il PDF sintetico, che porta le stesse
righe di piede del documento. `extraction_method` = `situazione_contabile_mineru`,
`validation_report.mineru_contrapposte = true`. Unicarton 31/08/2026 reso a sole immagini: al
centesimo in 1,5 secondi, contro 8,5 minuti e 315 mila di sbilancio della lettura CoGe sul testo
OCR. Qwen resta solo per tabelle che non hanno quella forma. Il limite è l'OCR: se MinerU perde
una colonna (la copia ripassata da PDF24 di Unicarton perde i ricavi), l'import la dichiara come
`Utile CE != sp13`, non la inventa.

**Sugli schemi di legge scansionati niente modello** (2026-10-26, con MinerU 4). Una scansione di
schema di legge non è a sezioni contrapposte: il percorso snello si dichiara `non_applicabile` e in
`_llm_extract` si provano, in ordine, il lettore col percorso nell'etichetta (`estrai_da_mineru` di
`schema_etichette_parser`, sotto) e **il lettore dello schema di legge generico sulle stesse
tabelle** (`schema_legge_generico.estrai_da_mineru`, `_schema_generico_mineru_extract`): le celle
di MinerU danno le stesse righe grezze che `_grezze_pdf` ricava dalla geometria (didascalia, un
importo per colonna-esercizio, gli anni dall'intestazione «31-12-2025»), e da lì valgono le stesse
regole e gli stessi controlli al centesimo del cuore XBRL (`_righe_da_grezze`,
`xbrl_reso_parser.estrai_da_righe`, adozione con `_adotta_candidato_reso`). Una tabella che si
intesta da sé con date dopo una didascalia (la nota «Varie altre riserve» in mezzo al prospetto)
non è il prospetto; il richiamo di nota in coda a un importo («220.159 (1)») si toglie. Prima
questa famiglia finiva sull'estrattore Anthropic, vietato, cioè su un errore: budget_1322 (schema
reso da XBRL e poi scansionato) ora si importa in meno di un secondo, coi due esercizi, voce per
voce uguale all'unità di euro a 1319, lo stesso bilancio al centesimo. Con le tabelle di MinerU
3.4.5, che sfasavano righe e colonne, lo stesso lettore lo **rifiuta**: un importo letto male
produce un rifiuto, mai un numero sbagliato.

Le tabelle della nota con le scadenze («Quota scadente entro/oltre l'esercizio») vengono anch'esse
dalle celle di MinerU (`xbrl_reso_parser.raccogli_tabelle`, parametro `tabelle_nota` di
`estrai_da_righe`): senza, crediti e debiti di un abbreviato restavano tutti in «altri»
(budget_173). Su budget_201 la scansione dà un dettaglio **migliore** del testo: `find_tables` di
PyMuPDF spezza «28.371» in «7 28.371» e la tabella non si applica, MinerU la legge pulita.

Con MinerU 4 **una cella vuota è un esercizio senza importo**: il lettore col percorso
nell'etichetta legge per posizione quando ogni cella è vuota o un importo intero e la Differenza
stampata, se c'è, lo conferma (`_ricomponi`). La ricomposizione che salta le celle vuote era per le
celle sporche della 3.4.5, e su «D.6) Acconti | | 3.000,00» dava all'esercizio i 3.000 dell'anno
prima (budget_283).

**Il prospetto CEE sintetico a una colonna** si legge dalle celle come dal testo
(`prospetto_sintetico.estrai_da_mineru`, `_prospetto_sintetico_mineru_extract` dopo lo schema
generico): stesse verifiche dello snello (`deterministico._esito`), stesso avviso «PROSPETTO
SINTETICO» (`_approssimazioni_prospetto`), `extraction_method` `prospetto_sintetico` (budget_1405).

**Le contrapposte AGO** (budget_330): il titolo sta in un'altra tabella e la sezione si riconosce
dall'intestazione dei lati («ATTIVITA' | PASSIVITA'», «COSTI | RICAVI»); codice e descrizione
stanno in una cella sola («13005000 - Costi di impianto…») e la riga a quattro celle torna a sei,
col lato della colonna d'origine (`_sei_celle`); i codici a 5-8 cifre e i sottoconti «100045 000»
sono codici (`_CODICE`). Nel PDF sintetico la descrizione si stampa **per intero**, rimpicciolita se
serve: troncata a 38 caratteri perdeva la coda, dove AGO stampa la scadenza («Debiti verso soci per
finanziamenti (OE)»), e 256.050 di finanziamento soci cadevano a breve. I codici a 6 cifre di
budget_337 ora ricostruiscono la gerarchia: il mastro «FONDI DI AMMORTAMENTO» (62.045,10) si netta
dai cespiti invece di restare fra gli altri debiti, come fa la lettura dal suo testo OCR. Una tabella
di righe «voce | importo» **senza codici di conto** non è una situazione contabile
(`pdf_da_tabelle`): presa per tale, budget_1405 passava 14 secondi su Qwen prima del lettore giusto.
Punto aperto: su budget_337 il conto «FINANZ. VOLKSBANK» sotto il mastro «FINANZ.TI A MEDIO LUNGO
TERMINE» va a breve, perché il lettore scende nel conto e la scadenza dichiarata dal mastro si perde
(lo faceva anche prima).

Sui tre schemi letti dalle tabelle MinerU **la ricerca dei dettagli non gira**
(`_dettagli_gia_letti`, motivo `dettagli_letti_dallo_schema_mineru`): il lettore ha già
verificato ogni dettaglio sul suo totale stampato. Col testo pulito di MinerU 4 quella ricerca
partiva su Qwen e ne respingeva ogni proposta: budget_1319 passava da 6-9 a 70-115 secondi, con
otto avvisi «DETTAGLI NON APPLICATI» su un foglio già dettagliato.

Il compose **non** dichiara alcuna `MINERU_*` in `environment:`: una voce lì scavalca `.env.docker`,
e fino al 2026-10-14 inchiodava `MINERU_BASE_URL` a `http://mineru:8000`. Senza variabili l'OCR è
spento (`MINERU_OCR_ENABLED` vale `False` di default in `config.py`).

In locale, col container: `.env.docker` con `MINERU_OCR_ENABLED=true` e
`MINERU_BASE_URL=http://mineru:8000`, poi

```bash
docker compose --profile mineru up -d
# con NVIDIA:
docker compose --profile mineru -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

Con l'OCR spento il backend è indifferente: `mineru_client` e `mineru_adapter` sono importati
**dentro** l'endpoint e mai a caricamento del modulo, `GET /import/capabilities` risponde
`ocr_available: false`, e `POST /import/pdf-ocr` restituisce un 503 `MINERU_DISABLED` pulito, reso
dall'interfaccia come *"Il servizio OCR non è disponibile — usa l'import PDF standard"*.

**Nell'interfaccia il pulsante OCR non è reso** (2026-08-14): è una rimozione semplice, **non** un
controllo di capability. `getImportCapabilities` esiste in `frontend/lib/api.ts` e non è cablato a
nulla — non cercare il cancello che nasconde il pulsante, non c'è. Il percorso client è intatto
(`importOCR`, `handleImport("pdf_ocr")`): riesporlo significa rimettere il pulsante, non
ricostruire il ramo.

Test: `tests/test_mineru_adapter.py`, `tests/test_mineru_client.py`,
`tests/test_mineru_import_integration.py`, `tests/test_pdf_ocr_endpoint.py`. Piano di
integrazione: `docs/piano-import-2026-07/14-PIANO-INTEGRAZIONE-MINERU-OCR.md`.

## 6. I totali di controllo dichiarati

Sono i totali che il documento **stampa da solo** — l'unica evidenza indipendente
dall'estrattore, e per questo l'ancora di tutto il sistema anti-masking.

Regole di lettura non ovvie:

- Robusto a intestazioni spaziate e ad accenti.
- Per ogni etichetta si prende **il valore più grande**: le righe di dettaglio ripetono importi
  parziali, il totale è il massimo.
- **Il pareggio si cerca solo prima dell'intestazione "CONTO ECONOMICO"**. Il pareggio è
  stampato sia per lo SP che per il CE, e "il più grande vince" assumeva che l'SP fosse sempre
  il maggiore. È falso su aziende ad alta rotazione e basso margine: in budget_337 il CE
  (372.733) supera l'SP (315.121), e senza questo vincolo tutto veniva ancorato al CE.
- Il recupero geometrico del risultato è accettato **solo** se la riga esprime un unico importo
  e se lo stesso valore compare su almeno due righe; gli "utili portati a nuovo" sono
  deliberatamente esclusi.
- L'utile e la perdita dichiarati sono **in valore assoluto** (`_largest_after`): il segno non
  si legge da qui.

### La riconciliazione al dichiarato non muove massa

Espone differenze diagnostiche e **non tocca alcuna voce**. Ha due sole intelligenze:

**Arbitraggio del segno del risultato.** Un bilancio di verifica può stampare *sia* un "utile"
*sia* una "perdita", oppure un "RISULTATO D'ESERCIZIO" che è in realtà il conto di patrimonio
netto dell'anno **precedente** (budget_211). Preferire ciecamente l'utile sbaglia il segno. Si
arbitra col gap contabile: quando il passivo esclude il risultato, `attivo − passivo` **è** il
risultato firmato. Vince il candidato più vicino. Un risultato CE pari a zero è trattato come
"nessuna ancora", non come ancora a zero.

**Recupero di un `sp13` omesso.** È l'unica scrittura, e non è un plug: avviene solo quando
**tre fatti indipendenti concordano entro €2** — la riga stampata, il risultato ricalcolato dal
CE, e il gap fra i due lati dello SP. Il valore esatto della fonte viene rimesso nel suo campo
legale; qualunque residuo estraneo resta bloccante.

### Situazioni contrapposte: le forme che il lettore deterministico riconosce (ottobre 2026)

Dai bilanci caricati a ottobre 2026, tutti importati «squadrati» senza un motivo nel documento:

- **Utile dell'anno prima ancora fra i conti del patrimonio netto** (AITEC 30/06/2026: mastro
  «309 UTILE (PERDITA) DELL'ESERCIZIO» 269.255,83 dentro il totale passività). Un conto di
  risultato diverso dal risultato del periodo va in `sp12g` **solo se chiude al centesimo** il
  divario misurato contro il totale passività stampato: STB 30/06/2026 ne ha uno nei conti
  d'ordine, fuori dai totali, e lì resta fuori (`_prior_result_booked`).
- **Totali con l'importo prima della didascalia** nel flusso di testo («1.406.600,60 Totale
  Attività: *** 1.352.014,11 Totale Passività:», STB): la ricerca lineare prendeva lo stesso
  importo per i due totali, utile zero. Quando entrambi i totali sono letti per coordinate
  valgono quelli; «Totali» senza lato (M.C.T.) li assegna la colonna.
- **Codici a segmenti azzerati** («102.00.00000» mastro, «102.01.00000» conto, «102.01.00004»
  sottoconto, M.C.T.): ridotti a cifre i tre livelli non erano uno il prefisso dell'altro e si
  sommavano tutti. Tolti i segmenti di zeri in coda (solo codici di almeno tre segmenti con
  l'ultimo di almeno quattro cifre) il riclassificatore sceglie un livello solo.
- **Percorso di legge davanti alla descrizione** («B) I) IMMOBILIZZAZ.IMMATERIALI», «A) 2)
  ESISTENZE INIZIALI»): si toglie e decide la descrizione — lo stesso gestionale scrive «B) F.DI
  AMMORTAM.» al passivo, dove B) sarebbero i fondi rischi. Con le abbreviazioni «F/A -», «F.DI
  AMMORT», «RAPPOR.», «IMMOBIL.» (`_descrizione_di_conto`).
- **Pagina di continuazione senza intestazione di sezione**: è della sezione della pagina prima.
- **C.III** («attività finanziarie che non costituiscono immobilizzazioni») ha ora una voce,
  `sp08`: prima finiva fra le immobilizzazioni materiali (contiene IMMOBILIZZAZIONI). Un credito
  non è mai un cespite («Crediti vs. Ad Immobiliare» prendeva la regola MOBILI).
- Esistenze iniziali e rimanenze finali scritte per esteso vanno in `ce10`, come «RIM.INIZ» e
  «RIM.FIN»: prima finivano in oneri diversi e altri ricavi. Il risultato non cambia.
- Una pagina senza sezione eredita quella della pagina prima **solo finché la sezione non ha
  chiuso** (totali di entrambi i lati, «Totali» due volte, pareggio o quadratura): dopo è un
  allegato («Dettaglio ratei, risconti e competenze», budget_210) e resta fuori.
- Nel percorso snello un parser standard che non ha letto nulla (`esito: "vuoto"`, colonne
  comparative viste in un bilancio di verifica: STB) non chiude più la ricerca dei lettori
  deterministici: prova la situazione contabile. Uno standard che legge e non quadra la chiude
  come prima.

## 7. L'anno precedente ha uno standard più severo

L'anno corrente viene salvato anche se solo strutturalmente valido. Il **precedente no**: deve
superare *sia* `validate_balance` *sia* la quadratura piena.

- Se tutti i suoi campi sono zero → PDF monocolonna, scartato in silenzio.
- Se non supera il gate → **non viene mai persistito**; un record già esistente viene
  **preservato**; l'utente riceve "ANNO PRECEDENTE NON IMPORTATO [anno]".
- Se lo supera → sostituisce l'eventuale record esistente, forzato ad anno pieno.
- Se il documento **stampa** un comparato (`has_comparative_ivcee_columns`) ma nessun lettore lo ha
  restituito, e nessun avviso sull'anno precedente c'è già → "ANNO PRECEDENTE NON IMPORTATO [anno]"
  nel risultato e nel report persistito dell'anno corrente (`_avviso_comparato_non_letto`, #60):
  un anno di riferimento che sparisce in silenzio non si distingue da un documento monocolonna.
- **Intestazione a parole** (`corrente | comparato | Scostamento | %`, `_labelled_layout` in
  `standard_ivcee_parser`, #60). Fino al 2026-10-04 il comparato di questo layout non si leggeva
  mai (#27): senza confine la seconda colonna riceveva lo scostamento, che è lineare e passa ogni
  controllo incrociato. Ora decidono i dati, come per le intestazioni a date: nessun importo stabile
  oltre il comparato → due colonne, si legge; una terza colonna sotto un'intestazione di analisi
  stampata → si legge con un confine subito oltre il bordo destro del comparato, purché nessun
  importo della terza colonna cada prima del confine; una terza colonna che nessuna intestazione
  nomina → il comparato non si legge. Misurato sui 200 PDF unici del corpus: l'anno corrente non
  cambia su nessuno.

La logica: un anno precedente sbagliato è peggio di un anno precedente assente, perché diventa
la base di confronto di tutto il previsionale.

## 8. XBRL: l'anno non è l'identità di un periodo

> Un'istanza XBRL può legittimamente contenere **un bilancio annuale e un nove-mesi che
> finiscono nello stesso anno solare**. Trattare l'anno come identità li fa collassare.

L'identità di un periodo ha **cinque** componenti: schema entità, identificativo entità, data di
fine, mesi di durata, data di inizio, dimensioni. L'anno *deriva* dalla data di fine, non è la
chiave. Etichetta risultante: `2025-9M@2025-09-30` contro `2025-12M@2025-12-31` — due periodi
distinti.

Regole di lettura del contesto:

- `forever` → contesto scartato;
- data di fine non parsabile → contesto **scartato** (non un anno nullo);
- durata in mesi accettata solo se compresa fra 1 e 12;
- un contesto istantaneo non ha durata.

**Selezione:** una sola entità (quella con più fatti, con spareggio lessicale per essere
indipendenti dall'ordine) e un solo scope dimensionale (**preferito quello senza dimensioni**).
I fatti di altre entità o dimensioni sono scartati. Un contesto istantaneo viene agganciato a
tutte le durate con **la stessa data di fine**: così lo SP di fine periodo si unisce al CE della
durata giusta, mantenendo annuale e infrannuale in contenitori separati.

**Fatti duplicati:** si sceglie per unità (EUR preferito), poi coerenza istante/durata, poi
precisione, poi due criteri puramente deterministici. Se restano valori distinti, warning.

L'XBRL ha inoltre un blocco **atomico**: se non quadra, rollback e HTTP 422 — non arriva
nemmeno al database.

## 9. CSV

**Encoding**, in ordine stretto: BOM UTF-8 → BOM UTF-16 LE/BE → tentativo UTF-8 → cp1252 →
errore. L'ordine non è casuale: cp1252 non fallisce quasi mai, quindi provarlo prima
produrrebbe sistematicamente mojibake ("Disponibilità").

**Intestazione** normalizzata: accenti rimossi, minuscolo, punteggiatura collassata. Il
riconoscimento è quindi immune ad accenti, maiuscole e punteggiatura.

**Schema BILAQ**: riconosciuto se le quattro colonne attese sono un **sottoinsieme** delle
intestazioni — colonne extra ammesse, posizione irrilevante. La mappatura è **per sezione
semantica IV-CEE, mai per posizione di colonna**.

**Schema TEBE**: prima cella che inizia per "bilancio" e una cella che contiene un anno.

Altrimenti: "Schema CSV non riconosciuto".

## 10. Percorso snello (default; `IMPORT_MOTORE=classico` per tornare a prima)

> Motori: `importers/import_snello/` (`righe.py`, `percorsi.py`, `lettura.py`, `verifica.py`,
> `legenda.txt`), `importers/struttura_documento/mappa.py`. Spec:
> `docs/superpowers/specs/2026-09-26-import-pdf-snello-design.md`.

Il motore d'import di default dal 2026-10-16 (vedi
[PRODUCTION_CONFIG.md](../deployment/PRODUCTION_CONFIG.md)); con `IMPORT_MOTORE=classico` (o un
altro valore) il percorso resta quello descritto nelle sezioni precedenti. Legge con Qwen locale
(gx10); **Anthropic è vietato** salvo `ANTHROPIC_CONSENTITO=1` (`llm_provider.vieta_anthropic`):
senza consenso, o con gx10 non configurato, la fase che servirebbe al modello si salta e si
dichiara. Prima del modello girano i lettori a regole, `lettura generica dello schema di legge`
compreso (`importers/schema_legge_generico.py`), e **non sceglie mai un codice da un
elenco lungo**: il modello nomina la voce di legge (il percorso, es. `SPP.D.4.E`), il codice la
traduce nel campo `sp`/`ce` con una tabella fissa.

**F0 — Prima i lettori deterministici, prima della struttura** (`importers/import_snello/deterministico.py`,
`tentativo()`). Prima di qualunque chiamata di modello si prova, nell'ordine: il PDF reso dall'XBRL
depositato (`importers/xbrl_reso_parser.py`: prospetti e tabelle di scadenza della nota integrativa,
ogni totale stampato riprodotto al centesimo, letto anche per posizione quando il testo a blocchi
non chiude), lo schema di legge col percorso come codice di riga («1.B.2», «3.B.9.a»; `importers/schema_codici_parser.py`: legge la sola colonna «Totali», una voce conta solo se nessuna voce sotto di lei ha un campo, anno precedente compreso), lo schema di legge col percorso nell'etichetta (`schema_etichette_parser`, sotto), lo schema di legge IV-CEE (`standard_ivcee_parser`), lo schema di legge con dettaglio
conti (`extract_ivcee_didascalie`), la situazione contabile. Un candidato si adotta solo se quadra
entro il tappo e la sua massa non classificata sta entro `soglia()`: allora la struttura **non si
chiede** (`struttura.stato = "non_richiesta"`, zero chiamate vision, zero gx10). Lo schema di
legge che **si riconosce ma non legge nulla** (esito `"vuoto"`) chiude comunque la ricerca: la
situazione contabile non si prova. È una scelta, non una svista: il commit `a72b8d4` aveva aperto
quella porta e `a09e472` l'ha richiusa (2026-10-03), perché il parser delle situazioni contabili
adottava budget_238 e budget_338 quadrati ma con le voci sbagliate. Prima ancora, un
riepilogo di poche macro-voci (`importers/import_snello/riepilogo.py`, tipo export xlsx) si rifiuta
con `PDFImportError`: non è un bilancio (decisione del proprietario, 2026-10-03).
**Prospetto sintetico** (`importers/prospetto_sintetico.py`, 2026-10-19, budget_1405): due pagine, una
colonna, voci di legge **appiattite** («B) Immobilizzazioni materiali», «C.II) Crediti», «B.7) Servizi»,
costi fra parentesi) e i totali di gruppo stampati. Non è un riepilogo da rifiutare: ha le voci che il
modello usa, manca solo il dettaglio. Entra fra gli ultimi lettori (`_ULTIMI_LETTORI`, dopo i lettori di
sempre, che non lo adottano) e ogni totale stampato deve tornare, altrimenti `rifiuto`. Il totale di una
voce senza dettaglio va nel sotto-campo «altri» della famiglia (`iv_cee_hierarchy.residual_bucket`, la
stessa convenzione di `residual_finalization`: massa letta, mai un plug), con una sola scelta propria,
del proprietario: le immobilizzazioni materiali in `sp03b` impianti e macchinari, non in altri beni. Le
assegnazioni stanno in `report['approssimazioni']` e nell'avviso «PROSPETTO SINTETICO»: l'utente le
affina in Rettifiche.

**Verifica «Mastri» a 3/5 cifre** (budget_1401, Metaldecor): stesso gestionale e tracciato del «Mastri»
a 4/8 cifre di Santini, con mastri `\d{3,4}` e conti `\d{5,8}`. Tre particolarità: un mastro con la sola
riga del totale («CLIENTI IT», codice a lettere) vale da sé; l'utile d'esercizio può essere già un conto
del PASSIVO (attivo = passivo, la DIFFERENZA è il solo risultato del CE); la scadenza la dichiara il
mastro («DEBITI V/FINANZ.ESIG.OLTRE 12M») e i suoi conti la ereditano, così i mutui non cadono a breve.
Per lo stesso motivo «DEBITI V/FINANZ.» è debito finanziario (gli anticipi su fatture non sono «altri
debiti»).
Lo schema di legge adottato porta con sé anche la colonna comparativa (`_con_precedente`, #60),
con le stesse regole di adozione dell'anno corrente ma **solo con esito `"ok"`**: un tappo
sull'anno precedente non avrebbe dove essere dichiarato. `deterministico.prior_stato` nel report
vale `"letto"`, `"scartato"` (con `prior_rifiuto`) o `"assente"`. Prima il percorso snello
lo scartava sempre, e solo il reso XBRL portava l'anno precedente.

**Schema col percorso nell'etichetta** (`importers/schema_etichette_parser.py`, 2026-10-16): la
"Situazione contabile riclassificata dettagliata" (BILAQ, detail_riclass, nicee, 2R, Santini),
`Cod. | Descrizione | esercizio | precedente | Differenza | Scost. %`, dove la descrizione comincia
col percorso di legge ("B.I.2) Costi di sviluppo", "C.II.5 bis.1) Esigibili entro…", "20)
Imposte") e il gestionale stampa sotto ogni voce i propri dettagli e i conti. Si legge **solo la
voce di legge**, tradotta con `campo_da_percorso`; le righe "Esigibili entro/oltre" sotto crediti e
debiti decidono la scadenza, le lettere di B.9/B.10 il dettaglio del personale e degli
ammortamenti; le sotto-righe del gestionale ("B.6.2) Materie prime", "(Fondi di ammortamento)",
il percorso ripetuto sulla riga sotto) e i conti non entrano mai. **Ogni totale stampato deve
essere la somma delle voci lette sotto di lui**, altrimenti l'anno non si adotta e `rifiuto`
nomina il totale più interno che non torna. A.3/A.4 seguono le colonne del DB, in ogni importatore dal Task 5-bis (2026-11-09): A.3 → `ce03`, A.4 →
`ce03a` (`data/iv_cee_tree.json`, `lettore.tavola`, estrattore LLM, parole chiave di route C). Gira in tre punti: qui in F0, e nel percorso di sempre
(`_schema_etichette_extract` in testa a `_llm_extract`) sul testo del PDF **e sulle tabelle
MinerU di una scansione** (`estrai_da_mineru`: la colonna Differenza ricompone le cifre che l'OCR
sposta da una cella alla successiva). Prima questa famiglia andava al modello, che prendeva
sotto-righe per totali, contava due volte i crediti oltre 12 mesi e perdeva i debiti verso il
gruppo (Santini 31/12/2025, sbilancio di 1,1 milioni).

**F1 — Struttura.** Riusa la mappa del branch struttura (vision su gx10, un blocco per chiamata;
Sonnet solo con `ANTHROPIC_CONSENTITO=1`):
per ogni pagina, quali sono SP/CE/dettaglio, lo `schema` (di legge / riclassificato / piano dei
conti), la `disposizione` (colonna unica / sezioni contrapposte), colonne per ruolo e totali
stampati. Decide quale dei due modi seguenti usare.

**F2 — Macroconti, due modi**, scelti dallo `schema` della struttura:

- **F2-L** (schema di legge: IV-CEE, abbreviato, micro, riclassificato) — una chiamata gx10 per
  sezione (SP, CE, in parallelo — `voci_di_legge` in `lettura.py`); il modello restituisce, per
  ciascun esercizio, le sole voci **stampate** come coppie `[percorso, importo]` — mai un totale,
  mai un `enum` di campi. Il modo ha una variante, `"legge_con_dettaglio"` (Task 24): lo schema di
  legge con i conti stampati sotto ogni voce; le righe con codice conto **non** entrano nel prompt
  (le didascalie portano già il netto, i conti il lordo e i fondi: il modello li sommerebbe due
  volte). Dove questa pagina dice modo `"legge"`, vale per entrambe.
  - **Scadenze** (`PROMPT_VOCI`, 2026-10-03). Quando sotto una voce sono stampati gli importi
    «esigibili entro» e «esigibili oltre l'esercizio successivo», il modello restituisce una coppia
    per scadenza col suffisso `.E`/`.O` (`SPP.D.4.E`, `SPP.D.4.O`, `SPA.C.II.1.O`,
    `SPA.B.III.2.O`), non il totale della voce; nessun suffisso se la scadenza non è stampata, e
    allora il debito va a breve. La regola sta nel prompt, non in `legenda.txt`. Prima il prompt
    chiedeva il suffisso solo per le voci senza numero arabo, e budget_597, 664, 289 e 297
    salvavano a breve debiti che il documento dichiarava oltre l'esercizio: il foglio quadrava,
    CCN e current ratio no.
  - **Coppie ripetute** (`conti.da_coppie`). Si scarta solo la coppia identica (stesso percorso,
    stesso importo: la stessa voce letta due volte). Lo stesso percorso con importi diversi sono
    voci distinte che la legenda non separa, come le sotto-lettere di B.III.2, e si sommano:
    budget_597 ne perdeva 26.268 quando si teneva la prima coppia di ogni percorso.
- **F2-C** (elenco di conti: bilancio di verifica, situazione contabile, contrapposte, piano dei
  conti) — la struttura fisica delle righe viene da `collect_source_rows` (rotazione, righe
  fisiche, contrapposte, colonne SAP); `righe.py` (`marca_totali`, `foglie`) esclude i totali
  perché uguali alla somma di righe adiacenti, imparando la direzione dai gruppi di almeno due
  righe; il modello (`percorsi_dei_conti` in `lettura.py`) assegna a ogni conto **foglia** il
  percorso di legge, a blocchi di 60 righe (`BLOCCO`) — solo gli id del blocco interrogato sono
  accettati in risposta, mai l'id di un altro blocco dello stesso giro; `percorsi.py`
  (`campo_da_percorso`) traduce percorso → campo e somma.

La legenda dei percorsi (`legenda.txt`) è identica a ogni chiamata dello stesso documento, per la
cache del prefisso. Le somme di centinaia di conti non si chiedono mai al modello: lente e
inaffidabili, il codice le fa. Le chiamate gx10 di questo percorso (`lettura.py`) usano un
timeout di **120 s**, più stretto del default del provider (600-900 s, vedi
[PRODUCTION_CONFIG.md](../deployment/PRODUCTION_CONFIG.md)): un gx10 impantanato non deve tenere
impegnato l'import per minuti.

**F3 — Verifica e tappo** (`importers/import_snello/verifica.py`). `misura()` calcola lo scarto
SP (attivo − passivo) e lo scarto CE (utile CE ricalcolato contro `sp13`), in una delle due forme
possibili — `"bilancio"` (il risultato corrente sta nel netto, come lo schema di legge) o
`"verifica"` (il risultato è la riga di quadratura, come un bilancio di verifica, e `sp13` letto
è quello dell'anno **prima**). Entrambi i modi passano `forma="bilancio"` esplicita: il modo
`"conti"` dal Task 14 (2026-09-26), perché il suo costruttore (`da_foglie`) porta già `sp13`
all'utile del CE, e una forma scelta da sé poteva tornare su `"verifica"` e sottrarre l'utile una
seconda volta, mascherando un vero sbilancio (budget_330).

`tappa()` confronta gli scarti con il limite del tappo, **10 €** per controllo: SP, CE e confronto
con i totali stampati (decisione del proprietario, 2026-10-03; manopola `IMPORT_SNELLO_TAPPO_MAX`).
Il codice (`limite_tappo()`) prende il minore fra quei 10 € e `soglia()`, ma `soglia()` non scende
mai sotto `IMPORT_SNELLO_SOGLIA_MIN` (100 € di default): in pratica il limite è 10 € su qualunque
bilancio, e non si allarga con l'attivo. `tappa()` restituisce uno tra quattro esiti:

| Esito | Quando |
|---|---|
| `"ok"` | nessuno scarto |
| `"tappo"` | scarto entro 10 €: si chiude su un campo dichiarato (sotto) |
| `"vuoto"` | attivo e passivo entrambi zero — **mai** `"ok"`: un'estrazione vuota non è una quadratura |
| `"oltre_soglia"` | scarto oltre il limite del tappo (10 €), oppure un tappo sul CE che porterebbe `ce06_servizi` sotto zero (non si applica: si dichiara oltre soglia invece di un tappo negativo). Il nome è storico: il grilletto è il limite del tappo, non `soglia()` |

**Il tappo** (solo entro 10 €): attivo in eccesso rispetto al passivo → manca passivo, si
aggiunge a `sp16g_altri_debiti_breve`; passivo in eccesso rispetto all'attivo → manca attivo, si
aggiunge a `sp06g_crediti_altri_breve`; utile CE diverso da `sp13` → lo scarto va su
`ce06_servizi` (in più o in meno). Mai su un campo `TIER0`. Dettagli su campi, soglia e dove si
legge nel report → [REGOLE-IMPORT-04-QUADRATURE.md §12](REGOLE-IMPORT-04-QUADRATURE.md).

**La rilettura, unica — solo nel modo `"legge"`.** `"vuoto"` e `"oltre_soglia"` innescano, **solo
in modo `"legge"`**, una sola rilettura mirata della sola sezione (SP o CE, quella con lo scarto
maggiore) in `forma="bilancio"` esplicita; il modo `"conti"` non rilegge mai. **Due eccezioni,
nessuna rilettura** (`causa: "documento_sbilanciato"`): il documento stampa Totale attivo e Totale
passivo diversi di oltre 10 € e le voci lette riproducono quella differenza; oppure stampa un
utile nello SP diverso da quello del CE e le voci lette li riproducono entrambi. In entrambi i casi
i numeri stampati devono essere letti dal testo del documento, mai riferiti dal modello, e l'avviso
li cita (decisione del proprietario, 2026-10-03). Le due frasi sono diverse
(`pdf_importer._snello_squadrato_reason`): sui totali l'avviso chiude con «importato così com'è:
correggilo in Rettifiche oppure carica una versione quadrata del bilancio»; sul risultato dice
«importato così com'è (bilancio squadrato di partenza)».

**La lettura più vicina (Task 28).** Se il modello chiude `"squadrato"`, o ripiegherebbe, e un
candidato deterministico era stato scartato solo perché oltre i 10 € (scarto peggiore entro
`soglia()`, massa non classificata entro soglia), si salva la lettura col peggiore scarto minore,
sempre `"squadrato"` e senza tappo; il report dichiara `confronto_letture` (o `ripiego_evitato`) e,
se la lettura salvata non ha l'anno precedente che il modello aveva letto, un avviso lo dice.

**Task 17 (decisione del proprietario, 2026-09-27): «se il bilancio non è quadrato deve essere
comunque importato con avviso, l'utente lo correggerà nella tab rettifiche».** Se l'esito resta
`"oltre_soglia"` dopo la rilettura in modo `"legge"`, o subito in modo `"conti"` (che non
rilegge), l'orchestratore **non ripiega più**: adotta il risultato con esito `"squadrato"`, senza
applicare alcun tappo — `bs`/`ce` restano quelli letti, invariati — con gli scarti misurati
(`scarto_sp`, `scarto_ce`, `scarto_stampati`) dichiarati in `misura`, letti da `pdf_importer.py`
per costruire l'avviso "BILANCIO SBILANCIATO" mostrato all'utente (→
[REGOLE-IMPORT-04-QUADRATURE.md §12](REGOLE-IMPORT-04-QUADRATURE.md)). Il ripiego resta l'unico
esito per **`"vuoto"`** (un'estrazione vuota non ha nulla di sensato da salvare), per una
struttura non riuscita e per un'eccezione imprevista, **a meno che** un candidato deterministico
scartato solo dal tappo abbia letto davvero (sopra, «La lettura più vicina»: si salva quella,
`"squadrato"`, con `ripiego_evitato` nel report). Solo in questi casi l'orchestratore
(`importers/import_snello/__init__.py`, `importa()`) solleva `SnelloNonRiuscito` e il chiamante
**ripiega sull'importatore attuale**, intero e invariato, che decide da sé come oggi — compreso
l'import squadrato e dichiarato descritto nelle sezioni precedenti di questa pagina.

**Gli esiti nel report** (`validation_report["import_snello"]`, scritto da `pdf_importer.py`) sono
un livello sopra quelli di `tappa()`:

| Esito | Quando | Chiavi proprie |
|---|---|---|
| *(chiave assente)* | `IMPORT_MOTORE=classico` (o un valore diverso da `snello`) | — |
| `"non_applicabile"` | il documento è una scansione o viene da OCR (RapidOCR locale, o MinerU senza tabelle a sezioni contrapposte): il percorso snello **non si tenta nemmeno**, un testo OCR non è mai un text layer nativo. Con le tabelle MinerU a sezioni contrapposte invece lo snello legge il loro PDF sintetico (pagina 01 §5) | `motivo`: `"scansione"` \| `"ocr"` (mai `fase`/`errore`) |
| `"ok"` / `"tappo"` | successo dell'orchestratore | `modo`, `struttura`, `misura`, `tappo`, `letture`, `diag`, `anomalie`, `secondi`, più `precedente` (`"incluso"` \| `"escluso_oltre_soglia"` \| `"non_letto_dalla_lettura_deterministica"`) quando in modo `"legge"` c'è un anno precedente |
| `"squadrato"` | scarto oltre il limite del tappo dopo l'unica rilettura (modo `"legge"`), direttamente (modo `"conti"`), o lettura deterministica vicina salvata al posto di quella del modello o del ripiego (Task 28, nessuna rilettura): si adotta comunque, `tappo.corrente` resta `None` e `misura` dichiara lo scarto | stesse chiavi di `"ok"`/`"tappo"`, più `confronto_letture` o `ripiego_evitato` nel caso Task 28 |
| `"ripiego"` | fallimento — dichiarato dall'orchestratore (solo su `"vuoto"`, o su una struttura non riuscita) o un'eccezione imprevista | `fase` (`"struttura"` \| `"lettura"` \| `"conti"` \| `"verifica"` \| `"eccezione"`), `errore` (il tipo di eccezione, o `"vuoto"` quando la causa è la verifica) |

Un esito `"squadrato"` produce un `validation_status` diverso da `"verified"` (lo stesso
`"unbalanced"` di uno sbilancio letto dall'importatore attuale) e blocca il previsionale con il
verdetto **esistente** di `check_quadratura` sul foglio persistito — nessun nuovo cancello (→
[REGOLE-IMPORT-04-QUADRATURE.md §12](REGOLE-IMPORT-04-QUADRATURE.md)).

`diag` porta sempre `lato_irrisolti` (lista, presente anche vuota): i conti SP letti sul lato
sbagliato e senza contropartita nota (`percorsi.CONTROPARTE`, applicata da `conti.applica_lato` in
modo `"conti"`) restano sul lato che la colonna dichiara e cadono su un secchio esplicito di
quella sezione — `sp06g_crediti_altri_breve` fra le attività, `sp16g_altri_debiti_breve` fra le
passività — mai su un campo `TIER0`, mai un segno ribaltato. `_unclassified_mass` (sul `bs`
finale) è la somma di quei valori; `_plug_residual` è l'importo del tappo SP (0 se nessun tappo) —
entrambe sempre dichiarate, anche a zero.

**Regole contabili.** Applicate all'uscita di F2, riusando il codice esistente: la colonna è la
verità sul lato (mai il contrario — vedi `applica_lato` sopra), netting cespite/fondo per
sottoconto (all'aggregato se manca il dettaglio), compensazioni sulle voci minori, debito senza
scadenza dichiarata → a breve.

**Il segno delle voci di conto economico** (`importers/import_snello/conti.py`). Sbagliarlo sposta
l'utile di **2×** l'importo della voce, e il foglio può quadrare lo stesso se l'errore è
simmetrico. Ogni segno corretto finisce in `diag["ce_segno_forzato"]`
(`[percorso o id, campo, letto, applicato]`), in entrambi i modi.

- **Modo `"legge"`** (`_segno_ce_legge`, una colonna sola, nessun lato fisico da cui dedurre
  nulla). Prima si vota per conteggio la convenzione di stampa del documento, separatamente per i
  costi (`_convenzione_costi`) e per i ricavi (`_convenzione_ricavi`): +1 se li stampa positivi,
  −1 se negativi, come fanno budget_115, 297 e 664. Poi:
  - le variazioni e i cambi (`ce02`, `ce03`, `ce16`) prendono il segno letto per la convenzione
    dei ricavi; `ce10` per quella dei costi. Una perdita su cambi stampata è una perdita (Task 27,
    budget_397);
  - i costi della produzione B.6–B.14 (`_CE_COSTI_PRODUZIONE`: `ce05`–`ce09b`, `ce11`, `ce11b`,
    `ce12`, con le sotto-voci) prendono il segno letto per la convenzione dei costi: un costo
    stampato contro la convenzione è una **riduzione vera**. budget_253 stampa «14) Oneri diversi
    di gestione −1.239» fra costi positivi, e il Totale costi della produzione lo conferma; in
    valore assoluto l'utile CE si allontanava da quello dello SP del doppio (2026-10-03);
  - tutto il resto prende il **valore assoluto**: oneri finanziari (la sezione C stampa spesso
    «17) interessi e altri oneri finanziari» col meno solo per presentazione, budget_289),
    imposte, svalutazioni B.10.c/d, proventi e ricavi a segno fisso.
- **Modo `"conti"`** (`da_foglie`). Con due colonne fisiche si vota per conteggio quale colonna è
  normale per i costi e quale per i ricavi: una foglia sulla propria colonna porta il segno letto
  così com'è, una foglia sulla colonna dell'altra famiglia è sempre una riduzione. Con una colonna
  sola ogni voce prende il valore assoluto. Le regole a segno libero del modo `"legge"` qui non
  esistono.

Nel modo `"conti"` un importo **dentro la descrizione** di un conto non è un saldo
(`righe._importo_in_descrizione`, Task 27, budget_243): «beni di valore inferiore euro 516,46» su
una riga con un solo importo, ben a sinistra della colonna degli importi, si scarta. Una riga con
più importi, o un importo allineato agli altri con la valuta davanti («Cassa Euro 239.126,40»),
non si tocca.

**F4 — Dettagli per il budget.** `enrich_pdf_details` gira dopo un successo snello, in entrambi i
modi, **tranne** quando ha letto il PDF reso da XBRL (`fonte: "deterministico:xbrl_reso_parser"`):
lì i dettagli vengono già dalle tabelle di scadenza della nota integrativa. Negli altri casi: in modo `"legge"` con le pagine di dettaglio della struttura
(`struttura.pagine_dettagli()`) e l'LLM di dettaglio **attivo**; in modo `"conti"` **senza** LLM
(`usa_llm=False`), perché i dettagli sono già usciti dalle foglie classificate in F2-C. La sua
riclassificazione deterministica di maturità (entro/oltre l'esercizio) può spostare massa fra il
lato breve e il lato lungo dello stesso aggregato — non tocca mai i totali.

### Regole del lotto week-43 (2026-10-27) sulla lettura

Ognuna ha il suo test; le regressioni sono su 208 PDF diversi (`Test/` più il lotto).

- **L'anno sul titolo di sezione non è un importo** (`schema_legge_generico._righe_da_grezze`):
  «CONTO ECONOMICO 2025» con l'anno delle colonne letto come importo non apriva la sezione, e il
  «21) Utile» restava voce IX del netto (Napolitano 1417/1421/1423/1425, rifiutati).
  `tests/test_schema_legge_generico_anno_e_totali.py`.
- **Il «Totale» che ripete la voce dopo i suoi conti va via con loro**
  (`_togli_dettaglio_conti`): stessi importi e nome contenuto nell'altro, altrimenti chiudeva il
  padre e la voce seguente saliva di livello. Stesso file di test.
- **C.I-bis, immobilizzazioni materiali destinate alla vendita** (`xbrl_reso_parser`): la riga
  senza enumeratore sotto C prende `SPA.C.I-bis`, va in `sp05` (attivo corrente non liquido, come
  il VBA legacy) e si dichiara fra gli ignoti; il controllo sul totale delle rimanenze la toglie.
  Prima finiva nei crediti e il documento era rifiutato (budget_1418). Decisione del
  proprietario, 2026-10-28: in `sp05` come nel VBA. `tests/test_xbrl_reso_parser.py`.
- **Lo schema inviato a gx10 richiede ogni campo** (`llm_provider.schema_tutto_richiesto`): con
  la decodifica guidata vLLM ometteva sp11–sp18 e pydantic li riempiva a zero; un attivo letto
  col passivo tutto a zero è una **lettura mancante** e l'importatore classico la rifiuta
  (`pdf_importer._rifiuta_passivo_non_letto`) invece di salvarla «sbilanciata».
- **Il report dello snello porta il messaggio dell'eccezione** (`messaggio`), non solo la classe.
- **Una parentesi è un segno solo se si chiude** (`import_snello.righe._dec`): «CLIENTI
  (5.367,37» era −5.367,37 (budget_1450).
- **Il capitale sociale nella ragione sociale non è un saldo**
  (`righe._senza_importo_in_descrizione`): su una riga con più importi, quello preceduto dalla
  valuta («euro», «€», la «E» di «CAP. SOC. E»), lontano dalla colonna della pagina mentre un
  altro importo della riga ci sta, è testo; se la valuta precede ogni importo è il prefisso delle
  colonne e non si tocca (budget_413). budget_1450: un fornitore valeva 22.000.000,00.
- **I ruoli di colonna vengono dalle intestazioni stampate** quando la vision non dà una colonna
  di saldo e le intestazioni non parlano di dare/avere (`analisi._ruoli_dalle_intestazioni`):
  la colonna datata più recente è il saldo corrente, «Diff.»/«variaz»/«scostam» sono variazioni,
  «%» percentuale (budget_1445: la vision dichiarava dare/avere su quattro colonne e il saldo
  ripiegava sull'ultimo importo, la Diff. Valore).

- **Un segno fuori colonna si ribalta una volta sola** (`conti.da_foglie`, CE a due colonne:
  `-f.valore`, non `-abs(f.valore)`): una riga già negativa nella colonna opposta
  (sopravvenienze attive −4.626,61 fra i costi) si ribaltava due volte e l'utile si spostava di
  2× l'importo (budget_1429).
- **Letture SP e CE sovrapposte: ogni voce dalla sua lettura** (`import_snello._per_sezione`):
  una voce letta da entrambe viene dalla lettura della sua sezione (le imposte della colonna
  comparata lette dalla pagina SP si sommavano a quelle della pagina CE, budget_1440). Un lato
  (attivo, passivo, CE) che la sua lettura non ha restituito si prende dall'altra (budget_1440,
  secondo giro: attivo a zero). Voce per voce no.
- **La pagina dove si apre una sezione è anche sua** (`analisi._pagine_di_apertura`): la pagina
  subito prima della prima pagina CE, assegnata allo SP, che porta su una riga sua il titolo
  «Conto economico», entra anche fra le pagine CE (e simmetricamente per lo SP). budget_1433/1434:
  il CE comincia in fondo alla pagina SP e i ricavi non li leggeva nessuno (utile CE −948.971,67
  contro −56.081,85 stampato).
- **Le didascalie di riga non sono colonne** (`analisi._colonne_vere`): se la vision dichiara
  come intestazioni di colonna in maggioranza didascalie di legge («5) Altri ricavi e proventi»,
  «B) Costi della produzione»), la sezione prende le colonne dell'altra sezione, se vere,
  altrimenti nessuna. budget_1433: il modello leggeva i valori «sotto» quelle colonne e saltava
  i ricavi.
- **Un conto orfano sotto un mastro si adotta solo se chiude al centesimo**
  (`situazione_contabile_parser._be_adotta_orfani`): un conto né padre né figlio per prefisso,
  stampato dopo una radice i cui figli non la sommano, diventa suo figlio solo se figli + orfano
  = radice al centesimo (budget_1478). Il totale stampato decide, non il prefisso.
- **Il risultato precedente con didascalia neutra prende il segno dalla colonna**
  (`conti._segno_pregresso`): «RISULT. D'ESERCIZIO PROVV. ANNO PRECEDENTE» senza
  utile/perdita, a due colonne, è utile nella colonna del passivo e perdita nell'altra
  (budget_1439); `_is_prior_result_caption` riconosce anche l'abbreviazione «RISULT».
- **Il risultato precedente con la didascalia ma senza importo si ricostruisce dai totali**
  (`situazione_contabile_parser._hier_prior_caption_senza_importo`, decisione del proprietario
  2026-10-28). Su una situazione contrapposta, se sotto il «Totale passività» c'è la didascalia
  del risultato precedente senza importo (l'OCR ha perso la cella) e il CE è verificato dai suoi
  totali stampati (ricavi − costi), `sp13` = utile del CE e la differenza dei totali SP meno
  quell'utile va in `sp12g`. Si dichiara in `_prior_result_ricostruito` e nell'avviso «RISULTATO
  ESERCIZIO PRECEDENTE RICOSTRUITO DAI TOTALI»; il bilancio si salva in `review_required`
  (previsionale bloccato finché non lo si verifica). Senza la didascalia non si ricostruisce
  nulla. Il PDF sintetico di MinerU ora conserva quella didascalia (`mineru_contrapposte._righe`).
  budget_1410: prima `sp13` = 241.711,59 con un tappo mascherato, ora 68.247,80 + 173.463,79.
- **La sezione di una riga continua quella della pagina prima** (`detail_enrichment`,
  `collect_source_rows`): le righe senza titolo sopra di loro (una pagina senza titolo, o la parte
  sopra il titolo di una pagina) restano nella sezione precedente finché quella non si è chiusa
  in fondo alla sua pagina (totale a pareggio/quadratura, attività/passività, costi/ricavi,
  risultato d'esercizio, o una riga di due importi uguali). Le parole del corpo non classificano:
  «crediti per costi anticipati» portava nel CE la pagina 2 di budget_1450, e la coda dello SP
  sopra il titolo del CE di budget_1432 finiva nel CE. Una pagina senza titolo che chiude con un
  totale proprio dell'altra sezione («TOTALE COSTI … TOTALE RICAVI», budget_615) decide da sé.
  Un riepilogo in testa («Totale Attività: Totale Passività:» sotto il titolo) non chiude nulla.
- **La prima pagina del CE con la coda dello SP sopra il titolo è anche SP**
  (`analisi._pagine_di_apertura`): budget_1432, crediti, cassa e debiti sopra «Conto Economico dal
  …»; la lettura SP non li vedeva.
- **Un blocco stampato al contrario del documento** (`righe.marca_totali`): dopo il punto fisso
  nella direzione del documento, una passata k≥2 nella direzione opposta sulle righe ancora vive,
  con candidati le sole righe di totale (senza descrizione o «Totale …») e la somma al centesimo.
  budget_1450: i partitari Clienti/Fornitori col totale dopo i figli in un documento coi mastri
  prima. Sul corpus riconosce 212 righe di totale generale stampate in fondo, nessun valore cambia.
- **Un partitario che ripete un conto del prospetto non si conta due volte**
  (`righe.escludi_partitari`): un elenco di almeno 3 voci con il totale su una riga senza
  descrizione, su una pagina successiva, il cui totale è al centesimo il saldo netto (foglie a
  sinistra meno foglie a destra) di **un solo** conto già letto, è la scomposizione di quel conto
  e le sue righe escono dalle foglie (`Riga.ripetuta`). Corrispondenza uno a uno: un solo totale
  senza descrizione per pagina e un solo elenco per conto, altrimenti nulla si esclude.
  budget_1450: «1410 CLIENTI ITALIA» e i clienti di pagina 7, «20 FORNITORI» sui due lati e i
  fornitori di pagina 8 (509.310,97 contati due volte); sul corpus scatta solo lì.
- **Una situazione a sezioni contrapposte resta in modo «conti»**
  (`analisi._riclassificato_con_captions_legali`): l'eccezione AMBIENTA, che legge in «legge» un
  «riclassificato con codici IVCEE» con le colonne comparative dello schema di legge, non vale
  quando `is_contrapposte_file` riconosce conti su due lati. budget_1432 era letto in «legge» e il
  modello mescolava lordi e fondi (sbilancio 585.819, ora 15.524,64). Sui 208 PDF la guardia può
  toccare 9 file; reimportati, 8 verificati e 1432 migliorato.

## 11. Lettore di righe unico (Fase 1)

`importers/lettore/` è il lettore nuovo, scritto **accanto** al percorso attuale. Dalla Fase 2 è collegato
all'import **solo in diagnosi** (blocchi che non chiudono, `validation_report["lettore"]`, nessun importo
cambia): vedi [REGOLE-IMPORT-04 §13](REGOLE-IMPORT-04-QUADRATURE.md). Per il resto non lo chiama nessuno;
collegarlo alla classificazione è il lavoro delle Fasi 3-4, e quello che si legge in queste pagine sopra
descrive l'import vero.

**Che cosa legge.** Da un PDF col text layer (`leggi_pdf`) o dalle tabelle HTML di MinerU (`leggi_celle`)
restituisce un `Documento`: righe con codice, etichetta e un importo `Decimal` per colonna; le colonne col
loro ruolo (esercizio, mastro, differenza, percentuale, dare, avere, saldo, oppure ignoto quando testata e
numeri non decidono), il periodo e la corrente; il lato
fisico e il verdetto «sezioni contrapposte»; la sezione SP/CE; la parte (prospetto, nota, altro); le righe di
totale coi figli colonna per colonna, e per ogni riga il padre, se verificato dalla somma, e il percorso. Non
classifica in campi `sp`/`ce`, non netta, non tappa: ciò che non sa decidere lo dichiara (`Documento.avvisi`,
`Profilo.avvisi`).

**I principi del proprietario, nell'ordine in cui il lettore li applica.**

- **Prima la struttura, poi le righe.** Il profilo del documento (`profilo.py`: tipo, colonne e periodi, lati,
  negativi, decimali, forme dei codici, sezioni, margini, parti) si calcola per primo, e le righe si leggono su
  di lui, senza rifare quelle decisioni.
- **Le tabelle della nota integrativa non sono mai un prospetto.** Si riconoscono e si dichiarano
  (`Profilo.tabelle_nota`, `Riga.parte == "nota"`); colonne, periodi, totali e padri si calcolano solo sul
  prospetto.
- **La parentela viene solo dalle somme stampate**, colonna per colonna; mai dal prefisso o dalla lunghezza del
  codice conto. Un titolo sopra dà al più un padre non verificato.
- **Verificato solo con almeno due importi non nulli** (un'uguaglianza a un solo membro resta un'ipotesi, R14)
  **e con gli stessi membri su ogni colonna** che ha un gruppo suo (R18).

**Le regole riusate e da dove.** Le regole riprese dall'importatore attuale citano la funzione da cui vengono
nella docstring del modulo (`geometria.py`, `colonne.py`, `lati.py`, `totali.py`, `celle.py`) o accanto alla
regola stessa (`righe.py` e `profilo.py`, che ne raccolgono molte: `schema_legge_generico._bordi`,
`standard_ivcee_parser._anchors_carry_amounts`, `import_snello/righe.py:marca_totali`,
`situazione_contabile_parser` per righe fisiche e lati, `xbrl_reso_parser._DISTANZA_IMPORTO_ORFANO`…);
`importi.py` è scritto da capo sulle contraddizioni C1-C2 e `__init__.py` esporta soltanto. L'elenco
completo, con le dodici contraddizioni C1-C12 fra copie della stessa regola e la scelta fatta per ciascuna, è
nell'inventario `.superpowers/sdd/2026-10-30-importatore-generico-fase1/inventario-lettura.md` (fuori da
git), e le decisioni prese durante la fase (R1-R23, Q1-Q2) nel registro della stessa cartella SDD
(`.superpowers/sdd/2026-11-04-fase1-lettore-righe/progress.md`).

Le regole aggiunte con la misura sul campione:

- **Poste rettificative.** Una voce fra parentesi col nome di una rettifica («(Ammortamenti)», «(Fondi di
  ammortamento)») stampata positiva si sottrae nella somma della voce sopra; la cella resta lo stampato.
- **Risultati del conto economico.** Nei risultati («Differenza tra valore e costi della produzione», «Risultato
  prima delle imposte», «Utile (perdita)», «Totale proventi e oneri finanziari», «Totale delle rettifiche») costi,
  interessi e oneri, svalutazioni e imposte stampati positivi si sottraggono, e quei risultati si cercano dopo gli
  altri totali. Vale **solo sul conto economico a sezione unica** (sulle contrapposte il risultato pareggia due
  lati); fuori da uno schema di legge (bilanci di verifica, situazioni contabili) solo col lessico di legge per
  intero, perché lì «Differenza cambi passiva» o «UTILE ESERCIZIO:» sono nomi di conto. La voce di legge che
  stampa il suo importo **prima** dei componenti («C) PROVENTI E ONERI FINANZIARI», «D) RETTIFICHE DI VALORE…»,
  1464) tiene la regola del segno ma non è una riga di controllo: cerca i suoi membri sotto di sé, come ogni voce.
- **Periodi.** Il periodo di una colonna viene dalla testata sopra di lei (anche con la didascalia a sinistra) e,
  quando manca, dai titoli del documento solo se il periodo stampato è uno solo. Una colonna «precedente» o
  «comparato» senza data prende l'anno intero prima (fine al 31/12, mesi ignoti) solo se un titolo dice «anno
  precedente» o se la corrente è un anno solare intero; quella data non è stampata da nessuna parte, e il profilo
  lo dichiara in `Profilo.avvisi` (1548, 313).
- **Tolleranza (C6) sulla cella del totale.** Un euro quando il totale è stampato all'unità (la colonna è tutta a
  interi, la cella non ha decimali, o sta nella colonna dei totali di una coppia), anche sopra figli al centesimo
  della stessa colonna (1533, 682: voci e conti in una colonna); altrimenti al centesimo. La chiusura esatta vince
  ancora su quella in tolleranza (R17).
- **Coppie parziali → totali (Q1, decisione del proprietario 2026-11-05).** In alcuni schemi con dettaglio i conti
  stanno nella colonna «parziali» e la voce che li somma nella colonna «totali» accanto (638, 1331, 1451, 1540,
  1558).
  Il profilo marca la coppia (`Profilo.coppie`, totali → parziali): due colonne di valori adiacenti sullo stesso
  lato che non stampano mai sulla stessa riga, i parziali coi centesimi, i totali all'unità. Una voce della
  colonna dei totali prende per membri le celle dei parziali delle righe fra lei e la riga dei totali successiva
  (o precedente: vale la direzione che chiude di più), fermandosi al titolo di una voce allo stesso rientro rimasta
  senza importo; i suoi figli stanno in `Riga.figli[parziali]`, la colonna su cui si leggono i loro importi. I due
  livelli **non si mescolano**: un conto già membro di un totale dei parziali non conta, fra righe a rientri
  diversi contano le meno rientrate, e i totali della colonna dei totali sommano solo celle della colonna dei
  totali. Unire le due colonne in una, la strada ovvia, peggiora la misura (chiusi 73,7% contro 74,5%): somma
  conti e voci insieme. R14, R16, R17 e R18 valgono come altrove.
- **Marcatore D/A per colonna (Q2, decisione del proprietario 2026-11-05).** Il profilo marca una colonna «a
  marcatore» (`Profilo.marcatori`) quando almeno il 60% delle sue celle, e almeno 10, sono seguite da un D/A
  staccato («11.429.777,38 D», 680). Solo lì il marcatore firma la cella e lascia l'etichetta; altrove resta
  testo, come prima (365/367: due «A» sparsi in una contrapposta; 1562: il marcatore dei soli mastri). Il
  marcatore attaccato all'importo («1.234,56A») lo firma sempre. In entrambi i casi il segno segue il lato (R23),
  perché la colonna è la verità sul lato: `leggi_importo` restituisce il marcatore a parte (`Importo.marcatore`,
  valore senza segno) e `importi.segno_del_lato` lo applica. A sinistra delle contrapposte (attivo, costi) e su una
  sezione unica D è positivo e A negativo (il saldo in dare); a destra (passivo, ricavi) A è positivo e D negativo.
  Il marcatore staccato non apre il varco fra i due lati (`lati._varco`, `_sfora`). Su una sezione unica una voce
  senza marcatore del passivo o dei ricavi (1533, 1540) chiude i conti a marcatore col segno rovesciato: lo decide
  la somma, e la voce lo dichiara in `Riga.verso` (-1 per la colonna dei figli). Deciderlo per token, provato e
  tolto, rompeva 365/367 e 1562.
- **Voce all'unità sopra un conto solo (R22).** «contributi in conto esercizio 113.946» sopra il solo conto
  113.945,74 non chiude mai come catena esatta (R14); il totale sopra, in tolleranza, prendeva allora il conto al
  posto della voce, e il conto saltava un livello (1533, 682; su 208 un credito «esigibile oltre» finiva sotto il
  totale dei crediti, oltre il confine entro/oltre). Prima di ogni altra somma la voce stampata senza decimali prende
  il conto adiacente, al centesimo e più rientrato di lei, entro un euro: un'ipotesi (`padre_verificato` falso),
  ma il conto esce dal cammino e il totale sopra somma la voce. Non vale se anche il conto dopo sta nella
  tolleranza, per le righe di controllo, né senza rientri (tabelle OCR). Lo stesso per la voce dei totali di una
  coppia con un conto solo nei parziali.

**Per chi integra (Fase 2).** Otto cose che il `Documento` non dice da sé:

- **Si lavora su `Documento.righe_del_prospetto()`, mai su `righe`.** Le righe di nota che `leggi_pdf`
  restituisce hanno `celle` con le chiavi delle colonne della loro tabella, `profilo.tabelle_nota[r.tabella]`,
  non di `Documento.colonne`: la colonna 0 di una riga di nota non è la colonna 0 del prospetto.
- **Le due letture non danno le stesse righe di nota.** `leggi_celle` non ne restituisce nessuna (le tabelle della
  nota stanno solo in `profilo.tabelle_nota`); `leggi_pdf` le restituisce, marcate `parte == "nota"`.
- **Gli avvisi sono in due posti**: quelli del documento in `profilo.avvisi`, quelli delle righe in
  `Documento.avvisi`. `Documento.tutti_gli_avvisi()` li dà insieme, prima il documento, senza ripetizioni.
- **Con `Profilo.coppie` i figli stanno su un'altra colonna.** Per una voce della colonna dei totali `t.figli[c]`
  ha per chiave `c` la colonna dei **parziali**, quella su cui si leggono gli importi dei figli, e `t.celle[c]` può
  non esistere: il totale della voce sta nella colonna dei totali (la chiave di `Profilo.coppie`).
- **Per risommare i figli si usa `valore_nel_totale(doc, totale, figlio, colonna)`, mai la cella com'è.** Il
  valore che un figlio porta nella somma del suo totale non è sempre lo stampato: una posta rettificativa
  stampata positiva si sottrae, un costo dentro un risultato del conto economico si sottrae, e in una voce dal
  verso rovesciato (`Riga.verso`, Q2) un conto a marcatore cambia segno. La cella resta lo stampato. Su una colonna che **non** sta in `totale.figli` (un totale chiuso su un'altra
  colonna) `valore_nel_totale` dà verso +1: chi risomma lì usa il verso della colonna che chiude
  (`blocchi._figli_altra_colonna`, come `totali._confronta_colonne`).
- **`contrapposto` non vuol dire la stessa cosa sulle due letture.** Su `leggi_pdf` `Documento.contrapposto` è il
  verdetto del profilo (R10: confine fisico **e** tipo contrapposte o verifica); su `leggi_celle` è vero ogni volta
  che ci sono colonne L e R. Sulla lettura OCR `Profilo.coppie` e `Profilo.marcatori` sono sempre vuoti.
- **I nomi privati degli altri moduli sono copiati in `importers/lettore/_ereditati.py`** (fatto nella Fase 2): il
  lettore non importa più nulla di privato dall'importatore attuale, e la deriva delle copie la vedono
  `tests/lettore/test_ereditati.py`. Resta solo il pubblico `bilancio_classifier.classify_bilancio` (`profilo.py`).
- **MinerU numera le pagine da 0 (`page_idx`), `leggi_celle` da 1.** Passare `page_idx` tal quale sposta ogni
  blocco di una pagina (e rompe la prima); `diagnosi._leggi` somma 1. `Blocco.pagina` e il «p. N» delle frasi
  contano da 1 su entrambe le letture.
- **Limite noto: il tetto di tempo non ferma la lettura.** Scaduto il tetto la diagnosi esce `tempo`, ma il thread
  abbandonato può continuare a leggere il PDF (PyMuPDF) mentre l'import va avanti. Accettato; chi lo toglie passa
  una scadenza a `_pagine_pdf` e la controlla fra le pagine.

**Come si misura.** Due script, nessun import, nessun DB, nessuna rete; i PDF e le verità sono cifre di
clienti e restano fuori da git (`Test/` è ignorata):

```bash
# profilo: tipo, contrapposte, periodi sul campione (e con --rete il controllo su tutti i PDF di Test/)
IMPORT_CORPUS_ROOT=$PWD/Test backend/venv/bin/python tests/corpus/profili_campione.py --etichetta <nome>
# righe: totali stampati ritrovati e chiusi, periodi, mastri giusti, contro le due letture e la verità
IMPORT_CORPUS_ROOT=$PWD/Test backend/venv/bin/python tests/corpus/righe_campione.py --etichetta <nome> [--solo 395,1456]
```

Il secondo legge `tests/corpus/campione.json` (78 documenti; le scansioni si contano a parte, vanno per
`leggi_celle` solo con MinerU acceso), le letture `Test/_analisi-campione/<id>.json` e `opus/<id>.json`, la
verità `verita/<id>.json`, e scrive `Test/_analisi-campione/righe/<nome>/righe.json` e `righe.md`: le quote in
totale e per tipologia, e per documento i totali non ritrovati o non chiusi, i periodi sbagliati e i conti col
mastro sbagliato. Un totale è chiuso solo se è chiusa la riga che è quel totale (fra le righe della pagina con
quel valore, quella la cui etichetta somiglia di più alla voce annotata), non un'altra riga con lo stesso importo;
i chiusi si riportano in tre quote affiancate: letterale, senza i totali ritrovati solo su colonne di differenza o
percentuale, e senza quelli ritrovati solo su differenza, percentuale, dare o avere. I mastri si contano in due modi: *stretto* (il padre diretto ha il codice o il nome annotato, o il percorso di
legge stampato in testa all'etichetta, «1.B.2.4 Altri beni»)
e *tollerante* (anche un «Totale X» con X uguale al padre annotato, o che lo contiene, numerazione di legge a
parte, salendo per i totali fino al primo antenato che non è un totale: la lettura nomina la voce, «1) Verso
clienti», il lettore il totale stampato che la chiude, «Totale crediti verso clienti»). Le annotazioni
sbagliate note stanno in `CORREZIONI_ANNOTAZIONE`, non pesano e si elencano; oggi l'elenco è vuoto, perché le
prime (353, 1524-1526) il proprietario le ha corrette alla fonte.

### Il percorso del lettore (Fase 3)

> Codice: `importers/lettore/{foglie,tavola,classifica,componi,percorso}.py`, il gancio in
> `importers/import_snello/__init__.py` (`_tenta_lettore`), i mesi dell'anno precedente in
> `importers/pdf_importer.py` (`mesi_precedente`). La regola sul risultato è in
> [REGOLE-IMPORT-04 §14](REGOLE-IMPORT-04-QUADRATURE.md).

Dalla Fase 3 il lettore di questa sezione non solo diagnostica: **decide gli importi** di un PDF che i lettori
deterministici noti non hanno adottato. Il modello (Qwen su gx10) non scrive mai un importo: indica una **classe**
per un id di riga, e gli importi vengono dal testo (o dalle celle MinerU) attraverso il lettore.

**Dove sta.** In `importa()` dopo i lettori deterministici noti (`xbrl_reso`, schema con o senza codici, situazione
contabile) e **prima** del percorso del modello di §10; un documento che un lettore noto adotta ha gli stessi numeri
di prima. Il candidato passa per **lo stesso cancello** di ogni lettore deterministico
(`deterministico.esito`, nome pubblico di `_esito`): adottato o no lo decide quello, non il percorso. Se non è
adottato, o solleva, il percorso di §10 prosegue come prima; l'esito resta in
`report["lettore_percorso"]` (solo conteggi, chiamate, secondi, esito del cancello: mai etichette o importi, il
report finisce nel DB) e la fonte di un import adottato è `deterministico:lettore`. Interruttore
`IMPORT_LETTORE=0|false|no|off`: spento, nulla cambia rispetto a prima. Il contesto MinerU non arriva al percorso:
il lettore gira sul solo PDF.

**I passi, nell'ordine.**

1. **Foglie contate una volta e ancore** (`foglie.py`). Una foglia è una riga di prospetto che non è un totale e ha
   un importo sulla colonna; un mastro coi figli verificati non è mai foglia, e una voce che ripete i propri conti
   (importo uguale alla somma dei conti stampati sotto, **al centesimo**) è un'eco e si toglie. *Se si ignora:* si
   somma il mastro e i suoi figli e la massa raddoppia, e nessun cancello vede l'inflazione. Le ancore sono gli
   importi che il documento stampa e che le foglie devono rifare: un totale chiuso risolto a una macro-voce, più
   totale attivo, totale passivo e risultato d'esercizio. Il segno di una foglia è quello normale per il suo lato
   (F3-1): positivo = saldo naturale; un fondo rettificativo stampato col meno resta negativo.
2. **Il lato lo decide la colonna.** Una foglia dell'attivo cade solo su `sp01`-`sp10`, una del passivo su
   `sp11`-`sp18`; nel CE il verso (costo/ricavo) viene dal lato sulle contrapposte, dalla sezione di legge
   dell'antenato o dal segno D/A (F3-2), `None` se ignoto. Su uno schema a colonna unica il lato SP viene dalla
   sezione di legge dell'antenato o dalla pagina (F3-7). *Se si ignora:* una foglia dell'attivo finita su un campo del
   passivo sposta il pareggio senza che nessuno la veda.
   **L'unica eccezione sono le rettifiche stampate nella colonna opposta** (decisione del proprietario, 2026-11-09:
   «riusare il sistema del vecchio importatore»): un fondo ammortamento o svalutazione nella colonna del passivo, perdite
   portate a nuovo o azioni proprie in quella dell'attivo. L'enum di una foglia SP offre le macro del suo lato **più le
   sole rettifiche di quel lato** (`tavola.rettifiche_ammesse`): dal passivo `sp02.F`, `sp03.F`, `sp04.F`, `sp06.F`
   (fondo del bene, il percorso del bene + `.F` della legenda snello, `percorsi.e_fondo`), dall'attivo `sp12g.N`,
   `sp12h.N` (percorsi `SPP.A.VIII`/`SPP.A.X`, `percorsi.e_netto`). Il campo viene da `percorsi.campo_da_percorso`
   come nel percorso snello (`sp06.F` → `sp06a`). Nessun altro conto attraversa il lato; un fondo rischi, il TFR, un
   fondo imposte restano passività.
3. **Classificazione in due passi** (`classifica.py`). Passo 1: foglia → macro-voce. Il modello risponde con JSON
   guidato in cui **ogni id ha il proprio enum**, ristretto alle macro ammesse da *quel* lato e verso, più «X»
   («non è un conto»), riservata a ciò che non è un conto: il prompt dice che un saldo a lato invertito (un
   fornitore in dare fra le attività) è comunque un conto e va sulla voce ammessa più vicina, e il contesto di ogni
   riga di SP dice «attivo»/«passivo», non solo la colonna fisica. Una risposta fuori enum, «X» o assente lascia la
   foglia **senza classe** (fonte `nessuna`);
   un blocco che il provider non ha saputo evadere dà fonte `errore` (diverso da «X»). Il blocco troncato o
   troppo lungo si dimezza e si riprova fino a una foglia. Le foglie con la stessa etichetta, antenato, lato,
   sezione e verso si chiedono una volta (cache). Passo 2: **dentro ogni macro che ha dettagli** (`tavola.DETTAGLI`,
   i gruppi di `iv_cee_hierarchy.detail_fields`: `sp01`-`sp07`, `sp12`, `sp14`, `sp16`, `sp17`, `ce08`, `ce09`; non
   `ce17`, che decide il verso) la sotto-voce, con l'enum ristretto ai dettagli di quella macro più «altri»; un fondo
   (rettifica `.F`) sceglie il dettaglio del bene che rettifica, o resta sull'aggregato. **La macro non cambia mai** e
   un dettaglio non attraversa la propria macro-voce. Un dettaglio che il percorso di legge dice esattamente
   («5-bis) crediti tributari» → `sp06e`) **si tiene** senza chiedere; «altri» solo quando il dettaglio non si sa, e
   allora la massa va nel secchio «altri» della macro (`tavola.altri_di`: `iv_cee_hierarchy.residual_bucket` per
   l'SP, `residual_finalization.CE_BUCKETS` per il CE, quindi mai `ce09c` per ripiego). Decisione del proprietario
   (2026-11-09: «macro accounts first, then check for details, max details if possible, if not generic accounts»),
   che sostituisce la profondità «macro + KPI» del 2026-11-06: i dettagli legali gratuiti finivano in «altri» anche
   quando il percorso li diceva. Il passo 2 resta sotto lo stesso tetto di chiamate; le sue chiamate si dichiarano
   in `diagnostica["chiamate_dettagli"]` (anche nel report).
4. **Percorso legale solo se ben formato** (F3-9/F3-10). Una foglia il cui percorso di legge (dal proprio codice, dalle
   etichette o dall'antenato verificato) è ben formato (`foglie.percorso_valido`: livelli in ordine senza
   ripetizioni, voce che la tavola sa tradurre, lettera solo dove divide davvero la voce, scadenza solo dove la voce
   ha entro/oltre) prende la macro dalla tavola **senza chiamare il modello** (fonte `legale`); altrimenti `None` e
   decide il modello. Una lettera che non divide la voce («a) Rossi» sotto «1) verso clienti», la ripartizione
   «a) … entro») si toglie e resta la base, che deve valere da sola (F3-10). *Se si ignora:* un percorso sbagliato
   costa una macro sbagliata senza nessun modello a contestarla; uno mancante costa solo una chiamata. Una macro che
   il percorso dà ma il lato non ammette si scarta. (Task 9) Il totale generale di un lato («A) TOTALE STATO
   PATRIMONIALE - ATTIVO») non è un livello di legge: la sua lettera numera il lato, e un totale di sezione
   verificato sotto di lui teneva la «A» al posto della propria «C» (161: rimanenze e liquidità finite in `sp01`).
   Il romano col punto («II. Crediti») è un livello quando è un totale sotto una voce con lettera, nella catena
   verificata o nell'outline quando fa salire il romano aperto e divide davvero la voce del lato («SPA.C.IV» sì anche
   se manca III, «SPA.C.V» no: mai «V. ROSSI» fra i conti); «- entro/oltre esercizio successivo» è una scadenza come
   «esigibili entro», e come totale senza numero stampato sopra i suoi conti divide la voce, non la chiude. *Se si ignora:* il percorso manca, decide il modello sull'etichetta nuda, e
   «CREDITI V/SOCI» sotto «5-quater) verso altri» diventa crediti verso soci (`sp01`).
5. **Composizione** (`componi.py`): ogni foglia somma una volta sul suo dettaglio o sul secchio «altri»; gli
   aggregati sono la somma dei dettagli (`percorsi.completa`); `sp13` viene dal CE. La riga del risultato
   (`foglie.e_riga_del_risultato`: «Utile (perdita) dell'esercizio», o un'etichetta di sole parole del risultato
   come «Utile» fra i costi a pareggio) nel CE non è mai una foglia; nello SP lo è solo se **non** vale il risultato
   del periodo (a meno del segno, entro la soglia di adozione): allora è l'utile di un esercizio prima non ancora
   destinato e va in `sp12g` (utili/perdite portati a nuovo), dichiarato in `scelte`. *Se si ignora:* togliendo
   quella riga il passivo perde un conto vero del patrimonio netto e il foglio non quadra. Dettagli in
   [REGOLE-IMPORT-04 §14](REGOLE-IMPORT-04-QUADRATURE.md).
   **Una rettifica della colonna opposta si netta** sul bene o sul netto col segno opposto a quello con cui la sua
   colonna la conta (sul dettaglio se noto, altrimenti sull'aggregato: «senza dettaglio si netta all'aggregato»):
   attivo e passivo scendono della stessa massa e il pareggio resta. Poi le regole del percorso snello, riusate
   tali e quali da `conti.py` (copie in `_ereditati.py` con test di deriva): un dettaglio di `sp02`/`sp03`/`sp04`
   rimasto negativo passa all'aggregato (`netta_fondi_negativi`), un aggregato ancora negativo si azzera e
   l'eccedenza si dichiara (`clamp_immobilizzazioni_negative` → `diagnostica["immobilizzazioni_negative_tagliate"]`,
   nelle anomalie del report come per lo snello) e resta sbilancio dichiarato, mai spostata. I totali stampati sono
   **lordi**: la massa rettificata si dichiara in `_netted_contra` (la chiave del percorso C) e si toglie dai totali
   attivo e passivo che il cancello confronta (`percorso._stampati`), come `net_contra_accounts` chiede al chiamante;
   una macro ancorata conta le rettifiche stampate sotto di lei, non quelle portate dall'altra colonna.
   `fondi_gia_nettati` non serve qui: una voce netta e i conti che la ricostruiscono non sono mai entrambi foglie.
   **Un fondo segue il suo cespite** (F3-16): prima di comporre, ogni fondo `sp02.F`/`sp03.F` si accoppia a un
   cespite e si netta sulla macro (e sul dettaglio) dove il modello ha messo quel cespite, anche se il modello aveva
   nominato l'altra categoria. Prima per etichetta: il fondo che nomina un solo cespite (ogni sua parola, tolta la
   testa «F.DO AMM.» di `_FONDO_AMM_HEAD_RE`, è l'inizio di una parola del cespite: «F/AMM. LAV. STR. SU BENI DI
   TERZ» e «LAVORI STRAOR. SU BENI DI TERZI»); poi per famiglia, con le regole del percorso C per cespiti e fondi
   (`_sp02_detail_field`/`_sp03_detail_field`, copiate in `_ereditati.py`). L'etichetta viene prima perché la sola
   famiglia sbaglia sulle abbreviazioni («F/AMM.COSTI IMPIANTO» cadrebbe fra gli impianti). Entra solo se la famiglia ha ancora cespite lordo che lo contenga (fondo ≤ cespite, i
   fondi dal più grande); altrimenti resta la classe del modello e si dichiara in `scelte`. *Se si ignora:* fondo e
   cespite su macro diverse spostano massa fra `sp02` e `sp03` senza toccare il totale (budget_395, 1531): nessun
   cancello la vede.
5-bis. **Regole di testo e di aritmetica dopo il modello** (Task 11). Il modello sceglie la classe, ma alcune
   decisioni le prende il testo stampato o l'aritmetica, sempre dichiarate per id:
   - **Il contesto è il mastro, anche non verificato.** `Foglia.mastri` = `Riga.percorso` (i titoli sopra il conto,
     dalla sezione al padre); `Foglia.contesto` (i mastri, o gli antenati verificati se più lunghi) va nel prompt
     («sotto: …»), nella chiave della cache, nella scadenza dei debiti e nella natura delle rimanenze, mai negli
     importi. *Se si ignora:* il mastro di una catena di un solo conto («ALTRI DEBITI VERSO FORNITORI» sopra «FATTURE DA
     RICEVERE», «DEBITI VERSO BANCHE OLTRE 12 M» sopra un mutuo) non è un antenato verificato, e il modello giudica
     l'etichetta nuda, cambiando idea da una corsa all'altra.
   - **La scadenza dei debiti la decide il testo** (`classifica.scadenza_dei_debiti`, prima del passo 2): un debito
     del modello va su `sp17` solo con una prova stampata nel conto o nel mastro («oltre 12 mesi/l'esercizio», «lungo
     termine», «medio/lungo», «m/l», le sigle «(OE)»/«(EE)» dei gestionali), altrimenti su `sp16` (CLAUDE.md, «Debito senza scadenza dichiarata → a breve»;
     il mastro «medio/lungo» è una scadenza dichiarata, gli interessi sotto di lui restano entro). Il dettaglio passa
     alla stessa lettera. Le classi `legale` portano già la loro scadenza. `diagnostica["scadenze"]`.
   - **Imposte anticipate senza scadenza stampata oltre 12 mesi** (`imposte_anticipate_oltre`, dopo il passo 2,
     regola D14 del proprietario): `sp06f` → `sp07f` salvo un «entro» nel percorso, nel conto o nel mastro.
   - **Un saldo negativo passa all'altro lato, per natura** (`componi.saldi_negativi`, regole D2/D12/D15): la
     liquidità negativa (una banca, una carta di credito) è un debito verso banche (`sp16a`) conto per conto; un credito
     o un debito negativo passa di lato **solo se il campo su cui somma esce negativo** (credito → `sp16e` se
     tributario, altrimenti `sp16g`; debito → `sp06e` se tributario, `sp09` se verso banche, altrimenti `sp06g`): una nota di credito da
     ricevere fra i fornitori rettifica una voce che resta positiva e lì resta nettata.
     Attivo e passivo salgono della stessa massa: il pareggio resta, e le ancore (di partenza e di arrivo) e i totali
     passati al cancello contano la massa spostata (`Composizione.spostati`, `percorso._stampati`). Fondi e rettifiche
     col meno restano dove sono. *Se si ignora:* il secchio «altri» esce negativo.
   - **Un contro-conto si riconosce dal nome**: l'enum offre i `.F` solo a un conto che si dice fondo, ammortamento,
     svalutazione o rettifica, i `.N` solo a perdite, azioni proprie o riserve negative. *Se si ignora:* il modello
     usa il `.F` per un conto che non trova posto sul lato (banche in avere sotto le disponibilità liquide nettate sui
     crediti verso clienti), massa spostata fra lati che nessun cancello vede.
   - **Una foglia di SP che il modello chiama risultato** (`sp13`) si tratta come la riga del risultato: lo è solo se
     ne vale l'importo, altrimenti va su `sp12g`. *Se si ignora:* «Utili portati a nuovo» scartato, foglio sbilanciato.
   - **Lavori in corso su ordinazione in A.3** (`rimanenze_ce.voce_rimanenze`, regola W4): le commesse vanno su `ce03`;
     `natura_rimanenze` resta invariata per i lettori di oggi.
   - **Il fondo segue il cespite anche nel secchio «altri»**: un cespite senza dettaglio somma sul secchio della macro
     e il suo fondo abbinato va lì, non sull'aggregato.
   - **Il prompt porta le regole di classificazione del proprietario** (natura sul mastro del gestionale: amministratori
     in B.7, somministrato in B.9, cauzioni fra le immobilizzazioni finanziarie, versamenti in conto capitale fra le
     riserve, migliorie su beni di terzi fra gli immateriali, TFR solo il fondo; nel passo 2 carte di credito verso banche, soci e finanziamenti agevolati verso altri finanziatori, fatture da ricevere
     verso fornitori, acconti dei clienti e debiti verso il gruppo fra gli altri debiti, ammortamenti senza categoria
     sui materiali, riserve di rivalutazione di legge, merci fra i prodotti finiti e merci).
   - **Dopo l'adozione dettagli e scadenze non si rifanno** (`pdf_importer._dettagli_gia_letti` →
     `dettagli_letti_dal_lettore`, come per il reso XBRL). *Se si ignora:* la ricerca dei dettagli rilegge il documento
     e `reclassify_ledger_maturities` riscrive `sp16`/`sp17` contro la scadenza decisa dal testo: la correzione del lettore
     non arriva al DB. (Dal 2026-11-09 quella funzione non ha più l'eccezione «finanziamenti e mutui oltre 12 mesi»:
     senza scadenza stampata ogni debito, mutui compresi, va a breve; politica `default-short-v2`.)
6. **Voti sui blocchi che non tornano** (F3-11). Se una macro ancorata (`sp06`, `ce08`, …) non rifà il proprio
   totale stampato oltre 1 €, **solo le sue foglie** si rivotano, tre volte a temperatura 0 con **tre presentazioni
   diverse** (altrimenti la stessa domanda darebbe tre volte la stessa risposta): ogni riga coi soli antenati;
   il blocco con l'ancora, il totale stampato e la somma di oggi (mai un importo di foglia); il blocco in ordine
   inverso coi fratelli. Vince la maggioranza stretta di risposte valide; senza maggioranza resta la classe di prima.
   Mai rivotate le foglie `legale`, né per un totale generale (attivo, passivo, utile): non dipendono dalla classe,
   il lato lo decide la colonna. Un documento che quadra al primo passo non costa un voto.
7. **Anno precedente** (F3-14). Le foglie della colonna precedente si accoppiano per id a quelle della corrente e
   usano **le stesse classi**; quelle presenti solo nel precedente entrano nello stesso giro, senza chiamate in
   più. Il precedente passa per lo stesso cancello (esito `ok`, nessun tappo, massa non classificata sotto soglia),
   altrimenti si scarta e `prior_rifiuto` dice perché; si scarta anche quando un'ancora della sua colonna non torna
   (`controllo: blocchi`). La durata viene dalla colonna del lettore
   (`Colonna.mesi`, `diagnostica["mesi_precedente"]`) e vale **anche a periodo pieno**, ma una durata diversa da 12 si
   dichiara solo se la colonna stampa anche l'inizio del periodo (senza, `mesi` conta da gennaio e un esercizio non solare
   1/7-30/6 risulterebbe di 6 mesi: `None`, anno intero come prima): un comparato di 9 mesi non si
   salva mai come anno intero (`period_months` = mesi), e un 12 dichiarato vale come durata nota. *Se si ignora:* un
   parziale salvato come anno pieno diventa un anno base falso.
8. **Guardia di costo, tetto e interruttore** (F3-15). Dopo il primo errore del provider (eccezione o timeout, non una risposta troncata)
   il documento non chiama più il modello: esce non adottabile con `motivo: modello_non_disponibile` e prosegue il percorso di oggi. Prima di ogni chiamata, se i lati delle foglie sono noti e attivo ≠ passivo
   (più l'utile letto dal CE) oltre la soglia di adozione, il percorso esce non adottabile con
   `motivo: foglie_non_in_pari` (o `senza_foglie_sp`) **senza chiamare il modello**: nessuna classe può rimediare,
   perché la colonna decide il lato. La guardia usa **la stessa regola della composizione** (`componi.lato_sp`,
   `importo_sp`, `e_risultato`): somma solo le foglie di sezione `SP`, la riga del risultato non conta, e il
   risultato candidato è zero, l'utile delle foglie di CE o l'utile stampato col suo segno. Un lato ignoto, una
   foglia di sezione ignota con un importo o un verso di CE ignoto non attivano la guardia (non lo so, non blocca). Tetto di
   `MAX_CHIAMATE = 40` per documento: oltre, il modello non è più chiamato, le foglie restano senza classe e il
   report dichiara `tetto_chiamate`.

**Non solleva mai.** Qualsiasi errore dà bs/ce vuoti e `diagnostica["errore"]`; il modello che non risponde o cade a
metà lascia il documento non adottato e l'import prosegue sul percorso di §10.

**Le correzioni al lettore delle Task 2b/2c** (cambiano quali righe sono foglie, non le regole sopra):

- sezione SP/CE assegnata anche su schema con dettaglio e bilanci di verifica, e ripresa a metà documento;
- un «-» finale nell'etichetta («Utile (Perdita) dell'esercizio -») è un segno, ma solo quando un totale stampato lo
  conferma; il «meno staccato» non si decide da una soglia;
- due tabelle affiancate (attivo e passivo sulla stessa pagina) hanno i lati dai titoli delle due metà, che vincono
  sul flusso di lettura;
- lato su tipo ignoto dedotto dalle sezioni;
- lettera D/A staccata prima dell'importo riconosciuta (marcatore per colonna, §11);
- (Task 9) un riepilogo di righe di chiusura subito sotto il titolo di sezione («Totale Costi: / Perdita
  d'Esercizio:» sotto «Conto Economico») non chiude la pagina, e «COSTI, SPESE E PERDITE / RICAVI E PROFITTI» è il
  titolo del conto economico: le pagine dopo non restano più senza sezione;
- (Task 9) le parole scritte in verticale a schermo (un timbro sul margine) si tolgono prima di formare le righe:
  alte quanto tre righe contabili, le univano in una sola e ne perdevano gli importi;
- catene di voci a uguale importo (eco, k=1): contate una volta;
- titolo di lato che porta il proprio totale («STATO PATRIMONIALE ATTIVO» seguito dal suo totale) ancora, solo se attivo e
  passivo coincidono: un titolo con un numero senza quella prova resta un titolo.

**Le correzioni al lettore della Fase 5** (2026-11-11, piano `docs/superpowers/plans/2026-11-11-fase5-contrapposte-lettura-e-classificazione.md`;
le misura offline `tests/corpus/foglie_campione.py`, che ripete il percorso fino alla guardia di costo senza modello e
confronta le foglie documento per documento):

- **sezione all'indietro** (`profilo._sezioni_dalle_chiusure`): una riga ancora senza sezione prende quella del primo
  totale di chiusura con importi che la segue (attività/passività lo SP, costi/ricavi il CE), anche nelle pagine
  prima; un titolo ferma la propagazione, e le righe sotto un titolo «nessuna sezione» restano senza. La chiusura di
  una pagina conta solo dopo il suo ultimo titolo, e «TOTALE ATTIVO CIRCOLANTE» non chiude lo SP;
- **anagrafica** (`righe._pezzi_della_riga`): «PIAZZA …», «PARTITA IVA …» si scartano solo su una riga senza codice o
  senza importi: un conto col codice e l'importo resta un conto;
- **totale di mastro senza conti** (`foglie._totale_senza_conti`): «Totale CLIENTI ITALIA:» subito sotto il titolo del
  suo mastro, senza conti in mezzo e senza figli in nessuna colonna, è l'unico portatore della massa e diventa una
  foglia. Il titolo deve finire col nome del totale (davanti solo il codice, in cifre o abbreviato); mai una voce di
  legge, mai un totale di chiusura;
- **colonna spuria** (`foglie._piene`, `_dominante`): una colonna senza data con meno di un decimo delle celle della
  più piena del suo lato non è mai corrente né precedente; l'unica colonna piena di un lato è la sua corrente;
  sull'altro lato senza corrente datata vale la colonna dello stesso ruolo, se è una sola, o quella con almeno il
  doppio delle celle di ogni altra. Due colonne piene senza data restano senza scelta;
- **«di cui» che ripartiscono la voce** (`foglie._di_cui_che_ripartiscono`): due o più «di cui» che sommano
  esattamente la voce sopra, e sono i suoi soli figli, ne sono le foglie, con la scadenza stampata;
- **«Eccedenza esercizio precedente»** è un conto del patrimonio netto, non una riga di controllo;
- **R22 sulle altre riserve**: la voce «Altre riserve» all'unità sopra il suo solo conto al centesimo chiude fino a
  10 € (la riserva da arrotondamento all'euro sta lì per legge); altrove resta l'euro;
- **testata dei costi negativa** (`totali._bersaglio`): «B) Costi della produzione» stampata fra parentesi sopra i
  costi positivi chiude sul suo valore assoluto;
- **riga di legge fusa** (`foglie._VOCE_FUSA`): «C) Proventi e oneri finanziari - 17) Interessi» è la voce C.17, non un
  risultato; un costo di legge stampato col meno dentro un risultato è un costo positivo.

**La classificazione della Fase 5** (`importers/lettore/classifica.py`):

- **scadenza dei crediti** (`scadenza_dei_crediti`): come per i debiti, sp06/sp07 li decide il testo stampato (conto o
  mastro), senza prova entro l'esercizio; le forme riconosciute comprendono «TERMIN» troncato, «MEDIO LUNGO» senza
  barra, «>12 mesi», «<12 mesi». I totali stampati di crediti e debiti entro/oltre decidono più della regola di
  testo (`percorso._scadenze_contro_ancore`). Il modello non sceglie mai entro/oltre;
- **regole del proprietario nelle istruzioni** (`importers/lettore/regole_proprietario.py`, interruttore
  `IMPORT_REGOLE_NEL_PROMPT`, **acceso per default** dal 2026-11-11, `0` = prompt di prima): le regole di giudizio sulla natura (D3-D16, P5-P7, W4, R3-*),
  una riga ciascuna, entrano nei prompt della macro-voce e dei dettagli; la frase sul saldo a lato invertito resta
  per un fornitore qualunque a saldo dare (altri crediti), mentre P6 vale per i conti che si dichiarano anticipo,
  acconto o caparra; un fondo svalutazione o rischi su crediti rettifica i crediti verso clienti, mai un fondo
  rischi (toglierla del tutto, nella prima versione, mandava il fornitore fra i ratei e il fondo rischi su crediti
  fra i fondi rischi: 1531); `ce18`/`ce19` escono dalle classi ammesse (D6); ogni riga
  porta anche il codice del conto, e la cache distingue due conti con lo stesso nome e codici diversi. Decisione del
  proprietario (2026-11-11): niente correzioni a parole chiave, la voce la sceglie il modello;
- **il lettore prima del parser delle situazioni contabili** (`IMPORT_LETTORE_PRIMA`, **acceso per default** dal
  2026-11-11, decisione del proprietario sulla misura qui sotto; `0` torna al parser prima): quando
  `situazione_contabile_parser` quadra, il percorso del lettore prova per primo, con lo stesso cancello; se non
  adotta resta il parser com'è.

*Misura della Fase 5 (86 documenti × 3 giri, giro `fase5-ee2a506`, 2026-11-11, con `IMPORT_LETTORE_PRIMA=1` e
`IMPORT_REGOLE_NEL_PROMPT=1`, contro `base5-86`): macro-voci esatte 79,2% → 81,7%, dettagli KPI 79,1% → 83,2%, altri
dettagli 78,7% → 82,8%, esito giusto 97,3% → 97,7%. Sulle contrapposte macro 64,5% → 70,6%, KPI 62,6% → 77,5%,
dettagli 53,2% → 72,3%; sui conti a colonne 56,8% → 59,4%, KPI 58,7% → 54,4%, dettagli 55,7% → 57,9%. Il lettore adotta
25 documenti (17 delle 24 contrapposte), uno instabile nell'adozione (1523). Peggiorano, fra i documenti che il lettore
adottava già, 1523, 1531 e 1566 (KPI), di poco 1407, 1440, 1567. I lettori deterministici, rifatti offline, danno numeri
identici a `main`; le poche differenze sui loro documenti vengono dalle chiamate al modello del passo dei dettagli.
Rinunce che restano: massa non classificata (1325, 1401, 229, 615, COLOMBO), oltre soglia (1452, 281), foglie non in
pari (588, 680, 1410, 1430). Costo per import adottato: mediana 6 chiamate (max 11), 69 s di lettore (max 142 s).*

*Le due leve separate (39 documenti × 3: contrapposte, conti a colonne e i documenti adottati dal lettore; macro / KPI
/ dettagli). Base `base5-86`: 66,3 / 66,5 / 63,0. Solo `IMPORT_LETTORE_PRIMA` (`fase5-soloprima-d33f5e5`): 69,3 / 72,5 /
71,7, contrapposte 70,1 / 73,9 / 70,6, nessuna perdita sugli altri adottati. Più le regole riviste
(`fase5-regole-e4be5f1`): 70,7 / 74,2 / 73,2, contrapposte 71,6 / 76,6 / 72,2, conti a colonne 55,6 / 54,0 / 52,6;
documenti instabili 12 in entrambi i giri (6 nella base), nessuno instabile nell'adozione. Restano sotto il solo
lettore-prima 337 e 158 (KPI) e di poco 1531 (macro). Su questi numeri il proprietario ha acceso entrambi gli
interruttori (2026-11-11).*

*Misura sul campione (78 documenti × 3 giri, `tests/corpus/punteggio.py`, giro `fase3-4de18b6`, 2026-11-09, contro `fase3-502f078` del primo innesto): dei 9 documenti il cui PDF quadra ma l'import no alla Fase 2, **7 escono quadrati in tutti i giri** (contro 2); i due fuori sono attesi (massa non classificabile; foglie davvero non in pari, attivo e passivo affiancati). Documenti salvati sbilanciati 12 → 7, nessuno nuovo. 11 documenti adottati dal lettore, nessuno instabile nell'adozione. Macro-voci esatte 78,7% → 80,6%, dettagli KPI 76,4% → 80,3%, altri dettagli 75,5% → 78,7%. Costo per import adottato: mediana 6 chiamate al modello (max 9, tetto 40 mai toccato), 66 s di lettore (max 153 s).*

*Misura della Fase 4 (78 documenti × 3 giri, giro `fase4-ad2b581`, 2026-11-09, contro `fase3-4de18b6`, percorso classico acceso come ripiego): il lettore adotta **14 documenti** (prima 11), nessuno instabile nell'adozione; i documenti salvati dal modo `legge` scendono da 6 a 4 (restano 161, 1426, 1445 e 1533, i quattro aperti: massa non classificabile, gerarchia senza totali, blocchi di CE, un'eco di 1,30 € che si chiuderebbe solo con un tappo). Documenti salvati sbilanciati 7 → 5, nessuno nuovo; i bersagli restano 7/9 quadrati in tutti i giri. Macro-voci esatte 80,6%, dettagli KPI 80,3% (invariati), altri dettagli 78,7% → 79,5%. I lettori deterministici cambiano numeri solo per A.4 che passa in `ce03a` (Task 5-bis) e su due documenti che ora coincidono con la verità. Il ripiego classico serve solo a tre documenti che nessun percorso snello legge (`non_applicabile`). Costo per import adottato: mediana 6 chiamate (max 9), 64 s di lettore (max 129 s). Due documenti adottati dal lettore perdono un campo: su uno, un conto di 4.178 € classificato dal modello passa da altri debiti a ratei passivi (il lettore è identico byte per byte prima e dopo: è la variabilità del modello); su un altro, 10,57 € di B.III.2.d-bis senza un percorso di legge vanno in `sp07g`.*

### Il ripiego sul percorso classico si può spegnere (Fase 4, 2026-11-09)

`IMPORT_RIPIEGO_CLASSICO` è **acceso per default**; `0`/`false`/`no`/`off` lo spegne
(`pdf_importer._ripiego_classico_acceso`). Quando lo snello non adotta un documento, o non è stato tentato, il motivo
si dichiara sempre in `validation_report["import_snello"]["ripiego_classico"]` (`usato`, `motivo`, da
`_motivo_ripiego_classico`), acceso o spento. Spento, il documento non passa all'importatore classico: esce con un
`PDFImportError` («percorso classico spento (IMPORT_RIPIEGO_CLASSICO=0) e il percorso snello non ha adottato il
documento (motivo)») prima di salvare qualunque cosa. Conta solo col motore snello: con `IMPORT_MOTORE=classico`
non ha effetto. È l'interruttore dei giri di misura «a classico spento»: dice quali documenti si reggono solo sul
classico.

### I parser di layout sono congelati (Fase 4, 2026-11)

Con il percorso generico del lettore, i parser per singolo layout di gestionale dentro
`importers/situazione_contabile_parser.py` non crescono più: da qui **solo correzioni di errori**, e un layout
nuovo si insegna al lettore (`importers/lettore`). L'elenco è `PARSER_DI_LAYOUT` (dodici nomi: i `parse_entries*`
per AGO, DEPI, 8 cifre, verifica I/E, mastri, sub-mastro, SEZBIL, TeamSystem, colonna singola e il generico,
più `parse_bilancio_verifica_segno` e `extract_contrapposte_best_effort`).
`tests/test_parser_layout_congelati.py` ricava i parser dal modulo (funzioni pubbliche di livello modulo
`parse_*`/`extract_*`, dispatcher `extract_situazione_contabile` escluso) e fallisce se ne trova uno fuori
dall'elenco. La regola e il danno a violarla stanno in CLAUDE.md, «Invarianti e trappole › Estrazione e classificazione».
