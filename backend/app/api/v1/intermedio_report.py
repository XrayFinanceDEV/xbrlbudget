"""PDF del report intermedio dell'infrannuale (situazione + crisi d'impresa).

Sostituisce la stampa del browser della tab Stampa: la tab resta come
anteprima a schermo, il documento che si consegna e' questo.
"""
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.api.v1.budget_scenarios import validate_scenario_belongs_to_company
from app.core.auth import get_current_user_id
from app.core.database import get_db
from app.core.render_panics import NON_ENTRA
from app.renderers.typst.runtime import (
    RendererBusy, RendererCompileError, RendererError, RendererTimeout, RendererUnavailable,
)
from app.schemas.infrannuale_pdf import InfrannualePdfRequest
from app.services import infrannuale_pdf_service
from app.services.intermedio_report_service import nomi_file, render_intermedio_pdf

router = APIRouter()


class IntermedioPdfRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    #: False quando l'utente ha chiuso, nella Stampa, l'avviso sui commenti stantii.
    avviso_commenti: bool = True


@router.post(
    "/companies/{company_id}/scenarios/{scenario_id}/infrannuale/report/pdf",
    response_class=Response,
    summary="Scarica il report intermedio dell'infrannuale in PDF",
    responses={
        400: {"description": "Scenario non infrannuale, o bilanci del periodo mancanti"},
        404: {"description": "Azienda o scenario non di questo utente"},
        422: {"description": "Un contenuto del report non entra nella pagina"},
        500: {"description": "PDF invalido o errore interno del renderer"},
        503: {"description": "Renderer occupato o non disponibile"},
        504: {"description": "Tempo massimo di impaginazione superato"},
    },
)
def download_intermedio_pdf(
    company_id: int,
    scenario_id: int,
    request: IntermedioPdfRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> Response:
    scenario = validate_scenario_belongs_to_company(scenario_id, company_id, user_id, db)
    if scenario.scenario_type != "infrannuale":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Il report intermedio è disponibile solo per gli scenari infrannuali.")
    try:
        model, pdf = render_intermedio_pdf(db, scenario, avviso_commenti=request.avviso_commenti)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from None
    except RendererCompileError as error:
        contenuti = [NON_ENTRA[code] for code in error.panics if code in NON_ENTRA]
        if "intermedio-page-overflow" in error.panics:
            contenuti.append("una pagina del report supera il foglio (un commento troppo lungo?)")
        if contenuti:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="Il report non si impagina: " + "; ".join(dict.fromkeys(contenuti)) + ".") from None
        raise HTTPException(status_code=500, detail="Compilazione del report non riuscita.") from None
    except RendererTimeout:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                            detail="Tempo massimo di impaginazione del report superato. Riprovare più tardi.") from None
    except RendererBusy:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Generazione documenti temporaneamente occupata. Riprovare tra poco.") from None
    except RendererUnavailable:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Compilatore del report non disponibile. Riprovare più tardi.") from None
    except RendererError as error:
        raise HTTPException(status_code=500, detail=error.message) from None
    filename, ascii_name = nomi_file(model)
    headers = {
        "Content-Disposition": f'attachment; filename="{ascii_name}"; '
                               f"filename*=UTF-8''{quote(filename, safe='', encoding='utf-8')}",
        "X-Report-Template-Version": pdf.template_version,
        "X-Report-Compiler-Version": pdf.compiler_version,
        "Cache-Control": "no-store",
    }
    return Response(content=pdf.data, media_type="application/pdf", headers=headers)


@router.post(
    "/companies/{company_id}/scenarios/{scenario_id}/infrannuale/pdf",
    response_class=Response,
    summary="Scarica il report infrannuale (ReportLab) in PDF",
    responses={
        400: {"description": "Scenario non infrannuale, o bilanci del periodo mancanti"},
        404: {"description": "Azienda o scenario non di questo utente"},
    },
)
def download_infrannuale_pdf(
    company_id: int,
    scenario_id: int,
    request: InfrannualePdfRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> Response:
    """Il report infrannuale che la Stampa consegna: numeri del motore, testi a regole, nessuna AI, nessuna scrittura."""
    scenario = validate_scenario_belongs_to_company(scenario_id, company_id, user_id, db)
    if scenario.scenario_type != "infrannuale":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Il report infrannuale è disponibile solo per gli scenari infrannuali.")
    try:
        result = infrannuale_pdf_service.render(db, scenario)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from None
    headers = {
        "Content-Disposition": (f'attachment; filename="{result.ascii_filename}"; '
                                f"filename*=UTF-8''{quote(result.filename, safe='', encoding='utf-8')}"),
        "ETag": f'"{result.etag}"',
        "Cache-Control": "no-store",
    }
    return Response(content=result.data, media_type="application/pdf", headers=headers)


@router.post(
    "/companies/{company_id}/scenarios/{scenario_id}/infrannuale/docx",
    response_class=Response,
    summary="Scarica il report infrannuale in Word",
    responses={
        400: {"description": "Scenario non infrannuale, o bilanci del periodo mancanti"},
        404: {"description": "Azienda o scenario non di questo utente"},
    },
)
def download_infrannuale_docx(
    company_id: int,
    scenario_id: int,
    request: InfrannualePdfRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> Response:
    """Lo stesso report in Word, per correggere i testi prima di consegnarlo: stessi controlli della PDF."""
    scenario = validate_scenario_belongs_to_company(scenario_id, company_id, user_id, db)
    if scenario.scenario_type != "infrannuale":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Il report infrannuale è disponibile solo per gli scenari infrannuali.")
    try:
        result = infrannuale_pdf_service.render_docx(db, scenario)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from None
    headers = {
        "Content-Disposition": (f'attachment; filename="{result.ascii_filename}"; '
                                f"filename*=UTF-8''{quote(result.filename, safe='', encoding='utf-8')}"),
        "ETag": f'"{result.etag}"',
        "Cache-Control": "no-store",
    }
    return Response(content=result.data, media_type=infrannuale_pdf_service.DOCX_MEDIA_TYPE, headers=headers)
