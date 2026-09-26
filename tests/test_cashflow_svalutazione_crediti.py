"""La svalutazione dei crediti netti non deve diventare finanza fittizia."""

from decimal import Decimal as D

from backend.app.calculations.cashflow_detailed import DetailedCashFlowCalculator
from backend.app.services import assumptions_service
from database.models import BudgetScenario, FinancialYear, ForecastYear
from tests.e2e_kit import memory_sessions, seed_base_year


def test_svalutazione_crediti_non_finanzia_il_rendiconto():
    engine, sessions = memory_sessions()
    db = sessions()
    try:
        company_id, fy_id = seed_base_year(db, user_id="cf-svalutazione")
        base = db.get(FinancialYear, fy_id)
        scenario = BudgetScenario(
            company_id=company_id, name="Svalutazione crediti", base_year=2026,
            scenario_type="budget",
        )
        db.add(scenario)
        db.commit()
        result = assumptions_service.bulk_upsert_assumptions(
            db, scenario.id,
            [{"forecast_year": 2027, "revenue_growth_pct": 5,
              "tax_rate": 30, "ce09d_override": 10000}],
            auto_generate=True,
        )
        assert result["forecast_generated"] is True, result["message"]

        forecast = db.query(ForecastYear).filter_by(
            scenario_id=scenario.id, year=2027,
        ).one()
        cashflow = DetailedCashFlowCalculator.calculate(
            bs_current=forecast.balance_sheet,
            bs_previous=base.balance_sheet,
            inc_current=forecast.income_statement,
            year=2027,
        )
        operating = cashflow.operating_activities
        net_receivables_change = (
            D(base.balance_sheet.sp06_crediti_breve)
            - D(base.balance_sheet.sp06e_crediti_tributari_breve)
            - D(forecast.balance_sheet.sp06_crediti_breve)
            + D(forecast.balance_sheet.sp06e_crediti_tributari_breve)
        )
        assert operating.non_cash_adjustments.write_downs == D("10000.00")
        assert operating.working_capital_changes.delta_receivables == (
            net_receivables_change - D("10000.00")
        ).quantize(D("0.01"))
        assert cashflow.cash_reconciliation.third_party_funds_gap == D("0.00")
    finally:
        db.close()
        engine.dispose()
