"""Un previsionale piu' vecchio delle ipotesi si dichiara (Task 13).

Il difetto: `PUT /scenarios/{id}/assumptions` risponde **200 con
`success: true`** anche quando la generazione viene respinta (CLAUDE.md ›
«Invarianti e trappole › Previsionale»). Le ipotesi restano salvate, il
`ForecastYear` no — e le cinque viste che leggono `/analysis` continuano a
mostrare i numeri della generazione **precedente** senza un segnale.

Il meccanismo e' un confronto di timestamp, non una bandiera persistita
(ruling del controllore 2026-09-09): il previsionale e' stantio quando
`max(updated_at delle ipotesi) > max(updated_at dei ForecastYear)`. Una
bandiera puo' divergere dalla realta', un confronto no.

Perche' `test_una_rigenerazione_riuscita_torna_allineata` non e' ridondante:
il ciclo di `generate_forecast` fa l'upsert dei figli (`ForecastBalanceSheet`,
`ForecastIncomeStatement`) e sul `ForecastYear` gia' esistente non scrive
nulla, quindi l'`onupdate` della colonna **non scatta**. Misurato prima della
correzione: dopo una seconda generazione riuscita `fy.updated_at` restava al
microsecondo della prima, e ogni rigenerazione successiva alla prima si
sarebbe dichiarata stantia. E' per questo che il motore ora tocca
esplicitamente `fy.updated_at`.
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal

# `backend/app/api/v1/analysis.py` importa `app.core.database` senza il
# bootstrap di sys.path che i suoi fratelli (`budget_scenarios.py`) fanno da
# soli: senza questa riga la raccolta del modulo riesce o fallisce a seconda
# dell'ordine degli import di questo file, che e' esattamente il genere di
# dipendenza che non deve reggere una suite.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

from backend.app.api.v1 import analysis as analysis_api
from backend.app.api.v1 import budget_scenarios
from backend.app.schemas.budget import BudgetScenarioCreate
from database import models
from tests.e2e_kit import memory_sessions, seed_base_year

USER = "stale"

# Un piano di investimenti che nessuna fonte finanzia: il motore budget
# **solleva** (`Unfunded financing requirement`) e non produce nulla, mentre
# il bulk risponde comunque 200. E' il caso reale che questo task rende
# visibile.
UNFUNDED = {"tangible_investments": 9_000_000}


def _scenario(db, company_id, base_year=2026):
    return budget_scenarios.create_budget_scenario(
        company_id,
        BudgetScenarioCreate(
            company_id=company_id, name="s", base_year=base_year, scenario_type="budget"
        ),
        user_id=USER,
        db=db,
    )


def _save(db, company_id, scenario_id, *, growth=5.0, extra=None, auto_generate=True):
    rows = [
        dict({"forecast_year": y, "revenue_growth_pct": growth}, **(extra or {}))
        for y in (2027, 2028)
    ]
    return budget_scenarios.bulk_upsert_assumptions(
        company_id,
        scenario_id,
        request={"assumptions": rows, "auto_generate": auto_generate},
        user_id=USER,
        db=db,
    )


def _istante(iso):
    """Il timestamp emesso da /analysis, riletto come istante UTC.

    Mai confrontare le stringhe: `isoformat()` omette la frazione quando i
    microsecondi sono zero, e col suffisso `Z` `"…00Z"` > `"…00.500000Z"` pur
    essendo l'istante precedente.
    """
    assert iso.endswith("Z"), iso
    return datetime.fromisoformat(iso)


def _analysis(db, company_id, scenario_id):
    return analysis_api.get_complete_analysis(
        company_id,
        scenario_id,
        include_historical=True,
        include_forecast=True,
        include_calculations=False,
        user_id=USER,
        db=db,
    )


def test_generazione_riuscita_non_e_stantia():
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            sc = _scenario(db, company_id)
            assert _save(db, company_id, sc.id)["forecast_generated"] is True

            out = _analysis(db, company_id, sc.id)
            assert out["forecast_stale"] is False
            # I due timestamp ci sono sempre quando c'e' qualcosa da datare:
            # servono a spiegare l'avviso, non solo ad alzarlo.
            assert out["assumptions_updated_at"] is not None
            assert out["forecast_updated_at"] is not None
            assert _istante(out["assumptions_updated_at"]) < _istante(out["forecast_updated_at"])
    finally:
        engine.dispose()


def test_generazione_respinta_dal_bulk_rende_stantio_il_previsionale():
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            sc = _scenario(db, company_id)
            assert _save(db, company_id, sc.id)["forecast_generated"] is True
            prima = _analysis(db, company_id, sc.id)
            ricavi_prima = [
                y["income_statement"]["ce01_ricavi_vendite"] for y in prima["forecast_years"]
            ]

            respinto = _save(db, company_id, sc.id, growth=30.0, extra=UNFUNDED)
            # Il bulk mente sullo status: 200 e `success: true` su una
            # generazione che non e' avvenuta.
            assert respinto["success"] is True
            assert respinto["forecast_generated"] is False

            dopo = _analysis(db, company_id, sc.id)
            assert dopo["forecast_stale"] is True
            # I numeri a schermo sono ancora quelli della generazione
            # precedente: e' esattamente cio' che l'avviso deve dire.
            assert [
                y["income_statement"]["ce01_ricavi_vendite"] for y in dopo["forecast_years"]
            ] == ricavi_prima
            assert _istante(dopo["assumptions_updated_at"]) > _istante(dopo["forecast_updated_at"])
    finally:
        engine.dispose()


def test_una_rigenerazione_riuscita_torna_allineata():
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            sc = _scenario(db, company_id)
            assert _save(db, company_id, sc.id)["forecast_generated"] is True
            assert _save(db, company_id, sc.id, growth=30.0, extra=UNFUNDED)["forecast_generated"] is False
            assert _analysis(db, company_id, sc.id)["forecast_stale"] is True

            # La via d'uscita: ipotesi sostenibili, generazione riuscita.
            assert _save(db, company_id, sc.id, growth=7.0)["forecast_generated"] is True
            out = _analysis(db, company_id, sc.id)
            assert out["forecast_stale"] is False
            assert _istante(out["assumptions_updated_at"]) < _istante(out["forecast_updated_at"])
    finally:
        engine.dispose()


def test_senza_previsionale_non_e_stantio():
    """Nessun `ForecastYear` ⇒ `false`, non `true`: non c'e' niente di stantio
    da mostrare, la vista e' vuota e il vuoto si vede da solo."""
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            sc = _scenario(db, company_id)
            salvato = _save(db, company_id, sc.id, auto_generate=False)
            assert salvato["forecast_generated"] is False
            assert db.query(models.ForecastYear).filter(
                models.ForecastYear.scenario_id == sc.id
            ).count() == 0

            out = _analysis(db, company_id, sc.id)
            assert out["forecast_stale"] is False
            assert out["forecast_updated_at"] is None
            assert out["assumptions_updated_at"] is not None
    finally:
        engine.dispose()


