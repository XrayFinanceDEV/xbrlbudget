# 14 — Piano di implementazione Import OCR con MinerU

> **Data:** 2026-07-22  
> **Stato:** pronto per l'esecuzione; nessuna modifica applicativa è inclusa in questo documento  
> **Perimetro:** nuovo endpoint backend per importare un PDF tramite MinerU Docker, riuso della pipeline contabile esistente e nuova opzione **PDF OCR (MinerU)** nell'import infrannuale

## 1. Obiettivo

Aggiungere all'importazione infrannuale una modalità esplicita **Import OCR** che:

1. invia il PDF a un servizio MinerU eseguito nella stessa rete Docker;
2. forza l'OCR e recupera testo, tabelle, ordine di lettura e struttura per pagina;
3. passa queste evidenze alla pipeline contabile esistente;
4. usa mapping deterministico e, quando necessario, LLM sui contenuti MinerU;
5. esegue sempre i controlli contabili deterministici già presenti;
6. salva `FinancialYear`, stato patrimoniale e conto economico soltanto se i gate finali sono superati;
7. lascia invariati l'import XBRL, l'import PDF standard e il caricamento del bilancio storico mancante.

Il flusso applicativo completo sarà:

```text
Utente seleziona "PDF OCR (MinerU)"
  → frontend importOCR(...)
  → POST /api/v1/import/pdf-ocr
  → validazione utente, azienda e PDF
  → MinerU Docker POST /file_parse
  → MinerUExtractionContext
  → classificatore esistente A/B/C
  → candidato deterministico MinerU
  → parser deterministico attuale come controllo indipendente
  → eventuale candidato LLM sul testo MinerU
  → scelta del candidato sostenuto dalla fonte
  → gerarchie IV CEE e riconciliazioni esistenti
  → quadratura Attivo/Passivo + CE/SP + dettaglio/aggregati
  → persistenza FinancialYear
  → controllo presenza anno storico
  → creazione scenario infrannuale tramite il flusso frontend esistente
```

MinerU è un estrattore documentale, non il motore contabile. Non può decidere quadrature, creare plug, inventare dettagli IV CEE o rendere valido un bilancio che non supera i gate attuali.

## 2. Decisioni funzionali

### 2.1 Interfaccia utente

Nel selettore **Tipo di file** dell'import infrannuale saranno disponibili:

- `PDF` — percorso attuale `/import/pdf`;
- `PDF OCR (MinerU)` — nuovo percorso `/import/pdf-ocr`;
- `XBRL` — percorso attuale `/import/xbrl`.

Quando è selezionato `PDF OCR (MinerU)`:

- il pulsante mostra **ImportOCR e continua**;
- durante l'attesa mostra **Estrazione MinerU e analisi contabile…**;
- la chiamata usa obbligatoriamente MinerU;
- se MinerU non è disponibile non avviene alcun fallback silenzioso su `/import/pdf`;
- al termine vengono mostrati motore OCR, metodo di estrazione, livello di dettaglio e avvisi.

Il caricamento del bilancio storico mancante continua a chiamare `importPDF(...)` senza `period_months`. L'XBRL continua a usare `importXBRL(...)`. La creazione dello scenario infrannuale resta successiva all'import e all'eventuale verifica dell'anno storico, come nel flusso attuale.

**Perimetro deliberato della fase 1: solo l'import infrannuale.** La pagina `/import`
(bilanci annuali) NON riceve l'opzione OCR in questa fase, anche se i bilanci annuali
scansionati esistono. Motivo: limitare il canary a un solo punto di ingresso. L'estensione
a `/import` è prevista come fase successiva, riusando lo stesso endpoint
`/import/pdf-ocr` senza modifiche backend; va tracciata come task separato, non è una
dimenticanza.

### 2.2 Contratti non negoziabili

- Nessuna voce contabile senza evidenza nel documento.
- Nessuna suddivisione breve/lungo o categoria di debito inventata.
- Nessuna quadratura ottenuta creando cassa, debito, utile o riserve fittizie.
- Tutti gli importi contabili usano `Decimal`, mai `float`.
- I totali legali espliciti prevalgono sulle somme inferite, ma totale e dettagli devono riconciliarsi.
- Un risultato MinerU vuoto, ambiguo o incoerente produce un errore esplicito.
- Un errore MinerU o contabile non lascia `FinancialYear`, `BalanceSheet` o `IncomeStatement` parziali.
- Il record tecnico dell'upload può restare con stato `error`, come previsto dall'attuale `upload_tracker`.
- Il contenuto del bilancio, Markdown e JSON MinerU non viene scritto nei log.
- Il vecchio `/import/pdf` deve restare funzionante senza MinerU.

## 3. Stato attuale e punti d'integrazione

