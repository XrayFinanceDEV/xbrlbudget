# Route C su Qwen locale — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** il pass CoGe della route C (situazioni contabili, sezioni contrapposte, bilanci di verifica) gira su Qwen in locale (gx10) invece che su Claude Haiku, senza cambiare nient'altro dell'importatore a tre route, e se ne misura l'esito sul banco reale contro Haiku.

**Architecture:** un modulo nuovo e piccolo, `importers/llm_provider.py`, fa una chiamata a gx10 (vLLM, OpenAI-compatibile) con output vincolato allo schema JSON del modello Pydantic che l'estrattore usa gia'. `_extract_with_llm` sceglie il fornitore con un parametro; `extract_trial_balance_with_llm` lo sceglie da una variabile d'ambiente, `PDF_LLM_PROVIDER_COGE`, che per default vale `anthropic` — quindi **senza la variabile il comportamento di oggi non cambia di un byte**. Il resto della route C (parser deterministico in parallelo, selettore «vince il candidato piu' vicino al totale stampato», netting, riscatto) resta com'e'. Il banco e' la sonda esistente `tests/_import_probe.py`, eseguita con i due fornitori.

**Tech Stack:** Python 3.12, httpx (gia' dipendenza del backend), Pydantic v2, pytest, PyMuPDF.

**Spec:** nessun documento di spec separato. Le decisioni che il piano applica sono quelle del proprietario del 2026-09-23, riportate qui sotto (§ Decisioni) e registrate per esteso in `/home/peter/DEV/budget-intermedio/.superpowers/sdd/2026-09-22-import-mappa-classificazione/progress.md` (sezione «Cambio di rotta del proprietario»). Chi esegue legge anche quella sezione.

## Decisioni del proprietario che il piano applica

1. «proviamo a riciclare il più possibile da quella impostazione con 3 route diversi per tipo di pdf»: le tre route restano la spina dorsale. Nessun motore parallelo.
2. «usare vision con sonnet 5 per la struttura e qwen per analisi e recupero dettagli»: le chiamate di **testo** vanno su Qwen locale; le chiamate **vision** restano sul cloud (Sonnet, in un piano successivo).
3. «la route è meglio sceglierla dopo la vision»: e' il piano successivo (routing guidato dalla mappa), **non questo**.
4. Il motore mappa del branch `feat/import-mappa-classificazione` resta com'e' («si tiene tutto sul branch e si decide dopo»): questo piano **non** lo tocca e **non** lo importa, tranne due costanti di configurazione (§ Task 1) che vi sono gia' definite.
5. Si parte dalla route C («Route C per prima»): e' la route piu' protetta, perche' il parser deterministico gira sempre in parallelo e vince se Qwen legge peggio.

**Fuori da questo piano, di proposito:** routing dopo la vision; route A/B su Qwen; `read_details`, `read_accounts`, `read_macros` su Qwen; le quattro regole nuove (riga «Sbilancio», segno del CE dal risultato stampato, compensazione dei negativi, natura del debito). Ognuna avra' il suo piano, deciso sui numeri del banco di questo.

## Global Constraints

- Branch: `feat/import-route-c-qwen`, worktree `/home/peter/DEV/budget-route-c` (creato da `main` @ `f4d3483`). Nessuna operazione git in `/home/peter/DEV/budget`.
- `git add` per NOME DI FILE, mai `-A` ne' `.`. Nessun push (il push scatena Jenkins sullo staging).
- `config.py` e `importers/pdf_extractor_llm.py` hanno terminatori **CRLF**: modificarli preservando CRLF; prima di ogni commit `git diff --stat` deve mostrare solo le righe cambiate davvero, non l'intero file.
- gx10 si chiama **sempre** con `Authorization: Bearer <chiave>`; la chiave arriva SOLO dall'ambiente, `GX10_API_KEY`; non compare mai in argv, log, messaggi di eccezione, rapporti o file salvati.
- La porta 18300 di gx10 non si apre mai sul router; si raggiunge via Tailscale (`100.65.63.12`).
- Su gx10: `temperature: 0`, `chat_template_kwargs: {"enable_thinking": false}`.
- Default `PDF_LLM_PROVIDER_COGE = "anthropic"`: con la variabile assente o diversa da `gx10`, nessun comportamento cambia.
- Non modificare `importers/situazione_contabile_parser.py`, `importers/bilancio_classifier.py`, `importers/iv_cee_hierarchy.py`, `data/iv_cee_tree.json`.
- Il corpus `Test/` e `inbox/` e i dati dei clienti non si committano mai. Il database reale `financial_analysis.db` non si tocca: la sonda usa un DB in memoria.
- Nessuna chiamata di rete nei test: gx10 si simula con `httpx.MockTransport`.
- Suite di riferimento: `cd /home/peter/DEV/budget-route-c && backend/venv/bin/python -m pytest tests/test_llm_provider.py tests/test_coge_provider.py tests/test_confronta_probe.py -q` piu' la suite esistente che tocca l'importatore: `backend/venv/bin/python -m pytest tests/ -q -x -k "pdf or import or vision or trial or coge"` (deve restare verde com'e' su `main`).

## Review Focus

1. **Testo della route C piu' lungo del contesto di Qwen** (il pass CoGe manda l'intero documento): gx10 risponde 400 → deve diventare un `LLMProviderError` pulito, e la route C deve proseguire col candidato deterministico, senza troncare il testo in silenzio. Test nel Task 1 (400) e nel Task 3 (l'eccezione esce da `extract_trial_balance_with_llm`).
2. **gx10 irraggiungibile o in timeout** (Tailscale giu', server spento): errore pulito, route C prosegue. Test nel Task 1.
3. **Qwen restituisce un JSON che non rispetta lo schema** (campo mancante o tipo sbagliato nonostante il vincolo): errore pulito, mai un modello parzialmente riempito accettato. Test nel Task 1.
4. **PDF di route C solo immagine con fornitore gx10 e senza chiave Anthropic**: la strada vision non ha un fornitore; deve dare un `PDFImportError` dichiarato, non un'eccezione di tipo o un None. Test nel Task 3.
5. **La chiave gx10 che trapela** in un messaggio di errore, poi scritto nel warning `Route C: CoGe LLM extractor failed (...)` di `pdf_importer.py`. Test nel Task 1 (nessun messaggio d'errore contiene la chiave).

---

### Task 1: `llm_provider.py` — una chiamata a gx10 con output vincolato allo schema Pydantic

**Files:**
- Create: `importers/llm_provider.py`
- Modify: `config.py` (CRLF!) — tre costanti dopo `PDF_LLM_MAX_TOKENS`
- Test: `tests/test_llm_provider.py`

**Interfaces:**
- Produces:
  - `class LLMProviderError(RuntimeError)`
  - `def provider_coge() -> str` — `"gx10"` se `os.environ.get("PDF_LLM_PROVIDER_COGE") == "gx10"`, altrimenti `"anthropic"`. Letta a ogni chiamata (non all'import), cosi' i test e la sonda possono cambiarla.
  - `def gx10_disponibile() -> bool` — vero se `GX10_API_KEY` e' presente e non vuota.
  - `def chiama_gx10_strutturato(system_prompt: str, testo_utente: str, output_model: type[pydantic.BaseModel], *, max_tokens: int, timeout: float = 900.0, transport: httpx.BaseTransport | None = None) -> pydantic.BaseModel`

- [ ] **Step 1: aggiungi le costanti a `config.py`, preservando CRLF**

Dopo la riga `PDF_LLM_MAX_TOKENS = 8192` (sezione «PDF LLM Extraction Settings»), aggiungi — con terminatori `\r\n` come il resto del file:

```python
# gx10: Qwen locale (vLLM, OpenAI-compatibile), raggiunto via Tailscale. La chiave NON sta
# qui: GX10_API_KEY si legge al momento della chiamata (importers/llm_provider.py).
GX10_BASE_URL = _os.environ.get("GX10_BASE_URL", "http://100.65.63.12:18300")
GX10_MODEL = _os.environ.get("GX10_MODEL", "qwen3.8-flash-next")
```

`config.py` su `main` **non importa `os`** (misurato: gli import in testa sono solo `enum` e
`typing`). Aggiungi in testa, accanto agli altri import e sempre con `\r\n`:

```python
import os as _os
```

(L'alias `_os` e' quello che usa gia' il branch `feat/import-mappa-classificazione` per le stesse
due costanti, e non esporta un nome `os` da `config` a chi fa `from config import *`.) Poi:

Run: `git -C /home/peter/DEV/budget-route-c diff --stat config.py`
Expected: `1 file changed, 5 insertions(+)` (non l'intero file).

- [ ] **Step 2: scrivi i test che falliscono**

`tests/test_llm_provider.py`:

```python
"""llm_provider: una chiamata a gx10 con output vincolato allo schema Pydantic.

Nessuna rete: gx10 si simula con httpx.MockTransport.
"""
import json
from decimal import Decimal

import httpx
import pydantic
import pytest

from importers import llm_provider
from importers.llm_provider import LLMProviderError, chiama_gx10_strutturato

CHIAVE = "chiave-di-prova-che-non-deve-mai-trapelare"


class Voce(pydantic.BaseModel):
    sp09_disponibilita_liquide: Decimal | None = None
    totale_attivo: Decimal


def _risposta(status=200, content=None, finish="stop"):
    def handler(request: httpx.Request) -> httpx.Response:
        handler.richiesta = request
        if status != 200:
            return httpx.Response(status, json={"error": {"message": "context length exceeded"}})
        return httpx.Response(200, json={
            "choices": [{"message": {"content": content}, "finish_reason": finish}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        })
    return handler


@pytest.fixture(autouse=True)
def _chiave(monkeypatch):
    monkeypatch.setenv("GX10_API_KEY", CHIAVE)


def test_risposta_valida_diventa_il_modello():
    h = _risposta(content=json.dumps({"sp09_disponibilita_liquide": "1200.50", "totale_attivo": "9000"}))
    out = chiama_gx10_strutturato("sys", "testo", Voce, max_tokens=500, transport=httpx.MockTransport(h))
    assert out == Voce(sp09_disponibilita_liquide=Decimal("1200.50"), totale_attivo=Decimal("9000"))


def test_la_richiesta_porta_bearer_schema_temperatura_zero_e_thinking_spento():
    h = _risposta(content=json.dumps({"totale_attivo": "1"}))
    chiama_gx10_strutturato("SISTEMA", "UTENTE", Voce, max_tokens=500, transport=httpx.MockTransport(h))
    req = h.richiesta
    assert req.headers["Authorization"] == "Bearer " + CHIAVE
    assert req.url.path == "/v1/chat/completions"
    body = json.loads(req.content)
    assert body["temperature"] == 0
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert body["structured_outputs"] == {"json": Voce.model_json_schema()}
    assert body["messages"] == [{"role": "system", "content": "SISTEMA"},
                                {"role": "user", "content": "UTENTE"}]
    assert body["max_tokens"] == 500


def test_senza_chiave_errore_pulito(monkeypatch):
    monkeypatch.delenv("GX10_API_KEY", raising=False)
    with pytest.raises(LLMProviderError, match="GX10_API_KEY"):
        chiama_gx10_strutturato("s", "u", Voce, max_tokens=10,
                                transport=httpx.MockTransport(_risposta(content="{}")))


@pytest.mark.parametrize("status", [400, 401, 500])
def test_status_non_200_errore_pulito_senza_chiave_ne_corpo(status):
    with pytest.raises(LLMProviderError) as exc:
        chiama_gx10_strutturato("s", "u", Voce, max_tokens=10,
                                transport=httpx.MockTransport(_risposta(status=status)))
    assert str(status) in str(exc.value)
    assert CHIAVE not in str(exc.value)
    assert "context length" not in str(exc.value)   # il corpo della risposta non si ripete


def test_gx10_irraggiungibile_errore_pulito():
    def giu(request):
        raise httpx.ConnectError("connessione rifiutata")
    with pytest.raises(LLMProviderError, match="non raggiungibile") as exc:
        chiama_gx10_strutturato("s", "u", Voce, max_tokens=10, transport=httpx.MockTransport(giu))
    assert CHIAVE not in str(exc.value)


def test_risposta_troncata_errore_pulito():
    h = _risposta(content='{"totale_attivo": "1', finish="length")
    with pytest.raises(LLMProviderError, match="troncata"):
        chiama_gx10_strutturato("s", "u", Voce, max_tokens=10, transport=httpx.MockTransport(h))


@pytest.mark.parametrize("content", ["non e' json", json.dumps({"sp09_disponibilita_liquide": "5"})])
def test_json_non_valido_o_fuori_schema_errore_pulito(content):
    with pytest.raises(LLMProviderError, match="non valida"):
        chiama_gx10_strutturato("s", "u", Voce, max_tokens=10,
                                transport=httpx.MockTransport(_risposta(content=content)))


def test_provider_coge_default_anthropic(monkeypatch):
    monkeypatch.delenv("PDF_LLM_PROVIDER_COGE", raising=False)
    assert llm_provider.provider_coge() == "anthropic"
    monkeypatch.setenv("PDF_LLM_PROVIDER_COGE", "qualcos'altro")
    assert llm_provider.provider_coge() == "anthropic"
    monkeypatch.setenv("PDF_LLM_PROVIDER_COGE", "gx10")
    assert llm_provider.provider_coge() == "gx10"


def test_gx10_disponibile(monkeypatch):
    assert llm_provider.gx10_disponibile() is True
    monkeypatch.setenv("GX10_API_KEY", "")
    assert llm_provider.gx10_disponibile() is False
```

- [ ] **Step 3: verifica che falliscano**

Run: `cd /home/peter/DEV/budget-route-c && backend/venv/bin/python -m pytest tests/test_llm_provider.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'importers.llm_provider'`.

- [ ] **Step 4: implementa `importers/llm_provider.py`**

```python
"""Chiamate di testo a Qwen locale (gx10, vLLM OpenAI-compatibile) con output vincolato.

Il contratto e' lo stesso delle chiamate a Haiku dell'importatore: un system prompt, un
testo, un modello Pydantic che la risposta DEVE rispettare. Su vLLM il vincolo si ottiene
con la decodifica guidata (`structured_outputs.json`) invece del tool forzato di Anthropic.
Thinking spento e temperatura 0: l'estrazione non ha bisogno di ragionare.

La chiave arriva solo da GX10_API_KEY, viaggia solo nell'header Bearer, e non compare mai
in un messaggio d'errore: i messaggi di questo modulo finiscono nei warning dell'import.
Anche il corpo di una risposta d'errore non si ripete, per non portare nei log testo del
documento o dettagli del server.
"""
from __future__ import annotations

import json
import os

import httpx
import pydantic

from config import GX10_BASE_URL, GX10_MODEL


class LLMProviderError(RuntimeError):
    pass


def provider_coge() -> str:
    """Il fornitore del pass CoGe di route C. Solo il valore esatto "gx10" lo cambia:
    assente o qualunque altra cosa -> "anthropic", cioe' il comportamento di oggi."""
    return "gx10" if os.environ.get("PDF_LLM_PROVIDER_COGE") == "gx10" else "anthropic"


def gx10_disponibile() -> bool:
    return bool(os.environ.get("GX10_API_KEY"))


def chiama_gx10_strutturato(system_prompt: str, testo_utente: str,
                            output_model: type[pydantic.BaseModel], *, max_tokens: int,
                            timeout: float = 900.0,
                            transport: httpx.BaseTransport | None = None) -> pydantic.BaseModel:
    chiave = os.environ.get("GX10_API_KEY", "")
    if not chiave:
        raise LLMProviderError("GX10_API_KEY non impostata: il fornitore gx10 non e' disponibile")
    body = {
        "model": GX10_MODEL,
        "temperature": 0,
        "max_tokens": max_tokens,
        "chat_template_kwargs": {"enable_thinking": False},
        "structured_outputs": {"json": output_model.model_json_schema()},
        "messages": [{"role": "system", "content": system_prompt},
                     {"role": "user", "content": testo_utente}],
    }
    try:
        with httpx.Client(timeout=timeout, transport=transport) as client:
            r = client.post(f"{GX10_BASE_URL.rstrip('/')}/v1/chat/completions",
                            headers={"Authorization": "Bearer " + chiave}, json=body)
    except httpx.HTTPError as exc:
        raise LLMProviderError(f"gx10 non raggiungibile: {type(exc).__name__}") from None
    if r.status_code != 200:
        raise LLMProviderError(f"gx10 ha risposto {r.status_code}") from None
    scelta = r.json()["choices"][0]
    if scelta.get("finish_reason") == "length":
        raise LLMProviderError("risposta gx10 troncata: max_tokens insufficiente")
    testo = scelta["message"].get("content") or ""
    try:
        return output_model.model_validate(json.loads(testo))
    except (json.JSONDecodeError, pydantic.ValidationError):
        raise LLMProviderError(f"risposta gx10 non valida per {output_model.__name__}") from None
```

- [ ] **Step 5: verifica che passino**

Run: `cd /home/peter/DEV/budget-route-c && backend/venv/bin/python -m pytest tests/test_llm_provider.py -q`
Expected: tutti PASS (13 test).

- [ ] **Step 6: commit**

```bash
cd /home/peter/DEV/budget-route-c
git diff --stat            # config.py: solo le righe aggiunte
git add importers/llm_provider.py config.py tests/test_llm_provider.py
git commit -m "feat(import): chiamata a Qwen locale con output vincolato allo schema Pydantic"
```

---

### Task 2: misura dal vivo — gx10 accetta lo schema, e quanto testo regge (lo fa il CONTROLLORE)

Questo task non ha codice nel repo: lo esegue chi coordina, perche' serve la chiave e la rete.
Serve a sapere **prima** del Task 3 se l'ipotesi del piano regge: che vLLM accetti
`structured_outputs.json` con lo schema, grande, di `BalanceSheetExtraction`, e che il testo intero
di un documento di route C entri nel contesto.

**Files:**
- Create (fuori dal repo, gitignorata): `/home/peter/DEV/budget-intermedio/.superpowers/sdd/2026-09-22-import-mappa-classificazione/banco/route-c/sonda_gx10_coge.py`

- [ ] **Step 1: scrivi la sonda**

```python
"""Sonda dal vivo: il pass CoGe su gx10 con lo schema vero, su un file di route C.
uso: python sonda_gx10_coge.py <file.pdf>   (GX10_API_KEY nell'ambiente)"""
import sys, time
sys.path.insert(0, "/home/peter/DEV/budget-route-c")
from importers import llm_provider
from importers.pdf_extractor_llm import (BalanceSheetExtraction, TRIAL_BALANCE_SP_SYSTEM_PROMPT,
                                         _extract_full_text)
testo = _extract_full_text(sys.argv[1])
print("caratteri del testo:", len(testo))
t0 = time.monotonic()
try:
    out = llm_provider.chiama_gx10_strutturato(TRIAL_BALANCE_SP_SYSTEM_PROMPT, testo,
                                               BalanceSheetExtraction, max_tokens=8192)
    print("OK in %.1f s, totale_attivo=%s" % (time.monotonic() - t0, out.totale_attivo))
except llm_provider.LLMProviderError as e:
    print("ERRORE in %.1f s:" % (time.monotonic() - t0), e)
```

- [ ] **Step 2: eseguila su tre file di route C di taglia diversa**

```bash
( export GX10_API_KEY="$(pi auth print-api-key --provider gx10 2>/dev/null)"; [ -n "$GX10_API_KEY" ] || exit 1
  for f in "/home/peter/DEV/budget/inbox/import-test/Bilancio di verifica al 30.06.2026.pdf" \
           "/home/peter/DEV/budget/inbox/riptova/budget_637_Facchinetti_Dic_25.pdf" \
           "/home/peter/DEV/budget/inbox/riptova/budget_680__bilver-s.pdf"; do
    /home/peter/DEV/budget/backend/venv/bin/python sonda_gx10_coge.py "$f"; done )
```

- [ ] **Step 3: decidi**

- Prima di interpretare: verificare con lo Step 1 del Task 6 che i tre file siano davvero di route C; se uno non lo e', sostituirlo con uno che lo e'.
- Tutti e tre OK → si prosegue col Task 3.
- `gx10 ha risposto 400` su tutti → il vincolo `structured_outputs.json` non e' accettato in quella forma: **fermarsi**, provare a mano `response_format: {"type": "json_schema", ...}`, e rivedere il Task 1 prima di andare avanti.
- 400 solo sul file grande → e' il contesto: si prosegue (la route C ricade sul deterministico, Review Focus 1), ma si registra la soglia in caratteri: sara' il dato su cui decidere se spezzare il testo in un piano successivo.
- Registrare nel registro del lotto: esito, secondi, caratteri, per ciascun file.

---

### Task 3: `extract_trial_balance_with_llm` sceglie il fornitore

**Files:**
- Modify: `importers/pdf_extractor_llm.py` (CRLF!) — `_extract_with_llm` (riga ~2662) e `extract_trial_balance_with_llm` (riga ~3786)
- Test: `tests/test_coge_provider.py`

**Interfaces:**
- Consumes: `llm_provider.provider_coge()`, `llm_provider.chiama_gx10_strutturato(...)`, `LLMProviderError` (Task 1).
- Produces: `_extract_with_llm(client, text, system_prompt, output_model, section_name, tool_name, max_retries=2, provider="anthropic")`; con `provider="gx10"` il parametro `client` e' ignorato e puo' essere `None`.

- [ ] **Step 1: scrivi i test che falliscono**

`tests/test_coge_provider.py`:

```python
"""Il pass CoGe di route C sceglie il fornitore da PDF_LLM_PROVIDER_COGE.

Nessuna rete: la chiamata a gx10 si sostituisce con monkeypatch.
"""
from decimal import Decimal

import fitz
import pytest

from importers import llm_provider, pdf_extractor_llm as P
from importers.llm_provider import LLMProviderError

# ATTENZIONE: PDFImportError e' definita DUE volte, in pdf_extractor_llm.py:29 e in
# pdf_importer.py:51, e sono classi diverse. extract_trial_balance_with_llm solleva quella
# dell'estrattore: e' quella che i test devono aspettarsi.
PDFImportError = P.PDFImportError


def _pdf(tmp_path, righe):
    doc = fitz.open()
    pagina = doc.new_page()
    for i, riga in enumerate(righe):
        pagina.insert_text((40, 60 + 14 * i), riga, fontsize=9)
    percorso = tmp_path / "situazione.pdf"
    doc.save(str(percorso))
    return str(percorso)


RIGHE = ["SITUAZIONE PATRIMONIALE AL 31/12/2025",
         "ATTIVITA'                                   PASSIVITA'",
         "Cassa contanti      1.000,00        Fornitori      1.000,00",
         "TOTALE ATTIVITA'    1.000,00        TOTALE PASSIVITA'  1.000,00"]


def _finto_gx10(chiamate):
    def finto(system_prompt, testo_utente, output_model, *, max_tokens, **_):
        chiamate.append((output_model.__name__, testo_utente))
        if output_model is P.BalanceSheetExtraction:
            return P.BalanceSheetExtraction(sp09_disponibilita_liquide=Decimal("1000"),
                                            sp16d_debiti_fornitori_breve=Decimal("1000"),
                                            totale_attivo=Decimal("1000"),
                                            totale_passivo=Decimal("1000"))
        return P.IncomeStatementExtraction()
    return finto


def test_con_gx10_non_serve_la_chiave_anthropic_e_anthropic_non_si_chiama(tmp_path, monkeypatch):
    monkeypatch.setenv("PDF_LLM_PROVIDER_COGE", "gx10")
    monkeypatch.setenv("GX10_API_KEY", "x")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    chiamate = []
    monkeypatch.setattr(llm_provider, "chiama_gx10_strutturato", _finto_gx10(chiamate))
    monkeypatch.setattr(P.anthropic, "Anthropic",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("Anthropic chiamato")))
    bs, ce = P.extract_trial_balance_with_llm(_pdf(tmp_path, RIGHE))
    assert bs["sp09_disponibilita_liquide"] == Decimal("1000")
    nomi = [c[0] for c in chiamate]
    assert "BalanceSheetExtraction" in nomi and "IncomeStatementExtraction" in nomi
    assert "Cassa contanti" in chiamate[0][1]          # il testo del documento arriva a gx10


def test_default_resta_anthropic_e_senza_chiave_solleva_come_oggi(tmp_path, monkeypatch):
    monkeypatch.delenv("PDF_LLM_PROVIDER_COGE", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(llm_provider, "chiama_gx10_strutturato",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("gx10 chiamato")))
    with pytest.raises(PDFImportError, match="ANTHROPIC_API_KEY"):
        P.extract_trial_balance_with_llm(_pdf(tmp_path, RIGHE))


def test_pdf_immagine_con_gx10_e_senza_chiave_anthropic_errore_dichiarato(tmp_path, monkeypatch):
    monkeypatch.setenv("PDF_LLM_PROVIDER_COGE", "gx10")
    monkeypatch.setenv("GX10_API_KEY", "x")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(P, "_is_image_pdf", lambda *_: True)
    with pytest.raises(PDFImportError, match="vision"):
        P.extract_trial_balance_with_llm(_pdf(tmp_path, RIGHE))


def test_errore_di_gx10_esce_come_eccezione_non_come_foglio_vuoto(tmp_path, monkeypatch):
    monkeypatch.setenv("PDF_LLM_PROVIDER_COGE", "gx10")
    monkeypatch.setenv("GX10_API_KEY", "x")

    def giu(*a, **k):
        raise LLMProviderError("gx10 ha risposto 400")
    monkeypatch.setattr(llm_provider, "chiama_gx10_strutturato", giu)
    with pytest.raises(LLMProviderError):
        P.extract_trial_balance_with_llm(_pdf(tmp_path, RIGHE))


def test_il_retry_di_completezza_tiene_il_draw_col_tappo_piu_piccolo(tmp_path, monkeypatch):
    monkeypatch.setenv("PDF_LLM_PROVIDER_COGE", "gx10")
    monkeypatch.setenv("GX10_API_KEY", "x")
    draw = iter([Decimal("300"), Decimal("5"), Decimal("80")])
    residui = []

    def finto(system_prompt, testo_utente, output_model, *, max_tokens, **_):
        if output_model is P.BalanceSheetExtraction:
            return P.BalanceSheetExtraction(totale_attivo=Decimal("1000"),
                                            totale_passivo=Decimal("1000"))
        return P.IncomeStatementExtraction()
    monkeypatch.setattr(llm_provider, "chiama_gx10_strutturato", finto)
    originale = P._reconcile_trial_to_declared

    def con_residuo(bs, declared, source, **kw):
        bs = dict(bs)
        bs["_plug_residual"] = next(draw)
        residui.append(bs["_plug_residual"])
        return bs
    monkeypatch.setattr(P, "_reconcile_trial_to_declared", con_residuo)
    bs, _ = P.extract_trial_balance_with_llm(_pdf(tmp_path, RIGHE))
    assert bs["_plug_residual"] == min(residui)
```

Nota per l'implementatore: i nomi dei campi di `BalanceSheetExtraction` e `IncomeStatementExtraction` usati qui (`sp09_disponibilita_liquide`, `sp16d_debiti_fornitori_breve`, `totale_attivo`, `totale_passivo`) vanno verificati in `importers/pdf_extractor_llm.py:86-171` PRIMA di eseguire i test; se un nome e' diverso, correggi il test, non il modello. Se `_reconcile_trial_to_declared` ha una firma diversa da `(bs, declared, source, **kw)`, adatta il finto alla firma vera. Se `_COGE_SP_CLEAN_PCT` fa terminare il ciclo prima del terzo draw, il test deve comunque tenere il minimo fra i draw eseguiti — `min(residui)` lo gestisce.

- [ ] **Step 2: verifica che falliscano**

Run: `cd /home/peter/DEV/budget-route-c && backend/venv/bin/python -m pytest tests/test_coge_provider.py -q`
Expected: FAIL (il primo test fallisce su «ANTHROPIC_API_KEY environment variable not set»).

- [ ] **Step 3: `_extract_with_llm` accetta il fornitore**

In `importers/pdf_extractor_llm.py` (CRLF!), aggiungi il parametro e il ramo gx10 in testa al corpo, lasciando intatto il ramo Anthropic:

```python
def _extract_with_llm(
    client: anthropic.Anthropic,
    text: str,
    system_prompt: str,
    output_model: type[pydantic.BaseModel],
    section_name: str,
    tool_name: str,
    max_retries: int = 2,
    provider: str = "anthropic",
) -> pydantic.BaseModel:
    """Call Claude Haiku with tool-use for structured extraction.

    provider="gx10": stessa estrazione su Qwen locale (importers/llm_provider.py), con lo
    schema del modello come vincolo di decodifica; `client` e' ignorato. Il messaggio utente
    e' lo stesso del ramo Anthropic, meno il riferimento al tool, che su vLLM non esiste.
    """
    if provider == "gx10":
        from importers import llm_provider
        logger.info(f"Calling gx10 for {section_name} extraction ({len(text)} chars)...")
        return llm_provider.chiama_gx10_strutturato(
            system_prompt,
            f"Extract the {section_name} values from this Italian balance sheet text.\n\n{text}",
            output_model, max_tokens=PDF_LLM_MAX_TOKENS)
    logger.info(f"Calling Claude Haiku for {section_name} extraction ({len(text)} chars)...")
    # ... resto invariato
```

- [ ] **Step 4: `extract_trial_balance_with_llm` sceglie il fornitore**

Sostituisci il blocco iniziale che legge la chiave e crea il client:

```python
    from importers import llm_provider
    provider = llm_provider.provider_coge()
    client = None
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if provider == "anthropic":
        if not api_key:
            raise PDFImportError("ANTHROPIC_API_KEY environment variable not set")
        try:
            client = anthropic.Anthropic(api_key=api_key)
        except Exception as e:
            raise PDFImportError(f"Failed to initialize Anthropic client: {e}")
```

Subito dopo il calcolo di `is_image` (nel ramo non-OCR), aggiungi:

```python
        if is_image and provider == "gx10":
            # La vision non ha un fornitore locale: resta sul cloud (decisione del
            # proprietario, 2026-09-23). Senza chiave Anthropic si dichiara, e la route C
            # prosegue col candidato deterministico.
            if not api_key:
                raise PDFImportError("PDF solo immagine: il pass CoGe richiede la vision, "
                                     "che non ha un fornitore locale (ANTHROPIC_API_KEY assente)")
            client = anthropic.Anthropic(api_key=api_key)
```

Nelle due chiamate a `_extract_with_llm` dentro `_extract_ce` e `_extract_sp_once`, passa `provider=provider` (le chiamate a `_extract_with_llm_vision` restano come sono, con `client`).

- [ ] **Step 5: verifica che passino, e che nulla d'altro si muova**

Run: `cd /home/peter/DEV/budget-route-c && backend/venv/bin/python -m pytest tests/test_coge_provider.py tests/test_llm_provider.py -q`
Expected: tutti PASS.

Run: `backend/venv/bin/python -m pytest tests/ -q -x -k "pdf or import or vision or trial or coge"`
Expected: verde come su `main` (stesso numero di test passati; annota il numero nel rapporto).

- [ ] **Step 6: commit**

```bash
cd /home/peter/DEV/budget-route-c
git diff --stat importers/pdf_extractor_llm.py     # solo le righe cambiate, CRLF preservato
git add importers/pdf_extractor_llm.py tests/test_coge_provider.py
git commit -m "feat(import): il pass CoGe di route C sceglie il fornitore, Qwen locale o Haiku"
```

---

### Task 4: la route C fa partire il pass CoGe anche senza chiave Anthropic, e dichiara il fornitore

**Files:**
- Modify: `importers/pdf_importer.py` (LF) — il blocco `if api_key and not local_coordinate_ocr:` (riga ~1263) e il punto dove si compone `validation_report` per la route C
- Test: `tests/test_coge_provider.py` (aggiunte)

**Interfaces:**
- Consumes: `llm_provider.provider_coge()`, `llm_provider.gx10_disponibile()` (Task 1).
- Produces: `pdf_importer._coge_attivo(api_key: str) -> bool`; chiave `validation_report["coge_provider"]` (`"anthropic"` o `"gx10"`) su ogni import di route C.

- [ ] **Step 1: scrivi i test che falliscono** (in coda a `tests/test_coge_provider.py`)

```python
from importers import pdf_importer


def test_coge_attivo_anthropic_segue_la_chiave(monkeypatch):
    monkeypatch.delenv("PDF_LLM_PROVIDER_COGE", raising=False)
    assert pdf_importer._coge_attivo("sk-qualcosa") is True
    assert pdf_importer._coge_attivo("") is False


def test_coge_attivo_gx10_segue_la_chiave_gx10_non_quella_anthropic(monkeypatch):
    monkeypatch.setenv("PDF_LLM_PROVIDER_COGE", "gx10")
    monkeypatch.setenv("GX10_API_KEY", "x")
    assert pdf_importer._coge_attivo("") is True
    monkeypatch.setenv("GX10_API_KEY", "")
    assert pdf_importer._coge_attivo("sk-qualcosa") is False
```

- [ ] **Step 2: verifica che falliscano**

Run: `backend/venv/bin/python -m pytest tests/test_coge_provider.py -q -k coge_attivo`
Expected: FAIL, `AttributeError: ... has no attribute '_coge_attivo'`.

- [ ] **Step 3: implementa**

Funzione a livello di modulo in `importers/pdf_importer.py`, vicino agli altri helper privati:

```python
def _coge_attivo(api_key: str) -> bool:
    """Il pass CoGe di route C puo' girare? Con il fornitore di default (Haiku) serve la
    chiave Anthropic, come sempre; con gx10 serve la chiave gx10, e la chiave Anthropic
    non conta (la route C deve poter girare interamente in locale)."""
    from importers.llm_provider import gx10_disponibile, provider_coge
    if provider_coge() == "gx10":
        return gx10_disponibile()
    return bool(api_key)
```

Nel blocco della route C sostituisci `if api_key and not local_coordinate_ocr:` con
`if _coge_attivo(api_key) and not local_coordinate_ocr:`. Lascia invariato il `try/except` che lo
segue: e' lui che fa ricadere la route C sul candidato deterministico quando il pass CoGe fallisce
(Review Focus 1 e 2), e il suo messaggio di warning non puo' contenere la chiave perche' i messaggi
di `LLMProviderError` non la contengono (Task 1).

Poi cerca dove si compone `validation_report` nel ramo della route C (`grep -n "validation_report\[" importers/pdf_importer.py`) e aggiungi, sul percorso che produce il risultato di route C:

```python
validation_report["coge_provider"] = provider_coge()
```

(con `from importers.llm_provider import provider_coge` locale). Se il dizionario si compone in piu' punti, mettila dove si imposta `extraction_method` per la route C (`pdf_importer.py:~2015`), che e' l'unico punto attraversato da ogni import di route C.

- [ ] **Step 4: verifica**

Run: `backend/venv/bin/python -m pytest tests/test_coge_provider.py tests/test_llm_provider.py -q`
Expected: tutti PASS.

Run: `backend/venv/bin/python -m pytest tests/ -q -x -k "pdf or import or vision or trial or coge"`
Expected: verde come su `main`.

- [ ] **Step 5: commit**

```bash
cd /home/peter/DEV/budget-route-c
git add importers/pdf_importer.py tests/test_coge_provider.py
git commit -m "feat(import): la route C fa girare il pass CoGe su Qwen anche senza chiave Anthropic"
```

---

### Task 5: la sonda registra il fornitore, e un confronto fra due esecuzioni

**Files:**
- Modify: `tests/_import_probe.py` — una chiave nel record
- Create: `scripts/confronta_probe.py`
- Test: `tests/test_confronta_probe.py`

**Interfaces:**
- Consumes: il JSONL di `tests/_import_probe.py --json` (un record per file, chiavi `file`, `route`, `extraction_method`, `totale_attivo`, `totale_passivo`, `sbilancio`, `utile_ce`, `quadra`, `plug_residual`, `fields`).
- Produces: `scripts/confronta_probe.py A.jsonl B.jsonl` → tabella per file; funzione `confronta(a: list[dict], b: list[dict]) -> list[dict]`.

- [ ] **Step 1: la sonda registra il fornitore**

In `tests/_import_probe.py`, dove si costruisce `rec` (accanto a `rec["route"] = ...`), aggiungi:

```python
        rec["coge_provider"] = (res.get("validation_report") or {}).get("coge_provider")
```

Verifica prima con `grep -n "validation_report" tests/_import_probe.py` come la sonda legge il report (se lo chiama `vr`, usa quello).

- [ ] **Step 2: test del confronto, che fallisce**

`tests/test_confronta_probe.py`:

```python
from scripts.confronta_probe import confronta


def _rec(file, metodo, attivo, sbil, utile, campi):
    return {"file": file, "extraction_method": metodo, "totale_attivo": attivo,
            "sbilancio": sbil, "utile_ce": utile, "quadra": sbil == "0.00", "fields": campi}


def test_confronto_per_file_con_campi_diversi():
    a = [_rec("x.pdf", "situazione_contabile_llm", "1000.00", "0.00", "50.00",
              {"sp09_disponibilita_liquide": "400", "sp16a_debiti_banche_breve": "600"})]
    b = [_rec("x.pdf", "situazione_contabile", "1000.00", "0.00", "50.00",
              {"sp09_disponibilita_liquide": "400", "sp16g_altri_debiti_breve": "600"})]
    righe = confronta(a, b)
    assert len(righe) == 1
    r = righe[0]
    assert r["file"] == "x.pdf"
    assert r["metodo"] == ("situazione_contabile_llm", "situazione_contabile")
    assert r["stesso_attivo"] is True
    assert r["campi_diversi"] == ["sp16a_debiti_banche_breve", "sp16g_altri_debiti_breve"]


def test_file_presente_in_una_sola_esecuzione():
    righe = confronta([_rec("x.pdf", "m", "1", "0.00", "0", {})], [])
    assert righe[0]["file"] == "x.pdf" and righe[0]["solo_in"] == "A"
```

Run: `backend/venv/bin/python -m pytest tests/test_confronta_probe.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'scripts.confronta_probe'` (se `scripts/` non e' un pacchetto importabile dai test, verifica come gli altri test importano da `scripts/` — `grep -rn "from scripts" tests/ | head -3` — e segui lo stesso modo).

- [ ] **Step 3: implementa `scripts/confronta_probe.py`**

```python
"""Confronta due esecuzioni di tests/_import_probe.py (per esempio Haiku contro Qwen).

uso: python scripts/confronta_probe.py A.jsonl B.jsonl
Per ogni file: il candidato vincente di route C, attivo, sbilancio, utile, e i campi che
cambiano. I campi sono il vero oggetto del confronto: la quadratura non vede uno
spostamento fra due campi dello stesso lato.
"""
from __future__ import annotations

import json
import sys


def _carica(percorso: str) -> list[dict]:
    with open(percorso, encoding="utf-8") as fh:
        return [json.loads(riga) for riga in fh if riga.strip()]


def confronta(a: list[dict], b: list[dict]) -> list[dict]:
    per_a = {r["file"]: r for r in a}
    per_b = {r["file"]: r for r in b}
    out = []
    for f in sorted(set(per_a) | set(per_b)):
        ra, rb = per_a.get(f), per_b.get(f)
        if ra is None or rb is None:
            out.append({"file": f, "solo_in": "A" if rb is None else "B"})
            continue
        ca, cb = ra.get("fields") or {}, rb.get("fields") or {}
        out.append({
            "file": f,
            "metodo": (ra.get("extraction_method"), rb.get("extraction_method")),
            "attivo": (ra.get("totale_attivo"), rb.get("totale_attivo")),
            "stesso_attivo": ra.get("totale_attivo") == rb.get("totale_attivo"),
            "sbilancio": (ra.get("sbilancio"), rb.get("sbilancio")),
            "utile": (ra.get("utile_ce"), rb.get("utile_ce")),
            "campi_diversi": sorted(k for k in set(ca) | set(cb) if ca.get(k) != cb.get(k)),
        })
    return out


def main(argv: list[str]) -> None:
    for r in confronta(_carica(argv[1]), _carica(argv[2])):
        if "solo_in" in r:
            print(f"{r['file']}: presente solo in {r['solo_in']}")
            continue
        print(f"== {r['file']}")
        print(f"   metodo   {r['metodo'][0]}  |  {r['metodo'][1]}")
        print(f"   attivo   {r['attivo'][0]}  |  {r['attivo'][1]}")
        print(f"   sbilancio {r['sbilancio'][0]}  |  {r['sbilancio'][1]}")
        print(f"   utile    {r['utile'][0]}  |  {r['utile'][1]}")
        print(f"   campi diversi ({len(r['campi_diversi'])}): {', '.join(r['campi_diversi'][:15])}")


if __name__ == "__main__":
    main(sys.argv)
```

- [ ] **Step 4: verifica**

Run: `backend/venv/bin/python -m pytest tests/test_confronta_probe.py -q`
Expected: PASS.

- [ ] **Step 5: commit**

```bash
cd /home/peter/DEV/budget-route-c
git add tests/_import_probe.py scripts/confronta_probe.py tests/test_confronta_probe.py
git commit -m "test(import): la sonda registra il fornitore del pass CoGe, e il confronto fra due esecuzioni"
```

---

### Task 6: il banco — route C su Qwen contro Haiku (lo fa il CONTROLLORE)

**Files:** nessuno nel repo. Output nella cartella di lavoro del lotto (gitignorata).

- [ ] **Step 1: elenca i file di route C**

```bash
OUT=/home/peter/DEV/budget-intermedio/.superpowers/sdd/2026-09-22-import-mappa-classificazione/banco/route-c   # gitignorata: verificato con git check-ignore
mkdir -p $OUT
cd /home/peter/DEV/budget-route-c && /home/peter/DEV/budget/backend/venv/bin/python - <<'PY'
import glob, os
from importers.bilancio_classifier import classify_bilancio, ROUTE_TRIAL
cand = glob.glob("/home/peter/DEV/budget/inbox/**/*.pdf", recursive=True) + \
       glob.glob("/home/peter/DEV/budget/Test/**/*.pdf", recursive=True)
for f in sorted(cand):
    try:
        if classify_bilancio(f).route == ROUTE_TRIAL:
            print(f)
    except Exception as e:
        pass
PY
```

Salvare la scelta, un percorso per riga, in `$OUT/elenco.txt`. Scegliere da quella lista: tutti quelli di `inbox/import-test` e `inbox/riptova`, piu' una dozzina dal corpus `Test/` di layout diversi (DEPI, AGO, contrapposte, bilanci di verifica, TeamSystem).

- [ ] **Step 2: due esecuzioni su Qwen, una su Haiku**

```bash
( export GX10_API_KEY="$(pi auth print-api-key --provider gx10 2>/dev/null)"; [ -n "$GX10_API_KEY" ] || exit 1
  export PDF_LLM_PROVIDER_COGE=gx10
  for n in 1 2; do while IFS= read -r f; do
    backend/venv/bin/python tests/_import_probe.py "$f" --json $OUT/qwen_$n.jsonl; done < $OUT/elenco.txt; done )
# Haiku (default): una sola esecuzione, sugli stessi file
while IFS= read -r f; do backend/venv/bin/python tests/_import_probe.py "$f" --json $OUT/haiku.jsonl; done < $OUT/elenco.txt
```

(La sonda carica `ANTHROPIC_API_KEY` da `backend/.env` come il backend. Con `PDF_LLM_PROVIDER_COGE=gx10`, il pass CoGe non chiama Haiku; le altre chiamate della route C — `read_details`, riscatto vision — restano su Anthropic in questo piano, ed e' atteso.)

- [ ] **Step 3: confronta**

```bash
backend/venv/bin/python scripts/confronta_probe.py $OUT/qwen_1.jsonl $OUT/qwen_2.jsonl   # quanto varia Qwen da solo
backend/venv/bin/python scripts/confronta_probe.py $OUT/haiku.jsonl  $OUT/qwen_1.jsonl   # Qwen contro Haiku
```

- [ ] **Step 4: decidi e registra**

Per ciascun file, nel registro del lotto: route, candidato vincente con Haiku e con Qwen, quadra si'/no, sbilancio, e campi diversi. Tre letture:

- **quante volte vince il candidato CoGe** con Qwen rispetto a Haiku (se Qwen perde sempre col deterministico, il pass CoGe su Qwen non aggiunge nulla, ma non toglie: la route C resta col deterministico);
- **campi che cambiano fra le due esecuzioni di Qwen** a parita' di commit: e' il rumore, e non va attribuito a Qwen-contro-Haiku (lezione registrata il 2026-09-23: un confronto campo per campo fra due singole esecuzioni di un LLM non e' un segnale di regressione);
- **nessun file deve peggiorare di route o di quadratura** rispetto a Haiku senza che sia spiegato.

Sui numeri si decide il piano successivo (route A/B, oppure `read_details`/`read_accounts`, oppure il routing dopo la vision).
