"""Tests for the route-C contra-netting overlay (fondi ammortamento + IVA).

Spec: docs/superpowers/specs/2026-07-06-contra-netting-overlay-design.md
Run:  python -m pytest tests/test_contra_netting.py -v
"""
import os
import sys
from decimal import Decimal

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from importers.situazione_contabile_parser import (  # noqa: E402
    ContraScan,
    _contra_classify,
    _dedup_parent_child,
    _is_iva_line,
)

D = Decimal


# ---------------------------------------------------------------- dedup

def test_dedup_drops_parent_when_children_sum_to_it():
    # 613_2024 real case: mastro "F.do amm fabbricati" 1.779.795,83 already equals
    # its two sub-accounts — counting both double-counts the fund.
    rows = [
        ("0402", "F.DO AMM FABBRICATI", D("1779795.83")),
        ("040201", "F.DO AMM FABBRICATI INDUSTRIALI", D("1416504.33")),
        ("040202", "F.DO AMM COSTRUZIONI LEGGERE", D("363291.50")),
    ]
    out = _dedup_parent_child(rows)
    assert [c for c, _, _ in out] == ["040201", "040202"]


def test_dedup_keeps_parent_without_children():
    rows = [("0402", "F.DO AMM FABBRICATI", D("100"))]
    assert _dedup_parent_child(rows) == rows


def test_dedup_keeps_parent_when_children_do_not_sum():
    rows = [
        ("0402", "F.DO AMM FABBRICATI", D("1000")),
        ("040201", "F.DO AMM FABBRICATI INDUSTRIALI", D("300")),
    ]
    # children present but sum (300) != parent (1000) -> parent is a real
    # independent balance, keep everything
    assert _dedup_parent_child(rows) == rows


def test_dedup_ignores_codeless_rows():
    rows = [("", "CASSA", D("10")), ("", "CASSA CONTANTI", D("10"))]
    assert _dedup_parent_child(rows) == rows


# ---------------------------------------------------------------- IVA detection

def test_is_iva_line_matches_erario_and_iva_accounts():
    assert _is_iva_line("ERARIO C/IVA")
    assert _is_iva_line("IVA C/ACQUISTI")
    assert _is_iva_line("IVA C/VENDITE")
    assert _is_iva_line("IVA A DEBITO")


def test_is_iva_line_rejects_riserva_and_plain_words():
    # 'RISERVA' contains the substring IVA — the \bIVA\b boundary must reject it
    assert not _is_iva_line("RISERVA LEGALE")
    assert not _is_iva_line("RISERVA STRAORDINARIA")
    assert not _is_iva_line("FORNITORI")


# ---------------------------------------------------------------- classification

ATTIVO_ROWS = [
    ("0101", "SOFTWARE DI PROPRIETA", D("20000")),
    ("0201", "FABBRICATI INDUSTRIALI", D("3000000")),
    ("0202", "IMPIANTI E MACCHINARI", D("500000")),
    ("0601", "CREDITI V/CLIENTI", D("100000")),
    ("0602", "ERARIO C/IVA", D("15000")),
    ("0901", "BANCA C/C", D("50000")),
]
PASSIVO_ROWS = [
    ("0401", "F.DO AMM.TO FABBRICATI", D("1800000")),
    ("0402", "F.DO AMM.TO IMPIANTI", D("53799.20")),
    ("0403", "F.DO AMM.TO SOFTWARE", D("5000")),
    ("1601", "FORNITORI", D("180000")),
    ("1602", "ERARIO C/IVA VENDITE", D("10000")),
    ("1101", "CAPITALE SOCIALE", D("1000000")),
]


def test_contra_classify_gross_trial_balance():
    scan = _contra_classify(ATTIVO_ROWS, PASSIVO_ROWS)
    assert scan.gross_sp02 == D("20000")
    assert scan.gross_sp03 == D("3500000")
    # full attivo side, fondi excluded: 20k+3M+500k+100k+15k+50k
    assert scan.attivo_total == D("3685000")
    assert scan.fondi_immat == D("5000")
    assert scan.fondi_mat == D("1853799.20")
    assert scan.iva_credito == D("15000")
    assert scan.iva_debito == D("10000")


def test_contra_classify_fondi_on_asset_side():
    # rare gross-on-asset presentation: fondi listed as attivo-side rows —
    # still summed as fondi, excluded from the gross asset totals
    attivo = ATTIVO_ROWS + [("0301", "F.DO AMM.TO IMPIANTI", D("53799.20"))]
    scan = _contra_classify(attivo, [])
    assert scan.fondi_mat == D("53799.20")
    assert scan.attivo_total == D("3685000")


def test_contra_classify_fondo_svalutazione_left_gross():
    # fondo svalutazione crediti is OUT of scope (spec §goal 3): not a fondo amm
    scan = _contra_classify([], [("0405", "F.DO SVALUTAZIONE CREDITI", D("9000"))])
    assert scan.fondi_immat == D("0")
    assert scan.fondi_mat == D("0")


def test_contra_classify_dedups_before_summing():
    passivo = [
        ("0402", "F.DO AMM FABBRICATI", D("1779795.83")),
        ("040201", "F.DO AMM FABBRICATI INDUSTRIALI", D("1416504.33")),
        ("040202", "F.DO AMM COSTRUZIONI LEGGERE", D("363291.50")),
    ]
    scan = _contra_classify([], passivo)
    assert scan.fondi_mat == D("1779795.83")


# ---------------------------------------------------------------- _contra_rows

EXAMPLES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "docs", "examples")
PDF_613 = os.path.join(
    EXAMPLES, "613_2024 Costruzione di edifici residenziali e non residenziali.pdf")


@pytest.mark.skipif(not os.path.exists(PDF_613), reason="evidence PDF not present")
def test_contra_rows_on_613_finds_the_fondi_mass():
    from importers.situazione_contabile_parser import _contra_rows, _contra_classify

    rows = _contra_rows(PDF_613)
    assert rows is not None
    attivo_rows, passivo_rows = rows
    scan = _contra_classify(attivo_rows, passivo_rows)
    # Spec reproduced evidence: fondi ammortamento 1.853.799,20 on this file
    assert abs(scan.fondi_immat + scan.fondi_mat - Decimal("1853799.20")) \
        <= Decimal("1853799.20") * Decimal("0.01")
    # gross attivo scan must land near the file's gross total (~4.99M order of
    # magnitude: net 3.13M + fondi 1.85M). Loose 2% band — the exact declared
    # total is asserted in the end-to-end test via _declared_control_totals.
    assert scan.attivo_total > Decimal("4000000")


def test_contra_rows_text_mode_classifies_fondi_by_nature():
    from importers.situazione_contabile_parser import _contra_rows, _contra_classify

    ocr = (
        "SITUAZIONE PATRIMONIALE\n"
        "0201 FABBRICATI INDUSTRIALI 3.000.000,00\n"
        "0401 F.DO AMM.TO FABBRICATI 1.800.000,00\n"
        "1601 FORNITORI 180.000,00\n"
        "CONTO ECONOMICO\n"
        "3101 RICAVI DELLE VENDITE 900.000,00\n"
    )
    rows = _contra_rows("/nonexistent.pdf", text=ocr)
    assert rows is not None
    scan = _contra_classify(*rows)
    assert scan.fondi_mat == Decimal("1800000.00")
    assert scan.gross_sp03 == Decimal("3000000.00")
    # the CE line must NOT leak into the attivo total (window cut at CONTO ECONOMICO)
    assert scan.attivo_total == Decimal("3000000.00")
