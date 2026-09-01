"""Il ramo a plug negativo persiste un bilancio normalizzato come ogni altro.

`generate_projection` normalizzava il bilancio proiettato solo in assenza di
diagnostiche `severity: "error"` — ma `unfunded_financing_requirement`, alzata
proprio quando il plug di cassa e' negativo, ha quella severita'. Il ramo in cui
il foglio e' piu' fragile era quindi l'unico a salvare valori non quantizzati e
sotto-campi che non sommano al proprio aggregato, e nessun controllo se ne
accorgeva: lo sbilancio da arrotondamento spariva dentro lo sbilancio piu'
grande che la diagnostica dichiara gia'.
"""

from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from calculations.intra_year_engine import IntraYearEngine
from database.db import Base
from database.models import (
    BalanceSheet,
    BudgetAssumptions,
    BudgetScenario,
    Company,
    FinancialYear,
    ForecastYear,
    IncomeStatement,
)


D = Decimal

# I sotto-campi di sp02 nell'ordine di `_distribute_sp02`, col secchio generico
# in coda: e' li' che il residuo di arrotondamento deve finire.
SP02_DETTAGLI = (
    'sp02a_costi_impianto', 'sp02b_costi_sviluppo', 'sp02c_brevetti',
    'sp02d_concessioni', 'sp02e_avviamento', 'sp02f_immob_in_corso',
    'sp02g_altre_immob_imm',
)


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


def _scenario(db, *, ce01_override, ce05_override, tag):
    """Un infrannuale a 9 mesi con sp02 ripartito in TRE parti uguali.

    Il terzo e' la chiave del test: `_distribute_sp02` scala i dettagli per
    ratio, quindi 1.000,00 su tre parti da' 333,3333... e la quantizzazione di
    ciascuna lascia un residuo di un centesimo contro l'aggregato. E' il difetto
    che `_normalize_balance_sheet_cents` esiste per assorbire.

    Le due override di CE decidono il ramo: una perdita ampia fa collassare il
    passivo sotto l'attivo non-cassa e manda il plug sotto zero; un utile ampio
    lo tiene sopra. L'anno parziale e' bilanciato e con `utile_ce == sp13`, o il
    cancello `_validate_forecastable` lo rifiuterebbe prima di arrivare al plug.
    """
    company = Company(name=f"Plug {tag}", tax_id=f"PLUG-{tag}", sector=1)
    db.add(company)
    db.flush()

    ref = FinancialYear(
        company_id=company.id, year=2024, period_months=None,
        validation_status="verified", forecastable=True,
    )
    db.add(ref)
    db.flush()
    db.add(BalanceSheet(
        financial_year_id=ref.id,
        sp09_disponibilita_liquide=D("1500"),
        sp11_capitale=D("300"),
        sp13_utile_perdita=D("1200"),
    ))
    db.add(IncomeStatement(financial_year_id=ref.id, ce01_ricavi_vendite=D("1200")))

    partial = FinancialYear(
        company_id=company.id, year=2025, period_months=9,
        validation_status="verified", forecastable=True,
    )
    db.add(partial)
    db.flush()
    db.add(BalanceSheet(
        financial_year_id=partial.id,
        sp02_immob_immateriali=D("1000"),
        sp02a_costi_impianto=D("1"),
        sp02b_costi_sviluppo=D("1"),
        sp02c_brevetti=D("1"),
        sp09_disponibilita_liquide=D("200"),
        sp11_capitale=D("300"),
        sp13_utile_perdita=D("900"),
    ))
    db.add(IncomeStatement(financial_year_id=partial.id, ce01_ricavi_vendite=D("900")))

    scenario = BudgetScenario(
        company_id=company.id, name="Infrannuale 9M", base_year=2024,
        scenario_type="infrannuale", period_months=9,
    )
    db.add(scenario)
    db.flush()
    db.add(BudgetAssumptions(
        scenario_id=scenario.id, forecast_year=2025, tax_rate=D("0"),
        fixed_materials_percentage=D("0"), fixed_services_percentage=D("0"),
        ce01_override=ce01_override, ce05_override=ce05_override,
    ))
    db.commit()
    return scenario


def _persisted_bs(db, scenario_id):
    return db.query(ForecastYear).filter(
        ForecastYear.scenario_id == scenario_id
    ).one().balance_sheet


def _quantizzato(valore):
    return valore == valore.quantize(D("0.01"))


def test_plug_negativo_persiste_sotto_campi_che_sommano_al_proprio_aggregato(db_session):
    scenario = _scenario(
        db_session, ce01_override=D("0"), ce05_override=D("5000"), tag="neg",
    )
    engine = IntraYearEngine(db_session)

    result = engine.generate_projection(scenario.id)

    assert result["success"] is True
    # Il ramo giusto: il plug e' andato sotto zero ed e' stato dichiarato.
    assert any(
        d["code"] == "unfunded_financing_requirement" and d["severity"] == "error"
        for d in result["diagnostics"]
    )
    bs = _persisted_bs(db_session, scenario.id)
    # Il clamp verso l'alto sopravvive: l'IntraYearEngine non trasforma un plug
    # negativo in debito a breve, a differenza del motore budget.
    assert bs.sp09_disponibilita_liquide == D("0")
    assert bs.sp16_debiti_breve == D("0")

    dettagli = [getattr(bs, campo) for campo in SP02_DETTAGLI]
    assert all(_quantizzato(v) for v in dettagli)
    assert _quantizzato(bs.sp02_immob_immateriali)
    assert sum(dettagli, D("0")) == bs.sp02_immob_immateriali


def test_plug_positivo_normalizza_come_prima_e_ricalcola_la_cassa(db_session):
    scenario = _scenario(
        db_session, ce01_override=D("5000"), ce05_override=D("0"), tag="pos",
    )
    engine = IntraYearEngine(db_session)

    result = engine.generate_projection(scenario.id)

    assert result["success"] is True
    assert not any(
        d["code"] == "unfunded_financing_requirement" for d in result["diagnostics"]
    )
    bs = _persisted_bs(db_session, scenario.id)
    assert bs.sp09_disponibilita_liquide > D("0")
    # Sul ramo pulito il ricalcolo finale di sp09 gira, quindi il foglio quadra
    # al centesimo: e' l'invariante che la guardia proteggeva e che resta.
    assert bs.total_assets == bs.total_liabilities

    dettagli = [getattr(bs, campo) for campo in SP02_DETTAGLI]
    assert sum(dettagli, D("0")) == bs.sp02_immob_immateriali
