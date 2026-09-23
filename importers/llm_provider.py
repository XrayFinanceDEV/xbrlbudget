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


class RispostaTroncata(LLMProviderError):
    pass


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


def chiama_gx10_json(system_prompt: str, messaggi: list[dict], schema: dict, *,
                     max_tokens: int, timeout: float = 900.0,
                     transport: httpx.BaseTransport | None = None) -> dict:
    chiave = os.environ.get("GX10_API_KEY", "")
    if not chiave:
        raise LLMProviderError("GX10_API_KEY non impostata: il fornitore gx10 non e' disponibile")
    body = {
        "model": GX10_MODEL,
        "temperature": 0,
        "max_tokens": max_tokens,
        "chat_template_kwargs": {"enable_thinking": False},
        "structured_outputs": {"json": schema},
        "messages": [{"role": "system", "content": system_prompt}, *messaggi],
    }
    try:
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
        testo = scelta["message"].get("content") or ""
    except RispostaTroncata:
        raise
    except (ValueError, KeyError, IndexError, TypeError):
        raise LLMProviderError("risposta gx10 non valida: formato inatteso") from None
    try:
        return json.loads(testo)
    except json.JSONDecodeError:
        raise LLMProviderError("risposta gx10 non valida: JSON non decodificabile") from None


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
