"""Da dove vengono i giorni del circolante: sceglie l'utente (decisione del
proprietario, 2026-09-16, due pulsanti nella tab Proiezione).

«Sui gg medi è più attendibile il bilancio intero dell'anno precedente — la
situazione infrannuale non è assestata — oppure lasciare la situazione simile
all'infrannuale osservato: diamo l'opzione all'utente.»

Su AMBIENTA 2026/6M la differenza vale 357.561,87 € di crediti, cioè altrettanta
cassa proiettata: non è una rifinitura, è la domanda a cui la proiezione risponde.
"""
from decimal import Decimal as D

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from calculations.intra_year_engine import IntraYearEngine
from database.db import Base
from database.models import (BalanceSheet, BudgetAssumptions, BudgetScenario, Company, FinancialYear, ForecastYear,
                             IncomeStatement)

# Riferimento: 100.000 di crediti su 1.000.000 di ricavi = 36 giorni.
# Parziale 6M: 200.000 su 500.000 (un milione annualizzato) = 72 giorni.
_RIF = dict(sp06_crediti_breve=D("100000"), sp06a_crediti_clienti_breve=D("100000"),
            sp11_capitale=D("100000"), sp13_utile_perdita=D("500000"),
            sp09_disponibilita_liquide=D("500000"))
_PAR = dict(sp06_crediti_breve=D("200000"), sp06a_crediti_clienti_breve=D("200000"),
            sp11_capitale=D("100000"), sp13_utile_perdita=D("250000"),
            sp09_disponibilita_liquide=D("150000"))


def _proietta(modo):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    azienda = Company(name="Circolante", tax_id="CIRCOLANTE-MODO", sector=1)
    db.add(azienda)
    db.flush()
    for anno, mesi, stato, conto in (
        (2024, None, _RIF, dict(ce01_ricavi_vendite=D("1000000"), ce05_materie_prime=D("500000"))),
        (2025, 6, _PAR, dict(ce01_ricavi_vendite=D("500000"), ce05_materie_prime=D("250000"))),
    ):
        fy = FinancialYear(company_id=azienda.id, year=anno, period_months=mesi,
                           validation_status="verified", forecastable=True)
        db.add(fy)
        db.flush()
        db.add(BalanceSheet(financial_year_id=fy.id, **stato))
        db.add(IncomeStatement(financial_year_id=fy.id, **conto))
    scenario = BudgetScenario(company_id=azienda.id, name="infra", base_year=2024,
                              scenario_type="infrannuale", period_months=6)
    db.add(scenario)
    db.flush()
    db.add(BudgetAssumptions(scenario_id=scenario.id, forecast_year=2025, tax_rate=D("0"),
                             fixed_materials_percentage=D("0"), fixed_services_percentage=D("0"),
                             working_capital_mode=modo))
    db.commit()
    IntraYearEngine(db).generate_projection(scenario.id)
    return db.query(ForecastYear).filter(ForecastYear.scenario_id == scenario.id).one().balance_sheet


@pytest.mark.parametrize("modo", ["storico", None], ids=["scelta esplicita", "scenario vecchio"])
def test_il_circolante_storico_usa_i_giorni_dell_anno_intero(modo):
    """NULL vale «storico»: nessuno scenario già salvato cambia numeri finché
    l'utente non sceglie."""
    sp = _proietta(modo)
    assert sp.sp06_crediti_breve == D("100000.00")


def test_il_circolante_infrannuale_porta_avanti_i_giorni_osservati():
    """Il parziale mostra 72 giorni di incasso contro i 36 dell'anno di
    riferimento: qui la proiezione li tiene, invece di assumere un rientro che
    nessuno ha deciso."""
    sp = _proietta("infrannuale")
    assert sp.sp06_crediti_breve == D("200000.00")


def test_le_due_modalita_non_dicono_la_stessa_cosa():
    storico = _proietta("storico")
    infrannuale = _proietta("infrannuale")
    differenza = infrannuale.sp06_crediti_breve - storico.sp06_crediti_breve
    assert differenza == D("100000.00")
    # E la differenza si vede tutta in cassa, perché è la cassa a chiudere il foglio.
    assert storico.sp09_disponibilita_liquide - infrannuale.sp09_disponibilita_liquide == differenza
