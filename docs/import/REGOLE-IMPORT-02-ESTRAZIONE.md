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
| 5 | **Identità CE↔SP** (diagnostica, tutte le route) |
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

## 4. Route C: la scelta del candidato è la regola più importante

Due candidati concorrono: il **CoGe-LLM** e il **parser deterministico**. Il deterministico gira
sempre, perché è gratuito e non può peggiorare il risultato.

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
perfetto — e il debito persistito resta sottostimato senza un solo avviso. La quantità misurata è
costruita per essere confrontabile con il totale *stampato*: `totale_passivo − utile + massa nettata`
(il risultato è esposto dal documento come riga di pareggio fuori dal totale di colonna; i fondi sono
righe della colonna destra che la ricostruzione porta in detrazione dell'attivo).

**Il segno del risultato viene dall'identità che ha validato i totali**, non dall'ordine delle
chiavi: un documento stampa spesso sia una riga "utile" sia una "perdita" (una delle due dell'anno
precedente, o una didascalia a zero), e preferire l'utile ribalta il risultato quando è il ramo
della perdita a tornare.

### Le due regole di merito della ricostruzione

**Scadenza non determinata → a breve, per prudenza.** I mastri non dicono se un debito è entro o
oltre l'esercizio. In assenza di un segno che li distingua i debiti vanno **a breve**: anticipare
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

Modello **Claude Haiku 4.5** (`claude-haiku-4-5-20251001`), 8192 token di output, chiamato con
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

## 5-bis. MinerU: l'OCR opzionale, e perché non è in produzione

> Motori: `importers/mineru_adapter.py`, `backend/app/services/mineru_client.py`, configurazione
> in `backend/app/core/config.py`. Endpoint dedicato: `POST /import/pdf-ocr`.

Backend OCR alternativo per i PDF scansionati che il text layer non riesce a leggere. È un
**percorso separato** da quello descritto a pagina 01 §5 (OCR locale a coordinate → OCR vision),
con un endpoint proprio.

> ⚠️ **Solo macchina di sviluppo. MinerU non va MAI sul VPS.** La sua immagine è
> `FROM vllm/vllm-openai`: gigabyte di layer orientati alla GPU. Il servizio sta dietro il
> **compose profile** `mineru`, che lo esclude da *ogni* comando compose — **`build` compreso** —
> se il profile non viene richiesto. È ciò che conta, perché il `Jenkinsfile` esegue
> `docker compose build --no-cache --parallel` e poi `up -d` sul VPS di staging: senza il profile
> quel build si tirava dietro vLLM. Per la stessa ragione `MINERU_OCR_ENABLED` è **false** di
> default nell'env del backend in compose.

In locale:

```bash
MINERU_OCR_ENABLED=true docker compose --profile mineru up -d
# con NVIDIA:
MINERU_OCR_ENABLED=true docker compose --profile mineru \
  -f docker-compose.yml -f docker-compose.gpu.yml up -d
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

## 7. L'anno precedente ha uno standard più severo

L'anno corrente viene salvato anche se solo strutturalmente valido. Il **precedente no**: deve
superare *sia* `validate_balance` *sia* la quadratura piena.

- Se tutti i suoi campi sono zero → PDF monocolonna, scartato in silenzio.
- Se non supera il gate → **non viene mai persistito**; un record già esistente viene
  **preservato**; l'utente riceve "ANNO PRECEDENTE NON IMPORTATO [anno]".
- Se lo supera → sostituisce l'eventuale record esistente, forzato ad anno pieno.

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
