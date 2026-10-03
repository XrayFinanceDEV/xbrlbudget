# Import PDF snello — piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** un PDF di bilancio arriva nei campi `sp`/`ce` del budget in poche chiamate (Sonnet per la struttura, Qwen/gx10 per la lettura), con un errore piccolo e dichiarato; l'importatore di oggi resta come ripiego.

**Architecture:** pacchetto nuovo `importers/import_snello/` dietro l'interruttore `IMPORT_MOTORE=snello`. F1 struttura (mappa del branch mappa, Sonnet vision) → F2 macroconti (il modello nomina il **percorso di legge** di ogni voce: su uno schema di legge restituisce coppie `[percorso, importo]`, su un elenco di conti `id → percorso` e somma il codice) → F3 verifica con soglia relativa e tappo dichiarato → consegna a `pdf_importer` nel punto di convergenza, da cui dettagli, residui, validazione e salvataggio girano invariati.

**Tech Stack:** Python 3, PyMuPDF (`fitz`), httpx (vLLM OpenAI-compatibile su gx10), Anthropic SDK (Sonnet per la struttura), pytest.

**Spec:** `docs/superpowers/specs/2026-09-26-import-pdf-snello-design.md` (questo branch). Riusa i Task 1-2 del piano `docs/superpowers/plans/2026-09-23-import-struttura-vision.md` (stesso branch).

## Global Constraints

- Branch `feat/import-struttura`, worktree `/home/peter/DEV/budget-struttura`. Nessuna operazione git in `/home/peter/DEV/budget`.
- Interruttore: `IMPORT_MOTORE=snello` accende il percorso; assente o qualunque altro valore → comportamento identico a `main`.
- gx10 si chiama sempre con `Authorization: Bearer <GX10_API_KEY>`; la chiave viene SOLO da env, mai in argv, log, eccezioni, report.
- gx10: al massimo `GX10_CONCORRENZA` (default **4**) richieste in volo per processo; ogni richiesta stima prompt + `max_tokens` ≤ `GX10_CONTESTO_MAX` (default **100000**) token, altrimenti si divide prima di inviarla. `temperature: 0`, `chat_template_kwargs: {"enable_thinking": False}`.
- `max_tokens` sempre proporzionato alla risposta attesa, mai un tetto fisso da 12.000-16.000.
- Il modello non sceglie mai da un `enum` di codici campo: nomina un percorso di legge (sintassi del Task 3).
- Soglia di verifica = `max(IMPORT_SNELLO_SOGLIA_MIN, totale_attivo × IMPORT_SNELLO_SOGLIA_PCT / 100)`, default `100` € e `0.1` %. Tappo entro soglia solo su `sp06g_crediti_altri_breve`, `sp16g_altri_debiti_breve`, `ce06_servizi`, sempre dichiarato.
- I campi `TIER0_FIELDS` (`importers/situazione_contabile_parser.py`: `sp02`, `sp03`, `sp04`, `sp11`, `sp12`, `sp13`, `sp16a`, `sp17a`, `ce09`) non sono mai destinazione di un tappo o di un ripiego.
- Le chiavi di `bs`/`ce` restituite sono i nomi COMPLETI delle colonne ORM (`sp06a_crediti_clienti_breve`), valori `Decimal` al centesimo, aggregati valorizzati.
- Qualunque eccezione del percorso snello → l'import prosegue con il codice di oggi, e `validation_report["import_snello"]["esito"] = "ripiego"` con la ragione.
- EOL: `config.py` e `importers/pdf_extractor_llm.py` sono CRLF (preservare); gli altri file toccati sono LF. `git diff --stat` prima di ogni commit.
- `git add` per nome file, mai `-A` o `.`. Nessun push.
- Corpus `Test/`, `inbox/`, dati clienti mai committati; le fixture sono PDF sintetici generati con `fitz` o oggetti costruiti a mano. DB reale mai toccato.
- Nessuna chiamata di rete nei test: ogni funzione che chiama un modello accetta la funzione di chiamata come parametro (`chiama=`), e i test ne passano una finta.
- Python: `cd /home/peter/DEV/budget-struttura && /home/peter/DEV/budget/backend/venv/bin/python -m pytest ...`. Regressione: `... -m pytest tests/ -q -p no:cacheprovider -k "pdf or import or vision or trial or coge or ivcee or detail or ledger or macro or struttura or snello or llm_provider"`. Fallimento preesistente accettato: `tests/test_vision_rescue.py::test_build_ce_non_manda_un_ricavo_sconosciuto_su_una_voce_di_costo`.
- Agenti pi: al massimo **2** attivi insieme (condividono gx10 con il banco: 500k di contesto totali). Il banco (Task 12) gira solo quando nessun agente pi è attivo.

## Review Focus

1. **Un totale contato come foglia** (mastro senza figli letti, riga «Totale crediti» in uno schema di legge): il foglio pareggia o sbaglia di un importo intero; `marca_totali` (Task 4) e la regola «il genitore cade se c'è un discendente» (Task 5) lo prevengono — test in entrambi i task.
2. **Il risultato dell'anno prima scambiato per quello corrente** in un bilancio di verifica: `misura` (Task 7) sceglie la forma che torna e sposta il risultato del netto in `sp12g`; test nel Task 7.
3. **Un conto stampato dal lato sbagliato** (c/c bancario fra le passività, erario in dare): `applica_lato` (Task 5) lo porta alla voce dell'altro lato; test nel Task 5.
4. **Il tappo supera la soglia o finisce su un campo TIER0**: `tappa` (Task 7) rifiuta; test nel Task 7.
5. **Qwen salta righe o risponde troncato**: una seconda chiamata solo sulle righe mancanti; righe ancora senza percorso dichiarate, mai contate; test nel Task 6.

---

### Task 1: `llm_provider` — semaforo, tetto di contesto, testo libero e immagini

**Files:**
- Modify: `importers/llm_provider.py`
- Test: `tests/test_llm_provider.py`

**Interfaces:**
- Produces:
  - `class ContestoEccessivo(LLMProviderError)`
  - `stima_token(messaggi: list[dict], system_prompt: str = "") -> int` — caratteri/3 del testo, più 1.500 per ogni immagine.
  - `chiama_gx10_json(...)` (esistente): ora passa dal semaforo e rifiuta con `ContestoEccessivo` se `stima_token + max_tokens > GX10_CONTESTO_MAX`; `messaggi[i]["content"]` può essere una stringa o una lista OpenAI (`[{"type": "text", ...}, {"type": "image_url", ...}]`).
  - `chiama_gx10_testo(system_prompt: str, messaggi: list[dict], *, max_tokens: int, timeout: float = 600.0, transport=None) -> str` — come `chiama_gx10_json` ma senza `structured_outputs`, restituisce il testo.
  - `GX10_CONCORRENZA: int`, `GX10_CONTESTO_MAX: int` letti da env all'import del modulo (default 4 e 100000).

- [ ] **Step 1: test che falliscono** — aggiungere a `tests/test_llm_provider.py`:

```python
import threading
import time


def _ok(testo='{"a": 1}'):
    return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": testo}}],
                                     "usage": {"prompt_tokens": 1, "completion_tokens": 1}})


def test_chiama_gx10_testo_restituisce_il_testo_senza_schema(monkeypatch):
    monkeypatch.setenv("GX10_API_KEY", "k-segreta")
    visto = {}
    def handler(request):
        visto["body"] = json.loads(request.content)
        return _ok("1 SPA.B.II.2\n2 X")
    out = llm_provider.chiama_gx10_testo("sys", [{"role": "user", "content": "u"}], max_tokens=50,
                                         transport=httpx.MockTransport(handler))
    assert out == "1 SPA.B.II.2\n2 X"
    assert "structured_outputs" not in visto["body"]
    assert visto["body"]["max_tokens"] == 50


def test_contesto_eccessivo_rifiutato_prima_di_inviare(monkeypatch):
    monkeypatch.setenv("GX10_API_KEY", "k-segreta")
    monkeypatch.setattr(llm_provider, "GX10_CONTESTO_MAX", 1000)
    def handler(request):
        raise AssertionError("non doveva inviare")
    with pytest.raises(llm_provider.ContestoEccessivo):
        llm_provider.chiama_gx10_testo("s", [{"role": "user", "content": "x" * 3000}], max_tokens=10,
                                       transport=httpx.MockTransport(handler))


def test_stima_token_conta_le_immagini():
    msg = [{"role": "user", "content": [{"type": "text", "text": "abc" * 100},
                                         {"type": "image_url", "image_url": {"url": "data:image/png;base64,AA"}}]}]
    assert llm_provider.stima_token(msg) == 100 + 1500


def test_semaforo_limita_le_richieste_in_volo(monkeypatch):
    monkeypatch.setenv("GX10_API_KEY", "k-segreta")
    monkeypatch.setattr(llm_provider, "_SEMAFORO", threading.BoundedSemaphore(2))
    in_volo, massimo, lock = [0], [0], threading.Lock()
    def handler(request):
        with lock:
            in_volo[0] += 1; massimo[0] = max(massimo[0], in_volo[0])
        time.sleep(0.05)
        with lock:
            in_volo[0] -= 1
        return _ok("ok")
    t = httpx.MockTransport(handler)
    th = [threading.Thread(target=llm_provider.chiama_gx10_testo,
                           args=("s", [{"role": "user", "content": "u"}]), kwargs={"max_tokens": 5, "transport": t})
          for _ in range(6)]
    [x.start() for x in th]; [x.join() for x in th]
    assert massimo[0] == 2
```

- [ ] **Step 2:** `pytest tests/test_llm_provider.py -q` → i quattro nuovi falliscono.
- [ ] **Step 3: implementazione** in `importers/llm_provider.py`:
  - in testa, dopo gli import: `import threading`;
  - costanti e semaforo:

```python
GX10_CONCORRENZA = int(os.environ.get("GX10_CONCORRENZA", "4"))
GX10_CONTESTO_MAX = int(os.environ.get("GX10_CONTESTO_MAX", "100000"))
# gx10 ha 500k token di contesto condivisi: 4 richieste sotto 100k non rallentano il prefill.
_SEMAFORO = threading.BoundedSemaphore(GX10_CONCORRENZA)


class ContestoEccessivo(LLMProviderError):
    pass


def stima_token(messaggi: list[dict], system_prompt: str = "") -> int:
    caratteri, immagini = len(system_prompt), 0
    for m in messaggi:
        c = m.get("content")
        if isinstance(c, str):
            caratteri += len(c)
        else:
            for parte in c or []:
                if parte.get("type") == "text":
                    caratteri += len(parte.get("text", ""))
                elif parte.get("type") == "image_url":
                    immagini += 1
    return caratteri // 3 + 1500 * immagini
```

  - rifattorizzare `chiama_gx10_json` in un `_invia(system_prompt, messaggi, *, max_tokens, timeout, transport, schema=None) -> str` che: controlla la chiave; se `stima_token(messaggi, system_prompt) + max_tokens > GX10_CONTESTO_MAX` solleva `ContestoEccessivo("richiesta gx10 oltre il tetto di contesto")`; costruisce il corpo come oggi, aggiungendo `structured_outputs` solo se `schema is not None`; esegue il `POST` dentro `with _SEMAFORO:`; gestisce errori, `finish_reason == "length"` → `RispostaTroncata`, e restituisce il testo del messaggio. `chiama_gx10_json` = `json.loads(_invia(..., schema=schema))` con lo stesso `LLMProviderError` di oggi sul JSON non decodificabile; `chiama_gx10_testo` = `_invia(..., schema=None)`. I messaggi d'errore restano quelli di oggi (i test esistenti non cambiano).
- [ ] **Step 4:** `pytest tests/test_llm_provider.py -q` → tutti verdi (nuovi ed esistenti).
- [ ] **Step 5: commit** `feat(import): gx10 con semaforo di concorrenza, tetto di contesto e chiamata a testo libero`

---

### Task 2: struttura del documento (porta i Task 1-2 del piano del 23/09, più colonne e testo)

**Files:**
- Create: `importers/struttura_documento/__init__.py`, `importers/struttura_documento/mappa.py`, `importers/struttura_documento/analisi.py`
- Create: `tests/_struttura_fixtures.py`, `tests/test_struttura_mappa.py`, `tests/test_struttura_analisi.py`
- Modify: `config.py` (CRLF)

