"""Debiti aggregates (sp16/sp17) are schema-derived — realign them to their
sub-details, but ONLY when it does not worsen the balance.

Regression: budget_585's prior-year (2024) column extracted an sp16_debiti_breve
aggregate that drifted from its own sub-details, so the balance sheet failed to
tie and the year was silently dropped. But the stochastic LLM can also drift the
DETAILS while the aggregate is right (585 current 2025 balanced on the raw
aggregate); a blind rollup broke that year by ~127k. The rollup must be
self-validating: keep a change only if |attivo - passivo| does not grow.
"""

from decimal import Decimal

from importers.iv_cee_hierarchy import rollup_debiti_aggregates


def test_drifted_aggregate_is_fixed_when_it_improves_balance():
    bs = {
        "sp09_disponibilita_liquide": Decimal("1000"),  # attivo
        "sp11_capitale": Decimal("400"),
        "sp16_debiti_breve": Decimal("580"),            # drifted low; details = 600
        "sp16d_debiti_fornitori_breve": Decimal("600"),
    }
    # raw: attivo 1000 vs passivo 980 (gap +20). rollup → passivo 1000 (gap 0): apply.
    out = rollup_debiti_aggregates(bs)
    assert out["sp16_debiti_breve"] == Decimal("600")
    assert bs["sp16_debiti_breve"] == Decimal("580")  # input not mutated


def test_good_aggregate_with_over_extracted_details_is_left_alone():
    bs = {
        "sp09_disponibilita_liquide": Decimal("1000"),
        "sp11_capitale": Decimal("400"),
        "sp16_debiti_breve": Decimal("600"),            # correct — already balances
        "sp16d_debiti_fornitori_breve": Decimal("750"),  # details over-extracted
    }
    # raw: gap 0. rollup would make passivo 1150 (gap -150): must NOT apply.
    out = rollup_debiti_aggregates(bs)
    assert out["sp16_debiti_breve"] == Decimal("600")


def test_missing_aggregate_rolled_up_from_details_when_it_balances():
    bs = {
        "sp09_disponibilita_liquide": Decimal("1000"),
        "sp11_capitale": Decimal("800"),
        "sp17_debiti_lungo": Decimal("0"),              # aggregate absent
        "sp17a_debiti_banche_lungo": Decimal("200"),
    }
    # raw: attivo 1000 vs passivo 800 (gap +200). rollup → passivo 1000: apply.
    out = rollup_debiti_aggregates(bs)
    assert out["sp17_debiti_lungo"] == Decimal("200")


def test_aggregate_untouched_when_no_details():
    bs = {"sp16_debiti_breve": Decimal("507758.55")}
    out = rollup_debiti_aggregates(bs)
    assert out["sp16_debiti_breve"] == Decimal("507758.55")
