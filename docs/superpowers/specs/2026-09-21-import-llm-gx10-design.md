# Import PDF su gx10 (Qwen 3.8 Flash-Next), con ripiego su Haiku — design

Data: 2026-09-21. Approvato dal proprietario in chat lo stesso giorno.

## Obiettivo

L'estrazione LLM dell'import PDF gira sul server dell'ufficio `gx10` (vLLM, `qwen3.8-flash-next`,
lo stesso modello dell'agente pi) invece che su Claude Haiku, per tutte le richieste degli utenti.
Haiku resta come **ripiego automatico e dichiarato** quando gx10 non risponde. Si accende per rotta,
e solo dove un confronto sul corpus mostra che Qwen non perde contro Haiku.

Ordine: prova su un bilancio → confronto sul corpus → staging → produzione.

## Stato di partenza (misurato sul codice e su gx10, 2026-09-21)

- Il modello è fisso in `config.py:213` (`PDF_LLM_MODEL = "claude-haiku-4-5-20251001"`); i client
  `anthropic.Anthropic(...)` nascono in 6 moduli (`pdf_extractor_llm`, `macro_analysis`,
  `detail_enrichment`, `ledger_evidence`, `vision_rescue`, `standard_ivcee_parser`), con parametri
  diversi (`timeout`, `max_retries`, `api_key` esplicita o dall'ambiente).
- Tutte le chiamate usano **tool imposto** (`tool_choice={"type": "tool", ...}`); due percorsi
  mandano immagini (vision di pagina, riscatto vision).
- Più punti spengono una rotta se manca `ANTHROPIC_API_KEY` (`macro_analysis.py:121`,
  `ledger_evidence.py:411`, `detail_enrichment.py:824`, `pdf_importer.py:751` e seguenti).
- gx10 espone **`/v1/messages`** (compatibile Anthropic) oltre a `/v1/chat/completions`: l'SDK
  `anthropic` ci parla con `base_url` + `auth_token` (Bearer). Provato: tool imposto → `tool_use`
  corretto in ~4 s; un PNG letto correttamente. Differenze osservate: `stop_reason` vale `end_turn`
  anche con tool imposto, e davanti al `tool_use` arriva un blocco `thinking`.
- Il reasoning del chat template va passato in `extra_body.chat_template_kwargs.reasoning_effort`
  (`low`/`medium`/`xhigh`; `high` → 400); senza, vale `xhigh`. Il `reasoning_effort` top-level è
  ignorato.

## Rete e sicurezza (già in opera, 2026-09-21)

- **Locale**: `http://192.168.1.137:18300` (LAN) o `http://100.65.63.12:18300` (Tailscale), Bearer.
- **VPS**: `https://kpsfinanciallab.w3pro.it:18443` (risolve a 31.188.16.192, router dell'ufficio →
  nginx su gx10 con TLS, allow-list IP, solo `/v1/`). Oggi la allow-list e il firewall `llm-fw`
  ammettono **solo lo staging** 194.163.175.249; la produzione (5.189.178.190) va aggiunta prima di
  accendere gx10 lì. 18300 non si inoltra mai dal router.
- Ogni chiamata porta `Authorization: Bearer`; la chiave non va mai in argv né nei log.

## Design

### 1. Un solo punto che crea il client — `importers/llm_client.py`

Configurazione da ambiente (propagata da `backend/app/core/config.py` come oggi `ANTHROPIC_API_KEY`):

| Variabile | Default | Significato |
|---|---|---|
| `LLM_PRIMARY` | `anthropic` | `gx10` o `anthropic`. Default = nessun cambiamento finché non si decide |
| `LLM_PRIMARY_ROUTES` | vuoto = tutte | elenco delle chiamate su cui vale `LLM_PRIMARY`; le altre vanno su Haiku |
| `GX10_BASE_URL` | — | base senza `/v1` |
| `GX10_API_KEY` | — | Bearer |
| `GX10_MODEL` | `qwen3.8-flash-next` | |
| `GX10_THINKING` | `off` | `off` → `chat_template_kwargs.enable_thinking=false`; `low`/`medium`/`xhigh` → `reasoning_effort` (vedi §3) |
| `LLM_FALLBACK` | `on` | `off` solo per il banco di confronto |

Ogni punto di chiamata ha un **nome di rotta stabile** (`ab_sections`, `ab_vision`, `vision_rescue`,
`coge`, `macro`, `detail`, `ledger`, `standard_ivcee`, …: l'elenco esatto lo fissa il piano leggendo
il codice). Il modulo espone una funzione che prende nome di rotta + argomenti di `messages.create`
e restituisce la risposta, sostituendo `model` con quello del provider scelto e aggiungendo
`extra_body` solo per gx10. I sei moduli smettono di costruire client e di leggere
`PDF_LLM_MODEL`; i propri `timeout`/`max_retries` diventano argomenti della chiamata, non del
client. I controlli «manca `ANTHROPIC_API_KEY` ⇒ rotta spenta» diventano «nessun provider
disponibile per questa rotta».

`max_tokens`: su gx10 il reasoning consuma lo stesso budget; con il thinking spento (default) il
problema sparisce (§3). I valori restano quelli di Haiku.

`temperature`: le chiamate di oggi non la impostano (Haiku usa il suo default). Su gx10 vale il
default di vLLM. Il ciclo «completeness retry» della rotta C (`_COGE_SP_MAX_ATTEMPTS`) ha senso solo
se due estrazioni possono differire: con `temperature=0` le tre ripetizioni sono identiche e costano
~35 s l'una. Il piano decide se gx10 gira a temperatura di default o se il ciclo si ferma alla prima
estrazione identica alla precedente.

### 2. Ripiego e tracciabilità

Si rifà la **stessa** chiamata su Haiku quando gx10:
- non si connette, va in timeout, risponde 5xx, 401 o 403 (401/403 si registrano come errore di
  configurazione, non come guasto passeggero);
- risponde senza il `tool_use` richiesto, o con un input che non valida contro lo schema del tool.

**Non** si ripiega su numeri che non quadrano: è compito della pipeline (misura e dichiara), e
mescolare i provider in base all'esito nasconderebbe proprio la differenza da misurare.

Ogni import raccoglie, per chiamata, `{rotta, provider, modello, ripiego: motivo|null, secondi}` e lo
dichiara nella diagnostica dell'estrazione (chiave sempre presente, anche vuota — regola degli
estrattori) e nel record `UploadedFile`. Senza ripieghi il costo Anthropic è zero.

