"""Il rendiconto ha una riga propria per debiti e crediti tributari (commercialista, 2026-09-18).

La variazione tributaria esce da «crediti» e «debiti» ed entra in `delta_tax`; il totale
della variazione del circolante non cambia.
"""
from decimal import Decimal as D

from backend.app.calculations.cashflow_detailed import DetailedCashFlowCalculator
from backend.app.services import assumptions_service
from database.models import BudgetScenario, FinancialYear, ForecastYear
from tests.e2e_kit import memory_sessions, seed_base_year


def _v(bs, campo):
    return D(str(getattr(bs, campo) or 0))


def test_la_variazione_tributaria_ha_la_sua_riga_e_il_totale_non_cambia():
    engine, sessions = memory_sessions()
    db = sessions()
    try:
        company_id, fy_id = seed_base_year(db, user_id="cf-tributi")
        base = db.query(FinancialYear).get(fy_id)
        sc = BudgetScenario(company_id=company_id, name="t", base_year=2026, scenario_type="budget")
        db.add(sc); db.commit()
        righe = [dict(forecast_year=a, revenue_growth_pct=5, tax_rate=27.9) for a in (2027, 2028)]
        esito = assumptions_service.bulk_upsert_assumptions(db, sc.id, righe, auto_generate=True)
        assert esito["forecast_generated"] is True, esito["message"]
        prev = base.balance_sheet
        visti = 0
        for anno in (2027, 2028):
            fy = db.query(ForecastYear).filter_by(scenario_id=sc.id, year=anno).one()
            cur = fy.balance_sheet
            wc = DetailedCashFlowCalculator.calculate(
                bs_current=cur, bs_previous=prev, inc_current=fy.income_statement,
                year=anno).operating_activities.working_capital_changes
            atteso = ((_v(cur, "sp16e_debiti_tributari_breve") + _v(cur, "sp17e_debiti_tributari_lungo"))
                      - (_v(prev, "sp16e_debiti_tributari_breve") + _v(prev, "sp17e_debiti_tributari_lungo"))
                      - (_v(cur, "sp06e_crediti_tributari_breve") + _v(cur, "sp07e_crediti_tributari_lungo"))
                      + (_v(prev, "sp06e_crediti_tributari_breve") + _v(prev, "sp07e_crediti_tributari_lungo")))
            assert wc.delta_tax == atteso.quantize(D("0.01")), anno
            assert wc.delta_receivables == (
                (_v(prev, "sp06_crediti_breve") - _v(prev, "sp06e_crediti_tributari_breve"))
                - (_v(cur, "sp06_crediti_breve") - _v(cur, "sp06e_crediti_tributari_breve"))
            ).quantize(D("0.01")), anno
            assert wc.total == (wc.delta_inventory + wc.delta_receivables + wc.delta_payables + wc.delta_tax
                                + wc.delta_accruals_deferrals_active + wc.delta_accruals_deferrals_passive
                                + wc.other_wc_changes), anno
            visti += atteso != 0
            prev = cur
        assert visti, "il kit non ha mosso la posizione tributaria: il test non proverebbe nulla"
    finally:
        db.close()
        engine.dispose()
