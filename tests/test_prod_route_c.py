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
    if "plug_pct_max" in exp:
        tot = Decimal(r["totale_attivo"]) or Decimal("1")
        pct = Decimal(100) * Decimal(r["plug_residual"]) / tot
        if pct > Decimal(str(exp["plug_pct_max"])):
            problems.append(f"plug {pct:.2f}% > max {exp['plug_pct_max']}%")
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
