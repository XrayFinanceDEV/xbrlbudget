"""Le voci minori dello SP agganciate a un driver (Task 15).

Oggi una voce minore lasciata in pace resta FERMA per tutto il piano: `_sp_growth`
restituisce zero quando la percentuale non e' impostata, e il saldo si riporta
identico. Questo lotto permette di agganciarla a un driver — «aumenta il volume,
aumenta tutto» — generalizzando la forma gia' cablata sui debiti previdenziali
(`base × costo del personale previsto / costo del personale base`): un fattore
indicizzato che moltiplica lo stock dell'ANNO BASE, mai una composizione sul
saldo dell'anno prima.

La proprieta' che questi test difendono per prima e' la PARITA': senza
`sp_indexing` ogni numero resta identico al centesimo.
"""
from decimal import ROUND_HALF_UP, Decimal as D

import pytest

from backend.app.api.v1 import budget_scenarios
from backend.app.schemas.budget import BudgetAssumptionsCreate, BudgetScenarioCreate
from backend.app.services.assumptions_service import build_assumption_row
from database.models import BalanceSheet, FinancialYear
from tests.e2e_kit import memory_sessions, read_forecast_maps, seed_base_year

USER = "indicizzazione"
# base (e2e_kit): ricavi 600.000 · ce05+ce06 350.000 · ce08 120.000 · ce20 50.000
MANUAL_TAX = {"sp16e_growth_pct": 0, "sp06e_growth_pct": 0}


def _run(db, company_id, rows, *, user=USER, expect_ok=True):
    sc = budget_scenarios.create_budget_scenario(
        company_id, BudgetScenarioCreate(company_id=company_id, name="i", base_year=2026, scenario_type="budget"),
        user_id=user, db=db)
    res = budget_scenarios.bulk_upsert_assumptions(
        company_id, sc.id, request={"assumptions": rows, "auto_generate": True}, user_id=user, db=db)
    if expect_ok:
        assert res["forecast_generated"] is True, res["message"]
    return sc, res


def _split_debts(db, company_id):
    """Sposta massa dagli aggregati ai sotto-conti che questo lotto indicizza.

    L'anno base del kit tiene TUTTO il passivo su `sp16d`/`sp17a`: con `sp16g`,
    `sp16f`, `sp17d` e `sp17g` a zero un fattore moltiplicherebbe zero e ogni
    asserzione passerebbe anche col ramo rotto. Le somme restano quelle del kit
    (sp16 = 140.000, sp17 = 50.000), quindi il bilancio pareggia come prima.
    """
    fy = db.query(FinancialYear).filter(FinancialYear.company_id == company_id).one()
    bs = db.query(BalanceSheet).filter(BalanceSheet.financial_year_id == fy.id).one()
    bs.sp16d_debiti_fornitori_breve = D("90000.00")
    bs.sp16f_debiti_previdenza_breve = D("15000.00")
    bs.sp16g_altri_debiti_breve = D("35000.00")
    bs.sp17a_debiti_banche_lungo = D("20000.00")
    bs.sp17d_debiti_fornitori_lungo = D("10000.00")
    bs.sp17g_altri_debiti_lungo = D("20000.00")
    db.commit()


def _preview(db, company_id, sc_id, rows, *, user=USER):
    return budget_scenarios.preview_forecast_route(
        company_id, sc_id, request={"assumptions": rows}, user_id=user, db=db)


# ── (e) PARITA': senza `sp_indexing` non cambia un centesimo ──

def test_no_indexing_is_a_fixed_point(monkeypatch):
    """Chiave assente ≡ `sp_indexing: null` ≡ `sp_indexing: {}`: gli stessi
    numeri, riga per riga, su SP e CE."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            _split_debts(db, company_id)
            rows = [dict(forecast_year=y, revenue_growth_pct=8, sp16g_growth_pct=3,
                         sp17d_growth_pct=5, **MANUAL_TAX) for y in (2027, 2028, 2029)]
            sc_a, _ = _run(db, company_id, rows)
            for variant in (None, {}):
                rows_b = [dict(r) for r in rows]
                for r in rows_b:
                    r["sp_indexing"] = variant
                sc_b, _ = _run(db, company_id, rows_b)
                for (_, bs_a, ce_a), (_, bs_b, ce_b) in zip(
                    read_forecast_maps(db, sc_a.id), read_forecast_maps(db, sc_b.id)
                ):
                    assert bs_a == bs_b and ce_a == ce_b
    finally:
        engine.dispose()


def test_details_declare_the_two_keys_without_any_indexing(monkeypatch):
    """`indicizzazione` e `indicizzazione_ignorata` su OGNI anno, anche vuote:
    a valle una chiave assente vale zero, quindi tacere equivarrebbe a
    dichiararsi indicizzati a nulla per scelta."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            rows = [dict(forecast_year=y, revenue_growth_pct=5, **MANUAL_TAX) for y in (2027, 2028)]
            sc, _ = _run(db, company_id, rows)
            out = _preview(db, company_id, sc.id, rows)
            assert len(out["forecast_years"]) == 2
            for year in out["forecast_years"]:
                assert year["details"]["indicizzazione"] == {}
                assert year["details"]["indicizzazione_ignorata"] == []
    finally:
        engine.dispose()


