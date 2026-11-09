"""GET /companies/{id}/years/{year}/income-statement restituisce ce03a (A.4)."""
from decimal import Decimal as D

from backend.app.api.v1 import financial_years
from backend.app.schemas import income_statement as is_schemas
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.db import Base
from database.models import Company, FinancialYear, IncomeStatement


def test_get_income_statement_include_ce03a():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    c = Company(name="A4", tax_id="GETCE03A01", sector=1, user_id="u-ce03a")
    db.add(c); db.flush()
    fy = FinancialYear(company_id=c.id, year=2025, period_months=None)
    db.add(fy); db.flush()
    db.add(IncomeStatement(financial_year_id=fy.id, ce03a_incrementi_immobilizzazioni=D("1234.50")))
    db.commit()
    out = financial_years.get_income_statement(c.id, 2025, user_id="u-ce03a", db=db)
    body = is_schemas.IncomeStatement.model_validate(out).model_dump()
    assert body["ce03a_incrementi_immobilizzazioni"] == D("1234.50")
    assert "ce03a_incrementi_immobilizzazioni" in is_schemas.IncomeStatementUpdate.model_fields
