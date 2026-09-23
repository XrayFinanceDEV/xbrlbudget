# Route A/B e seconda lettura su Qwen — piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** le chiamate LLM **di testo** di route A/B (estrattore IV-CEE, lettura delle macro-voci) e della seconda lettura dei dettagli (celle della nota integrativa, classificazione dei sottoconti) possono girare su Qwen locale (gx10), a scelta per variabile d'ambiente, con Haiku come default invariato.

**Architecture:** si estende `importers/llm_provider.py` (branch `feat/import-route-c-qwen`, dove route C è già su Qwen) con una chiamata a schema JSON libero e con conversazione a più turni, perché tre dei quattro punti usano schemi con `enum` calcolati a runtime e un turno di riparazione. Ogni punto di chiamata sceglie il fornitore con una funzione del modulo; la vision resta su Anthropic (Qwen qui è solo testo).

**Tech Stack:** Python 3, httpx, Pydantic v2, vLLM OpenAI-compatibile (`structured_outputs.json`), pytest.

**Spec:** nessuna spec separata. Decisioni del proprietario (2026-09-23): «vision con sonnet per la struttura e qwen per analisi e recupero dettagli»; «facciamo switch qwen anche su route A e B». Piano precedente, stesso branch: `docs/superpowers/plans/2026-09-23-route-c-su-qwen.md`.

## Global Constraints

- gx10 si chiama sempre con `Authorization: Bearer <GX10_API_KEY>`; la chiave viene SOLO da env `GX10_API_KEY`, mai in argv, log, eccezioni, report persistiti.
- Qwen: `temperature: 0`, `chat_template_kwargs: {"enable_thinking": False}`, output vincolato con `structured_outputs: {"json": <schema>}`.
- Default invariato: senza variabili il comportamento è identico a main (Haiku). Solo il valore esatto `"gx10"` cambia fornitore.
- Variabili: `PDF_LLM_PROVIDER_IVCEE` (estrattore A/B testuale + macro-voci), `PDF_LLM_PROVIDER_DETTAGLI` (seconda lettura: `read_details`, `read_accounts`). `PDF_LLM_PROVIDER_COGE` esiste già e non si tocca.
- La vision (`_extract_with_llm_vision`, `vision_rescue`, `ocr_pdf_sample_text`) resta su Anthropic.
- Ogni chiamata LLM resta dietro gli stessi controlli di oggi: l'LLM non fornisce importi dove oggi non li fornisce; i riduttori (`reduce_macros`, `apply_details`, `reduce_accounts`) non cambiano.
- File CRLF (`config.py`, `importers/pdf_extractor_llm.py`, verificare gli altri con `file`): preservare CRLF, `git diff --stat` prima di ogni commit.
- `git add` per nome file, mai `-A` o `.`. Nessun push.
- Corpora `Test/`, `inbox/` e dati clienti mai committati. DB reale mai scritto.

## Review Focus

1. Uno schema con `enum` calcolato a runtime (id di riga, campi ammessi) deve arrivare a vLLM **quello calcolato**, non lo schema statico del modello Pydantic: altrimenti Qwen può citare righe inesistenti.
2. Il turno di riparazione (`read_details`, `read_accounts`) oggi usa blocchi `tool_use`/`tool_result` Anthropic: su gx10 va tradotto in un messaggio `assistant` col JSON e un `user` con gli errori, senza perdere le risposte già accettate.
3. Una risposta troncata deve produrre lo stesso errore dichiarato di oggi (`macro_response_truncated`, `output_truncated`, `ledger_output_truncated`), non un'eccezione generica.
4. I cancelli «serve la chiave Anthropic» (`read_macros`, `enrich_pdf_details`, `extract_ledger_source`) devono guardare la chiave del fornitore scelto: con gx10 senza `ANTHROPIC_API_KEY` la seconda lettura non deve dichiararsi «unavailable».
5. `search_details` ha un budget di 240 s con 2 thread: con gx10 le chiamate sono più lente; il budget non si tocca nel codice, ma il banco lo misura.

