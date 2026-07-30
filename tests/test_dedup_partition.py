"""Prefix-free partition selection for the contra-netting scan.

AGO prints mastri as 8-digit codes and their sub-accounts as 9-digit codes.
Neither is a prefix of the other, so the historical startswith() dedup summed
both levels: on 613_2024 that over-read attivo by 41.613,46 and fondi by
393.916,50, which made net_contra_accounts no-op and left 2,25M of fondi
ammortamento booked as debts.
"""
import os
import sys
from decimal import Decimal

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from importers.situazione_contabile_parser import (  # noqa: E402
    _code_depth,
    _select_dedup,
)

D = Decimal

PDF_613 = os.path.join(
    ROOT, "docs", "examples",
    "613_2024 Costruzione di edifici residenziali e non residenziali.pdf",
)


def test_code_depth_uses_segments_for_dotted_codes():
    assert _code_depth("03") == 1
    assert _code_depth("03.01") == 2
    assert _code_depth("03.01.07") == 3


def test_code_depth_uses_length_for_flat_codes():
    assert _code_depth("13095000") == 8
    assert _code_depth("101080000") == 9


def test_code_depth_of_empty_code_is_zero():
    assert _code_depth("") == 0


def test_selection_prefers_the_partition_matching_the_declared_total():
    # mastri (8-digit) sum to 1000 == declared; details (9-digit) duplicate 300 of it
    rows = [
        ("13095000", "ATTREZZATURE", D("300")),
        ("101080000", "ATTREZZATURA VARIA", D("300")),
        ("13085000", "FABBRICATI", D("700")),
    ]
    label, dedup_fn, reconciled = _select_dedup(rows, D("1000"))
    assert reconciled is True
    kept = dedup_fn(rows)
    assert sum(a for _c, _d, a in kept) == D("1000")


def test_selection_reports_not_reconciled_when_nothing_matches():
    rows = [("13095000", "ATTREZZATURE", D("300"))]
    label, dedup_fn, reconciled = _select_dedup(rows, D("999999"))
    assert reconciled is False


def test_selection_without_a_declared_total_keeps_legacy_behaviour():
    rows = [("13095000", "ATTREZZATURE", D("300"))]
    label, dedup_fn, reconciled = _select_dedup(rows, None)
    assert label == "existing"
    assert reconciled is False


@pytest.mark.skipif(not os.path.exists(PDF_613), reason="evidence PDF not present")
def test_613_partition_reproduces_the_declared_total_exactly():
    from importers.situazione_contabile_parser import _contra_rows
    attivo_rows, _passivo_rows, _from_ocr = _contra_rows(PDF_613)
    label, dedup_fn, reconciled = _select_dedup(attivo_rows, D("4979885.27"))
    assert reconciled is True
    kept = dedup_fn(attivo_rows)
    assert sum(a for _c, _d, a in kept) == D("4979885.27")