**Interfaces:**
- Consumes: il piano `docs/superpowers/plans/2026-09-23-import-struttura-vision.md`, Task 1 e Task 2, eseguiti **alla lettera** (sono completi di codice e test).
- Produces, in aggiunta a quanto quei due task producono (`Struttura`, `analizza_struttura`, `route_da_mappe`, `pagine_tabelle_nota`):
  - campi nuovi di `Struttura`: `modo: str` (`"conti"` | `"legge"`), `colonne_sp: list[str]`, `colonne_ce: list[str]` (ruoli delle colonne, da sinistra, della prima sezione di ciascun prospetto), `intestazioni_sp: list[str]`, `intestazioni_ce: list[str]`, `pagine_senza_testo: list[int]`;
  - `modo_da_mappe(mappe: list[dict]) -> str`.

- [ ] **Step 1:** eseguire il Task 1 del piano del 23/09 (Steps 1-5, commit compreso).
- [ ] **Step 2:** eseguire il Task 2 del piano del 23/09 (Steps 1-5, commit compreso).
- [ ] **Step 3: test che falliscono** in `tests/test_struttura_analisi.py`:

```python
from importers.struttura_documento.analisi import modo_da_mappe


def _p(pagina, tipo, schema, ruoli, intest):
    return {"pagina": pagina, "tipo_pagina": tipo, "schema": schema,
            "sezioni": [{"posizione": "unica", "contenuto": "misto",
                         "colonne": [{"ruolo": r, "intestazione": i} for r, i in zip(ruoli, intest)]}]}


def test_modo_conti_o_legge():
    assert modo_da_mappe([_p(1, "prospetto_sp", "piano_dei_conti_gerarchico", ["saldo_corrente"], ["Saldo"])]) == "conti"
    assert modo_da_mappe([_p(1, "prospetto_sp", "elenco_piatto", ["saldo_corrente"], ["Saldo"])]) == "conti"
    assert modo_da_mappe([_p(1, "prospetto_sp", "iv_cee_di_legge", ["saldo_corrente"], ["2025"])]) == "legge"
    assert modo_da_mappe([_p(1, "prospetto_sp", "riclassificato_con_codici_ivcee", ["saldo_corrente"], ["x"])]) == "legge"


def test_struttura_porta_colonne_e_pagine_senza_testo(tmp_path):
    from importers.struttura_documento.analisi import analizza_struttura
    from tests._struttura_fixtures import pdf_colonna_unica, MAPPA_COLONNA_UNICA
    pdf = pdf_colonna_unica(str(tmp_path / "c.pdf"))
    s = analizza_struttura(pdf, mappa_pagina_fn=lambda client, png: MAPPA_COLONNA_UNICA)
    assert s.modo in ("conti", "legge")
    assert s.colonne_sp and all(isinstance(r, str) for r in s.colonne_sp)
    assert s.pagine_senza_testo == []
```

- [ ] **Step 4:** falliscono.
- [ ] **Step 5: implementazione** in `analisi.py`:

```python
SCHEMI_CONTI_MODO = {"piano_dei_conti_gerarchico", "elenco_piatto"}


def modo_da_mappe(mappe: list[dict]) -> str:
    prospetti = [m for m in mappe if m.get("tipo_pagina") in TIPI_SP | TIPI_CE]
    conti = sum(1 for m in prospetti if m.get("schema") in SCHEMI_CONTI_MODO)
    return "conti" if prospetti and conti * 2 > len(prospetti) else "legge"


def _colonne_di(mappe: list[dict], tipi: set[str]) -> tuple[list[str], list[str]]:
    for m in mappe:
        if m.get("tipo_pagina") in tipi and m.get("sezioni"):
            col = m["sezioni"][0].get("colonne") or []
            return [c.get("ruolo", "altro") for c in col], [c.get("intestazione", "") for c in col]
    return [], []
```

  In `Struttura` aggiungere i campi nuovi con default (`modo: str = "legge"`, `colonne_sp: list[str] = field(default_factory=list)`, ecc.); in `analizza_struttura`, prima del `return`, calcolare `modo = modo_da_mappe(mappe)`, le colonne con `_colonne_di(mappe, TIPI_SP)` / `_colonne_di(mappe, TIPI_CE)`, e `pagine_senza_testo` con `fitz` (pagine il cui `get_text().strip()` è vuoto, numerate da 1); passarli al costruttore; `report()` li include.
- [ ] **Step 6:** `pytest tests/test_struttura_analisi.py tests/test_struttura_mappa.py -q` verde.
- [ ] **Step 7: commit** `feat(import): la struttura dichiara modo, colonne e pagine senza testo`

---

### Task 3: percorsi di legge → campi del budget

**Files:**
- Create: `importers/import_snello/__init__.py` (per ora solo la docstring), `importers/import_snello/legenda.txt`, `importers/import_snello/percorsi.py`
- Test: `tests/test_snello_percorsi.py`

**Interfaces:**
- Produces (in `percorsi.py`):
  - `LEGENDA: str` — il contenuto di `legenda.txt`.
  - `NOMI: dict[str, str]` — codice breve → nome completo ORM (`"sp06a" → "sp06a_crediti_clienti_breve"`).
  - `campo_da_percorso(p: str) -> str | None` — codice breve (`"sp06a"`, `"sp06"` per un aggregato stampato senza dettaglio, `"ce08b"`), `None` per `X`, `R`, `CE.21` o un percorso sconosciuto.
  - `e_fondo(p: str) -> bool` — il percorso finisce con `.F`.
  - `e_risultato(p: str) -> bool` — `CE.21` o `CE.D.21`.
  - `CONTROPARTE: dict[str, str]` — prefisso di percorso → percorso dell'altro lato.
  - `lato_di(p: str) -> str | None` — `"att"`, `"pas"`, `"ce"`.
  - `famiglia(codice: str) -> str` — `"att"`, `"pas"`, `"ric"`, `"cos"` (su codice breve).
  - `completa(importi: dict[str, Decimal]) -> tuple[dict, dict]` — da codici brevi a `(bs, ce)` con nomi completi e aggregati valorizzati come somma di valore diretto + sotto-campi.

- [ ] **Step 1: `legenda.txt`** — creare con esattamente questo contenuto:

```
SPA.A crediti verso soci per versamenti ancora dovuti
SPA.B.I.1 costi di impianto e ampliamento | SPA.B.I.2 costi di sviluppo | SPA.B.I.3 brevetti e utilizzazione opere dell'ingegno | SPA.B.I.4 concessioni, licenze, marchi, software | SPA.B.I.5 avviamento | SPA.B.I.6 immobilizzazioni immateriali in corso e acconti | SPA.B.I.7 altre immobilizzazioni immateriali (spese su beni di terzi, manutenzioni straordinarie pluriennali)
SPA.B.II.1 terreni e fabbricati | SPA.B.II.2 impianti e macchinario | SPA.B.II.3 attrezzature industriali e commerciali | SPA.B.II.4 altri beni (mobili, macchine d'ufficio, elaboratori, automezzi, autovetture) | SPA.B.II.5 immobilizzazioni materiali in corso e acconti
SPA.B.III.1 partecipazioni | SPA.B.III.2 crediti immobilizzati (depositi cauzionali) | SPA.B.III.3 altri titoli | SPA.B.III.4 strumenti finanziari derivati attivi
(fondi ammortamento e svalutazione delle immobilizzazioni: percorso del bene + '.F', es. SPA.B.II.4.F)
SPA.C.I.1 materie prime, sussidiarie e di consumo | SPA.C.I.2 prodotti in corso e semilavorati | SPA.C.I.3 lavori in corso su ordinazione | SPA.C.I.4 prodotti finiti e merci | SPA.C.I.5 acconti
SPA.C.II.1 crediti verso clienti (anche fatture da emettere, effetti, ricevute bancarie; fondo svalutazione crediti = SPA.C.II.1.F) | SPA.C.II.2 verso controllate | SPA.C.II.3 verso collegate | SPA.C.II.4 verso controllanti | SPA.C.II.5-bis crediti tributari (erario, IVA a credito, acconti IRES/IRAP, ritenute subite) | SPA.C.II.5-ter imposte anticipate | SPA.C.II.5-quater verso altri (anticipi a fornitori, INAIL/INPS a credito, crediti diversi)
SPA.C.III attivita' finanziarie che non costituiscono immobilizzazioni
SPA.C.IV.1 depositi bancari e postali (c/c attivi) | SPA.C.IV.2 assegni | SPA.C.IV.3 denaro e valori in cassa
SPA.D ratei e risconti attivi
SPP.A.I capitale | SPP.A.II riserva sovrapprezzo | SPP.A.III riserve di rivalutazione | SPP.A.IV riserva legale | SPP.A.V riserve statutarie | SPP.A.VI altre riserve (straordinaria, versamenti soci in conto capitale) | SPP.A.VII riserva copertura flussi | SPP.A.VIII utili/perdite portati a nuovo | SPP.A.IX utile/perdita dell'esercizio | SPP.A.X riserva negativa azioni proprie
SPP.B.1 fondi trattamento quiescenza | SPP.B.2 fondi per imposte anche differite | SPP.B.3 derivati passivi | SPP.B.4 altri fondi rischi e oneri
SPP.C trattamento di fine rapporto (fondo TFR)
SPP.D.1 obbligazioni | SPP.D.3 debiti verso soci per finanziamenti | SPP.D.4 debiti verso banche (c/c passivi, mutui, finanziamenti bancari, anticipi fatture) | SPP.D.5 verso altri finanziatori (leasing finanziari, finanziarie) | SPP.D.6 acconti da clienti | SPP.D.7 debiti verso fornitori (anche fatture da ricevere) | SPP.D.8 titoli di credito | SPP.D.9 verso controllate | SPP.D.10 verso collegate | SPP.D.11 verso controllanti | SPP.D.12 debiti tributari (erario, IVA a debito, ritenute da versare, IRES/IRAP) | SPP.D.13 istituti di previdenza (INPS, INAIL, enti) | SPP.D.14 altri debiti (dipendenti c/retribuzioni, amministratori, debiti diversi)
SPP.E ratei e risconti passivi
CE.A.1 ricavi delle vendite e delle prestazioni | CE.A.2 variazione rimanenze prodotti (rimanenze iniziali e finali di prodotti) | CE.A.3 variazione lavori in corso | CE.A.4 incrementi di immobilizzazioni per lavori interni | CE.A.5 altri ricavi e proventi (contributi, rimborsi, plusvalenze ordinarie, sopravvenienze attive)
CE.B.6 acquisti materie prime, merci, materiale di consumo | CE.B.7 servizi (utenze, consulenze, manutenzioni, trasporti, assicurazioni, compensi amministratori, pubblicita', spese bancarie di servizio) | CE.B.8 godimento beni di terzi (affitti, locazioni, noleggi, canoni di leasing) | CE.B.9.a salari e stipendi | CE.B.9.b oneri sociali | CE.B.9.c trattamento di fine rapporto | CE.B.9.e altri costi del personale | CE.B.10.a ammortamento immobilizzazioni immateriali | CE.B.10.b ammortamento immobilizzazioni materiali | CE.B.10.c altre svalutazioni immobilizzazioni | CE.B.10.d svalutazione crediti | CE.B.11 variazione rimanenze materie prime e merci (rimanenze iniziali e finali di materie/merci) | CE.B.12 accantonamenti per rischi | CE.B.13 altri accantonamenti | CE.B.14 oneri diversi di gestione (imposte e tasse non sul reddito, IMU, sopravvenienze passive, minusvalenze, sanzioni)
CE.C.15 proventi da partecipazioni | CE.C.16 altri proventi finanziari (interessi attivi) | CE.C.17 interessi e altri oneri finanziari (interessi passivi, oneri su finanziamenti) | CE.C.17-bis utili e perdite su cambi
CE.D.18 rivalutazioni | CE.D.19 svalutazioni
CE.20 imposte sul reddito (IRES, IRAP, imposte differite e anticipate) | CE.21 utile o perdita dell'esercizio (solo controllo)
```

- [ ] **Step 2: test che falliscono** in `tests/test_snello_percorsi.py`:

