"""
Async client for the MinerU document-extraction service (Docker).

MinerU is an OCR/document extractor, NOT the accounting engine. This client only
transports a PDF to MinerU's ``/file_parse`` endpoint and returns the raw result;
all accounting classification, reconciliation and quadratura stay downstream in the
existing importer pipeline.

Contract is pinned to the running MinerU 3.2.0 container (see
``tests/fixtures/mineru/openapi.json``). The multipart field names and the response
envelope (``results`` keyed by file stem; ``middle_json``/``content_list`` are
JSON-encoded *strings*) were captured from the live service, not guessed.

Security / robustness:
- the MinerU response is untrusted: response size is capped and the structure is
  validated defensively;
- PDF bytes, Markdown, JSON and table content are NEVER logged (only hashes, sizes,
  durations, HTTP codes, page counts and error types);
- no blind retries on POST /file_parse (would duplicate a heavy OCR job); a single
  retry is allowed ONLY for a pre-send connection error.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
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
    protocol_version: Optional[int]
    queued_tasks: Optional[int]
    processing_tasks: Optional[int]
    max_concurrent_requests: Optional[int]
    raw: dict = field(default_factory=dict)

    @property
    def healthy(self) -> bool:
        return str(self.status).lower() == "healthy"


@dataclass(frozen=True)
class MinerURawResult:
    """Raw MinerU ``/file_parse`` envelope + the single file's result block."""

    version: Optional[str]
    status: Optional[str]
    file_stem: str
    md_content: str
    middle_json: str
    content_list: str
    raw: dict = field(default_factory=dict)


def _safe_filename(name: str) -> str:
    """Strip path components and keep a conservative charset (never trust the caller)."""
    base = re.sub(r"[\\/]", "_", name or "").strip() or "document.pdf"
    base = re.sub(r"[^A-Za-z0-9._-]", "_", base)
    stem = base[:-4] if base.lower().endswith(".pdf") else base
    stem = stem[:124] or "document"
    return f"{stem}.pdf"


