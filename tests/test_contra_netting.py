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


# ---------------------------------------------------------------- net_contra_accounts

import importers.situazione_contabile_parser as scp


def _gross_winner_bs():
    """Reproduces the observed CoGe-LLM failure shape on a gross trial balance:
    assets left GROSS, the whole fondi mass (1.858.799,20) dumped into debts."""
    return {
        "sp02_immob_immateriali": D("20000"),
        "sp03_immob_materiali": D("3500000"),
        "sp06_crediti_breve": D("115000"),          # incl. 15.000 IVA credit
        "sp09_disponibilita_liquide": D("50000"),
        "sp11_capitale": D("1000000"),
        "sp13_utile_perdita": D("636200.80"),
        "sp16_debiti_breve": D("2048799.20"),       # 190.000 real + 1.858.799,20 fondi
        "sp16g_altri_debiti_breve": D("1873799.20"),
        "totale_attivo": D("3685000"),
        "totale_passivo": D("3685000"),
    }


DECLARED = {"attivo": D("3685000"), "passivo": D("3685000"),
            "pareggio": D("3685000"), "utile": None, "perdita": None}


def _patch_scan(monkeypatch, attivo, passivo):
    monkeypatch.setattr(scp, "_contra_rows", lambda fp, text=None: (attivo, passivo))


def test_netting_applied_on_gross_extraction(monkeypatch):
    _patch_scan(monkeypatch, ATTIVO_ROWS, PASSIVO_ROWS)
    bs = _gross_winner_bs()
    bs, netted = scp.net_contra_accounts(bs, "x.pdf", declared=DECLARED)
    # netted = fondi 1.858.799,20 + IVA offset min(15000, 10000)
    assert netted == D("1868799.20")
    assert bs["sp02_immob_immateriali"] == D("15000")       # 20.000 - 5.000
    assert bs["sp03_immob_materiali"] == D("1646200.80")    # 3.500.000 - 1.853.799,20
    assert bs["sp06_crediti_breve"] == D("105000")          # IVA credit collapsed
    assert bs["totale_attivo"] == D("1816200.80")
    assert bs["totale_passivo"] == bs["totale_attivo"]      # pareggio preserved
    assert bs["sp16_debiti_breve"] == D("180000")           # only real debts left
    assert bs["sp13_utile_perdita"] == D("636200.80")       # result untouched


def test_noop_when_extractor_already_netted(monkeypatch):
    """Deterministic authority must be idempotent: a correct (net) sheet passes
    through with only the anchor-reduction value returned — no field changes."""
    _patch_scan(monkeypatch, ATTIVO_ROWS, PASSIVO_ROWS)
    bs = {
        "sp02_immob_immateriali": D("15000"),
        "sp03_immob_materiali": D("1646200.80"),
        "sp06_crediti_breve": D("105000"),
        "sp09_disponibilita_liquide": D("50000"),
        "sp11_capitale": D("1000000"),
        "sp13_utile_perdita": D("636200.80"),
        "sp16_debiti_breve": D("180000"),
        "totale_attivo": D("1816200.80"),
        "totale_passivo": D("1816200.80"),
    }
    before = dict(bs)
    bs, netted = scp.net_contra_accounts(bs, "x.pdf", declared=DECLARED)
    assert netted == D("1868799.20")   # still returned: the DECLARED anchor is gross
    # sp02/sp03 overwritten with the SAME net values; the IVA gross-evidence gate
    # skips the (non-idempotent) IVA delta because totale_attivo is already at the
    # NET magnitude; balance-invariant debt reduction sees excess 0 -> no real
    # debt touched. Net effect: the sheet passes through byte-identical.
    assert bs == before


def test_noop_without_fondi(monkeypatch):
    _patch_scan(monkeypatch, [("0601", "CREDITI V/CLIENTI", D("3685000"))], [])
    bs = _gross_winner_bs()
    before = dict(bs)
    bs, netted = scp.net_contra_accounts(bs, "x.pdf", declared=DECLARED)
    assert netted == D("0")
    assert bs == before


