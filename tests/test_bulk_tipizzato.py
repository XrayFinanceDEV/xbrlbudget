"""Il bulk delle ipotesi rifiuta l'input invalido prima di scrivere, con un 422 italiano per campo (lotto 3A, Task 7a)."""
import pytest
from fastapi import HTTPException

from backend.app.api.v1 import budget_scenarios
from backend.app.schemas.budget import BudgetScenarioCreate
from backend.app.services import assumptions_service
from database import models
from tests.e2e_kit import memory_sessions, seed_base_year

USER = "bulk-tipizzato"
VALIDE = [{"forecast_year": 2027, "revenue_growth_pct": 5}, {"forecast_year": 2028, "revenue_growth_pct": 5}]


def _scenario_salvato(db):
    company_id, _ = seed_base_year(db, user_id=USER)
    sc = budget_scenarios.create_budget_scenario(
        company_id, BudgetScenarioCreate(company_id=company_id, name="bulk", base_year=2026, scenario_type="budget"),
        user_id=USER, db=db)
    esito = budget_scenarios.bulk_upsert_assumptions(
        company_id, sc.id, request={"assumptions": [dict(r) for r in VALIDE], "auto_generate": True}, user_id=USER, db=db)
    assert esito["forecast_generated"] is True, esito["message"]
    return company_id, sc.id


def _stato(db, sid):
    db.expire_all()
    righe = (db.query(models.BudgetAssumptions).filter(models.BudgetAssumptions.scenario_id == sid)
             .order_by(models.BudgetAssumptions.forecast_year).all())
    anni = db.query(models.ForecastYear).filter(models.ForecastYear.scenario_id == sid).count()
    return [(r.forecast_year, r.revenue_growth_pct, r.overdraft_limit, r.tax_advances_paid) for r in righe], anni


def _rifiuto(db, company_id, sid, righe):
    with pytest.raises(HTTPException) as e:
        budget_scenarios.bulk_upsert_assumptions(
            company_id, sid, request={"assumptions": righe, "auto_generate": True}, user_id=USER, db=db)
    assert e.value.status_code == 422
    return e.value.detail


CASI = {
    "tetto di scoperto negativo": ({"overdraft_allowed": True, "overdraft_limit": -100}, "overdraft_limit",
                                   "deve essere maggiore o uguale a 0 (ricevuto: -100)"),
    "acconti negativi": ({"tax_advances_paid": -5000}, "tax_advances_paid",
                         "deve essere maggiore o uguale a 0 (ricevuto: -5000)"),
    "driver sconosciuto": ({"sp_indexing": {"sp16g": "magia"}}, "sp_indexing.sp16g",
                           "valore non ammesso: sono ammessi 'ricavi', 'acquisti' o 'personale' (ricevuto: 'magia')"),
    "tasso al 500%": ({"financing_loans": [{"amount": 50000, "duration_years": 3, "interest_rate": 500}]},
                      "financing_loans.0.interest_rate", "deve essere minore o uguale a 100 (ricevuto: 500)"),
    "campo sconosciuto": ({"campo_a_caso_che_non_esiste": 42}, "campo_a_caso_che_non_esiste",
                          "campo sconosciuto, non ammesso (ricevuto: 42)"),
}


@pytest.mark.parametrize("nome", list(CASI))
def test_un_input_che_lo_schema_rifiuta_risponde_422_e_non_scrive_nulla(nome, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    extra, campo, messaggio = CASI[nome]
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, sid = _scenario_salvato(db)
            prima = _stato(db, sid)
            righe = [dict(VALIDE[0], revenue_growth_pct=9, **extra), dict(VALIDE[1], revenue_growth_pct=9)]
            detail = _rifiuto(db, company_id, sid, righe)
            assert detail["errori"] == [{"forecast_year": 2027, "campo": campo, "messaggio": messaggio}]
            assert _stato(db, sid) == prima
    finally:
        engine.dispose()


def test_anni_non_consecutivi_rispondono_422_e_non_scrivono_nulla(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, sid = _scenario_salvato(db)
            prima = _stato(db, sid)
            righe = [{"forecast_year": 2027, "revenue_growth_pct": 9}, {"forecast_year": 2029, "revenue_growth_pct": 9}]
            assert _rifiuto(db, company_id, sid, righe)["errori"] == [{
                "forecast_year": 2029, "campo": "forecast_year",
                "messaggio": "anni non consecutivi: dopo il 2027 viene il 2029, manca il 2028"}]
            assert _stato(db, sid) == prima
    finally:
        engine.dispose()


def test_il_servizio_alza_l_errore_con_l_elenco(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    classe = getattr(assumptions_service, "AssumptionsValidationError", None)
    assert classe is not None, "assumptions_service.AssumptionsValidationError non esiste"
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            _company_id, sid = _scenario_salvato(db)
            with pytest.raises(classe) as e:
                assumptions_service.bulk_upsert_assumptions(db, sid, [dict(VALIDE[0], tax_advances_paid=-1), VALIDE[1]])
            assert isinstance(e.value, ValueError)
            assert e.value.errori[0]["campo"] == "tax_advances_paid"
    finally:
        engine.dispose()


def test_i_null_del_client_non_sono_errori_e_un_primo_anno_dopo_base_piu_uno_resta_accettato(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, sid = _scenario_salvato(db)
            con_null = [
                {"forecast_year": 2027, "revenue_growth_pct": 5, "financing_amount": None, "dso_days": None,
                 "tax_advances_paid": None, "cash_sweep_min_cash": None, "overdraft_limit": None,
                 "sp_overrides": {"sp10_ratei_risconti_attivi": None},
                 "financing_loans": [{"name": None, "amount": 50000, "opening_residual": 0, "duration_years": 5,
                                      "interest_rate": 3, "grace_years": None, "balloon_pct": None}],
                 "sp_indexing": {"sp16g": None}},
                {"forecast_year": 2028, "revenue_growth_pct": 5},
            ]
            esito = budget_scenarios.bulk_upsert_assumptions(
                company_id, sid, request={"assumptions": con_null, "auto_generate": True}, user_id=USER, db=db)
            assert esito["forecast_generated"] is True, esito["message"]
            dopo_la_base = [{"forecast_year": 2028, "revenue_growth_pct": 5}, {"forecast_year": 2029, "revenue_growth_pct": 5}]
            esito = budget_scenarios.bulk_upsert_assumptions(
                company_id, sid, request={"assumptions": dopo_la_base, "auto_generate": True}, user_id=USER, db=db)
            assert esito["success"] is True
            assert [a for a, *_ in _stato(db, sid)[0]] == [2028, 2029]
    finally:
        engine.dispose()
