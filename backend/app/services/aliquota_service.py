"""L'aliquota fiscale proposta: quella effettiva dell'ultimo bilancio annuale depositato.

Commercialista, 2026-09-18: l'aliquota non si prende dall'ultimo infrannuale (un anno
promosso e' una proiezione, e la sua aliquota e' quella che la proiezione ha usato) ma
dall'ultimo consuntivo depositato. E' una PROPOSTA: il wizard la mostra e l'utente la
tiene, mette 27,9 o altro; il motore applica `tax_rate` cosi' com'e'.

«Depositato» = `FinancialYear` annuale (`period_months` NULL o 12) che non nasce da un
promote (`promoted_from_scenario_id` NULL), di anno non successivo a quello dato.
Il frontend porta la stessa regola in `frontend/lib/budget-tax-rate.ts`.
"""
from decimal import Decimal
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from calculations.projection_common import ALIQUOTA_RIPIEGO, aliquota_effettiva
from database.models import FinancialYear


def ultimo_consuntivo_depositato(db: Session, company_id: int, anno_max: int) -> Optional[FinancialYear]:
    return (
        db.query(FinancialYear)
        .filter(
            FinancialYear.company_id == company_id,
            FinancialYear.year <= anno_max,
            (FinancialYear.period_months == None) | (FinancialYear.period_months == 12),  # noqa: E711
            FinancialYear.promoted_from_scenario_id == None,  # noqa: E711
        )
        .order_by(FinancialYear.year.desc())
        .first()
    )


def aliquota_proposta(db: Session, company_id: int, anno_max: int) -> Tuple[Decimal, Optional[int]]:
    """`(aliquota %, anno del consuntivo)`; `(27,9, None)` quando non e' derivabile."""
    fy = ultimo_consuntivo_depositato(db, company_id, anno_max)
    if fy is not None and fy.income_statement is not None:
        rate = aliquota_effettiva(fy.income_statement)
        if rate is not None:
            return rate, fy.year
    return ALIQUOTA_RIPIEGO, None
