"""La colonna di un anno compare una volta sola nella tabella indici.

Un anno promosso (proiezione infrannuale copiata su FinancialYear) esiste sia
come anno storico sia come anno di previsione dello scenario che lo ha
generato. `calculate_ratios_historical_and_forecast` prendeva TUTTI gli anni
storici a pieno periodo, ignorando il `base_year` che pure riceve: il 2026
finiva due volte nella lista `years` e il frontend rendeva due colonne con la
stessa chiave React.
"""
import os
import sys
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import backend.app.main  # noqa: F401,E402  — inserisce la project root in sys.path
from database.db import Base  # noqa: E402
from database.models import (  # noqa: E402
    BalanceSheet,
    BudgetScenario,
    Company,
    FinancialYear,
    ForecastBalanceSheet,
    ForecastIncomeStatement,
    ForecastYear,
    IncomeStatement,
)
from backend.app.services import calculation_service  # noqa: E402

D = Decimal


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _bs(**kw):
    return BalanceSheet(
        sp09_disponibilita_liquide=D("1000"),
        sp11_capitale=D("1000"),
        **kw,
    )


def _is(**kw):
    return IncomeStatement(ce01_ricavi_vendite=D("5000"), **kw)


def _forecast_bs(**kw):
    return ForecastBalanceSheet(
        sp09_disponibilita_liquide=D("1000"),
        sp11_capitale=D("1000"),
        **kw,
    )


def _forecast_is(**kw):
    return ForecastIncomeStatement(ce01_ricavi_vendite=D("5000"), **kw)


def _company_with_promoted_year(db):
    """2023-2025 storici, 2026 promosso, scenario base 2025 con previsione 2026-2028."""
    company = Company(name="Promossa S.r.l.", tax_id="00000000001", sector=1,
                      user_id="test-user")
    db.add(company)
    db.flush()

    for year in (2023, 2024, 2025, 2026):
        fy = FinancialYear(company_id=company.id, year=year, period_months=None)
        fy.balance_sheet = _bs()
        fy.income_statement = _is()
        db.add(fy)

    scenario = BudgetScenario(company_id=company.id, name="Budget 2026-2028",
                              base_year=2025, scenario_type="budget")
    db.add(scenario)
    db.flush()

    for year in (2026, 2027, 2028):
        fcy = ForecastYear(scenario_id=scenario.id, year=year)
        fcy.balance_sheet = _forecast_bs()
        fcy.income_statement = _forecast_is()
        db.add(fcy)

    db.commit()
    return company, scenario


def test_no_duplicate_year_columns(db):
    company, scenario = _company_with_promoted_year(db)

    result = calculation_service.calculate_ratios_historical_and_forecast(
        db=db, company_id=company.id, scenario_id=scenario.id,
        base_year=scenario.base_year,
    )

    years = result["years"]
    assert len(years) == len(set(years)), f"anni duplicati: {years}"


def test_historical_stops_at_base_year_and_forecast_continues(db):
    company, scenario = _company_with_promoted_year(db)

    result = calculation_service.calculate_ratios_historical_and_forecast(
        db=db, company_id=company.id, scenario_id=scenario.id,
        base_year=scenario.base_year,
    )

    # Il 2026 c'è, ma è quello dello SCENARIO: l'anno promosso non lo raddoppia.
    assert result["years"] == [2023, 2024, 2025, 2026, 2027, 2028]
    assert len(result["ratios"]) == len(result["years"])


def test_rod_usa_il_debito_finanziario_medio_dalla_seconda_colonna(db):
    """#61 S11 · il ROD dal secondo anno e' sul debito medio inizio/fine; la prima colonna resta sulla fine anno."""
    company = Company(name="Rod S.r.l.", tax_id="00000000002", sector=1, user_id="test-user")
    db.add(company)
    db.flush()
    for year, debito in ((2024, "100000"), (2025, "300000")):
        fy = FinancialYear(company_id=company.id, year=year, period_months=None)
        fy.balance_sheet = _bs(sp16a_debiti_banche_breve=D(debito))
        fy.income_statement = _is(ce15_oneri_finanziari=D("10000"))
        db.add(fy)
    scenario = BudgetScenario(company_id=company.id, name="B", base_year=2025, scenario_type="budget")
    db.add(scenario)
    db.commit()

    result = calculation_service.calculate_ratios_historical_and_forecast(
        db=db, company_id=company.id, scenario_id=scenario.id, base_year=2025)
    rod = {y: r["profitability"]["rod"] for y, r in zip(result["years"], result["ratios"])}
    assert result["years"] == [2024, 2025]
    assert abs(D(str(rod[2024])) - D("10000") / D("100000")) < D("0.0001")
    assert abs(D(str(rod[2025])) - D("10000") / D("200000")) < D("0.0001")