```python
from decimal import Decimal as D

import pytest

from importers.import_snello import percorsi as P


@pytest.mark.parametrize("p, atteso", [
    ("SPA.B.I.5", "sp02e"), ("SPA.B.II.2", "sp03b"), ("SPA.B.II.2.F", "sp03b"), ("SPA.B.II", "sp03"),
    ("SPA.B.III.2", "sp04b"), ("SPA.B.III.2.O", "sp04c"), ("SPA.C.I.1", "sp05a"), ("SPA.C.I", "sp05"),
    ("SPA.C.II.1", "sp06a"), ("SPA.C.II.1.E", "sp06a"), ("SPA.C.II.1.O", "sp07a"), ("SPA.C.II.5-bis", "sp06e"),
    ("SPA.C.II.5-quater.O", "sp07g"), ("SPA.C.II.E", "sp06"), ("SPA.C.II.O", "sp07"), ("SPA.C.IV.3", "sp09"),
    ("SPA.D", "sp10"), ("SPP.A.I", "sp11"), ("SPP.A.IV", "sp12c"), ("SPP.A.VIII", "sp12g"), ("SPP.A.IX", "sp13"),
    ("SPP.B.4", "sp14d"), ("SPP.C", "sp15"), ("SPP.D.4", "sp16a"), ("SPP.D.4.O", "sp17a"), ("SPP.D.3", "sp16b"),
    ("SPP.D.7.E", "sp16d"), ("SPP.D.12", "sp16e"), ("SPP.D.13", "sp16f"), ("SPP.D.14.O", "sp17g"),
    ("SPP.D.E", "sp16"), ("SPP.D.O", "sp17"), ("SPP.E", "sp18"),
    ("CE.A.1", "ce01"), ("CE.A.2", "ce02"), ("CE.A.3", "ce03"), ("CE.A.4", "ce03a"), ("CE.A.5", "ce04"), ("CE.B.6", "ce05"),
    ("CE.B.7", "ce06"), ("CE.B.8", "ce07"), ("CE.B.9.a", "ce08b"), ("CE.B.9.b", "ce08c"), ("CE.B.9.c", "ce08a"),
    ("CE.B.9.e", "ce08d"), ("CE.B.9", "ce08"), ("CE.B.10.a", "ce09a"), ("CE.B.10.d", "ce09d"), ("CE.B.10", "ce09"),
    ("CE.B.11", "ce10"), ("CE.B.12", "ce11"), ("CE.B.13", "ce11b"), ("CE.B.14", "ce12"), ("CE.C.16.d", "ce14"),
    ("CE.C.17", "ce15"), ("CE.C.17-bis", "ce16"), ("CE.D.18", "ce17a"), ("CE.D.19", "ce17b"), ("CE.20", "ce20"),
    ("CE.D.20", "ce20"), ("CE.21", None), ("X", None), ("R", None), ("SPA.Z.9", None), ("", None),
])
def test_campo_da_percorso(p, atteso):
    assert P.campo_da_percorso(p) == atteso


def test_nomi_completi_dal_modello_orm():
    assert P.NOMI["sp06a"] == "sp06a_crediti_clienti_breve"
    assert P.NOMI["ce08b"] == "ce08b_salari_stipendi"
    assert P.NOMI["sp16"] == "sp16_debiti_breve"


def test_fondo_risultato_lato():
    assert P.e_fondo("SPA.B.II.4.F") and not P.e_fondo("SPA.B.II.4")
    assert P.e_risultato("CE.21") and P.e_risultato("CE.D.21") and not P.e_risultato("CE.20")
    assert P.lato_di("SPA.C.IV.1") == "att" and P.lato_di("SPP.D.4") == "pas" and P.lato_di("CE.B.7") == "ce"


def test_famiglia():
    assert P.famiglia("sp03b") == "att" and P.famiglia("sp16a") == "pas"
    assert P.famiglia("ce01") == "ric" and P.famiglia("ce17a") == "ric" and P.famiglia("ce18") == "ric"
    assert P.famiglia("ce06") == "cos" and P.famiglia("ce17b") == "cos" and P.famiglia("ce20") == "cos"


def test_completa_aggregati_e_nomi():
    bs, ce = P.completa({"sp03b": D("100"), "sp03d": D("50"), "sp06": D("30"), "sp06a": D("70"),
                         "sp16a": D("10"), "ce08b": D("5"), "ce08c": D("2"), "ce06": D("9")})
    assert bs["sp03_immob_materiali"] == D("150.00")
    assert bs["sp03b_impianti_macchinari"] == D("100.00")
    assert bs["sp06_crediti_breve"] == D("100.00")      # 30 stampato senza dettaglio + 70 clienti
    assert bs["sp16_debiti_breve"] == D("10.00")
    assert ce["ce08_costi_personale"] == D("7.00")
    assert ce["ce06_servizi"] == D("9.00")
    assert all(k.startswith("sp") for k in bs) and all(k.startswith("ce") for k in ce)
```

- [ ] **Step 3:** `pytest tests/test_snello_percorsi.py -q` → falliscono (modulo assente).
- [ ] **Step 4: implementazione** — `importers/import_snello/__init__.py`:

```python
"""Import PDF snello: struttura, macroconti per percorso di legge, verifica con tappo dichiarato."""
```

`importers/import_snello/percorsi.py`:

```python
"""Percorsi di legge (artt. 2424-2425 c.c.) -> campi del budget.

Il modello nomina la voce di legge ('SPP.D.4.E'); questa tabella fissa la traduce nel campo.
Mai far scegliere al modello un codice da un elenco lungo: senza thinking lo scorre in ordine.
"""
from __future__ import annotations

import os
from decimal import Decimal

LEGENDA = open(os.path.join(os.path.dirname(__file__), "legenda.txt"), encoding="utf-8").read()


def _nomi() -> dict[str, str]:
    from database.models import BalanceSheet, IncomeStatement
    out = {}
    for modello in (BalanceSheet, IncomeStatement):
        for colonna in modello.__table__.columns:
            if colonna.name[:2] in ("sp", "ce"):
                out[colonna.name.split("_")[0]] = colonna.name
    return out


NOMI = _nomi()
_CR = {"1": "a", "2": "b", "3": "c", "4": "d", "5-bis": "e", "5-ter": "f", "5-quater": "g"}
_DEB = {"1": "c", "2": "c", "3": "b", "4": "a", "5": "b", "6": "g", "7": "d", "8": "g", "9": "g",
        "10": "g", "11": "g", "11-bis": "g", "12": "e", "13": "f", "14": "g"}
_PN = {"I": "sp11", "II": "sp12a", "III": "sp12b", "IV": "sp12c", "V": "sp12d", "VI": "sp12e",
       "VII": "sp12f", "VIII": "sp12g", "IX": "sp13", "X": "sp12h"}
_CE = {"1": "ce01", "2": "ce02", "3": "ce03", "4": "ce03a", "5": "ce04", "6": "ce05", "7": "ce06",
       "8": "ce07", "11": "ce10", "12": "ce11", "13": "ce11b", "14": "ce12", "15": "ce13", "16": "ce14",
       "17": "ce15", "17-bis": "ce16", "18": "ce17a", "19": "ce17b", "20": "ce20"}
RICAVI = {"ce01", "ce02", "ce03", "ce03a", "ce04", "ce13", "ce14", "ce16", "ce17a", "ce18"}
ATTIVO = ("sp01", "sp02", "sp03", "sp04", "sp05", "sp06", "sp07", "sp08", "sp09", "sp10")

CONTROPARTE = {
    "SPA.C.IV": "SPP.D.4", "SPA.C.II.5-bis": "SPP.D.12", "SPA.C.II.1": "SPP.D.6", "SPA.C.II.5-quater": "SPP.D.14",
    "SPA.C.II.2": "SPP.D.9", "SPA.C.II.3": "SPP.D.10", "SPA.C.II.4": "SPP.D.11",
    "SPP.D.4": "SPA.C.IV.1", "SPP.D.12": "SPA.C.II.5-bis", "SPP.D.13": "SPA.C.II.5-quater",
    "SPP.D.7": "SPA.C.II.5-quater", "SPP.D.14": "SPA.C.II.5-quater", "SPP.D.5": "SPA.C.II.5-quater",
    "SPP.D.6": "SPA.C.II.1", "SPP.D.3": "SPA.C.II.5-quater",
}


def e_fondo(p: str) -> bool:
    return p.endswith(".F")


def e_risultato(p: str) -> bool:
    return p in ("CE.21", "CE.D.21")


def lato_di(p: str) -> str | None:
    return {"SPA": "att", "SPP": "pas", "CE": "ce"}.get(p.split(".")[0])


def campo_da_percorso(p: str) -> str | None:
    if not p or p in ("X", "R") or e_risultato(p):
        return None
    t = [x for x in p.split(".") if x != "F"]
    scad = t[-1] if len(t) > 2 and t[-1] in ("E", "O") else None
    if scad:
        t = t[:-1]
    try:
        if t[0] == "SPA" and len(t) >= 2:
            if t[1] == "A":
                return "sp01"
            if t[1] == "B":
                if len(t) == 2:
                    return None
                if len(t) == 3:
                    return {"I": "sp02", "II": "sp03", "III": "sp04"}.get(t[2])
                n = int(t[3])
                if t[2] == "I" and 1 <= n <= 7:
                    return "sp02" + "abcdefg"[n - 1]
                if t[2] == "II" and 1 <= n <= 5:
                    return "sp03" + "abcde"[n - 1]
                if t[2] == "III":
                    return {1: "sp04a", 2: "sp04c" if scad == "O" else "sp04b", 3: "sp04d", 4: "sp04e"}.get(n)
            if t[1] == "C" and len(t) >= 3:
                if t[2] == "I":
                    return "sp05" + "abcde"[int(t[3]) - 1] if len(t) > 3 else "sp05"
                if t[2] == "II":
                    base = "sp07" if scad == "O" else "sp06"
                    return base + _CR[t[3]] if len(t) > 3 else base
                if t[2] == "III":
                    return "sp08"
                if t[2] == "IV":
                    return "sp09"
            if t[1] == "D":
                return "sp10"
        if t[0] == "SPP" and len(t) >= 2:
            if t[1] == "A" and len(t) >= 3:
                return _PN.get(t[2])
            if t[1] == "B" and len(t) >= 3:
                return "sp14" + "abcd"[int(t[2]) - 1]
            if t[1] == "C":
                return "sp15"
            if t[1] == "D":
                base = "sp17" if scad == "O" else "sp16"
                return base + _DEB[t[2]] if len(t) > 2 else (base if scad else None)
            if t[1] == "E":
                return "sp18"
        if t[0] == "CE":
            n = [x for x in t[1:] if x not in ("A", "B", "C", "D", "E")]
            if not n:
                return None
            voce, sub = n[0], (n[1] if len(n) > 1 else None)
            if voce == "9":
                return {"a": "ce08b", "b": "ce08c", "c": "ce08a", "d": "ce08d", "e": "ce08d"}.get(sub, "ce08") if sub else "ce08"
            if voce == "10":
                return {"a": "ce09a", "b": "ce09b", "c": "ce09c", "d": "ce09d"}.get(sub) if sub else "ce09"
            return _CE.get(voce)
    except (ValueError, KeyError, IndexError):
        return None
    return None


def famiglia(codice: str) -> str:
    if codice.startswith("sp"):
        return "att" if codice[:4] in ATTIVO else "pas"
    return "ric" if codice in RICAVI else "cos"


def completa(importi: dict[str, Decimal]) -> tuple[dict, dict]:
    """Codici brevi -> (bs, ce) con nomi completi; ogni aggregato = valore diretto + sotto-campi."""
    from importers.iv_cee_hierarchy import aggregates_with_details, detail_fields
    cent = Decimal("0.01")
    pieni = {NOMI[c]: Decimal(v) for c, v in importi.items() if c in NOMI}
    for aggregato in aggregates_with_details():
        dettagli = [d for d in detail_fields(aggregato) if d in pieni]
        if dettagli:
            pieni[aggregato] = pieni.get(aggregato, Decimal(0)) + sum((pieni[d] for d in dettagli), Decimal(0))
    bs = {k: v.quantize(cent) for k, v in pieni.items() if k.startswith("sp")}
    ce = {k: v.quantize(cent) for k, v in pieni.items() if k.startswith("ce")}
    return bs, ce
```

- [ ] **Step 5:** `pytest tests/test_snello_percorsi.py -q` verde. Se `test_completa_aggregati_e_nomi` fallisce perché `detail_fields("sp06_crediti_breve")` non elenca `sp06a_crediti_clienti_breve` (o `ce08_costi_personale` non elenca `ce08b`), leggere `_DETAIL_GROUPS`/`_CE_DETAIL_GROUPS` in `importers/iv_cee_hierarchy.py` e riportarlo nel report senza cambiare il test: è un'informazione per il controllore.
- [ ] **Step 6: commit** `feat(import): percorsi di legge tradotti nei campi del budget, con legenda`

---

### Task 4: righe e foglie di un elenco di conti

**Files:**
- Create: `importers/import_snello/righe.py`
- Test: `tests/test_snello_righe.py`

