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


# ── #62 S13: «imposte pagate» = versamenti effettivi del motore ───────────────────────────────

def _scenario_versamenti(db):
    company_id, fy_id = seed_base_year(db, user_id="cf-versate")
    base = db.query(FinancialYear).get(fy_id)
    sc = BudgetScenario(company_id=company_id, name="v", base_year=2026, scenario_type="budget")
    db.add(sc); db.commit()
    righe = [dict(forecast_year=a, revenue_growth_pct=5, tax_rate=27.9) for a in (2027, 2028)]
    esito = assumptions_service.bulk_upsert_assumptions(db, sc.id, righe, auto_generate=True)
    assert esito["forecast_generated"] is True, esito["message"]
    return company_id, sc, base


def test_R1_imposte_pagate_sono_i_versamenti_e_la_cassa_non_cambia():
    engine, sessions = memory_sessions()
    db = sessions()
    try:
        _, sc, base = _scenario_versamenti(db)
        prev = base.balance_sheet
        differenti = 0
        for anno in (2027, 2028):
            fy = db.query(ForecastYear).filter_by(scenario_id=sc.id, year=anno).one()
            versate = D(fy.engine_meta["imposte_versate"])
            kw = dict(bs_current=fy.balance_sheet, bs_previous=prev, inc_current=fy.income_statement,
                      year=anno, erogazioni=None)
            vecchio = DetailedCashFlowCalculator.calculate(**kw)
            nuovo = DetailedCashFlowCalculator.calculate(**kw, imposte_versate=versate)
            ca_v, ca_n = vecchio.operating_activities.cash_adjustments, nuovo.operating_activities.cash_adjustments
            assert ca_v.taxes_paid == -D(fy.income_statement.ce20_imposte).quantize(D("0.01"))
            assert ca_n.taxes_paid == -versate
            # la cassa non si muove: operativo e riconciliazione identici
            assert nuovo.operating_activities.total_operating_cashflow == vecchio.operating_activities.total_operating_cashflow
            assert nuovo.cash_reconciliation == vecchio.cash_reconciliation
            # segno: delta_tax (fonte di cassa) cresce di quanto taxes_paid (uscita) peggiora: stessa cassa
            wc_v = vecchio.operating_activities.working_capital_changes
            wc_n = nuovo.operating_activities.working_capital_changes
            assert wc_n.delta_tax == wc_v.delta_tax + (ca_v.taxes_paid - ca_n.taxes_paid)
            differenti += ca_v.taxes_paid != ca_n.taxes_paid
            prev = fy.balance_sheet
        assert differenti, "il kit non separa versamenti e imposta di CE: il test non proverebbe nulla"
    finally:
        db.close()
        engine.dispose()


def test_R1_le_due_pagine_del_rendiconto_mostrano_le_stesse_imposte_pagate():
    """Regola F3: /analysis e la pagina Rendiconto leggono lo stesso `engine_meta['imposte_versate']`."""
    from backend.app.services import analysis_service, calculation_service
    engine, sessions = memory_sessions()
    db = sessions()
    try:
        company_id, sc, _ = _scenario_versamenti(db)
        analisi = analysis_service.get_complete_analysis(db, company_id, sc.id)
        anni = {c["year"]: c for c in analisi["calculations"]["cashflow"]["years"]}
        pagina = calculation_service.calculate_detailed_cashflow_historical_and_forecast(
            db, company_id, sc.id, 2026)
        visti = 0
        for cf in pagina.cashflows:
            if cf.year not in (2027, 2028):
                continue
            fy = db.query(ForecastYear).filter_by(scenario_id=sc.id, year=cf.year).one()
            versate = D(fy.engine_meta["imposte_versate"])
            tp = cf.operating_activities.cash_adjustments.taxes_paid
            assert tp == -versate
            assert D(str(anni[cf.year]["operating"]["cash_adjustments"]["taxes_paid"])) == tp
            visti += 1
        assert visti == 2
    finally:
        db.close()
        engine.dispose()


def test_R1_senza_imposte_versate_il_rendiconto_e_quello_di_prima():
    engine, sessions = memory_sessions()
    db = sessions()
    try:
        _, sc, base = _scenario_versamenti(db)
        fy = db.query(ForecastYear).filter_by(scenario_id=sc.id, year=2027).one()
        cf = DetailedCashFlowCalculator.calculate(
            bs_current=fy.balance_sheet, bs_previous=base.balance_sheet,
            inc_current=fy.income_statement, year=2027)
        assert cf.operating_activities.cash_adjustments.taxes_paid == -D(fy.income_statement.ce20_imposte).quantize(D("0.01"))
    finally:
        db.close()
        engine.dispose()


def test_R1_in_via_manuale_imposte_versate_e_none():
    from calculations.forecast_engine import engine_meta
    assert engine_meta({"imposte": {"mode": "manual", "saldo_paid": D("0")}})["imposte_versate"] is None
    assert engine_meta({})["imposte_versate"] is None
    meta = engine_meta({"imposte": {"mode": "saldo_acconto", "saldo_paid": D("100"), "acconti_paid": D("50"),
                                    "rate_paid": D("10"), "credito_compensato": D("20"),
                                    "credito_storico_compensato": D("5.005")}})
    assert meta["imposte_versate"] == "135.00"
