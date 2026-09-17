"""Explicit page preparation and revision-protected commentary actions."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import get_current_user_id
from app.core.database import get_db
from app.core.render_panics import NON_ENTRA as _NON_ENTRA
from app.api.v1.budget_scenarios import validate_scenario_belongs_to_company
from app.schemas.editorial_notes import (
    EditorialSession, GenerateEditorialNotesRequest, PrepareEditorialRequest, SaveEditorialNotesRequest,
)
from app.services import editorial_notes_service as service
from app.services.final_report_service import FinalReportChainConflict, FinalReportNotFound, FinalReportPeriodUnavailable
from app.renderers.typst.runtime import RendererCompileError, RendererInputError, RendererTimeout, RendererUnavailable

router = APIRouter()

_PATH = "/companies/{company_id}/scenarios/{scenario_id}/final-report/editorial"


def _run(action, db, company_id, scenario_id, request=None):
    try:
        return action(db, company_id, scenario_id) if request is None else action(db, company_id, scenario_id, request)
    except FinalReportNotFound as error:
        raise HTTPException(404, str(error)) from None
    except (FinalReportChainConflict, FinalReportPeriodUnavailable, service.EditorialConflict) as error:
        db.rollback()
        raise HTTPException(409, str(error)) from None
    except service.EditorialInputError as error:
        db.rollback()
        raise HTTPException(422, str(error)) from None
    except RendererInputError:
        db.rollback()
        raise HTTPException(422, "Il contenuto supera i limiti del report.") from None
    except RendererCompileError as error:
        db.rollback()
        # Un contenuto che non entra non è un renderer guasto: lo si dice, con che cosa non entra.
        contenuti = [_NON_ENTRA[code] for code in error.panics if code in _NON_ENTRA]
        if contenuti:
            raise HTTPException(422, "Il report non si impagina: " + "; ".join(dict.fromkeys(contenuti)) + ".") from None
        dettaglio = f" (codice: {', '.join(error.panics)})" if error.panics else ""
        raise HTTPException(503, f"Compilazione del report non riuscita{dettaglio}. Riprovare più tardi.") from None
    except (RendererUnavailable, RendererTimeout):
        db.rollback()
        raise HTTPException(503, "La preparazione del report non è disponibile. Riprovare dopo aver verificato il renderer.") from None


@router.get(_PATH, response_model=EditorialSession)
def get_editorial_session(company_id: int, scenario_id: int, user_id: str = Depends(get_current_user_id), db: Session = Depends(get_db)):
    validate_scenario_belongs_to_company(scenario_id, company_id, user_id, db)
    return _run(service.session, db, company_id, scenario_id)


@router.post(_PATH + "/prepare", response_model=EditorialSession)
def prepare_editorial_session(company_id: int, scenario_id: int, request: PrepareEditorialRequest, user_id: str = Depends(get_current_user_id), db: Session = Depends(get_db)):
    validate_scenario_belongs_to_company(scenario_id, company_id, user_id, db)
    return _run(service.prepare, db, company_id, scenario_id, request)


@router.put(_PATH + "/notes", response_model=EditorialSession)
def save_editorial_notes(company_id: int, scenario_id: int, request: SaveEditorialNotesRequest, user_id: str = Depends(get_current_user_id), db: Session = Depends(get_db)):
    validate_scenario_belongs_to_company(scenario_id, company_id, user_id, db)
    return _run(service.save, db, company_id, scenario_id, request)


@router.post(_PATH + "/generate", response_model=EditorialSession)
def generate_editorial_notes(company_id: int, scenario_id: int, request: GenerateEditorialNotesRequest, user_id: str = Depends(get_current_user_id), db: Session = Depends(get_db)):
    validate_scenario_belongs_to_company(scenario_id, company_id, user_id, db)
    return _run(service.generate, db, company_id, scenario_id, request)
