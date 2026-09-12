from decimal import Decimal as D

import pytest

from calculations.projection_common import runoff_schedule, validate_runoff, tax_settlement_saldo_acconto


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

# ── Tax settlement: saldo + acconti kernel ──
def test_constant_tax_with_full_advance_generates_no_debt_and_pays_the_tax():
    t = tax_settlement_saldo_acconto(opening_credit=D("0"), saldo_due=D("0"), rate_due=D("0"),
                                     current_tax=D("100"), previous_tax=D("100"), acconto_pct=D("100"), explicit_advances=None)
    assert t.acconti_paid == D("100") and t.generated_debt == D("0") and t.generated_credit == D("0")
    assert t.cash_out == D("100")


def test_falling_tax_generates_a_credit_and_rising_tax_a_debt():
    down = tax_settlement_saldo_acconto(opening_credit=D("0"), saldo_due=D("0"), rate_due=D("0"),
                                        current_tax=D("60"), previous_tax=D("100"), acconto_pct=D("100"), explicit_advances=None)
    assert down.generated_credit == D("40") and down.generated_debt == D("0")
    up = tax_settlement_saldo_acconto(opening_credit=D("0"), saldo_due=D("0"), rate_due=D("0"),
                                      current_tax=D("130"), previous_tax=D("100"), acconto_pct=D("100"), explicit_advances=None)
    assert up.generated_debt == D("30")


def test_opening_credit_offsets_the_saldo_and_explicit_advances_win():
    t = tax_settlement_saldo_acconto(opening_credit=D("25"), saldo_due=D("40"), rate_due=D("10"),
                                     current_tax=D("100"), previous_tax=D("100"), acconto_pct=D("100"), explicit_advances=D("70"))
    assert t.saldo_paid == D("15") and t.opening_credit_left == D("0")
    assert t.acconti_paid == D("70") and t.generated_debt == D("30")
    assert t.rate_paid == D("10") and t.cash_out == D("15") + D("70") + D("10")
    big = tax_settlement_saldo_acconto(opening_credit=D("100"), saldo_due=D("40"), rate_due=D("0"),
                                       current_tax=D("0"), previous_tax=D("0"), acconto_pct=D("0"), explicit_advances=None)
    assert big.saldo_paid == D("0") and big.opening_credit_left == D("60") and big.acconti_paid == D("0")

def test_explicit_zero_advances_means_not_declared_and_falls_back_to_pct():
    """Lo zero esplicito non è un override: significa 'non dichiarato' e ricade sulla percentuale."""
    t = tax_settlement_saldo_acconto(opening_credit=D("0"), saldo_due=D("0"), rate_due=D("0"),
                                     current_tax=D("100"), previous_tax=D("100"), acconto_pct=D("50"), explicit_advances=D("0"))
    assert t.acconti_paid == D("50"), "Explicit zero deve ricadere sulla percentuale"
    assert t.generated_debt == D("50"), "Debito calcolato su acconti dalla percentuale, non su zero"


def test_zero_acconto_pct_without_explicit_means_no_advances():
    """acconto_pct = 0 senza importo esplicito ⇒ zero acconti assoluti."""
    t = tax_settlement_saldo_acconto(opening_credit=D("0"), saldo_due=D("0"), rate_due=D("0"),
                                     current_tax=D("100"), previous_tax=D("100"), acconto_pct=D("0"), explicit_advances=None)
    assert t.acconti_paid == D("0"), "Zero percentuale ⇒ zero acconti"
    assert t.cash_out == D("0"), "Cash-out non comprende acconti quando acconto_pct=0"
    assert t.generated_debt == D("100"), "Debito è l'intera imposta corrente"
