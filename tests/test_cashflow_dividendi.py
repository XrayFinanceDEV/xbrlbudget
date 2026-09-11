"""Il rendiconto dettagliato rimette i dividendi nell'operativo e dichiara lo scarto dei mezzi di terzi (lotto 3A, Task 6).

Holding del kit (`ce13` 30.000): oggi operativo −10.000,00, mezzi di terzi 30.000,00, debito finanziario misurato 0,00.
Kit senza partecipazioni: operativo 80.541,22 (2027) e 125.893,62 (2028), scarto zero, e tale resta.
"""
from decimal import Decimal as D

from backend.app.calculations.cashflow_detailed import DetailedCashFlowCalculator
from backend.app.services import analysis_service, assumptions_service
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


def test_l_analisi_dichiara_lo_scarto_dei_mezzi_di_terzi_come_il_rendiconto():
    """`GET /analysis` (analysis_service._serialize_cash_reconciliation) deve emettere
    `third_party_funds_gap` con lo stesso valore del calcolatore usato da
    `GET /detailed-cashflow` (Importante 1 della revisione del Task 6): il tipo
    frontend lo dichiara obbligatorio, e senza questa chiave un client di
    `/analysis` legge `undefined` al posto di un numero.
    """
    engine, sessions = memory_sessions()
    db = sessions()
    try:
        company_id, fy_id = seed_base_year(db, user_id="dividendi-analysis", holding=True)
        base = db.query(FinancialYear).get(fy_id)
        scenario = BudgetScenario(company_id=company_id, name="dividendi-analysis", base_year=2026, scenario_type="budget")
        db.add(scenario)
        db.commit()
        righe = [dict(forecast_year=anno, revenue_growth_pct=3.33, tax_rate=27.9) for anno in (2027, 2028)]
        esito = assumptions_service.bulk_upsert_assumptions(db, scenario.id, righe, auto_generate=True)
        assert esito["forecast_generated"] is True, esito["message"]

        analisi = analysis_service.get_complete_analysis(db, company_id, scenario.id)
        anni = {anno["base_year"]: anno["cash_reconciliation"] for anno in analisi["calculations"]["cashflow"]["years"]}

        precedente = base.balance_sheet
        fuori = []
        for anno in (2027, 2028):
            fy = db.query(ForecastYear).filter(ForecastYear.scenario_id == scenario.id, ForecastYear.year == anno).one()
            atteso = DetailedCashFlowCalculator.calculate(
                bs_current=fy.balance_sheet, bs_previous=precedente, inc_current=fy.income_statement, year=anno
            ).cash_reconciliation.third_party_funds_gap
            precedente = fy.balance_sheet

            rec = anni.get(anno - 1)
            assert rec is not None, f"{anno}: nessuna riconciliazione emessa da /analysis per l'anno base {anno - 1}"
            if "third_party_funds_gap" not in rec:
                fuori.append(f"{anno}: /analysis non emette third_party_funds_gap")
            elif D(str(rec["third_party_funds_gap"])) != atteso:
                fuori.append(f"{anno}: /analysis dichiara {rec['third_party_funds_gap']}, il rendiconto {atteso}")
        assert not fuori, "\n".join(fuori)
    finally:
        db.close()
        engine.dispose()
