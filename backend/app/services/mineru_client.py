"""
Async client for the MinerU document-extraction service.

MinerU is an OCR/document extractor, NOT the accounting engine. This client only
transports a PDF to MinerU's ``/v1/file_parse`` endpoint and returns the raw result;
all accounting classification, reconciliation and quadratura stay downstream in the
existing importer pipeline.

Contract is pinned to the MinerU 4 API served by gx10 (4.0.12, the VLM, from 2026-10-26;
``tests/fixtures/mineru/v4_*.json``): ``POST /v1/file_parse`` with ``tier``/``ocr_mode``/
``output_formats`` as query parameters and the PDF as multipart ``files``. The server
holds the request up to ``wait_timeout`` seconds; a job still queued or running answers
**202** with a ``task_id``, and the result is then polled on
``GET /v1/tasks/{task_id}/result`` until 200, all within ``timeout_seconds`` (measured: 76 s and 5 min 30 s of queue for
1-2 min of analysis). The result carries ``files[0].content.markdown`` and
``files[0].content.middle_json.pages[].blocks[]``; the page number lives on the page, no
longer on each block. ``_blocchi_da_pagine`` turns the pages back into the flat list of
typed blocks with ``page_idx`` that ``importers/mineru_adapter`` reads, so the adapter and
every reader behind it do not change.

Security / robustness:
- the MinerU response is untrusted: response size is capped and the structure is
  validated defensively;
- PDF bytes, Markdown, JSON and table content are NEVER logged (only hashes, sizes,
  durations, HTTP codes, page counts and error types);
- no blind retries on POST /v1/file_parse (would duplicate a heavy OCR job); a single
  retry is allowed ONLY for a pre-send connection error. Polling a task is a GET and
  repeats freely until the applicative deadline.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Exceptions
# --------------------------------------------------------------------------- #
class MinerUError(Exception):
    """Base class for all MinerU client errors."""


class MinerUUnavailableError(MinerUError):
    """MinerU is disabled, unreachable, unhealthy or saturated (→ HTTP 503)."""


class MinerUTimeoutError(MinerUError):
    """MinerU did not answer within the applicative timeout (→ HTTP 504)."""


class MinerUInvalidOutputError(MinerUError):
    """MinerU replied but the payload is empty, oversized or malformed (→ HTTP 422)."""


class MinerUContractError(MinerUError):
    """MinerU replied in a shape incompatible with the pinned contract."""


# --------------------------------------------------------------------------- #
# Value objects
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class MinerUHealth:
    status: str
    version: Optional[str]
    raw: dict = field(default_factory=dict)

    @property
    def healthy(self) -> bool:
        return str(self.status).lower() in ("ok", "healthy")


@dataclass(frozen=True)
class MinerURawResult:
    """The single file's result of a MinerU parse job.

    ``content_list`` is the flat list of typed blocks with ``page_idx`` rebuilt from
    ``middle_json.pages`` (the shape ``importers/mineru_adapter`` reads); ``middle_json``
    is the v4 document as returned."""

    version: Optional[str]
    status: Optional[str]
    file_stem: str
    md_content: str
    middle_json: Any
    content_list: Any
    raw: dict = field(default_factory=dict)


def versione_compatibile(attesa: Optional[str], letta: Optional[str]) -> bool:
    """``attesa`` fissa i componenti che scrive: "4" accetta ogni 4.x, "4.0.12" solo
    quella. gx10 si aggiorna da solo, e un pin esatto ripiegava in silenzio sull'OCR di
    riserva a ogni rilascio minore; il contratto cambia col numero maggiore."""
    if not attesa or not letta:
        return True
    pezzi = attesa.strip().split(".")
    return letta.strip().split(".")[: len(pezzi)] == pezzi


def _testo(content: Any) -> str:
    """Il testo di un blocco v4: ``content`` e' una stringa o una lista di span annidati
    ``{"type": ..., "content": ...}``."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(_testo(c.get("content")) if isinstance(c, dict) else _testo(c)
                       for c in content)
    return ""


_TIPI_TITOLO = {"title", "paragraph_title", "doc_title"}


