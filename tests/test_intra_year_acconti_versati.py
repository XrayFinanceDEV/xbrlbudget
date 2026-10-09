"""#63 R09: «Acconti già versati nell'anno» (`tax_advances_already_paid`) nell'infrannuale.

G sta dentro i crediti tributari a breve del parziale (`sp06e`). Gli acconti effettivi dell'anno sono
max(A, G); al 31/12 resta imposta − A_eff, e il credito d'apertura che resta in bilancio è `sp06e − G`:
nel periodo residuo escono di cassa solo A_eff − G."""
from decimal import Decimal as D

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import calculations.projection_common as comune
from calculations.intra_year_engine import IntraYearEngine
from database.db import Base
from database.models import (BalanceSheet, BudgetAssumptions, BudgetScenario, Company, FinancialYear, ForecastYear,
                             IncomeStatement)

CREDITO = D("15000")


def _proietta(riferimento, acconti, versati, credito=CREDITO, imposta=D("30000")):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    azienda = Company(name="Acconti versati", tax_id="ACC-VERS", sector=1)
    db.add(azienda)
    db.flush()
    anni = (
        (2024, None, dict(sp11_capitale=D("1000000"), sp13_utile_perdita=-riferimento,
                          sp09_disponibilita_liquide=D("1000000") - riferimento),
         dict(ce20_imposte=riferimento)),
        (2025, 6, dict(sp11_capitale=D("1000000"), sp06e_crediti_tributari_breve=credito, sp06_crediti_breve=credito,
                       sp09_disponibilita_liquide=D("1000000") - credito), {}),
    )
    for anno, mesi, stato, conto in anni:
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
                             ce20_override=imposta, tax_advances_paid=acconti, tax_advances_already_paid=versati))
    db.commit()
    esito = IntraYearEngine(db).generate_projection(scenario.id)
    sp = db.query(ForecastYear).filter(ForecastYear.scenario_id == scenario.id).one().balance_sheet
    diag = [d for d in esito["diagnostics"] if d["code"] == "posizione_tributaria_apertura"]
    return (sp.sp16e_debiti_tributari_breve, sp.sp06e_crediti_tributari_breve, sp.sp09_disponibilita_liquide), diag


def test_g_zero_non_muove_nulla():
    base, diag = _proietta(D("28773"), D("10000"), D("0"))
    assert base[:2] == (D("20000.00"), D("15000.00"))
    assert D(diag[0]["acconti_gia_versati"]) == 0 and D(diag[0]["credito_residuo_apertura"]) == D("15000")


def test_esempio_acconto_esplicito():
    # imposta 30.000, G = 10.000, A = 10.000: debito 20.000, credito d'apertura 15.000 - 10.000
    (debito, credito, cassa), diag = _proietta(D("28773"), D("10000"), D("10000"))
    base, _ = _proietta(D("28773"), D("10000"), D("0"))
    assert (debito, credito) == (D("20000.00"), D("5000.00"))
    assert cassa - base[2] == D("10000.00")          # nessun acconto in uscita: la cassa guadagna G
    assert D(diag[0]["acconti_gia_versati"]) == D("10000")
    assert D(diag[0]["credito_residuo_apertura"]) == D("5000")
    assert D(diag[0]["acconti_effettivi"]) == D("10000")


def test_esempio_acconti_al_cento_per_cento_dell_anno_prima():
    # A vuoto -> 100% di 28.773: debito 1.227, escono 18.773 (A_eff - G), credito d'apertura 5.000
    (debito, credito, cassa), diag = _proietta(D("28773"), D("0"), D("10000"))
    base, _ = _proietta(D("28773"), D("0"), D("0"))
    assert (debito, credito) == (D("1227.00"), D("5000.00"))
    assert cassa - base[2] == D("10000.00")
    assert D(diag[0]["acconti_effettivi"]) == D("28773")


def test_g_maggiore_di_a_alza_gli_acconti_effettivi():
    (debito, credito, _), diag = _proietta(D("0"), D("5000"), D("10000"))
    assert (debito, credito) == (D("20000.00"), D("5000.00"))
    assert D(diag[0]["acconti_effettivi"]) == D("10000")


def test_g_oltre_sp06e_e_rifiutato_in_italiano():
    with pytest.raises(ValueError, match="superano i crediti tributari"):
        _proietta(D("28773"), D("0"), D("15000.01"))


def test_kernel_g_zero_identico():
    k = comune.posizione_tributaria_fine_anno
    a = k(opening_credit=0, opening_debt=0, remaining_current_tax=D("1"), current_tax=D("30000"),
          reference_tax=D("28773"), explicit_advances=0)
    assert (a.closing_debt, a.acconti, a.already_paid) == (D("1227"), D("28773"), D("0"))
