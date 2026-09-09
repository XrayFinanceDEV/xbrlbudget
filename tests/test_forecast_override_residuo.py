"""Un override di dettaglio sopravvive alla normalizzazione dei centesimi (Task 11).

Il difetto, misurato prima della correzione: `_normalize_income_statement_cents`
posava SEMPRE il residuo di arrotondamento sull'ultimo dettaglio del gruppo
(`ce08d_altri_costi_personale` / `ce09d_svalutazione_crediti`), a prescindere
dal fatto che quel campo portasse un override esplicito. Senza alcun override
di dettaglio il residuo e' zero al centesimo — per questo il difetto era
invisibile — ma con un `ce08d_override` il residuo vale l'intera differenza fra
l'aggregato e i quattro dettagli e ci finisce sopra: `ce08d_override=7000` con
l'aggregato piu' alto diventava **113.777,78** sulla riga persistita, un numero
che l'utente non ha mai scritto. Il campo colpito e' esattamente quello in cui
questo lotto scrive l'inesigibile crediti (spec 2026-09-08-scadenziamento-
pregresso §3.4): senza questa correzione il motore scriverebbe in un campo che
il passaggio successivo riscrive.

Le ipotesi sono oggetti `BudgetAssumptions` staccati, mai persistiti: si
costruiscono con lo stesso passaggio del banco di sensibilita'
(`scripts.sensibilita_ipotesi._default_di_schema`), perche' un oggetto ORM
staccato non riceve i default di colonna e il motore troverebbe `None` dove si
aspetta un numero.
"""
from decimal import Decimal

from calculations.forecast_engine import ForecastEngine, load_forecast_source
from database.models import BudgetAssumptions, BudgetScenario
from scripts.sensibilita_ipotesi import NON_IPOTESI, _default_di_schema
from tests.e2e_kit import memory_sessions, seed_base_year

D = Decimal
USER = "override-residuo"


def _riga(scenario_id, forecast_year, **overrides):
    """Una riga di ipotesi staccata, ogni campo al default di schema."""
    riga = BudgetAssumptions()
    riga.scenario_id = scenario_id
    riga.forecast_year = forecast_year
    for colonna in BudgetAssumptions.__table__.columns:
        if colonna.name in NON_IPOTESI:
            continue
        setattr(riga, colonna.name, _default_di_schema(colonna))
    riga.tax_rate = D("27.9")
    for campo, valore in overrides.items():
        setattr(riga, campo, valore)
    return riga


def _source(db, user_id=USER):
    """Azienda + anno base persistiti (servono a `load_forecast_source`), scenario incluso."""
    company_id, _ = seed_base_year(db, user_id=user_id)
    scenario = BudgetScenario(
        company_id=company_id, name="s", base_year=2026, scenario_type="budget",
    )
    db.add(scenario)
    db.commit()
    return load_forecast_source(db, scenario.id)


def test_ce08d_override_sopravvive():
    """`ce08d_override=7000` con l'aggregato ce08 naturalmente piu' alto: la
    riga persistita vale 7.000,00, non il residuo che il difetto ci scaricava
    sopra (misurato: 113.777,78)."""
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            source = _source(db)
            riga = _riga(source.scenario.id, 2027, ce08d_override=D("7000.00"))
            comp = ForecastEngine(db).compute_forecast(source, [riga])
            assert comp.error is None
            ce = comp.years[0].income_statement
            assert ce["ce08d_altri_costi_personale"] == D("7000.00")
    finally:
        engine.dispose()


def test_ce09d_override_sopravvive():
    """Stesso difetto sul gruppo ammortamenti, sul campo in cui questo lotto
    scrive l'inesigibile crediti. Il residuo qui e' un centesimo di
    arrotondamento genuino (due dettagli con ammortamento frazionario, che
    quantizzati singolarmente non sommano all'aggregato quantizzato), non una
    grande differenza come per ce08 — ma un override pulito non deve riceverne
    comunque nemmeno uno: il residuo va sull'ultimo dettaglio libero (ce09c)."""
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            source = _source(db)
            riga = _riga(
                source.scenario.id, 2027,
                ce09d_override=D("5000.00"),
                tangible_investments=D("100.03"),
                intangible_investments=D("100.03"),
                depreciation_rate=D("11"),
                depreciation_rate_intangible=D("11"),
            )
            comp = ForecastEngine(db).compute_forecast(source, [riga])
            assert comp.error is None
            ce = comp.years[0].income_statement
            assert ce["ce09d_svalutazione_crediti"] == D("5000.00")
            # Il residuo di un centesimo esiste davvero (altrimenti il caso non
            # proverebbe nulla): ce09c, l'ultimo dettaglio libero, lo assorbe, e
            # i quattro dettagli tornano a sommare esattamente l'aggregato.
            assert ce["ce09c_svalutazioni"] == D("0.01")
            details_sum = (
                ce["ce09a_ammort_immateriali"] + ce["ce09b_ammort_materiali"]
                + ce["ce09c_svalutazioni"] + ce["ce09d_svalutazione_crediti"]
            )
            assert details_sum == ce["ce09_ammortamenti"]
    finally:
        engine.dispose()


