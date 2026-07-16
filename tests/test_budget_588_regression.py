"""Regression coverage for the adjusted-column four-sections statement."""

from decimal import Decimal
from pathlib import Path
import sys

import pytest

TESTS_DIR = Path(__file__).parent
sys.path.insert(0, str(TESTS_DIR))

from _prod_route_c_runner import run_prod_route_c  # noqa: E402


def test_budget_588_uses_final_adjusted_column_without_fake_prior_year():
    matches = list((Path(__file__).parents[1] / "Test" / "july_budget").glob(
        "budget_588_*.pdf"
    ))
    if not matches:
        pytest.skip("local regression PDF budget_588 is not available")

    result = run_prod_route_c(str(matches[0]))

    assert result["quadra"] is True
    assert result["masked"] is False
    assert result["plug_residual"] == Decimal("0")
    assert result["totale_attivo"] == Decimal("1023681.96")
    assert result["sp13"] == Decimal("42754.47")