def test_rod_prima_colonna_ignora_un_anno_precedente_solo_parziale(db):
    """#61 S11 · se year-1 esiste solo come record parziale, la prima colonna resta sulla fine anno."""
    company = Company(name="Parz S.r.l.", tax_id="00000000003", sector=1, user_id="test-user")
    db.add(company)
    db.flush()
    for year, mesi, debito in ((2024, 6, "100000"), (2025, None, "300000")):
        fy = FinancialYear(company_id=company.id, year=year, period_months=mesi)
        fy.balance_sheet = _bs(sp16a_debiti_banche_breve=D(debito))
        fy.income_statement = _is(ce15_oneri_finanziari=D("10000"))
        db.add(fy)
    scenario = BudgetScenario(company_id=company.id, name="B", base_year=2025, scenario_type="budget")
    db.add(scenario)
    db.commit()
    result = calculation_service.calculate_ratios_historical_and_forecast(
        db=db, company_id=company.id, scenario_id=scenario.id, base_year=2025)
    assert result["years"] == [2025]
    assert abs(D(str(result["ratios"][0]["profitability"]["rod"])) - D("10000") / D("300000")) < D("0.0001")


def _storico(db, company, year, **bs):
    fy = FinancialYear(company_id=company.id, year=year, period_months=None)
    fy.balance_sheet = _bs(**bs)
    fy.income_statement = _is(ce15_oneri_finanziari=D("10000"))
    db.add(fy)


def test_rod_apertura_senza_dettaglio_finanziario_resta_sulla_fine_anno(db):
    """Fix finale 1 · sp16+sp17 > 0 con le sei sotto-voci finanziarie a zero e' un import non
    classificato: la media inizio/fine dimezzerebbe il debito di chiusura e raddoppierebbe il ROD."""
    company = Company(name="NoDet S.r.l.", tax_id="00000000004", sector=1, user_id="test-user")
    db.add(company)
    db.flush()
    _storico(db, company, 2024, sp16_debiti_breve=D("500000"), sp16d_debiti_fornitori_breve=D("500000"))
    _storico(db, company, 2025, sp16_debiti_breve=D("300000"), sp16a_debiti_banche_breve=D("300000"))
    scenario = BudgetScenario(company_id=company.id, name="B", base_year=2025, scenario_type="budget")
    db.add(scenario)
    db.commit()
    result = calculation_service.calculate_ratios_historical_and_forecast(
        db=db, company_id=company.id, scenario_id=scenario.id, base_year=2025)
    rod = {y: r["profitability"]["rod"] for y, r in zip(result["years"], result["ratios"])}
    assert abs(D(str(rod[2025])) - D("10000") / D("300000")) < D("0.0001")


def test_analysis_rod_anno_di_piano_con_base_senza_dettaglio_non_si_raddoppia(db):
    """Fix finale 1 + 10 · /analysis: base 2025 senza dettaglio finanziario -> ROD del primo anno di
    piano sul debito di fine anno; la prima colonna storica legge l'anno prima a DB come /ratios."""
    from backend.app.services import analysis_service
    company = Company(name="NoDetA S.r.l.", tax_id="00000000005", sector=1, user_id="test-user")
    db.add(company)
    db.flush()
    _storico(db, company, 2023, sp16_debiti_breve=D("100000"), sp16a_debiti_banche_breve=D("100000"))
    _storico(db, company, 2024, sp16_debiti_breve=D("300000"), sp16a_debiti_banche_breve=D("300000"))
    _storico(db, company, 2025, sp16_debiti_breve=D("500000"), sp16d_debiti_fornitori_breve=D("500000"))
    scenario = BudgetScenario(company_id=company.id, name="B", base_year=2025, scenario_type="budget")
    db.add(scenario)
    db.flush()
    fcy = ForecastYear(scenario_id=scenario.id, year=2026)
    fcy.balance_sheet = _forecast_bs(sp16_debiti_breve=D("200000"), sp16a_debiti_banche_breve=D("200000"))
    fcy.income_statement = _forecast_is(ce15_oneri_finanziari=D("10000"))
    db.add(fcy)
    db.commit()
    by_year = analysis_service.get_complete_analysis(
        db=db, company_id=company.id, scenario_id=scenario.id)["calculations"]["by_year"]
    rod = {y: D(str(v["ratios"]["profitability"]["rod"])) for y, v in by_year.items() if v["ratios"]["profitability"]["rod"] is not None}
    assert abs(rod["2026"] - D("10000") / D("200000")) < D("0.0001")      # non 10000/350000 ne' doppiato
    assert abs(rod["2024"] - D("10000") / D("200000")) < D("0.0001")      # media 2023-2024


def test_rod_chiusura_senza_dettaglio_finanziario_e_none_anche_con_apertura_dettagliata(db):
    """Residuo fix finale 1 · apertura dettagliata + chiusura non classificata: niente media (dimezzerebbe
    il debito), il debito di chiusura vale 0 e il ROD e' None, coerente con F1."""
    company = Company(name="NoDetC S.r.l.", tax_id="00000000006", sector=1, user_id="test-user")
    db.add(company)
    db.flush()
    _storico(db, company, 2024, sp16_debiti_breve=D("300000"), sp16a_debiti_banche_breve=D("300000"))
    _storico(db, company, 2025, sp16_debiti_breve=D("500000"), sp16d_debiti_fornitori_breve=D("500000"))
    scenario = BudgetScenario(company_id=company.id, name="B", base_year=2025, scenario_type="budget")
    db.add(scenario)
    db.commit()
    result = calculation_service.calculate_ratios_historical_and_forecast(
        db=db, company_id=company.id, scenario_id=scenario.id, base_year=2025)
    rod = {y: r["profitability"]["rod"] for y, r in zip(result["years"], result["ratios"])}
    assert rod[2025] is None
