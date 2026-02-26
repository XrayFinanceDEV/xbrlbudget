"""
Reports API endpoint - PDF report generation and AI comments
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import get_current_user_id
from app.core.ownership import validate_company_owned_by_user
from app.services.analysis_service import get_complete_analysis
from app.services.ai_comments_service import generate_report_comments, get_stored_comments, save_comments

router = APIRouter()


@router.get(
    "/companies/{company_id}/scenarios/{scenario_id}/report/pdf",
    summary="Download PDF financial analysis report",
    description="""
    Generate and download a comprehensive PDF financial analysis report.

    The report includes:
    - Cover page with company data
    - Dashboard with Altman, FGPMI, and EM-Score gauges
    - Asset/liability composition charts
    - Income margin analysis with waterfall chart
    - Structural analysis (MS, CCN, MT)
    - All financial ratio categories with charts and tables
    - Altman Z-Score detail with components
    - EM-Score rating mapping
    - FGPMI Rating detail with indicators
    - Break Even Point analysis
    - Cash flow indices
    - Appendices: Balance Sheet, Income Statement, Reclassified BS, Cash Flow Statement
    - Notes and methodology

    **Returns:** PDF file (application/pdf)
    """,
    response_class=StreamingResponse,
    responses={
        200: {
            "content": {"application/pdf": {}},
            "description": "PDF report file"
        },
        404: {"description": "Company or scenario not found"},
        500: {"description": "Error generating report"},
    }
)
def download_pdf_report(
    company_id: int,
    scenario_id: int,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Generate and stream a PDF financial analysis report."""
    validate_company_owned_by_user(db, company_id, user_id)
    from pdf_service.report_generator import generate_report_data
    from pdf_service.pdf_renderer import PDFReportRenderer

    try:
        # Generate all data and charts
        report_data = generate_report_data(db, company_id, scenario_id)

        # Render PDF
        renderer = PDFReportRenderer(report_data)
        pdf_buffer = renderer.render()

        # Build filename
        company_name = report_data.company.name.replace(" ", "_")
        years = [yd.year for yd in report_data.years]
        year_range = f"{years[0]}-{years[-1]}" if len(years) > 1 else str(years[0])
        filename = f"{company_name}_Analisi_{year_range}.pdf"

        return StreamingResponse(
            pdf_buffer,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating PDF report: {str(e)}"
        )


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
