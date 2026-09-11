"""Sull'infrannuale un override che squilibra non persiste una cassa negativa (lotto 3A, Task 11; §11.1 del lotto 2).

Sonda sullo snapshot `452112d`: con `sp05_rimanenze` forzato a 5.000.000 la proiezione persisteva `sp09` −4.998.445,00
con le sole diagnostiche warning.
"""
from decimal import Decimal as D

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.services.promote_service import promote_projection_to_financial_year
from calculations.intra_year_engine import IntraYearEngine
from database.db import Base
from database.models import (BalanceSheet, BudgetAssumptions, BudgetScenario, Company, FinancialYear, ForecastYear,
                             IncomeStatement)


def _proietta(override):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    azienda = Company(name="Override infra", tax_id="OVERRIDE-INFRA", sector=1)
    db.add(azienda)
    db.flush()
    for anno, mesi, utile in ((2024, None, D("0")), (2025, 9, D("100"))):
        fy = FinancialYear(company_id=azienda.id, year=anno, period_months=mesi, validation_status="verified", forecastable=True)
        db.add(fy)
        db.flush()
        db.add(BalanceSheet(financial_year_id=fy.id, sp09_disponibilita_liquide=D("1000") + utile,
                            sp11_capitale=D("1000"), sp13_utile_perdita=utile))
        db.add(IncomeStatement(financial_year_id=fy.id, ce01_ricavi_vendite=utile))
    scenario = BudgetScenario(company_id=azienda.id, name="infra", base_year=2024, scenario_type="infrannuale", period_months=9)
    db.add(scenario)
    db.flush()
    db.add(BudgetAssumptions(scenario_id=scenario.id, forecast_year=2025, tax_rate=D("0"),
                             fixed_materials_percentage=D("0"), fixed_services_percentage=D("0"),
                             ce01_override=D("555"), sp_overrides=override))
    db.commit()
    esito = IntraYearEngine(db).generate_projection(scenario.id)
    sp = db.query(ForecastYear).filter(ForecastYear.scenario_id == scenario.id).one().balance_sheet
    fabbisogni = [d for d in esito["diagnostics"] if d["code"] == "unfunded_financing_requirement"]
    return db, scenario, sp.sp09_disponibilita_liquide, fabbisogni


def test_un_override_che_squilibra_diventa_un_fabbisogno_dichiarato_con_la_cassa_a_zero():
    db, scenario, cassa, fabbisogni = _proietta({"sp05_rimanenze": 5000000})
    assert cassa == D("0.00"), f"cassa persistita {cassa}"
    assert [(d["severity"], d["amount"]) for d in fabbisogni] == [("error", "4998445.00")]
    with pytest.raises(ValueError):
        promote_projection_to_financial_year(db, scenario.id)


@pytest.mark.parametrize("override, cassa_attesa", [
    ({"sp08_attivita_finanziarie": 1500}, "55.00"),
    ({"sp11_capitale": 1200}, "1755.00"),
], ids=["attivo che la cassa copre", "capitale forzato"])
def test_un_override_che_la_cassa_copre_non_cambia_nulla(override, cassa_attesa):
    _db, _scenario, cassa, fabbisogni = _proietta(override)
    assert (cassa, fabbisogni) == (D(cassa_attesa), [])
