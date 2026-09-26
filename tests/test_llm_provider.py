"""llm_provider: una chiamata a gx10 con output vincolato allo schema Pydantic.

Nessuna rete: gx10 si simula con httpx.MockTransport.
"""
import json
import threading
import time
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


def test_provider_ivcee_e_dettagli_default_anthropic(monkeypatch):
    monkeypatch.delenv("PDF_LLM_PROVIDER_IVCEE", raising=False)
    monkeypatch.delenv("PDF_LLM_PROVIDER_DETTAGLI", raising=False)
    assert llm_provider.provider_ivcee() == "anthropic"
    assert llm_provider.provider_dettagli() == "anthropic"
    monkeypatch.setenv("PDF_LLM_PROVIDER_IVCEE", "gx10")
    monkeypatch.setenv("PDF_LLM_PROVIDER_DETTAGLI", "GX10")
    assert llm_provider.provider_ivcee() == "gx10"
    assert llm_provider.provider_dettagli() == "anthropic"


def test_lettore_dettagli_disponibile(monkeypatch):
    monkeypatch.delenv("PDF_LLM_PROVIDER_DETTAGLI", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    assert llm_provider.lettore_dettagli_disponibile() is True
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert llm_provider.lettore_dettagli_disponibile() is False
    monkeypatch.setenv("PDF_LLM_PROVIDER_DETTAGLI", "gx10")
    assert llm_provider.lettore_dettagli_disponibile() is True  # GX10_API_KEY from the autouse fixture
    monkeypatch.setenv("GX10_API_KEY", "")
    assert llm_provider.lettore_dettagli_disponibile() is False


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