---

### Task 1: `llm_provider` — chiamata a schema libero, multi-turno, troncatura tipizzata

**Files:**
- Modify: `importers/llm_provider.py`
- Test: `tests/test_llm_provider.py`

**Interfaces:**
- Produces:
  - `class RispostaTroncata(LLMProviderError)`
  - `provider_ivcee() -> str` ("gx10" solo se `PDF_LLM_PROVIDER_IVCEE == "gx10"`, altrimenti "anthropic")
  - `provider_dettagli() -> str` (idem con `PDF_LLM_PROVIDER_DETTAGLI`)
  - `chiama_gx10_json(system_prompt: str, messaggi: list[dict], schema: dict, *, max_tokens: int, timeout: float = 900.0, transport: httpx.BaseTransport | None = None) -> dict` — `messaggi` è una lista di `{"role": "user"|"assistant", "content": str}`; restituisce il JSON della risposta già decodificato (dict), senza validarlo.
  - `chiama_gx10_strutturato(...)` resta con la stessa firma e diventa un involucro di `chiama_gx10_json` (schema = `output_model.model_json_schema()`, un solo messaggio user, poi `model_validate`).

- [ ] **Step 1: test che falliscono** — aggiungere a `tests/test_llm_provider.py` (usa lo stesso stile di trasporto finto già presente nel file, `httpx.MockTransport`):

```python
def test_provider_ivcee_e_dettagli_default_anthropic(monkeypatch):
    monkeypatch.delenv("PDF_LLM_PROVIDER_IVCEE", raising=False)
    monkeypatch.delenv("PDF_LLM_PROVIDER_DETTAGLI", raising=False)
    assert llm_provider.provider_ivcee() == "anthropic"
    assert llm_provider.provider_dettagli() == "anthropic"
    monkeypatch.setenv("PDF_LLM_PROVIDER_IVCEE", "gx10")
    monkeypatch.setenv("PDF_LLM_PROVIDER_DETTAGLI", "GX10")
    assert llm_provider.provider_ivcee() == "gx10"
    assert llm_provider.provider_dettagli() == "anthropic"


def test_chiama_gx10_json_manda_schema_e_messaggi_come_dati(monkeypatch):
    monkeypatch.setenv("GX10_API_KEY", "k-segreta")
    visto = {}
    def handler(request):
        visto["body"] = json.loads(request.content)
        visto["auth"] = request.headers["authorization"]
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop",
            "message": {"content": '{"a": 1}'}}]})
    schema = {"type": "object", "properties": {"a": {"enum": [1, 2]}}}
    out = llm_provider.chiama_gx10_json(
        "sys", [{"role": "user", "content": "u1"}, {"role": "assistant", "content": "{}"},
                {"role": "user", "content": "u2"}],
        schema, max_tokens=100, transport=httpx.MockTransport(handler))
    assert out == {"a": 1}
    assert visto["auth"] == "Bearer k-segreta"
    assert visto["body"]["structured_outputs"] == {"json": schema}
    assert [m["role"] for m in visto["body"]["messages"]] == ["system", "user", "assistant", "user"]
    assert visto["body"]["temperature"] == 0
    assert visto["body"]["chat_template_kwargs"] == {"enable_thinking": False}


def test_chiama_gx10_json_troncata_e_risposta_non_json(monkeypatch):
    monkeypatch.setenv("GX10_API_KEY", "k-segreta")
    def tronca(request):
        return httpx.Response(200, json={"choices": [{"finish_reason": "length",
            "message": {"content": '{"a": '}}]})
    with pytest.raises(llm_provider.RispostaTroncata):
        llm_provider.chiama_gx10_json("s", [{"role": "user", "content": "u"}], {},
                                      max_tokens=5, transport=httpx.MockTransport(tronca))
    def rotta(request):
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop",
            "message": {"content": "non json"}}]})
    with pytest.raises(llm_provider.LLMProviderError) as exc:
        llm_provider.chiama_gx10_json("s", [{"role": "user", "content": "u"}], {},
                                      max_tokens=5, transport=httpx.MockTransport(rotta))
    assert "k-segreta" not in str(exc.value)
```

