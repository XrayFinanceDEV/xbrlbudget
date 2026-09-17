"""
Reports API endpoint - AI comments for report sections
"""
from typing import Annotated, Dict, Optional
from urllib.parse import quote

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import get_current_user_id
from app.core.ownership import validate_company_owned_by_user
from app.services.analysis_service import get_complete_analysis
from app.services.ai_comments_service import (
    NarrativeGenerationError, generate_final_report_narrative, generate_report_comments, get_stored_comments,
    save_comments, save_generated_narrative_blocks, save_user_narrative_blocks,
)
from app.schemas.final_report import FinalReportModel, NarrativeSaveRequest
from app.schemas.final_report_pdf import FinalReportPdfRequest
from app.core.render_panics import NON_ENTRA
from app.renderers.typst.runtime import (
    RendererBusy, RendererCompileError, RendererError, RendererTimeout, RendererUnavailable,
)
from app.services import final_report_pdf_service as pdf_service
from app.services.final_report_pdf_service import EditorialPlanRequired, FinalNotReady
from app.schemas.final_report_v2 import FinalReportModelV2
from app.services.final_report_service import (
    FinalReportChainConflict, FinalReportNotFound, FinalReportPeriodUnavailable, assemble_final_report,
    narrative_source_hash,
)
from app.api.v1.budget_scenarios import validate_scenario_belongs_to_company

router = APIRouter()


@router.get(
    "/companies/{company_id}/scenarios/{scenario_id}/final-report",
    response_model=FinalReportModelV2 | FinalReportModel,
    summary="Get the assembled final report",
)
def get_final_report(
    company_id: int,
    scenario_id: int,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    schema_version: Annotated[int, Query(ge=1, le=2)] = 1,
) -> FinalReportModelV2 | FinalReportModel:
    validate_company_owned_by_user(db, company_id, user_id)
    try:
        return assemble_final_report(db, company_id, scenario_id, schema_version=schema_version)
    except FinalReportNotFound as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    except (FinalReportChainConflict, FinalReportPeriodUnavailable) as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))


def _assemble_or_http(db: Session, company_id: int, scenario_id: int) -> FinalReportModel:
    try:
        return assemble_final_report(db, company_id, scenario_id)
    except FinalReportNotFound as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    except FinalReportChainConflict as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))


@router.post(
    "/companies/{company_id}/scenarios/{scenario_id}/final-report/narrative/generate",
    response_model=FinalReportModel,
    summary="Explicitly generate unified final-report narrative",
)
def generate_final_report_narrative_endpoint(
    company_id: int,
    scenario_id: int,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> FinalReportModel:
    """Call the LLM only on demand, using the canonical server report model."""
    validate_scenario_belongs_to_company(scenario_id, company_id, user_id, db)
    report = _assemble_or_http(db, company_id, scenario_id)
    try:
        generated = generate_final_report_narrative(report)
    except NarrativeGenerationError as error:
        # Mai un 200 su una relazione che non c'è: la pagina lo leggerebbe come un successo.
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error
    if generated:
        # Normalize the canonical report to economic provenance so filling
        # missing prose cannot immediately make its own output stale.
        save_generated_narrative_blocks(db, scenario_id, generated, narrative_source_hash(report))
    return _assemble_or_http(db, company_id, scenario_id)


@router.put(
    "/companies/{company_id}/scenarios/{scenario_id}/final-report/narrative",
    response_model=FinalReportModel,
    summary="Save user-authored unified final-report narrative blocks",
)
def save_final_report_narrative(
    company_id: int,
    scenario_id: int,
    request: NarrativeSaveRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> FinalReportModel:
    """Persist manual edits separately from generation and mark them as user text."""
    validate_scenario_belongs_to_company(scenario_id, company_id, user_id, db)
    report = _assemble_or_http(db, company_id, scenario_id)
    save_user_narrative_blocks(
        db, scenario_id, {block.id: block.text for block in request.blocks}, narrative_source_hash(report),
    )
    return _assemble_or_http(db, company_id, scenario_id)


@router.post(
    "/companies/{company_id}/scenarios/{scenario_id}/final-report/pdf",
    response_class=Response,
    summary="Download the final report dossier as PDF",
    responses={
        404: {"description": "Azienda o scenario non di questo utente"},
        409: {"description": "Piano editoriale mancante o non attuale; «final» su report non ready"},
        422: {"description": "Un contenuto del dossier non entra nella pagina"},
        500: {"description": "PDF invalido o errore interno del renderer"},
        503: {"description": "Renderer occupato o non disponibile"},
        504: {"description": "Tempo massimo di impaginazione superato"},
    },
)
def download_final_report_pdf(
    company_id: int,
    scenario_id: int,
    request: FinalReportPdfRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> Response:
    """Serve il PDF del dossier congelato: nessuna AI, nessun forecast, nessuna scrittura."""
    validate_scenario_belongs_to_company(scenario_id, company_id, user_id, db)
    try:
        result = pdf_service.render_pdf(
            db, company_id, scenario_id,
            document_state=request.document_state, grayscale=request.grayscale,
        )
    except FinalReportNotFound as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from None
    except (FinalReportChainConflict, FinalReportPeriodUnavailable, EditorialPlanRequired, FinalNotReady) as error:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from None
    except RendererCompileError as error:
        db.rollback()
        # Un contenuto che non entra non è un renderer guasto: lo si dice, con che cosa non entra.
        contenuti = [NON_ENTRA[code] for code in error.panics if code in NON_ENTRA]
        if contenuti:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Il report non si impagina: " + "; ".join(dict.fromkeys(contenuti)) + ".",
            ) from None
        raise HTTPException(status_code=500, detail="Compilazione del report non riuscita.") from None
    except RendererTimeout:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                           detail="Tempo massimo di impaginazione del report superato. Riprovare più tardi.") from None
    except RendererBusy:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                           detail="Generazione documenti temporaneamente occupata. Riprovare tra poco.") from None
    except RendererUnavailable:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                           detail="Compilatore del report non disponibile. Riprovare più tardi.") from None
    except RendererError as error:
        # RendererInvalidPdf, RendererInputError e qualunque categoria nuova: errore interno, 500.
        db.rollback()
        raise HTTPException(status_code=500, detail=error.message) from None
    filename = pdf_service.artifact_filename(result.report)
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"; filename*=UTF-8\'\'{quote(filename, encoding="utf-8")}',
        "ETag": f'"{result.etag}"',
        "X-Report-Model-Hash": result.rendered.model_hash,
        "X-Report-Template-Version": result.rendered.template_version,
        "X-Report-Compiler-Version": result.rendered.compiler_version,
        "Cache-Control": "no-store",
    }
    return Response(content=result.rendered.data, media_type="application/pdf", headers=headers)


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
    validate_scenario_belongs_to_company(scenario_id, company_id, user_id, db)

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


from app.api.v1.editorial_notes import router as editorial_router
router.include_router(editorial_router)