class MinerUClient:
    """Thin async wrapper over the MinerU HTTP API."""

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float = 600.0,
        connect_timeout_seconds: float = 10.0,
        max_response_bytes: int = 209_715_200,
        language: str = "latin",
        backend: str = "pipeline",
        parse_method: str = "ocr",
        expected_version: Optional[str] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.connect_timeout_seconds = connect_timeout_seconds
        self.max_response_bytes = max_response_bytes
        self.language = language
        self.backend = backend
        self.parse_method = parse_method
        self.expected_version = expected_version
        self._transport = transport

    @classmethod
    def from_settings(cls, settings: Any, *, transport: Optional[httpx.AsyncBaseTransport] = None) -> "MinerUClient":
        return cls(
            base_url=getattr(settings, "MINERU_BASE_URL", "http://127.0.0.1:8002"),
            timeout_seconds=float(getattr(settings, "MINERU_TIMEOUT_SECONDS", 600)),
            connect_timeout_seconds=float(getattr(settings, "MINERU_CONNECT_TIMEOUT_SECONDS", 10)),
            max_response_bytes=int(getattr(settings, "MINERU_MAX_RESPONSE_BYTES", 209_715_200)),
            language=getattr(settings, "MINERU_LANGUAGE", "latin"),
            backend=getattr(settings, "MINERU_BACKEND", "pipeline"),
            parse_method=getattr(settings, "MINERU_PARSE_METHOD", "ocr"),
            expected_version=getattr(settings, "MINERU_EXPECTED_VERSION", None),
            transport=transport,
        )

    def _client(self) -> httpx.AsyncClient:
        timeout = httpx.Timeout(self.timeout_seconds, connect=self.connect_timeout_seconds)
        kwargs: dict = {"base_url": self.base_url, "timeout": timeout}
        if self._transport is not None:
            kwargs["transport"] = self._transport
        return httpx.AsyncClient(**kwargs)

    # ------------------------------------------------------------------ #
    # Health
    # ------------------------------------------------------------------ #
    async def health(self) -> MinerUHealth:
        try:
            async with self._client() as client:
                resp = await client.get("/health")
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

        health = MinerUHealth(
            status=str(data.get("status", "")),
            version=data.get("version"),
            protocol_version=data.get("protocol_version"),
            queued_tasks=data.get("queued_tasks"),
            processing_tasks=data.get("processing_tasks"),
            max_concurrent_requests=data.get("max_concurrent_requests"),
            raw=data,
        )
        if not health.healthy:
            raise MinerUUnavailableError(f"MinerU not healthy: status={health.status!r}")
        if self.expected_version and health.version and health.version != self.expected_version:
            raise MinerUContractError(
                f"MinerU version mismatch: expected {self.expected_version}, got {health.version}"
            )
        return health

    # ------------------------------------------------------------------ #
    # Parse
    # ------------------------------------------------------------------ #
    def _build_multipart(self, content: bytes, filename: str):
        files = {"files": (filename, content, "application/pdf")}
        # data MUST be a dict: httpx encodes a list-of-tuples body as a sync-only
        # IteratorByteStream, which an AsyncClient refuses to send. MinerU accepts a
        # single string for the array field lang_list (verified against the live
        # 3.2.0 container), so unique dict keys are sufficient.
        data = {
            "lang_list": self.language,
            "backend": self.backend,
            "parse_method": self.parse_method,
            "formula_enable": "false",
            "table_enable": "true",
            "image_analysis": "false",
            "return_md": "true",
            "return_content_list": "true",
            "return_middle_json": "true",
            "return_model_output": "false",
            "return_images": "false",
            "response_format_zip": "false",
        }
        return files, data

    async def parse_pdf(self, *, content: bytes, filename: str) -> MinerURawResult:
        if not content:
            raise MinerUInvalidOutputError("Empty PDF content passed to MinerU")

        safe_name = _safe_filename(filename)
        digest = hashlib.sha256(content).hexdigest()[:16]
        files, data = self._build_multipart(content, safe_name)

        status_code, headers, body = await self._post_parse(files, data)

        if status_code == 422:
            raise MinerUInvalidOutputError("MinerU rejected the document (422)")
        if status_code >= 500:
            raise MinerUUnavailableError(f"MinerU server error HTTP {status_code}")
        if status_code != 200:
            raise MinerUContractError(f"Unexpected MinerU HTTP {status_code}")

        ctype = headers.get("content-type", "")
        if "application/json" not in ctype:
            raise MinerUContractError(f"Unexpected MinerU content-type: {ctype!r}")

        try:
            payload = json.loads(body)
        except (ValueError, UnicodeDecodeError) as exc:
            raise MinerUInvalidOutputError("MinerU returned invalid JSON") from exc

        result = self._extract_result(payload, requested_stem=safe_name)
        logger.info(
            "MinerU parse ok: sha=%s bytes_in=%d bytes_out=%d version=%s status=%s",
            digest, len(content), len(body), result.version, result.status,
        )
        if self.expected_version and result.version and result.version != self.expected_version:
            raise MinerUContractError(
                f"MinerU version mismatch: expected {self.expected_version}, got {result.version}"
            )
        return result

    async def _post_parse(self, files, data) -> tuple[int, httpx.Headers, bytes]:
        """POST /file_parse and cap the body while it is being received."""
        attempt = 0
        while True:
            attempt += 1
            try:
                async with self._client() as client:
                    async with client.stream(
                        "POST", "/file_parse", files=files, data=data
                    ) as resp:
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
                if attempt == 1:
                    logger.warning("MinerU connect error, retrying once: %s", type(exc).__name__)
                    continue
                raise MinerUUnavailableError("MinerU connection failed") from exc
            except httpx.TimeoutException as exc:
                raise MinerUTimeoutError("MinerU parse timed out") from exc
            except httpx.HTTPError as exc:
                raise MinerUUnavailableError(f"MinerU transport error: {type(exc).__name__}") from exc

    def _extract_result(self, payload: Any, *, requested_stem: str) -> MinerURawResult:
        if not isinstance(payload, dict):
            raise MinerUContractError("MinerU payload is not an object")

        status = payload.get("status")
        if payload.get("error"):
            raise MinerUInvalidOutputError(f"MinerU reported an error: {str(payload['error'])[:120]}")

        results = payload.get("results")
        if not isinstance(results, dict) or not results:
            raise MinerUInvalidOutputError("MinerU returned no results")

        # results is keyed by file stem; take the requested one or the sole entry
        stem_key = None
        req_stem = requested_stem.rsplit(".", 1)[0]
        if req_stem in results:
            stem_key = req_stem
        elif len(results) == 1:
            stem_key = next(iter(results))
        else:
            # pick the first that carries md_content
            for k, v in results.items():
                if isinstance(v, dict) and v.get("md_content"):
                    stem_key = k
                    break
        if stem_key is None:
            raise MinerUContractError("MinerU results not associable to the requested file")

        block = results[stem_key]
        if not isinstance(block, dict):
            raise MinerUContractError("MinerU result block is not an object")

        md_content = block.get("md_content") or ""
        middle_json = block.get("middle_json") or ""
        content_list = block.get("content_list") or ""
        if not md_content and not content_list:
            raise MinerUInvalidOutputError("MinerU result carries no text/content")

        return MinerURawResult(
            version=payload.get("version"),
            status=status,
            file_stem=stem_key,
            md_content=md_content,
            middle_json=middle_json,
            content_list=content_list,
            raw=payload,
        )