**Interfaces:**
- Consumes: `importers.detail_enrichment.SourceRow`, `collect_source_rows`.
- Produces:
  - `@dataclass Riga(id: str, pagina: int, lato: str, testo: str, valore: Decimal | None, sezione: str = "", mastro: str | None = None, totale: bool = False, percorso: str | None = None)`
  - `importi(testo: str) -> list[tuple[Decimal, str]]` — importi della riga con marcatore `"D"`/`"A"`/`""`; toglie i `_` di sottolineatura fra le cifre.
  - `etichetta(testo: str) -> str` — il testo senza importi e marcatori D/A.
  - `regola_colonna(ruoli: list[str]) -> dict` — `{"n": len(ruoli), "k": indice del saldo}`; `{}` se non c'è un saldo.
  - `saldo(riga: SourceRow, regola: dict) -> Decimal | None`
  - `marca_totali(righe: list[Riga]) -> Counter` — marca `totale=True` e `mastro`; restituisce le direzioni imparate.
  - `righe_da_pdf(file_path: str, pagine: set[int] | None, ruoli: list[str], ocr_text: str | None = None) -> list[Riga]`
  - `foglie(righe: list[Riga]) -> list[Riga]` — con valore, non totali, con testo.

- [ ] **Step 1: test che falliscono** in `tests/test_snello_righe.py`:

```python
from decimal import Decimal as D

from importers.detail_enrichment import SourceRow
from importers.import_snello import righe as R


def test_importi_con_segni_e_sottolineature():
    assert R.importi("CASSA 1.199,64 A 4.251,97 3.119,94 D") == [(D("1199.64"), "A"), (D("4251.97"), ""), (D("3119.94"), "D")]
    assert R.importi("riserva legale _3_.09_4_,_3_1_") == [(D("3094.31"), "")]
    assert R.importi("Beni non superiori a € 516,46 24.087,77")[-1] == (D("24087.77"), "")
    assert R.importi("Perdite (1.500,00)") == [(D("-1500.00"), "")]
    assert R.importi("conto 10000001673 c/c 320.100,68") == [(D("320100.68"), "")]


def test_etichetta():
    assert R.etichetta("10101 CASSA CONTANTI 839,66 D 2.000,00") == "10101 CASSA CONTANTI"


def test_regola_e_saldo():
    assert R.regola_colonna(["saldo_precedente", "dare", "avere", "saldo_corrente"]) == {"n": 4, "k": 3}
    assert R.regola_colonna(["saldo_corrente", "saldo_precedente", "variazione", "percentuale"]) == {"n": 4, "k": 0}
    assert R.regola_colonna(["dare", "avere"]) == {}
    r4 = SourceRow("p1r1", 1, "T", "X 10,00 D 5,00 3,00 12,00 A", (D("10"), D("5"), D("3"), D("12")))
    assert R.saldo(r4, {"n": 4, "k": 3}) == D("-12.00")
    r1 = SourceRow("p1r2", 1, "T", "X 7,00", (D("7"),))
    assert R.saldo(r1, {"n": 4, "k": 3}) == D("7.00")          # un solo importo e il saldo e' l'ultima colonna
    r2 = SourceRow("p1r3", 1, "T", "X 7,00 8,00", (D("7"), D("8")))
    assert R.saldo(r2, {"n": 4, "k": 1}) is None               # ambiguo: dichiarato, non indovinato
    assert R.saldo(r1, {}) == D("7.00")                        # senza struttura: l'ultimo importo


def _r(i, valore, lato="L", testo=None):
    return R.Riga(id=str(i), pagina=1, lato=lato, testo=testo or f"conto {i}", valore=None if valore is None else D(valore))


def test_totali_dopo_i_figli_catene_e_somme_zero():
    righe = [_r(1, "100"), _r(2, "50"), _r(3, "150", testo="mastro A"),        # totale dopo i figli
             _r(4, "30"), _r(5, "30", testo="mastro B"), _r(6, "30", testo="gruppo B"),  # catena
             _r(7, "10"), _r(8, "-10"), _r(9, "5"), _r(10, "5", testo="mastro C")]       # coppia a somma zero dentro
    direzioni = R.marca_totali(righe)
    assert direzioni.most_common(1)[0][0] == -1
    tot = {r.id for r in righe if r.totale}
    assert {"3", "5", "6", "10"} <= tot
    assert "4" not in tot and "1" not in tot
    assert sum(r.valore for r in R.foglie(righe)) == D("185")   # 100+50+30+10-10+5


def test_totali_prima_dei_figli_e_lati_separati():
    righe = [_r(1, "80", testo="mastro"), _r(2, "50"), _r(3, "30"),
             _r(4, "80", lato="R", testo="mastro passivo"), _r(5, "80", lato="R")]
    R.marca_totali(righe)
    assert [r.id for r in righe if r.totale] == ["1", "4"]
    assert righe[1].mastro == "mastro"
```

- [ ] **Step 2:** falliscono.
- [ ] **Step 3: implementazione** `importers/import_snello/righe.py`:

```python
"""Righe di un elenco di conti: saldo, segno, totali esclusi perche' somma di righe vicine.

La struttura fisica delle righe viene dal lettore del repo (collect_source_rows: rotazione,
righe fisiche, sezioni contrapposte, colonne SAP). Qui si sceglie il saldo e si tolgono i
totali: il totale stampato decide, mai il prefisso del codice di conto.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal

_AMT = re.compile(r"^\(?-?(\d{1,3}(\.\d{3})+|\d+),\d{2}\)?-?$")
_MIGLIAIA = re.compile(r"^\(?-?\d{1,3}(\.\d{3})+\)?-?$")
_AMT_TESTO = re.compile(r"\s+\(?-?[\d.]+,\d{2}\)?-?(\s+[DA](?=\s|$))?")


@dataclass
class Riga:
    id: str
    pagina: int
    lato: str
    testo: str
    valore: Decimal | None
    sezione: str = ""
    mastro: str | None = None
    totale: bool = False
    percorso: str | None = None


def _dec(t: str) -> Decimal:
    negativo = t.startswith("-") or t.endswith("-") or t.startswith("(")
    v = Decimal(t.strip("()-").replace(".", "").replace(",", "."))
    return -v if negativo else v


def importi(testo: str) -> list[tuple[Decimal, str]]:
    toks = testo.replace("_", "").split()
    out = []
    for i, t in enumerate(toks):
        if _AMT.match(t) or _MIGLIAIA.match(t):
            dopo = toks[i + 1] if i + 1 < len(toks) else ""
            out.append((_dec(t), dopo if dopo in ("D", "A") else ""))
    return out


def etichetta(testo: str) -> str:
    return re.sub(r"\s+", " ", _AMT_TESTO.sub("", " " + testo.replace("_", ""))).strip()


def regola_colonna(ruoli: list[str]) -> dict:
    for ruolo in ("saldo_corrente", "saldo_finale"):
        if ruolo in ruoli:
            return {"n": len(ruoli), "k": ruoli.index(ruolo)}
    return {}


def saldo(riga, regola: dict) -> Decimal | None:
    vs = importi(riga.text)
    if not vs:
        return None
    if not regola:
        v, m = vs[-1]
    elif len(vs) == regola["n"]:
        v, m = vs[regola["k"]]
    elif regola["k"] == regola["n"] - 1:
        v, m = vs[-1]
    elif regola["k"] == 0:
        v, m = vs[0]
    else:
        return None
    v = -abs(v) if m == "A" else v
    return v.quantize(Decimal("0.01"))


def _marca(righe: list[Riga], forzata: int | None) -> Counter:
    per_lato = defaultdict(list)
    for r in righe:
        r.totale, r.mastro = False, None
        if r.valore is not None:
            per_lato[r.lato].append(r)
    direzioni: Counter = Counter()
    for kmin in (2, 1):
        if forzata is not None:
            consentite = (forzata,)
        elif kmin == 2 or not direzioni:
            consentite = (1, -1)
        else:
            consentite = (direzioni.most_common(1)[0][0],)
        cambiato = True
        while cambiato:
            cambiato = False
            for seq in per_lato.values():
                vive = [r for r in seq if not r.totale]
                for i, r in enumerate(vive):
                    if not r.valore:
                        continue
                    for d in consentite:
                        s, j, membri = Decimal(0), i + d, []
                        while 0 <= j < len(vive) and len(membri) < 80:
                            s += vive[j].valore
                            membri.append(vive[j])
                            if len(membri) >= kmin and s == r.valore:
                                r.totale = cambiato = True
                                if kmin == 2 and forzata is None:
                                    direzioni[d] += 1
                                for m in membri:
                                    m.mastro = m.mastro or r.testo
                                break
                            j += d
                        if r.totale:
                            break
                    if cambiato:
                        break
                if cambiato:
                    break
    return direzioni


def marca_totali(righe: list[Riga]) -> Counter:
    """Prima impara la direzione dei totali (prima o dopo i figli) dai gruppi di almeno due
    righe, poi ricalcola tutto con quella sola direzione: una sequenza all'indietro che
    somma per caso (un bene e il suo fondo si annullano) non marca piu' un conto vero."""
    direzioni = _marca(righe, None)
    if direzioni:
        _marca(righe, direzioni.most_common(1)[0][0])
    return direzioni


def righe_da_pdf(file_path: str, pagine: set[int] | None, ruoli: list[str],
                 ocr_text: str | None = None) -> list[Riga]:
    from importers.detail_enrichment import collect_source_rows
    regola = regola_colonna(ruoli)
    out = []
    for r in collect_source_rows(file_path, ocr_text=ocr_text):
        if pagine and r.page not in pagine:
            continue
        out.append(Riga(id=r.id, pagina=r.page, lato=r.side, testo=etichetta(r.text),
                        valore=saldo(r, regola), sezione=r.statement))
    marca_totali(out)
    return out


def foglie(righe: list[Riga]) -> list[Riga]:
    return [r for r in righe if r.valore is not None and not r.totale and r.testo]
```

- [ ] **Step 4:** `pytest tests/test_snello_righe.py -q` verde.
- [ ] **Step 5: commit** `feat(import): righe e foglie di un elenco di conti, totali riconosciuti dalle somme stampate`

---

### Task 5: dai percorsi agli importi

**Files:**
- Create: `importers/import_snello/conti.py`
- Test: `tests/test_snello_conti.py`

**Interfaces:**
- Consumes: Task 3 (`campo_da_percorso`, `e_fondo`, `e_risultato`, `famiglia`, `completa`, `CONTROPARTE`, `lato_di`), Task 4 (`Riga`).
- Produces:
  - `applica_lato(foglie: list[Riga]) -> int` — riscrive `percorso` dei conti SP stampati sul lato opposto; restituisce quanti.
  - `da_foglie(foglie: list[Riga]) -> tuple[dict, dict, dict]` — `(bs, ce, diag)`.
  - `da_coppie(coppie: list[tuple[str, Decimal]]) -> tuple[dict, dict, dict]` — `(bs, ce, diag)`.
  - `diag`: `{"non_mappati": [[id|percorso, percorso, importo]], "escluse": [[id, percorso, importo]], "risultato_stampato": str | None, "lato_corretti": int}` (importi come stringhe).

- [ ] **Step 1: test che falliscono** in `tests/test_snello_conti.py`:

