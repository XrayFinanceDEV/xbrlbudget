"""I crediti verso soci (sp01) viaggiano con le loro sotto-voci nel previsionale.

SGH SRL (XBRL micro 2025): 15.000 di capitale sottoscritto e non versato, tutto in
sp01b. Il motore scriveva l'aggregato sp01 ma non sp01a/sp01b, persistiti a zero:
ogni anno di piano falliva la quadratura semantica (GERARCHIA INCOERENTE) e il
Business plan restava bloccato.
"""
from decimal import Decimal as D

from backend.app.api.v1 import budget_scenarios
from backend.app.schemas.budget import BudgetScenarioCreate
from database.models import BalanceSheet, FinancialYear
from importers.iv_cee_hierarchy import check_quadratura
from tests.e2e_kit import memory_sessions, read_forecast_maps, seed_base_year


def _genera(db, user, sp01a, sp01b):
    company_id, _ = seed_base_year(db, user_id=user)
    fy = db.query(FinancialYear).filter(FinancialYear.company_id == company_id).one()
    b = db.query(BalanceSheet).filter(BalanceSheet.financial_year_id == fy.id).one()
    b.sp01_crediti_soci = D(sp01a) + D(sp01b)
    b.sp01a_parte_richiamata = D(sp01a)
    b.sp01b_parte_da_richiamare = D(sp01b)
    b.sp09_disponibilita_liquide = (b.sp09_disponibilita_liquide or D("0")) - b.sp01_crediti_soci
    db.commit()
    sc = budget_scenarios.create_budget_scenario(
        company_id, BudgetScenarioCreate(company_id=company_id, name="soci", base_year=2026, scenario_type="budget"),
        user_id=user, db=db)
    righe = [{"forecast_year": anno, "revenue_growth_pct": 2} for anno in (2027, 2028, 2029)]
    esito = budget_scenarios.bulk_upsert_assumptions(
        company_id, sc.id, request={"assumptions": righe, "auto_generate": True}, user_id=user, db=db)
    assert esito["forecast_generated"] is True, esito["message"]
    return read_forecast_maps(db, sc.id)


def test_sp01_tutto_da_richiamare_resta_in_sp01b_e_la_gerarchia_regge(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            anni = _genera(db, "soci-b", "0", "15000")
    finally:
        engine.dispose()
    for anno, bs, ce in anni:
        assert bs["sp01_crediti_soci"] == D("15000.00"), anno
        assert bs["sp01a_parte_richiamata"] == D("0"), anno
        assert bs["sp01b_parte_da_richiamare"] == D("15000.00"), anno
        assert check_quadratura(bs, ce).semantic_valid, (anno, check_quadratura(bs, ce).warnings)


def test_sp01_misto_mantiene_le_proporzioni_dell_anno_base(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            anni = _genera(db, "soci-ab", "4000", "6000")
    finally:
        engine.dispose()
    for anno, bs, ce in anni:
        assert bs["sp01a_parte_richiamata"] + bs["sp01b_parte_da_richiamare"] == bs["sp01_crediti_soci"], anno
        assert bs["sp01a_parte_richiamata"] == D("4000.00"), anno
        assert check_quadratura(bs, ce).semantic_valid, (anno, check_quadratura(bs, ce).warnings)
