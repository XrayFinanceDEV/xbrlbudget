"""
Company ownership helpers for user-scoped queries.
"""
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from database.models import Company
from app.core.config import settings


def validate_company_owned_by_user(
    db: Session, company_id: int, user_id: str
) -> Company:
    """
    Validate that company exists AND belongs to the current user.
    Returns 404 if not found or not owned (don't leak ownership info).
    """
    company = db.query(Company).filter(
        Company.id == company_id,
        Company.user_id == user_id,
    ).first()

    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company with id {company_id} not found",
        )
    return company


def check_company_limit(db: Session, user_id: str) -> None:
    """
    Enforce max companies per user.
    Raises 400 if limit reached.
    """
    count = db.query(Company).filter(Company.user_id == user_id).count()
    if count >= settings.MAX_COMPANIES_PER_USER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Limite aziende raggiunto ({settings.MAX_COMPANIES_PER_USER}). "
                   f"Elimina le aziende non utilizzate prima di crearne di nuove.",
        )
