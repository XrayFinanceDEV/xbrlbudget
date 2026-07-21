"""Property-style invariants of the budget forecast engine.

These tests assert accounting identities, not snapshots: they must hold for
ANY input, so a failure is a real engine defect.
"""
from decimal import Decimal

from backend.app.api.v1 import budget_scenarios
from backend.app.schemas.budget import BudgetScenarioCreate
from tests.e2e_kit import memory_sessions, read_forecast_maps, seed_base_year

USER = "invariants"


def _make_scenario(db, company_id, name, years, extra=None):
    scenario = budget_scenarios.create_budget_scenario(
        company_id,
        BudgetScenarioCreate(
            company_id=company_id, name=name, base_year=2026, scenario_type="budget"
        ),
        user_id=USER,
        db=db,
    )
    assumptions = []
    for year in years:
        row = {"forecast_year": year}
        row.update(extra or {})
        assumptions.append(row)
    result = budget_scenarios.bulk_upsert_assumptions(
        company_id,
        scenario.id,
        request={"assumptions": assumptions, "auto_generate": True},
        user_id=USER,
        db=db,
    )
    assert result["forecast_generated"] is True, result["message"]
    return scenario


def test_equity_and_tfr_roll_forward(monkeypatch):
    """CN_t = CN_{t-1} + utile_{t-1}; TFR_t = TFR_{t-1} + accantonamento_t."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            scenario = _make_scenario(
                db, company_id, "rollforward", [2027, 2028],
                extra={"revenue_growth_pct": 5, "tax_rate": 24},
            )
            rows = read_forecast_maps(db, scenario.id)
            (y1, bs1, ce1), (y2, bs2, ce2) = rows
            # anno 1: riserve = 60.000 base + 20.000 utile base
            assert bs1["sp12_riserve"] == Decimal("80000.00")
            assert bs1["sp11_capitale"] == Decimal("100000.00")
            assert bs1["sp15_tfr"] == Decimal("30000") + ce1["ce08a_tfr_accrual"]
            # anno 2: identita' ricorsiva sui valori davvero salvati
            assert bs2["sp12_riserve"] == bs1["sp12_riserve"] + bs1["sp13_utile_perdita"]
            assert bs2["sp15_tfr"] == bs1["sp15_tfr"] + ce2["ce08a_tfr_accrual"]
    finally:
        engine.dispose()


def test_zero_growth_is_a_fixed_point_for_operating_costs(monkeypatch):
    """Crescita 0%, zero investimenti: ricavi e costi operativi restano quelli base.

    (Gli ammortamenti possono scendere: il piano cespiti si esaurisce. Non sono inclusi.)
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            scenario = _make_scenario(
                db, company_id, "fixed-point", [2027],
                extra={
                    "revenue_growth_pct": 0,
                    "personnel_growth_pct": 0,
                    "tax_rate": 24,
                },
            )
            (_, bs1, ce1), = read_forecast_maps(db, scenario.id)
            assert ce1["ce01_ricavi_vendite"] == Decimal("600000.00")
            assert ce1["ce05_materie_prime"] == Decimal("200000.00")
            assert ce1["ce06_servizi"] == Decimal("150000.00")
            assert ce1["ce07_godimento_beni"] == Decimal("10000.00")
            assert ce1["ce08_costi_personale"] == Decimal("120000.00")
            assert bs1["_total_assets"] == bs1["_total_liabilities"]
    finally:
        engine.dispose()


def test_forecast_generation_is_deterministic(monkeypatch):
    """Due generazioni con le stesse ipotesi producono esattamente le stesse righe."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            extra = {"revenue_growth_pct": 7.35, "tax_rate": 24,
                     "tangible_investments": 12345.67}
            scenario = _make_scenario(db, company_id, "det", [2027, 2028, 2029], extra)
            first = read_forecast_maps(db, scenario.id)
            budget_scenarios.generate_forecasts(
                company_id, scenario.id, clear_overrides=False, user_id=USER, db=db
            )
            second = read_forecast_maps(db, scenario.id)
            assert first == second
    finally:
        engine.dispose()


def test_cash_plug_never_goes_negative(monkeypatch):
    """La cassa e' il plug: se il piano copre il fabbisogno, non deve mai scendere sotto zero.

    Corretta rispetto alla bozza originale del task: la bozza si aspettava che un
    fabbisogno di cassa scoperto venisse silenziosamente trasformato in debito a
    breve (sp16). Il motore attuale (calculations/forecast_engine.py, sezione
    "CASH PLUG") rifiuta DELIBERATAMENTE questo comportamento — vedi il commento
    a corredo: "Creating short-term bank debt here used to hide a missing
    scenario choice" — e solleva "Unfunded financing requirement" quando la
    cassa implicita sarebbe negativa, richiedendo un finanziamento esplicito
    invece di inventare un debito bancario. Questo e' il comportamento corretto
    (coerente con test_forecast_gate_rejects_*/unfunded_financing_requirement in
    tests/test_intra_year_semantics.py), quindi lo scenario di stress qui sotto
    include un `financing_amount` esplicito sufficiente a coprire il fabbisogno;
    l'invariante contabile testata resta "la cassa non scende mai sotto zero e lo
    stato patrimoniale quadra sempre al centesimo", non piu' "il motore genera
    debito a copertura automaticamente".
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            scenario = _make_scenario(
                db, company_id, "cash-squeeze", [2027, 2028],
                extra={
                    "revenue_growth_pct": 60,
                    "dso_days": 180,
                    "dpo_days": 5,
                    "tangible_investments": 250000,
                    "tax_rate": 24,
                    "financing_amount": 400000,
                    "financing_duration_years": 10,
                    "financing_interest_rate": 5,
                },
            )
            for _, bs, _ in read_forecast_maps(db, scenario.id):
                assert bs["sp09_disponibilita_liquide"] >= 0
                assert bs["_total_assets"] == bs["_total_liabilities"]
    finally:
        engine.dispose()


def test_taxes_follow_the_explicit_rate(monkeypatch):
    """Con tax_rate esplicito e PBT>0, ce20 = 24% del PBT (PBT = utile + imposte)."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            scenario = _make_scenario(
                db, company_id, "tax", [2027],
                extra={"revenue_growth_pct": 5, "tax_rate": 24},
            )
            (_, bs1, ce1), = read_forecast_maps(db, scenario.id)
            pbt = bs1["sp13_utile_perdita"] + ce1["ce20_imposte"]
            assert pbt > 0
            assert ce1["ce20_imposte"] == (pbt * Decimal("0.24")).quantize(Decimal("0.01"))
    finally:
        engine.dispose()
