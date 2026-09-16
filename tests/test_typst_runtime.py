"""M2-01: real isolated compilation and forced process/error lifecycle checks."""
import hashlib
import json
import os
import signal
import sys
import threading
import time
from pathlib import Path

import fitz
import pytest

from app.renderers.typst import (
    Compiler, RendererBusy, RendererCompileError, RendererInputError,
    RendererInvalidPdf, RendererLimits, RendererTimeout, RendererUnavailable,
    TemplateBundle, TypstRenderer,
)
from app.renderers.typst.runtime import validate_pdf
from tests.test_final_report_v2 import fixture_report

ROOT = Path(__file__).resolve().parents[1]
SMOKE = ROOT / 'backend/app/renderers/typst/templates/runtime-smoke'


@pytest.fixture
def renderer(tmp_path):
    binary = Path(os.environ.get('TYPST_TEST_BINARY', ROOT / 'tools/typst/bin/typst'))
    if not binary.is_file():
        pytest.skip('Install pinned tools/typst compiler for runtime integration tests')
    compiler = Compiler.from_manifest(ROOT / 'tools/typst/manifest.json', binary)
    return TypstRenderer(compiler, TemplateBundle(SMOKE), temp_root=tmp_path)


def bundle(tmp_path, source):
    folder = tmp_path / 'template'
    folder.mkdir()
    (folder / 'template.typ').write_text(source)
    digest = hashlib.sha256(source.encode()).hexdigest()
    (folder / 'manifest.json').write_text(json.dumps({
        'version': 'test-1', 'entrypoint': 'template.typ', 'files': {'template.typ': digest},
    }))
    return TemplateBundle(folder)


@pytest.mark.parametrize('workflow', ['bilancio', 'infrannuale', 'startup'])
@pytest.mark.parametrize('draft,gray', [(True, False), (False, False), (True, True), (False, True)])
def test_real_compile_states_workflows_and_private_cleanup(renderer, tmp_path, workflow, draft, gray):
    report = fixture_report(workflow)
    artifact = renderer.render(report, document_state='draft' if draft else 'final', grayscale=gray)
    assert artifact.model_hash == report.model_hash and artifact.source_hash == report.source_hash
    assert artifact.artifact_sha256 == hashlib.sha256(artifact.data).hexdigest()
    assert artifact.schema_version == 2 and artifact.compiler_version == '0.15.1'
    with fitz.open(stream=artifact.data, filetype='pdf') as pdf:
        assert pdf.metadata['title'] == report.document.title
        assert ('BOZZA' in pdf[0].get_text()) == draft
    assert not list(tmp_path.iterdir())


def test_identical_frozen_model_produces_identical_bytes(renderer):
    report = fixture_report()
    assert renderer.render(report).data == renderer.render(report).data


def test_untrusted_strings_are_literal_data(renderer):
    report = fixture_report()
    report.company.name = '#panic("DO-NOT-EXECUTE") @preview/no-package:9.9.9'
    report.source_hash = report.calculate_source_hash()
    report.model_hash = report.calculate_model_hash()
    artifact = renderer.render(report)
    with fitz.open(stream=artifact.data, filetype='pdf') as pdf:
        assert 'DO-NOT-EXECUTE' in pdf[0].get_text()


@pytest.mark.parametrize('source', [
    '#read("/etc/passwd")',
    '#read("../host-secret.txt")',
    '#import "@preview/runtime-offline-negative-control:9.9.9": *',
    '#panic("SENSITIVE-CUSTOMER-CONTENT")',
])
def test_filesystem_network_and_diagnostics_fail_closed(renderer, tmp_path, caplog, source):
    (tmp_path / 'host-secret.txt').write_text('PRIVATE-HOST-DATA')
    renderer.bundle = bundle(tmp_path, source)
    with pytest.raises(RendererCompileError) as caught:
        renderer.render(fixture_report())
    assert 'PRIVATE' not in str(caught.value) and str(tmp_path) not in str(caught.value)
    assert 'SENSITIVE' not in caplog.text and 'PRIVATE' not in caplog.text
    assert not list(tmp_path.glob('budget-typst-*'))


def test_altered_binary_refused_before_execution(renderer, tmp_path, monkeypatch):
    path = tmp_path / 'compiler'
    path.write_bytes(renderer.compiler.verified_bytes() + b'altered')
    path.chmod(0o700)
    renderer.compiler = Compiler(path, renderer.compiler.version, renderer.compiler.binary_sha256)
    monkeypatch.setattr(renderer, '_run', lambda *a, **k: pytest.fail('Executed altered compiler'))
    with pytest.raises(RendererUnavailable):
        renderer.render(fixture_report())


@pytest.mark.parametrize('mutation', ['checksum', 'traversal', 'symlink', 'fifo', 'reserved', 'oversize'])
def test_bundle_verification_rejects_mutated_assets(tmp_path, mutation):
    asset = bundle(tmp_path, 'Hello')
    manifest = asset.path / 'manifest.json'
    metadata = json.loads(manifest.read_text())
    limits = RendererLimits()
    if mutation == 'checksum':
        (asset.path / 'template.typ').write_text('ALTERED')
    elif mutation == 'symlink':
        (tmp_path / 'outside.typ').write_text('Hello')
        (asset.path / 'template.typ').unlink()
        (asset.path / 'template.typ').symlink_to(tmp_path / 'outside.typ')
    elif mutation == 'fifo':
        (asset.path / 'template.typ').unlink()
        os.mkfifo(asset.path / 'template.typ')
    elif mutation in ('traversal', 'reserved'):
        name = '../outside.typ' if mutation == 'traversal' else 'model.json'
        metadata['files'] = {name: hashlib.sha256(b'Hello').hexdigest()}
        manifest.write_text(json.dumps(metadata))
    else:
        limits = RendererLimits(max_asset_bytes=4)
    with pytest.raises(RendererUnavailable):
        asset.read(limits)


