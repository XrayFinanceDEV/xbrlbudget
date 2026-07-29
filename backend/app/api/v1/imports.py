"""
API endpoints for data import (XBRL, CSV, and PDF)
"""
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Query
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session
from typing import Optional
import tempfile
import os
import logging
import traceback

logger = logging.getLogger(__name__)

from app.core.database import get_db
from app.core.auth import CurrentUser, get_current_user, get_current_user_id
from app.core.config import settings
from app.core.ownership import validate_company_owned_by_user, check_company_limit
from app.schemas.imports import XBRLImportResponse, CSVImportResponse, ImportError
from app.services.upload_tracker import save_upload, mark_success, mark_error
from importers.xbrl_parser_enhanced import import_xbrl_file_enhanced, XBRLParseError
from importers.csv_importer import import_csv_file
from importers.pdf_importer import import_pdf_balance_sheet, PDFImportError

router = APIRouter()

MAX_PDF_SIZE = 50 * 1024 * 1024  # 50MB


async def _read_and_validate_pdf(
    file: UploadFile,
    company_id: Optional[int],
    create_company: bool,
    company_name: Optional[str],
) -> bytes:
    """Shared PDF upload validation for /import/pdf and /import/pdf-ocr.

    Kept in one place so the two routes cannot diverge. Raises HTTPException(400)
    on any invalid input; returns the raw bytes on success.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    file_ext = file.filename.lower().split('.')[-1]
    if file_ext != 'pdf':
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type: .{file_ext}. Only .pdf files are supported.",
        )

    try:
        content = await file.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {str(e)}")

    if len(content) > MAX_PDF_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size is 50MB, received {len(content) / 1024 / 1024:.1f}MB",
        )
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="File is empty")
    if not content.startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="Invalid PDF: missing %PDF- signature")

    if not company_id and (not create_company or not company_name):
        raise HTTPException(
            status_code=400,
            detail="Either company_id or (create_company=True and company_name) must be provided",
        )
    return content


@router.post(
    "/import/xbrl",
    response_model=XBRLImportResponse,
    summary="Import XBRL Financial Data",
    description="""
    Upload and import an Italian GAAP XBRL file.

    Supports taxonomies: 2011-01-04, 2014-11-17, 2015-12-14, 2016-11-14, 2017-07-06, 2018-11-04

    The file will be parsed and financial data (Balance Sheet and Income Statement) will be
    imported into the database. If no company_id is provided and create_company is True,
    a new company will be created from the XBRL entity information.
    """
)
async def upload_xbrl(
    file: UploadFile = File(..., description="XBRL file to import (.xbrl or .xml)"),
    company_id: Optional[int] = Query(None, description="Existing company ID (optional)"),
    create_company: bool = Query(True, description="Create company if not exists"),
    sector: Optional[int] = Query(None, ge=1, le=6, description="Company sector (1-6, used when creating new company)"),
    period_months: Optional[int] = Query(None, ge=1, le=12, description="Months in partial year (1-12). NULL = full 12-month year"),
    user_id: str = Depends(get_current_user_id),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Import XBRL file and extract financial data.

    Args:
        file: Uploaded XBRL file
        company_id: Optional company ID to associate data with
        create_company: Whether to create a new company if not found
        db: Database session

    Returns:
        XBRLImportResponse with import results

    Raises:
        HTTPException: If file validation fails or parsing errors occur
    """
    logger.info(f"[XBRL IMPORT] START filename={file.filename} company_id={company_id} sector={sector} period_months={period_months} user_id={user_id}")

    # Validate file extension
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    file_ext = file.filename.lower().split('.')[-1]
    if file_ext not in ['xbrl', 'xml']:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type: .{file_ext}. Only .xbrl and .xml files are supported."
        )

    # Validate file size (max 50MB)
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB in bytes

    # Read file content
    try:
        content = await file.read()
        logger.info(f"[XBRL IMPORT] File read OK, size={len(content)} bytes")
    except Exception as e:
        logger.error(f"[XBRL IMPORT] Failed to read file: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to read file: {str(e)}")

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size is 50MB, received {len(content) / 1024 / 1024:.1f}MB"
        )

    if len(content) == 0:
        logger.error("[XBRL IMPORT] File is empty (0 bytes)")
        raise HTTPException(status_code=400, detail="File is empty")

    # Track upload (persist file + DB row BEFORE parsing so hard crashes are captured)
    upload_record = save_upload(db, user_id, file.filename, "xbrl", content, company_id=company_id, user_email=user.email)

    # Save to temporary file
    tmp_file = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xbrl') as tmp:
            tmp.write(content)
            tmp_file = tmp.name
        logger.info(f"[XBRL IMPORT] Temp file written: {tmp_file}")

        # Validate company ownership if company_id provided
        if company_id:
            validate_company_owned_by_user(db, company_id, user_id)
        elif create_company:
            check_company_limit(db, user_id)
        logger.info(f"[XBRL IMPORT] Ownership/limit check passed")

        # Import XBRL file using enhanced parser with reconciliation
        logger.info(f"[XBRL IMPORT] Calling import_xbrl_file_enhanced...")
        result = import_xbrl_file_enhanced(
            file_path=tmp_file,
            company_id=company_id,
            create_company=create_company,
            sector=sector,
            user_id=user_id,
            period_months=period_months,
        )
        logger.info(f"[XBRL IMPORT] Parser OK: years={result.get('years')} company_id={result.get('company_id')}")

        # period_months is now auto-detected from XBRL contexts by the parser
        # Log if partial years were detected
        detected_pm = result.get("year_period_months", {})
        if detected_pm:
            logger.info(f"[XBRL IMPORT] Auto-detected partial years: {detected_pm}")

        mark_success(db, upload_record, company_id=result.get("company_id"))
        logger.info(f"[XBRL IMPORT] SUCCESS")
        return XBRLImportResponse(**result)

    except XBRLParseError as e:
        mark_error(db, upload_record, e)
        logger.error(f"[XBRL IMPORT] XBRLParseError: {e}\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=422,
            detail={
                "success": False,
                "error": str(e),
                "error_type": "XBRLParseError",
                "details": "Failed to parse XBRL file. Check taxonomy version and file structure."
            }
        )
    except ValueError as e:
        mark_error(db, upload_record, e)
        logger.error(f"[XBRL IMPORT] ValueError: {e}\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=422,
            detail={
                "success": False,
                "error": str(e),
                "error_type": "ValueError",
                "details": "Invalid data in XBRL file"
            }
        )
    except HTTPException:
        # Ownership/limit failures are user errors, not parser bugs — re-raise without tracking as error
        raise
    except Exception as e:
        mark_error(db, upload_record, e)
        logger.error(f"[XBRL IMPORT] UNEXPECTED {type(e).__name__}: {e}\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "details": "Unexpected error during import"
            }
        )
    finally:
        # Clean up temporary file
        if tmp_file and os.path.exists(tmp_file):
            try:
                os.unlink(tmp_file)
            except Exception:
                pass  # Ignore cleanup errors


