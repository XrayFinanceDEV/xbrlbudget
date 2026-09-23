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


def _risposta_corpo_200(corpo):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=corpo)
    return handler


def _risposta_non_json_200():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"questo non e' json")
    return handler


@pytest.mark.parametrize("corpo", [{}, {"choices": []}, {"choices": [{}]}])
def test_200_con_corpo_malformato_errore_pulito(corpo):
    with pytest.raises(LLMProviderError, match="formato inatteso") as exc:
        chiama_gx10_strutturato("s", "u", Voce, max_tokens=10,
                                transport=httpx.MockTransport(_risposta_corpo_200(corpo)))
    assert CHIAVE not in str(exc.value)


def test_200_con_corpo_non_json_errore_pulito():
    with pytest.raises(LLMProviderError, match="formato inatteso") as exc:
        chiama_gx10_strutturato("s", "u", Voce, max_tokens=10,
                                transport=httpx.MockTransport(_risposta_non_json_200()))
    assert CHIAVE not in str(exc.value)


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
