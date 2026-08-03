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
    _dedup_parent_child,
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


def test_winning_rule_applies_to_a_side_that_lacks_the_winning_depth():
    """The rule chosen on the attivo must apply UNCHANGED to the other sides.

    _select_dedup is scored on the attivo rows, but the callable it returns is
    also handed the passivo rows and the fondi subset. If the winner is
    re-derived from whatever rows it is given, a side that happens to contain
    no code of the winning depth yields no such candidate and the callable
    silently degrades to the legacy `c.startswith(code)` PREFIX dedup — the
    very rule this partition exists to eliminate. Depth may only ever be a
    hypothesis corroborated by a printed total; a prefix must never decide.
    """
    attivo = [
        ("13095000", "ATTREZZATURE", D("300")),
        ("101080000", "ATTREZZATURA VARIA", D("300")),
        ("13085000", "FABBRICATI", D("700")),
    ]
    label, dedup_fn, reconciled = _select_dedup(attivo, D("1000"))
    assert (label, reconciled) == ("depth<=8", True)

    # Passivo side of the same scan: only 9-deep codes, no 8-deep one at all.
    passivo = [
        ("101080000", "FONDO AMM ATTREZZATURA", D("300")),
        ("101090000", "FONDO AMM FABBRICATI", D("200")),
    ]
    # The legacy prefix dedup finds no parent/child pair here and keeps both
    # rows — that is exactly the fallback we must NOT get.
    assert len(_dedup_parent_child(passivo)) == 2

    kept = dedup_fn(passivo)
    assert kept == [], (
        "the depth<=8 rule must still be applied to a side with no 8-deep "
        f"code; got {kept!r} (prefix-dedup fallback)"
    )


def test_winning_rule_applies_to_a_subset_with_no_matching_depth():
    """Same failure mode one level deeper: _contra_classify re-applies the
    dedup to the fondi SUBSET of the rows inside _reduce_fondi."""
    attivo = [
        ("13095000", "ATTREZZATURE", D("300")),
        ("101080000", "ATTREZZATURA VARIA", D("300")),
        ("13085000", "FABBRICATI", D("700")),
    ]
    _label, dedup_fn, _ok = _select_dedup(attivo, D("1000"))
    subset = [r for r in attivo if _code_depth(r[0]) == 9]
    assert dedup_fn(subset) == []


def test_legacy_winner_is_still_the_historical_dedup():
    """The 'existing' winner legitimately IS _dedup_parent_child — the
    no-declared-total / nothing-reconciles fallback must keep it."""
    rows = [("13095000", "ATTREZZATURE", D("300"))]
    for declared in (None, D("0"), D("999999")):
        label, dedup_fn, reconciled = _select_dedup(rows, declared)
        assert (label, dedup_fn, reconciled) == (
            "existing", _dedup_parent_child, False)


@pytest.mark.skipif(not os.path.exists(PDF_613), reason="evidence PDF not present")
def test_613_partition_reproduces_the_declared_total_exactly():
    from importers.situazione_contabile_parser import _contra_rows
    attivo_rows, _passivo_rows, _from_ocr = _contra_rows(PDF_613)
    label, dedup_fn, reconciled = _select_dedup(attivo_rows, D("4979885.27"))
    assert reconciled is True
    kept = dedup_fn(attivo_rows)
    assert sum(a for _c, _d, a in kept) == D("4979885.27")