Adattare gli import in testa al file se mancano (`json`, `httpx`, `pytest`, `from importers import llm_provider`). I test esistenti di `chiama_gx10_strutturato` devono restare verdi senza modifiche, compreso il messaggio «troncata».

- [ ] **Step 2:** `pytest tests/test_llm_provider.py -q` → i tre nuovi falliscono (attributo mancante).

- [ ] **Step 3: implementazione** in `importers/llm_provider.py`:

```python
class RispostaTroncata(LLMProviderError):
    pass


def _provider_da_env(nome: str) -> str:
    return "gx10" if os.environ.get(nome) == "gx10" else "anthropic"


def provider_ivcee() -> str:
    """Estrattore testuale di route A/B e lettura delle macro-voci."""
    return _provider_da_env("PDF_LLM_PROVIDER_IVCEE")


def provider_dettagli() -> str:
    """Seconda lettura: celle di dettaglio (nota integrativa) e classificazione dei sottoconti."""
    return _provider_da_env("PDF_LLM_PROVIDER_DETTAGLI")


def chiama_gx10_json(system_prompt: str, messaggi: list[dict], schema: dict, *,
                     max_tokens: int, timeout: float = 900.0,
                     transport: httpx.BaseTransport | None = None) -> dict:
    # corpo della richiesta, errori di rete/status/formato: IDENTICI a quelli di oggi in
    # chiama_gx10_strutturato; la sola differenza e' che i messaggi arrivano dal chiamante
    # e lo schema e' un dict. finish_reason == "length" -> RispostaTroncata(
    #     "risposta gx10 troncata: max_tokens insufficiente").
    # Contenuto non JSON -> LLMProviderError("risposta gx10 non valida: JSON non decodificabile").
    ...
```

Riscrivere `chiama_gx10_strutturato` sopra `chiama_gx10_json` (un solo messaggio user con `testo_utente`, poi `output_model.model_validate(dati)`; `pydantic.ValidationError` → lo stesso messaggio di oggi `risposta gx10 non valida per {Model}`). Spostare il corpo di rete in `chiama_gx10_json`, senza duplicarlo. `provider_coge` può usare `_provider_da_env("PDF_LLM_PROVIDER_COGE")`.

- [ ] **Step 4:** `pytest tests/test_llm_provider.py tests/test_coge_provider.py -q` → tutto verde.
- [ ] **Step 5: commit** `feat(import): llm_provider con schema libero, piu' turni e troncatura tipizzata`

---

### Task 2: estrattore testuale di route A/B su `provider_ivcee`

**Files:**
- Modify: `importers/pdf_extractor_llm.py` (CRLF) — `extract_pdf_with_llm` (~3422) e `extract_pdf_both_years_with_llm` (~4902)
- Test: `tests/test_ivcee_provider.py` (nuovo)

**Interfaces:**
- Consumes: `llm_provider.provider_ivcee()`, `_extract_with_llm(..., provider=...)` (esiste già, ramo gx10 già scritto e usato da route C).

