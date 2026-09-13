"""Server-owned provenance rules for budget scenario creation."""
from __future__ import annotations

from decimal import Decimal
from typing import NamedTuple, Optional

from fastapi import HTTPException, status
from sqlalchemy import Numeric
from sqlalchemy.orm import Session

from database.models import BalanceSheet, BudgetScenario, FinancialYear, IncomeStatement


class ScenarioProvenance(NamedTuple):
    """The only lineage values that may be persisted for a new scenario."""

    workflow_type: str
    source_scenario_id: Optional[int]


def normalize_scenario_name(name: str) -> str:
    """Use one conservative identity for both insertion and idempotent lookup."""
    return " ".join(name.split()).casefold()


def derive_scenario_provenance(
    db: Session,
    *,
    company_id: int,
    base_year: int,
    scenario_type: str,
    period_months: Optional[int],
    workflow_intent: Optional[str],
) -> ScenarioProvenance:
    """Derive scenario lineage from trusted accounting records, never the client."""
    if scenario_type == "infrannuale":
        return ScenarioProvenance("infrannuale", None)

    financial_year = _full_year(db, company_id, base_year)
    if workflow_intent == "startup":
        if not _is_startup_opening(financial_year):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="L'intento startup richiede un bilancio di apertura con sola cassa e capitale sociale",
            )
        return ScenarioProvenance("startup", None)

    if (
        financial_year
        and financial_year.workflow_origin == "promoted_projection"
        and financial_year.promoted_from_scenario_id is not None
    ):
        source = db.get(BudgetScenario, financial_year.promoted_from_scenario_id)
        if source is None or source.company_id != company_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lo scenario infrannuale da cui proviene l'esercizio non è disponibile per questa azienda",
            )
        if (
            source.scenario_type == "infrannuale"
            and source.period_months is not None
            and 1 <= source.period_months <= 11
            and source.base_year + 1 == base_year
        ):
            return ScenarioProvenance("infrannuale", source.id)

    return ScenarioProvenance("bilancio", None)


def find_active_reusable_scenario(
    db: Session,
    *,
    company_id: int,
    base_year: int,
    name: str,
    provenance: ScenarioProvenance,
) -> Optional[BudgetScenario]:
    """Return only an active scenario with the exact derived lineage."""
    normalized_name = normalize_scenario_name(name)
    candidates = db.query(BudgetScenario).filter(
        BudgetScenario.company_id == company_id,
        BudgetScenario.base_year == base_year,
        BudgetScenario.is_active == 1,
        BudgetScenario.workflow_type == provenance.workflow_type,
        BudgetScenario.source_scenario_id == provenance.source_scenario_id,
    ).all()
    return next(
        (candidate for candidate in candidates if normalize_scenario_name(candidate.name) == normalized_name),
        None,
    )


def _full_year(db: Session, company_id: int, year: int) -> Optional[FinancialYear]:
    return db.query(FinancialYear).filter(
        FinancialYear.company_id == company_id,
        FinancialYear.year == year,
        (FinancialYear.period_months == None) | (FinancialYear.period_months == 12),
    ).first()


def _is_startup_opening(financial_year: Optional[FinancialYear]) -> bool:
    """Verify the deliberately tiny opening balance used by the startup flow."""
    if not financial_year or not financial_year.balance_sheet or not financial_year.income_statement:
        return False
    balance_sheet = financial_year.balance_sheet
    cash = _decimal(balance_sheet.sp09_disponibilita_liquide)
    capital = _decimal(balance_sheet.sp11_capitale)
    if cash <= 0 or cash != capital:
        return False
    if not _only_zero_statement_values(
        balance_sheet, BalanceSheet, {"id", "financial_year_id", "sp09_disponibilita_liquide", "sp11_capitale"}
    ):
        return False
    return _only_zero_statement_values(
        financial_year.income_statement, IncomeStatement, {"id", "financial_year_id"}
    )


def _only_zero_statement_values(statement, model, excluded: set[str]) -> bool:
    for column in model.__table__.columns:
        if column.name in excluded or not isinstance(column.type, Numeric):
            continue
        if _decimal(getattr(statement, column.name)) != 0:
            return False
    return True


def _decimal(value) -> Decimal:
    return Decimal(str(value or 0))
