"""Rettifiche: A.4 (ce03a, incrementi di immobilizzazioni per lavori interni) e' una voce che
PUT /adjustments accetta e la cui guardia vede (Task 5-bis parte 3, backend)."""
from decimal import Decimal as D

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.api.v1 import financial_years
from backend.app.schemas.adjustments import AdjustmentsUpdate
from database.db import Base
from database.models import BalanceSheet, Company, FinancialYear, IncomeStatement

UTENTE = "rettifica-ce03a"


@pytest.fixture
def foglio():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    azienda = Company(name="PROVA A4", tax_id="CE03A0001", sector=1, user_id=UTENTE)
    db.add(azienda); db.flush()
    fy = FinancialYear(company_id=azienda.id, year=2025, period_months=None,
                       validation_status="verified", forecastable=True)
    db.add(fy); db.flush()
    db.add(BalanceSheet(financial_year_id=fy.id, sp03_immob_materiali=D("50000"), sp03b_impianti_macchinari=D("50000"),
                        sp09_disponibilita_liquide=D("50000"),
                        sp11_capitale=D("90000"), sp13_utile_perdita=D("10000")))
    db.add(IncomeStatement(financial_year_id=fy.id, ce01_ricavi_vendite=D("100000"),
                           ce06_servizi=D("90000")))
    db.commit()
    return db, azienda.id


def _salva(db, company_id, bs, ce):
    return financial_years.save_adjustments(
        company_id, 2025, AdjustmentsUpdate(balance_sheet=bs, income_statement=ce, rettifiche_log=[]),
        period_months=None, user_id=UTENTE, db=db)


def test_ce03a_in_partita_doppia_con_sp03_e_accettata_e_persistita(foglio):
    db, cid = foglio
    _salva(db, cid, {"sp03_immob_materiali": D("70000"), "sp03b_impianti_macchinari": D("70000"),
                 "sp13_utile_perdita": D("30000")},
           {"ce03a_incrementi_immobilizzazioni": D("20000")})
    fy = db.query(FinancialYear).one()
    assert fy.income_statement.ce03a_incrementi_immobilizzazioni == D("20000")
    assert fy.balance_sheet.sp03_immob_materiali == D("70000")


def test_ce03a_senza_contropartita_sposta_il_risultato_ed_e_rifiutata(foglio):
    """La guardia legge ce03a nel risultato del CE: A.4 da sola apre un divario CE-SP13."""
    db, cid = foglio
    with pytest.raises(HTTPException) as esc:
        _salva(db, cid, {}, {"ce03a_incrementi_immobilizzazioni": D("20000")})
    assert esc.value.status_code == 400
