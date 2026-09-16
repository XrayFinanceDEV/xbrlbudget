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


def _proietta_con_diagnostiche(modo):
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
    esito = IntraYearEngine(db).generate_projection(scenario.id)
    anno = db.query(ForecastYear).filter(ForecastYear.scenario_id == scenario.id).one()
    return anno.balance_sheet, esito["diagnostics"]


def _proietta(modo):
    return _proietta_con_diagnostiche(modo)[0]


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


def _con_fabbisogno(modo):
    """Un'azienda in perdita con i crediti gonfi: coi giorni osservati il piano non
    chiude, coi giorni consolidati sì. Il corridoio contiene una soluzione.

    Riferimento 2024: ricavi 1.000.000, costi 1.400.000 (perdita 400.000), crediti
    250.000 = 90 giorni. Parziale 2025/6M: ricavi 500.000, costi 700.000 (perdita
    200.000), crediti 400.000 = 144 giorni annualizzati.
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    azienda = Company(name="Equilibrio", tax_id="EQUILIBRIO-MODO", sector=1)
    db.add(azienda)
    db.flush()
    rif = dict(sp06_crediti_breve=D("250000"), sp06a_crediti_clienti_breve=D("250000"),
               sp16_debiti_breve=D("100000"), sp16d_debiti_fornitori_breve=D("100000"),
               sp11_capitale=D("600000"), sp13_utile_perdita=D("-400000"),
               sp09_disponibilita_liquide=D("50000"))
    par = dict(sp06_crediti_breve=D("400000"), sp06a_crediti_clienti_breve=D("400000"),
               sp16_debiti_breve=D("100000"), sp16d_debiti_fornitori_breve=D("100000"),
               sp11_capitale=D("600000"), sp13_utile_perdita=D("-200000"),
               sp09_disponibilita_liquide=D("100000"))
    for anno, mesi, stato, conto in (
        (2024, None, rif, dict(ce01_ricavi_vendite=D("1000000"), ce05_materie_prime=D("1400000"))),
        (2025, 6, par, dict(ce01_ricavi_vendite=D("500000"), ce05_materie_prime=D("700000"))),
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
    esito = IntraYearEngine(db).generate_projection(scenario.id)
    sp = db.query(ForecastYear).filter(ForecastYear.scenario_id == scenario.id).one().balance_sheet
    return sp, esito["diagnostics"]


def test_il_circolante_di_equilibrio_chiude_la_cassa_restando_nel_corridoio():
    """Coi giorni osservati il piano ha un fabbisogno; il motore si sposta verso i
    giorni consolidati quel tanto che basta, e dichiara dove è arrivato."""
    infrannuale, diag_infra = _con_fabbisogno("infrannuale")
    fabbisogno = [d for d in diag_infra if d["code"] == "unfunded_financing_requirement"]
    assert fabbisogno, "il caso di prova deve partire da un fabbisogno"
    assert infrannuale.sp09_disponibilita_liquide == D("0.00")

    equilibrio, diag = _con_fabbisogno("equilibrio")
    # La cassa chiude a zero senza restare negativa: nessun fabbisogno.
    assert not [d for d in diag if d["code"] == "unfunded_financing_requirement"]
    assert equilibrio.sp09_disponibilita_liquide >= D("0")
    assert equilibrio.sp09_disponibilita_liquide < D("1000")
    dichiarazioni = [d for d in diag if d["code"] == "circolante_di_equilibrio"]
    assert len(dichiarazioni) == 1
    messaggio = dichiarazioni[0]["message"]
    assert "giorni di incasso" in messaggio
    assert "osservati" in messaggio and "consolidati" in messaggio
    # I crediti restano dentro il corridoio: fra i due estremi, mai fuori.
    storico, _ = _con_fabbisogno("storico")
    assert storico.sp06_crediti_breve <= equilibrio.sp06_crediti_breve <= infrannuale.sp06_crediti_breve


def test_se_il_circolante_di_equilibrio_gia_chiude_non_sposta_nulla():
    """Quando i giorni osservati bastano da soli, l'equilibrio non muove niente e
    non dichiara nulla: non c'è nessun fabbisogno da chiudere."""
    osservato = _proietta("infrannuale")
    equilibrio, diag = _proietta_con_diagnostiche("equilibrio")
    assert equilibrio.sp06_crediti_breve == osservato.sp06_crediti_breve
    assert not [d for d in diag if d["code"] == "circolante_di_equilibrio"]
