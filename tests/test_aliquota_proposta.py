"""L'aliquota proposta viene dall'ultimo consuntivo depositato, mai da un anno promosso
o da un parziale (commercialista, 2026-09-18)."""
from decimal import Decimal as D

from backend.app.services.aliquota_service import aliquota_proposta
from calculations.projection_common import aliquota_effettiva
from database.models import Company, FinancialYear, IncomeStatement
from tests.e2e_kit import memory_sessions


def _anno(db, cid, year, ricavi, imposte, period_months=None, promosso=None):
    fy = FinancialYear(company_id=cid, year=year, period_months=period_months,
                       promoted_from_scenario_id=promosso)
    db.add(fy); db.flush()
    db.add(IncomeStatement(financial_year_id=fy.id, ce01_ricavi_vendite=D(ricavi), ce20_imposte=D(imposte)))
    db.flush()


def test_aliquota_effettiva():
    from types import SimpleNamespace as NS
    assert aliquota_effettiva(NS(ce01_ricavi_vendite=D("100000"), ce20_imposte=D("25000"))) == D("25")
    assert aliquota_effettiva(NS(ce01_ricavi_vendite=D("100000"), ce20_imposte=D("0"))) is None
    assert aliquota_effettiva(NS(ce01_ricavi_vendite=D("100000"), ce20_imposte=D("70000"))) is None


def test_salta_promossi_e_parziali_e_ripiega_su_27_9():
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            c = Company(name="A", tax_id="X1", sector=1, user_id="u"); db.add(c); db.flush()
            _anno(db, c.id, 2024, "100000", "20000")                  # 20%
            _anno(db, c.id, 2025, "100000", "25000")                  # 25%: l'ultimo depositato
            _anno(db, c.id, 2026, "100000", "40000", promosso=7)      # promosso: si salta
            _anno(db, c.id, 2026, "50000", "1000", period_months=5)   # parziale: si salta
            db.commit()
            assert aliquota_proposta(db, c.id, 2026) == (D("25"), 2025)
            assert aliquota_proposta(db, c.id, 2024) == (D("20"), 2024)
            assert aliquota_proposta(db, c.id, 2023) == (D("27.9"), None)
    finally:
        engine.dispose()


def test_la_rotta_risponde_aliquota_e_anno():
    from backend.app.api.v1.financial_years import get_aliquota_proposta
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            c = Company(name="B", tax_id="X2", sector=1, user_id="u"); db.add(c); db.flush()
            _anno(db, c.id, 2025, "100000", "30925.27")
            db.commit()
            assert get_aliquota_proposta(c.id, 2026, user_id="u", db=db) == {"aliquota": 30.93, "anno": 2025}
    finally:
        engine.dispose()
