"""
Shared FinancialYear lookup helpers.

When both a partial-year (period_months IS NOT NULL) and a full-year
(period_months IS NULL) record exist for the same company+year, these
helpers ensure every caller gets the right one.
"""
from sqlalchemy.orm import Session
from database.models import FinancialYear


def get_fy_prefer_full(db: Session, company_id: int, year: int):
    """Return the full-year record if it exists, otherwise any record.

    Per the FinancialYear convention NULL/12 = full year, 1-11 = partial, so
    both NULL and 12 count as a full-year record here.
    """
    fy = db.query(FinancialYear).filter(
        FinancialYear.company_id == company_id,
        FinancialYear.year == year,
        (FinancialYear.period_months == None) | (FinancialYear.period_months == 12),
    ).first()
    if fy:
        return fy
    return db.query(FinancialYear).filter(
        FinancialYear.company_id == company_id,
        FinancialYear.year == year,
    ).first()


def get_fy_partial(db: Session, company_id: int, year: int):
    """Return only the partial-year record (period_months 1-11).

    A period_months of 12 is a full year, not a partial, so it is excluded.
    """
    return db.query(FinancialYear).filter(
        FinancialYear.company_id == company_id,
        FinancialYear.year == year,
        FinancialYear.period_months.isnot(None),
        FinancialYear.period_months != 12,
    ).first()