- [ ] **Step 1: test che falliscono** in `tests/test_ivcee_provider.py`: con `monkeypatch` su `pdf_extractor_llm._is_image_pdf` → `False`, `extract_relevant_pages` → `("SP testo", "CE testo")` (per both-years: la funzione che usa per il testo, leggerla nel codice) e `_extract_with_llm` sostituita da una finta che registra `provider` e restituisce un modello vuoto valido (`BalanceSheetExtraction()` / `IncomeStatementExtraction()` o i modelli both-years, a seconda del `output_model` ricevuto); asserire:
  - con `PDF_LLM_PROVIDER_IVCEE` assente → entrambe le chiamate ricevono `provider="anthropic"`;
  - con `PDF_LLM_PROVIDER_IVCEE=gx10` → entrambe ricevono `provider="gx10"`;
  - con `_is_image_pdf` → `True` e `gx10`: la vision resta su Anthropic (la finta di `_extract_with_llm_vision` viene chiamata, `_extract_with_llm` no).
  Stesse tre asserzioni per `extract_pdf_both_years_with_llm`. Se i passi dopo l'estrazione richiedono campi non vuoti per non sollevare, restituire dalla finta i modelli con i valori minimi che servono e annotarlo nel test.
- [ ] **Step 2:** i test falliscono (provider sempre "anthropic").
- [ ] **Step 3:** nelle due funzioni, nel solo ramo testuale: `provider = llm_provider.provider_ivcee()` e passarlo a entrambe le `_extract_with_llm(...)`. Il client Anthropic si crea comunque (serve alla vision); nessun altro cambiamento. Aggiungere `except llm_provider.LLMProviderError as e: raise PDFImportError(f"Errore gx10 durante l'estrazione SP: {e}")` (e CE) accanto agli `except anthropic.APIError` esistenti — la classe `PDFImportError` è quella del modulo (`pdf_extractor_llm.py:29`).
- [ ] **Step 4:** `pytest tests/test_ivcee_provider.py tests/test_coge_provider.py -q` verde; poi `pytest tests -q -k "pdf or import or vision or trial or coge or ivcee" -p no:cacheprovider` — atteso: stessi esiti di prima più i nuovi (il fallimento preesistente `test_vision_rescue.py::test_build_ce_non_manda_un_ricavo_sconosciuto_su_una_voce_di_costo` resta).
- [ ] **Step 5: commit** `feat(import): estrattore IV-CEE testuale di route A/B su Qwen con PDF_LLM_PROVIDER_IVCEE`

---

### Task 3: lettura delle macro-voci (`read_macros`) su `provider_ivcee`

**Files:**
- Modify: `importers/macro_analysis.py` (`read_macros`, ~120)
- Test: `tests/test_macro_analysis.py`

**Interfaces:**
- Consumes: `llm_provider.provider_ivcee()`, `chiama_gx10_json`, `RispostaTroncata`, `gx10_disponibile()`.

- [ ] **Step 1: test che falliscono** in `tests/test_macro_analysis.py`: con `PDF_LLM_PROVIDER_IVCEE=gx10`, `GX10_API_KEY` impostata, `ANTHROPIC_API_KEY` assente, e `llm_provider.chiama_gx10_json` sostituita da una finta:
  - la finta riceve uno `schema` il cui `$defs.MacroCell.properties.row.enum` è l'elenco degli id delle righe con importi passate (lo schema calcolato, non quello statico) e un solo messaggio user uguale al testo che oggi va ad Anthropic;
  - restituendo un dict valido per `MacroReading` (es. `{"facts": [], "absent": [], "unresolved": []}` — verificare i nomi reali dei campi di `MacroReading`), `read_macros` restituisce un `MacroReading`;
  - se la finta solleva `RispostaTroncata`, `read_macros` solleva `RuntimeError('macro_response_truncated')`;
  - senza `GX10_API_KEY` solleva `RuntimeError('api_key_unavailable')`.
  Un test che senza la variabile il ramo Anthropic è ancora quello chiamato (sostituire `anthropic.Anthropic` con una finta minima che registra la chiamata, oppure asserire che `chiama_gx10_json` NON viene chiamata e che senza `ANTHROPIC_API_KEY` si solleva `api_key_unavailable` come oggi).
- [ ] **Step 2:** falliscono.
- [ ] **Step 3:** in `read_macros`, dopo aver calcolato `schema` e il testo utente (estrarre il testo in una variabile locale, usata da entrambi i rami):

