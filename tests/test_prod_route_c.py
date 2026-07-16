"""Ground-truth field-by-field check of the deterministic route-C production path.

Quadratura alone is NOT sufficient: budget_395 balances (plug 0) with sp02/sp03
both wrong. This suite pins the CORRECT sp02/sp03/sp13/plug values (read from the
source PDFs, audit 2026-07-14) against the production replica in
`tests/_prod_route_c_runner.py`, so a silent netting corruption fails a test.

The corpus PDFs live in the gitignored Test/sez-contrapposte/, so each test skips
when its PDF is absent (fresh clone / CI without the corpus). Rows marked
status="open" are xfail(strict=True) until their fixing PR lands — flip them to
status="good" in the JSON when the fix is implemented.
Run: python -m pytest tests/test_prod_route_c.py -v
"""
import json
import importlib.util
import os
import sys
from decimal import Decimal

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _prod_route_c_runner import run_prod_route_c  # noqa: E402

GT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "_ground_truth_sez_contrapposte.json")
with open(GT_PATH, encoding="utf-8") as fh:
    _GT_DOC = json.load(fh)
CORPUS = os.path.join(ROOT, *_GT_DOC["corpus_dir"].split("/"))
_GT = _GT_DOC["files"]


def _check(fname, spec):
    path = os.path.join(CORPUS, fname)
    if not os.path.exists(path):
        pytest.skip(f"corpus PDF missing: {fname}")
    r = run_prod_route_c(path)
    tol = Decimal(str(spec["tol"]))
    exp = spec["expect"]
    problems = []
    for field in ("sp02", "sp03", "sp13", "totale_attivo"):
        if field in exp:
            got, want = Decimal(r[field]), Decimal(str(exp[field]))
            if abs(got - want) > tol:
                problems.append(f"{field}: got {got:,.2f} want {want:,.2f} (tol {tol})")
    if "plug_max" in exp and Decimal(r["plug_residual"]) > Decimal(str(exp["plug_max"])):
        problems.append(f"plug {Decimal(r['plug_residual']):,.2f} > max {exp['plug_max']}")
    if "plug_min" in exp and Decimal(r["plug_residual"]) < Decimal(str(exp["plug_min"])):
        problems.append(f"plug {Decimal(r['plug_residual']):,.2f} < min {exp['plug_min']}")
    if "plug_pct_max" in exp:
        tot = Decimal(r["totale_attivo"]) or Decimal("1")
        pct = Decimal(100) * Decimal(r["plug_residual"]) / tot
        if pct > Decimal(str(exp["plug_pct_max"])):
            problems.append(f"plug {pct:.2f}% > max {exp['plug_pct_max']}%")
    expected_quadra = exp.get("quadra", spec.get("status") == "good")
    if bool(r["quadra"]) != bool(expected_quadra):
        problems.append(f"quadra={r['quadra']} want {expected_quadra}")
    assert not problems, "; ".join(problems)


def _make_test(fname, spec):
    def _t():
        _check(fname, spec)
    if spec.get("status") == "open":
        _t = pytest.mark.xfail(reason=f"awaiting {spec.get('fixed_by', '?')}",
                               strict=True)(_t)
    return _t


_g = globals()
for _i, (_fname, _spec) in enumerate(_GT.items()):
    _key = _fname.split()[0].replace("-", "_").replace(".", "_")
    _g["test_gt_%02d_%s" % (_i, _key)] = _make_test(_fname, _spec)


@pytest.mark.parametrize(
    ("filename", "expected_total", "expected_result"),
    [
        ("budget_373_AITEC SRL - BILANCINO AL 31 12 2025.pdf", "10303346.66", "562984.30"),
        ("budget_374_AITEC SRL - PROVVISORIO 30 06 25.pdf", "10828894.85", "293158.04"),
        ("budget_375_AITEC SRL - BILANCIO ANALITICO 2024.pdf", "8256311.26", "278950.86"),
    ],
)
def test_erp_legal_parent_suffixes_do_not_double_count_children(
    filename, expected_total, expected_result
):
    path = os.path.join(ROOT, "Test", "june_sample", "success", filename)
    if not os.path.exists(path):
        pytest.skip(f"corpus PDF missing: {filename}")

    result = run_prod_route_c(path)

    assert result["quadra"] is True
    assert result["masked"] is False
    assert Decimal(result["totale_attivo"]) == Decimal(expected_total)
    assert Decimal(result["bs"]["totale_passivo"]) == Decimal(expected_total)
    assert Decimal(result["sp13"]) == Decimal(expected_result)
    assert Decimal(result["plug_residual"]) == Decimal("0")


def test_company_address_header_is_not_treated_as_a_ledger_account():
    path = os.path.join(ROOT, "Test", "BILANCIO-TEST.pdf")
    if not os.path.exists(path):
        pytest.skip("corpus PDF missing: BILANCIO-TEST.pdf")

    result = run_prod_route_c(path)

    assert result["quadra"] is True
    assert result["masked"] is False
    assert Decimal(result["totale_attivo"]) == Decimal("2918457.19")
    assert Decimal(result["bs"]["totale_passivo"]) == Decimal("2918457.19")
    assert Decimal(result["sp13"]) == Decimal("70353.09")
    assert Decimal(result["plug_residual"]) == Decimal("0")


@pytest.mark.skipif(
    importlib.util.find_spec("rapidocr_onnxruntime") is None,
    reason="rapidocr-onnxruntime is not installed",
)
def test_scanned_verifica_segno_uses_coordinate_ocr_without_a_balance_plug():
    path = os.path.join(
        ROOT, "Test", "sez-contrapposte", "Bilancino 31-5-26.pdf"
    )
    if not os.path.exists(path):
        pytest.skip("scanned corpus PDF missing: Bilancino 31-5-26.pdf")

    result = run_prod_route_c(path)

    assert result["quadra"] is True
    assert result["masked"] is False
    assert Decimal(result["totale_attivo"]) == Decimal("1913698.44")
    assert Decimal(result["bs"]["totale_passivo"]) == Decimal("1913698.44")
    assert Decimal(result["sp02"]) == Decimal("18931.18")
    assert Decimal(result["sp03"]) == Decimal("1232809.55")
    assert Decimal(result["sp13"]) == Decimal("17872.66")
    assert Decimal(result["plug_residual"]) == Decimal("0")
