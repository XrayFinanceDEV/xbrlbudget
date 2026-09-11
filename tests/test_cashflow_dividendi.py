"""Il rendiconto dettagliato rimette i dividendi nell'operativo e dichiara lo scarto dei mezzi di terzi (lotto 3A, Task 6).

Holding del kit (`ce13` 30.000): oggi operativo −10.000,00, mezzi di terzi 30.000,00, debito finanziario misurato 0,00.
Kit senza partecipazioni: operativo 80.541,22 (2027) e 125.893,62 (2028), scarto zero, e tale resta.
"""
from decimal import Decimal as D

from backend.app.calculations.cashflow_detailed import DetailedCashFlowCalculator
from backend.app.services import assumptions_service
from database.models import BudgetScenario, FinancialYear, ForecastYear
from tests.e2e_kit import memory_sessions, seed_base_year


def _rendiconti(holding):
    engine, sessions = memory_sessions()
    db = sessions()
    try:
        company_id, fy_id = seed_base_year(db, user_id=f"dividendi-{holding}", holding=holding)
        base = db.query(FinancialYear).get(fy_id)
        scenario = BudgetScenario(company_id=company_id, name="dividendi", base_year=2026, scenario_type="budget")
        db.add(scenario)
        db.commit()
        righe = [dict(forecast_year=anno, revenue_growth_pct=3.33, tax_rate=27.9) for anno in (2027, 2028)]
        esito = assumptions_service.bulk_upsert_assumptions(db, scenario.id, righe, auto_generate=True)
        assert esito["forecast_generated"] is True, esito["message"]
        precedente, rendiconti = base.balance_sheet, {}
        for anno in (2027, 2028):
            fy = db.query(ForecastYear).filter(ForecastYear.scenario_id == scenario.id, ForecastYear.year == anno).one()
            rendiconti[anno] = DetailedCashFlowCalculator.calculate(
                bs_current=fy.balance_sheet, bs_previous=precedente, inc_current=fy.income_statement, year=anno)
            precedente = fy.balance_sheet
        return rendiconti
    finally:
        db.close()
        engine.dispose()


def test_sulla_holding_i_dividendi_incassati_stanno_nell_operativo_e_lo_scarto_e_zero():
    fuori = []
    for anno, cf in _rendiconti(holding=True).items():
        op, rec = cf.operating_activities, cf.cash_reconciliation
        confronti = {
            "dividendi sottratti all'utile": (op.start.dividends, "30000.00"),
            "dividendi incassati": (op.cash_adjustments.dividends_received, "30000.00"),
            "flusso operativo": (op.total_operating_cashflow, "20000.00"),
            "mezzi di terzi": (cf.financing_activities.third_party_funds.net, "0.00"),
            "scarto dichiarato": (getattr(rec, "third_party_funds_gap", None), "0.00"),
            "variazione di cassa del rendiconto": (rec.total_cashflow, "20000.00"),
        }
        fuori += [f"{anno} {k}: {v}, atteso {a}" for k, (v, a) in confronti.items() if v != D(a)]
        if rec.total_cashflow != rec.difference:
            fuori.append(f"{anno} controllo di sanita': rendiconto {rec.total_cashflow} != variazione sp09 {rec.difference}")
    assert not fuori, "\n".join(fuori)


def test_senza_partecipazioni_nulla_cambia_e_lo_scarto_e_dichiarato_a_zero():
    attesi = {2027: "80541.22", 2028: "125893.62"}
    fuori = []
    for anno, cf in _rendiconti(holding=False).items():
        op, rec = cf.operating_activities, cf.cash_reconciliation
        if op.total_operating_cashflow != D(attesi[anno]):
            fuori.append(f"{anno} operativo {op.total_operating_cashflow}, atteso {attesi[anno]}")
        if op.cash_adjustments.dividends_received != D("0.00"):
            fuori.append(f"{anno} dividendi incassati {op.cash_adjustments.dividends_received}")
        if getattr(rec, "third_party_funds_gap", None) != D("0.00"):
            fuori.append(f"{anno} scarto {getattr(rec, 'third_party_funds_gap', None)}, atteso 0,00")
    assert not fuori, "\n".join(fuori)