def _blocchi_da_pagine(middle_json: Any) -> list[dict]:
    """``middle_json.pages[].blocks[]`` → la lista piatta di blocchi tipizzati con
    ``page_idx`` che l'adapter legge (``text``/``header``/``table``, la tabella con
    ``table_body`` HTML e ``table_caption`` lista di stringhe). Le intestazioni di
    paragrafo diventano testo con ``text_level``; numeri di pagina e pie' di pagina
    passano col loro tipo e l'adapter li ignora come prima."""
    pagine = middle_json.get("pages") if isinstance(middle_json, dict) else None
    if not isinstance(pagine, list):
        raise MinerUContractError("MinerU middle_json has no pages")
    out: list[dict] = []
    for n, pagina in enumerate(pagine):
        if not isinstance(pagina, dict):
            continue
        idx = pagina.get("page_idx", n)
        for blocco in pagina.get("blocks") or []:
            if not isinstance(blocco, dict):
                continue
            tipo = blocco.get("type")
            if tipo == "table":
                parti = blocco.get("content") if isinstance(blocco.get("content"), list) else []
                corpo = [p for p in parti if isinstance(p, dict) and p.get("type") == "table_body"]
                titoli = [_testo(p.get("content")).strip() for p in parti
                          if isinstance(p, dict) and p.get("type") == "table_caption"]
                note = [_testo(p.get("content")).strip() for p in parti
                        if isinstance(p, dict) and p.get("type") == "table_footnote"]
                out.append({"type": "table", "page_idx": idx, "bbox": blocco.get("bbox"),
                            "table_body": _testo(corpo[0].get("content")) if corpo else "",
                            "table_caption": [t for t in titoli if t],
                            "table_footnote": [t for t in note if t]})
            elif tipo in _TIPI_TITOLO:
                out.append({"type": "text", "page_idx": idx, "bbox": blocco.get("bbox"),
                            "text": _testo(blocco.get("content")), "text_level": 1})
            elif tipo == "header":
                out.append({"type": "header", "page_idx": idx, "bbox": blocco.get("bbox"),
                            "text": _testo(blocco.get("content"))})
            elif tipo in ("page_number", "footer", "image"):
                out.append({"type": tipo, "page_idx": idx, "bbox": blocco.get("bbox")})
            else:  # text, list e ogni tipo nuovo: testo, mai perso
                out.append({"type": "text", "page_idx": idx, "bbox": blocco.get("bbox"),
                            "text": _testo(blocco.get("content"))})
    return out


def _safe_filename(name: str) -> str:
    """Strip path components and keep a conservative charset (never trust the caller)."""
    base = re.sub(r"[\\/]", "_", name or "").strip() or "document.pdf"
    base = re.sub(r"[^A-Za-z0-9._-]", "_", base)
    stem = base[:-4] if base.lower().endswith(".pdf") else base
    stem = stem[:124] or "document"
    return f"{stem}.pdf"