| Area | Stato attuale | Punto di modifica |
|---|---|---|
| Docker | servizi `backend`, `frontend`, `nginx`; nessun MinerU | `docker-compose.yml` |
| Endpoint PDF | `POST /import/pdf` | `backend/app/api/v1/imports.py` |
| Pipeline PDF | `import_pdf_balance_sheet(...)` apre la propria sessione e instrada A/B/C | `importers/pdf_importer.py` |
| Classificatore | accetta già `file_path` e testo estratto | `importers/bilancio_classifier.py` |
| Gerarchie | aggregati e dettagli IV CEE già definiti | `importers/iv_cee_hierarchy.py` |
| Client frontend | `importPDF(...)`, timeout 300 secondi | `frontend/lib/api.ts` |
| Import iniziale | il PDF chiama `importPDF(...)` | `frontend/app/infrannuale/page.tsx` |
| Import storico | chiamata separata a `importPDF(...)` | `frontend/app/infrannuale/page.tsx` |
| Proxy | timeout API 300 secondi | `nginx/default.conf` |

Non verrà introdotto un secondo schema contabile. L'adattatore MinerU deve produrre evidenze documentali che alimentano i campi e le relazioni già presenti.

## 4. Deployment MinerU con Docker

### 4.1 Versione e immagine

La versione è bloccata su quella **realmente in esecuzione e verificata** sulla macchina:

```text
MinerU 3.2.0  (immagine xbrlbudget-mineru:3.2.0, comando "mineru-api")
```

> **Nota (2026-07-22):** il piano ipotizzava 3.2.1, ma il container deployato e healthy è
> **3.2.0** (verificato via `/health` live). L'integrazione è ancorata a 3.2.0: fixture
> contrattuali (`tests/fixtures/mineru/openapi.json`, `health.json`) catturate dal
> container reale. La risposta contabile `file_parse_response.json` è stata sostituita
> con un equivalente sintetico anonimizzato. Passare a 3.2.1 richiede pull/build
> dell'immagine e ri-verifica del contratto.

Non si deve costruire in produzione direttamente da `master`. Il Dockerfile MinerU va acquisito dalla release bloccata, conservato nel repository o scaricato in build usando commit/tag e checksum verificabili.

File previsti:

- modifica `docker-compose.yml`;
- nuovo `docker/mineru/Dockerfile` oppure immagine interna equivalente, costruita dalla release bloccata;
- eventuale `docker/mineru/mineru.json` per la configurazione locale dei modelli;
- aggiornamento del file `.env.docker.example`, se presente, senza inserire segreti o percorsi macchina-specifici.

Prima di scegliere l'immagine definitiva, eseguire una prova sulla macchina di destinazione. MinerU supporta Docker su Linux e Windows/WSL2; il backend `pipeline` può lavorare su CPU. L'accelerazione GPU va abilitata soltanto dopo verifica di driver, runtime NVIDIA e memoria disponibile.

### 4.2 Servizio Compose

Configurazione obiettivo:

```yaml
services:
  mineru:
    build:
      context: .
      dockerfile: docker/mineru/Dockerfile
    command: ["mineru-api", "--host", "0.0.0.0", "--port", "8000"]
    expose:
      - "8000"
    environment:
      MINERU_MODEL_SOURCE: local
      MINERU_API_MAX_CONCURRENT_REQUESTS: "1"
      MINERU_API_TASK_RETENTION_SECONDS: "3600"
    volumes:
      - mineru-models:/root/.cache
      - mineru-output:/app/output
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 10
      start_period: 120s
    restart: unless-stopped
```

