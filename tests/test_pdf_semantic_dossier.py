"""M2-04: semantic, pagination-independent verification of the compiled dossier PDF.

This harness targets the *contract* the template must meet, checked with a
tool the renderer itself does not use (poppler-utils, not PyMuPDF — see
`tests/pdf_semantic/__init__.py`). Every test is green against the fixtures of
all three workflows, including the forbidden-technical-strings check: it was
marked `xfail(strict=True)` while M2-02B was rebuilding the template in
parallel (the ID/unit/source leaks it caught are listed in
`docs/testing/M2-04-pdf-semantic.md`); M2-02B's integration removed the xfail
once the template stopped printing them.

Reuses `tests.test_typst_editorial_plan`'s own fixture/plan/note construction
(`fixture_report`, `prepare_editorial_report`, `verify_editorial_layout`,
`with_notes`) instead of re-implementing it — that module is the authority on
how a v2 report gets a frozen editorial plan and per-page notes.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import pytest

from app.renderers.typst import Compiler
from app.renderers.typst.dossier_catalog import build_inventory
from app.renderers.typst.editorial_plan import (
    DossierLayoutProbe, DossierTemplateBundle, prepare_editorial_report, verify_editorial_layout,
)
from app.schemas.final_report_v2 import FinalReportModelV2
from tests.pdf_semantic import (
    assert_all_fonts_embedded, assert_appendix_row_count_matches_plan, assert_draft_watermark,
    assert_metadata_title, assert_no_field_code_style_labels, assert_no_forbidden_technical_strings,
    assert_not_encrypted, assert_page_count, assert_pdf_signature, assert_text_present,
    format_euro_integer, page_text_range, pdf_fonts, pdf_info, poppler_available, raw_page_texts,
)
from tests.test_final_report_v2 import fixture_report
from tests.test_typst_editorial_plan import with_notes

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'backend/app/renderers/typst/templates/dossier-base'
BWRAP = Path('/usr/bin/bwrap')
WORKFLOWS = ('infrannuale', 'bilancio', 'startup')
YEARS = [2027, 2028, 2029]


@pytest.fixture(scope='module')
def probe(tmp_path_factory):
    binary = Path(os.environ.get('TYPST_TEST_BINARY', ROOT / 'tools/typst/bin/typst'))
    if not binary.is_file():
        pytest.skip('Install pinned compiler for the PDF semantic harness')
    if not BWRAP.is_file():
        pytest.skip('bwrap sandbox not available')
    if not poppler_available():
        pytest.skip('poppler-utils (pdftotext/pdffonts/pdfinfo) not available')
    return DossierLayoutProbe(Compiler.from_manifest(ROOT / 'tools/typst/manifest.json', binary),
                              DossierTemplateBundle(BASE), temp_root=tmp_path_factory.mktemp('pdf-semantic-probe'))


@dataclass
class CompiledDossier:
    workflow: str
    report: FinalReportModelV2
    draft_path: Path
    final_path: Path
    page_count: int


@pytest.fixture(scope='module', params=WORKFLOWS)
def dossier(request, probe, tmp_path_factory) -> CompiledDossier:
    """Compile once per workflow; every test function below reuses the same artefact.

    Compiling is the slow part (real Typst, real bwrap sandbox): sharing one
    compiled pair of PDFs (draft + final) per workflow across all the checks in
    this module keeps the suite in the tens of seconds instead of minutes.
    """
    workflow = request.param
    original = fixture_report(workflow, YEARS)
    prepared = prepare_editorial_report(original, probe)
    report = with_notes(prepared)
    verify_editorial_layout(report, probe)
    draft = probe.render(report, document_state='draft')
    final = probe.render(report, document_state='final')
    assert draft.page_count == final.page_count == len(report.editorial_plan.pages)
    root = tmp_path_factory.mktemp(f'pdf-semantic-{workflow}')
    draft_path = root / 'draft.pdf'
    draft_path.write_bytes(draft.data)
    final_path = root / 'final.pdf'
    final_path.write_bytes(final.data)
    return CompiledDossier(workflow=workflow, report=report, draft_path=draft_path,
                            final_path=final_path, page_count=draft.page_count)


def _row_pages(report: FinalReportModelV2) -> dict[str, int]:
    """Map every editorial content marker to its 1-based physical page."""
    mapping: dict[str, int] = {}
    for number, page in enumerate(report.editorial_plan.pages, start=1):
        for content_id in page.content_ids:
            mapping[content_id] = number
    return mapping


# --------------------------------------------------------------------------
# %PDF, metadata, fonts, page count
# --------------------------------------------------------------------------

def test_pdf_signature_metadata_and_page_count_match_the_editorial_plan(dossier):
    data = dossier.draft_path.read_bytes()
    assert_pdf_signature(data)
    info = pdf_info(dossier.draft_path)
    assert_not_encrypted(info)
    assert_metadata_title(info, dossier.report.document.title)
    assert_page_count(info, dossier.page_count)


def test_all_fonts_are_embedded_in_draft_and_final(dossier):
    for path in (dossier.draft_path, dossier.final_path):
        assert_all_fonts_embedded(pdf_fonts(path))


# --------------------------------------------------------------------------
# text content: cover, Allegati rows, notes
# --------------------------------------------------------------------------

def test_cover_shows_the_neutral_document_title(dossier):
    pages = raw_page_texts(dossier.draft_path, expected_pages=dossier.page_count)
    assert_text_present(pages[0], dossier.report.document.title, context='cover page')


def test_every_applicable_appendix_row_is_on_its_assigned_page_with_integer_euro_values(dossier):
    pages = raw_page_texts(dossier.draft_path, expected_pages=dossier.page_count)
    row_pages = _row_pages(dossier.report)
    checked_values = 0
    for statement in dossier.report.detailed_statements:
        for row in statement.rows:
            content_id = f'row:{statement.id}:{row.id}'
            page_number = row_pages[content_id]
            page_text = pages[page_number - 1]
            assert_text_present(page_text, row.label, context=f'{content_id} label on page {page_number}')
            if row.kind in ('detail', 'subtotal', 'total') and row.applicable:
                for value in row.values:
                    if value is not None:
                        assert_text_present(page_text, format_euro_integer(value),
                                             context=f'{content_id} value on page {page_number}')
                        checked_values += 1
        assert_appendix_row_count_matches_plan(statement.id, [row.id for row in statement.rows], row_pages)
    # A regression that emptied every statement would still pass an empty loop;
    # this is the corpus's own floor, not an arbitrary number.
    assert checked_values > 0


def test_every_physical_page_shows_its_assigned_note(dossier):
    assert len(dossier.report.editorial_notes) == dossier.page_count
    for index, note in enumerate(dossier.report.editorial_notes, start=1):
        page_text = page_text_range(dossier.draft_path, index, index)
        assert_text_present(page_text, note.text, context=f'note on physical page {index}')


# --------------------------------------------------------------------------
# watermark
# --------------------------------------------------------------------------

def test_draft_pages_carry_the_watermark_and_final_pages_do_not(dossier):
    draft_pages = raw_page_texts(dossier.draft_path, expected_pages=dossier.page_count)
    final_pages = raw_page_texts(dossier.final_path, expected_pages=dossier.page_count)
    for number, page_text in enumerate(draft_pages, start=1):
        assert_draft_watermark(page_text, draft=True)
    for number, page_text in enumerate(final_pages, start=1):
        assert_draft_watermark(page_text, draft=False)


# --------------------------------------------------------------------------
# conditional sections
# --------------------------------------------------------------------------
# Il vecchio test qui verificava che il testo «Il confronto non annualizza
# gli importi infrannuali» comparisse solo sul workflow infrannuale: quel
# testo veniva dal blocco «Rettifiche» del vecchio inventario generico, non
# ancora reintrodotto — dati.py ha registro vuoto in questa fase (fondazione
# M2-02D). Resta però vera, e verificabile senza quel testo, la garanzia più
# generale: nessuna pagina del catalogo di questa fase dichiara
# `infrannual_closing` come proprio id (nessuna pagina di quel gruppo esiste
# ancora), su nessuno dei tre workflow — un futuro dati.py che implementa
# quelle pagine dovrà reintrodurre anche la loro verifica testuale.

def test_no_page_declares_infrannual_closing_before_dati_py_implements_it(dossier):
    page_ids = {page.section_id for page in dossier.report.editorial_plan.pages}
    assert 'infrannual_closing' not in page_ids


# --------------------------------------------------------------------------
# forbidden technical strings — fails on the current (M2-02) template on purpose
# --------------------------------------------------------------------------

def test_no_forbidden_technical_strings_leak_into_the_dossier(dossier):
    full_text = ' '.join(raw_page_texts(dossier.draft_path, expected_pages=dossier.page_count))
    assert_no_forbidden_technical_strings(full_text)


# --------------------------------------------------------------------------
# field-code-style labels — M2-02B integrazione, rilievo del coordinatore su AMBIENTA
# --------------------------------------------------------------------------
# A curated fixture's forecast lines already carry a real Italian label, so
# this never turns red against `dossier`. Since M2-02D the pages implemented
# read `DetailedStatementRow.label` directly (no resolve-or-raise step to
# bypass any more — see `assert_no_field_code_style_labels`'s own docstring),
# so there is no dedicated mutation test proving this specific leak shape any
# more: the shape it used to guard cannot occur on these pages by
# construction. This test remains the harness's own, independent check that
# nothing *else* on the page reads like a field/model code.

def test_no_field_code_style_labels_leak_into_the_dossier(dossier):
    full_text = ' '.join(raw_page_texts(dossier.draft_path, expected_pages=dossier.page_count))
    assert_no_field_code_style_labels(full_text)


# --------------------------------------------------------------------------
# column count — vincolo del proprietario, 2026-09-17
# --------------------------------------------------------------------------

def test_no_table_exceeds_five_value_columns(dossier):
    """«Nessuna tabella del PDF supera 5 colonne di valori (più la colonna
    voce)» — verificato qui sull'esatto inventario che ha prodotto il PDF
    compilato (`dossier.report`), non su una fixture separata."""
    for page in build_inventory(dossier.report):
        for item in page['items']:
            if item['kind'] != 'table':
                continue
            value_columns = len(item['columns']) - 1
            assert value_columns <= 5, (page['id'], item['id'], item['columns'])


# --------------------------------------------------------------------------
# mutation test: prove the two riskiest checks above are actually sensitive
# --------------------------------------------------------------------------

def test_harness_fails_when_a_row_or_a_note_is_missing_from_the_rendered_text(dossier):
    """Mutates a COPY of the already-rendered report in memory; never touches the template.

    The PDFs on `dossier` were compiled once from the unmutated report and are
    reused, unchanged, by every test in this module — so any divergence found
    here comes only from the in-memory mutation, exactly as the brief asks
    ("modifica in memoria il modello, non il template").
    """
    pages = raw_page_texts(dossier.draft_path, expected_pages=dossier.page_count)
    row_pages = _row_pages(dossier.report)

    # --- Baseline: the real row and the real note ARE on the real PDF (same
    #     helper the green-path tests use, so the baseline and the mutation
    #     below are checked exactly the same way). ---
    statement = next(s for s in dossier.report.detailed_statements if s.id == 'income_statement')
    row = next(r for r in statement.rows if r.id == 'income_statement:ce01_ricavi_vendite')
    content_id = f'row:{statement.id}:{row.id}'
    page_number = row_pages[content_id]
    page_text = pages[page_number - 1]
    assert_text_present(page_text, row.label, context=f'{content_id} baseline on page {page_number}')
    note_page_text = page_text_range(dossier.draft_path, 1, 1)
    assert_text_present(note_page_text, dossier.report.editorial_notes[0].text, context='note baseline on physical page 1')

    # --- Mutation 1: relabel a row in a deep copy of the model. The rendered
    #     page still shows the ORIGINAL label (it was compiled before the
    #     mutation): the harness must flag the mismatch. ---
    mutated = dossier.report.model_copy(deep=True)
    mutated_statement = next(s for s in mutated.detailed_statements if s.id == 'income_statement')
    mutated_row = next(r for r in mutated_statement.rows if r.id == 'income_statement:ce01_ricavi_vendite')
    mutated_row.label = 'RIGA CHE IL TEMPLATE NON STAMPA PIÙ'
    with pytest.raises(AssertionError):
        assert_text_present(page_text, mutated_row.label, context=f'{content_id} on page {page_number}')

    # --- Mutation 2: drop that same row from the model's own row list. The
    #     plan/PDF still carry the original marker: the count check must fail. ---
    remaining_ids = [r.id for r in mutated_statement.rows if r.id != 'income_statement:ce01_ricavi_vendite']
    with pytest.raises(AssertionError):
        assert_appendix_row_count_matches_plan('income_statement', remaining_ids, row_pages)

    # --- Mutation 3: change the text of the page-1 note in a deep copy. The
    #     rendered page still shows the ORIGINAL text: the harness must flag it. ---
    mutated_note = dossier.report.editorial_notes[0].model_copy(deep=True)
    mutated_note.text = 'NOTA CHE NON COMPARE SU QUESTA PAGINA'
    with pytest.raises(AssertionError):
        assert_text_present(note_page_text, mutated_note.text, context='note on physical page 1')
