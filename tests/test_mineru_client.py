"""Unit tests for the MinerU async client (no Docker required — httpx.MockTransport).

Contract fixtures under tests/fixtures/mineru/ were captured from the live MinerU
3.2.0 container.
"""
import asyncio
import json
import os

import httpx
import pytest

from backend.app.services.mineru_client import (
    MinerUClient,
    MinerUContractError,
    MinerUInvalidOutputError,
    MinerUTimeoutError,
    MinerUUnavailableError,
    _safe_filename,
)

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "mineru")


def _load(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as fh:
        return fh.read()


def _run(coro):
    return asyncio.run(coro)


def _client(handler, **kw):
    transport = httpx.MockTransport(handler)
    return MinerUClient(base_url="http://mineru:8000", transport=transport, **kw)


# --------------------------------------------------------------------------- #
# health
# --------------------------------------------------------------------------- #
def test_health_ok():
    body = _load("health.json")

    def handler(request):
        assert request.url.path == "/health"
        return httpx.Response(200, content=body, headers={"content-type": "application/json"})

    health = _run(_client(handler).health())
    assert health.healthy
    assert health.version == "3.2.0"
    assert health.max_concurrent_requests == 3


def test_health_unhealthy_raises():
    def handler(request):
        return httpx.Response(200, json={"status": "starting"})

    with pytest.raises(MinerUUnavailableError):
        _run(_client(handler).health())


def test_health_connection_refused():
    def handler(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(MinerUUnavailableError):
        _run(_client(handler).health())


def test_health_timeout():
    def handler(request):
        raise httpx.ReadTimeout("slow")

    with pytest.raises(MinerUTimeoutError):
        _run(_client(handler).health())


def test_health_rejects_unpinned_version():
    def handler(request):
        return httpx.Response(200, json={"status": "healthy", "version": "3.3.0"})

    with pytest.raises(MinerUContractError):
        _run(_client(handler, expected_version="3.2.0").health())


# --------------------------------------------------------------------------- #
# parse_pdf
# --------------------------------------------------------------------------- #
def test_parse_ok_real_fixture():
    body = _load("file_parse_response.json")

    def handler(request):
        assert request.url.path == "/file_parse"
        # multipart must carry latin language + pipeline/ocr
        raw = request.content.decode("latin-1")
        assert "latin" in raw
        assert "pipeline" in raw
        return httpx.Response(200, content=body, headers={"content-type": "application/json"})

    result = _run(_client(handler).parse_pdf(content=b"%PDF-1.4 test", filename="sample.pdf"))
    assert result.version == "3.2.0"
    assert result.md_content
    assert result.content_list  # JSON-encoded string
    assert result.status == "completed"


def test_parse_422_invalid_output():
    def handler(request):
        return httpx.Response(422, json={"detail": "bad"})

    with pytest.raises(MinerUInvalidOutputError):
        _run(_client(handler).parse_pdf(content=b"%PDF-1.4", filename="x.pdf"))


def test_parse_500_unavailable():
    def handler(request):
        return httpx.Response(500, json={"detail": "boom"})

    with pytest.raises(MinerUUnavailableError):
        _run(_client(handler).parse_pdf(content=b"%PDF-1.4", filename="x.pdf"))


def test_parse_timeout():
    def handler(request):
        raise httpx.ReadTimeout("slow")

    with pytest.raises(MinerUTimeoutError):
        _run(_client(handler).parse_pdf(content=b"%PDF-1.4", filename="x.pdf"))


def test_parse_unexpected_content_type():
    def handler(request):
        return httpx.Response(200, content=b"<html>nope</html>", headers={"content-type": "text/html"})

    with pytest.raises(MinerUContractError):
        _run(_client(handler).parse_pdf(content=b"%PDF-1.4", filename="x.pdf"))


def test_parse_corrupt_json():
    def handler(request):
        return httpx.Response(200, content=b"{not json", headers={"content-type": "application/json"})

    with pytest.raises(MinerUInvalidOutputError):
        _run(_client(handler).parse_pdf(content=b"%PDF-1.4", filename="x.pdf"))


def test_parse_empty_results():
    def handler(request):
        return httpx.Response(200, json={"version": "3.2.0", "results": {}})

    with pytest.raises(MinerUInvalidOutputError):
        _run(_client(handler).parse_pdf(content=b"%PDF-1.4", filename="x.pdf"))


def test_parse_reported_error():
    def handler(request):
        return httpx.Response(200, json={"version": "3.2.0", "error": "OCR failed", "results": {}})

    with pytest.raises(MinerUInvalidOutputError):
        _run(_client(handler).parse_pdf(content=b"%PDF-1.4", filename="x.pdf"))


def test_parse_oversized_response_capped():
    big = json.dumps({"version": "3.2.0", "results": {"x": {"md_content": "a" * 100}}}).encode()

    def handler(request):
        return httpx.Response(200, content=big, headers={"content-type": "application/json"})

    client = _client(handler, max_response_bytes=10)  # tiny cap
    with pytest.raises(MinerUInvalidOutputError):
        _run(client.parse_pdf(content=b"%PDF-1.4", filename="x.pdf"))


def test_parse_empty_content_rejected():
    def handler(request):
        return httpx.Response(200, json={})

    with pytest.raises(MinerUInvalidOutputError):
        _run(_client(handler).parse_pdf(content=b"", filename="x.pdf"))


def test_safe_filename_keeps_pdf_extension_after_truncation():
    safe = _safe_filename("x" * 300 + ".pdf")
    assert len(safe) == 128
    assert safe.endswith(".pdf")


def test_parse_rejects_response_from_unpinned_version():
    body = _load("file_parse_response.json")

    def handler(request):
        payload = json.loads(body)
        payload["version"] = "3.3.0"
        return httpx.Response(200, json=payload)

    with pytest.raises(MinerUContractError):
        _run(
            _client(handler, expected_version="3.2.0").parse_pdf(
                content=b"%PDF-1.4", filename="x.pdf"
            )
        )


def test_connect_error_retries_once_then_fails():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        raise httpx.ConnectError("refused")

    with pytest.raises(MinerUUnavailableError):
        _run(_client(handler).parse_pdf(content=b"%PDF-1.4", filename="x.pdf"))
    assert calls["n"] == 2  # one retry only