def test_auto_generate_false_su_un_previsionale_gia_generato_e_stantio():
    """Il percorso `auto_generate=false` e' un vero stantio, non un falso
    positivo: le ipotesi sono nuove e il previsionale a schermo e' quello di
    prima."""
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            sc = _scenario(db, company_id)
            assert _save(db, company_id, sc.id)["forecast_generated"] is True
            assert _analysis(db, company_id, sc.id)["forecast_stale"] is False

            _save(db, company_id, sc.id, growth=12.0, auto_generate=False)
            assert _analysis(db, company_id, sc.id)["forecast_stale"] is True
    finally:
        engine.dispose()


class _Riga:
    def __init__(self, updated_at=None, created_at=None):
        self.updated_at = updated_at
        self.created_at = created_at


class _Scenario:
    def __init__(self, assumptions, forecast_years):
        self.assumptions = assumptions
        self.forecast_years = forecast_years


def _stale(assumptions, forecast_years):
    from backend.app.services.analysis_service import _forecast_staleness

    return _forecast_staleness(_Scenario(assumptions, forecast_years))


T0 = datetime(2026, 9, 10, 8, 0, 0, 100000)
T1 = datetime(2026, 9, 10, 8, 0, 0, 100001)  # un microsecondo dopo


def test_il_confronto_e_stretto_e_guarda_il_microsecondo():
    """La parita' e' «allineato», non «stantio»: il confronto stretto e' cio'
    che rende innocuo il caso in cui due scritture cadono nello stesso
    istante. E la discriminazione arriva al microsecondo, perche' e' quella la
    distanza reale fra il salvataggio delle ipotesi e la generazione."""
    assert _stale([_Riga(T0)], [_Riga(T0)])[2] is False
    assert _stale([_Riga(T1)], [_Riga(T0)])[2] is True
    assert _stale([_Riga(T0)], [_Riga(T1)])[2] is False


