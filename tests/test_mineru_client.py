"""Unit tests for the MinerU async client (no network — httpx.MockTransport).

The v4 fixtures under tests/fixtures/mineru/ (``v4_*.json``) follow the shape of the live
MinerU 4.0.12 on gx10, captured 2026-10-26 on a real scan; the amounts are synthetic.
``v4_openapi.json`` is the server's own contract.
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
    versione_compatibile,
)

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "mineru")


def _load(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as fh:
        return fh.read()


def _run(coro):
    return asyncio.run(coro)


def _client(handler, **kw):
    transport = httpx.MockTransport(handler)
    kw.setdefault("poll_interval_seconds", 0)
    return MinerUClient(base_url="http://mineru:8000", transport=transport, **kw)


def _json(status, payload):
    body = payload if isinstance(payload, (bytes, str)) else json.dumps(payload)
    return httpx.Response(status, content=body, headers={"content-type": "application/json"})


# --------------------------------------------------------------------------- #
# health
# --------------------------------------------------------------------------- #
def test_health_ok():
    def handler(request):
        assert request.url.path == "/v1/health"
        return _json(200, _load("v4_health.json"))

    health = _run(_client(handler, expected_version="4").health())
    assert health.healthy
    assert health.version == "4.0.12"


def test_health_unhealthy_raises():
    def handler(request):
        return _json(200, {"status": "starting", "version": "4.0.12"})

    with pytest.raises(MinerUUnavailableError):
        _run(_client(handler).health())


def test_health_503_unavailable():
    def handler(request):
        return _json(503, {"error": "busy"})

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


def test_health_rejects_another_major_version():
    def handler(request):
        return _json(200, {"status": "ok", "version": "5.0.0"})

    with pytest.raises(MinerUContractError):
        _run(_client(handler, expected_version="4").health())


def test_version_pin_fixes_only_the_components_it_writes():
    assert versione_compatibile("4", "4.0.12")
    assert versione_compatibile("4", "4.1.0")
    assert not versione_compatibile("4", "3.4.5")
    assert not versione_compatibile("4", "40.0.0")
    assert versione_compatibile("4.0.12", "4.0.12")
    assert not versione_compatibile("4.0.12", "4.0.13")
    assert versione_compatibile(None, "4.0.12") and versione_compatibile("4", None)


# --------------------------------------------------------------------------- #
# parse_pdf
# --------------------------------------------------------------------------- #
def test_parse_ok_sends_the_v4_request_and_rebuilds_the_blocks():
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        seen["params"] = request.url.params
        seen["body"] = request.content.decode("latin-1")
        return _json(200, _load("v4_file_parse_response.json"))

    result = _run(_client(handler, expected_version="4").parse_pdf(
        content=b"%PDF-1.4 test", filename="sample.pdf"))

    assert seen["path"] == "/v1/file_parse"
    assert seen["params"]["tier"] == "advanced"
    assert seen["params"]["ocr_mode"] == "ocr"
    assert seen["params"].get_list("output_formats") == ["markdown", "middle_json"]
    assert seen["params"]["wait_timeout"] == "50"  # sotto il timeout del proxy di gx10
    assert 'name="files"; filename="sample.pdf"' in seen["body"]

    assert result.version == "4.0.12"
    assert result.status == "completed"
    assert result.md_content.startswith("## Bilancio di verifica")
    tables = [b for b in result.content_list if b["type"] == "table"]
    assert [(t["page_idx"], t["table_caption"]) for t in tables] == [
        (0, ["STATO PATRIMONIALE"]), (1, ["CONTO ECONOMICO"])]
    assert tables[0]["table_body"].startswith("<table>")
    assert tables[1]["table_footnote"] == ["Importi in euro"]
    title = next(b for b in result.content_list if b.get("text") == "Bilancio di verifica")
    assert title["type"] == "text" and title["text_level"] == 1
    header = next(b for b in result.content_list if b["type"] == "header")
    assert header["text"] == "Esempio Srl" and header["page_idx"] == 0


def test_parse_result_feeds_the_adapter_unchanged():
    """Il client rende i blocchi nella forma che l'adapter legge da sempre: pagine,
    tabelle con didascalia e righe arrivano senza toccare importers/mineru_adapter."""
    from importers.mineru_adapter import build_extraction_context

    def handler(request):
        return _json(200, _load("v4_file_parse_response.json"))

    raw = _run(_client(handler).parse_pdf(content=b"%PDF-1.4", filename="sample.pdf"))
    ctx = build_extraction_context(raw)
    assert ctx.page_count == 2
    assert [(t.page, t.caption) for t in ctx.tables] == [
        (0, "STATO PATRIMONIALE"), (1, "CONTO ECONOMICO")]
    assert any("IMMOBILIZZAZIONI MATERIALI" in c.text for r in ctx.rows for c in r.cells)
    assert ctx.mineru_version == "4.0.12"
    assert "Bilancio di verifica" in ctx.headings


def test_parse_202_polls_the_task_until_the_result():
    calls = []
    queued = {"task_id": "job_abc123", "status": "queued"}

    def handler(request):
        calls.append((request.method, request.url.path))
        if request.method == "POST":
            return _json(202, queued)
        if len(calls) < 4:
            return _json(202, {**queued, "status": "running"})
        return _json(200, _load("v4_file_parse_response.json"))

    result = _run(_client(handler).parse_pdf(content=b"%PDF-1.4", filename="sample.pdf"))
    assert result.status == "completed"
    assert calls == [("POST", "/v1/file_parse")] + [("GET", "/v1/tasks/job_abc123/result")] * 3


def test_parse_202_past_the_deadline_times_out():
    def handler(request):
        return _json(202, {"task_id": "job_abc123", "status": "queued"})

    with pytest.raises(MinerUTimeoutError):
        _run(_client(handler, timeout_seconds=0.01).parse_pdf(content=b"%PDF-1.4", filename="x.pdf"))


def test_parse_202_without_task_id_is_a_contract_error():
    def handler(request):
        return _json(202, {"status": "queued"})

    with pytest.raises(MinerUContractError):
        _run(_client(handler).parse_pdf(content=b"%PDF-1.4", filename="x.pdf"))


def test_parse_failed_file_is_invalid_output():
    payload = json.loads(_load("v4_file_parse_response.json"))
    payload["files"][0]["status"] = "failed"
    payload["files"][0]["error"] = "ocr failed"

    def handler(request):
        return _json(200, payload)

    with pytest.raises(MinerUInvalidOutputError):
        _run(_client(handler).parse_pdf(content=b"%PDF-1.4", filename="sample.pdf"))


def test_parse_failed_task_is_invalid_output():
    def handler(request):
        return _json(200, {"task_id": "job_x", "status": "failed", "files": []})

    with pytest.raises(MinerUInvalidOutputError):
        _run(_client(handler).parse_pdf(content=b"%PDF-1.4", filename="x.pdf"))


def test_parse_422_invalid_output():
    def handler(request):
        return _json(422, {"detail": "bad"})

    with pytest.raises(MinerUInvalidOutputError):
        _run(_client(handler).parse_pdf(content=b"%PDF-1.4", filename="x.pdf"))


def test_parse_500_unavailable():
    def handler(request):
        return _json(500, {"detail": "boom"})

    with pytest.raises(MinerUUnavailableError):
        _run(_client(handler).parse_pdf(content=b"%PDF-1.4", filename="x.pdf"))


def test_parse_old_route_404_is_a_contract_error():
    def handler(request):
        return _json(404, {"detail": "Not Found"})

    with pytest.raises(MinerUContractError):
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
        return _json(200, b"{not json")

    with pytest.raises(MinerUInvalidOutputError):
        _run(_client(handler).parse_pdf(content=b"%PDF-1.4", filename="x.pdf"))


def test_parse_empty_files():
    def handler(request):
        return _json(200, {"task_id": "job_x", "status": "completed", "files": []})

    with pytest.raises(MinerUInvalidOutputError):
        _run(_client(handler).parse_pdf(content=b"%PDF-1.4", filename="x.pdf"))


def test_parse_without_pages_is_a_contract_error():
    payload = json.loads(_load("v4_file_parse_response.json"))
    payload["files"][0]["content"]["middle_json"] = {"schema": "docvortex.middle"}

    def handler(request):
        return _json(200, payload)

    with pytest.raises(MinerUContractError):
        _run(_client(handler).parse_pdf(content=b"%PDF-1.4", filename="sample.pdf"))


def test_parse_oversized_response_capped():
    def handler(request):
        return _json(200, _load("v4_file_parse_response.json"))

    client = _client(handler, max_response_bytes=10)  # tiny cap
    with pytest.raises(MinerUInvalidOutputError):
        _run(client.parse_pdf(content=b"%PDF-1.4", filename="x.pdf"))


def test_parse_empty_content_rejected():
    def handler(request):
        return _json(200, {})

    with pytest.raises(MinerUInvalidOutputError):
        _run(_client(handler).parse_pdf(content=b"", filename="x.pdf"))


def test_safe_filename_keeps_pdf_extension_after_truncation():
    safe = _safe_filename("x" * 300 + ".pdf")
    assert len(safe) == 128
    assert safe.endswith(".pdf")


def test_parse_rejects_response_from_another_major_version():
    payload = json.loads(_load("v4_file_parse_response.json"))
    payload["files"][0]["parse"]["parser_version"] = "5.0.0"

    def handler(request):
        return _json(200, payload)

    with pytest.raises(MinerUContractError):
        _run(_client(handler, expected_version="4").parse_pdf(
            content=b"%PDF-1.4", filename="sample.pdf"))


def test_connect_error_retries_once_then_fails():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        raise httpx.ConnectError("refused")

    with pytest.raises(MinerUUnavailableError):
        _run(_client(handler).parse_pdf(content=b"%PDF-1.4", filename="x.pdf"))
    assert calls["n"] == 2  # one retry only
