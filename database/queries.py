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


def get_fy_full(db: Session, company_id: int, year: int):
    """Return only a full-year record (``period_months`` NULL/12).

    This strict helper is used where a partial record would change the meaning of
    a calculation.  ``get_fy_prefer_full`` remains available to legacy display
    callers that explicitly accept an arbitrary fallback.
    """
    return db.query(FinancialYear).filter(
        FinancialYear.company_id == company_id,
        FinancialYear.year == year,
        (FinancialYear.period_months == None) | (FinancialYear.period_months == 12),
    ).first()


def get_fy_partial(
    db: Session,
    company_id: int,
    year: int,
    period_months: int,
):
    """Return the *exact* requested partial-year record.

    A company may have several imports for the same calendar year (for example a
    six-month and a nine-month situation).  Picking an arbitrary partial record
    makes the annualisation factor unrelated to the data being projected.  Full
    years (``NULL``/12) are deliberately not a fallback here.
    """
    if isinstance(period_months, bool) or not isinstance(period_months, int):
        raise ValueError("period_months must be an integer between 1 and 11")
    if not 1 <= period_months <= 11:
        raise ValueError("period_months must be between 1 and 11 for a partial year")

    return db.query(FinancialYear).filter(
        FinancialYear.company_id == company_id,
        FinancialYear.year == year,
        FinancialYear.period_months == period_months,
    ).first()
