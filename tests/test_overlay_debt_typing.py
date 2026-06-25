"""Test for overlay_debt_typing(): when the winning route-C candidate dumped the debt
mass into 'altri' (sp16g/sp17g) but the donor (deterministic) candidate has a richer
creditor-type breakdown, redistribute the winner's debt AGGREGATE using the donor's
typed proportions — preserving the winner's total, only fixing the split.
"""
import os, sys
from decimal import Decimal
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from importers.situazione_contabile_parser import overlay_debt_typing

D = Decimal

BREVE = ['sp16a_debiti_banche_breve', 'sp16b_debiti_altri_finanz_breve',
         'sp16c_debiti_obbligazioni_breve', 'sp16d_debiti_fornitori_breve',
         'sp16e_debiti_tributari_breve', 'sp16f_debiti_previdenza_breve',
         'sp16g_altri_debiti_breve']


def _bs(agg16, a=0, b=0, c=0, d=0, e=0, f=0, g=0):
    bs = {k: D('0') for k in BREVE}
    bs['sp16_debiti_breve'] = D(str(agg16))
    bs['sp16a_debiti_banche_breve'] = D(str(a))
    bs['sp16d_debiti_fornitori_breve'] = D(str(d))
    bs['sp16e_debiti_tributari_breve'] = D(str(e))
    bs['sp16f_debiti_previdenza_breve'] = D(str(f))
    bs['sp16g_altri_debiti_breve'] = D(str(g))
    return bs


def approx(x, y, tol=1):
    return abs(D(str(x)) - D(str(y))) <= D(str(tol))


def run():
    failures = []

    def check(name, cond):
        print(f"  [{'OK ' if cond else 'FAIL'}] {name}")
        if not cond:
            failures.append(name)

    # 1) Winner degenerate (all 1000 in altri); donor typed 60/30/10 banche/fornitori/tributari.
    #    Winner aggregate (1000) preserved; split adopts donor proportions.
    winner = _bs(1000, g=1000)
    donor = _bs(900, a=540, d=270, e=90)  # 60/30/10 of 900
    out = overlay_debt_typing(winner, donor)
    check("total preserved", approx(out['sp16_debiti_breve'], 1000))
    check("banche ~600", approx(out['sp16a_debiti_banche_breve'], 600))
    check("fornitori ~300", approx(out['sp16d_debiti_fornitori_breve'], 300))
    check("tributari ~100", approx(out['sp16e_debiti_tributari_breve'], 100))
    check("altri drained to ~0", approx(out['sp16g_altri_debiti_breve'], 0))
    check("subfields sum to aggregate",
          approx(sum(out[k] for k in BREVE), out['sp16_debiti_breve']))

    # 2) Winner already well-typed → NO-OP (donor must not override a good split).
    winner2 = _bs(1000, a=700, d=300)
    donor2 = _bs(900, a=100, d=100, g=700)
    out2 = overlay_debt_typing(winner2, donor2)
    check("well-typed winner unchanged (banche 700)",
          approx(out2['sp16a_debiti_banche_breve'], 700))
    check("well-typed winner unchanged (altri 0)",
          approx(out2['sp16g_altri_debiti_breve'], 0))

    # 3) Donor ALSO degenerate (mostly altri) → no reliable typing → NO-OP.
    winner3 = _bs(1000, g=1000)
    donor3 = _bs(900, a=50, g=850)
    out3 = overlay_debt_typing(winner3, donor3)
    check("donor degenerate → winner unchanged (altri stays 1000)",
          approx(out3['sp16g_altri_debiti_breve'], 1000))

    # 4) Donor empty → NO-OP.
    winner4 = _bs(1000, g=1000)
    donor4 = _bs(0)
    out4 = overlay_debt_typing(winner4, donor4)
    check("donor empty → winner unchanged",
          approx(out4['sp16g_altri_debiti_breve'], 1000))

    print()
    if failures:
        print(f"{len(failures)} checks FAILED: {failures}")
        sys.exit(1)
    print("All checks passed.")


if __name__ == "__main__":
    run()
