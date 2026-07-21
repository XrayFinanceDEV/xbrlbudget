"""Contrapposte 8-digit: the column split axis must follow the page layout.

`parse_entries_contrapposte_8digit` was written for a ROTATED contrapposte page,
where the two columns are separated along y and a "row" runs along x. AGO
"Situazione Contabile" exports are landscape but NOT rotated (budget_615:
rotation=0, ATTIVITA' x=156.12 y=90.74 / PASSIVITA' x=574.55 y=90.74 — same y).

Splitting those by y put every word of BOTH columns in `left` and nothing in
`right`, so the passivo column vanished (observed: totale_attivo=382558.51,
totale_passivo=0). The axis must be picked from the axis on which the two
column headers actually differ.
"""
import os
from decimal import Decimal

import pytest

from importers.situazione_contabile_parser import (
    _c8_parse_side,
    parse_entries_contrapposte_8digit,
)

# budget_615: AGO "Situazione Contabile" contrapposte, NOT rotated. Its SP spans
# pages 0-1 and its CE pages 3-7, but only page 1 carries live ATTIVITA'/PASSIVITA'
# header text tokens — every other page's headers/footers are drawn as vectors, so
# the parser used to read page 1 ALONE (attivo ~396k vs declared 2.828.226,30).
# Verified targets from docs/piano-import-2026-07/13-DIAGNOSI-budget_615-AGO-CONTRAPPOSTE.md
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PDF_615_CANDIDATES = (
    os.path.join(_ROOT, "tests", "debug", "budget_615_2024 Lavori di meccanica generale.pdf"),
    os.path.join(_ROOT, "Test", "july_budget", "budget_615_2024 Lavori di meccanica generale.pdf"),
)
PDF_615 = next((path for path in _PDF_615_CANDIDATES if os.path.exists(path)),
               _PDF_615_CANDIDATES[0])


def _word(x0, y0, x1, y1, text):
    return (x0, y0, x1, y1, text, 0, 0, 0)


def _unrotated_page_words():
    """Landscape, rotation=0: columns split by x, rows run along y (budget_615)."""
    return [
        # --- attivo column (x < 400) ---
        _word(12, 110, 60, 118, "13080000"),
        _word(62, 110, 100, 118, "Terreni"),
        _word(300, 110, 340, 118, "454.053,24"),
        _word(12, 130, 60, 138, "13085000"),
        _word(62, 130, 100, 138, "Fabbricati"),
        _word(300, 130, 345, 138, "1.301.228,05"),
        # --- passivo column (x > 400) ---
        _word(443, 110, 490, 118, "31000000"),
        _word(492, 110, 530, 118, "Capitale"),
        _word(760, 110, 800, 118, "10.000,00"),
        _word(443, 130, 490, 138, "37030000"),
        _word(492, 130, 560, 138, "Debiti"),
        _word(760, 130, 800, 138, "131.658,89"),
    ]


def test_unrotated_page_splits_columns_by_x():
    words = _unrotated_page_words()
    mid = 400.0

    attivo = _c8_parse_side(words, -1e9, mid, axis=0)
    passivo = _c8_parse_side(words, mid, 1e9, axis=0)

    assert [e.code for e in attivo] == ["13080000", "13085000"]
    assert sum(e.amount for e in attivo) == Decimal("1755281.29")
    assert [e.code for e in passivo] == ["31000000", "37030000"]
    assert sum(e.amount for e in passivo) == Decimal("141658.89")
    # the passivo column must NOT be empty — this is the budget_615 failure
    assert passivo, "passivo column collapsed to nothing"


def test_rotated_page_still_splits_by_y():
    """The pre-existing rotated layout must keep working unchanged (axis=1)."""
    words = [
        # column A: y < 300 ; a "row" runs along x, read bottom-to-top
        _word(100, 200, 140, 208, "13080000"),
        _word(100, 180, 140, 188, "Terreni"),
        _word(100, 100, 140, 108, "454.053,24"),
        # column B: y > 300
        _word(100, 500, 140, 508, "31000000"),
        _word(100, 480, 140, 488, "Capitale"),
        _word(100, 400, 140, 408, "10.000,00"),
    ]
    mid = 300.0

    left = _c8_parse_side(words, mid, 1e9, axis=1)
    right = _c8_parse_side(words, -1e9, mid, axis=1)

    assert [e.code for e in left] == ["31000000"]
    assert left[0].amount == Decimal("10000.00")
    assert [e.code for e in right] == ["13080000"]
    assert right[0].amount == Decimal("454053.24")


def test_axis_defaults_to_rotated_for_existing_callers():
    """Default must stay axis=1 so untouched call sites behave identically."""
    words = [
        _word(100, 200, 140, 208, "13080000"),
        _word(100, 180, 140, 188, "Terreni"),
        _word(100, 100, 140, 108, "454.053,24"),
    ]
    assert _c8_parse_side(words, -1e9, 300.0) == _c8_parse_side(words, -1e9, 300.0, axis=1)


def _section_sum(entries, section):
    return sum((e.amount for e in entries if e.section == section and e.amount), Decimal("0"))


@pytest.mark.skipif(not os.path.exists(PDF_615), reason="budget_615 debug PDF not present")
def test_615_reads_every_page_not_just_the_one_with_headers():
    """Step 2+3: header-less SP/CE pages must be read via the document-level gutter,
    with the SP->CE boundary found by OIC account recognition (not code prefixes),
    so the gross section totals reconcile to the declared TOTALE ATTIVITA'/COSTI/
    RICAVI (footer totals are vector-drawn)."""
    entries = parse_entries_contrapposte_8digit(PDF_615)

    # gross attivo mastri reconcile to the declared TOTALE ATTIVITA' exactly
    assert _section_sum(entries, "attivo") == Decimal("2828226.30")
    # CE mastri reconcile to the declared TOTALE COSTI / TOTALE RICAVI exactly
    assert _section_sum(entries, "costi") == Decimal("1323220.24")
    assert _section_sum(entries, "ricavi") == Decimal("1456925.50")
    # utile = ricavi - costi, derived from the CE when the SP footer is unreadable
    utile = [e for e in entries if e.code == "****"]
    assert utile and utile[0].amount == Decimal("133705.26")


@pytest.mark.skipif(not os.path.exists(PDF_615), reason="budget_615 debug PDF not present")
def test_615_orphan_recovery_balances_the_sheet():
    """Step 4+5: the two passivo mastri whose 8-digit total line is drawn as a
    vector (Altri debiti 2.000 + Ratei/risconti passivi 53.536,60 = 55.536,60) are
    recovered from their CLEAN 6-digit dettagli, gated on the SP balancing exactly,
    so the sheet ties (Assets == Equity + Liabilities)."""
    from importers.situazione_contabile_parser import extract_situazione_contabile

    bs, _ce = extract_situazione_contabile(PDF_615)
    ta = bs.get("totale_attivo") or Decimal("0")
    tp = bs.get("totale_passivo") or Decimal("0")
    assert abs(ta - tp) <= Decimal("1"), f"unbalanced: attivo={ta} passivo={tp}"
    # Ratei e risconti passivi was entirely missing (mastro vector) — recovered.
    # extract_situazione_contabile returns the SC parser's SHORT aggregate keys.
    assert bs.get("sp18") == Decimal("53536.60")
    assert bs.get("sp13") == Decimal("133705.26")
