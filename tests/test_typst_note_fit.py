"""Native, sandboxed bounds checks for editorial page notes."""
import os
from pathlib import Path

import pytest

from app.renderers.typst import Compiler, RendererCompileError, RendererInputError, RendererLimits, TemplateBundle
from app.renderers.typst.editorial_plan import DossierLayoutProbe, DossierTemplateBundle, prepare_editorial_report
from app.renderers.typst.note_fit import NoteFitProbe
from app.schemas.final_report_v2 import EditorialNote, FinalReportModelV2
from tests.test_final_report_v2 import fixture_report

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'backend/app/renderers/typst/templates/dossier-base'


def signed(report):
    report.source_hash = report.calculate_source_hash()
    report.model_hash = report.calculate_model_hash()
    return FinalReportModelV2.model_validate_json(report.model_dump_json())


@pytest.fixture
def probes(tmp_path):
    binary = Path(os.environ.get('TYPST_TEST_BINARY', ROOT / 'tools/typst/bin/typst'))
    if not binary.is_file():
        pytest.skip('Install pinned compiler for native note-fit tests')
    compiler = Compiler.from_manifest(ROOT / 'tools/typst/manifest.json', binary)
    bundle = DossierTemplateBundle(BASE)
    report = prepare_editorial_report(fixture_report(), DossierLayoutProbe(compiler, bundle, temp_root=tmp_path))
    return NoteFitProbe(compiler, bundle, temp_root=tmp_path), report, tmp_path


def _note_report(report, text):
    changed = report.model_copy(deep=True)
    changed.editorial_notes = [EditorialNote(
        id=page.note_id, content_ids=page.content_ids, text=text, provenance='automatic',
        updated_at=changed.generated_at, source_hash=changed.source_hash,
        plan_hash=changed.editorial_plan.plan_hash, revision=1, freshness='fresh',
    ) for page in changed.editorial_plan.pages]
    changed.editorial_readiness.status = 'ready'
    changed.editorial_readiness.reasons = []
    return signed(changed)


def test_native_footer_boundary_is_four_lines_not_five(probes):
    probe, report, _ = probes
    note_id = report.editorial_plan.pages[0].note_id
    four = '\n'.join(['Commento breve e leggibile.'] * 4)
    five = '\n'.join(['Commento breve e leggibile.'] * 5)
    assert probe.check_notes(report, {note_id: four}) == {note_id: True}
    assert probe.check_notes(report, {note_id: five}) == {note_id: False}
    # The fitting result is directly compatible with the real footer, rather
    # than a separate CSS-like approximation.
    DossierLayoutProbe(probe.compiler, probe.bundle, temp_root=probe.temp_root).render(_note_report(report, four))


def test_wrapped_italian_prose_matches_the_actual_footer_boundary(probes):
    probe, report, _ = probes
    note_id = report.editorial_plan.pages[0].note_id
    phrase = 'La pianificazione italiana richiede attenzione ai margini e alla liquidità.'
    fitting = ' '.join([phrase] * 8)
    overflowing = ' '.join([phrase] * 9)
    assert probe.check_notes(report, {note_id: fitting}) == {note_id: True}
    assert probe.check_notes(report, {note_id: overflowing}) == {note_id: False}
    renderer = DossierLayoutProbe(probe.compiler, probe.bundle, temp_root=probe.temp_root)
    renderer.render(_note_report(report, fitting))
    with pytest.raises(RendererCompileError):
        renderer.render(_note_report(report, overflowing))


def test_unbreakable_words_and_literal_markup_are_measured_as_plain_text(probes):
    probe, report, _ = probes
    note_id = report.editorial_plan.pages[0].note_id
    assert probe.check_notes(report, {note_id: 'W' * 300}) == {note_id: False}
    assert probe.check_notes(report, {note_id: ''}) == {note_id: False}
    literal = '#read("/definitely-not-staged/external.typ") [testo letterale]'
    assert probe.check_notes(report, {note_id: literal}) == {note_id: True}


def test_only_known_requested_ids_are_accepted(probes):
    probe, report, _ = probes
    known = report.editorial_plan.pages[0].note_id
    assert probe.check_notes(report, {known: 'Nota valida.'}) == {known: True}
    with pytest.raises(RendererInputError):
        probe.check_notes(report, {known: 'Nota valida.', 'outside-plan': 'Non misurare.'})


def test_input_output_failures_leave_no_private_job(probes):
    probe, report, temp_root = probes
    note_id = report.editorial_plan.pages[0].note_id
    probe.limits = RendererLimits(max_input_bytes=1)
    with pytest.raises(RendererInputError):
        probe.check_notes(report, {note_id: 'Nota valida.'})
    assert not list(temp_root.glob('budget-typst-*'))

    probe.limits = RendererLimits(max_output_bytes=1)
    with pytest.raises(RendererCompileError):
        probe.check_notes(report, {note_id: 'Nota valida.'})
    assert not list(temp_root.glob('budget-typst-*'))


@pytest.mark.parametrize('limit', ['bytes', 'files'])
def test_controlled_note_input_counts_toward_asset_limits_before_staging(probes, limit):
    probe, report, temp_root = probes
    _, _, files = TemplateBundle.read(probe.bundle, RendererLimits())
    if limit == 'bytes':
        probe.limits = RendererLimits(max_asset_bytes=sum(map(len, files.values())))
    else:
        probe.limits = RendererLimits(max_assets=len(files))
    with pytest.raises(RendererInputError):
        probe.check_notes(report, {report.editorial_plan.pages[0].note_id: 'Nota valida.'})
    assert not list(temp_root.glob('budget-typst-*'))
