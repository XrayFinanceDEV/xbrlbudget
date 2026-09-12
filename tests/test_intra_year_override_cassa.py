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


def _proietta(override, rompi_ripartizione_breve=False):
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
        cassa = D("1000") + utile
        kwargs = dict(financial_year_id=fy.id, sp11_capitale=D("1000"), sp13_utile_perdita=utile)
        if rompi_ripartizione_breve and anno == 2025:
            # Il parziale ha un sp16 aggregato con un dettaglio coerente CON SE STESSO
            # (sp16d = 400 = sp16_debiti_breve): non e' questo che rompe la ripartizione.
            # E' l'anno di riferimento (2024, sotto, senza alcun dettaglio sp16a..g) a
            # lasciare `_distribute_sp16` senza una proporzione da applicare
            # (calculations/intra_year_engine.py:1791-1802): la diagnostica
            # `missing_short_debt_breakdown` (severita' 'error') nasce PRIMA di ogni
            # override, indipendente da esso.
            kwargs["sp16_debiti_breve"] = D("400")
            kwargs["sp16d_debiti_fornitori_breve"] = D("400")
            cassa += D("400")
        kwargs["sp09_disponibilita_liquide"] = cassa
        db.add(BalanceSheet(**kwargs))
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


def test_recompute_cash_gira_anche_con_una_diagnostica_derrore_gia_presente():
    """Task 11 (lotto 3A): il terzo passo del ricalcolo cassa in `generate_projection`
    (`_normalize_balance_sheet_cents(recompute_cash=True)`) deve girare SEMPRE, non solo in
    assenza di diagnostiche d'errore preesistenti. Prima del fix era condizionato a
    `not ha_errori`: con una diagnostica d'errore gia' presente (qui
    `missing_short_debt_breakdown`, innescata da un anno di riferimento senza dettaglio sp16
    mentre il parziale ne dichiara uno coerente con se stesso) e un override che tocca ANCHE
    `sp09` (l'unico campo che esclude il ricalcolo automatico gia' interno a
    `_apply_sp_overrides`), la vecchia condizione lasciava la cassa congelata al valore
    letterale dell'override (1,00), sbilanciando il foglio persistito di 2.954,00. La rete
    esistente in questo file non lo vedeva: nei suoi tre scenari nessuna diagnostica d'errore
    precede l'override, quindi `ha_errori` era gia' `False` anche col codice vecchio."""
    _db, _scenario, cassa, fabbisogni = _proietta(
        {"sp11_capitale": 2000, "sp09_disponibilita_liquide": 1}, rompi_ripartizione_breve=True,
    )
    assert cassa == D("2955.00"), f"cassa persistita {cassa}: il ricalcolo dopo l'override non e' girato"
    assert fabbisogni == []
