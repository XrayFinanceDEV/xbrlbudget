"""
Reports API endpoint - AI comments for report sections
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import get_current_user_id
from app.core.ownership import validate_company_owned_by_user
from app.services.analysis_service import get_complete_analysis
from app.services.ai_comments_service import generate_report_comments, get_stored_comments, save_comments

router = APIRouter()


@router.get(
    "/companies/{company_id}/scenarios/{scenario_id}/report/ai-comments",
    summary="Get stored AI report comments",
    description="Returns previously generated AI comments from the database. Fast, no LLM call.",
    responses={
        200: {"description": "Stored AI comments (may be empty if never generated)"},
        404: {"description": "Company or scenario not found"},
    }
)
def get_ai_comments(
    company_id: int,
    scenario_id: int,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Return stored AI comments for 3 report sections."""
    validate_company_owned_by_user(db, company_id, user_id)
    return get_stored_comments(db, scenario_id)


@router.post(
    "/companies/{company_id}/scenarios/{scenario_id}/report/ai-comments",
    summary="Generate AI report comments",
    description="Generate 3 AI comments via Claude Haiku, save to DB, and return them.",
    responses={
        200: {"description": "AI-generated comments (may be empty if no API key)"},
        404: {"description": "Company or scenario not found"},
    }
)
def generate_ai_comments(
    company_id: int,
    scenario_id: int,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Generate AI comments via Haiku, persist to DB, return result."""
    validate_company_owned_by_user(db, company_id, user_id)

    try:
        analysis_data = get_complete_analysis(db, company_id, scenario_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )

    comments = generate_report_comments(analysis_data)
    if comments:
        save_comments(db, scenario_id, comments)
    return comments