```python
from decimal import Decimal as D

from importers.import_snello.conti import applica_lato, da_coppie, da_foglie
from importers.import_snello.righe import Riga


def _f(i, lato, valore, percorso):
    return Riga(id=str(i), pagina=1, lato=lato, testo=f"c{i}", valore=D(valore), percorso=percorso)


def test_contrapposte_fondo_a_destra_e_cc_passivo():
    foglie = [_f(1, "L", "1000", "SPA.B.II.2"), _f(2, "R", "400", "SPA.B.II.2.F"),
              _f(3, "L", "300", "SPA.C.IV.1"), _f(4, "R", "150", "SPA.C.IV.1"),   # c/c stampato fra le passivita'
              _f(5, "R", "500", "SPP.A.I"), _f(6, "R", "250", "SPP.D.7"),
              _f(7, "L", "80", "CE.B.7"), _f(8, "R", "100", "CE.A.1"), _f(9, "R", "20", "R"),
              _f(10, "L", "5", "X")]
    bs, ce, diag = da_foglie(foglie)
    assert bs["sp03b_impianti_macchinari"] == D("600.00")
    assert bs["sp09_disponibilita_liquide"] == D("300.00")
    assert bs["sp16a_debiti_banche_breve"] == D("150.00")
    assert bs["sp16_debiti_breve"] == D("400.00")
    assert ce["ce06_servizi"] == D("80.00") and ce["ce01_ricavi_vendite"] == D("100.00")
    assert diag["risultato_stampato"] == "20.00" and diag["lato_corretti"] == 1
    assert diag["escluse"] == [["10", "X", "5.00"]]


def test_colonna_unica_con_segno():
    foglie = [_f(1, "T", "1000", "SPA.B.II.4"), _f(2, "T", "-300", "SPA.B.II.4.F"),
              _f(3, "T", "-200", "SPP.D.4"), _f(4, "T", "50", "SPP.D.12"),          # erario in dare: e' un credito
              _f(5, "T", "-500", "SPP.A.I"), _f(6, "T", "90", "CE.B.6"), _f(7, "T", "-60", "CE.A.1")]
    bs, ce, diag = da_foglie(foglie)
    assert bs["sp03d_altri_beni"] == D("700.00")
    assert bs["sp16a_debiti_banche_breve"] == D("200.00")
    assert bs["sp06e_crediti_tributari_breve"] == D("50.00")
    assert bs["sp11_capitale"] == D("500.00")
    assert ce["ce05_materie_prime"] == D("90.00") and ce["ce01_ricavi_vendite"] == D("60.00")


def test_applica_lato_non_tocca_i_fondi():
    foglie = [_f(1, "L", "10", "SPA.B.II.2"), _f(2, "R", "4", "SPA.B.II.2.F"), _f(3, "R", "9", "SPP.D.7")]
    assert applica_lato(foglie) == 0
    assert foglie[1].percorso == "SPA.B.II.2.F"


def test_coppie_schema_di_legge_genitore_e_fondo():
    coppie = [("SPA.B.I", D("584094")), ("SPA.B.I.1", D("118720")), ("SPA.B.I.5", D("88362")),
              ("SPA.B.II.2", D("47738")), ("SPA.B.II.2.F", D("17605")),
              ("SPA.C.II.1", D("863659")), ("SPA.C.II.1.E", D("800000")), ("SPA.C.II.1.O", D("63659")),
              ("SPP.D.4", D("100")), ("SPP.D.4", D("100")), ("CE.B.7", D("9")), ("CE.21", D("7422"))]
    bs, ce, diag = da_coppie(coppie)
    assert bs["sp02_immob_immateriali"] == D("207082.00")        # il genitore cade: contano i figli
    assert bs["sp03b_impianti_macchinari"] == D("30133.00")       # fondo sottratto
    assert bs["sp06a_crediti_clienti_breve"] == D("800000.00") and bs["sp07a_crediti_clienti_lungo"] == D("63659.00")
    assert bs["sp16a_debiti_banche_breve"] == D("100.00")         # la voce ripetuta si conta una volta
    assert diag["risultato_stampato"] == "7422.00"
```

- [ ] **Step 2:** falliscono.
- [ ] **Step 3: implementazione** `importers/import_snello/conti.py`:

```python
"""Dai percorsi di legge agli importi dei campi, con le regole contabili di sempre:
la colonna decide il lato, un fondo si sottrae al bene, nessun conto contato due volte."""
from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal

from importers.import_snello.percorsi import (CONTROPARTE, campo_da_percorso, completa, e_fondo,
                                              e_risultato, famiglia, lato_di)

_C = Decimal("0.01")


def _corsia(f, due_lati: bool):
    return (1 if f.lato == "R" else 0) if due_lati else (f.valore >= 0)


def applica_lato(foglie) -> int:
    """Un conto il cui percorso sta dall'altra parte rispetto a dove e' stampato passa alla voce
    corrispondente del lato giusto (c/c fra le passivita' -> debiti verso banche). La colonna e' la
    verita' sul lato; la descrizione decide la voce."""
    sp = [f for f in foglie if f.percorso and lato_di(f.percorso) in ("att", "pas") and not e_fondo(f.percorso)]
    due_lati = len({f.lato for f in sp} & {"L", "R"}) == 2
    peso = Counter()
    for f in sp:
        peso[(lato_di(f.percorso), _corsia(f, due_lati))] += abs(f.valore)
    lato_normale = {}
    for sez in ("att", "pas"):
        candidati = [(v, k) for (s, k), v in peso.items() if s == sez]
        if candidati:
            lato_normale[sez] = max(candidati)[1]
    if len(set(lato_normale.values())) < 2:
        return 0
    n = 0
    for f in sp:
        if _corsia(f, due_lati) == lato_normale[lato_di(f.percorso)]:
            continue
        for prefisso, destinazione in CONTROPARTE.items():
            if f.percorso == prefisso or f.percorso.startswith(prefisso + "."):
                f.percorso = destinazione
                n += 1
                break
    return n


def da_foglie(foglie):
    diag = {"non_mappati": [], "escluse": [], "risultato_stampato": None, "lato_corretti": 0}
    diag["lato_corretti"] = applica_lato(foglie)
    due_lati = len({f.lato for f in foglie} & {"L", "R"}) == 2
    per_famiglia = defaultdict(list)
    for f in foglie:
        if f.percorso == "R" or (f.percorso and e_risultato(f.percorso)):
            diag["risultato_stampato"] = str(abs(f.valore).quantize(_C))
            continue
        if not f.percorso or f.percorso == "X":
            diag["escluse"].append([f.id, f.percorso or "", str(f.valore.quantize(_C))])
            continue
        codice = campo_da_percorso(f.percorso)
        if codice is None:
            diag["non_mappati"].append([f.id, f.percorso, str(f.valore.quantize(_C))])
            continue
        per_famiglia[famiglia(codice)].append((f, codice))
    importi = defaultdict(Decimal)
    for elementi in per_famiglia.values():
        peso_corsia, peso_segno = Counter(), Counter()
        for f, _ in elementi:
            if not e_fondo(f.percorso):
                peso_corsia[_corsia(f, True) if due_lati else 0] += abs(f.valore)
                peso_segno[f.valore >= 0] += abs(f.valore)
        corsia_n = peso_corsia.most_common(1)[0][0] if peso_corsia else 0
        positivo_n = peso_segno.most_common(1)[0][0] if peso_segno else True
        for f, codice in elementi:
            v = abs(f.valore)
            if e_fondo(f.percorso):
                contro = True
            else:
                corsia = _corsia(f, True) if due_lati else 0
                contro = (corsia != corsia_n) ^ ((f.valore >= 0) != positivo_n)
            importi[codice] += -v if contro else v
    bs, ce = completa(dict(importi))
    return bs, ce, diag


def da_coppie(coppie):
    """Schema di legge: coppie (percorso, importo) come stampate. Un percorso che ha un discendente
    fra le coppie e' un totale e cade; una voce ripetuta conta una volta; un fondo si sottrae."""
    diag = {"non_mappati": [], "escluse": [], "risultato_stampato": None, "lato_corretti": 0}
    viste, uniche = set(), []
    for p, v in coppie:
        if p not in viste:
            viste.add(p)
            uniche.append((p, Decimal(v)))
    tutti = [p for p, _ in uniche]
    importi = defaultdict(Decimal)
    for p, v in uniche:
        if e_risultato(p):
            diag["risultato_stampato"] = str(v.quantize(_C))
            continue
        if any(q != p and q.startswith(p + ".") and not e_fondo(q) for q in tutti):
            continue
        codice = campo_da_percorso(p)
        if codice is None:
            diag["non_mappati" if p not in ("X", "R") else "escluse"].append([p, p, str(v.quantize(_C))])
            continue
        importi[codice] += -abs(v) if e_fondo(p) else v
    bs, ce = completa(dict(importi))
    return bs, ce, diag
```

- [ ] **Step 4:** `pytest tests/test_snello_conti.py tests/test_snello_percorsi.py -q` verde.
- [ ] **Step 5: commit** `feat(import): importi dai percorsi di legge, lato dalla colonna e fondi sottratti`

---

### Task 6: lettura con Qwen (percorsi dei conti, voci di legge, trascrizione di pagine senza testo)

**Files:**
- Create: `importers/import_snello/lettura.py`
- Test: `tests/test_snello_lettura.py`

**Interfaces:**
- Consumes: Task 1 (`chiama_gx10_testo`, `chiama_gx10_json`), Task 3 (`LEGENDA`), Task 4 (`Riga`).
- Produces:
  - `BLOCCO = 60`
  - `percorsi_dei_conti(righe: list[Riga], foglie: list[Riga], *, chiama=None) -> dict` — assegna `percorso` alle foglie; restituisce `{"chiamate": n, "saltate_prima": n, "senza_percorso": n}`. `chiama(system, user, max_tokens) -> str`, default `chiama_gx10_testo`.
  - `voci_di_legge(testo: str, intestazioni: list[str], *, chiama_json=None, nota: str = "") -> dict` — `{"corrente": [(percorso, Decimal)], "precedente": [...], "totali": {...}}`. `chiama_json(system, user, schema, max_tokens) -> dict`, default `chiama_gx10_json`.
  - `trascrivi_pagine(pdf: str, pagine: list[int], *, chiama_json=None, strisce: int = 3, dpi: int = 120) -> str` — righe `etichetta | importo1 | importo2`, nell'ordine della pagina.

- [ ] **Step 1: test che falliscono** in `tests/test_snello_lettura.py`:

```python
from decimal import Decimal as D

from importers.import_snello import lettura as L
from importers.import_snello.righe import Riga


def _riga(i, testo, valore="10", totale=False, lato="L"):
    return Riga(id=f"p1r{i}", pagina=1, lato=lato, testo=testo, valore=None if valore is None else D(valore), totale=totale)


def test_percorsi_numerati_e_seconda_chiamata_sulle_saltate():
    righe = [_riga(0, "ATTIVITA'", None)] + [_riga(i, f"conto {i}") for i in range(1, 4)]
    foglie = righe[1:]
    chiamate = []
    def chiama(system, user, max_tokens):
        chiamate.append(user)
        if len(chiamate) == 1:
            assert "# ATTIVITA'" in user and "LEGENDA" in system
            return "1 SPA.B.II.2\n3 SPP.D.7\nrumore"
        assert "2|conto 2" in user and "1|conto 1" not in user
        return "2 CE.B.7"
    esito = L.percorsi_dei_conti(righe, foglie, chiama=chiama)
    assert [f.percorso for f in foglie] == ["SPA.B.II.2", "CE.B.7", "SPP.D.7"]
    assert esito == {"chiamate": 2, "saltate_prima": 1, "senza_percorso": 0}


def test_percorsi_a_blocchi_con_max_tokens_proporzionato():
    righe = [_riga(i, f"c{i}") for i in range(1, 131)]
    visti = []
    def chiama(system, user, max_tokens):
        visti.append(max_tokens)
        return "\n".join(f"{l.split('|')[0]} X" for l in user.splitlines() if "|" in l)
    L.percorsi_dei_conti(righe, righe, chiama=chiama)
    assert len(visti) == 3 and max(visti) <= 40 + 14 * L.BLOCCO


def test_voci_di_legge_converte_importi():
    def chiama_json(system, user, schema, max_tokens):
        assert "2025" in user and "LEGENDA" in system
        return {"corrente": [["SPA.B.I.1", 118720.39]], "precedente": [["SPA.B.I.1", 125571]],
                "totali": {"totale_attivo": 2161054, "totale_passivo": None, "utile": 7422}}
    out = L.voci_di_legge("riga|Costi di impianto|118.720,39", ["31-12-2025", "31-12-2024"], chiama_json=chiama_json)
    assert out["corrente"] == [("SPA.B.I.1", D("118720.39"))]
    assert out["precedente"] == [("SPA.B.I.1", D("125571"))]
    assert out["totali"]["totale_attivo"] == D("2161054")
```

- [ ] **Step 2:** falliscono.
- [ ] **Step 3: implementazione** `importers/import_snello/lettura.py`:

