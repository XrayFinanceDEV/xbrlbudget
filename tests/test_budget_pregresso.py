from decimal import Decimal as D

import pytest
from pydantic import ValidationError

from backend.app.api.v1 import budget_scenarios
from backend.app.schemas.budget import BudgetAssumptionsCreate, BudgetScenarioCreate, PregressoInput
from backend.app.services.assumptions_service import build_assumption_row
from calculations.projection_common import PREGRESSO_KEYS
from tests.e2e_kit import memory_sessions, read_forecast_maps, seed_base_year


def test_schema_accepts_a_plan_and_rejects_negatives():
    p = PregressoInput(crediti_commerciali={"opening": 1000, "amounts": [800, 200], "writeoff": [0, 0]},
                       debiti_tributari={"opening": 96, "saldo": 61, "rateizzato": 35, "amounts": [12, 12, 11]})
    assert p.debiti_tributari.acconto_pct == D("100")
    with pytest.raises(ValidationError):
        PregressoInput(debiti_fornitori={"opening": -1, "amounts": []})


def test_build_assumption_row_carries_pregresso_as_json():
    row = build_assumption_row(1, {"forecast_year": 2027, "pregresso": {"altri_debiti": {"opening": D("10"), "amounts": [D("10")]}}})
    assert row.pregresso == {"altri_debiti": {"opening": 10.0, "amounts": [10.0]}}
    assert build_assumption_row(1, {"forecast_year": 2027}).pregresso is None


# ── Motore: i quattro saldi con piano, e la validazione (Task 5) ──

USER = "pregresso"
# base (e2e_kit): sp06 = sp06a = 120.000; sp16 = sp16d = 140.000; ricavi 600.000; ce20 50.000

MANUAL_TAX = {"sp16e_growth_pct": 0, "sp06e_growth_pct": 0}   # via manuale: le imposte non cambiano


def _run(db, company_id, rows, *, expect_ok=True):
    sc = budget_scenarios.create_budget_scenario(
        company_id, BudgetScenarioCreate(company_id=company_id, name="p", base_year=2026, scenario_type="budget"),
        user_id=USER, db=db)
    res = budget_scenarios.bulk_upsert_assumptions(
        company_id, sc.id, request={"assumptions": rows, "auto_generate": True}, user_id=USER, db=db)
    if expect_ok:
        assert res["forecast_generated"] is True, res["message"]
    return sc, res


def test_no_plan_is_a_fixed_point_for_the_four_balances(monkeypatch):
    """Senza piano (assente o esplicitamente `null`) il motore deve dare gli
    STESSI numeri di prima del lotto, al centesimo: e' la proprieta' che questo
    task puo' rompere senza che nulla protesti."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            rows = [dict(forecast_year=y, revenue_growth_pct=5, **MANUAL_TAX) for y in (2027, 2028, 2029)]
            sc_a, _ = _run(db, company_id, rows)
            rows_b = [dict(r) for r in rows]
            rows_b[0]["pregresso"] = None
            sc_b, _ = _run(db, company_id, rows_b)
            for (_, bs_a, ce_a), (_, bs_b, ce_b) in zip(read_forecast_maps(db, sc_a.id), read_forecast_maps(db, sc_b.id)):
                assert bs_a == bs_b and ce_a == ce_b
    finally:
        engine.dispose()


def test_details_declare_the_three_keys_without_any_plan(monkeypatch):
    """Il tipo `ForecastYearDetails` promette `pregresso`, `imposte` e
    `pregresso_ignored` su OGNI anno: senza piano devono esserci lo stesso, a
    zero. Una chiave assente vale zero a valle, quindi tacere equivarrebbe a
    dichiararsi puliti."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            rows = [dict(forecast_year=y, revenue_growth_pct=5) for y in (2027, 2028)]
            sc, _ = _run(db, company_id, rows)
            out = budget_scenarios.preview_forecast_route(
                company_id, sc.id, request={"assumptions": rows}, user_id=USER, db=db)
            assert out["error"] is None
            assert len(out["forecast_years"]) == 2
            for year in out["forecast_years"]:
                details = year["details"]
                assert set(PREGRESSO_KEYS) == set(details["pregresso"])
                for key in PREGRESSO_KEYS:
                    saldo = details["pregresso"][key]
                    assert saldo["mode"] == "legacy"
                    assert set(saldo) == {"opening", "closed", "writeoff", "residual_short",
                                          "residual_long", "generated", "mode"}
                    assert saldo["closed"] == D("0") and saldo["writeoff"] == D("0")
                    assert saldo["residual_short"] == D("0") and saldo["residual_long"] == D("0")
                assert details["pregresso"]["crediti_commerciali"]["opening"] == D("120000.00")
                assert details["pregresso"]["debiti_fornitori"]["opening"] == D("140000.00")
                assert details["pregresso_ignored"] == []
                assert details["imposte"]["mode"] == "manual"
                assert set(details["imposte"]) == {"current_tax", "saldo_paid", "acconti_paid",
                                                   "rate_paid", "generated_debt", "generated_credit",
                                                   "opening_credit_left", "mode"}
    finally:
        engine.dispose()