```python
    if llm_provider.provider_ivcee() == "gx10":
        if not llm_provider.gx10_disponibile():
            raise RuntimeError('api_key_unavailable')
        try:
            dati = llm_provider.chiama_gx10_json(PROMPT, [{"role": "user", "content": testo}],
                                                 schema, max_tokens=12000)
        except llm_provider.RispostaTroncata:
            raise RuntimeError('macro_response_truncated') from None
        return MacroReading.model_validate(dati)
```

Il controllo `ANTHROPIC_API_KEY` resta, ma solo nel ramo Anthropic. Nessun altro cambiamento.
- [ ] **Step 4:** `pytest tests/test_macro_analysis.py tests/test_llm_provider.py -q` verde.
- [ ] **Step 5: commit** `feat(import): lettura delle macro-voci su Qwen con PDF_LLM_PROVIDER_IVCEE`

---

### Task 4: seconda lettura (`read_details`, `read_accounts`) su `provider_dettagli`

**Files:**
- Modify: `importers/detail_enrichment.py` (`read_details` ~293, cancello ~824), `importers/ledger_evidence.py` (`read_accounts` ~188, cancello ~411)
- Test: `tests/test_detail_enrichment.py`, `tests/test_ledger_evidence.py`

**Interfaces:**
- Consumes: `llm_provider.provider_dettagli()`, `chiama_gx10_json`, `RispostaTroncata`, `gx10_disponibile()`.
- Produces: `llm_provider.lettore_dettagli_disponibile() -> bool` — `gx10_disponibile()` se `provider_dettagli() == "gx10"`, altrimenti `bool(os.environ.get("ANTHROPIC_API_KEY"))`. Aggiungerla a `importers/llm_provider.py` con il suo test in `tests/test_llm_provider.py`.

- [ ] **Step 1: test che falliscono.**
  - `read_details` con gx10 e `chiama_gx10_json` finta: (a) lo schema ricevuto ha `$defs.DetailCell.properties.row.enum` = id delle righe con importi; (b) prima risposta con un id inesistente → seconda chiamata con messaggi `[user, assistant(JSON della prima risposta), user(testo che contiene «Correggi i riferimenti» e l'errore)]`; la seconda risposta valida viene restituita; (c) `RispostaTroncata` → `DetailReadError('output_truncated')`.
  - `read_accounts` con gx10: stesso schema calcolato (`$defs.AccountAssignment.properties.row.enum`), le assegnazioni valide della prima risposta restano accettate e la riparazione chiede solo le mancanti (il ciclo esistente lo fa già: il test lo fissa sul ramo gx10); `RispostaTroncata` → `DetailReadError('ledger_output_truncated')`.
  - `enrich_pdf_details` con `PDF_LLM_PROVIDER_DETTAGLI=gx10`, `GX10_API_KEY` impostata e `ANTHROPIC_API_KEY` assente chiama `search_details` (non si ferma a `local_only`); `extract_ledger_source` nella stessa condizione non restituisce `ledger_semantic_reader_unavailable`.
- [ ] **Step 2:** falliscono.
- [ ] **Step 3:** implementazione.
  - `read_details`: nel ciclo dei due tentativi, sul ramo gx10 si mantiene una lista `conversazione` di messaggi testuali: il primo user è il testo di oggi; la risposta si ottiene con `chiama_gx10_json(_PROMPT, conversazione, schema, max_tokens=16384)`; al posto di `block.input` si usa il dict restituito; per la riparazione si accodano `{"role": "assistant", "content": json.dumps(dati, ensure_ascii=False)}` e `{"role": "user", "content": <stesso testo di correzione di oggi>}`. La validazione e il controllo delle proposte restano il codice di oggi, condiviso fra i due rami (estrarre il blocco che oggi valida `block.input` in una funzione locale che prende il dict, per non duplicarlo).
  - `read_accounts`: stessa tecnica dentro `read(batch)`: ogni tentativo manda un solo messaggio user (oggi il messaggio è ricostruito a ogni tentativo con `repair`/`feedback`, quindi non serve storia); sul ramo gx10 `raw = dati.get('accounts', [])`.
  - Cancelli: `enrich_pdf_details` (`if os.environ.get("ANTHROPIC_API_KEY"):`) e `extract_ledger_source` (`not os.environ.get('ANTHROPIC_API_KEY')`) usano `llm_provider.lettore_dettagli_disponibile()`.