Se Haiku non è configurato (nessuna chiave) e gx10 fallisce, l'errore è quello di oggi per
«LLM non disponibile».

### 3. Prova su un bilancio (prima di tutto il resto)

Un PDF di rotta A/B e uno di rotta C dal corpus `Test/`, eseguiti con `tests/_import_probe.py`
(DB in memoria) con tutte le chiamate su gx10 e ripiego spento. Si guardano gli errori (troncamenti,
tool mancante, schema, tempi) e si correggono prima del confronto. Se la prova rivela un problema
strutturale, questa spec si aggiorna.

**Esito su `budget_624` (rotta C, contrapposte 8 cifre), 2026-09-21**, harness usa-e-getta che
dirotta ogni client su gx10, `temperature=0`:

| thinking | CoGe SP | vision | dettagli | totale import |
|---|---|---|---|---|
| `medium` | 8192/8192 token di solo thinking → nessun `tool_use`, rotta ripiega sul vision | 95 s | 131 s | 419 s |
| `low` | idem, 210 s | 52 s | **16384/16384 di thinking**, nessun `tool_use` | 657 s |
| **spento** | 3 × 35 s, `tool_use` ok | 21 s | 14 s | **155 s** |

- `reasoning_effort` arriva al template anche via `/v1/messages` (verificato: output diversi fra
  `low` e `xhigh`, identici fra `/v1/messages` e `/v1/chat/completions`). Il `low` non accorcia:
  il ragionamento si allunga fino a esaurire il budget. **Default: thinking spento.**
- Gli stessi numeri finali in tutte e tre le varianti (attivo 1.972.377,52, utile 8.906,79).
- Contro la baseline Haiku (mai verificata) 13 campi su 46 diversi, e sul PDF ha ragione Qwen:
  rimanenze merci 1.468.999,24 in `sp05` (Haiku le omette dall'attivo), variazione rimanenze a CE
  invece di rimanenze finali dentro `ce04` (il `ce04` di Haiku è esattamente altri ricavi +
  rimanenze finali + proventi finanziari), perdite portate a nuovo negative come stampate.
- Il timeout del proxy di staging per l'import PDF è 300 s: 155 s ci stanno, 419 s no. I tempi per
  rotta entrano fra le metriche del confronto.

### 4. Banco di confronto — `scripts/confronto_llm.py`

- Corpus: gli 87 PDF comparati di `Test/` (gitignorato, bilanci di clienti: mai committati).
- 2 esecuzioni con gx10 e 2 con Haiku per file, `LLM_FALLBACK=off`; `tests/_import_probe.py` su DB
  in memoria.
- **Il corpus non ha valori verificati**: le metriche sono segnali oggettivi — import riuscito o
  rifiutato, verdetto `reliability`, sbilancio, divari contro i totali stampati
  (`_declared_assets_difference`, `_plug_residual`, `_unclassified_mass`, `_ce_sp_difference`),
  tempo; più la concordanza campo per campo fra i due provider e fra le due esecuzioni dello stesso.
- I disaccordi si estraggono per un controllo a occhio sul PDF.
- Rapporto per rotta in `docs/superpowers/`, con la raccomandazione su `LLM_PRIMARY_ROUTES`. Gli
  output grezzi restano fuori dal repo (contengono dati di clienti).
- Le esecuzioni Haiku mandano i PDF ad Anthropic, come il prodotto: autorizzato dal proprietario
  con l'approvazione del confronto.

### 5. Attivazione

- Staging: il `Jenkinsfile` aggiunge a `.env.docker` le variabili del §1 e la credenziale
  `budget-gx10-api-key`; `LLM_PRIMARY_ROUTES` dal rapporto. Prima, dal VPS:
  `curl https://kpsfinanciallab.w3pro.it:18443/v1/models` → 401 senza chiave, 200 con.
- Produzione: IP 5.189.178.190 in `allow.conf` e `llm-fw` su gx10, poi le stesse variabili.

## Test

- Unitari su `llm_client`: scelta del provider per rotta, `extra_body` solo per gx10, ripiego per
  ciascun motivo, nessun ripiego su risposta valida, diagnostica sempre presente, chiave mai nei
  log. Con un finto server, senza rete.
- La suite di import esistente deve restare verde con `LLM_PRIMARY=anthropic` (nessun cambiamento
  di comportamento).

## Fuori perimetro

- I commenti AI (`ai_comments_service`, `editorial_notes_service`): restano su Anthropic.
- Il percorso `pdf-ocr` (MinerU).
- Qualunque modifica al prompt per adattarlo a Qwen, salvo quanto la prova su un bilancio renda
  indispensabile — va dichiarato nel rapporto, perché cambia anche Haiku.

## Lavoro

Codice su un branch dedicato (`feat/import-llm-gx10`); questa spec su `main`.
