"""M1-05B — the six chart series, read from canonical forecast/analysis values.

Ownership: this file and ``backend/app/services/final_report_charts.py`` only.
Every expected number here is taken from the same canonical producer the rest
of the app reads (persisted ``ForecastYear`` statements, ``analysis_service``
ratio and cashflow blocks) — the test never re-derives a value with its own
formula, or a divergence in the module could hide behind one.
"""
import sys
from decimal import Decimal

import pytest

import backend.app.services.final_report_charts as fra_charts  # noqa: F401 — loads the backend/ path shim
from app.schemas.final_report import ChartSeries
from app.services.final_report_charts import build_chart_series
from app.services.analysis_service import _serialize_income_statement
from database.models import ForecastBalanceSheet, ForecastIncomeStatement, ForecastYear


SERIES_ORDER = ["income_results", "margins", "cashflows", "liquidity_debt", "working_capital_days", "coverage"]


def _year(year: int, *, revenue: Decimal, amort: Decimal = Decimal("10"), taxes: Decimal = Decimal("5"),
          cash: Decimal = Decimal("100"), bank_short: Decimal = Decimal("40"),
          bank_long: Decimal = Decimal("60"), other_financial: Decimal = Decimal("0")) -> ForecastYear:
    row = ForecastYear(year=year)
    row.income_statement = ForecastIncomeStatement(
        ce01_ricavi_vendite=revenue,
        ce05_materie_prime=Decimal("100"),
        ce09_ammortamenti=amort,
        ce20_imposte=taxes,
    )
    row.balance_sheet = ForecastBalanceSheet(
        sp09_disponibilita_liquide=cash,
        sp16a_debiti_banche_breve=bank_short,
        sp16b_debiti_altri_finanz_breve=other_financial,
        sp16c_debiti_obbligazioni_breve=Decimal("0"),
        sp17a_debiti_banche_lungo=bank_long,
        sp17b_debiti_altri_finanz_lungo=Decimal("0"),
        sp17c_debiti_obbligazioni_lungo=Decimal("0"),
    )
    return row


def _calculations(years, **overrides):
    """A by_year block in the exact shape analysis_service produces it."""
    import copy

    default = {
        "ratios": {
            "profitability": {"ebitda_margin": 12.5, "ebit_margin": 8.0, "net_margin": 5.0},
            "activity": {"receivables_turnover_days": 60.0, "inventory_turnover_days": 45.0,
                         "payables_turnover_days": 30.0},
            "coverage": {"fixed_assets_coverage_with_equity_and_ltdebt": 1.4,
                         "fixed_assets_coverage_with_equity": 1.1,
                         "independence_from_third_parties": 0.8},
        }
    }
    return {str(year): overrides.get(year, copy.deepcopy(default)) for year in years}


def _cashflows(years):
    return [
        {"year": year,
         "operating": {"total_operating_cashflow": 10.5},
         "investing": {"total_investing_cashflow": -2.25},
         "financing": {"total_financing_cashflow": 0},
         "cash_reconciliation": {"cash_ending": 100.0}}
        for year in years
    ]


def _build(forecast_years, **kwargs):
    years = [fy.year for fy in forecast_years]
    kwargs.setdefault("calculations_by_year", _calculations(years))
    kwargs.setdefault("cashflow_years", _cashflows(years[1:]))
    return build_chart_series(forecast_years, **kwargs)


def _series(series, sid):
    return next(s for s in series if s.id == sid)


def _metric(series_obj, key):
    return next(m for m in series_obj.series if m.key == key)


# ---------------------------------------------------------------------------
# Shape
# ---------------------------------------------------------------------------

def test_six_series_in_canonical_order_with_canonical_units():
    series = _build([_year(2027, revenue=Decimal("1000"))])
    assert [s.id for s in series] == SERIES_ORDER
    assert [s.unit for s in series] == ["eur", "percent", "eur", "eur", "days", "ratio"]
    for chart in series:
        assert len(chart.series) >= 1
        assert chart.title


