"""Tests for the verifica-segno financing entro/oltre split (Bilancino 31-5-26).

Context (2026-07-16). `_vseg_classify_sp` books only MASTRO rows and has no rule for
financing, so "FINANZIAMENTI DI TERZI" (935.528,51 of bank mortgages) fell through to
`sp16g_altri_debiti_breve` and `sp17` stayed 0. That makes the forecast repayment
instalment ZERO -- `base_financial_long_term_debt` reads sp17a/sp17c -- so 935k of
mortgages were never amortised and were modelled as short-term debt scaling with
operating costs.

The maturity evidence lives in the scan's level-3 rows, which RapidOCR reads but
`_VSEG_CODE_RE` (levels 1-2 only) discarded:

    31.03.01  Banca c/anticipazioni                  129.244,60   -> breve
    31.03.05  Finanz. a medio/lungo termine bancari  500.946,24   -> lungo
    31.03.90  Mutuo Banco BPM N. 04793013              1.264,18   -> lungo
    31.03.92  Mutuo Banco Bpm c/05540646             243.073,49   -> lungo  (OCR: 24307349)
    31.03.97  Socio Gerevini Roberto c/finanziamento  61.000,00   -> soci   (OCR: 6100000)

RapidOCR drops the decimal comma on some rows. The repair (/100) is accepted ONLY when
the repaired rows sum exactly to the printed mastro total -- the source confirming
itself. Anything less returns None and the caller keeps the aggregate untouched.

Run: python -m pytest tests/test_vseg_financing_split.py -v
"""
import os
import sys
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

D = Decimal

# The real OCR output for Bilancino 31-5-26, level-3 rows under mastro 31.
# 31.03.92 and 31.03.97 arrive with the decimal comma dropped.
GEREVINI = [
    ("31.03.01", "BANCA C/ANTICIPAZIONI", D("129244.60")),
    ("31.03.05", "FINANZ.A MEDIO/LUNGO TERMINE BANCARI", D("500946.24")),
    ("31.03.90", "MUTUOBANCOBPM N.04793013", D("1264.18")),
    ("31.03.92", "MUTUOBANCOBPM C/05540646", D("24307349")),
    ("31.03.97", "SOCIO GEREVINI ROBERTO C/FINANANZIAMEN", D("6100000")),
]
GEREVINI_TOTAL = D("935528.51")


def test_gerevini_split_matches_the_paper():
    from importers.situazione_contabile_parser import _vseg_financing_split

    split = _vseg_financing_split(GEREVINI, GEREVINI_TOTAL)

    assert split is not None
    assert split["sp16a_debiti_banche_breve"] == D("129244.60")
    assert split["sp17a_debiti_banche_lungo"] == D("745283.91")
    assert split["sp17b_debiti_altri_finanz_lungo"] == D("61000.00")
    # The split may never create or destroy mass.
    assert sum(split.values()) == GEREVINI_TOTAL


def test_clean_rows_need_no_repair():
    from importers.situazione_contabile_parser import _vseg_financing_split

    clean = [
        ("31.03.01", "BANCA C/ANTICIPAZIONI", D("100.00")),
        ("31.03.05", "FINANZ.A MEDIO/LUNGO TERMINE BANCARI", D("900.00")),
    ]
    split = _vseg_financing_split(clean, D("1000.00"))
    assert split == {
        "sp16a_debiti_banche_breve": D("100.00"),
        "sp17a_debiti_banche_lungo": D("900.00"),
    }


def test_refuses_when_rows_do_not_reconcile_to_the_printed_total():
    """No self-validation -> no split. The caller keeps the aggregate."""
    from importers.situazione_contabile_parser import _vseg_financing_split

    assert _vseg_financing_split(GEREVINI, D("999999.99")) is None


def test_refuses_on_an_unrecognised_detail_caption():
    """Partial knowledge must not produce a partial split."""
    from importers.situazione_contabile_parser import _vseg_financing_split

    rows = GEREVINI[:-1] + [("31.03.97", "QUALCOSA DI IGNOTO", D("61000.00"))]
    assert _vseg_financing_split(rows, GEREVINI_TOTAL) is None


def test_no_details_no_split():
    from importers.situazione_contabile_parser import _vseg_financing_split

    assert _vseg_financing_split([], GEREVINI_TOTAL) is None


def test_repair_is_not_applied_when_raw_rows_already_tie():
    """A legitimately round amount must not be divided by 100."""
    from importers.situazione_contabile_parser import _vseg_financing_split

    rows = [
        ("31.03.01", "BANCA C/ANTICIPAZIONI", D("50000")),
        ("31.03.05", "FINANZ.A MEDIO/LUNGO TERMINE BANCARI", D("50000")),
    ]
    split = _vseg_financing_split(rows, D("100000"))
    assert split["sp16a_debiti_banche_breve"] == D("50000")