class MinerUClient:
    """Thin async wrapper over the MinerU 4 HTTP API."""

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float = 600.0,
        connect_timeout_seconds: float = 10.0,
        max_response_bytes: int = 209_715_200,
        tier: str = "advanced",
        ocr_mode: str = "ocr",
        expected_version: Optional[str] = None,
        api_key: Optional[str] = None,
        poll_interval_seconds: float = 3.0,
        wait_seconds: int = 50,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.connect_timeout_seconds = connect_timeout_seconds
        self.max_response_bytes = max_response_bytes
        self.tier = tier
        self.ocr_mode = ocr_mode
        self.expected_version = expected_version
        self.api_key = api_key or None
        self.poll_interval_seconds = poll_interval_seconds
        self.wait_seconds = wait_seconds
        self._transport = transport

    @classmethod
    def from_settings(cls, settings: Any, *, transport: Optional[httpx.AsyncBaseTransport] = None) -> "MinerUClient":
        return cls(
            base_url=getattr(settings, "MINERU_BASE_URL", "http://127.0.0.1:8002"),
            timeout_seconds=float(getattr(settings, "MINERU_TIMEOUT_SECONDS", 600)),
            connect_timeout_seconds=float(getattr(settings, "MINERU_CONNECT_TIMEOUT_SECONDS", 10)),
            max_response_bytes=int(getattr(settings, "MINERU_MAX_RESPONSE_BYTES", 209_715_200)),
            tier=getattr(settings, "MINERU_TIER", "advanced"),
            ocr_mode=getattr(settings, "MINERU_PARSE_METHOD", "ocr"),
            expected_version=getattr(settings, "MINERU_EXPECTED_VERSION", None),
            api_key=getattr(settings, "MINERU_API_KEY", None),
            wait_seconds=int(getattr(settings, "MINERU_WAIT_SECONDS", 50)),
            transport=transport,
        )

    def _client(self, read_timeout: Optional[float] = None) -> httpx.AsyncClient:
        timeout = httpx.Timeout(read_timeout or self.timeout_seconds,
                                connect=self.connect_timeout_seconds)
        kwargs: dict = {"base_url": self.base_url, "timeout": timeout}
        if self.api_key:
            kwargs["headers"] = {"X-Api-Key": self.api_key}
        if self._transport is not None:
            kwargs["transport"] = self._transport
        return httpx.AsyncClient(**kwargs)

    def _check_version(self, version: Optional[str]) -> None:
        if not versione_compatibile(self.expected_version, version):
            raise MinerUContractError(
                f"MinerU version mismatch: expected {self.expected_version}, got {version}"
            )

    # ------------------------------------------------------------------ #
    # Health
    # ------------------------------------------------------------------ #
    async def health(self) -> MinerUHealth:
        try:
            async with self._client() as client:
                resp = await client.get("/v1/health")
        except httpx.TimeoutException as exc:
            raise MinerUTimeoutError("MinerU health check timed out") from exc
        except httpx.HTTPError as exc:
            raise MinerUUnavailableError(f"MinerU unreachable: {type(exc).__name__}") from exc

        if resp.status_code != 200:
            raise MinerUUnavailableError(f"MinerU health returned HTTP {resp.status_code}")
        try:
            data = resp.json()
        except ValueError as exc:
            raise MinerUUnavailableError("MinerU health returned non-JSON") from exc
        if not isinstance(data, dict):
            raise MinerUUnavailableError("MinerU health returned a non-object")

        health = MinerUHealth(status=str(data.get("status", "")), version=data.get("version"), raw=data)
        if not health.healthy:
            raise MinerUUnavailableError(f"MinerU not healthy: status={health.status!r}")
        self._check_version(health.version)
        return health

    # ------------------------------------------------------------------ #
    # Parse
    # ------------------------------------------------------------------ #
    async def parse_pdf(self, *, content: bytes, filename: str) -> MinerURawResult:
        if not content:
            raise MinerUInvalidOutputError("Empty PDF content passed to MinerU")

        safe_name = _safe_filename(filename)
        digest = hashlib.sha256(content).hexdigest()[:16]
        scadenza = time.monotonic() + self.timeout_seconds
        # Il server tiene aperta la POST al massimo ``wait_seconds``, sotto il minuto: sui
        # VPS la richiesta passa dal proxy nginx di gx10, e un'attesa piu' lunga del suo
        # timeout di lettura tornerebbe 504. Il resto lo fa il polling, entro la scadenza.
        attesa = max(1, min(self.wait_seconds, 3600, int(self.timeout_seconds) or 1))
        params = [("tier", self.tier), ("ocr_mode", self.ocr_mode),
                  ("output_formats", "markdown"), ("output_formats", "middle_json"),
                  ("wait_timeout", str(attesa))]
        files = {"files": (safe_name, content, "application/pdf")}

        status_code, headers, body = await self._send(
            "POST", "/v1/file_parse", params=params, files=files,
            read_timeout=attesa + 30, retry_connect=True)
        payload = self._json(status_code, headers, body)

        while status_code == 202:
            task_id = payload.get("task_id") if isinstance(payload, dict) else None
            if not task_id or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", str(task_id)):
                raise MinerUContractError("MinerU 202 without a usable task_id")
            if isinstance(payload, dict) and payload.get("status") in ("failed", "canceled"):
                raise MinerUInvalidOutputError(f"MinerU task {payload.get('status')}")
            resta = scadenza - time.monotonic()
            if resta <= 0:
                raise MinerUTimeoutError("MinerU parse timed out while queued")
            await asyncio.sleep(min(self.poll_interval_seconds, resta))
            status_code, headers, body = await self._send(
                "GET", f"/v1/tasks/{task_id}/result", read_timeout=max(5.0, min(60.0, resta)))
            payload = self._json(status_code, headers, body)

        result = self._extract_result(payload, requested_name=safe_name)
        logger.info(
            "MinerU parse ok: sha=%s bytes_in=%d bytes_out=%d version=%s status=%s blocks=%d",
            digest, len(content), len(body), result.version, result.status, len(result.content_list),
        )
        self._check_version(result.version)
        return result

    def _json(self, status_code: int, headers: httpx.Headers, body: bytes) -> Any:
        if status_code == 422:
            raise MinerUInvalidOutputError("MinerU rejected the document (422)")
        if status_code >= 500:
            raise MinerUUnavailableError(f"MinerU server error HTTP {status_code}")
        if status_code not in (200, 202):
            raise MinerUContractError(f"Unexpected MinerU HTTP {status_code}")
        ctype = headers.get("content-type", "")
        if "application/json" not in ctype:
            raise MinerUContractError(f"Unexpected MinerU content-type: {ctype!r}")
        try:
            return json.loads(body)
        except (ValueError, UnicodeDecodeError) as exc:
            raise MinerUInvalidOutputError("MinerU returned invalid JSON") from exc

    async def _send(self, method: str, url: str, *, params=None, files=None,
                    read_timeout: Optional[float] = None,
                    retry_connect: bool = False) -> tuple[int, httpx.Headers, bytes]:
        """One request, with the body capped while it is being received."""
        attempt = 0
        while True:
            attempt += 1
            try:
                async with self._client(read_timeout) as client:
                    async with client.stream(method, url, params=params, files=files) as resp:
                        content_length = resp.headers.get("content-length")
                        if content_length:
                            try:
                                if int(content_length) > self.max_response_bytes:
                                    raise MinerUInvalidOutputError(
                                        f"MinerU response exceeds {self.max_response_bytes} bytes"
                                    )
                            except ValueError:
                                pass
                        body = bytearray()
                        async for chunk in resp.aiter_bytes():
                            body.extend(chunk)
                            if len(body) > self.max_response_bytes:
                                raise MinerUInvalidOutputError(
                                    f"MinerU response exceeds {self.max_response_bytes} bytes"
                                )
                        return resp.status_code, resp.headers, bytes(body)
            except httpx.ConnectError as exc:
                # Connection failed BEFORE the body was sent → safe to retry once
                if attempt == 1 and retry_connect:
                    logger.warning("MinerU connect error, retrying once: %s", type(exc).__name__)
                    continue
                raise MinerUUnavailableError("MinerU connection failed") from exc
            except httpx.TimeoutException as exc:
                raise MinerUTimeoutError("MinerU parse timed out") from exc
            except httpx.HTTPError as exc:
                raise MinerUUnavailableError(f"MinerU transport error: {type(exc).__name__}") from exc

    def _extract_result(self, payload: Any, *, requested_name: str) -> MinerURawResult:
        if not isinstance(payload, dict):
            raise MinerUContractError("MinerU payload is not an object")

        status = payload.get("status")
        if status in ("failed", "canceled") or payload.get("error"):
            raise MinerUInvalidOutputError(
                f"MinerU reported status={status!r} error={str(payload.get('error') or '')[:120]}")

        files = payload.get("files")
        if not isinstance(files, list) or not files:
            raise MinerUInvalidOutputError("MinerU returned no files")
        entry = next((f for f in files if isinstance(f, dict) and f.get("name") == requested_name),
                     files[0] if len(files) == 1 else None)
        if not isinstance(entry, dict):
            raise MinerUContractError("MinerU result not associable to the requested file")
        if entry.get("status") != "completed":
            raise MinerUInvalidOutputError(
                f"MinerU file status={entry.get('status')!r} error={str(entry.get('error') or '')[:120]}")

        content = entry.get("content") if isinstance(entry.get("content"), dict) else {}
        md_content = content.get("markdown") or ""
        middle_json = content.get("middle_json")
        if isinstance(middle_json, str):
            try:
                middle_json = json.loads(middle_json)
            except ValueError as exc:
                raise MinerUInvalidOutputError("MinerU middle_json is not valid JSON") from exc
        blocchi = _blocchi_da_pagine(middle_json) if middle_json is not None else []
        if not md_content and not blocchi:
            raise MinerUInvalidOutputError("MinerU result carries no text/content")

        parse = entry.get("parse") if isinstance(entry.get("parse"), dict) else {}
        version = parse.get("parser_version")
        if not version and isinstance(middle_json, dict):
            producer = (middle_json.get("metadata") or {}).get("producer") or {}
            version = producer.get("version") if isinstance(producer, dict) else None

        return MinerURawResult(
            version=version,
            status=status,
            file_stem=str(entry.get("name") or requested_name).rsplit(".", 1)[0],
            md_content=md_content,
            middle_json=middle_json,
            content_list=blocchi,
            raw=payload,
        )