@router.post(
    "/import/csv",
    response_model=CSVImportResponse,
    summary="Import CSV Financial Data (TEBE Format)",
    description="""
    Upload and import a CSV file in TEBE format (semicolon-delimited).

    The CSV must contain financial data for a specific company and up to 2 years.
    Company ID must be provided (CSV files don't contain entity information).
    """
)
async def upload_csv(
    file: UploadFile = File(..., description="CSV file to import (.csv)"),
    company_id: int = Query(..., description="Company ID to import data for"),
    year1: Optional[int] = Query(None, description="First year (most recent, auto-detect if None)"),
    year2: Optional[int] = Query(None, description="Second year (previous, auto-detect if None)"),
    user_id: str = Depends(get_current_user_id),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Import CSV file (TEBE format) and extract financial data.

    Args:
        file: Uploaded CSV file
        company_id: Company ID to associate data with
        year1: First fiscal year (optional, auto-detected from CSV)
        year2: Second fiscal year (optional, auto-detected from CSV)
        db: Database session

    Returns:
        CSVImportResponse with import results

    Raises:
        HTTPException: If file validation fails or parsing errors occur
    """
    # Validate file extension
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    file_ext = file.filename.lower().split('.')[-1]
    if file_ext != 'csv':
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type: .{file_ext}. Only .csv files are supported."
        )

    # Validate company exists and belongs to user
    validate_company_owned_by_user(db, company_id, user_id)

    # Read file content
    try:
        content = await file.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {str(e)}")

    if len(content) == 0:
        raise HTTPException(status_code=400, detail="File is empty")

    # Track upload
    upload_record = save_upload(db, user_id, file.filename, "csv", content, company_id=company_id, user_email=user.email)

    # Save to temporary file
    tmp_file = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.csv', mode='wb') as tmp:
            tmp.write(content)
            tmp_file = tmp.name

        # Import CSV file using existing importer
        result = import_csv_file(
            file_path=tmp_file,
            company_id=company_id,
            year1=year1,
            year2=year2
        )

        mark_success(db, upload_record)
        return CSVImportResponse(**result)

    except ValueError as e:
        mark_error(db, upload_record, e)
        raise HTTPException(
            status_code=422,
            detail={
                "success": False,
                "error": str(e),
                "error_type": "ValueError",
                "details": "Failed to parse CSV file. Check format and data."
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        mark_error(db, upload_record, e)
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "details": "Unexpected error during import"
            }
        )
    finally:
        # Clean up temporary file
        if tmp_file and os.path.exists(tmp_file):
            try:
                os.unlink(tmp_file)
            except Exception:
                pass  # Ignore cleanup errors


@router.post(
    "/import/pdf",
    summary="Import PDF Balance Sheet (IV CEE Format)",
    description="""
    Upload and import an Italian balance sheet PDF file (IV CEE format).

    Supports:
    - Bilancio Micro (simplified format for small companies)
    - Bilancio Abbreviato (abbreviated format)
    - Bilancio Ordinario (full format)

    Uses PyMuPDF + Claude Haiku to extract table data from PDF and maps to Italian GAAP schema.
    Requires ANTHROPIC_API_KEY.

    Processing time: ~5 seconds per PDF.
    """
)
async def upload_pdf(
    file: UploadFile = File(..., description="PDF balance sheet file (.pdf)"),
    company_id: Optional[int] = Query(None, description="Existing company ID (optional)"),
    fiscal_year: int = Query(..., description="Fiscal year of the balance sheet"),
    company_name: Optional[str] = Query(None, description="Company name (for new company creation)"),
    create_company: bool = Query(True, description="Create company if not exists"),
    sector: Optional[int] = Query(None, ge=1, le=6, description="Company sector (1-6, used when creating new company)"),
    period_months: Optional[int] = Query(None, ge=1, le=12, description="Months in partial year (1-12). NULL = full 12-month year"),
    user_id: str = Depends(get_current_user_id),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Import PDF balance sheet and extract financial data using PyMuPDF + Claude Haiku.

    Args:
        file: Uploaded PDF file
        company_id: Optional company ID to associate data with
        fiscal_year: Fiscal year for the balance sheet (required)
        company_name: Company name (required if company_id not provided)
        create_company: Whether to create a new company if not found
        db: Database session

    Returns:
        Import results with balance sheet and income statement IDs

    Raises:
        HTTPException: If file validation fails or extraction errors occur
    """
    # Validate file extension
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    file_ext = file.filename.lower().split('.')[-1]
    if file_ext != 'pdf':
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type: .{file_ext}. Only .pdf files are supported."
        )

    # Validate file size (max 50MB)
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB in bytes

    # Read file content
    try:
        content = await file.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {str(e)}")

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size is 50MB, received {len(content) / 1024 / 1024:.1f}MB"
        )

    if len(content) == 0:
        raise HTTPException(status_code=400, detail="File is empty")

    # Validate input: either company_id or (create_company + company_name)
    if not company_id and (not create_company or not company_name):
        raise HTTPException(
            status_code=400,
            detail="Either company_id or (create_company=True and company_name) must be provided"
        )

    # Track upload
    upload_record = save_upload(db, user_id, file.filename, "pdf", content, company_id=company_id, user_email=user.email)

    # Save to temporary file
    tmp_file = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
            tmp.write(content)
            tmp_file = tmp.name

        # Validate company ownership if company_id provided
        if company_id:
            validate_company_owned_by_user(db, company_id, user_id)
        elif create_company:
            check_company_limit(db, user_id)

        # Import PDF file (importer handles period_months + prior year internally)
        result = import_pdf_balance_sheet(
            file_path=tmp_file,
            company_id=company_id,
            fiscal_year=fiscal_year,
            company_name=company_name,
            create_company=create_company,
            sector=sector,
            period_months=period_months,
            user_id=user_id,
        )

        mark_success(db, upload_record, company_id=result.get("company_id") if isinstance(result, dict) else None)
        return result

    except PDFImportError as e:
        mark_error(db, upload_record, e)
        raise HTTPException(
            status_code=422,
            detail={
                "success": False,
                "error": str(e),
                "error_type": "PDFImportError",
                "details": "Failed to extract data from PDF. Check file format and content."
            }
        )
    except ValueError as e:
        mark_error(db, upload_record, e)
        raise HTTPException(
            status_code=422,
            detail={
                "success": False,
                "error": str(e),
                "error_type": "ValueError",
                "details": "Invalid data in PDF file"
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        mark_error(db, upload_record, e)
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "details": "Unexpected error during import"
            }
        )
    finally:
        # Clean up temporary file
        if tmp_file and os.path.exists(tmp_file):
            try:
                os.unlink(tmp_file)
            except Exception:
                pass  # Ignore cleanup errors