# ── (a) Il driver moltiplica lo stock dell'anno BASE, e non compone ──

def test_ricavi_driver_multiplies_the_base_stock_year_after_year(monkeypatch):
    """Ricavi +20%: `sp16g` vale `base × 1,2` nel primo anno e `base × 1,44` nel
    secondo — l'anno base per il fattore dell'anno, non il saldo dell'anno prima
    per una percentuale. Senza indicizzazione la stessa voce resta a 35.000."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            _split_debts(db, company_id)
            rows = [dict(forecast_year=y, revenue_growth_pct=20, **MANUAL_TAX) for y in (2027, 2028)]
            sc_base, _ = _run(db, company_id, rows)
            costante = [bs["sp16g_altri_debiti_breve"] for _, bs, _ in read_forecast_maps(db, sc_base.id)]
            assert costante == [D("35000.00"), D("35000.00")]

            rows_i = [dict(r, sp_indexing={"sp16g": "ricavi"}) for r in rows]
            sc, _ = _run(db, company_id, rows_i)
            indicizzato = [bs["sp16g_altri_debiti_breve"] for _, bs, _ in read_forecast_maps(db, sc.id)]
            assert indicizzato == [D("42000.00"), D("50400.00")]

            out = _preview(db, company_id, sc.id, rows_i)
            voce = out["forecast_years"][0]["details"]["indicizzazione"]["sp16g"]
            assert voce["driver"] == "ricavi"
            assert voce["fattore"] == D("1.2")
            assert out["forecast_years"][1]["details"]["indicizzazione"]["sp16g"]["fattore"] == D("1.44")
            assert out["forecast_years"][0]["details"]["indicizzazione_ignorata"] == []
    finally:
        engine.dispose()


def test_acquisti_and_personale_drivers(monkeypatch):
    """Gli altri due driver, sulla stessa forma. `acquisti` = `ce05 + ce06`
    previsti sui base (385.000/350.000 = 1,1); `personale` = `ce08` previsto sul
    base (150.000/120.000 = 1,25).

    Le due voci di acquisto sono forzate a importi che NON danno lo stesso
    fattore prese da sole (`ce05` 230.000/200.000 = 1,15): un driver che
    dimenticasse i servizi darebbe 11.500 invece di 11.000, e con due valori
    proporzionali il test non lo vedrebbe (mutazione M9, misurata)."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            _split_debts(db, company_id)
            rows = [dict(forecast_year=2027, revenue_growth_pct=10, personnel_growth_pct=25,
                         ce05_override=230000, ce06_override=155000,
                         sp_indexing={"sp17d": "acquisti", "sp16f": "personale"}, **MANUAL_TAX)]
            sc, _ = _run(db, company_id, rows)
            _, bs, _ = read_forecast_maps(db, sc.id)[0]
            assert bs["sp17d_debiti_fornitori_lungo"] == D("11000.00")   # 10.000 × 1,1
            assert bs["sp16f_debiti_previdenza_breve"] == D("18750.00")  # 15.000 × 1,25

            det = _preview(db, company_id, sc.id, rows)["forecast_years"][0]["details"]
            # `valore` e' il numero DAVVERO scritto sulla voce: e' quello che
            # rende esatto il confronto «persistito == dichiarato» anche dove la
            # formula ha un addendo in piu' di `base × fattore` (sp04, sp14).
            assert det["indicizzazione"]["sp17d"] == {
                "driver": "acquisti", "fattore": D("1.1"),
                "valore": D("11000"), "percentuale_ignorata": False}
            assert det["indicizzazione"]["sp16f"] == {
                "driver": "personale", "fattore": D("1.25"),
                "valore": D("18750"), "percentuale_ignorata": False}
    finally:
        engine.dispose()