**Il backend NON deve dichiarare `depends_on` su MinerU** (né `service_healthy` né altro):
con un `depends_on: condition: service_healthy` il backend non partirebbe affatto se MinerU è
unhealthy (immagine rotta, modelli mancanti), buttando giù TUTTI gli import — XBRL e CSV
compresi — in contraddizione con i contratti §2.2 ("il vecchio `/import/pdf` deve restare
funzionante senza MinerU") e §14 ("MinerU non disponibile produce 503"). La disponibilità di
MinerU è responsabilità **runtime** del client backend: `MinerUClient.health()` prima di ogni
parse, e 503 controllato sul solo percorso `/import/pdf-ocr` quando fallisce.

Il comando del healthcheck va verificato sull'immagine bloccata: molte immagini MinerU/sglang
**non includono `curl`**. Alternativa robusta senza dipendenze extra:
`test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]`.

Il servizio non pubblica porte sull'host e non viene esposto da nginx. Solo il backend lo raggiunge come `http://mineru:8000` sulla rete Compose.

I nomi dei volumi e il percorso cache definitivo devono essere verificati contro l'immagine bloccata. `MINERU_MODEL_SOURCE=local` va attivato in produzione soltanto dopo avere predisposto i modelli nel volume o nell'immagine: non deve trasformare il primo avvio in un errore per modelli assenti.

### 4.3 Configurazione backend

Variabili previste:

```dotenv
MINERU_OCR_ENABLED=true
MINERU_BASE_URL=http://mineru:8000
MINERU_EXPECTED_VERSION=3.2.0
MINERU_BACKEND=pipeline
MINERU_PARSE_METHOD=ocr
MINERU_LANGUAGE=latin
MINERU_TIMEOUT_SECONDS=600
MINERU_CONNECT_TIMEOUT_SECONDS=10
MINERU_MAX_RESPONSE_BYTES=209715200
```

> **Correzione lingua (verificata sull'OpenAPI reale):** MinerU **non ha un'opzione
> `lang_list=it`**. L'italiano è coperto dal modello OCR **`latin`** (l'OpenAPI elenca
> esplicitamente "Italian" sotto `latin`). Usare `it` selezionerebbe una lingua
> inesistente. Il default resta quindi `MINERU_LANGUAGE=latin`.

`MINERU_OCR_ENABLED` è `true` nell'ambiente integrato: il percorso standard e quello OCR
devono essere entrambi disponibili. Può essere impostato a `false` come kill switch backend.

**Scelta frontend esplicita.** Per un PDF il frontend mostra contemporaneamente due azioni:
**Importa standard e Continua** e **ImportOCR (MinerU) e Continua**. La capability
`ocr_available` resta disponibile per diagnostica/preflight, ma non nasconde il secondo
percorso. `MINERU_OCR_ENABLED=false` è il kill switch backend e produce un 503 controllato
soltanto sul percorso OCR; l'import standard continua a funzionare.

**Timeout a catena sfalsati, non tutti uguali.** La pipeline contabile inizia dopo MinerU:
proxy e browser devono quindi lasciare margine anche alla riclassificazione e al fallback
LLM, oltre a permettere al backend di restituire il 504 MinerU controllato. Valori prescritti:

| Livello | Timeout |
|---|---:|
| Client MinerU (`MINERU_TIMEOUT_SECONDS`) | 600 s |
| nginx `proxy_send/read_timeout` | 1200 s |
| Frontend `importOCR(...)` | 1.260.000 ms |

Ogni livello esterno deve avere margine sufficiente perché quello interno fallisca in modo
controllato e il messaggio d'errore arrivi all'utente.

### 4.4 Capacità e pulizia

- Limite iniziale: una richiesta MinerU contemporanea.
- `/file_parse` usa internamente il task manager MinerU e può accodare richieste.
- I due worker Uvicorn del backend non devono aggirare il limite: la capacità viene applicata dal servizio MinerU.
- Il client deve leggere, quando disponibile, `queued_ahead` e trasformarlo in diagnostica tecnica, senza esporre contenuto del documento.
- Output e task MinerU devono avere retention limitata; il backend non deve dipendere da file temporanei dopo la risposta.
- A regime, metriche minime: durata, esito, dimensione PDF, pagine, righe/tabelle riconosciute, attesa in coda e codice di errore.

## 5. Client MinerU nel backend

Nuovo file:

```text
backend/app/services/mineru_client.py
```

`httpx==0.28.1` è già presente nelle dipendenze backend, quindi non serve introdurre un secondo client HTTP.

### 5.1 Interfaccia proposta

```python
class MinerUUnavailableError(Exception): ...
class MinerUTimeoutError(Exception): ...
class MinerUInvalidOutputError(Exception): ...
class MinerUContractError(Exception): ...

class MinerUClient:
    async def health(self) -> MinerUHealth: ...
    async def parse_pdf(
        self,
        *,
        content: bytes,
        filename: str,
    ) -> MinerURawResult: ...
```

**Concorrenza: non bloccare l'event loop.** L'attuale `upload_pdf` è `async def` ma chiama il
sync `import_pdf_balance_sheet` direttamente: oggi blocca l'event loop per 3–10 secondi,
tollerabile. Il percorso OCR dura fino a 600 secondi: replicare lo schema congelerebbe
l'intero worker Uvicorn (auth, `/analysis`, tutti gli altri endpoint) per minuti. Regola per
`/import/pdf-ocr`:

- la chiamata MinerU è I/O puro → `await` sul client `httpx.AsyncClient` (non blocca);
- la fase contabile sincrona (`mineru_adapter` + `import_pdf_balance_sheet`) va eseguita in
  `fastapi.concurrency.run_in_threadpool(...)`, MAI chiamata direttamente dal corpo async.

Il client invia `multipart/form-data` a:

```text
POST {MINERU_BASE_URL}/file_parse
```

Campi obiettivo, da bloccare con un test sul contratto OpenAPI della versione 3.2.1:

```text
files=<PDF>
lang_list=latin
backend=pipeline
parse_method=ocr
formula_enable=false
table_enable=true
image_analysis=false
return_md=true
return_content_list=true
return_middle_json=true
return_model_output=false
return_images=false
response_format_zip=false
```

Il nome del campo file è `files`, anche per un singolo documento (confermato
sull'OpenAPI reale 3.2.0). `data` va inviato come **dict** e non come lista di tuple:
`httpx` codifica una lista di tuple come stream sync-only, che un `AsyncClient` rifiuta di
inviare. `image_analysis=false` disattiva la descrizione VLM delle immagini (non serve, più
veloce). I booleani sono inviati come stringhe `"true"`/`"false"` (accettate dal container).

**Forma reale della risposta (verificata, ≠ dalle ipotesi iniziali):** l'envelope è
`{task_id, status, version, results, ...}` dove `results` è un **dict indicizzato per
nome-file** (non una lista); ogni blocco ha `md_content` (Markdown), più `middle_json` e
`content_list` che sono **stringhe JSON codificate** (serve un secondo `json.loads`).
`content_list` è la lista di blocchi tipizzati (`text`/`header`/`footer`/`page_number`/
`table`), le tabelle in `table_body` come HTML. L'adapter è costruito su questa forma.

MinerU 3.x produce Markdown, `content_list.json`, `content_list_v2.json` e risultati intermedi la cui forma può evolvere. Prima dell'implementazione del parser della risposta bisogna:

1. avviare il container bloccato;
2. salvare `/openapi.json` come fixture contrattuale di test;
3. inviare un PDF minimo noto;
4. conservare una risposta JSON o ZIP anonimizzata come fixture;
5. implementare la normalizzazione solo sulle forme realmente osservate.

Il client può accettare sia risposta JSON sia ZIP quando dichiarate dal `Content-Type`, ma deve rifiutare contenuti inattesi, archivi con path traversal, output oltre il limite o JSON senza risultati associabili al file richiesto.

### 5.2 Timeout, retry e sicurezza

- Connect timeout breve e timeout totale configurabile fino a 600 secondi.
- Nessun retry automatico indiscriminato su `POST /file_parse`, per evitare elaborazioni duplicate.
- Un solo retry è ammesso esclusivamente per errore di connessione avvenuto prima dell'invio del body e deve essere coperto da test.
- Il nome file inviato deve essere sanitizzato.
- Vietato loggare PDF, Markdown, JSON, tabelle, righe contabili o risposta completa.
- Nei log sono ammessi hash, byte, durata, codice HTTP, versione, numero pagine/blocchi e tipo di errore.
- La risposta MinerU non è considerata attendibile: applicare limiti di dimensione, validazione strutturale e parsing difensivo.

## 6. Adattatore MinerU → pipeline contabile

Nuovo file:

```text
importers/mineru_adapter.py
```

### 6.1 Modello normalizzato

L'adattatore produrrà un oggetto documentale, non un secondo bilancio:

```python
@dataclass(frozen=True)
class MinerUCell:
    text: str
    row: int
    column: int
    page: int
    bbox: tuple[int, int, int, int] | None

@dataclass(frozen=True)
class MinerURow:
    cells: tuple[MinerUCell, ...]
    page: int
    source_block_id: str

@dataclass(frozen=True)
class MinerUExtractionContext:
    full_text: str
    page_texts: tuple[str, ...]
    rows: tuple[MinerURow, ...]
    tables: tuple[object, ...]
    headings: tuple[str, ...]
    current_year: int | None
    comparative_year: int | None
    supported_labels: frozenset[str]
    raw_format: str
    mineru_version: str
```

Le strutture concrete possono essere raffinate dopo la fixture MinerU reale, mantenendo questi requisiti:

- ordine di pagina e lettura conservato;
- coordinate conservate quando disponibili;
- distinzione fra testo, intestazione, tabella e celle;
- provenienza di ogni riga ricostruibile;
- nessun importo contabile convertito senza testo sorgente associato.

### 6.2 Numeri italiani e colonne

Il normalizzatore deve coprire almeno:

- `1.234,56`;
- `-1.234,56`;
- `(1.234,56)`;
- `1.234,56-` se presente nei gestionali;
- spazi e separatori OCR spurii;
- trattino come zero/assenza soltanto quando il layout lo dimostra;
- colonne anno corrente/precedente;
- colonne Dare/Avere;
- valori spezzati su più blocchi;
- righe gerarchiche senza valore.

La conversione produce `Decimal` e una confidenza/evidenza; un token ambiguo resta irrisolto invece di essere corretto automaticamente.

### 6.3 Livello di dettaglio IV CEE

MinerU deve alimentare le relazioni già definite in `importers/iv_cee_hierarchy.py`, fra cui:

- immobilizzazioni immateriali e materiali;
- rimanenze;
- crediti per categoria e scadenza;
- riserve;
- fondi rischi;
- debiti per categoria ed entro/oltre 12 mesi;
- costo del personale;
- ammortamenti immateriali, materiali, svalutazioni e svalutazione crediti.

Regole:

1. la voce legale specifica prevale sul sottoconto generico;
2. i sottoconti vengono aggregati nel nodo IV CEE pertinente;
3. totale e dettagli presenti devono riconciliarsi;
4. un aggregato senza dettagli rimane aggregato;
5. il dettaglio non dimostrato non viene inventato;
6. un residuo positivo può andare nell'attuale campo `altri` soltanto secondo le regole già esistenti e deve essere distinto dai campi letti direttamente;
7. `source_detail_fields` conta i campi sostenuti dalla fonte, inclusi eventuali zeri espliciti, non semplicemente i campi non nulli.

## 7. Collegamento alla pipeline PDF esistente

Modifica proposta:

```python
def import_pdf_balance_sheet(
    ...,
    extraction_context: MinerUExtractionContext | None = None,
) -> dict[str, Any]:
```

Con `extraction_context=None` il comportamento deve essere identico a oggi.

Con contesto MinerU:

1. `sample_text` viene ricavato da `extraction_context.full_text`;
2. non viene eseguito un secondo OCR vision per il routing;
3. `classify_bilancio(file_path=..., text=sample_text)` continua a decidere A/B/C;
4. MinerU fornisce un candidato strutturato;
5. i parser attuali sul PDF originale restano un controllo indipendente;
6. il testo MinerU può alimentare gli estrattori LLM esistenti;
7. la scelta finale usa quadratura, completezza, controlli dichiarati e provenienza;
8. la persistenza rimane nella pipeline comune dopo tutti i gate.

### 7.1 Documenti A/B — IV CEE

Ordine:

1. mapping deterministico delle tabelle e gerarchie MinerU;
2. parser IV CEE deterministico attuale sul PDF originale;
3. LLM sul testo MinerU soltanto se il deterministico è incompleto o ambiguo;
4. overlay esclusivamente di totali legali dimostrati;
5. riconciliazione aggregato/dettaglio;
6. quadratura finale e gate forecastable.

### 7.2 Documenti C — situazione contabile/CoGe

Ordine:

1. parser deterministico righe/colonne MinerU;
2. parser deterministico attuale basato sul PDF originale;
3. CoGe LLM sul testo MinerU quando necessario;
4. confronto dei candidati senza fusione opportunistica di valori incompatibili.
   **La selezione ESTENDE lo scorer già esistente in `pdf_importer`** (gap dal totale
   dichiarato via `_declared_control_totals`, con `_plug_residual` come tiebreaker sotto
   la soglia del 2%) portandolo da 2 a 3 candidati — NON introduce un criterio di scelta
   nuovo, che divergerebbe da quello del percorso standard;
5. netting fondi ammortamento;
6. tipizzazione debiti;
7. controlli Dare/Avere, risultato dichiarato e quadratura finale.

L'LLM propone fatti estratti, non certifica il bilancio. Tutte le quadrature e le decisioni di persistenza restano deterministiche.

### 7.3 Atomicità

L'attuale importer apre una propria `SessionLocal`, esegue `rollback()` su errore e `commit()` soltanto dopo la costruzione dei record. L'integrazione deve preservare questa proprietà e aggiungere test espliciti:

- errore MinerU prima dell'import: nessun record contabile creato;
- errore adattatore: nessun record contabile creato;
- errore classificatore/parser: rollback completo;
- errore quadratura: rollback completo;
- successo: un solo `FinancialYear` per azienda/anno/periodo secondo le regole attuali.

Non va promessa una transazione unica fra upload tracker e import contabile: il tracker deve sopravvivere proprio per registrare gli errori.

## 8. Nuovo endpoint backend

File principale:

```text
backend/app/api/v1/imports.py
```

Nuova rotta:

```http
POST /api/v1/import/pdf-ocr
Content-Type: multipart/form-data
```

Parametri uguali a `/import/pdf`:

- `file`;
- `company_id`;
- `fiscal_year`;
- `company_name`;
- `create_company`;
- `sector`;
- `period_months`.

### 8.1 Sequenza dell'endpoint

1. Verificare feature flag.
2. Verificare autenticazione.
3. Validare estensione, dimensione massima, contenuto non vuoto e firma `%PDF-`.
4. Validare `company_id` oppure dati per la nuova azienda.
5. Controllare ownership o limite aziende prima di spendere risorse OCR.
6. Registrare l'upload come `pdf_ocr`.
7. Chiamare `await MinerUClient.parse_pdf(...)` (I/O async, non blocca il worker).
8. Normalizzare con `mineru_adapter` **dentro `run_in_threadpool`** (CPU-bound).
9. Rifiutare output senza sufficiente testo/numeri/righe contabili.
10. Chiamare `import_pdf_balance_sheet(..., extraction_context=context)` **dentro
    `run_in_threadpool`** — mai direttamente dal corpo `async def` (vedi §5.1).
11. Marcare l'upload come riuscito o fallito.
12. Restituire risultato contabile e metadati OCR.

La logica comune di validazione upload fra `/import/pdf` e `/import/pdf-ocr` dovrebbe essere estratta in helper privati, evitando due copie destinate a divergere.

### 8.2 Mappatura errori HTTP

| Stato | Significato |
|---:|---|
| 400 | parametri, estensione, firma o dimensione PDF non validi |
| 401/404 | contratto auth/ownership già esistente |
| 422 | OCR vuoto/corrotto, documento non contabile, classificazione impossibile o quadrature fallite |
| 503 | MinerU disabilitato, non raggiungibile, unhealthy o saturo |
| 504 | MinerU oltre il timeout applicativo |
| 500 | errore interno non classificato, senza esposizione di contenuti o stack trace |

Le risposte devono avere codici macchina stabili, ad esempio:

```json
{
  "detail": {
    "success": false,
    "error_code": "MINERU_TIMEOUT",
    "message": "Il servizio OCR non ha completato l'estrazione entro il tempo previsto."
  }
}
```

## 9. Risposta e metadati

Estendere il risultato PDF con campi opzionali:

```json
{
  "ocr_engine": "mineru",
  "ocr_version": "3.2.1",
  "extraction_method": "mineru+ivcee_deterministic",
  "source_detail_fields": 31,
  "detail_level": "detailed",
  "ocr_pages": 9,
  "ocr_tables": 4
}
```

Valori ammessi per `detail_level`:

- `aggregate`;
- `partial_detail`;
- `detailed`.

I metadati persistenti entrano nel JSON `FinancialYear.validation_report` e in un `parser_version` compatto compatibile con la colonna esistente, per esempio `pdf-mineru-3.2.1`. Non è prevista una migrazione del database.

`extraction_method` deve descrivere il percorso realmente usato, non quello richiesto. Esempi:

- `mineru+ivcee_deterministic`;
- `mineru+ivcee_llm`;
- `mineru+coge_deterministic`;
- `mineru+coge_llm`.

## 10. Frontend infrannuale

### 10.1 Client API

In `frontend/lib/api.ts`:

- estendere `PDFImportResult` con i metadati OCR opzionali;
- aggiungere `importOCR(...)` con la stessa firma di `importPDF(...)`;
- chiamare `/import/pdf-ocr`;
- impostare timeout a 1.260.000 ms (livello più esterno della catena, vedi §4.3);
- mantenere `ocr_available` come preflight diagnostico, senza nascondere l'azione OCR;
- non effettuare fallback automatici.

### 10.2 Pagina infrannuale

In `frontend/app/infrannuale/page.tsx`:

- estendere `importType` a `"pdf" | "pdf_ocr" | "xbrl"`;
- aggiungere l'opzione **PDF OCR (MinerU)**;
- accettare `.pdf` per `pdf` e `pdf_ocr`;
- nel solo ramo `pdf_ocr` chiamare `importOCR(...)`;
- mantenere XBRL invariato;
- mantenere `handleImportRefYear()` su `importPDF(...)`;
- mostrare stato, metadati e warning OCR;
- distinguere i messaggi per 422, 503 e 504;
- disabilitare il doppio invio durante l'elaborazione.

Comportamento del pulsante:

| Tipo | Etichetta |
|---|---|
| PDF standard | Importa standard e Continua |
| PDF OCR (MinerU) | ImportOCR (MinerU) e Continua |
| XBRL | Importa e continua |

### 10.3 Proxy

In `nginx/default.conf` portare `proxy_send_timeout` e `proxy_read_timeout` da 300 a
**1200 secondi**, lasciando tempo sia all'OCR (massimo 600 s) sia alla successiva pipeline
contabile. Il browser resta il livello esterno a 1.260.000 ms. Catena completa in §4.3.

## 11. File previsti

### Nuovi

- `docs/piano-import-2026-07/14-PIANO-INTEGRAZIONE-MINERU-OCR.md`;
- `backend/app/services/mineru_client.py`;
- `importers/mineru_adapter.py`;
- `docker/mineru/Dockerfile`;
- fixture MinerU anonimizzate sotto `tests/fixtures/mineru/`;
- `tests/test_mineru_client.py`;
- `tests/test_mineru_adapter.py`;
- `tests/test_pdf_ocr_endpoint.py`;
- eventuale test di integrazione Docker separato e marcato.

### Da modificare

- `docker-compose.yml`;
- configurazione/env backend;
- `backend/app/api/v1/imports.py`;
- eventuale schema di risposta PDF in `backend/app/schemas/imports.py`;
- `importers/pdf_importer.py`;
- parser esistenti solo nei punti necessari ad accettare le evidenze MinerU;
- `frontend/lib/api.ts`;
- `frontend/app/infrannuale/page.tsx`;
- `nginx/default.conf`;
- esempi di configurazione e documentazione operativa.

## 12. Strategia di test

### 12.1 Test contrattuali MinerU

- `/health` risponde e contiene i campi minimi attesi;
- `/openapi.json` espone `/file_parse` e il campo multipart `files`;
- fixture PDF minima produce la forma di risposta prevista;
- versione/container diversi da quella bloccata falliscono prima del rollout oppure producono un warning bloccante controllato;
- JSON e ZIP, se entrambi abilitati, sono normalizzati in modo equivalente.

### 12.2 Test unitari client

- risposta valida;
- connessione rifiutata;
- health negativo;
- timeout;
- HTTP 4xx/5xx MinerU;
- risposta vuota;
- content type inatteso;
- JSON corrotto;
- archivio non sicuro o troppo grande;
- nessun contenuto sensibile nei log.

Usare `httpx.MockTransport` o equivalente: i test unitari non richiedono Docker.

### 12.3 Test unitari adattatore

- numeri italiani e negativi;
- colonne comparative;
- Dare/Avere;
- ordine righe e pagine;
- celle spezzate;
- gerarchie IV CEE;
- debiti breve/lungo;
- costo personale;
- `ce09a`–`ce09d`;
- aggregato senza dettaglio;
- dettaglio incompatibile con totale;
- maggiore dettaglio sorgente → maggiore `source_detail_fields`;
- nessuna suddivisione inventata.

### 12.4 Test endpoint

- autenticazione obbligatoria;
- ownership azienda;
- limite aziende;
- validazione `%PDF-`;
- `period_months` 1–12;
- tracking `pdf_ocr`;
- 503, 504 e 422;
- nessun `FinancialYear` su fallimento;
- import riuscito su azienda nuova ed esistente;
- import fino al dato necessario per creare lo scenario infrannuale.

### 12.5 Regressione pipeline

- `/import/pdf` invariato;
- `/import/xbrl` invariato;
- import storico invariato;
- route A/B/C;
- Attivo = Passivo;
- utile CE = `sp13`;
- aggregati = somma dettagli dove richiesto;
- nessun plug mascherato;
- anno parziale e anno storico coesistenti;
- suite test completa;
- build frontend;
- `docker compose config`;
- health check MinerU;
- prova reale su almeno un PDF scansionato del corpus.

### 12.6 Test discriminante di dettaglio

Preparare due PDF con gli stessi aggregati:

- uno sintetico, con soli totali;
- uno dettagliato, con sotto-voci IV CEE dimostrabili.

Criterio di accettazione:

- aggregati finali identici;
- entrambi quadrati;
- nessun dettaglio inventato nel sintetico;
- più campi sorgente nel dettagliato;
- `detail_level` superiore nel dettagliato;
- provenienza verificabile per ogni campo aggiuntivo.

## 13. Sequenza di implementazione

### Fase 0 — Preflight

1. Attendere che cessino modifiche concorrenti sugli stessi file.
2. Fotografare `git status` e i diff sovrapposti.
3. Eseguire suite backend e build frontend come baseline.
4. Provare MinerU 3.2.1 sul server destinazione con PDF del corpus.
5. Salvare OpenAPI e risposta anonimizzata della versione bloccata.

### Fase 1 — Infrastruttura

1. Aggiungere immagine MinerU bloccata.
2. Aggiungere servizio Compose, volumi e health check.
3. Predisporre modelli e modalità offline/local.
4. Verificare CPU; documentare separatamente l'eventuale profilo GPU.
5. Lasciare feature flag disabilitato.

### Fase 2 — Client e adattatore isolati

1. Implementare eccezioni e client MinerU.
2. Scrivere test prima del collegamento all'importer.
3. Implementare normalizzatore della risposta reale.
4. Implementare righe, tabelle, numeri e provenienza.
5. Rendere verdi fixture sintetiche e reali anonimizzate.

### Fase 3 — Pipeline contabile

1. Aggiungere `extraction_context` opzionale.
2. Collegare classificatore A/B/C al testo MinerU.
3. Aggiungere candidato deterministico MinerU.
4. Collegare LLM al testo MinerU nei casi previsti.
5. Riutilizzare riconciliazioni e quadrature esistenti.
6. Verificare rollback e assenza di regressioni sul percorso standard.

### Fase 4 — Endpoint

1. Estrarre validazioni PDF condivise.
2. Implementare `/import/pdf-ocr`.
3. Mappare errori e tracking.
4. Aggiungere metadati di risposta/persistenza.
5. Rendere verdi test API e atomicità.

### Fase 5 — Frontend e proxy

1. Aggiungere `importOCR(...)`.
2. Aggiungere opzione e stati UI.
3. Lasciare XBRL e storico sui percorsi attuali.
4. Aggiornare timeout nginx.
5. Eseguire build frontend e test manuale del wizard.

### Fase 6 — Canary e abilitazione

1. Confrontare import standard e MinerU sul corpus.
2. Classificare differenze per aggregati, dettagli, segni e scadenze.
3. Nessuna differenza viene accettata senza evidenza nel PDF.
4. Abilitare il flag solo per ambiente di test.
5. Eseguire UAT su PDF sintetici, dettagliati e scansionati.
6. Abilitare in produzione con rollback immediato via feature flag.

## 14. Definition of Done

L'intervento è concluso soltanto quando:

- per ogni PDF sono visibili insieme import standard e import OCR MinerU;
- il pulsante usa davvero `/api/v1/import/pdf-ocr`;
- MinerU è raggiungibile soltanto dal backend nella rete Docker;
- MinerU non disponibile produce 503 senza fallback;
- timeout produce 504 controllato;
- output vuoto o bilancio non quadrato produce 422;
- nessun errore lascia record contabili parziali;
- deterministico e LLM usano le evidenze MinerU senza bypassare i gate;
- `FinancialYear.validation_report` conserva metodo, versione e livello di dettaglio;
- PDF standard, XBRL e import storico restano invariati;
- la suite completa e la build frontend sono verdi;
- il test sintetico/dettagliato dimostra aggregati uguali e dettaglio maggiore solo quando presente nella fonte;
- almeno un PDF scansionato reale completa import, rettifiche e creazione dello scenario infrannuale.

## 15. Rollback

Il rollback operativo non richiede cancellazioni o migrazioni:

1. impostare `MINERU_OCR_ENABLED=false` — l'endpoint OCR risponde 503 controllato mentre
   PDF standard e XBRL restano disponibili;
2. lasciare disponibili PDF standard e XBRL;
3. fermare il servizio MinerU se necessario;
4. conservare upload tracker e diagnostica degli import falliti;
5. non eliminare `FinancialYear` già importati e validati correttamente.

## 16. Fonti MinerU verificate

- [MinerU — Quick usage e API (`/health`, `/file_parse`, `/tasks`)](https://opendatalab.github.io/MinerU/usage/quick_usage/)
- [MinerU — Docker deployment](https://opendatalab.github.io/MinerU/quick_start/docker_deployment/)
- [MinerU — Output files](https://opendatalab.github.io/MinerU/reference/output_files/)
- [MinerU — Release 3.2.1](https://github.com/opendatalab/MinerU/releases)

Le fonti sono state verificate il 2026-07-22. Il contratto realmente usato dall'implementazione deve comunque essere congelato mediante `/openapi.json` e fixture del container bloccato.

---

## 17. Stato di implementazione (2026-07-22)

Implementato nel working tree (**non committato**) e ancorato al contratto MinerU
**3.2.0**. Il container locale in esecuzione risponde `healthy`, versione `3.2.0`,
protocollo `1`.

**Fase 0/1 — Preflight e infrastruttura: FATTE.**

- `docker/mineru/Dockerfile` deriva dal Dockerfile ufficiale ma blocca
  `mineru[core]==3.2.0` (l'upstream usava il vincolo aperto `>=3.0.0`).
- `docker-compose.yml` costruisce/tagga `xbrlbudget-mineru:3.2.0`, usa modelli locali,
  rete interna e health check; il backend resta avviabile quando l'OCR è disabilitato.
- Il compose base non richiede NVIDIA. `docker-compose.gpu.yml` aggiunge la reservation
  GPU soltanto quando richiesto esplicitamente.
- `.env.docker` è stato normalizzato rimuovendo tre righe sintatticamente invalide;
  `docker compose config --quiet` passa.
- Catena sincrona: MinerU 600 s, nginx 1200 s, browser 1260 s.

**Fase 2/3 — Client, adapter e pipeline: FATTE.**

- Il client limita la risposta durante lo streaming (non dopo averla caricata tutta),
  conserva l'estensione `.pdf`, non registra contenuti contabili e rifiuta una versione
  diversa da 3.2.0.
- La fixture di risposta è sintetica e anonimizzata: nessun dato anagrafico reale è
  conservato nel repository.
- `MinerUExtractionContext` espone testo, pagine, righe, tabelle e testo line-oriented
  per i parser CoGe esistenti.
- Per A/B, le righe strutturate producono un candidato IV-CEE deterministico. Il candidato
  è usato solo se ricostruisce i due totali stampati, supera Attivo=Passivo e CE↔SP;
  altrimenti prosegue il parser sorgente e poi il fallback LLM.
- Per C, il testo tabellare line-oriented alimenta il parser deterministico esistente;
  il testo MinerU resta anche l'evidenza del CoGe LLM. Non esiste alcun plug OCR.
- Versione, pagine, tabelle, metodo, campi sostenuti dalla fonte e livello di dettaglio
  sono persistiti in `FinancialYear.validation_report` e `parser_version`, oltre che
  restituiti dall'API.

**Fase 4/5 — Endpoint, frontend e proxy: FATTE.**

- `POST /import/pdf-ocr` non effettua fallback silenzioso, esegue ownership/quota prima
  del tracking e marca come fallito ogni errore successivo alla registrazione.
- Errori documento → 422, timeout → 504, indisponibilità o contratto incompatibile → 503.
- `GET /import/capabilities` espone lo stato operativo; entrambe le azioni PDF restano visibili.
- Il wizard infrannuale conserva e mostra motore, versione, metodo e livello di dettaglio.
  PDF standard, XBRL e secondo import storico mantengono i percorsi precedenti.

**Verifiche eseguite.**

- Test di integrazione non mockato: PDF senza text layer → tabelle MinerU sintetiche →
  classificazione → mapper → quadrature → persistenza dell'anno corrente e comparativo.
- Suite backend: **277 passati, 3 saltati**.
- Build frontend Next.js: riuscita.
- Compose: configurazione valida; servizio live MinerU 3.2.0 healthy.

### Aperto prima dell'abilitazione produzione

- Eseguire il canary sul corpus reale autorizzato e una UAT completa nel wizard; le fixture
  versionate restano sintetiche per evitare PII.
- Costruire l'immagine Docker pinned nel registry/host di destinazione: il Dockerfile è
  pronto, ma la build completa (base vLLM + modelli) non è stata lanciata in questa verifica.
- La prima versione resta sincrona. Se i documenti reali richiedono regolarmente oltre
  20 minuti, migrare l'endpoint a `/tasks` con polling invece di aumentare ancora i timeout.
- La pagina annuale `/import` non è stata modificata: perimetro corrente = import iniziale
  della pagina infrannuale.