```python
"""Le sole chiamate a Qwen del percorso snello. Risposte corte, mai un elenco di codici da cui scegliere."""
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

from importers import llm_provider
from importers.import_snello.percorsi import LEGENDA

BLOCCO = 60

PROMPT_CONTI = (
    "Righe di un prospetto contabile italiano (bilancio di verifica, situazione contabile o bilancio). "
    "Il codice ha gia' tolto i totali: ogni riga con id e' un saldo che conta, anche se ha un nome generico "
    "(un mastro stampato senza conti sotto e' un conto). "
    "Per OGNI riga con id scrivi il percorso della voce di legge (artt. 2424 e 2425 c.c.): "
    "sezione SPA (attivo), SPP (passivo e netto) o CE, poi lettera, numero romano, numero arabo, lettera minuscola, "
    "separati da punto; aggiungi '.E' o '.O' per crediti/debiti entro/oltre l'esercizio se indicato. "
    "Fondi ammortamento e svalutazione: percorso del bene rettificato con '.F'. "
    "Utile o perdita di esercizi PRECEDENTI, o risultato d'esercizio registrato in un conto di patrimonio netto "
    "(con codice conto): SPP.A.VIII se portato a nuovo, altrimenti SPP.A.IX. "
    "'R' SOLO per la riga finale di quadratura senza codice conto (utile/perdita a pareggio, sbilancio). "
    "'X' SOLO per righe che non sono saldi contabili: prospetti fiscali (variazioni in aumento/diminuzione, "
    "reddito imponibile), conti d'ordine, statistiche, totali generali. "
    "Le righe '#' sono contesto e non si rispondono; '[...]' e' il mastro del conto; (sx)/(dx) la colonna di stampa. "
    "Formato: una riga per id, 'id percorso', nient'altro.\n\nLEGENDA DEI PERCORSI:\n" + LEGENDA)

PROMPT_VOCI = (
    "Prospetto di bilancio italiano secondo lo schema di legge (artt. 2424 e 2425 c.c.), eventualmente abbreviato. "
    "Per ciascuna colonna d'esercizio restituisci le voci STAMPATE come coppie [percorso, importo]: "
    "percorso con la sintassi della legenda, importo come stampato (negativo se tra parentesi o col meno). "
    "Solo le voci piu' di dettaglio stampate: non i totali ('Totale immobilizzazioni', 'Totale crediti', "
    "'Totale attivo'); una voce stampata solo al livello romano (schema abbreviato) si scrive a quel livello "
    "(es. 'SPA.B.I'); crediti o debiti stampati solo come 'esigibili entro/oltre' senza numero arabo: "
    "'SPA.C.II.E', 'SPP.D.O'. Fondi stampati a parte: percorso del bene con '.F'. "
    "Il risultato dell'esercizio va sia come 'SPP.A.IX' nello SP sia come 'CE.21' nel CE. "
    "In 'totali' riporta i totali stampati (totale attivo, totale passivo, utile), null se non stampati."
    "\n\nLEGENDA DEI PERCORSI:\n" + LEGENDA)

_COPPIE = {"type": "array", "items": {"type": "array", "prefixItems": [{"type": "string"}, {"type": "number"}],
                                      "minItems": 2, "maxItems": 2}}
SCHEMA_VOCI = {"type": "object", "properties": {
    "corrente": _COPPIE, "precedente": _COPPIE,
    "totali": {"type": "object", "properties": {k: {"type": ["number", "null"]}
                                                for k in ("totale_attivo", "totale_passivo", "utile")}}},
    "required": ["corrente", "precedente", "totali"]}

SCHEMA_RIGHE = {"type": "object", "properties": {"righe": {"type": "array", "items": {
    "type": "array", "prefixItems": [{"type": "string"}, {"type": ["number", "null"]}, {"type": ["number", "null"]}],
    "minItems": 3, "maxItems": 3}}}, "required": ["righe"]}
PROMPT_TRASCRIVI = ("Trascrivi TUTTE le righe di tabella visibili, in ordine (ignora le righe tagliate a meta' dal bordo). "
                    "Per ogni riga: [etichetta, importo colonna 1, importo colonna 2]. Importi senza separatori, "
                    "negativi se tra parentesi, null se vuoto o '-'.")


def _testo(system, user, max_tokens):
    return llm_provider.chiama_gx10_testo(system, [{"role": "user", "content": user}], max_tokens=max_tokens)


def _json(system, user, schema, max_tokens):
    return llm_provider.chiama_gx10_json(system, [{"role": "user", "content": user}], schema, max_tokens=max_tokens)


def _blocco_testo(righe, blocco):
    ids = {f.id for f in blocco}
    numero = {f.id: n for n, f in enumerate(righe)}
    lo, hi = numero[blocco[0].id], numero[blocco[-1].id]
    contesto = [r for r in righe[max(0, lo - 40):lo] if r.valore is None and r.testo][-5:]
    linee = ["# " + r.testo[:80] for r in contesto]
    for r in righe[lo:hi + 1]:
        if r.id in ids:
            mastro = f" [{r.mastro[:40]}]" if r.mastro else ""
            linee.append(f"{numero[r.id]}|{r.testo[:80]}{mastro} ({'dx' if r.lato == 'R' else 'sx'})")
        elif r.valore is None and r.testo:
            linee.append("# " + r.testo[:80])
    return "\n".join(linee)


def percorsi_dei_conti(righe, foglie, *, chiama=None) -> dict:
    chiama = chiama or _testo
    per_numero = {n: r for n, r in enumerate(righe)}
    esito = {"chiamate": 0, "saltate_prima": 0, "senza_percorso": 0}

    def uno(blocco):
        out = chiama(PROMPT_CONTI, _blocco_testo(righe, blocco), 40 + 14 * len(blocco))
        trovati = {}
        for linea in out.splitlines():
            parti = linea.split()
            if len(parti) == 2 and parti[0].isdigit():
                trovati[int(parti[0])] = parti[1]
        return trovati

    def giro(da_fare):
        blocchi = [da_fare[i:i + BLOCCO] for i in range(0, len(da_fare), BLOCCO)]
        with ThreadPoolExecutor(llm_provider.GX10_CONCORRENZA) as ex:
            for trovati in ex.map(uno, blocchi):
                esito["chiamate"] += 1
                for n, p in trovati.items():
                    if n in per_numero and per_numero[n] in da_fare:
                        per_numero[n].percorso = p

    giro(foglie)
    mancanti = [f for f in foglie if not f.percorso]
    esito["saltate_prima"] = len(mancanti)
    if mancanti:
        giro(mancanti)
    esito["senza_percorso"] = sum(1 for f in foglie if not f.percorso)
    return esito


def voci_di_legge(testo: str, intestazioni: list[str], *, chiama_json=None, nota: str = "") -> dict:
    chiama_json = chiama_json or _json
    colonne = ", ".join(f"'{i}'" for i in intestazioni) or "non indicate"
    user = (f"Colonne d'esercizio, da sinistra: {colonne}. 'corrente' = la prima colonna d'esercizio, "
            f"'precedente' = la seconda (vuoto se non c'e').\n{nota}\n\n{testo}")
    righe = max(1, testo.count("\n") + 1)
    o = chiama_json(PROMPT_VOCI, user, SCHEMA_VOCI, min(6000, 300 + 30 * righe))
    conv = lambda coppie: [(str(p), Decimal(str(v))) for p, v in coppie or [] if v is not None]
    totali = {k: (None if v is None else Decimal(str(v))) for k, v in (o.get("totali") or {}).items()}
    return {"corrente": conv(o.get("corrente")), "precedente": conv(o.get("precedente")), "totali": totali}


def trascrivi_pagine(pdf: str, pagine: list[int], *, chiama_json=None, strisce: int = 3, dpi: int = 120) -> str:
    import fitz
    chiama_json = chiama_json or (lambda system, contenuto, schema, max_tokens: llm_provider.chiama_gx10_json(
        system, [{"role": "user", "content": contenuto}], schema, max_tokens=max_tokens))
    lavori = []
    with fitz.open(pdf) as doc:
        for numero in pagine:
            pagina = doc[numero - 1]
            r = pagina.rect
            alto, basso = r.height * 0.05, r.height * 0.95
            passo = (basso - alto) / strisce
            for k in range(strisce):
                clip = fitz.Rect(0, max(alto, alto + k * passo - 12), r.width, min(basso, alto + (k + 1) * passo + 12))
                png = pagina.get_pixmap(dpi=dpi, clip=clip).tobytes("png")
                lavori.append((numero, k, base64.b64encode(png).decode()))

    def uno(lavoro):
        _, _, b64 = lavoro
        contenuto = [{"type": "text", "text": PROMPT_TRASCRIVI},
                     {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b64}}]
        return chiama_json("", contenuto, SCHEMA_RIGHE, 3000)["righe"]

    with ThreadPoolExecutor(llm_provider.GX10_CONCORRENZA) as ex:
        risultati = list(ex.map(uno, lavori))
    linee, ultima = [], None
    for riga in (r for blocco in risultati for r in blocco):
        if riga == ultima:  # la sovrapposizione fra strisce ripete la riga di bordo
            continue
        ultima = riga
        linee.append(" | ".join("" if x is None else str(x) for x in riga))
    return "\n".join(linee)
```

- [ ] **Step 4:** `pytest tests/test_snello_lettura.py -q` verde.
- [ ] **Step 5: commit** `feat(import): lettura snella su Qwen — percorsi dei conti, voci di legge, trascrizione di pagine immagine`

---

### Task 7: verifica, forma del risultato, tappo

**Files:**
- Modify: `config.py` (CRLF)
- Create: `importers/import_snello/verifica.py`
- Test: `tests/test_snello_verifica.py`

**Interfaces:**
- Consumes: `importers.iv_cee_hierarchy._ATTIVO_FIELDS`, `_PASSIVO_FIELDS`; `calculations.ce_result.calculate_ce_result`.
- Produces:
  - `soglia(totale_attivo: Decimal) -> Decimal`
  - `misura(bs: dict, ce: dict, stampati: dict | None = None) -> dict` — `{"attivo", "passivo", "utile_ce", "sp13", "forma", "scarto_sp", "scarto_ce", "scarto_stampati"}` (Decimal); `forma` = `"bilancio"` o `"verifica"`.
  - `normalizza_forma(bs: dict, ce: dict, m: dict) -> dict` — in forma `"verifica"` sposta `sp13` in `sp12g` e mette l'utile CE in `sp13`; restituisce `bs` nuovo.
  - `tappa(bs: dict, ce: dict, m: dict, s: Decimal) -> tuple[dict, dict, dict | None, str]` — `(bs, ce, tappo, esito)`; `esito` in `"ok"`, `"tappo"`, `"oltre_soglia"`.

- [ ] **Step 1:** in `config.py` (preservando CRLF), accanto a `GX10_MODEL`:

```python
IMPORT_SNELLO_SOGLIA_MIN = _os.environ.get("IMPORT_SNELLO_SOGLIA_MIN", "100")    # euro
IMPORT_SNELLO_SOGLIA_PCT = _os.environ.get("IMPORT_SNELLO_SOGLIA_PCT", "0.1")    # % del totale attivo
```

- [ ] **Step 2: test che falliscono** in `tests/test_snello_verifica.py`:

```python
from decimal import Decimal as D

from importers.import_snello.verifica import misura, normalizza_forma, soglia, tappa


def _bs(**kw):
    base = {"sp03_immob_materiali": D("1000"), "sp09_disponibilita_liquide": D("500"),
            "sp11_capitale": D("800"), "sp13_utile_perdita": D("100"), "sp16_debiti_breve": D("600"),
            "sp16d_debiti_fornitori_breve": D("600")}
    base.update({k: D(v) for k, v in kw.items()})
    return base


CE = {"ce01_ricavi_vendite": D("400"), "ce06_servizi": D("300")}    # utile 100


def test_soglia_relativa_con_minimo():
    assert soglia(D("50000")) == D("100.00")
    assert soglia(D("2000000")) == D("2000.00")


def test_bilancio_che_quadra():
    m = misura(_bs(), CE)
    assert m["forma"] == "bilancio" and m["scarto_sp"] == 0 and m["scarto_ce"] == 0
    bs, ce, tappo, esito = tappa(_bs(), CE, m, D("100"))
    assert esito == "ok" and tappo is None


def test_forma_verifica_sposta_il_risultato_dell_anno_prima():
    bs = _bs(sp13_utile_perdita="-40", sp09_disponibilita_liquide="460")   # nel netto la perdita dell'anno prima; attivo = netto + debiti + utile corrente
    m = misura(bs, CE)
    assert m["forma"] == "verifica" and m["scarto_sp"] == 0
    nuovo = normalizza_forma(bs, CE, m)
    assert nuovo["sp12g_utili_perdite_portati"] == D("-40") and nuovo["sp13_utile_perdita"] == D("100")
    assert nuovo["sp12_riserve"] == D("-40")


def test_tappo_entro_soglia_su_altri_debiti_e_crediti():
    bs = _bs(sp09_disponibilita_liquide="550")                   # attivo in piu' di 50
    bs2, ce2, tappo, esito = tappa(bs, CE, misura(bs, CE), D("100"))
    assert esito == "tappo" and tappo["campo"] == "sp16g_altri_debiti_breve" and tappo["importo"] == "50.00"
    assert bs2["sp16g_altri_debiti_breve"] == D("50.00") and bs2["sp16_debiti_breve"] == D("650.00")
    bs = _bs(sp09_disponibilita_liquide="470")                   # attivo in meno di 30
    bs3, _, tappo, _ = tappa(bs, CE, misura(bs, CE), D("100"))
    assert tappo["campo"] == "sp06g_crediti_altri_breve" and bs3["sp06_crediti_breve"] == D("30.00")


def test_tappo_ce_su_servizi():
    ce = {"ce01_ricavi_vendite": D("400"), "ce06_servizi": D("290")}   # utile CE 110 contro sp13 100
    bs2, ce2, tappo, esito = tappa(_bs(), ce, misura(_bs(), ce), D("100"))
    assert esito == "tappo" and ce2["ce06_servizi"] == D("300.00") and tappo["ce"]["campo"] == "ce06_servizi"


def test_oltre_soglia_non_tocca_nulla():
    bs = _bs(sp09_disponibilita_liquide="900")
    bs2, ce2, tappo, esito = tappa(bs, CE, misura(bs, CE), D("100"))
    assert esito == "oltre_soglia" and tappo is None and bs2 == bs
```

