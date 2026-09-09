from decimal import Decimal as D

import pytest

from calculations.projection_common import runoff_schedule, validate_runoff


def test_full_plan_in_first_year_leaves_nothing():
    y0 = runoff_schedule(D("1000"), [D("1000")], [], 0, 3)
    assert (y0.closed, y0.residual, y0.residual_short, y0.residual_long) == (D("1000"), D("0"), D("0"), D("0"))
    y1 = runoff_schedule(D("1000"), [D("1000")], [], 1, 3)
    assert y1.closed == D("0") and y1.residual == D("0")


def test_eighty_twenty_moves_the_residual_to_short_then_closes():
    y0 = runoff_schedule(D("1000"), [D("800"), D("200")], [], 0, 3)
    assert y0.residual == D("200") and y0.residual_short == D("200") and y0.residual_long == D("0")
    y1 = runoff_schedule(D("1000"), [D("800"), D("200")], [], 1, 3)
    assert y1.closed == D("200") and y1.residual == D("0")


def test_short_plan_leaves_the_rest_long_and_writeoff_is_not_a_collection():
    y0 = runoff_schedule(D("1000"), [D("300")], [D("50")], 0, 3)
    assert y0.writeoff == D("50")
    assert y0.residual == D("650")
    assert y0.residual_short == D("0") and y0.residual_long == D("650")
    y2 = runoff_schedule(D("1000"), [D("300")], [D("50")], 2, 3)
    assert y2.closed == D("0") and y2.residual == D("650") and y2.residual_long == D("650")


def test_three_equal_instalments_reclassify_by_maturity():
    plan = [D("33.34"), D("33.33"), D("33.33")]
    y0 = runoff_schedule(D("100"), plan, [], 0, 3)
    assert y0.residual_short == D("33.33") and y0.residual_long == D("33.33")
    y1 = runoff_schedule(D("100"), plan, [], 1, 3)
    assert y1.residual_short == D("33.33") and y1.residual_long == D("0")


@pytest.mark.parametrize("amounts,writeoff,msg", [
    ([D("700"), D("400")], [], "supera il saldo"),
    ([D("-1")], [], "negativ"),
    ([D("1"), D("1"), D("1"), D("1")], [], "orizzonte"),
    ([D("900")], [D("200")], "supera il saldo"),
])
def test_validation_errors(amounts, writeoff, msg):
    with pytest.raises(ValueError, match=msg):
        validate_runoff(D("1000"), amounts, writeoff, 3, "crediti commerciali")
