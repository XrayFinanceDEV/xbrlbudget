"""Al 31/12 l'infrannuale lascia solo il saldo d'imposta dell'anno (lotto 3A, Task 5, decisione 4 del proprietario)."""
from decimal import Decimal as D

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import calculations.projection_common as comune
from backend.app.services import assumptions_service, forecast_preview_service
from backend.app.services.promote_service import promote_projection_to_financial_year
from calculations.intra_year_engine import IntraYearEngine
from database.db import Base
from database.models import (BalanceSheet, BudgetAssumptions, BudgetScenario, Company, FinancialYear, ForecastYear,
                             IncomeStatement)

APERTURA = D("1150949.04")


def _kernel():
    fn = getattr(comune, "posizione_tributaria_fine_anno", None)
    assert callable(fn), "projection_common.posizione_tributaria_fine_anno non esiste"
    return fn


def test_i_numeri_della_sonda_sono_quelli_del_kernel_budget():
    p = _kernel()(opening_credit=0, opening_debt=APERTURA, remaining_current_tax=D("120000"),
                  current_tax=D("120000"), reference_tax=D("0"), explicit_advances=D("99247.26"))
    assert (p.closing_debt, p.closing_credit, p.acconti, p.cash_out) == (
        D("20752.74"), D("0"), D("99247.26"), D("1250196.30"))
    budget = comune.tax_settlement_saldo_acconto(opening_credit=0, saldo_due=APERTURA, rate_due=0,
                                                 current_tax=D("120000"), previous_tax=0, acconto_pct=D("100"),
                                                 explicit_advances=D("99247.26"))
    assert (budget.generated_debt, budget.cash_out) == (p.closing_debt, p.cash_out)


@pytest.mark.parametrize("dichiarati", [D("0"), D("-5")], ids=["zero", "negativo"])
def test_acconti_non_dichiarati_valgono_il_cento_per_cento_dell_imposta_di_riferimento(dichiarati):
    p = _kernel()(opening_credit=0, opening_debt=APERTURA, remaining_current_tax=D("120000"),
                  current_tax=D("120000"), reference_tax=D("80000"), explicit_advances=dichiarati)
    assert (p.acconti, p.closing_debt, p.cash_out) == (D("80000"), D("40000"), D("1230949.04"))


def test_una_posizione_negativa_diventa_credito():
    p = _kernel()(opening_credit=0, opening_debt=APERTURA, remaining_current_tax=D("120000"),
                  current_tax=D("120000"), reference_tax=D("150000"), explicit_advances=0)
    assert (p.closing_credit, p.closing_debt, p.cash_out) == (D("30000"), D("0"), D("1300949.04"))


def test_il_credito_di_apertura_e_l_imposta_gia_maturata_non_si_ripagano():
    con_credito = _kernel()(opening_credit=D("50000"), opening_debt=0, remaining_current_tax=D("120000"),
                            current_tax=D("120000"), reference_tax=0, explicit_advances=D("99247.26"))
    assert (con_credito.closing_debt, con_credito.cash_out) == (D("20752.74"), D("49247.26"))
    maturata = _kernel()(opening_credit=0, opening_debt=D("30000"), remaining_current_tax=D("30000"),
                         current_tax=D("120000"), reference_tax=0, explicit_advances=D("99247.26"))
    assert (maturata.closing_debt, maturata.cash_out) == (D("20752.74"), D("39247.26"))


def _sessione():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _infrannuale(db, imposta_riferimento, acconti):
    """Riferimento 2024 con imposta R e 1.000.000 di debito tributario; parziale 2025 (9 mesi) con 1.150.949,04."""
    azienda = Company(name="Imposte infra", tax_id="IMPOSTE-INFRA", sector=1)
    db.add(azienda)
    db.flush()
    anni = (
        (2024, None, dict(sp11_capitale=D("1000"), sp13_utile_perdita=-imposta_riferimento,
                          sp16_debiti_breve=D("1000000"), sp16e_debiti_tributari_breve=D("1000000"),
                          sp09_disponibilita_liquide=D("1000") - imposta_riferimento + D("1000000")),
         dict(ce20_imposte=imposta_riferimento)),
        (2025, 9, dict(sp11_capitale=D("2000000"), sp13_utile_perdita=D("0"), sp16_debiti_breve=APERTURA,
                       sp16e_debiti_tributari_breve=APERTURA, sp09_disponibilita_liquide=D("2000000") + APERTURA), {}),
    )
    for anno, mesi, stato, conto in anni:
        fy = FinancialYear(company_id=azienda.id, year=anno, period_months=mesi,
                           validation_status="verified", forecastable=True)
        db.add(fy)
        db.flush()
        db.add(BalanceSheet(financial_year_id=fy.id, **stato))
        db.add(IncomeStatement(financial_year_id=fy.id, **conto))
    scenario = BudgetScenario(company_id=azienda.id, name="infra", base_year=2024,
                              scenario_type="infrannuale", period_months=9)
    db.add(scenario)
    db.flush()
    db.add(BudgetAssumptions(scenario_id=scenario.id, forecast_year=2025, tax_rate=D("0"),
                             fixed_materials_percentage=D("0"), fixed_services_percentage=D("0"),
                             ce20_override=D("120000"), tax_advances_paid=acconti))
    db.commit()
    IntraYearEngine(db).generate_projection(scenario.id)
    return azienda, scenario


@pytest.mark.parametrize("riferimento, acconti, attesi", [
    (D("80000"), D("0"), ("40000.00", "0.00", "1920000.00")),
    (D("150000"), D("0"), ("0.00", "30000.00", "1850000.00")),
    (D("80000"), D("99247.26"), ("20752.74", "0.00", "1900752.74")),
], ids=["acconti non dichiarati", "posizione a credito", "acconti dichiarati"])
def test_la_proiezione_persiste_il_solo_saldo_e_paga_il_resto_di_cassa(riferimento, acconti, attesi):
    db = _sessione()
    _azienda, scenario = _infrannuale(db, riferimento, acconti)
    sp = db.query(ForecastYear).filter(ForecastYear.scenario_id == scenario.id).one().balance_sheet
    assert (sp.sp16e_debiti_tributari_breve, sp.sp06e_crediti_tributari_breve, sp.sp09_disponibilita_liquide) == tuple(
        D(v) for v in attesi)


def test_il_budget_nato_dal_promote_non_eredita_il_debito_dell_anno_prima():
    db = _sessione()
    azienda, scenario = _infrannuale(db, D("80000"), D("99247.26"))
    promote_projection_to_financial_year(db, scenario.id)
    budget = BudgetScenario(company_id=azienda.id, name="budget", base_year=2025, scenario_type="budget")
    db.add(budget)
    db.commit()
    righe = [{"forecast_year": 2026, "revenue_growth_pct": 0, "tax_rate": 27.9}]
    esito = assumptions_service.bulk_upsert_assumptions(db, budget.id, [dict(r) for r in righe], auto_generate=True)
    assert esito["forecast_generated"] is True, esito["message"]
    anteprima = forecast_preview_service.preview_forecast(db, budget.id, [dict(r) for r in righe])
    assert D(str(anteprima["forecast_years"][0]["details"]["imposte"]["saldo_paid"])) == D("20752.74")
