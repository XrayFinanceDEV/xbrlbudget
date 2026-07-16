"""Tests for the verifica-segno financing entro/oltre split.

Context (2026-07-16). `_vseg_classify_sp` books only MASTRO rows and had no rule for
financing, so a "FINANZIAMENTI DI TERZI" mastro (bank mortgages) fell through to
`sp16g_altri_debiti_breve` and `sp17` stayed 0. That makes the forecast repayment
instalment ZERO -- `base_financial_long_term_debt` reads sp17a/sp17c -- so the
mortgages are never amortised and get modelled as short-term debt scaling with
operating costs.

The maturity evidence lives in the scan's level-3 rows, which RapidOCR reads but
`_VSEG_CODE_RE` (levels 1-2 only) discarded:

    NN.NN.01  Banca c/anticipazioni                  -> breve  (revolves in-year)
    NN.NN.05  Finanz. a medio/lungo termine bancari  -> lungo
    NN.NN.90  Mutuo <istituto>                       -> lungo
    NN.NN.97  Socio <nome> c/finanziamento           -> soci   (D.5, not a bank)

Two OCR quirks drive the design and are pinned below:

1. RapidOCR drops the decimal comma on some rows (243.073,49 -> 24307349). The /100
   repair is accepted ONLY when the repaired rows sum to the printed mastro total --
   the source confirming itself.
2. RapidOCR mangles captions ("C/FINANZIAMEN" -> "C/FINANANZIAMEN"), which is why the
   soci rule keys on SOCIO and never on FINANZ.

The figures here are SYNTHETIC and chosen to reproduce those two properties. Real
client balance sheets stay out of this repo (see the gitignored `Test/`); the
end-to-end regression against the real scan runs from that corpus.

Run: python -m pytest tests/test_vseg_financing_split.py -v
"""
import os
import sys
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

D = Decimal

# Synthetic financing mastro. The last two rows arrive with the decimal comma dropped,
# exactly as RapidOCR emits them; the soci caption carries the real mangling.
# The clean rows deliberately carry non-zero cents, mirroring the source: the repair is
# all-or-nothing over the integer-valued rows, so a mastro whose clean rows happened to
# be round integers would be repaired too and fail to reconcile -> no split, no-op.
FINANZIAMENTI = [
    ("31.03.01", "BANCA C/ANTICIPAZIONI", D("120000.60")),
    ("31.03.05", "FINANZ.A MEDIO/LUNGO TERMINE BANCARI", D("500000.50")),
    ("31.03.90", "MUTUOBANCOALFA N.00000001", D("1000.18")),
    ("31.03.92", "MUTUOBANCOBETA C/00000002", D("24000000")),         # = 240.000,00
    ("31.03.97", "SOCIO ROSSI MARIO C/FINANANZIAMEN", D("6000000")),  # =  60.000,00
]
FINANZIAMENTI_TOTAL = D("921001.28")


def test_split_reads_maturity_from_the_detail_rows():
    from importers.situazione_contabile_parser import _vseg_financing_split

    split = _vseg_financing_split(FINANZIAMENTI, FINANZIAMENTI_TOTAL)

    assert split is not None
    assert split["sp16a_debiti_banche_breve"] == D("120000.60")
    assert split["sp17a_debiti_banche_lungo"] == D("741000.68")
    assert split["sp17b_debiti_altri_finanz_lungo"] == D("60000.00")
    # The split may never create or destroy mass.
    assert sum(split.values()) == FINANZIAMENTI_TOTAL


def test_soci_rule_survives_the_ocr_mangling_the_caption():
    """'C/FINANANZIAMEN' must not defeat the rule: it keys on SOCIO alone."""
    from importers.situazione_contabile_parser import _vseg_debt_field

    assert _vseg_debt_field("SOCIO ROSSI MARIO C/FINANANZIAMEN") == (
        "sp17b_debiti_altri_finanz_lungo"
    )


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

    assert _vseg_financing_split(FINANZIAMENTI, D("999999.99")) is None


def test_refuses_on_an_unrecognised_detail_caption():
    """Partial knowledge must not produce a partial split."""
    from importers.situazione_contabile_parser import _vseg_financing_split

    rows = FINANZIAMENTI[:-1] + [("31.03.97", "QUALCOSA DI IGNOTO", D("60000.00"))]
    assert _vseg_financing_split(rows, FINANZIAMENTI_TOTAL) is None


def test_no_details_no_split():
    from importers.situazione_contabile_parser import _vseg_financing_split

    assert _vseg_financing_split([], FINANZIAMENTI_TOTAL) is None


def test_repair_is_not_applied_when_raw_rows_already_tie():
    """A legitimately round amount must not be divided by 100."""
    from importers.situazione_contabile_parser import _vseg_financing_split

    rows = [
        ("31.03.01", "BANCA C/ANTICIPAZIONI", D("50000")),
        ("31.03.05", "FINANZ.A MEDIO/LUNGO TERMINE BANCARI", D("50000")),
    ]
    split = _vseg_financing_split(rows, D("100000"))
    assert split["sp16a_debiti_banche_breve"] == D("50000")
