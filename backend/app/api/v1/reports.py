"""
Reports API endpoint - AI comments for report sections
"""
from typing import Dict, Optional
from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import get_current_user_id
from app.core.ownership import validate_company_owned_by_user
from app.services.analysis_service import get_complete_analysis
from app.services.ai_comments_service import generate_report_comments, get_stored_comments, save_comments
from app.schemas.final_report import FinalReportModel
from app.services.final_report_service import (
    FinalReportChainConflict, FinalReportNotFound, assemble_final_report,
)
from app.api.v1.budget_scenarios import validate_scenario_belongs_to_company

router = APIRouter()


@router.get(
    "/companies/{company_id}/scenarios/{scenario_id}/final-report",
    response_model=FinalReportModel,
    summary="Get the assembled final report",
)
def get_final_report(
    company_id: int,
    scenario_id: int,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> FinalReportModel:
    validate_company_owned_by_user(db, company_id, user_id)
    try:
        return assemble_final_report(db, company_id, scenario_id)
    except FinalReportNotFound as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    except FinalReportChainConflict as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))


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
    validate_scenario_belongs_to_company(scenario_id, company_id, user_id, db)
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


@router.put(
    "/companies/{company_id}/scenarios/{scenario_id}/report/ai-comments",
    summary="Save user-edited report AI comments",
    description="Persist user edits to report AI comments (no LLM call).",
    responses={
        200: {"description": "Saved comments"},
        404: {"description": "Company or scenario not found"},
    }
)
def save_ai_comments(
    company_id: int,
    scenario_id: int,
    comments: Dict[str, Optional[str]] = Body(...),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Save user-edited AI comments to DB without LLM call."""
    validate_scenario_belongs_to_company(scenario_id, company_id, user_id, db)
    save_comments(db, scenario_id, comments)
    return get_stored_comments(db, scenario_id)
