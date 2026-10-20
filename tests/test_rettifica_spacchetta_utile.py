"""Rettifiche: lo spacchettamento dell'utile importato passa la guardia del server.

Un bilancio di verifica che non ha ancora girato a patrimonio netto il risultato dell'anno
prima stampa un solo "utile" (Unicarton 31/08/2026: SP 241.711,59, CE 68.247,80). Il
frontend riscrive sp13 dal CE a ogni conferma: senza portare la differenza negli utili
portati a nuovo NELLO STESSO salvataggio, lo scarto CE-SP diventa sbilancio SP e la guardia
di PUT /adjustments rifiuta la rettifica (era il caso dell'utente: «la riga utile e'
bloccata»). Il pulsante «Spacchetta utile» (frontend/lib/pratica-quadratura.ts,
``risultatoPrecedente``) manda proprio la coppia accettata qui.

Run: python -m pytest tests/test_rettifica_spacchetta_utile.py -v
"""
from decimal import Decimal as D

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.api.v1 import financial_years
from backend.app.schemas.adjustments import AdjustmentsUpdate
from database.db import Base
from database.models import BalanceSheet, Company, FinancialYear, IncomeStatement

UTENTE = "spacchetta-utile"


@pytest.fixture
def verifica():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    azienda = Company(name="UNICARTON PROVA", tax_id="SPACCHETTA01", sector=1, user_id=UTENTE)
    db.add(azienda); db.flush()
    fy = FinancialYear(company_id=azienda.id, year=2026, period_months=8,
                       validation_status="verified", forecastable=True)
    db.add(fy); db.flush()
    # Lo SP chiude con l'utile come differenza: 110.000 di capitale + 241.711,59.
    db.add(BalanceSheet(financial_year_id=fy.id, sp09_disponibilita_liquide=D("351711.59"),
                        sp11_capitale=D("110000"), sp13_utile_perdita=D("241711.59")))
    # Il CE del periodo: 68.247,80.
    db.add(IncomeStatement(financial_year_id=fy.id, ce01_ricavi_vendite=D("100000"),
                           ce06_servizi=D("31752.20")))
    db.commit()
    return db, azienda.id


def _salva(db, company_id, bs):
    return financial_years.save_adjustments(
        company_id, 2026,
        AdjustmentsUpdate(balance_sheet=bs, income_statement={}, rettifiche_log=[]),
        period_months=8, user_id=UTENTE, db=db,
    )


def test_spacchettare_l_utile_negli_utili_portati_a_nuovo_e_accettato(verifica):
    db, company_id = verifica
    _salva(db, company_id, {
        "sp13_utile_perdita": D("68247.80"),
        "sp12g_utili_perdite_portati": D("173463.79"),
        "sp12_riserve": D("173463.79"),
    })
    fy = db.query(FinancialYear).one()
    assert fy.balance_sheet.sp12g_utili_perdite_portati == D("173463.79")
    assert fy.balance_sheet.sp13_utile_perdita == D("68247.80")


def test_riportare_l_utile_al_ce_senza_spacchettare_e_rifiutato(verifica):
    """E' cio' che fa qualunque altra rettifica su questo foglio: sp13 torna al CE e i
    173.463,79 diventano sbilancio. Il rifiuto e' giusto; la via d'uscita e' il pulsante."""
    db, company_id = verifica
    with pytest.raises(HTTPException) as esc:
        _salva(db, company_id, {"sp13_utile_perdita": D("68247.80")})
    assert esc.value.status_code == 400
    assert "Attivo−Passivo" in esc.value.detail
