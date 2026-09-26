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
import threading

import httpx
import pydantic

from config import GX10_BASE_URL, GX10_MODEL


class LLMProviderError(RuntimeError):
    pass


class RispostaTroncata(LLMProviderError):
    pass


GX10_CONCORRENZA = int(os.environ.get("GX10_CONCORRENZA", "4"))
GX10_CONTESTO_MAX = int(os.environ.get("GX10_CONTESTO_MAX", "100000"))
# gx10 ha 500k token di contesto condivisi: 4 richieste sotto 100k non rallentano il prefill.
_SEMAFORO = threading.BoundedSemaphore(GX10_CONCORRENZA)


class ContestoEccessivo(LLMProviderError):
    pass


def stima_token(messaggi: list[dict], system_prompt: str = "") -> int:
    """Stima grezza dei token di una richiesta: caratteri/3 del testo, piu' 1.500 per ogni
    immagine (le immagini gx10 costano molto piu' di poche righe di testo)."""
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


def _provider_da_env(nome: str) -> str:
    return "gx10" if os.environ.get(nome) == "gx10" else "anthropic"


def provider_coge() -> str:
    """Il fornitore del pass CoGe di route C. Solo il valore esatto "gx10" lo cambia:
    assente o qualunque altra cosa -> "anthropic", cioe' il comportamento di oggi."""
    return _provider_da_env("PDF_LLM_PROVIDER_COGE")


def provider_ivcee() -> str:
    """Estrattore testuale di route A/B e lettura delle macro-voci."""
    return _provider_da_env("PDF_LLM_PROVIDER_IVCEE")


def provider_dettagli() -> str:
    """Seconda lettura: celle di dettaglio (nota integrativa) e classificazione dei sottoconti."""
    return _provider_da_env("PDF_LLM_PROVIDER_DETTAGLI")


def gx10_disponibile() -> bool:
    return bool(os.environ.get("GX10_API_KEY"))


def lettore_dettagli_disponibile() -> bool:
    """Le credenziali del fornitore scelto per read_details/read_accounts sono pronte."""
    if provider_dettagli() == "gx10":
        return gx10_disponibile()
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _invia(system_prompt: str, messaggi: list[dict], *, max_tokens: int, timeout: float,
          transport: httpx.BaseTransport | None, schema: dict | None = None) -> str:
    """Chiamata comune a gx10: chiave, tetto di contesto, semaforo di concorrenza, corpo
    della richiesta (con o senza vincolo di schema) e gestione degli errori. Restituisce il
    testo grezzo del messaggio di risposta; chi chiama decide se e come interpretarlo."""
    chiave = os.environ.get("GX10_API_KEY", "")
    if not chiave:
        raise LLMProviderError("GX10_API_KEY non impostata: il fornitore gx10 non e' disponibile")
    if stima_token(messaggi, system_prompt) + max_tokens > GX10_CONTESTO_MAX:
        raise ContestoEccessivo("richiesta gx10 oltre il tetto di contesto")
    body = {
        "model": GX10_MODEL,
        "temperature": 0,
        "max_tokens": max_tokens,
        "chat_template_kwargs": {"enable_thinking": False},
        "messages": [{"role": "system", "content": system_prompt}, *messaggi],
    }
    if schema is not None:
        body["structured_outputs"] = {"json": schema}
    try:
        with _SEMAFORO:
            with httpx.Client(timeout=timeout, transport=transport) as client:
                r = client.post(f"{GX10_BASE_URL.rstrip('/')}/v1/chat/completions",
                                headers={"Authorization": "Bearer " + chiave}, json=body)
    except httpx.HTTPError as exc:
        raise LLMProviderError(f"gx10 non raggiungibile: {type(exc).__name__}") from None
    if r.status_code != 200:
        raise LLMProviderError(f"gx10 ha risposto {r.status_code}") from None
    try:
        scelta = r.json()["choices"][0]
        if scelta.get("finish_reason") == "length":
            raise RispostaTroncata("risposta gx10 troncata: max_tokens insufficiente")
        return scelta["message"].get("content") or ""
    except RispostaTroncata:
        raise
    except (ValueError, KeyError, IndexError, TypeError):
        raise LLMProviderError("risposta gx10 non valida: formato inatteso") from None


def chiama_gx10_json(system_prompt: str, messaggi: list[dict], schema: dict, *,
                     max_tokens: int, timeout: float = 900.0,
                     transport: httpx.BaseTransport | None = None) -> dict:
    testo = _invia(system_prompt, messaggi, max_tokens=max_tokens, timeout=timeout,
                   transport=transport, schema=schema)
    try:
        return json.loads(testo)
    except json.JSONDecodeError:
        raise LLMProviderError("risposta gx10 non valida: JSON non decodificabile") from None


def chiama_gx10_testo(system_prompt: str, messaggi: list[dict], *, max_tokens: int,
                      timeout: float = 600.0,
                      transport: httpx.BaseTransport | None = None) -> str:
    """Come chiama_gx10_json ma senza vincolo di schema: restituisce il testo libero della
    risposta (es. le due righe "riga -> codice" del ripiego di route C)."""
    return _invia(system_prompt, messaggi, max_tokens=max_tokens, timeout=timeout,
                  transport=transport, schema=None)


def chiama_gx10_strutturato(system_prompt: str, testo_utente: str,
                            output_model: type[pydantic.BaseModel], *, max_tokens: int,
                            timeout: float = 900.0,
                            transport: httpx.BaseTransport | None = None) -> pydantic.BaseModel:
    dati = chiama_gx10_json(system_prompt, [{"role": "user", "content": testo_utente}],
                            output_model.model_json_schema(), max_tokens=max_tokens,
                            timeout=timeout, transport=transport)
    try:
        return output_model.model_validate(dati)
    except pydantic.ValidationError:
        raise LLMProviderError(f"risposta gx10 non valida per {output_model.__name__}") from None
