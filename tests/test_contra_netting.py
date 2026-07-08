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
