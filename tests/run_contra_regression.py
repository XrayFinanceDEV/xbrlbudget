"""Deterministic route-C regression runner for the contra-netting overlay.

Runs every PDF in tests/debug/ + the two docs/examples evidence files through
the DETERMINISTIC production path (no LLM, no API key), once WITHOUT and once
WITH net_contra_accounts, and prints quadratura verdicts side by side.

A file counts as REGRESSED when it was quadrato without netting and is not
with netting. The expected outcome is zero regressions and 612/613 improving.

Usage:  python tests/run_contra_regression.py
"""
import glob
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from importers.iv_cee_hierarchy import check_quadratura, enforce_ce_sp_identity
from importers.pdf_extractor_llm import (
    _declared_control_totals, _reconcile_trial_to_declared,
)
from importers.pdf_importer import _map_sc_keys
from importers.pdf_mapper import IVCEEMapper
from importers.situazione_contabile_parser import (
    extract_situazione_contabile, net_contra_accounts,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS = sorted(
    glob.glob(os.path.join(ROOT, "tests", "debug", "*.pdf"))
    + glob.glob(os.path.join(ROOT, "tests", "debug", "*.PDF"))
    + glob.glob(os.path.join(ROOT, "docs", "examples", "61[23]_*.pdf"))
)


def run_one(path, with_netting):
    bs, ce = extract_situazione_contabile(path)
    bs, ce = _map_sc_keys(bs), _map_sc_keys(ce)
    declared = _declared_control_totals(path)
    contra = Decimal("0")
    if with_netting:
        bs, contra = net_contra_accounts(bs, path, declared=declared)
    if not bs.pop("_skip_declared_reconcile", False):
        decl = dict(declared)
        if contra > 0:
            for k in ("attivo", "passivo", "pareggio"):
                if decl.get(k):
                    decl[k] = decl[k] - contra
        bs = _reconcile_trial_to_declared(bs, decl, os.path.basename(path))
    ce = enforce_ce_sp_identity(bs, ce, "regression", prefer="sp13",
                                declared=declared)
    valid = IVCEEMapper().validate_balance(bs)
    q = check_quadratura(bs, ce)
    return {
        "valid": valid, "quadra": q.quadra, "masked": q.masked,
        "empty": q.is_empty, "plug": q.plug_residual,
        "attivo": bs.get("totale_attivo", Decimal("0")), "contra": contra,
    }


def main():
    if not CORPUS:
        print("no corpus PDFs found (tests/debug/ empty?) — nothing to check")
        return
    regressions = 0
    print(f"{'file':50s} {'senza netting':>22s} {'con netting':>22s}  contra")
    for path in CORPUS:
        name = os.path.basename(path)[:48]
        try:
            base = run_one(path, with_netting=False)
        except Exception as exc:
            base = {"quadra": False, "masked": False, "empty": True,
                    "plug": Decimal("0"), "err": str(exc)[:40]}
        try:
            net = run_one(path, with_netting=True)
        except Exception as exc:
            net = {"quadra": False, "masked": False, "empty": True,
                   "plug": Decimal("0"), "err": str(exc)[:40], "contra": "?"}

        def verdict(r):
            if r.get("err"):
                return f"ERR {r['err'][:14]}"
            if r["empty"]:
                return "VUOTO"
            tag = "SI" if r["quadra"] else ("MASCHERATO" if r["masked"] else "NO")
            return f"{tag} plug={r['plug']:,.0f}"

        if base.get("quadra") and not net.get("quadra"):
            regressions += 1
            flag = "  << REGRESSIONE"
        else:
            flag = ""
        print(f"{name:50s} {verdict(base):>22s} {verdict(net):>22s}  "
              f"{net.get('contra', 0)}{flag}")
    print(f"\nregressioni: {regressions}")
    sys.exit(1 if regressions else 0)


if __name__ == "__main__":
    main()
