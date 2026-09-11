"""Per Immobiliare ed Edilizia un magazzino oltre l'anno scala coi ricavi; negli altri settori la guardia resta (lotto 3A, Task 10).

Budget: kit con rimanenze 1.000.000 (600 giorni sui 600.000 di ricavi), crescita ricavi 10%. Numeri dello snapshot
`452112d`: settore 1 com'e' oggi; settore 6 misurato con `dio_days` 600 esplicito, che e' il bersaglio. Il settore 5
segue la stessa regola del 6: il motore budget non legge il settore in nessun altro punto.
Infrannuale: rimanenze di riferimento 150.000 su 100.000 di materiali (rapporto 1,5), parziale 140.000.
"""
from decimal import Decimal as D

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.services import assumptions_service, forecast_preview_service
from calculations.intra_year_engine import IntraYearEngine
from database.db import Base
from database.models import (BalanceSheet, BudgetAssumptions, BudgetScenario, Company, FinancialYear, ForecastYear,
                             IncomeStatement)
from tests.e2e_kit import memory_sessions, read_forecast_maps, seed_base_year


def _budget(settore):
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=f"magazzino-{settore}")
            db.query(Company).filter(Company.id == company_id).one().sector = settore
            fy = db.query(FinancialYear).filter(FinancialYear.company_id == company_id).one()
            b = db.query(BalanceSheet).filter(BalanceSheet.financial_year_id == fy.id).one()
            b.sp05_rimanenze = D("1000000.00")
            b.sp05a_materie_prime = D("1000000.00")
            b.sp12_riserve += D("950000.00")
            b.sp12e_altre_riserve += D("950000.00")
            db.commit()
            sc = BudgetScenario(company_id=company_id, name="magazzino", base_year=2026, scenario_type="budget")
            db.add(sc)
            db.commit()
            righe = [{"forecast_year": anno, "revenue_growth_pct": 10, "tax_rate": 27.9} for anno in (2027, 2028)]
            esito = assumptions_service.bulk_upsert_assumptions(db, sc.id, [dict(r) for r in righe], auto_generate=True)
            assert esito["forecast_generated"] is True, esito["message"]
            anteprima = forecast_preview_service.preview_forecast(db, sc.id, [dict(r) for r in righe])
            dettagli = {a["year"]: a["details"] for a in anteprima["forecast_years"]}
            return {anno: (sp, dettagli[anno]) for anno, sp, _ce in read_forecast_maps(db, sc.id)}
    finally:
        engine.dispose()


@pytest.mark.parametrize("settore", [5, 6])
def test_immobiliare_ed_edilizia_scalano_le_rimanenze_coi_ricavi(settore):
    anni = _budget(settore)
    attesi = {2027: ("1100000.00", "44222.22"), 2028: ("1210000.00", "126974.44")}
    fuori = []
    for anno, (rimanenze, cassa) in attesi.items():
        sp, det = anni[anno]
        if sp["sp05_rimanenze"] != D(rimanenze) or sp["sp09_disponibilita_liquide"] != D(cassa):
            fuori.append(f"{anno}: sp05 {sp['sp05_rimanenze']} (atteso {rimanenze}), sp09 {sp['sp09_disponibilita_liquide']} (atteso {cassa})")
        if "dio" in det["degenerate_turnover_ratio"]:
            fuori.append(f"{anno}: dio dichiarato degenere")
        if D(str(det["dio_applied"])).quantize(D("0.000001")) != D("600"):
            fuori.append(f"{anno}: dio_applied {det['dio_applied']}")
        if det.get("soglia_giorni_magazzino") != {"settore": settore, "giorni_max": None}:
            fuori.append(f"{anno}: soglia dichiarata {det.get('soglia_giorni_magazzino')}")
    assert not fuori, "\n".join(fuori)


def test_negli_altri_settori_la_guardia_resta_com_e():
    anni = _budget(1)
    fuori = []
    for anno, cassa in {2027: "144222.22", 2028: "336974.44"}.items():
        sp, det = anni[anno]
        if sp["sp05_rimanenze"] != D("1000000.00") or sp["sp09_disponibilita_liquide"] != D(cassa):
            fuori.append(f"{anno}: sp05 {sp['sp05_rimanenze']}, sp09 {sp['sp09_disponibilita_liquide']}")
        if det["degenerate_turnover_ratio"] != ["dio"]:
            fuori.append(f"{anno}: degeneri {det['degenerate_turnover_ratio']}")
        soglia = det.get("soglia_giorni_magazzino") or {}
        if soglia.get("settore") != 1 or D(str(soglia.get("giorni_max"))) != D("365"):
            fuori.append(f"{anno}: soglia dichiarata {det.get('soglia_giorni_magazzino')}")
    assert not fuori, "\n".join(fuori)


def _infrannuale(settore):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    azienda = Company(name="Magazzino infra", tax_id="MAGAZZINO-INFRA", sector=settore)
    db.add(azienda)
    db.flush()
    for anno, mesi, stato, conto in (
        (2024, None, dict(sp05_rimanenze=D("150000"), sp05a_materie_prime=D("150000"), sp11_capitale=D("151000"),
                          sp09_disponibilita_liquide=D("1000")), dict(ce05_materie_prime=D("100000"), ce01_ricavi_vendite=D("100000"))),
        (2025, 9, dict(sp05_rimanenze=D("140000"), sp05a_materie_prime=D("140000"), sp11_capitale=D("151000"),
                       sp09_disponibilita_liquide=D("11000")), dict(ce05_materie_prime=D("90000"), ce01_ricavi_vendite=D("90000"))),
    ):
        fy = FinancialYear(company_id=azienda.id, year=anno, period_months=mesi, validation_status="verified", forecastable=True)
        db.add(fy)
        db.flush()
        db.add(BalanceSheet(financial_year_id=fy.id, **stato))
        db.add(IncomeStatement(financial_year_id=fy.id, **conto))
    scenario = BudgetScenario(company_id=azienda.id, name="infra", base_year=2024, scenario_type="infrannuale", period_months=9)
    db.add(scenario)
    db.flush()
    db.add(BudgetAssumptions(scenario_id=scenario.id, forecast_year=2025, tax_rate=D("0"),
                             fixed_materials_percentage=D("0"), fixed_services_percentage=D("0")))
    db.commit()
    esito = IntraYearEngine(db).generate_projection(scenario.id)
    sp = db.query(ForecastYear).filter(ForecastYear.scenario_id == scenario.id).one().balance_sheet
    diagnostici = [d for d in esito["diagnostics"]
                   if d["code"] == "degenerate_turnover_ratio" and d.get("field") == "sp05_rimanenze"]
    return sp.sp05_rimanenze, sp.sp09_disponibilita_liquide, diagnostici


def test_nell_infrannuale_l_edilizia_scala_il_magazzino_e_l_industria_lo_riporta():
    rimanenze, cassa, diagnostici = _infrannuale(6)
    assert (rimanenze, cassa, diagnostici) == (D("150000.00"), D("1000.00"), [])
    rimanenze, cassa, diagnostici = _infrannuale(1)
    assert (rimanenze, cassa) == (D("140000.00"), D("11000.00"))
    assert [d.get("soglia_giorni") for d in diagnostici] == ["365"]
