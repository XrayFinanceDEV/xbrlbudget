"""M1-05B — the six final-report chart series, built from already-calculated values.

Spec §6.5 lists six decision-oriented charts.  This module *selects, aligns and
renames* numbers the analysis service and the persisted forecast already
produce; it adds no financial formula of its own (spec §10: the assembler must
not replicate ``analysis_service`` or the forecast engine).  Where a chart line
has no canonical backend producer — the PFN and the DSCR — the value is only
emitted when the caller hands it in already measured; inventing the arithmetic
here would create a third PFN copy next to ``frontend/lib/budget-preview-rows.ts``
and ``frontend/lib/pratica-indicators.ts``, which already disagree on the term.

Every number leaving this module is a ``Decimal`` (or ``None``), compatible
with the strict string-decimal wire form of ``app.schemas.final_report``.
"""
from __future__ import annotations

import sys
import os
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Optional, Sequence

_backend_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _backend_path not in sys.path:
    sys.path.insert(0, _backend_path)

from app.schemas.final_report import ChartMetric, ChartSeries



def _decimal(value: Any) -> Optional[Decimal]:
    """Coerce an already-calculated value to Decimal; never trust float types."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, int):
        result = Decimal(value)
    elif isinstance(value, float):
        result = Decimal(repr(value))
    elif isinstance(value, str):
        try:
            result = Decimal(value)
        except InvalidOperation:
            raise ValueError(f"chart value {value!r} is not a decimal")
    else:
        raise ValueError(f"unsupported chart value {type(value).__name__}")
    return result if result.is_finite() else None


def _entry(mapping: Optional[Mapping], year: int) -> Optional[Mapping[str, Any]]:
    """Find one by-year record under either canonical spelling of the year key.

    ``analysis_service`` keys ``calculations.by_year`` with ``str(year)`` and
    each cashflow entry with an int ``"year"`` field; the assembler may hand
    over either shape.  An absent record is absent data, never a zero.
    """
    if mapping is None:
        return None
    entry = mapping.get(year, mapping.get(str(year)))
    return entry if isinstance(entry, Mapping) else None


def _walk(entry: Optional[Mapping[str, Any]], *path: str) -> Optional[Any]:
    node: Any = entry
    for key in path:
        if not isinstance(node, Mapping):
            return None
        node = node.get(key)
    return node


def _metric(key: str, label: str, values: Sequence[Optional[Decimal]]) -> ChartMetric:
    return ChartMetric(key=key, label=label, values=list(values))


def build_chart_series(
    forecast_years: Sequence[Any],
    *,
    calculations_by_year: Mapping[Any, Mapping[str, Any]],
    cashflow_years: Sequence[Mapping[str, Any]],
    net_financial_position_by_year: Optional[Mapping[Any, Any]] = None,
    dscr_by_year: Optional[Mapping[Any, Any]] = None,
) -> list[ChartSeries]:
    """Build the six canonical series, in canonical order, for one forecast.

    ``forecast_years`` — persisted ``ForecastYear`` ORM rows of the scenario in
    plan order; categories are exactly their years, so chart categories and
    forecast years can never drift apart.

    ``calculations_by_year`` — the ``calculations.by_year`` block of
    ``analysis_service.get_complete_analysis`` (ratios per year).

    ``cashflow_years`` — the ``calculations.cashflow.years`` list of the same
    block (each entry already matched to its year).  The first plan year can be
    legitimately missing there when no prior-year pair was computed: its flows
    come out as ``None``, not as a fabricated zero.

    ``net_financial_position_by_year`` / ``dscr_by_year`` — values measured
    elsewhere and passed in; see the module docstring for why they are never
    computed here.
    """
    years = [int(forecast_year.year) for forecast_year in forecast_years]
    if not years:
        raise ValueError("build_chart_series richiede almeno un anno di previsione")
    if len(set(years)) != len(years):
        raise ValueError("build_chart_series: anni di previsione duplicati")
    cashflow_by_year = {
        int(entry["year"]): entry for entry in cashflow_years or [] if isinstance(entry, Mapping) and "year" in entry
    }

    def ratios(year: int, group: str, name: str) -> Optional[Decimal]:
        return _decimal(_walk(_entry(calculations_by_year, year), "ratios", group, name))

    def series_values(pick: Any) -> list[Optional[Decimal]]:
        return [pick(year) for year in years]

    def attribute_value(owner: Any, attribute: str) -> Optional[Decimal]:
        # A property that cannot resolve (half-populated aggregate rows) yields
        # "no data" for that cell, never a fabricated zero and never a crash:
        # the renderer shows a gap, which is the honest "non lo so".
        if owner is None:
            return None
        try:
            return _decimal(getattr(owner, attribute))
        except (AttributeError, TypeError):
            return None

    def balance(year: int, attribute: str) -> Optional[Decimal]:
        row = _forecast_row(forecast_years, year)
        return attribute_value(getattr(row, "balance_sheet", None) if row is not None else None, attribute)

    def statement(year: int, attribute: str) -> Optional[Decimal]:
        row = _forecast_row(forecast_years, year)
        return attribute_value(getattr(row, "income_statement", None) if row is not None else None, attribute)

    def flow(year: int, *path: str) -> Optional[Decimal]:
        return _decimal(_walk(cashflow_by_year.get(year), *path))

    def supplied(mapping: Optional[Mapping[Any, Any]]) -> list[Optional[Decimal]]:
        return [None if mapping is None else _decimal(mapping.get(year, mapping.get(str(year)))) for year in years]

    income_results = ChartSeries(
        id="income_results",
        title="Ricavi, EBITDA e risultato netto",
        unit="eur",
        categories=years,
        series=[
            _metric("revenue", "Ricavi", series_values(lambda y: statement(y, "revenue"))),
            _metric("ebitda", "EBITDA", series_values(lambda y: statement(y, "ebitda"))),
            _metric("net_profit", "Utile netto", series_values(lambda y: statement(y, "net_profit"))),
        ],
    )
    margins = ChartSeries(
        id="margins",
        title="Margini EBITDA ed EBIT",
        unit="percent",
        categories=years,
        series=[
            _metric("ebitda_margin", "Margine EBITDA", series_values(lambda y: ratios(y, "profitability", "ebitda_margin"))),
            _metric("ebit_margin", "Margine EBIT", series_values(lambda y: ratios(y, "profitability", "ebit_margin"))),
        ],
    )
    cashflows = ChartSeries(
        id="cashflows",
        title="Flussi di cassa e cassa finale",
        unit="eur",
        categories=years,
        series=[
            _metric("operating", "Flusso operativo", series_values(lambda y: flow(y, "operating", "total_operating_cashflow"))),
            _metric("investing", "Flusso investimenti", series_values(lambda y: flow(y, "investing", "total_investing_cashflow"))),
            _metric("financing", "Flusso finanziamento", series_values(lambda y: flow(y, "financing", "total_financing_cashflow"))),
            _metric("cash_end", "Cassa finale", series_values(lambda y: flow(y, "cash_reconciliation", "cash_ending"))),
        ],
    )
    liquidity_metrics = [
        _metric("cash", "Cassa", series_values(lambda y: balance(y, "sp09_disponibilita_liquide"))),
        _metric("financial_debt", "Debito finanziario", series_values(lambda y: balance(y, "financial_debt_total"))),
    ]
    if net_financial_position_by_year is not None:
        liquidity_metrics.append(_metric("pfn", "PFN", supplied(net_financial_position_by_year)))
    liquidity_debt = ChartSeries(
        id="liquidity_debt",
        title="Cassa, debito finanziario e PFN",
        unit="eur",
        categories=years,
        series=liquidity_metrics,
    )
    working_capital_days = ChartSeries(
        id="working_capital_days",
        title="Giorni di rotazione del circolante",
        unit="days",
        categories=years,
        series=[
            _metric("dso", "DSO", series_values(lambda y: ratios(y, "activity", "receivables_turnover_days"))),
            _metric("dio", "DIO", series_values(lambda y: ratios(y, "activity", "inventory_turnover_days"))),
            _metric("dpo", "DPO", series_values(lambda y: ratios(y, "activity", "payables_turnover_days"))),
        ],
    )
    coverage_metrics = []
    if dscr_by_year is not None:
        coverage_metrics.append(_metric("dscr", "DSCR", supplied(dscr_by_year)))
    coverage_metrics += [
        _metric("fixed_assets_coverage_with_equity_and_ltdebt", "Coperture immobilizzi con PN+PF",
                series_values(lambda y: ratios(y, "coverage", "fixed_assets_coverage_with_equity_and_ltdebt"))),
        _metric("fixed_assets_coverage_with_equity", "Copertura immobilizzi con PN",
                series_values(lambda y: ratios(y, "coverage", "fixed_assets_coverage_with_equity"))),
        _metric("independence_from_third_parties", "Indipendenza dai terzi",
                series_values(lambda y: ratios(y, "coverage", "independence_from_third_parties"))),
    ]
    coverage = ChartSeries(
        id="coverage",
        title="Indicatori di copertura",
        unit="ratio",
        categories=years,
        series=coverage_metrics,
    )

    return [income_results, margins, cashflows, liquidity_debt, working_capital_days, coverage]


def _forecast_row(forecast_years: Sequence[Any], year: int) -> Optional[Any]:
    for row in forecast_years:
        if int(getattr(row, "year", -1)) == year:
            return row
    return None
