from decimal import Decimal as D

import pytest
from pydantic import ValidationError

from backend.app.api.v1 import budget_scenarios
from backend.app.schemas.budget import BudgetAssumptionsCreate, BudgetScenarioCreate, PregressoInput
from backend.app.services.assumptions_service import build_assumption_row
from calculations.forecast_engine import ForecastEngine, load_forecast_source
from calculations.projection_common import PREGRESSO_KEYS
from database import models
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
    dichiararsi puliti.

    `mode` resta `legacy` su tutti e cinque i saldi, tributario compreso: senza
    piano non c'e' nulla di scadenziato (spec §5.3). Cambia invece `imposte`, che
    dichiara `saldo_acconto` perche' la posizione fiscale e' governata dal kernel
    anche senza piano — e' l'unico saldo il cui comportamento cambia comunque."""
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
                assert details["imposte"]["mode"] == "saldo_acconto"
                assert details["imposte"]["current_tax"] > D("0")
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
    """Il lato breve e' generato + dovuto l'anno dopo, il lato oltre e' TUTTO
    pregresso (la % di crescita oltre viene ignorata). E il GENERATO dei due saldi
    senza driver nasce dalla base SCORPORATA della massa dichiarata: se il piano
    copre l'intero saldo — e `validate_pregresso` impone che lo copra — il generato
    e' zero e la voce scende man mano che il piano la paga. Fornitori invece
    genera da un flusso (acquisti × DPO) e non si scorpora."""
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
            # senza piano: i due saldi senza driver si riportano interi e il lato
            # oltre cresce del 50% — e' il percorso di sempre, la linea di base
            assert (bs0a["sp16f_debiti_previdenza_breve"], bs0a["sp17f_debiti_previdenza_lungo"]) == (D("25000.00"), D("15000.00"))
            assert (bs0a["sp16g_altri_debiti_breve"], bs0a["sp17g_altri_debiti_lungo"]) == (D("15000.00"), D("7500.00"))
            # con piano, numeri calcolati a mano:
            #   fornitori   115.000, piano 80.000 + 20.000 → residuo 35.000 (20.000
            #               dovuti l'anno dopo, 15.000 oltre); il generato resta il
            #               DPO sull'anno base (acquisti 350.000 invariati → 100.000)
            #   previdenz.   35.000, piano 25.000 + 5.000 → residuo 10.000 (5.000 e 5.000),
            #               generato 0 perche' la massa dichiarata e' l'intero saldo
            #   altri        20.000, piano 12.000 + 4.000 → residuo 8.000 (4.000 e 4.000),
            #               generato 0 per la stessa ragione
            for short, long_, y1_short, y1_long, y2_short, y2_long in (
                ("sp16d_debiti_fornitori_breve", "sp17d_debiti_fornitori_lungo",
                 "120000.00", "15000.00", "100000.00", "15000.00"),
                ("sp16f_debiti_previdenza_breve", "sp17f_debiti_previdenza_lungo",
                 "5000.00", "5000.00", "0.00", "5000.00"),
                ("sp16g_altri_debiti_breve", "sp17g_altri_debiti_lungo",
                 "4000.00", "4000.00", "0.00", "4000.00"),
            ):
                assert (bs0b[short], bs0b[long_]) == (D(y1_short), D(y1_long))
                assert (bs1b[short], bs1b[long_]) == (D(y2_short), D(y2_long))
            # e il saldo dei due senza driver SCENDE, invece di restare fermo:
            # 35.000 → 10.000 → 5.000 dopo aver pagato 25.000 e poi 5.000
            assert bs0b["sp16f_debiti_previdenza_breve"] + bs0b["sp17f_debiti_previdenza_lungo"] == D("10000.00")
            assert bs1b["sp16f_debiti_previdenza_breve"] + bs1b["sp17f_debiti_previdenza_lungo"] == D("5000.00")
            assert bs0b["_total_assets"] == bs0b["_total_liabilities"]
            assert bs1b["_total_assets"] == bs1b["_total_liabilities"]
    finally:
        engine.dispose()


def test_a_plan_that_schedules_nothing_neither_creates_nor_destroys_mass(monkeypatch):
    """Il momento in cui il piano parte: niente scadenziato, quindi il generato
    scorporato e' zero e il residuo e' l'intera massa. Il saldo della voce vale
    ancora esattamente il saldo dell'anno base — solo, tutto oltre 12 mesi, perche'
    nessun importo risulta dovuto l'anno dopo (spec §3.3)."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            _split_base_payables(db, company_id)
            rows = [dict(forecast_year=y, sp16f_growth_pct=30, sp17f_growth_pct=30, **MANUAL_TAX)
                    for y in (2027, 2028)]
            rows[0]["pregresso"] = {"debiti_previdenziali": {"opening": 35000, "amounts": []}}
            sc, _ = _run(db, company_id, rows)
            for _, bs, _ in read_forecast_maps(db, sc.id):
                assert bs["sp16f_debiti_previdenza_breve"] == D("0.00")     # generato 35.000 - 35.000
                assert bs["sp17f_debiti_previdenza_lungo"] == D("35000.00")  # residuo intero
            out = budget_scenarios.preview_forecast_route(
                company_id, sc.id, request={"assumptions": rows}, user_id=USER, db=db)
            for year in out["forecast_years"]:
                saldo = year["details"]["pregresso"]["debiti_previdenziali"]
                assert saldo["mode"] == "runoff"
                assert saldo["opening"] == D("35000.00")
                assert saldo["generated"] == D("0")
                assert saldo["closed"] == D("0") and saldo["residual_long"] == D("35000.00")
    finally:
        engine.dispose()