def test_si_guarda_il_piu_recente_di_ogni_lato():
    """Le ipotesi sono una per anno e i `ForecastYear` pure: conta il massimo
    di ciascun insieme, non il primo che capita."""
    assert _stale([_Riga(T0), _Riga(T1)], [_Riga(T0), _Riga(T0)])[2] is True
    assert _stale([_Riga(T0), _Riga(T0)], [_Riga(T0), _Riga(T1)])[2] is False


def test_una_riga_senza_updated_at_ricade_su_created_at():
    assert _stale([_Riga(None, T1)], [_Riga(T0)])[2] is True
    assert _stale([_Riga(None, T0)], [_Riga(None, T1)])[2] is False
    # Una riga senza alcun timestamp non e' un verdetto: e' un dato mancante.
    assert _stale([_Riga()], [_Riga(T0)])[2] is False


def test_scenario_senza_ipotesi_non_e_stantio():
    """Nemmeno il caso simmetrico alza l'avviso: senza ipotesi non c'e' un
    termine di confronto, e un controllo che manca e' «non lo so»."""
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            sc = _scenario(db, company_id)
            out = _analysis(db, company_id, sc.id)
            assert out["forecast_stale"] is False
            assert out["assumptions_updated_at"] is None
            assert out["forecast_updated_at"] is None
    finally:
        engine.dispose()


def test_i_timestamp_escono_in_utc_esplicito_con_e_senza_frazione():
    """Le colonne sono `default=datetime.utcnow`, cioe' UTC ingenuo: senza
    offset `Date.parse` le legge come ora locale. Il suffisso e' `Z`.

    I due formati sono entrambi reali: `isoformat()` omette la frazione quando
    i microsecondi sono zero. Ed e' proprio questa coppia a ordinarsi al
    contrario come stringhe (`'Z'` > `'.'`), cosa che la suite del client
    (`budget-stale.test.ts`) usa per provare che si confrontano gli istanti.
    """
    senza = datetime(2026, 9, 10, 8, 0, 0)
    con = datetime(2026, 9, 10, 8, 0, 0, 500000)
    assumptions_iso, forecast_iso, stale = _stale([_Riga(con)], [_Riga(senza)])
    assert assumptions_iso == "2026-09-10T08:00:00.500000Z"
    assert forecast_iso == "2026-09-10T08:00:00Z"
    assert stale is True
    # La premessa che rende pericoloso il confronto di stringhe:
    assert forecast_iso > assumptions_iso
    assert _istante(forecast_iso) < _istante(assumptions_iso)


def test_un_timestamp_con_fuso_esce_in_utc_con_una_sola_z():
    """Oggi le colonne sono ingenue. Se diventassero con fuso, accodare `Z` a
    `isoformat()` darebbe `…+00:00Z`, che `Date.parse` non legge: il client
    tratterebbe il timestamp come assente e l'avviso resterebbe spento senza
    un errore. Un valore con fuso si porta in UTC prima di uscire."""
    roma = timezone(timedelta(hours=2))
    alle_dieci_a_roma = datetime(2026, 9, 10, 10, 0, 0, 500000, tzinfo=roma)
    alle_otto_utc = datetime(2026, 9, 10, 8, 0, 0, tzinfo=timezone.utc)
    assumptions_iso, forecast_iso, stale = _stale(
        [_Riga(alle_dieci_a_roma)], [_Riga(alle_otto_utc)]
    )
    assert assumptions_iso == "2026-09-10T08:00:00.500000Z"
    assert forecast_iso == "2026-09-10T08:00:00Z"
    assert stale is True