@router.get(
    "/import/capabilities",
    summary="Import capabilities",
    description="Reports whether the OCR endpoint is operationally enabled. The UI keeps "
                "both PDF choices visible; this value is the emergency backend kill switch.",
)
async def import_capabilities(
    user_id: str = Depends(get_current_user_id),
):
    return {"ocr_available": bool(settings.MINERU_OCR_ENABLED)}


@router.post(
    "/import/pdf-ocr",
    summary="Import PDF via MinerU OCR",
    description="""
    Import an Italian balance sheet PDF using the MinerU OCR service (Docker), then the
    existing deterministic + LLM accounting pipeline for classification, reconciliation
    and quadratura. Use for scanned / image-only PDFs where standard text extraction is
    insufficient.

    MinerU is an extractor only: it never decides quadrature, invents detail or bypasses
    the accounting gates. If MinerU is disabled or unreachable there is NO silent fallback
    to /import/pdf (503). Errors never leave partial FinancialYear records.
    """,
)
async def upload_pdf_ocr(
    file: UploadFile = File(..., description="PDF balance sheet file (.pdf)"),
    company_id: Optional[int] = Query(None, description="Existing company ID (optional)"),
    fiscal_year: int = Query(..., description="Fiscal year of the balance sheet"),
    company_name: Optional[str] = Query(None, description="Company name (for new company creation)"),
    create_company: bool = Query(True, description="Create company if not exists"),
    sector: Optional[int] = Query(None, ge=1, le=6, description="Company sector (1-6)"),
    period_months: Optional[int] = Query(None, ge=1, le=12, description="Months in partial year (1-12). NULL = full year"),
    user_id: str = Depends(get_current_user_id),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Import here so a MinerU-less deployment can still import this module.
    from app.services.mineru_client import (
        MinerUClient,
        MinerUUnavailableError,
        MinerUTimeoutError,
        MinerUInvalidOutputError,
        MinerUContractError,
        MinerUError,
    )
    from importers.mineru_adapter import build_extraction_context

    # 1. Feature flag - the only rollback switch.
    if not settings.MINERU_OCR_ENABLED:
        raise HTTPException(
            status_code=503,
            detail={
                "success": False,
                "error_code": "MINERU_DISABLED",
                "message": "L'import OCR (MinerU) non e abilitato.",
            },
        )

    # 3-5. Validate PDF + resolve company target BEFORE spending OCR resources.
    content = await _read_and_validate_pdf(file, company_id, create_company, company_name)

    # Ownership and quota checks precede tracking: an unauthorized request must
    # not create a pending upload row for a company the caller does not own.
    if company_id:
        validate_company_owned_by_user(db, company_id, user_id)
    elif create_company:
        check_company_limit(db, user_id)

    # Track the heavy OCR job only after all request-level authorization gates.
    upload_record = save_upload(
        db,
        user_id,
        file.filename,
        "pdf_ocr",
        content,
        company_id=company_id,
        user_email=user.email,
    )

    tmp_file = None
    try:

        # 7. MinerU: health probe then parse (async I/O - does not block the loop).
        client = MinerUClient.from_settings(settings)
        await client.health()
        raw = await client.parse_pdf(content=content, filename=file.filename)

        # 8. Normalize (CPU-bound) off the event loop.
        context = await run_in_threadpool(build_extraction_context, raw)

        # 9. Reject an OCR result with no usable text.
        if not (context.full_text or "").strip():
            raise HTTPException(
                status_code=422,
                detail={
                    "success": False,
                    "error_code": "MINERU_EMPTY",
                    "message": "L'OCR non ha prodotto testo sufficiente dal documento.",
                },
            )

        # 10. Accounting pipeline (sync, gated) off the event loop.
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
            tmp.write(content)
            tmp_file = tmp.name

        result = await run_in_threadpool(
            import_pdf_balance_sheet,
            file_path=tmp_file,
            company_id=company_id,
            fiscal_year=fiscal_year,
            company_name=company_name,
            create_company=create_company,
            sector=sector,
            period_months=period_months,
            user_id=user_id,
            extraction_context=context,
        )

        mark_success(db, upload_record, company_id=result.get("company_id") if isinstance(result, dict) else None)
        return result

    except MinerUTimeoutError as e:
        mark_error(db, upload_record, e)
        raise HTTPException(
            status_code=504,
            detail={"success": False, "error_code": "MINERU_TIMEOUT",
                    "message": "Il servizio OCR non ha completato l'estrazione entro il tempo previsto."},
        )
    except MinerUUnavailableError as e:
        mark_error(db, upload_record, e)
        raise HTTPException(
            status_code=503,
            detail={"success": False, "error_code": "MINERU_UNAVAILABLE",
                    "message": "Il servizio OCR non e al momento disponibile."},
        )
    except MinerUInvalidOutputError as e:
        mark_error(db, upload_record, e)
        raise HTTPException(
            status_code=422,
            detail={"success": False, "error_code": "MINERU_INVALID_OUTPUT",
                    "message": "L'OCR non ha prodotto un risultato utilizzabile dal documento."},
        )
    except MinerUContractError as e:
        mark_error(db, upload_record, e)
        raise HTTPException(
            status_code=503,
            detail={"success": False, "error_code": "MINERU_CONTRACT_MISMATCH",
                    "message": "La versione del servizio OCR non e compatibile con il backend."},
        )
    except PDFImportError as e:
        mark_error(db, upload_record, e)
        raise HTTPException(
            status_code=422,
            detail={"success": False, "error": str(e), "error_type": "PDFImportError",
                    "details": "Import contabile fallito sul risultato OCR."},
        )
    except ValueError as e:
        mark_error(db, upload_record, e)
        raise HTTPException(
            status_code=422,
            detail={"success": False, "error": str(e), "error_type": "ValueError",
                    "details": "Dati non validi nel PDF."},
        )
    except HTTPException as e:
        mark_error(db, upload_record, e)
        raise
    except MinerUError as e:
        mark_error(db, upload_record, e)
        raise HTTPException(
            status_code=503,
            detail={"success": False, "error_code": "MINERU_ERROR",
                    "message": "Errore del servizio OCR."},
        )
    except Exception as e:
        mark_error(db, upload_record, e)
        raise HTTPException(
            status_code=500,
            detail={"success": False, "error_type": type(e).__name__,
                    "details": "Errore interno durante l'import OCR."},
        )
    finally:
        if tmp_file and os.path.exists(tmp_file):
            try:
                os.unlink(tmp_file)
            except Exception:
                pass
