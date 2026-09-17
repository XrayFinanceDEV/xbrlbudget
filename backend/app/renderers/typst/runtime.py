"""Pinned Typst compilation with fail-closed Linux filesystem/network isolation.

Only a private job tree and the verified static compiler enter Bubblewrap.
Report text is JSON data, never interpolated into a Typst program or command.
The parent captures neither compiler source diagnostics nor user content in logs.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import platform
import re
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

import fitz

from app.schemas.final_report_v2 import FinalReportModelV2

log = logging.getLogger(__name__)
_SHA = re.compile(r'^[0-9a-f]{64}$')


class RendererError(Exception):
    category = 'renderer_error'
    message = 'Generazione del documento non riuscita.'

    def __init__(self):
        super().__init__(self.message)


class RendererUnavailable(RendererError):
    category = 'renderer_unavailable'
    message = 'Compilatore o isolamento del documento non disponibile.'


class RendererBusy(RendererUnavailable):
    category = 'renderer_busy'
    message = 'Generazione documenti temporaneamente occupata.'


class RendererTimeout(RendererError):
    category = 'renderer_timeout'
    message = 'Tempo massimo di generazione del documento superato.'


class RendererInputError(RendererError):
    category = 'renderer_input_invalid'
    message = 'Modello o opzioni del documento non validi.'


class RendererCompileError(RendererError):
    category = 'renderer_compile_failed'
    message = 'Compilazione del documento non riuscita.'

    def __init__(self, panics: tuple[str, ...] = ()):
        super().__init__()
        #: I codici con cui il template si è fermato di proposito («editorial-amount-does-not-fit»).
        #: Vuoto quando la compilazione è fallita per altro. Solo i codici, mai il resto dello
        #: stderr: sono costanti del nostro template e non portano dati del documento.
        self.panics = tuple(panics)


_PANIC_CODE = re.compile(rb'panicked with: "?([a-z0-9][a-z0-9-]{0,80})')
_STDERR_LIMIT = 64 * 1024


def _panic_codes(stderr: bytes) -> tuple[str, ...]:
    codes: list[str] = []
    for match in _PANIC_CODE.finditer(stderr[:_STDERR_LIMIT]):
        code = match.group(1).decode('ascii')
        if code not in codes:
            codes.append(code)
    return tuple(codes)


class RendererInvalidPdf(RendererError):
    category = 'renderer_output_invalid'
    message = 'Il documento generato non supera la validazione PDF.'


@dataclass(frozen=True)
class RendererLimits:
    timeout_seconds: float = 30
    max_input_bytes: int = 8 * 1024 * 1024
    max_output_bytes: int = 32 * 1024 * 1024
    memory_bytes: int = 512 * 1024 * 1024
    cpu_seconds: int = 25
    max_pages: int = 200
    max_concurrent: int = 2
    max_asset_bytes: int = 16 * 1024 * 1024
    max_assets: int = 64

    def __post_init__(self):
        for key, value in vars(self).items():
            if key == 'timeout_seconds':
                valid = isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0
            else:
                valid = type(value) is int and value > 0
            if not valid:
                raise ValueError(f'Invalid renderer limit: {key}')


def _regular(path: Path, maximum: int) -> bytes:
    """Read a bounded regular file; refuse symlinks including parent segments."""
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise RendererUnavailable()
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > maximum:
                raise RendererUnavailable()
            data = stream.read(maximum + 1)
            if len(data) > maximum:
                raise RendererUnavailable()
            return data
    except OSError:
        raise RendererUnavailable() from None


@dataclass(frozen=True)
class Compiler:
    path: Path
    version: str
    binary_sha256: str

    def __post_init__(self):
        if (not isinstance(self.path, Path) or not isinstance(self.version, str)
                or not re.fullmatch(r'\d+\.\d+\.\d+', self.version)
                or not isinstance(self.binary_sha256, str) or not _SHA.fullmatch(self.binary_sha256)):
            raise RendererUnavailable()

    @classmethod
    def from_manifest(cls, manifest: Path, binary: Path):
        try:
            metadata = json.loads(_regular(manifest.absolute(), 64 * 1024))
            version, digest = metadata['version'], metadata['binary_sha256']
            if not re.fullmatch(r'\d+\.\d+\.\d+', version) or not _SHA.fullmatch(digest):
                raise ValueError()
            return cls(binary.absolute(), version, digest)
        except (KeyError, TypeError, ValueError):
            raise RendererUnavailable() from None

    def verified_bytes(self) -> bytes:
        data = _regular(self.path.absolute(), 100 * 1024 * 1024)
        if not _SHA.fullmatch(self.binary_sha256) or hashlib.sha256(data).hexdigest() != self.binary_sha256:
            raise RendererUnavailable()
        if not os.access(self.path, os.X_OK):
            raise RendererUnavailable()
        return data


@dataclass(frozen=True)
class TemplateBundle:
    path: Path

    def read(self, limits: RendererLimits) -> tuple[str, str, dict[str, bytes]]:
        try:
            metadata = json.loads(_regular(self.path.absolute() / 'manifest.json', 64 * 1024))
            if set(metadata) != {'version', 'entrypoint', 'files'} or not isinstance(metadata['version'], str) or not metadata['version']:
                raise ValueError()
            files = metadata['files']
            if not isinstance(files, dict) or not files or len(files) > limits.max_assets:
                raise ValueError()
            result, total = {}, 0
            for name, digest in files.items():
                relative = PurePosixPath(name)
                if (relative.is_absolute() or any(p in ('..', '.') for p in name.split('/'))
                        or '\\' in name or str(relative) != name or not _SHA.fullmatch(digest)
                        or name in ('model.json', 'options.json', 'compiler', 'manifest.json')
                        or name.startswith(('output/', 'packages/', 'cache/'))):
                    raise ValueError()
                data = _regular(self.path.absolute() / name, limits.max_asset_bytes)
                total += len(data)
                if total > limits.max_asset_bytes or hashlib.sha256(data).hexdigest() != digest:
                    raise ValueError()
                result[name] = data
            entry = metadata['entrypoint']
            if not isinstance(entry, str) or entry not in result or not entry.endswith('.typ'):
                raise ValueError()
            return metadata['version'], entry, result
        except (KeyError, TypeError, ValueError):
            raise RendererUnavailable() from None


@dataclass(frozen=True)
class RenderedPdf:
    data: bytes
    artifact_sha256: str
    model_hash: str
    source_hash: str
    schema_version: int
    template_version: str
    compiler_version: str
    page_count: int
    duration_seconds: float


def validate_pdf(data: bytes, *, title: str, draft: bool, limits: RendererLimits) -> int:
    if (not data.startswith(b'%PDF-') or not data.rstrip().endswith(b'%%EOF')
            or not data or len(data) > limits.max_output_bytes):
        raise RendererInvalidPdf()
    try:
        with fitz.open(stream=data, filetype='pdf') as document:
            if (not document.is_pdf or document.is_repaired or document.is_encrypted
                    or document.embfile_count() or not 0 < document.page_count <= limits.max_pages
                    or document.metadata.get('title') != title):
                raise RendererInvalidPdf()
            for page in document:
                dimensions = sorted((page.rect.width, page.rect.height))
                if abs(dimensions[0] - 595.276) > 1 or abs(dimensions[1] - 841.89) > 1:
                    raise RendererInvalidPdf()
                text = page.get_text()
                if not text.strip() or (draft and 'BOZZA' not in text):
                    raise RendererInvalidPdf()
            return document.page_count
    except RendererError:
        raise
    except Exception:
        raise RendererInvalidPdf() from None


class TypstRenderer:
    """Reuse one instance per application worker: semaphore caps local processes.

    Limits are per worker; deployment must also cap workers and provision memory.
    There is no unsandboxed fallback when Bubblewrap or namespaces are unavailable.
    """
    def __init__(self, compiler: Compiler, bundle: TemplateBundle, *, limits: RendererLimits | None = None,
                 sandbox: Path = Path('/usr/bin/bwrap'), temp_root: Path | None = None):
        self.compiler, self.bundle = compiler, bundle
        self.limits = limits or RendererLimits()
        self.sandbox = sandbox.absolute()
        self.temp_root = temp_root
        self._slots = threading.BoundedSemaphore(self.limits.max_concurrent)

    @classmethod
    def from_project(cls, root: Path, **kwargs):
        return cls(Compiler.from_manifest(root / 'tools/typst/manifest.json', root / 'tools/typst/bin/typst'),
                   TemplateBundle(Path(__file__).parent / 'templates/runtime-smoke'), **kwargs)

    def _sandbox_command(self, job: Path, command: list[str]) -> list[str]:
        return [str(self.sandbox), '--unshare-all', '--unshare-user', '--die-with-parent', '--disable-userns',
                '--cap-drop', 'ALL', '--clearenv', '--ro-bind', str(job), '/report',
                '--bind', str(job / 'output'), '/report/output', '--chdir', '/report', '--', *command]

    @contextmanager
    def _private_job(self, serialized: bytes, files: dict[str, bytes], binary: bytes, options: bytes):
        """Stage only verified bundle data in the private tree mounted by Bubblewrap."""
        with tempfile.TemporaryDirectory(prefix='budget-typst-', dir=self.temp_root) as folder:
            job = Path(folder)
            for name, data in files.items():
                destination = job / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)
            (job / 'model.json').write_bytes(serialized)
            (job / 'options.json').write_bytes(options)
            (job / 'compiler').write_bytes(binary)
            (job / 'compiler').chmod(0o500)
            for directory in ('output', 'packages', 'cache', 'fonts'):
                (job / directory).mkdir(exist_ok=True)
            yield job

    def _run(self, command: list[str], job: Path, *, unavailable=False, deadline: float | None = None,
             stdout_path: Path | None = None):
        remaining = self.limits.timeout_seconds if deadline is None else deadline - time.monotonic()
        if remaining <= 0:
            raise RendererTimeout()
        worker = Path(__file__).with_name('worker.py')
        wrapped = [sys.executable, '-I', str(worker), str(self.limits.memory_bytes),
                   str(self.limits.cpu_seconds), str(self.limits.max_output_bytes), '128', *command]
        output = None
        if stdout_path is not None:
            if stdout_path.parent != job / 'output' or stdout_path.name != 'layout.json':
                raise RendererUnavailable()
            try:
                fd = os.open(stdout_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                output = os.fdopen(fd, 'wb')
            except OSError:
                raise RendererUnavailable() from None
        # Un file anonimo, fuori dal job montato nella sandbox: se ne leggono solo i codici dei panic
        # (`_panic_codes`). Prima andava in DEVNULL, e un importo che non entrava nella colonna
        # arrivava all'utente come «verificare il renderer» (AMBIENTA, 2026-09-17).
        errors = tempfile.TemporaryFile()
        try:
            process = subprocess.Popen(wrapped, cwd=job, stdin=subprocess.DEVNULL,
                stdout=output if output is not None else subprocess.DEVNULL,
                stderr=errors, env={}, start_new_session=True)
        except OSError:
            errors.close()
            raise RendererUnavailable() from None
        finally:
            if output is not None:
                output.close()
        try:
            code = process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            errors.close()
            raise RendererTimeout() from None
        except BaseException:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            errors.close()
            raise
        try:
            if code:
                if unavailable:
                    raise RendererUnavailable()
                errors.seek(0)
                raise RendererCompileError(_panic_codes(errors.read(_STDERR_LIMIT)))
        finally:
            errors.close()

    def render(self, report: FinalReportModelV2, *, document_state: Literal['draft', 'final'] = 'draft',
               grayscale: bool = False) -> RenderedPdf:
        started = time.monotonic()
        if document_state not in ('draft', 'final') or type(grayscale) is not bool or not isinstance(report, FinalReportModelV2):
            raise RendererInputError()
        if not self._slots.acquire(blocking=False):
            raise RendererBusy()
        try:
            if platform.system() != 'Linux' or platform.machine() != 'x86_64':
                raise RendererUnavailable()
            try:
                serialized = report.model_dump_json().encode('utf-8')
                if len(serialized) > self.limits.max_input_bytes:
                    raise RendererInputError()
                frozen = FinalReportModelV2.model_validate_json(serialized)
            except RendererError:
                raise
            except Exception:
                raise RendererInputError() from None
            version, entry, files = self.bundle.read(self.limits)
            binary = self.compiler.verified_bytes()
            if not self.sandbox.is_file() or self.sandbox.is_symlink() or not os.access(self.sandbox, os.X_OK):
                raise RendererUnavailable()
            try:
                options = json.dumps({'document_state': document_state, 'grayscale': grayscale}).encode('utf-8')
                with self._private_job(serialized, files, binary, options) as job:
                    # A real sandbox probe distinguishes unavailable namespaces
                    # from a compiler error, without capturing any diagnostics.
                    deadline = started + self.limits.timeout_seconds
                    self._run(self._sandbox_command(job, ['/report/compiler', '--version']), job,
                              unavailable=True, deadline=deadline)
                    timestamp = str(int(frozen.generated_at.timestamp()))
                    compiler = ['/report/compiler', 'compile', '--root', '/report', '--format', 'pdf',
                        '--jobs', '1', '--ignore-system-fonts', '--package-path', '/report/packages',
                        '--package-cache-path', '/report/cache', '--font-path', '/report/fonts',
                        '--creation-timestamp', timestamp, '--diagnostic-format', 'short',
                        f'/report/{entry}', '/report/output/report.pdf']
                    self._run(self._sandbox_command(job, compiler), job, deadline=deadline)
                    path = job / 'output/report.pdf'
                    try:
                        data = _regular(path, self.limits.max_output_bytes)
                    except RendererUnavailable:
                        raise RendererInvalidPdf() from None
                    pages = validate_pdf(data, title=frozen.document.title, draft=document_state == 'draft', limits=self.limits)
                    if time.monotonic() > deadline:
                        raise RendererTimeout()
            except RendererError:
                raise
            except OSError:
                raise RendererUnavailable() from None
            elapsed = time.monotonic() - started
            log.info('typst_render_success schema=%d pages=%d bytes=%d elapsed_ms=%d',
                frozen.schema_version, pages, len(data), int(elapsed * 1000))
            return RenderedPdf(data, hashlib.sha256(data).hexdigest(), frozen.model_hash, frozen.source_hash,
                frozen.schema_version, version, self.compiler.version, pages, elapsed)
        except RendererError as error:
            log.warning('typst_render_failed category=%s', error.category)
            raise
        finally:
            self._slots.release()