def test_receivables_eighty_twenty_keeps_twenty_percent_short_and_lowers_cash(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            base = [dict(forecast_year=y, revenue_growth_pct=0, **MANUAL_TAX) for y in (2027, 2028)]
            sc0, _ = _run(db, company_id, base)
            planned = [dict(r) for r in base]
            planned[0]["pregresso"] = {"crediti_commerciali": {"opening": 120000, "amounts": [96000, 24000]}}
            sc1, _ = _run(db, company_id, planned)
            (y0a, bs0a, _), (y1a, bs1a, _) = read_forecast_maps(db, sc0.id)
            (y0b, bs0b, _), (y1b, bs1b, _) = read_forecast_maps(db, sc1.id)
            assert bs0b["sp06_crediti_breve"] == bs0a["sp06_crediti_breve"] + D("24000.00")
            assert bs0b["sp07_crediti_lungo"] == bs0a["sp07_crediti_lungo"]
            assert bs0b["sp09_disponibilita_liquide"] == bs0a["sp09_disponibilita_liquide"] - D("24000.00")
            assert bs1b["sp06_crediti_breve"] == bs1a["sp06_crediti_breve"]
    finally:
        engine.dispose()


def test_short_plan_pushes_the_rest_long_and_writeoff_hits_ce09d(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            rows = [dict(forecast_year=y, **MANUAL_TAX) for y in (2027, 2028)]
            rows[0]["pregresso"] = {"crediti_commerciali": {"opening": 120000, "amounts": [60000], "writeoff": [5000]}}
            sc, _ = _run(db, company_id, rows)
            (_, bs0, ce0), (_, bs1, ce1) = read_forecast_maps(db, sc.id)
            assert ce0["ce09d_svalutazione_crediti"] == D("5000.00") and ce1["ce09d_svalutazione_crediti"] == D("0.00")
            assert bs0["sp07_crediti_lungo"] == D("55000.00")          # residuo, niente dovuto l'anno dopo
            assert bs0["_total_assets"] == bs0["_total_liabilities"]
    finally:
        engine.dispose()


def _split_base_payables(db, company_id):
    """Riparte i debiti dell'anno base su fornitori, previdenziali e altri debiti.

    Il fixture condiviso tiene tutto il passivo a breve su `sp16d` e tutto quello
    oltre su `sp17a`: senza questo riparto i piani su previdenziali e altri debiti
    avrebbero massa zero, e il lato oltre non avrebbe una percentuale di crescita
    da ignorare. Gli aggregati `sp16` e `sp17` non cambiano, quindi il gate
    aggregato/dettagli dell'anno base resta soddisfatto."""
    from database.models import BalanceSheet, FinancialYear
    fy = db.query(FinancialYear).filter(FinancialYear.company_id == company_id).one()
    bs = db.query(BalanceSheet).filter(BalanceSheet.financial_year_id == fy.id).one()
    bs.sp16d_debiti_fornitori_breve = D("100000.00")     # sp16 = 140.000
    bs.sp16f_debiti_previdenza_breve = D("25000.00")
    bs.sp16g_altri_debiti_breve = D("15000.00")
    bs.sp17a_debiti_banche_lungo = D("20000.00")         # sp17 = 50.000
    bs.sp17d_debiti_fornitori_lungo = D("15000.00")
    bs.sp17f_debiti_previdenza_lungo = D("10000.00")
    bs.sp17g_altri_debiti_lungo = D("5000.00")
    db.commit()


def test_payables_previdenza_and_altri_debiti_follow_the_same_rule(monkeypatch):
    """Gli altri tre saldi: il lato breve e' generato + dovuto l'anno dopo, il
    lato oltre e' TUTTO pregresso — e la sua percentuale di crescita (+50% qui)
    non si applica piu'. La massa di apertura somma i due lati dell'anno base."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            _split_base_payables(db, company_id)
            base = [dict(forecast_year=y, sp17d_growth_pct=50, sp17f_growth_pct=50,
                         sp17g_growth_pct=50, **MANUAL_TAX) for y in (2027, 2028)]
            sc0, _ = _run(db, company_id, base)
            planned = [dict(r) for r in base]
            planned[0]["pregresso"] = {
                "debiti_fornitori": {"opening": 115000, "amounts": [80000, 20000]},
                "debiti_previdenziali": {"opening": 35000, "amounts": [25000, 5000]},
                "altri_debiti": {"opening": 20000, "amounts": [12000, 4000]},
            }
            sc1, _ = _run(db, company_id, planned)
            (_, bs0a, _), (_, bs1a, _) = read_forecast_maps(db, sc0.id)
            (_, bs0b, _), (_, bs1b, _) = read_forecast_maps(db, sc1.id)
            # L'ultimo campo dice se il GENERATO di quel saldo si riporta dall'anno
            # prima (`prev × (1+%)`, spec §3.1) invece di rinascere da una
            # rotazione: in quel caso l'anno 2 riparte da un anno 1 che gia'
            # conteneva il residuo a breve, e il suo lato breve resta piu' alto
            # della linea di base di quell'importo. E' la "formula di oggi"
            # applicata all'anno di piano, non un doppio conteggio del piano:
            # il residuo dell'anno 2 vale zero e non viene aggiunto una seconda volta.
            for short, long_, due_next, residual_long, carried in (
                ("sp16d_debiti_fornitori_breve", "sp17d_debiti_fornitori_lungo", "20000.00", "15000.00", False),
                ("sp16f_debiti_previdenza_breve", "sp17f_debiti_previdenza_lungo", "5000.00", "5000.00", True),
                ("sp16g_altri_debiti_breve", "sp17g_altri_debiti_lungo", "4000.00", "4000.00", True),
            ):
                # anno 1: generato + quanto e' dovuto l'anno dopo a breve, il resto oltre
                assert bs0b[short] == bs0a[short] + D(due_next)
                assert bs0b[long_] == D(residual_long)
                assert bs0a[long_] != D(residual_long)      # senza piano cresceva del 50%
                # anno 2: il residuo non scadenziato e' tutto oltre (non c'e' un anno dopo)
                assert bs1b[short] == bs1a[short] + (D(due_next) if carried else D("0"))
                assert bs1b[long_] == D(residual_long)
            assert bs0b["_total_assets"] == bs0b["_total_liabilities"]
            assert bs1b["_total_assets"] == bs1b["_total_liabilities"]
    finally:
        engine.dispose()


def test_validation_errors_are_honest(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            rows = [dict(forecast_year=y, **MANUAL_TAX) for y in (2027, 2028)]
            rows[1]["pregresso"] = {"altri_debiti": {"opening": 0, "amounts": []}}
            _, res = _run(db, company_id, rows, expect_ok=False)
            assert res["forecast_generated"] is False and "primo anno" in res["message"]
            rows = [dict(forecast_year=y, **MANUAL_TAX) for y in (2027, 2028)]
            rows[0]["pregresso"] = {"debiti_fornitori": {"opening": 100, "amounts": [100]}}
            _, res = _run(db, company_id, rows, expect_ok=False)
            assert "apertura" in res["message"] and "140000" in res["message"]
            rows[0]["pregresso"] = {"debiti_fornitori": {"opening": 140000, "amounts": [100000, 100000]}}
            _, res = _run(db, company_id, rows, expect_ok=False)
            assert "supera" in res["message"]
    finally:
        engine.dispose()


def test_writeoff_survives_the_ce09_rounding_residual(monkeypatch):
    """`ce09d` e' l'ULTIMO dettaglio del gruppo `ce09`: e' anche il campo in cui
    l'inesigibile viene scritto. Senza dichiararlo forzato, il residuo di
    arrotondamento dell'aggregato gli finisce sopra e l'importo scadenziato
    risulta di un centesimo diverso da quello chiesto — senza alcun errore.

    Gli investimenti da 0,02 con ammortamento al 20% producono due quote da
    0,004: i dettagli arrotondano in giu' (0,00) e l'aggregato in su (0,01),
    cioe' esattamente un centesimo di residuo da posare."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            rows = [dict(forecast_year=y, intangible_investments=0.02, tangible_investments=0.02,
                         depreciation_rate=20, depreciation_rate_intangible=20, **MANUAL_TAX)
                    for y in (2027, 2028)]
            rows[0]["pregresso"] = {"crediti_commerciali": {"opening": 120000, "amounts": [60000], "writeoff": [5000]}}
            sc, _ = _run(db, company_id, rows)
            (_, _, ce0), _ = read_forecast_maps(db, sc.id)
            assert ce0["ce09d_svalutazione_crediti"] == D("5000.00")
            # il residuo esiste davvero e sta sull'ultimo dettaglio LIBERO
            assert ce0["ce09c_svalutazioni"] == D("0.01")
            assert ce0["ce09_ammortamenti"] == (
                ce0["ce09a_ammort_immateriali"] + ce0["ce09b_ammort_materiali"]
                + ce0["ce09c_svalutazioni"] + ce0["ce09d_svalutazione_crediti"]
            )
    finally:
        engine.dispose()