def test_the_scorporo_also_applies_to_previdenza_scaled_on_personnel(monkeypatch):
    """L'aggancio al costo del personale e' pur sempre uno STOCK riportato, solo
    ancorato all'anno base invece che all'anno prima: se quello stock e' dichiarato
    a pregresso, moltiplicarlo per il fattore del personale lo rimetterebbe dentro
    ogni anno. Anche li' il generato parte dalla base scorporata."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            _split_base_payables(db, company_id)
            rows = [dict(forecast_year=y, personnel_growth_pct=20,
                         previdenza_scales_with_personnel=True, **MANUAL_TAX)
                    for y in (2027, 2028)]
            without = _run(db, company_id, [dict(r) for r in rows])[0]
            (_, bs_no_plan, _), _ = read_forecast_maps(db, without.id)
            assert bs_no_plan["sp16f_debiti_previdenza_breve"] == D("30000.00")   # 25.000 × 1,2
            rows[0]["pregresso"] = {"debiti_previdenziali": {"opening": 35000, "amounts": [25000, 5000]}}
            sc, _ = _run(db, company_id, rows)
            (_, bs0, _), (_, bs1, _) = read_forecast_maps(db, sc.id)
            assert (bs0["sp16f_debiti_previdenza_breve"], bs0["sp17f_debiti_previdenza_lungo"]) == (D("5000.00"), D("5000.00"))
            assert (bs1["sp16f_debiti_previdenza_breve"], bs1["sp17f_debiti_previdenza_lungo"]) == (D("0.00"), D("5000.00"))
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


# ── Imposte a saldo + acconto (Task 6) ──


def _tax_rows(years, extra=None):
    return [dict(forecast_year=y, revenue_growth_pct=0, tax_rate=24, **(extra or {})) for y in years]


def test_constant_tax_pays_itself_and_leaves_no_debt(monkeypatch):
    """ce20 base 50.000 con aliquota esplicita 24 su un CE piatto: acconto 100% ->
    debito generato = imposte(N) - imposte(N-1).

    L'acconto e' commisurato all'imposta dell'anno PRECEDENTE, quindi il primo
    anno versa 50.000 (il ce20 del consuntivo) a fronte di 16.800 di imposta
    corrente: l'eccedenza diventa credito tributario e la cassa e' piu' bassa di
    tutto l'acconto. Si misura contro lo stesso piano con `acconto_pct = 0`,
    perche' su questo fixture — molto redditizio e senza investimenti — la cassa
    cresce comunque di ~99.000 l'anno: guardarla in assoluto non direbbe nulla
    sull'imposta pagata."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            sc, _ = _run(db, company_id, _tax_rows((2027, 2028, 2029)))
            (_, bs0, ce0), (_, bs1, ce1), (_, bs2, ce2) = read_forecast_maps(db, sc.id)
            # dal secondo anno in poi l'imposta e' costante: nessun debito generato
            assert bs1["sp16e_debiti_tributari_breve"] == D("0.00") or bs1["sp16e_debiti_tributari_breve"] == bs2["sp16e_debiti_tributari_breve"]
            # 50.000 di acconto contro 16.800 di imposta corrente -> 33.200 a credito
            assert ce0["ce20_imposte"] == D("16800.00")
            assert bs0["sp06e_crediti_tributari_breve"] == D("33200.00")
            # senza acconti la stessa azienda tiene in cassa esattamente i 50.000
            # non versati, e il debito generato si paga l'anno DOPO
            zero_acconto = [dict(r) for r in _tax_rows((2027, 2028, 2029))]
            zero_acconto[0]["pregresso"] = {"debiti_tributari": {
                "opening": 0, "saldo": 0, "rateizzato": 0, "amounts": [], "acconto_pct": 0}}
            sc0, _ = _run(db, company_id, zero_acconto)
            for (_, bs_acc, _), (_, bs_no, _) in zip(read_forecast_maps(db, sc.id),
                                                     read_forecast_maps(db, sc0.id)):
                assert bs_no["sp09_disponibilita_liquide"] - bs_acc["sp09_disponibilita_liquide"] == D("50000.00")
                assert bs_no["sp16e_debiti_tributari_breve"] == D("16800.00")
    finally:
        engine.dispose()