def test_invalid_input_size_and_options(renderer):
    renderer.limits = RendererLimits(max_input_bytes=32)
    for options in ({}, {'document_state': 'unknown'}, {'grayscale': 'yes'}):
        with pytest.raises(RendererInputError):
            renderer.render(fixture_report(), **options)


def test_missing_sandbox_no_fallback_and_cleanup(renderer, tmp_path):
    renderer.sandbox = tmp_path / 'missing-bwrap'
    with pytest.raises(RendererUnavailable):
        renderer.render(fixture_report())
    assert not list(tmp_path.iterdir())


def test_real_compile_timeout_cleans_job(renderer, tmp_path):
    renderer.bundle = bundle(tmp_path, '#for i in range(100000) { [Repeated word #i] }')
    renderer.limits = RendererLimits(timeout_seconds=0.3)
    with pytest.raises(RendererTimeout):
        renderer.render(fixture_report())
    assert not list(tmp_path.glob('budget-typst-*'))


def test_timeout_kills_process_group_and_descendant(renderer, tmp_path):
    pidfile = tmp_path / 'descendant.pid'
    script = tmp_path / 'sleep.py'
    script.write_text('import subprocess,sys,time\n'
        'p=subprocess.Popen([sys.executable,"-c","import time;time.sleep(60)"])\n'
        f'open({str(pidfile)!r},"w").write(str(p.pid))\n'
        'time.sleep(60)\n')
    renderer.limits = RendererLimits(timeout_seconds=0.5)
    with pytest.raises(RendererTimeout):
        renderer._run([sys.executable, str(script)], tmp_path)
    pid = int(pidfile.read_text())
    # A terminated orphan may remain a zombie until the host reaps it.
    status = Path(f'/proc/{pid}/stat')
    for _ in range(30):
        if not status.exists() or status.read_text().split()[2] == 'Z':
            break
        time.sleep(0.02)
    else:
        os.kill(pid, signal.SIGKILL)
        pytest.fail('Descendant survived timeout')


def test_os_output_limit_is_enforced(renderer, tmp_path):
    renderer.limits = RendererLimits(max_output_bytes=1024)
    output = tmp_path / 'too-large'
    with pytest.raises(RendererCompileError):
        renderer._run([sys.executable, '-c', f'with open({str(output)!r},"wb") as f:\n f.write(b"x"*4096)\n f.flush()'], tmp_path)
    assert output.stat().st_size <= 1024


def test_concurrency_saturation_and_error_release(renderer, monkeypatch):
    entered = threading.Barrier(3)
    release = threading.Event()
    errors = []
    def blocked(*args, **kwargs):
        entered.wait(timeout=10)
        release.wait(timeout=10)
        raise RendererCompileError()
    monkeypatch.setattr(renderer, '_run', blocked)
    def request():
        try:
            renderer.render(fixture_report())
        except RendererCompileError:
            errors.append('compile')
    threads = [threading.Thread(target=request) for _ in range(2)]
    for thread in threads:
        thread.start()
    try:
        entered.wait(timeout=10)
        with pytest.raises(RendererBusy):
            renderer.render(fixture_report())
    finally:
        release.set()
        for thread in threads:
            thread.join(timeout=10)
    assert errors == ['compile', 'compile']
    assert renderer._slots.acquire(blocking=False)
    assert renderer._slots.acquire(blocking=False)
    renderer._slots.release(); renderer._slots.release()


@pytest.mark.parametrize('fault', ['header', 'eof', 'title', 'empty', 'size', 'pages', 'watermark'])
def test_pdf_validation_rejects_bad_output(fault):
    pdf = fitz.open()
    page = pdf.new_page(width=595.276, height=841.89)
    if fault != 'empty':
        page.insert_text((30, 30), 'Report Budget 2027' + ('' if fault == 'watermark' else ' BOZZA'))
    pdf.set_metadata({'title': 'wrong' if fault == 'title' else 'Report Budget 2027'})
    if fault == 'pages':
        pdf.new_page()
    data = pdf.tobytes(); pdf.close()
    if fault == 'header':
        data = b'NOT-PDF'
    if fault == 'eof':
        data = data[:-6]
    limits = RendererLimits(max_output_bytes=8) if fault == 'size' else RendererLimits(max_pages=1)
    with pytest.raises(RendererInvalidPdf):
        validate_pdf(data, title='Report Budget 2027', draft=True, limits=limits)


@pytest.mark.parametrize('option', [{'timeout_seconds': 0}, {'timeout_seconds': float('inf')},
                                  {'memory_bytes': True}, {'max_concurrent': -1}])
def test_invalid_limits_fail_at_configuration(option):
    with pytest.raises(ValueError):
        RendererLimits(**option)