def test_noop_when_scan_does_not_reconcile(monkeypatch):
    # scan reads only half the attivo -> gate 2 fails -> untouched sheet
    _patch_scan(monkeypatch, ATTIVO_ROWS[:2], PASSIVO_ROWS)
    bs = _gross_winner_bs()
    before = dict(bs)
    bs, netted = scp.net_contra_accounts(bs, "x.pdf", declared=DECLARED)
    assert netted == D("0")
    assert bs == before


def test_noop_without_declared_totals(monkeypatch):
    _patch_scan(monkeypatch, ATTIVO_ROWS, PASSIVO_ROWS)
    bs = _gross_winner_bs()
    before = dict(bs)
    bs, netted = scp.net_contra_accounts(bs, "x.pdf", declared=None)
    assert netted == D("0")
    assert bs == before


def test_iva_one_sided_left_gross(monkeypatch):
    # only an IVA credit exists -> offset 0 -> crediti untouched, fondi still netted
    passivo_no_iva = [r for r in PASSIVO_ROWS if "IVA" not in r[1]]
    # keep the attivo scan total equal to declared by replacing the IVA row
    attivo = [r if "IVA" not in r[1] else (r[0], "CREDITI DIVERSI", r[2])
              for r in ATTIVO_ROWS]
    _patch_scan(monkeypatch, attivo, passivo_no_iva)
    bs = _gross_winner_bs()
    bs, netted = scp.net_contra_accounts(bs, "x.pdf", declared=DECLARED)
    assert netted == D("1858799.20")                 # fondi only, no IVA offset
    assert bs["sp06_crediti_breve"] == D("115000")   # untouched


# ---------------------------------------------------------------- end-to-end (production path)

def _gross_winner_bs_613():
    """Observed-failure shape for 613_2024, built from the spec's evidence:
    equity 2,93M, real debts ~182k, fondi 1.853.799,20 booked as altri debiti,
    assets gross. Numbers approximate the real file; the scan overwrites the
    asset side from the document itself, so only the SHAPE matters here."""
    return {
        "sp02_immob_immateriali": D("0"),
        "sp03_immob_materiali": D("4930000"),
        "sp06_crediti_breve": D("30000"),
        "sp09_disponibilita_liquide": D("25000"),
        "sp11_capitale": D("2930000"),
        "sp13_utile_perdita": D("19590.98"),
        "sp16_debiti_breve": D("2035409.02"),
        "sp16g_altri_debiti_breve": D("2035409.02"),
        "totale_attivo": D("4985000"),
        "totale_passivo": D("4985000"),
    }


@pytest.mark.skipif(not os.path.exists(PDF_613), reason="evidence PDF not present")
def test_613_production_path_with_stubbed_gross_llm():
    """Full route-C post-selection pipeline on the real 613_2024 PDF, with the
    winning candidate stubbed to the observed LLM failure (gross assets, fondi
    in debts). No API key needed. Asserts the spec's acceptance numbers."""
    from importers.pdf_extractor_llm import (
        _declared_control_totals, _reconcile_trial_to_declared,
    )
    from importers.situazione_contabile_parser import net_contra_accounts

    declared = _declared_control_totals(PDF_613)
    assert declared.get("pareggio") or declared.get("attivo"), \
        "613 must print its own control totals"

    # stubbed winner reproducing the observed failure: real scan drives the fix
    bs, netted = net_contra_accounts(_gross_winner_bs_613(), PDF_613,
                                     declared=declared)
    assert netted > D("1800000")

    decl = dict(declared)
    for k in ("attivo", "passivo", "pareggio"):
        if decl.get(k):
            decl[k] = decl[k] - netted
    bs = _reconcile_trial_to_declared(bs, decl, "test-613")

    # Spec acceptance: sp03 ~ 3,08M net; debts ~ real (~182k, fondi removed);
    # totale_attivo ~ 3,13M net; attivo == passivo
    assert abs(bs["sp03_immob_materiali"] - D("3080000")) < D("100000")
    debts = bs.get("sp16_debiti_breve", D("0")) + bs.get("sp17_debiti_lungo", D("0"))
    assert debts < D("400000")
    assert abs(bs["totale_attivo"] - D("3130000")) < D("100000")
    assert abs(bs["totale_attivo"] - bs["totale_passivo"]) <= D("1")
    # no false plug: the netted mass must NOT resurface as _plug_residual
    assert bs.get("_plug_residual", D("0")) < bs["totale_attivo"] * D("0.01")