def test_an_indexed_voce_ignores_its_growth_percentage_and_says_so(monkeypatch):
    """Un driver e una percentuale sulla stessa voce sono due affermazioni
    diverse: vince il driver, e la percentuale ignorata viene DICHIARATA — se
    tacesse, l'utente vedrebbe una casella che accetta un numero senza effetto."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            _split_debts(db, company_id)
            rows = [dict(forecast_year=2027, revenue_growth_pct=20, sp16g_growth_pct=90,
                         sp_indexing={"sp16g": "ricavi"}, **MANUAL_TAX)]
            sc, _ = _run(db, company_id, rows)
            _, bs, _ = read_forecast_maps(db, sc.id)[0]
            assert bs["sp16g_altri_debiti_breve"] == D("42000.00")  # 35.000 × 1,2, non × 1,9
            det = _preview(db, company_id, sc.id, rows)["forecast_years"][0]["details"]
            assert det["indicizzazione"]["sp16g"]["percentuale_ignorata"] is True
    finally:
        engine.dispose()


def test_indexing_sp04_does_not_cancel_the_writedowns_already_recorded(monkeypatch):
    """`ce09c` non torna indietro perche' la voce e' indicizzata.

    L'ancora sull'anno base riparte ogni anno dallo stesso stock: sottrarre la
    sola svalutazione dell'anno cancellerebbe quelle degli anni prima, e con un
    driver piatto (fattore 1,00) la serie 30.000 / 20.000 / 10.000 diventerebbe
    30.000 / 30.000 / 30.000 — senza una diagnostica, e con un attivo che non
    scende mentre il conto economico dichiara di averlo svalutato.

    L'asserzione forte e' l'ultima: **a fattore 1,00 l'indicizzazione non deve
    cambiare un solo centesimo** rispetto alla voce lasciata a riporto. Un driver
    che non si muove non e' un'ipotesi diversa.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            fy = db.query(FinancialYear).filter(FinancialYear.company_id == company_id).one()
            bs_row = db.query(BalanceSheet).filter(BalanceSheet.financial_year_id == fy.id).one()
            bs_row.sp03_immob_materiali = D("120000.00")
            bs_row.sp04_immob_finanziarie = D("40000.00")
            bs_row.sp04a_partecipazioni = D("40000.00")
            db.commit()
            # Ricavi fermi ⇒ fattore 1,00; `ce09c` di 10.000 l'anno.
            rows = [dict(forecast_year=y, revenue_growth_pct=0, ce09c_override=10000,
                         **MANUAL_TAX) for y in (2027, 2028, 2029)]
            sc_riporto, _ = _run(db, company_id, rows)
            a_riporto = [bs["sp04_immob_finanziarie"] for _, bs, _ in read_forecast_maps(db, sc_riporto.id)]
            assert a_riporto == [D("30000.00"), D("20000.00"), D("10000.00")]

            rows_i = [dict(r, sp_indexing={"sp04": "ricavi"}) for r in rows]
            sc, _ = _run(db, company_id, rows_i)
            indicizzato = [bs["sp04_immob_finanziarie"] for _, bs, _ in read_forecast_maps(db, sc.id)]
            assert indicizzato == [D("30000.00"), D("20000.00"), D("10000.00")]

            det = _preview(db, company_id, sc.id, rows_i)["forecast_years"]
            assert [d["details"]["svalutazioni_cumulate"] for d in det] == [
                D("10000"), D("20000"), D("30000")]
            # Fattore piatto ⇒ nessun numero si muove, riga per riga.
            for (_, bs_a, ce_a), (_, bs_b, ce_b) in zip(
                read_forecast_maps(db, sc_riporto.id), read_forecast_maps(db, sc.id)
            ):
                assert bs_a == bs_b and ce_a == ce_b
    finally:
        engine.dispose()


# ── (b) Driver degenere: costante, e dichiarato ──

