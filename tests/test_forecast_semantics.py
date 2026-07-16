"""Non-inventive rules shared by the ordinary budget forecast."""

from decimal import Decimal
from types import SimpleNamespace

import pytest

from calculations.forecast_engine import ForecastEngine


D = Decimal


def test_legacy_total_investment_is_not_split_fifty_fifty():
    assumption = SimpleNamespace(
        intangible_investments=D("0"),
        tangible_investments=D("0"),
        investments=D("100"),
    )

    with pytest.raises(ValueError, match="automatic 50/50 allocation is disabled"):
        ForecastEngine._get_split_investments(assumption)


def test_budget_pre_tax_result_uses_the_canonical_ce_formula():
    income = SimpleNamespace(
        ce01_ricavi_vendite=D("1000"),
        ce03a_incrementi_immobilizzazioni=D("100"),
        ce11b_altri_accantonamenti=D("40"),
        ce17_rettifiche_attivita_fin=D("999"),
        ce17a_rivalutazioni=D("20"),
        ce17b_svalutazioni=D("5"),
    )

    # 1000 + 100 - 40 + (20 - 5); aggregate ce17 is deliberately ignored
    # because the source supplied its more specific D.18/D.19 detail.
    assert ForecastEngine._pbt_from_income(income) == D("1075")