def test_chart_series_pass_the_contract_validators():
    series = _build([_year(2027, revenue=Decimal("1000"))])
    for chart in series:
        ChartSeries.model_validate(chart.model_dump(mode="json"))


@pytest.mark.parametrize("count", [1, 3, 5])
def test_categories_and_every_metric_follow_the_forecast_horizon(count):
    forecast_years = [_year(2027 + i, revenue=Decimal(1000 + i)) for i in range(count)]
    series = _build(forecast_years)
    expected = list(range(2027, 2027 + count))
    for chart in series:
        assert chart.categories == expected
        for metric in chart.series:
            assert len(metric.values) == count


def test_empty_or_duplicated_years_are_refused():
    with pytest.raises(ValueError):
        build_chart_series([], calculations_by_year={}, cashflow_years=[])
    duplicated = [_year(2027, revenue=Decimal("1")), _year(2027, revenue=Decimal("2"))]
    with pytest.raises(ValueError):
        build_chart_series(duplicated, calculations_by_year=_calculations([2027, 2027]), cashflow_years=[])


# ---------------------------------------------------------------------------
# Value parity with the canonical producers
# ---------------------------------------------------------------------------

def test_income_series_equals_the_persisted_statement_aggregates():
    rows = [_year(2027, revenue=Decimal("1200"), amort=Decimal("120"), taxes=Decimal("60")),
            _year(2028, revenue=Decimal("1300"), amort=Decimal("120"), taxes=Decimal("70"))]
    series = _build(rows)
    income = _series(series, "income_results")
    for forecast_year in rows:
        index = forecast_year.year - 2027
        inc = forecast_year.income_statement
        assert _metric(income, "revenue").values[index] == inc.revenue
        assert _metric(income, "ebitda").values[index] == inc.ebitda
        assert _metric(income, "net_profit").values[index] == inc.net_profit


def test_income_series_matches_the_analysis_serialization_of_the_same_year():
    row = _year(2027, revenue=Decimal("1200"), amort=Decimal("120"), taxes=Decimal("60"))
    canonical = _serialize_income_statement(row.income_statement)
    series = _build([row], calculations_by_year={}, cashflow_years=[])
    income = _series(series, "income_results")
    for key in ("revenue", "ebitda", "net_profit"):
        assert _metric(income, key).values == [Decimal(repr(canonical[key]))]


def test_liquidity_series_reads_cash_and_the_models_financial_debt_helper():
    row = _year(2027, revenue=Decimal("1000"), cash=Decimal("33.30"),
                bank_short=Decimal("40"), bank_long=Decimal("60"))
    series = _build([row])
    liquidity = _series(series, "liquidity_debt")
    assert liquidity.title == "Cassa e debito finanziario"
    assert _metric(liquidity, "cash").values == [Decimal("33.30")]
    assert _metric(liquidity, "financial_debt").values == [row.balance_sheet.financial_debt_total]


def test_ratio_series_read_the_analysis_by_year_block_verbatim():
    years = [2027, 2028]
    rows = [_year(y, revenue=Decimal("1000")) for y in years]
    calcs = _calculations(years)
    calcs["2028"]["ratios"]["activity"]["receivables_turnover_days"] = 55.5
    series = _build(rows, calculations_by_year=calcs, cashflow_years=_cashflows(years))
    assert _metric(_series(series, "working_capital_days"), "dso").values == [Decimal("60.0"), Decimal("55.5")]
    assert _metric(_series(series, "margins"), "ebitda_margin").values == [Decimal("12.5"), Decimal("12.5")]
    coverage = _metric(_series(series, "coverage"), "fixed_assets_coverage_with_equity")
    assert coverage.values == [Decimal("1.1"), Decimal("1.1")]


