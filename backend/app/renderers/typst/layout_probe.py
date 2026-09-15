"""Inspect resolved, invisible Typst layout metadata in the renderer sandbox."""
from __future__ import annotations

import json
import hashlib
import os
import platform
import time
from dataclasses import dataclass
from typing import Literal

from app.schemas.final_report_v2 import FinalReportModelV2

from .runtime import (
    RendererBusy, RendererCompileError, RendererInputError, RendererTimeout,
    RendererUnavailable, TypstRenderer, _regular, log,
)

_EXPRESSION = 'query(metadata).map(x => x.value)'


@dataclass(frozen=True)
class LayoutProbeRecord:
    kind: Literal['content', 'row', 'page']
    page: int
    content_id: str
    statement_id: str | None = None
    row_id: str | None = None


@dataclass(frozen=True)
class LayoutMeasurement:
    """Base-only measurement bound to the exact verified bytes used by Typst."""
    records: tuple[LayoutProbeRecord, ...]
    source_hash: str
    model_hash: str
    layout_version: str
    font_hash: str
    layout_hash: str
    asset_hash: str
    page_count: int


class TypstLayoutProbe(TypstRenderer):
    """Runs a fixed Typst query against the same isolated job as PDF rendering."""

    def inspect_layout(self, report: FinalReportModelV2) -> tuple[LayoutProbeRecord, ...]:
        return self.measure_layout(report).records

    def measure_layout(self, report: FinalReportModelV2) -> LayoutMeasurement:
        started = time.monotonic()
        if not isinstance(report, FinalReportModelV2):
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
            except RendererInputError:
                raise
            except Exception:
                raise RendererInputError() from None
            version, entry, files = self.bundle.read(self.limits)
            binary = self.compiler.verified_bytes()
            if not self.sandbox.is_file() or self.sandbox.is_symlink() or not os.access(self.sandbox, os.X_OK):
                raise RendererUnavailable()
            options = b'{"document_state":"draft","grayscale":false}'
            with self._private_job(serialized, files, binary, options) as job:
                deadline = started + self.limits.timeout_seconds
                self._run(self._sandbox_command(job, ['/report/compiler', '--version']), job,
                          unavailable=True, deadline=deadline)
                command = [
                    '/report/compiler', 'eval', _EXPRESSION, '--in', f'/report/{entry}',
                    '--root', '/report', '--format', 'json', '--jobs', '1', '--ignore-system-fonts',
                    '--package-path', '/report/packages', '--package-cache-path', '/report/cache',
                    '--font-path', '/report/fonts', '--creation-timestamp',
                    str(int(frozen.generated_at.timestamp())), '--diagnostic-format', 'short',
                ]
                output = job / 'output/layout.json'
                self._run(self._sandbox_command(job, command), job, deadline=deadline, stdout_path=output)
                try:
                    records = self._validate_records(_regular(output, self.limits.max_output_bytes), frozen,
                                                     max_pages=self.limits.max_pages)
                except RendererCompileError:
                    raise
                except RendererUnavailable:
                    raise RendererCompileError() from None
                if time.monotonic() > deadline:
                    raise RendererTimeout()
            elapsed = time.monotonic() - started
            log.info('typst_layout_probe_success schema=%d records=%d elapsed_ms=%d',
                     frozen.schema_version, len(records), int(elapsed * 1000))
            def fingerprint(items):
                return hashlib.sha256(json.dumps(items, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            digests = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
            return LayoutMeasurement(records, frozen.source_hash, frozen.model_hash, version,
                fingerprint({n: h for n, h in digests.items() if n.startswith('fonts/')}),
                fingerprint({'templates': {n: h for n, h in digests.items() if n.endswith('.typ')},
                             'compiler': self.compiler.binary_sha256, 'options': json.loads(options)}),
                fingerprint({n: h for n, h in digests.items() if not n.startswith('fonts/')}),
                max(r.page for r in records))
        except (RendererBusy, RendererCompileError, RendererInputError, RendererTimeout, RendererUnavailable) as error:
            log.warning('typst_layout_probe_failed category=%s', error.category)
            raise
        except OSError:
            log.warning('typst_layout_probe_failed category=renderer_unavailable')
            raise RendererUnavailable() from None
        finally:
            self._slots.release()

    @staticmethod
    def _validate_records(raw: bytes, report: FinalReportModelV2, *, max_pages: int = 200) -> tuple[LayoutProbeRecord, ...]:
        try:
            values = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise RendererCompileError() from None
        if not isinstance(values, list) or not values:
            raise RendererCompileError()
        records: list[LayoutProbeRecord] = []
        for value in values:
            if not isinstance(value, dict) or type(value.get('page')) is not int or value['page'] <= 0:
                raise RendererCompileError()
            kind, content_id = value.get('kind'), value.get('content_id')
            if kind == 'content':
                if set(value) != {'kind', 'content_id', 'page'} or content_id != 'cover' or value['page'] != 1:
                    raise RendererCompileError()
                records.append(LayoutProbeRecord(kind, value['page'], content_id))
            elif kind == 'page':
                if set(value) != {'kind', 'content_id', 'page'} or content_id != 'page-shell':
                    raise RendererCompileError()
                records.append(LayoutProbeRecord(kind, value['page'], content_id))
            elif kind == 'row':
                if (set(value) != {'kind', 'content_id', 'statement_id', 'row_id', 'page'}
                        or not all(isinstance(value.get(key), str) and value[key]
                                   for key in ('content_id', 'statement_id', 'row_id'))
                        or value['content_id'] != f"row:{value['statement_id']}:{value['row_id']}"):
                    raise RendererCompileError()
                records.append(LayoutProbeRecord(kind, value['page'], content_id,
                                                 value['statement_id'], value['row_id']))
            else:
                raise RendererCompileError()
        pages = sorted({record.page for record in records})
        shell_pages = [record.page for record in records if record.kind == 'page']
        body_pages = sorted({r.page for r in records if r.kind != 'page'})
        if (pages[-1] > max_pages or pages != list(range(1, pages[-1] + 1))
                or sorted(shell_pages) != pages
                or body_pages != pages
                or len([r for r in records if r.kind == 'content']) != 1):
            raise RendererCompileError()
        expected = [(statement.id, row.id) for statement in report.detailed_statements for row in statement.rows]
        actual = [(record.statement_id, record.row_id) for record in records if record.kind == 'row']
        if actual != expected:
            raise RendererCompileError()
        content_pages = [record.page for record in records if record.kind != 'page']
        if content_pages != sorted(content_pages):
            raise RendererCompileError()
        return tuple(records)