def test_receivables_plan_leaves_the_deferred_tax_quota_of_sp07_alone(monkeypatch):
    """Il lato oltre dei crediti e' pregresso solo per la parte COMMERCIALE:
    imposte anticipate e crediti tributari oltre l'anno dipendono dalla posizione
    fiscale, non dalla rotazione, e restano quelli del percorso di sempre."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            differences = [{"kind": "deductible", "maturity": "long",
                            "opening_amount": 0, "additions": 40000, "reversals": 0,
                            "tax_rate": 25}]
            rows = [dict(forecast_year=y, tax_temporary_differences=differences, **MANUAL_TAX)
                    for y in (2027, 2028)]
            rows[0]["pregresso"] = {"crediti_commerciali": {"opening": 120000, "amounts": [60000]}}
            sc, _ = _run(db, company_id, rows)
            (_, bs0, _), _ = read_forecast_maps(db, sc.id)
            assert bs0["sp07f_imposte_anticipate_lungo"] == D("10000.00")   # 40.000 × 25%
            assert bs0["sp07a_crediti_clienti_lungo"] == D("60000.00")      # residuo commerciale
            assert bs0["sp07_crediti_lungo"] == D("70000.00")
            assert bs0["_total_assets"] == bs0["_total_liabilities"]
    finally:
        engine.dispose()