- [ ] **Step 4:** `pytest tests/test_detail_enrichment.py tests/test_detail_search.py tests/test_ledger_evidence.py tests/test_source_detail_reconcile.py tests/test_llm_provider.py -q` verde.
- [ ] **Step 5: commit** `feat(import): seconda lettura dei dettagli su Qwen con PDF_LLM_PROVIDER_DETTAGLI`

---

### Task 5: provenienza persistita, sonda, documentazione

**Files:**
- Modify: `importers/pdf_importer.py` (payload, accanto a `coge_provider` ~1804 e ~1973), `tests/_import_probe.py`, `scripts/confronta_probe.py`, `docs/deployment/PRODUCTION_CONFIG.md` (CRLF), `docs/import/REGOLE-IMPORT-02-ESTRAZIONE.md`
- Test: `tests/test_coge_provider.py` (o nuovo `tests/test_provenienza_llm.py`), `tests/test_confronta_probe.py`

- [ ] **Step 1: test che falliscono:** il `validation_report` persistito di un import (usare lo stesso impianto del test che oggi fissa `coge_provider` nel payload) contiene `ivcee_provider` e `dettagli_provider` su **ogni** route (non solo C), con i valori delle due funzioni; `confronta` riporta anche le due chiavi nella tupla `provider`.
- [ ] **Step 2:** falliscono.
- [ ] **Step 3:** scrivere nel payload `ivcee_provider = provider_ivcee()` e `dettagli_provider = provider_dettagli()` fuori dal ramo `if is_trial_balance:`, nello stesso punto prima della serializzazione, e lo stesso su `_prior_validation`. Nella sonda: `rec["ivcee_provider"]`, `rec["dettagli_provider"]` come già `coge_provider`. In `confronta`: `"provider": ((ra.get("coge_provider"), ra.get("ivcee_provider"), ra.get("dettagli_provider")), (…di rb))`. Documentazione: le due variabili nuove nella sezione già scritta per `PDF_LLM_PROVIDER_COGE` in `PRODUCTION_CONFIG.md`, e in `REGOLE-IMPORT-02-ESTRAZIONE.md` una riga per variabile su che cosa sposta e che la vision resta su Anthropic.
- [ ] **Step 4:** test verdi + regressione `-k "pdf or import or vision or trial or coge or ivcee or detail or ledger or macro"`.
- [ ] **Step 5: commit** `feat(import): provenienza del fornitore LLM di route A/B e dei dettagli nel report`

---

### Task 6 (controller): sonda dal vivo e banco A/B

- [ ] Sonda dal vivo su 2 file di route A e 1 di route B (testo nativo) con `PDF_LLM_PROVIDER_IVCEE=gx10 PDF_LLM_PROVIDER_DETTAGLI=gx10`: la chiamata a schema con `enum` e `$defs` è accettata da vLLM, tempi per chiamata.
- [ ] Banco: elenco dei file di route A/B del corpus (classificazione con `classify_bilancio`, esclusi i PDF immagine e i report dell'app in `inbox/artifacts`), un run Haiku e due run Qwen in sequenza, con il cronometro per file nella sonda. Confronto: quadratura, totale attivo, campi diversi, e — obiettivo del proprietario — per ogni file se `sp16a`/`sp17a` (banche) e `sp16d` (fornitori) escono valorizzati o la massa resta in `sp16g`/`sp17g`.
- [ ] Registrare nel ledger esiti e decisione.