def test_a_degenerate_driver_falls_back_to_constant_and_declares_it(monkeypatch):
    """Denominatore a zero (holding: nessun costo del personale nell'anno base)
    non produce un fattore inventato: la voce resta costante — cioe' la formula
    di oggi — e la ricaduta e' dichiarata invece di essere taciuta."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER, holding=True)
            fy = db.query(FinancialYear).filter(FinancialYear.company_id == company_id).one()
            bs_row = db.query(BalanceSheet).filter(BalanceSheet.financial_year_id == fy.id).one()
            bs_row.sp16d_debiti_fornitori_breve = D("30000.00")
            bs_row.sp16g_altri_debiti_breve = D("20000.00")
            db.commit()
            rows = [dict(forecast_year=2027, sp_indexing={"sp16g": "personale"}, **MANUAL_TAX)]
            sc, _ = _run(db, company_id, rows)
            _, bs, _ = read_forecast_maps(db, sc.id)[0]
            assert bs["sp16g_altri_debiti_breve"] == D("20000.00")
            det = _preview(db, company_id, sc.id, rows)["forecast_years"][0]["details"]
            assert det["indicizzazione"] == {}
            assert det["indicizzazione_ignorata"] == [
                {"voce": "sp16g", "driver": "personale", "motivo": "driver degenere"}
            ]
    finally:
        engine.dispose()


# ── (c) Piano di scadenziamento: il driver e' ignorato, non convive ──

def test_a_voce_with_a_runoff_plan_ignores_the_driver_and_names_it(monkeypatch):
    """Ruling 17. `validate_pregresso` impone che la massa dichiarata sia quella
    del bilancio base, quindi per una voce con piano il generato e' `base −
    massa` = 0: un fattore lo moltiplicherebbe restando zero, cioe' codice morto
    che l'utente crede attivo. Il piano vince, la voce si estingue con lui, e il
    driver e' dichiarato ignorato — riga per riga gli stessi numeri di uno
    scenario che il driver non lo aveva scritto affatto."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            _split_debts(db, company_id)
            piano = {"altri_debiti": {"opening": 55000, "amounts": [30000, 25000]}}
            rows = [dict(forecast_year=y, revenue_growth_pct=20, **MANUAL_TAX) for y in (2027, 2028)]
            rows[0]["pregresso"] = piano
            sc_plain, _ = _run(db, company_id, rows)

            rows_i = [dict(r, sp_indexing={"sp16g": "ricavi", "sp17g": "ricavi"}) for r in rows]
            sc, _ = _run(db, company_id, rows_i)
            for (_, bs_a, ce_a), (_, bs_b, ce_b) in zip(
                read_forecast_maps(db, sc_plain.id), read_forecast_maps(db, sc.id)
            ):
                assert bs_a == bs_b and ce_a == ce_b

            det = _preview(db, company_id, sc.id, rows_i)["forecast_years"][0]["details"]
            assert det["indicizzazione"] == {}
            assert det["indicizzazione_ignorata"] == [
                {"voce": "sp16g", "driver": "ricavi", "motivo": "piano di scadenziamento"},
                {"voce": "sp17g", "driver": "ricavi", "motivo": "piano di scadenziamento"},
            ]
    finally:
        engine.dispose()


# ── (d) Voci governate altrove: ignorate e dichiarate ──

def test_tax_and_bank_codes_are_ignored_and_declared(monkeypatch):
    """I tributari sono governati dalle imposte e le banche dal piano di
    rimborso: indicizzarli darebbe due padroni allo stesso numero. La chiave e'
    ignorata e DICHIARATA, mai applicata in silenzio."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            _split_debts(db, company_id)
            rows = [dict(forecast_year=2027, revenue_growth_pct=20, **MANUAL_TAX)]
            sc_plain, _ = _run(db, company_id, rows)
            rows_i = [dict(r, sp_indexing={"sp16e": "ricavi", "sp17a": "ricavi",
                                           "sp06f": "ricavi", "sp99": "ricavi"}) for r in rows]
            sc, _ = _run(db, company_id, rows_i)
            for (_, bs_a, ce_a), (_, bs_b, ce_b) in zip(
                read_forecast_maps(db, sc_plain.id), read_forecast_maps(db, sc.id)
            ):
                assert bs_a == bs_b and ce_a == ce_b
            det = _preview(db, company_id, sc.id, rows_i)["forecast_years"][0]["details"]
            assert det["indicizzazione"] == {}
            assert det["indicizzazione_ignorata"] == [
                {"voce": "sp06f", "driver": "ricavi", "motivo": "governata dalla posizione fiscale"},
                {"voce": "sp16e", "driver": "ricavi", "motivo": "governata dalla posizione tributaria"},
                {"voce": "sp17a", "driver": "ricavi", "motivo": "governata dal piano di rimborso"},
                {"voce": "sp99", "driver": "ricavi", "motivo": "voce non indicizzabile"},
            ]
    finally:
        engine.dispose()


def test_the_previdenza_switch_keeps_its_two_voci(monkeypatch):
    """`previdenza_scales_with_personnel` E' gia' l'indicizzazione di sp16f/sp17f
    al costo del personale, cablata su un interruttore. Con l'interruttore acceso
    una chiave su quelle due voci avrebbe due padroni: vince l'interruttore
    (cosi' gli scenari esistenti non cambiano di un centesimo) e la chiave e'
    dichiarata ignorata."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            _split_debts(db, company_id)
            rows = [dict(forecast_year=2027, revenue_growth_pct=20, personnel_growth_pct=25,
                         previdenza_scales_with_personnel=True, **MANUAL_TAX)]
            sc_plain, _ = _run(db, company_id, rows)
            rows_i = [dict(r, sp_indexing={"sp16f": "ricavi", "sp17f": "ricavi"}) for r in rows]
            sc, _ = _run(db, company_id, rows_i)
            for (_, bs_a, ce_a), (_, bs_b, ce_b) in zip(
                read_forecast_maps(db, sc_plain.id), read_forecast_maps(db, sc.id)
            ):
                assert bs_a == bs_b and ce_a == ce_b
            det = _preview(db, company_id, sc.id, rows_i)["forecast_years"][0]["details"]
            assert det["indicizzazione"] == {}
            assert [v["motivo"] for v in det["indicizzazione_ignorata"]] == [
                "governata dall'interruttore previdenza/personale"] * 2
    finally:
        engine.dispose()


# ── Il residuo di quadratura non riscrive una voce indicizzata ──

def test_the_quadratura_residual_never_rewrites_an_indexed_voce(monkeypatch):
    """`sp16g`/`sp17g` sono i secchi di default del residuo di `sp16`/`sp17` —
    esattamente le due voci che questo lotto indicizza piu' spesso. Il valore
    persistito deve restare `base × fattore` al centesimo: e' il difetto che il
    Task 11 ha chiuso sul CE e il Task 5 sullo SP, qui sulla terza famiglia di
    campi dichiarati."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            _split_debts(db, company_id)
            # La combinazione non e' stata immaginata: e' stata CERCATA con una
            # sonda che disattiva la dichiarazione dei campi forzati e prova 48
            # scenari — 15 divergono, e questo e' il piu' semplice (crescita
            # 3,33%, DSO esplicito, rimborso del debito esistente a 7 anni: nel
            # 2028 `sp17g` persiste 21.354,17 contro i 21.354,18 dichiarati).
            rows = [dict(forecast_year=y, revenue_growth_pct=3.33, dso_days=47.3,
                         existing_debt_repayment_years=7,
                         sp_indexing={"sp16g": "ricavi", "sp17g": "ricavi"}, **MANUAL_TAX)
                    for y in (2027, 2028, 2029)]
            sc, _ = _run(db, company_id, rows)
            out = _preview(db, company_id, sc.id, rows)
            for (_, bs, _), preview in zip(read_forecast_maps(db, sc.id), out["forecast_years"]):
                fattore = preview["details"]["indicizzazione"]["sp16g"]["fattore"]
                # ROUND_HALF_UP: la stessa quantizzazione del motore
                # (`_quantize_values`), non quella di default di Decimal.
                def atteso(base):
                    return (base * fattore).quantize(D("0.01"), rounding=ROUND_HALF_UP)
                assert bs["sp16g_altri_debiti_breve"] == atteso(D("35000"))
                assert bs["sp17g_altri_debiti_lungo"] == atteso(D("20000"))
                # il centesimo non e' sparito: i due gruppi quadrano lo stesso
                assert bs["sp16_debiti_breve"] == sum(
                    bs[f] for f in bs if f.startswith("sp16") and f != "sp16_debiti_breve")
                assert bs["sp17_debiti_lungo"] == sum(
                    bs[f] for f in bs if f.startswith("sp17") and f != "sp17_debiti_lungo")
    finally:
        engine.dispose()


# ── Schema e persistenza ──

def test_schema_accepts_the_three_drivers_and_rejects_a_fourth():
    ok = BudgetAssumptionsCreate(scenario_id=1, forecast_year=2027,
                                 sp_indexing={"sp16g": "ricavi", "sp17d": "acquisti", "sp16f": "personale"})
    assert ok.sp_indexing["sp16g"] == "ricavi"
    with pytest.raises(Exception):
        BudgetAssumptionsCreate(scenario_id=1, forecast_year=2027, sp_indexing={"sp16g": "inflazione"})


def test_build_assumption_row_carries_sp_indexing_as_json():
    row = build_assumption_row(1, {"forecast_year": 2027, "sp_indexing": {"sp16g": "ricavi"}})
    assert row.sp_indexing == {"sp16g": "ricavi"}
    assert build_assumption_row(1, {"forecast_year": 2027}).sp_indexing is None