def test_residuo_va_sul_dettaglio_non_forzato():
    """ce08d forzato, ce08c libero: il residuo si posa su ce08c, e i quattro
    dettagli tornano a sommare esattamente l'aggregato."""
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            source = _source(db)
            riga = _riga(source.scenario.id, 2027, ce08d_override=D("7000.00"))
            comp = ForecastEngine(db).compute_forecast(source, [riga])
            ce = comp.years[0].income_statement
            assert ce["ce08d_altri_costi_personale"] == D("7000.00")
            # ce08b resta al proprio valore naturale (0, nessuna crescita nella
            # linea di base): il residuo scarta ce08d (forzato) e finisce
            # sull'ultimo libero, ce08c.
            assert ce["ce08c_oneri_sociali"] != D("0.00")
            somma = (
                ce["ce08a_tfr_accrual"] + ce["ce08b_salari_stipendi"]
                + ce["ce08c_oneri_sociali"] + ce["ce08d_altri_costi_personale"]
            )
            assert somma == ce["ce08_costi_personale"]
    finally:
        engine.dispose()


def test_aggregato_libero_segue_i_dettagli_forzati_ce08():
    """Tutti e quattro i dettagli di ce08 forzati, l'aggregato libero (nessun
    `ce08_override`): l'aggregato persistito e' la loro somma (10.000,00),
    non il valore che la crescita avrebbe prodotto dall'anno base (120.000,00
    — nessuna crescita del personale nella linea di base, quindi l'aggregato
    "naturale" resterebbe fermo li'). Discrimina davvero: tolto il ramo che
    implementa questa regola (`calculations/forecast_engine.py` — «se tutti i
    dettagli sono forzati e l'aggregato no, l'aggregato diventa la loro
    somma»), l'aggregato persistito torna a 120.000,00 (misurato)."""
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            source = _source(db)
            riga = _riga(
                source.scenario.id, 2027,
                ce08a_override=D("1000.00"),
                ce08b_override=D("2000.00"),
                ce08c_override=D("3000.00"),
                ce08d_override=D("4000.00"),
            )
            comp = ForecastEngine(db).compute_forecast(source, [riga])
            assert comp.error is None
            ce = comp.years[0].income_statement
            assert ce["ce08_costi_personale"] == D("10000.00")
    finally:
        engine.dispose()


def test_aggregato_libero_segue_i_dettagli_forzati_ce09():
    """Stesso ramo, gruppo ammortamenti, con un residuo di arrotondamento
    genuino: quattro dettagli forzati a 1,004 quantizzano tutti a 1,00
    (somma 4,00), ma la somma grezza pre-quantizzazione (4,016) arrotonda
    a 4,02. L'aggregato libero deve seguire i dettagli persistiti (4,00), non
    il residuo di un centesimo. Discrimina: tolto lo stesso ramo, l'aggregato
    resta 4,02 e il centesimo di residuo finisce scaricato sull'ultimo
    dettaglio (misurato)."""
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            source = _source(db)
            riga = _riga(
                source.scenario.id, 2027,
                ce09a_override=D("1.004"),
                ce09b_override=D("1.004"),
                ce09c_override=D("1.004"),
                ce09d_override=D("1.004"),
            )
            comp = ForecastEngine(db).compute_forecast(source, [riga])
            assert comp.error is None
            ce = comp.years[0].income_statement
            assert ce["ce09a_ammort_immateriali"] == D("1.00")
            assert ce["ce09b_ammort_materiali"] == D("1.00")
            assert ce["ce09c_svalutazioni"] == D("1.00")
            assert ce["ce09d_svalutazione_crediti"] == D("1.00")
            assert ce["ce09_ammortamenti"] == D("4.00")
    finally:
        engine.dispose()


def test_conflitto_dichiarato():
    """ce08 e tutti e quattro i dettagli forzati e fra loro incoerenti:
    l'aggregato vince (com'era prima), e il conflitto e' dichiarato in
    `details['override_conflicts']`, mai taciuto."""
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            source = _source(db)
            riga = _riga(
                source.scenario.id, 2027,
                ce08_override=D("100000.00"),
                ce08a_override=D("1000.00"),
                ce08b_override=D("2000.00"),
                ce08c_override=D("3000.00"),
                ce08d_override=D("4000.00"),
            )
            comp = ForecastEngine(db).compute_forecast(source, [riga])
            year = comp.years[0]
            ce = year.income_statement
            # L'aggregato dichiarato vince.
            assert ce["ce08_costi_personale"] == D("100000.00")
            # Tutti e quattro i dettagli sono forzati: nessuno e' libero, il
            # residuo va sull'ultimo del gruppo (ce08d), com'era prima.
            assert ce["ce08d_altri_costi_personale"] == D("94000.00")
            conflicts = year.details["override_conflicts"]
            assert conflicts == [{
                "aggregate": "ce08_costi_personale",
                "declared": D("100000.00"),
                "details_sum": D("10000.00"),
            }]
    finally:
        engine.dispose()
