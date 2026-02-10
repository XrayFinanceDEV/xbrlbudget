"""
API endpoints for data import (XBRL, CSV, and PDF)
"""
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
import tempfile
import os

from app.core.database import get_db
from app.schemas.imports import XBRLImportResponse, CSVImportResponse, ImportError
from importers.xbrl_parser_enhanced import import_xbrl_file_enhanced, XBRLParseError
from importers.csv_importer import import_csv_file
from importers.pdf_importer import import_pdf_balance_sheet, PDFImportError

router = APIRouter()


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
    db: Session = Depends(get_db)
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {str(e)}")

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size is 50MB, received {len(content) / 1024 / 1024:.1f}MB"
        )

    if len(content) == 0:
        raise HTTPException(status_code=400, detail="File is empty")

    # Save to temporary file
    tmp_file = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xbrl') as tmp:
            tmp.write(content)
            tmp_file = tmp.name

        # Import XBRL file using enhanced parser with reconciliation
        result = import_xbrl_file_enhanced(
            file_path=tmp_file,
            company_id=company_id,
            create_company=create_company,
            sector=sector
        )

        return XBRLImportResponse(**result)

    except XBRLParseError as e:
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
        raise HTTPException(
            status_code=422,
            detail={
                "success": False,
                "error": str(e),
                "error_type": "ValueError",
                "details": "Invalid data in XBRL file"
            }
        )
    except Exception as e:
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
    db: Session = Depends(get_db)
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

    # Validate company exists
    from database.models import Company
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail=f"Company with ID {company_id} not found")

    # Read file content
    try:
        content = await file.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {str(e)}")

    if len(content) == 0:
        raise HTTPException(status_code=400, detail="File is empty")

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

        return CSVImportResponse(**result)

    except ValueError as e:
        raise HTTPException(
            status_code=422,
            detail={
                "success": False,
                "error": str(e),
                "error_type": "ValueError",
                "details": "Failed to parse CSV file. Check format and data."
            }
        )
    except Exception as e:
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
    
    Uses Docling AI to extract table data from PDF and maps to Italian GAAP schema.
    
    Processing time: 3-10 seconds per PDF (first run downloads models ~2GB).
    """
)
async def upload_pdf(
    file: UploadFile = File(..., description="PDF balance sheet file (.pdf)"),
    company_id: Optional[int] = Query(None, description="Existing company ID (optional)"),
    fiscal_year: int = Query(..., description="Fiscal year of the balance sheet"),
    company_name: Optional[str] = Query(None, description="Company name (for new company creation)"),
    create_company: bool = Query(True, description="Create company if not exists"),
    sector: Optional[int] = Query(None, ge=1, le=6, description="Company sector (1-6, used when creating new company)"),
    db: Session = Depends(get_db)
):
    """
    Import PDF balance sheet and extract financial data using Docling AI.

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

    # Save to temporary file
    tmp_file = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
            tmp.write(content)
            tmp_file = tmp.name

        # Import PDF file using Docling
        result = import_pdf_balance_sheet(
            file_path=tmp_file,
            company_id=company_id,
            fiscal_year=fiscal_year,
            company_name=company_name,
            create_company=create_company,
            sector=sector
        )

        return result

    except PDFImportError as e:
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
        raise HTTPException(
            status_code=422,
            detail={
                "success": False,
                "error": str(e),
                "error_type": "ValueError",
                "details": "Invalid data in PDF file"
            }
        )
    except Exception as e:
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
