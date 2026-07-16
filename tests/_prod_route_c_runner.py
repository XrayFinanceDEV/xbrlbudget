"""Faithful DETERMINISTIC replica of the production route-C post-extraction path.

The quadratura harness runs only `extract -> check_quadratura`, which does NOT run
`net_contra_accounts` nor `_reconcile_trial_to_declared`. For route C that is
OPTIMISTIC: a file can look "SI plug 0" while the netting overlay silently
corrupts sp02/sp03 (budget_395) or the extractor under-reads the sheet
(budget_131). This module reproduces the EXACT sequence `pdf_importer` runs after
picking the deterministic candidate (no api_key branch), so a fix can be measured
on the same numbers the user sees.

It mirrors `importers.pdf_importer.import_pdf_balance_sheet` route C (the
`is_trial_balance` block, deterministic candidate only). Kept as a faithful
replica rather than a refactor of the live import path; if the two drift, the
assertions in `tests/test_prod_route_c.py` catch it against the real PDFs.

CLI (needs the local, gitignored Test/ corpus):
    python tests/_prod_route_c_runner.py <folder>        # table over a folder
    python tests/_prod_route_c_runner.py <single.pdf>    # verbose single file
"""
import os
import sys
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from importers.situazione_contabile_parser import (  # noqa: E402
    extract_situazione_contabile, net_contra_accounts,
)
from importers.pdf_importer import _map_sc_keys  # noqa: E402
from importers.iv_cee_hierarchy import (  # noqa: E402
    check_quadratura, enforce_ce_sp_identity, _net_profit_from_ce,
)
from importers.pdf_extractor_llm import (  # noqa: E402
    _declared_control_totals, _reconcile_trial_to_declared,
)

Z = Decimal('0')


def run_prod_route_c(file_path: str, ocr_text=None) -> dict:
    """Run the deterministic route-C production sequence on one file.

    Returns a dict with the FINAL balance sheet / income statement plus the
    diagnostics the user would see (plug residual, netted contra, quadratura).
    Raises on a genuinely empty extraction (mirrors the no-api_key hard fail).
    """
    sc_bs, sc_ce, sc_prior_bs, sc_prior_ce = extract_situazione_contabile(
        file_path, return_prior=True)
    bs = _map_sc_keys(sc_bs)
    ce = _map_sc_keys(sc_ce)
    if bs.get('totale_attivo', Z) <= 0:
        raise ValueError("estrazione deterministica vuota (totale_attivo<=0)")

    # mirrors pdf_importer: a garbled text layer makes the declared totals garbage
    # -> they must not drive the reconcile / candidate anchoring.
    import fitz
    from importers.pdf_extractor_llm import _text_layer_is_garbled
    try:
        _sample = "".join(pg.get_text() for pg in fitz.open(file_path)[:14])
    except Exception:
        _sample = ""
    text_garbled = _text_layer_is_garbled(_sample)
    dc0 = {} if text_garbled else _declared_control_totals(file_path, text=ocr_text)

    # source == deterministico -> overlay_debt_typing is a no-op (skipped in prod).
    contra = Z
    try:
        bs, contra = net_contra_accounts(bs, file_path, text=ocr_text, declared=dc0)
    except Exception as exc:  # pragma: no cover - defensive, mirrors prod
        print(f"  [warn] contra-netting saltato: {exc}", file=sys.stderr)

    authoritative = bs.pop('_skip_declared_reconcile', False)
    if not authoritative:
        decl = dict(dc0)
        anchor_cut = contra if contra > 0 else bs.get('_netted_contra', Z)
        if anchor_cut > 0:
            for k in ('attivo', 'passivo', 'pareggio'):
                if decl.get(k):
                    decl[k] = decl[k] - anchor_cut
        try:
            ce_result = _net_profit_from_ce(ce)
        except Exception:
            ce_result = None
        bs = _reconcile_trial_to_declared(bs, decl, "prod-replica", ce_result=ce_result)

    try:
        ce = enforce_ce_sp_identity(bs, ce, "import", prefer="sp13", declared=dc0)
    except Exception as exc:  # pragma: no cover
        print(f"  [warn] enforce CE-SP saltato: {exc}", file=sys.stderr)

    q = check_quadratura(bs, ce)
    return {
        "bs": bs, "ce": ce, "declared": dc0, "contra": contra,
        "sp02": bs.get('sp02_immob_immateriali', Z),
        "sp03": bs.get('sp03_immob_materiali', Z),
        "sp13": bs.get('sp13_utile_perdita', Z),
        "totale_attivo": bs.get('totale_attivo', Z),
        "plug_residual": bs.get('_plug_residual', Z),
        "plug_detail": bs.get('_plug_detail', []),
        "quadra": q.quadra, "masked": q.masked, "is_empty": q.is_empty,
    }


def _fmt(d):
    try:
        return f"{Decimal(d):,.2f}"
    except Exception:
        return str(d)


def _print_single(path):
    r = run_prod_route_c(path)
    print(f"\n== {os.path.basename(path)} ==")
    print(f"  quadra={r['quadra']} masked={r['masked']} empty={r['is_empty']}")
    print(f"  totale_attivo = {_fmt(r['totale_attivo'])}")
    print(f"  sp02 immat    = {_fmt(r['sp02'])}")
    print(f"  sp03 mat      = {_fmt(r['sp03'])}")
    print(f"  sp13 result   = {_fmt(r['sp13'])}")
    print(f"  contra netted = {_fmt(r['contra'])}")
    print(f"  plug residual = {_fmt(r['plug_residual'])}")
    for desc, amt, side in (r['plug_detail'] or [])[:8]:
        print(f"    plug [{side}] {desc}: {_fmt(amt)}")


def _print_table(folder):
    pdfs = sorted(f for f in os.listdir(folder) if f.lower().endswith('.pdf'))
    print(f"{'FILE':<52} {'quadra':<7} {'sp02':>14} {'sp03':>16} "
          f"{'sp13':>14} {'plug':>12}")
    print("-" * 120)
    for name in pdfs:
        path = os.path.join(folder, name)
        try:
            r = run_prod_route_c(path)
            flag = 'SI' if r['quadra'] else ('MASK' if r['masked'] else 'NO')
            print(f"{name[:52]:<52} {flag:<7} {_fmt(r['sp02']):>14} "
                  f"{_fmt(r['sp03']):>16} {_fmt(r['sp13']):>14} "
                  f"{_fmt(r['plug_residual']):>12}")
        except Exception as exc:
            print(f"{name[:52]:<52} {'ERR':<7} {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    target = (sys.argv[1] if len(sys.argv) > 1
              else os.path.join(ROOT, "Test", "sez-contrapposte"))
    if os.path.isdir(target):
        _print_table(target)
    else:
        _print_single(target)
