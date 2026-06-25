"""Test for _debt_type() OIC creditor-type classification (route-C deterministic parser).

Strings are real passivo debt descriptions extracted from tests/debug route-C PDFs
(LIO, AITEC, budget_342). Each must map to its OIC sub-letter:
  a=banche  b=altri finanz  c=obbligazioni  d=fornitori  e=tributari  f=previdenza  g=altri
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from importers.situazione_contabile_parser import _debt_type

# (descrizione_upper, tipo_atteso)
CASES = [
    # --- BANCHE (D.4): named banks without the literal "BANCHE" plural ---
    ("BANCA C/C", "a"),
    ("BANCO BPM", "a"),
    ("BPER BANCA S.P.A.", "a"),
    ("EMILBANCA-114588 C/C 089330114588", "a"),
    ("BANCA IFIS SPA 70 C/C", "a"),
    ("BANCA MONTEPASCHI DI SIENA S.P.A.", "a"),
    ("BANCA CREDEM SBF", "a"),            # already worked (SBF), must stay 'a'
    ("BANCHE C/C E POSTA C/C", "a"),      # plural, must stay 'a'
    # c/c = conto corrente → bank, even when the bank name carries no 'BANC'
    ("UNICREDIT C/C 12345", "a"),
    ("INTESA SANPAOLO C/C", "a"),
    ("BPER C/C ORDINARIO", "a"),
    ("UNICREDIT C.C. 999", "a"),          # dotted variant C.C.
    # bank advances against invoices/credits (short-term bank debt)
    ("INTESA SANPAOLO ANTICIPO FATTURE", "a"),
    ("BANCA INTESA CONTO ANTICIPI SU CREDITI", "a"),
    # --- FORNITORI (D.7) ---
    ("DEBITI COMMERCIALI", "d"),
    ("FATTURE DA RICEVERE DA FORNITORI TERZI", "d"),
    ("DEBITI V/FORNITORI", "d"),
    ("FORNITORI TERZI ITALIA", "d"),
    # --- TRIBUTARI (D.12) ---
    ("CONTI ERARIALI", "e"),
    ("ERARIO C/IVA", "e"),
    ("ERARIO C/SOSTITUTO D'IMPOSTA", "e"),
    # --- ALTRI FINANZIATORI (D.3/D.5) — must NOT be stolen by banche rule ---
    ("SOCI C/FINANZIAMENTO INFRUTTIFERO", "b"),
    ("DEBITI VERSO ALTRI FINANZIATORI", "b"),
    ("SOCI C/C", "b"),                    # shareholder current account: NOT a bank c/c
    # --- PREVIDENZA (D.13) ---
    ("ENTI PREVIDENZIALI", "f"),
    ("INPS DIPENDENTI", "f"),
    # --- ALTRI (D.14) — genuinely "altri", must stay 'g' (regression guard) ---
    ("DEBITI VERSO IL PERSONALE", "g"),
    ("CREDITORI DIVERSI", "g"),
    ("DEPOSITI CAUZIONALI VARI", "g"),
    ("ALTRI DEBITI", "g"),
    ("ANTICIPI DA CLIENTI", "g"),     # acconti, NOT a bank advance
    ("DEBITI VARI", "g"),
]


def run():
    failures = []
    for desc, expected in CASES:
        got = _debt_type(desc)
        status = "OK " if got == expected else "FAIL"
        if got != expected:
            failures.append((desc, expected, got))
        print(f"  [{status}] {desc[:50]:50} expected={expected} got={got}")
    print()
    if failures:
        print(f"{len(failures)}/{len(CASES)} FAILED:")
        for desc, exp, got in failures:
            print(f"    {desc!r}: expected {exp}, got {got}")
        sys.exit(1)
    print(f"All {len(CASES)} cases passed.")


if __name__ == "__main__":
    run()