- [ ] **Step 3:** falliscono.
- [ ] **Step 4: implementazione** `importers/import_snello/verifica.py`:

```python
"""Verifica del percorso snello: stesse formule dell'app (campi di quadratura, risultato CE canonico),
soglia relativa, tappo dichiarato entro soglia su altri crediti, altri debiti, servizi (decisione del
proprietario, 2026-09-26). Oltre soglia non si tocca nulla: decide il chiamante."""
from __future__ import annotations

from decimal import Decimal

import config
from calculations.ce_result import calculate_ce_result
from importers.iv_cee_hierarchy import _ATTIVO_FIELDS, _PASSIVO_FIELDS

_C = Decimal("0.01")


def soglia(totale_attivo: Decimal) -> Decimal:
    minimo = Decimal(str(config.IMPORT_SNELLO_SOGLIA_MIN))
    pct = Decimal(str(config.IMPORT_SNELLO_SOGLIA_PCT))
    return max(minimo, abs(Decimal(totale_attivo)) * pct / 100).quantize(_C)


def misura(bs: dict, ce: dict, stampati: dict | None = None) -> dict:
    att = sum((Decimal(bs.get(k, 0)) for k in _ATTIVO_FIELDS), Decimal(0))
    pas = sum((Decimal(bs.get(k, 0)) for k in _PASSIVO_FIELDS), Decimal(0))
    sp13 = Decimal(bs.get("sp13_utile_perdita", 0))
    utile = calculate_ce_result(ce).net_profit
    bilancio = (att - pas, utile - sp13)                     # sp13 e' il risultato corrente
    verifica = (att - pas - utile, Decimal(0))               # sp13 e' l'anno prima (resta nel netto); il corrente e' l'utile CE
    forma, (s_sp, s_ce) = min((("bilancio", bilancio), ("verifica", verifica)),
                              key=lambda x: abs(x[1][0]) + abs(x[1][1]))
    scarto_stampati = Decimal(0)
    for chiave, nostro in (("totale_attivo", att), ("totale_passivo", pas if forma == "bilancio" else pas + utile)):
        v = (stampati or {}).get(chiave)
        if v is not None:
            scarto_stampati = max(scarto_stampati, abs(nostro - Decimal(v)))
    return {"attivo": att, "passivo": pas, "utile_ce": utile, "sp13": sp13, "forma": forma,
            "scarto_sp": s_sp.quantize(_C), "scarto_ce": s_ce.quantize(_C), "scarto_stampati": scarto_stampati.quantize(_C)}


def normalizza_forma(bs: dict, ce: dict, m: dict) -> dict:
    bs = dict(bs)
    if m["forma"] == "verifica":
        precedente = Decimal(bs.get("sp13_utile_perdita", 0))
        bs["sp12g_utili_perdite_portati"] = Decimal(bs.get("sp12g_utili_perdite_portati", 0)) + precedente
        bs["sp12_riserve"] = Decimal(bs.get("sp12_riserve", 0)) + precedente
        bs["sp13_utile_perdita"] = m["utile_ce"].quantize(_C)
    return bs


def _aggiungi(d: dict, campo: str, aggregato: str, v: Decimal) -> None:
    d[campo] = (Decimal(d.get(campo, 0)) + v).quantize(_C)
    d[aggregato] = (Decimal(d.get(aggregato, 0)) + v).quantize(_C)


def tappa(bs: dict, ce: dict, m: dict, s: Decimal):
    if abs(m["scarto_sp"]) > s or abs(m["scarto_ce"]) > s or m["scarto_stampati"] > s:
        return bs, ce, None, "oltre_soglia"
    if m["scarto_sp"] == 0 and m["scarto_ce"] == 0:
        return bs, ce, None, "ok"
    bs, ce, tappo = dict(bs), dict(ce), {"soglia": str(s)}
    if m["scarto_sp"] > 0:        # attivo in piu': manca passivo
        _aggiungi(bs, "sp16g_altri_debiti_breve", "sp16_debiti_breve", m["scarto_sp"])
        tappo.update(campo="sp16g_altri_debiti_breve", importo=str(m["scarto_sp"]))
    elif m["scarto_sp"] < 0:      # manca attivo
        _aggiungi(bs, "sp06g_crediti_altri_breve", "sp06_crediti_breve", -m["scarto_sp"])
        tappo.update(campo="sp06g_crediti_altri_breve", importo=str(-m["scarto_sp"]))
    if m["scarto_ce"] != 0:       # utile CE diverso da sp13: i servizi assorbono la differenza
        ce["ce06_servizi"] = (Decimal(ce.get("ce06_servizi", 0)) + m["scarto_ce"]).quantize(_C)
        tappo["ce"] = {"campo": "ce06_servizi", "importo": str(m["scarto_ce"])}
    return bs, ce, tappo, "tappo"
```

- [ ] **Step 5:** `pytest tests/test_snello_verifica.py -q` verde. Se `calculate_ce_result` restituisce l'utile con un segno o una composizione diversa da `ce01 − ce06` sui dati di test, leggerne il codice (`calculations/ce_result.py`) e riportarlo: non cambiare la formula dell'app.
- [ ] **Step 6: commit** `feat(import): verifica snella con soglia relativa e tappo dichiarato`

---

### Task 8: orchestratore `importa`

**Files:**
- Modify: `importers/import_snello/__init__.py`
- Test: `tests/test_snello_importa.py`

**Interfaces:**
- Consumes: Tasks 2-7.
- Produces:
  - `class SnelloNonRiuscito(Exception)` con attributo `report: dict`.
  - `@dataclass Risultato(bs: dict, ce: dict, prior_bs: dict | None, prior_ce: dict | None, report: dict, struttura)`
  - `importa(file_path: str, *, ocr_text: str | None = None, analizza=None, leggi_conti=None, leggi_voci=None, trascrivi=None) -> Risultato` — i quattro parametri finali servono ai test (default: le funzioni vere).

Algoritmo (da implementare così):
1. `t0`; `struttura = (analizza or analizza_struttura)(file_path)`; eccezione → `SnelloNonRiuscito` con `report={"esito": "ripiego", "fase": "struttura", "errore": <classe>}`.
2. `pagine_sp`, `pagine_ce` dalla struttura; se entrambe vuote → `SnelloNonRiuscito(fase="struttura", errore="nessun prospetto")`.
3. **Modo `conti`:** `righe = righe_da_pdf(file_path, set(pagine_sp) | set(pagine_ce), struttura.colonne_sp or struttura.colonne_ce, ocr_text)`; `fo = foglie(righe)`; `(leggi_conti or percorsi_dei_conti)(righe, fo)`; `bs, ce, diag = da_foglie(fo)`; prior `None`.
4. **Modo `legge`:** per SP e CE separatamente, in parallelo (2 thread): testo = righe di `collect_source_rows` delle pagine della sezione, una per riga `"{id}|{text}"`; se una pagina della sezione è in `struttura.pagine_senza_testo`, quel testo è `(trascrivi or trascrivi_pagine)(file_path, pagine della sezione)`. `(leggi_voci or voci_di_legge)(testo, intestazioni della sezione)`. Unire le coppie di SP e CE per esercizio; `da_coppie` sul corrente e, se ci sono coppie, sul precedente. `stampati` = unione dei `totali` delle due chiamate.
5. Per ogni esercizio: `m = misura(bs, ce, stampati)`; `s = soglia(m["attivo"])`; `bs = normalizza_forma(bs, ce, m)`; `m = misura(bs, ce, stampati)`; `bs, ce, tappo, esito = tappa(bs, ce, m, s)`.
6. Se l'esercizio corrente è `oltre_soglia` e il modo è `legge`: **una** rilettura della sola sezione che non torna (SP se `scarto_sp`/`scarto_stampati` fuori soglia, altrimenti CE), passando a `voci_di_legge` la `nota`: `"Una lettura precedente dava uno scarto di {scarto} euro fra attivo e passivo (o fra risultato CE e SP): controlla voci mancanti, doppie o totali presi come voci."`; poi ripetere i passi 4-5 per quella sezione. Se resta oltre soglia (o il modo è `conti`) → `SnelloNonRiuscito` con `report` completo e `esito="ripiego"`, `fase="verifica"`.
7. Un esercizio precedente oltre soglia non fa fallire: diventa `None` e il report lo dichiara (`precedente: "escluso_oltre_soglia"`).
8. `bs["_plug_residual"] = Decimal(0)`, `bs["_unclassified_mass"] = Decimal(0)` sempre (una chiave diagnostica assente vale «pulito»: la si dichiara, a zero).
9. `report = {"esito": esito ("ok"/"tappo"), "modo", "struttura": struttura.report(), "misura": {esercizio: {k: str(v)}}, "tappo": {esercizio: tappo}, "letture": {...contatori}, "diag": diag, "secondi": round(time.monotonic() - t0, 1)}`.

- [ ] **Step 1: test che falliscono** in `tests/test_snello_importa.py`, con PDF sintetici delle fixture del Task 2 e funzioni finte (nessuna rete):

```python
from decimal import Decimal as D

import pytest

from importers import import_snello as S
from importers.struttura_documento.analisi import Struttura
from tests._struttura_fixtures import pdf_colonna_unica


def _struttura(modo, **kw):
    base = dict(fonte="vision", route=None, pagine_sp=[1], pagine_ce=[1], pagine_dettaglio=[],
                chiamate_vision=1, secondi=0.1, mappe=[], modo=modo,
                colonne_sp=["saldo_corrente", "saldo_precedente"], colonne_ce=["saldo_corrente", "saldo_precedente"],
                intestazioni_sp=["2025", "2024"], intestazioni_ce=["2025", "2024"], pagine_senza_testo=[])
    base.update(kw)
    return Struttura(**base)


def _voci_quadrate(testo, intestazioni, nota=""):
    if "rilettura" in nota:
        raise AssertionError("non serve rileggere")
    return {"corrente": [("SPA.C.IV.1", D("1000")), ("SPP.A.I", D("900")), ("SPP.A.IX", D("100")),
                         ("CE.A.1", D("500")), ("CE.B.7", D("400")), ("CE.21", D("100"))],
            "precedente": [], "totali": {"totale_attivo": D("1000"), "totale_passivo": D("1000"), "utile": D("100")}}


def test_legge_che_quadra(tmp_path):
    pdf = pdf_colonna_unica(str(tmp_path / "c.pdf"))
    r = S.importa(pdf, analizza=lambda p: _struttura("legge"), leggi_voci=_voci_quadrate)
    assert r.bs["sp09_disponibilita_liquide"] == D("1000.00") and r.ce["ce06_servizi"] == D("400.00")
    assert r.report["esito"] == "ok" and r.prior_bs is None
    assert r.bs["_plug_residual"] == 0


def test_legge_oltre_soglia_rilegge_una_volta_poi_ripiega(tmp_path):
    pdf = pdf_colonna_unica(str(tmp_path / "c.pdf"))
    chiamate = []
    def voci(testo, intestazioni, nota=""):
        chiamate.append(nota)
        return {"corrente": [("SPA.C.IV.1", D("5000")), ("SPP.A.I", D("900")), ("CE.A.1", D("500")), ("CE.B.7", D("400"))],
                "precedente": [], "totali": {}}
    with pytest.raises(S.SnelloNonRiuscito) as exc:
        S.importa(pdf, analizza=lambda p: _struttura("legge"), leggi_voci=voci)
    assert exc.value.report["esito"] == "ripiego" and exc.value.report["fase"] == "verifica"
    assert len(chiamate) == 3 and any("scarto" in n for n in chiamate)     # SP, CE, una rilettura


def test_struttura_in_errore_ripiega(tmp_path):
    pdf = pdf_colonna_unica(str(tmp_path / "c.pdf"))
    def rotta(p):
        raise RuntimeError("sonnet giu'")
    with pytest.raises(S.SnelloNonRiuscito) as exc:
        S.importa(pdf, analizza=rotta)
    assert exc.value.report["fase"] == "struttura" and exc.value.report["errore"] == "RuntimeError"
```

- [ ] **Step 2:** falliscono.
- [ ] **Step 3:** implementare `importa` in `importers/import_snello/__init__.py` seguendo l'algoritmo; gli import dei moduli di fase stanno dentro la funzione (import pigri), la docstring del pacchetto resta in testa. Le chiamate SP/CE del modo `legge` passano `nota` come parola chiave solo nella rilettura (quindi la funzione finta dei test la riceve con default `""` nelle prime due chiamate).
- [ ] **Step 4:** `pytest tests/test_snello_importa.py -q` verde, poi tutti `tests/test_snello_*.py`.
- [ ] **Step 5: commit** `feat(import): orchestratore del percorso snello con una sola rilettura e ripiego dichiarato`

