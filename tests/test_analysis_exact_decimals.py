"""The dossier can retain Decimal values from the canonical analysis output."""
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from typing import NamedTuple

import pytest

from backend.app.services import analysis_service
from backend.app.services import assumptions_service
from database.models import BudgetScenario
from tests.e2e_kit import memory_sessions, seed_base_year


def _analysis_fixture():
    engine, sessions = memory_sessions()
    db = sessions()
    company_id, year_id = seed_base_year(db, user_id="analysis-exact")
    scenario = BudgetScenario(
        company_id=company_id, name="precision", base_year=2026, scenario_type="budget"
    )
    db.add(scenario)
    db.commit()
    result = assumptions_service.bulk_upsert_assumptions(
        db, scenario.id,
        [
            {"forecast_year": 2027, "revenue_growth_pct": 3.33, "tax_rate": 27.9},
            {"forecast_year": 2028, "revenue_growth_pct": 3.33, "tax_rate": 27.9},
        ],
        auto_generate=True,
    )
    assert result["forecast_generated"] is True
    return engine, db, company_id, scenario.id, year_id


def _as_legacy(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {key: _as_legacy(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_as_legacy(item) for item in value]
    return value


def test_exact_mode_retains_decimals_through_statements_ratios_and_cashflow():
    engine, db, company_id, scenario_id, _ = _analysis_fixture()
    try:
        exact = analysis_service.get_complete_analysis(
            db, company_id, scenario_id, exact_decimals=True
        )
        legacy = analysis_service.get_complete_analysis(db, company_id, scenario_id)

        statement = exact["historical_years"][-1]["balance_sheet"]
        assert isinstance(statement["sp09_disponibilita_liquide"], Decimal)
        assert isinstance(statement["total_assets"], Decimal)
        assert isinstance(exact["calculations"]["by_year"]["2026"]["ratios"]["liquidity"]["current_ratio"], Decimal)
        assert isinstance(exact["calculations"]["cashflow"]["years"][0]["operating"]["start"]["net_profit"], Decimal)
        assert _as_legacy(exact) == legacy
    finally:
        db.close()
        engine.dispose()


def test_statement_serializer_does_not_lose_a_decimal_larger_than_ieee_754_precision():
    class Statement:
        sp09_disponibilita_liquide = Decimal("9007199254740993.01")
        total_assets = sp09_disponibilita_liquide
        total_equity = sp09_disponibilita_liquide
        total_debt = sp09_disponibilita_liquide
        fixed_assets = sp09_disponibilita_liquide
        current_assets = sp09_disponibilita_liquide
        current_liabilities = sp09_disponibilita_liquide
        working_capital_net = sp09_disponibilita_liquide

    statement = Statement()
    token = analysis_service._exact_decimals.set(True)
    try:
        exact = analysis_service._serialize_balance_sheet(statement)
    finally:
        analysis_service._exact_decimals.reset(token)

    assert exact["sp09_disponibilita_liquide"] == Decimal("9007199254740993.01")
    assert isinstance(analysis_service._serialize_balance_sheet(statement)["sp09_disponibilita_liquide"], float)


def test_nested_and_null_namedtuple_serialization_keeps_the_legacy_shape():
    class Nested(NamedTuple):
        amount: Decimal

    class Result(NamedTuple):
        nested: Nested
        unavailable: Decimal | None

    value = Result(Nested(Decimal("1.25")), None)
    assert analysis_service._namedtuple_to_dict(value) == {
        "nested": {"amount": 1.25},
        "unavailable": None,
    }

    token = analysis_service._exact_decimals.set(True)
    try:
        assert analysis_service._namedtuple_to_dict(value) == {
            "nested": {"amount": Decimal("1.25")},
            "unavailable": None,
        }
    finally:
        analysis_service._exact_decimals.reset(token)


def test_exact_mode_is_reset_after_an_exception_and_default_serializers_stay_float():
    engine, db, company_id, scenario_id, _ = _analysis_fixture()
    try:
        with pytest.raises(ValueError):
            analysis_service.get_complete_analysis(
                db, company_id, scenario_id + 1, exact_decimals=True
            )

        assert analysis_service._output_number(Decimal("9007199254740993.01")) == float(Decimal("9007199254740993.01"))
        assert isinstance(analysis_service._output_number(Decimal("1.00")), float)
    finally:
        db.close()
        engine.dispose()


def test_exact_mode_is_isolated_between_concurrent_calls(monkeypatch):
    barrier = Barrier(2)

    def stubbed_analysis(*args):
        barrier.wait()
        return analysis_service._output_number(Decimal("1.25"))

    monkeypatch.setattr(analysis_service, "_get_complete_analysis", stubbed_analysis)
    with ThreadPoolExecutor(max_workers=2) as executor:
        exact, legacy = list(executor.map(
            lambda exact_decimals: analysis_service.get_complete_analysis(
                None, 1, 1, exact_decimals=exact_decimals
            ),
            (True, False),
        ))

    assert exact == Decimal("1.25")
    assert legacy == 1.25
