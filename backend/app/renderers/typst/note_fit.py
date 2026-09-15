"""Bounded native fit checks for the fixed editorial page-note footer."""
from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
import json
import os
import platform
import time
from pathlib import Path

from app.schemas.final_report_v2 import FinalReportModelV2

from .editorial_plan import DossierTemplateBundle
from .runtime import (
    Compiler, RendererBusy, RendererCompileError, RendererInputError,
    RendererTimeout, RendererUnavailable, RendererLimits, TemplateBundle,
    TypstRenderer, _regular, log,
)

_EXPRESSION = 'query(metadata).map(x => x.value)'
_ENTRYPOINT = 'note-fit.typ'
_INPUT = 'note-fit-input.json'
_OPTIONS = b'{"document_state":"draft","grayscale":false}'
_PT_PER_MM = Decimal(72) / Decimal('25.4')
_FOOTER_WIDTH = Decimal(178) * _PT_PER_MM
_FOOTER_HEIGHT = Decimal(18) * _PT_PER_MM


class NoteFitProbe(TypstRenderer):
    """Measure literal note strings using the installed editorial footer font.

    This intentionally does not inherit ``DossierLayoutProbe``: checking note
    text must not generate an inventory or make claims about physical pages.
    """

    def __init__(self, compiler: Compiler, bundle: DossierTemplateBundle, *,
                 limits: RendererLimits | None = None,
                 sandbox: Path = Path('/usr/bin/bwrap'), temp_root: Path | None = None):
        if not isinstance(bundle, DossierTemplateBundle):
            raise RendererUnavailable()
        super().__init__(compiler, bundle, limits=limits, sandbox=sandbox, temp_root=temp_root)

    def check_notes(self, report: FinalReportModelV2, texts: dict[str, str]) -> dict[str, bool]:
        """Return native fit results for the requested, known note IDs only."""
        started = time.monotonic()
        if not isinstance(report, FinalReportModelV2) or type(texts) is not dict:
            raise RendererInputError()
        if not self._slots.acquire(blocking=False):
            raise RendererBusy()
        try:
            frozen, serialized = self._freeze(report)
            selected = self._selected_notes(frozen, texts)
            if not selected:
                return {}
            payload = json.dumps({'notes': selected}, ensure_ascii=False, allow_nan=False,
                                 separators=(',', ':')).encode('utf-8')
            if len(serialized) + len(payload) > self.limits.max_input_bytes:
                raise RendererInputError()
            if platform.system() != 'Linux' or platform.machine() != 'x86_64':
                raise RendererUnavailable()
            version, files = self._note_fit_bundle()
            binary = self.compiler.verified_bytes()
            if not self.sandbox.is_file() or self.sandbox.is_symlink() or not os.access(self.sandbox, os.X_OK):
                raise RendererUnavailable()
            with self._private_job(serialized, files, binary, _OPTIONS, payload) as job:
                deadline = started + self.limits.timeout_seconds
                self._run(self._sandbox_command(job, ['/report/compiler', '--version']), job,
                          unavailable=True, deadline=deadline)
                command = [
                    '/report/compiler', 'eval', _EXPRESSION, '--in', f'/report/{_ENTRYPOINT}',
                    '--root', '/report', '--format', 'json', '--jobs', '1', '--ignore-system-fonts',
                    '--package-path', '/report/packages', '--package-cache-path', '/report/cache',
                    '--font-path', '/report/fonts', '--creation-timestamp',
                    str(int(frozen.generated_at.timestamp())), '--diagnostic-format', 'short',
                ]
                output = job / 'output/layout.json'
                self._run(self._sandbox_command(job, command), job, deadline=deadline, stdout_path=output)
                try:
                    result = self._validate_output(_regular(output, self.limits.max_output_bytes), selected)
                except RendererCompileError:
                    raise
                except RendererUnavailable:
                    raise RendererCompileError() from None
                if time.monotonic() > deadline:
                    raise RendererTimeout()
            log.info('typst_note_fit_success schema=%d notes=%d elapsed_ms=%d bundle=%s',
                     frozen.schema_version, len(result), int((time.monotonic() - started) * 1000), version)
            return result
        except (RendererBusy, RendererCompileError, RendererInputError, RendererTimeout, RendererUnavailable) as error:
            log.warning('typst_note_fit_failed category=%s', error.category)
            raise
        except (OSError, TypeError, ValueError, UnicodeError):
            log.warning('typst_note_fit_failed category=renderer_unavailable')
            raise RendererUnavailable() from None
        finally:
            self._slots.release()

    @staticmethod
    def _freeze(report: FinalReportModelV2) -> tuple[FinalReportModelV2, bytes]:
        """Check mutable in-memory hashes before serializing the render input."""
        try:
            if (report.source_hash != report.calculate_source_hash()
                    or report.model_hash != report.calculate_model_hash()):
                raise ValueError()
            serialized = report.model_dump_json().encode('utf-8')
            frozen = FinalReportModelV2.model_validate_json(serialized)
            if (frozen.source_hash != frozen.calculate_source_hash()
                    or frozen.model_hash != frozen.calculate_model_hash()
                    or frozen.editorial_plan is None
                    or frozen.editorial_plan.source_hash != frozen.source_hash
                    or frozen.editorial_plan.plan_hash != frozen.editorial_plan.calculate_plan_hash()):
                raise ValueError()
            return frozen, serialized
        except Exception:
            raise RendererInputError() from None

    @staticmethod
    def _selected_notes(report: FinalReportModelV2, texts: dict[str, str]) -> list[dict[str, object]]:
        plan = report.editorial_plan
        if plan is None:  # guarded by _freeze; keeps this helper total.
            raise RendererInputError()
        expected = {page.note_id for page in plan.pages}
        if (any(type(note_id) is not str or type(text) is not str for note_id, text in texts.items())
                or any(note_id not in expected for note_id in texts)):
            raise RendererInputError()
        selected = []
        for page in plan.pages:
            if page.note_id not in texts:
                continue
            slot = page.note_slot
            if (not isinstance(slot.width_pt, Decimal) or not slot.width_pt.is_finite()
                    or abs(slot.width_pt - _FOOTER_WIDTH) > Decimal('0.001')
                    or not isinstance(slot.height_pt, Decimal) or not slot.height_pt.is_finite()
                    or abs(slot.height_pt - _FOOTER_HEIGHT) > Decimal('0.001')
                    or not isinstance(slot.font_size_pt, Decimal) or slot.font_size_pt != Decimal('9')
                    or type(slot.max_lines) is not int or slot.max_lines != 4):
                raise RendererInputError()
            selected.append({
                'id': page.note_id,
                'text': texts[page.note_id],
                'width_pt': format(slot.width_pt, 'f'),
                'height_pt': format(slot.height_pt, 'f'),
                'font_size_pt': format(slot.font_size_pt, 'f'),
                'max_lines': slot.max_lines,
            })
        return selected

    def _note_fit_bundle(self) -> tuple[str, dict[str, bytes]]:
        # Bypass the dossier bundle's normal editorial entrypoint only; all
        # bytes still come from its signed manifest and remain internal assets.
        version, _, files = TemplateBundle.read(self.bundle, self.limits)
        if _ENTRYPOINT not in files or _INPUT in files:
            raise RendererUnavailable()
        return version, files

    @contextmanager
    def _private_job(self, serialized: bytes, files: dict[str, bytes], binary: bytes,
                     options: bytes, note_input: bytes):
        if _INPUT in files:
            raise RendererUnavailable()
        if (len(files) + 1 > self.limits.max_assets
                or sum(map(len, files.values())) + len(note_input) > self.limits.max_asset_bytes):
            raise RendererInputError()
        with super()._private_job(serialized, files, binary, options) as job:
            try:
                destination = job / _INPUT
                fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(note_input)
            except OSError:
                raise RendererUnavailable() from None
            yield job

    @staticmethod
    def _validate_output(raw: bytes, selected: list[dict[str, object]]) -> dict[str, bool]:
        try:
            values = json.loads(raw)
            if not isinstance(values, list) or len(values) != len(selected):
                raise ValueError()
            expected = {str(item['id']): item for item in selected}
            result: dict[str, bool] = {}
            required = {'id', 'fits', 'width_pt', 'height_pt', 'font_size_pt', 'max_lines'}
            for value in values:
                if (not isinstance(value, dict) or set(value) != required
                        or type(value.get('id')) is not str or type(value.get('fits')) is not bool
                        or value['id'] not in expected or value['id'] in result):
                    raise ValueError()
                source = expected[value['id']]
                if (value['width_pt'] != source['width_pt'] or value['height_pt'] != source['height_pt']
                        or value['font_size_pt'] != source['font_size_pt']
                        or value['max_lines'] != source['max_lines']):
                    raise ValueError()
                result[value['id']] = value['fits']
            if set(result) != set(expected):
                raise ValueError()
            # Stable plan order is part of the request/result binding.
            return {str(item['id']): result[str(item['id'])] for item in selected}
        except (TypeError, ValueError, KeyError, json.JSONDecodeError):
            raise RendererCompileError() from None