def test_cashflow_series_is_matched_by_year_not_by_position():
    rows = [_year(y, revenue=Decimal("1000")) for y in (2027, 2028, 2029)]
    flows = _cashflows([2029, 2027])[::-1]  # the middle plan year was never paired
    series = _build(rows, cashflow_years=flows)
    cashflows = _series(series, "cashflows")
    assert _metric(cashflows, "operating").values == [Decimal("10.5"), None, Decimal("10.5")]
    assert _metric(cashflows, "cash_end").values == [Decimal("100.0"), None, Decimal("100.0")]


def test_missing_calculation_year_is_none_not_zero():
    rows = [_year(2027, revenue=Decimal("1000")), _year(2028, revenue=Decimal("1000"))]
    series = _build(rows, calculations_by_year={"2027": _calculations([2027])["2027"]},
                    cashflow_years=[])
    assert _metric(_series(series, "margins"), "ebit_margin").values == [Decimal("8.0"), None]
    assert _metric(_series(series, "working_capital_days"), "dpo").values == [Decimal("30.0"), None]


def test_nulls_and_negatives_pass_through():
    rows = [_year(2027, revenue=Decimal("-250.75"))]
    calcs = {"2027": {"ratios": {
        "profitability": {"ebitda_margin": None, "ebit_margin": -3.5},
        "activity": {"receivables_turnover_days": None, "inventory_turnover_days": None,
                     "payables_turnover_days": None},
        "coverage": {"fixed_assets_coverage_with_equity_and_ltdebt": None,
                     "fixed_assets_coverage_with_equity": None,
                     "independence_from_third_parties": None},
    }}}
    series = _build(rows, calculations_by_year=calcs, cashflow_years=[])
    assert _metric(_series(series, "income_results"), "revenue").values == [Decimal("-250.75")]
    assert _metric(_series(series, "margins"), "ebitda_margin").values == [None]
    assert _metric(_series(series, "margins"), "ebit_margin").values == [Decimal("-3.5")]


def test_values_are_decimals_never_floats():
    series = _build([_year(2027, revenue=Decimal("1000"))])
    for chart in series:
        for metric in chart.series:
            for value in metric.values:
                assert value is None or isinstance(value, Decimal), (chart.id, metric.key, value)


# ---------------------------------------------------------------------------
# PFN and DSCR stay caller-supplied
# ---------------------------------------------------------------------------

def test_pfn_and_dscr_are_absent_unless_measured_elsewhere():
    series = _build([_year(2027, revenue=Decimal("1000"))])
    assert "pfn" not in [m.key for m in _series(series, "liquidity_debt").series]
    assert "dscr" not in [m.key for m in _series(series, "coverage").series]


def test_pfn_and_dscr_are_read_verbatim_when_supplied():
    rows = [_year(2027, revenue=Decimal("1000")), _year(2028, revenue=Decimal("1000"))]
    series = _build(rows,
                    net_financial_position_by_year={2027: "-106.70", "2028": Decimal("12")},
                    dscr_by_year={2027: 1.25, 2028: None})
    assert _series(series, "liquidity_debt").title == "Cassa, debito finanziario e PFN"
    assert _metric(_series(series, "liquidity_debt"), "pfn").values == [Decimal("-106.70"), Decimal("12")]
    assert _metric(_series(series, "coverage"), "dscr").values == [Decimal("1.25"), None]


def test_missing_balance_sheet_or_statement_yields_none_cells():
    row = ForecastYear(year=2027)
    series = _build([row], calculations_by_year={}, cashflow_years=[])
    assert _metric(_series(series, "income_results"), "revenue").values == [None]
    assert _metric(_series(series, "liquidity_debt"), "cash").values == [None]


def test_contract_wires_into_a_full_model_shape():
    # The six series must be usable as the chart_series of FinalReportModel
    # (six distinct canonical ids, categories equal to the practice years).
    series = _build([_year(2027, revenue=Decimal("1000"))])
    assert len(series) == 6 and len({s.id for s in series}) == 6
    assert all(s.categories == [2027] for s in series)
    assert all(isinstance(s, ChartSeries) for s in series)