def test_instalments_go_short_then_long(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            # base: sp16e = 0 nel kit -> aggiungerlo: 90.000 di debito tributario, 30.000 a breve + 60.000 a lungo
            fy = db.query(models.FinancialYear).filter_by(company_id=company_id).one()
            fy.balance_sheet.sp16e_debiti_tributari_breve = D("30000"); fy.balance_sheet.sp16_debiti_breve += D("30000")
            fy.balance_sheet.sp17e_debiti_tributari_lungo = D("60000"); fy.balance_sheet.sp17_debiti_lungo += D("60000")
            fy.balance_sheet.sp09_disponibilita_liquide += D("90000"); db.commit()
            rows = _tax_rows((2027, 2028, 2029))
            rows[0]["pregresso"] = {"debiti_tributari": {"opening": 90000, "saldo": 30000, "rateizzato": 60000,
                                                          "amounts": [20000, 20000, 20000], "acconto_pct": 100}}
            sc, _ = _run(db, company_id, rows)
            (_, bs0, _), (_, bs1, _), (_, bs2, _) = read_forecast_maps(db, sc.id)
            # fine anno 1: rata 2 a breve, rata 3 oltre (piu' il debito generato a breve)
            assert bs0["sp17e_debiti_tributari_lungo"] == D("20000.00")
            assert bs0["sp16e_debiti_tributari_breve"] >= D("20000.00")
            assert bs1["sp17e_debiti_tributari_lungo"] == D("0.00")
            assert bs2["sp17e_debiti_tributari_lungo"] == D("0.00")
    finally:
        engine.dispose()


def test_manual_tax_position_ignores_the_plan_and_says_so(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            rows = _tax_rows((2027, 2028), MANUAL_TAX)
            rows[0]["pregresso"] = {"debiti_tributari": {"opening": 0, "saldo": 0, "rateizzato": 0, "amounts": []}}
            sc, _ = _run(db, company_id, rows)
            source = load_forecast_source(db, sc.id)
            orm_rows = db.query(models.BudgetAssumptions).filter_by(scenario_id=sc.id).order_by(models.BudgetAssumptions.forecast_year).all()
            comp = ForecastEngine(db).compute_forecast(source, orm_rows)
            assert comp.years[0].details["imposte"]["mode"] == "manual"
            assert comp.years[0].details["pregresso_ignored"] == ["debiti_tributari"]
    finally:
        engine.dispose()


def test_the_debt_generated_is_last_years_tax_difference(monkeypatch):
    """L'acconto e' commisurato all'imposta dell'anno PRECEDENTE: su un CE che
    cresce, il debito tributario di fine anno e' esattamente l'incremento di
    imposta rispetto all'anno prima. Commisurarlo all'anno in corso lo
    azzererebbe — e su un CE piatto quel difetto sarebbe invisibile."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            rows = [dict(forecast_year=y, revenue_growth_pct=20, tax_rate=24)
                    for y in (2027, 2028, 2029)]
            sc, _ = _run(db, company_id, rows)
            (_, bs0, ce0), (_, bs1, ce1), (_, bs2, ce2) = read_forecast_maps(db, sc.id)
            assert ce1["ce20_imposte"] > ce0["ce20_imposte"] > D("0")
            assert bs1["sp16e_debiti_tributari_breve"] == ce1["ce20_imposte"] - ce0["ce20_imposte"]
            assert bs2["sp16e_debiti_tributari_breve"] == ce2["ce20_imposte"] - ce1["ce20_imposte"]
            assert bs1["sp16e_debiti_tributari_breve"] > D("0")
    finally:
        engine.dispose()


def test_the_opening_tax_credit_absorbs_the_saldo_and_the_rest_survives(monkeypatch):
    """Il credito tributario di apertura compensa il saldo fino a capienza, e
    l'eccedenza resta credito invece di sparire. Senza quella compensazione il
    saldo verrebbe versato per intero e la cassa direbbe il falso."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            # 20.000 di crediti tributari contro 5.000 di debito tributario:
            # il saldo si estingue in compensazione e restano 15.000 di credito.
            fy = db.query(models.FinancialYear).filter_by(company_id=company_id).one()
            bs = fy.balance_sheet
            bs.sp06e_crediti_tributari_breve = D("20000")
            bs.sp06a_crediti_clienti_breve -= D("20000")          # sp06 invariato
            bs.sp16e_debiti_tributari_breve = D("5000")
            bs.sp16d_debiti_fornitori_breve -= D("5000")          # sp16 invariato
            db.commit()
            rows = [dict(forecast_year=y, revenue_growth_pct=0, tax_rate=24)
                    for y in (2027, 2028)]
            sc, _ = _run(db, company_id, rows)
            source = load_forecast_source(db, sc.id)
            orm_rows = (db.query(models.BudgetAssumptions).filter_by(scenario_id=sc.id)
                        .order_by(models.BudgetAssumptions.forecast_year).all())
            imposte = [y.details["imposte"] for y in ForecastEngine(db).compute_forecast(source, orm_rows).years]
            assert imposte[0]["mode"] == "saldo_acconto"
            assert imposte[0]["saldo_paid"] == D("0")             # 5.000 tutti compensati
            assert imposte[0]["opening_credit_left"] == D("15000")
            assert imposte[0]["acconti_paid"] == D("50000")       # 100% del ce20 base
            assert imposte[0]["generated_credit"] == D("33200")
            (_, bs0, _), _ = read_forecast_maps(db, sc.id)
            assert bs0["sp06e_crediti_tributari_breve"] == D("48200.00")   # 33.200 + 15.000
            assert bs0["sp16e_debiti_tributari_breve"] == D("0.00")
            assert bs0["_total_assets"] == bs0["_total_liabilities"]
    finally:
        engine.dispose()


def test_the_leftover_tax_credit_is_spent_on_a_later_saldo(monkeypatch):
    """Il credito di apertura non consumato viaggia di anno in anno e paga il
    SALDO di un anno successivo — il debito generato a fine anno N si versa in
    N+1. Senza quel versamento il credito resterebbe li' per sempre: e' un
    difetto che nessun anno singolo puo' vedere, perche' il saldo non tocca il
    patrimoniale (sp16e nasce dal debito generato, e la cassa e' il plug)."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            bs = db.query(models.FinancialYear).filter_by(company_id=company_id).one().balance_sheet
            bs.sp06e_crediti_tributari_breve = D("20000"); bs.sp06a_crediti_clienti_breve -= D("20000")
            bs.sp16e_debiti_tributari_breve = D("5000"); bs.sp16d_debiti_fornitori_breve -= D("5000")
            db.commit()
            rows = [dict(forecast_year=y, revenue_growth_pct=20, tax_rate=24)
                    for y in (2027, 2028, 2029)]
            sc, _ = _run(db, company_id, rows)
            source = load_forecast_source(db, sc.id)
            orm_rows = (db.query(models.BudgetAssumptions).filter_by(scenario_id=sc.id)
                        .order_by(models.BudgetAssumptions.forecast_year).all())
            imposte = [y.details["imposte"] for y in ForecastEngine(db).compute_forecast(source, orm_rows).years]
            # 2027: 5.000 di saldo compensati, restano 15.000; l'acconto (50.000)
            #       supera l'imposta (45.600) e genera altri 4.400 di credito
            assert (imposte[0]["saldo_paid"], imposte[0]["opening_credit_left"]) == (D("0"), D("15000"))
            # 2028: niente saldo da pagare (2027 non ha generato debito), quindi il
            #       credito resta intero a 19.400 e l'anno chiude con 34.560 di debito
            assert (imposte[1]["saldo_paid"], imposte[1]["opening_credit_left"]) == (D("0"), D("19400"))
            # 2029: il saldo del 2028 (34.560) consuma i 19.400 e se ne versano 15.160
            assert imposte[2]["saldo_paid"] == D("15160")
            assert imposte[2]["opening_credit_left"] == D("0")
            (_, _, _), (_, bs1, _), (_, bs2, _) = read_forecast_maps(db, sc.id)
            assert bs1["sp06e_crediti_tributari_breve"] == D("19400.00")
            assert bs2["sp06e_crediti_tributari_breve"] == D("0.00")
    finally:
        engine.dispose()


def test_the_writeoff_that_no_override_lets_the_ce_record_does_not_leave_the_sp(monkeypatch):
    """L'inesigibile esce dai crediti solo se il costo entra nel CE.

    Con un `ce09d_override` la svalutazione dell'anno e' quella dell'utente, non
    quella del piano: scaricare lo stesso il credito farebbe sparire un attivo
    senza contropartita, e il plug di cassa lo rimpiazzerebbe euro per euro
    (misurato prima della correzione: 5.000 di credito diventavano 5.000 di
    cassa). L'override vince e il credito resta: il piano con inesigibile
    soppresso deve dare, riga per riga, lo stesso bilancio di un piano che
    l'inesigibile non lo aveva scritto affatto."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            def _scenario(writeoff, override_field):
                rows = [dict(forecast_year=y, **MANUAL_TAX) for y in (2027, 2028)]
                rows[0][override_field] = 800
                plan = {"opening": 120000, "amounts": [60000]}
                if writeoff:
                    plan["writeoff"] = writeoff
                rows[0]["pregresso"] = {"crediti_commerciali": plan}
                return _run(db, company_id, rows)[0], rows
            senza, _ = _scenario(None, "ce09d_override")
            con, rows_con = _scenario([5000], "ce09d_override")
            for (_, bs_a, ce_a), (_, bs_b, ce_b) in zip(read_forecast_maps(db, senza.id),
                                                        read_forecast_maps(db, con.id)):
                assert bs_a == bs_b and ce_a == ce_b
            (_, bs0, ce0), _ = read_forecast_maps(db, con.id)
            assert ce0["ce09d_svalutazione_crediti"] == D("800.00")   # l'override, non 5.000
            assert bs0["sp07_crediti_lungo"] == D("60000.00")         # 120.000 - 60.000, niente svalutazione
            assert bs0["_total_assets"] == bs0["_total_liabilities"]
            # e la cosa e' DICHIARATA, non taciuta
            out = budget_scenarios.preview_forecast_route(
                company_id, con.id, request={"assumptions": rows_con}, user_id=USER, db=db)
            y0, y1 = out["forecast_years"]
            assert y0["details"]["pregresso_writeoff_ignored"] == [{
                "saldo": "crediti_commerciali", "field": "ce09d_svalutazione_crediti",
                "requested": D("5000"), "reason": "ce09d_override",
            }]
            assert y1["details"]["pregresso_writeoff_ignored"] == []
            assert y0["details"]["pregresso"]["crediti_commerciali"]["writeoff"] == D("0")
    finally:
        engine.dispose()


def test_an_aggregate_ce09_override_blocks_the_writeoff_too(monkeypatch):
    """Il gemello dell'aggregato: `ce09_override` e' la riga che entra nel
    risultato d'esercizio, quindi con quella forzata la svalutazione del piano
    non arriva al risultato nemmeno passando dal dettaglio."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            rows = [dict(forecast_year=y, **MANUAL_TAX) for y in (2027, 2028)]
            rows[0]["ce09_override"] = 45000
            rows[0]["pregresso"] = {"crediti_commerciali": {"opening": 120000, "amounts": [60000], "writeoff": [5000]}}
            sc, _ = _run(db, company_id, rows)
            (_, bs0, ce0), _ = read_forecast_maps(db, sc.id)
            assert ce0["ce09_ammortamenti"] == D("45000.00")
            assert bs0["sp07_crediti_lungo"] == D("60000.00")   # il credito NON si scarica
            out = budget_scenarios.preview_forecast_route(
                company_id, sc.id, request={"assumptions": rows}, user_id=USER, db=db)
            ignored = out["forecast_years"][0]["details"]["pregresso_writeoff_ignored"]
            assert [i["reason"] for i in ignored] == ["ce09_override"]
            assert ignored[0]["requested"] == D("5000")
    finally:
        engine.dispose()


def test_the_quadratura_residual_never_rewrites_a_field_the_plan_wrote(monkeypatch):
    """`sp16g`/`sp17g` sono i secchi in cui `_normalize_balance_sheet_cents` posa
    il residuo di quadratura di `sp16`/`sp17`, e sono ESATTAMENTE i due campi che
    il piano `altri_debiti` scrive. Un centesimo di residuo li faceva divergere
    dal numero dichiarato nei `details` — cioe' la tabella che l'utente legge dal
    bilancio che l'utente stampa (misurato: `sp16g` persistito 0,01 contro 0
    dichiarato, dal secondo anno in poi). Ora il residuo va sull'ultimo campo
    libero del gruppo, e i due prospetti tornano a dire la stessa cosa."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            _split_base_payables(db, company_id)
            rows = [dict(forecast_year=y, revenue_growth_pct=1.11,
                         variable_materials_growth_pct=1.11, variable_services_growth_pct=1.11,
                         personnel_growth_pct=1.11,
                         financing_amount=(120000 if y == 2027 else 0),
                         financing_duration_years=7, financing_interest_rate=4.44)
                    for y in (2027, 2028, 2029)]
            rows[0]["pregresso"] = {"altri_debiti": {"opening": 20000, "amounts": [12000, 4000]}}
            sc, _ = _run(db, company_id, rows)
            out = budget_scenarios.preview_forecast_route(
                company_id, sc.id, request={"assumptions": rows}, user_id=USER, db=db)
            persisted = read_forecast_maps(db, sc.id)
            for (year, bs, _), preview in zip(persisted, out["forecast_years"]):
                declared = preview["details"]["pregresso"]["altri_debiti"]
                assert bs["sp16g_altri_debiti_breve"] == declared["residual_short"], year
                assert bs["sp17g_altri_debiti_lungo"] == declared["residual_long"], year
                # il residuo non e' sparito: e' andato su un campo libero, e i due
                # gruppi continuano a quadrare col proprio aggregato
                for aggregate, letters in (("sp16_debiti_breve", "abcdefg"), ("sp17_debiti_lungo", "abcdefg")):
                    detail_sum = sum(
                        (v for k, v in bs.items()
                         if k[:4] == aggregate[:4] and len(k.split("_")[0]) == 5
                         and k.split("_")[0][4] in letters),
                        D("0"),
                    )
                    assert bs[aggregate] == detail_sum, (year, aggregate)
            # il caso misurato: nel secondo anno il residuo a breve e' zero, e
            # prima della correzione `sp16g` valeva 0,01
            assert persisted[1][1]["sp16g_altri_debiti_breve"] == D("0.00")
    finally:
        engine.dispose()