---

### Task 9: `pdf_importer` e dettagli — innesto dietro `IMPORT_MOTORE=snello`

**Files:**
- Modify: `importers/pdf_importer.py`, `importers/detail_enrichment.py`
- Test: `tests/test_snello_innesto.py` (nuovo), `tests/test_detail_enrichment.py`

**Interfaces:**
- Consumes: `importa`, `SnelloNonRiuscito`, `Risultato` (Task 8); `Struttura.pagine_dettagli()` (Task 2).
- Produces:
  - `enrich_pdf_details(file_path, current, prior=None, *, fiscal_year=None, ocr_text=None, pagine: set[int] | None = None, usa_llm: bool = True)`: `pagine` non `None` → dopo `collect_source_rows` tiene solo le righe di quelle pagine e scrive `report["pagine"]`; `usa_llm=False` → salta `search_details` (resta la riclassificazione deterministica delle scadenze e i dettagli locali), `report["reason"] = "llm_disattivato"`.
  - `validation_report["import_snello"]` su ogni import PDF quando l'interruttore è acceso (anche in ripiego), per corrente e precedente.
  - `result["extraction_method"] == "import_snello"` quando il percorso è riuscito.

- [ ] **Step 1: leggere** `tests/test_provenienza_llm.py` e `tests/test_coge_provider.py` (impianto: DB in memoria, `import_pdf_balance_sheet`, fixture PDF, sostituzioni con `monkeypatch`) e le righe di `pdf_importer.py` intorno a `is_trial_balance = (classification.route == ROUTE_TRIAL)` (~878), ai due cancelli `if is_trial_balance and not _source_complete:` (~1259) e `if not is_trial_balance and not _source_complete:` (~1522), alla chiamata di `enrich_pdf_details` (~1588), a `_validation_payload = _validation_report_payload(...)` (~1796), a `_prior_validation` (~1978) e alla catena di `result["extraction_method"]` (~2056).
- [ ] **Step 2: test che falliscono** in `tests/test_snello_innesto.py` (sullo stesso impianto), con `importers.import_snello.importa` sostituita da una finta:
  1. interruttore assente → la finta non è chiamata e `validation_report` non ha `import_snello`;
  2. `IMPORT_MOTORE=snello`, finta che restituisce un `Risultato` quadrato → il `BalanceSheet` salvato ha i valori della finta, `extraction_method == "import_snello"`, `validation_report["import_snello"]["esito"] == "ok"`, e né `extract_trial_balance_with_llm` né `extract_pdf_with_llm` né `analyze_pdf_macros` sono chiamate (sostituirle con finte che sollevano);
  3. finta che solleva `SnelloNonRiuscito(report={"esito": "ripiego", "fase": "verifica"})` → l'import prosegue col codice di oggi (lasciare la finta dell'estrattore di oggi restituire un bilancio quadrato) e `validation_report["import_snello"]["esito"] == "ripiego"`;
  4. finta che solleva `RuntimeError` → come il 3, con `validation_report["import_snello"]["errore"] == "RuntimeError"`;
  5. modo `conti` → `enrich_pdf_details` riceve `usa_llm=False`; modo `legge` → `usa_llm=True` e `pagine == struttura.pagine_dettagli()`.
  E in `tests/test_detail_enrichment.py`: con `usa_llm=False` il lettore dei dettagli non viene chiamato e `report["reason"] == "llm_disattivato"`; con `pagine={1}` restano solo righe di pagina 1.
- [ ] **Step 3:** falliscono.
- [ ] **Step 4: implementazione.**
  - `detail_enrichment.enrich_pdf_details`: aggiungere i due parametri; il filtro `pagine` subito dopo `rows = collect_source_rows(...)`; `usa_llm=False` fa prendere il ramo `else` di `if llm_provider.lettore_dettagli_disponibile():` con `report["reason"] = "llm_disattivato"`.
  - `pdf_importer.import_pdf_balance_sheet`, subito dopo `is_trial_balance = (classification.route == ROUTE_TRIAL)`:

```python
        _snello = None
        _snello_report = None
        if os.environ.get("IMPORT_MOTORE") == "snello":
            from importers import import_snello
            try:
                _snello = import_snello.importa(file_path, ocr_text=ocr_text)
                _snello_report = _snello.report
                balance_sheet_data, income_data = _snello.bs, _snello.ce
                prior_bs_data, prior_ce_data = _snello.prior_bs, _snello.prior_ce
            except import_snello.SnelloNonRiuscito as exc:
                _snello_report = exc.report
            except Exception as exc:  # il percorso snello e' un'economia: senza, l'import di oggi
                logger.warning("Import snello non riuscito (%s): importatore attuale", type(exc).__name__)
                _snello_report = {"esito": "ripiego", "fase": "eccezione", "errore": type(exc).__name__}
```

  - i due cancelli diventano `if is_trial_balance and not _source_complete and _snello is None:` e `if not is_trial_balance and not _source_complete and _snello is None:`. Verificare leggendo il codice fra l'innesto e i cancelli (preflight, `_source_complete`, `extract_source_candidates`) che nulla sovrascriva `balance_sheet_data`/`income_data` quando `_snello` non è `None`; se qualcosa lo fa (per esempio `extract_source_candidates`), aggiungere `and _snello is None` anche a quel ramo e annotarlo nel report.
  - alla chiamata di `enrich_pdf_details` aggiungere `pagine=(_snello.struttura.pagine_dettagli() if _snello is not None and _snello.report.get("modo") == "legge" else None)` e `usa_llm=not (_snello is not None and _snello.report.get("modo") == "conti")`.
  - dopo `_validation_payload = _validation_report_payload(...)`: `if _snello_report is not None: _validation_payload["import_snello"] = _snello_report`; lo stesso su `_prior_validation`.
  - nella catena di `extraction_method`, come primo ramo: `if _snello is not None: result["extraction_method"] = "import_snello"`.
  - le variabili `balance_sheet_data`, `income_data`, `prior_bs_data`, `prior_ce_data` devono esistere prima dell'innesto con i nomi che il codice a valle usa: se nel codice attuale nascono dentro i blocchi di route, inizializzarle a `None`/`{}` prima dell'innesto come fa già il codice esistente (leggerlo; non duplicare inizializzazioni).
- [ ] **Step 5:** `pytest tests/test_snello_innesto.py tests/test_detail_enrichment.py tests/test_provenienza_llm.py tests/test_coge_provider.py -q` verde; poi la regressione dei Global Constraints.
- [ ] **Step 6: commit** `feat(import): percorso snello innestato in pdf_importer dietro IMPORT_MOTORE=snello, ripiego sull'importatore attuale`

---

### Task 10: sonda e documentazione

**Files:**
- Modify: `tests/_import_probe.py`, `docs/deployment/PRODUCTION_CONFIG.md` (CRLF), `docs/import/REGOLE-IMPORT-00-INDICE.md`, `docs/import/REGOLE-IMPORT-02-ESTRAZIONE.md`, `docs/import/REGOLE-IMPORT-04-QUADRATURE.md`, `CLAUDE.md`

- [ ] **Step 1:** nella sonda, `rec["import_snello"] = vr.get("import_snello")` (accanto alle altre letture di `validation_report`).
- [ ] **Step 2: documentazione** (italiano, «tu» dove ci si rivolge al lettore):
  - `PRODUCTION_CONFIG.md`: `IMPORT_MOTORE=snello`, `STRUTTURA_MODEL`, `GX10_CONCORRENZA` (4), `GX10_CONTESTO_MAX` (100000), `IMPORT_SNELLO_SOGLIA_MIN` (100), `IMPORT_SNELLO_SOGLIA_PCT` (0.1); le pagine intere vanno ad Anthropic per la struttura.
  - `REGOLE-IMPORT-02-ESTRAZIONE.md`: sezione «Percorso snello»: F1-F3, i due modi, il percorso di legge al posto degli elenchi di codici, la rilettura unica, il ripiego.
  - `REGOLE-IMPORT-04-QUADRATURE.md`: soglia relativa e tappo dichiarato (campi, dove si legge nel report), e che la chiusura al centesimo resta la regola dell'importatore attuale.
  - `REGOLE-IMPORT-00-INDICE.md`: una riga che rimanda alle due sezioni.
  - `CLAUDE.md`, «Invarianti e trappole › Estrazione e classificazione»: aggiungere una voce «**Percorso snello (`IMPORT_MOTORE=snello`)**: il modello nomina il percorso di legge e, sugli schemi di legge, restituisce l'importo; il codice verifica con soglia `max(100 €, 0,1% dell'attivo)` e chiude lo scarto entro soglia con un tappo dichiarato su `sp06g`, `sp16g`, `ce06` (decisione del proprietario, 2026-09-26); oltre soglia una rilettura, poi l'importatore attuale. Il divieto di plug e il contratto "riferimenti, non importi" valgono per l'importatore attuale.» Non cancellare le voci esistenti.
- [ ] **Step 3:** `git diff --stat` (CRLF preservati), regressione verde.
- [ ] **Step 4: commit** `docs(import): percorso snello — configurazione, estrazione, quadrature, CLAUDE.md`

---

### Task 11 (controller): banco

- [ ] Nessun agente pi attivo durante il banco (contesto gx10 condiviso).
- [ ] Elenchi: i 22 file di route C (`/home/peter/DEV/budget-intermedio/.superpowers/sdd/2026-09-22-import-mappa-classificazione/banco/route-c/elenco.txt`), i 26 di route A/B (`.../banco/route-ab/elenco.txt`), i due AMBIENTA di `inbox/import-test/`.
- [ ] Passate con `IMPORT_MOTORE=snello`, `PDF_LLM_PROVIDER_COGE=gx10`, `PDF_LLM_PROVIDER_IVCEE=gx10`, `PDF_LLM_PROVIDER_DETTAGLI=gx10` (per il ripiego), sonda strumentata (`scratchpad/proto/profila.py` della sessione del 2026-09-26, o equivalente) su snapshot del codice; due passate.
- [ ] Misure per file: esito (`ok`/`tappo`/`ripiego`), secondi, chiamate gx10 e token, quadratura finale, tappo, banche valorizzate; confronto con il sistema attuale (profilo del 2026-09-26 e banchi del registro mappa).
- [ ] Criteri della spec §7; registrare esiti e decisione nel ledger (accendere `IMPORT_MOTORE=snello`, tarare, o prossimo passo).

---

## Ordine e parallelismo (agenti pi, al massimo 2 insieme)

| Ondata | Task | Dipende da |
|---|---|---|
| 1 | Task 1 (llm_provider) · Task 3 (percorsi) | — |
| 2 | Task 2 (struttura) · Task 4 (righe) | — |
| 3 | Task 5 (conti) · Task 7 (verifica) | 3, 4 |
| 4 | Task 6 (lettura) | 1, 3, 4 |
| 5 | Task 8 (orchestratore) | 2, 5, 6, 7 |
| 6 | Task 9 (innesto) | 8 |
| 7 | Task 10 (documentazione) | 9 |
| 8 | Task 11 (banco, controllore) | 10 |

Revisione di ogni task: sonnet. Revisione finale del branch: opus. Il Task 9 tocca `pdf_importer.py` (2.100 righe, ramificazioni per route): se l'agente pi resta oltre un'ora senza modificare file, spostarlo su sonnet.

---

**Superato (annotazione del 2026-10-02, giro di riallineamento 2026-10-03).** `GX10_CONCORRENZA`
è stato portato a default **6** dal commit `91624a57` (decisione del proprietario 2026-09-26, «6
richieste parallele»): questo verbale lo dava 4. Stato attuale in
`docs/deployment/PRODUCTION_CONFIG.md` e in `importers/llm_provider.py`.

**Superato (annotazione del 2026-10-03, secondo giro di riallineamento).** Il passo 6 di pagina 1317
(«resta oltre soglia, o modo `conti` → `SnelloNonRiuscito` con esito `ripiego`») è stato smentito
due volte dopo che questo verbale è stato scritto: il Task 17 (2026-09-27) ha deciso che un bilancio
oltre il limite **si importa comunque con avviso** (esito `squadrato`, nessun tappo applicato), e il
Task 28 (`1f3486f`, `bf1e9e5`, 2026-10-03) ha aggiunto che quando un candidato deterministico ha
letto davvero e non quadra solo per il limite del tappo, si salva **quella** lettura e il ripiego non
avviene (`ripiego_evitato`). Stato attuale in `docs/import/REGOLE-IMPORT-02-ESTRAZIONE.md` §F3 e in
`importers/import_snello/__init__.py`.
