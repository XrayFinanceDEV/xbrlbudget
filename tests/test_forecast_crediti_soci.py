"""Crediti verso soci nel previsionale (SGH, budget_1340): `sp01` segue la sua crescita e il dettaglio
A.1/A.2 con la proporzione dell'anno base. Senza il dettaglio, `check_quadratura` legge l'aggregato
positivo con le due righe a zero come gerarchia incoerente e il Business plan blocca ogni anno di
piano (`forecast_unbalanced`), anche se attivo e passivo tornano."""
from decimal import Decimal as D

from backend.app.services import assumptions_service, forecast_preview_service  # noqa: F401 (import order puts backend/ on sys.path)
from database.models import BalanceSheet, BudgetScenario, FinancialYear
from importers.iv_cee_hierarchy import check_quadratura
from tests.e2e_kit import memory_sessions, seed_base_year


def _forecast(user, *, parte_richiamata):
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=user)
            fy = db.query(FinancialYear).filter_by(company_id=company_id).one()
            bs = db.query(BalanceSheet).filter_by(financial_year_id=fy.id).one()
            # 15.000 di crediti verso soci, coperti da altrettante riserve: il foglio resta in pari
            bs.sp01_crediti_soci = D("15000.00")
            bs.sp01a_parte_richiamata = parte_richiamata
            bs.sp01b_parte_da_richiamare = D("15000.00") - parte_richiamata
            bs.sp12_riserve = bs.sp12_riserve + D("15000.00")
            bs.sp12e_altre_riserve = bs.sp12e_altre_riserve + D("15000.00")
            sc = BudgetScenario(company_id=company_id, name=user, base_year=2026, scenario_type="budget")
            db.add(sc); db.commit()
            return forecast_preview_service.preview_forecast(
                db, sc.id, [{"forecast_year": 2027, "tax_rate": 27.9}, {"forecast_year": 2028, "tax_rate": 27.9}])
    finally:
        engine.dispose()


def test_crediti_verso_soci_portano_il_dettaglio_e_la_gerarchia_regge():
    out = _forecast("soci-b", parte_richiamata=D("0.00"))
    assert out.get("error") is None
    for y in out["forecast_years"]:
        bs = y["balance_sheet"]
        assert D(str(bs["sp01_crediti_soci"])) == D("15000.00")
        assert D(str(bs["sp01a_parte_richiamata"])) + D(str(bs["sp01b_parte_da_richiamare"])) == D("15000.00")
        q = check_quadratura({k: D(str(v)) for k, v in bs.items()},
                             {k: D(str(v)) for k, v in y["income_statement"].items()})
        assert q.hierarchy_consistent and q.semantic_valid, q.warnings


def test_la_parte_richiamata_dell_anno_base_si_riporta_in_proporzione():
    out = _forecast("soci-ab", parte_richiamata=D("5000.00"))
    bs = out["forecast_years"][0]["balance_sheet"]
    assert D(str(bs["sp01a_parte_richiamata"])) == D("5000.00")
    assert D(str(bs["sp01b_parte_da_richiamare"])) == D("10000.00")
