from decimal import Decimal

import pytest
from fastapi import HTTPException

from backend.app.api.v1 import budget_scenarios
from backend.app.schemas.budget import BudgetScenarioCreate
from database import models
from tests.e2e_kit import memory_sessions, read_forecast_maps, seed_base_year

USER = "preview"


def _saved_scenario(db, company_id):
    sc = budget_scenarios.create_budget_scenario(
        company_id, BudgetScenarioCreate(company_id=company_id, name="p", base_year=2026, scenario_type="budget"),
        user_id=USER, db=db)
    rows = [{"forecast_year": y, "revenue_growth_pct": 5} for y in (2027, 2028)]
    res = budget_scenarios.bulk_upsert_assumptions(
        company_id, sc.id, request={"assumptions": rows, "auto_generate": True}, user_id=USER, db=db)
    assert res["forecast_generated"] is True
    return sc, rows


def _counts(db):
    return tuple(db.query(m).count() for m in (
        models.BudgetAssumptions, models.ForecastYear, models.ForecastBalanceSheet, models.ForecastIncomeStatement))


def test_preview_of_saved_rows_equals_persisted_and_writes_nothing(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            sc, rows = _saved_scenario(db, company_id)
            before = _counts(db)
            saved_pct = [a.revenue_growth_pct for a in db.query(models.BudgetAssumptions).order_by(models.BudgetAssumptions.forecast_year)]
            out = budget_scenarios.preview_forecast_route(
                company_id, sc.id, request={"assumptions": [dict(r, revenue_growth_pct=40) for r in rows]},
                user_id=USER, db=db)
            # I3: l'asserzione di forma corre SUBITO dopo la chiamata, PRIMA di
            # qualunque query — una query fa autoflush e ripulisce db.dirty, e
            # a quel punto una mutazione in memoria e' gia' scritta nel DB
            # (misurato: dirty=1 subito dopo preview, dirty=0 dopo una sola
            # query, col valore gia' nel DB). Mettere l'asserzione dopo una
            # query non discrimina piu' nulla.
            assert not db.new and not db.dirty and not db.deleted
            assert out["error"] is None
            assert [y["year"] for y in out["forecast_years"]] == [2027, 2028]
            assert _counts(db) == before
            assert [a.revenue_growth_pct for a in db.query(models.BudgetAssumptions).order_by(models.BudgetAssumptions.forecast_year)] == saved_pct
            # con le righe salvate, l'anteprima coincide col persistito
            same = budget_scenarios.preview_forecast_route(
                company_id, sc.id, request={"assumptions": rows}, user_id=USER, db=db)
            assert not db.new and not db.dirty and not db.deleted
            for y, (_, bs, ce) in zip(same["forecast_years"], read_forecast_maps(db, sc.id)):
                assert Decimal(str(y["balance_sheet"]["sp09_disponibilita_liquide"])) == bs["sp09_disponibilita_liquide"]
                assert Decimal(str(y["income_statement"]["ce01_ricavi_vendite"])) == ce["ce01_ricavi_vendite"]
            for key in ("ce05_fixed", "ce05_variable", "ce06_fixed", "ce06_variable", "dso_applied", "dio_applied", "dpo_applied"):
                assert key in same["forecast_years"][0]["details"]
    finally:
        engine.dispose()


def test_null_and_fractional_inputs_match_persisted_numbers(monkeypatch):
    """C1 + I2: un `null` esplicito e un valore a tre decimali devono dare, in
    anteprima, esattamente gli stessi numeri del bulk sullo stesso corpo — non
    solo non alzare piu'. `revenue_growth_pct`/`tax_rate` a null riproducono i
    default di colonna (0 e 24, NON 27,9: CLAUDE.md "Tax rate"); `dso_days` e
    `financing_duration_years` a tre decimali quantizzano alla scala della
    colonna esattamente come farebbe il giro DB."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            sc = budget_scenarios.create_budget_scenario(
                company_id, BudgetScenarioCreate(company_id=company_id, name="p", base_year=2026, scenario_type="budget"),
                user_id=USER, db=db)
            rows = [
                {
                    "forecast_year": 2027,
                    "revenue_growth_pct": None,
                    "tax_rate": None,
                    "dso_days": 90.999,
                    "financing_amount": 100000,
                    "financing_duration_years": 3.999,
                    "financing_interest_rate": 5,
                },
                {"forecast_year": 2028, "revenue_growth_pct": 5},
            ]
            res = budget_scenarios.bulk_upsert_assumptions(
                company_id, sc.id, request={"assumptions": rows, "auto_generate": True}, user_id=USER, db=db)
            assert res["forecast_generated"] is True
            saved = {a.forecast_year: a for a in db.query(models.BudgetAssumptions)}
            assert saved[2027].revenue_growth_pct == Decimal("0.000000")
            assert saved[2027].tax_rate == Decimal("24.000000")  # non 27,9: si riproduce, non si corregge
            assert saved[2027].dso_days == Decimal("91.00")
            assert saved[2027].financing_duration_years == Decimal("4.00")

            out = budget_scenarios.preview_forecast_route(
                company_id, sc.id, request={"assumptions": rows}, user_id=USER, db=db)
            assert out["error"] is None

            persisted = read_forecast_maps(db, sc.id)
            for y, (_, bs, ce) in zip(out["forecast_years"], persisted):
                # Confronta solo i campi che il motore dichiara (non i sotto-campi
                # di dettaglio che il calcolo puro non popola, e che sul foglio
                # persistito restano al default 0 di colonna): la parita' che
                # conta e' su cio' che entrambi i percorsi calcolano davvero.
                for field, value in bs.items():
                    if field.startswith("_") or field not in y["balance_sheet"]:
                        continue
                    assert Decimal(str(y["balance_sheet"][field])) == value, f"balance_sheet.{field} anno {y['year']}"
                for field, value in ce.items():
                    if field not in y["income_statement"]:
                        continue
                    assert Decimal(str(y["income_statement"][field])) == value, f"income_statement.{field} anno {y['year']}"
    finally:
        engine.dispose()


def test_infrannuale_scenario_is_rejected_with_400(monkeypatch):
    """I1: il wizard e' budget-only. Un tentativo di anteprima su uno scenario
    infrannuale va rifiutato con un 400 parlante, senza ramificare su
    IntraYearEngine (che darebbe due bilanci diversi della stessa azienda dallo
    stesso corpo — l'invariante "un solo motore di proiezione")."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            sc = models.BudgetScenario(
                company_id=company_id, name="infra", base_year=2025,
                scenario_type="infrannuale", period_months=6,
            )
            db.add(sc)
            db.commit()
            with pytest.raises(HTTPException) as e:
                budget_scenarios.preview_forecast_route(
                    company_id, sc.id, request={"assumptions": [{"forecast_year": 2026}]},
                    user_id=USER, db=db)
            assert e.value.status_code == 400
            assert "infrannuale" in e.value.detail.lower()
    finally:
        engine.dispose()


def test_unfunded_requirement_returns_200_with_partial_years(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            sc, rows = _saved_scenario(db, company_id)
            rows[1]["tangible_investments"] = 5_000_000
            out = budget_scenarios.preview_forecast_route(
                company_id, sc.id, request={"assumptions": rows}, user_id=USER, db=db)
            assert [y["year"] for y in out["forecast_years"]] == [2027]
            assert out["error"]["year"] == 2028
            assert "Unfunded financing requirement" in out["error"]["message"]
    finally:
        engine.dispose()


def test_bad_input_is_400_and_foreign_scenario_is_404(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            sc, rows = _saved_scenario(db, company_id)
            with pytest.raises(HTTPException) as e:
                budget_scenarios.preview_forecast_route(
                    company_id, sc.id, request={"assumptions": [{"forecast_year": 2026}]}, user_id=USER, db=db)
            assert e.value.status_code == 400
            with pytest.raises(HTTPException) as e:
                budget_scenarios.preview_forecast_route(
                    company_id, sc.id, request={"assumptions": rows}, user_id="someone-else", db=db)
            assert e.value.status_code == 404
    finally:
        engine.dispose()


def test_forecast_year_convertible_string_succeeds_on_both_endpoints(monkeypatch):
    """N1: una stringa numerica convertibile ("2027") deve funzionare come
    l'intero, su entrambi gli endpoint. La coercizione gira una volta sola
    dentro validate_assumptions_list, e il valore coerciato e' quello che
    build_assumption_row scrive sulla colonna — mai la stringa grezza, che
    altrimenti sopravvive fino al sorted() dell'anteprima o alla lista degli
    anni del bulk e li fa fallire piu' a valle (con, sul bulk, le righe gia'
    committate: la regressione che questo round corregge)."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            sc = budget_scenarios.create_budget_scenario(
                company_id, BudgetScenarioCreate(company_id=company_id, name="p", base_year=2026, scenario_type="budget"),
                user_id=USER, db=db)
            rows = [{"forecast_year": "2027", "revenue_growth_pct": 5}]

            out = budget_scenarios.preview_forecast_route(
                company_id, sc.id, request={"assumptions": rows}, user_id=USER, db=db)
            assert out["error"] is None
            assert [y["year"] for y in out["forecast_years"]] == [2027]

            res = budget_scenarios.bulk_upsert_assumptions(
                company_id, sc.id, request={"assumptions": rows, "auto_generate": True}, user_id=USER, db=db)
            assert res["forecast_generated"] is True
            saved = db.query(models.BudgetAssumptions).filter(
                models.BudgetAssumptions.scenario_id == sc.id).all()
            assert len(saved) == 1
            assert saved[0].forecast_year == 2027
            assert isinstance(saved[0].forecast_year, int)  # non la stringa grezza
    finally:
        engine.dispose()


def test_forecast_year_not_convertible_is_rejected_and_writes_nothing_on_both_endpoints(monkeypatch):
    """N1: un forecast_year che non si converte a intero e' un errore con
    messaggio, mai un 500 — 400 sull'anteprima, 422 sul bulk (dal lotto 3A,
    Task 7a, perche' la validazione delle righe ora gira prima di scrivere)
    — e non scrive nulla, nemmeno le righe valide dello
    stesso corpo: la validazione gira TUTTA prima di qualunque scrittura, cosi'
    un corpo misto (una riga buona + una con "abc") non lascia il bulk a meta'
    con la tabella scritta e la risposta che dice il contrario."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            sc = budget_scenarios.create_budget_scenario(
                company_id, BudgetScenarioCreate(company_id=company_id, name="p", base_year=2026, scenario_type="budget"),
                user_id=USER, db=db)
            rows = [
                {"forecast_year": 2027, "revenue_growth_pct": 5},
                {"forecast_year": "abc", "revenue_growth_pct": 5},
            ]

            with pytest.raises(HTTPException) as e:
                budget_scenarios.preview_forecast_route(
                    company_id, sc.id, request={"assumptions": rows}, user_id=USER, db=db)
            assert e.value.status_code == 400
            assert db.query(models.BudgetAssumptions).filter(
                models.BudgetAssumptions.scenario_id == sc.id).count() == 0

            with pytest.raises(HTTPException) as e:
                budget_scenarios.bulk_upsert_assumptions(
                    company_id, sc.id, request={"assumptions": rows, "auto_generate": True}, user_id=USER, db=db)
            assert e.value.status_code == 422
            assert e.value.detail["errori"] == [{"forecast_year": None, "campo": "forecast_year",
                                                "messaggio": "forecast_year non valido: 'abc'"}]
            assert db.query(models.BudgetAssumptions).filter(
                models.BudgetAssumptions.scenario_id == sc.id).count() == 0
            assert db.query(models.ForecastYear).filter(
                models.ForecastYear.scenario_id == sc.id).count() == 0
    finally:
        engine.dispose()