# ── Infrannuale: il gemello della rigenerazione ────────────────────────────
#
# `IntraYearEngine._save_forecast` ha lo stesso upsert sui soli figli del
# motore budget, e la stessa riga che tocca `fy.updated_at`. Senza un test
# proprio quella riga si poteva togliere lasciando verde la suite intera
# (revisione del task 13, rilievo 1): tornerebbe l'avviso «stantio» permanente
# su ogni infrannuale rigenerato piu' di una volta.
#
# Le ipotesi vanno risalvate FRA le due generazioni, e non solo prima della
# prima: altrimenti, anche senza quella riga, `updated_at` resterebbe alla
# prima generazione — gia' piu' recente delle ipotesi — e il test passerebbe
# per la ragione sbagliata. Due salvataggi bulk sono esattamente questo.

INFRA_ROW = {
    "forecast_year": 2025,
    "tax_rate": 0,
    "fixed_materials_percentage": 0,
    "fixed_services_percentage": 0,
    "ce01_override": 5000,
}


def _infrannuale(db):
    """Riferimento 2024 a 12 mesi e parziale 2025 a 9 mesi, entrambi quadrati
    e con utile CE == `sp13`, o il cancello di forecastabilita' li rifiuterebbe."""
    company = models.Company(name="Infra stale", tax_id="INFRA-STALE", sector=1, user_id=USER)
    db.add(company)
    db.flush()

    ref = models.FinancialYear(
        company_id=company.id, year=2024, period_months=None,
        validation_status="verified", forecastable=True,
    )
    db.add(ref)
    db.flush()
    db.add(models.BalanceSheet(
        financial_year_id=ref.id,
        sp09_disponibilita_liquide=Decimal("1500"),
        sp11_capitale=Decimal("300"),
        sp13_utile_perdita=Decimal("1200"),
    ))
    db.add(models.IncomeStatement(financial_year_id=ref.id, ce01_ricavi_vendite=Decimal("1200")))

    partial = models.FinancialYear(
        company_id=company.id, year=2025, period_months=9,
        validation_status="verified", forecastable=True,
    )
    db.add(partial)
    db.flush()
    db.add(models.BalanceSheet(
        financial_year_id=partial.id,
        sp09_disponibilita_liquide=Decimal("1200"),
        sp11_capitale=Decimal("300"),
        sp13_utile_perdita=Decimal("900"),
    ))
    db.add(models.IncomeStatement(financial_year_id=partial.id, ce01_ricavi_vendite=Decimal("900")))

    scenario = models.BudgetScenario(
        company_id=company.id, name="Infrannuale 9M", base_year=2024,
        scenario_type="infrannuale", period_months=9,
    )
    db.add(scenario)
    db.commit()
    return company.id, scenario.id


def _save_infra(db, company_id, scenario_id, row):
    return budget_scenarios.bulk_upsert_assumptions(
        company_id,
        scenario_id,
        request={"assumptions": [row], "auto_generate": True},
        user_id=USER,
        db=db,
    )


def test_infrannuale_rigenerato_due_volte_non_e_stantio():
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, scenario_id = _infrannuale(db)

            primo = _save_infra(db, company_id, scenario_id, INFRA_ROW)
            assert primo["forecast_generated"] is True, primo["message"]
            assert _analysis(db, company_id, scenario_id)["forecast_stale"] is False

            secondo = _save_infra(db, company_id, scenario_id, dict(INFRA_ROW, ce01_override=6000))
            assert secondo["forecast_generated"] is True, secondo["message"]

            # Un solo ForecastYear: la seconda generazione e' passata dal ramo
            # «anno gia' esistente», che e' quello sotto prova.
            assert db.query(models.ForecastYear).filter(
                models.ForecastYear.scenario_id == scenario_id
            ).count() == 1

            out = _analysis(db, company_id, scenario_id)
            assert out["forecast_stale"] is False
            assert _istante(out["assumptions_updated_at"]) < _istante(out["forecast_updated_at"])
    finally:
        engine.dispose()
